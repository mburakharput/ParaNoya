from write_transaction import write_transaction
from datetime import date, timedelta
import calendar
from finance_core import money

def upgrade(db):
    with db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS credit_cards (
            id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL REFERENCES profiles(id),
            name TEXT NOT NULL, statement_day INTEGER NOT NULL CHECK(statement_day BETWEEN 1 AND 31),
            due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31),
            credit_limit_cents INTEGER NOT NULL DEFAULT 0 CHECK(credit_limit_cents>=0),
            UNIQUE(profile_id,name));
        CREATE TABLE IF NOT EXISTS card_purchases (
            id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES credit_cards(id),
            category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            total_cents INTEGER NOT NULL CHECK(total_cents>0),
            installments INTEGER NOT NULL CHECK(installments BETWEEN 1 AND 60),
            purchase_date TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS card_installments (
            id INTEGER PRIMARY KEY, purchase_id INTEGER NOT NULL REFERENCES card_purchases(id),
            sequence INTEGER NOT NULL, due_date TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            paid_cents INTEGER NOT NULL DEFAULT 0 CHECK(paid_cents>=0 AND paid_cents<=amount_cents),
            UNIQUE(purchase_id,sequence));
        CREATE TABLE IF NOT EXISTS card_payments (
            id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES credit_cards(id),
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS shared_expense_edits (
            id INTEGER PRIMARY KEY, transaction_id INTEGER NOT NULL REFERENCES transactions(id),
            before_json TEXT NOT NULL, after_json TEXT NOT NULL,
            modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_cardpurchases_card ON card_purchases(card_id);
        ''')
        db.execute('PRAGMA user_version=4')

def cards(db, profile):
    return db.execute('''SELECT c.id,c.name,c.statement_day,c.due_day,c.credit_limit_cents,
      COALESCE((SELECT SUM(p.total_cents) FROM card_purchases p WHERE p.card_id=c.id),0)
      - COALESCE((SELECT SUM(pay.amount_cents) FROM card_payments pay WHERE pay.card_id=c.id),0)
      FROM credit_cards c WHERE c.profile_id=? ORDER BY c.id''',(profile,)).fetchall()

def create_card(db,profile,name,statement_day,due_day,limit_cents):
    if not name.strip() or not 1<=statement_day<=31 or not 1<=due_day<=31 or limit_cents<0:
        raise ValueError('Kart bilgilerini kontrol edin.')
    with db:
        db.execute('INSERT INTO credit_cards(profile_id,name,statement_day,due_day,credit_limit_cents) VALUES (?,?,?,?,?)',(profile,name.strip(),statement_day,due_day,limit_cents))

def month_add(d,n):
    y=d.year+(d.month-1+n)//12; m=(d.month-1+n)%12+1
    return date(y,m,min(d.day,calendar.monthrange(y,m)[1]))

def due_in_month(origin, offset, due_day):
    month = month_add(origin.replace(day=1), offset)
    return month.replace(day=min(due_day, calendar.monthrange(month.year, month.month)[1]))


def first_due(purchase_date,statement_day,due_day):
    # Simple projected schedule: the first payment due date is the first 'due_day' strictly after purchase.
    # Not bank-specific; statements can differ. UI labels it an estimated schedule.
    d=date(purchase_date.year,purchase_date.month,min(due_day,calendar.monthrange(purchase_date.year,purchase_date.month)[1]))
    if d<=purchase_date: d=due_in_month(purchase_date,1,due_day)
    return d

def purchase(db,profile,card_id,category,description,amount,installments,purchased=None):
    with write_transaction(db):
        if amount<=0 or not 1<=installments<=60 or amount<installments or not category.strip():
            raise ValueError('Alışveriş tutarı/taksit/kategori geçersiz.')
        row=db.execute('SELECT statement_day,due_day FROM credit_cards WHERE id=? AND profile_id=?',(card_id,profile)).fetchone()
        if not row: raise ValueError('Kart bu çalışma alanına ait değil.')
        day=date.fromisoformat(purchased) if purchased else date.today()
        first=first_due(day,*row)
        q,r=divmod(amount,installments)
        cursor=db.execute('INSERT INTO card_purchases(card_id,category,description,total_cents,installments,purchase_date) VALUES (?,?,?,?,?,?)',(card_id,category.strip(),description.strip(),amount,installments,day.isoformat()))
        db.executemany('INSERT INTO card_installments(purchase_id,sequence,due_date,amount_cents) VALUES (?,?,?,?)',[(cursor.lastrowid,i+1,due_in_month(first,i,row[1]).isoformat(),q+(1 if i<r else 0)) for i in range(installments)])
        return cursor.lastrowid

def pay_card(db,profile,card_id,account_id,amount):
    with write_transaction(db):
        if amount<=0: raise ValueError('Ödeme pozitif olmalı.')
        row=db.execute('SELECT 1 FROM credit_cards WHERE id=? AND profile_id=?',(card_id,profile)).fetchone()
        acct=db.execute('SELECT 1 FROM accounts WHERE id=? AND profile_id=?',(account_id,profile)).fetchone()
        debt=db.execute('''SELECT COALESCE(SUM(p.total_cents),0)-COALESCE((SELECT SUM(amount_cents) FROM card_payments WHERE card_id=?),0) FROM card_purchases p WHERE p.card_id=?''',(card_id,card_id)).fetchone()[0]
        if not row or not acct or amount>debt:raise ValueError('Hesap, kart veya borç tutarı geçersiz.')
        # Payments reduce card debt and bank/cash balances; NEVER add another expense.
        db.execute('INSERT INTO card_payments(card_id,account_id,amount_cents) VALUES (?,?,?)',(card_id,account_id,amount))
        # allocate payment to oldest unpaid installments, accounting for prior allocations
        remaining=amount
        for iid,total,paid in db.execute('''SELECT i.id,i.amount_cents,i.paid_cents FROM card_installments i JOIN card_purchases p ON p.id=i.purchase_id WHERE p.card_id=? ORDER BY i.due_date,i.id''',(card_id,)).fetchall():
            inc=min(remaining,total-paid)
            if inc:db.execute('UPDATE card_installments SET paid_cents=paid_cents+? WHERE id=?',(inc,iid))
            remaining-=inc
            if not remaining:break

def upcoming(db,profile):
    return db.execute('''SELECT c.name,i.due_date,i.amount_cents-i.paid_cents,p.category,p.description FROM card_installments i JOIN card_purchases p ON p.id=i.purchase_id JOIN credit_cards c ON c.id=p.card_id WHERE c.profile_id=? AND i.paid_cents<i.amount_cents ORDER BY i.due_date,i.id LIMIT 100''',(profile,)).fetchall()

def shared_history(db):
    return db.execute('''SELECT t.id,t.recorded_at,a.name,t.category,t.amount_cents,
      COALESCE((SELECT group_concat(m.name || ': ' || printf('%.2f',s.amount_cents/100.0), ' / ') FROM expense_splits s JOIN family_members m ON m.id=s.member_id WHERE s.transaction_id=t.id),'')
      FROM transactions t JOIN accounts a ON a.id=t.account_id WHERE t.profile_id=2 AND EXISTS(SELECT 1 FROM expense_splits s WHERE s.transaction_id=t.id) ORDER BY t.id DESC''').fetchall()

def edit_shared_split(db,tx_id,allocation):
    import json
    row=db.execute('SELECT amount_cents FROM transactions WHERE id=? AND profile_id=2 AND kind="expense"',(tx_id,)).fetchone()
    previous=dict(db.execute('SELECT member_id,amount_cents FROM expense_splits WHERE transaction_id=?',(tx_id,)).fetchall())
    allowed={r[0] for r in db.execute('SELECT id FROM family_members WHERE active=1')}
    if not row or not previous or not allocation or not set(allocation).issubset(allowed) or any(v<0 for v in allocation.values()) or sum(allocation.values())!=row[0]:
        raise ValueError('Paylaşım geçersiz: payların toplamı gider tutarına eşit olmalı.')
    with db:
        db.execute('DELETE FROM expense_splits WHERE transaction_id=?',(tx_id,))
        db.executemany('INSERT INTO expense_splits(transaction_id,member_id,amount_cents) VALUES (?,?,?)',[(tx_id,k,v) for k,v in allocation.items()])
        db.execute('INSERT INTO shared_expense_edits(transaction_id,before_json,after_json) VALUES (?,?,?)',(tx_id,json.dumps(previous,sort_keys=True),json.dumps(allocation,sort_keys=True)))
