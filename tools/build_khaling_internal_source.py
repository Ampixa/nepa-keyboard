#!/usr/bin/env python3
"""Build deterministic Khaling direct-input tables from the pinned SIL APK JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools import sil_apk_jsonl_internal_source as sil_apk


PACK_ID = "klr-Deva-NP"
SOURCE_ID = "klr-apk"
SOURCE_SHA256 = "442415559f1ec6191b2624e27439cc22438aaf24d19b4124571c826774c2adb4"
EXPECTED_DATA_ROWS = 4_513
HELPER_NAME = "sil_apk_jsonl_internal_source"
HELPER_VERSION = 1
HELPER_REPOSITORY_PATH = "tools/sil_apk_jsonl_internal_source.py"
HELPER_SHA256 = "f520e65402412c0982875d12751808a74082452fd3b5d10fbafa9b7b11d580c3"
ADAPTER_PATH = Path(__file__).resolve()
AdapterError = sil_apk.AdapterError
RANK_SCORE = sil_apk.RANK_SCORE

CONFIG = sil_apk.SilApkConfig(
    adapter_name="build_khaling_internal_source",
    adapter_version=1,
    pack_id=PACK_ID,
    source_id=SOURCE_ID,
    source_sha256=SOURCE_SHA256,
    expected_data_rows=EXPECTED_DATA_ROWS,
    language="klr",
    source_tag="sil-apk/khaling",
    file_name="nepali-khaling.sil-apk.dict.jsonl",
    display_name="Khaling",
    variety="Western Kiranti",
    stable_id_prefix="klr:apk",
    source_title="Khaling SIL Dictionary App Builder lexicon",
    license_id="restricted",
    redistribution="prohibited",
    allow_terminal_zwnj=False,
)


def _verify_helper_identity() -> str:
    loaded_name = getattr(sil_apk, "__file__", None)
    if not isinstance(loaded_name, str):
        raise AdapterError("loaded SIL-APK helper has no source path")
    loaded = Path(loaded_name)
    expected = ADAPTER_PATH.parent / "sil_apk_jsonl_internal_source.py"
    if loaded.is_symlink() or not loaded.is_file() or loaded.resolve() != expected.resolve():
        raise AdapterError(
            f"loaded SIL-APK helper is not the canonical repository source: {loaded}"
        )
    if sil_apk.HELPER_NAME != HELPER_NAME or sil_apk.HELPER_VERSION != HELPER_VERSION:
        raise AdapterError("loaded SIL-APK helper name or version mismatch")
    actual = hashlib.sha256(loaded.read_bytes()).hexdigest()
    if actual != HELPER_SHA256:
        raise AdapterError(
            "SIL-APK helper SHA-256 mismatch: "
            f"expected {HELPER_SHA256}, got {actual}"
        )
    return actual


def build_internal_source(args: argparse.Namespace) -> dict[str, object]:
    helper_sha256 = _verify_helper_identity()
    return sil_apk.build_internal_source(
        args,
        config=CONFIG,
        adapter_path=ADAPTER_PATH,
        helper_sha256=helper_sha256,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sil-apk-jsonl", type=Path, required=True)
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
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
