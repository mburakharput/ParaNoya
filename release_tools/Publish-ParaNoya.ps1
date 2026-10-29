<# User-run only. The assistant must never run this against the real signing key.
Downloads a successful CI artifact, checks its source/hash, asks the user to select
the local key, signs locally, and publishes only ParaNoya assets in the central repo.
No key material is uploaded, printed, or stored in GitHub Actions.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][long]$BuildRunId,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$InstallerSha256,
    [string]$SignedDirectory
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Push-Location $project
try {
    $config = Get-Content -LiteralPath (Join-Path $project 'release-config.json') -Raw -Encoding utf8 | ConvertFrom-Json
    $version = $config.version
    if ($config.repository -ne 'mburakharput/uygulama-guncellemeleri') { throw 'Merkezi depo eşleşmiyor.' }
    $sourceRepo = 'mburakharput/ParaNoya'
    $targetRepo = $config.repository
    $tag = "ParaNoya-v$version"
    $python = (Get-Command python -ErrorAction Stop).Source

    # Reuse the user's normal GitHub sign-in via Git Credential Manager.
    # Captured credentials are kept in memory and never written to console/files.
    $credentials = "protocol=https`nhost=github.com`n`n" | git credential fill
    if ($LASTEXITCODE -ne 0) { throw 'GitHub oturumu alınamadı. Git Credential Manager ile GitHub hesabınıza giriş yapıp komutu yeniden çalıştırın.' }
    $credentialMap = @{}
    foreach ($line in $credentials) {
        $pair = $line -split '=', 2
        if ($pair.Count -eq 2) { $credentialMap[$pair[0]] = $pair[1] }
    }
    $token = $credentialMap['password']
    if (!$token) { throw 'GitHub kimlik bilgisi bulunamadı.' }
    $headers = @{ Authorization="Bearer $token"; Accept='application/vnd.github+json'; 'X-GitHub-Api-Version'='2022-11-28'; 'User-Agent'='ParaNoya-Local-Publisher' }
    $api = 'https://api.github.com'
    $run = Invoke-RestMethod -Uri "$api/repos/$sourceRepo/actions/runs/$BuildRunId" -Headers $headers
    if ($run.head_sha -ne $SourceCommit -or $run.status -ne 'completed' -or $run.path -ne '.github/workflows/windows-release.yml') { throw 'Derleme kaynağı doğrulanamadı.' }
    $jobs = Invoke-RestMethod -Uri "$api/repos/$sourceRepo/actions/runs/$BuildRunId/jobs?per_page=100" -Headers $headers
    if (@($jobs.jobs | Where-Object { $_.name -eq 'build' -and $_.conclusion -eq 'success' }).Count -ne 1) { throw 'Başarılı Windows derlemesi yok.' }
    if (!$SignedDirectory) {
    $artifacts = Invoke-RestMethod -Uri "$api/repos/$sourceRepo/actions/runs/$BuildRunId/artifacts" -Headers $headers
    $artifact = @($artifacts.artifacts | Where-Object { $_.name -eq 'ParaNoya-Windows-x64' -and !$_.expired })
    if ($artifact.Count -ne 1 -or $artifact[0].digest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Doğrulanabilir derleme paketi bulunamadı.' }
    $output = Join-Path $project ("release-output\ParaNoya-$version-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $output | Out-Null
    $zip = Join-Path $output 'ci-artifact.zip'
    Invoke-WebRequest -Uri "$api/repos/$sourceRepo/actions/artifacts/$($artifact[0].id)/zip" -Headers $headers -OutFile $zip -UseBasicParsing
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $artifact[0].digest.Substring(7)) { throw 'ZIP özeti eşleşmiyor.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        $names = @("ParaNoya-$version-Windows-x64-Setup.exe", 'SHA256SUMS.txt', 'verification.json')
        if ($archive.Entries.Count -ne $names.Count) { throw 'Paket dosya listesi farklı.' }
        foreach ($name in $names) {
            $entry = @($archive.Entries | Where-Object { $_.FullName -ceq $name })
            if ($entry.Count -ne 1) { throw "Paket dosyası eksik veya mükerrer: $name" }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry[0], (Join-Path $output $name), $false)
        }
    } finally { $archive.Dispose() }
    } else {
        $output = (Resolve-Path -LiteralPath $SignedDirectory -ErrorAction Stop).Path
    }
    $installer = Join-Path $output "ParaNoya-$version-Windows-x64-Setup.exe"
    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $InstallerSha256) { throw 'Kurulum dosyasının beklenen özeti eşleşmiyor; imzalanmadı.' }
    $verified = Get-Content -LiteralPath (Join-Path $output 'verification.json') -Raw -Encoding utf8 | ConvertFrom-Json
    if ($verified.ok -ne $true -or $verified.database -ne 'temporary') { throw 'Kurulum doğrulama raporu geçersiz.' }
    # The user selects the key locally; only this user-run signer reads it.
    if (!$SignedDirectory) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.InitialDirectory = [Environment]::GetFolderPath('Desktop')
    $dialog.Title = 'ParaNoya yayın anahtarını seçin (anahtar yüklenmez)'
    $dialog.Filter = 'Anahtar dosyası (*.key;*.txt)|*.key;*.txt|Tüm dosyalar (*.*)|*.*'
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw 'İmzalama kullanıcı tarafından iptal edildi.' }
    & $python -m release_tools.sign_release --key-file $dialog.FileName --installer $installer
    if ($LASTEXITCODE -ne 0) { throw 'İmzalama başarısız; yayın yapılmadı.' }
    $dialog.Dispose()
    }
    & $python -m release_tools.verify_release --installer $installer
    if ($LASTEXITCODE -ne 0) { throw 'İmza doğrulaması başarısız; yayın yapılmadı.' }
    @{ repository=$sourceRepo; source_commit=$SourceCommit; build_run_id="$BuildRunId"; version=$version } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'build-provenance.json') -Encoding utf8
    # Existing app/version tags are never overwritten. All uploads remain draft
    # until every asset has been verified by GitHub's SHA-256 response.
    # Get-Content returns a decorated PowerShell string in Windows PowerShell 5.1;
    # ConvertTo-Json serializes its provider properties as an object. Read plain
    # System.String directly so GitHub receives the required JSON string.
    $notes = [IO.File]::ReadAllText((Join-Path $project 'RELEASE-NOTES.md'), [Text.Encoding]::UTF8)
    $body = @{ tag_name=$tag; name="ParaNoya $version"; body=$notes; draft=$true; prerelease=$false; make_latest='false' } | ConvertTo-Json
    $release = Invoke-RestMethod -Method Post -Uri "$api/repos/$targetRepo/releases" -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
    $upload = $release.upload_url -replace '\{\?name,label\}$', ''
    if (!$upload.StartsWith("https://uploads.github.com/repos/$targetRepo/releases/")) { throw 'Yükleme adresi doğrulanamadı.' }
    $files = @("ParaNoya-$version-Windows-x64-Setup.exe", "ParaNoya-$version-manifest.json", "ParaNoya-$version-manifest.json.sig", 'SHA256SUMS.txt', 'verification.json', 'build-provenance.json')
    foreach ($name in $files) {
        $file = Join-Path $output $name
        $asset = Invoke-RestMethod -Method Post -Uri ($upload + '?name=' + [Uri]::EscapeDataString($name)) -Headers $headers -ContentType 'application/octet-stream' -InFile $file
        $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($asset.state -ne 'uploaded' -or $asset.digest -ne "sha256:$hash") { throw "Yüklenen dosya doğrulanamadı: $name. Sürüm taslak kaldı." }
    }
    $release = Invoke-RestMethod -Method Patch -Uri "$api/repos/$targetRepo/releases/$($release.id)" -Headers $headers -ContentType 'application/json' -Body '{"draft":false,"make_latest":"false"}'
    Write-Host "Yayımlandı: $($release.html_url)"
    Write-Host "İmzalı dosyalar: $output"
} finally {
    $token=$null; $headers=$null; $credentials=$null; $credentialMap=$null
    Pop-Location
}
