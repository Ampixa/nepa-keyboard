#!/usr/bin/env python3
"""Add redistribution-safe Roman aliases to the pinned Nepali release source.

The adapter deliberately has a narrow input contract:

* the already-audited direct Nepali v2 source directory is copied unchanged;
* the pinned Aksharantar Nepali archive contributes only ``AK-Freq`` and
  ``Wikidata`` training rows whose native form already exists in that source;
* ``IndicCorp`` rows remain excluded because Aksharantar's dataset card says
  that AI4Bharat does not own the underlying extracted text; and
* the pinned Google pronunciation lexicon contributes bounded, project-owned
  phoneme-to-ASCII aliases.

Validation and test members are hashed and counted but never parsed into pack
aliases.  They remain held out for tuning and final evaluation respectively.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from tools import generate_indicxlit_nepali_aliases as indicxlit


PACK_ID = "npi-Deva-NP"
GOOGLE_SOURCE_ID = "google-language-resources-ne-lexicon"
AKSHARANTAR_FREQ_SOURCE_ID = "aksharantar-nep-ak-freq"
AKSHARANTAR_WIKIDATA_SOURCE_ID = "aksharantar-nep-wikidata"
INDICXLIT_SOURCE_ID = "indicxlit-indic-en-v1.0"

AKSHARANTAR_COMMIT = "e418c1fc928d9f5393af33268472cf20c1891be8"
AKSHARANTAR_ARCHIVE_SHA256 = (
    "8bdcc5957d701ea36b63c00c713b43bc30902774b70736737d480e77929de92c"
)
AKSHARANTAR_CARD_SHA256 = (
    "1846b06a04bbec6b7b4c0bd0cda3c62a0a8c050b7d69927f5dd23a98d3e8daeb"
)
AKSHARANTAR_ARCHIVE_URL = (
    "https://huggingface.co/datasets/ai4bharat/Aksharantar/resolve/"
    f"{AKSHARANTAR_COMMIT}/nep.zip"
)
AKSHARANTAR_CARD_URL = (
    "https://huggingface.co/datasets/ai4bharat/Aksharantar/blob/"
    f"{AKSHARANTAR_COMMIT}/README.md"
)
AKSHARANTAR_PROJECT_URL = "https://github.com/AI4Bharat/IndicXlit"
AKSHARANTAR_CITATION = (
    "Madhani, Parthan, Bedekar, NC, Khapra, Kunchukuttan, Kumar, and Khapra. "
    "Aksharantar: Open Indic-language Transliteration datasets and models for "
    "the Next Billion Users. Findings of EMNLP 2023; arXiv:2205.03018."
)

AKSHARANTAR_MEMBER_SHA256 = {
    "nep_train.json": "55f6ca38b30c6fab0b5b8a11eefd2bb2be3cbce633c93a3b03215ec5675810b4",
    "nep_valid.json": "9bc1c65df08c5f41eb61ffeaf631bf1bc3820c64ef71ae54b4868c5ac3ea9be7",
    "nep_test.json": "172c759fcbb9faeda0a23765ccd12ad0520fb535a05dca42dd9c9923ee5f554e",
}
AKSHARANTAR_MEMBER_ROWS = {
    "nep_train.json": 2_397_414,
    "nep_valid.json": 2_804,
    "nep_test.json": 4_101,
}

DIRECT_SOURCE_SHA256 = {
    "pack.json": "c355bf664afb372ed2e73a0eed167d7a37e9c3aa08ea0004a5624d1d45203310",
    "sources.jsonl": "4c98035d3f446959436f7b77c21256bb7474c5797a0e3585f65b17eefea3b073",
    "forms.jsonl": "1ea9db6637c1332e57cb2c5a437cdf3da13c6a166723196e1680902eb7bcf7c2",
    "aliases.jsonl": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "adapter-report.json": "ca10c2f0b26ac65c0c1c23a6ba8de0d11d65bdb50f3128a8343438767631ae43",
}
DIRECT_FORM_COUNT = 80_969

GOOGLE_LEXICON_SHA256 = (
    "a9f616db4ecc35ecde4e519e1438c5501d8574b3623d43370fb0089a31ea8a83"
)
CC_BY_4_LEGALCODE_SHA256 = (
    "9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411"
)
CC0_1_LEGALCODE_SHA256 = (
    "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499"
)
CC_BY_4_LEGALCODE_URL = "https://creativecommons.org/licenses/by/4.0/legalcode"
CC0_1_LEGALCODE_URL = "https://creativecommons.org/publicdomain/zero/1.0/legalcode"

SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ASCII_ALIAS_RE = re.compile(r"^[a-z]+$")
DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")

# Google language-resources uses an ASCII phoneme inventory.  This table is a
# project-owned rendering from that inventory to ordinary Nepali phone typing.
# It is intentionally finite: a new upstream phone fails the build and requires
# review rather than silently passing through into a release alias.
PHONE_TO_ROMAN = {
    "aaj": "ai",
    "aajn": "ain",
    "aan": "an",
    "aa": "a",
    "aaw": "au",
    "aawn": "aun",
    "ax": "a",
    "axj": "ai",
    "axjn": "ain",
    "axn": "an",
    "axw": "au",
    "axwn": "aun",
    "b": "b",
    "bh": "bh",
    "d": "d",
    "dd": "d",
    "ddh": "dh",
    "dh": "dh",
    "e": "e",
    "en": "en",
    "ew": "eu",
    "g": "g",
    "gh": "gh",
    "h": "h",
    "i": "i",
    "in": "in",
    "jh": "j",
    "jhh": "jh",
    "k": "k",
    "kh": "kh",
    "l": "l",
    "m": "m",
    "n": "n",
    "ng": "ng",
    "nn": "n",
    "o": "o",
    "oj": "oi",
    "ojn": "oin",
    "ow": "ou",
    "own": "oun",
    "p": "p",
    "ph": "ph",
    "r": "r",
    "s": "s",
    "t": "t",
    "th": "th",
    "ts": "ch",
    "tsh": "chh",
    "tt": "t",
    "tth": "th",
    "u": "u",
    "un": "un",
    "w": "w",
    "y": "y",
}

SAFE_AKSHARANTAR_SOURCES = {
    "AK-Freq": {
        "source_id": AKSHARANTAR_FREQ_SOURCE_ID,
        "evidence": "attested",
        "license": "CC-BY-4.0",
        "license_url": CC_BY_4_LEGALCODE_URL,
        "rank_delta": 0,
        "scheme": "aksharantar_ak_freq_attested",
    },
    "Wikidata": {
        "source_id": AKSHARANTAR_WIKIDATA_SOURCE_ID,
        "evidence": "induced",
        "license": "CC0-1.0",
        "license_url": CC0_1_LEGALCODE_URL,
        "rank_delta": -200,
        "scheme": "aksharantar_wikidata_pair",
    },
}
EXCLUDED_AKSHARANTAR_SOURCES = {
    "IndicCorp": (
        "Excluded from the release candidate: the Aksharantar card licenses its "
        "packaging under CC0 but states that AI4Bharat does not own the underlying "
        "extracted text."
    )
}


class RomanAdapterError(ValueError):
    """Raised when an input cannot safely produce Roman release aliases."""


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
        raise RomanAdapterError(f"missing required input: {path}") from exc
    return digest.hexdigest()


def _verify_file(path: Path, expected: str, label: str) -> str:
    actual = _sha256_file(path)
    if actual != expected:
        raise RomanAdapterError(
            f"{label} SHA-256 mismatch: expected {expected}, got {actual}"
        )
    return actual


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RomanAdapterError(f"missing {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RomanAdapterError(f"invalid JSON in {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RomanAdapterError(f"{label} must contain one JSON object")
    return value


def _read_jsonl(path: Path, label: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        handle = path.open(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RomanAdapterError(f"missing {label}: {path}") from exc
    with handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RomanAdapterError(
                    f"invalid JSON at {label}:{line_number}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise RomanAdapterError(
                    f"expected an object at {label}:{line_number}"
                )
            rows.append(row)
    return rows


def _read_pinned_text(
    path: Path,
    expected_sha256: str,
    required_phrases: tuple[str, ...],
    label: str,
) -> tuple[str, str]:
    actual = _verify_file(path, expected_sha256, label)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RomanAdapterError(f"{label} is not UTF-8: {path}") from exc
    for phrase in required_phrases:
        if phrase not in text:
            raise RomanAdapterError(f"{label} does not contain {phrase!r}")
    return text.strip(), actual


def _verify_direct_source(
    source_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, dict[str, object]]]:
    for filename, expected in DIRECT_SOURCE_SHA256.items():
        _verify_file(source_dir / filename, expected, f"direct source {filename}")

    if (source_dir / "aliases.jsonl").read_bytes():
        raise RomanAdapterError("pinned direct source aliases.jsonl must be empty")

    pack = _read_json(source_dir / "pack.json", "direct pack.json")
    if pack.get("pack_id") != PACK_ID:
        raise RomanAdapterError(f"direct pack must have pack_id={PACK_ID}")
    if pack.get("output_script") != "Deva" or pack.get("language") != "npi":
        raise RomanAdapterError("direct pack must be Nepali Devanagari")
    if pack.get("artifact_license") != "CC-BY-SA-4.0":
        raise RomanAdapterError(
            "direct pack must preserve artifact_license=CC-BY-SA-4.0"
        )

    report = _read_json(source_dir / "adapter-report.json", "direct adapter report")
    if report.get("direct_only") is not True:
        raise RomanAdapterError("direct adapter report must declare direct_only=true")

    forms = _read_jsonl(source_dir / "forms.jsonl", "direct forms.jsonl")
    if len(forms) != DIRECT_FORM_COUNT:
        raise RomanAdapterError(
            f"direct forms count mismatch: expected {DIRECT_FORM_COUNT}, got {len(forms)}"
        )
    by_surface: dict[str, dict[str, object]] = {}
    form_ids: set[str] = set()
    for line_number, form in enumerate(forms, 1):
        surface = form.get("surface")
        form_id = form.get("form_id")
        if not isinstance(surface, str) or not surface:
            raise RomanAdapterError(
                f"direct forms.jsonl:{line_number}: invalid surface"
            )
        if not isinstance(form_id, str) or not form_id:
            raise RomanAdapterError(
                f"direct forms.jsonl:{line_number}: invalid form_id"
            )
        if unicodedata.normalize("NFC", surface) != surface:
            raise RomanAdapterError(
                f"direct forms.jsonl:{line_number}: surface is not NFC"
            )
        if surface in by_surface or form_id in form_ids:
            raise RomanAdapterError(
                f"direct forms.jsonl:{line_number}: duplicate surface or form_id"
            )
        by_surface[surface] = form
        form_ids.add(form_id)

    sources = _read_jsonl(source_dir / "sources.jsonl", "direct sources.jsonl")
    by_source: dict[str, dict[str, object]] = {}
    for row in sources:
        source_id = row.get("source_id")
        if not isinstance(source_id, str) or source_id in by_source:
            raise RomanAdapterError("direct source rows must have unique source_id values")
        by_source[source_id] = row
    if GOOGLE_SOURCE_ID not in by_source:
        raise RomanAdapterError(f"direct sources must contain {GOOGLE_SOURCE_ID}")
    return pack, sources, by_surface


def _normalize_alias(value: object, location: str) -> str:
    if not isinstance(value, str):
        raise RomanAdapterError(f"{location}: english word must be a string")
    alias = unicodedata.normalize("NFC", value).lower()
    if not ASCII_ALIAS_RE.fullmatch(alias):
        raise RomanAdapterError(
            f"{location}: alias must contain only lowercase ASCII letters: {value!r}"
        )
    return alias


def _validate_aksharantar_row(
    row: object,
    member: str,
    line_number: int,
) -> dict[str, object]:
    location = f"{member}:{line_number}"
    if not isinstance(row, dict):
        raise RomanAdapterError(f"{location}: expected a JSON object")
    required = {"unique_identifier", "native word", "english word", "source"}
    missing = sorted(required - row.keys())
    if missing:
        raise RomanAdapterError(f"{location}: missing fields: {', '.join(missing)}")
    identifier = row.get("unique_identifier")
    native = row.get("native word")
    source = row.get("source")
    if not isinstance(identifier, str) or not re.fullmatch(r"nep[0-9]+", identifier):
        raise RomanAdapterError(f"{location}: invalid unique_identifier")
    if not isinstance(native, str) or not native or not DEVANAGARI_RE.search(native):
        raise RomanAdapterError(f"{location}: invalid native word")
    if not isinstance(source, str) or not source:
        raise RomanAdapterError(f"{location}: invalid source")
    _normalize_alias(row.get("english word"), location)
    return row


def _hash_and_count_member(handle: object) -> tuple[str, int]:
    digest = hashlib.sha256()
    rows = 0
    for raw in handle:  # type: ignore[union-attr]
        digest.update(raw)
        rows += 1
    return digest.hexdigest(), rows


def _verify_member_result(member: str, digest: str, rows: int) -> None:
    expected_digest = AKSHARANTAR_MEMBER_SHA256[member]
    expected_rows = AKSHARANTAR_MEMBER_ROWS[member]
    if digest != expected_digest:
        raise RomanAdapterError(
            f"{member} SHA-256 mismatch: expected {expected_digest}, got {digest}"
        )
    if rows != expected_rows:
        raise RomanAdapterError(
            f"{member} row count mismatch: expected {expected_rows}, got {rows}"
        )


def _load_aksharantar_training_aliases(
    archive_path: Path,
    forms: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    expected_names = set(AKSHARANTAR_MEMBER_SHA256)
    aliases: list[dict[str, object]] = []
    stats = Counter()
    source_stats = Counter()
    member_evidence: dict[str, dict[str, object]] = {}

    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        raise RomanAdapterError(f"invalid Aksharantar archive: {archive_path}") from exc

    with archive:
        actual_names = set(archive.namelist())
        if actual_names != expected_names:
            raise RomanAdapterError(
                "Aksharantar archive members mismatch: expected "
                f"{sorted(expected_names)}, got {sorted(actual_names)}"
            )

        for member in ("nep_valid.json", "nep_test.json"):
            with archive.open(member) as handle:
                digest, rows = _hash_and_count_member(handle)
            _verify_member_result(member, digest, rows)
            member_evidence[member] = {
                "sha256": digest,
                "rows": rows,
                "used_in_pack": False,
            }

        member = "nep_train.json"
        digest = hashlib.sha256()
        rows = 0
        seen_identifiers: set[str] = set()
        with archive.open(member) as handle:
            for raw in handle:
                digest.update(raw)
                rows += 1
                try:
                    row = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RomanAdapterError(
                        f"invalid JSON at {member}:{rows}: {exc}"
                    ) from exc
                row = _validate_aksharantar_row(row, member, rows)
                identifier = str(row["unique_identifier"])
                if identifier in seen_identifiers:
                    raise RomanAdapterError(
                        f"{member}:{rows}: duplicate unique_identifier {identifier}"
                    )
                seen_identifiers.add(identifier)
                source = str(row["source"])
                source_stats[source] += 1
                native = unicodedata.normalize("NFC", str(row["native word"]))
                if native not in forms:
                    stats["excluded_missing_direct_form"] += 1
                    continue
                if source in EXCLUDED_AKSHARANTAR_SOURCES:
                    stats[f"excluded_rights_{source}"] += 1
                    continue
                config = SAFE_AKSHARANTAR_SOURCES.get(source)
                if config is None:
                    raise RomanAdapterError(
                        f"{member}:{rows}: unreviewed Aksharantar source {source!r}"
                    )
                alias = _normalize_alias(row["english word"], f"{member}:{rows}")
                aliases.append(
                    {
                        "alias": alias,
                        "form_id": forms[native]["form_id"],
                        "rank_delta": config["rank_delta"],
                        "scheme": config["scheme"],
                        "source_ids": [config["source_id"]],
                        "evidence": config["evidence"],
                    }
                )
                stats[f"included_{source}"] += 1

        train_digest = digest.hexdigest()
        _verify_member_result(member, train_digest, rows)
        member_evidence[member] = {
            "sha256": train_digest,
            "rows": rows,
            "used_in_pack": True,
            "allowed_source_labels": sorted(SAFE_AKSHARANTAR_SOURCES),
            "excluded_source_labels": sorted(EXCLUDED_AKSHARANTAR_SOURCES),
        }

    stats["included_rows"] = len(aliases)
    return aliases, {
        "members": member_evidence,
        "training_source_rows": dict(sorted(source_stats.items())),
        "join_stats": dict(sorted(stats.items())),
    }


def _phoneme_primary(tokens: tuple[str, ...], location: str) -> str:
    unknown = sorted(set(tokens) - PHONE_TO_ROMAN.keys())
    if unknown:
        raise RomanAdapterError(
            f"{location}: unreviewed Google phonemes: {', '.join(unknown)}"
        )
    alias = "".join(PHONE_TO_ROMAN[token] for token in tokens)
    if not ASCII_ALIAS_RE.fullmatch(alias):
        raise RomanAdapterError(f"{location}: phoneme alias is not lowercase ASCII")
    return alias


def _collapse_geminates(value: str) -> str:
    return re.sub(r"([a-z])\1+", r"\1", value)


def _phoneme_alias_variants(
    surface: str,
    tokens: tuple[str, ...],
    location: str,
) -> list[tuple[str, str, int]]:
    primary = _phoneme_primary(tokens, location)
    candidates: list[tuple[str, str, int]] = [
        (primary, "google_ne_phoneme_primary_v1", -50),
    ]

    long_parts = [
        "aa" if token == "aa" else PHONE_TO_ROMAN[token]
        for token in tokens
    ]
    candidates.append(("".join(long_parts), "google_ne_phoneme_long_aa_v1", -110))
    candidates.append(
        (_collapse_geminates(primary), "google_ne_phoneme_degeminated_v1", -120)
    )
    if primary.endswith("a") and len(primary) > 1:
        candidates.append(
            (primary[:-1], "google_ne_phoneme_terminal_schwa_drop_v1", -130)
        )
    else:
        candidates.append(
            (primary + "a", "google_ne_phoneme_terminal_schwa_add_v1", -160)
        )
    if "फ" in surface and "ph" in primary:
        candidates.append(
            (primary.replace("ph", "f"), "google_ne_phoneme_ph_to_f_v1", -100)
        )
    if any(character in surface for character in "शष") and "s" in primary:
        candidates.append(
            (primary.replace("s", "sh"), "google_ne_phoneme_s_to_sh_v1", -110)
        )
    if "व" in surface and "b" in primary:
        candidates.append(
            (primary.replace("b", "w"), "google_ne_phoneme_b_to_w_v1", -140)
        )
        candidates.append(
            (primary.replace("b", "v"), "google_ne_phoneme_b_to_v_v1", -150)
        )
    if "क्ष" in surface:
        candidates.append(
            (
                primary.replace("kchhy", "ksh").replace("kchh", "ksh"),
                "google_ne_phoneme_ksh_v1",
                -90,
            )
        )
    if "श्र" in surface and "sr" in primary:
        candidates.append(
            (primary.replace("sr", "shr", 1), "google_ne_phoneme_shr_v1", -90)
        )

    result: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for alias, scheme, rank_delta in candidates:
        if alias in seen or not ASCII_ALIAS_RE.fullmatch(alias):
            continue
        seen.add(alias)
        result.append((alias, scheme, rank_delta))
    return result


def _load_google_phoneme_aliases(
    path: Path,
    forms: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    aliases: list[dict[str, object]] = []
    stats = Counter()
    seen_pairs: set[tuple[str, tuple[str, ...]]] = set()
    try:
        handle = path.open(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise RomanAdapterError(f"missing Google Nepali lexicon: {path}") from exc
    with handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip("\r\n")
            if not line or line.lstrip().startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 2:
                raise RomanAdapterError(
                    f"Google lexicon:{line_number}: expected tab-separated spelling and phonemes"
                )
            surface = unicodedata.normalize("NFC", fields[0].strip())
            if surface not in forms:
                stats["excluded_missing_direct_form"] += 1
                continue
            tokens = tuple(token for token in fields[1].split() if token != ".")
            if not tokens:
                stats["excluded_empty_phonemes"] += 1
                continue
            pair = (surface, tokens)
            if pair in seen_pairs:
                stats["duplicate_surface_phonemes"] += 1
                continue
            seen_pairs.add(pair)
            variants = _phoneme_alias_variants(
                surface, tokens, f"Google lexicon:{line_number}"
            )
            for alias, scheme, rank_delta in variants:
                aliases.append(
                    {
                        "alias": alias,
                        "form_id": forms[surface]["form_id"],
                        "rank_delta": rank_delta,
                        "scheme": scheme,
                        "source_ids": [GOOGLE_SOURCE_ID],
                        "evidence": "generated",
                    }
                )
                stats[f"scheme_{scheme}"] += 1
            stats["included_pronunciations"] += 1
    stats["alias_rows"] = len(aliases)
    stats["surfaces_with_pronunciations"] = len({pair[0] for pair in seen_pairs})
    return aliases, dict(sorted(stats.items()))


def _aksharantar_source_rows(
    archive_sha256: str,
    card_text: str,
    card_sha256: str,
    cc_by_text: str,
    cc_by_sha256: str,
    cc0_text: str,
    cc0_sha256: str,
) -> list[dict[str, object]]:
    common = {
        "sha256": archive_sha256,
        "source_url": AKSHARANTAR_ARCHIVE_URL,
        "project_url": AKSHARANTAR_PROJECT_URL,
        "upstream_commit": AKSHARANTAR_COMMIT,
        "path": "nep_train.json",
        "citation": AKSHARANTAR_CITATION,
        "modified": True,
    }
    card_excerpt = (
        "Pinned dataset-card SHA-256: "
        f"{card_sha256}. The card assigns manually collected data to CC BY and "
        "mined/existing-source packaging to CC0; it also states that AI4Bharat "
        "does not own the text from which mined data was extracted."
    )
    return [
        {
            **common,
            "source_id": AKSHARANTAR_FREQ_SOURCE_ID,
            "title": "Aksharantar Nepali AK-Freq manually collected transliterations",
            "method": "training_split_exact_native_form_join_ak_freq_only",
            "license": "CC-BY-4.0",
            "redistribution": "allowed",
            "license_url": CC_BY_4_LEGALCODE_URL,
            "license_sha256": cc_by_sha256,
            "copyright": "AI4Bharat and Aksharantar contributors",
            "changes": "Kept only nep_train.json AK-Freq rows whose NFC native word exactly matches a pinned direct-pack form; validation, test, and IndicCorp rows excluded.",
            "license_notice": (
                "Aksharantar by Madhani et al. / AI4Bharat, pinned at dataset "
                f"commit {AKSHARANTAR_COMMIT}. {card_excerpt}\n\n"
                "Pinned dataset card:\n"
                + card_text
                + "\n\nFull CC BY 4.0 legalcode:\n"
                + cc_by_text
            ),
        },
        {
            **common,
            "source_id": AKSHARANTAR_WIKIDATA_SOURCE_ID,
            "title": "Aksharantar Nepali Wikidata transliteration pairs",
            "method": "training_split_exact_native_form_join_wikidata_only",
            "license": "CC0-1.0",
            "redistribution": "allowed",
            "license_url": CC0_1_LEGALCODE_URL,
            "license_sha256": cc0_sha256,
            "copyright": "Wikidata contributors; Aksharantar packaging by AI4Bharat",
            "changes": "Kept only nep_train.json Wikidata rows whose NFC native word exactly matches a pinned direct-pack form; validation, test, and IndicCorp rows excluded.",
            "license_notice": (
                "Aksharantar by Madhani et al. / AI4Bharat, pinned at dataset "
                f"commit {AKSHARANTAR_COMMIT}; source label Wikidata. "
                f"{card_excerpt}\n\nPinned dataset card:\n"
                + card_text
                + "\n\nFull CC0 1.0 legalcode:\n"
                + cc0_text
            ),
        },
    ]


def _update_google_source_notice(sources: list[dict[str, object]]) -> None:
    matches = [row for row in sources if row.get("source_id") == GOOGLE_SOURCE_ID]
    if len(matches) != 1:
        raise RomanAdapterError(f"expected exactly one {GOOGLE_SOURCE_ID} source row")
    source = matches[0]
    method = source.get("method")
    changes = source.get("changes")
    notice = source.get("license_notice")
    if not all(isinstance(value, str) for value in (method, changes, notice)):
        raise RomanAdapterError("Google direct source row lacks auditable text fields")
    omission = "and omits the pronunciations."
    if omission not in str(notice):
        raise RomanAdapterError(
            "Google direct source notice no longer contains the audited pronunciation omission"
        )
    source["method"] = str(method) + "+bounded_phoneme_to_roman_alias_generation_v1"
    source["changes"] = (
        str(changes)
        + " The pronunciation column is additionally rendered through the finite "
        "project-owned PHONE_TO_ROMAN v1 table and bounded reviewed variants."
    )
    source["license_notice"] = str(notice).replace(
        omission,
        "and uses the pronunciation column through a finite, project-owned "
        "phoneme-to-Roman v1 rendering for bounded keyboard aliases.",
    )


def _alias_summary(aliases: list[dict[str, object]]) -> dict[str, object]:
    targets: dict[str, set[str]] = defaultdict(set)
    schemes = Counter()
    evidence = Counter()
    sources = Counter()
    exact_rows: set[tuple[object, ...]] = set()
    duplicate_rows = 0
    for row in aliases:
        key = (
            row["alias"],
            row["form_id"],
            row["rank_delta"],
            row["scheme"],
            tuple(row["source_ids"]),
            row["evidence"],
        )
        if key in exact_rows:
            duplicate_rows += 1
            continue
        exact_rows.add(key)
        targets[str(row["alias"])].add(str(row["form_id"]))
        schemes[str(row["scheme"])] += 1
        evidence[str(row["evidence"])] += 1
        for source_id in row["source_ids"]:  # type: ignore[union-attr]
            sources[str(source_id)] += 1
    collisions = {alias: values for alias, values in targets.items() if len(values) > 1}
    return {
        "rows": len(aliases),
        "exact_duplicate_rows": duplicate_rows,
        "unique_alias_keys": len(targets),
        "colliding_alias_keys": len(collisions),
        "maximum_targets_per_alias": max((len(values) for values in targets.values()), default=0),
        "schemes": dict(sorted(schemes.items())),
        "evidence": dict(sorted(evidence.items())),
        "source_rows": dict(sorted(sources.items())),
    }


def _dedupe_exact_alias_rows(
    aliases: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    result: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    removed = 0
    for row in aliases:
        key = (
            row["alias"],
            row["form_id"],
            row["rank_delta"],
            row["scheme"],
            tuple(row["source_ids"]),
            row["evidence"],
        )
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        result.append(row)
    return result, removed


def _indicxlit_semantic_manifest_sha256(manifest: dict[str, object]) -> str:
    """Hash release-relevant generation evidence, excluding Fairseq wall time.

    Fairseq writes per-example ``W-*`` timing records into its stdout. Those
    records change across otherwise identical CPU runs and therefore change
    the raw-output hash, while the hypotheses and generated aliases remain
    byte-identical. The exact run manifests stay preserved as build evidence;
    the deterministic release-source report binds only the semantic manifest.
    """

    semantic = json.loads(_canonical_json(manifest))
    outputs = semantic.get("outputs")
    if isinstance(outputs, dict):
        outputs.pop("fairseq_output_sha256", None)
    return hashlib.sha256(_canonical_json(semantic).encode("utf-8")).hexdigest()


def _load_indicxlit_aliases(
    aliases_path: Path,
    manifest_path: Path,
    license_path: Path,
    forms: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    license_sha256 = _verify_file(
        license_path,
        indicxlit.INDICXLIT_LICENSE_SHA256,
        "IndicXlit MIT license",
    )
    license_text = license_path.read_text(encoding="utf-8")
    if "MIT License" not in license_text or "Copyright (c) 2022 AI4Bhārat" not in license_text:
        raise RomanAdapterError("IndicXlit license lacks the audited MIT notice")

    manifest = _read_json(manifest_path, "IndicXlit alias manifest")
    if manifest.get("generator") != "generate_indicxlit_nepali_aliases":
        raise RomanAdapterError("IndicXlit manifest has the wrong generator")
    if manifest.get("generator_version") != indicxlit.GENERATOR_VERSION:
        raise RomanAdapterError("IndicXlit manifest has an unsupported generator version")
    if manifest.get("pack_id") != PACK_ID:
        raise RomanAdapterError(f"IndicXlit manifest must have pack_id={PACK_ID}")
    if manifest.get("evaluation_data_consumed") is not False:
        raise RomanAdapterError(
            "IndicXlit manifest must declare evaluation_data_consumed=false"
        )
    inputs = manifest.get("inputs")
    outputs = manifest.get("outputs")
    decoding = manifest.get("decoding")
    if not all(isinstance(value, dict) for value in (inputs, outputs, decoding)):
        raise RomanAdapterError("IndicXlit manifest lacks input/output/decoding objects")
    direct_input = inputs.get("direct_forms")  # type: ignore[union-attr]
    model_input = inputs.get("model_archive")  # type: ignore[union-attr]
    project_input = inputs.get("indicxlit")  # type: ignore[union-attr]
    if not all(isinstance(value, dict) for value in (direct_input, model_input, project_input)):
        raise RomanAdapterError("IndicXlit manifest lacks pinned model inputs")
    expected_values = (
        (direct_input.get("sha256"), DIRECT_SOURCE_SHA256["forms.jsonl"], "direct forms"),
        (direct_input.get("rows"), len(forms), "direct form rows"),
        (
            model_input.get("sha256"),
            indicxlit.INDICXLIT_MODEL_ARCHIVE_SHA256,
            "model archive",
        ),
        (
            model_input.get("checkpoint_sha256"),
            indicxlit.INDICXLIT_CHECKPOINT_SHA256,
            "model checkpoint",
        ),
        (
            model_input.get("ne_dictionary_sha256"),
            indicxlit.INDICXLIT_NE_DICT_SHA256,
            "Nepali model dictionary",
        ),
        (
            model_input.get("en_dictionary_sha256"),
            indicxlit.INDICXLIT_EN_DICT_SHA256,
            "Roman model dictionary",
        ),
        (
            project_input.get("commit"),
            indicxlit.INDICXLIT_REPO_COMMIT,
            "IndicXlit commit",
        ),
        (project_input.get("license"), "MIT", "IndicXlit license label"),
        (
            project_input.get("license_sha256"),
            indicxlit.INDICXLIT_LICENSE_SHA256,
            "IndicXlit license hash",
        ),
        (
            project_input.get("lang_list_sha256"),
            indicxlit.INDICXLIT_LANG_LIST_SHA256,
            "IndicXlit language list",
        ),
    )
    for actual, expected, label in expected_values:
        if actual != expected:
            raise RomanAdapterError(
                f"IndicXlit manifest {label} mismatch: expected {expected}, got {actual}"
            )
    required_decoding = {
        "beam": 4,
        "nbest": 4,
        "cpu": True,
        "seed": 1,
        "fairseq_task": "translation_multi_simple_epoch",
        "source_language": "ne",
        "target_language": "en",
        "encoder_langtok": "src",
    }
    for key, expected in required_decoding.items():
        if decoding.get(key) != expected:  # type: ignore[union-attr]
            raise RomanAdapterError(
                f"IndicXlit manifest decoding {key} must be {expected!r}"
            )

    aliases_sha256 = _verify_file(
        aliases_path,
        str(outputs.get("aliases_sha256")),  # type: ignore[union-attr]
        "IndicXlit generated aliases",
    )
    fairseq_output_sha256 = outputs.get("fairseq_output_sha256")  # type: ignore[union-attr]
    if fairseq_output_sha256 is not None and (
        not isinstance(fairseq_output_sha256, str)
        or not SHA256_RE.fullmatch(fairseq_output_sha256)
    ):
        raise RomanAdapterError(
            "IndicXlit manifest fairseq_output_sha256 must be lowercase SHA-256"
        )
    semantic_manifest_sha256 = _indicxlit_semantic_manifest_sha256(manifest)
    rows: list[dict[str, object]] = []
    seen_by_form: dict[str, set[int]] = defaultdict(set)
    seen_alias_by_form: dict[str, set[str]] = defaultdict(set)
    try:
        handle = aliases_path.open(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RomanAdapterError(f"missing IndicXlit aliases: {aliases_path}") from exc
    with handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RomanAdapterError(
                    f"invalid IndicXlit alias JSON at line {line_number}: {exc}"
                ) from exc
            if not isinstance(row, dict) or set(row) != {
                "alias",
                "beam_rank",
                "form_id",
                "surface",
            }:
                raise RomanAdapterError(
                    f"IndicXlit aliases line {line_number} has an invalid row contract"
                )
            form_id = row["form_id"]
            surface = row["surface"]
            beam_rank = row["beam_rank"]
            if not isinstance(form_id, str) or not isinstance(surface, str):
                raise RomanAdapterError(
                    f"IndicXlit aliases line {line_number} lacks form identity"
                )
            form = forms.get(surface)
            if form is None or form.get("form_id") != form_id:
                raise RomanAdapterError(
                    f"IndicXlit aliases line {line_number} does not match a direct form"
                )
            if not isinstance(beam_rank, int) or not 1 <= beam_rank <= 4:
                raise RomanAdapterError(
                    f"IndicXlit aliases line {line_number} has invalid beam_rank"
                )
            alias = _normalize_alias(row["alias"], f"IndicXlit aliases:{line_number}")
            if beam_rank in seen_by_form[form_id] or alias in seen_alias_by_form[form_id]:
                raise RomanAdapterError(
                    f"IndicXlit aliases line {line_number} duplicates a form beam or alias"
                )
            seen_by_form[form_id].add(beam_rank)
            seen_alias_by_form[form_id].add(alias)
            rows.append(
                {
                    "alias": alias,
                    "form_id": form_id,
                    "rank_delta": -20 - (beam_rank - 1) * 50,
                    "scheme": f"indicxlit_indic_en_v1_beam_{beam_rank}",
                    "source_ids": [INDICXLIT_SOURCE_ID],
                    "evidence": "generated",
                }
            )
    manifest_counts = outputs.get("counts")  # type: ignore[union-attr]
    if not isinstance(manifest_counts, dict):
        raise RomanAdapterError("IndicXlit manifest lacks output counts")
    if manifest_counts.get("alias_rows") != len(rows):
        raise RomanAdapterError("IndicXlit alias row count differs from its manifest")
    if manifest_counts.get("forms") != len(forms):
        raise RomanAdapterError("IndicXlit form count differs from its manifest")
    if set(seen_by_form) != {str(form["form_id"]) for form in forms.values()}:
        raise RomanAdapterError("IndicXlit aliases do not cover every direct form")

    source_row = {
        "source_id": INDICXLIT_SOURCE_ID,
        "title": "AI4Bharat IndicXlit v1.0 native-to-Roman model",
        "method": "offline_cpu_beam4_native_to_roman_generation_over_pinned_direct_forms",
        "license": "MIT",
        "redistribution": "allowed",
        "sha256": indicxlit.INDICXLIT_MODEL_ARCHIVE_SHA256,
        "source_url": indicxlit.MODEL_ARCHIVE_URL,
        "project_url": indicxlit.MODEL_PROJECT_URL,
        "upstream_commit": indicxlit.INDICXLIT_REPO_COMMIT,
        "path": "transformer/indicxlit.pt",
        "license_url": indicxlit.MODEL_LICENSE_URL,
        "license_sha256": license_sha256,
        "copyright": "Copyright (c) 2022 AI4Bhārat",
        "changes": "Ran the pinned native-to-Roman checkpoint offline on CPU with beam=nbest=4, seed 1, and the exact pinned direct Nepali form list; retained lowercase ASCII outputs as generated aliases. No evaluation rows were input.",
        "citation": AKSHARANTAR_CITATION,
        "license_notice": (
            "AI4Bharat IndicXlit v1.0 native-to-Roman model at commit "
            f"{indicxlit.INDICXLIT_REPO_COMMIT}, used as an offline build-time "
            "generator. Generated aliases are labeled generated evidence.\n\n"
            "Full MIT license:\n"
            + license_text.strip()
        ),
        "modified": True,
    }
    stats: dict[str, object] = {
        "aliases_sha256": aliases_sha256,
        "semantic_manifest_sha256": semantic_manifest_sha256,
        "semantic_manifest_excludes": ["outputs.fairseq_output_sha256"],
        "rows": len(rows),
        "forms": len(seen_by_form),
        "beam_counts": dict(
            sorted(Counter(int(row["scheme"].rsplit("_", 1)[1]) for row in rows).items())
        ),
        "evaluation_data_consumed": False,
    }
    return rows, stats, source_row


def build_release_source(args: argparse.Namespace) -> dict[str, object]:
    if not SEMVER_RE.fullmatch(args.data_version):
        raise RomanAdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise RomanAdapterError("max suggestions must be an integer from 1 to 32")

    direct_pack, direct_sources, forms = _verify_direct_source(args.direct_source)
    archive_sha256 = _verify_file(
        args.aksharantar_archive,
        AKSHARANTAR_ARCHIVE_SHA256,
        "Aksharantar Nepali archive",
    )
    card_text, card_sha256 = _read_pinned_text(
        args.aksharantar_card,
        AKSHARANTAR_CARD_SHA256,
        (
            "Nepali (nep)",
            "Manually collected data: Released under CC-BY license.",
            "Mined dataset (from Samanantar and IndicCorp): Released under CC0 license.",
            "We do not own any of the text from which this data has been extracted.",
        ),
        "Aksharantar dataset card",
    )
    cc_by_text, cc_by_sha256 = _read_pinned_text(
        args.cc_by_license,
        CC_BY_4_LEGALCODE_SHA256,
        ("Attribution 4.0 International",),
        "CC BY 4.0 legalcode",
    )
    cc0_text, cc0_sha256 = _read_pinned_text(
        args.cc0_license,
        CC0_1_LEGALCODE_SHA256,
        ("CC0 1.0 Universal",),
        "CC0 1.0 legalcode",
    )
    google_sha256 = _verify_file(
        args.google_lexicon,
        GOOGLE_LEXICON_SHA256,
        "Google Nepali pronunciation lexicon",
    )

    aksharantar_aliases, split_report = _load_aksharantar_training_aliases(
        args.aksharantar_archive,
        forms,
    )
    google_aliases, google_stats = _load_google_phoneme_aliases(
        args.google_lexicon,
        forms,
    )
    model_paths = (
        getattr(args, "indicxlit_aliases", None),
        getattr(args, "indicxlit_manifest", None),
        getattr(args, "indicxlit_license", None),
    )
    if any(model_paths) and not all(model_paths):
        raise RomanAdapterError(
            "IndicXlit aliases, manifest, and license must be supplied together"
        )
    indicxlit_aliases: list[dict[str, object]] = []
    indicxlit_stats: dict[str, object] | None = None
    indicxlit_source: dict[str, object] | None = None
    if all(model_paths):
        indicxlit_aliases, indicxlit_stats, indicxlit_source = _load_indicxlit_aliases(
            model_paths[0],  # type: ignore[arg-type]
            model_paths[1],  # type: ignore[arg-type]
            model_paths[2],  # type: ignore[arg-type]
            forms,
        )
    aliases, removed_exact_duplicates = _dedupe_exact_alias_rows(
        aksharantar_aliases + google_aliases + indicxlit_aliases
    )
    aliases.sort(
        key=lambda row: (
            str(row["alias"]),
            str(row["form_id"]),
            -int(row["rank_delta"]),
            str(row["scheme"]),
            tuple(row["source_ids"]),  # type: ignore[arg-type]
        )
    )

    output_sources = [dict(row) for row in direct_sources]
    _update_google_source_notice(output_sources)
    output_sources.extend(
        _aksharantar_source_rows(
            archive_sha256,
            card_text,
            card_sha256,
            cc_by_text,
            cc_by_sha256,
            cc0_text,
            cc0_sha256,
        )
    )
    if indicxlit_source is not None:
        output_sources.append(indicxlit_source)
    output_sources.sort(key=lambda row: str(row["source_id"]))

    output_pack = dict(direct_pack)
    output_pack["data_version"] = args.data_version
    output_pack["max_suggestions"] = args.max_suggestions
    if output_pack.get("artifact_license") != "CC-BY-SA-4.0":
        raise RomanAdapterError("combined pack must preserve CC-BY-SA-4.0")

    report: dict[str, object] = {
        "adapter": "build_nepali_roman_release_source",
        "adapter_version": 2,
        "pack_id": PACK_ID,
        "data_version": args.data_version,
        "artifact_license": "CC-BY-SA-4.0",
        "inputs": {
            "direct_source": {
                "files": dict(sorted(DIRECT_SOURCE_SHA256.items())),
                "forms": len(forms),
            },
            "aksharantar": {
                "archive_sha256": archive_sha256,
                "card_sha256": card_sha256,
                "upstream_commit": AKSHARANTAR_COMMIT,
                "archive_url": AKSHARANTAR_ARCHIVE_URL,
                "card_url": AKSHARANTAR_CARD_URL,
            },
            "google_pronunciation_lexicon": {
                "sha256": google_sha256,
                "source_id": GOOGLE_SOURCE_ID,
            },
            "licenses": {
                "CC-BY-4.0": cc_by_sha256,
                "CC0-1.0": cc0_sha256,
            },
        },
        "split_contract": split_report,
        "google_phoneme_aliases": google_stats,
        "indicxlit_aliases": indicxlit_stats,
        "aliases": _alias_summary(aliases),
        "rights_decisions": {
            "included_aksharantar_sources": sorted(SAFE_AKSHARANTAR_SOURCES),
            "excluded_aksharantar_sources": EXCLUDED_AKSHARANTAR_SOURCES,
            "development_split_used_in_pack": False,
            "test_split_used_in_pack": False,
            "indicxlit_model_aliases_included": indicxlit_stats is not None,
        },
        "exact_duplicate_alias_rows_removed": removed_exact_duplicates,
        "normalization": "NFC native exact join; lowercase ASCII [a-z]+ aliases",
    }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "pack.json").write_text(
        _canonical_json(output_pack) + "\n",
        encoding="utf-8",
    )
    _write_jsonl(args.output / "sources.jsonl", output_sources)
    shutil.copyfile(args.direct_source / "forms.jsonl", args.output / "forms.jsonl")
    _write_jsonl(args.output / "aliases.jsonl", aliases)
    (args.output / "adapter-report.json").write_text(
        _canonical_json(report) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a pinned Nepali release source with safe Aksharantar training "
            "aliases and bounded Google-phoneme aliases."
        )
    )
    parser.add_argument("--direct-source", type=Path, required=True)
    parser.add_argument("--aksharantar-archive", type=Path, required=True)
    parser.add_argument("--aksharantar-card", type=Path, required=True)
    parser.add_argument("--google-lexicon", type=Path, required=True)
    parser.add_argument("--cc-by-license", type=Path, required=True)
    parser.add_argument("--cc0-license", type=Path, required=True)
    parser.add_argument("--indicxlit-aliases", type=Path)
    parser.add_argument("--indicxlit-manifest", type=Path)
    parser.add_argument("--indicxlit-license", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--max-suggestions", type=int, default=8)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        report = build_release_source(args)
    except RomanAdapterError as exc:
        parser.error(str(exc))
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
