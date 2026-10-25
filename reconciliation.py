"""Read-only statement reconciliation. No ledger writes or guessed matches."""
from collections import defaultdict
from datetime import datetime
import json


def statement_reconciliation(db, profile_id, document_id):
    row = db.execute('SELECT doc_type,extracted_json FROM imported_documents WHERE id=? AND profile_id=?', (document_id,profile_id)).fetchone()
    if not row or row[0] not in ('statement','movements'):
        raise ValueError('Geçerli ekstre/hareket belgesi bulunamadı')
    candidates=json.loads(row[1]).get('candidates',[])
    result=[]
    for r in candidates:
        amount=int(r['amount_cents'])
        if amount==0:
            result.append({**r,'status':'review','reason':'Sıfır tutarlı satır'});continue
        # No automatic match merely on amount, especially where dates/account ownership unknown.
        # Show possible transactions of same profile and amount for manual cross-check only.
        possibles=db.execute('''SELECT id,recorded_at,category,description,kind FROM transactions
                 WHERE profile_id=? AND amount_cents=? ORDER BY id DESC LIMIT 20''',(profile_id,abs(amount))).fetchall()
        result.append({**r,'status':'review', 'possible_matches':[{'id':x[0],'date':x[1],'category':x[2],'description':x[3],'kind':x[4]} for x in possibles],
                       'reason':'Tutar benzerliği kesin eşleşme değildir; kullanıcı doğrulamalı'})
    return result


def validate_schedule_preview(db,profile_id,document_id):
    row=db.execute('SELECT doc_type,extracted_json FROM imported_documents WHERE id=? AND profile_id=?',(document_id,profile_id)).fetchone()
    if not row or row[0]!='schedule': raise ValueError('Ödeme planı bulunamadı')
    data=json.loads(row[1]);candidates=data.get('candidates',[])
    errors=list(data.get('warnings',[]))
    nums=[x['installment'] for x in candidates]
    if len(nums)!=len(set(nums)):errors.append('Mükerrer taksit numaraları')
    if nums and sorted(nums)!=list(range(min(nums),max(nums)+1)):errors.append('Eksik taksit numaraları')
    if any(x['total_cents']<0 for x in candidates):errors.append('Negatif taksit')
    return {'rows':candidates,'errors':errors,'requires_approval':True,'posted':False}
