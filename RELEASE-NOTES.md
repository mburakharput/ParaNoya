# ParaNoya 1.2.5.6 — uygulama içinden güvenli güncelleme

- Yeni sürümleri uygulamadaki **Güncellemeleri denetle** düğmesinden kontrol edin.
- Yalnızca tanınan yayıncı anahtarıyla Ed25519 imzası doğrulanmış merkezi sürümler kabul edilir. İndirilen kurulumun boyutu ve SHA-256 özeti de kontrol edilir.
- İndirme ve kurulum için ayrı onay istenir. Kurulum öncesinde finans verileri ve ürün ekleri yedeklenir; yedek doğrulanamazsa uygulama kapanmaz.
- Ayrı güncelleme yardımcısı ParaNoya'nın doğru işleminin kapandığını bekler; kurulumu görünür biçimde açar ve ardından uygulamayı yeniden başlatır.
- Açık işlem formu varken güncelleme başlatılmaz. Hatalı imza, dosya değişikliği, eski sürüm veya farklı kurulum klasörü durumunda kurulum durdurulur.

1.2.5.5 ve daha eski sürümlerden ilk geçiş bir kez manuel kurulum gerektirir. Merkezi yayın deposuna yeni paket ve geçerli imzalı manifest eklenmeden uygulama içinde daha yeni bir sürüm görünmez. İmzasız paket uygulama tarafından çalıştırılmaz. Windows kurulum dosyasının Authenticode kod imzası yoktur; Ed25519 manifest doğrulaması ayrı bir mekanizmadır.

Bu sürüm kişisel veri veya özel imza anahtarı içermez. Banka bağlantısı ve OCR bu sürüme dahil değildir.
