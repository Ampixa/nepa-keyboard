#!/usr/bin/env python3
"""Audit one catalog-pinned SIL-APK lexicon against a compiled layout.

The audit is intentionally read-only. It validates the strict SIL-APK row
contract through the shared adapter helper, evaluates both the conjunct-only
and terminal-ZWNJ policies, and distinguishes absent input scalars from
scalars that exist on the layout but terminate composition.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from tools import build_keyboard_layouts as layout_compiler
from tools import sil_apk_jsonl_internal_source as sil_apk


AUDITOR_NAME = "audit_sil_apk_layout_gap"
AUDITOR_VERSION = 1
CODE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = CODE_ROOT
REQUIRED_UNICODE_VERSION = "16.0.0"
LAYERS = ("base", "shift", "symbols", "numeric")
TEXT_FIELD_LAYERS = frozenset({"base", "shift", "symbols"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_DELTA_EXAMPLES = 32
MAX_REJECTION_EXAMPLES = 32
MAX_SCALAR_EXAMPLES = 8
EXPECTED_HELPER_NAME = "sil_apk_jsonl_internal_source"
EXPECTED_HELPER_VERSION = 1
EXPECTED_HELPER_SHA256 = "f520e65402412c0982875d12751808a74082452fd3b5d10fbafa9b7b11d580c3"
EXPECTED_LAYOUT_COMPILER_SHA256 = (
    "5c6b7eb27b8c97857d457397a43c459f814e44740871f9d78755a7bbe580e2bb"
)
COMPOSING_KINDS = frozenset({
    "orthographic_word",
    "intra_word_punctuation",
    "deva_conjunct_joiner",
    "deva_terminal_zwnj",
})


class AuditError(ValueError):
    """Raised when the audit inputs do not match their pinned contracts."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AuditError(f"{label} is not a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AuditError(f"cannot read {label} {path}: {exc}") from exc


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise AuditError(f"duplicate JSON key {key!r}")
        value[key] = child
    return value


def _read_json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    encoded = _read_regular(path, label)
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise AuditError(f"{label} must not contain a UTF-8 BOM")
    try:
        value = json.loads(encoded.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"invalid UTF-8 JSON in {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"{label} must be a JSON object: {path}")
    return value, encoded


def _repository_relative(path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise AuditError(f"{label} must be inside the repository") from exc


def _repository_reference(relative: object, label: str) -> tuple[Path, str]:
    if not isinstance(relative, str) or not relative:
        raise AuditError(f"{label} path must be a non-empty string")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise AuditError(f"{label} path must be repository-relative")
    resolved = REPOSITORY_ROOT / path
    if _repository_relative(resolved, label) != path.as_posix():
        raise AuditError(f"{label} path is not canonical")
    return resolved, path.as_posix()


def _required_string(value: dict[str, Any], key: str, location: str) -> str:
    child = value.get(key)
    if not isinstance(child, str) or not child:
        raise AuditError(f"{location}.{key} must be a non-empty string")
    return child


def _required_positive_int(value: dict[str, Any], key: str, location: str) -> int:
    child = value.get(key)
    if isinstance(child, bool) or not isinstance(child, int) or child < 1:
        raise AuditError(f"{location}.{key} must be a positive integer")
    return child


def _required_sha256(value: dict[str, Any], key: str, location: str) -> str:
    child = _required_string(value, key, location)
    if not SHA256_RE.fullmatch(child):
        raise AuditError(f"{location}.{key} must be a lowercase SHA-256")
    return child


def _verified_reference(
    reference: object,
    expected_path: str,
    location: str,
) -> dict[str, str]:
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        raise AuditError(f"{location} must contain exactly path and sha256")
    path, relative = _repository_reference(reference.get("path"), location)
    if relative != expected_path:
        raise AuditError(f"{location}.path must be {expected_path}")
    actual = _sha256_bytes(_read_regular(path, location))
    expected = _required_sha256(reference, "sha256", location)
    if actual != expected:
        raise AuditError(f"{location} SHA-256 does not match current source")
    return {"path": relative, "sha256": actual}


def _verify_helper_identity() -> tuple[Path, str]:
    if (
        sil_apk.HELPER_NAME != EXPECTED_HELPER_NAME
        or sil_apk.HELPER_VERSION != EXPECTED_HELPER_VERSION
    ):
        raise AuditError("loaded SIL-APK helper name or version is unsupported")
    helper_path = Path(sil_apk.__file__).resolve()
    expected_helper = CODE_ROOT / "tools" / "sil_apk_jsonl_internal_source.py"
    if helper_path != expected_helper.resolve():
        raise AuditError("loaded SIL-APK helper is not the canonical repository source")
    actual = _sha256_bytes(_read_regular(helper_path, "SIL-APK helper"))
    if actual != EXPECTED_HELPER_SHA256:
        raise AuditError(
            "SIL-APK helper SHA-256 mismatch: "
            f"expected {EXPECTED_HELPER_SHA256}, got {actual}"
        )
    return helper_path, actual


def _verify_layout_compiler_identity() -> tuple[Path, str]:
    compiler_path = Path(layout_compiler.__file__).resolve()
    expected_compiler = CODE_ROOT / "tools" / "build_keyboard_layouts.py"
    if compiler_path != expected_compiler.resolve():
        raise AuditError(
            "loaded layout compiler is not the canonical repository source"
        )
    actual = _sha256_bytes(_read_regular(compiler_path, "layout compiler"))
    if actual != EXPECTED_LAYOUT_COMPILER_SHA256:
        raise AuditError(
            "layout compiler SHA-256 mismatch: "
            f"expected {EXPECTED_LAYOUT_COMPILER_SHA256}, got {actual}"
        )
    return compiler_path, actual


def _verify_layout_lock(
    path: Path,
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    _compiler_path, loaded_compiler_sha256 = _verify_layout_compiler_identity()
    lock, encoded = _read_json_object(path, "layout lock")
    compiler_reference = _verified_reference(
        lock.get("compiler"),
        "tools/build_keyboard_layouts.py",
        "layout lock compiler",
    )
    if compiler_reference["sha256"] != loaded_compiler_sha256:
        raise AuditError("layout lock does not reference the loaded layout compiler")
    schemas = lock.get("schemas")
    if not isinstance(schemas, dict) or set(schemas) != {"source", "lock"}:
        raise AuditError("layout lock schemas must contain exactly source and lock")
    schema_references = {
        "source": _verified_reference(
            schemas.get("source"),
            "schemas/layout-v1.schema.json",
            "layout source schema",
        ),
        "lock": _verified_reference(
            schemas.get("lock"),
            "schemas/layout-lock-v1.schema.json",
            "layout lock schema",
        ),
    }
    profile_reference = lock.get("profile_lock")
    if (
        not isinstance(profile_reference, dict)
        or set(profile_reference) != {"path", "sha256"}
    ):
        raise AuditError("layout profile lock reference must contain path and sha256")
    profile_path, profile_relative = _repository_reference(
        profile_reference.get("path"),
        "layout profile lock",
    )
    profile_lock, profile_bytes = _read_json_object(profile_path, "profile lock")
    profile_sha256 = _sha256_bytes(profile_bytes)
    if profile_sha256 != _required_sha256(
        profile_reference,
        "sha256",
        "layout profile lock",
    ):
        raise AuditError("layout profile lock SHA-256 does not match current source")
    source_directory, source_relative = _repository_reference(
        lock.get("source_directory"),
        "layout source directory",
    )
    if source_directory.is_symlink() or not source_directory.is_dir():
        raise AuditError("layout source directory is not a regular directory")
    try:
        rebuilt = layout_compiler.build_lock(
            source_directory,
            profile_lock,
            profile_lock_path=profile_relative,
            profile_lock_sha256=profile_sha256,
            source_path_prefix=source_relative,
            compiler_reference=compiler_reference,
            schema_references=schema_references,
        )
    except layout_compiler.LayoutError as exc:
        raise AuditError(f"layout lock regeneration failed: {exc}") from exc
    if layout_compiler._canonical_bytes(rebuilt) != encoded:
        raise AuditError("layout lock is stale or not canonical")
    return lock, encoded, {
        "compiler": compiler_reference,
        "profile_lock_path": profile_relative,
        "profile_lock_sha256": profile_sha256,
        "schemas": schema_references,
        "source_directory": source_relative,
    }


def _catalog_binding(
    catalog: dict[str, Any],
    target_id: str,
    resource_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    packs = catalog.get("packs")
    if not isinstance(packs, list):
        raise AuditError("resource catalog packs must be an array")
    targets = [
        row for row in packs
        if isinstance(row, dict) and row.get("id") == target_id
    ]
    if len(targets) != 1:
        raise AuditError("resource catalog must contain exactly one target")
    target = targets[0]
    resources = target.get("resources")
    if not isinstance(resources, list):
        raise AuditError("resource catalog target resources must be an array")
    matches = [
        row for row in resources
        if isinstance(row, dict) and row.get("id") == resource_id
    ]
    if len(matches) != 1:
        raise AuditError("resource catalog must contain exactly one resource")
    resource = matches[0]
    if resource.get("kind") != "lexicon" or resource.get("format") != "JSONL":
        raise AuditError("SIL-APK audit resource must be a JSONL lexicon")
    if resource.get("structured") is not True:
        raise AuditError("SIL-APK audit resource must be structured")
    if resource.get("canonical") is not True:
        raise AuditError("SIL-APK audit resource must be canonical")
    uses = resource.get("uses")
    if not isinstance(uses, list) or "candidate_vocabulary" not in uses:
        raise AuditError(
            "SIL-APK audit resource must support candidate vocabulary"
        )
    if resource.get("record_unit") != "entries":
        raise AuditError("SIL-APK audit resource must count entries")
    sha256 = _required_string(resource, "sha256", "catalog resource")
    if not SHA256_RE.fullmatch(sha256):
        raise AuditError("catalog resource SHA-256 is malformed")
    _required_positive_int(resource, "records", "catalog resource")
    _required_positive_int(resource, "bytes", "catalog resource")
    _required_string(target, "iso_639_3", "catalog target")
    _required_string(target, "name", "catalog target")
    return target, resource


def _layout_binding(
    lock: dict[str, Any],
    layout_id: str,
) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]]]:
    layouts = lock.get("layouts")
    if not isinstance(layouts, list):
        raise AuditError("layout lock layouts must be an array")
    matches = [
        row for row in layouts
        if isinstance(row, dict) and row.get("layout_id") == layout_id
    ]
    if len(matches) != 1:
        raise AuditError("layout lock must contain exactly one requested layout")
    layout = matches[0]
    if layout.get("input_script") != "Deva":
        raise AuditError("SIL-APK layout audit currently requires input script Deva")
    transforms = layout.get("transforms")
    if transforms != []:
        raise AuditError("layout audit does not claim runtime support for transforms")
    layers = layout.get("layers")
    if not isinstance(layers, dict) or set(layers) != set(LAYERS):
        raise AuditError("compiled layout must contain the four exact v1 layers")

    access: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for layer_id in LAYERS:
        layer = layers.get(layer_id)
        if not isinstance(layer, dict) or not isinstance(layer.get("rows"), list):
            raise AuditError(f"compiled layout {layout_id} has invalid {layer_id} rows")
        for row in layer["rows"]:
            if not isinstance(row, list):
                raise AuditError(f"compiled layout {layout_id} has a non-array row")
            for key in row:
                if not isinstance(key, dict):
                    raise AuditError(f"compiled layout {layout_id} has a non-object key")
                kind = _required_string(key, "kind", "compiled key")
                if kind == "action":
                    continue
                if kind not in layout_compiler.TEXT_KEY_KINDS:
                    raise AuditError(f"compiled key kind is unsupported: {kind}")
                text = _required_string(key, "text", "compiled key")
                if len(text) != 1:
                    raise AuditError(
                        "layout scalar audit requires one-scalar text key payloads"
                    )
                if key.get("action") is not None or key.get("hold_action") is not None:
                    raise AuditError("compiled text key cannot define an action or hold")
                if key.get("width_units") != 100:
                    raise AuditError("compiled text key width must be 100")
                if kind == "orthographic_word" and text != "\u2018":
                    raise AuditError("orthographic_word key must carry U+2018")
                if kind == "intra_word_punctuation" and text not in {"-", "/", "\\", ":"}:
                    raise AuditError(
                        "intra_word_punctuation key must carry hyphen, slash, backslash, or colon"
                    )
                if kind == "deva_conjunct_joiner" and text not in {"\u200c", "\u200d"}:
                    raise AuditError("deva_conjunct_joiner key has an invalid payload")
                if kind == "deva_terminal_zwnj" and text != "\u200c":
                    raise AuditError("deva_terminal_zwnj key must carry U+200C")
                key_id = _required_string(key, "key_id", "compiled key")
                if layer_id in TEXT_FIELD_LAYERS:
                    access[text].append({
                        "key_id": key_id,
                        "kind": kind,
                        "layer": layer_id,
                    })
    for rows in access.values():
        rows.sort(key=lambda row: (row["layer"], row["key_id"], row["kind"]))
    return layout, dict(access)


def _default_text_composes(character: str) -> bool:
    category = unicodedata.category(character)
    return category[0] in {"L", "M", "N"} or character in {"'", "\u2019"}


def _has_composing_access(
    character: str,
    access: dict[str, list[dict[str, str]]],
) -> bool:
    for row in access.get(character, []):
        kind = row["kind"]
        if kind in COMPOSING_KINDS:
            return True
        if kind == "text" and _default_text_composes(character):
            return True
    return False


def _key_valid_at_position(
    row: dict[str, str],
    surface: str,
    index: int,
    has_word_character: bool,
) -> bool:
    character = surface[index]
    kind = row["kind"]
    if kind == "text":
        category = unicodedata.category(character)
        return category[0] in {"L", "M", "N"} or (
            character in {"'", "\u2019"} and has_word_character
        )
    if kind == "orthographic_word":
        return character == "\u2018"
    if kind == "intra_word_punctuation":
        if index == 0:
            return False
        preceding_category = unicodedata.category(surface[index - 1])
        return preceding_category[0] in {"L", "M", "N"}
    if kind == "deva_conjunct_joiner":
        return sil_apk._is_valid_conjunct_joiner(surface, index)
    if kind == "deva_terminal_zwnj":
        return (
            sil_apk._is_valid_conjunct_joiner(surface, index)
            or sil_apk._is_valid_terminal_zwnj(surface, index)
        )
    return False


def _surface_gap(
    surface: str,
    access: dict[str, list[dict[str, str]]],
) -> dict[str, Any] | None:
    has_word_character = False
    for index, character in enumerate(surface):
        category = unicodedata.category(character)
        code_point = f"U+{ord(character):04X}"
        if character.isspace() or category.startswith("Z"):
            return {
                "code_point": code_point,
                "index": index,
                "reason": "word_boundary_scalar",
                "scalar": character,
            }
        rows = access.get(character, [])
        if not rows:
            return {
                "code_point": code_point,
                "index": index,
                "reason": "missing_text_field_input",
                "scalar": character,
            }
        if not any(
            _key_valid_at_position(row, surface, index, has_word_character)
            for row in rows
        ):
            kinds = {row["kind"] for row in rows}
            if (
                character == "\u200c"
                and sil_apk._is_valid_terminal_zwnj(surface, index)
            ):
                reason = "terminal_zwnj_layout_policy"
            elif "intra_word_punctuation" in kinds:
                reason = "intra_word_punctuation_context"
            elif kinds == {"text"} and category[0] in {"P", "S"}:
                reason = "noncomposing_layout_key"
            elif kinds & {"deva_conjunct_joiner", "deva_terminal_zwnj"}:
                reason = "joiner_layout_policy"
            else:
                reason = "layout_input_policy"
            return {
                "code_point": code_point,
                "index": index,
                "reason": reason,
                "scalar": character,
            }
        if category[0] in {"L", "N"}:
            has_word_character = True
    return None


def _surface_reachability(
    forms: list[dict[str, object]],
    access: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    gaps: list[dict[str, Any]] = []
    for row in forms:
        surface = str(row["surface"])
        gap = _surface_gap(surface, access)
        if gap is not None:
            gaps.append({
                "line": _line_from_form_id(row["form_id"]),
                "surface": surface,
                **gap,
            })
    gaps.sort(key=lambda row: (int(row["line"]), str(row["reason"])))
    reasons = collections.Counter(str(row["reason"]) for row in gaps)
    return {
        "bounded_unqueryable_examples": gaps[:MAX_REJECTION_EXAMPLES],
        "example_limit": MAX_REJECTION_EXAMPLES,
        "queryable_rows": len(forms) - len(gaps),
        "unqueryable_by_reason": dict(sorted(reasons.items())),
        "unqueryable_distinct_surfaces": len({str(row["surface"]) for row in gaps}),
        "unqueryable_rows": len(gaps),
    }


def _scalar_inventory(
    surfaces: Iterable[str],
    access: dict[str, list[dict[str, str]]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    occurrences: collections.Counter[str] = collections.Counter()
    row_counts: collections.Counter[str] = collections.Counter()
    unique_surfaces = sorted(set(surfaces))
    for surface in surfaces:
        occurrences.update(surface)
        row_counts.update(set(surface))

    inventory: list[dict[str, Any]] = []
    missing: list[str] = []
    noncomposing: list[str] = []
    for character in sorted(occurrences, key=ord):
        category = unicodedata.category(character)
        if character.isspace() or category.startswith("Z"):
            continue
        key_rows = access.get(character, [])
        input_present = bool(key_rows)
        composing_present = _has_composing_access(character, access)
        if not input_present:
            missing.append(character)
        elif not composing_present:
            noncomposing.append(character)
        inventory.append({
            "category": category,
            "bounded_surface_examples": [
                surface
                for surface in unique_surfaces
                if character in surface
            ][:MAX_SCALAR_EXAMPLES],
            "code_point": f"U+{ord(character):04X}",
            "contextual_composing_access": composing_present,
            "input_access": input_present,
            "layout_key_ids": sorted({row["key_id"] for row in key_rows}),
            "layout_kinds": sorted({row["kind"] for row in key_rows}),
            "name": unicodedata.name(character, "<unassigned>"),
            "occurrences": occurrences[character],
            "row_count": row_counts[character],
            "scalar": character,
        })
    return inventory, missing, noncomposing


def _policy_report(
    forms: list[dict[str, object]],
    rejected: list[dict[str, object]],
    stats: dict[str, int],
    access: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    surfaces = [str(row["surface"]) for row in forms]
    inventory, missing, noncomposing = _scalar_inventory(surfaces, access)
    rejection_reasons = collections.Counter(str(row["reason"]) for row in rejected)
    counts = collections.Counter(surfaces)
    return {
        "accepted_rows": stats["accepted_rows"],
        "accepted_rows_with_zwnj": sum("\u200c" in value for value in surfaces),
        "accepted_rows_with_zwj": sum("\u200d" in value for value in surfaces),
        "accepted_terminal_zwnj_rows": stats["accepted_terminal_zwnj_rows"],
        "bounded_rejection_examples": rejected[:MAX_REJECTION_EXAMPLES],
        "distinct_accepted_surfaces": stats["distinct_accepted_surfaces"],
        "duplicate_groups": sum(count > 1 for count in counts.values()),
        "duplicate_rows_merged_by_pack": sum(count - 1 for count in counts.values()),
        "missing_input_scalars": missing,
        "noncomposing_present_scalars": noncomposing,
        "normalized_rows": stats["normalized_rows"],
        "rejected_by_reason": dict(sorted(rejection_reasons.items())),
        "rejected_rows": stats["rejected_rows"],
        "rejection_example_limit": MAX_REJECTION_EXAMPLES,
        "scalar_inventory": inventory,
        "single_token_composition": _surface_reachability(forms, access),
    }


def _line_from_form_id(value: object) -> int:
    match = re.search(r":line-([0-9]{6})$", str(value))
    if match is None:
        raise AuditError("audit form ID does not contain a stable line number")
    return int(match.group(1))


def _terminal_delta(
    conjunct_forms: list[dict[str, object]],
    terminal_forms: list[dict[str, object]],
) -> dict[str, Any]:
    conjunct_ids = {str(row["form_id"]) for row in conjunct_forms}
    extra = [
        row for row in terminal_forms
        if str(row["form_id"]) not in conjunct_ids
    ]
    extra.sort(key=lambda row: _line_from_form_id(row["form_id"]))
    examples = [
        {
            "line": _line_from_form_id(row["form_id"]),
            "surface": str(row["surface"]),
        }
        for row in extra[:MAX_DELTA_EXAMPLES]
    ]
    return {
        "additional_accepted_rows": len(extra),
        "additional_distinct_surfaces": len({str(row["surface"]) for row in extra}),
        "bounded_examples": examples,
        "example_limit": MAX_DELTA_EXAMPLES,
        "requires_terminal_zwnj_to_retain_rows": bool(extra),
    }


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    if unicodedata.unidata_version != REQUIRED_UNICODE_VERSION:
        raise AuditError(
            "audit requires Unicode data "
            f"{REQUIRED_UNICODE_VERSION}, got {unicodedata.unidata_version}"
        )
    _helper_path, helper_sha256 = _verify_helper_identity()
    expected_catalog = REPOSITORY_ROOT / "catalog" / "resources.json"
    if args.resource_catalog.resolve() != expected_catalog.resolve():
        raise AuditError(f"resource catalog must be {expected_catalog}")
    catalog, catalog_bytes = _read_json_object(args.resource_catalog, "resource catalog")
    target, resource = _catalog_binding(catalog, args.target_id, args.resource_id)
    layout_lock, layout_lock_bytes, layout_verification = _verify_layout_lock(
        args.layout_lock
    )
    layout, access = _layout_binding(layout_lock, args.layout_id)
    input_bytes = _read_regular(args.sil_apk_jsonl, "SIL-APK JSONL")

    expected_bytes = _required_positive_int(resource, "bytes", "catalog resource")
    expected_rows = _required_positive_int(resource, "records", "catalog resource")
    expected_sha256 = _required_string(resource, "sha256", "catalog resource")
    expected_name = Path(_required_string(resource, "path", "catalog resource")).name
    if args.sil_apk_jsonl.name != expected_name:
        raise AuditError(f"input filename must be {expected_name}")
    if len(input_bytes) != expected_bytes:
        raise AuditError("input byte count does not match the resource catalog")
    actual_sha256 = _sha256_bytes(input_bytes)
    if actual_sha256 != expected_sha256:
        raise AuditError("input SHA-256 does not match the resource catalog")
    source_match = re.fullmatch(r"nepali-(.+)\.sil-apk\.dict\.jsonl", expected_name)
    if source_match is None:
        raise AuditError("catalog resource filename is not a supported SIL-APK name")
    expected_source_tag = f"sil-apk/{source_match.group(1)}"
    if args.source_tag != expected_source_tag:
        raise AuditError(f"source tag must be {expected_source_tag}")

    language = _required_string(target, "iso_639_3", "catalog target")
    base_config = sil_apk.SilApkConfig(
        adapter_name=AUDITOR_NAME,
        adapter_version=AUDITOR_VERSION,
        pack_id=f"{language}-Deva-NP",
        source_id=args.resource_id,
        source_sha256=expected_sha256,
        expected_data_rows=expected_rows,
        language=language,
        source_tag=args.source_tag,
        file_name=expected_name,
        display_name=_required_string(target, "name", "catalog target"),
        variety=target.get("variety") if isinstance(target.get("variety"), str) else None,
        stable_id_prefix=f"{language}:audit",
        source_title="SIL-APK audit input",
        license_id=str(resource.get("license", "unknown")),
        redistribution=str(resource.get("redistribution", "unknown")),
        allow_terminal_zwnj=False,
    )
    try:
        conjunct_forms, conjunct_rejected, conjunct_stats = sil_apk._read_rows(
            input_bytes,
            base_config,
        )
        terminal_forms, terminal_rejected, terminal_stats = sil_apk._read_rows(
            input_bytes,
            dataclasses.replace(base_config, allow_terminal_zwnj=True),
        )
    except sil_apk.AdapterError as exc:
        raise AuditError(str(exc)) from exc

    auditor_path = Path(__file__).resolve()
    layout_source = layout.get("source")
    if not isinstance(layout_source, dict):
        raise AuditError("compiled layout source must be an object")
    layout_source_sha256 = _required_string(
        layout_source,
        "sha256",
        "compiled layout source",
    )
    if not SHA256_RE.fullmatch(layout_source_sha256):
        raise AuditError("compiled layout source SHA-256 is malformed")

    return {
        "auditor": {
            "name": AUDITOR_NAME,
            "path": "tools/audit_sil_apk_layout_gap.py",
            "sha256": _sha256_bytes(_read_regular(auditor_path, "auditor source")),
            "version": AUDITOR_VERSION,
        },
        "format_version": 1,
        "input": {
            "bytes": len(input_bytes),
            "file_name": expected_name,
            "language": language,
            "records": expected_rows,
            "resource_id": args.resource_id,
            "sha256": actual_sha256,
            "source_tag": args.source_tag,
            "target_id": args.target_id,
        },
        "layout": {
            "layout_id": args.layout_id,
            "layout_lock_path": _repository_relative(args.layout_lock, "layout lock"),
            "layout_lock_sha256": _sha256_bytes(layout_lock_bytes),
            "layout_source_sha256": layout_source_sha256,
            "revision": _required_positive_int(layout, "revision", "compiled layout"),
            "verification": layout_verification,
        },
        "policies": {
            "conjunct_only": _policy_report(
                conjunct_forms,
                conjunct_rejected,
                conjunct_stats,
                access,
            ),
            "terminal_zwnj": _policy_report(
                terminal_forms,
                terminal_rejected,
                terminal_stats,
                access,
            ),
        },
        "resource_catalog": {
            "path": _repository_relative(args.resource_catalog, "resource catalog"),
            "sha256": _sha256_bytes(catalog_bytes),
        },
        "terminal_zwnj_delta": _terminal_delta(conjunct_forms, terminal_forms),
        "unicode_data_version": unicodedata.unidata_version,
        "verified_helper": {
            "name": sil_apk.HELPER_NAME,
            "path": "tools/sil_apk_jsonl_internal_source.py",
            "sha256": helper_sha256,
            "version": sil_apk.HELPER_VERSION,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-catalog", type=Path, required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--resource-id", required=True)
    parser.add_argument("--sil-apk-jsonl", type=Path, required=True)
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--layout-lock", type=Path, required=True)
    parser.add_argument("--layout-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_audit(args)
        encoded = _canonical_bytes(report)
        if args.check:
            existing = _read_regular(args.output, "audit output")
            if existing != encoded:
                raise AuditError("audit output is stale")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=args.output.parent,
                prefix=f".{args.output.name}.",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
            try:
                os.replace(temporary, args.output)
            except OSError:
                temporary.unlink(missing_ok=True)
                raise
    except (AuditError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "output": str(args.output),
        "report_sha256": _sha256_bytes(encoded),
        "status": "passed",
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
