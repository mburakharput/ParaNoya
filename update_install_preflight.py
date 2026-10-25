"""Conservative, read-only checks before any future installer handoff.

This module does not start a process, close the app or modify user data.
"""
import hashlib
import os
import tempfile
from pathlib import Path
import sys

from central_updates import UpdateError, load_config, version_tuple, authenticate_candidate

def check_install_preflight(installer, item, *, executable=None, local_app_data=None,
                            finance_data_dir=None, frozen=None):
    config = load_config()
    if config["updates_enabled"] is not True:
        raise UpdateError("Otomatik güncelleme henüz etkin değil")
    if os.name != "nt":
        raise UpdateError("Kurulum yalnızca Windows'ta desteklenir")
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if not frozen:
        raise UpdateError("Yalnızca kurulmuş uygulama güncellenebilir")
    executable = Path(executable or sys.executable).resolve()
    if executable.name.casefold() != "paranoya.exe":
        raise UpdateError("Uygulama dosyası eşleşmiyor")
    if local_app_data is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise UpdateError("Kullanıcı kurulum klasörü belirlenemedi")
    expected_folder = (Path(local_app_data) / "Programs" / "ParaNoya").resolve()
    if executable.parent != expected_folder:
        raise UpdateError("Mevcut kurulum klasörü doğrulanamadı")
    if not (expected_folder / "unins000.exe").is_file():
        raise UpdateError("Mevcut kurulumun kaldırma kaydı yok")
    # Finance data is never part of the installed application tree.
    from finance_core import DB_DIR
    data_dir = Path(finance_data_dir or DB_DIR).resolve()
    if data_dir == expected_folder or expected_folder in data_dir.parents:
        raise UpdateError("Finansal veriler uygulama klasörünün içinde; yükseltme durduruldu")
    original = Path(installer).absolute()
    path = original.resolve()
    if any(part.is_symlink() for part in (original, *original.parents)):
        raise UpdateError("Kurulum yolu sembolik bağlantı içeriyor")
    if not path.is_file():
        raise UpdateError("Kurulum dosyası bulunamadı")
    # Only accept files placed in the isolated verified download directory.
    folder = path.parent
    trusted_temp = Path(tempfile.gettempdir()).resolve()
    if (not folder.name.startswith("paranoya-verified-")
            or folder.parent.resolve() != trusted_temp):
        raise UpdateError("Kurulum dosyası doğrulanmış indirme klasöründe değil")
    name = item.get("name")
    version = item.get("version", "")
    if not isinstance(version, str) or version_tuple(version) <= version_tuple(config["version"]):
        raise UpdateError("Güncelleme sürümü mevcut sürümden yeni olmalı")
    if name != f"ParaNoya-{version}-Windows-x64-Setup.exe":
        raise UpdateError("Kurulum adı sürümle eşleşmiyor")
    size = item.get("size")
    digest = item.get("sha256")
    if path.name != name or not isinstance(size, int) or isinstance(size, bool):
        raise UpdateError("Kurulum dosyası bilgileri geçersiz")
    if not isinstance(digest, str) or len(digest) != 64:
        raise UpdateError("Kurulum özeti geçersiz")
    # Recheck the signed release metadata immediately before handoff.
    # A matching local SHA-256 is not sufficient without publisher authentication.
    authenticate_candidate(config, item)
    if path.stat().st_size != size:
        raise UpdateError("Kurulum dosyası boyutu değişmiş")
    sha = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            sha.update(block)
    if sha.hexdigest() != digest:
        raise UpdateError("Kurulum dosyası doğrulamayı geçemedi")
    # No execution happens here. An installer handoff needs additional
    # authenticated-release verification and explicit user confirmation.
    return expected_folder
