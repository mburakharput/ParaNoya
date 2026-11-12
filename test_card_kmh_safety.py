"""Card and KMH financial invariant regressions (temporary sample databases only)."""
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from finance_core import migrate, open_db, add_account, accounts_with_balances
from v04_core import create_card, cards, purchase, pay_card, edit_shared_split
from kmh_core import (set_overdraft, use_overdraft, add_installment_loan,
                      monthly_calendar, pay_installment)


class CardKmhSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paranoya-card-kmh-")
        self.path = Path(self.temp.name) / "ailefinans.db"
        migrate(self.path)
        self.db = open_db(self.path)
        add_account(self.db, 1, "Banka", "bank", 100000)
        self.account = accounts_with_balances(self.db, 1)[0][0]
        create_card(self.db, 1, "Test Kartı", 10, 20, 10000)
        self.card = cards(self.db, 1)[0][0]

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_card_limit_and_released_capacity(self):
        purchase(self.db, 1, self.card, "Market", "İlk", 8000, 4, "2026-11-01")
        with self.assertRaisesRegex(ValueError, "limitini aşıyor"):
            purchase(self.db, 1, self.card, "Market", "Fazla", 2001, 1, "2026-11-02")
        self.assertEqual(cards(self.db, 1)[0][-1], 8000)
        pay_card(self.db, 1, self.card, self.account, 3000)
        purchase(self.db, 1, self.card, "Market", "Sonraki", 5000, 1, "2026-11-02")
        self.assertEqual(cards(self.db, 1)[0][-1], 10000)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM card_purchases").fetchone()[0], 2)
        self.assertEqual(accounts_with_balances(self.db, 1)[0][3], 97000)

    def test_card_rejects_non_integer_cents_and_installments(self):
        for amount, installments in ((100.5, 1), (True, 1), (100, 1.5), (100, True)):
            with self.subTest(amount=amount, installments=installments):
                with self.assertRaises(ValueError):
                    purchase(self.db, 1, self.card, "Market", "", amount, installments)
        with self.assertRaises(ValueError):
            pay_card(self.db, 1, self.card, self.account, 1.5)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM card_purchases").fetchone()[0], 0)

    def test_kmh_invalid_schedule_and_fractional_amounts(self):
        od = set_overdraft(self.db, 1, self.account, 20000)
        with self.assertRaises(ValueError):
            set_overdraft(self.db, 1, self.account, 20000.1)
        with self.assertRaises(ValueError):
            use_overdraft(self.db, 1, od, 3.5, "draw")
        invalid_schedules = [
            [("2026-12-10", 1000, 1.25, 0, 0)],
            [("2026-12-10", 1000)],
            [("2026-12-10", True, 0, 0, 0)],
            [("2026-12-10", 1000, -1, 0, 0)],
        ]
        for schedule in invalid_schedules:
            with self.subTest(schedule=schedule):
                with self.assertRaises(ValueError):
                    add_installment_loan(self.db, 1, od, 1000, schedule)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM kmh_loans").fetchone()[0], 0)
        loan = add_installment_loan(
            self.db, 1, od, 1000, [("2026-12-10", 1000, 100, 0, 0)]
        )
        self.assertGreater(loan, 0)
        installment_id = monthly_calendar(self.db, 1)[0][0]
        with self.assertRaises(ValueError):
            pay_installment(self.db, 1, installment_id, self.account, 1100.1)
        pay_installment(self.db, 1, installment_id, self.account, 1100)
        self.assertEqual(monthly_calendar(self.db, 1), [])


if __name__ == "__main__":
    unittest.main()
