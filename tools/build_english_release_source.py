#!/usr/bin/env python3
"""Build a deterministic English release source from pinned SCOWL lists.

The three vocabulary inputs are cumulative, deaccented US English word lists
generated at SCOWL sizes 35, 50, and 60. A separately pinned FrequencyWords
English 50k input ranks their intersection but can never add vocabulary. This
adapter intentionally preserves SCOWL casing. Lookup normalization belongs to
the compiler/runtime boundary rather than to the canonical surface data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import string
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


SOURCE_ID = "eng-scowl-us"
FREQUENCY_SOURCE_ID = "eng-frequencywords-2018"
TIERS = (35, 50, 60)
RANK_SCORE_BY_TIER = {35: 3000, 50: 2000, 60: 1000}
FREQUENCY_SCORE_SCALE = 1000
FREQUENCY_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/legalcode"
WORD_RE = re.compile(r"^[A-Za-z]+(?:'[A-Za-z]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")
FULL_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
README_CONTENT_LICENSE_RE = re.compile(
    r"\bcc[\s-]*by[\s-]*sa[\s-]*4\.0\s+for\s+content\b",
    re.IGNORECASE,
)
LEGALCODE_FAMILY = "creative commons attribution-sharealike 4.0 international public license"
ASCII_LOWER_TABLE = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
COMPOSITE_HASH_DOMAIN = b"nepa-keyboard:esdb-scowl-input-set:v1\0"
COMPOSITE_HASH_FRAMING = (
    "SHA-256(domain || concatenation of, for tiers 35/50/60 in order: "
    "uint16be(tier) || uint64be(filename_utf8_length) || filename_utf8 || "
    "uint64be(raw_content_length) || raw_content); domain bytes are recorded "
    "separately as hexadecimal"
)


class AdapterError(ValueError):
    """Raised when pinned SCOWL input cannot become a release source."""


@dataclass(frozen=True)
class TierInput:
    tier: int
    filename: str
    content: bytes
    words: frozenset[str]
    report: dict[str, object]
    rejected_rows: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class FrequencyInput:
    counts: dict[str, int]
    content: bytes
    report: dict[str, object]
    rejected_rows: tuple[dict[str, object], ...]


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def stable_form_id(surface: str) -> str:
    digest = hashlib.sha256(("eng\0" + surface).encode("utf-8")).hexdigest()[:20]
    return f"eng:{digest}"


def _validate_sha256(value: str, label: str) -> None:
    if not SHA256_RE.fullmatch(value):
        raise AdapterError(f"{label} must be 64 lowercase hexadecimal characters")


def _validate_https_url(value: str, label: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AdapterError(f"{label} must be an absolute HTTPS URL")


def _validate_pinned_source_url(value: str, upstream_commit: str) -> None:
    _validate_https_url(value, "--source-url")
    path_segments = [segment for segment in urlsplit(value).path.split("/") if segment]
    if upstream_commit not in path_segments:
        raise AdapterError("--source-url must contain --upstream-commit as a complete path segment")


def _validate_frequency_source_url(value: str, upstream_commit: str) -> None:
    _validate_https_url(value, "--frequency-source-url")
    path_segments = [segment for segment in urlsplit(value).path.split("/") if segment]
    lowered_segments = [segment.casefold() for segment in path_segments]
    if upstream_commit not in path_segments:
        raise AdapterError(
            "--frequency-source-url must contain --frequency-commit as a complete path segment"
        )
    repository_path = "/".join(lowered_segments)
    if "hermitdave/frequencywords" not in repository_path:
        raise AdapterError("--frequency-source-url must identify hermitdave/FrequencyWords")


def _read_pinned_utf8(
    path: Path,
    expected_sha256: str,
    label: str,
) -> tuple[bytes, str, str]:
    _validate_sha256(expected_sha256, f"--{label}-sha256")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read {label} input {path}: {exc}") from exc
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise AdapterError(
            f"{label} SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdapterError(f"{label} input is not valid UTF-8: {exc}") from exc
    return content, text, actual_sha256


def _rejection_reason(value: str) -> str | None:
    if not value:
        return "blank"
    if value != value.strip():
        return "surrounding_whitespace"
    if unicodedata.normalize("NFC", value) != value:
        return "non_nfc"
    if not value.isascii():
        return "non_ascii"
    if any(character.isspace() for character in value):
        return "embedded_whitespace"
    if any(character in string.punctuation and character != "'" for character in value):
        return "unsupported_punctuation"
    if any(not ("A" <= character <= "Z" or "a" <= character <= "z" or character == "'") for character in value):
        return "unsupported_character"
    if not WORD_RE.fullmatch(value):
        return "invalid_apostrophe_placement"
    return None


def _read_tier(tier: int, path: Path, expected_sha256: str) -> TierInput:
    _validate_sha256(expected_sha256, f"--size-{tier}-sha256")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read size-{tier} input {path}: {exc}") from exc
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise AdapterError(
            f"size-{tier} SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdapterError(f"size-{tier} input is not valid UTF-8: {exc}") from exc

    words: set[str] = set()
    rejected_rows: list[dict[str, object]] = []
    rejected_by_reason: Counter[str] = Counter()
    duplicate_rows = 0
    valid_rows = 0
    lines = text.splitlines()
    for line_number, value in enumerate(lines, 1):
        reason = _rejection_reason(value)
        if reason is not None:
            rejected_by_reason[reason] += 1
            rejected_rows.append({
                "line": line_number,
                "reason": reason,
                "tier": tier,
                "value": value,
            })
            continue
        valid_rows += 1
        if value in words:
            duplicate_rows += 1
        else:
            words.add(value)

    report: dict[str, object] = {
        "accepted_rows": valid_rows,
        "bytes": len(content),
        "duplicate_rows": duplicate_rows,
        "expected_sha256": expected_sha256,
        "filename": path.name,
        "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
        "rejected_rows": len(rejected_rows),
        "rows": len(lines),
        "sha256": actual_sha256,
        "tier": tier,
        "unique_words": len(words),
    }
    return TierInput(
        tier=tier,
        filename=path.name,
        content=content,
        words=frozenset(words),
        report=report,
        rejected_rows=tuple(rejected_rows),
    )


def _read_frequency(path: Path, expected_sha256: str) -> FrequencyInput:
    content, text, actual_sha256 = _read_pinned_utf8(
        path, expected_sha256, "frequency"
    )
    counts: dict[str, int] = {}
    rejected_rows: list[dict[str, object]] = []
    rejected_by_reason: Counter[str] = Counter()
    duplicate_rows = 0
    accepted_rows = 0
    lines = text.splitlines()
    for line_number, value in enumerate(lines, 1):
        reason: str | None = None
        key = ""
        count = 0
        if not value:
            reason = "blank"
        elif value != value.strip():
            reason = "surrounding_whitespace"
        else:
            fields = value.split()
            if len(fields) != 2:
                reason = "malformed_fields"
            else:
                key, encoded_count = fields
                key_reason = _rejection_reason(key)
                if key_reason is not None:
                    reason = f"key_{key_reason}"
                elif not encoded_count.isascii() or not encoded_count.isdecimal():
                    reason = "invalid_count"
                else:
                    count = int(encoded_count)
                    if count <= 0:
                        reason = "nonpositive_count"
        if reason is not None:
            rejected_by_reason[reason] += 1
            rejected_rows.append({
                "line": line_number,
                "reason": reason,
                "value": value,
            })
            continue

        accepted_rows += 1
        normalized_key = key.translate(ASCII_LOWER_TABLE)
        if normalized_key in counts:
            duplicate_rows += 1
            counts[normalized_key] += count
        else:
            counts[normalized_key] = count

    report: dict[str, object] = {
        "accepted_rows": accepted_rows,
        "bytes": len(content),
        "duplicate_rows_aggregated": duplicate_rows,
        "expected_sha256": expected_sha256,
        "filename": path.name,
        "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
        "rejected_rows": len(rejected_rows),
        "rows": len(lines),
        "sha256": actual_sha256,
        "unique_keys": len(counts),
    }
    return FrequencyInput(
        counts=counts,
        content=content,
        report=report,
        rejected_rows=tuple(rejected_rows),
    )


def _composite_sha256(inputs: list[TierInput]) -> str:
    digest = hashlib.sha256()
    digest.update(COMPOSITE_HASH_DOMAIN)
    for tier_input in inputs:
        filename = tier_input.filename.encode("utf-8")
        digest.update(tier_input.tier.to_bytes(2, "big"))
        digest.update(len(filename).to_bytes(8, "big"))
        digest.update(filename)
        digest.update(len(tier_input.content).to_bytes(8, "big"))
        digest.update(tier_input.content)
    return digest.hexdigest()


def _read_license_notice(path: Path) -> tuple[str, str]:
    try:
        content = path.read_bytes()
        notice = content.decode("utf-8").strip()
    except OSError as exc:
        raise AdapterError(f"cannot read license notice {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise AdapterError(f"license notice is not valid UTF-8: {exc}") from exc
    if not notice:
        raise AdapterError("license notice must not be empty")
    return notice, hashlib.sha256(content).hexdigest()


def _read_frequency_licensing(
    readme_path: Path,
    readme_expected_sha256: str,
    legalcode_path: Path,
) -> tuple[str, str, str, str]:
    _, readme, readme_sha256 = _read_pinned_utf8(
        readme_path, readme_expected_sha256, "frequency-readme"
    )
    if not README_CONTENT_LICENSE_RE.search(readme):
        raise AdapterError(
            "pinned FrequencyWords README must state CC-by-sa-4.0 for content"
        )
    try:
        legalcode_content = legalcode_path.read_bytes()
        legalcode = legalcode_content.decode("utf-8")
    except OSError as exc:
        raise AdapterError(f"cannot read CC-BY-SA legalcode {legalcode_path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise AdapterError(f"CC-BY-SA legalcode is not valid UTF-8: {exc}") from exc
    normalized_legalcode = " ".join(legalcode.casefold().split())
    if LEGALCODE_FAMILY not in normalized_legalcode:
        raise AdapterError(
            "legalcode file is not Creative Commons Attribution-ShareAlike 4.0 International"
        )
    return (
        readme,
        readme_sha256,
        legalcode,
        hashlib.sha256(legalcode_content).hexdigest(),
    )


def _frequency_license_notice(
    *,
    commit: str,
    source_url: str,
    readme: str,
    readme_sha256: str,
    legalcode: str,
    legalcode_sha256: str,
) -> str:
    readme_url = (
        "https://github.com/hermitdave/FrequencyWords/blob/"
        f"{commit}/README.md"
    )
    return "\n".join([
        "FrequencyWords / OpenSubtitles 2018 attribution",
        "",
        "Frequency ranking data is from hermitdave/FrequencyWords, English 50k (2018),",
        "generated from the tokenized OpenSubtitles2018 corpus. FrequencyWords identifies",
        "its generated content as CC-BY-SA-4.0.",
        f"Pinned data source: {source_url}",
        f"Pinned FrequencyWords README: {readme_url}",
        f"Pinned FrequencyWords README SHA-256: {readme_sha256}",
        f"Upstream commit: {commit}",
        "OpenSubtitles2018 source named by FrequencyWords:",
        "http://opus.nlpl.eu/OpenSubtitles2018.php",
        "License: Creative Commons Attribution-ShareAlike 4.0 International",
        f"Legal code: {FREQUENCY_LICENSE_URL}",
        f"Supplied legal code SHA-256: {legalcode_sha256}",
        "",
        "Changes by Nepa Keyboard:",
        "- Parsed positive integer token counts from the pinned English 50k list.",
        "- Filtered ranking keys to ASCII letters with optional internal straight apostrophes.",
        "- Normalized ranking keys with ASCII lowercase only.",
        "- Intersected ranking keys with the independently licensed ESDB vocabulary;",
        "  FrequencyWords entries never add candidate forms.",
        "- Converted matched counts to an additive score using",
        "  round(1000 * log1p(count)).",
        "- Repacked the resulting ranked intersection for offline keyboard lookup.",
        "The resulting English pack is distributed under CC-BY-SA-4.0.",
        "",
        "Pinned upstream README (verbatim):",
        "--- BEGIN FREQUENCYWORDS README ---",
        readme,
        "--- END FREQUENCYWORDS README ---",
        "",
        "CC-BY-SA-4.0 legal code (verbatim):",
        "--- BEGIN CC-BY-SA-4.0 LEGAL CODE ---",
        legalcode,
        "--- END CC-BY-SA-4.0 LEGAL CODE ---",
    ])


def _validate_args(args: argparse.Namespace) -> None:
    if not COMMIT_RE.fullmatch(args.upstream_commit):
        raise AdapterError("--upstream-commit must be 7 to 64 lowercase hexadecimal characters")
    _validate_pinned_source_url(args.source_url, args.upstream_commit)
    _validate_https_url(args.license_url, "--license-url")
    if not FULL_COMMIT_RE.fullmatch(args.frequency_commit):
        raise AdapterError(
            "--frequency-commit must be exactly 40 lowercase hexadecimal characters"
        )
    _validate_frequency_source_url(args.frequency_source_url, args.frequency_commit)
    if not SEMVER_RE.fullmatch(args.data_version):
        raise AdapterError("--data-version must be semantic x.y.z")
    if not 1 <= args.max_suggestions <= 32:
        raise AdapterError("--max-suggestions must be from 1 to 32")


def build_source(args: argparse.Namespace) -> dict[str, object]:
    """Create release compiler tables and return the adapter report."""
    _validate_args(args)
    tier_paths = {35: args.size_35, 50: args.size_50, 60: args.size_60}
    expected_hashes = {
        35: args.size_35_sha256,
        50: args.size_50_sha256,
        60: args.size_60_sha256,
    }
    inputs = [
        _read_tier(tier, tier_paths[tier], expected_hashes[tier])
        for tier in TIERS
    ]
    words_by_tier = {tier_input.tier: set(tier_input.words) for tier_input in inputs}
    missing_35_from_50 = sorted(words_by_tier[35] - words_by_tier[50])
    missing_50_from_60 = sorted(words_by_tier[50] - words_by_tier[60])
    if missing_35_from_50 or missing_50_from_60:
        details = []
        if missing_35_from_50:
            details.append(f"{len(missing_35_from_50)} size-35 words missing from size 50")
        if missing_50_from_60:
            details.append(f"{len(missing_50_from_60)} size-50 words missing from size 60")
        raise AdapterError("SCOWL inputs are not cumulative: " + "; ".join(details))
    if not words_by_tier[60]:
        raise AdapterError("SCOWL inputs contain no accepted words")

    first_tier_by_word: dict[str, int] = {}
    for tier in TIERS:
        for word in words_by_tier[tier]:
            first_tier_by_word.setdefault(word, tier)

    frequency = _read_frequency(args.frequency_file, args.frequency_sha256)
    readme, readme_sha256, legalcode, legalcode_sha256 = _read_frequency_licensing(
        args.frequency_readme,
        args.frequency_readme_sha256,
        args.frequency_legalcode_file,
    )
    frequency_notice = _frequency_license_notice(
        commit=args.frequency_commit,
        source_url=args.frequency_source_url,
        readme=readme,
        readme_sha256=readme_sha256,
        legalcode=legalcode,
        legalcode_sha256=legalcode_sha256,
    )
    matched_frequency_keys: set[str] = set()
    matched_frequency_forms = 0
    forms: list[dict[str, object]] = []
    for surface in sorted(first_tier_by_word):
        normalized_surface = surface.translate(ASCII_LOWER_TABLE)
        frequency_count = frequency.counts.get(normalized_surface)
        rank_score = RANK_SCORE_BY_TIER[first_tier_by_word[surface]]
        source_ids = [SOURCE_ID]
        if frequency_count is not None:
            rank_score += round(FREQUENCY_SCORE_SCALE * math.log1p(frequency_count))
            source_ids.append(FREQUENCY_SOURCE_ID)
            matched_frequency_keys.add(normalized_surface)
            matched_frequency_forms += 1
        forms.append({
            "evidence": "attested",
            "form_id": stable_form_id(surface),
            "rank_score": rank_score,
            "source_ids": source_ids,
            "surface": surface,
        })

    composite_sha256 = _composite_sha256(inputs)
    notice, notice_sha256 = _read_license_notice(args.license_notice_file)
    scowl_source = {
        "domains": ["general", "US English"],
        "license": args.license,
        "license_notice": notice,
        "license_url": args.license_url,
        "method": "SCOWL cumulative US deaccented word-list extraction at sizes 35/50/60",
        "modified": True,
        "notes": (
            "The source sha256 is a framed composite over the three pinned raw inputs; "
            "adapter-report.json records the framing and each raw digest. The ESDB component "
            "of rank scores encodes only the first cumulative size tier."
        ),
        "path": ",".join(tier_input.filename for tier_input in inputs),
        "redistribution": "allowed",
        "sha256": composite_sha256,
        "source_id": SOURCE_ID,
        "source_url": args.source_url,
        "title": "SCOWL/ESDB US English cumulative deaccented word lists",
        "upstream_commit": args.upstream_commit,
    }
    frequency_source = {
        "domains": ["subtitles", "general"],
        "license": "CC-BY-SA-4.0",
        "license_notice": frequency_notice,
        "license_url": FREQUENCY_LICENSE_URL,
        "method": "FrequencyWords English 50k token-count intersection for ranking only",
        "modified": True,
        "notes": (
            "Counts originate from the OpenSubtitles2018-derived FrequencyWords content. "
            "Ranking keys are ASCII-lowercased and intersected with ESDB; unmatched keys "
            "are excluded and cannot add forms. The pinned README and full legal code are "
            "embedded in license_notice."
        ),
        "path": args.frequency_file.name,
        "redistribution": "allowed",
        "sha256": str(frequency.report["sha256"]),
        "source_id": FREQUENCY_SOURCE_ID,
        "source_url": args.frequency_source_url,
        "title": "FrequencyWords English 50k (OpenSubtitles 2018)",
        "upstream_commit": args.frequency_commit,
    }
    pack = {
        "artifact_license": "CC-BY-SA-4.0",
        "data_version": args.data_version,
        "display_name": "English (US)",
        "language": "eng",
        "max_suggestions": args.max_suggestions,
        "output_script": "Latn",
        "pack_id": "eng-Latn-US",
        "region": "US",
        "surface_lookup_normalization": "NFC+ASCII-lower",
        "variety": "United States",
    }

    rejected_rows = [
        row
        for tier_input in inputs
        for row in tier_input.rejected_rows
    ]
    rejected_by_reason: Counter[str] = Counter(
        str(row["reason"]) for row in rejected_rows
    )
    new_words_by_tier = {
        "35": len(words_by_tier[35]),
        "50": len(words_by_tier[50] - words_by_tier[35]),
        "60": len(words_by_tier[60] - words_by_tier[50]),
    }
    unmatched_frequency_keys = set(frequency.counts) - matched_frequency_keys
    frequency_report = dict(frequency.report)
    frequency_report.update({
        "commit": args.frequency_commit,
        "forms_matched": matched_frequency_forms,
        "keys_matching_multiple_forms": (
            matched_frequency_forms - len(matched_frequency_keys)
        ),
        "keys_matched": len(matched_frequency_keys),
        "keys_not_in_esdb": len(unmatched_frequency_keys),
        "legalcode": {
            "family": "CC-BY-SA-4.0",
            "filename": args.frequency_legalcode_file.name,
            "sha256": legalcode_sha256,
            "url": FREQUENCY_LICENSE_URL,
        },
        "ranking_formula": (
            "SCOWL tier score + round(1000 * log1p(FrequencyWords count))"
        ),
        "readme": {
            "expected_sha256": args.frequency_readme_sha256,
            "filename": args.frequency_readme.name,
            "sha256": readme_sha256,
            "url": (
                "https://github.com/hermitdave/FrequencyWords/blob/"
                f"{args.frequency_commit}/README.md"
            ),
        },
        "rejected_row_details": list(frequency.rejected_rows),
        "source_url": args.frequency_source_url,
    })
    report: dict[str, object] = {
        "adapter": "build_english_release_source",
        "adapter_version": 2,
        "composite_sha256": composite_sha256,
        "composite_sha256_domain_hex": COMPOSITE_HASH_DOMAIN.hex(),
        "composite_sha256_framing": COMPOSITE_HASH_FRAMING,
        "counts": {
            "accepted_rows": sum(int(tier_input.report["accepted_rows"]) for tier_input in inputs),
            "aliases": 0,
            "duplicate_rows_within_tiers": sum(
                int(tier_input.report["duplicate_rows"]) for tier_input in inputs
            ),
            "forms": len(forms),
            "forms_ranked_by_frequency": matched_frequency_forms,
            "forms_without_frequency": len(forms) - matched_frequency_forms,
            "frequency_accepted_rows": int(frequency.report["accepted_rows"]),
            "frequency_keys_matched": len(matched_frequency_keys),
            "frequency_keys_not_in_esdb": len(unmatched_frequency_keys),
            "frequency_rejected_rows": int(frequency.report["rejected_rows"]),
            "frequency_rows": int(frequency.report["rows"]),
            "frequency_unique_keys": len(frequency.counts),
            "input_rows": sum(int(tier_input.report["rows"]) for tier_input in inputs),
            "membership_counts": {
                "35_50_60": len(words_by_tier[35]),
                "50_60": len(words_by_tier[50] - words_by_tier[35]),
                "60": len(words_by_tier[60] - words_by_tier[50]),
            },
            "new_words_by_tier": new_words_by_tier,
            "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
            "rejected_rows": len(rejected_rows),
            "unique_words_by_tier": {
                str(tier): len(words_by_tier[tier]) for tier in TIERS
            },
        },
        "filters": {
            "accepted_shape": "ASCII letters with optional internal straight apostrophes",
            "canonical_casing": "preserved",
            "frequency_keys": "same accepted shape plus ASCII-lower normalization",
            "normalization": "NFC-strict",
        },
        "frequency": frequency_report,
        "inputs": [tier_input.report for tier_input in inputs],
        "scowl_license_notice": {
            "filename": args.license_notice_file.name,
            "sha256": notice_sha256,
        },
        "pack_id": pack["pack_id"],
        "rank_scores_by_first_tier": {
            str(tier): RANK_SCORE_BY_TIER[tier] for tier in TIERS
        },
        "ranking_formula": {
            "frequency_bonus": "round(1000 * log1p(count))",
            "frequency_scale": FREQUENCY_SCORE_SCALE,
            "total": "tier_score + frequency_bonus when matched; otherwise tier_score",
        },
        "rejected_rows": rejected_rows,
        "source_ids": [SOURCE_ID, FREQUENCY_SOURCE_ID],
        "upstream_commit": args.upstream_commit,
    }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "pack.json").write_text(canonical_json(pack) + "\n", encoding="utf-8")
    write_jsonl(args.output / "sources.jsonl", [scowl_source, frequency_source])
    write_jsonl(args.output / "forms.jsonl", forms)
    write_jsonl(args.output / "aliases.jsonl", [])
    (args.output / "adapter-report.json").write_text(
        canonical_json(report) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build eng-Latn-US release tables from pinned SCOWL vocabulary and "
            "pinned FrequencyWords ranking data."
        )
    )
    for tier in TIERS:
        parser.add_argument(f"--size-{tier}", type=Path, required=True)
        parser.add_argument(f"--size-{tier}-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upstream-commit", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--license-url", required=True)
    parser.add_argument("--license-notice-file", type=Path, required=True)
    parser.add_argument("--license", default="SCOWL/ESDB word-list license")
    parser.add_argument("--frequency-file", type=Path, required=True)
    parser.add_argument("--frequency-sha256", required=True)
    parser.add_argument("--frequency-commit", required=True)
    parser.add_argument("--frequency-source-url", required=True)
    parser.add_argument("--frequency-readme", type=Path, required=True)
    parser.add_argument("--frequency-readme-sha256", required=True)
    parser.add_argument("--frequency-legalcode-file", type=Path, required=True)
    parser.add_argument("--data-version", default="0.1.0")
    parser.add_argument("--max-suggestions", type=int, default=8)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        report = build_source(args)
    except AdapterError as exc:
        parser.error(str(exc))
    print(canonical_json({
        "composite_sha256": report["composite_sha256"],
        "counts": report["counts"],
        "pack_id": report["pack_id"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
