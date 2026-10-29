# ParaNoya 1.2.5.8

- Program Files ve özel klasörlerdeki kayıtlı kurulumları reddeden güncelleme denetimi düzeltildi.
- Kurulum klasörü ve kullanıcı/tüm kullanıcılar kapsamı Windows kurulum kaydıyla doğrulanıp korunuyor.
- Yönetici izni gereken güncellemelerde yalnız imzası doğrulanmış kurulum dosyası Windows onayıyla çalıştırılıyor. Yönetici onayı beklenirken dosya değiştirilemiyor veya silinemiyor.
- Yönetici onayı iptal edilirse mevcut uygulama yeniden açılıyor.
- 1.2.5.7'nin finans güvenilirliği, geri yükleme ve tüm menülerde zemin düzeltmeleri dahildir.

Eski güncelleyici Program Files kurulumunu reddediyorsa bu sürüme bir kez elle, mevcut kurulum klasörüne geçin. Programı kaldırmayın; kişisel veri klasörünü taşımayın. Sonraki sürümler uygulama içinden alınabilir.

Özel anahtar veya kişisel veri paketlenmez. Windows Authenticode kod imzası ile güncelleme manifestinin Ed25519 imzası ayrı mekanizmalardır; kurulum EXE'si Windows kod imzalı değildir.
