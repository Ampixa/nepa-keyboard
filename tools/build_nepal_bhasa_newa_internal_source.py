#!/usr/bin/env python3
"""Build a deterministic internal Prachalit/Newa Nepal Bhasa source.

The pinned source is born-digital Newa text collected from Nepal Lipi Online.
Only whitespace-delimited tokens that reduce to Newa letters and combining
marks after boundary-punctuation removal become candidates. Mixed-script,
non-NFC, malformed-joiner, and punctuation-internal tokens are recorded in a
rejection ledger. Ranking uses observed token frequency; no Devanagari
conversion, OCR output, or guessed word segmentation enters this pack.
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


PACK_ID = "new-Newa-NP"
SOURCE_ID = "new-prachalit-online-corpus"
SOURCE_SHA256 = "6ff04654fb048b56b021cda8719b3c8bc5c3b5d7baa59621a7bef2019930fcc2"
EXPECTED_DATA_ROWS = 285
NEWARANGE = range(0x11400, 0x11480)
NEWA_VIRAMA = "\U00011442"
JOINERS = frozenset({"\u200c", "\u200d"})
ALLOWED_FORMAT_CODEPOINTS = {0x200C, 0x200D}
BOUNDARY_CATEGORIES = frozenset({"N", "P", "S"})
RANK_BASE = 1_000
ALIASES_POLICY = "none"
NORMALIZATION_POLICY = "raw NFC identity required"
TOKENIZATION_POLICY = (
    "split only on source whitespace; remove boundary punctuation, numbers, "
    "and symbols; never split remaining token content"
)
FILTER_POLICY = (
    "require a Newa letter; allow only Newa letters/marks plus context-valid "
    "ZWJ/ZWNJ after Newa virama"
)
RANKING_POLICY = "1000 plus attested token occurrence count; Unicode tie-break"


class AdapterError(ValueError):
    """Raised when the pinned Prachalit corpus violates its contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _is_newa(character: str) -> bool:
    return ord(character) in NEWARANGE


def _is_newa_letter(character: str) -> bool:
    return _is_newa(character) and unicodedata.category(character).startswith("L")


def _is_boundary(character: str) -> bool:
    return unicodedata.category(character)[:1] in BOUNDARY_CATEGORIES


def _trim_boundaries(token: str) -> str:
    start = 0
    end = len(token)
    while start < end and _is_boundary(token[start]):
        start += 1
    while end > start and _is_boundary(token[end - 1]):
        end -= 1
    return token[start:end]


def _has_newa_base_before_virama(value: str, joiner_index: int) -> bool:
    index = joiner_index - 2
    while index >= 0 and _is_newa(value[index]) and unicodedata.category(
        value[index]
    ).startswith("M"):
        index -= 1
    return index >= 0 and _is_newa_letter(value[index])


def _is_valid_joiner_context(value: str, index: int) -> bool:
    return (
        1 < index < len(value) - 1
        and value[index - 1] == NEWA_VIRAMA
        and _has_newa_base_before_virama(value, index)
        and _is_newa_letter(value[index + 1])
    )


def _validate_surface(surface: str) -> str | None:
    if not surface:
        return "empty_after_boundary_trim"
    has_letter = False
    for index, character in enumerate(surface):
        category = unicodedata.category(character)
        if category == "Cf":
            if character not in JOINERS:
                return "unsupported_format_character"
            if not _is_valid_joiner_context(surface, index):
                return "invalid_joiner_context"
            continue
        if not _is_newa(character):
            return "outside_newa"
        if category[0] not in {"L", "M"}:
            return "unsupported_newa_character"
        has_letter = has_letter or category.startswith("L")
    return None if has_letter else "no_newa_letter"


def _read_rows(
    input_bytes: bytes,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    if input_bytes.startswith(b"\xef\xbb\xbf"):
        raise AdapterError("Prachalit corpus must not contain a UTF-8 BOM")
    try:
        text = input_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdapterError(f"cannot decode Prachalit corpus as UTF-8: {exc}") from exc
    lines = text.splitlines()
    if len(lines) != EXPECTED_DATA_ROWS:
        raise AdapterError(
            "Prachalit corpus line count mismatch: "
            f"expected {EXPECTED_DATA_ROWS}, got {len(lines)}"
        )

    occurrences: Counter[str] = Counter()
    first_location: dict[str, tuple[int, int]] = {}
    rejected: list[dict[str, object]] = []
    stats: Counter[str] = Counter(lines=len(lines))
    for line_number, line in enumerate(lines, 1):
        if unicodedata.normalize("NFC", line) != line:
            raise AdapterError(f"Prachalit corpus line {line_number} is not NFC")
        for token_number, raw_token in enumerate(re.findall(r"\S+", line), 1):
            stats["tokens"] += 1
            surface = _trim_boundaries(raw_token)
            reason = _validate_surface(surface)
            if reason is not None:
                stats["rejected_rows"] += 1
                stats[f"rejected_{reason}"] += 1
                rejected.append(
                    {
                        "line": line_number,
                        "raw_token": raw_token,
                        "reason": reason,
                        "token": token_number,
                    }
                )
                continue
            occurrences[surface] += 1
            first_location.setdefault(surface, (line_number, token_number))
            stats["accepted_rows"] += 1

    if not occurrences:
        raise AdapterError("Prachalit corpus has no accepted word tokens")
    forms: list[dict[str, object]] = []
    for surface in sorted(occurrences):
        line_number, token_number = first_location[surface]
        digest = hashlib.sha256(surface.encode("utf-8")).hexdigest()[:20]
        forms.append(
            {
                "evidence": "attested",
                "form_id": f"new:prachalit-online:{digest}",
                "rank_score": RANK_BASE + occurrences[surface],
                "source_ids": [SOURCE_ID],
                "surface": surface,
            }
        )
        del line_number, token_number
    stats["distinct_accepted_surfaces"] = len(forms)
    stats["max_surface_frequency"] = max(occurrences.values())
    stats["singleton_surfaces"] = sum(count == 1 for count in occurrences.values())
    for key in ("accepted_rows", "rejected_rows", "tokens"):
        stats.setdefault(key, 0)
    return forms, rejected, dict(sorted(stats.items()))


def _accepted_scalar_inventory(forms: list[dict[str, object]]) -> dict[str, object]:
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
    ]
    return {
        "distinct_scalars": len(frequencies),
        "frequencies": frequencies,
        "semantics": "all scalars in accepted candidate surfaces",
    }


def build_internal_source(args: argparse.Namespace) -> dict[str, object]:
    try:
        input_bytes = args.prachalit_corpus.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read input {args.prachalit_corpus}: {exc}") from exc
    source_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if source_sha256 != SOURCE_SHA256:
        raise AdapterError(
            "Prachalit corpus SHA-256 mismatch: "
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
            "Pinned born-digital Nepal Lipi Online lines; source whitespace is "
            "the only word boundary; strict Newa-script token filtering"
        ),
        "notes": (
            "Internal attested source. This pack contains no Devanagari-to-Newa "
            "conversion and no OCR-derived candidates."
        ),
        "path": "nepal_lipi_online_corpus.txt",
        "redistribution": "prohibited",
        "sha256": source_sha256,
        "source_id": SOURCE_ID,
        "title": "Nepal Lipi Online born-digital Newa corpus",
    }
    pack = {
        "allowed_format_characters": ["U+200C", "U+200D"],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Nepal Bhasa (Prachalit Nepal Lipi)",
        "language": "new",
        "max_suggestions": args.max_suggestions,
        "output_script": "Newa",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": None,
    }
    adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report: dict[str, object] = {
        "adapter": "build_nepal_bhasa_newa_internal_source",
        "adapter_sha256": adapter_sha256,
        "adapter_version": 1,
        "accepted_scalar_inventory": _accepted_scalar_inventory(forms),
        "aliases": {"policy": ALIASES_POLICY, "rows": 0},
        "claim_scope": (
            "attested_internal_candidate_pack; layout ergonomics and native "
            "accessibility review remain pending"
        ),
        "data_version": args.data_version,
        "input": {
            "bytes": len(input_bytes),
            "expected_data_rows": EXPECTED_DATA_ROWS,
            "path": "nepal_lipi_online_corpus.txt",
            "sha256": source_sha256,
        },
        "pack_id": PACK_ID,
        "policies": {
            "aliases": ALIASES_POLICY,
            "filter": FILTER_POLICY,
            "normalization": NORMALIZATION_POLICY,
            "ranking": RANKING_POLICY,
            "tokenization": TOKENIZATION_POLICY,
        },
        "ranking": {
            "base_score": RANK_BASE,
            "frequency_unit": "source token occurrence",
            "tie_break": "Unicode surface order",
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
    parser.add_argument("--prachalit-corpus", type=Path, required=True)
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
