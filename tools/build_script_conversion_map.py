"""Compile a reviewed script-to-script conversion map.

`build_conversion_map.py` produces the reviewed Devanagari-to-Newa converter and
hardcodes that output script, so it cannot express another target. Its SHA-256 is
recorded in completed relock evidence, so this compiler is a separate artifact
rather than an edit to it, the same way the emoji catalog, key alternates and
transliteration maps were added.

Every character is written as a Unicode character name and resolved with
`unicodedata.lookup`, so a reviewer reads `TIRHUTA LETTER KA` rather than a
codepoint and a typo fails the build instead of emitting the wrong glyph.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

SOURCE_FORMAT = "nepa-script-conversion-map-source"
SOURCE_FORMAT_VERSION = 1
ASSET_VERSION = 1
GENERATOR = "build_script_conversion_map"
ALGORITHM = "leftmost-longest-codepoint-v1"
NORMALIZATION = "NFC"
UNMAPPED_POLICY = "no-match"
UNICODE_VERSION = "16.0.0"

SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "Deva": ((0x0900, 0x097F), (0xA8E0, 0xA8FF)),
    "Tirh": ((0x11480, 0x114DF),),
    "Limb": ((0x1900, 0x194F),),
}
SCRIPT_NAME_PREFIX = {"Deva": "DEVANAGARI ", "Tirh": "TIRHUTA ", "Limb": "LIMBU "}
MAX_RULES = 2048
MAX_SCALARS = 8


class ScriptConversionError(Exception):
    """A conversion map that must not ship."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScriptConversionError(message)


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _resolve(names: list[str], script: str, where: str) -> str:
    _require(
        isinstance(names, list) and 1 <= len(names) <= MAX_SCALARS,
        f"{where} must be a list of 1..{MAX_SCALARS} Unicode names",
    )
    text = ""
    for name in names:
        _require(isinstance(name, str) and name.strip() == name, f"{where} name is unsafe")
        try:
            character = unicodedata.lookup(name)
        except KeyError as unknown:
            raise ScriptConversionError(f"{where} names unknown character {name!r}") from unknown
        _require(
            name.startswith(SCRIPT_NAME_PREFIX[script]),
            f"{where} character {name!r} is not {script}",
        )
        codepoint = ord(character)
        _require(
            any(lo <= codepoint <= hi for lo, hi in SCRIPT_RANGES[script]),
            f"{where} character {name!r} falls outside {script}",
        )
        text += character
    normalized = unicodedata.normalize(NORMALIZATION, text)
    _require(normalized == text, f"{where} is not {NORMALIZATION}-normalized")
    return text


def build_asset(source_path: Path) -> dict[str, Any]:
    _require(
        unicodedata.unidata_version == UNICODE_VERSION,
        f"compiler Unicode database must be {UNICODE_VERSION}, "
        f"got {unicodedata.unidata_version}",
    )
    source = json.loads(source_path.read_text(encoding="utf-8"))
    _require(
        source.get("source_format") == SOURCE_FORMAT,
        f"source_format must be {SOURCE_FORMAT}",
    )
    _require(
        source.get("source_format_version") == SOURCE_FORMAT_VERSION,
        f"source_format_version must be {SOURCE_FORMAT_VERSION}",
    )
    converter_id = source.get("converter_id")
    _require(bool(isinstance(converter_id, str) and converter_id), "converter_id is required")
    source_script = source.get("source_script")
    output_script = source.get("output_script")
    _require(source_script in SCRIPT_RANGES, f"unsupported source script: {source_script}")
    _require(output_script in SCRIPT_RANGES, f"unsupported output script: {output_script}")
    _require(source_script != output_script, "a conversion map must change script")

    rules_value = source.get("rules")
    _require(
        isinstance(rules_value, list) and 1 <= len(rules_value) <= MAX_RULES,
        f"rules must contain 1..{MAX_RULES} rows",
    )

    compiled: dict[str, str] = {}
    for index, row in enumerate(rules_value):
        where = f"rules[{index}]"
        _require(isinstance(row, dict), f"{where} must be an object")
        _require(
            set(row) == {"from", "to"},
            f"{where} fields must be exactly ['from', 'to']",
        )
        key = _resolve(row["from"], source_script, f"{where}.from")
        value = _resolve(row["to"], output_script, f"{where}.to")
        _require(key not in compiled, f"{where} duplicates source text {key!r}")
        compiled[key] = value

    # Leftmost-longest matching: longer keys must be tried first, so the runtime
    # ordering is part of the artifact rather than left to the reader.
    ordered = sorted(compiled.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    return {
        "asset_version": ASSET_VERSION,
        "generator": GENERATOR,
        "converter_id": converter_id,
        "language": source["language"],
        "source_script": source_script,
        "output_script": output_script,
        "normalization": NORMALIZATION,
        "algorithm": ALGORITHM,
        "unmapped_policy": UNMAPPED_POLICY,
        "unicode_data_version": UNICODE_VERSION,
        "rule_count": len(ordered),
        "rules": [{"from": key, "to": value} for key, value in ordered],
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
    }


def convert_text(asset: dict[str, Any], text: str) -> str:
    """Reference implementation of the map's deterministic runtime semantics."""

    rules = [(row["from"], row["to"]) for row in asset["rules"]]
    output: list[str] = []
    position = 0
    while position < len(text):
        for key, value in rules:
            if text.startswith(key, position):
                output.append(value)
                position += len(key)
                break
        else:
            # Unmapped input passes through: the policy is no-match, not deletion.
            output.append(text[position])
            position += 1
    return unicodedata.normalize(NORMALIZATION, "".join(output))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        asset = build_asset(args.source)
    except ScriptConversionError as failure:
        print(f"script_conversion_error={failure}", file=sys.stderr)
        return 2

    encoded = _canonical_bytes(asset)
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != encoded:
            print("script_conversion_check=drifted", file=sys.stderr)
            return 3
        print(f"script_conversion_check=ok converter={asset['converter_id']}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(f"script_conversion_converter={asset['converter_id']}")
    print(f"script_conversion_rules={asset['rule_count']}")
    print(f"script_conversion_sha256={hashlib.sha256(encoded).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
