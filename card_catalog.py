"""Offline curated starter catalog. Not a complete/current bank product database."""
import json
from pathlib import Path

# Illustrative candidates; only Garanti Diji verified against issuer during preparation.
SEED = {
 'Garanti BBVA':['Bonus','Bonus Gold','Bonus Platinum','Bonus Diji','Bonus Gold Diji','Bonus Platinum Diji','Miles&Smiles','Shop&Fly'],
 'Türkiye İş Bankası':['Maximum','Maximum Gold','Maximum Platinum','Maximiles','Maximiles Black'],
 'Akbank':['Axess','Axess Platinum','Wings','Free'],
 'Yapı Kredi':['World','World Gold','World Platinum','adios'],
 'Ziraat Bankası':['Bankkart','Bankkart Genç'],
 'VakıfBank':['Worldcard','Worldcard Platinum'],
 'Halkbank':['Paraf','Parafly'],
 'QNB':['CardFinans','CardFinans Platinum'],
 'DenizBank':['Bonus','Bonus Platinum'],
 'TEB':['Bonus','CEPTETEB'],
 'ING':['Bonus'],
 'HSBC':['Advantage'],
 'Enpara Bank':['Enpara Kredi Kartı'],
 'Kuveyt Türk':['Sağlam Kart'],
 'Türkiye Finans':['Happy Kart'],
 'Albaraka Türk':['Worldcard'],
 'Fibabanka':['Fiba Kart'],
 'Ziraat Katılım':['Kart modelini elle belirtin'],
 'Ziraat Dinamik':['Kart modelini elle belirtin'],
 'Burgan Bank':['Kart modelini elle belirtin'],
 'Odeabank':['Bank’O Card'],
 'Şekerbank':['Bonus'],
 'Anadolubank':['Worldcard'],
}
VERIFIED = {('Garanti BBVA','Bonus Platinum Diji'),('Garanti BBVA','Bonus Gold Diji'),('Garanti BBVA','Bonus Diji'),('Garanti BBVA','Bonus Platinum')}
SOURCE = 'https://www.garantibbva.com.tr/kartlar/bonus-diji'

def load_catalog(extra_path=None):
    data = [{'bank':bank,'card':card,'verified':(bank,card) in VERIFIED,
             'source': SOURCE if (bank,card) in VERIFIED else ''}
            for bank,names in SEED.items() for card in names]
    if extra_path and Path(extra_path).exists():
        custom=json.loads(Path(extra_path).read_text(encoding='utf-8'))
        if not isinstance(custom,list): raise ValueError('Katalog JSON listesi bekleniyor.')
        for item in custom:
            if not isinstance(item,dict): raise ValueError('Katalog kaydı nesne olmalı.')
            bank=str(item.get('bank','')).strip();card=str(item.get('card','')).strip()
            if not bank or not card or len(bank)>100 or len(card)>150: raise ValueError('Geçersiz banka/kart.')
            data.append({'bank':bank,'card':card,'verified':False,'source':''})
    by_key={}
    for x in data:by_key[(x['bank'].casefold(),x['card'].casefold())]=x
    return sorted(by_key.values(),key=lambda x:(x['bank'].casefold(),x['card'].casefold()))

def search_catalog(items,query='',bank=''):
    q=query.strip().casefold()
    return [x for x in items if (not bank or x['bank']==bank) and (not q or q in (x['bank']+' '+x['card']).casefold())]
