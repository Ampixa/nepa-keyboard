from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.build_key_alternates import (
    ASSET_VERSION,
    MAX_ALTERNATES_PER_KEY,
    SOURCE_FORMAT,
    SOURCE_FORMAT_VERSION,
    KeyAlternatesError,
    build_asset,
    canonical_bytes,
)

REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "catalog/key-alternates-v0.json"
LOCK = REPOSITORY / "layouts/internal/layouts-v1.lock.json"
ASSET = REPOSITORY / "android/ime-app/src/main/assets/nepa-layouts/key-alternates-v1.json"


class KeyAlternatesBuilderTest(unittest.TestCase):
    def _build_from(self, source: dict) -> dict:
        directory = Path(tempfile.mkdtemp())
        path = directory / "key-alternates.json"
        path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        return build_asset(path, LOCK)

    def _valid_source(self) -> dict:
        return {
            "source_format": SOURCE_FORMAT,
            "source_format_version": SOURCE_FORMAT_VERSION,
            "layouts": [
                {
                    "layout_id": "deva-nepal-basic-v1",
                    "keys": [
                        {"key_id": "base.r0.k0", "text": "ट", "alternates": ["ठ"]}
                    ],
                }
            ],
        }

    def test_builds_a_valid_source(self) -> None:
        asset = self._build_from(self._valid_source())
        self.assertEqual(asset["asset_version"], ASSET_VERSION)
        self.assertEqual(asset["total_keys"], 1)

    def test_rejects_an_unknown_layout(self) -> None:
        source = self._valid_source()
        source["layouts"][0]["layout_id"] = "no-such-layout-v1"
        with self.assertRaises(KeyAlternatesError):
            self._build_from(source)

    def test_rejects_a_key_the_layout_does_not_render(self) -> None:
        source = self._valid_source()
        source["layouts"][0]["keys"][0]["key_id"] = "base.r9.k9"
        with self.assertRaises(KeyAlternatesError):
            self._build_from(source)

    def test_rejects_text_that_no_longer_matches_the_compiled_key(self) -> None:
        source = self._valid_source()
        source["layouts"][0]["keys"][0]["text"] = "क"
        with self.assertRaises(KeyAlternatesError):
            self._build_from(source)

    def test_rejects_a_scalar_the_layout_cannot_emit(self) -> None:
        source = self._valid_source()
        # A Newa scalar is outside the Devanagari layout's repertoire.
        source["layouts"][0]["keys"][0]["alternates"] = ["\U0001140e"]
        with self.assertRaises(KeyAlternatesError):
            self._build_from(source)

    def test_rejects_a_conjunct_joiner(self) -> None:
        source = self._valid_source()
        source["layouts"][0]["keys"][0]["alternates"] = ["‍"]
        with self.assertRaises(KeyAlternatesError):
            self._build_from(source)

    def test_rejects_a_variant_that_repeats_the_key(self) -> None:
        source = self._valid_source()
        source["layouts"][0]["keys"][0]["alternates"] = ["ट"]
        with self.assertRaises(KeyAlternatesError):
            self._build_from(source)

    def test_rejects_duplicate_variants(self) -> None:
        source = self._valid_source()
        source["layouts"][0]["keys"][0]["alternates"] = ["ठ", "ठ"]
        with self.assertRaises(KeyAlternatesError):
            self._build_from(source)

    def test_rejects_duplicate_keys(self) -> None:
        source = self._valid_source()
        source["layouts"][0]["keys"].append(
            {"key_id": "base.r0.k0", "text": "ट", "alternates": ["ठ"]}
        )
        with self.assertRaises(KeyAlternatesError):
            self._build_from(source)

    def test_rejects_an_empty_or_oversized_variant_list(self) -> None:
        for values in ([], ["ठ"] * (MAX_ALTERNATES_PER_KEY + 1)):
            source = self._valid_source()
            source["layouts"][0]["keys"][0]["alternates"] = values
            with self.assertRaises(KeyAlternatesError):
                self._build_from(source)

    def test_rejects_an_unsupported_format(self) -> None:
        source = self._valid_source()
        source["source_format_version"] = 99
        with self.assertRaises(KeyAlternatesError):
            self._build_from(source)


class BundledKeyAlternatesTest(unittest.TestCase):
    def test_asset_matches_its_reviewed_source_and_lock(self) -> None:
        asset = build_asset(SOURCE, LOCK)
        self.assertEqual(ASSET.read_bytes(), canonical_bytes(asset))

    def test_asset_binds_the_reviewed_layout_lock(self) -> None:
        asset = json.loads(ASSET.read_text(encoding="utf-8"))
        import hashlib

        self.assertEqual(
            asset["layout_lock_sha256"],
            hashlib.sha256(LOCK.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            asset["source_sha256"],
            hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        )

    def test_every_variant_is_reachable_from_the_layout(self) -> None:
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        asset = json.loads(ASSET.read_text(encoding="utf-8"))
        for layout in asset["layouts"]:
            compiled = next(
                entry
                for entry in lock["layouts"]
                if entry["layout_id"] == layout["layout_id"]
            )
            available: set[str] = set()
            for layer in compiled["layers"].values():
                for row in layer["rows"]:
                    for key in row:
                        if key.get("text"):
                            available.update(key["text"])
            for key in layout["keys"]:
                for alternate in key["alternates"]:
                    self.assertTrue(set(alternate) <= available, alternate)


if __name__ == "__main__":
    unittest.main()
