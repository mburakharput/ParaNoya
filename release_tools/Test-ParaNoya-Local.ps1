# ParaNoya: run source regression tests locally, without GitHub Actions.
# Usage: powershell -ExecutionPolicy Bypass -File .\release_tools\Test-ParaNoya-Local.ps1
#        powershell -ExecutionPolicy Bypass -File .\release_tools\Test-ParaNoya-Local.ps1 -CriticalOnly
[CmdletBinding()]
param([switch]$CriticalOnly)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not (Test-Path (Join-Path $repo 'finance_core.py'))) {
    throw 'ParaNoya kaynak klasoru bulunamadi.'
}

$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    $exe = $launcher.Source
    $prefix = @('-3')
} else {
    $launcher = Get-Command python -ErrorAction SilentlyContinue
    if (-not $launcher) { throw 'Python 3 bulunamadi. Python 3 yukleyin.' }
    $exe = $launcher.Source
    $prefix = @()
}

# Never run against the default %USERPROFILE%\AileFinans database.
$tempDir = Join-Path ([IO.Path]::GetTempPath()) ('paranoya-local-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempDir -ErrorAction Stop | Out-Null
$previous = [Environment]::GetEnvironmentVariable('PARANOYA_DATA_DIR', 'Process')
$exitCode = 1
Push-Location $repo
try {
    [Environment]::SetEnvironmentVariable('PARANOYA_DATA_DIR', $tempDir, 'Process')
    Write-Host ('ParaNoya test veri klasoru (gecici): ' + $tempDir)
    Write-Host 'Gercek veritabani, kurulu uygulama ve GitHub Actions kullanilmaz.'
    if ($CriticalOnly) {
        $testFiles = @(
            'test_backup_identity',
            'test_migration_identity',
            'test_financial_amounts',
            'test_card_kmh_safety',
            'test_recurring',
            'test_document_posting',
            'test_reporting_core'
        )
        & $exe @prefix -m unittest -v @testFiles
    } else {
        & $exe @prefix -m unittest discover -v
    }
    $exitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('PARANOYA_DATA_DIR', $previous, 'Process')
    Pop-Location
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
if ($exitCode -ne 0) { throw "ParaNoya yerel testleri basarisiz (cikis kodu $exitCode)." }
Write-Host 'ParaNoya yerel testleri basarili.' -ForegroundColor Green
