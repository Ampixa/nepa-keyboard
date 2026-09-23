from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.build_transliteration_map import (
    TransliterationError,
    build_asset,
    transliterate,
)

REPOSITORY = Path(__file__).resolve().parents[1]
SOURCES = REPOSITORY / "catalog/transliteration"
LIMBU = SOURCES / "lif-Latn-Limb-v0.json"

# Maps whose language has a phonemic contrast the script encodes. A map listed
# here must declare it, so the contrast cannot be dropped by deleting a field.
CONTRAST_BEARING = {
    "lif-Latn-Limb-v0": {
        "LIMBU SIGN MUKPHRENG",   # glottal stop
        "LIMBU SIGN KEMPHRENG",   # vowel length
    },
}


def _build(source: dict):
    directory = Path(tempfile.mkdtemp())
    path = directory / "map.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    return build_asset(path)


def _limbu() -> dict:
    return json.loads(LIMBU.read_text(encoding="utf-8"))


class ContrastInvariantTest(unittest.TestCase):
    def test_contrast_bearing_maps_declare_their_marks(self) -> None:
        for map_id, required in CONTRAST_BEARING.items():
            with self.subTest(map_id=map_id):
                source = json.loads(
                    (SOURCES / f"{map_id}.json").read_text(encoding="utf-8")
                )
                self.assertTrue(
                    required.issubset(set(source.get("required_characters", []))),
                    f"{map_id} must declare {sorted(required)} as required",
                )
                self.assertTrue(source.get("contrasts"), f"{map_id} declares no contrasts")

    def test_declared_contrasts_render_distinctly(self) -> None:
        source = _limbu()
        asset = build_asset(LIMBU)
        for contrast in source["contrasts"]:
            left, right = contrast["pair"]
            with self.subTest(feature=contrast["feature"], pair=contrast["pair"]):
                self.assertNotEqual(
                    transliterate(asset, left),
                    transliterate(asset, right),
                    f"{contrast['feature']} collapsed",
                )

    def test_removing_the_glottal_key_is_rejected(self) -> None:
        source = _limbu()
        source["consonants"].pop("q")
        source["final_forms"].pop("q")
        with self.assertRaisesRegex(TransliterationError, "MUKPHRENG"):
            _build(source)

    def test_removing_the_length_keys_is_rejected(self) -> None:
        source = _limbu()
        for table in ("vowel_signs", "independent_vowels"):
            for key in [k for k in source[table] if k.endswith(":")]:
                source[table].pop(key)
        with self.assertRaisesRegex(TransliterationError, "KEMPHRENG"):
            _build(source)

    def test_collapsing_a_contrast_is_rejected(self) -> None:
        # The mark is still emitted somewhere, so only the pair check can catch this.
        source = _limbu()
        source["final_forms"]["q"] = ["LIMBU SMALL LETTER PA"]
        with self.assertRaisesRegex(TransliterationError, "collapses"):
            _build(source)

    def test_a_contrast_needs_exactly_two_sides(self) -> None:
        source = _limbu()
        source["contrasts"][0]["pair"] = ["hap"]
        with self.assertRaisesRegex(TransliterationError, "exactly two"):
            _build(source)

    def test_required_characters_must_be_real_unicode_names(self) -> None:
        source = _limbu()
        source["required_characters"].append("LIMBU SIGN NOT A REAL MARK")
        with self.assertRaisesRegex(TransliterationError, "not a Unicode name"):
            _build(source)

    def test_glottal_contrasts_with_every_final_stop(self) -> None:
        """The grammar's contrast set is /p t k/ against /ʔ/, so all three must differ."""
        asset = build_asset(LIMBU)
        glottal = transliterate(asset, "haq")
        for stop in ("hap", "hat", "hak"):
            with self.subTest(stop=stop):
                self.assertNotEqual(transliterate(asset, stop), glottal)

    def test_length_is_orthogonal_to_vowel_quality(self) -> None:
        """Lengthening must add a mark, not change which vowel is written."""
        asset = build_asset(LIMBU)
        for short, long_ in (("kaa", "kaa:"), ("ki", "ki:"), ("ku", "ku:")):
            with self.subTest(pair=(short, long_)):
                rendered_short = transliterate(asset, short)
                rendered_long = transliterate(asset, long_)
                self.assertNotEqual(rendered_short, rendered_long)
                self.assertTrue(
                    rendered_long.startswith(rendered_short),
                    f"{long_} should extend {short}, got {rendered_long!r}",
                )


if __name__ == "__main__":
    unittest.main()
