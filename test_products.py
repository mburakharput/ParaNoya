import sqlite3,unittest
from finance_core import migrate
from product_core import *
from tempfile import TemporaryDirectory
from pathlib import Path
class ProductTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'f.db';migrate(self.path)
  self.db=sqlite3.connect(self.path);self.db.execute('PRAGMA foreign_keys=ON');migrate_products(self.db)
 def tearDown(self):self.db.close();self.temp.cleanup()
 def test_create_archive_restore(self):
  i=create_product(self.db,1,'TV','2026-10-25',3000000,'2028-10-25')
  self.assertEqual(len(list_products(self.db,1)),1)
  change_product(self.db,1,i,state='archived');self.assertEqual(list_products(self.db,1),[])
  change_product(self.db,1,i,state='active');self.assertEqual(len(list_products(self.db,1)),1)
 def test_profile_isolation(self):
  i=create_product(self.db,1,'TV','2026-10-25');self.assertEqual(list_products(self.db,2),[])
  with self.assertRaises(ValueError):change_product(self.db,2,i,state='archived')
 def test_warranty_validation(self):
  with self.assertRaises(ValueError):create_product(self.db,1,'TV','2026-10-25',0,'2025-01-01')
 def test_service(self):
  i=create_product(self.db,1,'TV','2026-10-25');add_service(self.db,1,i,'2026-10-25','Bakım',12000)
  self.assertEqual(self.db.execute('SELECT cost_cents FROM product_service').fetchone()[0],12000)
 def test_expiring(self):
  create_product(self.db,1,'TV','2026-10-25',0,'2026-11-01')
  self.assertEqual(len(expiring(self.db,1,30,date(2026,10,25))),1)
if __name__=='__main__':unittest.main()
