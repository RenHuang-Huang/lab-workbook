"""Local Access diagnostics and architecture selection; no patient data in reports."""
from dataclasses import dataclass
from pathlib import Path
import copy, datetime, hashlib, json, os, re, subprocess, threading, time
from .paths import ROOT
from .version import APP_VERSION

PROVIDERS = ('Microsoft.ACE.OLEDB.12.0', 'Microsoft.ACE.OLEDB.16.0')
INSTALLERS = {
    'x86': ('AccessRuntime_x86.exe', 'cb6e704a50d2d58c12bb587eb4cbf5561f9c2565b5ac07a5c88564ae03de39dd'),
    'x64': ('AccessRuntime_x64.exe', '5174d8fa1767a9bc118cc992f4d702a4c7782834fca082ebed2c88fd11c3d2db'),
}
MESSAGES = {
    'OK': 'DB連線成功',
    'FILE_NOT_FOUND': '找不到資料庫檔案。請重新選擇現場的 MDB／ACCDB；若在網路磁碟，請先確認可連到該磁碟。',
    'ACCESS_DENIED': '資料庫或所在資料夾的讀取權限不足。請由現場管理員授予目前帳號必要權限。',
    'FILE_UNREADABLE': '資料庫目前無法讀取。請確認磁碟／網路可用，且未被其他程式獨占。',
    'DATABASE_LOCKED': '資料庫被其他程式獨占或鎖定。請解除獨占後重試，或選擇穩定的資料庫備份。',
    'PASSWORD_REQUIRED': '資料庫需要密碼；目前不支援此加密連線。請提供可唯讀存取的資料庫備份。',
    'FORMAT_INVALID': 'Access 引擎無法辨識此檔案，可能格式不支援或檔案損壞。請核對檔案或使用完好的備份。',
    'SCHEMA_MISMATCH': '資料庫缺少程式需要的資料表或欄位。請確認選到檢驗系統的正確資料庫版本。',
    'NO_PROVIDER': '未找到可用的 Access ACE 驅動，已檢查本機可用的 32／64 位元環境。',
    'NO_POWERSHELL': '找不到 Windows PowerShell。請由現場管理員修復 Windows 系統元件。',
    'BRIDGE_MISSING': '程式的連線元件不完整，請重新完整解壓縮部署包，勿只複製 EXE。',
    'DRIVER_CRASH': 'Access 驅動程序異常結束（0xC0000005），已嘗試其他位元環境；請保留連線診斷供檢查。',
    'TIMEOUT': '單次連線檢查超過30秒，請確認資料庫網路位置及檔案可用。',
    'PROTOCOL_ERROR': 'Windows 連線程序未正常回傳診斷，可能被安全軟體或系統政策阻擋。',
    'PROCESS_FAILED': '無法啟動 Windows 連線程序，請檢查系統政策及程式執行權限。',
    'ENVIRONMENT_FAILED': 'Windows 元件或 Office 安裝資訊無法讀取，請保留連線診斷供現場管理員檢查。',
    'OPEN_FAILED': 'Access 驅動存在，但開啟資料庫失敗。已記錄錯誤碼，請檢查現場 Office／資料庫環境。',
    'READ_FAILED': '連線檢查成功，但資料擷取失敗。請核對檔案是否在讀取期間變動，並保留診斷紀錄。',
}
CODES = set(MESSAGES)
_selected = {}
_reports = {}
_lock = threading.RLock()
_install_lock = threading.Lock()


@dataclass(frozen=True)
class Runtime:
    shell: str
    provider: str
    bits: int


def windows_shells():
    """Use .NET Framework Windows PowerShell, independent of PATH/pwsh/Office bitness."""
    base = Path(os.environ.get('SystemRoot', 'C:/Windows'))
    system = 'Sysnative' if os.environ.get('PROCESSOR_ARCHITEW6432') else 'System32'
    candidates = [(base/system/'WindowsPowerShell/v1.0/powershell.exe', 64),
                  (base/'SysWOW64/WindowsPowerShell/v1.0/powershell.exe', 32)]
    return [(str(path), bits) for path, bits in candidates if path.is_file()]


def command(shell, script, *args):
    return [shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-Mta', '-ExecutionPolicy', 'Bypass',
            '-File', str(ROOT/'workbook'/script), *map(str, args)]


def run_process(args, timeout=30):
    environment = os.environ.copy()
    # A Python/PowerShell 7 host can inherit an incompatible module search path.
    # Keep this change in the child process; use Windows' own matching modules.
    environment['PSModulePath'] = str(Path(args[0]).parent/'Modules')
    return subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=timeout, env=environment)


def key_for(database):
    return os.path.normcase(str(Path(database).absolute()))


def sanitize(raw, bits):
    """Reject unexpected fields, text, and protocol versions; diagnostics cannot leak raw errors."""
    if not isinstance(raw, dict) or raw.get('protocol') != 2:
        return {'ok': False, 'code': 'PROTOCOL_ERROR', 'bits': bits}
    code = raw.get('code') if raw.get('code') in CODES else 'PROTOCOL_ERROR'
    provider = raw.get('provider') if raw.get('provider') in PROVIDERS else ''
    ok = raw.get('ok') is True and code == 'OK' and bool(provider) and raw.get('bits') == bits
    if code == 'OK' and not ok:
        code = 'PROTOCOL_ERROR'
    return {'ok': ok, 'code': code, 'bits': bits, 'provider': provider,
            'phase': raw.get('phase') if raw.get('phase') in ('environment','file','provider','open','schema') else '',
            'native_errors': [v for v in raw.get('native_errors', []) if type(v) is int][:12],
            'hresult': raw.get('hresult') if re.fullmatch(r'0x[0-9A-Fa-f]{8}', str(raw.get('hresult', ''))) else '',
            'office_platform': raw.get('office_platform') if raw.get('office_platform') in ('x86','x64') else '',
            'office_msi': raw.get('office_msi') is True}


def probe(shell, bits, database):
    try:
        p = run_process(command(shell, 'diagnose_connection.ps1', '-Database', database))
        if p.returncode in (-1073741819, 3221225477):
            return {'ok': False, 'code': 'DRIVER_CRASH', 'bits': bits}
        if p.returncode:
            return {'ok': False, 'code': 'PROCESS_FAILED', 'bits': bits}
        return sanitize(json.loads(p.stdout.decode('utf-8-sig')), bits)
    except subprocess.TimeoutExpired:
        return {'ok': False, 'code': 'TIMEOUT', 'bits': bits}
    except (ValueError, UnicodeError, TypeError):
        return {'ok': False, 'code': 'PROTOCOL_ERROR', 'bits': bits}
    except OSError:
        return {'ok': False, 'code': 'PROCESS_FAILED', 'bits': bits}


def record(database, report):
    saved = dict(report, app_version=APP_VERSION, checked_at=datetime.datetime.now().isoformat(timespec='seconds'))
    with _lock:
        _reports[key_for(database)] = saved
        try:
            from .core import save_json
            save_json(ROOT/'diagnostics/connection_latest.json', saved)
        except OSError:
            pass
    return copy.deepcopy(saved)


def last_report(database):
    with _lock:
        return copy.deepcopy(_reports.get(key_for(database), {}))


def diagnose(database):
    key = key_for(database)
    with _lock:
        _selected.pop(key, None)
    try:
        if not str(database).strip() or Path(database).suffix.lower() not in ('.mdb','.accdb'):
            return record(database, {'ok': False, 'code': 'FILE_NOT_FOUND', 'attempts': []})
        # Opening without reading catches actual permissions; never inspect patient bytes.
        with Path(database).open('rb'):
            pass
    except FileNotFoundError:
        return record(database, {'ok': False, 'code': 'FILE_NOT_FOUND', 'attempts': []})
    except PermissionError:
        return record(database, {'ok': False, 'code': 'ACCESS_DENIED', 'attempts': []})
    except OSError:
        return record(database, {'ok': False, 'code': 'FILE_UNREADABLE', 'attempts': []})
    shells = windows_shells()
    if not shells:
        return record(database, {'ok': False, 'code': 'NO_POWERSHELL', 'attempts': []})
    if not (ROOT/'workbook/diagnose_connection.ps1').is_file():
        return record(database, {'ok': False, 'code': 'BRIDGE_MISSING', 'attempts': []})
    attempts = []
    for shell, bits in shells:
        result = probe(shell, bits, database)
        attempts.append(result)
        if result['ok']:
            with _lock:
                _selected[key] = Runtime(shell, result['provider'], bits)
            return record(database, dict(result, attempts=attempts))
    # File/schema errors are more informative than the other architecture missing a driver.
    priority = ('SCHEMA_MISMATCH','PASSWORD_REQUIRED','FORMAT_INVALID','ACCESS_DENIED','DATABASE_LOCKED',
                'FILE_NOT_FOUND','FILE_UNREADABLE','DRIVER_CRASH','TIMEOUT','OPEN_FAILED',
                'ENVIRONMENT_FAILED','PROCESS_FAILED','PROTOCOL_ERROR','NO_PROVIDER')
    chosen = min(attempts, key=lambda a: priority.index(a['code']) if a['code'] in priority else 99)
    return record(database, dict(chosen, attempts=attempts))


def describe(report):
    text = MESSAGES.get(report.get('code'), MESSAGES['OPEN_FAILED'])
    if report.get('ok'):
        return text
    return text + f"［{report.get('code', 'OPEN_FAILED')}］"


def get_runtime(database):
    with _lock:
        selected = _selected.get(key_for(database))
    if selected:
        return selected
    result = diagnose(database)
    if not result['ok']:
        raise ValueError(describe(result))
    with _lock:
        return _selected[key_for(database)]


def read_bridge(database, script, args, timeout):
    if not (ROOT/'workbook'/script).is_file():
        raise ValueError(MESSAGES['BRIDGE_MISSING'])
    runtime = get_runtime(database)
    def invoke(selected):
        return run_process(command(selected.shell, script, '-Database', database, '-Provider', selected.provider, *args), timeout)
    try:
        p = invoke(runtime)
    except (OSError, subprocess.TimeoutExpired):
        p = None
    if p is not None and p.returncode == 0:
        return
    result = diagnose(database)
    if result['ok']:
        replacement = get_runtime(database)
        if replacement != runtime:
            try:
                p = invoke(replacement)
                if p.returncode == 0:
                    return
            except (OSError, subprocess.TimeoutExpired):
                pass
        result = record(database, dict(result, ok=False, code='READ_FAILED'))
    raise ValueError(describe(result))


def repair_plan(report):
    if report.get('code') != 'NO_PROVIDER' or not report.get('attempts'):
        return None, '這個問題不適合安裝驅動，請依診斷原因處理。'
    if any(a.get('code') != 'NO_PROVIDER' for a in report['attempts']):
        return None, '環境檢查尚未完成，不能確定缺少驅動，請先處理診斷錯誤。'
    if any(a.get('office_msi') for a in report['attempts']):
        return None, '偵測到 MSI 版 Office，與新版 Access Runtime 安裝方式不相容；請由現場管理員處理 Office 安裝，程式不會移除既有 Office。'
    platforms = {a['office_platform'] for a in report['attempts'] if a.get('office_platform')}
    if len(platforms) > 1:
        return None, 'Office 位元資訊不一致，請由現場管理員確認，未啟動安裝。'
    return next(iter(platforms), 'x64'), ''


def install_runtime(report, progress=lambda message: None):
    arch, reason = repair_plan(report)
    if not arch:
        return {'code': 'REPAIR_NOT_APPLICABLE', 'message': reason}
    if not _install_lock.acquire(blocking=False):
        return {'code': 'INSTALLER_BUSY', 'message': '另一個相依元件安裝正在執行。'}
    try:
        name, digest = INSTALLERS[arch]
        installer = ROOT/'dependencies'/name
        if not installer.is_file():
            return {'code': 'INSTALLER_MISSING', 'message': '找不到隨附的 Access Runtime 安裝程式，請完整解壓縮含相依元件的部署包。'}
        if hashlib.sha256(installer.read_bytes()).hexdigest() != digest:
            return {'code': 'INSTALLER_UNTRUSTED', 'message': '安裝程式校驗不符，已停止執行。請重新取得部署包。'}
        shells = windows_shells()
        if not shells:
            return {'code': 'NO_POWERSHELL', 'message': MESSAGES['NO_POWERSHELL']}
        progress(f'缺少 ACE，正在啟動 Microsoft Access Runtime {arch} 安裝。需要網路，請完成 Windows 管理員權限及 Microsoft 安裝畫面。')
        try:
            p = run_process(command(shells[0][0], 'install_access_runtime.ps1', '-Installer', installer,
                                    '-ExpectedHash', digest), timeout=1800)
            raw = json.loads(p.stdout.decode('utf-8-sig')) if p.returncode == 0 else {}
            code = raw.get('code')
            if code not in ('INSTALLER_EXIT','INSTALLER_UNTRUSTED','INSTALLER_CANCELLED','INSTALLER_FAILED'):
                code = 'INSTALLER_FAILED'
            exit_code = raw.get('exit_code') if type(raw.get('exit_code')) is int else None
            messages = {'INSTALLER_CANCELLED':'已取消 Windows 管理員權限或安裝，仍未連線。',
                        'INSTALLER_UNTRUSTED':'Microsoft 數位簽章或檔案校驗未通過，未執行安裝。',
                        'INSTALLER_FAILED':'無法完成安裝。請確認網路、管理員權限及 Microsoft 安裝畫面訊息。',
                        'INSTALLER_EXIT':'Microsoft 安裝程式已結束，正在重新測試連線。'}
            return {'code': code, 'exit_code': exit_code, 'arch': arch, 'message': messages[code]}
        except subprocess.TimeoutExpired:
            return {'code': 'INSTALLER_TIMEOUT', 'message': '安裝仍未完成，請查看 Microsoft 安裝畫面；完成後再按測試連線。'}
        except (OSError,ValueError,UnicodeError):
            return {'code': 'INSTALLER_FAILED', 'message': '安裝啟動失敗，請確認系統執行權限。'}
    finally:
        _install_lock.release()
