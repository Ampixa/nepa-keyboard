import json
import plistlib
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_macos_romanized_bundle as builder  # noqa: E402


class MacosRomanizedBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = json.loads(builder.DEFAULT_SPEC.read_text(encoding="utf-8"))
        self.profiles = {profile["output_script"]: profile for profile in self.spec["profiles"]}

    def output(self, script: str, layer: str, key: str) -> str:
        layers = builder.resolve_layers(self.profiles[script])
        return layers[layer][builder.KEY_CODES[key]]

    def test_v1_contains_nepali_newa_and_limbu(self) -> None:
        builder.validate_spec(self.spec)
        self.assertEqual(set(self.profiles), {"Deva", "Newa", "Limb"})
        self.assertEqual(len(self.spec["profiles"]), 3)

    def test_nepali_reference_and_shortcut_layers(self) -> None:
        self.assertEqual(self.output("Deva", "normal", "q"), "ट")
        self.assertEqual(self.output("Deva", "shift", "q"), "ठ")
        self.assertEqual(self.output("Deva", "caps", "k"), "क्ष")
        self.assertEqual(self.output("Deva", "caps", "1"), "1")
        self.assertEqual(self.output("Deva", "caps", "equal"), "=")
        self.assertEqual(self.output("Deva", "normal", "slash"), "्")
        self.assertEqual(self.output("Deva", "option", "q"), "q")
        self.assertEqual(self.output("Deva", "command", "c"), "c")

    def test_newa_base_shift_and_extended_letters(self) -> None:
        self.assertEqual(self.output("Newa", "normal", "k"), "𑐎")
        self.assertEqual(self.output("Newa", "shift", "k"), "𑐏")
        self.assertEqual(self.output("Newa", "option", "comma"), "𑐓")
        self.assertEqual(self.output("Newa", "option", "y"), "𑐙")
        self.assertEqual(self.output("Newa", "option", "n"), "𑐤")
        self.assertEqual(self.output("Newa", "option", "m"), "𑐪")
        self.assertEqual(self.output("Newa", "option", "q"), "𑐭")
        self.assertEqual(self.output("Newa", "normal", "slash"), "𑑂")

    def test_limbu_base_shift_option_and_complete_letters(self) -> None:
        self.assertEqual(self.output("Limb", "normal", "k"), "ᤁ")
        self.assertEqual(self.output("Limb", "shift", "k"), "ᤂ")
        self.assertEqual(self.output("Limb", "option", "k"), "ᤰ")
        self.assertEqual(self.output("Limb", "option", "comma"), "ᤝ")
        self.assertEqual(self.output("Limb", "option", "backslash"), "ᤞ")
        self.assertEqual(self.output("Limb", "normal", "0"), "᥆")
        self.assertEqual(self.output("Limb", "normal", "9"), "᥏")

    def test_build_is_byte_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path = Path(first)
            second_path = Path(second)
            builder.build_tree(builder.DEFAULT_SPEC, first_path)
            builder.build_tree(builder.DEFAULT_SPEC, second_path)
            self.assertEqual(builder.tree_snapshot(first_path), builder.tree_snapshot(second_path))

    def test_generated_bundle_is_current(self) -> None:
        builder.materialize(builder.DEFAULT_SPEC, builder.DEFAULT_OUTPUT, check=True)

    def test_bundle_metadata_registers_all_input_sources(self) -> None:
        info_path = (
            builder.DEFAULT_OUTPUT
            / "Nepa Romanized Pro.bundle"
            / "Contents"
            / "Info.plist"
        )
        with info_path.open("rb") as stream:
            info = plistlib.load(stream)
        keyboard_entries = sorted(key for key in info if key.startswith("KLInfo_"))
        self.assertEqual(len(keyboard_entries), 3)
        languages = {info[key]["TISIntendedLanguage"] for key in keyboard_entries}
        self.assertEqual(languages, {"ne", "new", "lif"})
        source_ids = {info[key]["TISInputSourceID"] for key in keyboard_entries}
        self.assertEqual(len(source_ids), 3)

    def test_keylayouts_have_seven_complete_modifier_maps(self) -> None:
        resources = (
            builder.DEFAULT_OUTPUT
            / "Nepa Romanized Pro.bundle"
            / "Contents"
            / "Resources"
        )
        layouts = sorted(resources.glob("*.keylayout"))
        self.assertEqual(len(layouts), 3)
        for path in layouts:
            text = path.read_text(encoding="utf-8")
            self.assertIn("KeyboardLayout.dtd", text)
            self.assertEqual(len(re.findall(r'<keyMap index="[0-6]">', text)), 7)
            self.assertNotRegex(text, "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
            for index in range(7):
                match = re.search(
                    rf'<keyMap index="{index}">(.*?)</keyMap>', text, flags=re.DOTALL
                )
                self.assertIsNotNone(match)
                self.assertGreaterEqual(match.group(1).count("<key "), 100)


if __name__ == "__main__":
    unittest.main()
