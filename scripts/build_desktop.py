"""Build an allowlisted portable distribution. Never bundle database or patient records."""
from pathlib import Path
import os,sys,json,subprocess,shutil,hashlib,zipfile,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workbook.core import get_settings,save_json
from workbook import layout_settings
from workbook.version import APP_VERSION

def synthetic_demo():
    labels={'0921':'AC','101':'OT','102':'PT','204':'cre','206':'UA','202':'BUN',
        '301':'TG','302':'CHO','3061':'HDL','307':'LDL','111':'TP','112':'Alb',
        '096':'HbA1c','205':'mab','136':'sAg','138':'eAg','151':'HCV','7021':'AFP',
        '4021':'T3','4031':'FT4','4061':'TSH','7041':'CEA',
        'B02':'WBC','B04':'RBC','B10':'Hb','B24':'Hct','B38':'MCV','B39':'MCH','B40':'MCHC','B43':'PLT',
        'DE01':'Alk-P','DE02':'GGT','DE03':'T-Bil','DE04':'D-Bil','DE05':'eGFR',
        'DE06':'LDH','DE07':'Amy','DE08':'Fe','DE09':'Pi','DE10':'L/H'}
    data={'date':'2026-09-20','headers':[],'details':[],
        'items':[dict(LCI_ID=c,LCI_NAME=l,LCI_NAMES=l,LCI_NAMEC='') for c,l in labels.items()],
        'hospitals':[dict(HOS_ID='DEMO',HOS_NAME='示範診所')],
        'sets':[],'set_members':[],'adult_health':[],'identity_local_only':False,
        'source_file':'人工建立的示範資料，非真實檢驗紀錄'}
    base=['0921','101','102','204','301','302','3061','307']
    for i in range(1,25):
        no=f'{i:05}';data['headers'].append(dict(LCHK_DEPT='DEMO',LCHK_WORKNO=no,LCHK_SOURCE='DEMO',ORDER_NOTE=''))
        codes=base.copy()
        if i%2==0:codes+=['096']
        if i%3==0:codes+=['205']
        if i%4==0:codes+=['136','151','7021']
        if i==12:codes+=['111','112','202','206']+['B02','B04','B10','B24','B38','B39','B40','B43']
        for n,c in enumerate(codes):data['details'].append(dict(LCHK_DEPT='DEMO',LCHK_WORKNO=no,LCHK_ITEM=c,LCHK_ITEMTYPE='I',LCHK_ITEMSER=n))
    blood=['B02','B04','B10','B24','B38','B39','B40','B43']
    data['sets']=[dict(LCS_ID='0051',LCS_NAME='人工CBC套組',LCS_UNIKEY='DEMO_CBC',LCS_HOSPITAL='DEMO')]
    data['set_members']=[dict(LCS_UNIKEY='DEMO_CBC',LCS_ITEM=c,LCS_SERIAL=i) for i,c in enumerate(blood)]
    data['details'].append(dict(LCHK_DEPT='DEMO',LCHK_WORKNO='00012',LCHK_ITEM='0051',LCHK_ITEMTYPE='G',LCHK_ITEMSER=100))
    for detail in data['details']:
        detail['LCHK_MKEY']='0051' if detail['LCHK_WORKNO']=='00012' and detail['LCHK_ITEM'] in blood else ''
    return data

def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--settings-from',type=Path,help='Local-only build carrying settings from an explicit previous application folder. Never publish this build.')
    mode.add_argument('--public',action='store_true',help='Publishable build: no database, saved settings or source dictionary; factory defaults come from code.')
    parser.add_argument('--catalog-from',type=Path,help='Include an allowlisted non-patient JSON dictionary.')
    parser.add_argument('--installers-from',type=Path,default=ROOT/'tmp/runtime-installers',help='Verified Microsoft Access Runtime online installers.')
    args=parser.parse_args()
    settings_source=args.settings_from.resolve() if args.settings_from else None
    from workbook.core import load_json
    from workbook import config_store
    if args.public and args.catalog_from:parser.error('--public cannot include a local catalog')
    bundle=config_store.read_bundle(settings_source) if settings_source else None
    saved_settings,saved_layout=(bundle['settings'],bundle['layout']) if bundle else (None,None)
    saved_catalog=bundle['catalog'] if bundle else None
    if args.catalog_from and bundle:
        saved_settings,saved_layout,saved_catalog=config_store.normalize(saved_settings,saved_layout,load_json(args.catalog_from))
    build=ROOT/'tmp/desktop-build';dist=ROOT/'output'/f'app-{APP_VERSION}';build.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tmp/build-tools')+os.pathsep+str(ROOT)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed',
        '--name','工作簿輸出','--distpath',str(dist),'--workpath',str(build/'work'),
        '--specpath',str(build),'--paths',str(ROOT),'--hidden-import','reportlab.pdfbase.ttfonts',
        '--exclude-module','numpy','--exclude-module','pandas','--exclude-module','matplotlib',
        '--exclude-module','scipy',str(ROOT/'scripts/desktop_entry.py')]
    subprocess.run(command,env=env,check=True)
    package=dist/'工作簿輸出';(package/'output').mkdir(exist_ok=True)
    updater_command=[sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed',
        '--name','WorkbookUpdater','--distpath',str(build/'updater-dist'),'--workpath',str(build/'updater-work'),
        '--specpath',str(build),'--paths',str(ROOT),str(ROOT/'scripts/update_entry.py')]
    subprocess.run(updater_command,env=env,check=True)
    shutil.copy2(build/'updater-dist/WorkbookUpdater.exe',package/'WorkbookUpdater.exe')
    # Only initialization seeds ship. Extracting an update never overwrites live settings.
    if bundle:
        save_json(package/'defaults/print_settings/settings.json',saved_settings)
        save_json(package/'defaults/print_settings/layout_settings.json',saved_layout)
        if saved_catalog:save_json(package/'defaults/print_settings/catalog.json',saved_catalog)
        if bundle['system_present']:save_json(package/'defaults/system_seed.json',bundle['system'])
        save_json(package/'defaults/設定來源.json',dict(source_version=settings_source.parent.name,
            print_settings_carried=True,system_settings_carried=bundle['system_present'],
            policy='本機設定包不可上傳GitHub；現場設定優先。'))
    (package/'workbook').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'workbook/access_bridge.ps1',package/'workbook/access_bridge.ps1')
    shutil.copy2(ROOT/'workbook/check_connection.ps1',package/'workbook/check_connection.ps1')
    shutil.copy2(ROOT/'workbook/catalog_bridge.ps1',package/'workbook/catalog_bridge.ps1')
    for name in ('diagnose_connection.ps1','install_access_runtime.ps1'):
        shutil.copy2(ROOT/'workbook'/name,package/'workbook'/name)
    from workbook import access_runtime
    dependencies=package/'dependencies';dependencies.mkdir(exist_ok=True)
    for arch,(name,digest) in access_runtime.INSTALLERS.items():
        source=args.installers_from/name
        assert source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest()==digest,'Missing or unexpected installer'
        probe=access_runtime.run_process(access_runtime.command(access_runtime.windows_shells()[0][0],
            'install_access_runtime.ps1','-Installer',source.resolve(),'-ExpectedHash',digest,'-VerifyOnly'))
        assert probe.returncode==0 and json.loads(probe.stdout.decode('utf-8-sig')).get('code')=='VERIFIED','Untrusted Microsoft signature'
        shutil.copy2(source,dependencies/name)
    shutil.copy2(args.installers_from/'sources.json',dependencies/'sources.json')
    (dependencies/'安裝步驟.txt').write_text('''Microsoft 365 Access Runtime（繁體中文，官方線上安裝程式）

建議從主程式「系統設定」按「測試連線」，由程式先檢查本機32／64位元驅動。
若只是位元不符，程式會自動換成可用環境，不需安裝。
若顯示NO_PROVIDER，在「連線工具」按「安裝 Access 元件」，程式會選擇符合現場Office位元的安裝檔。
請連上網路，在Windows管理員權限提示按「是」，依Microsoft畫面完成安裝。
這兩個EXE是官方線上安裝程式，不是完整離線Office安裝媒體。
安裝完會重新測試連線；若安裝仍在進行，請完成後再按測試連線。
如果要求重開機，請先保存其他工作，重開後重新啟動工作簿。

手動安裝：Office 32位元使用AccessRuntime_x86.exe；Office 64位元使用AccessRuntime_x64.exe。
沒有Office時，這個Windows64部署包使用x64。
若顯示與既有MSI版Office不相容，請由現場管理員處理，勿直接移除現有Office。
程式不卸載Office、不改資料庫、不變更系統權限、不強制關閉其他程式。

官方來源：https://support.microsoft.com/en-us/access/download-and-install-microsoft-365-access-runtime
原始下載網址、SHA256及檔案大小見sources.json；程式啟動安裝前另驗證Microsoft數位簽章。
''',encoding='utf-8-sig')
    save_json(package/'assets/demo.json',synthetic_demo())
    guide=(ROOT/'README.md').read_text(encoding='utf-8')
    if not args.public:guide='LOCAL ONLY: 此包含本機設定，不可上傳或公開。\n\n'+guide
    (package/'開始使用.txt').write_text(f'版本 {APP_VERSION}\n\n'+guide,encoding='utf-8-sig')
    (package/'修復未完成更新.cmd').write_text('@echo off\r\n"%~dp0WorkbookUpdater.exe" --recover "%~dp0."\r\n',encoding='ascii')
    files=list(package.rglob('*'))
    assert not any(p.suffix.lower() in {'.mdb','.accdb','.jpg','.png'} for p in files if p.is_file())
    assert not (package/'preferences.json').exists() and not (package/'print_settings').exists(),'Update ZIP must not overwrite user files'
    assert not any((package/'workbook'/name).exists() for name in config_store.PRINT_FILES),'Legacy settings must not be overwritten'
    manifest={str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    save_json(package/'檔案校驗.json',manifest)
    if args.public:
        from workbook.updates import MANIFEST,asset_name
        from workbook.update_install import safe_name
        public_files={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in package.rglob('*') if p.is_file()}
        assert all(safe_name(n) for n in public_files),'Public package contains a protected or unexpected file'
        save_json(package/MANIFEST,dict(format=1,version=APP_VERSION,files=public_files))
        archive=dist/asset_name(APP_VERSION)
    else:
        archive=dist/f'工作簿輸出_Windows64_{APP_VERSION}_LOCAL_ONLY.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in package.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(dist))
    print(json.dumps({'package':str(package),'zip':str(archive),'zip_mb':round(archive.stat().st_size/1048576,1)},ensure_ascii=False))

if __name__=='__main__':main()
