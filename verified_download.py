"""Download a trusted installer to an isolated temporary directory; NEVER launch it.

The entire release record must be Ed25519-authenticated before bytes are accepted.
"""
import hashlib
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from central_updates import UpdateError, authenticate_candidate

_ALLOWED_HOSTS = frozenset({
    "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
})

def _validate_url(value):
    try:
        p = urlsplit(value)
        if (p.scheme != "https" or p.hostname not in _ALLOWED_HOSTS
                or p.username or p.password or p.port not in (None, 443)):
            raise UpdateError("İndirme adresi güvenli değil")
    except (TypeError, ValueError) as exc:
        raise UpdateError("İndirme adresi geçersiz") from exc
    return value

class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def _open(url):
    return build_opener(_SafeRedirect()).open(
        Request(_validate_url(url), headers={"User-Agent": "ParaNoya-Verified-Update"}),
        timeout=30,
    )

def download_verified(config, item):
    """Download only after manifest verification. Returns file path, never executes.

    Disabled-by-default feature may not be bypassed by a supplied release item.
    """
    if config.get("updates_enabled") is not True:
        raise UpdateError("Güncelleme indirmeleri henüz etkin değil")
    if not isinstance(item, dict):
        raise UpdateError("Geçersiz güncelleme bilgisi")
    version = item.get("version", "")
    expected_name = f"ParaNoya-{version}-Windows-x64-Setup.exe"
    expected_url = (f"https://github.com/{config.get('repository')}/releases/download/"
                    f"ParaNoya-v{version}/{expected_name}")
    if (not re.fullmatch(r"[0-9]+(?:\\.[0-9]+){2,3}", version)
            or item.get("name") != expected_name or item.get("url") != expected_url):
        raise UpdateError("Sürüm veya indirme adresi eşleşmiyor")
    if (type(item.get("size")) is not int or not 0 < item["size"] <= 2 * 1024**3
            or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", ""))):
        raise UpdateError("Kurulum bilgileri hatalı")
    authenticate_candidate(config, item)  # retrieves and verifies the signed record again
    folder = Path(tempfile.mkdtemp(prefix="paranoya-verified-"))
    partial = folder / "setup.partial"
    target = folder / expected_name
    digest = hashlib.sha256()
    received = 0
    try:
        with _open(expected_url) as response, partial.open("xb") as output:
            while block := response.read(1024 * 1024):
                received += len(block)
                if received > item["size"]:
                    raise UpdateError("Dosya imzalı boyutu aşıyor")
                digest.update(block)
                output.write(block)
        if received != item["size"] or digest.hexdigest() != item["sha256"]:
            raise UpdateError("Kurulum dosyasının SHA-256 doğrulaması başarısız")
        os.replace(partial, target)
        return target
    except BaseException:
        partial.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        folder.rmdir()
        raise
