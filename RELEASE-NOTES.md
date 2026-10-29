# ParaNoya 1.2.5.7

- Kart/KMH ödemeleri ve limit kontrolleri eşzamanlı işlemlere karşı korundu.
- Gecikmiş faturalar listede tutuluyor; uzun süreli ödeme planlarındaki 240 dönem sınırı kaldırıldı. Gecikmiş/bekleyen durumları gösteriliyor.
- Belge Merkezi'ne yedek oluşturma ve onaylı geri yükleme eklendi. Yedekte SQLite bütünlüğü, kayıt ilişkileri, sürüm, dosya yolları ve ek belge özetleri kontrol ediliyor.
- Geri yüklemede eski veri klasörünün tamamı kurtarma kopyası olarak korunuyor. Başarısız veya yarım kalan değiştirmeden kurtarma eklendi.
- Aynı veri klasöründe ikinci uygulama penceresinin açılması engellendi.
- Tüm menülerdeki özet kartları ve ayrıntı kutularında renk şeridi oluşturan yazı zeminleri düzeltildi. Açık/koyu tema kontrol edildi.

Geri yüklemeden önce diğer eski ParaNoya kopyalarını kapatın. Özel imza anahtarı veya kişisel veri paketlenmez. Windows Authenticode kod imzası ile güncelleme manifestinin Ed25519 imzası ayrı mekanizmalardır; bu paket Windows kod imzalı değildir.
