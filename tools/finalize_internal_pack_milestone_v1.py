#!/usr/bin/env python3
"""Finalize a deterministic internal language-pack milestone.

The finalizer accepts no artifact hashes, counts, or expected candidates from
the command line. A versioned repository spec pins the adapter, raw source,
pack identity, canonical query selection, and layout contract. The finalizer
then proves this chain before updating the cumulative internal profile review:

raw dictionary -> current adapter -> two source trees -> current compiler ->
two byte-identical NKPs -> derived lookup evidence -> exact layout binding.

This tool is intentionally independent of the historical Limbu finalizer so a
new internal profile cannot rewrite or weaken the immutable Limbu evidence.
"""

from __future__ import annotations

import argparse
import copy
import filecmp
import hashlib
import importlib
import inspect
import json
import os
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

from nepa_keyboard.compiler import PackValidationError, compile_pack
from nepa_keyboard.runtime import KeyboardPack
from tools.build_shipping_profile_catalog import CatalogError, build_lock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = frozenset({
    "adapter-report.json",
    "aliases.jsonl",
    "forms.jsonl",
    "pack.json",
    "rejected-rows.jsonl",
    "sources.jsonl",
})
PACK_MEMBERS = frozenset({
    "aliases.trie",
    "candidates.bin",
    "manifest.json",
    "notices.json",
    "scores.bin",
    "surface.trie",
})
VERIFIED_MEMBERS = PACK_MEMBERS - {"manifest.json"}
INTERNAL_GATES = (
    "deterministic_build",
    "internal_pack",
    "layout_implemented",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LAYOUT_NOTICE_PATH_RE = re.compile(
    r"^layouts/(?:internal/)?notices/[A-Za-z0-9._-]+$"
)
LAYOUT_REDISTRIBUTION_VALUES = frozenset({
    "allowed",
    "permission_required",
    "prohibited",
    "system",
    "unknown",
})


class FinalizeError(ValueError):
    """Raised when the milestone evidence chain is incomplete or inconsistent."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise FinalizeError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise FinalizeError(f"{label} is not a regular file: {path}")


def _read_bytes(path: Path, label: str) -> bytes:
    _regular_file(path, label)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FinalizeError(f"cannot read {label} {path}: {exc}") from exc


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    encoded = _read_bytes(path, label)
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"invalid UTF-8 JSON in {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FinalizeError(f"{label} must be a JSON object: {path}")
    return value


def _required_object(value: dict[str, Any], key: str, location: str) -> dict[str, Any]:
    child = value.get(key)
    if not isinstance(child, dict):
        raise FinalizeError(f"{location}.{key} must be an object")
    return child


def _required_array(value: dict[str, Any], key: str, location: str) -> list[Any]:
    child = value.get(key)
    if not isinstance(child, list):
        raise FinalizeError(f"{location}.{key} must be an array")
    return child


def _required_string(value: dict[str, Any], key: str, location: str) -> str:
    child = value.get(key)
    if not isinstance(child, str) or not child:
        raise FinalizeError(f"{location}.{key} must be a non-empty string")
    return child


def _required_sha256(value: dict[str, Any], key: str, location: str) -> str:
    child = _required_string(value, key, location)
    if not SHA256_RE.fullmatch(child):
        raise FinalizeError(f"{location}.{key} must be a lowercase SHA-256 digest")
    return child


def _required_exact_int(value: dict[str, Any], key: str, location: str) -> int:
    child = value.get(key)
    if isinstance(child, bool) or not isinstance(child, int):
        raise FinalizeError(f"{location}.{key} must be an exact integer")
    return child


def _exact_fields(value: dict[str, Any], expected: set[str], location: str) -> None:
    if set(value) != expected:
        raise FinalizeError(
            f"{location} must contain exactly {sorted(expected)}, got {sorted(value)}"
        )


def _canonical_repo_path(path: Path, relative: str, label: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise FinalizeError(f"{label} spec path must be repository-relative")
    expected = REPOSITORY_ROOT / relative
    if path.resolve() != expected.resolve():
        raise FinalizeError(f"{label} must use canonical path {expected}")
    return expected


def _validate_v3_layout_license(value: object) -> None:
    """Validate the explicit v3 replacement for an inherited layout license."""
    if value is None:
        return
    if not isinstance(value, dict):
        raise FinalizeError("spec.layout.license must be null or an object")
    required = {"copyright", "id", "redistribution"}
    optional = {"license_url", "notice_path", "notice_sha256"}
    fields = set(value)
    if not required <= fields or not fields <= required | optional:
        raise FinalizeError(
            "spec.layout.license must contain id, copyright, redistribution, "
            "and only the optional license_url or paired notice fields"
        )
    _required_string(value, "id", "spec.layout.license")
    _required_string(value, "copyright", "spec.layout.license")
    redistribution = _required_string(
        value,
        "redistribution",
        "spec.layout.license",
    )
    if redistribution not in LAYOUT_REDISTRIBUTION_VALUES:
        raise FinalizeError("spec.layout.license.redistribution is unsupported")
    if "license_url" in value:
        license_url = _required_string(
            value,
            "license_url",
            "spec.layout.license",
        )
        if not re.fullmatch(r"https://[^\s]+", license_url):
            raise FinalizeError("spec.layout.license.license_url must use HTTPS")
    has_notice_path = "notice_path" in value
    has_notice_sha256 = "notice_sha256" in value
    if has_notice_path != has_notice_sha256:
        raise FinalizeError(
            "spec.layout.license notice_path and notice_sha256 must be paired"
        )
    if has_notice_path:
        notice_path = _required_string(
            value,
            "notice_path",
            "spec.layout.license",
        )
        if not LAYOUT_NOTICE_PATH_RE.fullmatch(notice_path):
            raise FinalizeError(
                "spec.layout.license.notice_path must be a layout notice path"
            )
        _required_sha256(value, "notice_sha256", "spec.layout.license")


def _require_distinct(first: Path, second: Path, label: str) -> None:
    if first.resolve() == second.resolve():
        raise FinalizeError(f"the two {label} paths must be distinct")
    try:
        same = os.path.samefile(first, second)
    except OSError as exc:
        raise FinalizeError(f"cannot compare {label} identities: {exc}") from exc
    if same:
        raise FinalizeError(f"the two {label} inputs must not share a file identity")


def _tree_inventory(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise FinalizeError(f"adapter source is not a regular directory: {root}")
    entries = sorted(root.iterdir(), key=lambda item: item.name)
    names = {entry.name for entry in entries}
    if names != SOURCE_FILES:
        raise FinalizeError(
            f"adapter source file set mismatch: expected {sorted(SOURCE_FILES)}, "
            f"got {sorted(names)}"
        )
    files: list[dict[str, object]] = []
    for path in entries:
        _regular_file(path, "adapter source member")
        files.append({
            "bytes": path.stat().st_size,
            "path": path.name,
            "sha256": _sha256_file(path),
        })
    payload = {"files": files}
    return {
        "algorithm": "sha256(canonical-json({files:[{bytes,path,sha256},...]}))",
        "files": files,
        "tree_sha256": _sha256_bytes(_canonical_bytes(payload)),
    }


def _compare_source_trees(
    source_a: Path,
    source_b: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _require_distinct(source_a, source_b, "source directory")
    inventory_a = _tree_inventory(source_a)
    inventory_b = _tree_inventory(source_b)
    if inventory_a != inventory_b:
        raise FinalizeError("the two adapter source trees are not byte-identical")
    for name in sorted(SOURCE_FILES):
        first = source_a / name
        second = source_b / name
        _require_distinct(first, second, f"source member {name}")
        if not filecmp.cmp(first, second, shallow=False):
            raise FinalizeError(f"adapter source member differs across runs: {name}")
    return inventory_a, inventory_b


def _validate_spec(spec_path: Path) -> tuple[dict[str, Any], bytes]:
    spec_bytes = _read_bytes(spec_path, "milestone spec")
    try:
        spec = json.loads(spec_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"invalid milestone spec: {exc}") from exc
    if not isinstance(spec, dict):
        raise FinalizeError("milestone spec must be an object")
    _exact_fields(
        spec,
        {"adapter", "evidence", "layout", "pack", "paths", "profile", "source", "spec_version"},
        "spec",
    )
    spec_version = _required_exact_int(spec, "spec_version", "spec")
    if spec_version not in {1, 2, 3, 4}:
        raise FinalizeError(
            "only milestone spec versions 1, 2, 3, and 4 are supported"
        )
    adapter = _required_object(spec, "adapter", "spec")
    evidence = _required_object(spec, "evidence", "spec")
    layout = _required_object(spec, "layout", "spec")
    pack = _required_object(spec, "pack", "spec")
    paths = _required_object(spec, "paths", "spec")
    profile = _required_object(spec, "profile", "spec")
    source = _required_object(spec, "source", "spec")
    _exact_fields(
        adapter,
        {"input_argument", "module", "name", "path", "sha256", "version"},
        "spec.adapter",
    )
    _exact_fields(
        evidence,
        {"remaining_production_gates", "report_id", "report_version"},
        "spec.evidence",
    )
    common_layout_fields = {
        "base_path", "base_sha256", "display_name", "layout_id",
        "provenance", "revision", "source_sha256",
    }
    if spec_version == 1:
        _exact_fields(
            layout,
            common_layout_fields
            | {
                "extension_layers", "extension_row", "license_notice_path",
                "operation",
            },
            "spec.layout",
        )
    elif spec_version == 2:
        _exact_fields(
            layout,
            common_layout_fields
            | {"license_notice_path", "license_notice_sha256", "operations"},
            "spec.layout",
        )
    else:
        _exact_fields(
            layout,
            common_layout_fields | {"license", "operations"},
            "spec.layout",
        )
    _exact_fields(
        pack,
        {"artifact_license", "file_name", "language", "output_script", "pack_id"},
        "spec.pack",
    )
    _exact_fields(
        paths,
        {"evidence_output", "layout_source", "queries", "resource_catalog", "review"},
        "spec.paths",
    )
    _exact_fields(
        profile,
        {"default_enabled", "input_method_id", "target_id"},
        "spec.profile",
    )
    common_source_fields = {
        "data_version", "expected_data_rows", "file_name", "max_suggestions",
        "resource_id", "sha256",
    }
    if spec_version == 4:
        _exact_fields(
            source,
            common_source_fields | {"auxiliary_input"},
            "spec.source",
        )
        auxiliary = _required_object(source, "auxiliary_input", "spec.source")
        _exact_fields(
            auxiliary,
            {"argument", "bytes", "file_name", "resource_id", "sha256"},
            "spec.source.auxiliary_input",
        )
        argument = _required_string(
            auxiliary,
            "argument",
            "spec.source.auxiliary_input",
        )
        if not re.fullmatch(r"[a-z][a-z0-9_]*", argument):
            raise FinalizeError("spec.source.auxiliary_input.argument is unsafe")
        if argument == adapter.get("input_argument"):
            raise FinalizeError(
                "auxiliary adapter argument must differ from the raw input argument"
            )
        _required_sha256(
            auxiliary,
            "sha256",
            "spec.source.auxiliary_input",
        )
        auxiliary_bytes = auxiliary.get("bytes")
        if (
            isinstance(auxiliary_bytes, bool)
            or not isinstance(auxiliary_bytes, int)
            or auxiliary_bytes < 1
        ):
            raise FinalizeError(
                "spec.source.auxiliary_input.bytes must be a positive integer"
            )
        _required_string(auxiliary, "file_name", "spec.source.auxiliary_input")
        _required_string(auxiliary, "resource_id", "spec.source.auxiliary_input")
    else:
        _exact_fields(source, common_source_fields, "spec.source")
    pack_id = _required_string(pack, "pack_id", "spec.pack")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", pack_id):
        raise FinalizeError("spec.pack.pack_id is unsafe")
    expected_spec = REPOSITORY_ROOT / "catalog/internal-pack-milestones" / f"{pack_id}-v0.json"
    if spec_path.resolve() != expected_spec.resolve():
        raise FinalizeError(f"milestone spec must use canonical path {expected_spec}")
    if spec_bytes != _canonical_bytes(spec):
        raise FinalizeError("milestone spec is not canonical UTF-8 JSON")
    _required_sha256(adapter, "sha256", "spec.adapter")
    _required_sha256(source, "sha256", "spec.source")
    _required_sha256(layout, "base_sha256", "spec.layout")
    _required_sha256(layout, "source_sha256", "spec.layout")
    if spec_version == 2:
        _required_sha256(layout, "license_notice_sha256", "spec.layout")
    elif spec_version in {3, 4}:
        _validate_v3_layout_license(layout.get("license"))
    for location, value in (
        ("spec.adapter.version", adapter.get("version")),
        ("spec.evidence.report_version", evidence.get("report_version")),
        ("spec.layout.revision", layout.get("revision")),
        ("spec.source.expected_data_rows", source.get("expected_data_rows")),
        ("spec.source.max_suggestions", source.get("max_suggestions")),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise FinalizeError(f"{location} must be a positive integer")
    if not isinstance(profile.get("default_enabled"), bool):
        raise FinalizeError("spec.profile.default_enabled must be boolean")
    remaining = evidence.get("remaining_production_gates")
    if (
        not isinstance(remaining, list)
        or not remaining
        or any(not isinstance(item, str) or not item for item in remaining)
        or remaining != sorted(set(remaining))
    ):
        raise FinalizeError("remaining production gates must be sorted unique strings")
    if spec_version == 1:
        layers = layout.get("extension_layers")
        if layers != ["base", "shift"]:
            raise FinalizeError("layout extension_layers must be exactly base and shift")
        if layout.get("operation") != "insert_row_before_actions":
            raise FinalizeError("unsupported layout milestone operation")
        row = layout.get("extension_row")
        if not isinstance(row, list) or not row:
            raise FinalizeError("layout extension_row must be a non-empty array")
    else:
        operations = layout.get("operations")
        if not isinstance(operations, list) or not operations:
            raise FinalizeError("layout operations must be a non-empty array")
        if len(operations) > 16:
            raise FinalizeError("layout operations exceed the bounded maximum")
        previous_key: tuple[str, str, int, int] | None = None
        targets: set[tuple[str, str, int, int]] = set()
        for index, operation in enumerate(operations):
            location = f"spec.layout.operations[{index}]"
            if not isinstance(operation, dict):
                raise FinalizeError(f"{location} must be an object")
            kind = _required_string(operation, "kind", location)
            layer_id = _required_string(operation, "layer_id", location)
            if layer_id not in {"base", "shift", "symbols", "numeric"}:
                raise FinalizeError(f"{location}.layer_id is unsupported")
            if kind == "insert_row_before_actions":
                _exact_fields(operation, {"kind", "layer_id", "row"}, location)
                row = operation.get("row")
                if not isinstance(row, list) or not row:
                    raise FinalizeError(f"{location}.row must be a non-empty array")
                row_index = -1
                key_index = -1
                target_kind = "insert_row_before_actions"
            elif kind == "append_keys_to_row":
                _exact_fields(
                    operation,
                    {"keys", "kind", "layer_id", "row_index"},
                    location,
                )
                row_index = operation.get("row_index")
                if (
                    isinstance(row_index, bool)
                    or not isinstance(row_index, int)
                    or row_index < 0
                ):
                    raise FinalizeError(f"{location}.row_index must be non-negative")
                keys = operation.get("keys")
                if not isinstance(keys, list) or not keys:
                    raise FinalizeError(f"{location}.keys must be a non-empty array")
                key_index = -1
                target_kind = "row"
            elif kind == "replace_key":
                _exact_fields(
                    operation,
                    {"key", "key_index", "kind", "layer_id", "row_index"},
                    location,
                )
                row_index = operation.get("row_index")
                key_index = operation.get("key_index")
                for field, value in (("row_index", row_index), ("key_index", key_index)):
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        raise FinalizeError(f"{location}.{field} must be non-negative")
                key = operation.get("key")
                if not isinstance(key, (str, dict)) or not key:
                    raise FinalizeError(f"{location}.key must be a non-empty key value")
                target_kind = "key"
            else:
                raise FinalizeError(f"{location}.kind is unsupported")
            sort_key = (layer_id, kind, row_index, key_index)
            if previous_key is not None and sort_key <= previous_key:
                raise FinalizeError("layout operations must be strictly sorted")
            previous_key = sort_key
            target = (layer_id, target_kind, row_index, key_index)
            if target in targets:
                raise FinalizeError("layout operations contain a duplicate target")
            targets.add(target)
    provenance = layout.get("provenance")
    if (
        not isinstance(provenance, list)
        or not provenance
        or any(not isinstance(item, dict) for item in provenance)
    ):
        raise FinalizeError("layout provenance must be a non-empty array of objects")
    return spec, spec_bytes


def _verify_resource_catalog(
    catalog_path: Path,
    spec: dict[str, Any],
    raw_input: Path,
    auxiliary_input: Path | None,
) -> dict[str, Any]:
    catalog = _read_json_object(catalog_path, "resource catalog")
    pack_spec = _required_object(spec, "pack", "spec")
    profile_spec = _required_object(spec, "profile", "spec")
    source_spec = _required_object(spec, "source", "spec")
    targets = catalog.get("packs")
    if not isinstance(targets, list):
        raise FinalizeError("resource catalog packs must be an array")
    matches = [row for row in targets if isinstance(row, dict) and row.get("id") == profile_spec["target_id"]]
    if len(matches) != 1:
        raise FinalizeError("resource catalog must contain exactly one milestone target")
    target = matches[0]
    if target.get("iso_639_3") != pack_spec["language"]:
        raise FinalizeError("resource catalog target language does not match pack")
    methods = target.get("input_methods")
    if not isinstance(methods, list) or not any(
        isinstance(row, dict)
        and row.get("id") == profile_spec["input_method_id"]
        and row.get("type") == "direct"
        and row.get("source_script") == pack_spec["output_script"]
        and row.get("output_script") == pack_spec["output_script"]
        for row in methods
    ):
        raise FinalizeError("resource catalog direct input method does not match spec")
    resources = target.get("resources")
    if not isinstance(resources, list):
        raise FinalizeError("resource catalog target resources must be an array")
    rows = [row for row in resources if isinstance(row, dict) and row.get("id") == source_spec["resource_id"]]
    if len(rows) != 1:
        raise FinalizeError("resource catalog must contain exactly one pinned source resource")
    resource = rows[0]
    raw_bytes = _read_bytes(raw_input, "raw dictionary")
    expected = {
        "sha256": source_spec["sha256"],
        "records": source_spec["expected_data_rows"],
        "bytes": len(raw_bytes),
    }
    for key, value in expected.items():
        if resource.get(key) != value:
            raise FinalizeError(f"resource catalog {key} does not match pinned raw source")
    if Path(str(resource.get("path", ""))).name != source_spec["file_name"]:
        raise FinalizeError("resource catalog source filename does not match spec")
    actual_sha = _sha256_bytes(raw_bytes)
    if actual_sha != source_spec["sha256"]:
        raise FinalizeError(
            f"raw dictionary SHA-256 mismatch: expected {source_spec['sha256']}, got {actual_sha}"
        )
    result: dict[str, Any] = {
        "bytes": len(raw_bytes),
        "path": source_spec["file_name"],
        "records": source_spec["expected_data_rows"],
        "resource_id": source_spec["resource_id"],
        "sha256": actual_sha,
    }
    if spec["spec_version"] == 4:
        auxiliary_spec = _required_object(
            source_spec,
            "auxiliary_input",
            "spec.source",
        )
        if auxiliary_input is None:
            raise FinalizeError("milestone spec v4 requires --auxiliary-input")
        auxiliary_bytes = _read_bytes(auxiliary_input, "auxiliary adapter input")
        auxiliary_sha256 = _sha256_bytes(auxiliary_bytes)
        if len(auxiliary_bytes) != auxiliary_spec["bytes"]:
            raise FinalizeError("auxiliary input byte count does not match milestone spec")
        if auxiliary_sha256 != auxiliary_spec["sha256"]:
            raise FinalizeError("auxiliary input SHA-256 does not match milestone spec")
        if auxiliary_input.name != auxiliary_spec["file_name"]:
            raise FinalizeError("auxiliary input filename does not match milestone spec")
        auxiliary_rows = [
            row
            for row in resources
            if isinstance(row, dict)
            and row.get("id") == auxiliary_spec["resource_id"]
        ]
        if len(auxiliary_rows) != 1:
            raise FinalizeError(
                "resource catalog must contain exactly one auxiliary source resource"
            )
        auxiliary_resource = auxiliary_rows[0]
        for key, expected_value in (
            ("bytes", len(auxiliary_bytes)),
            ("sha256", auxiliary_sha256),
        ):
            if auxiliary_resource.get(key) != expected_value:
                raise FinalizeError(
                    f"auxiliary resource catalog {key} does not match pinned input"
                )
        if Path(str(auxiliary_resource.get("path", ""))).name != auxiliary_spec["file_name"]:
            raise FinalizeError(
                "auxiliary resource catalog filename does not match milestone spec"
            )
        result["auxiliary_input"] = {
            "argument": auxiliary_spec["argument"],
            "bytes": len(auxiliary_bytes),
            "path": auxiliary_spec["file_name"],
            "resource_id": auxiliary_spec["resource_id"],
            "sha256": auxiliary_sha256,
        }
    elif auxiliary_input is not None:
        raise FinalizeError("--auxiliary-input is only valid for milestone spec v4")
    return result


def _load_adapter(spec: dict[str, Any]) -> ModuleType:
    adapter_spec = _required_object(spec, "adapter", "spec")
    adapter_path = REPOSITORY_ROOT / adapter_spec["path"]
    _regular_file(adapter_path, "adapter source")
    if _sha256_file(adapter_path) != adapter_spec["sha256"]:
        raise FinalizeError("adapter source SHA-256 does not match milestone spec")
    try:
        module = importlib.import_module(adapter_spec["module"])
    except (ImportError, ValueError) as exc:
        raise FinalizeError(f"cannot import milestone adapter: {exc}") from exc
    loaded_source = inspect.getsourcefile(module)
    if loaded_source is None or Path(loaded_source).resolve() != adapter_path.resolve():
        raise FinalizeError("loaded adapter is not the repository-pinned source")
    build = getattr(module, "build_internal_source", None)
    if not callable(build):
        raise FinalizeError("adapter module has no callable build_internal_source")
    source_spec = _required_object(spec, "source", "spec")
    pack_spec = _required_object(spec, "pack", "spec")
    expected_constants = {
        "PACK_ID": pack_spec["pack_id"],
        "SOURCE_SHA256": source_spec["sha256"],
        "EXPECTED_DATA_ROWS": source_spec["expected_data_rows"],
    }
    for name, expected in expected_constants.items():
        if getattr(module, name, None) != expected:
            raise FinalizeError(f"adapter constant {name} does not match milestone spec")
    if spec["spec_version"] == 4:
        auxiliary_spec = _required_object(
            source_spec,
            "auxiliary_input",
            "spec.source",
        )
        if getattr(module, "TRANSLITERATOR_SHA256", None) != auxiliary_spec["sha256"]:
            raise FinalizeError(
                "adapter constant TRANSLITERATOR_SHA256 does not match milestone spec"
            )
    return module


def _regenerate_and_compare_sources(
    module: ModuleType,
    spec: dict[str, Any],
    raw_input: Path,
    auxiliary_input: Path | None,
    source_a: Path,
    source_b: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    inventory_a, inventory_b = _compare_source_trees(source_a, source_b)
    adapter_spec = _required_object(spec, "adapter", "spec")
    source_spec = _required_object(spec, "source", "spec")
    with tempfile.TemporaryDirectory(prefix="nepa-internal-adapter-v1-") as temporary:
        regenerated = Path(temporary) / "source"
        namespace_values: dict[str, object] = {
            adapter_spec["input_argument"]: raw_input,
            "output": regenerated,
            "data_version": source_spec["data_version"],
            "max_suggestions": source_spec["max_suggestions"],
        }
        if spec["spec_version"] == 4:
            auxiliary_spec = _required_object(
                source_spec,
                "auxiliary_input",
                "spec.source",
            )
            if auxiliary_input is None:
                raise FinalizeError("milestone spec v4 requires --auxiliary-input")
            namespace_values[auxiliary_spec["argument"]] = auxiliary_input
        try:
            report = module.build_internal_source(argparse.Namespace(**namespace_values))
        except Exception as exc:
            adapter_error = getattr(module, "AdapterError", ValueError)
            if isinstance(exc, (adapter_error, OSError, UnicodeError, ValueError)):
                raise FinalizeError(f"current adapter could not regenerate source: {exc}") from exc
            raise
        regenerated_inventory = _tree_inventory(regenerated)
        if regenerated_inventory != inventory_a:
            raise FinalizeError("provided source trees are not derived from the pinned raw dictionary")
        for supplied in (source_a, source_b):
            for name in sorted(SOURCE_FILES):
                if not filecmp.cmp(regenerated / name, supplied / name, shallow=False):
                    raise FinalizeError(
                        f"provided source member is not adapter-derived: {name}"
                    )
        report_file = _read_json_object(regenerated / "adapter-report.json", "regenerated adapter report")
        if report != report_file:
            raise FinalizeError("adapter return value does not match adapter-report.json")
    if report_file.get("adapter") != adapter_spec["name"]:
        raise FinalizeError("adapter report name does not match milestone spec")
    if report_file.get("adapter_version") != adapter_spec["version"]:
        raise FinalizeError("adapter report version does not match milestone spec")
    if report_file.get("adapter_sha256") != adapter_spec["sha256"]:
        raise FinalizeError("adapter report SHA-256 does not match milestone spec")
    return inventory_a, report_file


def _loaded_compiler_source() -> Path:
    source = inspect.getsourcefile(compile_pack)
    if source is None:
        raise FinalizeError("cannot identify the loaded pack compiler source")
    loaded = Path(source).resolve()
    expected = (REPOSITORY_ROOT / "src/nepa_keyboard/compiler.py").resolve()
    if loaded != expected:
        raise FinalizeError(
            f"loaded pack compiler is not the repository source: {loaded} != {expected}"
        )
    return loaded


def _verified_pack(
    path: Path,
    spec: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    _regular_file(path, "NKP")
    pack_spec = _required_object(spec, "pack", "spec")
    if path.name != pack_spec["file_name"]:
        raise FinalizeError(f"NKP has unexpected filename: {path.name}")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise FinalizeError(f"NKP contains duplicate members: {path}")
            if set(names) != PACK_MEMBERS:
                raise FinalizeError(
                    f"NKP member set mismatch: expected {sorted(PACK_MEMBERS)}, got {sorted(names)}"
                )
            if archive.comment:
                raise FinalizeError("NKP ZIP comment must be empty")
            if any(
                info.is_dir()
                or info.compress_type != zipfile.ZIP_STORED
                or info.extra
                for info in infos
            ):
                raise FinalizeError("NKP members must be regular ZIP-STORE entries without extras")
            members = {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise FinalizeError(f"cannot verify NKP {path}: {exc}") from exc
    try:
        manifest = json.loads(members["manifest.json"].decode("utf-8"))
        notices = json.loads(members["notices.json"].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"NKP metadata is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(notices, dict):
        raise FinalizeError("NKP metadata roots must be objects")
    if _required_exact_int(manifest, "format_version", "manifest") != 0:
        raise FinalizeError("NKP does not use pack format v0")
    if _required_string(manifest, "release_mode", "manifest") != "internal":
        raise FinalizeError("NKP is not release_mode=internal")
    if _required_string(notices, "release_mode", "notices") != "internal":
        raise FinalizeError("NKP notices are not release_mode=internal")
    manifest_pack = _required_object(manifest, "pack", "manifest")
    for key in ("pack_id", "language", "output_script", "artifact_license"):
        if manifest_pack.get(key) != pack_spec[key]:
            raise FinalizeError(f"manifest.pack.{key} does not match milestone spec")
    source_spec = _required_object(spec, "source", "spec")
    if manifest_pack.get("data_version") != source_spec["data_version"]:
        raise FinalizeError("manifest data version does not match milestone spec")
    if manifest_pack.get("max_suggestions") != source_spec["max_suggestions"]:
        raise FinalizeError("manifest max suggestions does not match milestone spec")
    declared = _required_object(manifest, "members", "manifest")
    if set(declared) != VERIFIED_MEMBERS:
        raise FinalizeError("manifest member allowlist does not match pack format v0")
    for name in sorted(VERIFIED_MEMBERS):
        metadata = _required_object(declared, name, "manifest.members")
        expected_bytes = _required_exact_int(metadata, "bytes", f"manifest.members.{name}")
        expected_sha = _required_sha256(metadata, "sha256", f"manifest.members.{name}")
        if expected_bytes != len(members[name]) or expected_sha != _sha256_bytes(members[name]):
            raise FinalizeError(f"manifest member identity mismatch: {name}")
    counts = _required_object(manifest, "counts", "manifest")
    indexes = _required_object(manifest, "indexes", "manifest")
    surface = _required_object(indexes, "surface", "manifest.indexes")
    aliases = _required_object(indexes, "aliases", "manifest.indexes")
    candidate_count = _required_exact_int(counts, "candidate_surfaces", "manifest.counts")
    surface_key_count = _required_exact_int(surface, "keys", "manifest.indexes.surface")
    alias_key_count = _required_exact_int(aliases, "keys", "manifest.indexes.aliases")
    if candidate_count < 1 or surface_key_count < 1 or alias_key_count != 0:
        raise FinalizeError("direct pack must be a non-empty surface-only pack")
    artifact = {
        "artifact_bytes": path.stat().st_size,
        "artifact_sha256": _sha256_file(path),
        "file_name": pack_spec["file_name"],
    }
    return manifest, artifact


def _normalized_compiler_report(pack_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    report_path = pack_path.with_suffix(pack_path.suffix + ".report.json")
    report = _read_json_object(report_path, "compiler report")
    if report.get("manifest") != manifest:
        raise FinalizeError(f"compiler report manifest does not match NKP: {report_path}")
    if report.get("artifact_sha256") != _sha256_file(pack_path):
        raise FinalizeError(f"compiler report artifact hash does not match NKP: {report_path}")
    if report.get("artifact_bytes") != pack_path.stat().st_size:
        raise FinalizeError(f"compiler report artifact size does not match NKP: {report_path}")
    normalized = copy.deepcopy(report)
    normalized.pop("artifact", None)
    return normalized


def _verify_packs_and_compiler(
    source_a: Path,
    source_b: Path,
    pack_a: Path,
    pack_b: Path,
    spec: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _require_distinct(pack_a, pack_b, "NKP")
    report_a_path = pack_a.with_suffix(pack_a.suffix + ".report.json")
    report_b_path = pack_b.with_suffix(pack_b.suffix + ".report.json")
    _require_distinct(report_a_path, report_b_path, "compiler report")
    manifest_a, artifact_a = _verified_pack(pack_a, spec)
    manifest_b, artifact_b = _verified_pack(pack_b, spec)
    if manifest_a != manifest_b or artifact_a != artifact_b:
        raise FinalizeError("the two compiled NKPs have different manifests or identities")
    if not filecmp.cmp(pack_a, pack_b, shallow=False):
        raise FinalizeError("the two compiled NKPs are not byte-identical")
    compiler_a = _normalized_compiler_report(pack_a, manifest_a)
    compiler_b = _normalized_compiler_report(pack_b, manifest_b)
    if compiler_a != compiler_b:
        raise FinalizeError("normalized compiler reports are not identical")
    pack_spec = _required_object(spec, "pack", "spec")
    with tempfile.TemporaryDirectory(prefix="nepa-internal-compiler-v1-") as temporary:
        root = Path(temporary)
        for label, source, supplied in (
            ("a", source_a, pack_a),
            ("b", source_b, pack_b),
        ):
            output = root / label / pack_spec["file_name"]
            try:
                rebuilt = compile_pack(source, output, "internal")
            except (OSError, PackValidationError, ValueError) as exc:
                raise FinalizeError(f"current compiler could not rebuild run {label}: {exc}") from exc
            if not filecmp.cmp(output, supplied, shallow=False):
                raise FinalizeError(f"run {label} NKP is not derived by the current compiler")
            normalized = copy.deepcopy(rebuilt)
            normalized.pop("artifact", None)
            if normalized != compiler_a:
                raise FinalizeError(f"run {label} compiler report is not source-derived")
    return manifest_a, artifact_a, compiler_a


def _query_selection(path: Path) -> tuple[str, list[str], str]:
    encoded = _read_bytes(path, "query selection")
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"invalid query selection: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"benchmark_queries", "validation_query"}:
        raise FinalizeError("query selection must contain exactly validation_query and benchmark_queries")
    if encoded != _canonical_bytes(value):
        raise FinalizeError("query selection is not canonical UTF-8 JSON")
    validation = value.get("validation_query")
    benchmarks = value.get("benchmark_queries")
    if not isinstance(validation, str) or not validation:
        raise FinalizeError("validation query must be a non-empty string")
    if (
        not isinstance(benchmarks, list)
        or not 1 <= len(benchmarks) <= 64
        or any(not isinstance(item, str) or not item for item in benchmarks)
    ):
        raise FinalizeError("benchmark queries must contain 1..64 non-empty strings")
    all_queries = [validation, *benchmarks]
    if len(all_queries) != len(set(all_queries)):
        raise FinalizeError("validation and benchmark queries must be unique")
    for query in all_queries:
        if unicodedata.normalize("NFC", query) != query or query.strip() != query:
            raise FinalizeError("queries must be trimmed NFC")
        if any(character.isspace() for character in query):
            raise FinalizeError("queries must not contain whitespace boundaries")
    return validation, benchmarks, _sha256_bytes(encoded)


def _run_queries(
    pack_path: Path,
    validation_query: str,
    benchmark_queries: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    def run(pack: KeyboardPack, query: str) -> dict[str, Any]:
        rows = pack.lookup(query, "surface")
        if not rows:
            raise FinalizeError(f"pack query has no candidates: {query!r}")
        surfaces = [str(row["surface"]) for row in rows]
        return {
            "returned_candidate_count": len(surfaces),
            "expected_surface": surfaces[0],
            "query": query,
            "top_surfaces": surfaces,
        }
    try:
        with KeyboardPack(pack_path) as pack:
            validation = run(pack, validation_query)
            benchmark = [run(pack, query) for query in benchmark_queries]
    except (OSError, ValueError) as exc:
        raise FinalizeError(f"cannot query verified NKP: {exc}") from exc
    return validation, benchmark


def _verify_layout(spec: dict[str, Any]) -> dict[str, Any]:
    layout_spec = _required_object(spec, "layout", "spec")
    paths = _required_object(spec, "paths", "spec")
    base_path = REPOSITORY_ROOT / layout_spec["base_path"]
    layout_path = REPOSITORY_ROOT / paths["layout_source"]
    if _sha256_file(base_path) != layout_spec["base_sha256"]:
        raise FinalizeError("base layout SHA-256 does not match milestone spec")
    if _sha256_file(layout_path) != layout_spec["source_sha256"]:
        raise FinalizeError("extended layout SHA-256 does not match milestone spec")
    base = _read_json_object(base_path, "base layout")
    layout = _read_json_object(layout_path, "extended layout")
    if layout.get("layout_id") != layout_spec["layout_id"]:
        raise FinalizeError("extended layout ID does not match milestone spec")
    if layout.get("revision") != layout_spec["revision"]:
        raise FinalizeError("extended layout revision does not match milestone spec")
    base_layers = _required_object(base, "layers", "base layout")
    expected = copy.deepcopy(base)
    expected["layout_id"] = layout_spec["layout_id"]
    expected["revision"] = layout_spec["revision"]
    expected["display_name"] = layout_spec["display_name"]
    expected["provenance"] = copy.deepcopy(layout_spec["provenance"])
    if spec["spec_version"] in {3, 4}:
        license_override = layout_spec["license"]
        if license_override is None:
            expected.pop("license", None)
        else:
            expected["license"] = copy.deepcopy(license_override)
    else:
        expected_license = _required_object(expected, "license", "expected layout")
        expected_license["notice_path"] = layout_spec["license_notice_path"]
        if spec["spec_version"] == 2:
            expected_license["notice_sha256"] = layout_spec["license_notice_sha256"]
    expected_layers = _required_object(expected, "layers", "expected layout")
    if spec["spec_version"] == 1:
        extension_row = layout_spec["extension_row"]
        extension_layers = set(layout_spec["extension_layers"])
        for layer_id in sorted(base_layers):
            expected_layer = expected_layers[layer_id]
            if not isinstance(expected_layer, dict):
                raise FinalizeError("layout layers must be objects")
            if layer_id in extension_layers:
                rows = expected_layer.get("rows")
                if not isinstance(rows, list) or not rows:
                    raise FinalizeError(f"base layer {layer_id} has no action row")
                rows.insert(len(rows) - 1, copy.deepcopy(extension_row))
    else:
        for operation in layout_spec["operations"]:
            layer_id = operation["layer_id"]
            expected_layer = expected_layers.get(layer_id)
            if not isinstance(expected_layer, dict):
                raise FinalizeError(f"base layout has no object layer {layer_id}")
            rows = expected_layer.get("rows")
            if not isinstance(rows, list) or not rows:
                raise FinalizeError(f"base layer {layer_id} has no rows")
            if operation["kind"] == "insert_row_before_actions":
                rows.insert(len(rows) - 1, copy.deepcopy(operation["row"]))
                continue
            row_index = operation["row_index"]
            if row_index >= len(rows) - 1:
                raise FinalizeError(
                    f"layout operation row index reaches action row: {layer_id}"
                )
            row = rows[row_index]
            if not isinstance(row, list) or not row:
                raise FinalizeError(
                    f"base layer row is not a non-empty array: {layer_id}[{row_index}]"
                )
            if operation["kind"] == "append_keys_to_row":
                row.extend(copy.deepcopy(operation["keys"]))
                continue
            key_index = operation["key_index"]
            if key_index >= len(row):
                raise FinalizeError(
                    "layout operation key index is outside base row: "
                    f"{layer_id}[{row_index}][{key_index}]"
                )
            row[key_index] = copy.deepcopy(operation["key"])
    if layout != expected:
        raise FinalizeError("extended layout is not the exact declared base transformation")
    if spec["spec_version"] in {3, 4}:
        layout_license = layout_spec["license"]
        if layout_license is not None and "notice_path" in layout_license:
            notice_path = REPOSITORY_ROOT / layout_license["notice_path"]
            if _sha256_file(notice_path) != layout_license["notice_sha256"]:
                raise FinalizeError(
                    "extended layout notice bytes do not match notice_sha256"
                )
    else:
        layout_license = _required_object(layout, "license", "extended layout")
        notice_relative = Path(layout_spec["license_notice_path"])
        if notice_relative.is_absolute() or ".." in notice_relative.parts:
            raise FinalizeError("layout notice path must be repository-relative")
        notice_path = REPOSITORY_ROOT / notice_relative
        if _sha256_file(notice_path) != layout_license.get("notice_sha256"):
            raise FinalizeError(
                "extended layout notice bytes do not match notice_sha256"
            )
    provenance = layout.get("provenance")
    for row in provenance:
        source = row.get("source") if isinstance(row, dict) else None
        sha256 = row.get("sha256") if isinstance(row, dict) else None
        if not isinstance(source, str) or not SHA256_RE.fullmatch(str(sha256 or "")):
            raise FinalizeError("layout provenance rows must pin a source SHA-256")
        source_path = Path(source)
        if source_path.is_absolute() or ".." in source_path.parts:
            raise FinalizeError("layout provenance source must be repository-relative")
        if _sha256_file(REPOSITORY_ROOT / source_path) != sha256:
            raise FinalizeError(f"layout provenance source hash mismatch: {source}")
    return {
        "layout_id": layout_spec["layout_id"],
        "revision": layout_spec["revision"],
        "source_path": paths["layout_source"],
        "source_sha256": layout_spec["source_sha256"],
    }


def _build_evidence(
    args: argparse.Namespace,
    spec: dict[str, Any],
    spec_bytes: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = _required_object(spec, "paths", "spec")
    catalog_path = REPOSITORY_ROOT / paths["resource_catalog"]
    query_path = REPOSITORY_ROOT / paths["queries"]
    raw = _verify_resource_catalog(
        catalog_path,
        spec,
        args.raw_input,
        args.auxiliary_input,
    )
    adapter = _load_adapter(spec)
    source_inventory, adapter_report = _regenerate_and_compare_sources(
        adapter,
        spec,
        args.raw_input,
        args.auxiliary_input,
        args.source_a,
        args.source_b,
    )
    compiler_source = _loaded_compiler_source()
    manifest, artifact, compiler_report = _verify_packs_and_compiler(
        args.source_a,
        args.source_b,
        args.pack_a,
        args.pack_b,
        spec,
    )
    validation_query, benchmark_queries, query_sha = _query_selection(query_path)
    validation, benchmark = _run_queries(args.pack_a, validation_query, benchmark_queries)
    layout = _verify_layout(spec)
    pack_spec = _required_object(spec, "pack", "spec")
    profile_spec = _required_object(spec, "profile", "spec")
    evidence_spec = _required_object(spec, "evidence", "spec")
    source_spec = _required_object(spec, "source", "spec")
    if spec["spec_version"] == 4:
        measurement = _required_object(
            adapter_report,
            "measurement",
            "adapter report",
        )
        report_stats = _required_object(
            measurement,
            "stats",
            "adapter report.measurement",
        )
        source_summary = {
            "accepted_rows": _required_exact_int(
                report_stats,
                "accepted_rows",
                "adapter report.measurement.stats",
            ),
            "data_version": source_spec["data_version"],
            "distinct_accepted_surfaces": _required_exact_int(
                report_stats,
                "distinct_generated_surfaces",
                "adapter report.measurement.stats",
            ),
            "rejected_rows": 0,
        }
    else:
        source_summary = {
            "accepted_rows": adapter_report["stats"]["accepted_rows"],
            "data_version": source_spec["data_version"],
            "distinct_accepted_surfaces": adapter_report["stats"]["distinct_accepted_surfaces"],
            "rejected_rows": adapter_report["stats"]["rejected_rows"],
        }
    evidence = {
        "adapter": {
            "name": spec["adapter"]["name"],
            "report_sha256": _sha256_bytes(_canonical_bytes(adapter_report)),
            "source_path": spec["adapter"]["path"],
            "source_sha256": spec["adapter"]["sha256"],
            "version": spec["adapter"]["version"],
        },
        "compiler": {
            "normalized_report_sha256": _sha256_bytes(_canonical_bytes(compiler_report)),
            "source_path": "src/nepa_keyboard/compiler.py",
            "source_sha256": _sha256_file(compiler_source),
        },
        "determinism": {
            "adapter_regeneration_matches_both_sources": True,
            "compiler_reports_identical": True,
            "current_compiler_rebuild_matches_both_packs": True,
            "pack_a_sha256": artifact["artifact_sha256"],
            "pack_b_sha256": artifact["artifact_sha256"],
            "packs_byte_identical": True,
            "source_a_tree_sha256": source_inventory["tree_sha256"],
            "source_b_tree_sha256": source_inventory["tree_sha256"],
            "source_trees_byte_identical": True,
        },
        "gates": {
            "passed": list(INTERNAL_GATES),
            "remaining_production": evidence_spec["remaining_production_gates"],
        },
        "layout": layout,
        "pack": {
            **artifact,
            "allowed_format_characters": manifest["pack"].get("allowed_format_characters", []),
            "alias_key_count": manifest["indexes"]["aliases"]["keys"],
            "artifact_license": manifest["pack"]["artifact_license"],
            "candidate_count": manifest["counts"]["candidate_surfaces"],
            "data_version": manifest["pack"]["data_version"],
            "language": manifest["pack"]["language"],
            "output_script": manifest["pack"]["output_script"],
            "pack_id": manifest["pack"]["pack_id"],
            "release_mode": manifest["release_mode"],
            "source_form_count": manifest["counts"]["source_forms"],
            "surface_key_count": manifest["indexes"]["surface"]["keys"],
        },
        "profile_id": pack_spec["pack_id"],
        "queries": {
            "benchmark": benchmark,
            "selection_path": paths["queries"],
            "selection_sha256": query_sha,
            "validation": validation,
        },
        "raw_source": raw,
        "report_id": evidence_spec["report_id"],
        "report_version": evidence_spec["report_version"],
        "reviewed_at": args.reviewed_at,
        "source": source_summary,
        "spec": {
            "path": str(args.spec.resolve().relative_to(REPOSITORY_ROOT)),
            "sha256": _sha256_bytes(spec_bytes),
        },
        "status": "passed",
        "target_id": profile_spec["target_id"],
    }
    return evidence, manifest


def _validate_review_with_catalog(
    review: dict[str, Any],
    spec: dict[str, Any],
) -> None:
    paths = _required_object(spec, "paths", "spec")
    catalog_path = REPOSITORY_ROOT / paths["resource_catalog"]
    catalog = _read_json_object(catalog_path, "resource catalog")
    review_bytes = _canonical_bytes(review)
    compiler_path = REPOSITORY_ROOT / "tools/build_shipping_profile_catalog.py"
    schema_paths = {
        "catalog": REPOSITORY_ROOT / "schemas/resource-catalog.schema.json",
        "review": REPOSITORY_ROOT / "schemas/shipping-profile-review.schema.json",
        "lock": REPOSITORY_ROOT / "schemas/shipping-profile-lock.schema.json",
    }
    try:
        lock = build_lock(
            catalog,
            review,
            catalog_path=paths["resource_catalog"],
            review_path=paths["review"],
            catalog_sha256=_sha256_file(catalog_path),
            review_sha256=_sha256_bytes(review_bytes),
            compiler_reference={
                "path": "tools/build_shipping_profile_catalog.py",
                "sha256": _sha256_file(compiler_path),
            },
            schema_references={
                name: {
                    "path": str(path.relative_to(REPOSITORY_ROOT)),
                    "sha256": _sha256_file(path),
                }
                for name, path in schema_paths.items()
            },
        )
    except CatalogError as exc:
        raise FinalizeError(f"generated cumulative review is invalid: {exc}") from exc
    pack_id = spec["pack"]["pack_id"]
    matches = [row for row in lock["profiles"] if row.get("profile_id") == pack_id]
    if len(matches) != 1 or not matches[0].get("selectable"):
        raise FinalizeError("generated cumulative review does not select the milestone profile")


def _build_review(
    args: argparse.Namespace,
    spec: dict[str, Any],
    evidence: dict[str, Any],
    evidence_bytes: bytes,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    review = _read_json_object(args.review_input, "cumulative internal review")
    if review.get("authority") != "internal":
        raise FinalizeError("review input must use internal authority")
    if review.get("review_version") != 1:
        raise FinalizeError("review input must use version 1")
    profile_overrides = review.get("profile_overrides")
    evidence_rows = review.get("evidence")
    expected_counts = review.get("expected_counts")
    if not isinstance(profile_overrides, dict) or not isinstance(evidence_rows, list):
        raise FinalizeError("review input has invalid profile overrides or evidence")
    if not isinstance(expected_counts, dict):
        raise FinalizeError("review input has invalid expected counts")
    pack_spec = spec["pack"]
    profile_spec = spec["profile"]
    layout = evidence["layout"]
    evidence_id = f"{pack_spec['language']}-direct-internal-{args.reviewed_at}"
    override = {
        "default_enabled": profile_spec["default_enabled"],
        "evidence_ids": [evidence_id],
        "layout_id": layout["layout_id"],
        "pack_binding": pack_spec["pack_id"],
        "profile_id": pack_spec["pack_id"],
        "selectable": True,
    }
    existing_override = profile_overrides.get(profile_spec["input_method_id"])
    if existing_override is not None and existing_override != override:
        raise FinalizeError("refusing to overwrite a different existing profile override")
    profile_overrides[profile_spec["input_method_id"]] = override
    validation = evidence["queries"]["validation"]
    benchmark = evidence["queries"]["benchmark"]
    evidence_row = {
        "artifacts": [{
            "path": spec["paths"]["evidence_output"],
            "sha256": _sha256_bytes(evidence_bytes),
        }],
        "evidence_id": evidence_id,
        "gates": list(INTERNAL_GATES),
        "layout_binding": {
            "layout_id": layout["layout_id"],
            "revision": layout["revision"],
            "source_sha256": layout["source_sha256"],
        },
        "pack_artifact": {
            "alias_key_count": manifest["indexes"]["aliases"]["keys"],
            "artifact_license": manifest["pack"]["artifact_license"],
            "artifact_sha256": evidence["pack"]["artifact_sha256"],
            "candidate_count": manifest["counts"]["candidate_surfaces"],
            "file_name": pack_spec["file_name"],
            "language": pack_spec["language"],
            "output_script": pack_spec["output_script"],
            "pack_id": pack_spec["pack_id"],
            "release_mode": "internal",
            "surface_key_count": manifest["indexes"]["surface"]["keys"],
            "validation": {
                "benchmark_queries": [row["query"] for row in benchmark],
                "expected_surface": validation["expected_surface"],
                "query": validation["query"],
            },
        },
        "profile_id": pack_spec["pack_id"],
        "status": "passed",
    }
    by_id: dict[str, dict[str, Any]] = {}
    for row in evidence_rows:
        if not isinstance(row, dict) or not isinstance(row.get("evidence_id"), str):
            raise FinalizeError("review input contains malformed evidence")
        row_id = row["evidence_id"]
        if row_id in by_id:
            raise FinalizeError(f"review input contains duplicate evidence ID: {row_id}")
        by_id[row_id] = row
    existing_evidence = by_id.get(evidence_id)
    if existing_evidence is not None and existing_evidence != evidence_row:
        raise FinalizeError("refusing to overwrite a different existing evidence row")
    by_id[evidence_id] = evidence_row
    review["evidence"] = [by_id[key] for key in sorted(by_id)]
    review["reviewed_at"] = args.reviewed_at
    review["review_id"] = f"internal-profiles-{args.reviewed_at}"
    selectable = sum(
        isinstance(row, dict) and row.get("selectable") is True
        for row in profile_overrides.values()
    )
    expected_counts["selectable"] = selectable
    _validate_review_with_catalog(review, spec)
    return review


def _write_or_check(path: Path, encoded: bytes, check: bool) -> None:
    if path.is_symlink():
        raise FinalizeError(f"output must not be a symbolic link: {path}")
    if check:
        try:
            actual = path.read_bytes()
        except OSError as exc:
            raise FinalizeError(f"cannot check output {path}: {exc}") from exc
        if actual != encoded:
            raise FinalizeError(f"generated output is stale: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def finalize(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    if not DATE_RE.fullmatch(args.reviewed_at):
        raise FinalizeError("reviewed-at must be YYYY-MM-DD")
    spec, spec_bytes = _validate_spec(args.spec)
    paths = spec["paths"]
    _canonical_repo_path(
        REPOSITORY_ROOT / paths["resource_catalog"],
        paths["resource_catalog"],
        "resource catalog",
    )
    _canonical_repo_path(
        REPOSITORY_ROOT / paths["queries"],
        paths["queries"],
        "query selection",
    )
    _canonical_repo_path(
        REPOSITORY_ROOT / paths["layout_source"],
        paths["layout_source"],
        "layout source",
    )
    canonical_review = _canonical_repo_path(
        args.review_input,
        paths["review"],
        "review input",
    )
    if args.review_output.resolve() != canonical_review.resolve():
        raise FinalizeError(f"review output must use canonical path {canonical_review}")
    canonical_evidence = _canonical_repo_path(
        args.evidence_output,
        paths["evidence_output"],
        "evidence output",
    )
    if canonical_evidence.resolve() == canonical_review.resolve():
        raise FinalizeError("evidence and review outputs must be distinct")
    _regular_file(args.raw_input, "raw dictionary")
    if spec["spec_version"] == 4:
        if args.auxiliary_input is None:
            raise FinalizeError("milestone spec v4 requires --auxiliary-input")
        _regular_file(args.auxiliary_input, "auxiliary adapter input")
        _require_distinct(
            args.raw_input,
            args.auxiliary_input,
            "raw and auxiliary adapter inputs",
        )
    elif args.auxiliary_input is not None:
        raise FinalizeError("--auxiliary-input is only valid for milestone spec v4")
    evidence, manifest = _build_evidence(args, spec, spec_bytes)
    evidence_bytes = _canonical_bytes(evidence)
    review = _build_review(args, spec, evidence, evidence_bytes, manifest)
    review_bytes = _canonical_bytes(review)
    _write_or_check(args.evidence_output, evidence_bytes, args.check)
    _write_or_check(args.review_output, review_bytes, args.check)
    return evidence, review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--raw-input", type=Path, required=True)
    parser.add_argument("--auxiliary-input", type=Path)
    parser.add_argument("--source-a", type=Path, required=True)
    parser.add_argument("--source-b", type=Path, required=True)
    parser.add_argument("--pack-a", type=Path, required=True)
    parser.add_argument("--pack-b", type=Path, required=True)
    parser.add_argument("--review-input", type=Path, required=True)
    parser.add_argument("--review-output", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        evidence, review = finalize(args)
    except FinalizeError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "evidence_output": str(args.evidence_output),
        "evidence_sha256": _sha256_bytes(_canonical_bytes(evidence)),
        "review_output": str(args.review_output),
        "review_sha256": _sha256_bytes(_canonical_bytes(review)),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
