#!/usr/bin/env python3
"""Audit the two pinned Nepal Bhasa TSV lexicons without choosing pack semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


FORMAT_VERSION = 1
AUDITOR_VERSION = 1
AUDITOR_NAME = "audit_nepal_bhasa_tsv_contract"
REQUIRED_PYTHON_VERSION = (3, 14)
REQUIRED_UNICODE_VERSION = "16.0.0"
TARGET_ID = "new"
TARGET_NAME = "Nepal Bhasa"
TEXT_KEY_KINDS = {
    "text",
    "orthographic_word",
    "intra_word_punctuation",
    "deva_conjunct_joiner",
    "deva_terminal_zwnj",
    "newa_conjunct_joiner",
}
TEXT_KEY_SCRIPT_REQUIREMENTS = {
    "deva_conjunct_joiner": "Deva",
    "deva_terminal_zwnj": "Deva",
    "newa_conjunct_joiner": "Newa",
}
REPO = Path(__file__).resolve().parents[1]
EXPECTED_CATALOG = REPO / "catalog/resources.json"
EXPECTED_PROFILE_LOCK = REPO / "catalog/internal-profiles.lock.json"
EXPECTED_LAYOUT_LOCK = REPO / "layouts/internal/layouts-v1.lock.json"

TRILINGUAL = {
    "resource_id": "new-nepali-trilingual",
    "catalog_path": (
        "/Users/cdjk/github/llm/nllb-better/data/lexicons_pdf/new_nepali_trilingual.tsv"
    ),
    "remote_path": Path(
        "/home/cdjk/github/llm/nllb-better/data/lexicons_pdf/new_nepali_trilingual.tsv"
    ),
    "header": ("newar", "nepali"),
    "uses": ("candidate_vocabulary", "spellcheck"),
    "records": 9708,
    "bytes": 543567,
    "sha256": "4167c21626674fd1e71bd814c6b2bbb33d2d35ab0f5d5bb071b7b43e071d7929",
}
APK = {
    "resource_id": "new-apk-english",
    "catalog_path": (
        "/Users/cdjk/github/llm/nllb-better/data/lexicons_apk/new_apk_eng_lexicon.tsv"
    ),
    "remote_path": Path(
        "/home/cdjk/github/llm/nllb-better/data/lexicons_apk/new_apk_eng_lexicon.tsv"
    ),
    "header": ("newar", "english", "transliteration"),
    "uses": ("candidate_vocabulary", "roman_aliases"),
    "records": 5727,
    "bytes": 404596,
    "sha256": "470be5aaf526d2dca973044fa5ca9a69b4259854958456145661bd58d4889b41",
}
METHOD_PINS = {
    "new-deva-direct": ("direct", "Deva", "Deva", "beta", "layout"),
    "new-newa-direct": ("direct", "Newa", "Newa", "research", "layout"),
    "new-latn-deva": (
        "roman_phonetic",
        "Latn",
        "Deva",
        "research",
        "alias_decoder",
    ),
    "new-deva-newa": (
        "script_conversion",
        "Deva",
        "Newa",
        "research",
        "converter",
    ),
}
PROFILE_PINS = {
    "new-Deva-NP": (
        "new-deva-direct",
        "Deva",
        "Deva",
        "pending-new-deva-direct",
        "surface_prefix",
        "direct",
        "layout",
        "beta",
    ),
    "new-Newa-NP": (
        "new-newa-direct",
        "Newa",
        "Newa",
        "pending-new-newa-direct",
        "surface_prefix",
        "direct",
        "layout",
        "research",
    ),
    "new-Latn-Deva-NP": (
        "new-latn-deva",
        "Latn",
        "Deva",
        "latn-qwerty-us-v1",
        "alias_prefix",
        "roman_phonetic",
        "alias_decoder",
        "research",
    ),
    "new-Deva-Newa-NP": (
        "new-deva-newa",
        "Deva",
        "Newa",
        "pending-new-deva-newa",
        "conversion",
        "script_conversion",
        "converter",
        "research",
    ),
}
CLAIM_SCOPE = (
    "Measured the two pinned Nepal Bhasa TSV schemas, separate per-column Unicode "
    "inventories, exact raw newar-column overlap, and scalar-only Devanagari layout "
    "coverage. No rows were merged and all candidate, alternative-splitting, filter, "
    "normalization, joiner, layout, Roman-alias, conversion, prefix, pack, and profile "
    "promotion decisions remain unselected."
)


class AuditError(ValueError):
    """Raised when a pinned input or neutral source contract is violated."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_compact_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(encoded)


def _read_regular(path: Path, label: str) -> bytes:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise AuditError(f"cannot inspect {label}: {path}: {exc}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise AuditError(f"{label} must be a regular non-symbolic file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AuditError(f"cannot read {label}: {path}: {exc}") from exc


def _require_canonical_path(path: Path, expected: Path, label: str) -> None:
    if (
        not path.is_absolute()
        or path != path.resolve(strict=False)
        or path != expected.resolve()
    ):
        raise AuditError(f"{label} must use the canonical path {expected.resolve()}")


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise AuditError(f"JSON contains non-finite number {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise AuditError(f"JSON contains non-finite number {value}")
    return parsed


def _validate_json_scalars(value: Any, label: str) -> None:
    if isinstance(value, str):
        _validate_scalars(value, label)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json_scalars(child, f"{label}[{index}]")
    elif isinstance(value, dict):
        for key, child in value.items():
            _validate_scalars(key, f"{label} object key")
            _validate_json_scalars(child, f"{label}.{key}")


def _load_json(path: Path, expected: Path, label: str) -> tuple[dict[str, Any], bytes]:
    _require_canonical_path(path, expected, label)
    encoded = _read_regular(path, label)
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise AuditError(f"{label} must not contain a UTF-8 BOM")
    try:
        value = json.loads(
            encoded,
            object_pairs_hook=_json_object,
            parse_constant=_reject_constant,
            parse_float=_parse_finite_float,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot decode {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"{label} must contain one JSON object")
    _validate_json_scalars(value, label)
    return value, encoded


def _validate_runtime() -> None:
    actual = sys.version_info[:2]
    if actual != REQUIRED_PYTHON_VERSION:
        raise AuditError(
            f"Nepal Bhasa audit requires Python {REQUIRED_PYTHON_VERSION}, got {actual}"
        )
    if unicodedata.unidata_version != REQUIRED_UNICODE_VERSION:
        raise AuditError(
            "Nepal Bhasa audit requires Unicode data "
            f"{REQUIRED_UNICODE_VERSION}, got {unicodedata.unidata_version}"
        )


def _one(items: list[Any], label: str) -> Any:
    if len(items) != 1:
        raise AuditError(f"{label} must occur exactly once, got {len(items)}")
    return items[0]


def _catalog_bindings(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packs = catalog.get("packs")
    if not isinstance(packs, list):
        raise AuditError("resource catalog packs must be an array")
    target = _one(
        [
            item
            for item in packs
            if isinstance(item, dict) and item.get("id") == TARGET_ID
        ],
        "Nepal Bhasa catalog target",
    )
    if target.get("name") != TARGET_NAME or target.get("iso_639_3") != TARGET_ID:
        raise AuditError("Nepal Bhasa catalog identity drifted")
    if target.get("scope") != "language":
        raise AuditError("Nepal Bhasa catalog scope drifted")
    scripts = target.get("scripts")
    expected_scripts = {
        "Deva": ("Devanagari", "widely_used"),
        "Newa": ("Newa/Prachalit Nepal Lipi", "traditional"),
    }
    if not isinstance(scripts, list) or len(scripts) != len(expected_scripts):
        raise AuditError("Nepal Bhasa catalog scripts drifted")
    for script_code, (script_name, role) in expected_scripts.items():
        script = _one(
            [
                item
                for item in scripts
                if isinstance(item, dict) and item.get("iso_15924") == script_code
            ],
            f"catalog script {script_code}",
        )
        if script.get("name") != script_name or script.get("role") != role:
            raise AuditError(f"catalog script {script_code} drifted")
    methods = target.get("input_methods")
    if not isinstance(methods, list):
        raise AuditError("Nepal Bhasa input_methods must be an array")
    method_ids = [item.get("id") for item in methods if isinstance(item, dict)]
    if (
        len(method_ids) != len(methods)
        or not all(isinstance(method_id, str) for method_id in method_ids)
        or set(method_ids) != set(METHOD_PINS)
    ):
        raise AuditError("Nepal Bhasa catalog input-method membership drifted")
    for method_id, expected in METHOD_PINS.items():
        method = _one(
            [
                item
                for item in methods
                if isinstance(item, dict) and item.get("id") == method_id
            ],
            f"catalog input method {method_id}",
        )
        method_type, source_script, output_script, readiness, engine_kind = expected
        required_method = {
            "type": method_type,
            "source_script": source_script,
            "output_script": output_script,
            "readiness": readiness,
            "engine_kind": engine_kind,
        }
        for key, value in required_method.items():
            if type(method.get(key)) is not type(value) or method.get(key) != value:
                raise AuditError(f"catalog input method {method_id} {key} drifted")
    resources = target.get("resources")
    if not isinstance(resources, list):
        raise AuditError("Nepal Bhasa resources must be an array")
    result: dict[str, dict[str, Any]] = {}
    for specification in (TRILINGUAL, APK):
        resource_id = str(specification["resource_id"])
        resource = _one(
            [
                item
                for item in resources
                if isinstance(item, dict) and item.get("id") == resource_id
            ],
            f"catalog resource {resource_id}",
        )
        required_resource = {
            "kind": "lexicon",
            "path": specification["catalog_path"],
            "format": "TSV",
            "structured": True,
            "quality": "needs_audit",
            "record_unit": "entries",
            "records": specification["records"],
            "bytes": specification["bytes"],
            "sha256": specification["sha256"],
            "evidence_type": "attested",
        }
        for key, value in required_resource.items():
            if type(resource.get(key)) is not type(value) or resource.get(key) != value:
                raise AuditError(f"catalog resource {resource_id} {key} drifted")
        uses = resource.get("uses")
        if not isinstance(uses, list) or tuple(uses) != specification["uses"]:
            raise AuditError(f"catalog resource {resource_id} uses drifted")
        result[resource_id] = resource
    return result


def _profile_bindings(lock: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = lock.get("profiles")
    if not isinstance(profiles, list):
        raise AuditError("internal profile lock profiles must be an array")
    target_profiles = [
        profile
        for profile in profiles
        if isinstance(profile, dict) and profile.get("target_id") == TARGET_ID
    ]
    target_profile_ids = [profile.get("profile_id") for profile in target_profiles]
    if (
        len(target_profile_ids) != len(PROFILE_PINS)
        or not all(isinstance(profile_id, str) for profile_id in target_profile_ids)
        or set(target_profile_ids) != set(PROFILE_PINS)
    ):
        raise AuditError("Nepal Bhasa profile membership drifted")
    bindings: list[dict[str, Any]] = []
    for profile_id, expected in PROFILE_PINS.items():
        profile = _one(
            [
                item
                for item in profiles
                if isinstance(item, dict) and item.get("profile_id") == profile_id
            ],
            f"profile {profile_id}",
        )
        (
            input_method,
            source_script,
            output_script,
            layout_id,
            lookup_kind,
            method_type,
            engine_kind,
            readiness,
        ) = expected
        required = {
            "target_id": TARGET_ID,
            "input_method_id": input_method,
            "source_script": source_script,
            "output_script": output_script,
            "layout_id": layout_id,
            "layout_revision": None,
            "layout_source_sha256": None,
            "lookup_kind": lookup_kind,
            "method_type": method_type,
            "engine_kind": engine_kind,
            "catalog_readiness": readiness,
            "language_tag": "new-NP",
            "scope": "language",
            "selectable": False,
            "default_enabled": False,
            "pack_artifact": None,
            "pack_binding": None,
        }
        for key, value in required.items():
            if type(profile.get(key)) is not type(value) or profile.get(key) != value:
                raise AuditError(f"profile {profile_id} {key} drifted")
        if profile.get("evidence_ids") != [] or profile.get("evidence_artifacts") != []:
            raise AuditError(
                f"profile {profile_id} unexpectedly has promotion evidence"
            )
        bindings.append(
            {
                key: profile.get(key)
                for key in (
                    "profile_id",
                    "input_method_id",
                    "source_script",
                    "output_script",
                    "layout_id",
                    "layout_revision",
                    "layout_source_sha256",
                    "lookup_kind",
                    "method_type",
                    "engine_kind",
                    "catalog_readiness",
                    "language_tag",
                    "scope",
                    "selectable",
                    "default_enabled",
                    "pack_artifact",
                    "pack_binding",
                    "evidence_ids",
                    "evidence_artifacts",
                )
            }
        )
    return bindings


def _deva_layouts(lock: dict[str, Any]) -> list[tuple[str, set[int]]]:
    layouts = lock.get("layouts")
    if not isinstance(layouts, list):
        raise AuditError("layout lock layouts must be an array")
    result: list[tuple[str, set[int]]] = []
    seen: set[str] = set()
    for layout_index, layout in enumerate(layouts):
        if not isinstance(layout, dict):
            raise AuditError(f"layout lock layout {layout_index} must be an object")
        layout_id = layout.get("layout_id")
        if not isinstance(layout_id, str) or not layout_id:
            raise AuditError(f"layout lock layout {layout_index} has invalid layout_id")
        if layout_id in seen:
            raise AuditError(f"layout lock repeats layout_id {layout_id}")
        seen.add(layout_id)
        input_script = layout.get("input_script")
        if not isinstance(input_script, str) or not input_script:
            raise AuditError(f"layout {layout_id} input_script is malformed")
        if input_script != "Deva":
            continue
        layers = layout.get("layers")
        if not isinstance(layers, dict) or not layers:
            raise AuditError(f"Devanagari layout {layout_id} layers are malformed")
        scalars: set[int] = set()
        for layer_name, layer in layers.items():
            if not isinstance(layer_name, str) or not isinstance(layer, dict):
                raise AuditError(f"Devanagari layout {layout_id} has malformed layer")
            rows = layer.get("rows")
            if not isinstance(rows, list):
                raise AuditError(f"Devanagari layout {layout_id} rows are malformed")
            for row_index, row in enumerate(rows):
                if not isinstance(row, list):
                    raise AuditError(
                        f"Devanagari layout {layout_id} row {row_index} is malformed"
                    )
                for key_index, key in enumerate(row):
                    if not isinstance(key, dict):
                        raise AuditError(
                            f"Devanagari layout {layout_id} key {key_index} is malformed"
                        )
                    kind = key.get("kind")
                    if kind == "action":
                        if key.get("text") is not None:
                            raise AuditError(
                                f"Devanagari layout {layout_id} action text is malformed"
                            )
                        continue
                    if kind not in TEXT_KEY_KINDS:
                        raise AuditError(
                            f"Devanagari layout {layout_id} key kind is malformed"
                        )
                    required_script = TEXT_KEY_SCRIPT_REQUIREMENTS.get(kind)
                    if required_script is not None and required_script != input_script:
                        raise AuditError(
                            f"layout {layout_id} key kind {kind} requires input script "
                            f"{required_script}"
                        )
                    text = key.get("text")
                    if not isinstance(text, str) or not text:
                        raise AuditError(
                            f"Devanagari layout {layout_id} text key is malformed"
                        )
                    _validate_scalars(text, f"Devanagari layout {layout_id} text key")
                    scalars.update(ord(character) for character in text)
        result.append((layout_id, scalars))
    if not result:
        raise AuditError("layout lock contains no Devanagari layout")
    result.sort(key=lambda item: item[0])
    return result


def _script(code_point: int) -> str:
    if 0x0900 <= code_point <= 0x097F or 0xA8E0 <= code_point <= 0xA8FF:
        return "Deva"
    if 0x11B00 <= code_point <= 0x11B5F:
        return "Deva"
    if 0x11400 <= code_point <= 0x1147F:
        return "Newa"
    name = unicodedata.name(chr(code_point), "")
    if "LATIN" in name:
        return "Latn"
    category = unicodedata.category(chr(code_point))
    if chr(code_point).isspace():
        return "Whitespace"
    if category[0] in {"P", "N", "S"}:
        return "Common"
    return "Other"


def _scalar_label(code_point: int) -> str:
    return f"U+{code_point:04X}"


def _validate_scalars(value: str, label: str) -> None:
    for character in value:
        code_point = ord(character)
        if code_point == 0:
            raise AuditError(f"{label} contains U+0000")
        if 0xD800 <= code_point <= 0xDFFF:
            raise AuditError(f"{label} contains an unpaired surrogate escape")


def _inventory(values: list[str]) -> dict[str, Any]:
    counts = Counter(values)
    scalar_counts: Counter[int] = Counter()
    script_counts: Counter[str] = Counter()
    control_counts: Counter[int] = Counter()
    format_counts: Counter[int] = Counter()
    for value in values:
        for character in value:
            code_point = ord(character)
            scalar_counts[code_point] += 1
            script_counts[_script(code_point)] += 1
            category = unicodedata.category(character)
            if category == "Cc":
                control_counts[code_point] += 1
            if category == "Cf":
                format_counts[code_point] += 1
    duplicate_values = [
        {"count": count, "value": value}
        for value, count in sorted(counts.items())
        if value and count > 1
    ]
    duplicate_values_sha256 = _canonical_compact_sha256(duplicate_values)
    semicolon_segment_counts = Counter(
        len(value.split(";")) for value in values if ";" in value
    )
    return {
        "control_scalars": [
            {"count": count, "scalar": _scalar_label(code_point)}
            for code_point, count in sorted(control_counts.items())
        ],
        "distinct_values": len(counts),
        "duplicate_nonempty_extra_occurrences": sum(
            item["count"] - 1 for item in duplicate_values
        ),
        "duplicate_nonempty_value_groups": len(duplicate_values),
        "duplicate_nonempty_values": duplicate_values[:32],
        "duplicate_nonempty_values_sha256": duplicate_values_sha256,
        "empty_values": counts.get("", 0),
        "format_scalars": [
            {"count": count, "scalar": _scalar_label(code_point)}
            for code_point, count in sorted(format_counts.items())
        ],
        "joiner_contexts": {
            "values_with_zwnj": sum("\u200c" in value for value in values),
            "values_with_zwj": sum("\u200d" in value for value in values),
            "zwnj_after_devanagari_virama": sum("्\u200c" in value for value in values),
            "zwj_after_devanagari_virama": sum("्\u200d" in value for value in values),
        },
        "leading_or_trailing_whitespace_values": sum(
            value != value.strip() for value in values
        ),
        "multiword_values": sum(
            any(character.isspace() for character in value.strip()) for value in values
        ),
        "nfc_changed_values": sum(
            unicodedata.normalize("NFC", value) != value for value in values
        ),
        "nonempty_values": len(values) - counts.get("", 0),
        "scalar_frequencies": [
            {
                "character": chr(code_point),
                "count": count,
                "name": unicodedata.name(chr(code_point), "<unassigned>"),
                "scalar": _scalar_label(code_point),
                "script": _script(code_point),
            }
            for code_point, count in sorted(scalar_counts.items())
        ],
        "script_scalar_occurrences": dict(sorted(script_counts.items())),
        "semicolon_segment_count_distribution": [
            {"cells": count, "segments": segments}
            for segments, count in sorted(semicolon_segment_counts.items())
        ],
        "semicolon_values": sum(";" in value for value in values),
        "values": len(values),
    }


def _layout_coverage(
    values: list[str],
    layouts: list[tuple[str, set[int]]],
) -> list[dict[str, Any]]:
    required = {
        ord(character)
        for value in values
        for character in value
        if not character.isspace()
    }
    return [
        {
            "covered_required_scalars": len(required & emitted),
            "emitted_scalars": len(emitted),
            "layout_id": layout_id,
            "missing_required_scalars": [
                _scalar_label(code_point) for code_point in sorted(required - emitted)
            ],
            "required_scalars": len(required),
        }
        for layout_id, emitted in layouts
    ]


def _parse_tsv(
    encoded: bytes,
    specification: dict[str, Any],
    layouts: list[tuple[str, set[int]]],
) -> tuple[dict[str, Any], set[str]]:
    resource_id = str(specification["resource_id"])
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise AuditError(f"{resource_id} must not contain a UTF-8 BOM")
    if not encoded.endswith(b"\n"):
        raise AuditError(f"{resource_id} must be LF-terminated")
    if b"\r" in encoded:
        raise AuditError(f"{resource_id} must use LF line endings")
    try:
        decoded = encoded.decode("utf-8")
    except UnicodeError as exc:
        raise AuditError(f"{resource_id} is not valid UTF-8: {exc}") from exc
    physical_lines = decoded[:-1].split("\n")
    expected_header = tuple(specification["header"])
    if not physical_lines or physical_lines[0] != "\t".join(expected_header):
        raise AuditError(f"{resource_id} header must be {expected_header!r}")
    columns: dict[str, list[str]] = {column: [] for column in expected_header}
    rows: list[tuple[str, ...]] = []
    for row_number, line in enumerate(physical_lines[1:], 1):
        fields = tuple(line.split("\t"))
        if len(fields) != len(expected_header):
            raise AuditError(
                f"{resource_id} data row {row_number} must have exactly "
                f"{len(expected_header)} columns, got {len(fields)}"
            )
        for column, value in zip(expected_header, fields, strict=True):
            _validate_scalars(value, f"{resource_id} row {row_number} column {column}")
            columns[column].append(value)
        rows.append(fields)
    if len(rows) != specification["records"]:
        raise AuditError(
            f"{resource_id} row count must be {specification['records']}, got {len(rows)}"
        )
    newar_values = columns["newar"]
    row_counts = Counter(rows)
    duplicate_rows = [
        {"count": count, "row": list(row)}
        for row, count in sorted(row_counts.items())
        if count > 1
    ]
    transliteration_coverage = None
    if "transliteration" in columns:
        transliterations = columns["transliteration"]
        transliteration_coverage = {
            "distinct_nonempty_values": len(
                {value for value in transliterations if value}
            ),
            "empty_values": sum(not value for value in transliterations),
            "newar_rows": len(newar_values),
            "nonempty_newar_rows": sum(bool(value) for value in newar_values),
            "nonempty_newar_rows_with_nonempty_transliteration": sum(
                bool(newar) and bool(transliteration)
                for newar, transliteration in zip(
                    newar_values,
                    transliterations,
                    strict=True,
                )
            ),
            "nonempty_values": sum(bool(value) for value in transliterations),
        }
    return {
        "column_inventories": [
            {
                "column": column,
                "index": index,
                "string_values": _inventory(columns[column]),
            }
            for index, column in enumerate(expected_header)
        ],
        "columns_per_row": len(expected_header),
        "data_rows": len(rows),
        "encoding": "UTF-8",
        "header": list(expected_header),
        "layout_coverage_for_raw_newar_column": _layout_coverage(newar_values, layouts),
        "lf_terminated": True,
        "raw_duplicate_extra_occurrences": sum(
            item["count"] - 1 for item in duplicate_rows
        ),
        "raw_duplicate_row_groups": len(duplicate_rows),
        "raw_duplicate_rows": duplicate_rows[:32],
        "raw_duplicate_rows_sha256": _canonical_compact_sha256(duplicate_rows),
        "resource_id": resource_id,
        "transliteration_column_coverage": transliteration_coverage,
    }, set(newar_values)


def _read_raw(path: Path, specification: dict[str, Any]) -> bytes:
    expected = Path(specification["remote_path"])
    _require_canonical_path(path, expected, f"{specification['resource_id']} raw input")
    encoded = _read_regular(path, f"{specification['resource_id']} raw TSV")
    if len(encoded) != specification["bytes"]:
        raise AuditError(f"{specification['resource_id']} byte count drifted")
    actual_sha = _sha256(encoded)
    if actual_sha != specification["sha256"]:
        raise AuditError(
            f"{specification['resource_id']} SHA-256 drifted: {actual_sha}"
        )
    return encoded


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    _validate_runtime()
    catalog, catalog_bytes = _load_json(
        args.resource_catalog,
        EXPECTED_CATALOG,
        "resource catalog",
    )
    _catalog_bindings(catalog)
    profile_lock, profile_bytes = _load_json(
        args.profile_lock, EXPECTED_PROFILE_LOCK, "internal profile lock"
    )
    profiles = _profile_bindings(profile_lock)
    layout_lock, layout_bytes = _load_json(
        args.layout_lock, EXPECTED_LAYOUT_LOCK, "internal layout lock"
    )
    layouts = _deva_layouts(layout_lock)
    trilingual_bytes = _read_raw(args.trilingual_tsv, TRILINGUAL)
    apk_bytes = _read_raw(args.apk_tsv, APK)
    trilingual_contract, trilingual_newar = _parse_tsv(
        trilingual_bytes,
        TRILINGUAL,
        layouts,
    )
    apk_contract, apk_newar = _parse_tsv(apk_bytes, APK, layouts)
    overlap = trilingual_newar & apk_newar
    nonempty_overlap = {value for value in overlap if value}
    trilingual_unique = trilingual_newar - apk_newar
    apk_unique = apk_newar - trilingual_newar
    auditor_path = Path(__file__).resolve()
    return {
        "auditor": {
            "name": AUDITOR_NAME,
            "path": "tools/audit_nepal_bhasa_tsv_contract.py",
            "sha256": _sha256(_read_regular(auditor_path, "auditor source")),
            "version": AUDITOR_VERSION,
        },
        "catalog_binding": {
            "path": "catalog/resources.json",
            "resource_ids": [TRILINGUAL["resource_id"], APK["resource_id"]],
            "sha256": _sha256(catalog_bytes),
            "target_id": TARGET_ID,
        },
        "claim_scope": CLAIM_SCOPE,
        "cross_source_raw_newar_overlap": {
            "comparison": "exact raw strings including empty; no normalization or splitting",
            "empty_present_in_both": "" in overlap,
            "exact_overlap_count": len(overlap),
            "exact_overlap_examples": sorted(overlap)[:32],
            "exact_overlap_sha256": _canonical_compact_sha256(sorted(overlap)),
            "exact_nonempty_overlap_count": len(nonempty_overlap),
            "exact_nonempty_overlap_examples": sorted(nonempty_overlap)[:32],
            "exact_nonempty_overlap_sha256": _canonical_compact_sha256(
                sorted(nonempty_overlap)
            ),
            "new_apk_english_nonempty_unique_count": sum(
                bool(value) for value in apk_unique
            ),
            "new_apk_english_unique_count": len(apk_unique),
            "new_apk_english_unique_sha256": _canonical_compact_sha256(
                sorted(apk_unique)
            ),
            "new_nepali_trilingual_nonempty_unique_count": sum(
                bool(value) for value in trilingual_unique
            ),
            "new_nepali_trilingual_unique_count": len(trilingual_unique),
            "new_nepali_trilingual_unique_sha256": _canonical_compact_sha256(
                sorted(trilingual_unique)
            ),
        },
        "format_version": FORMAT_VERSION,
        "layout_evidence": {
            "coverage_semantics": "exact non-whitespace scalar emission only",
            "deva_layout_ids": [layout_id for layout_id, _ in layouts],
            "path": "layouts/internal/layouts-v1.lock.json",
            "sha256": _sha256(layout_bytes),
        },
        "profile_bindings": {
            "path": "catalog/internal-profiles.lock.json",
            "profiles": profiles,
            "sha256": _sha256(profile_bytes),
        },
        "raw_inputs": [
            {
                "bytes": len(encoded),
                "path": str(specification["remote_path"]),
                "records": specification["records"],
                "resource_id": specification["resource_id"],
                "sha256": specification["sha256"],
            }
            for specification, encoded in (
                (TRILINGUAL, trilingual_bytes),
                (APK, apk_bytes),
            )
        ],
        "runtime_contract": {
            "python_major_minor": "3.14",
            "unicode_data_version": unicodedata.unidata_version,
        },
        "selections": {
            "alternative_splitting_policy": None,
            "candidate_columns": {
                str(TRILINGUAL["resource_id"]): None,
                str(APK["resource_id"]): None,
            },
            "candidate_resource_ids": [],
            "conversion_policy": None,
            "filter_policy": None,
            "joiner_policy": None,
            "layout_ids": [],
            "normalization_policy": None,
            "pack_id": None,
            "prefix_vectors": [],
            "profile_promotions": {profile_id: False for profile_id in PROFILE_PINS},
            "roman_alias_policy": None,
        },
        "source_contracts": [trilingual_contract, apk_contract],
    }


def _canonical_bytes(value: Any) -> bytes:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    return (rendered + "\n").encode("utf-8")


def _prepare_output_parent(parent: Path) -> None:
    missing: list[Path] = []
    cursor = parent
    while True:
        try:
            mode = cursor.lstat().st_mode
        except FileNotFoundError:
            missing.append(cursor)
            if cursor.parent == cursor:
                raise AuditError("audit output parent has no existing ancestor")
            cursor = cursor.parent
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise AuditError(
                f"audit output parent is symbolic or not a directory: {cursor}"
            )
        break
    for directory in reversed(missing):
        directory.mkdir()
        mode = directory.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise AuditError(f"created output parent is not a directory: {directory}")


def _validate_output(args: argparse.Namespace) -> None:
    output = args.output
    if not output.is_absolute() or output != output.resolve(strict=False):
        raise AuditError(
            "audit output path must be absolute, canonical, and use no symbolic parents"
        )
    protected = {
        path.resolve()
        for path in (
            args.resource_catalog,
            args.profile_lock,
            args.layout_lock,
            args.trilingual_tsv,
            args.apk_tsv,
            Path(__file__),
        )
    }
    if output.resolve(strict=False) in protected:
        raise AuditError("audit output must not overwrite a protected input")
    try:
        mode = output.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise AuditError("audit output must be absent or a regular non-symbolic file")
    for protected_path in protected:
        try:
            if output.samefile(protected_path):
                raise AuditError("audit output must not hard-link a protected input")
        except FileNotFoundError:
            continue


def _write_atomic(path: Path, encoded: bytes) -> None:
    _prepare_output_parent(path.parent)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            mode = None
        if mode is not None and (stat.S_ISLNK(mode) or not stat.S_ISREG(mode)):
            raise AuditError("audit output changed to a symbolic or special node")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-catalog", type=Path, required=True)
    parser.add_argument("--profile-lock", type=Path, required=True)
    parser.add_argument("--layout-lock", type=Path, required=True)
    parser.add_argument("--trilingual-tsv", type=Path, required=True)
    parser.add_argument("--apk-tsv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _validate_output(args)
        report = build_audit(args)
        encoded = _canonical_bytes(report)
        if args.check:
            if _read_regular(args.output, "audit output") != encoded:
                raise AuditError("audit output is stale")
        else:
            _write_atomic(args.output, encoded)
    except (AuditError, OSError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "report_sha256": _sha256(encoded),
                "status": "passed",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
