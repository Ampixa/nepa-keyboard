from __future__ import annotations

import json
import unicodedata
import unittest
from pathlib import Path

from tools.build_script_conversion_map import (
    _canonical_bytes,
    build_asset,
    convert_text,
)
from tools.build_transliteration_map import build_asset as build_transliteration_map
from tools.build_transliteration_map import transliterate

REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "catalog/script-conversion/lif-Deva-Limb-v0.json"
ASSET = REPOSITORY / "android/ime-app/src/main/assets/nepa-conversions/lif-Deva-Limb-v1.json"
ROMAN = REPOSITORY / "catalog/transliteration/lif-Latn-Limb-v0.json"

# Minimal pairs from the Chhatthare Limbu grammar and the project's Limbu G2P
# contrast evaluation, written in the LIFWBT-style Devanagari orthography.
CONTRASTS = [
    ("हप्", "हॽ", "glottal stop against final /p/"),
    ("लत्", "लॽ", "glottal stop against final /t/"),
    ("हे़क्", "हे़ॽ", "glottal stop against final /k/"),
    ("लाङ्", "लाःङ्", "vowel length"),
    ("के", "के़", "lower-mid vowel"),
]


class LimbuScriptConversionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.asset = build_asset(SOURCE)

    def test_matches_the_shipped_asset(self) -> None:
        self.assertEqual(ASSET.read_bytes(), _canonical_bytes(self.asset))

    def test_targets_the_limbu_script(self) -> None:
        self.assertEqual(self.asset["source_script"], "Deva")
        self.assertEqual(self.asset["output_script"], "Limb")

    def test_every_rule_crosses_script(self) -> None:
        for row in self.asset["rules"]:
            with self.subTest(source=row["from"]):
                for character in row["from"]:
                    self.assertTrue(unicodedata.name(character).startswith("DEVANAGARI "))
                for character in row["to"]:
                    self.assertTrue(unicodedata.name(character).startswith("LIMBU "))

    def test_phonemic_contrasts_survive_conversion(self) -> None:
        for left, right, feature in CONTRASTS:
            with self.subTest(feature=feature):
                self.assertNotEqual(
                    convert_text(self.asset, left),
                    convert_text(self.asset, right),
                    f"{feature} collapsed converting Devanagari to Sirijanga",
                )

    def test_the_contrast_marks_are_actually_emitted(self) -> None:
        emitted = {c for row in self.asset["rules"] for c in row["to"]}
        for name in ("LIMBU SIGN MUKPHRENG", "LIMBU SIGN KEMPHRENG"):
            with self.subTest(mark=name):
                self.assertIn(unicodedata.lookup(name), emitted)

    def test_mid_vowels_are_not_swapped(self) -> None:
        """The Limbu sign names invert the values, so this is easy to get backwards.

        VOWEL SIGN EE carries /e/ and VOWEL SIGN E carries /ɛ/. Plain Devanagari
        ``े`` is /e/ and the nukta-marked form is /ɛ/, so they must land that way
        round and not on the similarly named sign.
        """
        self.assertEqual(
            convert_text(self.asset, "के"),
            "ᤁᤣ",  # KA + VOWEL SIGN EE  = /ke/
        )
        self.assertEqual(
            convert_text(self.asset, "के़"),
            "ᤁᤧ",  # KA + VOWEL SIGN E   = /kɛ/
        )

    def test_agrees_with_the_independent_roman_map(self) -> None:
        """Two separately authored artifacts must produce the same Sirijanga."""
        roman = build_transliteration_map(ROMAN)
        for roman_input, devanagari in (
            ("hap", "हप्"),
            ("haq", "हॽ"),
            ("lat", "लत्"),
            ("laang", "लाङ्"),
            ("laa:ng", "लाःङ्"),
        ):
            with self.subTest(roman=roman_input):
                self.assertEqual(
                    transliterate(roman, roman_input),
                    convert_text(self.asset, devanagari),
                )

    def test_a_coda_becomes_a_small_letter(self) -> None:
        # Devanagari spells a coda consonant + virama; Limbu has a dedicated letter.
        self.assertEqual(convert_text(self.asset, "क्"), "ᤰ")   # SMALL LETTER KA
        self.assertEqual(convert_text(self.asset, "ङ्"), "ᤱ")   # SMALL LETTER NGA

    def test_unshared_punctuation_passes_through(self) -> None:
        # Limbu does not share the danda, so it is left alone rather than approximated.
        self.assertEqual(convert_text(self.asset, "।"), "।")

    def test_source_declares_why_it_is_lossy(self) -> None:
        note = json.loads(SOURCE.read_text(encoding="utf-8"))["note"]
        self.assertIn("retroflex", note)
        self.assertIn("danda", note)


if __name__ == "__main__":
    unittest.main()
