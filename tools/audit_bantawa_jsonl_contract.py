#!/usr/bin/env python3
"""Inventory the pinned Bantawa dictionary JSONL without selecting semantics.

This auditor is deliberately earlier than a language adapter.  It proves the
raw JSONL contract and inventories every top-level field independently, but it
does not choose a candidate field, normalization, joiner policy, layout, pack,
or promotion state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


AUDITOR_NAME = "audit_bantawa_jsonl_contract"
AUDITOR_VERSION = 1
FORMAT_VERSION = 1
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CATALOG_PATH = REPOSITORY_ROOT / "catalog" / "resources.json"
EXPECTED_REMOTE_RAW_PATH = Path(
    "/home/cdjk/github/llm/rai-speech-toolkit/dialects/central/"
    "bantawa/dict/bantawa-english.dict.jsonl"
)
EXPECTED_CATALOG_RESOURCE_PATH = (
    "/Users/cdjk/github/llm/rai-speech-toolkit/dialects/central/"
    "bantawa/dict/bantawa-english.dict.jsonl"
)
EXPECTED_TARGET_ID = "bap"
EXPECTED_TARGET_NAME = "Bantawa"
EXPECTED_ISO_639_3 = "bap"
EXPECTED_RESOURCE_ID = "bap-dictionary"
EXPECTED_RECORDS = 2_040
EXPECTED_BYTES = 360_086
EXPECTED_SHA256 = "a69917c00e7a8587f4a38458faf89c95fc9e5ac9cbe6cfb612383438bdf5ae12"
REQUIRED_PYTHON_VERSION = (3, 14)
REQUIRED_UNICODE_VERSION = "16.0.0"
EXAMPLE_LIMIT = 8
EXAMPLE_SCALAR_LIMIT = 128
WHITESPACE_RE = re.compile(r"\s+")
DEVANAGARI_RANGES = ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x11B00, 0x11B5F))
DEVANAGARI_VIRAMA = "\u094d"
ZERO_WIDTH_NON_JOINER = "\u200c"
ZERO_WIDTH_JOINER = "\u200d"
JOINERS = (ZERO_WIDTH_NON_JOINER, ZERO_WIDTH_JOINER)
CLAIM_SCOPE = (
    "Pinned Bantawa raw JSONL schema and per-field value/scalar inventory only; "
    "candidate and headword fields, filtering, normalization policy, joiner "
    "policy, layout, prefix vectors, pack construction, and profile promotion "
    "remain unselected."
)


class AuditError(ValueError):
    """Raised when an input or output violates the source-contract audit."""


@dataclass(frozen=True)
class StringOccurrence:
    """One direct string value or one string element inside an array."""

    value: str
    line: int
    array_index: int | None


@dataclass
class FieldInventory:
    """Raw observations for one top-level JSON field."""

    rows_present: int = 0
    json_types: Counter[str] = field(default_factory=Counter)
    direct_strings: list[StringOccurrence] = field(default_factory=list)
    arrays: int = 0
    empty_arrays: int = 0
    array_lengths: Counter[int] = field(default_factory=Counter)
    array_element_types: Counter[str] = field(default_factory=Counter)
    array_strings: list[StringOccurrence] = field(default_factory=list)
    canonical_arrays: set[str] = field(default_factory=set)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _canonical_inline(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AuditError(f"{label} is not a regular non-symbolic file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AuditError(f"cannot read {label} {path}: {exc}") from exc


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise AuditError(f"duplicate JSON key {key!r}")
        value[key] = child
    return value


def _reject_nonfinite(value: str) -> object:
    raise AuditError(f"non-finite JSON number {value!r} is not allowed")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise AuditError(f"non-finite JSON number {value!r} is not allowed")
    return parsed


def _decode_json(encoded: str, label: str) -> object:
    try:
        value = json.loads(
            encoded,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except json.JSONDecodeError as exc:
        raise AuditError(f"{label} is invalid JSON: {exc}") from exc
    except AuditError as exc:
        raise AuditError(f"{label}: {exc}") from exc
    _validate_unicode_scalars(value, label)
    return value


def _validate_unicode_scalars(value: object, location: str) -> None:
    if isinstance(value, str):
        for index, character in enumerate(value):
            if 0xD800 <= ord(character) <= 0xDFFF:
                raise AuditError(
                    f"{location} contains an unpaired surrogate instead of a "
                    f"Unicode scalar at string index {index}"
                )
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_unicode_scalars(child, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_unicode_scalars(key, f"{location} object key")
            _validate_unicode_scalars(child, f"{location}.{key}")


def _read_catalog(path: Path) -> dict[str, Any]:
    if path.resolve() != EXPECTED_CATALOG_PATH.resolve():
        raise AuditError(f"resource catalog must be {EXPECTED_CATALOG_PATH}")
    encoded = _read_regular(path, "resource catalog")
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise AuditError("resource catalog must not contain a UTF-8 BOM")
    try:
        decoded = encoded.decode("utf-8")
    except UnicodeError as exc:
        raise AuditError(f"resource catalog is not UTF-8: {exc}") from exc
    value = _decode_json(decoded, "resource catalog")
    if not isinstance(value, dict):
        raise AuditError("resource catalog must be a JSON object")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AuditError(f"{label} must be a positive integer")
    return value


def _catalog_binding(catalog: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    packs = catalog.get("packs")
    if not isinstance(packs, list):
        raise AuditError("resource catalog packs must be an array")
    targets = [
        item
        for item in packs
        if isinstance(item, dict) and item.get("id") == EXPECTED_TARGET_ID
    ]
    if len(targets) != 1:
        raise AuditError(f"catalog must contain exactly one {EXPECTED_TARGET_ID} target")
    target = targets[0]
    if target.get("name") != EXPECTED_TARGET_NAME:
        raise AuditError(f"catalog target name must be {EXPECTED_TARGET_NAME}")
    if target.get("iso_639_3") != EXPECTED_ISO_639_3:
        raise AuditError(f"catalog target ISO 639-3 must be {EXPECTED_ISO_639_3}")
    resources = target.get("resources")
    if not isinstance(resources, list):
        raise AuditError("Bantawa catalog resources must be an array")
    matches = [
        item
        for item in resources
        if isinstance(item, dict) and item.get("id") == EXPECTED_RESOURCE_ID
    ]
    if len(matches) != 1:
        raise AuditError(f"catalog must contain exactly one {EXPECTED_RESOURCE_ID} resource")
    resource = matches[0]
    expected_fields = {
        "kind": "lexicon",
        "path": EXPECTED_CATALOG_RESOURCE_PATH,
        "format": "JSONL",
        "structured": True,
        "canonical": True,
        "record_unit": "entries",
        "records": EXPECTED_RECORDS,
        "bytes": EXPECTED_BYTES,
        "sha256": EXPECTED_SHA256,
    }
    for key, expected in expected_fields.items():
        actual = resource.get(key)
        if type(actual) is not type(expected) or actual != expected:
            raise AuditError(f"catalog {EXPECTED_RESOURCE_ID}.{key} must be {expected!r}")
    uses = resource.get("uses")
    if not isinstance(uses, list) or "candidate_vocabulary" not in uses:
        raise AuditError("Bantawa resource must declare candidate_vocabulary use")
    _positive_int(resource.get("records"), "catalog resource records")
    _positive_int(resource.get("bytes"), "catalog resource bytes")
    return target, resource


def _validate_runtime() -> None:
    if sys.version_info[:2] != REQUIRED_PYTHON_VERSION:
        required = ".".join(str(part) for part in REQUIRED_PYTHON_VERSION)
        actual = f"{sys.version_info.major}.{sys.version_info.minor}"
        raise AuditError(f"Bantawa audit requires Python {required}, got {actual}")
    if unicodedata.unidata_version != REQUIRED_UNICODE_VERSION:
        raise AuditError(
            "Bantawa audit requires Unicode data "
            f"{REQUIRED_UNICODE_VERSION}, got {unicodedata.unidata_version}"
        )


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (int, float)):
        return "number"
    raise AuditError(f"unsupported decoded JSON value type: {type(value).__name__}")


def _is_devanagari_letter(character: str) -> bool:
    codepoint = ord(character)
    return unicodedata.category(character).startswith("L") and any(
        start <= codepoint <= end for start, end in DEVANAGARI_RANGES
    )


def _is_latin_letter(character: str) -> bool:
    return (
        unicodedata.category(character).startswith("L")
        and unicodedata.name(character, "").startswith("LATIN ")
    )


def _scalar_label(codepoint: int) -> str:
    return f"U+{codepoint:04X}"


def _frequency_rows(counter: Counter[int]) -> list[dict[str, object]]:
    return [
        {
            "category": unicodedata.category(chr(codepoint)),
            "character": chr(codepoint),
            "code_point": _scalar_label(codepoint),
            "count": counter[codepoint],
            "name": unicodedata.name(chr(codepoint), "<unnamed>"),
        }
        for codepoint in sorted(counter)
    ]


def _joiner_context(value: str, index: int) -> str:
    previous = value[index - 1] if index > 0 else None
    following = value[index + 1] if index + 1 < len(value) else None
    if previous == DEVANAGARI_VIRAMA and following is None:
        return "after_virama_terminal"
    if previous == DEVANAGARI_VIRAMA and following is not None:
        if unicodedata.category(following).startswith("L"):
            return "after_virama_before_letter"
        return "after_virama_before_nonletter"
    return "other"


def _examples(occurrences: Iterable[StringOccurrence]) -> list[dict[str, object]]:
    first_by_value: dict[str, StringOccurrence] = {}
    for occurrence in occurrences:
        existing = first_by_value.get(occurrence.value)
        array_index = -1 if occurrence.array_index is None else occurrence.array_index
        location = (occurrence.line, array_index)
        if existing is None:
            first_by_value[occurrence.value] = occurrence
            continue
        existing_array_index = (
            -1 if existing.array_index is None else existing.array_index
        )
        if location < (existing.line, existing_array_index):
            first_by_value[occurrence.value] = occurrence
    examples: list[dict[str, object]] = []
    for value in sorted(first_by_value)[:EXAMPLE_LIMIT]:
        occurrence = first_by_value[value]
        examples.append({
            "array_index": occurrence.array_index,
            "first_line": occurrence.line,
            "original_scalar_length": len(value),
            "truncated": len(value) > EXAMPLE_SCALAR_LIMIT,
            "value": value[:EXAMPLE_SCALAR_LIMIT],
            "value_sha256": _sha256_bytes(value.encode("utf-8")),
        })
    return examples


def _string_inventory(occurrences: list[StringOccurrence]) -> dict[str, object]:
    scalar_frequencies: Counter[int] = Counter()
    control_frequencies: Counter[int] = Counter()
    format_frequencies: Counter[int] = Counter()
    joiner_contexts = {
        ZERO_WIDTH_NON_JOINER: Counter(),
        ZERO_WIDTH_JOINER: Counter(),
    }
    values_with_devanagari = 0
    values_with_latin = 0
    values_with_other_letters = 0
    values_with_controls = 0
    values_with_formats = 0
    values_with_zwnj = 0
    values_with_zwj = 0
    for occurrence in occurrences:
        value = occurrence.value
        has_devanagari = False
        has_latin = False
        has_other_letter = False
        has_control = False
        has_format = False
        for index, character in enumerate(value):
            codepoint = ord(character)
            category = unicodedata.category(character)
            scalar_frequencies[codepoint] += 1
            if category == "Cc":
                control_frequencies[codepoint] += 1
                has_control = True
            if category == "Cf":
                format_frequencies[codepoint] += 1
                has_format = True
            if _is_devanagari_letter(character):
                has_devanagari = True
            elif _is_latin_letter(character):
                has_latin = True
            elif category.startswith("L"):
                has_other_letter = True
            if character in JOINERS:
                joiner_contexts[character][_joiner_context(value, index)] += 1
        values_with_devanagari += int(has_devanagari)
        values_with_latin += int(has_latin)
        values_with_other_letters += int(has_other_letter)
        values_with_controls += int(has_control)
        values_with_formats += int(has_format)
        values_with_zwnj += int(ZERO_WIDTH_NON_JOINER in value)
        values_with_zwj += int(ZERO_WIDTH_JOINER in value)

    values = [occurrence.value for occurrence in occurrences]
    joiner_report: dict[str, object] = {}
    for character, name in (
        (ZERO_WIDTH_NON_JOINER, "ZWNJ"),
        (ZERO_WIDTH_JOINER, "ZWJ"),
    ):
        contexts = joiner_contexts[character]
        joiner_report[name] = {
            "code_point": _scalar_label(ord(character)),
            "contexts": dict(sorted(contexts.items())),
            "occurrences": sum(contexts.values()),
            "values": values_with_zwnj if name == "ZWNJ" else values_with_zwj,
        }
    return {
        "collapsed_whitespace_changed_values": sum(
            WHITESPACE_RE.sub(" ", value) != value for value in values
        ),
        "complete_scalar_frequencies": _frequency_rows(scalar_frequencies),
        "control_scalar_frequencies": _frequency_rows(control_frequencies),
        "distinct_values": len(set(values)),
        "examples": _examples(occurrences),
        "example_limit": EXAMPLE_LIMIT,
        "example_scalar_limit": EXAMPLE_SCALAR_LIMIT,
        "format_scalar_frequencies": _frequency_rows(format_frequencies),
        "joiners": joiner_report,
        "nfc_changed_values": sum(unicodedata.normalize("NFC", value) != value for value in values),
        "nonblank_after_strip_values": sum(bool(value.strip()) for value in values),
        "nonempty_values": sum(bool(value) for value in values),
        "strip_changed_values": sum(value.strip() != value for value in values),
        "values": len(values),
        "values_with_control_characters": values_with_controls,
        "values_with_devanagari_letters": values_with_devanagari,
        "values_with_format_characters": values_with_formats,
        "values_with_latin_letters": values_with_latin,
        "values_with_other_letters": values_with_other_letters,
    }


def _counter_rows(counter: Counter[Any], key: str) -> list[dict[str, object]]:
    return [
        {key: value, "count": counter[value]}
        for value in sorted(counter)
    ]


def _field_report(
    name: str,
    inventory: FieldInventory,
    row_count: int,
) -> dict[str, object]:
    return {
        "array_element_types": dict(sorted(inventory.array_element_types.items())),
        "array_lengths": _counter_rows(inventory.array_lengths, "length"),
        "array_string_elements": _string_inventory(inventory.array_strings),
        "arrays": inventory.arrays,
        "distinct_arrays": len(inventory.canonical_arrays),
        "direct_string_values": _string_inventory(inventory.direct_strings),
        "empty_arrays": inventory.empty_arrays,
        "field": name,
        "json_types": dict(sorted(inventory.json_types.items())),
        "rows_missing": row_count - inventory.rows_present,
        "rows_present": inventory.rows_present,
    }


def _parse_rows(input_bytes: bytes) -> tuple[list[dict[str, object]], dict[str, object]]:
    if input_bytes.startswith(b"\xef\xbb\xbf"):
        raise AuditError("Bantawa JSONL must not contain a UTF-8 BOM")
    if input_bytes and not input_bytes.endswith(b"\n"):
        raise AuditError("Bantawa JSONL must be LF-terminated")
    if b"\r" in input_bytes:
        raise AuditError("Bantawa JSONL must use LF line endings")
    try:
        decoded = input_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise AuditError(f"Bantawa JSONL is not valid UTF-8: {exc}") from exc
    if not decoded:
        raise AuditError("Bantawa JSONL must not be empty")

    encoded_lines = decoded[:-1].split("\n")
    rows: list[dict[str, object]] = []
    ordered_fields: Counter[tuple[str, ...]] = Counter()
    ordered_field_types: Counter[tuple[tuple[str, str], ...]] = Counter()
    inventories: dict[str, FieldInventory] = {}
    for line_number, encoded in enumerate(encoded_lines, 1):
        if not encoded.strip():
            raise AuditError(f"Bantawa JSONL row {line_number} is blank")
        value = _decode_json(encoded, f"Bantawa JSONL row {line_number}")
        if not isinstance(value, dict):
            raise AuditError(f"Bantawa JSONL row {line_number} must be an object")
        row = dict(value)
        rows.append(row)
        fields = tuple(row)
        ordered_fields[fields] += 1
        ordered_field_types[tuple((name, _json_type(child)) for name, child in row.items())] += 1
        for name, child in row.items():
            inventory = inventories.setdefault(name, FieldInventory())
            inventory.rows_present += 1
            child_type = _json_type(child)
            inventory.json_types[child_type] += 1
            if isinstance(child, str):
                inventory.direct_strings.append(StringOccurrence(child, line_number, None))
            elif isinstance(child, list):
                inventory.arrays += 1
                inventory.empty_arrays += int(not child)
                inventory.array_lengths[len(child)] += 1
                inventory.canonical_arrays.add(_canonical_inline(child))
                for array_index, element in enumerate(child):
                    element_type = _json_type(element)
                    inventory.array_element_types[element_type] += 1
                    if isinstance(element, str):
                        inventory.array_strings.append(
                            StringOccurrence(element, line_number, array_index)
                        )

    if len(rows) != EXPECTED_RECORDS:
        raise AuditError(
            f"Bantawa JSONL row count must be {EXPECTED_RECORDS}, got {len(rows)}"
        )
    contract = {
        "blank_rows": 0,
        "duplicate_keys": "rejected",
        "encoding": "UTF-8",
        "field_inventories": [
            _field_report(name, inventories[name], len(rows))
            for name in sorted(inventories)
        ],
        "lf_terminated": True,
        "ordered_field_signatures": [
            {"count": ordered_fields[signature], "fields": list(signature)}
            for signature in sorted(ordered_fields)
        ],
        "ordered_field_type_signatures": [
            {
                "count": ordered_field_types[signature],
                "fields": [
                    {"field": name, "json_type": json_type}
                    for name, json_type in signature
                ],
            }
            for signature in sorted(ordered_field_types)
        ],
        "rows": len(rows),
    }
    return rows, contract


def build_audit(args: argparse.Namespace) -> dict[str, object]:
    """Build the deterministic neutral source-contract report."""

    _validate_runtime()
    catalog = _read_catalog(args.resource_catalog)
    _target, resource = _catalog_binding(catalog)
    if args.bantawa_jsonl.resolve() != EXPECTED_REMOTE_RAW_PATH.resolve():
        raise AuditError(f"Bantawa raw input must be {EXPECTED_REMOTE_RAW_PATH}")
    input_bytes = _read_regular(args.bantawa_jsonl, "Bantawa raw JSONL")
    if len(input_bytes) != EXPECTED_BYTES:
        raise AuditError(
            f"Bantawa raw byte count must be {EXPECTED_BYTES}, got {len(input_bytes)}"
        )
    actual_sha256 = _sha256_bytes(input_bytes)
    if actual_sha256 != EXPECTED_SHA256:
        raise AuditError(
            f"Bantawa raw SHA-256 must be {EXPECTED_SHA256}, got {actual_sha256}"
        )
    _rows, contract = _parse_rows(input_bytes)
    auditor_path = Path(__file__).resolve()
    return {
        "auditor": {
            "name": AUDITOR_NAME,
            "path": "tools/audit_bantawa_jsonl_contract.py",
            "sha256": _sha256_bytes(_read_regular(auditor_path, "auditor source")),
            "version": AUDITOR_VERSION,
        },
        "claim_scope": CLAIM_SCOPE,
        "format_version": FORMAT_VERSION,
        "jsonl_contract": contract,
        "raw_input": {
            "bytes": len(input_bytes),
            "catalog_path": str(resource["path"]),
            "path": str(EXPECTED_REMOTE_RAW_PATH),
            "records": len(_rows),
            "resource_id": EXPECTED_RESOURCE_ID,
            "sha256": actual_sha256,
            "target_id": EXPECTED_TARGET_ID,
        },
        "runtime_contract": {
            "python_major_minor": ".".join(str(part) for part in REQUIRED_PYTHON_VERSION),
            "unicode_data_version": unicodedata.unidata_version,
        },
        "selections": {
            "candidate_field": None,
            "filter_policy": None,
            "headword_field": None,
            "joiner_policy": None,
            "layout_id": None,
            "normalization_policy": None,
            "pack_id": None,
            "prefix_vectors": [],
            "profile_promotion": False,
        },
    }


def _write_atomic(path: Path, encoded: bytes) -> None:
    if path.is_symlink():
        raise AuditError("audit output must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _validate_output_path(
    output: Path,
    resource_catalog: Path,
    bantawa_jsonl: Path,
) -> None:
    if not output.is_absolute():
        raise AuditError("audit output path must be absolute")
    resolved = output.resolve(strict=False)
    if output != resolved:
        raise AuditError(
            "audit output path must be canonical and must not use symbolic parents"
        )
    protected = {
        resource_catalog.resolve(): "resource catalog",
        bantawa_jsonl.resolve(): "Bantawa raw JSONL",
        Path(__file__).resolve(): "auditor source",
    }
    if resolved in protected:
        raise AuditError(f"audit output must not overwrite {protected[resolved]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-catalog", type=Path, required=True)
    parser.add_argument("--bantawa-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _validate_output_path(
            args.output,
            args.resource_catalog,
            args.bantawa_jsonl,
        )
        report = build_audit(args)
        encoded = _canonical_bytes(report)
        if args.check:
            existing = _read_regular(args.output, "audit output")
            if existing != encoded:
                raise AuditError("audit output is stale")
        else:
            _write_atomic(args.output, encoded)
    except (AuditError, OSError) as exc:
        parser.error(str(exc))
    print(_canonical_inline({
        "output": str(args.output),
        "report_sha256": _sha256_bytes(encoded),
        "status": "passed",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
