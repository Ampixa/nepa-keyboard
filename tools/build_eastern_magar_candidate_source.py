#!/usr/bin/env python3
"""Build a direct-input research candidate from the pinned Eastern Magar TSV.

Only the first column supplies candidate surfaces. Alignment scores, cooccurrence
counts, and Nepali forms remain source context; they are not keyboard frequency.
The output retains induced provenance and needs native review before promotion.
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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


PACK_ID = "mgp-Deva-NP"
SOURCE_ID = "mgp-induced"
SOURCE_SHA256 = "3df7a496e56bb7cef17c7f6462224546d4cbe1d0ca4747cff81783da1366a7ae"
EXPECTED_DATA_ROWS = 2_838
EXPECTED_HEADER = ("mgp", "npi", "score", "p_fwd", "p_rev", "cooc")
RANK_SCORE = 1_000


class AdapterError(ValueError):
    """Raised when the pinned induced lexicon violates its input contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_input_snapshot(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AdapterError(f"input is not a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read input {path}: {exc}") from exc


def _normalize_surface(raw: str) -> tuple[str, bool]:
    surface = unicodedata.normalize("NFC", raw).strip()
    return surface, surface != raw


def _validate_surface(surface: str) -> str | None:
    if not surface:
        return "blank_headword"
    if any(character.isspace() for character in surface):
        return "contains_whitespace"
    if any(not 0x0900 <= ord(character) <= 0x097F for character in surface):
        return "outside_devanagari"
    if any(unicodedata.category(character)[0] not in {"L", "M"} for character in surface):
        return "non_letter_mark"
    if not any(unicodedata.category(character).startswith("L") for character in surface):
        return "no_devanagari_letter"
    return None


def _probability(raw: str, line: int, column: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise AdapterError(f"row {line} has invalid {column}") from exc
    if not value.is_finite() or not 0 <= value <= 1:
        raise AdapterError(f"row {line} has out-of-range {column}")
    return value


def _read_rows(
    input_bytes: bytes,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    try:
        handle = io.StringIO(input_bytes.decode("utf-8-sig"), newline="")
    except UnicodeError as exc:
        raise AdapterError(f"cannot decode Eastern Magar TSV as UTF-8: {exc}") from exc

    forms: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    with handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise AdapterError("Eastern Magar TSV is empty") from exc
        if tuple(header) != EXPECTED_HEADER:
            raise AdapterError("Eastern Magar TSV header mismatch")
        for line_number, row in enumerate(reader, 2):
            stats["rows"] += 1
            if len(row) != len(EXPECTED_HEADER):
                raise AdapterError(f"row {line_number} has the wrong number of columns")
            for index, column in enumerate(("score", "p_fwd", "p_rev"), 2):
                _probability(row[index], line_number, column)
            if not re.fullmatch(r"[0-9]+", row[5]) or int(row[5]) < 1:
                raise AdapterError(f"row {line_number} has invalid cooc")
            if row[0] == row[1]:
                stats["same_as_nepali_rows"] += 1
            score = Decimal(row[2])
            if score < Decimal("0.4"):
                stats["score_lt_0_4_rows"] += 1
            if score >= Decimal("0.5"):
                stats["score_gte_0_5_rows"] += 1
            surface, normalized = _normalize_surface(row[0])
            reason = _validate_surface(surface)
            if reason:
                stats["rejected_rows"] += 1
                stats[f"rejected_{reason}"] += 1
                rejected.append({
                    "line": line_number,
                    "raw_headword": row[0],
                    "reason": reason,
                })
                continue
            if normalized:
                stats["normalized_rows"] += 1
            forms.append({
                "evidence": "induced",
                "form_id": f"mgp:induced:line-{line_number:06d}",
                "rank_score": RANK_SCORE,
                "source_ids": [SOURCE_ID],
                "surface": surface,
            })
            stats["accepted_rows"] += 1
    if stats["rows"] != EXPECTED_DATA_ROWS:
        raise AdapterError(
            f"Eastern Magar TSV row count mismatch: expected {EXPECTED_DATA_ROWS}, "
            f"got {stats['rows']}"
        )
    if not forms:
        raise AdapterError("Eastern Magar TSV contains no accepted headwords")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: int(row["line"]))
    for key in (
        "accepted_rows", "rejected_rows", "normalized_rows", "same_as_nepali_rows",
        "score_lt_0_4_rows", "score_gte_0_5_rows",
    ):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len({str(row["surface"]) for row in forms})
    return forms, rejected, dict(sorted(stats.items()))


def build_candidate_source(args: argparse.Namespace) -> dict[str, object]:
    input_bytes = _read_input_snapshot(args.induced_tsv)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != SOURCE_SHA256:
        raise AdapterError(
            f"Eastern Magar TSV SHA-256 mismatch: expected {SOURCE_SHA256}, "
            f"got {source_sha256}"
        )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")

    forms, rejected, stats = _read_rows(input_bytes)
    source = {
        "license": "unknown",
        "method": "Pinned Eastern Magar induced Magar–Nepali TSV; first column only",
        "notes": (
            "Alignment scores and cooccurrence are not keyboard frequency. "
            "Induced spellings and variety fit require speaker review."
        ),
        "path": "mgp-npi.tsv",
        "redistribution": "unknown",
        "sha256": source_sha256,
        "source_id": SOURCE_ID,
        "title": "Eastern Magar induced Magar–Nepali lexicon",
    }
    pack = {
        "allowed_format_characters": [],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Eastern Magar Candidate",
        "language": "mgp",
        "max_suggestions": args.max_suggestions,
        "output_script": "Deva",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": "Eastern Magar induced source review pending",
    }
    report: dict[str, object] = {
        "adapter": "build_eastern_magar_candidate_source",
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "adapter_version": 1,
        "claim_scope": "candidate_only_induced_lexicon",
        "aliases": {"rows": 0, "policy": "direct input only"},
        "data_version": args.data_version,
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": EXPECTED_DATA_ROWS,
            "path": "mgp-npi.tsv",
            "sha256": source_sha256,
        },
        "normalization": (
            "NFC and outer whitespace trimming; accept only one Devanagari "
            "letter/mark token containing a letter"
        ),
        "pack_id": PACK_ID,
        "ranking": {
            "rank_score": RANK_SCORE,
            "tie_break": "Unicode surface order, then pinned TSV line ID",
            "source_alignment_score_used": False,
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
    parser.add_argument("--induced-tsv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-version", default="1.0.0")
    parser.add_argument("--max-suggestions", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_candidate_source(args)
    except AdapterError as exc:
        parser.error(str(exc))
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
