"""Real packaged executable validation in an isolated installation with synthetic settings."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workbook import updates as u,update_install as ins,config_store as cs
from workbook.version import APP_VERSION


def main():
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='Workbook-update-validation-') as d:
        temp=Path(d);stage=temp/'stage';onsite=temp/'現場 with spaces';onsite.mkdir()
        names=ins.unpack(args.archive,stage,APP_VERSION)
        ins.smoke(stage,temp/'stage.json',APP_VERSION)
        # Existing source installation; all private files below are synthetic markers.
        shutil.copytree(stage,onsite,dirs_exist_ok=True)
        cs.ensure_configuration(onsite)
        bundle=cs.read_bundle(onsite);bundle['settings']['ditto_font_size']=22
        bundle['system']['database_path']='synthetic-local-only.mdb'
        cs.transaction(cs.targets(onsite,bundle))
        (onsite/'synthetic.mdb').write_bytes(b'FAKE DATABASE - NEVER OPEN')
        (onsite/'output').mkdir();(onsite/'output/synthetic.pdf').write_bytes(b'FAKE PDF - NEVER OPEN')
        protected=[onsite/'preferences.json',*list((onsite/'print_settings').glob('*.json')),onsite/'synthetic.mdb',onsite/'output/synthetic.pdf']
        before={p.relative_to(onsite).as_posix():ins.file_hash(p) for p in protected}
        backup=ins.install(stage,onsite,names,APP_VERSION)
        ins.smoke(onsite,temp/'installed.json',APP_VERSION)
        assert before=={n:ins.file_hash(onsite/n) for n in before}
        ins.rollback(onsite)
        assert before=={n:ins.file_hash(onsite/n) for n in before}
        assert not (onsite/ins.JOURNAL).exists()
        result=dict(ok=True,version=APP_VERSION,sha256=ins.file_hash(args.archive),files=len(names),
                    real_executable_smoke=True,real_install=True,rollback=True,protected_files=len(before),settings_preserved=True)
        args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))


if __name__=='__main__':main()
