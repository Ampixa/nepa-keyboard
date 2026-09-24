#!/usr/bin/env python3
"""Build a conservative Central Gurung candidate from a pinned toolkit TSV.

The headerless first column supplies candidate headwords. Dash placeholders,
phrases, and punctuation-bearing rows are recorded as rejections. Nepali and
English columns provide context only. The small source still needs variety,
spelling, and ranking review before any profile decision.
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


PACK_ID = "gvr-Deva-NP"
SOURCE_ID = "gvr-nepali-lexicon"
SOURCE_SHA256 = "7f2040eaa40eb0e012938261659f3c9f3f96bb568faf2b5ef261580f10352a7a"
EXPECTED_DATA_ROWS = 328
RANK_SCORE = 1_000


class AdapterError(ValueError):
    """Raised when the pinned Central Gurung TSV violates its contract."""


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
    normalized = unicodedata.normalize("NFC", raw).strip()
    return normalized, normalized != raw


def _validate_surface(surface: str) -> str | None:
    if not surface:
        return "blank_headword"
    if surface == "-":
        return "dash_placeholder"
    if any(character.isspace() for character in surface):
        return "contains_whitespace"
    if any(not 0x0900 <= ord(character) <= 0x097F for character in surface):
        return "outside_devanagari"
    if any(unicodedata.category(character)[0] not in {"L", "M"} for character in surface):
        return "non_letter_mark"
    if not any(unicodedata.category(character).startswith("L") for character in surface):
        return "no_devanagari_letter"
    return None


def _read_rows(
    input_bytes: bytes,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    forms: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    try:
        handle = io.StringIO(input_bytes.decode("utf-8-sig"), newline="")
    except UnicodeError as exc:
        raise AdapterError(
            f"cannot decode Central Gurung toolkit TSV as UTF-8: {exc}"
        ) from exc

    with handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        for line_number, row in enumerate(reader, 1):
            stats["rows"] += 1
            if len(row) != 3:
                raise AdapterError(
                    f"Central Gurung toolkit TSV row {line_number} has the wrong "
                    "number of columns"
                )

            raw_surface = row[0]
            surface, normalized = _normalize_surface(raw_surface)
            reason = _validate_surface(surface)
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
                "form_id": f"gvr:toolkit:line-{line_number:06d}",
                "rank_score": RANK_SCORE,
                "source_ids": [SOURCE_ID],
                "surface": surface,
            })
            stats["accepted_rows"] += 1

    if stats["rows"] != EXPECTED_DATA_ROWS:
        raise AdapterError(
            "Central Gurung toolkit TSV row count mismatch: "
            f"expected {EXPECTED_DATA_ROWS}, got {stats['rows']}"
        )
    if not forms:
        raise AdapterError("Central Gurung toolkit TSV contains no accepted headwords")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: int(row["line"]))
    for key in ("accepted_rows", "rejected_rows", "normalized_rows"):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len(
        {str(row["surface"]) for row in forms}
    )
    return forms, rejected, dict(sorted(stats.items()))


def build_candidate_source(args: argparse.Namespace) -> dict[str, object]:
    input_bytes = _read_input_snapshot(args.toolkit_tsv)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != SOURCE_SHA256:
        raise AdapterError(
            "Central Gurung toolkit TSV SHA-256 mismatch: "
            f"expected {SOURCE_SHA256}, got {source_sha256}"
        )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")

    forms, rejected, stats = _read_rows(input_bytes)
    source = {
        "license": "restricted",
        "method": (
            "Pinned headerless Gurung Central toolkit TSV; first column only; "
            "NFC and outer whitespace trimming"
        ),
        "notes": (
            "The catalog count was corrected from 327 to 328 physical data "
            "rows. Nepali and English columns are never "
            "candidates or ranking evidence; rejected headwords remain in "
            "rejected-rows.jsonl."
        ),
        "path": "gvr_nep_lexicon.tsv",
        "redistribution": "prohibited",
        "sha256": source_sha256,
        "source_id": SOURCE_ID,
        "title": "Gurung Central toolkit trilingual lexicon",
    }
    pack = {
        "allowed_format_characters": [],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Central Gurung Candidate",
        "language": "gvr",
        "max_suggestions": args.max_suggestions,
        "output_script": "Deva",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": "Central Gurung source review pending",
    }
    adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report: dict[str, object] = {
        "adapter": "build_central_gurung_candidate_source",
        "adapter_sha256": adapter_sha256,
        "adapter_version": 1,
        "claim_scope": "candidate_only_small_lexicon",
        "aliases": {"rows": 0, "policy": "direct input only"},
        "data_version": args.data_version,
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": EXPECTED_DATA_ROWS,
            "path": "gvr_nep_lexicon.tsv",
            "sha256": source_sha256,
        },
        "normalization": (
            "NFC and outer whitespace trimming; accept only a single "
            "Devanagari letter/mark token containing a letter; reject dash "
            "placeholders, phrases, punctuation, numbers, and other scripts"
        ),
        "pack_id": PACK_ID,
        "ranking": {
            "rank_score": RANK_SCORE,
            "tie_break": "Unicode surface order, then pinned TSV line ID",
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
    parser.add_argument("--toolkit-tsv", type=Path, required=True)
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
