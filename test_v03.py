from contextlib import closing
import tempfile,unittest,sqlite3
from pathlib import Path
from finance_core import *

class TestV03(unittest.TestCase):
    def test_upgrade_and_split_transfer(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ailefinans.db'
            migrate(path)
            db=open_db(path)
            add_account(db,2,'Ortak cüzdan','cash',100000)
            add_account(db,2,'Banka','bank',20000)
            a,b=[x[0] for x in accounts_with_balances(db,2)]
            add_member(db,'Kişi A');add_member(db,'Kişi B')
            members=get_members(db)
            tx=add_shared_expense(db,2,a,'Market','',30000,{members[0][0]:15000,members[1][0]:15000})
            self.assertEqual(summary(db,2),(0,30000,90000))
            transfer(db,2,a,b,10000)
            self.assertEqual(summary(db,2),(0,30000,90000))
            self.assertEqual([x[3] for x in accounts_with_balances(db,2)],[60000,30000])
            self.assertEqual(sum(x[1] for x in member_expenses(db)),30000)
            with self.assertRaises(ValueError):
                add_shared_expense(db,2,a,'Market','',5000,{members[0][0]:3000})
            with self.assertRaises(ValueError):
                transfer(db,2,a,a,1000)
            db.close()
            migrate(path)
            with closing(open_db(path)) as db, db:
                self.assertEqual(summary(db,2),(0,30000,90000))

if __name__ == '__main__': unittest.main()
