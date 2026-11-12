"""Regression tests for exact integer-cent financial writes and account isolation."""
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from finance_core import (
    migrate, open_db, add_account, add_transaction, accounts_with_balances,
    summary, transfer, add_member, add_shared_expense,
)


class FinancialAmountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paranoya-finance-test-")
        self.path = Path(self.temp.name) / "ailefinans.db"
        migrate(self.path)
        self.db = open_db(self.path)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def add_account(self, profile, name, initial=0):
        add_account(self.db, profile, name, "bank", initial)
        return self.db.execute(
            "SELECT id FROM accounts WHERE profile_id=? AND name=?", (profile, name)
        ).fetchone()[0]

    def test_reject_fractional_or_boolean_cents_without_writing(self):
        for value in (12.5, True, "100", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    add_account(self.db, 1, "Invalid", "cash", value)
        account = self.add_account(1, "Main", 10000)
        for value in (15.5, True, "100", None):
            with self.subTest(transaction=value):
                with self.assertRaises(ValueError):
                    add_transaction(self.db, 1, account, "expense", "Market", "", value)
                with self.assertRaises(ValueError):
                    transfer(self.db, 1, account, account + 1, value)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM transfers").fetchone()[0], 0)

    def test_transfers_conserve_total_and_keep_profiles_separate(self):
        first = self.add_account(1, "Primary", 12000)
        second = self.add_account(1, "Savings", 3000)
        family = self.add_account(2, "Family", 40000)
        add_transaction(self.db, 1, first, "income", "Salary", "", 5000)
        add_transaction(self.db, 1, first, "expense", "Groceries", "", 2000)
        before = sum(row[3] for row in accounts_with_balances(self.db, 1))
        transfer(self.db, 1, first, second, 7000)
        balances = {row[0]: row[3] for row in accounts_with_balances(self.db, 1)}
        self.assertEqual(balances, {first: 8000, second: 10000})
        self.assertEqual(sum(balances.values()), before)
        self.assertEqual(summary(self.db, 1), (5000, 2000, 18000))
        self.assertEqual(accounts_with_balances(self.db, 2)[0][3], 40000)
        with self.assertRaises(ValueError):
            transfer(self.db, 1, first, family, 100)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM transfers").fetchone()[0], 1)

    def test_shared_expense_requires_exact_integer_splits(self):
        family = self.add_account(2, "Family", 10000)
        add_member(self.db, "Sample")
        member = self.db.execute("SELECT id FROM family_members WHERE name='Sample'").fetchone()[0]
        for amount, shares in ((100.0, {member: 100}), (100, {member: 100.0}),
                               (100, {member: True}), (100, [100])):
            with self.subTest(amount=amount, shares=shares):
                with self.assertRaises(ValueError):
                    add_shared_expense(self.db, 2, family, "Bills", "", amount, shares)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 0)
        add_shared_expense(self.db, 2, family, "Bills", "", 123, {member: 123})
        self.assertEqual(accounts_with_balances(self.db, 2)[0][3], 9877)


if __name__ == "__main__":
    unittest.main()
