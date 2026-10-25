from contextlib import closing
import json,sqlite3,tempfile,unittest
from pathlib import Path
from backup_manager import make_backup,verify_backup
from reconciliation import statement_reconciliation, validate_schedule_preview

class ReviewAndBackupTests(unittest.TestCase):
 def test_reconciliation_read_only_and_profile(self):
  db=sqlite3.connect(':memory:')
  db.executescript('CREATE TABLE imported_documents(id integer,profile_id integer,doc_type text,extracted_json text);CREATE TABLE transactions(id integer,profile_id integer,amount_cents integer,recorded_at text,category text,description text,kind text);')
  db.execute('INSERT INTO imported_documents VALUES(1,1,?,?)',('statement',json.dumps({'candidates':[{'date':'2026-10-01','description':'Market','amount_cents':5000}]})))
  db.execute("INSERT INTO transactions VALUES(12,1,5000,'2026-10-01','Market','Test','expense')")
  before=db.total_changes
  rows=statement_reconciliation(db,1,1)
  self.assertEqual(rows[0]['status'],'review')
  self.assertEqual(rows[0]['possible_matches'][0]['id'],12)
  self.assertEqual(db.total_changes,before)
  with self.assertRaises(ValueError):statement_reconciliation(db,2,1)
 def test_schedule_duplicates(self):
  db=sqlite3.connect(':memory:')
  db.execute('CREATE TABLE imported_documents(id integer,profile_id integer,doc_type text,extracted_json text)')
  rows=[{'installment':1,'total_cents':190000},{'installment':1,'total_cents':190000}]
  db.execute('INSERT INTO imported_documents VALUES(1,1,?,?)',('schedule',json.dumps({'candidates':rows})))
  self.assertTrue(validate_schedule_preview(db,1,1)['errors'])
 def test_backup_includes_documents(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'user';p.mkdir()
   with closing(sqlite3.connect(p/'ailefinans.db')) as db, db:db.execute('CREATE TABLE x(a int)')
   (p/'product_documents').mkdir();(p/'product_documents'/'invoice.pdf').write_bytes(b'example')
   zip_path=Path(t)/'safe.zip';make_backup(p,zip_path)
   self.assertTrue(verify_backup(zip_path))
   with self.assertRaises(FileExistsError):make_backup(p,zip_path)
if __name__=='__main__':unittest.main()
