#!/usr/bin/env python3
"""Build deterministic Bantawa Devanagari candidates from the pinned IPA lexicon.

The canonical Bantawa dictionary stores Doornenbal-style scholarly headwords,
not Devanagari surfaces.  This adapter therefore requires the separately
pinned Bantawa Devanagari<->IPA bridge, converts each attested headword with
its best-effort ``ipa2deva`` direction, and verifies that the forward direction
returns either the exact headword or only the bridge's documented lossy
neutralizations.  Generated spelling collisions are retained as provenance
rows and merged by the NKP compiler; they are not guessed apart.

This is an internal direct-input source.  It intentionally emits no Roman
aliases: Doornenbal transcription is not a validated casual Roman keyboard.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType
from typing import Iterable


PACK_ID = "bap-Deva-NP"
DICTIONARY_SOURCE_ID = "bap-dictionary"
TRANSLITERATOR_SOURCE_ID = "bap-romanizer"
SOURCE_SHA256 = "a69917c00e7a8587f4a38458faf89c95fc9e5ac9cbe6cfb612383438bdf5ae12"
TRANSLITERATOR_SHA256 = "aa599191d86975b0dcae330592df48c609c8a37e400c850d4494945bc7d9b9d2"
EXPECTED_DATA_ROWS = 2_040
EXPECTED_FIELDS = (
    "lang",
    "headword",
    "pos",
    "conj",
    "en",
    "n_examples",
    "source",
)
EXPECTED_ROW_SOURCE = "doornenbal_2009_grammar_of_bantawa/AppendixC"
RANK_SCORE = 1_000
DEVA_RANGES = ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x11B00, 0x11B5F))
SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


class AdapterError(ValueError):
    """Raised when a pinned Bantawa input violates the adapter contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AdapterError(f"{label} is not a regular non-symbolic file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read {label} {path}: {exc}") from exc


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AdapterError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> object:
    raise AdapterError(f"non-finite JSON number {token!r} is not allowed")


def _parse_dictionary(encoded: bytes) -> list[dict[str, object]]:
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise AdapterError("Bantawa dictionary must not contain a UTF-8 BOM")
    if b"\r" in encoded:
        raise AdapterError("Bantawa dictionary must use LF line endings")
    if not encoded.endswith(b"\n"):
        raise AdapterError("Bantawa dictionary must end with LF")
    try:
        text = encoded.decode("utf-8")
    except UnicodeError as exc:
        raise AdapterError(f"Bantawa dictionary is not UTF-8: {exc}") from exc

    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line:
            raise AdapterError(f"Bantawa dictionary line {line_number} is blank")
        try:
            value = json.loads(
                line,
                object_pairs_hook=_strict_object,
                parse_constant=_reject_nonfinite,
                parse_float=lambda token: _finite_float(token, line_number),
            )
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"Bantawa dictionary line {line_number} is invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(value, dict):
            raise AdapterError(f"Bantawa dictionary line {line_number} must be an object")
        if tuple(value) != EXPECTED_FIELDS:
            raise AdapterError(
                f"Bantawa dictionary line {line_number} fields do not match the pinned order"
            )
        _validate_raw_row(value, line_number)
        rows.append(value)
    if len(rows) != EXPECTED_DATA_ROWS:
        raise AdapterError(
            f"Bantawa dictionary row count mismatch: expected {EXPECTED_DATA_ROWS}, got {len(rows)}"
        )
    return rows


def _finite_float(token: str, line_number: int) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise AdapterError(
            f"Bantawa dictionary line {line_number} has non-finite number {token!r}"
        )
    return value


def _validate_raw_row(row: dict[str, object], line_number: int) -> None:
    if row["lang"] != "bap":
        raise AdapterError(f"Bantawa dictionary line {line_number} lang must be 'bap'")
    for field in ("headword", "pos", "en"):
        if not isinstance(row[field], str):
            raise AdapterError(
                f"Bantawa dictionary line {line_number} {field} must be a string"
            )
    if not row["headword"]:
        raise AdapterError(f"Bantawa dictionary line {line_number} headword is blank")
    if not row["pos"]:
        raise AdapterError(f"Bantawa dictionary line {line_number} pos is blank")
    if row["conj"] is not None and not isinstance(row["conj"], str):
        raise AdapterError(
            f"Bantawa dictionary line {line_number} conj must be null or a string"
        )
    count = row["n_examples"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise AdapterError(
            f"Bantawa dictionary line {line_number} n_examples must be a non-negative integer"
        )
    if row["source"] != EXPECTED_ROW_SOURCE:
        raise AdapterError(
            f"Bantawa dictionary line {line_number} has an unexpected source"
        )
    for field, value in row.items():
        if isinstance(value, str):
            for character in value:
                if 0xD800 <= ord(character) <= 0xDFFF:
                    raise AdapterError(
                        f"Bantawa dictionary line {line_number} {field} has a surrogate"
                    )


def _load_transliterator(path: Path, encoded: bytes) -> ModuleType:
    digest = hashlib.sha256(encoded).hexdigest()
    if digest != TRANSLITERATOR_SHA256:
        raise AdapterError(
            "Bantawa transliterator SHA-256 mismatch: "
            f"expected {TRANSLITERATOR_SHA256}, got {digest}"
        )
    spec = importlib.util.spec_from_file_location("_nepa_bantawa_transliterator", path)
    if spec is None or spec.loader is None:
        raise AdapterError("cannot construct the Bantawa transliterator module")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - exact exception is upstream-defined
        raise AdapterError(f"cannot load the Bantawa transliterator: {exc}") from exc
    for name in ("ipa2deva", "deva2ipa"):
        if not callable(getattr(module, name, None)):
            raise AdapterError(f"Bantawa transliterator is missing callable {name}")
    loaded_path = getattr(module, "__file__", None)
    if not isinstance(loaded_path, str) or Path(loaded_path).resolve() != path.resolve():
        raise AdapterError("loaded Bantawa transliterator path does not match the pinned input")
    return module


def _normalize_lossy(headword: str) -> str:
    """Apply only neutralizations documented by the pinned bridge."""
    return (
        headword.replace("ʈʰ", "tʰ")
        .replace("ɖʰ", "dʰ")
        .replace("ʈ", "t")
        .replace("ɖ", "d")
        .replace("ɳ", "n")
        .replace("ʔ", "")
        .replace("ī", "i")
        .replace("ū", "u")
        .replace("ə", "a")
        .replace("ɨ", "a")
    )


def _is_devanagari(codepoint: int) -> bool:
    return any(start <= codepoint <= end for start, end in DEVA_RANGES)


def _validate_generated_surface(surface: str, line_number: int) -> None:
    if not surface:
        raise AdapterError(
            f"Bantawa dictionary line {line_number} generated an empty surface"
        )
    if unicodedata.normalize("NFC", surface) != surface:
        raise AdapterError(
            f"Bantawa dictionary line {line_number} generated a non-NFC surface"
        )
    has_letter = False
    for character in surface:
        codepoint = ord(character)
        category = unicodedata.category(character)
        if category in {"Cc", "Cf"}:
            raise AdapterError(
                f"Bantawa dictionary line {line_number} generated disallowed U+{codepoint:04X}"
            )
        if _is_devanagari(codepoint):
            if category.startswith("L"):
                has_letter = True
            continue
        if category[0] in {"N", "P", "Z"}:
            continue
        raise AdapterError(
            f"Bantawa dictionary line {line_number} generated outside-Devanagari U+{codepoint:04X}"
        )
    if not has_letter:
        raise AdapterError(
            f"Bantawa dictionary line {line_number} generated no Devanagari letter"
        )


def _build_forms(
    rows: list[dict[str, object]],
    transliterator: ModuleType,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    forms: list[dict[str, object]] = []
    surfaces_to_headwords: dict[str, set[str]] = defaultdict(set)
    stats: Counter[str] = Counter()
    for line_number, row in enumerate(rows, 1):
        headword = str(row["headword"])
        generated = transliterator.ipa2deva(headword)
        if not isinstance(generated, str):
            raise AdapterError(
                f"Bantawa dictionary line {line_number} ipa2deva did not return a string"
            )
        surface = unicodedata.normalize("NFC", generated)
        _validate_generated_surface(surface, line_number)
        back = transliterator.deva2ipa(surface)
        if not isinstance(back, str):
            raise AdapterError(
                f"Bantawa dictionary line {line_number} deva2ipa did not return a string"
            )
        if back == headword:
            stats["exact_roundtrip_rows"] += 1
        elif back == _normalize_lossy(headword):
            stats["accountable_lossy_roundtrip_rows"] += 1
        else:
            raise AdapterError(
                "Bantawa dictionary line "
                f"{line_number} has an unexplained round-trip: {headword!r} -> "
                f"{surface!r} -> {back!r}"
            )
        if unicodedata.normalize("NFC", headword) != headword:
            stats["non_nfc_input_headword_rows"] += 1
        surfaces_to_headwords[surface].add(headword)
        forms.append(
            {
                "evidence": "generated",
                "form_id": f"bap:doornenbal:line-{line_number:06d}",
                "rank_score": RANK_SCORE,
                "source_ids": [DICTIONARY_SOURCE_ID, TRANSLITERATOR_SOURCE_ID],
                "surface": surface,
            }
        )

    forms.sort(key=lambda row: (str(row["surface"]), str(row["form_id"])))
    collision_rows = [
        {
            "headwords": sorted(headwords),
            "surface": surface,
        }
        for surface, headwords in surfaces_to_headwords.items()
        if len(headwords) > 1
    ]
    collision_rows.sort(key=lambda row: str(row["surface"]))
    stats["rows"] = len(rows)
    stats["accepted_rows"] = len(forms)
    stats["distinct_input_headwords"] = len({str(row["headword"]) for row in rows})
    stats["distinct_generated_surfaces"] = len(surfaces_to_headwords)
    stats["duplicate_surface_rows"] = len(forms) - len(surfaces_to_headwords)
    stats["collision_surfaces_across_distinct_headwords"] = len(collision_rows)
    for key in (
        "exact_roundtrip_rows",
        "accountable_lossy_roundtrip_rows",
        "non_nfc_input_headword_rows",
    ):
        stats.setdefault(key, 0)
    return forms, {
        "collision_examples": collision_rows[:32],
        "collision_example_limit": 32,
        "stats": dict(sorted(stats.items())),
    }


def build_internal_source(args: argparse.Namespace) -> dict[str, object]:
    dictionary_bytes = _read_regular(args.dictionary_jsonl, "Bantawa dictionary")
    dictionary_sha256 = hashlib.sha256(dictionary_bytes).hexdigest()
    if dictionary_sha256 != SOURCE_SHA256:
        raise AdapterError(
            "Bantawa dictionary SHA-256 mismatch: "
            f"expected {SOURCE_SHA256}, got {dictionary_sha256}"
        )
    transliterator_bytes = _read_regular(
        args.transliterator_python,
        "Bantawa transliterator",
    )
    transliterator = _load_transliterator(args.transliterator_python, transliterator_bytes)
    if not SEMVER_RE.fullmatch(args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")

    rows = _parse_dictionary(dictionary_bytes)
    forms, measurement = _build_forms(rows, transliterator)
    transliterator_sha256 = hashlib.sha256(transliterator_bytes).hexdigest()
    sources = [
        {
            "license": "unknown",
            "method": "Pinned Doornenbal Appendix C structured JSONL headword field",
            "notes": "Attested scholarly Bantawa transcription; not a casual Roman alias source.",
            "path": "bantawa-english.dict.jsonl",
            "redistribution": "unknown",
            "sha256": dictionary_sha256,
            "source_id": DICTIONARY_SOURCE_ID,
            "title": "Doornenbal 2009 Grammar of Bantawa Appendix C word list",
        },
        {
            "license": "unknown",
            "method": (
                "Pinned deterministic ipa2deva conversion with exact-or-documented-lossy "
                "deva2ipa round-trip verification"
            ),
            "notes": "Best-effort generated orthography; community spelling review remains required.",
            "path": "bantawa_deva2ipa.py",
            "redistribution": "unknown",
            "sha256": transliterator_sha256,
            "source_id": TRANSLITERATOR_SOURCE_ID,
            "title": "Bantawa Devanagari and Doornenbal-IPA bridge",
        },
    ]
    pack = {
        "allowed_format_characters": [],
        "artifact_license": "LicenseRef-Internal",
        "data_version": args.data_version,
        "display_name": "Bantawa",
        "language": "bap",
        "max_suggestions": args.max_suggestions,
        "output_script": "Deva",
        "pack_id": PACK_ID,
        "region": "NP",
        "surface_lookup_normalization": "NFC",
        "variety": "Central Kiranti",
    }
    adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report: dict[str, object] = {
        "adapter": "build_bantawa_internal_source",
        "adapter_sha256": adapter_sha256,
        "adapter_version": 1,
        "aliases": {
            "policy": "none; scholarly transcription is not a casual Roman IME",
            "rows": 0,
        },
        "claim_scope": (
            "Internal generated Devanagari candidate surfaces; no native spelling, "
            "ranking-quality, or casual Roman-input approval"
        ),
        "conversion": {
            "lossy_neutralizations": [
                "retroflex_to_dental",
                "glottal_stop_omitted",
                "vowel_length_collapsed",
                "schwa_to_a",
                "high_central_vowel_to_a",
            ],
            "policy": "ipa2deva then NFC; require exact or documented-lossy deva2ipa round-trip",
            "transliterator_sha256": transliterator_sha256,
        },
        "data_version": args.data_version,
        "input": {
            "bytes": len(dictionary_bytes),
            "expected_data_rows": EXPECTED_DATA_ROWS,
            "path": "bantawa-english.dict.jsonl",
            "sha256": dictionary_sha256,
        },
        "measurement": measurement,
        "pack_id": PACK_ID,
        "ranking": {
            "rank_score": RANK_SCORE,
            "tie_break": "Unicode surface order, then pinned JSONL line ID",
        },
    }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "pack.json").write_text(_canonical_json(pack) + "\n", encoding="utf-8")
    _write_jsonl(args.output / "sources.jsonl", sources)
    _write_jsonl(args.output / "forms.jsonl", forms)
    (args.output / "aliases.jsonl").write_text("", encoding="utf-8")
    (args.output / "rejected-rows.jsonl").write_text("", encoding="utf-8")
    (args.output / "adapter-report.json").write_text(
        _canonical_json(report) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary-jsonl", type=Path, required=True)
    parser.add_argument("--transliterator-python", type=Path, required=True)
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
