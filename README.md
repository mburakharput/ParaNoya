# ParaNoya v1.2.5.6

## 1.2.5.6 — güvenli uygulama içi güncelleme

Kurulum sihirbazı Türkçedir. İlk geçişte yeni kurulum bir kez elle yapılır;
sonraki sürümler **Güncellemeleri denetle** üzerinden indirilip açık onayla kurulabilir.
İmzalı güncellemelerin tek merkezi `mburakharput/uygulama-guncellemeleri`,
etiket biçimi `ParaNoya-vSÜRÜM` şeklindedir. Başka uygulamaların yayınları yok sayılır.
Yayıncı Ed25519 imzası, sürüm, dosya adı, boyut ve SHA-256 yeniden denetlenir;
imzasız veya eski kurulumlar çalıştırılmaz. Kurulumdan önce SQLite ve ürün ekleri
`%LOCALAPPDATA%\ParaNoya\UpdateBackups` altında doğrulanmış ZIP olarak yedeklenir.
Yedek veya hazırlık başarısızsa uygulama açık kalır. Yardımcı işlem, ParaNoya'nın
doğru Windows işleminin kapanmasını bekledikten sonra görünür kurulumu başlatır.

Geliştirme ortamından/portable kopyadan otomatik kurulum yapılmaz; mevcut
`%LOCALAPPDATA%\Programs\ParaNoya` kullanıcı kurulumu ve kaldırma kaydı gereklidir.
İndirme sırasında kapanış istenirse iş iptal edilir; çalışan Qt iş parçacığı yok edilmez.
İnternet hatası veya geçersiz imza finans kayıtlarını değiştirmez.

### Yayıncı için yerel imzalama ve merkezi yayın

Özel anahtar yalnız yayıncının bilgisayarında kalır; GitHub'a yüklenmez ve CI
tarafından okunmaz. `release_tools/Publish-ParaNoya.ps1`, kullanıcı tarafından
çalıştırıldığında başarılı CI paketini indirir, kaynağını ve beklenen özetini
kontrol eder, masaüstündeki anahtarı seçtirir ve yerel imzalama yapar. Ardından
EXE, manifest, imza, SHA256SUMS, doğrulama raporu ve kaynak bilgilerini merkezi
depoya taslak olarak yükler. Tüm dosya özetleri eşleşince yayın açılır.
GitHub oturumu Git Credential Manager üzerinden alınır; erişim bilgileri yazdırılmaz.
Çalıştırma komutundaki BuildRunId, SourceCommit ve InstallerSha256 değerleri ilgili
başarılı CI koşusundan alınmalıdır. Bu betiği asistan özel anahtara karşı çalıştırmaz.


Windows x64 merkezi yayınları: https://github.com/mburakharput/uygulama-guncellemeleri/releases

Bu sürüm: daha dar banka listesi ve 32px satırlar; logo ile banka adı arasında sabit boşluk; Enpara symbol/use ve Şekerbank clipPath çizim düzeltmesi; hesap, kart, KMH, ödeme ve transfer seçimlerinde ortak logo çizimi; tüm seçim kutularında ve tarih açılır alanlarında uyumlu ok. ParaNoya baykuşu uygulama ve Setup EXE ikonuna gömülüdür. Banka logolarının indirme davranışı korunur. Kişisel veri paketlenmez.

# ParaNoya — Birleşik geliştirme sürümü v1.2.2

**Slogan:** Paranın peşini bırakma!  
**Platform:** Windows, Python 3 ve PySide6.  
**Durum:** Önizleme / geliştirme sürümü. Gerçek hassas finans verileri için güvenlik ve uçtan uca Windows testleri henüz tamamlanmadı.

## Başlangıç (Windows)

1. Çalışan eski ParaNoya / Aile Finans pencerelerini kapatın.
2. **Önce** `%USERPROFILE%\AileFinans` veri klasörünü ayrı bir yere yedekleyin; özellikle `ailefinans.db` dosyasını silmeyin.
3. Bu klasörde Dosya Gezgini adres çubuğuna `cmd` yazıp Enter'a basın.
4. Bağımlılıkları yükleyin: `py -m pip install -r requirements.txt`
5. Uygulamayı çalıştırın: `py ailefinans.py`

Ana başlangıç dosyasının adı geçmişle uyumluluk için hâlâ **`ailefinans.py`**. Bu dosyayı sırf isim değişikliği için yeniden adlandırmayın.

## Veriler nerededir?

Program önceki sürümlerle aynı konumu kullanır: `%USERPROFILE%\AileFinans\ailefinans.db`. Bu dağıtımda **kullanıcı veritabanı yoktur**; var olan veriler paket temizliği sırasında değiştirilmemiştir. Yeni bir sürümle açmadan önce ayrıca yedek almak önemlidir. Sadece ZIP içindeki kod ve belgeler temizlenmiştir; kullanıcının bilgisayarındaki eski sürüm klasörlerine dokunulmamıştır.

## Bugüne kadar birleştirilen işlevler

- ParaNoya markası, baykuş simgesi, açık/koyu tema, gruplanmış sol menü.
- Ana panel: gelir/gider ve hesap özetleri, kategorik ve aylık grafikler, son işlemler.
- Profil alanları: kişisel/aile, gelir-gider, nakit ve banka hesapları, transferler.
- Aile üyeleri, ortak gider ve paylaştırma; paylaşım düzeltme.
- Kredi kartı ekleme, borç, taksit, ödeme; banka/kart kataloğu başlangıç listesi; Visa/Mastercard/TROY alanı.
- Kart son ödeme günü için kesim tarihinden 10 gün sonrası *önerisi* (bankanın gerçek vadesi farklı olabilir).
- KMH limitleri, kullanım, ödeme, taksitli KMH ve aylık ödemeler.
- Kart, hesap ve KMH listelerinde seçimle düzenleme/arşivleme/geri alınabilir silme işlemleri (bağlı kayıt korumasıyla).
- Akıllı Belge Merkezi önizlemesi: PDF/Excel/CSV/TXT içe alma; temel bordro net tutar önerisi ve onayla gelir kaydı; ekstre/ödeme planı belgelerini incelemeye alma.
- Yeni banka hesabı eklerken banka seçimi, banka adını kendin girme alternatifi.

## Bilinen sınırlar

- Tüm banka ve kredi kartları kapsanmış **değildir**; katalog başlangıç düzeyindedir. Banka logosu dosyaları paketlenmemiştir, varsayılan metin simgesi kullanılır. Uygun logolar `assets/bank_logos/` altına konabilir; üçüncü taraf marka haklarına dikkat edin.
- Belgelerde tam bankaya özgü ekstre satırı ayrıştırma, KMH ödeme planını otomatik mutabakatla uygulama ve OCR henüz yoktur; yanlış okuma riski vardır.
- Otomatik KMH faiz/BSMV/KKDF tahakkuku, banka takvimleri, erken ödeme planı yeniden hesaplama eksiktir.
- Profiller **güvenli şifreli oturum** değildir; veritabanı uçtan uca şifreli değildir.
- Bazı uyarı pencereleri ayrı açılabilir. Referans tasarımının piksel piksel kopyası değildir.
- Bakiye, finans ve belge işleme açısından kod testleri vardır; Windows GUI için uçtan uca test yapılmamıştır. Test verisi kullanın.
- Abonelikler, faturalar ve garanti yönetimi eksiksiz çalışan modüller hâlinde henüz tamamlanmamıştır.

## Test

`py -m unittest discover -p "test*.py" -v`

Özel GUI testi Windows'ta yapılmalıdır. Paket testleri gerçek veritabanına dokunmamalıdır.

## Proje içeriği

| Dosya / klasör | Amaç |
|---|---|
| `ailefinans.py` | PySide6 masaüstü arayüzü ve uygulama girişi |
| `finance_core.py` | Hesap, işlem, profil, aile ve şema geçişleri |
| `v04_core.py` | Kredi kartı ve taksit çekirdeği |
| `kmh_core.py` | KMH ve taksitli KMH işlemleri |
| `document_center.py` | Belge alma ve inceleme çekirdeği |
| `record_manager.py` | Düzenleme/arşivleme/güvenli silme katmanı |
| `card_catalog.py` | Başlangıç banka ve kart listesi |
| `assets/paranoya_mascot.png` | Kullanılan baykuş görseli |
| `test_*.py` | Otomatik testler |
| `requirements.txt` | Python bağımlılıkları |

## Banka logoları

`assets/bank_logos/` klasörüne bankanın katalog anahtarına uygun PNG/SVG logolar eklenebilir. Örnekler: `fibabanka.png`, `ziraat_katılım.png`, `ziraat_dinamik.png`, `odeabank.png`, `burgan_bank.png`. Dosya yoksa arayüz baş harf/simge gösterebilir. Bu ZIP gerçek banka logolarının eksiksiz koleksiyonunu içermez.

## Temizleme notu

Bu paket en güncel **v1.1.4** kaynaklarını temel alır. Önceki sürümlerin farklı `BENI_OKU*`, `SURUM_NOTU*`, düzeltme/test notları tek README'de birleştirildi ve eski ayrı dosyalar paketten kaldırıldı. Geriye dönük test kodları *gereksiz dosya sanılıp silinmedi*. Geçmiş kaynak sürümleri kullanıcının bilgisayarından otomatik olarak kaldırılmaz.


## v1.1.5 — Hesap ve KMH ayrıntı panelleri

- Banka hesabı seçildiğinde bakiye ve varsa bağlı KMH limiti/kullanımı gösterilir.
- KMH satırı seçildiğinde normal KMH limit/kullanımı ve kalan taksitli borç görünür.
- Aylık Ödemeler ekranında bu ay, geciken ve toplam bekleyen taksit tutarları ile filtreler bulunur.
- Ödeme planlarında taksitlerin tarih ve tutarları mevcut kayıt sisteminden gelir; banka ekstresiyle mutabakat yine gereklidir.
- Bu paket yeni tablo oluşturmaz, var olan kullanıcı verilerini silmez. Eski veri klasörü yedeklenmelidir.
- Grafik arayüzü Windows üzerinde henüz doğrulanmadığından geliştirme önizlemesidir.

## v1.1.6 — Faturalar ve Abonelikler (geliştirme önizlemesi)

- Sol menüde **Faturalar / Abonelikler** açılır. Aynı sayfada ad, tür, tutar, kategori, ilk vade ve aylık/üç aylık/yıllık dönem seçilir.
- Düzenli ödeme oluşturulması **gelir/gider ya da hesap bakiyesi değiştirmez**. Beklenen ödemeler listelenir.
- Seçilen dönem ödenirken mevcut profildeki bir hesap seçilir; onay sonrasında gider kaydı yalnızca bir kere oluşur. Aynı dönem ikinci defa ödenemez.
- Durdurulan düzenli ödeme gelecek takvimden çıkar; geçmiş finans işlemi korunur.
- KMH **Aylık Ödemeler** sayfasında ayrıca fatura ve abonelik yenileme tarihleri listelenir.
- Tarih hesapları ayın 31'i gibi günlerde kısa ayların son gününe uyarlanır.

**Sınırlamalar:** Gerçek Windows/PySide6 kullanıcı arayüzü burada açılarak doğrulanmadı. Ödeme yöntemi seçimi mevcut uygulamanın iletişim akışını kullanır; tüm formların tamamen içerik alanına taşınması henüz bitmedi. Bankadan otomatik tahsilat yapılmaz; abonelik tutar değişikliği, banka entegrasyonu, ödeme erteleme ve gerçek fatura PDF eşleştirmesi sonraki aşamalardadır. Güvenli çok kullanıcılı oturum özelliği hâlâ yoktur. Gerçek finans bilgileriyle kullanmadan önce uçtan uca doğrulama gerekir.


## v1.1.7 — Pencereye uyumlu sol menü
Sol menü dar ekranlarda dikey kaydırılır; logo ve çalışma alanı seçimi yukarıda, ParaNoya etiketi ve tema düğmesi altta sabit kalır. Menü öğeleri küçültülerek üst üste bindirilmez. Ana pencerenin asgari boyutu 920 × 600 olarak değiştirildi. Koyu ve açık tema desteklenir. Bu değişiklik finans kayıtlarını veya SQLite şemasını değiştirmez.

## v1.1.8 — Türkçe, uyumlu kayıt düzenleme ekranı
- Hesap, kredi kartı ve KMH düzenleme ekranlarındaki teknik veritabanı alan adları Türkçe etiketlerle değiştirildi.
- Kart ve KMH limitleri kuruş cinsinden ham sayı yerine iki ondalıklı **TL** olarak görüntülenir, kaydederken kuruşa doğru çevrilir.
- Hesap kesim / son ödeme günleri 1–31 aralıklı sayısal kontrollerle girilir.
- Kaydet ve İptal düğmeleri Türkçeleştirildi, form küçük ekranlarda kaydırılabilir oldu.
- SQLite şeması ve mevcut kayıtlar değiştirilmedi. Windows GUI görsel testi henüz yapılmadı.

## v1.1.9 — Ürün ve Garanti Merkezi (25 Ekim 2026)

- Sol menüden **Ürünler / Garantiler** açılır.
- Ürün adı, marka, model, satıcı, alış tarihi, fiyat ve isteğe bağlı garanti bitişi kaydedilir.
- Tablodan seçili ürün arşivlenebilir ve geri yüklenebilir; servis/bakım notu ve maliyeti kaydedilebilir.
- Önümüzdeki 30 günde garanti süresi bitecek aktif ürünlerin sayısı gösterilir.
- Ürün kaydetmek banka hesabından otomatik para düşmez; alışverişin mevcut gelir-gider kaydıyla iki kez sayılmasını önlemek için bu bilinçli bir kısıtlamadır.
- Her iki profilin ürün kayıtları ayrı listelenir. Ancak profil seçimi henüz gerçek kimlik doğrulama değildir.
- Yeni veritabanı tabloları: `products`, `product_service`. Mevcut veritabanı verileri silinmez.
- Test: `py -m unittest discover -p "test_*.py" -q` (29 test, geliştirme ortamında başarılı).

### Geliştirme durumu ve sınırlar

Bu sürüm **Windows grafik arayüzünde uçtan uca test edilmemiş bir önizlemedir**. Gerçek finans verilerini aktarmadan önce `%USERPROFILE%\AileFinans` klasörünün yedeğini alın. Belgeleri tüm banka ekstrelerinden satır satır okuyup ödeme planlarına aktarabilme, ürün faturasını OCR ile ürün/işlem kaydına bağlama, resmî banka logo seti, tüm formların tamamen modal olmayan hâle getirilmesi, gerçek kullanıcı yetkileri ve kapsamlı Windows kabul testleri henüz tamamlanmadı. Mevcut kayıtları silerek temizleme yapmayın.


## v1.2.0 — Ürün belgeleri
Ürün ve Garantiler ekranında ürün seçip **Belge bağla** ile PDF veya görsel biçiminde fatura, garanti belgesi ve kullanım kılavuzu eklenebilir. Dosyalar `%USERPROFILE%\AileFinans\product_documents` klasörüne **kopyalanır**. **Belgeleri görüntüle** üzerinden yeniden açılır. Aynı belge aynı ürüne aynı türle ikinci kez bağlanamaz. 25 MB dosya sınırı vardır. Belgeler şifrelenmemiş yerel dosyalardır; hassas belgeler için kullanıcı hesap erişimlerini koruyun. Bu aşamada OCR ve ürün harcama kaydı eşleştirmesi yoktur. Veri yedeği alırken `ailefinans.db` yanında `product_documents` klasörünü de yedekleyin.

## v1.2.1 — Belge satırı önizleme

- Kredi kartı ekstresi ve hesap hareketlerinden **yalnızca açıkça ayrılmış** `Tarih | Açıklama | Tutar` satırları aday olarak çıkarılır.
- KMH ödeme planlarında `Taksit no | Tarih | Anapara | Faiz | Vergi | Toplam` biçimindeki satırlar için toplam kontrolü yapılır.
- Belgeler sayfasındaki **Seçili belgedeki öneri satırlarını göster** düğmesi aday kayıtları listeler. Hiçbir aday otomatik olarak gelir/gider, kart borcu veya taksit tablosuna işlenmez.
- Farklı banka PDF yerleşimleri, OCR, gerçek ekstre mutabakatı ve onaylı toplu muhasebeleştirme henüz desteklenmiyor.
- Sadece belge dosyası hash'ine göre tekrar yükleme denetimi vardır; farklı dosyalarda aynı banka işlemi için ayrı mutabakat henüz yoktur.


## v1.2.2 — Güvenli mutabakat ve doğrulanmış yedek

- `reconciliation.py` kredi kartı ekstresi ve hesap hareketi adaylarını mevcut profil işlemleriyle **salt okunur** karşılaştırır. Tutarı eşit olan kayıtları sadece *olası eşleşme* olarak sunar. Aynı tutardan hareketle otomatik finans kaydı **yapmaz**.
- Banka ödeme planı önizlemesinde mükerrer/eksik taksit numaraları denetlenebilir. Bu kontrol gerçek banka planını otomatik güncellemez.
- `yedekle.py` çalışan uygulamanın kapatılmasından sonra `py yedekle.py` ile çalıştırılabilir. SQLite yedekleme API'siyle tutarlı veritabanı kopyası, ürün belgeleri ve SHA-256 manifesti içeren ZIP üretir; ardından yedeği doğrular. Dosya varsayılan olarak `Belgeler/ParaNoya_Yedekleri` klasörüne kaydedilir. **Bu ZIP bir proje kaynak paketi değildir; kişisel veri içerdiği için gizli tutulmalıdır.**
- `test_reconciliation_backup.py` salt okunur eşleştirme, profil ayrımı, taksit uyarısı ve yedek bütünlüğü kontrollerini kapsar.
- Bu yenilikler servis düzeyinde hazırlanmıştır. Mutabakat kontrolünün tüm sonuçlarını onaylı finans kaydına dönüştüren arayüz **henüz mevcut değildir**. Banka bazlı PDF/OCR şablonlarının tamamı, gerçek banka logoları, güvenli çok kullanıcılı oturumlar, uçtan uca Windows testi ve muhasebe mutabakatı **tamamlanmadı**. Bu yüzden bu paket nihai ürün değildir.
- Geri yükleme otomatik değildir; özgün veri üzerine yazmadan önce veri dosyalarının ayrı bir klasöre doğrulanarak çıkarılması ve manuel değerlendirilmesi gerekir.

## Banka logoları — v1.2.3

Yeni **Banka logolarını indir** düğmesi, internet bağlantınız varsa GitHub'daki
`murattahtaci/turkish-bank-logos-svg` koleksiyonundan SVG'leri indirir. İndirme
arka planda yapılır. Başarılı olduktan sonra ParaNoya'yı yeniden başlatın.
İndirilen logolar `assets/bank_logos/` altında kalır ve sonraki açılışlarda
çevrimdışı çalışır. Dilerseniz `py bank_logo_manager.py` komutunu kullanın.

* Logoların mülkiyeti ilgili banka/kurumlara aittir. Logo koleksiyonunun
  dosya bazlı lisans/kaynak listesini kontrol edin:
  https://github.com/murattahtaci/turkish-bank-logos-svg
* Resmî logo kaynaklarının bir bölümü üçüncü taraf web sitelerinden alınmıştır;
  ParaNoya bankalarla bağlantılı veya bankalar tarafından onaylanmış değildir.
* Ziraat Dinamik gibi koleksiyonda bulunmayan bankalarda mevcut baş harf simgesi görünür.
* İndirilmeyen SVG'ler paket içinde yoktur; yeni bilgisayarda tek seferlik internet
  gereklidir. Logosuz çevrimdışı çalışma devam eder.
* SVG'ler yalnız izin verilen adlarla indirilir ve temel güvenlik doğrulamasından geçer.
* Finansal bilgiler veya kullanıcı veritabanı bu işlem sırasında gönderilmez.


## v1.2.4 — Banka logoları
- Sol menüdeki manuel indirme düğmesi kaldırıldı.
- İlk açılışta eksik logolar arka planda indirilir; sonraki açılışlarda sadece eksikler denenir.
- İlerleme metni işlem bitince kaybolur; bağlantı hataları durum çubuğuna yazılır.
- Üst çubuktaki Ayarlar / Banka Logolarını Güncelle ile elle denetlenebilir.
- Karta, hesaba ve KMH’ye ait ayrıntı panelleri eşleşen banka logosunu gösterir.
- Banka adı bulunmayan eski hesaplarda logo yerine normal başlık gösterilir.
- Banka logoları üçüncü taraf marka varlıklarıdır, yeniden dağıtım için ayrı kullanım hakkı kontrolü gerekir.


## v1.2.5 banka seçim arayüzü
- Yeni hesap formunda banka alanının tamamına tıklayınca banka listesi açılır.
- Banka alanında yazılan metne göre arama/otomatik tamamlama çalışır.
- Liste 7 satır yüksekliğinde kaydırılabilir; logolar 88x28 piksel alanında oranı bozulmadan ölçeklenir.
- Açılır menü okları modern turkuaz çizgi SVG görseliyle değiştirildi.
- Eksik veya görünmeyen banka logosu yerine banka adı her zaman kalır.
- Finans veritabanı şemasında ve mevcut kayıtlarda değişiklik yoktur.
- Windows üzerinde PySide6 görsel testi bu çalışma ortamında yapılmadı.


## v1.2.5.1 — Kompakt banka seçim düzeltmesi
- Banka listesi en fazla 5 satır yüksekliğinde açılır.
- Banka logoları 74×28 şeffaf tuval içinde 60×20 sınırlarına en-boy oranı korunarak ortalanır.
- Popup genişliği form alanına göre sınırlanır, arama ve doğrudan açılma davranışı korunur.


## v1.2.5.2 — Net banka logoları
- SVG banka işaretleri 3× çözünürlükte yeniden çizilir (yüksek DPI desteği).
- Açılır listede logonun 122×32 alanda oranı korunur, banka adı ayrı metin olarak kalır.
- Açılır liste 5×42 piksel satır yüksekliğiyle kompakt kalır ve arama korunur.
- Çok uzun ve ayrıntılı banka logolarının küçük boyutta tüm iç yazılarının okunaklı olması garanti edilemez; banka adı her zaman tam görünür.

## Windows kurulumu ve yayınlama (v1.2.5.3)

GitHub Actions → Windows installer her main değişikliğinde Windows x64 kurulumunu üretir.
Yeni bir sürüm yayımlamak için önce installer/ParaNoya.iss dosyasındaki AppVersion değerini yükseltin. GitHub Actions → Windows installer içinde Run workflow → publish seçeneğiyle veya bu sürüme karşılık gelen vSÜRÜM etiketiyle yayın başlatın. İş akışı kurulum sürümünü bu dosyadan okur; etiket uyuşmazsa ya da aynı sürümün Release kaydı zaten varsa yayınlamayı durdurur.
Yayın yalnızca Windows testleri, gerçek kurulum, uygulama açılışı, yeniden kurulum ve kaldırma başarılıysa yapılır.
Kurulum dosyası kod imzalı değildir.

Kaynak: Python 3.13, pip install -r requirements.txt, ardından python ailefinans.py.
Yerel paketleme: pip install -r requirements-build.txt, python -m PyInstaller --clean --noconfirm ParaNoya.spec,
Inno Setup 6 ile ISCC installer\ParaNoya.iss.

Veriler önceki sürümlerle uyum için kullanıcı klasöründeki AileFinans dizininde tutulur.
Veritabanı, belgeler, yedekler ve indirilen banka logoları kaynak paketine veya kurulum dosyasına dahil edilmez.
Kaldırma kişisel finans verilerini silmez. Testlerde PARANOYA_DATA_DIR ile geçici veri klasörü kullanılabilir.
Banka logoları ilk açılışta mevcut kaynak listesinden indirilir; çevrimdışı durumda harf simgeleri kullanılır.
Logo önbelleği kullanıcı veri klasöründedir. Marka hakları ilgili sahiplerine aittir.

Windows paketleme düzeltmeleri: sürüm etiketi 1.2.5.2; yazılabilir logo önbelleği;
şema geçişi/yedekleme SQLite bağlantılarının kesin kapatılması. Finans hesaplama kuralları değiştirilmedi.
## Belgeden onaylı gelir / gider aktarımı

Akıllı Belge Merkezi'nde **Belge yükle** ile bordro, fatura veya kredi kartı ekstresi seçin. Yeni yüklemede kontrol/onay formu açılır; iptal ederseniz belge beklemede kalır. Daha sonra **Seçili belgeden gelir / gider oluştur** ile devam edebilirsiniz.

- **Bordro:** okunan net tutarı, dönemi, hesabı ve hesaba geçiş tarihini kontrol edin. Ödeme gerçekleşti onayından sonra gelir oluşur.
- **Fatura:** okunan toplam, firma ve fatura numarası açıklamaya önerilir. Ödemeyi yaptığınız banka/nakit hesabını ve ödeme tarihini seçip onaylayınca gider oluşur. Ödenmemiş faturayı henüz gider olarak onaylamayın.
- **Kredi kartı ekstresi:** okunabilen alışveriş satırını, kartı, tarihi, kategoriyi ve tutarı onaylayın. Her seferinde bir satır işlenir. Alışveriş kart borcuna eklenir ve Gelir/Gider listesinde **Kart gideri** olarak görünür; banka/nakit bakiyesi bu aşamada azalmaz. Kart ödemesini ayrıca kart ödeme ekranından kaydedin.

Aynı belge/satır tekrar işlenmez. Aynı hesap veya kartta tarih, tutar ve açıklaması eşleşen mevcut kayıt bulunursa yeni kayıt açılmaz; belge mevcut kayda bağlanır. Tarih/tutar eşleşip açıklama belirsizse işlem durdurulur; mevcut kaydı kontrol edin. Bu karşılaştırma tüm farklı belge biçimlerindeki mükerrerleri kesin olarak tespit edemez.

Ekstre toplam borcu, devreden borç, kart ödemesi ve iade alışveriş olarak aktarılmaz. Taksitli alışverişin tek ekstre taksitini yeniden toplam alışveriş gibi girmeyin; mevcut taksit planıyla karşılaştırın. Otomatik toplu ekstre aktarımı yoktur.

Destek: metin içeren PDF, TXT, CSV ve XLSX. Ekstre satır ayrıştırması `Tarih;Açıklama;Tutar`, sekme veya `|` sütunlu düzenleri tanır; her bankanın PDF düzeni okunamayabilir. Taranmış belge ve fotoğraf OCR'ı henüz yoktur. Banka bağlantısı/API entegrasyonu bu özelliğin parçası değildir.
