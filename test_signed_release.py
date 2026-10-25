import json
import unittest

from nacl.signing import SigningKey
from signed_release import SignatureError, verify_manifest

class SignedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.key = SigningKey(bytes(range(32)))
        self.payload = dict(schema=1, app="ParaNoya", version="1.2.5.4",
                            tag="ParaNoya-v1.2.5.4",
                            name="ParaNoya-1.2.5.4-Windows-x64-Setup.exe",
                            size=12345, sha256="a"*64)
        self.raw = json.dumps(self.payload, separators=(",", ":")).encode("ascii")

    def verify(self, raw=None, signature=None, **overrides):
        params=dict(version=self.payload["version"], name=self.payload["name"],
                    size=self.payload["size"], sha256=self.payload["sha256"])
        params.update(overrides)
        data=self.raw if raw is None else raw
        sig=self.key.sign(data).signature.hex() if signature is None else signature
        return verify_manifest(self.key.verify_key.encode().hex(), data, sig, **params)

    def test_valid_manifest(self):
        self.assertTrue(self.verify())

    def test_content_tamper(self):
        with self.assertRaises(SignatureError):
            self.verify(raw=self.raw.replace(b"ParaNoya", b"OtherApp"))

    def test_wrong_version(self):
        with self.assertRaises(SignatureError):
            self.verify(version="1.2.5.5")

    def test_wrong_digest(self):
        with self.assertRaises(SignatureError):
            self.verify(sha256="b"*64)

    def test_invalid_key(self):
        with self.assertRaises(SignatureError):
            verify_manifest("00", self.raw, self.key.sign(self.raw).signature.hex(),
                            version="1.2.5.4", name=self.payload["name"], size=12345, sha256="a"*64)

    def test_duplicate_signed_fields(self):
        bad=self.raw[:-1]+b',"app":"ParaNoya"}'
        with self.assertRaises(SignatureError):
            self.verify(raw=bad)

    def test_bool_size_rejected(self):
        with self.assertRaises(SignatureError):
            self.verify(size=True)

    def test_rfc8032_empty_vector(self):
        from nacl.signing import VerifyKey
        key=bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig=bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertEqual(VerifyKey(key).verify(b"", sig), b"")

if __name__=="__main__":
    unittest.main()
