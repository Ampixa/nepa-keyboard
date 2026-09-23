from __future__ import annotations

import plistlib
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "desktop/macos-ime/build"
APPS = (
    ("Nepali Phonetic - Nepa.app", "Deva", "npi-Latn-Deva-v1.json"),
    ("Nepal Bhasa Phonetic Newa - Nepa.app", "Newa", "new-Latn-Newa-v1.json"),
    ("Limbu Phonetic Sirijanga - Nepa.app", "Limb", "lif-Latn-Limb-v1.json"),
)


@unittest.skipUnless(__import__("sys").platform == "darwin", "macOS-only bundle test")
class MacosPhoneticBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            ["bash", str(ROOT / "desktop/macos-ime/build-package.sh")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_native_swift_core_vectors_and_toggle(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "desktop/macos-ime/test-core.sh")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("macos_phonetic_core=ok profiles=3", result.stdout)

    def test_package_contains_three_input_method_apps(self) -> None:
        package_root = BUILD / "package-root/Library/Input Methods"
        for app_name, script, asset in APPS:
            with self.subTest(app=app_name):
                contents = package_root / app_name / "Contents"
                info = plistlib.loads((contents / "Info.plist").read_bytes())
                self.assertEqual("NepaPhonetic.NepaInputController", info["InputMethodServerControllerClass"])
                self.assertEqual([script], info["tsInputMethodCharacterRepertoireKey"])
                self.assertTrue((contents / "Resources" / asset).is_file())
                self.assertTrue((contents / "MacOS/NepaPhonetic").is_file())

    def test_unsigned_test_installer_exists(self) -> None:
        package = BUILD / "NepaPhonetic-0.2.0.pkg"
        self.assertGreater(package.stat().st_size, 10_000)
        result = subprocess.run(
            ["pkgutil", "--check-signature", str(package)],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
