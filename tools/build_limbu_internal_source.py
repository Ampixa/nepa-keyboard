#!/usr/bin/env python3
"""Build deterministic direct-input source tables from the pinned LimDic TSV.

This adapter is intentionally small. It accepts only native Sirijanga
headwords, preserves stable LimDic IDs, emits no Roman aliases, and records
every rejected row for later review instead of guessing how variants should be
split. The resulting tables are for an ``internal`` NKP build.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable


PACK_ID = "lif-Limb-NP"
SOURCE_ID = "lif-limdic"
LIMDIC_SHA256 = "fb6d4922943f08473784b7d47ced8f427c34df9f936db24adf9d456442cd9a1e"
EXPECTED_DATA_ROWS = 8_797
EXPECTED_HEADER = (
    "id",
    "headword_limbu",
    "desc_devanagari",
    "group",
    "definition",
    "ipa",
)
SAFE_ROW_ID = re.compile(r"^[A-Za-z0-9._-]+$")
LIMBU_START = 0x1900
LIMBU_END = 0x194F
RANK_SCORE = 1_000


class AdapterError(ValueError):
    """Raised when the pinned LimDic table violates the adapter contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_input_snapshot(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read input {path}: {exc}") from exc


def _validate_surface(raw: str) -> tuple[str | None, str | None, bool, bool]:
    stripped = raw.strip()
    normalized = unicodedata.normalize("NFC", stripped)
    trimmed = stripped != raw
    nfc_changed = normalized != stripped
    if not normalized:
        return None, "blank_headword", trimmed, nfc_changed
    has_letter = False
    for character in normalized:
        codepoint = ord(character)
        category = unicodedata.category(character)
        if not LIMBU_START <= codepoint <= LIMBU_END:
            return None, "outside_limbu_block", trimmed, nfc_changed
        if category[0] not in {"L", "M"}:
            return None, "unsupported_limbu_character", trimmed, nfc_changed
        has_letter = has_letter or category.startswith("L")
    if not has_letter:
        return None, "no_limbu_letter", trimmed, nfc_changed
    return normalized, None, trimmed, nfc_changed


def _read_rows(input_bytes: bytes) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    forms: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    seen_ids: set[str] = set()
    try:
        handle = io.StringIO(input_bytes.decode("utf-8-sig"), newline="")
    except UnicodeError as exc:
        raise AdapterError(f"cannot decode LimDic TSV as UTF-8: {exc}") from exc

    with handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADER:
            raise AdapterError("LimDic TSV header does not match the pinned six-column contract")
        for line_number, row in enumerate(reader, 2):
            stats["rows"] += 1
            if None in row or any(value is None for value in row.values()):
                raise AdapterError(f"LimDic row {line_number} has the wrong number of columns")
            row_id = row["id"]
            if not SAFE_ROW_ID.fullmatch(row_id):
                raise AdapterError(f"LimDic row {line_number} has an invalid stable id")
            if row_id in seen_ids:
                raise AdapterError(f"LimDic row {line_number} repeats stable id {row_id!r}")
            seen_ids.add(row_id)

            raw_surface = row["headword_limbu"]
            surface, reason, trimmed, nfc_changed = _validate_surface(raw_surface)
            if reason is not None:
                stats["rejected_rows"] += 1
                stats[f"rejected_{reason}"] += 1
                rejected.append({
                    "id": row_id,
                    "line": line_number,
                    "raw_headword": raw_surface,
                    "reason": reason,
                })
                continue
            if trimmed:
                stats["trimmed_rows"] += 1
            if nfc_changed:
                stats["nfc_normalized_rows"] += 1
            forms.append({
                "evidence": "attested",
                "form_id": f"lif:limdic:{row_id}",
                "rank_score": RANK_SCORE,
                "source_ids": [SOURCE_ID],
                "surface": surface,
            })
            stats["accepted_rows"] += 1

    if stats["rows"] != EXPECTED_DATA_ROWS:
        raise AdapterError(
            f"LimDic row count mismatch: expected {EXPECTED_DATA_ROWS}, got {stats['rows']}"
        )
    if not forms:
        raise AdapterError("LimDic contains no accepted native-script headwords")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: (int(row["line"]), str(row["id"])))
    for key in (
        "accepted_rows",
        "rejected_rows",
        "trimmed_rows",
        "nfc_normalized_rows",
    ):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len({str(row["surface"]) for row in forms})
    return forms, rejected, dict(sorted(stats.items()))


def build_internal_source(args: argparse.Namespace) -> dict[str, object]:
    input_bytes = _read_input_snapshot(args.limdic_tsv)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != LIMDIC_SHA256:
        raise AdapterError(
            "LimDic SHA-256 mismatch: "
            f"expected {LIMDIC_SHA256}, got {source_sha256}"
        )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")

    forms, rejected, stats = _read_rows(input_bytes)
    source = {
        "license": "unknown",
        "method": "Pinned LimDic TSV headword_limbu rows; NFC and surrounding-whitespace normalization only",
        "notes": "Internal product source. Variant spellings containing punctuation remain in rejected-rows.jsonl for explicit review.",
        "path": "limdic_dictionary.tsv",
        "redistribution": "unknown",
        "sha256": source_sha256,
        "source_id": SOURCE_ID,
        "title": "LimDic Limbu dictionary",
    }
    pack = {
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Limbu",
        "language": "lif",
        "max_suggestions": args.max_suggestions,
        "output_script": "Limb",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": None,
    }
    adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report: dict[str, object] = {
        "adapter": "build_limbu_internal_source",
        "adapter_sha256": adapter_sha256,
        "adapter_version": 2,
        "aliases": {"rows": 0, "policy": "direct input only"},
        "data_version": args.data_version,
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": EXPECTED_DATA_ROWS,
            "path": "limdic_dictionary.tsv",
            "sha256": source_sha256,
        },
        "normalization": "trim surrounding whitespace; NFC; require Limbu block letter/mark scalars and at least one letter",
        "pack_id": PACK_ID,
        "ranking": {
            "rank_score": RANK_SCORE,
            "tie_break": "Unicode surface order, then stable form ID",
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limdic-tsv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-version", default="1.0.0")
    parser.add_argument("--max-suggestions", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_internal_source(args)
    except AdapterError as exc:
        parser.error(str(exc))
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
