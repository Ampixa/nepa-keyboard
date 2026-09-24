#!/usr/bin/env python3
"""Build isolated Athpahariya, Kulung, or Sampang induced candidate tables.

The Rai headword alone supplies a direct-input candidate. Valid Devanagari
conjunct joiners remain literal; smart quotes and invalid joiners are rejected
with line evidence. Alignment scores are not keyboard usage frequency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class RaiSpec:
    language: str
    display_name: str
    source_file: str
    source_sha256: str
    data_rows: int


SPECS = {
    "aph": RaiSpec(
        "aph", "Athpahariya", "nepali-athpariya.induced-lexicon.jsonl",
        "077f42e4bb6fe1141ad4ee73eb83e715d7df4572ffb2c7d7e47dc4feb40769c4",
        3_009,
    ),
    "kle": RaiSpec(
        "kle", "Kulung", "nepali-kulung.induced-lexicon.jsonl",
        "88ecad091dd207a48ae8c058d82471c08c942d06f7284c5e6345e26b2b1bb8ae",
        3_123,
    ),
    "rav": RaiSpec(
        "rav", "Sampang", "nepali-sampang.induced-lexicon.jsonl",
        "ec65236b227bb5f8396f7ba7a8adc31b8b053bee91d9b0a1e0dd5da8b3b3fbd7",
        3_151,
    ),
}
EXPECTED_FIELDS = {
    "rai", "nepali", "score", "cooc", "p_rai_given_nep",
    "p_nep_given_rai", "lang", "method", "source",
}
RANK_SCORE = 1_000
JOINERS = frozenset({"\u200c", "\u200d"})
EDITORIAL_QUOTES = frozenset({"\u2018", "\u2019", "\u201c", "\u201d"})
DEVANAGARI_VIRAMA = "\u094d"


class AdapterError(ValueError):
    """Raised when a pinned Rai induced JSONL source violates its contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows), encoding="utf-8"
    )


def _read_input_snapshot(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AdapterError(f"input is not a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read input {path}: {exc}") from exc


def _is_devanagari(character: str) -> bool:
    return 0x0900 <= ord(character) <= 0x097F


def _is_devanagari_letter(character: str) -> bool:
    return _is_devanagari(character) and unicodedata.category(character).startswith("L")


def _base_before_virama(surface: str, joiner_index: int) -> bool:
    index = joiner_index - 2
    while (
        index >= 0
        and _is_devanagari(surface[index])
        and unicodedata.category(surface[index]).startswith("M")
    ):
        index -= 1
    return index >= 0 and _is_devanagari_letter(surface[index])


def _valid_joiner_context(surface: str, index: int) -> bool:
    if index < 2 or surface[index - 1] != DEVANAGARI_VIRAMA:
        return False
    if not _base_before_virama(surface, index):
        return False
    if surface[index] == "\u200c" and index == len(surface) - 1:
        return True
    return index < len(surface) - 1 and _is_devanagari_letter(surface[index + 1])


def _validate_surface(surface: str) -> str | None:
    if not surface:
        return "blank_headword"
    if any(character.isspace() for character in surface):
        return "contains_whitespace"
    if any(character in EDITORIAL_QUOTES for character in surface):
        return "editorial_quote"
    has_letter = False
    for index, character in enumerate(surface):
        if character in JOINERS:
            if not _valid_joiner_context(surface, index):
                return "invalid_joiner_context"
            continue
        if not _is_devanagari(character):
            return "outside_devanagari"
        category = unicodedata.category(character)
        if category[0] not in {"L", "M"}:
            return "non_letter_mark"
        has_letter |= category.startswith("L")
    return None if has_letter else "no_devanagari_letter"


def _probability(value: object, line: int, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise AdapterError(f"line {line} has invalid {field}")
    number = Decimal(value)
    if not number.is_finite() or not 0 <= number <= 1:
        raise AdapterError(f"line {line} has out-of-range {field}")
    return number


def _read_rows(
    input_bytes: bytes, spec: RaiSpec
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    try:
        lines = input_bytes.decode("utf-8-sig").splitlines()
    except UnicodeError as exc:
        raise AdapterError(f"cannot decode {spec.language} JSONL as UTF-8: {exc}") from exc
    forms: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    for line_number, line in enumerate(lines, 1):
        stats["rows"] += 1
        try:
            row = json.loads(line, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"line {line_number} is not valid JSON") from exc
        if not isinstance(row, dict) or set(row) != EXPECTED_FIELDS:
            raise AdapterError(f"line {line_number} has the wrong JSONL fields")
        if (
            not isinstance(row["rai"], str)
            or not isinstance(row["nepali"], str)
            or row["lang"] != spec.language
            or row["method"] != "ibm1-symmetrized"
            or row["source"] != "induced/bible"
        ):
            raise AdapterError(f"line {line_number} violates the Rai source contract")
        for field in ("score", "p_rai_given_nep", "p_nep_given_rai"):
            _probability(row[field], line_number, field)
        if isinstance(row["cooc"], bool) or not isinstance(row["cooc"], int) or row["cooc"] < 1:
            raise AdapterError(f"line {line_number} has invalid cooc")
        if row["rai"] == row["nepali"]:
            stats["same_as_nepali_rows"] += 1
        if row["score"] < Decimal("0.4"):
            stats["score_lt_0_4_rows"] += 1
        if row["score"] >= Decimal("0.5"):
            stats["score_gte_0_5_rows"] += 1
        raw_surface = row["rai"]
        surface = unicodedata.normalize("NFC", raw_surface).strip()
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
        if surface != raw_surface:
            stats["normalized_rows"] += 1
        if any(character in JOINERS for character in surface):
            stats["accepted_joiner_rows"] += 1
        forms.append({
            "evidence": "induced",
            "form_id": f"{spec.language}:induced:line-{line_number:06d}",
            "rank_score": RANK_SCORE,
            "source_ids": [f"{spec.language}-induced"],
            "surface": surface,
        })
        stats["accepted_rows"] += 1
    if stats["rows"] != spec.data_rows:
        raise AdapterError(
            f"{spec.language} row count mismatch: expected {spec.data_rows}, "
            f"got {stats['rows']}"
        )
    if not forms:
        raise AdapterError(f"{spec.language} JSONL contains no accepted headwords")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: int(row["line"]))
    for key in (
        "accepted_rows", "accepted_joiner_rows", "rejected_rows", "normalized_rows",
        "same_as_nepali_rows", "score_lt_0_4_rows", "score_gte_0_5_rows",
    ):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len({str(row["surface"]) for row in forms})
    return forms, rejected, dict(sorted(stats.items()))


def build_candidate_source(args: argparse.Namespace) -> dict[str, object]:
    spec = SPECS[args.language]
    input_bytes = _read_input_snapshot(args.induced_jsonl)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != spec.source_sha256:
        raise AdapterError(
            f"{spec.language} JSONL SHA-256 mismatch: expected "
            f"{spec.source_sha256}, got {source_sha256}"
        )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")
    forms, rejected, stats = _read_rows(input_bytes, spec)
    source_id = f"{spec.language}-induced"
    pack_id = f"{spec.language}-Deva-NP"
    source = {
        "license": "unknown",
        "method": "Pinned Rai induced Bible-alignment JSONL; rai field only",
        "notes": (
            "Valid conjunct joiners are literal. Editorial quotes and invalid "
            "joiners are recorded as rejections. Alignment scores and "
            "cooccurrence do not measure keyboard usage frequency."
        ),
        "path": spec.source_file,
        "redistribution": "unknown",
        "sha256": source_sha256,
        "source_id": source_id,
        "title": f"{spec.display_name} induced Rai–Nepali lexicon",
    }
    pack = {
        "allowed_format_characters": ["U+200C", "U+200D"],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": f"{spec.display_name} Candidate",
        "language": spec.language,
        "max_suggestions": args.max_suggestions,
        "output_script": "Deva",
        "pack_id": pack_id,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": f"{spec.display_name} induced source review pending",
    }
    report: dict[str, object] = {
        "adapter": "build_rai_induced_candidate_source",
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "adapter_version": 1,
        "claim_scope": "candidate_only_induced_lexicon",
        "aliases": {"rows": 0, "policy": "direct input only"},
        "data_version": args.data_version,
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": spec.data_rows,
            "path": spec.source_file,
            "sha256": source_sha256,
        },
        "normalization": (
            "NFC and outer whitespace trimming; accept one Devanagari "
            "letter/mark token with valid conjunct joiners; reject smart "
            "quotes and invalid joiners"
        ),
        "pack_id": pack_id,
        "ranking": {
            "rank_score": RANK_SCORE,
            "source_alignment_score_used": False,
            "tie_break": "Unicode surface order, then pinned JSONL line ID",
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
    parser.add_argument("--language", choices=sorted(SPECS), required=True)
    parser.add_argument("--induced-jsonl", type=Path, required=True)
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
