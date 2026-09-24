#!/usr/bin/env python3
"""Build a research-only Sherpa Devanagari source from pinned verse text."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Iterable


PACK_ID = "xsr-Deva-NP"
SOURCE_ID = "xsr-bible-root"
MANIFEST_SHA256 = "9924c7c640129bdb486c11e634b790b43470a8af2dacac39709c9aa06e8a6dfe"
TREE_SHA256 = "8063ccc05fa92f56777dfe6dac0076eddcda590fcf3d3e1d06e6fad24bfb915c"
SOURCE_PREFIX = PurePosixPath(
    "/Volumes/TRANSCEND/bible_brain_nepal/xsr/XSRXSR_Sherpa"
)
EXPECTED_FILES = 260
EXPECTED_VERSES = 7_957
EXPECTED_OCCURRENCES = 184_136
EXPECTED_SURFACES = 6_835
RANK_SCORE = 1_000
JOINERS = frozenset("\u200c\u200d")


class AdapterError(ValueError):
    """The pinned Sherpa source does not satisfy the extraction contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows), encoding="utf-8"
    )


def _is_devanagari_letter(character: str) -> bool:
    return 0x0900 <= ord(character) <= 0x097F and unicodedata.category(
        character
    ).startswith("L")


def _is_token_character(character: str) -> bool:
    return (
        0x0900 <= ord(character) <= 0x097F
        and unicodedata.category(character)[0] in {"L", "M"}
    ) or character in JOINERS


def _tokens(text: str) -> Iterable[str]:
    current: list[str] = []
    for character in unicodedata.normalize("NFC", text):
        if _is_token_character(character):
            current.append(character)
        elif current:
            yield "".join(current)
            current.clear()
    if current:
        yield "".join(current)


def _token_rejection(token: str) -> str | None:
    if not any(_is_devanagari_letter(character) for character in token):
        return "no_devanagari_letter"
    if unicodedata.category(token[0]).startswith("M"):
        return "leading_mark"
    for index, character in enumerate(token):
        if character in JOINERS and not (
            index > 1
            and index + 1 < len(token)
            and token[index - 1] == "\u094d"
            and _is_devanagari_letter(token[index + 1])
        ):
            return "invalid_joiner_context"
    return None


def _relative_chapter_path(row: dict[str, object]) -> PurePosixPath:
    if (
        row.get("bible_id") != "XSRXSR"
        or row.get("fileset_id") != "XSRWBT"
        or row.get("fileset_type") != "text_plain"
        or row.get("status") != "downloaded"
        or not isinstance(row.get("book_id"), str)
        or not isinstance(row.get("chapter"), int)
        or row["chapter"] < 1
        or not isinstance(row.get("path"), str)
    ):
        raise AdapterError("Sherpa manifest row has invalid metadata")
    try:
        relative = PurePosixPath(row["path"]).relative_to(SOURCE_PREFIX)
    except ValueError as exc:
        raise AdapterError("Sherpa manifest chapter escapes pinned source root") from exc
    if (
        len(relative.parts) != 4
        or relative.parts[:2] != ("text", "XSRWBT")
        or relative.parts[2] != row["book_id"]
        or not re.fullmatch(r"B[0-9]{2}_[A-Z0-9]{3}_[0-9]{3}\.json", relative.name)
    ):
        raise AdapterError("Sherpa manifest chapter path violates pinned layout")
    return relative


def _read_regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AdapterError(f"missing regular Sherpa source file: {path}")
    return path.read_bytes()


def _extract(
    source_root: Path,
) -> tuple[Counter[str], dict[str, dict[str, object]], list[dict[str, object]], dict[str, object]]:
    if source_root.is_symlink() or not source_root.is_dir():
        raise AdapterError("Sherpa source root must be a regular directory")
    manifest_path = source_root / "metadata" / "text_manifest.jsonl"
    manifest_bytes = _read_regular_file(manifest_path)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != MANIFEST_SHA256:
        raise AdapterError("Sherpa manifest SHA-256 does not match pinned source")
    try:
        rows = [json.loads(line) for line in manifest_bytes.decode("utf-8").splitlines()]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"invalid Sherpa manifest JSONL: {exc}") from exc
    if len(rows) != EXPECTED_FILES or any(not isinstance(row, dict) for row in rows):
        raise AdapterError("Sherpa manifest row count or shape changed")

    counts: Counter[str] = Counter()
    first_reference: dict[str, dict[str, object]] = {}
    rejected: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    hashes: list[tuple[str, str]] = []
    seen_paths: set[PurePosixPath] = set()
    for row in rows:
        relative = _relative_chapter_path(row)
        if relative in seen_paths:
            raise AdapterError(f"duplicate Sherpa manifest path: {relative}")
        seen_paths.add(relative)
        path = source_root / Path(*relative.parts)
        raw = _read_regular_file(path)
        hashes.append((f"XSRXSR_Sherpa/{relative}", hashlib.sha256(raw).hexdigest()))
        stats["files"] += 1
        stats["file_bytes"] += len(raw)
        try:
            verses = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise AdapterError(f"invalid Sherpa chapter JSON at {relative}: {exc}") from exc
        if not isinstance(verses, list):
            raise AdapterError(f"Sherpa chapter is not a verse array: {relative}")
        for verse in verses:
            if (
                not isinstance(verse, dict)
                or verse.get("book_id") != row["book_id"]
                or verse.get("chapter") != row["chapter"]
                or not isinstance(verse.get("verse_start"), int)
                or not isinstance(verse.get("verse_end"), int)
                or not isinstance(verse.get("verse_text"), str)
            ):
                raise AdapterError(f"invalid Sherpa verse structure in {relative}")
            text = verse["verse_text"]
            stats["verses"] += 1
            stats["verse_chars"] += len(text)
            if unicodedata.normalize("NFC", text) != text:
                stats["verses_needing_nfc"] += 1
            reference = {
                "book_id": row["book_id"],
                "chapter": row["chapter"],
                "verse_start": verse["verse_start"],
            }
            for token in _tokens(text):
                stats["token_occurrences"] += 1
                reason = _token_rejection(token)
                if reason is not None:
                    stats["rejected_occurrences"] += 1
                    stats[f"rejected_{reason}"] += 1
                    rejected.append({"reference": reference, "token": token, "reason": reason})
                    continue
                counts[token] += 1
                first_reference.setdefault(token, reference)
                stats["accepted_occurrences"] += 1

    actual_paths = {
        PurePosixPath(path.relative_to(source_root).as_posix())
        for path in (source_root / "text" / "XSRWBT").rglob("*.json")
    }
    if actual_paths != seen_paths:
        raise AdapterError("Sherpa chapter tree differs from pinned manifest")
    tree_sha256 = hashlib.sha256(
        "".join(f"{path}\0{digest}\n" for path, digest in sorted(hashes)).encode("utf-8")
    ).hexdigest()
    if tree_sha256 != TREE_SHA256:
        raise AdapterError("Sherpa chapter tree SHA-256 does not match pinned source")
    stats["distinct_accepted_surfaces"] = len(counts)
    stats.setdefault("rejected_occurrences", 0)
    if (
        stats["verses"] != EXPECTED_VERSES
        or stats["accepted_occurrences"] != EXPECTED_OCCURRENCES
        or len(counts) != EXPECTED_SURFACES
        or stats["rejected_occurrences"] != 0
    ):
        raise AdapterError("Sherpa extracted verse/token counts differ from pinned source")
    provenance = {
        "chapter_tree_sha256": tree_sha256,
        "manifest_sha256": manifest_sha256,
        "stats": dict(sorted(stats.items())),
    }
    return counts, first_reference, rejected, provenance


def build_candidate_source(args: argparse.Namespace) -> dict[str, object]:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.data_version):
        raise AdapterError("data version must be semantic x.y.z")
    if not isinstance(args.max_suggestions, int) or not 1 <= args.max_suggestions <= 32:
        raise AdapterError("max suggestions must be an integer from 1 to 32")
    counts, references, rejected, provenance = _extract(args.source_root)
    source = {
        "source_id": SOURCE_ID,
        "title": "XSRXSR Sherpa XSRWBT Devanagari verse text",
        "method": "Pinned 260-chapter verse_text token extraction",
        "path": "XSRXSR_Sherpa/text/XSRWBT",
        "sha256": provenance["chapter_tree_sha256"],
        "license": "unknown",
        "redistribution": "unknown",
        "notes": "Religious-domain token occurrences are recorded but do not set keyboard rank.",
    }
    pack = {
        "pack_id": PACK_ID,
        "language": "xsr",
        "display_name": "Sherpa Candidate",
        "output_script": "Deva",
        "region": "NP",
        "data_version": args.data_version,
        "max_suggestions": args.max_suggestions,
        "surface_lookup_normalization": "NFC",
        "allowed_format_characters": ["U+200C", "U+200D"],
        "artifact_license": "LicenseRef-Internal",
        "variety": "XSRXSR source variety review pending",
    }
    forms = []
    evidence = []
    for index, surface in enumerate(sorted(counts), 1):
        form_id = f"xsr:bible:surface-{index:06d}"
        forms.append({
            "form_id": form_id,
            "surface": surface,
            "rank_score": RANK_SCORE,
            "source_ids": [SOURCE_ID],
            "evidence": "attested",
        })
        evidence.append({
            "form_id": form_id,
            "surface": surface,
            "occurrences": counts[surface],
            "first_reference": references[surface],
        })
    report = {
        "adapter": "build_sherpa_candidate_source",
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "adapter_version": 1,
        "claim_scope": "candidate_only_religious_domain_corpus",
        "pack_id": PACK_ID,
        "input": provenance,
        "normalization": "NFC; maximal Devanagari letter/mark tokens with valid conjunct joiners",
        "ranking": {"rank_score": RANK_SCORE, "policy": "uniform; verse counts are evidence only"},
        "aliases": {"rows": 0, "policy": "direct input only"},
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "pack.json").write_text(_canonical_json(pack) + "\n", encoding="utf-8")
    _write_jsonl(args.output / "sources.jsonl", [source])
    _write_jsonl(args.output / "forms.jsonl", forms)
    (args.output / "aliases.jsonl").write_text("", encoding="utf-8")
    _write_jsonl(args.output / "token-evidence.jsonl", evidence)
    _write_jsonl(args.output / "rejected-tokens.jsonl", rejected)
    (args.output / "adapter-report.json").write_text(
        _canonical_json(report) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-version", default="1.0.0")
    parser.add_argument("--max-suggestions", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        report = build_candidate_source(args)
    except AdapterError as exc:
        parser.error(str(exc))
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
