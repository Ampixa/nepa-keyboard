#!/usr/bin/env python3
"""Build a research-only Lepcha candidate from pinned Wiktionary lemmas.

The source mixes lemmas with standalone script reference characters. Only
multi-scalar Lepcha letter-and-mark tokens become candidate forms. The small
source cannot establish production vocabulary or ranking quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable


PACK_ID = "lep-Lepc-NP"
SOURCE_ID = "lep-wiktionary-lemmas"
SOURCE_SHA256 = "94ad449b11db2eba9defdec47dca3d9a5069f1785ce04c75f7ed01b0c607a74d"
EXPECTED_ROWS = 280
RANK_SCORE = 1_000


class AdapterError(ValueError):
    """Raised when the pinned Lepcha source violates its input contract."""


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


def _validate_surface(surface: str) -> str | None:
    if not surface:
        return "blank_entry"
    if any(character.isspace() for character in surface):
        return "contains_whitespace"
    if any(not 0x1C00 <= ord(character) <= 0x1C4F for character in surface):
        return "outside_lepcha"
    if any(unicodedata.category(character)[0] not in {"L", "M"} for character in surface):
        return "non_letter_mark"
    if not any(unicodedata.category(character).startswith("L") for character in surface):
        return "no_lepcha_letter"
    if len(surface) == 1:
        return "standalone_script_letter"
    return None


def _read_rows(
    input_bytes: bytes,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    try:
        lines = input_bytes.decode("utf-8-sig").splitlines()
    except UnicodeError as exc:
        raise AdapterError(f"cannot decode Lepcha lemmas as UTF-8: {exc}") from exc
    forms: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    for line_number, raw_surface in enumerate(lines, 1):
        stats["rows"] += 1
        surface = unicodedata.normalize("NFC", raw_surface).strip()
        reason = _validate_surface(surface)
        if reason is not None:
            stats["rejected_rows"] += 1
            stats[f"rejected_{reason}"] += 1
            rejected.append({
                "line": line_number,
                "raw_entry": raw_surface,
                "reason": reason,
            })
            continue
        if surface != raw_surface:
            stats["normalized_rows"] += 1
        forms.append({
            "evidence": "attested",
            "form_id": f"lep:wiktionary:line-{line_number:06d}",
            "rank_score": RANK_SCORE,
            "source_ids": [SOURCE_ID],
            "surface": surface,
        })
        stats["accepted_rows"] += 1
    if stats["rows"] != EXPECTED_ROWS:
        raise AdapterError(
            f"Lepcha lemma row count mismatch: expected {EXPECTED_ROWS}, "
            f"got {stats['rows']}"
        )
    if not forms:
        raise AdapterError("Lepcha source contains no accepted candidate forms")
    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    rejected.sort(key=lambda row: int(row["line"]))
    for key in ("accepted_rows", "rejected_rows", "normalized_rows"):
        stats.setdefault(key, 0)
    stats["distinct_accepted_surfaces"] = len({str(row["surface"]) for row in forms})
    return forms, rejected, dict(sorted(stats.items()))


def build_candidate_source(args: argparse.Namespace) -> dict[str, object]:
    input_bytes = _read_input_snapshot(args.lemmas)
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != SOURCE_SHA256:
        raise AdapterError(
            f"Lepcha lemma SHA-256 mismatch: expected {SOURCE_SHA256}, "
            f"got {source_sha256}"
        )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")
    forms, rejected, stats = _read_rows(input_bytes)
    source = {
        "license": "unknown",
        "method": "Pinned Lepcha Wiktionary lemma list; conservative multi-scalar selection",
        "notes": (
            "The list contains standalone script reference characters and "
            "punctuation-bearing entries. Rejected rows remain in the source report."
        ),
        "path": "wiktionary_lepcha_lemmas.txt",
        "redistribution": "unknown",
        "sha256": source_sha256,
        "source_id": SOURCE_ID,
        "title": "Lepcha Wiktionary lemma reference list",
    }
    pack = {
        "allowed_format_characters": [],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Lepcha Candidate",
        "language": "lep",
        "max_suggestions": args.max_suggestions,
        "output_script": "Lepc",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": "Lepcha reference lemma review pending",
    }
    report: dict[str, object] = {
        "adapter": "build_lepcha_candidate_source",
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "adapter_version": 1,
        "claim_scope": "candidate_only_small_reference_list",
        "aliases": {"rows": 0, "policy": "direct input only"},
        "data_version": args.data_version,
        "input": {
            "bytes": len(input_bytes),
            "expected_rows": EXPECTED_ROWS,
            "path": "wiktionary_lepcha_lemmas.txt",
            "sha256": source_sha256,
        },
        "normalization": (
            "NFC and outer whitespace trimming; accept only multi-scalar "
            "Lepcha letter/mark tokens containing a letter"
        ),
        "pack_id": PACK_ID,
        "ranking": {
            "rank_score": RANK_SCORE,
            "tie_break": "Unicode surface order, then pinned source line ID",
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
    parser.add_argument("--lemmas", type=Path, required=True)
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
