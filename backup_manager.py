from contextlib import closing
"""Consistent offline backup including attachments; never alters originals."""
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from tempfile import TemporaryDirectory


def make_backup(data_dir, destination):
    data_dir=Path(data_dir).resolve();destination=Path(destination).resolve()
    db=data_dir/'ailefinans.db'
    if not db.is_file(): raise FileNotFoundError('Veritabanı bulunamadı')
    if destination.exists(): raise FileExistsError('Yedek hedefi zaten var; üzerine yazılmaz')
    if data_dir in destination.parents: raise ValueError('Yedek veri klasörünün dışında tutulmalı')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory() as tmp:
        copy=Path(tmp)/'ailefinans.db'
        with closing(sqlite3.connect(f'file:{db}?mode=ro',uri=True)) as source, closing(sqlite3.connect(copy)) as target, target:
            source.backup(target)
            result=target.execute('PRAGMA integrity_check').fetchone()[0]
            if result!='ok':raise RuntimeError(f'Veritabanı bütünlük sorunu: {result}')
        files=[('ailefinans.db',copy)]
        attachments=data_dir/'product_documents'
        if attachments.exists():
            for file in attachments.rglob('*'):
                if file.is_symlink():raise ValueError('Belge klasöründe sembolik bağlantı var')
                if file.is_file():files.append((str(file.relative_to(data_dir)).replace('\\','/'),file))
        manifest={'format':'paranoya-backup-v1','created_at':datetime.now().isoformat(),'files':{}}
        with ZipFile(destination,'x',compression=ZIP_DEFLATED) as z:
            for name,file in files:
                blob=file.read_bytes()
                manifest['files'][name]={'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob)}
                z.writestr(name,blob)
            z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return destination


def verify_backup(path):
    with ZipFile(path) as z:
        manifest=json.loads(z.read('manifest.json'))
        if manifest['format']!='paranoya-backup-v1':raise ValueError('Yedek biçimi tanınmadı')
        if set(z.namelist())!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Dosya listesi farklı')
        for name,info in manifest['files'].items():
            if name.startswith('/') or '..' in Path(name).parts:raise ValueError('Güvenli olmayan yol')
            data=z.read(name)
            if len(data)!=info['bytes'] or hashlib.sha256(data).hexdigest()!=info['sha256']:
                raise ValueError('Dosya doğrulaması başarısız: '+name)
    return True
