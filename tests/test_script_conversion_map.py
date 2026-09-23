from __future__ import annotations

import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from tools.build_script_conversion_map import (
    ASSET_VERSION,
    GENERATOR,
    ScriptConversionError,
    _canonical_bytes,
    build_asset,
    convert_text,
)
from tools.build_transliteration_map import transliterate

REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "catalog/script-conversion/mai-Deva-Tirh-v0.json"
ASSET = REPOSITORY / "android/ime-app/src/main/assets/nepa-conversions/mai-Deva-Tirh-v1.json"
TRANSLIT = REPOSITORY / "android/ime-app/src/main/assets/nepa-translit"


def _source() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def _build(source: dict):
    directory = Path(tempfile.mkdtemp())
    path = directory / "map.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    return build_asset(path)


class ScriptConversionCompilerTest(unittest.TestCase):
    def test_builds_the_reviewed_source(self) -> None:
        asset = build_asset(SOURCE)
        self.assertEqual(asset["asset_version"], ASSET_VERSION)
        self.assertEqual(asset["generator"], GENERATOR)
        self.assertEqual(asset["source_script"], "Deva")
        self.assertEqual(asset["output_script"], "Tirh")
        self.assertEqual(asset["rule_count"], len(asset["rules"]))

    def test_matches_the_shipped_asset(self) -> None:
        self.assertEqual(ASSET.read_bytes(), _canonical_bytes(build_asset(SOURCE)))

    def test_rules_are_longest_first(self) -> None:
        lengths = [len(row["from"]) for row in build_asset(SOURCE)["rules"]]
        self.assertEqual(lengths, sorted(lengths, reverse=True))

    def test_every_rule_crosses_script(self) -> None:
        for row in build_asset(SOURCE)["rules"]:
            with self.subTest(source=row["from"]):
                for character in row["from"]:
                    self.assertTrue(unicodedata.name(character).startswith("DEVANAGARI "))
                for character in row["to"]:
                    self.assertTrue(unicodedata.name(character).startswith("TIRHUTA "))

    def test_rejects_an_unknown_character_name(self) -> None:
        source = _source()
        source["rules"][0]["from"] = ["DEVANAGARI LETTER NOT REAL"]
        with self.assertRaises(ScriptConversionError):
            _build(source)

    def test_rejects_output_in_the_source_script(self) -> None:
        source = _source()
        source["rules"][0]["to"] = ["DEVANAGARI LETTER KA"]
        with self.assertRaises(ScriptConversionError):
            _build(source)

    def test_rejects_a_map_that_does_not_change_script(self) -> None:
        source = _source()
        source["output_script"] = "Deva"
        with self.assertRaises(ScriptConversionError):
            _build(source)

    def test_rejects_duplicate_source_text(self) -> None:
        source = _source()
        source["rules"].append(dict(source["rules"][0]))
        with self.assertRaises(ScriptConversionError):
            _build(source)

    def test_unmapped_input_passes_through(self) -> None:
        asset = build_asset(SOURCE)
        # The danda has no same-named Tirhuta counterpart and is deliberately unmapped.
        self.assertEqual(convert_text(asset, "।"), "।")

    def test_agrees_with_the_independent_transliteration_maps(self) -> None:
        """Roman->Deva->Tirh must equal Roman->Tirh.

        The converter and the two transliteration maps were built separately, so
        agreement across them is real evidence rather than a restatement.
        """
        converter = build_asset(SOURCE)
        deva = json.loads((TRANSLIT / "npi-Latn-Deva-v1.json").read_text(encoding="utf-8"))
        tirhuta = json.loads((TRANSLIT / "mai-Latn-Tirh-v1.json").read_text(encoding="utf-8"))
        for roman in (
            "ka", "kaa", "ki", "k_", "kaam", "maithili", "mithilaa",
            "a", "i", "raamro", "nepaal", "5", "gharmaa", "chha", "himaal",
        ):
            with self.subTest(roman=roman):
                self.assertEqual(
                    convert_text(converter, transliterate(deva, roman)),
                    transliterate(tirhuta, roman),
                )


if __name__ == "__main__":
    unittest.main()
