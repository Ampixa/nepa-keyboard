#!/usr/bin/env python3
"""Deterministic source adapter for reviewed SIL-APK dictionary JSONL files.

The supported source contract is deliberately narrow: one UTF-8 JSON object
per line with the ordered fields ``lang``, ``headword``, ``ne``, ``en``, and
``source``. Only the headword is emitted as a candidate. Per-language wrapper
modules pin the raw bytes and select an explicitly reviewed joiner policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


HELPER_NAME = "sil_apk_jsonl_internal_source"
HELPER_VERSION = 1
EXPECTED_FIELDS = ("lang", "headword", "ne", "en", "source")
RANK_SCORE = 1_000
ALLOWED_FORMAT_CODEPOINTS = {0x200C, 0x200D}
JOINERS = frozenset(chr(codepoint) for codepoint in ALLOWED_FORMAT_CODEPOINTS)
DEVANAGARI_VIRAMA = "\u094d"
ZERO_WIDTH_NON_JOINER = "\u200c"
DEVA_RANGES = ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x11B00, 0x11B5F))
WHITESPACE_RE = re.compile(r"\s+")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AdapterError(ValueError):
    """Raised when a pinned SIL-APK source violates its reviewed contract."""


@dataclass(frozen=True)
class SilApkConfig:
    """All language-specific values that a thin wrapper must pin."""

    adapter_name: str
    adapter_version: int
    pack_id: str
    source_id: str
    source_sha256: str
    expected_data_rows: int
    language: str
    source_tag: str
    file_name: str
    display_name: str
    variety: str | None
    stable_id_prefix: str
    source_title: str
    license_id: str
    redistribution: str
    allow_terminal_zwnj: bool


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256(path: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise AdapterError(f"{label} is not a regular file: {path}")
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise AdapterError(f"cannot read {label} {path}: {exc}") from exc


def _read_input_snapshot(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AdapterError(f"input is not a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read input {path}: {exc}") from exc


def _normalize_surface(raw: str) -> tuple[str, bool]:
    normalized = WHITESPACE_RE.sub(
        " ",
        unicodedata.normalize("NFC", raw),
    ).strip()
    return normalized, normalized != raw


def _is_devanagari_character(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in DEVA_RANGES)


def _is_devanagari_letter(character: str) -> bool:
    return _is_devanagari_character(character) and unicodedata.category(
        character
    ).startswith("L")


def _has_devanagari_base_before_virama(value: str, joiner_index: int) -> bool:
    index = joiner_index - 2
    while (
        index >= 0
        and _is_devanagari_character(value[index])
        and unicodedata.category(value[index]).startswith("M")
    ):
        index -= 1
    return index >= 0 and _is_devanagari_letter(value[index])


def _is_valid_conjunct_joiner(value: str, index: int) -> bool:
    return (
        1 < index < len(value) - 1
        and value[index - 1] == DEVANAGARI_VIRAMA
        and _has_devanagari_base_before_virama(value, index)
        and _is_devanagari_letter(value[index + 1])
    )


def _is_valid_terminal_zwnj(value: str, index: int) -> bool:
    return (
        value[index] == ZERO_WIDTH_NON_JOINER
        and index == len(value) - 1
        and index > 1
        and value[index - 1] == DEVANAGARI_VIRAMA
        and _has_devanagari_base_before_virama(value, index)
    )


def validate_surface(surface: str, *, allow_terminal_zwnj: bool) -> str | None:
    """Return a stable rejection reason, or ``None`` for an accepted surface."""

    if not surface:
        return "blank_headword"
    has_devanagari_letter = False
    for index, character in enumerate(surface):
        category = unicodedata.category(character)
        if category == "Cf":
            if character not in JOINERS:
                return "unsupported_format_character"
            valid = _is_valid_conjunct_joiner(surface, index)
            if (
                not valid
                and allow_terminal_zwnj
                and _is_valid_terminal_zwnj(surface, index)
            ):
                valid = True
            if not valid:
                return "invalid_joiner_context"
            continue
        if category == "Cc":
            return "control_character"
        if _is_devanagari_character(character):
            if category[0] not in {"L", "M", "N", "P"}:
                return "unsupported_devanagari_character"
            has_devanagari_letter = has_devanagari_letter or category.startswith("L")
            continue
        if category[0] in {"N", "P", "Z"}:
            continue
        if category.startswith("S"):
            return "unsupported_symbol"
        return "outside_devanagari"
    return None if has_devanagari_letter else "no_devanagari_letter"


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise AdapterError(f"duplicate JSON key {key!r}")
        value[key] = child
    return value


def _parse_row(encoded: str, line_number: int, config: SilApkConfig) -> dict[str, object]:
    try:
        value = json.loads(encoded, object_pairs_hook=_strict_object)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"SIL-APK JSONL row {line_number} is invalid JSON: {exc}") from exc
    except AdapterError as exc:
        raise AdapterError(f"SIL-APK JSONL row {line_number}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdapterError(f"SIL-APK JSONL row {line_number} must be an object")
    if tuple(value) != EXPECTED_FIELDS:
        raise AdapterError(
            f"SIL-APK JSONL row {line_number} fields must be exactly "
            f"{EXPECTED_FIELDS} in order"
        )
    for field in ("lang", "headword", "source"):
        if not isinstance(value[field], str):
            raise AdapterError(
                f"SIL-APK JSONL row {line_number} field {field} must be a string"
            )
    for field in ("ne", "en"):
        child = value[field]
        if not isinstance(child, list) or any(not isinstance(item, str) for item in child):
            raise AdapterError(
                f"SIL-APK JSONL row {line_number} field {field} must be an array of strings"
            )
    if value["lang"] != config.language:
        raise AdapterError(
            f"SIL-APK JSONL row {line_number} language must be {config.language!r}"
        )
    if value["source"] != config.source_tag:
        raise AdapterError(
            f"SIL-APK JSONL row {line_number} source must be {config.source_tag!r}"
        )
    return value


def _read_rows(
    input_bytes: bytes,
    config: SilApkConfig,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    if input_bytes.startswith(b"\xef\xbb\xbf"):
        raise AdapterError("SIL-APK JSONL must not contain a UTF-8 BOM")
    if input_bytes and not input_bytes.endswith(b"\n"):
        raise AdapterError("SIL-APK JSONL must be LF-terminated")
    if b"\r" in input_bytes:
        raise AdapterError("SIL-APK JSONL must use LF line endings")
    try:
        decoded = input_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise AdapterError(f"cannot decode SIL-APK JSONL as UTF-8: {exc}") from exc

    lines = decoded.splitlines()
    forms: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    for line_number, encoded in enumerate(lines, 1):
        stats["rows"] += 1
        if not encoded:
            raise AdapterError(f"SIL-APK JSONL row {line_number} is blank")
        row = _parse_row(encoded, line_number, config)
        raw_surface = str(row["headword"])
        surface, normalized = _normalize_surface(raw_surface)
        reason = validate_surface(
            surface,
            allow_terminal_zwnj=config.allow_terminal_zwnj,
        )
        if reason is not None:
            stats["rejected_rows"] += 1
            stats[f"rejected_{reason}"] += 1
            rejected.append({
                "line": line_number,
                "raw_headword": raw_surface,
                "reason": reason,
            })
            continue
        if normalized:
            stats["normalized_rows"] += 1
        forms.append({
            "evidence": "attested",
            "form_id": f"{config.stable_id_prefix}:line-{line_number:06d}",
            "rank_score": RANK_SCORE,
            "source_ids": [config.source_id],
            "surface": surface,
        })
        stats["accepted_rows"] += 1
        if surface.endswith(DEVANAGARI_VIRAMA + ZERO_WIDTH_NON_JOINER):
            stats["accepted_terminal_zwnj_rows"] += 1

    if stats["rows"] != config.expected_data_rows:
        raise AdapterError(
            "SIL-APK JSONL row count mismatch: "
            f"expected {config.expected_data_rows}, got {stats['rows']}"
        )
    if not forms:
        raise AdapterError("SIL-APK JSONL contains no accepted headwords")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: int(row["line"]))
    for key in (
        "accepted_rows",
        "accepted_terminal_zwnj_rows",
        "rejected_rows",
        "normalized_rows",
    ):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len(
        {str(row["surface"]) for row in forms}
    )
    return forms, rejected, dict(sorted(stats.items()))


def build_internal_source(
    args: argparse.Namespace,
    *,
    config: SilApkConfig,
    adapter_path: Path,
    helper_sha256: str,
) -> dict[str, object]:
    """Build canonical compiler tables for one pinned language wrapper."""

    if not SHA256_RE.fullmatch(helper_sha256):
        raise AdapterError("verified helper SHA-256 is malformed")
    input_bytes = _read_input_snapshot(args.sil_apk_jsonl)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != config.source_sha256:
        raise AdapterError(
            "SIL-APK JSONL SHA-256 mismatch: "
            f"expected {config.source_sha256}, got {source_sha256}"
        )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")

    forms, rejected, stats = _read_rows(input_bytes, config)
    source = {
        "license": config.license_id,
        "method": (
            "Pinned SIL Dictionary App Builder JSONL headword field; "
            "NFC and whitespace normalization only"
        ),
        "notes": (
            "Internal product source. Nepali and English gloss arrays are not "
            "candidate surfaces or ranking evidence; rejected headwords remain "
            "in rejected-rows.jsonl. License fields are provenance metadata, "
            "not an internal implementation gate."
        ),
        "path": config.file_name,
        "redistribution": config.redistribution,
        "sha256": source_sha256,
        "source_id": config.source_id,
        "title": config.source_title,
    }
    pack = {
        "allowed_format_characters": ["U+200C", "U+200D"],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": config.display_name,
        "language": config.language,
        "max_suggestions": args.max_suggestions,
        "output_script": "Deva",
        "pack_id": config.pack_id,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": config.variety,
    }
    adapter_sha256 = _sha256(adapter_path.resolve(), "language adapter")
    report: dict[str, object] = {
        "adapter": config.adapter_name,
        "adapter_sha256": adapter_sha256,
        "adapter_version": config.adapter_version,
        "aliases": {"rows": 0, "policy": "direct input only"},
        "data_version": args.data_version,
        "helper": {
            "name": HELPER_NAME,
            "path": "tools/sil_apk_jsonl_internal_source.py",
            "sha256": helper_sha256,
            "version": HELPER_VERSION,
        },
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": config.expected_data_rows,
            "path": config.file_name,
            "sha256": source_sha256,
        },
        "joiner_policy": {
            "allow_conjunct_zwnj": True,
            "allow_conjunct_zwj": True,
            "allow_terminal_zwnj": config.allow_terminal_zwnj,
            "allow_terminal_zwj": False,
        },
        "normalization": (
            "NFC; collapse whitespace; trim; preserve only reviewed ZWJ/ZWNJ "
            "contexts; reject controls and symbols; require at least one "
            "Devanagari letter"
        ),
        "pack_id": config.pack_id,
        "ranking": {
            "rank_score": RANK_SCORE,
            "tie_break": "Unicode surface order, then pinned JSONL line ID",
        },
        "source_contract": {
            "fields": list(EXPECTED_FIELDS),
            "lang": config.language,
            "source": config.source_tag,
        },
        "stats": stats,
    }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "pack.json").write_text(
        _canonical_json(pack) + "\n", encoding="utf-8"
    )
    _write_jsonl(args.output / "sources.jsonl", [source])
    _write_jsonl(args.output / "forms.jsonl", forms)
    (args.output / "aliases.jsonl").write_text("", encoding="utf-8")
    _write_jsonl(args.output / "rejected-rows.jsonl", rejected)
    (args.output / "adapter-report.json").write_text(
        _canonical_json(report) + "\n", encoding="utf-8"
    )
    return report
