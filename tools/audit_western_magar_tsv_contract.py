#!/usr/bin/env python3
"""Inventory the pinned Western Magar TSV without selecting semantics.

This probe is deliberately earlier than a language adapter. It proves the raw
TSV, catalog, and pending-profile contracts and inventories every column
independently. Layout results are scalar-emission measurements only: the probe
does not choose a candidate column, normalization or joiner policy, layout,
pack, query set, or promotion state.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


AUDITOR_NAME = "audit_western_magar_tsv_contract"
AUDITOR_VERSION = 1
FORMAT_VERSION = 1
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CATALOG_PATH = REPOSITORY_ROOT / "catalog" / "resources.json"
EXPECTED_PROFILE_LOCK_PATH = (
    REPOSITORY_ROOT / "catalog" / "internal-profiles.lock.json"
)
EXPECTED_LAYOUT_LOCK_PATH = (
    REPOSITORY_ROOT / "layouts" / "internal" / "layouts-v1.lock.json"
)
EXPECTED_REMOTE_RAW_PATH = Path(
    "/home/cdjk/github/llm/nllb-better/data/lexicons_apk/"
    "mrd_nep_lexicon.tsv"
)
EXPECTED_CATALOG_RESOURCE_PATH = (
    "/Users/cdjk/github/llm/nllb-better/data/lexicons_apk/"
    "mrd_nep_lexicon.tsv"
)
EXPECTED_TARGET_ID = "mrd"
EXPECTED_TARGET_NAME = "Western Magar"
EXPECTED_ISO_639_3 = "mrd"
EXPECTED_RESOURCE_ID = "mrd-apk"
EXPECTED_PROFILE_ID = "mrd-Deva-NP"
EXPECTED_INPUT_METHOD_ID = "mrd-deva-direct"
EXPECTED_LOOKUP_KIND = "surface_prefix"
EXPECTED_PENDING_LAYOUT_ID = "pending-mrd-deva-direct"
EXPECTED_HEADER = ("mrd_headword", "nepali_gloss", "english_gloss")
EXPECTED_RECORDS = 1_264
EXPECTED_BYTES = 68_724
EXPECTED_SHA256 = "d55d34e4c4d754ee1bbcf3382f3250690e53884020c06305e34bfc1a7948591a"
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
    "Pinned Western Magar raw TSV schema, pending direct-profile identity, "
    "per-column value/scalar inventory, and neutral scalar-emission layout "
    "coverage only; candidate and headword semantics, filtering, "
    "normalization policy, joiner policy, layout selection, prefix vectors, "
    "pack construction, and profile promotion remain unselected."
)


class AuditError(ValueError):
    """Raised when an audit input or output violates the pinned contract."""


@dataclass(frozen=True)
class StringOccurrence:
    value: str
    row: int


@dataclass(frozen=True)
class LayoutScalars:
    layout_id: str
    input_script: str
    scalars: frozenset[int]


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
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AuditError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
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


def _validate_unicode_scalars(value: object, location: str) -> None:
    if isinstance(value, str):
        for index, character in enumerate(value):
            if character == "\x00":
                raise AuditError(f"{location} contains NUL at string index {index}")
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


def _decode_json(encoded: bytes, label: str) -> dict[str, Any]:
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise AuditError(f"{label} must not contain a UTF-8 BOM")
    try:
        decoded = encoded.decode("utf-8")
    except UnicodeError as exc:
        raise AuditError(f"{label} is not UTF-8: {exc}") from exc
    try:
        value = json.loads(
            decoded,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except json.JSONDecodeError as exc:
        raise AuditError(f"{label} is invalid JSON: {exc}") from exc
    except AuditError as exc:
        raise AuditError(f"{label}: {exc}") from exc
    _validate_unicode_scalars(value, label)
    if not isinstance(value, dict):
        raise AuditError(f"{label} must be a JSON object")
    return value


def _read_pinned_json(path: Path, expected: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.resolve() != expected.resolve():
        raise AuditError(f"{label} must be {expected}")
    encoded = _read_regular(path, label)
    return _decode_json(encoded, label), encoded


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
    exact_target_fields = {
        "name": EXPECTED_TARGET_NAME,
        "iso_639_3": EXPECTED_ISO_639_3,
    }
    for key, expected in exact_target_fields.items():
        if target.get(key) != expected:
            raise AuditError(f"catalog target {key} must be {expected!r}")

    methods = target.get("input_methods")
    if not isinstance(methods, list):
        raise AuditError("Western Magar catalog input_methods must be an array")
    direct_methods = [
        item
        for item in methods
        if isinstance(item, dict) and item.get("id") == EXPECTED_INPUT_METHOD_ID
    ]
    if len(direct_methods) != 1:
        raise AuditError(
            f"catalog must contain exactly one {EXPECTED_INPUT_METHOD_ID} input method"
        )
    method = direct_methods[0]
    expected_method_fields = {
        "type": "direct",
        "source_script": "Deva",
        "output_script": "Deva",
        "readiness": "beta",
        "engine_kind": "layout",
    }
    for key, expected in expected_method_fields.items():
        if type(method.get(key)) is not type(expected) or method.get(key) != expected:
            raise AuditError(
                f"catalog {EXPECTED_INPUT_METHOD_ID}.{key} must be {expected!r}"
            )

    resources = target.get("resources")
    if not isinstance(resources, list):
        raise AuditError("Western Magar catalog resources must be an array")
    matches = [
        item
        for item in resources
        if isinstance(item, dict) and item.get("id") == EXPECTED_RESOURCE_ID
    ]
    if len(matches) != 1:
        raise AuditError(
            f"catalog must contain exactly one {EXPECTED_RESOURCE_ID} resource"
        )
    resource = matches[0]
    expected_resource_fields = {
        "kind": "lexicon",
        "path": EXPECTED_CATALOG_RESOURCE_PATH,
        "format": "TSV",
        "structured": True,
        "canonical": True,
        "record_unit": "entries",
        "records": EXPECTED_RECORDS,
        "bytes": EXPECTED_BYTES,
        "sha256": EXPECTED_SHA256,
    }
    for key, expected in expected_resource_fields.items():
        actual = resource.get(key)
        if type(actual) is not type(expected) or actual != expected:
            raise AuditError(
                f"catalog {EXPECTED_RESOURCE_ID}.{key} must be {expected!r}"
            )
    uses = resource.get("uses")
    if not isinstance(uses, list) or "candidate_vocabulary" not in uses:
        raise AuditError("Western Magar resource must declare candidate_vocabulary use")
    _positive_int(resource.get("records"), "catalog resource records")
    _positive_int(resource.get("bytes"), "catalog resource bytes")
    return target, resource


def _profile_binding(profile_lock: dict[str, Any]) -> dict[str, Any]:
    profiles = profile_lock.get("profiles")
    if not isinstance(profiles, list):
        raise AuditError("profile lock profiles must be an array")
    matches = [
        item
        for item in profiles
        if isinstance(item, dict) and item.get("profile_id") == EXPECTED_PROFILE_ID
    ]
    if len(matches) != 1:
        raise AuditError(
            f"profile lock must contain exactly one {EXPECTED_PROFILE_ID} profile"
        )
    profile = matches[0]
    expected_fields: dict[str, object] = {
        "target_id": EXPECTED_TARGET_ID,
        "display_label": EXPECTED_TARGET_NAME,
        "native_label": EXPECTED_TARGET_NAME,
        "input_method_id": EXPECTED_INPUT_METHOD_ID,
        "source_script": "Deva",
        "output_script": "Deva",
        "method_type": "direct",
        "engine_kind": "layout",
        "lookup_kind": EXPECTED_LOOKUP_KIND,
        "layout_id": EXPECTED_PENDING_LAYOUT_ID,
        "layout_revision": None,
        "layout_source_sha256": None,
        "pack_artifact": None,
        "pack_binding": None,
        "selectable": False,
        "default_enabled": False,
    }
    for key, expected in expected_fields.items():
        actual = profile.get(key)
        if type(actual) is not type(expected) or actual != expected:
            raise AuditError(f"profile {EXPECTED_PROFILE_ID}.{key} must be {expected!r}")
    return profile


def _validate_runtime() -> None:
    if sys.version_info[:2] != REQUIRED_PYTHON_VERSION:
        required = ".".join(str(part) for part in REQUIRED_PYTHON_VERSION)
        actual = f"{sys.version_info.major}.{sys.version_info.minor}"
        raise AuditError(f"Western Magar audit requires Python {required}, got {actual}")
    if unicodedata.unidata_version != REQUIRED_UNICODE_VERSION:
        raise AuditError(
            "Western Magar audit requires Unicode data "
            f"{REQUIRED_UNICODE_VERSION}, got {unicodedata.unidata_version}"
        )


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
        current = first_by_value.get(occurrence.value)
        if current is None or occurrence.row < current.row:
            first_by_value[occurrence.value] = occurrence
    examples: list[dict[str, object]] = []
    for value in sorted(first_by_value)[:EXAMPLE_LIMIT]:
        occurrence = first_by_value[value]
        examples.append({
            "first_data_row": occurrence.row,
            "original_scalar_length": len(value),
            "truncated": len(value) > EXAMPLE_SCALAR_LIMIT,
            "value": value[:EXAMPLE_SCALAR_LIMIT],
            "value_sha256": _sha256_bytes(value.encode("utf-8")),
        })
    return examples


def _layout_coverage(
    occurrences: list[StringOccurrence],
    layouts: list[LayoutScalars],
) -> list[dict[str, object]]:
    required: Counter[int] = Counter()
    value_scalars: list[set[int]] = []
    for occurrence in occurrences:
        scalars = {ord(character) for character in occurrence.value if not character.isspace()}
        value_scalars.append(scalars)
        required.update(
            ord(character) for character in occurrence.value if not character.isspace()
        )
    results: list[dict[str, object]] = []
    for layout in layouts:
        missing = Counter({
            codepoint: count
            for codepoint, count in required.items()
            if codepoint not in layout.scalars
        })
        results.append({
            "emitted_scalar_count": len(layout.scalars),
            "input_script": layout.input_script,
            "layout_id": layout.layout_id,
            "missing_distinct_nonwhitespace_scalars": len(missing),
            "missing_nonwhitespace_scalar_frequencies": _frequency_rows(missing),
            "missing_nonwhitespace_scalar_occurrences": sum(missing.values()),
            "required_distinct_nonwhitespace_scalars": len(required),
            "values_fully_scalar_covered": sum(
                scalars.issubset(layout.scalars) for scalars in value_scalars
            ),
        })
    return results


def _string_inventory(
    occurrences: list[StringOccurrence],
    layouts: list[LayoutScalars],
) -> dict[str, object]:
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
        _validate_unicode_scalars(value, f"TSV data row {occurrence.row}")
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
        "empty_values": sum(not value for value in values),
        "examples": _examples(occurrences),
        "example_limit": EXAMPLE_LIMIT,
        "example_scalar_limit": EXAMPLE_SCALAR_LIMIT,
        "format_scalar_frequencies": _frequency_rows(format_frequencies),
        "joiners": joiner_report,
        "layout_scalar_coverage": _layout_coverage(occurrences, layouts),
        "nfc_changed_values": sum(
            unicodedata.normalize("NFC", value) != value for value in values
        ),
        "nonblank_after_strip_values": sum(bool(value.strip()) for value in values),
        "nonempty_values": sum(bool(value) for value in values),
        "null_values": 0,
        "strip_changed_values": sum(value.strip() != value for value in values),
        "values": len(values),
        "values_with_control_characters": values_with_controls,
        "values_with_devanagari_letters": values_with_devanagari,
        "values_with_format_characters": values_with_formats,
        "values_with_latin_letters": values_with_latin,
        "values_with_other_letters": values_with_other_letters,
    }


def _layout_scalars(layout_lock: dict[str, Any]) -> list[LayoutScalars]:
    layouts = layout_lock.get("layouts")
    if not isinstance(layouts, list):
        raise AuditError("layout lock layouts must be an array")
    seen: set[str] = set()
    result: list[LayoutScalars] = []
    for layout_index, layout in enumerate(layouts):
        if not isinstance(layout, dict):
            raise AuditError(f"layout lock layout {layout_index} must be an object")
        layout_id = layout.get("layout_id")
        input_script = layout.get("input_script")
        if not isinstance(layout_id, str) or not layout_id:
            raise AuditError(f"layout lock layout {layout_index} has invalid layout_id")
        if layout_id in seen:
            raise AuditError(f"layout lock repeats layout_id {layout_id}")
        seen.add(layout_id)
        if not isinstance(input_script, str) or not input_script:
            raise AuditError(f"layout {layout_id} has invalid input_script")
        if input_script != "Deva":
            continue
        layers = layout.get("layers")
        if not isinstance(layers, dict) or not layers:
            raise AuditError(f"layout {layout_id} layers must be an object")
        emitted: set[int] = set()
        for layer_name, layer in layers.items():
            if not isinstance(layer_name, str) or not isinstance(layer, dict):
                raise AuditError(f"layout {layout_id} has an invalid layer")
            rows = layer.get("rows")
            if not isinstance(rows, list):
                raise AuditError(f"layout {layout_id} layer {layer_name} rows must be an array")
            for row_index, row in enumerate(rows):
                if not isinstance(row, list):
                    raise AuditError(
                        f"layout {layout_id} layer {layer_name} row {row_index} must be an array"
                    )
                for key_index, key in enumerate(row):
                    if not isinstance(key, dict):
                        raise AuditError(
                            f"layout {layout_id} layer {layer_name} row {row_index} "
                            f"key {key_index} must be an object"
                        )
                    text = key.get("text")
                    if text is None:
                        continue
                    if not isinstance(text, str) or not text:
                        raise AuditError(
                            f"layout {layout_id} layer {layer_name} row {row_index} "
                            f"key {key_index} text must be null or non-empty string"
                        )
                    _validate_unicode_scalars(text, f"layout {layout_id} key text")
                    emitted.update(ord(character) for character in text)
        result.append(LayoutScalars(layout_id, input_script, frozenset(emitted)))
    if not result:
        raise AuditError("layout lock contains no Devanagari layouts")
    return sorted(result, key=lambda item: item.layout_id)


def _parse_tsv(
    input_bytes: bytes,
    layouts: list[LayoutScalars],
) -> tuple[list[tuple[str, str, str]], dict[str, object]]:
    if input_bytes.startswith(b"\xef\xbb\xbf"):
        raise AuditError("Western Magar TSV must not contain a UTF-8 BOM")
    if b"\x00" in input_bytes:
        raise AuditError("Western Magar TSV must not contain NUL")
    if input_bytes and not input_bytes.endswith(b"\n"):
        raise AuditError("Western Magar TSV must be LF-terminated")
    if b"\r" in input_bytes:
        raise AuditError("Western Magar TSV must use LF line endings")
    try:
        decoded = input_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise AuditError(f"Western Magar TSV is not valid UTF-8: {exc}") from exc
    if not decoded:
        raise AuditError("Western Magar TSV must not be empty")
    expected_header = "\t".join(EXPECTED_HEADER)
    if decoded.split("\n", 1)[0] != expected_header:
        raise AuditError(f"Western Magar TSV header must be {EXPECTED_HEADER!r}")
    try:
        reader = csv.reader(
            io.StringIO(decoded, newline=""),
            delimiter="\t",
            strict=True,
        )
        header = next(reader)
        if tuple(header) != EXPECTED_HEADER:
            raise AuditError(f"Western Magar TSV header must be {EXPECTED_HEADER!r}")
        rows: list[tuple[str, str, str]] = []
        occurrences = {name: [] for name in EXPECTED_HEADER}
        for data_row, parsed in enumerate(reader, 1):
            if len(parsed) != len(EXPECTED_HEADER):
                raise AuditError(
                    f"Western Magar TSV data row {data_row} must have exactly "
                    f"{len(EXPECTED_HEADER)} columns, got {len(parsed)}"
                )
            for column, value in zip(EXPECTED_HEADER, parsed, strict=True):
                _validate_unicode_scalars(value, f"TSV data row {data_row} column {column}")
                occurrences[column].append(StringOccurrence(value, data_row))
            rows.append((parsed[0], parsed[1], parsed[2]))
    except csv.Error as exc:
        raise AuditError(f"Western Magar TSV is malformed: {exc}") from exc
    if len(rows) != EXPECTED_RECORDS:
        raise AuditError(
            f"Western Magar TSV data row count must be {EXPECTED_RECORDS}, got {len(rows)}"
        )
    return rows, {
        "column_inventories": [
            {
                "column": name,
                "index": index,
                "string_values": _string_inventory(occurrences[name], layouts),
            }
            for index, name in enumerate(EXPECTED_HEADER)
        ],
        "columns_per_row": len(EXPECTED_HEADER),
        "data_rows": len(rows),
        "encoding": "UTF-8",
        "header": list(EXPECTED_HEADER),
        "lf_terminated": True,
        "null_representation": "none; empty TSV fields are inventoried as empty strings",
    }


def build_audit(args: argparse.Namespace) -> dict[str, object]:
    """Build the deterministic neutral Western Magar source report."""

    _validate_runtime()
    catalog, catalog_bytes = _read_pinned_json(
        args.resource_catalog,
        EXPECTED_CATALOG_PATH,
        "resource catalog",
    )
    _target, resource = _catalog_binding(catalog)
    profile_lock, profile_bytes = _read_pinned_json(
        args.profile_lock,
        EXPECTED_PROFILE_LOCK_PATH,
        "profile lock",
    )
    profile = _profile_binding(profile_lock)
    layout_lock, layout_bytes = _read_pinned_json(
        args.layout_lock,
        EXPECTED_LAYOUT_LOCK_PATH,
        "layout lock",
    )
    layouts = _layout_scalars(layout_lock)
    if args.western_magar_tsv.resolve() != EXPECTED_REMOTE_RAW_PATH.resolve():
        raise AuditError(f"Western Magar raw input must be {EXPECTED_REMOTE_RAW_PATH}")
    input_bytes = _read_regular(args.western_magar_tsv, "Western Magar raw TSV")
    if len(input_bytes) != EXPECTED_BYTES:
        raise AuditError(
            f"Western Magar raw byte count must be {EXPECTED_BYTES}, got {len(input_bytes)}"
        )
    actual_sha256 = _sha256_bytes(input_bytes)
    if actual_sha256 != EXPECTED_SHA256:
        raise AuditError(
            f"Western Magar raw SHA-256 must be {EXPECTED_SHA256}, got {actual_sha256}"
        )
    rows, contract = _parse_tsv(input_bytes, layouts)
    auditor_path = Path(__file__).resolve()
    return {
        "auditor": {
            "name": AUDITOR_NAME,
            "path": "tools/audit_western_magar_tsv_contract.py",
            "sha256": _sha256_bytes(_read_regular(auditor_path, "auditor source")),
            "version": AUDITOR_VERSION,
        },
        "claim_scope": CLAIM_SCOPE,
        "format_version": FORMAT_VERSION,
        "layout_evidence": {
            "coverage_semantics": "exact non-whitespace scalar emission only",
            "deva_layout_ids": [layout.layout_id for layout in layouts],
            "path": str(EXPECTED_LAYOUT_LOCK_PATH),
            "sha256": _sha256_bytes(layout_bytes),
        },
        "profile_binding": {
            "default_enabled": profile["default_enabled"],
            "input_method_id": profile["input_method_id"],
            "layout_id": profile["layout_id"],
            "lookup_kind": profile["lookup_kind"],
            "path": str(EXPECTED_PROFILE_LOCK_PATH),
            "profile_id": profile["profile_id"],
            "selectable": profile["selectable"],
            "sha256": _sha256_bytes(profile_bytes),
            "target_id": profile["target_id"],
        },
        "raw_input": {
            "bytes": len(input_bytes),
            "catalog_path": str(resource["path"]),
            "path": str(EXPECTED_REMOTE_RAW_PATH),
            "records": len(rows),
            "resource_catalog_sha256": _sha256_bytes(catalog_bytes),
            "resource_id": EXPECTED_RESOURCE_ID,
            "sha256": actual_sha256,
            "target_id": EXPECTED_TARGET_ID,
        },
        "runtime_contract": {
            "python_major_minor": ".".join(
                str(part) for part in REQUIRED_PYTHON_VERSION
            ),
            "unicode_data_version": unicodedata.unidata_version,
        },
        "selections": {
            "candidate_column": None,
            "filter_policy": None,
            "headword_column": None,
            "joiner_policy": None,
            "layout_id": None,
            "normalization_policy": None,
            "pack_id": None,
            "prefix_vectors": [],
            "profile_promotion": False,
        },
        "tsv_contract": contract,
    }


def _existing_mode(path: Path) -> int | None:
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AuditError(f"cannot inspect output path {path}: {exc}") from exc


def _prepare_output_parent(parent: Path) -> None:
    missing: list[Path] = []
    cursor = parent
    while True:
        mode = _existing_mode(cursor)
        if mode is not None:
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise AuditError(
                    f"audit output parent is symbolic or not a directory: {cursor}"
                )
            break
        missing.append(cursor)
        if cursor.parent == cursor:
            raise AuditError("audit output parent has no existing directory ancestor")
        cursor = cursor.parent
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except OSError as exc:
            raise AuditError(f"cannot create audit output parent {directory}: {exc}") from exc
        mode = _existing_mode(directory)
        if mode is None or stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise AuditError(
                f"created audit output parent is not a regular directory: {directory}"
            )


def _write_atomic(path: Path, encoded: bytes) -> None:
    _prepare_output_parent(path.parent)
    mode = _existing_mode(path)
    if mode is not None and (stat.S_ISLNK(mode) or not stat.S_ISREG(mode)):
        raise AuditError("audit output must be absent or a regular non-symbolic file")
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
        mode = _existing_mode(path)
        if mode is not None and (stat.S_ISLNK(mode) or not stat.S_ISREG(mode)):
            raise AuditError("audit output changed to a symbolic or special node")
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _validate_output_path(
    output: Path,
    resource_catalog: Path,
    profile_lock: Path,
    layout_lock: Path,
    western_magar_tsv: Path,
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
        profile_lock.resolve(): "profile lock",
        layout_lock.resolve(): "layout lock",
        western_magar_tsv.resolve(): "Western Magar raw TSV",
        Path(__file__).resolve(): "auditor source",
    }
    if resolved in protected:
        raise AuditError(f"audit output must not overwrite {protected[resolved]}")
    mode = _existing_mode(output)
    if mode is not None:
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise AuditError("audit output must be absent or a regular non-symbolic file")
        for protected_path, label in protected.items():
            try:
                if output.samefile(protected_path):
                    raise AuditError(f"audit output must not alias {label}")
            except FileNotFoundError:
                continue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-catalog", type=Path, required=True)
    parser.add_argument("--profile-lock", type=Path, required=True)
    parser.add_argument("--layout-lock", type=Path, required=True)
    parser.add_argument("--western-magar-tsv", type=Path, required=True)
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
            args.profile_lock,
            args.layout_lock,
            args.western_magar_tsv,
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
