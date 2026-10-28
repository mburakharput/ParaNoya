"""ParaNoya bank logo downloader. Logos belong to their respective owners.

Data source: https://github.com/murattahtaci/turkish-bank-logos-svg
No network call is made merely by importing this module.
"""
from pathlib import Path
from finance_core import DB_DIR
import re
import urllib.request

SOURCE_BASE = 'https://raw.githubusercontent.com/murattahtaci/turkish-bank-logos-svg/main/svg/'
LOGO_IDS = {
 'Garanti BBVA':'garanti', 'Akbank':'akbank', 'Türkiye İş Bankası':'isbank',
 'Yapı Kredi':'yapikredi', 'Ziraat Bankası':'ziraat',
 'Türkiye Cumhuriyeti Ziraat Bankası':'ziraat', 'Ziraat Katılım':'ziraatkatilim',
 'VakıfBank':'vakifbank', 'Türkiye Vakıflar Bankası':'vakifbank',
 'Vakıf Katılım':'vakifkatilim', 'Halkbank':'halkbank',
 'Türkiye Halk Bankası':'halkbank', 'QNB':'qnb', 'DenizBank':'denizbank',
 'TEB':'teb', 'ING':'ing', 'ING Bank':'ing', 'HSBC':'hsbc',
 'Enpara Bank':'enpara', 'Enpara':'enpara', 'Kuveyt Türk':'kuveytturk',
 'Türkiye Finans':'turkiyefinans', 'Türkiye Finans Katılım':'turkiyefinans',
 'Albaraka Türk':'albaraka', 'Fibabanka':'fibabanka',
 'Burgan Bank':'burgan', 'Odeabank':'odeabank', 'Şekerbank':'sekerbank',
 'Anadolubank':'anadolubank', 'Aktif Bank':'aktifbank',
 'Alternatif Bank':'alternatifbank', 'Türkiye Emlak Katılım':'emlakkatilim',
 'Dünya Katılım Bankası':'dunyakatilim', 'ICBC Turkey':'icbc',
 'Citibank':'citibank', 'Hayat Finans':'hayatfinans',
 'Golden Global Yatırım Bankası':'goldenglobal',
 'Tera Bank':'terabank', 'Arap Türk Bankası':'atbank',
 'Ziraat Dinamik':None, 'Turkish Bank':None,
}

def logo_dir(root=None):
    return (Path(root) if root is not None else DB_DIR / 'bank_logos')

def logo_path(bank, root=None):
    slug = LOGO_IDS.get(bank)
    if not slug:
        return None
    path = logo_dir(root) / (slug + '.svg')
    return path if path.is_file() else None

def missing_logos(root=None):
    """Return bank logo IDs missing from the local cache."""
    folder=logo_dir(root)
    return sorted({slug for slug in LOGO_IDS.values() if slug and not (folder/(slug+'.svg')).is_file()})

def fetch_logos(root=None, timeout=12, cancelled=None):
    """Explicitly invoked downloader: return counts and errors; never erase existing files."""
    dest = logo_dir(root)
    dest.mkdir(parents=True, exist_ok=True)
    downloaded, present, failures = 0, 0, []
    for slug in sorted({s for s in LOGO_IDS.values() if s}):
        if cancelled is not None and cancelled():
            break
        path = dest / (slug + '.svg')
        if path.is_file():
            present += 1
            continue
        try:
            req = urllib.request.Request(SOURCE_BASE + slug + '.svg', headers={'User-Agent':'ParaNoya-BankLogoFetcher/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read(800_001)
            if len(data) > 800_000 or not re.search(rb'<svg\b', data[:800], re.I):
                raise ValueError('Geçerli SVG yanıtı alınmadı')
            if re.search(rb'<(?:script|foreignObject)\b|\bon\w+\s*=|(?:href|url)\s*=\s*[\"\']?https?://', data, re.I):
                raise ValueError('Dış bağlantı veya etkin SVG içeriği')
            path.write_bytes(data)
            downloaded += 1
        except Exception as exc:
            failures.append(f'{slug}: {type(exc).__name__}')
    return downloaded, present, failures

if __name__=='__main__':
    n,p,err=fetch_logos()
    print(f'İndirilen: {n}; zaten bulunan: {p}; başarısız: {len(err)}')
    for e in err: print(e)
