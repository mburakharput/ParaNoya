"""Local product/warranty inventory. No automatic finance postings."""
from datetime import date, timedelta

def migrate_products(db):
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS products (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           profile_id INTEGER NOT NULL REFERENCES profiles(id),
           name TEXT NOT NULL, brand TEXT NOT NULL DEFAULT '',
           model TEXT NOT NULL DEFAULT '', serial TEXT NOT NULL DEFAULT '',
           seller TEXT NOT NULL DEFAULT '', purchase_date TEXT NOT NULL,
           price_cents INTEGER NOT NULL DEFAULT 0 CHECK(price_cents>=0),
           warranty_end TEXT, notes TEXT NOT NULL DEFAULT '',
           state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','archived')),
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        db.execute('''CREATE TABLE IF NOT EXISTS product_service (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
           service_date TEXT NOT NULL, description TEXT NOT NULL,
           cost_cents INTEGER NOT NULL DEFAULT 0 CHECK(cost_cents>=0))''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_products_profile ON products(profile_id,state)')
        db.execute('''CREATE TABLE IF NOT EXISTS product_attachments (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
           kind TEXT NOT NULL CHECK(kind IN ('invoice','warranty','manual','other')),
           original_name TEXT NOT NULL, stored_name TEXT NOT NULL UNIQUE,
           sha256 TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE(product_id,kind,sha256))''')

def create_product(db, profile_id, name, purchase_date, price_cents=0, warranty_end=None,
                   brand='', model='', serial='', seller='', notes=''):
    if not name.strip() or price_cents < 0: raise ValueError('Ürün adı ve tutar geçerli olmalı.')
    purchased=date.fromisoformat(purchase_date)
    if warranty_end and date.fromisoformat(warranty_end)<purchased:
        raise ValueError('Garanti tarihi alışverişten önce olamaz.')
    with db:
        cur=db.execute('''INSERT INTO products(profile_id,name,brand,model,serial,seller,purchase_date,
           price_cents,warranty_end,notes) VALUES(?,?,?,?,?,?,?,?,?,?)''',
           (profile_id,name.strip(),brand.strip(),model.strip(),serial.strip(),seller.strip(),
            purchase_date,price_cents,warranty_end or None,notes.strip()))
        return cur.lastrowid

def list_products(db, profile_id, include_archived=False):
    return db.execute('''SELECT id,name,brand,model,purchase_date,price_cents,warranty_end,state
        FROM products WHERE profile_id=? AND (? OR state='active') ORDER BY id DESC''',
        (profile_id,int(include_archived))).fetchall()

def change_product(db, profile_id, product_id, *, state):
    if state not in ('active','archived'):raise ValueError('Geçersiz durum')
    with db:
        cur=db.execute('UPDATE products SET state=? WHERE id=? AND profile_id=?',(state,product_id,profile_id))
        if cur.rowcount!=1:raise ValueError('Ürün bulunamadı')

def add_service(db, profile_id, product_id, day, description, cost_cents=0):
    if not description.strip() or cost_cents<0:raise ValueError('Servis bilgisi geçersiz')
    date.fromisoformat(day)
    with db:
        if not db.execute('SELECT 1 FROM products WHERE id=? AND profile_id=?',(product_id,profile_id)).fetchone():
            raise ValueError('Ürün bulunamadı')
        db.execute('INSERT INTO product_service(product_id,service_date,description,cost_cents) VALUES(?,?,?,?)',
                   (product_id,day,description.strip(),cost_cents))

def expiring(db, profile_id, days=30, today=None):
    base=today or date.today()
    return db.execute('''SELECT id,name,warranty_end FROM products
       WHERE profile_id=? AND state='active' AND warranty_end BETWEEN ? AND ? ORDER BY warranty_end''',
       (profile_id,base.isoformat(),(base+timedelta(days=days)).isoformat())).fetchall()


# Attachments are stored under the application's local data folder, not alongside source code.
# Never use an incoming file name as a destination path.
def attach_product_document(db, profile_id, product_id, source, folder, kind='invoice'):
    import hashlib, shutil, uuid
    from pathlib import Path
    if kind not in ('invoice','warranty','manual','other'):
        raise ValueError('Geçersiz belge türü')
    source=Path(source)
    if not source.is_file() or source.is_symlink():
        raise ValueError('Belge dosyası bulunamadı veya desteklenmiyor')
    if source.suffix.lower() not in ('.pdf','.png','.jpg','.jpeg','.webp'):
        raise ValueError('PDF veya görsel seçin')
    if source.stat().st_size > 25*1024*1024:
        raise ValueError('Belge boyutu 25 MB sınırını aşıyor')
    if not db.execute('SELECT 1 FROM products WHERE id=? AND profile_id=?',(product_id,profile_id)).fetchone():
        raise ValueError('Ürün bu profile ait değil')
    digest=hashlib.sha256()
    with source.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    sha=digest.hexdigest()
    if db.execute('SELECT 1 FROM product_attachments WHERE product_id=? AND kind=? AND sha256=?',
                  (product_id,kind,sha)).fetchone():
        raise ValueError('Bu belge zaten aynı ürüne bağlı')
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    stored=uuid.uuid4().hex+source.suffix.lower()
    dest=folder/stored
    shutil.copyfile(source,dest)
    try:
        with db:
            cur=db.execute('''INSERT INTO product_attachments(product_id,kind,original_name,stored_name,sha256)
              VALUES (?,?,?,?,?)''',(product_id,kind,source.name,stored,sha))
            return cur.lastrowid
    except Exception:
        dest.unlink(missing_ok=True)
        raise

def list_product_documents(db,profile_id,product_id):
    return db.execute('''SELECT d.id,d.kind,d.original_name,d.stored_name,d.sha256
      FROM product_attachments d JOIN products p ON p.id=d.product_id
      WHERE p.id=? AND p.profile_id=? ORDER BY d.id DESC''',(product_id,profile_id)).fetchall()

def document_path(db,profile_id,attachment_id,folder):
    from pathlib import Path
    row=db.execute('''SELECT d.stored_name FROM product_attachments d
      JOIN products p ON p.id=d.product_id WHERE d.id=? AND p.profile_id=?''',
      (attachment_id,profile_id)).fetchone()
    if not row: raise ValueError('Belge bulunamadı')
    base=Path(folder).resolve()
    candidate=(base/row[0]).resolve()
    if candidate.parent != base or not candidate.is_file():raise ValueError('Belge dosyası bulunamadı')
    return candidate
