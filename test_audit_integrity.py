"""Regression coverage for the October audit; uses disposable data only."""
from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace

from finance_core import migrate, open_db, add_account
from record_manager import migrate_record_state, change_state, get_state
from kmh_core import set_overdraft, add_installment_loan, monthly_calendar, pay_installment
from v04_core import create_card, purchase, first_due


class AuditIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.sqlite'
        migrate(self.path)
        self.db = open_db(self.path)
        self.addCleanup(self.db.close)
        migrate_record_state(self.db)

    def test_future_schema_refused_without_changes(self):
        with self.db:
            self.db.execute('PRAGMA user_version=9')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            migrate(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('*.db')), [])

    def test_current_schema_not_downgraded(self):
        with self.db:
            self.db.execute('PRAGMA user_version=8')
        migrate(self.path)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], 8)

    def test_existing_v3_upgraded_and_backed_up(self):
        with self.db:
            self.db.execute('PRAGMA user_version=3')
        migrate(self.path)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], 4)
        self.assertTrue(list(self.path.parent.glob('*.v03_backup_*.sqlite')))

    def test_kmh_loan_and_payer_cannot_be_trashed(self):
        add_account(self.db, 1, 'Banka', 'bank', 0)
        add_account(self.db, 1, 'Nakit', 'cash', 10000)
        od = set_overdraft(self.db, 1, 1, 10000)
        add_installment_loan(self.db, 1, od, 10000, [('2026-11-30', 10000, 0, 0, 0)])
        with self.assertRaises(ValueError):
            change_state(self.db, 'kmh', od, 'trashed')
        iid = monthly_calendar(self.db, 1)[0][0]
        pay_installment(self.db, 1, iid, 2, 10000)
        with self.assertRaises(ValueError):
            change_state(self.db, 'account', 2, 'trashed')
        self.assertEqual(get_state(self.db, 'account', 2), 'active')
        change_state(self.db, 'account', 2, 'archived')
        self.assertEqual(get_state(self.db, 'account', 2), 'archived')

    def test_month_end_schedule_keeps_contract_day(self):
        self.assertEqual(first_due(date(2027, 2, 28), 10, 31), date(2027, 3, 31))
        create_card(self.db, 1, 'Kart', 10, 31, 10000)
        purchase(self.db, 1, 1, 'Ev', '', 10000, 4, '2027-01-31')
        rows = self.db.execute('SELECT due_date,amount_cents FROM card_installments ORDER BY sequence').fetchall()
        self.assertEqual([x[0] for x in rows], ['2027-02-28', '2027-03-31', '2027-04-30', '2027-05-31'])
        self.assertEqual(sum(x[1] for x in rows), 10000)

    def test_too_small_installment_rejected_without_partial_purchase(self):
        create_card(self.db, 1, 'Kart', 10, 20, 10000)
        with self.assertRaises(ValueError):
            purchase(self.db, 1, 1, 'Ev', '', 1, 2, '2026-10-29')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM card_purchases').fetchone()[0], 0)

    def test_dashboard_expenses_include_card_purchases_and_other_categories(self):
        from ailefinans import App
        from finance_core import add_transaction
        class Chart:
            def set_values(self, values):
                self.values = values
        add_account(self.db, 1, 'Banka', 'bank', 10000)
        for i in range(8):
            add_transaction(self.db, 1, 1, 'expense', f'Kategori {i}', '', 100)
        create_card(self.db, 1, 'Kart', 10, 20, 10000)
        purchase(self.db, 1, 1, 'Kart harcaması', '', 200, 1, '2026-10-29')
        host = SimpleNamespace(db=self.db,category_chart=Chart(),trend_chart=Chart(),asset_chart=Chart())
        App.refresh_charts(host, 1)
        self.assertEqual(len(host.category_chart.values), 6)
        self.assertEqual(sum(v for _,v in host.category_chart.values), 1000)
        self.assertEqual(sum(v[2] for v in host.trend_chart.values), 1000)
        self.assertIn(('Kart harcaması', 200), host.category_chart.values)
        App.refresh_charts(host, 2)
        self.assertEqual(host.category_chart.values, [])
