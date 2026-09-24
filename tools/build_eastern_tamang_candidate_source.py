#!/usr/bin/env python3
"""Build a conservative Tamang candidate from a pinned app translation TSV.

The source's ``tamang`` column contains semicolon, comma, and danda separated
translations. Only single Devanagari letter/mark tokens become candidates.
Phrases, annotations, numerals, and mixed-script fragments remain as
rejections; separator-created empty fragments are counted. The source's
variety assignment still needs human confirmation, so this is an exploratory
internal pack and never a profile-promotion decision.
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


PACK_ID = "taj-Deva-NP"
SOURCE_ID = "taj-app"
SOURCE_SHA256 = "47d5c62b43b627d4ca29dc303907412dc2868623e3a3a258c13415c0456b96dd"
EXPECTED_DATA_ROWS = 4_482
EXPECTED_HEADER = ("nepali", "tamang", "english")
RANK_SCORE = 1_000
SEGMENT_RE = re.compile(r"[;,।]")


class AdapterError(ValueError):
    """Raised when the pinned Eastern Tamang APK table violates its contract."""


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
        return "empty_fragment"
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
            f"cannot decode Eastern Tamang APK TSV as UTF-8: {exc}"
        ) from exc

    with handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADER:
            raise AdapterError(
                "Eastern Tamang APK TSV header does not match the pinned "
                "three-column contract"
            )
        for line_number, row in enumerate(reader, 2):
            stats["rows"] += 1
            if None in row or any(value is None for value in row.values()):
                raise AdapterError(
                    f"Eastern Tamang APK TSV row {line_number} has the wrong "
                    "number of columns"
                )

            for segment_number, raw_segment in enumerate(
                SEGMENT_RE.split(row["tamang"]), 1
            ):
                stats["segments"] += 1
                surface, normalized = _normalize_surface(raw_segment)
                reason = _validate_surface(surface)
                if reason == "empty_fragment":
                    stats["separator_empty_segments"] += 1
                    continue
                if reason is not None:
                    stats["rejected_segments"] += 1
                    stats[f"rejected_{reason}"] += 1
                    rejected.append({
                        "line": line_number,
                        "segment": segment_number,
                        "raw_segment": raw_segment,
                        "reason": reason,
                    })
                    continue
                if normalized:
                    stats["normalized_segments"] += 1
                forms.append({
                    "evidence": "attested",
                    "form_id": (
                        f"taj:app:line-{line_number:06d}:"
                        f"segment-{segment_number:04d}"
                    ),
                    "rank_score": RANK_SCORE,
                    "source_ids": [SOURCE_ID],
                    "surface": surface,
                })
                stats["accepted_segments"] += 1

    if stats["rows"] != EXPECTED_DATA_ROWS:
        raise AdapterError(
            "Eastern Tamang APK TSV row count mismatch: "
            f"expected {EXPECTED_DATA_ROWS}, got {stats['rows']}"
        )
    if not forms:
        raise AdapterError("Eastern Tamang APK TSV contains no accepted segments")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: (int(row["line"]), int(row["segment"])))
    for key in (
        "accepted_segments",
        "rejected_segments",
        "separator_empty_segments",
        "normalized_segments",
    ):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len(
        {str(row["surface"]) for row in forms}
    )
    return forms, rejected, dict(sorted(stats.items()))


def build_candidate_source(args: argparse.Namespace) -> dict[str, object]:
    input_bytes = _read_input_snapshot(args.apk_tsv)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != SOURCE_SHA256:
        raise AdapterError(
            "Eastern Tamang APK TSV SHA-256 mismatch: "
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
            "Pinned app translation TSV tamang column; split semicolon, comma, "
            "and danda; retain only single Devanagari letter/mark tokens"
        ),
        "notes": (
            "The app's variety assignment remains unconfirmed. Nepali and "
            "English columns are never candidates or ranking evidence. "
            "Rejected nonempty segments remain in rejected-rows.jsonl."
        ),
        "path": "taj_amrityonjan_lexicon.tsv",
        "redistribution": "prohibited",
        "sha256": source_sha256,
        "source_id": SOURCE_ID,
        "title": "Tamang Amrityonjan app translation table",
    }
    pack = {
        "allowed_format_characters": [],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Tamang App Candidate",
        "language": "taj",
        "max_suggestions": args.max_suggestions,
        "output_script": "Deva",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": "Unconfirmed Tamang app variety",
    }
    adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report: dict[str, object] = {
        "adapter": "build_eastern_tamang_candidate_source",
        "adapter_sha256": adapter_sha256,
        "adapter_version": 1,
        "claim_scope": "candidate_only_variety_unconfirmed",
        "aliases": {"rows": 0, "policy": "direct input only"},
        "data_version": args.data_version,
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": EXPECTED_DATA_ROWS,
            "path": "taj_amrityonjan_lexicon.tsv",
            "sha256": source_sha256,
        },
        "normalization": (
            "Split Tamang translation cells on semicolon, comma, and danda; "
            "NFC and trim; accept only single Devanagari letter/mark tokens "
            "containing a letter; reject phrases, annotations, numbers, "
            "punctuation, and other scripts"
        ),
        "pack_id": PACK_ID,
        "ranking": {
            "rank_score": RANK_SCORE,
            "tie_break": "Unicode surface order, then pinned TSV line and segment ID",
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
    parser.add_argument("--apk-tsv", type=Path, required=True)
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
