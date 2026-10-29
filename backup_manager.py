"""Bounded, verified backups and offline recovery. No migration during validation."""
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

MAX_FILE = 256 * 1024**2
MAX_TOTAL = 1024**3
MAX_FILES = 10000


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('Yedekte tekrar eden alan')
        result[key]=value
    return result


def _name(name):
    if not isinstance(name,str) or '\\' in name or ':' in name:
        raise ValueError('Güvenli olmayan yedek yolu')
    p=PurePosixPath(name)
    if p.is_absolute() or any(x in ('','..','.') for x in name.split('/')):
        raise ValueError('Güvenli olmayan yedek yolu')
    if name!='ailefinans.db' and not (len(p.parts)==2 and p.parts[0]=='product_documents'):
        raise ValueError('Beklenmeyen yedek dosyası')
    # Reject Windows aliases, including trailing dots/spaces and device names.
    for part in p.parts:
        if part.rstrip(' .')!=part or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',part):
            raise ValueError('Güvenli olmayan yedek yolu')
    return p


def _database(path, folder, *, require_app=False):
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                raise ValueError('Yedek veritabanının bütünlüğü bozuk')
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Yedekte ilişkisi kopuk kayıtlar var')
            from finance_core import MAX_SCHEMA_VERSION
            if not 0<=db.execute('PRAGMA user_version').fetchone()[0]<=MAX_SCHEMA_VERSION:
                raise ValueError('Yedek daha yeni bir uygulama sürümüne ait')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if require_app and not {'profiles','accounts','transactions'}.issubset(tables):
                raise ValueError('ParaNoya veritabanı bulunamadı')
            if 'product_attachments' in tables:
                for name,digest in db.execute('SELECT stored_name,sha256 FROM product_attachments'):
                    _name('product_documents/'+name)
                    attachment=folder/'product_documents'/name
                    if not attachment.is_file() or hashlib.sha256(attachment.read_bytes()).hexdigest()!=digest:
                        raise ValueError('Yedekte ürün belgesi eksik veya değişmiş')
    except sqlite3.DatabaseError as exc:
        raise ValueError('Yedek geçerli bir SQLite veritabanı içermiyor') from exc


def _unpack(path, folder):
    with ZipFile(path) as z:
        entries=z.infolist();names=[i.filename for i in entries]
        if len(entries)>MAX_FILES or len({n.casefold() for n in names})!=len(names):
            raise ValueError('Yedekte fazla veya tekrar eden dosya')
        if sum(i.file_size for i in entries)>MAX_TOTAL or any(i.file_size>MAX_FILE for i in entries):
            raise ValueError('Yedek boyut sınırını aşıyor')
        if 'manifest.json' not in names or z.getinfo('manifest.json').file_size>2*1024**2:
            raise ValueError('Yedek manifesti eksik veya çok büyük')
        manifest=json.loads(z.read('manifest.json'),object_pairs_hook=_pairs)
        if manifest.get('format')!='paranoya-backup-v1' or not isinstance(manifest.get('files'),dict):
            raise ValueError('Yedek biçimi tanınmadı')
        if set(names)!=set(manifest['files'])|{'manifest.json'} or 'ailefinans.db' not in manifest['files']:
            raise ValueError('Yedek dosya listesi farklı')
        for name,info in manifest['files'].items():
            p=_name(name);entry=z.getinfo(name)
            if (not isinstance(info,dict) or type(info.get('bytes')) is not int or
                    info['bytes']!=entry.file_size or not re.fullmatch('[0-9a-f]{64}',info.get('sha256',''))):
                raise ValueError('Yedek dosya bilgisi geçersiz')
            if entry.flag_bits & 1 or (entry.external_attr>>16)&0o170000==0o120000:
                raise ValueError('Bağlantılı/şifreli yedek dosyası kabul edilmez')
            target=folder.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True)
            digest=hashlib.sha256();count=0
            with z.open(entry) as source,target.open('xb') as output:
                while chunk:=source.read(1024*1024):
                    count+=len(chunk)
                    if count>info['bytes']:raise ValueError('Yedek boyutu tutarsız')
                    digest.update(chunk);output.write(chunk)
            if count!=info['bytes'] or digest.hexdigest()!=info['sha256']:
                raise ValueError('Yedek dosya doğrulaması başarısız: '+name)
    _database(folder/'ailefinans.db',folder)


def verify_backup(path):
    with TemporaryDirectory(prefix='paranoya-check-') as tmp:
        _unpack(path,Path(tmp))
    return True


def make_backup(data_dir, destination):
    data_dir=Path(data_dir).resolve();destination=Path(destination).resolve()
    db=data_dir/'ailefinans.db'
    if not db.is_file():raise FileNotFoundError('Veritabanı bulunamadı')
    if destination.exists():raise FileExistsError('Yedek hedefi zaten var; üzerine yazılmaz')
    if data_dir in destination.parents:raise ValueError('Yedek veri klasörünün dışında tutulmalı')
    destination.parent.mkdir(parents=True,exist_ok=True)
    partial=destination.with_name(destination.name+'.'+uuid4().hex+'.partial')
    try:
        with TemporaryDirectory() as tmp:
            copy=Path(tmp)/'ailefinans.db'
            with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(copy)) as target:
                source.backup(target)
            files=[('ailefinans.db',copy)];attachments=data_dir/'product_documents'
            if attachments.is_symlink():raise ValueError('Belge klasörü bağlantı içeriyor')
            if attachments.exists():
                for file in attachments.rglob('*'):
                    if file.is_symlink():raise ValueError('Belge klasörü bağlantı içeriyor')
                    if file.is_file():files.append((file.relative_to(data_dir).as_posix(),file))
            manifest={'format':'paranoya-backup-v1','created_at':datetime.now().isoformat(),'files':{}}
            total=0
            if len(files)+1>MAX_FILES:raise ValueError('Çok fazla yedek dosyası')
            with ZipFile(partial,'x',compression=ZIP_DEFLATED) as z:
                for name,file in files:
                    _name(name)
                    digest=hashlib.sha256();count=0
                    with file.open('rb') as source,z.open(name,'w') as output:
                        while chunk:=source.read(1024*1024):
                            count+=len(chunk);total+=len(chunk)
                            if count>MAX_FILE or total>MAX_TOTAL:raise ValueError('Yedek boyut sınırını aşıyor')
                            digest.update(chunk);output.write(chunk)
                    manifest['files'][name]={'sha256':digest.hexdigest(),'bytes':count}
                z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
            verify_backup(partial)
            # Windows rename is atomic and refuses an existing destination.
            if os.name=='nt':os.rename(partial,destination)
            else:os.link(partial,destination)
        return destination
    finally:partial.unlink(missing_ok=True)


def restore_backup(path, data_dir, *, confirmed=False):
    """Caller must hold the application lock and close every DB connection.

    Stage and validate first. Preserve the entire old directory as the recovery
    copy; if replacement fails, put it back. Never delete the recovery copy.
    """
    if confirmed is not True:raise ValueError('Geri yükleme onayı gerekli')
    original=Path(data_dir).absolute()
    if any(p.is_symlink() for p in (original,*original.parents)):
        raise ValueError('Veri klasörü bağlantı içeriyor')
    data_dir=original.resolve();data_dir.parent.mkdir(parents=True,exist_ok=True)
    recovery=data_dir.with_name(data_dir.name+'.before-restore-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
    journal=data_dir.with_name(data_dir.name+'.restore-pending.json')
    if journal.exists():raise ValueError('Önce yarım kalan geri yükleme kurtarılmalı')
    with TemporaryDirectory(prefix='paranoya-restore-',dir=data_dir.parent) as tmp:
        stage=Path(tmp)/'data';stage.mkdir()
        _unpack(path,stage)
        _database(stage/'ailefinans.db',stage,require_app=True)
        existed=data_dir.exists()
        if existed:
            with journal.open('x',encoding='utf-8') as output:
                json.dump({'recovery':recovery.name},output);output.flush();os.fsync(output.fileno())
        try:
            if existed:os.rename(data_dir,recovery)
            try:os.rename(stage,data_dir)
            except BaseException:
                if existed:os.rename(recovery,data_dir)
                raise
        finally:
            if data_dir.exists():journal.unlink(missing_ok=True)
    return recovery if existed else None


def recover_interrupted_restore(data_dir):
    """Called under the app lock BEFORE creating/opening any finance database."""
    data_dir=Path(data_dir).absolute()
    journal=data_dir.with_name(data_dir.name+'.restore-pending.json')
    if not journal.exists():return
    if journal.is_symlink() or journal.stat().st_size>4096:raise ValueError('Kurtarma kaydı geçersiz')
    record=json.loads(journal.read_text(encoding='utf-8'),object_pairs_hook=_pairs)
    name=record.get('recovery')
    if not isinstance(name,str) or Path(name).name!=name or not name.startswith(data_dir.name+'.before-restore-'):
        raise ValueError('Kurtarma yolu geçersiz')
    recovery=data_dir.parent/name
    if recovery.is_symlink():raise ValueError('Kurtarma klasörü bağlantı içeriyor')
    if not data_dir.exists():
        _database(recovery/'ailefinans.db',recovery,require_app=True)
        os.rename(recovery,data_dir)
    journal.unlink()
