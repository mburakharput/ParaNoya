from contextlib import closing
import tempfile,unittest
from pathlib import Path
from finance_core import migrate,open_db,add_account,summary,accounts_with_balances,add_member,add_shared_expense,member_expenses
from v04_core import create_card,cards,purchase,pay_card,upcoming,shared_history,edit_shared_split
class TestV04(unittest.TestCase):
 def test_card_payment_not_double_expense(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'db.sqlite';migrate(path);db=open_db(path)
   add_account(db,2,'Banka','bank',500000)
   aid=accounts_with_balances(db,2)[0][0]
   create_card(db,2,'Kart',10,20,1000000)
   cid=cards(db,2)[0][0]
   purchase(db,2,cid,'Ev','Test',120000,6,'2026-10-25')
   self.assertEqual(summary(db,2),(0,120000,500000))
   self.assertEqual([r[2] for r in upcoming(db,2)],[20000]*6)
   pay_card(db,2,cid,aid,20000)
   self.assertEqual(summary(db,2),(0,120000,480000))
   self.assertEqual(cards(db,2)[0][-1],100000)
   with self.assertRaises(ValueError):pay_card(db,2,cid,aid,110000)
   db.close();migrate(path)
   with closing(open_db(path)) as db2, db2:self.assertEqual(cards(db2,2)[0][-1],100000)
 def test_edit_shared(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'db.sqlite';migrate(p);db=open_db(p)
   add_account(db,2,'Nakit','cash',100000)
   aid=accounts_with_balances(db,2)[0][0]
   add_member(db,'A');add_member(db,'B');m=db.execute('SELECT id FROM family_members ORDER BY id').fetchall()
   ids=[r[0] for r in m]
   tid=add_shared_expense(db,2,aid,'Market','',10000,{ids[0]:5000,ids[1]:5000})
   self.assertEqual(len(shared_history(db)),1)
   edit_shared_split(db,tid,{ids[0]:7000,ids[1]:3000})
   self.assertEqual(dict(member_expenses(db)),{'A':7000,'B':3000})
   self.assertEqual(summary(db,2),(0,10000,90000))
   with self.assertRaises(ValueError):edit_shared_split(db,tid,{ids[0]:1000})
   db.close()
if __name__=='__main__':unittest.main()
