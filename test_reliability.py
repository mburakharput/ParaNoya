"""Real independent SQLite writers and recovery tests; synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from finance_core import migrate,open_db,add_account
from v04_core import create_card,purchase,pay_card,cards
from kmh_core import set_overdraft,use_overdraft,add_installment_loan,pay_installment
from recurring_core import migrate_recurring,add_item,upcoming_items,pay_occurrence
from backup_manager import make_backup,verify_backup,restore_backup,recover_interrupted_restore


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.data=self.root/'data';self.data.mkdir()
        self.path=self.data/'ailefinans.db';migrate(self.path)
        self.db=open_db(self.path);self.addCleanup(self.db.close)
        add_account(self.db,1,'Synthetic bank','bank',100000)
        self.od=set_overdraft(self.db,1,1,10000)

    def race(self,operation):
        barrier=threading.Barrier(2)
        def task():
            with closing(open_db(self.path)) as db:
                barrier.wait(timeout=5)
                try:operation(db);return 'accepted'
                except ValueError:return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(task) for _ in range(2)]
            results=[f.result(timeout=10) for f in futures]
        self.assertEqual(sorted(results),['accepted','rejected'])

    def test_two_card_payments_cannot_exceed_debt(self):
        create_card(self.db,1,'Synthetic card',10,20,10000)
        purchase(self.db,1,1,'Test','Test',10000,1)
        self.race(lambda db:pay_card(db,1,1,1,10000))
        self.assertEqual(cards(self.db,1)[0][-1],0)
        self.assertEqual(self.db.execute('SELECT SUM(amount_cents) FROM card_payments').fetchone()[0],10000)

    def test_two_kmh_draws_cannot_exceed_limit(self):
        self.race(lambda db:use_overdraft(db,1,self.od,10000,'draw'))
        self.assertEqual(self.db.execute('SELECT SUM(amount_cents) FROM overdraft_events').fetchone()[0],10000)

    def test_two_kmh_repayments_cannot_exceed_debt(self):
        use_overdraft(self.db,1,self.od,10000,'draw')
        self.race(lambda db:use_overdraft(db,1,self.od,10000,'repay'))
        self.assertEqual(self.db.execute("SELECT SUM(amount_cents) FROM overdraft_events WHERE kind='repay'").fetchone()[0],10000)

    def test_two_installment_payments_cannot_exceed_remaining(self):
        add_installment_loan(self.db,1,self.od,10000,[('2026-11-01',10000,0,0,0)])
        self.race(lambda db:pay_installment(db,1,1,1,10000))
        self.assertEqual(self.db.execute('SELECT paid_cents FROM kmh_installments').fetchone()[0],10000)

    def test_nested_purchase_does_not_commit_outer_operation(self):
        create_card(self.db,1,'Synthetic card',10,20,10000)
        self.db.execute('BEGIN IMMEDIATE')
        purchase(self.db,1,1,'Test','Test',10000,1)
        self.db.rollback()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM card_purchases').fetchone()[0],0)

    def test_overdue_bill_remains_visible_and_old_period_can_be_paid(self):
        migrate_recurring(self.db)
        item=add_item(self.db,1,'Old bill','bill','Test',5000,'monthly','2000-01-31')
        dues={r[3] for r in upcoming_items(self.db,1,date(2026,10,29),1)}
        self.assertIn('2000-01-31',dues);self.assertIn('2026-10-31',dues)
        pay_occurrence(self.db,1,item,'2026-10-31',1)
        self.assertNotIn('2026-10-31',{r[3] for r in upcoming_items(self.db,1,date(2026,10,29),1)})
        with self.assertRaises(ValueError):pay_occurrence(self.db,1,item,'2026-10-30',1)

    def test_same_bill_paid_by_two_connections_is_posted_once(self):
        migrate_recurring(self.db)
        item=add_item(self.db,1,'Bill','bill','Test',5000,'monthly','2026-01-31')
        self.race(lambda db:pay_occurrence(db,1,item,'2026-02-28',1))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM recurring_payments').fetchone()[0],1)

    def forged(self,files):
        path=self.root/'forged.zip'
        manifest={'format':'paranoya-backup-v1','files':{n:{'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)} for n,b in files.items()}}
        with ZipFile(path,'w') as z:
            for n,b in files.items():z.writestr(n,b)
            z.writestr('manifest.json',json.dumps(manifest))
        return path

    def test_non_database_with_valid_hash_is_rejected(self):
        with self.assertRaises(ValueError):verify_backup(self.forged({'ailefinans.db':b'not SQLite'}))

    def test_future_schema_rejected(self):
        self.db.execute('PRAGMA user_version=999');self.db.commit()
        with self.assertRaises(ValueError):make_backup(self.data,self.root/'future.zip')
        self.assertFalse((self.root/'future.zip').exists())
        self.assertEqual(list(self.root.glob('*.partial')),[])

    def test_foreign_key_corruption_rejected(self):
        self.db.execute('PRAGMA foreign_keys=OFF')
        self.db.execute("INSERT INTO accounts(profile_id,name,kind,opening_balance_cents) VALUES(999,'Orphan','bank',0)")
        self.db.commit()
        with self.assertRaises(ValueError):make_backup(self.data,self.root/'orphan.zip')

    def test_unsafe_path_rejected(self):
        for name in ('../outside','product_documents/../outside','product_documents/C:bad','product_documents/NUL','product_documents/x.'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                verify_backup(self.forged({'ailefinans.db':self.path.read_bytes(),name:b'x'}))

    def test_duplicate_zip_name_rejected(self):
        path=self.forged({'ailefinans.db':self.path.read_bytes()})
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with ZipFile(path,'a') as z:z.writestr('ailefinans.db',self.path.read_bytes())
        with self.assertRaises(ValueError):verify_backup(path)

    def test_restore_keeps_entire_original_and_replaces_from_verified_backup(self):
        docs=self.data/'product_documents';docs.mkdir();(docs/'example.pdf').write_bytes(b'synthetic attachment')
        path=make_backup(self.data,self.root/'valid.zip')
        (self.data/'preserve.txt').write_text('recovery sentinel')
        add_account(self.db,1,'Added after backup','cash',1)
        self.db.close()
        recovery=restore_backup(path,self.data,confirmed=True)
        self.assertEqual((recovery/'preserve.txt').read_text(),'recovery sentinel')
        self.assertEqual((self.data/'product_documents'/'example.pdf').read_bytes(),b'synthetic attachment')
        with closing(open_db(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0],1)

    def test_restore_without_consent_or_with_bad_backup_does_not_modify_data(self):
        before=self.path.read_bytes()
        path=self.forged({'ailefinans.db':b'bad'})
        with self.assertRaises(ValueError):restore_backup(path,self.data)
        with self.assertRaises(ValueError):restore_backup(path,self.data,confirmed=True)
        self.assertEqual(self.path.read_bytes(),before)

    def test_restore_failed_replacement_rolls_back(self):
        path=make_backup(self.data,self.root/'valid.zip');self.db.close()
        before=self.path.read_bytes()
        import os
        rename=os.rename;calls=[]
        def fail_second(src,dst):
            calls.append((src,dst))
            if len(calls)==2:raise OSError('synthetic replacement failure')
            return rename(src,dst)
        with patch('backup_manager.os.rename',side_effect=fail_second),self.assertRaises(OSError):
            restore_backup(path,self.data,confirmed=True)
        self.assertEqual(self.path.read_bytes(),before)

    def test_failed_backup_never_publishes_partial_output(self):
        target=self.root/'failed.zip'
        with patch('backup_manager.verify_backup',side_effect=ValueError('synthetic failure')),self.assertRaises(ValueError):
            make_backup(self.data,target)
        self.assertFalse(target.exists());self.assertEqual(list(self.root.glob('*.partial')),[])

    def test_missing_referenced_attachment_rejected(self):
        from product_core import migrate_products,create_product,attach_product_document
        migrate_products(self.db)
        product=create_product(self.db,1,'Synthetic','2026-01-01')
        source=self.root/'invoice.pdf';source.write_bytes(b'synthetic')
        attach_product_document(self.db,1,product,source,self.data/'product_documents')
        for file in (self.data/'product_documents').iterdir():file.unlink()
        with self.assertRaises(ValueError):make_backup(self.data,self.root/'missing.zip')

    def test_interrupted_restore_recovers_before_database_creation(self):
        self.db.close();before=self.path.read_bytes()
        recovery=self.root/'data.before-restore-synthetic'
        self.data.rename(recovery)
        (self.root/'data.restore-pending.json').write_text(json.dumps({'recovery':recovery.name}))
        recover_interrupted_restore(self.data)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse((self.root/'data.restore-pending.json').exists())

    def test_recovery_journal_cannot_redirect_outside_data_parent(self):
        (self.root/'data.restore-pending.json').write_text(json.dumps({'recovery':'../outside'}))
        with self.assertRaises(ValueError):recover_interrupted_restore(self.data)


if __name__=='__main__':unittest.main()
