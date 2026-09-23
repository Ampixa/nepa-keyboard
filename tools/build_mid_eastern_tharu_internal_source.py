#!/usr/bin/env python3
"""Build deterministic Mid-Eastern Tharu direct-input tables from the pinned APK TSV.

The source is the pinned Mid-Eastern Tharu Dictionary App Builder TSV. Only the
headword column yields candidates. Leading asterisks are rejected as editorial
markers if present. Valid conjunct joiners remain unchanged, while ambiguous
joiner sequences are rejected rather than silently repaired. Glosses never
become candidates or ranking evidence. The resulting tables are for an
``internal`` NKP build.
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


PACK_ID = "thq-Deva-NP"
SOURCE_ID = "thq-apk"
SOURCE_SHA256 = "575ecfa0b2cbcafe3c4b8783e302f0af5c5a3c7a321b75a61b8bd1fe802d39c5"
EXPECTED_DATA_ROWS = 3_044
EXPECTED_HEADER = ("thq_headword", "nepali_gloss", "english_gloss")
RANK_SCORE = 1_000
ALLOWED_FORMAT_CODEPOINTS = {0x200C, 0x200D}
JOINERS = frozenset(chr(codepoint) for codepoint in ALLOWED_FORMAT_CODEPOINTS)
DEVANAGARI_VIRAMA = "\u094d"
DEVA_RANGES = ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x11B00, 0x11B5F))
WHITESPACE_RE = re.compile(r"\s+")


class AdapterError(ValueError):
    """Raised when the pinned Mid-Eastern Tharu APK table violates its contract."""


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


def _is_valid_joiner_context(value: str, index: int) -> bool:
    return (
        1 < index < len(value) - 1
        and value[index - 1] == DEVANAGARI_VIRAMA
        and _has_devanagari_base_before_virama(value, index)
        and _is_devanagari_letter(value[index + 1])
    )


def _is_valid_terminal_zwnj(value: str, index: int) -> bool:
    return (
        value[index] == "\u200c"
        and index == len(value) - 1
        and index > 1
        and value[index - 1] == DEVANAGARI_VIRAMA
        and _has_devanagari_base_before_virama(value, index)
    )


def _validate_surface(surface: str) -> str | None:
    if not surface:
        return "blank_headword"
    if surface.startswith("*"):
        return "editorial_asterisk"
    has_devanagari_letter = False
    for index, character in enumerate(surface):
        category = unicodedata.category(character)
        if category == "Cf":
            if character not in JOINERS:
                return "unsupported_format_character"
            if not (
                _is_valid_joiner_context(surface, index)
                or _is_valid_terminal_zwnj(surface, index)
            ):
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
            f"cannot decode Mid-Eastern Tharu APK TSV as UTF-8: {exc}"
        ) from exc

    with handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADER:
            raise AdapterError(
                "Mid-Eastern Tharu APK TSV header does not match the pinned "
                "three-column contract"
            )
        for line_number, row in enumerate(reader, 2):
            stats["rows"] += 1
            if None in row or any(value is None for value in row.values()):
                raise AdapterError(
                    f"Mid-Eastern Tharu APK TSV row {line_number} has the wrong "
                    "number of columns"
                )

            raw_surface = row["thq_headword"]
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
                "form_id": f"thq:apk:line-{line_number:06d}",
                "rank_score": RANK_SCORE,
                "source_ids": [SOURCE_ID],
                "surface": surface,
            })
            stats["accepted_rows"] += 1

    if stats["rows"] != EXPECTED_DATA_ROWS:
        raise AdapterError(
            "Mid-Eastern Tharu APK TSV row count mismatch: "
            f"expected {EXPECTED_DATA_ROWS}, got {stats['rows']}"
        )
    if not forms:
        raise AdapterError("Mid-Eastern Tharu APK TSV contains no accepted headwords")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: int(row["line"]))
    for key in ("accepted_rows", "rejected_rows", "normalized_rows"):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len(
        {str(row["surface"]) for row in forms}
    )
    return forms, rejected, dict(sorted(stats.items()))


def build_internal_source(args: argparse.Namespace) -> dict[str, object]:
    input_bytes = _read_input_snapshot(args.apk_tsv)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != SOURCE_SHA256:
        raise AdapterError(
            "Mid-Eastern Tharu APK TSV SHA-256 mismatch: "
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
            "Pinned Dictionary App Builder SQLite-index extraction TSV "
            "thq_headword column; NFC and whitespace normalization only"
        ),
        "notes": (
            "Internal product source. Nepali and English gloss columns are not "
            "candidate surfaces or ranking evidence; rejected headwords remain "
            "in rejected-rows.jsonl."
        ),
        "path": "thq_nep_lexicon.tsv",
        "redistribution": "prohibited",
        "sha256": source_sha256,
        "source_id": SOURCE_ID,
        "title": "Mid-Eastern Tharu Dictionary App Builder lexicon extraction",
    }
    pack = {
        "allowed_format_characters": ["U+200C", "U+200D"],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Mid-Eastern Tharu",
        "language": "thq",
        "max_suggestions": args.max_suggestions,
        "output_script": "Deva",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": "Mid-Eastern Tharu",
    }
    adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report: dict[str, object] = {
        "adapter": "build_mid_eastern_tharu_internal_source",
        "adapter_sha256": adapter_sha256,
        "adapter_version": 1,
        "aliases": {"rows": 0, "policy": "direct input only"},
        "data_version": args.data_version,
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": EXPECTED_DATA_ROWS,
            "path": "thq_nep_lexicon.tsv",
            "sha256": source_sha256,
        },
        "normalization": (
            "NFC; collapse whitespace; trim; preserve conjunct ZWJ/ZWNJ, "
            "virama-final ZWNJ, and punctuation; reject editorial asterisk, "
            "ambiguous joiners, and symbols; require a Devanagari letter"
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
    parser.add_argument("--apk-tsv", type=Path, required=True)
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
