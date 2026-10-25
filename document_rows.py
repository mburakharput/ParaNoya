"""Conservative preview parser. Never modifies finance entries."""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE = re.compile(r'^\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}-\d{2}-\d{2})\s*$')
AMOUNT = re.compile(r'^\s*[-+]?\s*(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?\s*(?:TL|₺)?\s*$')
def cents(raw):
    s=str(raw).strip().replace('TL','').replace('₺','').replace(' ','')
    if not AMOUNT.fullmatch(str(raw)):raise ValueError('Belirsiz tutar')
    return int(Decimal(s.replace('.','').replace(',','.'))*100)
def date_iso(raw):
    raw=raw.strip()
    for fmt in ('%d.%m.%Y','%d/%m/%Y','%d-%m-%Y','%Y-%m-%d'):
        try:return datetime.strptime(raw,fmt).date().isoformat()
        except ValueError:pass
    raise ValueError('Geçersiz tarih')
def preview_rows(text,kind):
    """Only strict pipe/semicolon tabular rows are accepted; rejected rows stay visible as warnings."""
    if kind not in ('statement','schedule','movements'):return [],['Satır ayrıştırma bu belge türü için yok']
    accepted=[];warnings=[]
    for lineno,line in enumerate(text.splitlines(),1):
        if not any(s in line for s in ('|',';','\t')):continue
        sep='|' if '|' in line else ('\t' if '\t' in line else ';')
        cells=[x.strip() for x in line.split(sep)]
        try:
            if kind in ('statement','movements'):
                if len(cells)!=3 or not DATE.fullmatch(cells[0]) or not AMOUNT.fullmatch(cells[2]):continue
                if not cells[1] or len(cells[1])>160:raise ValueError('İşlem açıklaması eksik/uzun')
                accepted.append({'date':date_iso(cells[0]),'description':cells[1],'amount_cents':cents(cells[2]),'source_line':lineno})
            else:
                # Taksit no | vade | anapara | faiz | vergi | toplam
                if len(cells)!=6 or not cells[0].isdigit() or not DATE.fullmatch(cells[1]):continue
                if not all(AMOUNT.fullmatch(x) for x in cells[2:]):raise ValueError('Taksit tutarları belirsiz')
                vals=list(map(cents,cells[2:]))
                if any(v<0 for v in vals) or abs(sum(vals[:3])-vals[3])>1:raise ValueError('Taksit alt kalemleri toplamla uyuşmuyor')
                accepted.append({'installment':int(cells[0]),'date':date_iso(cells[1]),'principal_cents':vals[0],'interest_cents':vals[1],'tax_cents':vals[2],'total_cents':vals[3],'source_line':lineno})
        except (ValueError,InvalidOperation) as exc:warnings.append(f'Satır {lineno}: {exc}')
    if not accepted:warnings.append('Güvenle ayrıştırılabilen satır bulunamadı; belgeyi elle kontrol edin')
    if len(accepted)>1000:raise ValueError('Belge satır sayısı sınırı aşıyor')
    if kind=='schedule' and len({r['installment'] for r in accepted})!=len(accepted):warnings.append('Tekrarlanan taksit numaraları var')
    return accepted,warnings
