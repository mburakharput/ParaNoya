"""Regression tests for rejecting backups with unrelated SQLite contents."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from backup_manager import verify_backup, restore_backup


class BackupIdentityTests(unittest.TestCase):
    def test_valid_sqlite_from_another_application_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            foreign_db = root / "foreign.db"
            with sqlite3.connect(foreign_db) as db:
                db.execute("CREATE TABLE unrelated_application (id INTEGER PRIMARY KEY)")
            payload = foreign_db.read_bytes()
            archive = root / "foreign.zip"
            manifest = {
                "format": "paranoya-backup-v1",
                "files": {
                    "ailefinans.db": {
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload),
                    }
                },
            }
            with ZipFile(archive, "w", ZIP_DEFLATED) as output:
                output.writestr("ailefinans.db", payload)
                output.writestr("manifest.json", json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "ParaNoya veritabanı"):
                verify_backup(archive)
            destination = root / "existing-data"
            destination.mkdir()
            sentinel = destination / "keep.txt"
            sentinel.write_text("preserved", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ParaNoya veritabanı"):
                restore_backup(archive, destination, confirmed=True)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserved")
            self.assertFalse((destination / "ailefinans.db").exists())


if __name__ == "__main__":
    unittest.main()
