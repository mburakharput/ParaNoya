import unittest
from pathlib import Path
class BankSelectorTests(unittest.TestCase):
 def test_ui_contract(self):
  s=(Path(__file__).parent/'ailefinans.py').read_text(encoding='utf-8')
  for t in ('class BankSelectionCombo', 'MatchContains', 'setMaxVisibleItems(7)', 'self.bank = BankSelectionCombo()', 'chevron-down.svg', 'MouseButtonRelease'):
   self.assertIn(t,s)
 def test_asset(self):
  assert (Path(__file__).parent/'assets'/'chevron-down.svg').is_file()
