@echo off
setlocal
cd /d "%~dp0"
title ParaNoya - Gelistirme Onizlemesi

rem Development runs with an isolated database; never open or migrate personal data.
if not defined PARANOYA_DATA_DIR set "PARANOYA_DATA_DIR=%LOCALAPPDATA%\ParaNoya\DevelopmentSandbox"
echo ParaNoya gelistirme onizlemesi
echo Test veri klasoru: %PARANOYA_DATA_DIR%
echo Kisisel finans verileri kullanilmaz.
echo.

if not exist "ailefinans.py" (
    echo HATA: Baslat.bat, ailefinans.py dosyasi ile ayni klasorde olmali.
    pause
    exit /b 1
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 ailefinans.py
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo HATA: Python bulunamadi. Python 3 ve requirements.txt bagimliliklarini kurun.
        pause
        exit /b 1
    )
    python ailefinans.py
)
set "result=%errorlevel%"
if not "%result%"=="0" (
    echo.
    echo ParaNoya baslatilamadi. Hata kodu: %result%
    echo Gerekiyorsa: py -3 -m pip install -r requirements.txt
    pause
)
exit /b %result%
