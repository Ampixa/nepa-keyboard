from __future__ import annotations

import copy
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from tools.build_transliteration_map import (
    ALGORITHM,
    ASSET_VERSION,
    MAX_ROMAN_KEY,
    NORMALIZATION,
    SOURCE_FORMAT,
    SOURCE_FORMAT_VERSION,
    TransliterationError,
    build_asset,
    canonical_bytes,
    transliterate,
)

REPOSITORY = Path(__file__).resolve().parents[1]
SOURCES = REPOSITORY / "catalog/transliteration"
ASSETS = REPOSITORY / "android/ime-app/src/main/assets/nepa-translit"


def _discover_maps() -> dict[str, str]:
    """Every reviewed source, keyed to the script it declares.

    Discovered rather than listed so a new map cannot be added to the catalog
    without inheriting the whole suite; ``EXPECTED_MAPS`` below is what stops a
    map from silently disappearing instead.
    """
    discovered: dict[str, str] = {}
    for path in sorted(SOURCES.glob("*.json")):
        source = json.loads(path.read_text(encoding="utf-8"))
        discovered[path.stem] = source["output_script"]
    return discovered


MAPS = _discover_maps()
# The catalog as reviewed. Adding a language means adding it here deliberately.
EXPECTED_MAPS = {
    "npi-Latn-Deva-v0": "Deva",
    "new-Latn-Newa-v0": "Newa",
    "lif-Latn-Limb-v0": "Limb",
    "lep-Latn-Lepc-v0": "Lepc",
    "mai-Latn-Tirh-v0": "Tirh",
}


def minimal_source() -> dict:
    return {
        "source_format": SOURCE_FORMAT,
        "source_format_version": SOURCE_FORMAT_VERSION,
        "map_id": "test-Latn-Deva-v0",
        "language": "npi",
        "source_script": "Latn",
        "output_script": "Deva",
        "inherent_vowel": "a",
        "final_consonant": "inherent",
        "explicit_virama": "_",
        "virama": ["DEVANAGARI SIGN VIRAMA"],
        "consonants": {"k": ["DEVANAGARI LETTER KA"]},
        "independent_vowels": {
            "a": ["DEVANAGARI LETTER A"],
            "aa": ["DEVANAGARI LETTER AA"],
        },
        "vowel_signs": {"a": [], "aa": ["DEVANAGARI VOWEL SIGN AA"]},
        "standalone": {},
        "words": {},
        "vectors": [],
    }


class TransliterationCompilerTest(unittest.TestCase):
    def _build(self, source: dict):
        directory = Path(tempfile.mkdtemp())
        path = directory / "map.json"
        path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        return build_asset(path)

    def test_builds_a_minimal_map(self) -> None:
        asset = self._build(minimal_source())
        self.assertEqual(asset["asset_version"], ASSET_VERSION)
        self.assertEqual(asset["algorithm"], ALGORITHM)
        self.assertEqual(asset["normalization"], NORMALIZATION)

    def test_rejects_an_unresolvable_unicode_name(self) -> None:
        source = minimal_source()
        source["consonants"]["k"] = ["DEVANAGARI LETTER NOT A REAL LETTER"]
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_rejects_a_character_outside_the_declared_script(self) -> None:
        source = minimal_source()
        source["consonants"]["k"] = ["NEWA LETTER KA"]
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_rejects_unsupported_roman_input(self) -> None:
        source = minimal_source()
        source["consonants"]["k~"] = ["DEVANAGARI LETTER KA"]
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_rejects_an_overlong_roman_key(self) -> None:
        source = minimal_source()
        source["consonants"]["k" * (MAX_ROMAN_KEY + 1)] = ["DEVANAGARI LETTER KA"]
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_rejects_an_inherent_vowel_that_renders_a_sign(self) -> None:
        source = minimal_source()
        source["vowel_signs"]["a"] = ["DEVANAGARI VOWEL SIGN AA"]
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_rejects_a_vowel_sign_without_an_independent_form(self) -> None:
        source = minimal_source()
        source["vowel_signs"]["ii"] = ["DEVANAGARI VOWEL SIGN II"]
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_rejects_an_unsupported_output_script(self) -> None:
        source = minimal_source()
        source["output_script"] = "Latn"
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_requires_a_virama_unless_the_script_has_none(self) -> None:
        source = minimal_source()
        source["virama"] = []
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_final_form_maps_must_not_declare_a_virama(self) -> None:
        source = minimal_source()
        source["final_consonant"] = "final_form"
        source["final_forms"] = {"k": ["DEVANAGARI LETTER KA"]}
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_final_form_maps_require_final_forms(self) -> None:
        source = minimal_source()
        source["final_consonant"] = "final_form"
        source["virama"] = []
        source["explicit_virama"] = ""
        with self.assertRaises(TransliterationError):
            self._build(source)

    def test_final_forms_must_name_declared_consonants(self) -> None:
        source = minimal_source()
        source["final_consonant"] = "final_form"
        source["virama"] = []
        source["explicit_virama"] = ""
        source["final_forms"] = {"zzz": ["DEVANAGARI LETTER KA"]}
        with self.assertRaises(TransliterationError):
            self._build(source)


class TransliterationEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = Path(tempfile.mkdtemp())
        path = directory / "map.json"
        path.write_text(json.dumps(minimal_source(), ensure_ascii=False), encoding="utf-8")
        self.asset = build_asset(path)

    def test_consonant_takes_the_inherent_vowel_at_the_end(self) -> None:
        self.assertEqual(transliterate(self.asset, "ka"), "क")
        self.assertEqual(transliterate(self.asset, "k"), "क")

    def test_explicit_virama_produces_a_dead_consonant(self) -> None:
        self.assertEqual(transliterate(self.asset, "k_"), "क्")

    def test_vowel_sign_attaches_to_a_consonant(self) -> None:
        self.assertEqual(transliterate(self.asset, "kaa"), "का")

    def test_a_leading_vowel_uses_its_independent_form(self) -> None:
        self.assertEqual(transliterate(self.asset, "aa"), "आ")

    def test_a_medial_consonant_without_a_vowel_is_dead(self) -> None:
        self.assertEqual(transliterate(self.asset, "kka"), "क्क")

    def test_unmapped_input_passes_through(self) -> None:
        self.assertEqual(transliterate(self.asset, "?"), "?")

    def test_output_is_normalized(self) -> None:
        produced = transliterate(self.asset, "kaa")
        self.assertEqual(produced, unicodedata.normalize(NORMALIZATION, produced))

    def test_a_whole_word_override_wins(self) -> None:
        source = minimal_source()
        source["words"] = {"ka": ["DEVANAGARI LETTER AA"]}
        directory = Path(tempfile.mkdtemp())
        path = directory / "map.json"
        path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        asset = build_asset(path)
        self.assertEqual(transliterate(asset, "ka"), "आ")


class BundledMapsTest(unittest.TestCase):
    def test_catalog_matches_the_reviewed_map_set(self) -> None:
        # Catches both directions: an unreviewed map appearing in the catalog,
        # and a reviewed map being removed or having its script changed.
        self.assertEqual(EXPECTED_MAPS, MAPS)

    def test_every_map_builds_and_matches_its_asset(self) -> None:
        for map_id in MAPS:
            with self.subTest(map_id=map_id):
                asset = build_asset(SOURCES / f"{map_id}.json")
                self.assertEqual(
                    (ASSETS / f"{map_id.rsplit('-', 1)[0]}-v1.json").read_bytes(),
                    canonical_bytes(asset),
                )

    def test_every_declared_vector_holds(self) -> None:
        for map_id in MAPS:
            source_path = SOURCES / f"{map_id}.json"
            asset = build_asset(source_path)
            source = json.loads(source_path.read_text(encoding="utf-8"))
            self.assertTrue(source["vectors"], f"{map_id} declares no vectors")
            for vector in source["vectors"]:
                with self.subTest(map_id=map_id, input=vector["input"]):
                    self.assertEqual(
                        transliterate(asset, vector["input"]), vector["output"]
                    )

    def test_every_output_stays_inside_its_script(self) -> None:
        # Checked against Unicode character names rather than against the
        # compiler's own range table: repeating that table here would only
        # restate what the compiler already enforced, and would not catch a
        # range that is itself wrong.
        prefixes = {
            "Deva": "DEVANAGARI ",
            "Newa": "NEWA ",
            "Limb": "LIMBU ",
            "Lepc": "LEPCHA ",
            "Tirh": "TIRHUTA ",
        }
        self.assertEqual(
            set(prefixes),
            set(EXPECTED_MAPS.values()),
            "every reviewed script needs a Unicode name prefix to check against",
        )
        for map_id, script in MAPS.items():
            asset = build_asset(SOURCES / f"{map_id}.json")
            for section in ("consonants", "independent_vowels", "vowel_signs",
                            "standalone", "final_forms"):
                for key, value in asset.get(section, {}).items():
                    for character in value:
                        with self.subTest(map_id=map_id, key=key):
                            name = unicodedata.name(character)
                            self.assertTrue(
                                name.startswith(prefixes[script]),
                                f"{name} is not {script} (key {key!r})",
                            )

    def test_final_form_maps_declare_no_virama(self) -> None:
        # Limbu and Lepcha both close a syllable with a dedicated letter. Leaving
        # a virama declared as well would give two contradictory ways to do it.
        checked = 0
        for map_id in MAPS:
            asset = build_asset(SOURCES / f"{map_id}.json")
            if asset["final_consonant"] != "final_form":
                continue
            with self.subTest(map_id=map_id):
                self.assertEqual(asset["virama"], "")
                self.assertEqual(asset["explicit_virama"], "")
                self.assertTrue(asset["final_forms"])
            checked += 1
        self.assertEqual(checked, 2, "expected Limbu and Lepcha to use final forms")

    def test_devanagari_and_newa_share_their_key_conventions(self) -> None:
        deva = build_asset(SOURCES / "npi-Latn-Deva-v0.json")
        newa = build_asset(SOURCES / "new-Latn-Newa-v0.json")
        shared = set(deva["consonants"]) & set(newa["consonants"])
        self.assertGreater(len(shared), 25)
        self.assertEqual(deva["inherent_vowel"], newa["inherent_vowel"])
        for key in ("aa", "i", "u", "e", "o"):
            self.assertIn(key, deva["vowel_signs"])
            self.assertIn(key, newa["vowel_signs"])

    def test_assets_are_deterministic(self) -> None:
        for map_id in MAPS:
            first = build_asset(SOURCES / f"{map_id}.json")
            second = build_asset(SOURCES / f"{map_id}.json")
            self.assertEqual(canonical_bytes(first), canonical_bytes(second))
            self.assertEqual(first, copy.deepcopy(second))


if __name__ == "__main__":
    unittest.main()
