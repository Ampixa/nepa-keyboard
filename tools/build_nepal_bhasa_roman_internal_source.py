#!/usr/bin/env python3
"""Build a deterministic Nepal Bhasa Devanagari pack with Roman aliases.

The candidate vocabulary is regenerated unchanged from the pinned trilingual
source through ``build_nepal_bhasa_internal_source``. Roman aliases come only
from exact positional pairs in the pinned APK lexicon: both semicolon-separated
columns must have the same shape, the Devanagari segment must already be an
accepted direct-pack surface, and both sides must be single tokens. Exact ASCII
source aliases remain attested; scholarly diacritics are reduced by one
explicit NFD fold and labeled generated. No academic-only key is packed and no
alias is generated for a Newa/Prachalit surface.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from tools import build_nepal_bhasa_internal_source as direct


PACK_ID = "new-Deva-NP"
APK_SOURCE_ID = "new-apk-english"
APK_SHA256 = "470be5aaf526d2dca973044fa5ca9a69b4259854958456145661bd58d4889b41"
EXPECTED_APK_ROWS = 5_727
EXPECTED_APK_HEADER = ("newar", "english", "transliteration")
WHITESPACE_RE = re.compile(r"\s")
ASCII_ALIAS_RE = re.compile(r"^[a-z]+$")
ACADEMIC_EXTRA_SCALARS = frozenset("ñāīśūɱḍḥṁṅṇṛṣṭ\u032e")
ALLOWED_ACADEMIC_SCALARS = frozenset("abcdefghijklmnopqrstuvwxyz") | ACADEMIC_EXTRA_SCALARS
REMOVED_NFD_MARKS = frozenset(
    {"\u0301", "\u0303", "\u0304", "\u0307", "\u0323", "\u032e"}
)
ACADEMIC_MEASUREMENT_SCHEME = "new_apk_academic_measurement_v1"
EXACT_ASCII_SCHEME = "new_apk_transliteration_exact_ascii_v1"
ASCII_FOLD_SCHEME = "new_apk_transliteration_ascii_fold_v1"
ALIAS_COMPLETION_BASE = 512
ALIAS_LENGTH_STEP = 2
FOLDED_ALIAS_PENALTY = 1


class RomanAdapterError(ValueError):
    """Raised when a pinned source violates the Roman alias contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RomanAdapterError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise RomanAdapterError(f"expected JSON object at {path}:{line_number}")
        rows.append(row)
    return rows


def _segments(value: str) -> list[str]:
    return [segment.strip(" ") for segment in value.split(";")]


def _normalize_academic_alias(value: str) -> tuple[str | None, str | None]:
    if unicodedata.normalize("NFC", value) != value:
        return None, "non_nfc_alias"
    if WHITESPACE_RE.search(value):
        return None, "multiword_alias"
    normalized = value.casefold()
    if not normalized:
        return None, "empty_alias"
    for character in normalized:
        if character not in ALLOWED_ACADEMIC_SCALARS:
            return None, "unsupported_alias_scalar"
    return normalized, None


def _fold_ascii_alias(value: str) -> str:
    output: list[str] = []
    for character in unicodedata.normalize("NFD", value):
        if "a" <= character <= "z":
            output.append(character)
        elif character == "ɱ":
            output.append("m")
        elif character in REMOVED_NFD_MARKS:
            continue
        else:
            raise RomanAdapterError(
                f"academic alias contains an unmapped NFD scalar U+{ord(character):04X}"
            )
    folded = "".join(output)
    if not ASCII_ALIAS_RE.fullmatch(folded):
        raise RomanAdapterError(f"academic alias did not fold to ASCII letters: {value!r}")
    return folded


def _alias_rank_delta(alias: str, *, exact_ascii: bool) -> int:
    """Prefer a completed alias over longer descendants in the prefix trie."""
    return (
        ALIAS_COMPLETION_BASE
        - ALIAS_LENGTH_STEP * len(alias)
        - (0 if exact_ascii else FOLDED_ALIAS_PENALTY)
    )


def _accepted_form_index(forms: list[dict[str, object]]) -> dict[str, str]:
    by_surface: dict[str, list[str]] = defaultdict(list)
    for row in forms:
        surface = row.get("surface")
        form_id = row.get("form_id")
        if not isinstance(surface, str) or not isinstance(form_id, str):
            raise RomanAdapterError("direct source contains malformed forms")
        by_surface[surface].append(form_id)
    return {surface: min(form_ids) for surface, form_ids in by_surface.items()}


def _collision_summary(
    aliases: list[dict[str, object]],
    form_to_surface: dict[str, str],
    *,
    schemes: frozenset[str] | None = None,
) -> dict[str, object]:
    keys: dict[str, set[str]] = defaultdict(set)
    for row in aliases:
        if schemes is None or row["scheme"] in schemes:
            keys[str(row["alias"])].add(form_to_surface[str(row["form_id"])])
    distribution = Counter(len(surfaces) for surfaces in keys.values())
    collision_rows = [
        {"alias": alias, "surfaces": sorted(surfaces)}
        for alias, surfaces in sorted(keys.items())
        if len(surfaces) > 1
    ]
    return {
        "collision_key_count": len(collision_rows),
        "collision_key_sha256": _sha256_bytes(
            "".join(
                f"{row['alias']}\t{'|'.join(row['surfaces'])}\n" for row in collision_rows
            ).encode("utf-8")
        ),
        "collision_examples": collision_rows[:32],
        "distinct_keys": len(keys),
        "max_targets_per_exact_key": max((len(value) for value in keys.values()), default=0),
        "target_count_distribution": [
            {"keys": distribution[count], "targets": count} for count in sorted(distribution)
        ],
    }


def _build_alias_rows(
    apk_bytes: bytes,
    surface_to_form: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    if apk_bytes.startswith(b"\xef\xbb\xbf"):
        raise RomanAdapterError("APK TSV must not contain a UTF-8 BOM")
    try:
        handle = io.StringIO(apk_bytes.decode("utf-8-sig"), newline="")
    except UnicodeError as exc:
        raise RomanAdapterError(f"cannot decode APK TSV as UTF-8: {exc}") from exc

    aliases_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    academic_by_key: dict[tuple[str, str], dict[str, object]] = {}
    rejected: list[dict[str, object]] = []
    accepted_occurrences: list[str] = []
    stats: Counter[str] = Counter()
    with handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != EXPECTED_APK_HEADER:
            raise RomanAdapterError("APK TSV header does not match the pinned contract")
        for line_number, row in enumerate(reader, 2):
            stats["rows"] += 1
            if None in row or any(value is None for value in row.values()):
                raise RomanAdapterError(f"APK TSV row {line_number} has the wrong column count")
            surfaces = _segments(row["newar"])
            academic_aliases = _segments(row["transliteration"])
            if len(surfaces) != len(academic_aliases):
                raise RomanAdapterError(
                    f"APK TSV row {line_number} has asymmetric semicolon segments"
                )
            trailing_positions = 0
            while surfaces and not surfaces[-1] and not academic_aliases[-1]:
                surfaces.pop()
                academic_aliases.pop()
                trailing_positions += 1
            if trailing_positions:
                stats["rows_with_matched_trailing_delimiter"] += 1
                stats["matched_trailing_empty_positions"] += trailing_positions
            stats["segments"] += len(surfaces)
            for segment_index, (surface, raw_alias) in enumerate(
                zip(surfaces, academic_aliases, strict=True), 1
            ):
                location = {
                    "line": line_number,
                    "segment": segment_index,
                    "source_id": APK_SOURCE_ID,
                    "surface": surface,
                    "transliteration": raw_alias,
                }
                if not surface and not raw_alias:
                    reason = "paired_empty_segment"
                elif not surface or not raw_alias:
                    raise RomanAdapterError(
                        f"APK TSV row {line_number} segment {segment_index} is asymmetrically empty"
                    )
                elif unicodedata.normalize("NFC", surface) != surface:
                    reason = "non_nfc_surface"
                elif WHITESPACE_RE.search(surface):
                    reason = "multiword_surface"
                elif surface not in surface_to_form:
                    reason = "surface_absent_from_direct_pack"
                else:
                    academic, reason = _normalize_academic_alias(raw_alias)
                    if reason is None:
                        assert academic is not None
                        form_id = surface_to_form[surface]
                        folded = _fold_ascii_alias(academic)
                        academic_by_key[(academic, form_id)] = {
                            "alias": academic,
                            "form_id": form_id,
                            "scheme": ACADEMIC_MEASUREMENT_SCHEME,
                        }
                        is_exact_ascii = folded == academic
                        scheme = EXACT_ASCII_SCHEME if is_exact_ascii else ASCII_FOLD_SCHEME
                        alias_row = {
                            "alias": folded,
                            "evidence": "attested" if is_exact_ascii else "generated",
                            "form_id": form_id,
                            "rank_delta": _alias_rank_delta(
                                folded, exact_ascii=is_exact_ascii
                            ),
                            "scheme": scheme,
                            "source_ids": [APK_SOURCE_ID],
                        }
                        aliases_by_key[(folded, form_id, scheme)] = alias_row
                        accepted_occurrences.append(
                            f"{line_number}\t{segment_index}\t{surface}\t{academic}\t{folded}\n"
                        )
                        stats["accepted_pair_occurrences"] += 1
                        continue
                stats["rejected_segments"] += 1
                stats[f"rejected_{reason}"] += 1
                rejected.append({**location, "reason": reason})

    if stats["rows"] != EXPECTED_APK_ROWS:
        raise RomanAdapterError(
            f"APK TSV row count mismatch: expected {EXPECTED_APK_ROWS}, got {stats['rows']}"
        )
    aliases = [aliases_by_key[key] for key in sorted(aliases_by_key)]
    if not aliases:
        raise RomanAdapterError("APK TSV produced no accepted Roman aliases")
    form_to_surface = {form_id: surface for surface, form_id in surface_to_form.items()}
    academic_rows = [academic_by_key[key] for key in sorted(academic_by_key)]
    academic_pairs = {
        (str(row["alias"]), form_to_surface[str(row["form_id"])])
        for row in academic_rows
    }
    ascii_pairs = {
        (str(row["alias"]), form_to_surface[str(row["form_id"])])
        for row in aliases
    }
    stats.setdefault("rejected_segments", 0)
    stats["accepted_academic_pairs"] = len(academic_pairs)
    stats["accepted_ascii_pairs"] = len(ascii_pairs)
    stats["accepted_exact_ascii_pairs"] = sum(
        row["scheme"] == EXACT_ASCII_SCHEME for row in aliases
    )
    stats["accepted_folded_ascii_pairs"] = sum(
        row["scheme"] == ASCII_FOLD_SCHEME for row in aliases
    )
    stats["accepted_target_surfaces"] = len(
        {surface for _alias, surface in academic_pairs}
    )
    stats["duplicate_academic_pair_occurrences"] = (
        stats["accepted_pair_occurrences"] - len(academic_pairs)
    )
    return aliases, rejected, {
        "accepted_occurrence_sha256": _sha256_bytes(
            "".join(accepted_occurrences).encode("utf-8")
        ),
        "academic_measurement": _collision_summary(academic_rows, form_to_surface),
        "ascii": _collision_summary(aliases, form_to_surface),
        "ascii_exact_only": _collision_summary(
            aliases, form_to_surface, schemes=frozenset({EXACT_ASCII_SCHEME})
        ),
        "ascii_folded_only": _collision_summary(
            aliases, form_to_surface, schemes=frozenset({ASCII_FOLD_SCHEME})
        ),
        "stats": dict(sorted(stats.items())),
    }


def build_internal_source(args: argparse.Namespace) -> dict[str, object]:
    try:
        apk_bytes = args.apk_tsv.read_bytes()
    except OSError as exc:
        raise RomanAdapterError(f"cannot read APK TSV {args.apk_tsv}: {exc}") from exc
    apk_sha256 = _sha256_bytes(apk_bytes)
    if apk_sha256 != APK_SHA256:
        raise RomanAdapterError(
            f"APK TSV SHA-256 mismatch: expected {APK_SHA256}, got {apk_sha256}"
        )

    with tempfile.TemporaryDirectory(prefix="new-roman-direct-") as temporary:
        direct_output = Path(temporary) / "direct"
        try:
            direct_report = direct.build_internal_source(
                argparse.Namespace(
                    trilingual_tsv=args.trilingual_tsv,
                    output=direct_output,
                    data_version=args.data_version,
                    max_suggestions=args.max_suggestions,
                )
            )
        except direct.AdapterError as exc:
            raise RomanAdapterError(str(exc)) from exc
        forms = _read_jsonl(direct_output / "forms.jsonl")
        surface_to_form = _accepted_form_index(forms)
        aliases, rejected_aliases, alias_report = _build_alias_rows(
            apk_bytes, surface_to_form
        )

        args.output.mkdir(parents=True, exist_ok=True)
        for file_name in ("pack.json", "forms.jsonl"):
            shutil.copyfile(direct_output / file_name, args.output / file_name)

        sources = _read_jsonl(direct_output / "sources.jsonl")
        sources.append(
            {
                "license": "restricted",
                "method": (
                    "Exact positional pairing of literal-semicolon Devanagari and "
                    "transliteration segments; single-token direct-pack intersection"
                ),
                "notes": (
                    "Exact ASCII aliases are source-provided. Diacritic aliases use "
                    "only the adapter's explicit NFD scalar fold and remain generated "
                    "evidence. Academic keys are measured but not packed."
                ),
                "path": "new_apk_eng_lexicon.tsv",
                "redistribution": "prohibited",
                "sha256": apk_sha256,
                "source_id": APK_SOURCE_ID,
                "title": "Nepal Bhasa/English APK lexicon",
            }
        )
        sources.sort(key=lambda row: str(row["source_id"]))
        _write_jsonl(args.output / "sources.jsonl", sources)
        _write_jsonl(args.output / "aliases.jsonl", aliases)

        rejected_direct = _read_jsonl(direct_output / "rejected-rows.jsonl")
        rejected = [
            {**row, "source_id": direct.SOURCE_ID} for row in rejected_direct
        ] + rejected_aliases
        rejected.sort(
            key=lambda row: (
                str(row.get("source_id", "")),
                int(row.get("line", 0)),
                int(row.get("segment", 0)),
            )
        )
        _write_jsonl(args.output / "rejected-rows.jsonl", rejected)

    adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    direct_target_count = len(surface_to_form)
    accepted_target_count = int(alias_report["stats"]["accepted_target_surfaces"])
    report: dict[str, object] = {
        "adapter": "build_nepal_bhasa_roman_internal_source",
        "adapter_sha256": adapter_sha256,
        "adapter_version": 1,
        "alias_contract": {
            "academic_measurement_scheme": ACADEMIC_MEASUREMENT_SCHEME,
            "ascii_fold": {
                "nfd_marks_removed": [f"U+{ord(value):04X}" for value in sorted(REMOVED_NFD_MARKS, key=ord)],
                "special_bases": [{"from": "ɱ", "to": "m"}],
            },
            "ascii_ranking": {
                "completion_base": ALIAS_COMPLETION_BASE,
                "exact_ascii_penalty": 0,
                "folded_alias_penalty": FOLDED_ALIAS_PENALTY,
                "length_step": ALIAS_LENGTH_STEP,
                "policy": (
                    "direct form score + completion_base - 2*ASCII length - "
                    "folded penalty; exact completed keys precede descendants"
                ),
            },
            "ascii_exact_scheme": EXACT_ASCII_SCHEME,
            "ascii_fold_scheme": ASCII_FOLD_SCHEME,
            "candidate_policy": "exact intersection with accepted new-Deva-NP surfaces",
            "format_policy": "reject controls, joiners, punctuation, digits, and symbols",
            "segmentation": (
                "literal semicolon; trim U+0020; record and remove matched trailing "
                "empty positions; preserve interior positional empties"
            ),
            "token_policy": "single-token Devanagari surface and Roman alias only",
        },
        "aliases": alias_report,
        "candidate_coverage": {
            "accepted_target_surfaces": accepted_target_count,
            "direct_pack_surfaces": direct_target_count,
            "ratio": f"{accepted_target_count}/{direct_target_count}",
        },
        "claim_scope": (
            "internal Roman-to-Devanagari alias candidate; no Roman-to-Newa claim"
        ),
        "data_version": args.data_version,
        "direct_adapter_report_sha256": _sha256_bytes(
            _canonical_json(direct_report).encode("utf-8")
        ),
        "inputs": {
            "apk": {
                "bytes": len(apk_bytes),
                "expected_data_rows": EXPECTED_APK_ROWS,
                "sha256": apk_sha256,
            },
            "trilingual": {
                "expected_data_rows": direct.EXPECTED_DATA_ROWS,
                "sha256": direct.SOURCE_SHA256,
            },
        },
        "pack_id": PACK_ID,
    }
    (args.output / "adapter-report.json").write_text(
        _canonical_json(report) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trilingual-tsv", type=Path, required=True)
    parser.add_argument("--apk-tsv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-version", default="1.1.0")
    parser.add_argument("--max-suggestions", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_internal_source(args)
    except RomanAdapterError as exc:
        parser.error(str(exc))
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
