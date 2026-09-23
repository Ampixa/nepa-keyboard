#!/usr/bin/env python3
"""Build an auditable, direct-input Nepali release-pack source directory.

Only two pinned, redistributable inputs are accepted:

* ``google/language-resources`` ``ne/data/lexicon.tsv`` at the audited commit;
* OpenSLR54 ``utt_spk_text.tsv``.

The adapter emits canonical Devanagari surface forms only.  It deliberately
does not generate Roman aliases and never reads the older combined frequency
table or Hunspell dictionary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable


PACK_ID = "npi-Deva-NP"
GOOGLE_SOURCE_ID = "google-language-resources-ne-lexicon"
OPENSLR_SOURCE_ID = "openslr54-nepali-transcripts"

GOOGLE_PINNED_COMMIT = "a90601024f07ab7e96c911243324e0adeb16da96"
GOOGLE_LEXICON_SHA256 = "a9f616db4ecc35ecde4e519e1438c5501d8574b3623d43370fb0089a31ea8a83"
OPENSLR_TRANSCRIPTS_SHA256 = "2e4379f4799a280ef71150bce91dc629cc87e89ae344db1ec1575b00c76740fa"

GOOGLE_PROJECT_URL = "https://github.com/google/language-resources"
GOOGLE_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/legalcode"
OPENSLR_PROJECT_URL = "https://www.openslr.org/54/"
OPENSLR_SOURCE_URL = "https://www.openslr.org/resources/54/utt_spk_text.tsv"
OPENSLR_LICENSE_URL = "https://www.openslr.org/resources/54/LICENSE"
OPENSLR_LEGALCODE_URL = "https://creativecommons.org/licenses/by-sa/4.0/legalcode"

GOOGLE_ATTESTATION_RANK_BONUS = 1000
OPENSLR_LOG_FREQUENCY_SCALE = 1000
DEVANAGARI_VIRAMA = "\u094d"
ZWNJ = "\u200c"
ZWJ = "\u200d"
JOINERS = frozenset({ZWNJ, ZWJ})
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DEVANAGARI_RANGES = (
    (0x0900, 0x097F),
    (0xA8E0, 0xA8FF),
    (0x11B00, 0x11B5F),
)


class AdapterError(ValueError):
    """Raised when an input cannot safely produce the release source."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except FileNotFoundError as exc:
        raise AdapterError(f"missing required input: {path}") from exc
    return digest.hexdigest()


def _verify_pinned_file(path: Path, expected_sha256: str, label: str) -> str:
    actual = _sha256_file(path)
    if actual != expected_sha256:
        raise AdapterError(
            f"{label} SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return actual


def _read_license(path: Path, required_phrase: str, label: str) -> tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
    except FileNotFoundError as exc:
        raise AdapterError(f"missing required {label}: {path}") from exc
    except UnicodeDecodeError as exc:
        raise AdapterError(f"{label} is not UTF-8: {path}") from exc
    if not text:
        raise AdapterError(f"{label} is empty: {path}")
    if required_phrase not in text:
        raise AdapterError(f"{label} does not contain {required_phrase!r}: {path}")
    return text, _sha256_file(path)


def _is_devanagari_character(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in DEVANAGARI_RANGES)


def _is_devanagari_letter(character: str) -> bool:
    return _is_devanagari_character(character) and unicodedata.category(character).startswith("L")


def _is_devanagari_letter_or_mark(character: str) -> bool:
    return _is_devanagari_character(character) and unicodedata.category(character)[0] in {"L", "M"}


def _is_valid_joiner_context(value: str, index: int) -> bool:
    return (
        0 < index < len(value) - 1
        and value[index - 1] == DEVANAGARI_VIRAMA
        and _is_devanagari_letter(value[index + 1])
    )


def _canonical_token(value: str) -> str | None:
    normalized = unicodedata.normalize("NFC", value.strip())
    if not normalized or not _is_devanagari_letter(normalized[0]):
        return None
    for index, character in enumerate(normalized):
        if _is_devanagari_letter_or_mark(character):
            continue
        if character in JOINERS and _is_valid_joiner_context(normalized, index):
            continue
        return None
    return normalized


def _record_retained_joiners(token: str, stats: Counter[str]) -> None:
    zwnj_count = token.count(ZWNJ)
    zwj_count = token.count(ZWJ)
    total = zwnj_count + zwj_count
    if not total:
        return
    stats["retained_joiner_tokens"] += 1
    stats["retained_joiner_characters"] += total
    stats["retained_zwnj"] += zwnj_count
    stats["retained_zwj"] += zwj_count


def _ensure_quality_stats(stats: Counter[str]) -> None:
    for key in (
        "rejected_invalid_runs",
        "rejected_invalid_joiner_runs",
        "retained_joiner_tokens",
        "retained_joiner_characters",
        "retained_zwnj",
        "retained_zwj",
    ):
        stats.setdefault(key, 0)


def _extract_transcript_tokens(text: str, stats: Counter[str] | None = None) -> list[str]:
    """Extract maximal Devanagari/joiner runs, rejecting malformed runs whole."""
    result: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        raw_token = "".join(run)
        token = _canonical_token(raw_token)
        if token is not None:
            result.append(token)
            if stats is not None:
                _record_retained_joiners(token, stats)
        elif stats is not None:
            stats["rejected_invalid_runs"] += 1
            if any(character in JOINERS for character in raw_token):
                stats["rejected_invalid_joiner_runs"] += 1
        run.clear()

    for character in text:
        if _is_devanagari_letter_or_mark(character) or character in JOINERS:
            run.append(character)
        else:
            flush()
    flush()
    return result


def _load_google_lexicon(path: Path) -> tuple[set[str], dict[str, int]]:
    tokens: set[str] = set()
    stats = Counter()
    try:
        handle = path.open(encoding="utf-8-sig", newline="")
    except FileNotFoundError as exc:
        raise AdapterError(f"missing Google lexicon: {path}") from exc

    with handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip("\r\n")
            if not line.strip():
                stats["blank_rows"] += 1
                continue
            if line.lstrip().startswith("#"):
                stats["comment_rows"] += 1
                continue
            fields = line.split("\t")
            if len(fields) < 2:
                raise AdapterError(
                    f"Google lexicon row {line_number} is not tab-separated"
                )
            stats["data_rows"] += 1
            spelling = fields[0].strip()
            token = _canonical_token(spelling)
            if token is None:
                stats["rejected_rows"] += 1
                if any(character in JOINERS for character in spelling):
                    stats["rejected_invalid_joiner_rows"] += 1
                continue
            if token != spelling:
                stats["normalized_rows"] += 1
            _record_retained_joiners(token, stats)
            if token in tokens:
                stats["duplicate_rows"] += 1
            tokens.add(token)

    if not tokens:
        raise AdapterError("Google lexicon contains no valid Nepali Devanagari tokens")
    _ensure_quality_stats(stats)
    stats.setdefault("rejected_invalid_joiner_rows", 0)
    stats["unique_tokens"] = len(tokens)
    return tokens, dict(sorted(stats.items()))


def _load_openslr_counts(path: Path) -> tuple[Counter[str], dict[str, int]]:
    counts: Counter[str] = Counter()
    stats = Counter()
    seen_prompts: set[str] = set()
    try:
        handle = path.open(encoding="utf-8-sig", newline="")
    except FileNotFoundError as exc:
        raise AdapterError(f"missing OpenSLR54 transcripts: {path}") from exc

    with handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip("\r\n")
            if not line:
                raise AdapterError(f"OpenSLR54 row {line_number} is empty")
            fields = line.split("\t", 2)
            if len(fields) != 3 or not fields[0] or not fields[1]:
                raise AdapterError(
                    f"OpenSLR54 row {line_number} must contain file ID, speaker ID, and text"
                )
            stats["rows"] += 1
            prompt = fields[2]
            if prompt in seen_prompts:
                stats["duplicate_prompt_rows"] += 1
                continue
            seen_prompts.add(prompt)
            tokens = _extract_transcript_tokens(prompt, stats)
            if not tokens:
                stats["rows_without_valid_tokens"] += 1
                continue
            counts.update(tokens)
            stats["token_occurrences"] += len(tokens)

    if not counts:
        raise AdapterError("OpenSLR54 contains no valid Nepali Devanagari tokens")
    _ensure_quality_stats(stats)
    stats.setdefault("duplicate_prompt_rows", 0)
    stats["unique_prompts"] = len(seen_prompts)
    stats["unique_tokens"] = len(counts)
    return counts, dict(sorted(stats.items()))


def _stable_form_id(surface: str) -> str:
    digest = hashlib.sha256(("npi\0" + surface).encode("utf-8")).hexdigest()[:20]
    return f"npi:{digest}"


def _source_rows(
    google_commit: str,
    google_source_sha256: str,
    google_license_sha256: str,
    google_license_text: str,
    openslr_source_sha256: str,
    openslr_license_sha256: str,
    openslr_license_text: str,
) -> list[dict[str, object]]:
    google_source_url = (
        "https://raw.githubusercontent.com/google/language-resources/"
        f"{google_commit}/ne/data/lexicon.tsv"
    )
    google_attribution = (
        "Copyright 2018 Google Inc. The source is google/language-resources "
        f"ne/data/lexicon.tsv at commit {google_commit}, licensed under CC BY 4.0. "
        "Nepa Keyboard extracts the spelling column, NFC-normalizes it, filters it "
        "to Devanagari letter/mark forms with context-valid conjunct joiners, and "
        "omits the pronunciations."
    )
    openslr_attribution = (
        "Copyright 2016, 2017, 2018 Google, Inc. The source is OpenSLR SLR54, "
        "Large Nepali ASR training data set, licensed under CC BY-SA 4.0. "
        "Nepa Keyboard deduplicates exact transcript prompts, extracts NFC Devanagari "
        "letter/mark tokens with context-valid conjunct joiners, and uses log-scaled "
        "token counts solely to rank direct-input forms. "
        "Citation: Oddur Kjartansson, Supheakmungkol Sarin, Knot Pipatsrisawat, "
        "Martin Jansche, and Linne Ha, 'Crowd-Sourced Speech Corpora for Javanese, "
        "Sundanese, Sinhala, Nepali, and Bangla,' SLTU 2018."
    )
    return [
        {
            "source_id": GOOGLE_SOURCE_ID,
            "title": "google/language-resources Nepali pronunciation lexicon",
            "method": "nfc_devanagari_headword_extraction",
            "license": "CC-BY-4.0",
            "redistribution": "allowed",
            "sha256": google_source_sha256,
            "source_url": google_source_url,
            "project_url": GOOGLE_PROJECT_URL,
            "upstream_commit": google_commit,
            "path": "ne/data/lexicon.tsv",
            "license_url": GOOGLE_LICENSE_URL,
            "license_sha256": google_license_sha256,
            "copyright": "Copyright 2018 Google Inc.",
            "changes": "Spelling-column extraction, NFC normalization, and Devanagari letter/mark filtering with context-valid U+200C/U+200D retention; pronunciations omitted.",
            "license_notice": google_attribution + "\n\nFull CC BY 4.0 legalcode:\n" + google_license_text,
        },
        {
            "source_id": OPENSLR_SOURCE_ID,
            "title": "OpenSLR SLR54 Large Nepali ASR training data set transcripts",
            "method": "nfc_devanagari_deduplicated_prompt_token_frequency_extraction",
            "license": "CC-BY-SA-4.0",
            "redistribution": "allowed",
            "sha256": openslr_source_sha256,
            "source_url": OPENSLR_SOURCE_URL,
            "project_url": OPENSLR_PROJECT_URL,
            "path": "utt_spk_text.tsv",
            "license_url": OPENSLR_LICENSE_URL,
            "license_legalcode_url": OPENSLR_LEGALCODE_URL,
            "license_sha256": openslr_license_sha256,
            "copyright": "Copyright 2016, 2017, 2018 Google, Inc.",
            "changes": "Exact-prompt deduplication, transcript token extraction, NFC normalization, Devanagari letter/mark filtering with context-valid U+200C/U+200D retention, and log-scaled frequency ranking.",
            "citation": "Kjartansson, Sarin, Pipatsrisawat, Jansche, and Ha. Crowd-Sourced Speech Corpora for Javanese, Sundanese, Sinhala, Nepali, and Bangla. SLTU 2018.",
            "license_notice": openslr_attribution + "\n\nFull CC BY-SA 4.0 legalcode:\n" + openslr_license_text,
        },
    ]


def build_release_source(args: argparse.Namespace) -> dict[str, object]:
    if not SEMVER_RE.fullmatch(args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")
    if not COMMIT_RE.fullmatch(args.google_commit):
        raise AdapterError("Google commit must be 40 lowercase hexadecimal characters")
    if args.google_commit != GOOGLE_PINNED_COMMIT:
        raise AdapterError(
            f"Google commit must match audited pin {GOOGLE_PINNED_COMMIT}"
        )

    google_source_sha256 = _verify_pinned_file(
        args.google_lexicon,
        GOOGLE_LEXICON_SHA256,
        "Google Nepali lexicon",
    )
    openslr_source_sha256 = _verify_pinned_file(
        args.openslr_transcripts,
        OPENSLR_TRANSCRIPTS_SHA256,
        "OpenSLR54 transcripts",
    )
    google_license_text, google_license_sha256 = _read_license(
        args.google_license,
        "Attribution 4.0 International",
        "Google lexicon CC BY 4.0 legalcode",
    )
    openslr_license_text, openslr_license_sha256 = _read_license(
        args.openslr_license,
        "Attribution-ShareAlike 4.0 International",
        "OpenSLR54 CC BY-SA 4.0 legalcode",
    )

    google_tokens, google_stats = _load_google_lexicon(args.google_lexicon)
    openslr_counts, openslr_stats = _load_openslr_counts(args.openslr_transcripts)
    surfaces = sorted(google_tokens | set(openslr_counts))

    forms: list[dict[str, object]] = []
    google_only = 0
    openslr_only = 0
    both = 0
    for surface in surfaces:
        source_ids: list[str] = []
        if surface in google_tokens:
            source_ids.append(GOOGLE_SOURCE_ID)
        if surface in openslr_counts:
            source_ids.append(OPENSLR_SOURCE_ID)
        if len(source_ids) == 2:
            both += 1
        elif source_ids[0] == GOOGLE_SOURCE_ID:
            google_only += 1
        else:
            openslr_only += 1
        transcript_count = openslr_counts.get(surface, 0)
        google_bonus = GOOGLE_ATTESTATION_RANK_BONUS if surface in google_tokens else 0
        rank_score = google_bonus + round(
            OPENSLR_LOG_FREQUENCY_SCALE * math.log1p(transcript_count)
        )
        if rank_score >= 2**31:
            raise AdapterError(f"rank score exceeds signed int32 for {surface!r}")
        forms.append(
            {
                "form_id": _stable_form_id(surface),
                "surface": surface,
                "rank_score": rank_score,
                "source_ids": source_ids,
                "evidence": "attested",
            }
        )

    source_rows = _source_rows(
        args.google_commit,
        google_source_sha256,
        google_license_sha256,
        google_license_text,
        openslr_source_sha256,
        openslr_license_sha256,
        openslr_license_text,
    )
    pack = {
        "pack_id": PACK_ID,
        "language": "npi",
        "display_name": "Nepali",
        "variety": None,
        "output_script": "Deva",
        "region": "NP",
        "data_version": args.data_version,
        "max_suggestions": args.max_suggestions,
        "artifact_license": "CC-BY-SA-4.0",
        "allowed_format_characters": ["U+200C", "U+200D"],
    }
    report: dict[str, object] = {
        "adapter": "build_nepali_release_source",
        "adapter_version": 2,
        "pack_id": PACK_ID,
        "data_version": args.data_version,
        "artifact_license": "CC-BY-SA-4.0",
        "inputs": {
            GOOGLE_SOURCE_ID: {
                "sha256": google_source_sha256,
                "license_sha256": google_license_sha256,
                "upstream_commit": args.google_commit,
                "source_url": source_rows[0]["source_url"],
                "license_url": GOOGLE_LICENSE_URL,
            },
            OPENSLR_SOURCE_ID: {
                "sha256": openslr_source_sha256,
                "license_sha256": openslr_license_sha256,
                "source_url": OPENSLR_SOURCE_URL,
                "license_url": OPENSLR_LICENSE_URL,
            },
        },
        "counts": {
            "forms": len(forms),
            "google_only": google_only,
            "openslr_only": openslr_only,
            "both_sources": both,
            "alias_rows": 0,
        },
        "source_stats": {
            GOOGLE_SOURCE_ID: google_stats,
            OPENSLR_SOURCE_ID: openslr_stats,
        },
        "ranking": {
            "formula": "(1000 if google_attested else 0) + round(1000 * log1p(deduplicated_openslr54_token_count))",
            "google_attestation_bonus": GOOGLE_ATTESTATION_RANK_BONUS,
            "openslr_log_frequency_scale": OPENSLR_LOG_FREQUENCY_SCALE,
            "tie_break": "Unicode surface lexical order in the pack compiler",
        },
        "normalization": "NFC; surface starts with a Devanagari letter; Devanagari letter/mark categories; U+200C/U+200D only immediately after U+094D and before a Devanagari letter",
        "direct_only": True,
    }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "pack.json").write_text(
        _canonical_json(pack) + "\n",
        encoding="utf-8",
    )
    _write_jsonl(args.output / "sources.jsonl", source_rows)
    _write_jsonl(args.output / "forms.jsonl", forms)
    (args.output / "aliases.jsonl").write_text("", encoding="utf-8")
    (args.output / "adapter-report.json").write_text(
        _canonical_json(report) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the pinned, direct-only Nepali release-pack source tables."
    )
    parser.add_argument("--google-lexicon", type=Path, required=True)
    parser.add_argument("--google-license", type=Path, required=True)
    parser.add_argument("--google-commit", required=True)
    parser.add_argument("--openslr-transcripts", type=Path, required=True)
    parser.add_argument("--openslr-license", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--max-suggestions", type=int, default=8)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        report = build_release_source(args)
    except AdapterError as exc:
        parser.error(str(exc))
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
