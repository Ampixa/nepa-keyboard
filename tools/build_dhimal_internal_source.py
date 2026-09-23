#!/usr/bin/env python3
"""Build deterministic Dhimal direct-input tables from the pinned Webonary TSV.

The source is already a reviewed extraction produced by dhimal-toolkit. This
adapter does not reinterpret Nepali glosses or generate Roman aliases. It
selects the Dhimal headword column, applies conservative NFC and whitespace
normalization, preserves only context-valid conjunct ZWJ/ZWNJ, and records
rejected rows rather than guessing repairs. The resulting tables are for an
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


PACK_ID = "dhi-Deva-NP"
SOURCE_ID = "dhi-webonary"
SOURCE_TAG = "dict_sil_webonary"
WEBONARY_SHA256 = "8ba3846eeff8c0b76c9d923b4ebec379189c5abe8a5bd9bb07e9500643cb8321"
# Common milestone finalizers use this language-neutral constant name. Keep the
# source-specific alias above because it remains clearer in adapter diagnostics.
SOURCE_SHA256 = WEBONARY_SHA256
EXPECTED_DATA_ROWS = 8_781
EXPECTED_HEADER = ("nepali", "dhimal", "pos", "source")
RANK_SCORE = 1_000
ALLOWED_FORMAT_CODEPOINTS = {0x200C, 0x200D}
JOINERS = frozenset(chr(codepoint) for codepoint in ALLOWED_FORMAT_CODEPOINTS)
DEVANAGARI_VIRAMA = "\u094d"
DEVA_RANGES = ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x11B00, 0x11B5F))
WHITESPACE_RE = re.compile(r"\s+")


class AdapterError(ValueError):
    """Raised when the pinned Webonary table violates the adapter contract."""


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
    normalized = WHITESPACE_RE.sub(
        " ",
        unicodedata.normalize("NFC", raw),
    ).strip()
    return normalized, normalized != raw


def _is_devanagari_character(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in DEVA_RANGES)


def _is_devanagari_letter(character: str) -> bool:
    return _is_devanagari_character(character) and unicodedata.category(character).startswith("L")


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
        raise AdapterError(f"cannot decode Dhimal Webonary TSV as UTF-8: {exc}") from exc

    with handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADER:
            raise AdapterError("Dhimal TSV header does not match the pinned four-column contract")
        for line_number, row in enumerate(reader, 2):
            stats["rows"] += 1
            if None in row or any(value is None for value in row.values()):
                raise AdapterError(f"Dhimal TSV row {line_number} has the wrong number of columns")
            if row["source"] != SOURCE_TAG:
                raise AdapterError(
                    f"Dhimal TSV row {line_number} has unexpected source tag {row['source']!r}"
                )

            surface, normalized = _normalize_surface(row["dhimal"])
            reason = _validate_surface(surface)
            if reason is not None:
                stats["rejected_rows"] += 1
                stats[f"rejected_{reason}"] += 1
                rejected.append({
                    "line": line_number,
                    "raw_headword": row["dhimal"],
                    "reason": reason,
                })
                continue
            if normalized:
                stats["normalized_rows"] += 1
            forms.append({
                "evidence": "attested",
                "form_id": f"dhi:webonary:line-{line_number:06d}",
                "rank_score": RANK_SCORE,
                "source_ids": [SOURCE_ID],
                "surface": surface,
            })
            stats["accepted_rows"] += 1

    if stats["rows"] != EXPECTED_DATA_ROWS:
        raise AdapterError(
            f"Dhimal TSV row count mismatch: expected {EXPECTED_DATA_ROWS}, got {stats['rows']}"
        )
    if not forms:
        raise AdapterError("Dhimal TSV contains no accepted native-script headwords")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: int(row["line"]))
    for key in ("accepted_rows", "rejected_rows", "normalized_rows"):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len({str(row["surface"]) for row in forms})
    return forms, rejected, dict(sorted(stats.items()))


def build_internal_source(args: argparse.Namespace) -> dict[str, object]:
    input_bytes = _read_input_snapshot(args.webonary_tsv)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != WEBONARY_SHA256:
        raise AdapterError(
            "Dhimal Webonary SHA-256 mismatch: "
            f"expected {WEBONARY_SHA256}, got {source_sha256}"
        )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")

    forms, rejected, stats = _read_rows(input_bytes)
    source = {
        "license": "SIL-(c)-ARR",
        "method": (
            "Pinned dhimal-toolkit Webonary TSV dhimal column; NFC and "
            "whitespace normalization only"
        ),
        "notes": (
            "Internal product source. Nepali gloss, POS, and source columns are "
            "not candidate surfaces; rejected headwords remain in rejected-rows.jsonl."
        ),
        "path": "dict_webonary_nep_dhi.tsv",
        "redistribution": "prohibited",
        "sha256": source_sha256,
        "source_id": SOURCE_ID,
        "title": "SIL Webonary Dhimal dictionary",
    }
    pack = {
        "allowed_format_characters": ["U+200C", "U+200D"],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Dhimal",
        "language": "dhi",
        "max_suggestions": args.max_suggestions,
        "output_script": "Deva",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": None,
    }
    adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report: dict[str, object] = {
        "adapter": "build_dhimal_internal_source",
        "adapter_sha256": adapter_sha256,
        "adapter_version": 2,
        "aliases": {"rows": 0, "policy": "direct input only"},
        "data_version": args.data_version,
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": EXPECTED_DATA_ROWS,
            "path": "dict_webonary_nep_dhi.tsv",
            "sha256": source_sha256,
        },
        "normalization": (
            "NFC; collapse whitespace; trim; preserve context-valid conjunct "
            "ZWJ/ZWNJ; reject symbols; require at least one Devanagari letter"
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
    parser.add_argument("--webonary-tsv", type=Path, required=True)
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
