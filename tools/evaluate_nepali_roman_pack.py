#!/usr/bin/env python3
"""Evaluate a Nepali alias pack against the pinned held-out Aksharantar test set."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from nepa_keyboard.runtime import KeyboardPack
from tools import build_nepali_roman_release_source as adapter


class EvaluationError(ValueError):
    """Raised when held-out evaluation evidence is invalid or insufficient."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except FileNotFoundError as exc:
        raise EvaluationError(f"missing required input: {path}") from exc
    return digest.hexdigest()


def _ratio(numerator: int | float, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _rank_metrics(
    denominator: int,
    returned_any: int,
    ranks: Counter[int],
    reciprocal_rank_sum: float,
) -> dict[str, object]:
    top1 = ranks[1]
    top3 = sum(count for rank, count in ranks.items() if rank <= 3)
    top5 = sum(count for rank, count in ranks.items() if rank <= 5)
    return {
        "denominator": denominator,
        "returned_any": returned_any,
        "lookup_coverage": _ratio(returned_any, denominator),
        "top1": top1,
        "top1_accuracy": _ratio(top1, denominator),
        "top3": top3,
        "top3_accuracy": _ratio(top3, denominator),
        "top5": top5,
        "top5_accuracy": _ratio(top5, denominator),
        "mean_reciprocal_rank": _ratio(reciprocal_rank_sum, denominator),
        "rank_counts": {str(key): value for key, value in sorted(ranks.items())},
    }


def _verified_test_rows(archive_path: Path) -> list[dict[str, object]]:
    archive_sha256 = _sha256_file(archive_path)
    if archive_sha256 != adapter.AKSHARANTAR_ARCHIVE_SHA256:
        raise EvaluationError(
            "Aksharantar archive SHA-256 mismatch: expected "
            f"{adapter.AKSHARANTAR_ARCHIVE_SHA256}, got {archive_sha256}"
        )
    member = "nep_test.json"
    rows: list[dict[str, object]] = []
    digest = hashlib.sha256()
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except zipfile.BadZipFile as exc:
        raise EvaluationError(f"invalid Aksharantar archive: {archive_path}") from exc
    with archive:
        try:
            handle = archive.open(member)
        except KeyError as exc:
            raise EvaluationError(f"Aksharantar archive lacks {member}") from exc
        with handle:
            for line_number, raw in enumerate(handle, 1):
                digest.update(raw)
                try:
                    row = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise EvaluationError(
                        f"invalid JSON at {member}:{line_number}: {exc}"
                    ) from exc
                try:
                    row = adapter._validate_aksharantar_row(row, member, line_number)
                except adapter.RomanAdapterError as exc:
                    raise EvaluationError(str(exc)) from exc
                rows.append(row)
    expected_rows = adapter.AKSHARANTAR_MEMBER_ROWS[member]
    if len(rows) != expected_rows:
        raise EvaluationError(
            f"{member} row count mismatch: expected {expected_rows}, got {len(rows)}"
        )
    actual_member_sha256 = digest.hexdigest()
    expected_member_sha256 = adapter.AKSHARANTAR_MEMBER_SHA256[member]
    if actual_member_sha256 != expected_member_sha256:
        raise EvaluationError(
            f"{member} SHA-256 mismatch: expected {expected_member_sha256}, "
            f"got {actual_member_sha256}"
        )
    return rows


def evaluate(args: argparse.Namespace) -> dict[str, object]:
    if not isinstance(args.minimum_cases, int) or args.minimum_cases < 1:
        raise EvaluationError("minimum cases must be a positive integer")
    pack_sha256 = _sha256_file(args.pack)
    test_rows = _verified_test_rows(args.aksharantar_archive)

    gold_targets_by_alias: dict[str, set[str]] = defaultdict(set)
    source_counts = Counter()
    eligible_source_counts = Counter()
    evaluated_source_counts = Counter()
    ranks = Counter()
    source_ranks: dict[str, Counter[int]] = defaultdict(Counter)
    reciprocal_rank_sum = 0.0
    source_reciprocal_rank_sums = Counter()
    returned_any = 0
    source_returned_any = Counter()
    ineligible = 0
    cases: list[dict[str, object]] = []

    try:
        pack = KeyboardPack(args.pack)
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as exc:
        raise EvaluationError(f"cannot open keyboard pack: {exc}") from exc
    with pack:
        pack_metadata = pack.manifest.get("pack", {})
        if not isinstance(pack_metadata, dict) or pack_metadata.get("pack_id") != adapter.PACK_ID:
            raise EvaluationError(f"pack must have pack_id={adapter.PACK_ID}")
        if pack.manifest.get("release_mode") != "release":
            raise EvaluationError("evaluation requires a release-mode pack")
        candidate_surfaces = set(pack._candidates)

        for row_number, row in enumerate(test_rows, 1):
            native = unicodedata.normalize("NFC", str(row["native word"]))
            alias = adapter._normalize_alias(
                row["english word"], f"nep_test.json:{row_number}"
            )
            source = str(row["source"])
            source_counts[source] += 1
            gold_targets_by_alias[alias].add(native)
            if native not in candidate_surfaces:
                ineligible += 1
                continue
            eligible_source_counts[source] += 1
            results = pack.lookup(alias, "aliases")
            returned = [str(result["surface"]) for result in results]
            if returned:
                returned_any += 1
                source_returned_any[source] += 1
            rank = returned.index(native) + 1 if native in returned else None
            if rank is not None:
                ranks[rank] += 1
                source_ranks[source][rank] += 1
                reciprocal_rank_sum += 1.0 / rank
                source_reciprocal_rank_sums[source] += 1.0 / rank
            evaluated_source_counts[source] += 1
            cases.append(
                {
                    "case_id": f"aksharantar.nep.test.{row_number}",
                    "alias": alias,
                    "target": native,
                    "source": source,
                    "rank": rank,
                    "returned": returned,
                }
            )

    evaluated = len(cases)
    if evaluated < args.minimum_cases:
        raise EvaluationError(
            f"only {evaluated} held-out cases have targets in the pack; "
            f"minimum is {args.minimum_cases}"
        )
    closed_vocabulary = _rank_metrics(
        evaluated,
        returned_any,
        ranks,
        reciprocal_rank_sum,
    )
    end_to_end = _rank_metrics(
        len(test_rows),
        returned_any,
        ranks,
        reciprocal_rank_sum,
    )
    by_source: dict[str, object] = {}
    for source in sorted(source_counts):
        source_rows = source_counts[source]
        eligible_rows = eligible_source_counts[source]
        by_source[source] = {
            "test_rows": source_rows,
            "eligible_rows": eligible_rows,
            "ineligible_target_rows": source_rows - eligible_rows,
            "target_vocabulary_coverage": _ratio(eligible_rows, source_rows),
            "closed_vocabulary": _rank_metrics(
                eligible_rows,
                source_returned_any[source],
                source_ranks[source],
                source_reciprocal_rank_sums[source],
            ),
            "end_to_end": _rank_metrics(
                source_rows,
                source_returned_any[source],
                source_ranks[source],
                source_reciprocal_rank_sums[source],
            ),
        }
    gold_collisions = sum(1 for values in gold_targets_by_alias.values() if len(values) > 1)
    report: dict[str, object] = {
        "evaluator": "evaluate_nepali_roman_pack",
        "evaluator_version": 2,
        "pack": {
            "path": str(args.pack),
            "sha256": pack_sha256,
            "pack_id": adapter.PACK_ID,
        },
        "evaluation_source": {
            "dataset": "AI4Bharat Aksharantar",
            "upstream_commit": adapter.AKSHARANTAR_COMMIT,
            "archive_sha256": adapter.AKSHARANTAR_ARCHIVE_SHA256,
            "member": "nep_test.json",
            "member_sha256": adapter.AKSHARANTAR_MEMBER_SHA256["nep_test.json"],
            "held_out_from_pack_alias_build": True,
        },
        "population": {
            "test_rows": len(test_rows),
            "eligible_rows": evaluated,
            "ineligible_target_rows": ineligible,
            "target_vocabulary_coverage": evaluated / len(test_rows),
            "minimum_required_cases": args.minimum_cases,
            "unique_gold_aliases": len(gold_targets_by_alias),
            "gold_alias_collisions": gold_collisions,
            "source_rows": dict(sorted(source_counts.items())),
            "eligible_source_rows": dict(sorted(eligible_source_counts.items())),
        },
        "metrics": {
            "closed_vocabulary": closed_vocabulary,
            "end_to_end": end_to_end,
            "by_source": by_source,
            "evaluated_source_rows": dict(sorted(evaluated_source_counts.items())),
        },
        "cases": cases if args.include_cases else None,
    }
    if not args.include_cases:
        report.pop("cases")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(_canonical_json(report) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a release Nepali alias pack on pinned held-out test rows."
    )
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--aksharantar-archive", type=Path, required=True)
    parser.add_argument("--minimum-cases", type=int, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-cases", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        report = evaluate(args)
    except (EvaluationError, adapter.RomanAdapterError) as exc:
        parser.error(str(exc))
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
