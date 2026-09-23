#!/usr/bin/env python3
"""Freeze the pinned Devanagari-to-Newa table as conversion-map source v1.

This adapter reads only literal character tables from a pinned Aksharamukha
checkout.  Android never executes that package: the canonical JSON source and
the compiled ``.ncm`` artifact are the complete runtime authority.

The base mapping is mechanical script conversion, not attested Newa text.  It
preserves ZWJ and ZWNJ only in a virama-plus-joiner-plus-consonant sequence and
deliberately excludes Aksharamukha's lossy modern-vowel and Vedic fallbacks.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from tools.build_conversion_map import (
    ALGORITHM,
    JOINER_POLICY,
    NORMALIZATION,
    SOURCE_FORMAT,
    SOURCE_FORMAT_VERSION,
    UNMAPPED_POLICY,
    compile_source,
    convert_text,
)


UPSTREAM_COMMIT = "9ad8cce3cac4900dea63b149ca077e691a8916a9"
DEVANAGARI_TABLE_SHA256 = (
    "f453abe3dc86605a68eddbcb1440e56809597565c7fd3c93c4779bf2ea222916"
)
NEWA_TABLE_SHA256 = (
    "5845afdd9618afeddd09cf9b40675a28ba2bdf01bbcccb23be30e5d68d7fe09f"
)

TABLE_COUNTS = {
    "VowelMap": 14,
    "VowelSignMap": 13,
    "AyogavahaMap": 3,
    "ViramaMap": 1,
    "ConsonantMap": 33,
    "SouthConsonantMap": 4,
    "NuktaConsonantMap": 8,
    "NuktaMap": 1,
    "OmMap": 1,
    "SignMap": 3,
    "NumeralMap": 10,
}
EXPECTED_DIRECT_RULES = sum(TABLE_COUNTS.values())
JOINERS = ("\u200c", "\u200d")
DEVA_VIRAMA = "\u094d"
NEWA_VIRAMA = "\U00011442"

# Aksharamukha 2.3 maps the two candra vowel signs through lossy modifier
# fallbacks, and its Vedic fallbacks use arrows outside the Newa block.  These
# scalars must remain NO_MATCH in the frozen v1 profile.
EXCLUDED_SCALARS = {
    "\u0945": "DEVANAGARI VOWEL SIGN CANDRA E",
    "\u0949": "DEVANAGARI VOWEL SIGN CANDRA O",
    "\u0951": "DEVANAGARI STRESS SIGN UDATTA",
    "\u0952": "DEVANAGARI STRESS SIGN ANUDATTA",
}


class AdapterError(ValueError):
    """Raised when a pinned table or candidate input violates the adapter."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _read_pinned(path: Path, expected_sha256: str, label: str) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read {label}: {path}") from exc
    actual = _sha256(data)
    if actual != expected_sha256:
        raise AdapterError(
            f"{label} SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return data


def _literal_tables(encoded: bytes, label: str) -> dict[str, list[str]]:
    try:
        module = ast.parse(encoded.decode("utf-8"), filename=label)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise AdapterError(f"cannot parse pinned {label}") from exc

    tables: dict[str, list[str]] = {}
    for statement in module.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name) or target.id not in TABLE_COUNTS:
            continue
        try:
            value = ast.literal_eval(statement.value)
        except (ValueError, TypeError) as exc:
            raise AdapterError(f"{label}.{target.id} is not a literal list") from exc
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            raise AdapterError(f"{label}.{target.id} must be nonempty strings")
        expected = TABLE_COUNTS[target.id]
        if len(value) != expected:
            raise AdapterError(
                f"{label}.{target.id} count mismatch: expected {expected}, got {len(value)}"
            )
        tables[target.id] = value

    missing = sorted(set(TABLE_COUNTS) - set(tables))
    if missing:
        raise AdapterError(f"{label} is missing tables: {missing}")
    return tables


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_source(
    devanagari_tables: dict[str, list[str]],
    newa_tables: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Build the canonical source object and per-table direct-rule counts."""

    rules: list[dict[str, str]] = []
    table_rule_counts: dict[str, int] = {}
    for table, expected_count in TABLE_COUNTS.items():
        sources = devanagari_tables[table]
        targets = newa_tables[table]
        if len(sources) != len(targets) or len(sources) != expected_count:
            raise AdapterError(f"unaligned {table} tables")
        before = len(rules)
        for source_text, target_text in zip(sources, targets, strict=True):
            source_nfc = unicodedata.normalize(NORMALIZATION, source_text)
            target_nfc = unicodedata.normalize(NORMALIZATION, target_text)
            excluded = set(source_nfc) & set(EXCLUDED_SCALARS)
            if excluded:
                names = [EXCLUDED_SCALARS[item] for item in sorted(excluded)]
                raise AdapterError(f"{table} unexpectedly includes excluded scalars: {names}")
            rules.append({"from": source_nfc, "to": target_nfc})
        table_rule_counts[table] = len(rules) - before

    if len(rules) != EXPECTED_DIRECT_RULES:
        raise AdapterError(
            f"direct-rule count mismatch: expected {EXPECTED_DIRECT_RULES}, got {len(rules)}"
        )

    # Preserve only keyboard-valid joiners.  A standalone joiner remains
    # unmapped, while VIRAMA + joiner + consonant is converted atomically.
    joiner_consonants = list(
        zip(
            devanagari_tables["ConsonantMap"]
            + devanagari_tables["SouthConsonantMap"],
            newa_tables["ConsonantMap"] + newa_tables["SouthConsonantMap"],
            strict=True,
        )
    )
    for joiner in JOINERS:
        for source_consonant, target_consonant in joiner_consonants:
            rules.append(
                {
                    "from": DEVA_VIRAMA
                    + joiner
                    + unicodedata.normalize(NORMALIZATION, source_consonant),
                    "to": NEWA_VIRAMA
                    + joiner
                    + unicodedata.normalize(NORMALIZATION, target_consonant),
                }
            )

    source: dict[str, Any] = {
        "source_format": SOURCE_FORMAT,
        "source_format_version": SOURCE_FORMAT_VERSION,
        "converter_id": "new-Deva-Newa-NP",
        "mapping_version": "1.0.0",
        "language": "new",
        "source_script": "Deva",
        "output_script": "Newa",
        "normalization": NORMALIZATION,
        "algorithm": ALGORITHM,
        "unmapped_policy": UNMAPPED_POLICY,
        "joiner_policy": JOINER_POLICY,
        "rules": rules,
    }
    # Reuse the runtime compiler as the final semantic validator.  The source
    # intentionally retains authored table order; compilation canonicalizes it.
    compile_source(source)
    return source, table_rule_counts


def _candidate_coverage(
    artifact: dict[str, Any], forms_path: Path | None
) -> dict[str, Any] | None:
    if forms_path is None:
        return None
    try:
        encoded_lines = forms_path.read_bytes().splitlines()
    except OSError as exc:
        raise AdapterError(f"cannot read forms JSONL: {forms_path}") from exc

    surfaces: set[str] = set()
    forms: list[str] = []
    for line_number, encoded in enumerate(encoded_lines, 1):
        try:
            row = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterError(f"forms JSONL line {line_number} is invalid") from exc
        if not isinstance(row, dict) or not isinstance(row.get("surface"), str):
            raise AdapterError(f"forms JSONL line {line_number} lacks surface")
        surface = unicodedata.normalize(NORMALIZATION, row["surface"])
        if surface:
            forms.append(surface)
            surfaces.add(surface)

    converted: list[str] = []
    rejected: list[str] = []
    excluded_counts = {name: 0 for name in EXCLUDED_SCALARS.values()}
    for surface in sorted(surfaces):
        result = convert_text(artifact, surface)
        if result is not None:
            converted.append(surface)
            continue
        rejected.append(surface)
        for scalar, name in EXCLUDED_SCALARS.items():
            if scalar in surface:
                excluded_counts[name] += 1

    total = len(surfaces)
    converted_set = set(converted)
    converted_forms = sum(surface in converted_set for surface in forms)
    return {
        "forms_jsonl_sha256": _sha256(forms_path.read_bytes()),
        "forms": len(forms),
        "converted_forms": converted_forms,
        "no_match_forms": len(forms) - converted_forms,
        "distinct_surfaces": total,
        "converted_surfaces": len(converted),
        "no_match_surfaces": len(rejected),
        "coverage_fraction": len(converted) / total if total else 0.0,
        "no_match_examples": rejected[:32],
        "excluded_scalar_surface_counts": excluded_counts,
        "surface_set_sha256": _sha256(
            ("\n".join(sorted(surfaces)) + "\n").encode("utf-8")
        ),
    }


def generate(
    devanagari_path: Path,
    newa_path: Path,
    source_path: Path,
    report_path: Path,
    forms_path: Path | None,
) -> dict[str, Any]:
    devanagari_bytes = _read_pinned(
        devanagari_path, DEVANAGARI_TABLE_SHA256, "Devanagari table"
    )
    newa_bytes = _read_pinned(newa_path, NEWA_TABLE_SHA256, "Newa table")
    source, table_rule_counts = build_source(
        _literal_tables(devanagari_bytes, "Devanagari.py"),
        _literal_tables(newa_bytes, "Newa.py"),
    )
    source_bytes = _canonical_bytes(source)
    artifact = compile_source(source)
    report = {
        "report_format": "nepa-newa-conversion-source-report",
        "report_format_version": 1,
        "converter_id": source["converter_id"],
        "mapping_version": source["mapping_version"],
        "claim_scope": "internal mechanical Devanagari-to-Newa script conversion beta; generated output is not attested Newa text",
        "upstream": {
            "project": "virtualvinodh/aksharamukha-python",
            "commit": UPSTREAM_COMMIT,
            "devanagari_table_sha256": DEVANAGARI_TABLE_SHA256,
            "newa_table_sha256": NEWA_TABLE_SHA256,
        },
        "policy": {
            "normalization": NORMALIZATION,
            "algorithm": ALGORITHM,
            "unmapped": UNMAPPED_POLICY,
            "joiners": JOINER_POLICY,
            "ascii_whitespace_and_punctuation": "no-match",
            "murmured_resonant_contraction": "disabled_pending_native_review",
            "excluded_scalars": [
                {"scalar": scalar, "code_point": f"U+{ord(scalar):04X}", "name": name}
                for scalar, name in EXCLUDED_SCALARS.items()
            ],
        },
        "counts": {
            "direct_rules": EXPECTED_DIRECT_RULES,
            "joiner_rules": len(source["rules"]) - EXPECTED_DIRECT_RULES,
            "total_rules": len(source["rules"]),
            "per_table": table_rule_counts,
        },
        "source_sha256": _sha256(source_bytes),
        "candidate_coverage": _candidate_coverage(artifact, forms_path),
    }
    _atomic_write(source_path, source_bytes)
    _atomic_write(report_path, _canonical_bytes(report))
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devanagari-table", required=True, type=Path)
    parser.add_argument("--newa-table", required=True, type=Path)
    parser.add_argument("--output-source", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    parser.add_argument("--forms-jsonl", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = generate(
            args.devanagari_table,
            args.newa_table,
            args.output_source,
            args.output_report,
            args.forms_jsonl,
        )
    except AdapterError as exc:
        raise SystemExit(f"build_nepal_bhasa_conversion_source: error: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
