import unittest
import tempfile
import json
from pathlib import Path
from card_catalog import load_catalog,search_catalog

class CatalogTests(unittest.TestCase):
 def test_search(self):
  items=load_catalog()
  matches=search_catalog(items,'platinum diji','Garanti BBVA')
  self.assertEqual(len(matches),1)
  self.assertTrue(matches[0]['verified'])
 def test_custom(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'extra.json'
   p.write_text(json.dumps([{'bank':'Örnek Banka','card':'Özel Kart'}]),encoding='utf-8')
   self.assertEqual(len(search_catalog(load_catalog(p),'Özel Kart')),1)
 def test_no_automatic_verification(self):
  self.assertFalse(search_catalog(load_catalog(),'Axess')[0]['verified'])
if __name__=='__main__':unittest.main()
