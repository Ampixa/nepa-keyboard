#!/usr/bin/env python3
"""Build the Central Gurung internal engineering source from the pinned TSV."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools import build_central_gurung_candidate_source as candidate


PACK_ID = candidate.PACK_ID
SOURCE_SHA256 = candidate.SOURCE_SHA256
EXPECTED_DATA_ROWS = candidate.EXPECTED_DATA_ROWS
AdapterError = candidate.AdapterError


def build_internal_source(args: argparse.Namespace) -> dict[str, object]:
    report = candidate.build_candidate_source(args)
    pack_path = args.output / "pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["display_name"] = "Central Gurung"
    pack_path.write_text(candidate._canonical_json(pack) + "\n", encoding="utf-8")

    report["adapter"] = "build_central_gurung_internal_source"
    report["adapter_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["claim_scope"] = "internal_engineering_small_lexicon"
    (args.output / "adapter-report.json").write_text(
        candidate._canonical_json(report) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = candidate.build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_internal_source(args)
    except AdapterError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
