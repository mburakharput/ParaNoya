"""Safe archive/soft delete metadata. Financial records are never cascaded."""
from datetime import datetime, timezone

KINDS = {'account': 'accounts', 'card': 'credit_cards', 'kmh': 'overdraft_accounts'}

def migrate_record_state(db):
    with db:
        db.execute("""CREATE TABLE IF NOT EXISTS record_states (
            kind TEXT NOT NULL, record_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','archived','trashed')),
            updated_at TEXT NOT NULL,
            PRIMARY KEY(kind,record_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS record_state_audit (
            id INTEGER PRIMARY KEY, kind TEXT NOT NULL, record_id INTEGER NOT NULL,
            previous TEXT NOT NULL, current TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

def get_state(db,kind,record_id):
    if kind not in KINDS: raise ValueError('Bilinmeyen kayıt türü')
    row=db.execute('SELECT status FROM record_states WHERE kind=? AND record_id=?',(kind,record_id)).fetchone()
    return row[0] if row else 'active'

def dependencies(db,kind,record_id):
    if kind=='account':
        checks=[('Gelir/gider','transactions','account_id'),('Gelen transfer','transfers','to_account_id'),('Giden transfer','transfers','from_account_id'),('Kart ödemesi','card_payments','account_id'),('KMH','overdraft_accounts','account_id'),('KMH taksit ödemesi','kmh_payments','from_account_id')]
    elif kind=='card':
        checks=[('Alışveriş','card_purchases','card_id'),('Kart ödemesi','card_payments','card_id')]
    elif kind=='kmh':
        checks=[('KMH hareketi','overdraft_events','overdraft_id'),('Taksitli KMH','kmh_loans','overdraft_id')]
    else: raise ValueError('Bilinmeyen kayıt türü')
    result=[]
    for label,table,column in checks:
        columns={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
        if column not in columns: continue
        count=db.execute(f'SELECT COUNT(*) FROM {table} WHERE {column}=?',(record_id,)).fetchone()[0]
        if count: result.append((label,count))
    return result

def change_state(db,kind,record_id,target):
    if kind not in KINDS or target not in ('active','archived','trashed'):
        raise ValueError('Geçersiz işlem')
    if not db.execute('SELECT 1 FROM '+KINDS[kind]+' WHERE id=?',(record_id,)).fetchone():
        raise ValueError('Kayıt bulunamadı')
    previous=get_state(db,kind,record_id)
    if target=='trashed' and dependencies(db,kind,record_id):
        raise ValueError('Bağlı finans kayıtları var: Sil yerine arşivleyin.')
    if previous==target: return
    with db:
        db.execute('INSERT INTO record_states(kind,record_id,status,updated_at) VALUES(?,?,?,?) ON CONFLICT(kind,record_id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at', (kind,record_id,target,datetime.now(timezone.utc).isoformat()))
        db.execute('INSERT INTO record_state_audit(kind,record_id,previous,current) VALUES(?,?,?,?)',(kind,record_id,previous,target))
