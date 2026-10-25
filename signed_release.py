"""Verify signed central release records; never execute a downloaded installer."""
import json
import re
from nacl.exceptions import BadSignatureError

class SignatureError(ValueError):
    pass

def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SignatureError("İmzalı kayıtta tekrar eden alan var")
        result[key] = value
    return result

def verify_manifest(public_key_hex, raw_manifest, signature_hex, *, version, name, size, sha256):
    """Accept ONLY an exact Ed25519-signed schema-1 ParaNoya manifest.

    Caller must separately validate installer byte count and SHA-256 before install.
    This routine deliberately cannot download or execute anything.
    """
    try:
        public_key = bytes.fromhex(public_key_hex)
        signature = bytes.fromhex(signature_hex.strip())
        if len(public_key) != 32 or len(signature) != 64:
            raise SignatureError("İmza anahtarı ya da imza uzunluğu geçersiz")
        if type(raw_manifest) is not bytes or len(raw_manifest) > 16 * 1024:
            raise SignatureError("İmzalı kayıt boyutu geçersiz")
        from nacl.signing import VerifyKey
        VerifyKey(public_key).verify(raw_manifest, signature)
        record = json.loads(raw_manifest.decode("ascii"), object_pairs_hook=_no_duplicate_keys)
    except (ValueError, TypeError, UnicodeError, BadSignatureError, ImportError) as exc:
        raise SignatureError("Sürüm imzası doğrulanamadı") from exc
    if type(size) is not int or not 0 < size <= 2 * 1024**3:
        raise SignatureError("Kurulum dosyası boyutu geçersiz")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise SignatureError("SHA-256 geçersiz")
    expected = dict(schema=1, app="ParaNoya", version=version, tag="ParaNoya-v"+version,
                    name=name, size=size, sha256=sha256)
    if record != expected or type(record.get("schema")) is not int or type(record.get("size")) is not int:
        raise SignatureError("İmzalı sürüm bilgileri eşleşmiyor")
    return True
