#!/usr/bin/env python3
"""Compile a deterministic Devanagari-to-Newa conversion map v1.

The runtime artifact is canonical UTF-8 JSON with a ``.ncm`` suffix.  Rules are
pure string substitutions interpreted with leftmost-longest code-point
matching.  An unmapped input position makes the complete conversion a no-match;
the format never authorizes mixed-script output or heuristic fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


FORMAT = "nepa-conversion-map"
FORMAT_VERSION = 1
SOURCE_FORMAT = "nepa-conversion-map-source"
SOURCE_FORMAT_VERSION = 1
NORMALIZATION = "NFC"
ALGORITHM = "leftmost-longest-codepoint-v1"
UNMAPPED_POLICY = "no-match"
JOINER_POLICY = "virama-context-only-v1"

MAX_ARTIFACT_BYTES = 256 * 1024
MAX_SOURCE_BYTES = 512 * 1024
MAX_RULES = 1024
MAX_SOURCE_CODE_POINTS = 8
MAX_TARGET_CODE_POINTS = 16

DEVA_RANGES = (
    (0x0900, 0x097F),
    (0xA8E0, 0xA8FF),
    (0x11B00, 0x11B5F),
)
NEWA_RANGES = ((0x11400, 0x1147F),)
DEVA_VIRAMA = "\u094d"
NEWA_VIRAMA = "\U00011442"
JOINERS = frozenset({"\u200c", "\u200d"})
ALLOWED_CATEGORY_PREFIXES = frozenset({"L", "M", "N", "P"})

SOURCE_FIELDS = frozenset(
    {
        "source_format",
        "source_format_version",
        "converter_id",
        "mapping_version",
        "language",
        "source_script",
        "output_script",
        "normalization",
        "algorithm",
        "unmapped_policy",
        "joiner_policy",
        "rules",
    }
)
ARTIFACT_FIELDS = frozenset(
    {
        "format",
        "format_version",
        "converter_id",
        "mapping_version",
        "language",
        "source_script",
        "output_script",
        "normalization",
        "algorithm",
        "unmapped_policy",
        "joiner_policy",
        "rule_count",
        "rules",
    }
)
RULE_FIELDS = frozenset({"from", "to"})
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SEMANTIC_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")


class ConversionMapError(ValueError):
    """Raised when a source or runtime artifact violates conversion-map v1."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConversionMapError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_json(encoded: bytes, label: str) -> dict[str, Any]:
    if not encoded:
        raise ConversionMapError(f"{label} must not be empty")
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise ConversionMapError(f"{label} must not contain a UTF-8 BOM")
    try:
        text = encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConversionMapError(f"{label} must be UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ConversionMapError(f"unsupported JSON number: {token}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ConversionMapError(f"invalid JSON in {label}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ConversionMapError(f"{label} must be a JSON object")
    return value


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _require_exact_fields(
    value: dict[str, Any], expected: frozenset[str], location: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        detail: list[str] = []
        if missing:
            detail.append(f"missing {missing}")
        if unknown:
            detail.append(f"unknown {unknown}")
        raise ConversionMapError(f"{location} fields are invalid: {', '.join(detail)}")


def _require_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConversionMapError(f"{location} must be a non-empty string")
    return value


def _require_exact_integer(value: object, expected: int, location: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise ConversionMapError(f"{location} must equal {expected}")


def _in_ranges(character: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    scalar = ord(character)
    return any(start <= scalar <= end for start, end in ranges)


def _is_script_character(
    character: str, ranges: tuple[tuple[int, int], ...]
) -> bool:
    return (
        _in_ranges(character, ranges)
        and unicodedata.name(character, None) is not None
        and unicodedata.category(character)[0] in ALLOWED_CATEGORY_PREFIXES
    )


def _is_script_letter(
    character: str, ranges: tuple[tuple[int, int], ...]
) -> bool:
    return _in_ranges(character, ranges) and unicodedata.category(character)[0] == "L"


def _validate_joiner_neighbors(
    value: str,
    index: int,
    *,
    ranges: tuple[tuple[int, int], ...],
    virama: str,
    location: str,
) -> None:
    if (
        index < 1
        or index + 1 >= len(value)
        or value[index - 1] != virama
        or not _is_script_letter(value[index + 1], ranges)
    ):
        raise ConversionMapError(
            f"{location} has a joiner outside virama-plus-letter context"
        )


def _has_base_before_virama(
    value: str,
    joiner_index: int,
    ranges: tuple[tuple[int, int], ...],
) -> bool:
    index = joiner_index - 2
    while (
        index >= 0
        and _in_ranges(value[index], ranges)
        and unicodedata.category(value[index])[0] == "M"
    ):
        index -= 1
    return index >= 0 and _is_script_letter(value[index], ranges)


def _validate_script_text(
    value: object,
    *,
    ranges: tuple[tuple[int, int], ...],
    virama: str,
    maximum_code_points: int | None,
    require_complete_joiners: bool,
    location: str,
) -> str:
    text = _require_string(value, location)
    if unicodedata.normalize(NORMALIZATION, text) != text:
        raise ConversionMapError(f"{location} must be NFC")
    if maximum_code_points is not None and len(text) > maximum_code_points:
        raise ConversionMapError(
            f"{location} exceeds {maximum_code_points} code points"
        )

    has_script_character = False
    for index, character in enumerate(text):
        if character in JOINERS:
            _validate_joiner_neighbors(
                text,
                index,
                ranges=ranges,
                virama=virama,
                location=location,
            )
            if require_complete_joiners and not _has_base_before_virama(
                text, index, ranges
            ):
                raise ConversionMapError(
                    f"{location} has a joiner without a preceding script base"
                )
            continue
        if not _is_script_character(character, ranges):
            raise ConversionMapError(f"{location} contains an out-of-script character")
        has_script_character = True
    if not has_script_character:
        raise ConversionMapError(f"{location} must contain a script character")
    return text


def _validate_metadata(source: dict[str, Any]) -> None:
    _require_exact_integer(
        source["source_format_version"],
        SOURCE_FORMAT_VERSION,
        "source_format_version",
    )
    expected_constants = {
        "source_format": SOURCE_FORMAT,
        "source_script": "Deva",
        "output_script": "Newa",
        "normalization": NORMALIZATION,
        "algorithm": ALGORITHM,
        "unmapped_policy": UNMAPPED_POLICY,
        "joiner_policy": JOINER_POLICY,
    }
    for field, expected in expected_constants.items():
        if source[field] != expected:
            raise ConversionMapError(f"{field} must equal {expected!r}")

    converter_id = _require_string(source["converter_id"], "converter_id")
    if SAFE_ID.fullmatch(converter_id) is None:
        raise ConversionMapError("converter_id is unsafe")
    mapping_version = _require_string(source["mapping_version"], "mapping_version")
    if SEMANTIC_VERSION.fullmatch(mapping_version) is None:
        raise ConversionMapError("mapping_version must be semantic x.y.z")
    language = _require_string(source["language"], "language")
    if re.fullmatch(r"[a-z]{3}", language) is None:
        raise ConversionMapError("language must be ISO 639-3")


def compile_source(source: dict[str, Any]) -> dict[str, Any]:
    """Validate one authored source object and return its runtime artifact."""

    if not isinstance(source, dict):
        raise ConversionMapError("conversion-map source must be an object")
    _require_exact_fields(source, SOURCE_FIELDS, "conversion-map source")
    _validate_metadata(source)

    rules_value = source["rules"]
    if not isinstance(rules_value, list) or not 1 <= len(rules_value) <= MAX_RULES:
        raise ConversionMapError(f"rules must contain 1..{MAX_RULES} rows")

    rules: list[dict[str, str]] = []
    seen_sources: set[str] = set()
    for index, value in enumerate(rules_value):
        location = f"rules[{index}]"
        if not isinstance(value, dict):
            raise ConversionMapError(f"{location} must be an object")
        _require_exact_fields(value, RULE_FIELDS, location)
        rule_source = _validate_script_text(
            value["from"],
            ranges=DEVA_RANGES,
            virama=DEVA_VIRAMA,
            maximum_code_points=MAX_SOURCE_CODE_POINTS,
            require_complete_joiners=False,
            location=f"{location}.from",
        )
        rule_target = _validate_script_text(
            value["to"],
            ranges=NEWA_RANGES,
            virama=NEWA_VIRAMA,
            maximum_code_points=MAX_TARGET_CODE_POINTS,
            require_complete_joiners=False,
            location=f"{location}.to",
        )
        if rule_source in seen_sources:
            raise ConversionMapError(f"duplicate rule source: {rule_source!r}")
        seen_sources.add(rule_source)
        rules.append({"from": rule_source, "to": rule_target})

    rules.sort(key=lambda row: tuple(ord(character) for character in row["from"]))
    artifact: dict[str, Any] = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "converter_id": source["converter_id"],
        "mapping_version": source["mapping_version"],
        "language": source["language"],
        "source_script": source["source_script"],
        "output_script": source["output_script"],
        "normalization": source["normalization"],
        "algorithm": source["algorithm"],
        "unmapped_policy": source["unmapped_policy"],
        "joiner_policy": source["joiner_policy"],
        "rule_count": len(rules),
        "rules": rules,
    }
    encoded = _canonical_bytes(artifact)
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise ConversionMapError(
            f"compiled artifact exceeds {MAX_ARTIFACT_BYTES} bytes"
        )
    return artifact


def compile_bytes(encoded: bytes) -> bytes:
    """Compile source JSON bytes to canonical runtime-artifact bytes."""

    if len(encoded) > MAX_SOURCE_BYTES:
        raise ConversionMapError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
    return _canonical_bytes(compile_source(_parse_json(encoded, "conversion-map source")))


def validate_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Validate that an object is the exact canonical conversion-map v1 shape."""

    if not isinstance(artifact, dict):
        raise ConversionMapError("conversion-map artifact must be an object")
    _require_exact_fields(artifact, ARTIFACT_FIELDS, "conversion-map artifact")
    _require_exact_integer(artifact["format_version"], FORMAT_VERSION, "format_version")
    rules = artifact["rules"]
    if not isinstance(rules, list):
        raise ConversionMapError("artifact rules must be an array")
    _require_exact_integer(
        artifact["rule_count"], len(rules), "rule_count"
    )
    if artifact["format"] != FORMAT:
        raise ConversionMapError(f"format must equal {FORMAT!r}")
    source = {
        "source_format": SOURCE_FORMAT,
        "source_format_version": SOURCE_FORMAT_VERSION,
        "converter_id": artifact["converter_id"],
        "mapping_version": artifact["mapping_version"],
        "language": artifact["language"],
        "source_script": artifact["source_script"],
        "output_script": artifact["output_script"],
        "normalization": artifact["normalization"],
        "algorithm": artifact["algorithm"],
        "unmapped_policy": artifact["unmapped_policy"],
        "joiner_policy": artifact["joiner_policy"],
        "rules": artifact["rules"],
    }
    canonical = compile_source(source)
    if artifact != canonical:
        raise ConversionMapError("artifact rules are not in canonical order")
    return canonical


def convert_text(artifact: dict[str, Any], text: str) -> str | None:
    """Reference implementation of the map's deterministic runtime semantics."""

    validated = validate_artifact(artifact)
    try:
        source = _validate_script_text(
            text,
            ranges=DEVA_RANGES,
            virama=DEVA_VIRAMA,
            maximum_code_points=None,
            require_complete_joiners=True,
            location="input",
        )
    except ConversionMapError:
        return None

    rules_by_first: dict[str, list[tuple[str, str]]] = {}
    for row in validated["rules"]:
        rules_by_first.setdefault(row["from"][0], []).append(
            (row["from"], row["to"])
        )
    for candidates in rules_by_first.values():
        candidates.sort(
            key=lambda pair: (-len(pair[0]), tuple(ord(ch) for ch in pair[0]))
        )

    output: list[str] = []
    index = 0
    while index < len(source):
        match: tuple[str, str] | None = None
        for candidate in rules_by_first.get(source[index], []):
            if source.startswith(candidate[0], index):
                match = candidate
                break
        if match is None:
            return None
        output.append(match[1])
        index += len(match[0])

    converted = "".join(output)
    try:
        return _validate_script_text(
            converted,
            ranges=NEWA_RANGES,
            virama=NEWA_VIRAMA,
            maximum_code_points=None,
            require_complete_joiners=True,
            location="output",
        )
    except ConversionMapError:
        return None


def compile_file(source_path: Path, output_path: Path) -> dict[str, Any]:
    """Compile one source file and atomically write its canonical ``.ncm``."""

    if output_path.suffix != ".ncm":
        raise ConversionMapError("output path must use the .ncm suffix")
    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise ConversionMapError(f"cannot read source: {source_path}") from exc
    artifact_bytes = compile_bytes(source_bytes)
    artifact = _parse_json(artifact_bytes, "compiled conversion-map artifact")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(artifact_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="authored conversion-map source JSON")
    parser.add_argument("output", type=Path, help="canonical runtime .ncm output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        artifact = compile_file(args.source, args.output)
        encoded = args.output.read_bytes()
    except ConversionMapError as exc:
        raise SystemExit(f"build_conversion_map: error: {exc}") from exc
    print(
        json.dumps(
            {
                "artifact_sha256": hashlib.sha256(encoded).hexdigest(),
                "converter_id": artifact["converter_id"],
                "output": str(args.output),
                "rule_count": artifact["rule_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
