from write_transaction import write_transaction
"""Overdraft / installment KMH; all amounts integer kuruş; no fictional interest assumptions."""
import calendar
from datetime import date, timedelta
from v04_core import month_add


def closing_due(closing_date, lag=10):
    if lag < 10: raise ValueError('Son ödeme günü en az 10 takvim günü sonra olmalı.')
    return date.fromisoformat(closing_date) + timedelta(days=lag)


def migrate_kmh(db):
    with db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS overdraft_accounts (
          id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL UNIQUE REFERENCES accounts(id),
          limit_cents INTEGER NOT NULL CHECK(limit_cents>=0),
          annual_rate_bp INTEGER NOT NULL DEFAULT 0 CHECK(annual_rate_bp>=0));
        CREATE TABLE IF NOT EXISTS overdraft_events (
          id INTEGER PRIMARY KEY, overdraft_id INTEGER NOT NULL REFERENCES overdraft_accounts(id),
          kind TEXT NOT NULL CHECK(kind IN ('draw','repay','interest','fee')),
          amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
          recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          note TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS kmh_loans (
          id INTEGER PRIMARY KEY, overdraft_id INTEGER NOT NULL REFERENCES overdraft_accounts(id),
          principal_cents INTEGER NOT NULL CHECK(principal_cents>0),
          description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS kmh_installments (
          id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES kmh_loans(id),
          sequence INTEGER NOT NULL, due_date TEXT NOT NULL,
          principal_cents INTEGER NOT NULL CHECK(principal_cents>=0),
          interest_cents INTEGER NOT NULL CHECK(interest_cents>=0),
          tax_cents INTEGER NOT NULL CHECK(tax_cents>=0),
          fee_cents INTEGER NOT NULL CHECK(fee_cents>=0),
          paid_cents INTEGER NOT NULL DEFAULT 0 CHECK(paid_cents>=0),
          UNIQUE(loan_id,sequence));
        CREATE TABLE IF NOT EXISTS kmh_payments (
          id INTEGER PRIMARY KEY, installment_id INTEGER NOT NULL REFERENCES kmh_installments(id),
          from_account_id INTEGER NOT NULL REFERENCES accounts(id),
          amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
          paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        ''')


def overdraft(db, profile):
    return db.execute('''SELECT od.id,a.id,a.name,od.limit_cents,
      COALESCE(SUM(CASE WHEN e.kind='draw' THEN e.amount_cents
           WHEN e.kind='repay' THEN -e.amount_cents ELSE 0 END),0)
      FROM overdraft_accounts od JOIN accounts a ON a.id=od.account_id
      LEFT JOIN overdraft_events e ON e.overdraft_id=od.id
      WHERE a.profile_id=? GROUP BY od.id ORDER BY a.name''',(profile,)).fetchall()


def set_overdraft(db, profile, account_id, limit_cents):
    with write_transaction(db):
        if limit_cents < 0: raise ValueError('Limit negatif olamaz.')
        row=db.execute('SELECT kind FROM accounts WHERE id=? AND profile_id=?',(account_id,profile)).fetchone()
        if row != ('bank',):raise ValueError('KMH yalnızca seçili çalışma alanının banka hesabına bağlanır.')
        existing=db.execute('SELECT id FROM overdraft_accounts WHERE account_id=?',(account_id,)).fetchone()
        if existing:
            used=db.execute('SELECT COALESCE(SUM(CASE kind WHEN "draw" THEN amount_cents WHEN "repay" THEN -amount_cents ELSE 0 END),0) FROM overdraft_events WHERE overdraft_id=?',(existing[0],)).fetchone()[0]
            if limit_cents < used:raise ValueError('Limit kullanılan tutarın altına indirilemez.')
            db.execute('UPDATE overdraft_accounts SET limit_cents=? WHERE id=?',(limit_cents,existing[0]))
            return existing[0]
        return db.execute('INSERT INTO overdraft_accounts(account_id,limit_cents) VALUES(?,?)',(account_id,limit_cents)).lastrowid


def use_overdraft(db, profile, od_id, amount_cents, kind, note=''):
    with write_transaction(db):
        if amount_cents<=0 or kind not in ('draw','repay'):raise ValueError('İşlem türü veya tutarı geçersiz.')
        row=db.execute('''SELECT od.limit_cents,a.profile_id FROM overdraft_accounts od JOIN accounts a ON a.id=od.account_id WHERE od.id=?''',(od_id,)).fetchone()
        if not row or row[1]!=profile:raise ValueError('KMH bu profile ait değil.')
        used=db.execute('SELECT COALESCE(SUM(CASE kind WHEN "draw" THEN amount_cents WHEN "repay" THEN -amount_cents ELSE 0 END),0) FROM overdraft_events WHERE overdraft_id=?',(od_id,)).fetchone()[0]
        if kind=='draw' and used+amount_cents>row[0]:raise ValueError('KMH limiti aşılıyor.')
        if kind=='repay' and amount_cents>used:raise ValueError('KMH borcundan fazla kapatılamaz.')
        db.execute('INSERT INTO overdraft_events(overdraft_id,kind,amount_cents,note) VALUES(?,?,?,?)',(od_id,kind,amount_cents,note))


def add_installment_loan(db, profile, od_id, principal_cents, schedule, description=''):
    """schedule: [(ISO due date, principal cents, interest cents, tax cents, fee cents)] from bank statement.
    Cash receipt on bank account, and an equal loan liability, not income.
    Each loan is separate from revolving KMH utilization.
    """
    if principal_cents<=0 or not schedule or len(schedule)>120:raise ValueError('Kredi veya plan geçersiz.')
    row=db.execute('SELECT a.id FROM overdraft_accounts od JOIN accounts a ON a.id=od.account_id WHERE od.id=? AND a.profile_id=?',(od_id,profile)).fetchone()
    if not row: raise ValueError('KMH hesabı bulunamadı.')
    if sum(x[1] for x in schedule)!=principal_cents:raise ValueError('Taksit anaparalarının toplamı kredi anaparasına eşit olmalı.')
    if any(len(x)!=5 or any(v<0 for v in x[1:]) for x in schedule):raise ValueError('Negatif ödeme kalemi olamaz.')
    dates=[date.fromisoformat(x[0]) for x in schedule]
    if dates != sorted(set(dates)):raise ValueError('Taksit tarihleri tekil ve artan olmalı.')
    with db:
        loan=db.execute('INSERT INTO kmh_loans(overdraft_id,principal_cents,description) VALUES(?,?,?)',(od_id,principal_cents,description)).lastrowid
        db.executemany('''INSERT INTO kmh_installments(loan_id,sequence,due_date,principal_cents,interest_cents,tax_cents,fee_cents)
          VALUES(?,?,?,?,?,?,?)''',[(loan,i+1,*line) for i,line in enumerate(schedule)])
    return loan


def monthly_calendar(db,profile):
    return db.execute('''SELECT i.id,a.name,i.due_date,i.principal_cents+i.interest_cents+i.tax_cents+i.fee_cents-i.paid_cents,
      l.description FROM kmh_installments i JOIN kmh_loans l ON l.id=i.loan_id
      JOIN overdraft_accounts od ON od.id=l.overdraft_id JOIN accounts a ON a.id=od.account_id
      WHERE a.profile_id=? AND i.paid_cents<i.principal_cents+i.interest_cents+i.tax_cents+i.fee_cents
      ORDER BY i.due_date,i.id''',(profile,)).fetchall()


def pay_installment(db,profile,installment_id,from_account_id,cents):
    with write_transaction(db):
        if cents<=0:raise ValueError('Tutar pozitif olmalı.')
        row=db.execute('''SELECT i.principal_cents+i.interest_cents+i.tax_cents+i.fee_cents-i.paid_cents,a.profile_id
          FROM kmh_installments i JOIN kmh_loans l ON l.id=i.loan_id JOIN overdraft_accounts od ON od.id=l.overdraft_id
          JOIN accounts a ON a.id=od.account_id WHERE i.id=?''',(installment_id,)).fetchone()
        payer=db.execute('SELECT profile_id FROM accounts WHERE id=?',(from_account_id,)).fetchone()
        if not row or row[1]!=profile or payer!=(profile,) or cents>row[0]:raise ValueError('Ödeme hesabı veya tutar geçersiz.')
        db.execute('INSERT INTO kmh_payments(installment_id,from_account_id,amount_cents) VALUES(?,?,?)',(installment_id,from_account_id,cents))
        db.execute('UPDATE kmh_installments SET paid_cents=paid_cents+? WHERE id=?',(cents,installment_id))
