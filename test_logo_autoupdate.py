import tempfile
import unittest
from pathlib import Path
from bank_logo_manager import missing_logos, LOGO_IDS

class TestLogoAutoUpdate(unittest.TestCase):
    def test_missing_without_existing(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(len(missing_logos(td)),len(set(x for x in LOGO_IDS.values() if x)))
    def test_partial_cache(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'garanti.svg';p.write_text('<svg/>')
            self.assertNotIn('garanti',missing_logos(td))
            self.assertIn('akbank',missing_logos(td))
