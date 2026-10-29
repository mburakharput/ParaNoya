"""Read-only central release discovery. Never downloads or executes installers."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from signed_release import verify_manifest, SignatureError

class UpdateError(RuntimeError):
    pass

def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2,3}", value):
        raise UpdateError("Geçersiz sürüm bilgisi")
    return tuple(map(int, value.split("."))) + (0,) * (4 - len(value.split(".")))

def load_config(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name("release-config.json")
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("repository") != "mburakharput/uygulama-guncellemeleri":
        raise UpdateError("Güncelleme deposu doğrulanamadı")
    if config.get("asset_prefix") != "ParaNoya" or config.get("tag_prefix") != "ParaNoya-v":
        raise UpdateError("Uygulama kimliği doğrulanamadı")
    if config.get("install_scope") != "user":
        raise UpdateError("Mevcut kullanıcı kurulumu korunmalı")
    version_tuple(config.get("version"))
    if type(config.get("updates_enabled")) is not bool:
        raise UpdateError("Güncelleme etkinlik ayarı hatalı")
    return config

def candidate(config, release):
    if release.get("draft") or release.get("prerelease"):
        return None
    tag = release.get("tag_name", "")
    if not isinstance(tag, str) or not tag.startswith(config["tag_prefix"]):
        return None
    ver = tag[len(config["tag_prefix"]):]
    if version_tuple(ver) <= version_tuple(config["version"]):
        return None
    name = f"ParaNoya-{ver}-Windows-x64-Setup.exe"
    prefix = f"https://github.com/{config['repository']}/releases/download/{tag}/"
    matching = [a for a in release.get("assets", []) if a.get("name") == name and a.get("state") == "uploaded"]
    if len(matching) != 1:
        return None
    asset = matching[0]
    url = asset.get("browser_download_url", "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or url != prefix + name:
        raise UpdateError("Güncelleme bağlantısı güvenli değil")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", asset.get("digest", "")):
        raise UpdateError("Kurulumun SHA-256 doğrulaması eksik")
    size = asset.get("size")
    if type(size) is not int or not 0 < size <= 2 * 1024**3:
        raise UpdateError("Kurulum boyutu geçersiz")
    links = {}
    for field, suffix in (("manifest_url", "-manifest.json"), ("signature_url", "-manifest.json.sig")):
        filename = f"ParaNoya-{ver}{suffix}"
        match = [a for a in release.get("assets", []) if a.get("name") == filename and a.get("state") == "uploaded"]
        if len(match) != 1 or match[0].get("browser_download_url") != prefix + filename:
            raise UpdateError("İmzalı sürüm kaydı eksik")
        links[field] = prefix + filename
    return {"version": ver, "url": url, "name": name, "sha256": asset["digest"][7:], "size": size, **links}

def _read_small(url):
    # GitHub assets may redirect. A host allowlist limits where metadata is retrieved.
    from urllib.request import build_opener, HTTPRedirectHandler
    allowed = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
    def valid(target):
        parsed = urlsplit(target)
        if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise UpdateError("İmzalı kayıt kaynağı güvenli değil")
        return target
    class SafeRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            valid(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    with build_opener(SafeRedirect()).open(Request(valid(url), headers={"User-Agent": "ParaNoya-Update-Check"}), timeout=15) as response:
        data = response.read(16 * 1024 + 1)
    if len(data) > 16 * 1024:
        raise UpdateError("İmzalı kayıt çok büyük")
    return data


def authenticate_candidate(config, item):
    key = config.get("signing_public_key", "")
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise UpdateError("Yayıncı doğrulama anahtarı henüz yapılandırılmadı")
    manifest = _read_small(item["manifest_url"])
    try:
        signature = _read_small(item["signature_url"]).decode("ascii")
        verify_manifest(key, manifest, signature, version=item["version"],
                        name=item["name"], size=item["size"], sha256=item["sha256"])
    except (SignatureError, UnicodeError) as exc:
        raise UpdateError("Güncelleme imzası doğrulanamadı") from exc
    return item


def check(config=None):
    """Only metadata discovery. Disabled unless a trusted configuration enables it."""
    config = load_config() if config is None else config
    if not config.get("updates_enabled", False):
        return None
    url = f"https://api.github.com/repos/{config['repository']}/releases?per_page=100"
    with urlopen(Request(url, headers={"User-Agent": "ParaNoya-Update-Check", "Accept": "application/vnd.github+json"}), timeout=15) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise UpdateError("Sürüm yanıtı çok büyük")
    releases = json.loads(data)
    if not isinstance(releases, list):
        raise UpdateError("Geçersiz sürüm listesi")
    candidates = [item for release in releases if (item := candidate(config, release))]
    best = max(candidates, key=lambda x: version_tuple(x["version"]), default=None)
    return authenticate_candidate(config, best) if best else None
