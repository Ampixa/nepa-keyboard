#!/usr/bin/env python3
"""Validate deterministic surface and alias queries against NKP bundles."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from nepa_keyboard.runtime import KeyboardPack


CASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
INDEX_VALUES = {"surface", "aliases"}
REVIEW_STATUS_VALUES = {"fixture", "pending_speaker_review", "speaker_reviewed"}
ALLOWED_FIELDS = {
    "case_id",
    "profile_id",
    "pack_id",
    "index",
    "query",
    "expected_surface",
    "max_rank",
    "expect_empty",
    "review_status",
}
REQUIRED_FIELDS = {
    "case_id",
    "profile_id",
    "pack_id",
    "index",
    "query",
    "review_status",
}


class QueryValidationError(ValueError):
    """Raised when a validation-query row does not match its schema."""


def _require_nonempty_string(row: dict[str, Any], field: str, location: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise QueryValidationError(f"{location}: {field} must be a non-empty string")
    return value


def _validate_row(row: dict[str, Any], location: str) -> dict[str, Any]:
    unknown = sorted(set(row) - ALLOWED_FIELDS)
    if unknown:
        raise QueryValidationError(f"{location}: unknown fields: {', '.join(unknown)}")
    missing = sorted(REQUIRED_FIELDS - row.keys())
    if missing:
        raise QueryValidationError(f"{location}: missing fields: {', '.join(missing)}")

    case_id = _require_nonempty_string(row, "case_id", location)
    if not CASE_ID_RE.fullmatch(case_id):
        raise QueryValidationError(f"{location}: invalid case_id {case_id!r}")
    _require_nonempty_string(row, "profile_id", location)
    _require_nonempty_string(row, "pack_id", location)
    query_index = _require_nonempty_string(row, "index", location)
    if query_index not in INDEX_VALUES:
        raise QueryValidationError(f"{location}: index must be surface or aliases")
    _require_nonempty_string(row, "query", location)
    review_status = _require_nonempty_string(row, "review_status", location)
    if review_status not in REVIEW_STATUS_VALUES:
        raise QueryValidationError(f"{location}: invalid review_status {review_status!r}")

    has_expected = "expected_surface" in row or "max_rank" in row
    has_empty = "expect_empty" in row
    if has_expected:
        if "expected_surface" not in row or "max_rank" not in row or has_empty:
            raise QueryValidationError(
                f"{location}: expected_surface and max_rank must appear together without expect_empty"
            )
        _require_nonempty_string(row, "expected_surface", location)
        max_rank = row["max_rank"]
        if type(max_rank) is not int or not 1 <= max_rank <= 32:
            raise QueryValidationError(f"{location}: max_rank must be an integer from 1 to 32")
    elif not has_empty or row.get("expect_empty") is not True:
        raise QueryValidationError(
            f"{location}: provide expected_surface with max_rank, or expect_empty=true"
        )
    return dict(row)


def load_queries(path: Path) -> list[dict[str, Any]]:
    """Load and validate JSONL rows using validation-query.schema.json semantics."""
    rows: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise QueryValidationError(f"cannot read query file {path}: {exc}") from exc

    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        location = f"{path}:{line_number}"
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QueryValidationError(f"{location}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise QueryValidationError(f"{location}: expected an object")
        row = _validate_row(value, location)
        case_id = row["case_id"]
        if case_id in seen_case_ids:
            raise QueryValidationError(f"{location}: duplicate case_id {case_id!r}")
        seen_case_ids.add(case_id)
        rows.append(row)

    if not rows:
        raise QueryValidationError(f"{path}: at least one validation query is required")
    return sorted(rows, key=lambda row: row["case_id"])


def _case_result(row: dict[str, Any], pack: KeyboardPack | None, pack_error: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case_id": row["case_id"],
        "index": row["index"],
        "pack_id": row["pack_id"],
        "profile_id": row["profile_id"],
        "query": row["query"],
        "review_status": row["review_status"],
    }
    if pack_error is not None or pack is None:
        result.update({"passed": False, "reason": pack_error or "pack unavailable"})
        return result

    try:
        candidates = pack.lookup(row["query"], row["index"])
    except Exception as exc:  # Keep one corrupt lookup from hiding the remaining cases.
        result.update({"passed": False, "reason": f"lookup failed: {type(exc).__name__}: {exc}"})
        return result

    surfaces = [candidate["surface"] for candidate in candidates]
    result["observed_surfaces"] = surfaces
    if row.get("expect_empty") is True:
        passed = not surfaces
        result.update({"expect_empty": True, "passed": passed})
        if not passed:
            result["reason"] = "expected no candidates"
        return result

    expected_surface = row["expected_surface"]
    max_rank = row["max_rank"]
    try:
        observed_rank: int | None = surfaces.index(expected_surface) + 1
    except ValueError:
        observed_rank = None
    passed = observed_rank is not None and observed_rank <= max_rank
    result.update(
        {
            "expected_surface": expected_surface,
            "max_rank": max_rank,
            "observed_rank": observed_rank,
            "passed": passed,
        }
    )
    if not passed:
        result["reason"] = (
            "expected surface was not returned"
            if observed_rank is None
            else f"expected surface rank {observed_rank} exceeds {max_rank}"
        )
    return result


def validate_queries(
    queries: Iterable[dict[str, Any]],
    pack_paths: dict[str, Path],
) -> dict[str, Any]:
    """Run validated query rows and return a deterministic JSON-compatible summary."""
    rows = sorted((dict(row) for row in queries), key=lambda row: row["case_id"])
    required_pack_ids = sorted({row["pack_id"] for row in rows})
    packs: dict[str, KeyboardPack] = {}
    pack_errors: dict[str, str] = {}

    for pack_id in required_pack_ids:
        path = pack_paths.get(pack_id)
        if path is None:
            pack_errors[pack_id] = f"no pack path supplied for {pack_id}"
            continue
        try:
            pack = KeyboardPack(path)
            actual_pack_id = pack.manifest.get("pack", {}).get("pack_id")
            if actual_pack_id != pack_id:
                pack.close()
                pack_errors[pack_id] = (
                    f"pack ID mismatch: expected {pack_id}, found {actual_pack_id!r}"
                )
                continue
            packs[pack_id] = pack
        except Exception as exc:
            pack_errors[pack_id] = f"cannot open pack: {type(exc).__name__}: {exc}"

    try:
        case_results = [
            _case_result(row, packs.get(row["pack_id"]), pack_errors.get(row["pack_id"]))
            for row in rows
        ]
    finally:
        for pack_id in sorted(packs):
            packs[pack_id].close()

    passed = sum(1 for result in case_results if result["passed"])
    failed = len(case_results) - passed
    return {
        "cases": case_results,
        "counts": {"failed": failed, "passed": passed, "total": len(case_results)},
        "status": "ok" if failed == 0 else "failed",
    }


def _parse_pack_bindings(values: list[str]) -> dict[str, Path]:
    bindings: dict[str, Path] = {}
    for value in values:
        pack_id, separator, path = value.partition("=")
        if not separator or not pack_id or not path:
            raise QueryValidationError("--pack must use PACK_ID=PATH")
        if pack_id in bindings:
            raise QueryValidationError(f"duplicate --pack binding for {pack_id}")
        bindings[pack_id] = Path(path)
    return bindings


def _print_summary(summary: dict[str, Any]) -> None:
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate deterministic surface and alias lookups in release packs."
    )
    parser.add_argument("--queries", type=Path, required=True, help="Validation JSONL file")
    parser.add_argument(
        "--pack",
        action="append",
        default=[],
        metavar="PACK_ID=PATH",
        help="Pack binding; repeat for every pack referenced by the query file",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows = load_queries(args.queries)
        bindings = _parse_pack_bindings(args.pack)
        summary = validate_queries(rows, bindings)
    except QueryValidationError as exc:
        _print_summary(
            {
                "cases": [],
                "counts": {"failed": 0, "passed": 0, "total": 0},
                "errors": [str(exc)],
                "status": "error",
            }
        )
        return 2
    _print_summary(summary)
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
