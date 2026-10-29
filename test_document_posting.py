from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
import sqlite3

from document_center import migrate_documents, stage, parse, approve_document_entry
from finance_core import migrate, open_db, add_account, add_transaction, summary, accounts_with_balances
from v04_core import create_card, purchase, cards


class DocumentPostingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'finance.sqlite';migrate(self.path)
        self.db=open_db(self.path);self.addCleanup(self.db.close)
        migrate_documents(self.db);add_account(self.db,1,'Banka','bank',100000)
        create_card(self.db,1,'Kart',10,20,100000)

    def stage_text(self,text,typ,name='document.txt'):
        p=Path(self.temp.name)/name;p.write_text(text,encoding='utf-8')
        return stage(self.db,1,p,typ)[0]

    def post(self,did,**kwargs):
        args=dict(account_id=1,cents=12500,day='2026-10-29',category='Faturalar',description='Elektrik',confirmed=True)
        args.update(kwargs)
        return approve_document_entry(self.db,1,did,**args)

    def test_invoice_fields_and_confirmed_expense_once(self):
        text='Firma: Elektrik AŞ\nFatura No: ABC2026001\nFatura Tarihi: 28.10.2026\nÖdenecek Tutar: 125,00 TL'
        fields=parse(text,'invoice')['fields']
        self.assertEqual(fields['total'],12500)
        self.assertEqual(fields['invoice_number'],'ABC2026001')
        did=self.stage_text(text,'invoice')
        with self.assertRaises(ValueError):self.post(did,confirmed=False)
        self.assertEqual(summary(self.db,1),(0,0,100000))
        self.assertTrue(self.post(did)[1])
        self.assertEqual(summary(self.db,1),(0,12500,87500))
        with self.assertRaises(ValueError):self.post(did)

    def test_exact_existing_expense_links_without_double_post(self):
        add_transaction(self.db,1,1,'expense','Faturalar','Elektrik',12500)
        with self.db:self.db.execute("UPDATE transactions SET recorded_at='2026-10-29 09:00:00'")
        did=self.stage_text('Genel Toplam: 125,00','invoice')
        self.assertFalse(self.post(did)[1])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],1)

    def test_ambiguous_duplicate_stays_pending(self):
        add_transaction(self.db,1,1,'expense','Diğer','Başka açıklama',12500)
        with self.db:self.db.execute("UPDATE transactions SET recorded_at='2026-10-29 09:00:00'")
        did=self.stage_text('Genel Toplam: 125,00','invoice')
        with self.assertRaises(ValueError):self.post(did)
        self.assertEqual(self.db.execute('SELECT status FROM imported_documents WHERE id=?',(did,)).fetchone()[0],'pending')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM document_posting_links').fetchone()[0],0)

    def test_salary_income_on_selected_date(self):
        did=self.stage_text('Net maaş: 125,00\nDönem: 10/2026','payslip')
        self.post(did,category='Maaş',period='10/2026')
        self.assertEqual(summary(self.db,1),(12500,0,112500))
        self.assertEqual(self.db.execute('SELECT recorded_at,description FROM transactions').fetchone(),('2026-10-29 12:00:00','Bordro: 10/2026'))

    def test_statement_post_creates_card_debt_without_cash_withdrawal(self):
        did=self.stage_text('29.10.2026;Market;125,00\n30.10.2026;Kitap;50,00','statement')
        self.assertTrue(self.post(did,card_id=1,source_line=1,description='Market')[1])
        self.assertEqual(summary(self.db,1),(0,12500,100000))
        self.assertEqual(cards(self.db,1)[0][-1],12500)
        self.assertEqual(self.db.execute('SELECT status FROM imported_documents WHERE id=?',(did,)).fetchone()[0],'partial')
        with self.assertRaises(ValueError):self.post(did,card_id=1,source_line=1)
        self.post(did,card_id=1,source_line=2,cents=5000,description='Kitap',day='2026-10-30')
        self.assertEqual(self.db.execute('SELECT status FROM imported_documents WHERE id=?',(did,)).fetchone()[0],'posted')

    def test_statement_links_previously_recorded_purchase(self):
        purchase(self.db,1,1,'Market','Market',12500,1,'2026-10-29')
        did=self.stage_text('29.10.2026;Market;125,00','statement')
        self.assertFalse(self.post(did,card_id=1,source_line=1,description='Market')[1])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM card_purchases').fetchone()[0],1)

    def test_statement_cannot_post_total_payment_or_negative_row(self):
        for text,line in [('Dönem borcu: 125,00',1),('29.10.2026;Kart ödemesi;125,00',1),('29.10.2026;Market;-125,00',1),('29.10.2026;Mobilya 2/6 taksit;125,00',1)]:
            with self.subTest(text=text):
                did=self.stage_text(text,'statement')
                with self.assertRaises(ValueError):self.post(did,card_id=1,source_line=line)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM card_purchases').fetchone()[0],0)

    def test_foreign_profile_account_and_card_rejected(self):
        add_account(self.db,2,'Aile','bank',0);create_card(self.db,2,'Aile kartı',10,20,100000)
        did=self.stage_text('Genel Toplam: 125,00','invoice')
        with self.assertRaises(ValueError):self.post(did,account_id=2)
        did=self.stage_text('29.10.2026;Market;125,00','statement')
        with self.assertRaises(ValueError):self.post(did,card_id=2,source_line=1)

    def test_same_upload_keeps_original_type_and_parsed_data(self):
        text='Genel Toplam: 125,00'
        did=self.stage_text(text,'invoice')
        _,fresh,parsed=stage(self.db,1,Path(self.temp.name)/'document.txt','payslip')
        self.assertFalse(fresh);self.assertEqual(parsed['type'],'invoice')

    def test_posting_rolls_back_if_document_link_fails(self):
        did=self.stage_text('29.10.2026;Market;125,00','statement')
        self.db.execute("CREATE TRIGGER fail_link BEFORE INSERT ON document_posting_links BEGIN SELECT RAISE(ABORT,'test failure'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):self.post(did,card_id=1,source_line=1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM card_purchases').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM card_installments').fetchone()[0],0)

    def test_concurrent_exports_do_not_duplicate_expense(self):
        first=self.stage_text('Genel Toplam: 125,00','invoice','first.txt')
        second=self.stage_text('Genel Toplam: 125,00\nKopya','invoice','second.txt')
        def post_with_connection(did):
            with closing(open_db(self.path)) as db:
                return approve_document_entry(db,1,did,account_id=1,cents=12500,day='2026-10-29',category='Faturalar',description='Elektrik',confirmed=True)[1]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(post_with_connection,[first,second]))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],1)
