import unittest
from card_catalog import load_catalog, search_catalog

class CatalogNewBanksTests(unittest.TestCase):
    def test_requested_banks_are_listed(self):
        data=load_catalog()
        banks={item['bank'] for item in data}
        for bank in ['Fibabanka','Ziraat Katılım','Ziraat Dinamik','Odeabank','Burgan Bank']:
            self.assertIn(bank,banks)
            self.assertTrue(search_catalog(data,bank=bank))

if __name__=='__main__': unittest.main()
