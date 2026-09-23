#!/usr/bin/env python3
"""Build candidate-only internal source tables from one pinned SIL-APK JSONL.

This adapter is deliberately not a profile-promotion tool. It derives source
identity from the resource catalog and requires the caller to select one of the
two policies measured by ``audit_sil_apk_layout_gap.py``. The cdjk candidate
runner validates that selection against a pinned audit before invoking this
module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools import sil_apk_jsonl_internal_source as sil_apk


ADAPTER_NAME = "build_sil_apk_candidate_source"
ADAPTER_VERSION = 1
HELPER_NAME = "sil_apk_jsonl_internal_source"
HELPER_VERSION = 1
HELPER_REPOSITORY_PATH = "tools/sil_apk_jsonl_internal_source.py"
HELPER_SHA256 = "f520e65402412c0982875d12751808a74082452fd3b5d10fbafa9b7b11d580c3"
POLICIES = {
    "conjunct_only": False,
    "terminal_zwnj": True,
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_NAME_RE = re.compile(r"^nepali-(.+)\.sil-apk\.dict\.jsonl$")
LANGUAGE_RE = re.compile(r"^[a-z]{3}$")
ADAPTER_PATH = Path(__file__).resolve()
AdapterError = sil_apk.AdapterError


class CandidateError(ValueError):
    """Raised when a candidate input is outside the narrow SIL-APK contract."""


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise CandidateError(f"duplicate JSON key {key!r}")
        value[key] = child
    return value


def read_strict_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CandidateError(f"{label} is not a regular file: {path}")
    try:
        encoded = path.read_bytes()
    except OSError as exc:
        raise CandidateError(f"cannot read {label} {path}: {exc}") from exc
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise CandidateError(f"{label} must not contain a UTF-8 BOM")
    try:
        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_strict_object,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateError(f"invalid UTF-8 JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise CandidateError(f"{label} must be a JSON object")
    return value


def _required_string(value: dict[str, Any], key: str, location: str) -> str:
    child = value.get(key)
    if not isinstance(child, str) or not child:
        raise CandidateError(f"{location}.{key} must be a non-empty string")
    return child


def _required_positive_int(value: dict[str, Any], key: str, location: str) -> int:
    child = value.get(key)
    if isinstance(child, bool) or not isinstance(child, int) or child < 1:
        raise CandidateError(f"{location}.{key} must be a positive integer")
    return child


def _catalog_binding(
    catalog: dict[str, Any],
    target_id: str,
    resource_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    packs = catalog.get("packs")
    if not isinstance(packs, list):
        raise CandidateError("resource catalog packs must be an array")
    targets = [
        row
        for row in packs
        if isinstance(row, dict) and row.get("id") == target_id
    ]
    if len(targets) != 1:
        raise CandidateError("resource catalog must contain exactly one target")
    target = targets[0]
    resources = target.get("resources")
    if not isinstance(resources, list):
        raise CandidateError("catalog target resources must be an array")
    matches = [
        row
        for row in resources
        if isinstance(row, dict) and row.get("id") == resource_id
    ]
    if len(matches) != 1:
        raise CandidateError("resource catalog must contain exactly one resource")
    resource = matches[0]
    if resource.get("kind") != "lexicon" or resource.get("format") != "JSONL":
        raise CandidateError("candidate resource must be a JSONL lexicon")
    if resource.get("structured") is not True or resource.get("canonical") is not True:
        raise CandidateError("candidate resource must be structured and canonical")
    if resource.get("record_unit") != "entries":
        raise CandidateError("candidate resource must count entries")
    uses = resource.get("uses")
    if not isinstance(uses, list) or "candidate_vocabulary" not in uses:
        raise CandidateError("candidate resource must support candidate vocabulary")
    sha256 = _required_string(resource, "sha256", "catalog resource")
    if not SHA256_RE.fullmatch(sha256):
        raise CandidateError("catalog resource SHA-256 is malformed")
    _required_positive_int(resource, "records", "catalog resource")
    _required_positive_int(resource, "bytes", "catalog resource")
    language = _required_string(target, "iso_639_3", "catalog target")
    if not LANGUAGE_RE.fullmatch(language):
        raise CandidateError("catalog target ISO 639-3 code is malformed")
    _required_string(target, "name", "catalog target")
    return target, resource


def _verify_helper_identity() -> str:
    loaded_name = getattr(sil_apk, "__file__", None)
    if not isinstance(loaded_name, str):
        raise CandidateError("loaded SIL-APK helper has no source path")
    loaded = Path(loaded_name)
    expected = ADAPTER_PATH.parent / "sil_apk_jsonl_internal_source.py"
    if loaded.is_symlink() or not loaded.is_file() or loaded.resolve() != expected.resolve():
        raise CandidateError(
            f"loaded SIL-APK helper is not the canonical repository source: {loaded}"
        )
    if sil_apk.HELPER_NAME != HELPER_NAME or sil_apk.HELPER_VERSION != HELPER_VERSION:
        raise CandidateError("loaded SIL-APK helper name or version mismatch")
    actual = hashlib.sha256(loaded.read_bytes()).hexdigest()
    if actual != HELPER_SHA256:
        raise CandidateError(
            "SIL-APK helper SHA-256 mismatch: "
            f"expected {HELPER_SHA256}, got {actual}"
        )
    return actual


def build_candidate_source(args: argparse.Namespace) -> dict[str, object]:
    catalog = read_strict_json_object(args.resource_catalog, "resource catalog")
    target, resource = _catalog_binding(catalog, args.target_id, args.resource_id)
    expected_name = Path(
        _required_string(resource, "path", "catalog resource")
    ).name
    source_match = SOURCE_NAME_RE.fullmatch(expected_name)
    if source_match is None:
        raise CandidateError(
            "catalog resource filename is not a supported SIL-APK JSONL name"
        )
    expected_source_tag = f"sil-apk/{source_match.group(1)}"
    if args.source_tag != expected_source_tag:
        raise CandidateError(f"source tag must be {expected_source_tag}")
    if args.sil_apk_jsonl.is_symlink() or not args.sil_apk_jsonl.is_file():
        raise CandidateError("SIL-APK JSONL input must be a regular file")
    if args.sil_apk_jsonl.name != expected_name:
        raise CandidateError(f"SIL-APK JSONL filename must be {expected_name}")
    try:
        input_bytes = args.sil_apk_jsonl.read_bytes()
    except OSError as exc:
        raise CandidateError(f"cannot read SIL-APK JSONL: {exc}") from exc
    if len(input_bytes) != _required_positive_int(resource, "bytes", "catalog resource"):
        raise CandidateError("SIL-APK JSONL byte count does not match the catalog")
    actual_sha256 = hashlib.sha256(input_bytes).hexdigest()
    expected_sha256 = _required_string(resource, "sha256", "catalog resource")
    if actual_sha256 != expected_sha256:
        raise CandidateError("SIL-APK JSONL SHA-256 does not match the catalog")
    if args.policy not in POLICIES:
        raise CandidateError("policy must be conjunct_only or terminal_zwnj")
    if args.output.is_symlink():
        raise CandidateError("candidate source output must not be a symbolic link")

    helper_sha256 = _verify_helper_identity()
    language = _required_string(target, "iso_639_3", "catalog target")
    display_name = _required_string(target, "name", "catalog target")
    variety = target.get("variety")
    if variety is not None and (not isinstance(variety, str) or not variety):
        raise CandidateError("catalog target variety must be null or a non-empty string")
    license_id = resource.get("license", "unknown")
    redistribution = resource.get("redistribution", "unknown")
    if not isinstance(license_id, str) or not license_id:
        raise CandidateError("catalog resource license must be a non-empty string")
    if not isinstance(redistribution, str) or not redistribution:
        raise CandidateError("catalog resource redistribution must be a non-empty string")
    config = sil_apk.SilApkConfig(
        adapter_name=ADAPTER_NAME,
        adapter_version=ADAPTER_VERSION,
        pack_id=f"{language}-Deva-NP",
        source_id=args.resource_id,
        source_sha256=expected_sha256,
        expected_data_rows=_required_positive_int(
            resource,
            "records",
            "catalog resource",
        ),
        language=language,
        source_tag=args.source_tag,
        file_name=expected_name,
        display_name=display_name,
        variety=variety,
        stable_id_prefix=f"{language}:apk",
        source_title=f"{display_name} SIL Dictionary App Builder lexicon",
        license_id=license_id,
        redistribution=redistribution,
        allow_terminal_zwnj=POLICIES[args.policy],
    )
    try:
        return sil_apk.build_internal_source(
            args,
            config=config,
            adapter_path=ADAPTER_PATH,
            helper_sha256=helper_sha256,
        )
    except AdapterError as exc:
        raise CandidateError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-catalog", type=Path, required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--resource-id", required=True)
    parser.add_argument("--sil-apk-jsonl", type=Path, required=True)
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--policy", choices=sorted(POLICIES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-version", default="1.0.0")
    parser.add_argument("--max-suggestions", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_candidate_source(args)
    except (CandidateError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
