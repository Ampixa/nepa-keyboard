from __future__ import annotations

import hashlib
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from tools.build_emoji_catalog import (
    CATALOG_VERSION,
    CATEGORY_ORDER,
    EMOJI_VERSION_MIN_API,
    FITZPATRICK_MODIFIERS,
    GROUP_TO_CATEGORY,
    SOURCE_SHA256,
    EmojiCatalogError,
    build_catalog,
    canonical_bytes,
)

REPOSITORY = Path(__file__).resolve().parents[1]
CATALOG_ASSET = REPOSITORY / "android/ime-app/src/main/assets/nepa-emoji/emoji-v1.json"

HEADER = "# emoji-test.txt\n# Version: 15.1\n"


def source_text(rows: list[str]) -> str:
    return HEADER + "\n".join(rows) + "\n"


def group(name: str, subgroup: str, rows: list[str]) -> list[str]:
    return [f"# group: {name}", f"# subgroup: {subgroup}", *rows]


def minimal_source() -> str:
    rows: list[str] = []
    samples = {
        "Smileys & Emotion": ("1F600", "grinning face"),
        "Animals & Nature": ("1F436", "dog face"),
        "Food & Drink": ("1F34E", "red apple"),
        "Activities": ("26BD", "soccer ball"),
        "Travel & Places": ("1F697", "car"),
        "Objects": ("1F4A1", "light bulb"),
        "Symbols": ("2764 FE0F", "red heart"),
        "Flags": ("1F3C1", "chequered flag"),
    }
    for unicode_group, (codepoints, name) in samples.items():
        rows.extend(
            group(
                unicode_group,
                "sample",
                [f"{codepoints} ; fully-qualified # X E1.0 {name}"],
            )
        )
    return source_text(rows)


class EmojiCatalogTest(unittest.TestCase):
    def _write(self, text: str) -> Path:
        directory = Path(tempfile.mkdtemp())
        path = directory / "emoji-test.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def _build(self, text: str) -> dict:
        path = self._write(text)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        original = SOURCE_SHA256
        try:
            import tools.build_emoji_catalog as module

            module.SOURCE_SHA256 = digest
            return build_catalog(path)
        finally:
            import tools.build_emoji_catalog as module

            module.SOURCE_SHA256 = original

    def test_rejects_a_source_that_is_not_the_pinned_file(self) -> None:
        path = self._write(minimal_source())
        with self.assertRaises(EmojiCatalogError):
            build_catalog(path)

    def test_builds_every_reviewed_category_in_order(self) -> None:
        catalog = self._build(minimal_source())
        self.assertEqual(catalog["catalog_version"], CATALOG_VERSION)
        self.assertEqual(catalog["category_order"], list(CATEGORY_ORDER))
        self.assertEqual(
            [entry["id"] for entry in catalog["categories"]], list(CATEGORY_ORDER)
        )
        self.assertEqual(catalog["total_emoji"], len(CATEGORY_ORDER))

    def test_keeps_only_fully_qualified_rows(self) -> None:
        rows = group(
            "Smileys & Emotion",
            "sample",
            [
                "1F600 ; fully-qualified # X E1.0 grinning face",
                "263A ; minimally-qualified # X E1.0 smiling face",
                "1F3FB ; component # X E1.0 light skin tone",
            ],
        )
        for unicode_group in GROUP_TO_CATEGORY:
            if unicode_group == "Smileys & Emotion":
                continue
            rows.extend(
                group(unicode_group, "sample", ["1F600 ; fully-qualified # X E1.0 filler"])
            )
        with self.assertRaises(EmojiCatalogError):
            # The filler reuses one codepoint, so the duplicate guard must fire.
            self._build(source_text(rows))

    def test_excludes_skin_tone_variants(self) -> None:
        rows = list(
            group(
                "Smileys & Emotion",
                "sample",
                [
                    "1F600 ; fully-qualified # X E1.0 grinning face",
                    "1F44D 1F3FF ; fully-qualified # X E2.0 thumbs up dark skin tone",
                ],
            )
        )
        for unicode_group, codepoints in (
            ("Animals & Nature", "1F436"),
            ("Food & Drink", "1F34E"),
            ("Activities", "26BD"),
            ("Travel & Places", "1F697"),
            ("Objects", "1F4A1"),
            ("Symbols", "2764 FE0F"),
            ("Flags", "1F3C1"),
        ):
            rows.extend(
                group(unicode_group, "sample", [f"{codepoints} ; fully-qualified # X E1.0 x"])
            )
        catalog = self._build(source_text(rows))
        smileys = next(
            entry for entry in catalog["categories"] if entry["id"] == "smileys-people"
        )
        self.assertEqual(len(smileys["emoji"]), 1)
        for entry in smileys["emoji"]:
            self.assertFalse(
                any(ord(char) in FITZPATRICK_MODIFIERS for char in entry["value"])
            )

    def test_rejects_an_unmapped_group(self) -> None:
        rows = group("Nonsense", "sample", ["1F600 ; fully-qualified # X E1.0 x"])
        with self.assertRaises(EmojiCatalogError):
            self._build(source_text(rows))

    def test_rejects_a_row_before_its_group_header(self) -> None:
        with self.assertRaises(EmojiCatalogError):
            self._build(source_text(["1F600 ; fully-qualified # X E1.0 x"]))

    def test_rejects_an_empty_category(self) -> None:
        rows = group("Smileys & Emotion", "sample", ["1F600 ; fully-qualified # X E1.0 x"])
        with self.assertRaises(EmojiCatalogError):
            self._build(source_text(rows))

    def test_rejects_carriage_returns(self) -> None:
        with self.assertRaises(EmojiCatalogError):
            self._build(minimal_source().replace("\n", "\r\n"))

    def test_minimum_api_table_is_sorted_and_bounded(self) -> None:
        versions = [version for version, _ in EMOJI_VERSION_MIN_API]
        apis = [api for _, api in EMOJI_VERSION_MIN_API]
        self.assertEqual(versions, sorted(versions))
        self.assertEqual(apis, sorted(apis))
        self.assertTrue(all(api >= 21 for api in apis))


class BundledCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = json.loads(CATALOG_ASSET.read_text(encoding="utf-8"))

    def test_asset_is_canonical(self) -> None:
        self.assertEqual(CATALOG_ASSET.read_bytes(), canonical_bytes(self.catalog))

    def test_asset_declares_its_pinned_source(self) -> None:
        self.assertEqual(self.catalog["source"]["sha256"], SOURCE_SHA256)
        self.assertEqual(self.catalog["catalog_version"], CATALOG_VERSION)

    def test_every_emoji_is_unique_nfc_and_gated(self) -> None:
        seen: set[str] = set()
        total = 0
        for entry in self.catalog["categories"]:
            self.assertIn(entry["id"], CATEGORY_ORDER)
            for emoji in entry["emoji"]:
                value = emoji["value"]
                self.assertNotIn(value, seen)
                seen.add(value)
                self.assertEqual(value, unicodedata.normalize("NFC", value))
                self.assertGreaterEqual(emoji["min_api"], 21)
                self.assertFalse(
                    any(ord(char) in FITZPATRICK_MODIFIERS for char in value)
                )
                total += 1
        self.assertEqual(total, self.catalog["total_emoji"])

    def test_categories_are_in_the_reviewed_order(self) -> None:
        self.assertEqual(
            [entry["id"] for entry in self.catalog["categories"]],
            self.catalog["category_order"],
        )
        self.assertEqual(self.catalog["category_order"], list(CATEGORY_ORDER))


if __name__ == "__main__":
    unittest.main()
