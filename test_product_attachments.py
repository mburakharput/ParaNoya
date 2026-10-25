import unittest,sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from finance_core import migrate
from product_core import migrate_products, create_product, attach_product_document, list_product_documents, document_path

class Attachments(unittest.TestCase):
 def test_attach_duplicate_and_isolation(self):
  with TemporaryDirectory() as tmp:
   root=Path(tmp);path=root/'db.sqlite';migrate(path)
   db=sqlite3.connect(path);db.execute('PRAGMA foreign_keys=ON');migrate_products(db)
   product=create_product(db,1,'Laptop','2026-10-25')
   doc=root/'invoice.pdf';doc.write_bytes(b'%PDF-example')
   folder=root/'docs'
   ident=attach_product_document(db,1,product,doc,folder)
   self.assertEqual(len(list_product_documents(db,1,product)),1)
   self.assertTrue(document_path(db,1,ident,folder).exists())
   self.assertEqual(list_product_documents(db,2,product),[])
   with self.assertRaises(ValueError):document_path(db,2,ident,folder)
   with self.assertRaises(ValueError):attach_product_document(db,1,product,doc,folder)
   with self.assertRaises(ValueError):attach_product_document(db,2,product,doc,folder)
   db.close()
 def test_invalid_type(self):
  with TemporaryDirectory() as tmp:
   path=Path(tmp)/'db.sqlite';migrate(path)
   db=sqlite3.connect(path);migrate_products(db)
   product=create_product(db,1,'Laptop','2026-10-25')
   doc=Path(tmp)/'x.txt';doc.write_text('test')
   with self.assertRaises(ValueError):attach_product_document(db,1,product,doc,Path(tmp)/'docs')
   db.close()
