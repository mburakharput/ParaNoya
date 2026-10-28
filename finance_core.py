import sqlite3
import os
from contextlib import closing
import shutil
from pathlib import Path
from datetime import datetime
from decimal import Decimal

DB_DIR = Path(os.environ['PARANOYA_DATA_DIR']) if os.environ.get('PARANOYA_DATA_DIR') else Path.home() / 'AileFinans'
DB_PATH = DB_DIR / 'ailefinans.db'
MAX_SCHEMA_VERSION = 8


def money(cents):
    value = Decimal(int(cents)) / 100
    return f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + ' ₺'


def open_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 5000')
    return conn


def migrate(path=DB_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Existing v0.1 DB is preserved. The backup is made only when v0.2 tables are not present.
        with closing(open_db(path)) as check, check:
            exists = check.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone()
        if not exists:
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup = path.with_name(f'{path.stem}.v01_backup_{stamp}{path.suffix}')
            shutil.copy2(path, backup)
    if path.exists():
        with closing(open_db(path)) as check, check:
            version = check.execute('PRAGMA user_version').fetchone()[0]
            needs_upgrade = version < 3
            if needs_upgrade and check.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone():
                stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                backup = path.with_name(f'{path.stem}.v02_backup_{stamp}{path.suffix}')
                with closing(sqlite3.connect(backup)) as destination, destination:
                    check.backup(destination)
    with closing(open_db(path)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL CHECK(kind IN ('personal','family')))''')
        db.executemany('INSERT OR IGNORE INTO profiles (id,name,kind) VALUES (?,?,?)',
                       [(1, 'Kişisel', 'personal'), (2, 'Aile', 'family')])
        db.execute('''CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL REFERENCES profiles(id),
            name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('cash','bank')),
            opening_balance_cents INTEGER NOT NULL DEFAULT 0,
            UNIQUE(profile_id, name))''')
        db.execute('''CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL REFERENCES profiles(id),
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
            category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_tx_profile ON transactions(profile_id,recorded_at)')
        db.execute('''CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)))''')
        db.execute('''CREATE TABLE IF NOT EXISTS expense_splits (
            transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
            member_id INTEGER NOT NULL REFERENCES family_members(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
            PRIMARY KEY(transaction_id, member_id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL REFERENCES profiles(id),
            from_account_id INTEGER NOT NULL REFERENCES accounts(id),
            to_account_id INTEGER NOT NULL REFERENCES accounts(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            note TEXT NOT NULL DEFAULT '',
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(from_account_id != to_account_id))''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_transfer_profile ON transfers(profile_id)')
        db.execute('PRAGMA user_version=3')


def get_profiles(db):
    return db.execute('SELECT id,name FROM profiles ORDER BY id').fetchall()


def add_account(db, profile, name, kind, opening_cents):
    name = name.strip()
    if not name or kind not in ('cash', 'bank'):
        raise ValueError('Geçerli bir hesap adı ve türü girin.')
    with db:
        db.execute('INSERT INTO accounts(profile_id,name,kind,opening_balance_cents) VALUES(?,?,?,?)',
                   (profile, name, kind, opening_cents))


def add_transaction(db, profile, account, kind, category, description, amount_cents):
    if amount_cents <= 0 or kind not in ('income', 'expense') or not category.strip():
        raise ValueError('İşlem türü, kategori veya tutar geçersiz.')
    with db:
        valid = db.execute('SELECT 1 FROM accounts WHERE id=? AND profile_id=?',
                           (account, profile)).fetchone()
        if not valid:
            raise ValueError('Bu hesap seçili profile ait değil.')
        db.execute('''INSERT INTO transactions(profile_id,account_id,kind,category,description,amount_cents)
                      VALUES(?,?,?,?,?,?)''',
                   (profile, account, kind, category.strip(), description.strip(), amount_cents))


def accounts_with_balances(db, profile):
    return db.execute('''SELECT a.id, a.name, a.kind,
        a.opening_balance_cents
        + COALESCE((SELECT SUM(CASE t.kind WHEN 'income' THEN t.amount_cents ELSE -t.amount_cents END)
                    FROM transactions t WHERE t.account_id=a.id),0)
        + COALESCE((SELECT SUM(tr.amount_cents) FROM transfers tr WHERE tr.to_account_id=a.id),0)
        - COALESCE((SELECT SUM(tr.amount_cents) FROM transfers tr WHERE tr.from_account_id=a.id),0)
        - COALESCE((SELECT SUM(cp.amount_cents) FROM card_payments cp WHERE cp.account_id=a.id),0)
        + COALESCE((SELECT SUM(CASE e.kind WHEN 'draw' THEN e.amount_cents WHEN 'repay' THEN -e.amount_cents ELSE 0 END) FROM overdraft_events e JOIN overdraft_accounts od ON od.id=e.overdraft_id WHERE od.account_id=a.id),0)
        + COALESCE((SELECT SUM(l.principal_cents) FROM kmh_loans l JOIN overdraft_accounts od ON od.id=l.overdraft_id WHERE od.account_id=a.id),0)
        - COALESCE((SELECT SUM(p.amount_cents) FROM kmh_payments p WHERE p.from_account_id=a.id),0)
        FROM accounts a WHERE a.profile_id=? ORDER BY a.id''', (profile,)).fetchall()


def summary(db, profile):
    result = db.execute('''SELECT
        COALESCE(SUM(CASE WHEN kind='income' THEN amount_cents ELSE 0 END),0),
        COALESCE(SUM(CASE WHEN kind='expense' THEN amount_cents ELSE 0 END),0)
        FROM transactions WHERE profile_id=?''', (profile,)).fetchone()
    from v04_core import cards
    result = (result[0], result[1] + (db.execute('SELECT COALESCE(SUM(p.total_cents),0) FROM card_purchases p JOIN credit_cards c ON c.id=p.card_id WHERE c.profile_id=?',(profile,)).fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE name='credit_cards'").fetchone() else 0))
    balance = sum(row[3] for row in accounts_with_balances(db, profile))
    return result[0], result[1], balance




def add_member(db, name):
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError('Üye adı 1-100 karakter arasında olmalı.')
    with db:
        db.execute('INSERT INTO family_members(name) VALUES (?)', (name,))


def get_members(db):
    return db.execute('SELECT id,name FROM family_members WHERE active=1 ORDER BY name').fetchall()


def add_shared_expense(db, profile, account, category, description, amount_cents, allocation):
    # Split describes attribution only. Actual money movement occurs once, in transactions.
    if amount_cents <= 0 or not allocation or any(v < 0 for v in allocation.values()) or sum(allocation.values()) != amount_cents:
        raise ValueError('Pay toplamları gider tutarına eşit olmalı.')
    with db:
        if db.execute('SELECT kind FROM profiles WHERE id=?', (profile,)).fetchone() != ('family',):
            raise ValueError('Paylaşılan gider için Aile çalışma alanını seçin.')
        if not db.execute('SELECT 1 FROM accounts WHERE id=? AND profile_id=?', (account,profile)).fetchone():
            raise ValueError('Hesap aile çalışma alanına ait değil.')
        existing = {row[0] for row in get_members(db)}
        if not set(allocation).issubset(existing):
            raise ValueError('Bilinmeyen aile üyesi.')
        cur = db.execute('INSERT INTO transactions(profile_id,account_id,kind,category,description,amount_cents) VALUES (?,?,?,?,?,?)',
                         (profile,account,'expense',category.strip() or 'Ortak gider',description.strip(),amount_cents))
        db.executemany('INSERT INTO expense_splits(transaction_id,member_id,amount_cents) VALUES (?,?,?)',
                       [(cur.lastrowid,member,cents) for member,cents in allocation.items()])
        return cur.lastrowid


def member_expenses(db):
    return db.execute("""SELECT m.name, COALESCE(SUM(s.amount_cents),0)
        FROM family_members m LEFT JOIN expense_splits s ON s.member_id=m.id
        WHERE m.active=1 GROUP BY m.id ORDER BY m.name""").fetchall()


def transfer(db, profile, from_account, to_account, cents, note=''):
    if cents <= 0 or from_account == to_account:
        raise ValueError('Pozitif tutar ve farklı iki hesap seçin.')
    with db:
        valid = db.execute('SELECT COUNT(*) FROM accounts WHERE profile_id=? AND id IN (?,?)',
                           (profile,from_account,to_account)).fetchone()[0]
        if valid != 2:
            raise ValueError('İki hesap da aynı çalışma alanına ait olmalı.')
        db.execute('INSERT INTO transfers(profile_id,from_account_id,to_account_id,amount_cents,note) VALUES (?,?,?,?,?)',
                   (profile,from_account,to_account,cents,note.strip()))


_migrate_previous = migrate
def migrate(path=DB_PATH):
    path=Path(path)
    version=0
    if path.exists():
        with closing(open_db(path)) as db, db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version > MAX_SCHEMA_VERSION:
                raise ValueError('Veritabanı daha yeni bir ParaNoya sürümüne ait; güncel uygulamayı kullanın.')
            if version < 4 and db.execute("SELECT 1 FROM sqlite_master WHERE name='accounts'").fetchone():
                stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                with closing(sqlite3.connect(path.with_name(f'{path.stem}.v03_backup_{stamp}{path.suffix}'))) as backup, backup:
                    db.backup(backup)
    if not path.exists() or version < 3:
        _migrate_previous(path)
    from v04_core import upgrade
    db=open_db(path)
    try:
        # Do not lower the full application's schema marker on every startup.
        if version < 4:
            upgrade(db)
        from kmh_core import migrate_kmh
        migrate_kmh(db)
    finally:db.close()
