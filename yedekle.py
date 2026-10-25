"""Kullanıcı verilerini değiştirmeden doğrulanabilir yedek oluşturur."""
from datetime import datetime
from pathlib import Path
from finance_core import DB_DIR
from backup_manager import make_backup, verify_backup

if __name__ == '__main__':
    folder=Path.home()/'Documents'/'ParaNoya_Yedekleri'
    folder.mkdir(parents=True,exist_ok=True)
    output=folder/f'ParaNoya_{datetime.now():%Y%m%d_%H%M%S}.zip'
    try:
        make_backup(DB_DIR,output)
        assert verify_backup(output)
    except Exception as error:
        print('Yedek alınamadı:',error)
        raise SystemExit(1)
    print('Yedek doğrulandı:',output)
