import json
from pathlib import Path
import tempfile
import unittest
from nacl.signing import SigningKey
from packaging.sign_release import sign_installer
from signed_release import verify_manifest

class OfflineSigningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.signer = SigningKey.generate()
        self.key_path = self.root / "release.key"
        self.key_path.write_text(self.signer.encode().hex() + "\n", encoding="ascii")
        self.version = "1.2.5.4"
        self.config = self.root / "release-config.json"
        self.config.write_text(json.dumps({
            "version": self.version, "asset_prefix": "ParaNoya",
            "tag_prefix": "ParaNoya-v",
            "signing_public_key": self.signer.verify_key.encode().hex()
        }), encoding="utf-8")
        self.installer = self.root / f"ParaNoya-{self.version}-Windows-x64-Setup.exe"
        self.installer.write_bytes(b"test fixture - not a real exe")

    def test_signs_release_and_matches_verifier(self):
        manifest, signature = sign_installer(self.key_path, self.installer, config_path=self.config)
        raw = manifest.read_bytes()
        item = json.loads(raw)
        self.assertTrue(verify_manifest(
            self.signer.verify_key.encode().hex(), raw,
            signature.read_text(encoding="ascii"),
            version=self.version, name=self.installer.name,
            size=item["size"], sha256=item["sha256"]))
        self.assertTrue(self.key_path.exists())

    def test_rejects_mismatched_private_key_without_artifacts(self):
        other = SigningKey.generate()
        self.key_path.write_text(other.encode().hex(), encoding="ascii")
        with self.assertRaises(ValueError):
            sign_installer(self.key_path, self.installer, config_path=self.config)
        self.assertFalse((self.root / f"ParaNoya-{self.version}-manifest.json").exists())

    def test_rejects_wrong_installer_name(self):
        other = self.root / "other.exe"
        other.write_bytes(b"data")
        with self.assertRaises(ValueError):
            sign_installer(self.key_path, other, config_path=self.config)

    def test_does_not_overwrite_existing_signature(self):
        sign_installer(self.key_path, self.installer, config_path=self.config)
        with self.assertRaises(FileExistsError):
            sign_installer(self.key_path, self.installer, config_path=self.config)

if __name__ == "__main__":
    unittest.main()
