"""Compile the reviewed transliteration-profile catalog.

A profile in the generated lock becomes selectable only when it carries a
dictionary pack, because the lock models Roman input as an alias decoder. That
is the right gate for dictionary-backed input and the wrong one for a language
that has no dictionary at all -- which is exactly the case for the languages
this project targets.

This compiler produces a separate, additive artifact. It never edits the
profile lock and never contradicts it: the lock's statement "this profile has
no pack, so it cannot do alias-decoder input" stays true. This artifact makes
an orthogonal claim -- "this profile has a verified transliteration map, so it
can do deterministic transliteration input" -- with its own evidence and its
own hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SOURCE_FORMAT = "nepa-transliteration-profiles-source"
SOURCE_FORMAT_VERSION = 1
ASSET_VERSION = 1
GENERATOR = "build_transliteration_profiles"

# The only layout a transliteration profile may bind: phonetic input is typed on
# a Latin keyboard, so binding anything else would misdescribe the input surface.
REQUIRED_LAYOUT_ID = "latn-qwerty-us-v1"
# Only the Roman-input slot may be granted transliteration.
REQUIRED_METHOD_TYPE = "roman_phonetic"
# Transliteration may only be granted where the block is the missing dictionary.
GRANTABLE_BLOCKED_REASONS = {
    "ROMAN_ALIAS_NOT_INTERNAL_READY",
    "ROMAN_ALIAS_NOT_RELEASE_APPROVED",
}
REQUIRED_GATES = ("deterministic_build", "map_verified", "layout_implemented")
MAX_PROFILES = 64


class ProfileError(Exception):
    """A transliteration-profile catalog that must not ship."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProfileError(message)


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_asset(
    source_path: Path,
    profile_lock_path: Path,
    asset_directory: Path,
    map_source_directory: Path,
) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    _require(
        source.get("source_format") == SOURCE_FORMAT,
        f"source_format must be {SOURCE_FORMAT}",
    )
    _require(
        source.get("source_format_version") == SOURCE_FORMAT_VERSION,
        f"source_format_version must be {SOURCE_FORMAT_VERSION}",
    )
    catalog_id = source.get("catalog_id")
    _require(bool(isinstance(catalog_id, str) and catalog_id), "catalog_id is required")
    authority = source.get("authority")
    _require(authority in {"internal", "release"}, "authority must be internal or release")

    lock_bytes = profile_lock_path.read_bytes()
    lock = json.loads(lock_bytes.decode("utf-8"))
    by_id = {row["profile_id"]: row for row in lock.get("profiles", [])}
    _require(bool(by_id), "profile lock declares no profiles")

    declared = source.get("profiles")
    _require(bool(isinstance(declared, list) and declared), "profiles must be a non-empty list")
    _require(len(declared) <= MAX_PROFILES, f"at most {MAX_PROFILES} profiles are supported")

    compiled: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(declared):
        where = f"profiles[{index}]"
        _require(isinstance(entry, dict), f"{where} must be an object")
        expected = {"profile_id", "map_id", "map_asset", "layout_id", "gates", "note"}
        _require(
            set(entry) == expected,
            f"{where} fields must be exactly {sorted(expected)}, got {sorted(entry)}",
        )
        profile_id = entry["profile_id"]
        _require(profile_id not in seen, f"{where} duplicates profile {profile_id}")
        seen.add(profile_id)

        row = by_id.get(profile_id)
        _require(row is not None, f"{where} names unknown profile {profile_id}")
        assert row is not None

        # The profile must be the Roman-input slot on the Latin layout.
        _require(
            row.get("method_type") == REQUIRED_METHOD_TYPE,
            f"{where} profile {profile_id} is {row.get('method_type')}, "
            f"not {REQUIRED_METHOD_TYPE}",
        )
        _require(
            row.get("layout_id") == REQUIRED_LAYOUT_ID == entry["layout_id"],
            f"{where} profile {profile_id} must bind {REQUIRED_LAYOUT_ID}",
        )
        # Never contradict the lock: only grant where the block is the missing pack.
        blocked = row.get("blocked_reason")
        _require(
            blocked in GRANTABLE_BLOCKED_REASONS,
            f"{where} profile {profile_id} is blocked as {blocked!r}, which is not a "
            "missing-dictionary block and must not be granted transliteration",
        )
        _require(
            not row.get("pack_binding"),
            f"{where} profile {profile_id} already has a pack binding",
        )

        gates = entry["gates"]
        _require(
            isinstance(gates, list) and tuple(gates) == REQUIRED_GATES,
            f"{where} gates must be exactly {list(REQUIRED_GATES)}",
        )

        map_source = map_source_directory / f"{entry['map_id']}.json"
        _require(map_source.is_file(), f"{where} names missing map source {map_source}")
        asset_path = asset_directory / entry["map_asset"]
        _require(asset_path.is_file(), f"{where} names missing map asset {asset_path}")
        asset = json.loads(asset_path.read_text(encoding="utf-8"))
        _require(
            asset.get("map_id") == entry["map_id"],
            f"{where} asset declares map {asset.get('map_id')}, expected {entry['map_id']}",
        )
        _require(
            asset.get("output_script") == row.get("output_script"),
            f"{where} map emits {asset.get('output_script')} but profile "
            f"{profile_id} declares {row.get('output_script')}",
        )
        _require(
            bool(isinstance(entry["note"], str) and entry["note"].strip()),
            f"{where} needs a note explaining why transliteration is the input method",
        )

        compiled.append(
            {
                "profile_id": profile_id,
                "map_id": entry["map_id"],
                "map_asset": entry["map_asset"],
                "map_sha256": _sha256(asset_path),
                "map_source_sha256": _sha256(map_source),
                "layout_id": entry["layout_id"],
                "output_script": asset["output_script"],
                "gates": list(REQUIRED_GATES),
                "granted_over_blocked_reason": blocked,
            }
        )

    compiled.sort(key=lambda row: row["profile_id"])
    return {
        "asset_version": ASSET_VERSION,
        "generator": GENERATOR,
        "catalog_id": catalog_id,
        "authority": authority,
        "profile_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "profile_count": len(compiled),
        "profiles": compiled,
        "source_sha256": _sha256(source_path),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--profile-lock", type=Path, required=True)
    parser.add_argument("--asset-directory", type=Path, required=True)
    parser.add_argument("--map-source-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        asset = build_asset(
            args.source,
            args.profile_lock,
            args.asset_directory,
            args.map_source_directory,
        )
    except ProfileError as failure:
        print(f"transliteration_profiles_error={failure}", file=sys.stderr)
        return 2

    encoded = _canonical_bytes(asset)
    if args.check:
        if not args.output.is_file():
            print("transliteration_profiles_check=missing", file=sys.stderr)
            return 3
        if args.output.read_bytes() != encoded:
            print("transliteration_profiles_check=drifted", file=sys.stderr)
            return 3
        print(
            f"transliteration_profiles_check=ok catalog={asset['catalog_id']} "
            f"profiles={asset['profile_count']}"
        )
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(f"transliteration_profiles_catalog={asset['catalog_id']}")
    print(f"transliteration_profiles_count={asset['profile_count']}")
    print(f"transliteration_profiles_sha256={hashlib.sha256(encoded).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
