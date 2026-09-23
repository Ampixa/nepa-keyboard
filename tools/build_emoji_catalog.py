#!/usr/bin/env python3
"""Build the deterministic bundled emoji catalog from a pinned Unicode data file.

The catalog is the only emoji source the keyboard reads at runtime. It is derived
from `emoji-test.txt` (UTS #51) so the repertoire, ordering, and category grouping
are reproducible from an exactly pinned input rather than hand curation.

Emoji are gated by the Android release that first shipped their Unicode emoji
version, so an older device never renders a row of missing-glyph boxes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

SOURCE_SHA256 = "d876ee249aa28eaa76cfa6dfaa702847a8d13b062aa488d465d0395ee8137ed9"
SOURCE_FILENAME = "emoji-test.txt"
SOURCE_EMOJI_VERSION = "15.1"
CATALOG_VERSION = 1

# Reviewed panel order. Unicode groups are merged into the categories the product
# shows; every retained group must map to exactly one category.
CATEGORY_ORDER = (
    "smileys-people",
    "animals-nature",
    "food-drink",
    "activities",
    "travel-places",
    "objects",
    "symbols",
    "flags",
)
GROUP_TO_CATEGORY = {
    "Smileys & Emotion": "smileys-people",
    "People & Body": "smileys-people",
    "Animals & Nature": "animals-nature",
    "Food & Drink": "food-drink",
    "Activities": "activities",
    "Travel & Places": "travel-places",
    "Objects": "objects",
    "Symbols": "symbols",
    "Flags": "flags",
}
# Component-only group; never shown as a standalone key.
IGNORED_GROUPS = {"Component"}

# First Android API level that shipped each Unicode emoji version's glyphs.
EMOJI_VERSION_MIN_API = (
    # E0.6 and E0.7 predate the versioned releases and shipped with the platform.
    (0.6, 21),
    (0.7, 21),
    (1.0, 21),
    (2.0, 21),
    (3.0, 22),
    (4.0, 24),
    (5.0, 26),
    (11.0, 28),
    (12.0, 29),
    (12.1, 29),
    (13.0, 30),
    (13.1, 31),
    (14.0, 32),
    (15.0, 34),
    (15.1, 34),
)
MAX_SUPPORTED_EMOJI_VERSION = 15.1
FITZPATRICK_MODIFIERS = frozenset(range(0x1F3FB, 0x1F400))

DATA_LINE = re.compile(
    r"^(?P<codepoints>[0-9A-F ]+);\s*(?P<status>[a-z-]+)\s*#\s*\S+\s+E(?P<version>\d+\.\d+)\s+(?P<name>.+)$"
)
GROUP_LINE = re.compile(r"^# group: (?P<group>.+)$")
SUBGROUP_LINE = re.compile(r"^# subgroup: (?P<subgroup>.+)$")


class EmojiCatalogError(RuntimeError):
    """Raised when the pinned input or derived catalog violates the contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _minimum_api(emoji_version: float) -> int:
    selected = None
    for version, api in EMOJI_VERSION_MIN_API:
        if emoji_version >= version:
            selected = api
    if selected is None:
        raise EmojiCatalogError(f"no Android mapping for emoji version {emoji_version}")
    return selected


def _parse(source: Path) -> list[dict[str, Any]]:
    if source.is_symlink() or not source.is_file():
        raise EmojiCatalogError(f"emoji source must be a regular file: {source}")
    rows: list[dict[str, Any]] = []
    group = None
    subgroup = None
    seen: set[str] = set()
    # Read bytes: text mode normalizes newlines, which would silently accept CRLF.
    raw = source.read_bytes()
    if b"\r" in raw:
        raise EmojiCatalogError("emoji source must not contain carriage returns")
    text = raw.decode("utf-8")
    for raw in text.split("\n"):
        group_match = GROUP_LINE.match(raw)
        if group_match:
            group = group_match.group("group").strip()
            continue
        subgroup_match = SUBGROUP_LINE.match(raw)
        if subgroup_match:
            subgroup = subgroup_match.group("subgroup").strip()
            continue
        if raw.startswith("#") or not raw.strip():
            continue
        match = DATA_LINE.match(raw.strip())
        if not match:
            continue
        if match.group("status") != "fully-qualified":
            continue
        if group is None or subgroup is None:
            raise EmojiCatalogError("emoji data row appeared before its group header")
        if group in IGNORED_GROUPS:
            continue
        category = GROUP_TO_CATEGORY.get(group)
        if category is None:
            raise EmojiCatalogError(f"unmapped emoji group: {group}")
        codepoints = [int(value, 16) for value in match.group("codepoints").split()]
        # Skin-tone variants are excluded; the panel presents one neutral form.
        if any(point in FITZPATRICK_MODIFIERS for point in codepoints):
            continue
        emoji_version = float(match.group("version"))
        if emoji_version > MAX_SUPPORTED_EMOJI_VERSION:
            raise EmojiCatalogError(f"unexpected emoji version: {emoji_version}")
        value = "".join(chr(point) for point in codepoints)
        if value != unicodedata.normalize("NFC", value):
            raise EmojiCatalogError(f"emoji is not NFC: {value!r}")
        if value in seen:
            raise EmojiCatalogError(f"duplicate emoji: {value!r}")
        seen.add(value)
        rows.append(
            {
                "value": value,
                "category": category,
                "name": match.group("name").strip(),
                "min_api": _minimum_api(emoji_version),
                "emoji_version": match.group("version"),
            }
        )
    if not rows:
        raise EmojiCatalogError("emoji source produced no rows")
    return rows


def build_catalog(source: Path) -> dict[str, Any]:
    actual_sha256 = _sha256(source)
    if actual_sha256 != SOURCE_SHA256:
        raise EmojiCatalogError(
            f"emoji source is not the pinned file: expected {SOURCE_SHA256}, got {actual_sha256}"
        )
    rows = _parse(source)
    categories = []
    for category in CATEGORY_ORDER:
        members = [row for row in rows if row["category"] == category]
        if not members:
            raise EmojiCatalogError(f"category is empty: {category}")
        categories.append(
            {
                "id": category,
                "emoji": [
                    {"value": row["value"], "min_api": row["min_api"]} for row in members
                ],
            }
        )
    return {
        "catalog_version": CATALOG_VERSION,
        "generator": "build_emoji_catalog",
        "source": {
            "filename": SOURCE_FILENAME,
            "emoji_version": SOURCE_EMOJI_VERSION,
            "sha256": SOURCE_SHA256,
        },
        "category_order": list(CATEGORY_ORDER),
        "total_emoji": sum(len(entry["emoji"]) for entry in categories),
        "categories": categories,
    }


def canonical_bytes(catalog: dict[str, Any]) -> bytes:
    return (
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the existing output instead of writing it",
    )
    args = parser.parse_args(argv)

    catalog = build_catalog(args.source.resolve())
    payload = canonical_bytes(catalog)
    if args.check:
        if not args.output.is_file():
            raise EmojiCatalogError(f"missing catalog: {args.output}")
        if args.output.read_bytes() != payload:
            raise EmojiCatalogError("catalog does not match its pinned source")
        print(f"emoji_catalog_check=ok total={catalog['total_emoji']}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"emoji_catalog_sha256={hashlib.sha256(payload).hexdigest()}")
    print(f"emoji_total={catalog['total_emoji']}")
    for entry in catalog["categories"]:
        print(f"  {entry['id']}={len(entry['emoji'])}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except EmojiCatalogError as failure:
        print(f"error: {failure}", file=sys.stderr)
        sys.exit(2)
