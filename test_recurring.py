import unittest, sqlite3
from finance_core import migrate,add_account,summary
from recurring_core import *
from tempfile import TemporaryDirectory
from pathlib import Path
class TestRecurring(unittest.TestCase):
 def setUp(self):
  self.t=TemporaryDirectory();self.dbpath=Path(self.t.name)/'test.db';migrate(self.dbpath)
  self.db=sqlite3.connect(self.dbpath);self.db.execute('PRAGMA foreign_keys=ON');migrate_recurring(self.db)
  add_account(self.db,1,'Bankam','bank',100000)
  self.acc=self.db.execute('SELECT id FROM accounts').fetchone()[0]
 def tearDown(self):self.db.close();self.t.cleanup()
 def test_calendar_edge(self):
  self.assertEqual(next_occurrence('2026-01-31','monthly',1),'2026-02-28')
  self.assertEqual(next_occurrence('2026-11-15','yearly',1),'2027-11-15')
 def test_pay_once_no_pending_double(self):
  item=add_item(self.db,1,'Internet','bill','Faturalar',50000,'monthly','2026-11-15')
  self.assertEqual(len(upcoming_items(self.db,1,date(2026,11,1),1)),1)
  pay_occurrence(self.db,1,item,'2026-11-15',self.acc)
  self.assertEqual(summary(self.db,1)[1],50000)
  with self.assertRaises(ValueError):pay_occurrence(self.db,1,item,'2026-11-15',self.acc)
  self.assertEqual(summary(self.db,1)[1],50000)
 def test_profile_guard(self):
  item=add_item(self.db,1,'Hizmet','subscription','Abonelik',1200,'monthly','2026-11-01')
  with self.assertRaises(ValueError):pay_occurrence(self.db,2,item,'2026-11-01',self.acc)
 def test_archive(self):
  item=add_item(self.db,1,'Hizmet','subscription','Abonelik',1200,'monthly','2026-11-01')
  set_active(self.db,1,item,False)
  self.assertEqual(upcoming_items(self.db,1,date(2026,11,1),1),[])
if __name__=='__main__':unittest.main()
