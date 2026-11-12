"""Read-only dashboard reports should preserve calendar gaps and ledger semantics."""
from contextlib import closing
from datetime import date
from pathlib import Path
import tempfile
import unittest

from finance_core import migrate, open_db, add_account, add_transaction, summary
from reporting_core import monthly_trend, category_expenses
from v04_core import create_card, cards, purchase, pay_card


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paranoya-reporting-")
        self.path = Path(self.temp.name) / "finance.db"
        migrate(self.path)
        self.db = open_db(self.path)
        add_account(self.db, 1, "Kişisel banka", "bank", 200000)
        add_account(self.db, 2, "Aile banka", "bank", 100000)
        self.personal = self.db.execute(
            "SELECT id FROM accounts WHERE profile_id=1"
        ).fetchone()[0]
        self.family = self.db.execute(
            "SELECT id FROM accounts WHERE profile_id=2"
        ).fetchone()[0]
        create_card(self.db, 1, "Kişisel kart", 10, 20, 100000)
        self.card = cards(self.db, 1)[0][0]

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_recent_six_months_include_zeros_and_ignore_old_data(self):
        add_transaction(self.db, 1, self.personal, "income", "Maaş", "", 50000)
        with self.db:
            self.db.execute(
                "UPDATE transactions SET recorded_at='2026-08-02 11:00:00' WHERE profile_id=1"
            )
        purchase(self.db, 1, self.card, "Market", "Alışveriş", 12000, 1, "2026-10-19")
        add_transaction(self.db, 2, self.family, "expense", "Aile", "", 9000)
        self.assertEqual(
            monthly_trend(self.db, 1, today=date(2026, 11, 12)),
            [
                ("2026-06", 0, 0),
                ("2026-07", 0, 0),
                ("2026-08", 50000, 0),
                ("2026-09", 0, 0),
                ("2026-10", 0, 12000),
                ("2026-11", 0, 0),
            ],
        )
        self.assertEqual(
            monthly_trend(self.db, 2, today=date(2026, 11, 12))[-1],
            ("2026-11", 0, 9000),
        )

    def test_card_repayment_is_not_another_expense(self):
        purchase(self.db, 1, self.card, "Ulaşım", "Otobüs", 10000, 2, "2026-10-21")
        pay_card(self.db, 1, self.card, self.personal, 3000)
        self.assertEqual(summary(self.db, 1)[1], 10000)
        self.assertEqual(category_expenses(self.db, 1), [("Ulaşım", 10000)])
        self.assertEqual(
            monthly_trend(self.db, 1, today=date(2026, 11, 12))[-2],
            ("2026-10", 0, 10000),
        )

    def test_january_rollover_and_window_validation(self):
        rows = monthly_trend(self.db, 1, today=date(2027, 1, 5), months=3)
        self.assertEqual(
            rows, [("2026-11", 0, 0), ("2026-12", 0, 0), ("2027-01", 0, 0)]
        )
        for count in (0, -1, 121, 1.5, True, "6"):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    monthly_trend(self.db, 1, months=count)


if __name__ == "__main__":
    unittest.main()
