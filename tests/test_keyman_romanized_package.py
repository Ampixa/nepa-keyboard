import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_keyman_romanized_package as keyman  # noqa: E402
import build_macos_romanized_bundle as mapping  # noqa: E402


class KeymanRomanizedPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = json.loads(keyman.DEFAULT_SPEC.read_text(encoding="utf-8"))
        self.profiles = {
            profile["output_script"]: profile for profile in self.spec["profiles"]
        }

    def test_package_contains_all_three_first_release_profiles(self) -> None:
        self.assertEqual(set(self.profiles), {"Deva", "Newa", "Limb"})
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            keyman.build_tree(keyman.DEFAULT_SPEC, output)
            package = ET.parse(output / "source" / "nepa_romanized_pro.kps")
            ids = [node.text for node in package.findall("./Keyboards/Keyboard/ID")]
            self.assertEqual(
                ids,
                [
                    "nepa_nepali_romanized",
                    "nepa_newa_romanized",
                    "nepa_limbu_romanized",
                ],
            )

    def test_every_keyman_rule_matches_the_canonical_desktop_layer(self) -> None:
        for profile in self.spec["profiles"]:
            layers = mapping.resolve_layers(profile)
            rules = keyman.rules_for_profile(profile)
            self.assertEqual(len(rules), 8 * len(mapping.KEY_CODES))
            for rule in rules:
                self.assertEqual(
                    rule.output,
                    layers[rule.layer][mapping.KEY_CODES[rule.key]],
                    msg=f"{profile['profile_id']} {rule.modifiers} {rule.key}",
                )

    def test_nepali_caps_and_newa_limbu_extended_layers_are_present(self) -> None:
        nepali = keyman.render_kmn(self.profiles["Deva"])
        newa = keyman.render_kmn(self.profiles["Newa"])
        limbu = keyman.render_kmn(self.profiles["Limb"])
        self.assertIn("+ [CAPS K_K] > U+0915 U+094D U+0937", nepali)
        self.assertIn("+ [RALT NCAPS K_COMMA] > U+11413", newa)
        self.assertIn("+ [RALT NCAPS K_COMMA] > U+191D", limbu)
        self.assertIn("+ [RALT NCAPS K_BKSLASH] > U+191E", limbu)

    def test_only_right_alt_is_claimed_for_extended_layers(self) -> None:
        for profile in self.spec["profiles"]:
            source = keyman.render_kmn(profile)
            self.assertIn("RALT", source)
            self.assertNotIn("[ALT ", source)
            self.assertNotIn("[LALT ", source)

    def test_outputs_use_explicit_unicode_scalars(self) -> None:
        sources = []
        for profile in self.spec["profiles"]:
            source = keyman.render_kmn(profile)
            sources.append(source)
            self.assertIsNone(re.search(r"^\+ .* > '(?!')", source, flags=re.MULTILINE))
            self.assertNotIn(" > ''", source)
            self.assertIsNotNone(
                re.search(r"^\+ .* > U\+[0-9A-F]{4,6}", source, flags=re.MULTILINE)
            )
        self.assertIn("U+200D", "\n".join(sources))

    def test_generated_sources_are_byte_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path = Path(first)
            second_path = Path(second)
            keyman.build_tree(keyman.DEFAULT_SPEC, first_path)
            keyman.build_tree(keyman.DEFAULT_SPEC, second_path)
            self.assertEqual(
                keyman.tree_snapshot(first_path), keyman.tree_snapshot(second_path)
            )

    def test_checked_generated_sources_are_current(self) -> None:
        keyman.materialize(keyman.DEFAULT_SPEC, keyman.DEFAULT_OUTPUT, check=True)


if __name__ == "__main__":
    unittest.main()
