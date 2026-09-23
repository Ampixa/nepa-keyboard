#!/usr/bin/env python3
"""Build a deterministic Nepali vocabulary table from a pinned Wikipedia dump.

This build-host tool reads only namespace-zero pages from the official Nepali
Wikipedia pages/articles XML dump. It does not read transliteration validation
or test data and it does not grant the generated vocabulary shipping authority.
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as etree
from collections import Counter
from pathlib import Path

from tools import build_nepali_release_source as direct_adapter


GENERATOR_VERSION = 2
DUMP_DATE = "20260701"
DUMP_FILENAME = "newiki-20260701-pages-articles.xml.bz2"
DUMP_URL = f"https://dumps.wikimedia.org/newiki/{DUMP_DATE}/{DUMP_FILENAME}"
DUMP_SHA1 = "551fbbbadedf3bcb179b15d6d1c1917b5ec1a80e"
DUMP_SHA256 = "d3a5f01e5cbfd63c5a31b47531cbb36002f7c2630ac051e940997d38e0eb7c1d"
DUMP_BYTES = 54_288_881
DUMP_LICENSE_INFO_URL = "https://dumps.wikimedia.org/legal.html"
DUMP_LICENSE_INFO_SHA256 = (
    "104242365285791c1d60d61b2ec8eac34e5c4b6a74ae5fdca9996a52f9cd3714"
)
DUMP_LICENSE_INFO_BYTES = 6_744
WIKIMEDIA_TERMS_REVISION = 554_823
WIKIMEDIA_TERMS_URL = (
    "https://foundation.wikimedia.org/w/index.php?"
    "title=Policy%3ATerms_of_Use&oldid=554823&printable=yes"
)
WIKIMEDIA_TERMS_SHA256 = (
    "d3bf66f44649e785df8234cf7923b1823d2db0032641ff35d831219d012754cc"
)
WIKIMEDIA_TERMS_BYTES = 153_827
LICENSE_ID = "CC-BY-SA-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/legalcode.txt"
LICENSE_SHA256 = "28a9529c7d0bb4dc51f4bf5c116a3d16ef247a052f7591466768ddf563fd1cf5"
LICENSE_BYTES = 20_138
SHIPPING_GATE = "WIKIMEDIA_ATTRIBUTION_REVIEW_REQUIRED"


class WikipediaVocabularyError(ValueError):
    """Raised when the pinned dump or generated vocabulary is invalid."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _file_hashes(path: Path, label: str = "Wikipedia dump") -> tuple[str, str, int]:
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    total = 0
    try:
        handle = path.open("rb")
    except FileNotFoundError as exc:
        raise WikipediaVocabularyError(f"missing {label}: {path}") from exc
    with handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(block)
            sha1.update(block)
            sha256.update(block)
    return sha1.hexdigest(), sha256.hexdigest(), total


def _verified_legal_document(
    path: Path,
    expected_sha256: str,
    expected_bytes: int,
    required_phrase: str,
    label: str,
) -> dict[str, object]:
    _sha1, sha256, size = _file_hashes(path, label)
    if (sha256, size) != (expected_sha256, expected_bytes):
        raise WikipediaVocabularyError(
            f"{label} pin mismatch: expected sha256={expected_sha256}, "
            f"bytes={expected_bytes}; got sha256={sha256}, bytes={size}"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise WikipediaVocabularyError(f"{label} is not UTF-8: {path}") from exc
    if required_phrase not in text:
        raise WikipediaVocabularyError(
            f"{label} lacks required phrase {required_phrase!r}: {path}"
        )
    return {"bytes": size, "sha256": sha256}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: etree.Element, name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == name:
            return child.text
    return None


def _revision_text(page: etree.Element) -> str | None:
    for child in page:
        if _local_name(child.tag) != "revision":
            continue
        return _child_text(child, "text")
    return None


def _revision_id(page: etree.Element) -> str | None:
    for child in page:
        if _local_name(child.tag) != "revision":
            continue
        return _child_text(child, "id")
    return None


def _positive_id(value: str | None, label: str) -> int:
    try:
        parsed = int(value or "")
    except ValueError as exc:
        raise WikipediaVocabularyError(f"invalid {label}: {value!r}") from exc
    if parsed < 1 or str(parsed) != value:
        raise WikipediaVocabularyError(f"invalid {label}: {value!r}")
    return parsed


def _load_counts(
    path: Path,
) -> tuple[Counter[str], dict[str, int], list[dict[str, object]]]:
    counts: Counter[str] = Counter()
    stats: Counter[str] = Counter()
    attribution_pages: list[dict[str, object]] = []
    page_ids: set[int] = set()
    revision_ids: set[int] = set()
    try:
        compressed = bz2.open(path, "rb")
    except OSError as exc:
        raise WikipediaVocabularyError(f"cannot open Wikipedia dump: {path}") from exc
    try:
        with compressed:
            for _event, element in etree.iterparse(compressed, events=("end",)):
                if _local_name(element.tag) != "page":
                    continue
                stats["pages_seen"] += 1
                namespace = _child_text(element, "ns")
                if namespace != "0":
                    stats["non_main_namespace_pages_skipped"] += 1
                    element.clear()
                    continue
                stats["main_namespace_pages"] += 1
                title = _child_text(element, "title") or ""
                if not title:
                    raise WikipediaVocabularyError("main-namespace page has no title")
                page_id = _positive_id(_child_text(element, "id"), "page ID")
                revision_id = _positive_id(_revision_id(element), "revision ID")
                if page_id in page_ids:
                    raise WikipediaVocabularyError(f"duplicate page ID: {page_id}")
                if revision_id in revision_ids:
                    raise WikipediaVocabularyError(
                        f"duplicate revision ID: {revision_id}"
                    )
                page_ids.add(page_id)
                revision_ids.add(revision_id)
                attribution_pages.append(
                    {
                        "page_id": page_id,
                        "page_url": f"https://ne.wikipedia.org/?curid={page_id}",
                        "revision_id": revision_id,
                        "revision_url": (
                            "https://ne.wikipedia.org/w/index.php?"
                            f"oldid={revision_id}"
                        ),
                        "title": title,
                    }
                )
                text = _revision_text(element) or ""
                if not text:
                    stats["main_namespace_pages_without_text"] += 1
                for field, value in (("title", title), ("text", text)):
                    tokens = direct_adapter._extract_transcript_tokens(value, stats)
                    counts.update(tokens)
                    stats[f"{field}_token_occurrences"] += len(tokens)
                element.clear()
    except (OSError, EOFError, etree.ParseError) as exc:
        raise WikipediaVocabularyError(f"invalid Wikipedia XML dump: {exc}") from exc
    direct_adapter._ensure_quality_stats(stats)
    stats["token_occurrences"] = sum(counts.values())
    stats["unique_tokens"] = len(counts)
    if not counts:
        raise WikipediaVocabularyError("Wikipedia dump produced no Nepali tokens")
    attribution_pages.sort(key=lambda row: (int(row["page_id"]), str(row["title"])))
    if len(attribution_pages) != stats["main_namespace_pages"]:
        raise WikipediaVocabularyError("attribution index does not cover every source page")
    return counts, dict(sorted(stats.items())), attribution_pages


def _write_vocabulary(path: Path, counts: Counter[str]) -> str:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for rank, (surface, count) in enumerate(ordered, 1):
            encoded = (
                _canonical_json({"count": count, "rank": rank, "surface": surface})
                + "\n"
            ).encode("utf-8")
            handle.write(encoded)
            digest.update(encoded)
    return digest.hexdigest()


def _write_attribution_pages(path: Path, rows: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for row in rows:
            encoded = (_canonical_json(row) + "\n").encode("utf-8")
            handle.write(encoded)
            digest.update(encoded)
    return digest.hexdigest()


def build(args: argparse.Namespace) -> dict[str, object]:
    if os.path.lexists(args.output_dir):
        raise WikipediaVocabularyError(
            f"output path already exists; refusing to overwrite evidence: {args.output_dir}"
        )
    sha1, sha256, size = _file_hashes(args.dump)
    if (sha1, sha256, size) != (DUMP_SHA1, DUMP_SHA256, DUMP_BYTES):
        raise WikipediaVocabularyError(
            "Wikipedia dump pin mismatch: expected "
            f"sha1={DUMP_SHA1}, sha256={DUMP_SHA256}, bytes={DUMP_BYTES}; "
            f"got sha1={sha1}, sha256={sha256}, bytes={size}"
        )
    legal_documents = {
        "dump_license_information": {
            **_verified_legal_document(
                args.dump_license,
                DUMP_LICENSE_INFO_SHA256,
                DUMP_LICENSE_INFO_BYTES,
                "Attribution-Share-Alike 4.0",
                "Wikimedia dump license information",
            ),
            "filename": "dumps-legal.html",
            "source_url": DUMP_LICENSE_INFO_URL,
        },
        "terms_of_use": {
            **_verified_legal_document(
                args.terms,
                WIKIMEDIA_TERMS_SHA256,
                WIKIMEDIA_TERMS_BYTES,
                "CC BY-SA 4.0",
                "Wikimedia Terms of Use",
            ),
            "filename": f"wikimedia-terms-of-use-oldid-{WIKIMEDIA_TERMS_REVISION}.html",
            "revision": WIKIMEDIA_TERMS_REVISION,
            "source_url": WIKIMEDIA_TERMS_URL,
        },
        "cc_by_sa_legalcode": {
            **_verified_legal_document(
                args.cc_by_sa_license,
                LICENSE_SHA256,
                LICENSE_BYTES,
                "Attribution-ShareAlike 4.0 International",
                "CC BY-SA 4.0 legal code",
            ),
            "filename": "cc-by-sa-4.0-legalcode.txt",
            "source_url": LICENSE_URL,
        },
    }
    counts, stats, attribution_pages = _load_counts(args.dump)

    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{args.output_dir.name}.staging-",
            dir=args.output_dir.parent,
        )
    )
    try:
        vocabulary_path = staging / "vocabulary.jsonl"
        vocabulary_sha256 = _write_vocabulary(vocabulary_path, counts)
        attribution_filename = "attribution-pages.jsonl"
        attribution_sha256 = _write_attribution_pages(
            staging / attribution_filename,
            attribution_pages,
        )
        manifest: dict[str, object] = {
            "generator": "build_nepali_wikipedia_vocabulary",
            "generator_version": GENERATOR_VERSION,
            "language": "npi",
            "output_script": "Deva",
            "input": {
                "dataset": "Nepali Wikipedia pages/articles dump",
                "date": DUMP_DATE,
                "filename": DUMP_FILENAME,
                "source_url": DUMP_URL,
                "bytes": size,
                "sha1": sha1,
                "sha256": sha256,
                "namespace": 0,
                "legal_documents": legal_documents,
            },
            "redistribution": {
                "license_id": LICENSE_ID,
                "license_url": LICENSE_URL,
                "source_license_information_url": DUMP_LICENSE_INFO_URL,
                "terms_url": WIKIMEDIA_TERMS_URL,
                "shipping_authority": False,
                "gate": SHIPPING_GATE,
                "attribution_index_included": True,
                "attribution_index_scope": "every namespace-zero source page",
                "reason": (
                    "Pinned legal texts and per-page attribution links are "
                    "preserved, but the keyboard notice and share-alike "
                    "mechanism has not yet passed release review."
                ),
            },
            "selection_contract": {
                "evaluation_data_consumed": False,
                "fields": ["title", "revision.text"],
                "ranking": "descending token occurrence count, then Unicode surface order",
                "tokenization": (
                    "NFC maximal Devanagari letter/mark runs with context-valid "
                    "U+200C/U+200D conjunct joiners"
                ),
            },
            "counts": stats,
            "output": {
                "filename": "vocabulary.jsonl",
                "rows": len(counts),
                "sha256": vocabulary_sha256,
                "attribution_pages": {
                    "filename": attribution_filename,
                    "rows": len(attribution_pages),
                    "sha256": attribution_sha256,
                },
            },
        }
        (staging / "manifest.json").write_text(
            _canonical_json(manifest) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, args.output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a pinned, evaluation-independent Nepali Wikipedia vocabulary."
    )
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--dump-license", type=Path, required=True)
    parser.add_argument("--terms", type=Path, required=True)
    parser.add_argument("--cc-by-sa-license", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    parser = build_parser()
    try:
        manifest = build(parser.parse_args())
    except WikipediaVocabularyError as exc:
        parser.error(str(exc))
    print(_canonical_json(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
