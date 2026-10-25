# ParaNoya 1.2.5.4 — imzalı yayın son adımları

**Durum:** Kaynak kodu geliştirme dalındadır. Bu belge yayımlama komutu çalıştırmaz; mevcut 1.2.5.3 sürümüne ve finans verilerine dokunmaz.

## Ön koşullar

- PR #1 ve `feature/signed-central-updates` dalında Windows CI tamamen yeşil olmalı.
- `ParaNoya-Windows-x64` GitHub Actions çıktısındaki **1.2.5.4** kurulum EXE'si indirilmeli.
- Kullanıcının mevcut yerel anahtarı `$HOME\ParaNoya-Yayin-Anahtari\release.key` yerinde kalmalı. Bu dosya GitHub'a veya sohbetlere gönderilmemeli.
- Sürüm paketiyle doğrulama çıktısı (`verification.json`) gözden geçirilmeli.

## Yalnızca kullanıcı bilgisayarında imzalama

Özel geliştirme deposunun ilgili dalında Python gereksinimleri kurulduktan sonra PowerShell'de:

```powershell
$setup = "C:\YAYIN\ParaNoya-1.2.5.4-Windows-x64-Setup.exe"
$key = Join-Path $HOME "ParaNoya-Yayin-Anahtari\release.key"
python -m release_tools.sign_release --key-file $key --installer $setup
Get-FileHash -Algorithm SHA256 $setup
```

`ParaNoya-1.2.5.4-manifest.json` ve `ParaNoya-1.2.5.4-manifest.json.sig` EXE'nin yanında oluşturulur. İmzalama aracı, anahtarın uygulamanın tanınan açık anahtarıyla eşleşmesini kontrol eder.

## Yayın güvenliği

- Hedef: `mburakharput/uygulama-guncellemeleri`; etiket: `ParaNoya-v1.2.5.4`.
- Yalnızca doğrulanmış EXE, manifest, imza, SHA256SUMS ve sürüm notları yayımlanmalıdır.
- `release.key`, finansal DB, kullanıcı ekstreleri veya özel kaynaklar yüklenmemelidir.
- İmzalı manifest dosyası yükleme öncesinde EXE'nin gerçek SHA-256 özetiyle tekrar karşılaştırılmalıdır.
- Otomatik güncelleme özelliği `release-config.json` içinde **kapalı** kalır. Yükseltme ancak ayrıca uçtan uca denetlenirse etkinleştirilir.
