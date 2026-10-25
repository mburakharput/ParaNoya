import sqlite3, tempfile, unittest
from pathlib import Path
from finance_core import migrate, open_db, add_account, summary
from document_center import migrate_documents, stage, list_docs, approve_salary, parse

class TestDocuments(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'finance.db'
  migrate(self.path);self.db=open_db(self.path);migrate_documents(self.db)
  add_account(self.db,1,'Maaş hesabı','bank',0)
  self.account=self.db.execute('SELECT id FROM accounts WHERE profile_id=1').fetchone()[0]
 def tearDown(self):self.db.close();self.temp.cleanup()
 def test_payslip_stage_and_approval(self):
  p=Path(self.temp.name)/'bordro.txt';p.write_text('Dönem: 10/2026\nNet ödenecek: 58.200,00 TL',encoding='utf8')
  did,fresh,parsed=stage(self.db,1,p,'payslip')
  self.assertTrue(fresh);self.assertEqual(parsed['fields']['net'],5820000)
  self.assertEqual(stage(self.db,1,p,'payslip')[1],False)
  self.assertEqual(summary(self.db,1)[0],0)
  with self.assertRaises(ValueError):approve_salary(self.db,1,did,self.account,5820000,'10/2026',False)
  self.assertEqual(summary(self.db,1)[0],0)
  approve_salary(self.db,1,did,self.account,5820000,'10/2026',True)
  self.assertEqual(summary(self.db,1)[0],5820000)
  with self.assertRaises(ValueError):approve_salary(self.db,1,did,self.account,5820000,'10/2026',True)
  self.assertEqual(summary(self.db,1)[0],5820000)
 def test_statement_no_auto_post(self):
  p=Path(self.temp.name)/'extre.txt';p.write_text('Dönem borcu: 12.000,00\nAsgari ödeme: 2.400,00',encoding='utf8')
  _,_,parsed=stage(self.db,1,p,'statement')
  self.assertEqual(parsed['fields']['statement_total'],1200000)
  self.assertEqual(summary(self.db,1)[0:2],(0,0))
 def test_profile_isolation(self):
  p=Path(self.temp.name)/'bordro.txt';p.write_text('Net maaş: 1000,00',encoding='utf8')
  stage(self.db,1,p,'payslip')
  self.assertEqual(list_docs(self.db,2),[])
 def test_missing_field_conservative(self):
  self.assertIn('Net ödenecek',parse('Brüt: 1000','payslip')['warnings'][0])
if __name__=='__main__':unittest.main()
