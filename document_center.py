"""Local-only, conservative document intake and user-approved salary posting."""
import csv, hashlib, json, re, sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from document_rows import preview_rows

TYPES={'payslip':'Maaş bordrosu','statement':'Kredi kartı ekstresi','schedule':'Banka ödeme planı','movements':'Hesap hareketleri'}

def migrate_documents(db):
    with db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS imported_documents (
            id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL REFERENCES profiles(id),
            sha256 TEXT NOT NULL, filename TEXT NOT NULL, doc_type TEXT NOT NULL,
            extracted_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_id, sha256));
        CREATE TABLE IF NOT EXISTS document_income_links (
            document_id INTEGER PRIMARY KEY REFERENCES imported_documents(id),
            transaction_id INTEGER NOT NULL UNIQUE REFERENCES transactions(id));
        ''')

def amount_cents(value):
    s = str(value).replace('₺','').replace('TL','').replace(' ','').strip()
    if ',' in s: s=s.replace('.','').replace(',','.')
    elif s.count('.')>1: s=s.replace('.','')
    try: result=Decimal(s)
    except InvalidOperation: raise ValueError('Belgede geçersiz para değeri')
    if result<=0: raise ValueError('Tutar pozitif olmalı')
    return int((result*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def extract(path):
    path=Path(path)
    if path.stat().st_size>15*1024*1024: raise ValueError('Belge 15 MB sınırını aşıyor')
    suffix=path.suffix.lower()
    if suffix=='.pdf':
        try: import fitz
        except ImportError: raise RuntimeError('PDF okumak için: py -m pip install pymupdf')
        with fitz.open(path) as doc:
            if doc.is_encrypted: raise ValueError('Şifreli PDF; önce yerel olarak şifresini çözün')
            return '\n'.join(p.get_text(sort=True) for p in list(doc)[:25])[:200000]
    if suffix in ('.txt','.csv'):
        raw=path.read_bytes()
        for enc in ('utf-8-sig','cp1254','latin-1'):
            try: return raw.decode(enc)[:200000]
            except UnicodeDecodeError: pass
    if suffix=='.xlsx':
        try: from openpyxl import load_workbook
        except ImportError: raise RuntimeError('Excel için: py -m pip install openpyxl')
        wb=load_workbook(path,read_only=True,data_only=True)
        try:
            return '\n'.join(' | '.join(str(v) if v is not None else '' for v in row) for ws in wb.worksheets[:3] for row in ws.iter_rows(min_row=1,max_row=1000,max_col=25,values_only=True))[:200000]
        finally: wb.close()
    if suffix in ('.png','.jpg','.jpeg'):
        raise ValueError('Görsel OCR henüz entegre edilmedi; metin içeren PDF/CSV/Excel kullanın')
    raise ValueError('Desteklenmeyen belge formatı')

def parse(text,typ):
    if typ not in TYPES: raise ValueError('Belge türü geçersiz')
    result={'type':typ,'fields':{},'warnings':[],'sample':text[:1200]}
    patterns={
      'payslip':{'net':r'(?:ödenecek\s+net|net\s+(?:ödenecek|maaş|ücret|tutar)|ele\s+geçen)\s*[:=]?\s*(?:TL\s*)?([\d.,]+)', 'period':r'(?:dönem|maaş\s+ayı)\s*[:=]?\s*(\d{2}[./-]\d{4}|\d{4}[./-]\d{2})'},
      'statement':{'statement_total':r'(?:dönem\s+borcu|ekstre\s+borcu)\s*[:=]?\s*([\d.,]+)','minimum':r'(?:asgari\s+(?:ödeme|tutar))\s*[:=]?\s*([\d.,]+)','due':r'(?:son\s+ödeme\s+tarihi)\s*[:=]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4})'},
      'schedule':{'principal':r'(?:kredi\s+tutarı|anapara)\s*[:=]?\s*([\d.,]+)','total':r'(?:toplam\s+geri\s+ödeme)\s*[:=]?\s*([\d.,]+)'},
      'movements':{}
    }
    for field,pattern in patterns[typ].items():
        m=re.search(pattern,text,flags=re.IGNORECASE)
        if m:
            try: result['fields'][field]=amount_cents(m.group(1)) if field in ('net','statement_total','minimum','principal','total') else m.group(1)
            except ValueError: result['warnings'].append(f'{field} okunamadı')
    if typ in ('statement','schedule','movements'):
        result['candidates'],row_warnings=preview_rows(text,typ)
        result['warnings'].extend(row_warnings)
    if typ=='payslip' and 'net' not in result['fields']:
        result['warnings'].append('Net ödenecek tutar belirlenemedi; elle kontrol edin')
    if typ in ('statement','schedule','movements'):
        result['warnings'].append('Otomatik finans kaydı yapılmaz; bu belge şu anda inceleme kaydıdır')
    return result

def stage(db, profile, path, typ):
    raw=Path(path).read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    parsed=parse(extract(path),typ)
    with db:
        existing=db.execute('SELECT id FROM imported_documents WHERE profile_id=? AND sha256=?',(profile,digest)).fetchone()
        if existing: return existing[0],False,parsed
        cur=db.execute('INSERT INTO imported_documents(profile_id,sha256,filename,doc_type,extracted_json) VALUES(?,?,?,?,?)',(profile,digest,Path(path).name,typ,json.dumps(parsed,ensure_ascii=False)))
        return cur.lastrowid,True,parsed

def list_docs(db,profile):
    return db.execute('SELECT id,filename,doc_type,status,created_at,extracted_json FROM imported_documents WHERE profile_id=? ORDER BY id DESC',(profile,)).fetchall()

def approve_salary(db,profile,doc_id,account_id,net_cents,period,paid):
    if not paid: raise ValueError('Bankaya ödeme doğrulanmadan bakiye oluşturulmaz. Belge incelemede kalacak.')
    if net_cents<=0: raise ValueError('Net gelir tutarı geçersiz')
    with db:
        doc=db.execute('SELECT doc_type,status FROM imported_documents WHERE id=? AND profile_id=?',(doc_id,profile)).fetchone()
        if not doc or doc[0]!='payslip' or doc[1]!='pending': raise ValueError('Bu belge zaten işlendi veya bordro değil')
        if not db.execute('SELECT 1 FROM accounts WHERE id=? AND profile_id=?',(account_id,profile)).fetchone():raise ValueError('Hesap bu profile ait değil')
        cur=db.execute('INSERT INTO transactions(profile_id,account_id,kind,category,description,amount_cents) VALUES(?,?,?,?,?,?)',(profile,account_id,'income','Maaş',f'Bordro: {period}',net_cents))
        db.execute('INSERT INTO document_income_links(document_id,transaction_id) VALUES(?,?)',(doc_id,cur.lastrowid))
        db.execute("UPDATE imported_documents SET status='posted' WHERE id=?",(doc_id,))
        return cur.lastrowid
