"""Check the installed app with disposable data and without network access."""
import json
import os
from pathlib import Path
import sys
import tempfile

def run():
    if not os.environ.get('PARANOYA_SMOKE_CHILD'):
        import subprocess
        with tempfile.TemporaryDirectory(prefix='paranoya-smoke-') as folder:
            env = dict(os.environ, PARANOYA_DATA_DIR=folder, PARANOYA_SMOKE_CHILD='1')
            command = [sys.executable]
            if not getattr(sys, 'frozen', False):
                command.append(str(Path(__file__).with_name('ailefinans.py')))
            result = subprocess.run(command + sys.argv[1:], env=env, timeout=90)
            sys.exit(result.returncode)
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QPixmap
    import ailefinans as ui
    from finance_core import DB_PATH, migrate, open_db
    from kmh_core import migrate_kmh
    from document_center import migrate_documents
    from record_manager import migrate_record_state
    from recurring_core import migrate_recurring
    from bank_logo_manager import logo_dir
    from central_updates import load_config
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError
    try:
        VerifyKey(bytes.fromhex(load_config()['signing_public_key'])).verify(b'smoke',bytes(64))
    except BadSignatureError:
        pass
    else:
        raise AssertionError('Invalid signature accepted')
    migrate()
    with open_db() as db:
        migrate_kmh(db)
        db.execute('CREATE TABLE IF NOT EXISTS card_catalog_links (card_id INTEGER PRIMARY KEY REFERENCES credit_cards(id) ON DELETE CASCADE, bank TEXT NOT NULL, card_model TEXT NOT NULL, payment_network TEXT NOT NULL DEFAULT "")')
        migrate_documents(db)
        migrate_record_state(db)
        migrate_recurring(db)
    app = ui.QApplication([])
    ui.App.download_bank_logos = lambda *args, **kwargs: None
    window = ui.App()
    asset = Path(ui.__file__).parent / 'assets' / 'paranoya_mascot.png'
    assert not QPixmap(str(asset)).isNull(), 'Mascot missing'
    assert (asset.parent / 'chevron-down.svg').is_file()
    logo_dir().mkdir(parents=True, exist_ok=True)
    probe = logo_dir() / 'write-probe.tmp'
    probe.write_text('ok')
    probe.unlink()
    assert DB_PATH.is_file()
    window.show()
    QTimer.singleShot(1000, window.close)
    QTimer.singleShot(1200, app.quit)
    assert app.exec() == 0
    report = Path(sys.argv[sys.argv.index('--smoke-test') + 1])
    report.write_text(json.dumps({'ok': True, 'database': 'temporary', 'assets': True, 'logo_cache_writable': True}), encoding='utf-8')
