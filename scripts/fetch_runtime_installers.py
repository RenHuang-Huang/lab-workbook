"""Download Microsoft bootstrap installers into ignored tmp/, never execute them."""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workbook.access_runtime import INSTALLERS


def main():
    folder=ROOT/'tmp/runtime-installers';folder.mkdir(parents=True,exist_ok=True)
    sources=[]
    for arch,(name,digest) in INSTALLERS.items():
        url=f'https://c2rsetup.officeapps.live.com/c2r/download.aspx?ProductreleaseID=AccessRuntimeRetail&language=zh-tw&platform={arch}'
        dest=folder/name
        if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest()!=digest:
            with urllib.request.urlopen(url,timeout=60) as response:data=response.read(20*1024*1024+1)
            if hashlib.sha256(data).hexdigest()!=digest:
                raise SystemExit('Microsoft installer changed: independently verify source, signature and pinned hash before updating.')
            dest.write_bytes(data)
        sources.append(dict(arch=arch,file=name,bytes=dest.stat().st_size,sha256=digest,url=url))
    (folder/'sources.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
    print('Verified both Microsoft bootstrap installer hashes. Build also verifies Authenticode signatures.')


if __name__=='__main__':main()
