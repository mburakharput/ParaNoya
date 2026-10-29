"""Offline ParaNoya release signer. Keep release.key off GitHub.

Usage:
  python packaging/sign_release.py --key-file PATH_TO_RELEASE_KEY --installer PATH_TO_SETUP_EXE
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nacl.signing import SigningKey
from signed_release import verify_manifest

CONFIG = Path(__file__).resolve().parents[1] / "release-config.json"

def sign_installer(key_file, installer, *, config_path=CONFIG):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    public_hex = config.get("signing_public_key", "")
    if not re.fullmatch(r"[0-9a-f]{64}", public_hex):
        raise ValueError("ParaNoya yayıncı açık anahtarı eksik")
    if config.get("asset_prefix") != "ParaNoya" or config.get("tag_prefix") != "ParaNoya-v":
        raise ValueError("Uygulama kimliği eşleşmiyor")
    version = config["version"]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2,3}", version):
        raise ValueError("Sürüm geçersiz")
    path = Path(installer).resolve()
    if not path.is_file():
        raise FileNotFoundError('Kurulum dosyası bulunamadı')
    expected_name = f"ParaNoya-{version}-Windows-x64-Setup.exe"
    if path.name != expected_name:
        raise ValueError("Kurulum dosyası sürümü release-config.json ile eşleşmiyor")
    seed = Path(key_file).read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", seed):
        raise ValueError("Özel anahtar 32 baytlık Ed25519 seed olmalı")
    signer = SigningKey(bytes.fromhex(seed))
    if signer.verify_key.encode().hex() != public_hex:
        raise ValueError("Özel anahtar ParaNoya açık anahtarıyla eşleşmiyor")
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            size += len(block)
            if size > 2 * 1024 ** 3:
                raise ValueError("Kurulum dosyası çok büyük")
            sha.update(block)
    if not size:
        raise ValueError("Kurulum dosyası boş")
    record = dict(schema=1, app="ParaNoya", version=version,
                  tag="ParaNoya-v"+version, name=expected_name,
                  size=size, sha256=sha.hexdigest())
    manifest = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    signature = signer.sign(manifest).signature.hex()
    verify_manifest(public_hex, manifest, signature, version=version,
                    name=expected_name, size=size, sha256=sha.hexdigest())
    prefix = f"ParaNoya-{version}-manifest.json"
    manifest_file = path.with_name(prefix)
    signature_file = path.with_name(prefix + ".sig")
    # Never silently overwrite a prior signature.
    with manifest_file.open("xb") as handle:
        handle.write(manifest)
    try:
        with signature_file.open("x", encoding="ascii") as handle:
            handle.write(signature + "\n")
    except BaseException:
        manifest_file.unlink(missing_ok=True)
        raise
    return manifest_file, signature_file

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Sign ParaNoya release without uploading the private key")
    p.add_argument("--key-file", required=True)
    p.add_argument("--installer", required=True)
    args = p.parse_args()
    for created in sign_installer(args.key_file, args.installer):
        print(created)
