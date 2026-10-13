"""Public GitHub releases; no credentials, database or settings sent to the server."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'RenHuang-Huang/lab-workbook'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
MAX_DOWNLOAD = 250 * 1024 * 1024
EXE = '工作簿輸出.exe'
UPDATER = 'WorkbookUpdater.exe'
MANIFEST = 'release-manifest.json'


class UpdateError(ValueError):
    pass


def version_key(value):
    match = re.fullmatch(r'(\d{8})-v([1-9]\d*)', str(value))
    if not match:
        raise UpdateError('發行版本格式不正確。')
    return int(match[1]), int(match[2])


def asset_name(version):
    version_key(version)
    return f'lab-workbook-{version}-windows-x64.zip'


def validate_release(release):
    if release.get('draft') or release.get('prerelease'):
        raise UpdateError('只接受正式發行版本。')
    version = release.get('tag_name', '')
    version_key(version)
    matches = [a for a in release.get('assets', []) if a.get('name') == asset_name(version)]
    if len(matches) != 1:
        raise UpdateError('此 Release 缺少 Windows 64 位元更新包，請稍後重試。')
    asset = matches[0]
    digest = asset.get('digest', '')
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
        raise UpdateError('GitHub 尚未提供更新包校驗值，請稍後重試。')
    size = asset.get('size')
    if not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD:
        raise UpdateError('更新包大小不正確。')
    expected = f'https://github.com/{REPOSITORY}/releases/download/{version}/{asset_name(version)}'
    if asset.get('browser_download_url') != expected or asset.get('state') != 'uploaded':
        raise UpdateError('更新包來源不符合本程式的官方倉庫。')
    return dict(version=version, url=expected, sha256=digest[7:].lower(), size=size)


def request(url):
    return urllib.request.Request(url, headers={'User-Agent': 'LabWorkbook-Updater',
        'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})


def latest():
    try:
        with urllib.request.urlopen(request(API_URL), timeout=20) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise UpdateError('Release 資訊超過大小限制。')
        return validate_release(json.loads(data))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise UpdateError('尚無正式發行版本，請稍後重試。') from None
        if error.code in (403, 429):
            raise UpdateError('GitHub 暫時限制查詢，請稍後重試。') from None
        raise UpdateError(f'GitHub 回應錯誤（HTTP {error.code}），請稍後重試。') from None
    except (OSError, ValueError) as error:
        if isinstance(error, UpdateError):
            raise
        raise UpdateError('無法連線到 GitHub，請確認網路、代理伺服器及系統時間。') from None


def download(release, destination, progress=lambda _: None):
    # Reconstruct and validate the expected URL even when called from a saved ticket.
    expected = f'https://github.com/{REPOSITORY}/releases/download/{release["version"]}/{asset_name(release["version"])}'
    if release.get('url') != expected or not re.fullmatch('[a-f0-9]{64}', release.get('sha256', '')):
        raise UpdateError('更新來源或校驗值不正確。')
    size = release.get('size', 0)
    if not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD:
        raise UpdateError('更新大小超過限制。')
    digest = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(request(expected), timeout=30) as response, open(destination, 'wb') as stream:
            parsed = urllib.parse.urlparse(response.url)
            if parsed.scheme != 'https' or parsed.hostname not in {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}:
                raise UpdateError('更新下載導向了不受信任的來源。')
            while chunk := response.read(256 * 1024):
                total += len(chunk)
                if total > size:
                    raise UpdateError('下載大小與 Release 不符。')
                digest.update(chunk)
                stream.write(chunk)
                progress(f'下載更新：{total / size:.0%}')
        if total != size or digest.hexdigest() != release['sha256']:
            raise UpdateError('更新包校驗失敗，舊程式尚未變更。')
    except Exception:
        Path(destination).unlink(missing_ok=True)
        raise


def launch(root, pid, release=None, recover=False):
    """Run a self-contained copy outside the installation, avoiding Windows file locks."""
    root = Path(root).resolve()
    source = root / UPDATER
    if not source.is_file():
        raise UpdateError('缺少獨立更新工具，請完整解壓縮新版安裝包。')
    folder = Path(tempfile.mkdtemp(prefix='LabWorkbook-update-'))
    shutil.copy2(source, folder / UPDATER)
    ticket = dict(root=str(root), parent_pid=pid, release=release, recover=recover)
    (folder / 'ticket.json').write_text(json.dumps(ticket), encoding='utf-8')
    # The visible window belongs to the updater, not a console or PowerShell window.
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
    process = subprocess.Popen([str(folder / UPDATER), str(folder / 'ticket.json')],
                               cwd=folder, creationflags=flags, close_fds=True)
    process.workbook_folder = folder
    if recover:
        (folder / 'go').touch()
    return process
