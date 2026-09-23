#!/usr/bin/env python3
"""Build deterministic Nepal Bhasa Devanagari tables from the pinned TSV.

Only the ``newar`` column of the reviewed Nepal Bhasa/Nepali trilingual table
becomes candidate vocabulary. Nepali glosses never become candidates or
ranking evidence, and cells are never split into guessed alternatives. The
adapter requires raw NFC identity and no whitespace, preserves only
context-valid conjunct ZWJ/ZWNJ, and records rejected rows instead of repairing
them. The resulting source tables are for an internal ``new-Deva-NP`` build.
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


PACK_ID = "new-Deva-NP"
SOURCE_ID = "new-nepali-trilingual"
SOURCE_SHA256 = "4167c21626674fd1e71bd814c6b2bbb33d2d35ab0f5d5bb071b7b43e071d7929"
EXPECTED_DATA_ROWS = 9_708
EXPECTED_HEADER = ("newar", "nepali")
RANK_SCORE = 1_000
ALLOWED_FORMAT_CODEPOINTS = {0x200C, 0x200D}
JOINERS = frozenset(chr(codepoint) for codepoint in ALLOWED_FORMAT_CODEPOINTS)
DEVANAGARI_VIRAMA = "\u094d"
DEVA_RANGES = ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x11B00, 0x11B5F))
WHITESPACE_RE = re.compile(r"\s+")
ALIASES_POLICY = "none"
FILTER_POLICY = (
    "require a Devanagari letter; allow Devanagari L/M/N/P; reject controls, "
    "symbols, and other scripts"
)
JOINER_POLICY = (
    "allow only ZWJ/ZWNJ between owned Devanagari virama and following "
    "Devanagari letter"
)
NORMALIZATION_POLICY = "raw NFC identity required; reject whitespace"
RANKING_POLICY = "constant 1000; Unicode surface then pinned line ID tie-break"
SPLITTING_POLICY = "none; reject semicolon-bearing cells"


class AdapterError(ValueError):
    """Raised when the pinned Nepal Bhasa table violates its contract."""


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


def _normalize_surface(raw: str) -> tuple[str, bool]:
    normalized = unicodedata.normalize("NFC", raw)
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


def _validate_surface(surface: str) -> str | None:
    if not surface:
        return "blank_headword"
    has_devanagari_letter = False
    for index, character in enumerate(surface):
        category = unicodedata.category(character)
        if category == "Cf":
            if character not in JOINERS:
                return "unsupported_format_character"
            if not _is_valid_joiner_context(surface, index):
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
            f"cannot decode Nepal Bhasa trilingual TSV as UTF-8: {exc}"
        ) from exc

    with handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADER:
            raise AdapterError(
                "Nepal Bhasa trilingual TSV header does not match the pinned "
                "two-column contract"
            )
        for line_number, row in enumerate(reader, 2):
            stats["rows"] += 1
            if None in row or any(value is None for value in row.values()):
                raise AdapterError(
                    f"Nepal Bhasa trilingual TSV row {line_number} has the wrong "
                    "number of columns"
                )

            raw_surface = row["newar"]
            surface, normalized = _normalize_surface(raw_surface)
            if normalized:
                reason = "non_nfc_headword"
            elif ";" in surface:
                reason = "alternative_delimiter"
            elif WHITESPACE_RE.search(surface):
                reason = "whitespace_headword"
            else:
                reason = _validate_surface(surface)
            if reason is not None:
                stats["rejected_rows"] += 1
                stats[f"rejected_{reason}"] += 1
                rejected.append(
                    {
                        "line": line_number,
                        "raw_headword": raw_surface,
                        "reason": reason,
                    }
                )
                continue
            forms.append(
                {
                    "evidence": "attested",
                    "form_id": f"new:trilingual:line-{line_number:06d}",
                    "rank_score": RANK_SCORE,
                    "source_ids": [SOURCE_ID],
                    "surface": surface,
                }
            )
            stats["accepted_rows"] += 1

    if stats["rows"] != EXPECTED_DATA_ROWS:
        raise AdapterError(
            "Nepal Bhasa trilingual TSV row count mismatch: "
            f"expected {EXPECTED_DATA_ROWS}, got {stats['rows']}"
        )
    if not forms:
        raise AdapterError("Nepal Bhasa trilingual TSV has no accepted headwords")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: int(row["line"]))
    for key in ("accepted_rows", "rejected_rows", "normalized_rows"):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len(
        {str(row["surface"]) for row in forms}
    )
    return forms, rejected, dict(sorted(stats.items()))


def _accepted_scalar_inventory(
    forms: list[dict[str, object]],
) -> dict[str, object]:
    counts: Counter[str] = Counter()
    for row in forms:
        counts.update(str(row["surface"]))
    frequencies = [
        {
            "category": unicodedata.category(character),
            "character": character,
            "count": counts[character],
            "name": unicodedata.name(character, "UNNAMED"),
            "scalar": f"U+{ord(character):04X}",
        }
        for character in sorted(counts, key=ord)
        if not character.isspace()
    ]
    return {
        "distinct_non_whitespace_scalars": len(frequencies),
        "frequencies": frequencies,
        "semantics": "all scalars in accepted candidate surfaces",
    }


def build_internal_source(args: argparse.Namespace) -> dict[str, object]:
    input_bytes = _read_input_snapshot(args.trilingual_tsv)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != SOURCE_SHA256:
        raise AdapterError(
            "Nepal Bhasa trilingual TSV SHA-256 mismatch: "
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
            "Pinned OCR-derived Nepal Bhasa/Nepali trilingual TSV newar column; "
            "raw NFC identity required; no whitespace or cell splitting"
        ),
        "notes": (
            "Internal product source. The Nepali gloss column is not candidate "
            "vocabulary or ranking evidence; rejected headwords remain in "
            "rejected-rows.jsonl."
        ),
        "path": "new_nepali_trilingual.tsv",
        "redistribution": "prohibited",
        "sha256": source_sha256,
        "source_id": SOURCE_ID,
        "title": "Nepal Bhasa/Nepali trilingual lexicon",
    }
    pack = {
        "allowed_format_characters": ["U+200C", "U+200D"],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Nepal Bhasa (Devanagari)",
        "language": "new",
        "max_suggestions": args.max_suggestions,
        "output_script": "Deva",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": None,
    }
    adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report: dict[str, object] = {
        "adapter": "build_nepal_bhasa_internal_source",
        "adapter_sha256": adapter_sha256,
        "adapter_version": 1,
        "accepted_scalar_inventory": _accepted_scalar_inventory(forms),
        "aliases": {"rows": 0, "policy": ALIASES_POLICY},
        "alternative_splitting": SPLITTING_POLICY,
        "candidate_column": "newar",
        "claim_scope": "candidate_only; no profile or layout is selected",
        "data_version": args.data_version,
        "excluded_columns": ["nepali"],
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": EXPECTED_DATA_ROWS,
            "path": "new_nepali_trilingual.tsv",
            "sha256": source_sha256,
        },
        "filter_policy": FILTER_POLICY,
        "joiner_policy": JOINER_POLICY,
        "normalization": NORMALIZATION_POLICY,
        "pack_id": PACK_ID,
        "ranking": {
            "rank_score": RANK_SCORE,
            "tie_break": "Unicode surface order, then pinned TSV line ID",
            "wikipedia_frequency_ingress": False,
        },
        "policies": {
            "aliases": ALIASES_POLICY,
            "filter": FILTER_POLICY,
            "joiners": JOINER_POLICY,
            "normalization": NORMALIZATION_POLICY,
            "ranking": RANKING_POLICY,
            "splitting": SPLITTING_POLICY,
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
    parser.add_argument("--trilingual-tsv", type=Path, required=True)
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
