from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from finance_core import migrate, open_db, add_account, add_transaction, accounts_with_balances, summary

class FinanceTests(unittest.TestCase):
    def test_v01_migration_and_balances(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'ailefinans.db'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE profiles (id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,kind TEXT NOT NULL CHECK(kind IN ('personal','family')))")
                db.execute("INSERT INTO profiles VALUES (1,'Kişisel','personal')")
            migrate(path)
            self.assertEqual(len(list(Path(folder).glob('*.v01_backup_*.db'))), 1)
            db = open_db(path)
            add_account(db, 1, 'Cüzdan', 'cash', 10000)
            account_id = db.execute('SELECT id FROM accounts').fetchone()[0]
            add_transaction(db, 1, account_id, 'income', 'Maaş', '', 30000)
            add_transaction(db, 1, account_id, 'expense', 'Market', '', 7500)
            self.assertEqual(summary(db, 1), (30000, 7500, 32500))
            self.assertEqual(accounts_with_balances(db, 1)[0][3], 32500)
            with self.assertRaises(ValueError):
                add_transaction(db, 2, account_id, 'income', 'Maaş', '', 50)
            db.close()
            migrate(path)
            db = open_db(path)
            self.assertEqual(summary(db, 1), (30000, 7500, 32500))
            db.close()

if __name__ == '__main__':
    unittest.main()
