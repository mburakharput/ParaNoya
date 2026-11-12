"""Ensure migration rejects unrelated databases without modifying their contents."""
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from finance_core import migrate, open_db


class MigrationIdentityTests(unittest.TestCase):
    def test_unrelated_database_is_not_converted(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "ailefinans.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("CREATE TABLE other_app (secret TEXT)")
                conn.execute("INSERT INTO other_app VALUES ('unchanged')")
            with self.assertRaisesRegex(ValueError, "ParaNoya veritabanı değil"):
                migrate(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(conn.execute("SELECT secret FROM other_app").fetchone(), ("unchanged",))
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 0)
                self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='accounts'").fetchone())
            self.assertEqual(list(Path(temp).glob("*backup*.db")), [])

    def test_fake_profiles_table_is_not_converted(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "ailefinans.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("CREATE TABLE profiles (random_column TEXT)")
                conn.execute("INSERT INTO profiles VALUES ('kept')")
            with self.assertRaisesRegex(ValueError, "profil tablosu tanınmadı"):
                migrate(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(conn.execute("SELECT random_column FROM profiles").fetchone(), ("kept",))
                self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='accounts'").fetchone())

    def test_new_database_still_initializes(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "ailefinans.db"
            migrate(db_path)
            with closing(open_db(db_path)) as conn:
                self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='accounts'").fetchone())


if __name__ == "__main__":
    unittest.main()
