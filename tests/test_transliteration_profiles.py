from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.build_transliteration_profiles import (
    ASSET_VERSION,
    GENERATOR,
    REQUIRED_GATES,
    ProfileError,
    build_asset,
)

REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "catalog/transliteration-profiles-v0.json"
LOCK = REPOSITORY / "catalog/internal-profiles.lock.json"
ASSETS = REPOSITORY / "android/ime-app/src/main/assets/nepa-translit"
MAP_SOURCES = REPOSITORY / "catalog/transliteration"
GENERATED = ASSETS / "profiles-v1.json"


def _build(source: dict, lock: dict | None = None):
    directory = Path(tempfile.mkdtemp())
    source_path = directory / "profiles.json"
    source_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    lock_path = LOCK
    if lock is not None:
        lock_path = directory / "lock.json"
        lock_path.write_text(json.dumps(lock, ensure_ascii=False), encoding="utf-8")
    return build_asset(source_path, lock_path, ASSETS, MAP_SOURCES)


def _source() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def _lock() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))


def _row(lock: dict, profile_id: str) -> dict:
    for row in lock["profiles"]:
        if row["profile_id"] == profile_id:
            return row
    raise AssertionError(f"missing fixture profile {profile_id}")


class TransliterationProfileCatalogTest(unittest.TestCase):
    def test_builds_the_reviewed_catalog(self) -> None:
        asset = _build(_source())
        self.assertEqual(asset["asset_version"], ASSET_VERSION)
        self.assertEqual(asset["generator"], GENERATOR)
        self.assertEqual(asset["profile_count"], len(asset["profiles"]))
        self.assertTrue(asset["profiles"])

    def test_matches_the_generated_asset(self) -> None:
        # The shipped asset must be exactly what the reviewed source compiles to.
        # Built from the real source path, not a temp copy: the asset pins the
        # source's own SHA-256, so a re-serialised copy would not reproduce it.
        from tools.build_transliteration_profiles import _canonical_bytes

        asset = build_asset(SOURCE, LOCK, ASSETS, MAP_SOURCES)
        self.assertEqual(GENERATED.read_bytes(), _canonical_bytes(asset))

    def test_every_entry_names_a_real_blocked_profile(self) -> None:
        lock = _lock()
        for entry in _build(_source())["profiles"]:
            with self.subTest(profile=entry["profile_id"]):
                row = _row(lock, entry["profile_id"])
                self.assertEqual(row["output_script"], entry["output_script"])
                self.assertEqual(row["layout_id"], entry["layout_id"])
                # Still blocked in the lock: this catalog adds a capability, it
                # does not edit the lock or mark the profile pack-ready.
                self.assertTrue(row["blocked_reason"])
                self.assertFalse(row.get("pack_binding"))

    def test_rejects_an_unknown_profile(self) -> None:
        source = _source()
        source["profiles"][0]["profile_id"] = "zzz-Latn-Zzzz-NP"
        with self.assertRaisesRegex(ProfileError, "unknown profile"):
            _build(source)

    def test_rejects_a_block_that_is_not_a_missing_dictionary(self) -> None:
        # The safety property: a profile withheld for any other reason -- an
        # unreviewed layout, a converter gap -- must not gain input this way.
        source = _source()
        lock = _lock()
        _row(lock, source["profiles"][0]["profile_id"])["blocked_reason"] = (
            "DIRECT_PROFILE_NOT_INTERNAL_READY"
        )
        with self.assertRaisesRegex(ProfileError, "not a missing-dictionary block"):
            _build(source, lock)

    def test_rejects_a_profile_that_already_has_a_pack(self) -> None:
        source = _source()
        lock = _lock()
        _row(lock, source["profiles"][0]["profile_id"])["pack_binding"] = "lep-Lepc-NP"
        with self.assertRaisesRegex(ProfileError, "already has a pack binding"):
            _build(source, lock)

    def test_rejects_a_map_that_emits_the_wrong_script(self) -> None:
        source = _source()
        # Point the Lepcha profile at the Devanagari map.
        source["profiles"][0]["map_id"] = "npi-Latn-Deva-v0"
        source["profiles"][0]["map_asset"] = "npi-Latn-Deva-v1.json"
        with self.assertRaisesRegex(ProfileError, "but profile"):
            _build(source)

    def test_rejects_a_non_roman_method(self) -> None:
        source = _source()
        lock = _lock()
        _row(lock, source["profiles"][0]["profile_id"])["method_type"] = "direct"
        with self.assertRaisesRegex(ProfileError, "not roman_phonetic"):
            _build(source, lock)

    def test_rejects_a_layout_other_than_latin_qwerty(self) -> None:
        source = _source()
        source["profiles"][0]["layout_id"] = "deva-nepal-basic-v1"
        with self.assertRaisesRegex(ProfileError, "must bind"):
            _build(source)

    def test_rejects_a_duplicate_profile(self) -> None:
        source = _source()
        source["profiles"].append(copy.deepcopy(source["profiles"][0]))
        with self.assertRaisesRegex(ProfileError, "duplicates profile"):
            _build(source)

    def test_rejects_incomplete_gates(self) -> None:
        source = _source()
        source["profiles"][0]["gates"] = list(REQUIRED_GATES)[:-1]
        with self.assertRaisesRegex(ProfileError, "gates must be exactly"):
            _build(source)

    def test_rejects_an_unexplained_entry(self) -> None:
        source = _source()
        source["profiles"][0]["note"] = "   "
        with self.assertRaisesRegex(ProfileError, "needs a note"):
            _build(source)

    def test_rejects_a_missing_map_asset(self) -> None:
        source = _source()
        source["profiles"][0]["map_asset"] = "not-a-real-map-v1.json"
        with self.assertRaisesRegex(ProfileError, "missing map asset"):
            _build(source)

    def test_is_deterministic(self) -> None:
        self.assertEqual(_build(_source()), _build(_source()))

    def test_pins_the_lock_it_was_compiled_against(self) -> None:
        import hashlib

        asset = _build(_source())
        self.assertEqual(
            asset["profile_lock_sha256"],
            hashlib.sha256(LOCK.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
