#!/usr/bin/env python3
"""Measure fixed-cutoff held-out coverage for a pinned Nepali vocabulary.

This evaluator reads the Aksharantar test member only after the direct and
Wikipedia vocabularies have been fixed and SHA-pinned.  It emits aggregate
counts, never target identities, and its output is forbidden as release input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

from tools import build_nepali_release_source as direct_adapter
from tools import build_nepali_roman_release_source as roman_adapter
from tools import build_nepali_wikipedia_vocabulary as wikipedia_adapter
from tools import evaluate_nepali_roman_pack as heldout_evaluator


EVALUATOR_VERSION = 2
WIKIPEDIA_VOCABULARY_SHA256 = (
    "829c71836407912509883917a43c88d301f9be08c4400442b4a61d6eaf742214"
)
WIKIPEDIA_MANIFEST_SHA256 = (
    "221bddfe0d4e3bc5835892ee0ae7f0602cdcfc16f74cc9ab74c281f071a79f70"
)
WIKIPEDIA_ROWS = 439_308
WIKIPEDIA_ATTRIBUTION_SHA256 = (
    "fd5bd0744f6e2fcbc3e3d2465e6346394fe66af30c79bd625fc791707d302b7e"
)
WIKIPEDIA_ATTRIBUTION_ROWS = 42_263
CUTOFFS = (0, 10_000, 25_000, 50_000, 100_000, 200_000, WIKIPEDIA_ROWS)


class CoverageEvaluationError(ValueError):
    """Raised when pinned coverage-evaluation evidence is invalid."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except FileNotFoundError as exc:
        raise CoverageEvaluationError(f"missing required input: {path}") from exc
    return digest.hexdigest()


def _verified_direct_surfaces(path: Path) -> set[str]:
    actual_sha256 = _sha256_file(path)
    expected_sha256 = roman_adapter.DIRECT_SOURCE_SHA256["forms.jsonl"]
    if actual_sha256 != expected_sha256:
        raise CoverageEvaluationError(
            "direct forms SHA-256 mismatch: expected "
            f"{expected_sha256}, got {actual_sha256}"
        )
    surfaces: set[str] = set()
    try:
        handle = path.open(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CoverageEvaluationError(f"direct forms are not UTF-8: {path}") from exc
    with handle:
        for line_number, raw in enumerate(handle, 1):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise CoverageEvaluationError(
                    f"invalid direct form JSON at line {line_number}: {exc}"
                ) from exc
            surface = row.get("surface") if isinstance(row, dict) else None
            if not isinstance(surface, str) or direct_adapter._canonical_token(surface) != surface:
                raise CoverageEvaluationError(
                    f"invalid direct Devanagari surface at line {line_number}"
                )
            if surface in surfaces:
                raise CoverageEvaluationError(
                    f"duplicate direct surface at line {line_number}: {surface!r}"
                )
            surfaces.add(surface)
    if len(surfaces) != roman_adapter.DIRECT_FORM_COUNT:
        raise CoverageEvaluationError(
            "direct form count mismatch: expected "
            f"{roman_adapter.DIRECT_FORM_COUNT}, got {len(surfaces)}"
        )
    return surfaces


def _verified_wikipedia_manifest(path: Path) -> dict[str, object]:
    actual_sha256 = _sha256_file(path)
    if actual_sha256 != WIKIPEDIA_MANIFEST_SHA256:
        raise CoverageEvaluationError(
            "Wikipedia manifest SHA-256 mismatch: expected "
            f"{WIKIPEDIA_MANIFEST_SHA256}, got {actual_sha256}"
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoverageEvaluationError(f"invalid Wikipedia manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CoverageEvaluationError("Wikipedia manifest must be a JSON object")
    source = manifest.get("input")
    output = manifest.get("output")
    selection = manifest.get("selection_contract")
    redistribution = manifest.get("redistribution")
    expected_source = {
        "date": wikipedia_adapter.DUMP_DATE,
        "sha1": wikipedia_adapter.DUMP_SHA1,
        "sha256": wikipedia_adapter.DUMP_SHA256,
        "bytes": wikipedia_adapter.DUMP_BYTES,
        "namespace": 0,
    }
    if not isinstance(source, dict) or any(
        source.get(key) != value for key, value in expected_source.items()
    ):
        raise CoverageEvaluationError("Wikipedia manifest does not bind the pinned dump")
    legal_documents = source.get("legal_documents")
    expected_legal_documents = {
        "dump_license_information": {
            "bytes": wikipedia_adapter.DUMP_LICENSE_INFO_BYTES,
            "sha256": wikipedia_adapter.DUMP_LICENSE_INFO_SHA256,
            "source_url": wikipedia_adapter.DUMP_LICENSE_INFO_URL,
        },
        "terms_of_use": {
            "bytes": wikipedia_adapter.WIKIMEDIA_TERMS_BYTES,
            "sha256": wikipedia_adapter.WIKIMEDIA_TERMS_SHA256,
            "source_url": wikipedia_adapter.WIKIMEDIA_TERMS_URL,
            "revision": wikipedia_adapter.WIKIMEDIA_TERMS_REVISION,
        },
        "cc_by_sa_legalcode": {
            "bytes": wikipedia_adapter.LICENSE_BYTES,
            "sha256": wikipedia_adapter.LICENSE_SHA256,
            "source_url": wikipedia_adapter.LICENSE_URL,
        },
    }
    if not isinstance(legal_documents, dict):
        raise CoverageEvaluationError("Wikipedia manifest lacks pinned legal documents")
    for document_id, expected in expected_legal_documents.items():
        document = legal_documents.get(document_id)
        if not isinstance(document, dict) or any(
            document.get(key) != value for key, value in expected.items()
        ):
            raise CoverageEvaluationError(
                f"Wikipedia legal document binding mismatch: {document_id}"
            )
    if manifest.get("generator_version") != wikipedia_adapter.GENERATOR_VERSION:
        raise CoverageEvaluationError("Wikipedia manifest generator version mismatch")
    if not isinstance(output, dict) or (
        output.get("rows") != WIKIPEDIA_ROWS
        or output.get("sha256") != WIKIPEDIA_VOCABULARY_SHA256
    ):
        raise CoverageEvaluationError("Wikipedia manifest output binding mismatch")
    attribution = output.get("attribution_pages")
    if not isinstance(attribution, dict) or (
        attribution.get("rows") != WIKIPEDIA_ATTRIBUTION_ROWS
        or attribution.get("sha256") != WIKIPEDIA_ATTRIBUTION_SHA256
    ):
        raise CoverageEvaluationError("Wikipedia attribution binding mismatch")
    if not isinstance(selection, dict) or selection.get("evaluation_data_consumed") is not False:
        raise CoverageEvaluationError(
            "Wikipedia vocabulary must declare evaluation_data_consumed=false"
        )
    if not isinstance(redistribution, dict) or (
        redistribution.get("shipping_authority") is not False
        or redistribution.get("gate") != wikipedia_adapter.SHIPPING_GATE
        or redistribution.get("attribution_index_included") is not True
    ):
        raise CoverageEvaluationError(
            "Wikipedia vocabulary must retain its redistribution gate"
        )
    return manifest


def _verified_attribution_pages(path: Path) -> int:
    actual_sha256 = _sha256_file(path)
    if actual_sha256 != WIKIPEDIA_ATTRIBUTION_SHA256:
        raise CoverageEvaluationError(
            "Wikipedia attribution SHA-256 mismatch: expected "
            f"{WIKIPEDIA_ATTRIBUTION_SHA256}, got {actual_sha256}"
        )
    previous_page_id = 0
    page_ids: set[int] = set()
    revision_ids: set[int] = set()
    rows = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise CoverageEvaluationError(
                        f"invalid Wikipedia attribution JSON at line {line_number}: {exc}"
                    ) from exc
                if not isinstance(row, dict):
                    raise CoverageEvaluationError(
                        f"Wikipedia attribution line {line_number} must be an object"
                    )
                page_id = row.get("page_id")
                revision_id = row.get("revision_id")
                title = row.get("title")
                if (
                    not isinstance(page_id, int)
                    or isinstance(page_id, bool)
                    or page_id <= previous_page_id
                ):
                    raise CoverageEvaluationError(
                        f"invalid or unsorted page ID at attribution line {line_number}"
                    )
                if (
                    not isinstance(revision_id, int)
                    or isinstance(revision_id, bool)
                    or revision_id < 1
                    or revision_id in revision_ids
                ):
                    raise CoverageEvaluationError(
                        f"invalid revision ID at attribution line {line_number}"
                    )
                if not isinstance(title, str) or not title:
                    raise CoverageEvaluationError(
                        f"invalid title at attribution line {line_number}"
                    )
                if row.get("page_url") != f"https://ne.wikipedia.org/?curid={page_id}":
                    raise CoverageEvaluationError(
                        f"invalid page URL at attribution line {line_number}"
                    )
                if row.get("revision_url") != (
                    f"https://ne.wikipedia.org/w/index.php?oldid={revision_id}"
                ):
                    raise CoverageEvaluationError(
                        f"invalid revision URL at attribution line {line_number}"
                    )
                previous_page_id = page_id
                page_ids.add(page_id)
                revision_ids.add(revision_id)
                rows = line_number
    except UnicodeDecodeError as exc:
        raise CoverageEvaluationError(
            f"Wikipedia attribution index is not UTF-8: {path}"
        ) from exc
    if rows != WIKIPEDIA_ATTRIBUTION_ROWS or len(page_ids) != rows:
        raise CoverageEvaluationError(
            "Wikipedia attribution row count mismatch: expected "
            f"{WIKIPEDIA_ATTRIBUTION_ROWS}, got {rows}"
        )
    return rows


def _verified_wikipedia_ranks(
    path: Path,
    direct_surfaces: set[str],
    heldout_targets: set[str],
) -> tuple[dict[str, int], dict[int, int]]:
    actual_sha256 = _sha256_file(path)
    if actual_sha256 != WIKIPEDIA_VOCABULARY_SHA256:
        raise CoverageEvaluationError(
            "Wikipedia vocabulary SHA-256 mismatch: expected "
            f"{WIKIPEDIA_VOCABULARY_SHA256}, got {actual_sha256}"
        )
    first_rank_by_heldout_target: dict[str, int] = {}
    overlap_at_cutoff = {0: 0}
    cutoffs = set(CUTOFFS)
    seen: set[str] = set()
    previous_count: int | None = None
    previous_surface: str | None = None
    overlaps = 0
    rows = 0
    try:
        handle = path.open(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CoverageEvaluationError(f"Wikipedia vocabulary is not UTF-8: {path}") from exc
    with handle:
        for line_number, raw in enumerate(handle, 1):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise CoverageEvaluationError(
                    f"invalid Wikipedia vocabulary JSON at line {line_number}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise CoverageEvaluationError(
                    f"Wikipedia vocabulary line {line_number} must be an object"
                )
            rank = row.get("rank")
            count = row.get("count")
            surface = row.get("surface")
            if rank != line_number or not isinstance(rank, int):
                raise CoverageEvaluationError(
                    f"Wikipedia vocabulary rank mismatch at line {line_number}"
                )
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise CoverageEvaluationError(
                    f"invalid Wikipedia count at line {line_number}"
                )
            if not isinstance(surface, str) or direct_adapter._canonical_token(surface) != surface:
                raise CoverageEvaluationError(
                    f"invalid Wikipedia Devanagari surface at line {line_number}"
                )
            if surface in seen:
                raise CoverageEvaluationError(
                    f"duplicate Wikipedia surface at line {line_number}: {surface!r}"
                )
            if previous_count is not None and (
                count > previous_count
                or (count == previous_count and surface <= (previous_surface or ""))
            ):
                raise CoverageEvaluationError(
                    f"Wikipedia rank order violation at line {line_number}"
                )
            seen.add(surface)
            previous_count = count
            previous_surface = surface
            rows = line_number
            if surface in direct_surfaces:
                overlaps += 1
            elif surface in heldout_targets:
                first_rank_by_heldout_target[surface] = rank
            if rank in cutoffs:
                overlap_at_cutoff[rank] = overlaps
    if rows != WIKIPEDIA_ROWS:
        raise CoverageEvaluationError(
            f"Wikipedia row count mismatch: expected {WIKIPEDIA_ROWS}, got {rows}"
        )
    missing_cutoffs = sorted(set(CUTOFFS) - set(overlap_at_cutoff))
    if missing_cutoffs:
        raise CoverageEvaluationError(f"Wikipedia cutoffs exceed rows: {missing_cutoffs}")
    return first_rank_by_heldout_target, overlap_at_cutoff


def _coverage_curve(
    test_rows: list[dict[str, object]],
    direct_surfaces: set[str],
    first_wikipedia_rank: dict[str, int],
    overlap_at_cutoff: dict[int, int],
) -> list[dict[str, object]]:
    source_totals = Counter(str(row["source"]) for row in test_rows)
    result: list[dict[str, object]] = []
    for cutoff in CUTOFFS:
        covered_by_source = Counter()
        covered = 0
        for row in test_rows:
            target = unicodedata.normalize("NFC", str(row["native word"]))
            if target in direct_surfaces or first_wikipedia_rank.get(target, cutoff + 1) <= cutoff:
                covered += 1
                covered_by_source[str(row["source"])] += 1
        result.append(
            {
                "wikipedia_prefix_rows": cutoff,
                "wikipedia_rows_overlapping_direct": overlap_at_cutoff[cutoff],
                "wikipedia_unique_additions": cutoff - overlap_at_cutoff[cutoff],
                "candidate_union_rows": (
                    len(direct_surfaces) + cutoff - overlap_at_cutoff[cutoff]
                ),
                "covered_test_rows": covered,
                "target_vocabulary_coverage": covered / len(test_rows),
                "additional_rows_covered_vs_direct": covered
                - sum(
                    1
                    for row in test_rows
                    if unicodedata.normalize("NFC", str(row["native word"]))
                    in direct_surfaces
                ),
                "by_source": {
                    source: {
                        "test_rows": source_totals[source],
                        "covered_rows": covered_by_source[source],
                        "target_vocabulary_coverage": (
                            covered_by_source[source] / source_totals[source]
                        ),
                    }
                    for source in sorted(source_totals)
                },
            }
        )
    return result


def evaluate(args: argparse.Namespace) -> dict[str, object]:
    if os.path.lexists(args.output):
        raise CoverageEvaluationError(
            f"output path already exists; refusing to overwrite evidence: {args.output}"
        )
    direct_surfaces = _verified_direct_surfaces(args.direct_forms)
    wikipedia_manifest = _verified_wikipedia_manifest(args.wikipedia_manifest)
    attribution_rows = _verified_attribution_pages(args.wikipedia_attribution)
    try:
        test_rows = heldout_evaluator._verified_test_rows(args.aksharantar_archive)
    except heldout_evaluator.EvaluationError as exc:
        raise CoverageEvaluationError(str(exc)) from exc
    heldout_targets = {
        unicodedata.normalize("NFC", str(row["native word"])) for row in test_rows
    }
    first_rank, overlap_at_cutoff = _verified_wikipedia_ranks(
        args.wikipedia_vocabulary,
        direct_surfaces,
        heldout_targets,
    )
    curve = _coverage_curve(
        test_rows,
        direct_surfaces,
        first_rank,
        overlap_at_cutoff,
    )
    report: dict[str, object] = {
        "evaluator": "evaluate_nepali_vocabulary_coverage",
        "evaluator_version": EVALUATOR_VERSION,
        "contract": {
            "evaluation_only": True,
            "held_out_targets_consumed_after_vocabulary_ranks_were_fixed": True,
            "fixed_wikipedia_cutoffs": list(CUTOFFS),
            "report_contains_target_identities": False,
            "release_build_must_not_consume_this_report": True,
        },
        "inputs": {
            "direct_forms": {
                "rows": len(direct_surfaces),
                "sha256": roman_adapter.DIRECT_SOURCE_SHA256["forms.jsonl"],
            },
            "wikipedia_vocabulary": {
                "rows": WIKIPEDIA_ROWS,
                "sha256": WIKIPEDIA_VOCABULARY_SHA256,
                "manifest_sha256": WIKIPEDIA_MANIFEST_SHA256,
                "attribution_rows": attribution_rows,
                "attribution_sha256": WIKIPEDIA_ATTRIBUTION_SHA256,
                "shipping_authority": wikipedia_manifest["redistribution"][
                    "shipping_authority"
                ],
                "redistribution_gate": wikipedia_manifest["redistribution"]["gate"],
            },
            "evaluation_source": {
                "dataset": "AI4Bharat Aksharantar",
                "archive_sha256": roman_adapter.AKSHARANTAR_ARCHIVE_SHA256,
                "member": "nep_test.json",
                "member_sha256": roman_adapter.AKSHARANTAR_MEMBER_SHA256[
                    "nep_test.json"
                ],
                "held_out_from_both_vocabulary_builds": True,
            },
        },
        "population": {
            "test_rows": len(test_rows),
            "unique_targets": len(heldout_targets),
            "source_rows": dict(
                sorted(Counter(str(row["source"]) for row in test_rows).items())
            ),
        },
        "curve": curve,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{args.output.name}.staging-",
        dir=args.output.parent,
    )
    os.close(descriptor)
    staging = Path(staging_name)
    try:
        staging.write_text(_canonical_json(report) + "\n", encoding="utf-8")
        os.replace(staging, args.output)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure fixed-cutoff held-out coverage of pinned Nepali vocabulary."
    )
    parser.add_argument("--direct-forms", type=Path, required=True)
    parser.add_argument("--wikipedia-vocabulary", type=Path, required=True)
    parser.add_argument("--wikipedia-manifest", type=Path, required=True)
    parser.add_argument("--wikipedia-attribution", type=Path, required=True)
    parser.add_argument("--aksharantar-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    parser = build_parser()
    try:
        report = evaluate(parser.parse_args())
    except CoverageEvaluationError as exc:
        parser.error(str(exc))
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
