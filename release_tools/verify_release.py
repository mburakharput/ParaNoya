"""Verify publisher signature and installer bytes locally; never read a private key."""
import argparse
import hashlib
import json
from pathlib import Path
from central_updates import load_config
from signed_release import verify_manifest


def verify_installer(installer):
    path=Path(installer);config=load_config();version=config['version']
    if path.name!=f'ParaNoya-{version}-Windows-x64-Setup.exe':raise ValueError('Kurulum sürümü eşleşmiyor')
    prefix=path.with_name(f'ParaNoya-{version}-manifest.json')
    raw=prefix.read_bytes();signature=prefix.with_suffix(prefix.suffix+'.sig').read_text(encoding='ascii')
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    verify_manifest(config['signing_public_key'],raw,signature,version=version,name=path.name,size=path.stat().st_size,sha256=digest.hexdigest())
    return True


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--installer',required=True)
    verify_installer(parser.parse_args().installer)
    print('Yayıncı imzası ve kurulum dosyası doğrulandı.')
