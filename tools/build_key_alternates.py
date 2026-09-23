#!/usr/bin/env python3
"""Compile reviewed long-press key variants into a deterministic runtime asset.

Variants are held outside the layout lock on purpose. The layout compiler is bound by
a completed native-speaker review, so extending it would invalidate that review. This
artifact adds a presentation-layer capability instead: it can only attach variants to
keys that a compiled layout already renders, and every variant must be a scalar the
bound layout can already emit. It therefore cannot widen a layout's repertoire or
bypass its reviewed input policies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

SOURCE_FORMAT = "key_alternates"
SOURCE_FORMAT_VERSION = 1
ASSET_VERSION = 1
MAX_ALTERNATES_PER_KEY = 8
MAX_TEXT_SCALARS = 16
CONJUNCT_JOINERS = {"‌", "‍"}


class KeyAlternatesError(ValueError):
    """Raised when the reviewed source or the bound layout lock rejects a variant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise KeyAlternatesError(message)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_bytes()
    _require(not raw.startswith(b"\xef\xbb\xbf"), f"{label} must not contain a BOM")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as failure:
        raise KeyAlternatesError(f"{label} is not valid UTF-8 JSON: {failure}") from failure
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _compiled_keys(lock: dict[str, Any], layout_id: str) -> dict[str, dict[str, Any]]:
    """Every text key the compiled layout renders, keyed by its stable key id."""
    for layout in lock["layouts"]:
        if layout["layout_id"] != layout_id:
            continue
        keys: dict[str, dict[str, Any]] = {}
        for layer in layout["layers"].values():
            for row in layer["rows"]:
                for key in row:
                    keys[key["key_id"]] = key
        return keys
    raise KeyAlternatesError(f"layout is not in the lock: {layout_id}")


def _layout_scalars(lock: dict[str, Any], layout_id: str) -> set[str]:
    """Scalars the layout can already emit across all of its layers."""
    scalars: set[str] = set()
    for key in _compiled_keys(lock, layout_id).values():
        text = key.get("text")
        if text:
            scalars.update(text)
    return scalars


def build_asset(source_path: Path, lock_path: Path) -> dict[str, Any]:
    source = _read_json(source_path, "key-alternates source")
    lock = _read_json(lock_path, "layout lock")
    _require(
        source.get("source_format") == SOURCE_FORMAT
        and source.get("source_format_version") == SOURCE_FORMAT_VERSION,
        "key-alternates source declares an unsupported format",
    )

    compiled_layouts = []
    seen_layouts: set[str] = set()
    for entry in source["layouts"]:
        layout_id = entry["layout_id"]
        _require(layout_id not in seen_layouts, f"duplicate layout: {layout_id}")
        seen_layouts.add(layout_id)
        compiled_keys = _compiled_keys(lock, layout_id)
        available = _layout_scalars(lock, layout_id)

        rows = []
        seen_keys: set[str] = set()
        for key_entry in entry["keys"]:
            key_id = key_entry["key_id"]
            location = f"{layout_id}.{key_id}"
            _require(key_id not in seen_keys, f"{location} is a duplicate key")
            seen_keys.add(key_id)

            if key_id not in compiled_keys:
                raise KeyAlternatesError(f"{location} is not in the compiled layout")
            compiled = compiled_keys[key_id]
            _require(
                compiled["kind"] == "text",
                f"{location} is not a plain text key",
            )
            # The declared text must still match the compiled key, so a layout edit can
            # never silently re-point a variant set at a different letter.
            _require(
                compiled["text"] == key_entry["text"],
                f"{location} text does not match the compiled layout",
            )

            alternates = key_entry["alternates"]
            _require(
                isinstance(alternates, list) and 0 < len(alternates) <= MAX_ALTERNATES_PER_KEY,
                f"{location} must declare 1 to {MAX_ALTERNATES_PER_KEY} alternates",
            )
            seen_values: list[str] = []
            for index, value in enumerate(alternates):
                entry_location = f"{location}.alternates[{index}]"
                _require(
                    isinstance(value, str) and 0 < len(value) <= MAX_TEXT_SCALARS,
                    f"{entry_location} must be a bounded non-empty string",
                )
                _require(
                    unicodedata.normalize("NFC", value) == value,
                    f"{entry_location} must be NFC",
                )
                _require(value != key_entry["text"], f"{entry_location} repeats the key")
                _require(value not in seen_values, f"{entry_location} is a duplicate")
                _require(
                    not any(scalar in CONJUNCT_JOINERS for scalar in value),
                    f"{entry_location} must not carry a conjunct joiner",
                )
                # The core guarantee: a variant can only reach what the layout already emits.
                missing = sorted(set(value) - available)
                _require(
                    not missing,
                    f"{entry_location} introduces scalars the layout cannot emit: {missing}",
                )
                seen_values.append(value)
            rows.append({"key_id": key_id, "alternates": list(seen_values)})

        rows.sort(key=lambda row: row["key_id"])
        compiled_layouts.append({"layout_id": layout_id, "keys": rows})

    compiled_layouts.sort(key=lambda layout: layout["layout_id"])
    return {
        "asset_version": ASSET_VERSION,
        "generator": "build_key_alternates",
        "layout_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "total_keys": sum(len(layout["keys"]) for layout in compiled_layouts),
        "layouts": compiled_layouts,
    }


def canonical_bytes(asset: dict[str, Any]) -> bytes:
    return (json.dumps(asset, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--layout-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    asset = build_asset(args.source.resolve(), args.layout_lock.resolve())
    payload = canonical_bytes(asset)
    if args.check:
        _require(args.output.is_file(), f"missing asset: {args.output}")
        _require(
            args.output.read_bytes() == payload,
            "asset does not match its reviewed source and layout lock",
        )
        print(f"key_alternates_check=ok total_keys={asset['total_keys']}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"key_alternates_sha256={hashlib.sha256(payload).hexdigest()}")
    print(f"key_alternates_total_keys={asset['total_keys']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyAlternatesError as failure:
        print(f"error: {failure}", file=sys.stderr)
        sys.exit(2)
