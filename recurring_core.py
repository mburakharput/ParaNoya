from write_transaction import write_transaction
"""Offline recurring bills/subscriptions. Money is stored in integer kuruş.
Creating a schedule never posts expense; confirming a paid occurrence posts once.
"""
from datetime import date
import calendar

KINDS=('bill','subscription')
FREQUENCIES=('monthly','quarterly','yearly')

def migrate_recurring(db):
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS recurring_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,profile_id INTEGER NOT NULL REFERENCES profiles(id),
          name TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('bill','subscription')),
          category TEXT NOT NULL,amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
          frequency TEXT NOT NULL CHECK(frequency IN ('monthly','quarterly','yearly')),
          first_due TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)))''')
        db.execute('''CREATE TABLE IF NOT EXISTS recurring_payments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,item_id INTEGER NOT NULL REFERENCES recurring_items(id),
          due_date TEXT NOT NULL,transaction_id INTEGER NOT NULL UNIQUE REFERENCES transactions(id),
          paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(item_id,due_date))''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_recurring_profile ON recurring_items(profile_id,active)')

def next_occurrence(start,frequency,index):
    origin=date.fromisoformat(start)
    months={'monthly':1,'quarterly':3,'yearly':12}[frequency]*index
    total=origin.year*12+origin.month-1+months
    y,m=divmod(total,12);y+=0;m+=1
    return date(y,m,min(origin.day,calendar.monthrange(y,m)[1])).isoformat()

def add_item(db,profile,name,kind,category,amount_cents,frequency,first_due):
    if not name.strip() or kind not in KINDS or frequency not in FREQUENCIES or amount_cents<=0:
        raise ValueError('Geçersiz düzenli ödeme bilgisi')
    date.fromisoformat(first_due)
    with db:
        return db.execute('INSERT INTO recurring_items(profile_id,name,kind,category,amount_cents,frequency,first_due) VALUES (?,?,?,?,?,?,?)',
            (profile,name.strip(),kind,category.strip() or 'Diğer',amount_cents,frequency,first_due)).lastrowid

def upcoming_items(db,profile,today=None,months_ahead=12):
    today=today or date.today()
    rows=db.execute('SELECT id,name,kind,category,amount_cents,frequency,first_due FROM recurring_items WHERE profile_id=? AND active=1',(profile,)).fetchall()
    result=[]
    for item_id,name,kind,cat,amount,freq,first in rows:
        paid_dates={r[0] for r in db.execute('SELECT due_date FROM recurring_payments WHERE item_id=?',(item_id,))}
        origin=date.fromisoformat(first)
        end=date.fromisoformat(next_occurrence(today.replace(day=1).isoformat(),'monthly',months_ahead))
        step={'monthly':1,'quarterly':3,'yearly':12}[freq]
        count=max(0,((end.year-origin.year)*12+end.month-origin.month)//step+1)
        for i in range(count):
            due=next_occurrence(first,freq,i)
            if due > next_occurrence(today.replace(day=1).isoformat(),'monthly',months_ahead):break
            if due not in paid_dates: result.append((item_id,name,kind,due,amount,cat))
    return sorted(result,key=lambda r:(r[3],r[1]))

def pay_occurrence(db,profile,item_id,due_date,account_id):
    with write_transaction(db):
        row=db.execute('SELECT name,category,amount_cents,frequency,first_due,active FROM recurring_items WHERE id=? AND profile_id=?',(item_id,profile)).fetchone()
        if not row or not row[5]:raise ValueError('Etkin ödeme bulunamadı')
        name,category,amount,freq,start,_=row
        if date.fromisoformat(due_date) < date.fromisoformat(start):raise ValueError('Geçersiz vade')
        origin=date.fromisoformat(start);due=date.fromisoformat(due_date)
        months=(due.year-origin.year)*12+due.month-origin.month
        step={'monthly':1,'quarterly':3,'yearly':12}[freq]
        if months % step or next_occurrence(start,freq,months//step)!=due_date:
            raise ValueError('Bu tarih ödeme planında yok')
        if not db.execute('SELECT 1 FROM accounts WHERE id=? AND profile_id=?',(account_id,profile)).fetchone():
            raise ValueError('Seçilen hesap bu profile ait değil')
        if db.execute('SELECT 1 FROM recurring_payments WHERE item_id=? AND due_date=?',(item_id,due_date)).fetchone():
            raise ValueError('Bu dönemin ödemesi zaten kaydedilmiş')
        tx=db.execute('INSERT INTO transactions(profile_id,account_id,kind,category,description,amount_cents) VALUES (?,?,?,?,?,?)',
            (profile,account_id,'expense',category,f'{name} · {due_date}',amount)).lastrowid
        db.execute('INSERT INTO recurring_payments(item_id,due_date,transaction_id) VALUES (?,?,?)',(item_id,due_date,tx))
        return tx

def set_active(db,profile,item_id,active):
    with db:
        cur=db.execute('UPDATE recurring_items SET active=? WHERE id=? AND profile_id=?',(int(bool(active)),item_id,profile))
        if not cur.rowcount:raise ValueError('Kayıt bulunamadı')
