import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from bank_logo_manager import logo_path, fetch_logos, LOGO_IDS

class LogoTests(unittest.TestCase):
    def test_explicit_aliases(self):
        self.assertEqual(LOGO_IDS['Garanti BBVA'], 'garanti')
        self.assertEqual(LOGO_IDS['Ziraat Katılım'], 'ziraatkatilim')
        self.assertNotEqual(LOGO_IDS['Ziraat Bankası'], LOGO_IDS['Ziraat Katılım'])
    def test_missing_uses_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(logo_path('Ziraat Dinamik', d))
            self.assertIsNone(logo_path('Garanti BBVA', d))
            (Path(d)/'garanti.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
            self.assertEqual(logo_path('Garanti BBVA', d).name, 'garanti.svg')
    def test_existing_logos_do_not_download(self):
        with tempfile.TemporaryDirectory() as d:
            for slug in set(v for v in LOGO_IDS.values() if v):
                (Path(d)/(slug+'.svg')).write_text('<svg/>')
            with patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network')):
                downloaded,present,errors=fetch_logos(d)
            self.assertEqual(downloaded,0)
            self.assertEqual(len(errors),0)
            self.assertEqual(present,len(set(v for v in LOGO_IDS.values() if v)))

if __name__=='__main__': unittest.main()
