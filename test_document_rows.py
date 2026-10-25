import unittest
from document_rows import preview_rows
from document_center import parse
class TestDocumentRows(unittest.TestCase):
 def test_statement(self):
  rows,w=preview_rows('05.11.2026 | Market | -1.250,75\n06.11.2026 | İade | +300,00','statement')
  self.assertEqual(len(rows),2);self.assertEqual(rows[0]['amount_cents'],-125075)
  self.assertEqual(rows[0]['date'],'2026-11-05')
 def test_schedule(self):
  rows,w=preview_rows('1 | 15.11.2026 | 1500,00 | 250,00 | 150,00 | 1900,00','schedule')
  self.assertEqual(rows[0]['total_cents'],190000)
 def test_bad_sum(self):
  rows,w=preview_rows('1 | 15.11.2026 | 1500,00 | 250,00 | 150,00 | 1800,00','schedule')
  self.assertFalse(rows);self.assertTrue(w)
 def test_no_post(self):
  parsed=parse('Dönem borcu: 1.000,00\n05.11.2026 | Market | 500,00','statement')
  self.assertEqual(parsed['candidates'][0]['amount_cents'],50000)
  self.assertIn('Otomatik finans kaydı yapılmaz',parsed['warnings'][-1])
if __name__=='__main__':unittest.main()
