import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from . import updates as u, update_install as ins, config_store as cs


def release(version='20261013-v45'):
    return {'tag_name': version, 'draft': False, 'prerelease': False, 'assets': [dict(
        name=u.asset_name(version), size=123, digest='sha256:'+'a'*64, state='uploaded',
        browser_download_url=f'https://github.com/{u.REPOSITORY}/releases/download/{version}/{u.asset_name(version)}')]}


def package(folder, version='20261013-v45', extra=None):
    files={u.EXE:b'new app',u.UPDATER:b'new updater','_internal/python312.dll':b'runtime','開始使用.txt':b'readme'}
    files.update(extra or {})
    manifest={'format':1,'version':version,'files':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()}}
    files[u.MANIFEST]=json.dumps(manifest).encode()
    archive=Path(folder)/'release.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for name,value in files.items():z.writestr('工作簿輸出/'+name,value)
    return archive


class Updates(unittest.TestCase):
    def test_version_numeric(self):
        self.assertGreater(u.version_key('20261013-v44'),u.version_key('20261013-v9'))
        for value in ('latest','v44','20261013-v0','../v44'):
            with self.assertRaises(u.UpdateError):u.version_key(value)

    def test_trusted_release(self):
        self.assertEqual(u.validate_release(release())['version'],'20261013-v45')
        for field,value in [('draft',True),('prerelease',True),('assets',[])]:
            r=release();r[field]=value
            with self.assertRaises(u.UpdateError):u.validate_release(r)
        for field,value in [('browser_download_url','https://evil.example/a.zip'),('digest',''),('size',u.MAX_DOWNLOAD+1),('state','new')]:
            r=release();r['assets'][0][field]=value
            with self.assertRaises(u.UpdateError):u.validate_release(r)

    def test_zip_rejects_sensitive_and_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('preferences.json','print_settings/settings.json','defaults/system_seed.json','db.mdb','_internal/../preferences.json',
                         '_internal/C:evil','_internal/settings.json','_internal/NUL.txt','_internal/x.','workbook/catalog.json'):
                with self.subTest(name=name),self.assertRaises(u.UpdateError):
                    ins.unpack(package(d,extra={name:b'private'}),Path(d)/'stage','20261013-v45')

    def test_zip_corrupt_missing_wrong_version_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            z=package(d)
            with self.assertRaises(u.UpdateError):ins.unpack(z,Path(d)/'stage','20261013-v46')
            with zipfile.ZipFile(z,'a') as archive:archive.writestr('工作簿輸出/WORKBOOKUPDATER.EXE',b'collision')
            with self.assertRaises(u.UpdateError):ins.unpack(z,Path(d)/'stage','20261013-v45')
            z=package(d)
            with zipfile.ZipFile(z) as source:files={n:source.read(n) for n in source.namelist()}
            files['工作簿輸出/'+u.EXE]=b'tampered'
            with zipfile.ZipFile(z,'w') as target:
                for name,value in files.items():target.writestr(name,value)
            with self.assertRaises(u.UpdateError):ins.unpack(z,Path(d)/'stage','20261013-v45')

    def test_install_preserves_settings_and_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'onsite';root.mkdir();stage=Path(d)/'stage'
            names=ins.unpack(package(d),stage,'20261013-v45')
            (root/u.EXE).write_bytes(b'old app')
            protected={'preferences.json':b'{"path":"local.mdb"}','print_settings/settings.json':b'{"mine":true}',
                       'data.mdb':b'private database','output/report.pdf':b'private report'}
            for name,value in protected.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
            ins.install(stage,root,names,'20261013-v45')
            self.assertEqual((root/u.EXE).read_bytes(),b'new app')
            for name,value in protected.items():self.assertEqual((root/name).read_bytes(),value)
            ins.rollback(root)
            self.assertEqual((root/u.EXE).read_bytes(),b'old app')
            self.assertFalse((root/u.UPDATER).exists())
            for name,value in protected.items():self.assertEqual((root/name).read_bytes(),value)

    def test_install_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'onsite';root.mkdir();stage=Path(d)/'stage'
            names=ins.unpack(package(d),stage,'20261013-v45')
            (root/u.EXE).write_bytes(b'old app')
            original=ins.replace_file;calls=[]
            def fail_once(src,dst):
                calls.append(dst)
                if len(calls)==3:raise PermissionError('locked')
                return original(src,dst)
            with patch.object(ins,'replace_file',side_effect=fail_once),self.assertRaises(PermissionError):
                ins.install(stage,root,names,'20261013-v45')
            self.assertEqual((root/u.EXE).read_bytes(),b'old app')
            self.assertFalse((root/ins.JOURNAL).exists())

    def test_insufficient_space_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'onsite';root.mkdir();stage=Path(d)/'stage'
            names=ins.unpack(package(d),stage,'20261013-v45');(root/u.EXE).write_bytes(b'old')
            from collections import namedtuple
            with patch.object(ins.shutil,'disk_usage',return_value=namedtuple('Usage','free')(0)),self.assertRaises(u.UpdateError):
                ins.install(stage,root,names,'20261013-v45')
            self.assertEqual((root/u.EXE).read_bytes(),b'old')
            self.assertFalse((root/ins.JOURNAL).exists())

    def test_factory_bootstrap_and_existing_settings(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            cs.ensure_configuration(root)
            self.assertEqual(cs.read(root/'preferences.json')['database_path'],'')
            before=cs.read_bundle(root)
            before['settings']['ditto_font_size']=21
            cs.transaction(cs.targets(root,before))
            after=cs.ensure_configuration(root)
            self.assertEqual(after['settings']['ditto_font_size'],21)
            self.assertIsNone(after['catalog'])

    def test_download_checksum_and_length(self):
        import io
        r=u.validate_release(release());r['size']=3;r['sha256']=hashlib.sha256(b'abc').hexdigest()
        class Response(io.BytesIO):url='https://release-assets.githubusercontent.com/asset'
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/'archive.zip'
            with patch.object(u.urllib.request,'urlopen',return_value=Response(b'abc')):u.download(r,dest)
            self.assertEqual(dest.read_bytes(),b'abc')
            for content in (b'ab',b'abcd',b'xyz'):
                with patch.object(u.urllib.request,'urlopen',return_value=Response(content)),self.assertRaises(u.UpdateError):u.download(r,dest)
                self.assertFalse(dest.exists())

    def test_partial_configuration_is_not_reset(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'print_settings').mkdir()
            path=root/'print_settings/layout_settings.json';path.write_text('{"mine":true}',encoding='utf-8')
            with self.assertRaises(ValueError):cs.ensure_configuration(root)
            self.assertEqual(path.read_text(),'{"mine":true}')
            self.assertFalse((root/'print_settings/settings.json').exists())

    def test_symlink_zip_and_corrupt_backup_rejected(self):
        import stat
        with tempfile.TemporaryDirectory() as d:
            archive=package(d)
            with zipfile.ZipFile(archive,'a') as z:
                entry=zipfile.ZipInfo('工作簿輸出/_internal/linked.dll');entry.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(entry,'../../secret')
            with self.assertRaises(u.UpdateError):ins.unpack(archive,Path(d)/'stage','20261013-v45')
            root=Path(d)/'onsite';root.mkdir();stage=Path(d)/'stage2'
            names=ins.unpack(package(d),stage,'20261013-v45');(root/u.EXE).write_bytes(b'old')
            backup=ins.install(stage,root,names,'20261013-v45')
            (backup/u.EXE).write_bytes(b'corrupt')
            with self.assertRaises(u.UpdateError):ins.rollback(root)
            self.assertTrue((root/ins.JOURNAL).exists())
            self.assertEqual((root/u.EXE).read_bytes(),b'new app')


if __name__=='__main__':unittest.main()
