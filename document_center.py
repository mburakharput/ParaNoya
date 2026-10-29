"""Local-only, conservative document intake and user-approved salary posting."""
import csv, hashlib, json, re, sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from document_rows import preview_rows

TYPES={'payslip':'Maaş bordrosu','invoice':'Fatura','statement':'Kredi kartı ekstresi','schedule':'Banka ödeme planı','movements':'Hesap hareketleri'}

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
        CREATE TABLE IF NOT EXISTS document_posting_links (
            document_id INTEGER NOT NULL REFERENCES imported_documents(id),
            row_key TEXT NOT NULL,
            transaction_id INTEGER REFERENCES transactions(id),
            purchase_id INTEGER REFERENCES card_purchases(id),
            PRIMARY KEY(document_id,row_key),
            CHECK((transaction_id IS NULL) != (purchase_id IS NULL)));
        ''')

def amount_cents(value):
    s = str(value).replace('₺','').replace('TL','').replace(' ','').strip()
    if ',' in s: s=s.replace('.','').replace(',','.')
    elif s.count('.')>1: s=s.replace('.','')
    try: result=Decimal(s)
    except InvalidOperation: raise ValueError('Belgede geçersiz para değeri')
    if not result.is_finite() or result<=0 or result>Decimal('100000000'):
        raise ValueError('Tutar pozitif ve en fazla 100 milyon TL olmalı')
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
            return '\n'.join(doc[i].get_text(sort=True) for i in range(min(25,len(doc))))[:200000]
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
      'invoice':{'total':r'(?:ödenecek\s+(?:toplam\s+)?tutar|genel\s+toplam|fatura\s+(?:toplamı|tutarı))\s*[:=]?\s*(?:TL\s*)?([\d.,]+)',
                 'invoice_number':r'(?:fatura\s*(?:numarası|no))\s*[:=]?\s*([A-Z0-9][A-Z0-9/-]{2,40})',
                 'issuer':r'(?:satıcı|firma|düzenleyen)\s*[:=]\s*([^\n]{2,100})',
                 'date':r'(?:fatura\s+tarihi)\s*[:=]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4})'},
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
    if typ=='invoice' and 'total' not in result['fields']:
        result['warnings'].append('Fatura toplamı belirlenemedi; tutarı elle doğrulayın')
    if typ in ('statement','movements'):
        result['warnings'].append('Otomatik finans kaydı yapılmaz; yalnız onayladığınız satırlar işlenir. Ödeme/iade/devir satırlarını alışveriş olarak eklemeyin')
    if typ=='schedule':
        result['warnings'].append('Ödeme planı inceleme kaydıdır; otomatik borç oluşturulmaz')
    return result

def stage(db, profile, path, typ):
    path=Path(path)
    with path.open('rb') as handle:
        raw=handle.read(15*1024*1024+1)
    if len(raw)>15*1024*1024:raise ValueError('Belge 15 MB sınırını aşıyor')
    digest=hashlib.sha256(raw).hexdigest()
    parsed=parse(extract(path),typ)
    with db:
        existing=db.execute('SELECT id,extracted_json FROM imported_documents WHERE profile_id=? AND sha256=?',(profile,digest)).fetchone()
        if existing: return existing[0],False,json.loads(existing[1])
        cur=db.execute('INSERT INTO imported_documents(profile_id,sha256,filename,doc_type,extracted_json) VALUES(?,?,?,?,?)',(profile,digest,Path(path).name,typ,json.dumps(parsed,ensure_ascii=False)))
        return cur.lastrowid,True,parsed

def list_docs(db,profile):
    return db.execute('SELECT id,filename,doc_type,status,created_at,extracted_json FROM imported_documents WHERE profile_id=? ORDER BY id DESC',(profile,)).fetchall()

def approve_salary(db,profile,doc_id,account_id,net_cents,period,paid):
    return approve_document_entry(db,profile,doc_id,account_id=account_id,
        cents=net_cents,day=date.today().isoformat(),category='Maaş',
        description='Bordro',confirmed=paid,period=period)[0]


def approve_document_entry(db, profile, doc_id, *, account_id=None, card_id=None,
                           cents, day, category, description, confirmed,
                           source_line=None, period=''):
    """Post one reviewed entry or link an exact existing entry; no guessed totals.

    Statement purchases create card debt, never withdraw cash from a bank account.
    The write lock covers duplicate checks and posting across app processes.
    """
    if not confirmed:raise ValueError('Ödeme / alışveriş doğrulaması gerekli')
    if type(cents) is not int or not 0<cents<=10000000000:
        raise ValueError('Tutar geçersiz')
    if date.fromisoformat(day).isoformat()!=day:raise ValueError('Tarih YYYY-AA-GG biçiminde olmalı')
    if not category.strip() or not description.strip():raise ValueError('Kategori ve açıklama gerekli')
    if db.in_transaction:raise ValueError('Önce bekleyen işlemi tamamlayın')
    with db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT doc_type,status,extracted_json FROM imported_documents WHERE id=? AND profile_id=?',(doc_id,profile)).fetchone()
        if not row or row[0] not in ('payslip','invoice','statement'):
            raise ValueError('Bordro, fatura veya kredi kartı ekstresi seçin')
        typ,status,payload=row
        parsed=json.loads(payload)
        key=str(source_line) if typ=='statement' else 'document'
        if status=='posted' or db.execute('SELECT 1 FROM document_posting_links WHERE document_id=? AND row_key=?',(doc_id,key)).fetchone():
            raise ValueError('Bu belge / satır zaten işlendi')
        purchase_id=tx_id=None;created=True
        if typ=='statement':
            candidate=next((x for x in parsed.get('candidates',[]) if x.get('source_line')==source_line),None)
            if not candidate or candidate['amount_cents']<=0:
                raise ValueError('Pozitif alışveriş satırı seçin; ödeme ve iadeler ayrı işlenmeli')
            if re.search(r'ödeme|iade|devir|devreden|önceki\s+dönem',candidate['description'],re.I):
                raise ValueError('Ödeme, iade ve devreden borç alışveriş olarak aktarılamaz')
            if re.search(r'taksit|installment|\b\d+\s*/\s*\d+\b',candidate['description'],re.I):
                raise ValueError('Ekstre taksitini yeni alışveriş gibi eklemeyin; mevcut taksit planıyla karşılaştırın')
            card=db.execute('SELECT statement_day,due_day FROM credit_cards WHERE id=? AND profile_id=?',(card_id,profile)).fetchone()
            if not card:raise ValueError('Kart bu profile ait değil')
            # A matching date+amount is ambiguous: link only if description also agrees.
            matches=db.execute('SELECT id,description FROM card_purchases WHERE card_id=? AND purchase_date=? AND total_cents=?',(card_id,day,cents)).fetchall()
            exact=[x[0] for x in matches if x[1].strip().casefold()==description.strip().casefold()]
            if matches and len(exact)!=1:raise ValueError('Aynı tarih/tutarda alışveriş var; önce mevcut kayıtla karşılaştırın')
            if exact:purchase_id=exact[0];created=False
            else:
                from v04_core import first_due
                purchase_id=db.execute('INSERT INTO card_purchases(card_id,category,description,total_cents,installments,purchase_date) VALUES(?,?,?,?,1,?)',(card_id,category.strip(),description.strip(),cents,day)).lastrowid
                due=first_due(date.fromisoformat(day),*card).isoformat()
                db.execute('INSERT INTO card_installments(purchase_id,sequence,due_date,amount_cents) VALUES(?,1,?,?)',(purchase_id,due,cents))
        else:
            if not db.execute('SELECT 1 FROM accounts WHERE id=? AND profile_id=?',(account_id,profile)).fetchone():
                raise ValueError('Hesap bu profile ait değil')
            kind='income' if typ=='payslip' else 'expense'
            if typ=='payslip':
                if not period.strip():raise ValueError('Bordro dönemi gerekli')
                description='Bordro: '+period.strip()
            matches=db.execute('SELECT id,description FROM transactions WHERE account_id=? AND kind=? AND amount_cents=? AND substr(recorded_at,1,10)=?',(account_id,kind,cents,day)).fetchall()
            exact=[x[0] for x in matches if x[1].strip().casefold()==description.strip().casefold()]
            if matches and len(exact)!=1:raise ValueError('Aynı gün/tutarda işlem var; önce mevcut kayıtla karşılaştırın')
            if exact:tx_id=exact[0];created=False
            else:
                tx_id=db.execute('INSERT INTO transactions(profile_id,account_id,kind,category,description,amount_cents,recorded_at) VALUES(?,?,?,?,?,?,?)',(profile,account_id,kind,category.strip(),description.strip(),cents,day+' 12:00:00')).lastrowid
        db.execute('INSERT INTO document_posting_links(document_id,row_key,transaction_id,purchase_id) VALUES(?,?,?,?)',(doc_id,key,tx_id,purchase_id))
        if typ=='payslip':
            db.execute('INSERT OR IGNORE INTO document_income_links(document_id,transaction_id) VALUES(?,?)',(doc_id,tx_id))
        expected=len(parsed.get('candidates',[])) if typ=='statement' else 1
        count=db.execute('SELECT COUNT(*) FROM document_posting_links WHERE document_id=?',(doc_id,)).fetchone()[0]
        db.execute('UPDATE imported_documents SET status=? WHERE id=?',('posted' if count>=expected else 'partial',doc_id))
        return (purchase_id if typ=='statement' else tx_id),created
