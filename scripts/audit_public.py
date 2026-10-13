"""Fail closed: audit the staged Git snapshot and optional public release ZIP."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workbook.update_install import safe_name

SAFE_SCRIPTS={'build_desktop.py','desktop_entry.py','update_entry.py','fetch_runtime_installers.py','audit_public.py','test_update_ui.py','verify_update_release.py'}
SAFE_TESTS={'test_updates.py','test_config_store.py','test_preferences.py','test_catalog_cache.py','test_print_preferences_v45.py','test_three_rows_panels.py'}


def permitted(name):
    p=Path(name)
    if name in {'.gitignore','README.md'}:return True
    if len(p.parts)==2 and p.parts[0]=='scripts':return p.name in SAFE_SCRIPTS
    if len(p.parts)==2 and p.parts[0]=='workbook':
        if p.name.startswith('test_'):return p.name in SAFE_TESTS
        return p.suffix in {'.py','.ps1'} and p.name!='check_and_sample.py' or p.name=='requirements.txt'
    return False


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--zip',type=Path);args=parser.parse_args()
    names=subprocess.check_output(['git','diff','--cached','--name-only','--diff-filter=ACMR','-z'],cwd=ROOT).decode('utf-8').split('\0')
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0')
    issues=[]
    for name in sorted(set(names+tracked)-{''}):
        if not permitted(name):issues.append((name,'not in public source allowlist'));continue
        blob=subprocess.check_output(['git','show',':'+name],cwd=ROOT).decode('utf-8-sig')
        # Report location only, never the matched secret or identity value.
        checks={
            'credential':r'(?i)(?:gh[pousr]_[a-z0-9]{30,}|github_pat_[a-z0-9_]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',
            'local user path':r'(?i)C:[/\\]+Users[/\\]+(?:583|[^/\\\s\x27\x22]+)[/\\]',
            'identity number':r'(?<![A-Za-z0-9])[A-Z][12][0-9]{8}(?![A-Za-z0-9])',
        }
        for category,pattern in checks.items():
            if re.search(pattern,blob):issues.append((name,category))
    if args.zip:
        with zipfile.ZipFile(args.zip) as z:
            for name in z.namelist():
                if name.endswith('/'):continue
                if not name.startswith('工作簿輸出/') or not safe_name(name[len('工作簿輸出/'):]):issues.append((name,'protected release file'))
    if issues:
        for name,reason in issues:print(name,reason)
        raise SystemExit('PUBLICATION BLOCKED')
    print('PUBLIC AUDIT PASSED:',len(set(tracked)-{''}),'source files; no data/settings files or credential patterns.')


if __name__=='__main__':main()
