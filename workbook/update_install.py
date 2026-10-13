"""Verified file-only updates with a durable rollback journal; user files are excluded."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import time
import uuid
import zipfile
from .updates import EXE, UPDATER, MANIFEST, UpdateError, version_key

JOURNAL = '.update-transaction.json'
LOCK = '.update-lock.json'
MAX_EXPANDED = 800 * 1024 * 1024
ROOT_FILES = {EXE, UPDATER, '開始使用.txt', '檔案校驗.json', MANIFEST, '修復未完成更新.cmd'}
BRIDGES = {'access_bridge.ps1', 'check_connection.ps1', 'catalog_bridge.ps1',
           'diagnose_connection.ps1', 'install_access_runtime.ps1'}


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in name.split('/')):
        return False
    if any(re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p) for p in path.parts):
        return False
    if path.suffix.lower() in {'.mdb', '.accdb', '.ldb', '.laccdb', '.pdf', '.jpg', '.png'}:
        return False
    if path.name.lower() in {'preferences.json', 'settings.json', 'layout_settings.json', 'catalog.json', 'system_seed.json'}:
        return False
    if name in ROOT_FILES:
        return True
    if len(path.parts) < 2:
        return False
    head = path.parts[0]
    if head == '_internal':
        return not any(p.startswith('.') for p in path.parts)
    if head == 'workbook':
        return len(path.parts) == 2 and path.name in BRIDGES
    if head == 'assets':
        return name == 'assets/demo.json'
    if head == 'dependencies':
        return len(path.parts) == 2 and path.name in {'AccessRuntime_x86.exe', 'AccessRuntime_x64.exe', 'sources.json', '安裝步驟.txt'}
    return False


def contained(root, name):
    if not safe_name(name):
        raise UpdateError('更新包包含不允許替換的檔案。')
    root = Path(root).resolve()
    target = root.joinpath(*PurePosixPath(name).parts)
    if not target.resolve().is_relative_to(root):
        raise UpdateError('更新目的路徑超出安裝資料夾。')
    current = target
    while current != root:
        if current.is_symlink() or (current.exists() and getattr(current, 'is_junction', lambda: False)()):
            raise UpdateError('更新目的路徑含連結，請改用一般資料夾。')
        current = current.parent
    return target


def file_hash(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def unpack(archive, stage, expected_version):
    """Inspect the whole ZIP before extraction, reject duplicates, links and traversal."""
    stage = Path(stage)
    with zipfile.ZipFile(archive) as source:
        members = {}
        seen = set()
        expanded = 0
        if len(source.infolist()) > 5000:
            raise UpdateError('更新包檔案數量異常。')
        for entry in source.infolist():
            if entry.is_dir():
                continue
            prefix = '工作簿輸出/'
            if not entry.filename.startswith(prefix):
                raise UpdateError('更新包根目錄不正確。')
            name = entry.filename[len(prefix):]
            if not safe_name(name) or name.casefold() in seen:
                raise UpdateError('更新包含禁止、重複或無效路徑。')
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise UpdateError('更新包不可包含連結或加密檔案。')
            seen.add(name.casefold())
            expanded += entry.file_size
            if expanded > MAX_EXPANDED:
                raise UpdateError('更新包解壓縮大小超過限制。')
            members[name] = entry
        if MANIFEST not in members or members[MANIFEST].file_size > 2 * 1024 * 1024:
            raise UpdateError('更新包缺少有效的程式清單。')
        manifest = json.loads(source.read(members[MANIFEST]))
        if manifest.get('version') != expected_version or manifest.get('format') != 1:
            raise UpdateError('更新包版本與 Release 不符。')
        version_key(expected_version)
        hashes = manifest.get('files', {})
        if set(hashes) != set(members) - {MANIFEST} or not {EXE, UPDATER, '_internal/python312.dll'} <= set(hashes):
            raise UpdateError('更新包程式清單不完整。')
        for name, entry in members.items():
            dest = contained(stage, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as src, dest.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            if name != MANIFEST and file_hash(dest) != hashes[name]:
                raise UpdateError('更新包內的程式檔案校驗失敗。')
    return sorted(members)


def process_running(pid):
    if os.name != 'nt':
        return False
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    handle = kernel.OpenProcess(0x100000, False, int(pid))
    if not handle:
        return ctypes.get_last_error() == 5  # Fail closed if access is denied.
    try:
        return kernel.WaitForSingleObject(handle, 0) == 0x102
    finally:
        kernel.CloseHandle(handle)


def application_pids(executable):
    """Enumerate executable paths without reading process command lines or user data."""
    if os.name != 'nt':
        return []
    import ctypes
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('th32ProcessID', w.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', w.DWORD),
                    ('cntThreads', w.DWORD), ('th32ParentProcessID', w.DWORD),
                    ('pcPriClassBase', w.LONG), ('dwFlags', w.DWORD), ('szExeFile', w.WCHAR * 260)]
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateToolhelp32Snapshot.restype = w.HANDLE
    k.OpenProcess.restype = w.HANDLE
    k.OpenProcess.argtypes = (w.DWORD, w.BOOL, w.DWORD)
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = (w.HANDLE, ctypes.POINTER(Entry))
    k.QueryFullProcessImageNameW.argtypes = (w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD))
    k.CloseHandle.argtypes = (w.HANDLE,)
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise UpdateError('無法檢查程式是否已關閉。')
    result = []
    try:
        entry = Entry(); entry.dwSize = ctypes.sizeof(entry)
        ok = k.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.casefold() == Path(executable).name.casefold():
                handle = k.OpenProcess(0x1000, False, entry.th32ProcessID)
                if not handle:
                    raise UpdateError('另有無法檢查的工作簿程式，請先關閉。')
                try:
                    size = w.DWORD(32768); text = ctypes.create_unicode_buffer(size.value)
                    if not k.QueryFullProcessImageNameW(handle, 0, text, ctypes.byref(size)):
                        raise UpdateError('無法確認其他工作簿程式的安裝位置。')
                    if os.path.normcase(os.path.abspath(text.value)) == os.path.normcase(str(Path(executable).resolve())):
                        result.append(entry.th32ProcessID)
                finally:
                    k.CloseHandle(handle)
            ok = k.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        k.CloseHandle(snapshot)
    return result


def wait_closed(root, parent_pid, progress, timeout=45):
    until = time.monotonic() + timeout
    while process_running(parent_pid) or application_pids(Path(root) / EXE):
        if time.monotonic() >= until:
            raise UpdateError('工作簿仍在執行，未更換任何檔案。請關閉其他視窗後再試。')
        progress('等待工作簿關閉，請先關閉此資料夾的其他工作簿視窗…')
        time.sleep(.2)


def replace_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + '.updating')
    try:
        shutil.copy2(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def rollback(root):
    root = Path(root).resolve()
    journal_path = root / JOURNAL
    data = json.loads(journal_path.read_text(encoding='utf-8'))
    identifier = data.get('id', '')
    if not re.fullmatch('[a-f0-9]{32}', identifier):
        raise UpdateError('更新復原記錄無效，請保留 .update-backups 並手動還原。')
    backup = root / '.update-backups' / identifier
    if backup.is_symlink() or not backup.resolve().is_relative_to(root):
        raise UpdateError('更新備份路徑不正確。')
    # Validate every entry and backup before modifying any installed file.
    for name, digest in data['files'].items():
        contained(root, name)
        if digest is not None and file_hash(contained(backup, name)) != digest:
            raise UpdateError('更新備份校驗失敗，請保留備份並手動還原。')
    for name, digest in reversed(list(data['files'].items())):
        target = contained(root, name)
        if digest is None:
            target.unlink(missing_ok=True)
        elif target.is_file() and file_hash(target) == digest:
            # A locked file may never have been changed; no need to replace it again.
            continue
        else:
            replace_file(contained(backup, name), target)
    journal_path.unlink()


def install(stage, root, names, expected_version, progress=lambda _: None):
    root, stage = Path(root).resolve(), Path(stage).resolve()
    if (root / JOURNAL).exists():
        raise UpdateError('上次更新未完成，請先執行復原工具。')
    names = sorted(set(names))
    # Remove only stale program files explicitly listed by a prior public release.
    previous = root / MANIFEST
    if previous.exists():
        old = json.loads(previous.read_text(encoding='utf-8'))
        names = sorted(set(names) | {n for n in old.get('files', {}) if safe_name(n)})
    for name in names:
        target = contained(root, name)
        if target.exists() and not target.is_file():
            raise UpdateError('程式檔案位置被資料夾占用，未開始更新。')
    required = sum((root / name).stat().st_size for name in names if (root / name).is_file())
    required += sum(p.stat().st_size for p in stage.rglob('*') if p.is_file()) + 20 * 1024 * 1024
    if shutil.disk_usage(root).free < required:
        raise UpdateError('磁碟空間不足，需保留更新及還原用空間。')
    identifier = uuid.uuid4().hex
    backup = root / '.update-backups' / identifier
    if not backup.resolve().is_relative_to(root):
        raise UpdateError('備份資料夾不可連到其他位置。')
    backup.mkdir(parents=True)
    old_files = {}
    for name in names:
        target = contained(root, name)
        old_files[name] = file_hash(target) if target.is_file() else None
        if target.is_file():
            dest = contained(backup, name); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dest)
    atomic_json(root / JOURNAL, dict(id=identifier, version=expected_version, files=old_files))
    try:
        for index, name in enumerate(names):
            progress(f'安裝更新：{index + 1}/{len(names)}')
            source = contained(stage, name); target = contained(root, name)
            if source.is_file():
                replace_file(source, target)
            else:
                target.unlink(missing_ok=True)
        manifest = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
        if manifest['version'] != expected_version:
            raise UpdateError('安裝版本不正確。')
        for name, digest in manifest['files'].items():
            if file_hash(contained(root, name)) != digest:
                raise UpdateError('安裝後程式檔案校驗失敗。')
    except Exception:
        try:
            rollback(root)
        except Exception as error:
            raise UpdateError('更新失敗且自動還原未完成。請執行「修復未完成更新.cmd」；備份已保留。') from error
        raise
    # Keep the journal until startup smoke validation completes.
    return backup


def smoke(root, report, expected_version):
    try:
        result = subprocess.run([str(Path(root) / EXE), '--update-smoke', str(report)],
            cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        data = json.loads(Path(report).read_text(encoding='utf-8'))
        if result.returncode != 0 or data != {'ok': True, 'version': expected_version}:
            raise UpdateError('新版程式啟動檢查未通過。')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise UpdateError('新版程式啟動檢查未通過。') from None
