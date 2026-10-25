import sqlite3
import unittest
from record_manager import migrate_record_state,change_state,get_state

class SafeRecordTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:')
  self.db.execute('PRAGMA foreign_keys=ON')
  self.db.executescript('CREATE TABLE accounts(id INTEGER PRIMARY KEY); CREATE TABLE credit_cards(id INTEGER PRIMARY KEY); CREATE TABLE overdraft_accounts(id INTEGER PRIMARY KEY,account_id INTEGER); CREATE TABLE transactions(id INTEGER PRIMARY KEY,account_id INTEGER); CREATE TABLE transfers(id INTEGER PRIMARY KEY,from_account_id INTEGER,to_account_id INTEGER); CREATE TABLE card_payments(id INTEGER PRIMARY KEY,account_id INTEGER,card_id INTEGER); CREATE TABLE card_purchases(id INTEGER PRIMARY KEY,card_id INTEGER); CREATE TABLE overdraft_events(id INTEGER PRIMARY KEY,overdraft_id INTEGER);')
  self.db.execute('INSERT INTO accounts VALUES(1)')
  self.db.execute('INSERT INTO credit_cards VALUES(2)')
  self.db.execute('INSERT INTO overdraft_accounts VALUES(3,1)')
  migrate_record_state(self.db)
 def tearDown(self):self.db.close()
 def test_empty_card_trashed_restored(self):
  change_state(self.db,'card',2,'trashed')
  self.assertEqual(get_state(self.db,'card',2),'trashed')
  change_state(self.db,'card',2,'active')
  self.assertEqual(get_state(self.db,'card',2),'active')
 def test_linked_card_cannot_trash(self):
  self.db.execute('INSERT INTO card_purchases VALUES(1,2)')
  with self.assertRaises(ValueError):change_state(self.db,'card',2,'trashed')
  change_state(self.db,'card',2,'archived')
  self.assertEqual(get_state(self.db,'card',2),'archived')
 def test_kmh_account_cannot_trash(self):
  with self.assertRaises(ValueError):change_state(self.db,'account',1,'trashed')
 def test_invalid_target(self):
  with self.assertRaises(ValueError):change_state(self.db,'card',2,'deleted')

if __name__=='__main__':unittest.main()
