#!/usr/bin/env python3
"""Build the reviewed, runtime-facing shipping-profile catalog lock.

The resource catalog describes research coverage. It never grants shipping
approval. Only explicit entries in the reviewed override/evidence input may
make a generated profile selectable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


FOUNDATION_PROFILE_IDS = {"eng-Latn-US", "npi-Deva-NP"}
COUNT_FIELDS = {"targets", "profiles", "scripts", "selectable"}
BASE_REQUIRED_EVIDENCE_GATES = {
    "layout_implemented",
    "redistribution_review",
    "release_pack",
    "license_notice_ui",
    "runtime_smoke",
}
EXPANSION_REQUIRED_EVIDENCE_GATES = {
    "native_speaker_review",
    "quality_evaluation",
    "physical_device_runtime",
    "accessibility_review",
}
INTERNAL_REQUIRED_EVIDENCE_GATES = {
    "deterministic_build",
    "internal_pack",
    "layout_implemented",
}
INTERNAL_CONVERSION_REQUIRED_EVIDENCE_GATES = {
    "deterministic_build",
    "internal_converter",
    "layout_implemented",
}
METHOD_TO_LOOKUP = {
    "direct": "surface_prefix",
    "roman_phonetic": "alias_prefix",
    "script_conversion": "conversion",
}
METHOD_TO_ENGINE = {
    "direct": "layout",
    "roman_phonetic": "alias_decoder",
    "script_conversion": "converter",
}
METHOD_BLOCK_DETAIL = {
    "direct": (
        "Requires a reviewed layout, redistributable dictionary pack, "
        "native-speaker evaluation, and runtime evidence."
    ),
    "roman_phonetic": (
        "Requires reviewed casual Roman aliases, N-best evaluation, "
        "redistribution approval, and runtime evidence."
    ),
    "script_conversion": (
        "Requires reviewed script-conversion rules, input design, and runtime evidence."
    ),
}
INTERNAL_METHOD_BLOCK_DETAIL = {
    "direct": "No deterministic internal dictionary pack and layout binding are available yet.",
    "roman_phonetic": "No reviewed internal casual-Roman alias pack is available yet.",
    "script_conversion": "No reviewed internal converter and input design are available yet.",
}
RELEASE_BLOCKED_REASONS = {
    "direct": "DIRECT_PROFILE_NOT_RELEASE_APPROVED",
    "roman_phonetic": "ROMAN_ALIAS_NOT_RELEASE_APPROVED",
    "script_conversion": "SCRIPT_CONVERTER_NOT_RELEASE_APPROVED",
}
INTERNAL_BLOCKED_REASONS = {
    "direct": "DIRECT_PROFILE_NOT_INTERNAL_READY",
    "roman_phonetic": "ROMAN_ALIAS_NOT_INTERNAL_READY",
    "script_conversion": "SCRIPT_CONVERTER_NOT_INTERNAL_READY",
}


class CatalogError(ValueError):
    """Raised when catalog/review data cannot safely produce a shipping lock."""


def _required_evidence_gates(
    profile_id: str,
    authority: str,
    method_type: str,
) -> set[str]:
    if authority == "internal":
        return set(
            INTERNAL_CONVERSION_REQUIRED_EVIDENCE_GATES
            if method_type == "script_conversion"
            else INTERNAL_REQUIRED_EVIDENCE_GATES
        )
    required = set(BASE_REQUIRED_EVIDENCE_GATES)
    if profile_id not in FOUNDATION_PROFILE_IDS:
        required.update(EXPANSION_REQUIRED_EVIDENCE_GATES)
    return required


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogError(f"missing {label}: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"invalid UTF-8 JSON in {label}: {path}") from exc
    if not isinstance(value, dict):
        raise CatalogError(f"{label} must be a JSON object")
    return value


def _require_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{location} must be a non-empty string")
    return value


def _require_sha256(value: object, location: str) -> str:
    digest = _require_string(value, location)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise CatalogError(f"{location} must be a lowercase SHA-256 digest")
    return digest


def _require_nonnegative_int(value: object, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CatalogError(f"{location} must be a non-negative integer")
    return value


def _validate_evidence_artifacts(value: object, location: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise CatalogError(f"{location} must be a non-empty array")
    result: list[dict[str, str]] = []
    paths: set[str] = set()
    for index, item in enumerate(value):
        item_location = f"{location}[{index}]"
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise CatalogError(f"{item_location} must contain only path and sha256")
        path = _require_string(item.get("path"), f"{item_location}.path")
        parts = Path(path).parts
        if Path(path).is_absolute() or not parts or ".." in parts or "." in parts:
            raise CatalogError(f"{item_location}.path must be repository-relative")
        if path in paths:
            raise CatalogError(f"duplicate evidence artifact path: {path}")
        paths.add(path)
        result.append({
            "path": path,
            "sha256": _require_sha256(item.get("sha256"), f"{item_location}.sha256"),
        })
    return result


def _validate_pack_artifact(
    value: object,
    *,
    profile_id: str,
    pack_binding: str,
    language: str,
    output_script: str,
    lookup_kind: str,
    authority: str,
) -> dict[str, Any]:
    location = f"profile {profile_id} pack artifact"
    required = {
        "pack_id",
        "file_name",
        "artifact_sha256",
        "language",
        "output_script",
        "artifact_license",
        "release_mode",
        "candidate_count",
        "surface_key_count",
        "alias_key_count",
        "validation",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise CatalogError(f"{location} must contain exactly {sorted(required)}")
    pack_id = _require_string(value.get("pack_id"), f"{location}.pack_id")
    file_name = _require_string(value.get("file_name"), f"{location}.file_name")
    artifact_language = _require_string(value.get("language"), f"{location}.language")
    artifact_script = _require_string(
        value.get("output_script"), f"{location}.output_script"
    )
    artifact_license = _require_string(
        value.get("artifact_license"), f"{location}.artifact_license"
    )
    release_mode = _require_string(value.get("release_mode"), f"{location}.release_mode")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", pack_id):
        raise CatalogError(f"{location}.pack_id is unsafe")
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.nkp", file_name):
        raise CatalogError(f"{location}.file_name is unsafe")
    if not re.fullmatch(r"[a-z]{3}", artifact_language):
        raise CatalogError(f"{location}.language must be ISO 639-3")
    if not re.fullmatch(r"[A-Z][a-z]{3}", artifact_script):
        raise CatalogError(f"{location}.output_script must be ISO 15924")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,63}", artifact_license):
        raise CatalogError(f"{location}.artifact_license is unsafe")
    if pack_id != pack_binding:
        raise CatalogError(f"{location}.pack_id does not match pack_binding")
    if artifact_language != language or artifact_script != output_script:
        raise CatalogError(f"{location} language/script does not match profile")
    if release_mode not in {"release", "internal"}:
        raise CatalogError(f"{location}.release_mode must be release or internal")
    if authority == "release" and release_mode != "release":
        raise CatalogError(f"{location} cannot bind an internal pack to release authority")
    candidate_count = _require_nonnegative_int(
        value.get("candidate_count"), f"{location}.candidate_count"
    )
    surface_key_count = _require_nonnegative_int(
        value.get("surface_key_count"), f"{location}.surface_key_count"
    )
    alias_key_count = _require_nonnegative_int(
        value.get("alias_key_count"), f"{location}.alias_key_count"
    )
    if candidate_count < 1:
        raise CatalogError(f"{location}.candidate_count must be positive")
    if lookup_kind == "surface_prefix" and surface_key_count < 1:
        raise CatalogError(f"{location} has no surface-prefix index")
    if lookup_kind == "alias_prefix" and alias_key_count < 1:
        raise CatalogError(f"{location} has no alias-prefix index")
    if lookup_kind == "conversion":
        raise CatalogError("conversion profiles must use a conversion artifact")

    validation = value.get("validation")
    validation_fields = {"query", "expected_surface", "benchmark_queries"}
    if not isinstance(validation, dict) or set(validation) != validation_fields:
        raise CatalogError(
            f"{location}.validation must contain exactly {sorted(validation_fields)}"
        )
    query = _require_string(validation.get("query"), f"{location}.validation.query")
    expected_surface = _require_string(
        validation.get("expected_surface"),
        f"{location}.validation.expected_surface",
    )
    benchmark_queries = validation.get("benchmark_queries")
    if (
        not isinstance(benchmark_queries, list)
        or not benchmark_queries
        or len(benchmark_queries) > 64
        or any(not isinstance(item, str) or not item for item in benchmark_queries)
    ):
        raise CatalogError(
            f"{location}.validation.benchmark_queries must contain 1..64 strings"
        )
    return {
        "pack_id": pack_id,
        "file_name": file_name,
        "artifact_sha256": _require_sha256(
            value.get("artifact_sha256"), f"{location}.artifact_sha256"
        ),
        "language": artifact_language,
        "output_script": artifact_script,
        "artifact_license": artifact_license,
        "release_mode": release_mode,
        "candidate_count": candidate_count,
        "surface_key_count": surface_key_count,
        "alias_key_count": alias_key_count,
        "validation": {
            "query": query,
            "expected_surface": expected_surface,
            "benchmark_queries": benchmark_queries,
        },
    }


def _validate_conversion_artifact(
    value: object,
    *,
    profile_id: str,
    conversion_binding: str,
    language: str,
    source_script: str,
    output_script: str,
    authority: str,
) -> dict[str, Any]:
    location = f"profile {profile_id} conversion artifact"
    required = {
        "converter_id",
        "file_name",
        "artifact_sha256",
        "language",
        "source_script",
        "output_script",
        "release_mode",
        "rule_count",
        "validation",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise CatalogError(f"{location} must contain exactly {sorted(required)}")
    converter_id = _require_string(
        value.get("converter_id"), f"{location}.converter_id"
    )
    file_name = _require_string(value.get("file_name"), f"{location}.file_name")
    artifact_language = _require_string(
        value.get("language"), f"{location}.language"
    )
    artifact_source_script = _require_string(
        value.get("source_script"), f"{location}.source_script"
    )
    artifact_output_script = _require_string(
        value.get("output_script"), f"{location}.output_script"
    )
    release_mode = _require_string(value.get("release_mode"), f"{location}.release_mode")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", converter_id):
        raise CatalogError(f"{location}.converter_id is unsafe")
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.ncm", file_name):
        raise CatalogError(f"{location}.file_name is unsafe")
    if not re.fullmatch(r"[a-z]{3}", artifact_language):
        raise CatalogError(f"{location}.language must be ISO 639-3")
    for field, script in (
        ("source_script", artifact_source_script),
        ("output_script", artifact_output_script),
    ):
        if not re.fullmatch(r"[A-Z][a-z]{3}", script):
            raise CatalogError(f"{location}.{field} must be ISO 15924")
    if converter_id != conversion_binding:
        raise CatalogError(
            f"{location}.converter_id does not match conversion_binding"
        )
    if (
        artifact_language != language
        or artifact_source_script != source_script
        or artifact_output_script != output_script
    ):
        raise CatalogError(f"{location} language/scripts do not match profile")
    if artifact_source_script == artifact_output_script:
        raise CatalogError(f"{location} must change scripts")
    if release_mode not in {"release", "internal"}:
        raise CatalogError(f"{location}.release_mode must be release or internal")
    if authority == "release" and release_mode != "release":
        raise CatalogError(
            f"{location} cannot bind an internal converter to release authority"
        )
    rule_count = _require_nonnegative_int(
        value.get("rule_count"), f"{location}.rule_count"
    )
    if not 1 <= rule_count <= 1024:
        raise CatalogError(f"{location}.rule_count must be in 1..1024")

    validation = value.get("validation")
    if not isinstance(validation, dict) or set(validation) != {"vectors"}:
        raise CatalogError(f"{location}.validation must contain only vectors")
    vector_rows = validation.get("vectors")
    if not isinstance(vector_rows, list) or not 2 <= len(vector_rows) <= 64:
        raise CatalogError(
            f"{location}.validation.vectors must contain 2..64 rows"
        )
    vectors: list[dict[str, Any]] = []
    seen_vectors: set[tuple[str, str, str | None]] = set()
    statuses: set[str] = set()
    for index, vector in enumerate(vector_rows):
        vector_location = f"{location}.validation.vectors[{index}]"
        if not isinstance(vector, dict) or set(vector) != {
            "input", "expected_status", "expected_output"
        }:
            raise CatalogError(
                f"{vector_location} must contain input, expected_status, and expected_output"
            )
        input_text = _require_string(vector.get("input"), f"{vector_location}.input")
        status = _require_string(
            vector.get("expected_status"), f"{vector_location}.expected_status"
        )
        expected_output = vector.get("expected_output")
        if status == "MATCH":
            expected_output = _require_string(
                expected_output, f"{vector_location}.expected_output"
            )
        elif status == "NO_MATCH":
            if expected_output is not None:
                raise CatalogError(
                    f"{vector_location}.expected_output must be null for NO_MATCH"
                )
        else:
            raise CatalogError(
                f"{vector_location}.expected_status must be MATCH or NO_MATCH"
            )
        identity = (input_text, status, expected_output)
        if identity in seen_vectors:
            raise CatalogError(f"duplicate conversion validation vector: {identity!r}")
        seen_vectors.add(identity)
        statuses.add(status)
        vectors.append({
            "input": input_text,
            "expected_status": status,
            "expected_output": expected_output,
        })
    if statuses != {"MATCH", "NO_MATCH"}:
        raise CatalogError(
            f"{location}.validation.vectors need at least one MATCH and one NO_MATCH"
        )
    return {
        "converter_id": converter_id,
        "file_name": file_name,
        "artifact_sha256": _require_sha256(
            value.get("artifact_sha256"), f"{location}.artifact_sha256"
        ),
        "language": artifact_language,
        "source_script": artifact_source_script,
        "output_script": artifact_output_script,
        "release_mode": release_mode,
        "rule_count": rule_count,
        "validation": {"vectors": vectors},
    }


def _profile_id(target_id: str, source_script: str, output_script: str, region: str) -> str:
    if source_script == output_script:
        return f"{target_id}-{output_script}-{region}"
    return f"{target_id}-{source_script}-{output_script}-{region}"


def _validate_input_reference(value: object, location: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise CatalogError(f"{location} must contain only path and sha256")
    return {
        "path": _require_string(value.get("path"), f"{location}.path"),
        "sha256": _require_sha256(value.get("sha256"), f"{location}.sha256"),
    }


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def build_lock(
    catalog: dict[str, Any],
    review: dict[str, Any],
    *,
    catalog_path: str = "catalog/resources.json",
    review_path: str = "catalog/shipping-profile-review.json",
    catalog_sha256: str,
    review_sha256: str,
    compiler_reference: dict[str, str],
    schema_references: dict[str, dict[str, str]],
) -> dict[str, Any]:
    review_fields = {
        "review_version", "review_id", "reviewed_at", "authority", "expected_counts",
        "blocked_reason_by_method", "target_overrides", "profile_overrides", "evidence",
    }
    if set(review) != review_fields:
        raise CatalogError(f"shipping review must contain exactly {sorted(review_fields)}")
    if review.get("review_version") != 1 or isinstance(review.get("review_version"), bool):
        raise CatalogError("shipping review version must be 1")
    authority = review.get("authority")
    if authority not in {"release", "internal"}:
        raise CatalogError("review.authority must be release or internal")
    _require_string(review.get("review_id"), "review.review_id")
    reviewed_at = _require_string(review.get("reviewed_at"), "review.reviewed_at")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", reviewed_at):
        raise CatalogError("review.reviewed_at must be an ISO date")
    packs = catalog.get("packs")
    if not isinstance(packs, list):
        raise CatalogError("catalog.packs must be an array")
    blocked_reasons = review.get("blocked_reason_by_method")
    target_overrides = review.get("target_overrides", {})
    profile_overrides = review.get("profile_overrides")
    evidence_rows = review.get("evidence")
    if not isinstance(blocked_reasons, dict):
        raise CatalogError("review.blocked_reason_by_method must be an object")
    expected_blocked_reasons = (
        RELEASE_BLOCKED_REASONS if authority == "release" else INTERNAL_BLOCKED_REASONS
    )
    if blocked_reasons != expected_blocked_reasons:
        raise CatalogError(
            f"review.blocked_reason_by_method does not match {authority} authority"
        )
    if not isinstance(target_overrides, dict) or not isinstance(profile_overrides, dict):
        raise CatalogError("review target/profile overrides must be objects")
    if not isinstance(evidence_rows, list):
        raise CatalogError("review.evidence must be an array")
    catalog_sha256 = _require_sha256(catalog_sha256, "catalog SHA-256")
    review_sha256 = _require_sha256(review_sha256, "review SHA-256")
    compiler_reference = _validate_input_reference(
        compiler_reference, "compiler reference"
    )
    if set(schema_references) != {"catalog", "review", "lock"}:
        raise CatalogError("schema references must contain catalog, review, and lock")
    validated_schema_references = {
        name: _validate_input_reference(reference, f"{name} schema reference")
        for name, reference in schema_references.items()
    }

    script_labels: dict[str, str] = {}
    for pack_index, pack in enumerate(packs):
        if not isinstance(pack, dict):
            raise CatalogError(f"catalog.packs[{pack_index}] must be an object")
        scripts = pack.get("scripts")
        if not isinstance(scripts, list) or not scripts:
            raise CatalogError(f"catalog.packs[{pack_index}].scripts must be a non-empty array")
        for script in scripts:
            if not isinstance(script, dict):
                raise CatalogError(f"catalog.packs[{pack_index}] has a non-object script")
            script_id = _require_string(
                script.get("iso_15924"), f"catalog.packs[{pack_index}] script ID"
            )
            script_label = _require_string(
                script.get("name"), f"catalog.packs[{pack_index}] script name"
            )
            previous = script_labels.setdefault(script_id, script_label)
            if previous != script_label:
                raise CatalogError(
                    f"script {script_id} has inconsistent names: {previous!r}, {script_label!r}"
                )

    evidence: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(evidence_rows):
        if not isinstance(row, dict):
            raise CatalogError(f"review.evidence[{index}] must be an object")
        base_evidence_fields = {
            "evidence_id", "profile_id", "status", "gates", "layout_binding",
            "artifacts",
        }
        artifact_fields = set(row) - base_evidence_fields
        if (
            not base_evidence_fields.issubset(row)
            or artifact_fields not in ({"pack_artifact"}, {"conversion_artifact"})
        ):
            raise CatalogError(
                f"review.evidence[{index}] must contain exactly the base evidence fields and "
                "exactly one of pack_artifact or conversion_artifact"
            )
        evidence_id = _require_string(
            row.get("evidence_id"), f"review.evidence[{index}].evidence_id"
        )
        if evidence_id in evidence:
            raise CatalogError(f"duplicate evidence ID: {evidence_id}")
        artifacts = _validate_evidence_artifacts(
            row.get("artifacts"), f"review.evidence[{index}].artifacts"
        )
        gates = row.get("gates")
        if (
            not isinstance(gates, list)
            or any(not isinstance(item, str) or not item for item in gates)
            or len(set(gates)) != len(gates)
        ):
            raise CatalogError(f"evidence {evidence_id} gates must be strings")
        evidence[evidence_id] = {**row, "artifacts": artifacts}

    targets: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    target_ids: set[str] = set()
    method_ids: set[str] = set()
    profile_ids: set[str] = set()
    script_ids: set[str] = set()
    used_overrides: set[str] = set()
    used_evidence: set[str] = set()

    for pack_index, pack in enumerate(packs):
        if not isinstance(pack, dict):
            raise CatalogError(f"catalog.packs[{pack_index}] must be an object")
        target_id = _require_string(pack.get("id"), f"catalog.packs[{pack_index}].id")
        if target_id in target_ids:
            raise CatalogError(f"duplicate target ID: {target_id}")
        target_ids.add(target_id)
        iso_639_3 = _require_string(pack.get("iso_639_3"), f"target {target_id}.iso_639_3")
        display_label = _require_string(pack.get("name"), f"target {target_id}.name")
        scope = _require_string(pack.get("scope"), f"target {target_id}.scope")
        if scope not in {"language", "variety"}:
            raise CatalogError(f"target {target_id} has unsupported scope: {scope}")
        override = target_overrides.get(target_id, {})
        if not isinstance(override, dict):
            raise CatalogError(f"target override {target_id} must be an object")
        if not set(override).issubset({"native_label", "language_tag"}):
            raise CatalogError(f"target override {target_id} has unknown fields")
        native_label = _require_string(
            override.get("native_label", display_label),
            f"target override {target_id}.native_label",
        )
        language_tag = _require_string(
            override.get("language_tag", f"{iso_639_3}-NP"),
            f"target override {target_id}.language_tag",
        )
        scripts = pack.get("scripts")
        if not isinstance(scripts, list) or not scripts:
            raise CatalogError(f"target {target_id}.scripts must be a non-empty array")
        target_scripts: list[str] = []
        for script in scripts:
            if not isinstance(script, dict):
                raise CatalogError(f"target {target_id} has a non-object script")
            script_id = _require_string(script.get("iso_15924"), f"target {target_id} script")
            target_scripts.append(script_id)
            script_ids.add(script_id)
        if len(target_scripts) != len(set(target_scripts)):
            raise CatalogError(f"target {target_id} has duplicate scripts")
        targets.append({
            "target_id": target_id,
            "iso_639_3": iso_639_3,
            "display_label": display_label,
            "native_label": native_label,
            "scope": scope,
            "group": pack.get("group"),
            "variety": pack.get("variety"),
            "scripts": target_scripts,
        })

        methods = pack.get("input_methods")
        if not isinstance(methods, list):
            raise CatalogError(f"target {target_id}.input_methods must be an array")
        for method_index, method in enumerate(methods):
            if not isinstance(method, dict):
                raise CatalogError(
                    f"target {target_id} input method {method_index} must be an object"
                )
            method_id = _require_string(method.get("id"), f"target {target_id} method ID")
            if method_id in method_ids:
                raise CatalogError(f"duplicate input method ID: {method_id}")
            method_ids.add(method_id)
            method_type = _require_string(method.get("type"), f"method {method_id}.type")
            engine_kind = _require_string(
                method.get("engine_kind"), f"method {method_id}.engine_kind"
            )
            source_script = _require_string(
                method.get("source_script"), f"method {method_id}.source_script"
            )
            output_script = _require_string(
                method.get("output_script"), f"method {method_id}.output_script"
            )
            readiness = _require_string(
                method.get("readiness"), f"method {method_id}.readiness"
            )
            if method_type not in METHOD_TO_LOOKUP:
                raise CatalogError(f"unsupported method type for {method_id}: {method_type}")
            if engine_kind != METHOD_TO_ENGINE[method_type]:
                raise CatalogError(
                    f"method {method_id} engine {engine_kind} is incompatible with {method_type}"
                )
            if source_script not in script_labels:
                raise CatalogError(f"method {method_id} has unknown source script")
            if output_script not in target_scripts:
                raise CatalogError(
                    f"method {method_id} output script is not declared by its target"
                )
            if method_type == "direct" and source_script != output_script:
                raise CatalogError(f"direct method {method_id} must preserve its script")
            if method_type == "roman_phonetic" and (
                source_script != "Latn" or source_script == output_script
            ):
                raise CatalogError(
                    f"Roman method {method_id} must map Latin input to another script"
                )
            if method_type == "script_conversion" and source_script == output_script:
                raise CatalogError(f"conversion method {method_id} must change scripts")
            region = "US" if target_id == "eng" else "NP"
            generated_profile_id = _profile_id(
                target_id, source_script, output_script, region
            )
            method_override = profile_overrides.get(method_id, {})
            if not isinstance(method_override, dict):
                raise CatalogError(f"profile override {method_id} must be an object")
            if not set(method_override).issubset({
                "profile_id", "layout_id", "pack_binding", "conversion_binding",
                "selectable", "default_enabled", "evidence_ids", "blocked_detail",
            }):
                raise CatalogError(f"profile override {method_id} has unknown fields")
            if method_override:
                used_overrides.add(method_id)
            profile_id = _require_string(
                method_override.get("profile_id", generated_profile_id),
                f"profile override {method_id}.profile_id",
            )
            if profile_id != generated_profile_id:
                raise CatalogError(
                    f"profile override {method_id} changes deterministic ID "
                    f"{generated_profile_id}"
                )
            if profile_id in profile_ids:
                raise CatalogError(f"duplicate generated profile ID: {profile_id}")
            profile_ids.add(profile_id)
            selectable = method_override.get("selectable", False)
            default_enabled = method_override.get("default_enabled", False)
            if not isinstance(selectable, bool) or not isinstance(default_enabled, bool):
                raise CatalogError(
                    f"profile {profile_id} selectable/default flags must be booleans"
                )
            evidence_ids = method_override.get("evidence_ids", [])
            if not isinstance(evidence_ids, list) or any(
                not isinstance(item, str) for item in evidence_ids
            ):
                raise CatalogError(f"profile {profile_id} evidence_ids must be strings")
            pack_binding = method_override.get("pack_binding")
            conversion_binding = method_override.get("conversion_binding")
            pack_artifact: dict[str, Any] | None = None
            conversion_artifact: dict[str, Any] | None = None
            evidence_artifacts: list[dict[str, str]] = []
            evidence_artifacts_by_path: dict[str, str] = {}
            default_layout_id = (
                "latn-qwerty-us-v1"
                if method_type == "roman_phonetic"
                else f"pending-{method_id}"
            )
            layout_id = method_override.get("layout_id", default_layout_id)
            layout_revision: int | None = None
            layout_source_sha256: str | None = None
            if selectable:
                if method_type == "script_conversion":
                    if pack_binding is not None:
                        raise CatalogError(
                            f"conversion profile {profile_id} cannot carry a pack binding"
                        )
                    if not isinstance(conversion_binding, str) or not conversion_binding:
                        raise CatalogError(
                            f"selectable profile {profile_id} needs a conversion binding"
                        )
                else:
                    if conversion_binding is not None:
                        raise CatalogError(
                            f"pack profile {profile_id} cannot carry a conversion binding"
                        )
                    if not isinstance(pack_binding, str) or not pack_binding:
                        raise CatalogError(
                            f"selectable profile {profile_id} needs a pack binding"
                        )
                if not evidence_ids:
                    raise CatalogError(
                        f"selectable profile {profile_id} needs passed evidence"
                    )
                for evidence_id in evidence_ids:
                    row = evidence.get(evidence_id)
                    if row is None:
                        raise CatalogError(
                            f"profile {profile_id} references unknown evidence {evidence_id}"
                        )
                    gates = row.get("gates")
                    required_gates = _required_evidence_gates(
                        profile_id, authority, method_type
                    )
                    if (
                        row.get("profile_id") != profile_id
                        or row.get("status") != "passed"
                        or not isinstance(gates, list)
                        or not required_gates.issubset(set(gates))
                    ):
                        missing_gates = (
                            sorted(required_gates - set(gates))
                            if isinstance(gates, list)
                            else sorted(required_gates)
                        )
                        raise CatalogError(
                            f"evidence {evidence_id} does not pass required gates; "
                            f"missing {missing_gates}"
                        )
                    if method_type == "script_conversion":
                        if "pack_artifact" in row:
                            raise CatalogError(
                                f"conversion profile {profile_id} evidence cannot carry a pack artifact"
                            )
                        evidence_conversion_artifact = _validate_conversion_artifact(
                            row.get("conversion_artifact"),
                            profile_id=profile_id,
                            conversion_binding=conversion_binding,
                            language=iso_639_3,
                            source_script=source_script,
                            output_script=output_script,
                            authority=authority,
                        )
                        if conversion_artifact is None:
                            conversion_artifact = evidence_conversion_artifact
                        elif conversion_artifact != evidence_conversion_artifact:
                            raise CatalogError(
                                f"profile {profile_id} evidence has inconsistent conversion artifacts"
                            )
                    else:
                        if "conversion_artifact" in row:
                            raise CatalogError(
                                f"pack profile {profile_id} evidence cannot carry a conversion artifact"
                            )
                        evidence_pack_artifact = _validate_pack_artifact(
                            row.get("pack_artifact"),
                            profile_id=profile_id,
                            pack_binding=pack_binding,
                            language=iso_639_3,
                            output_script=output_script,
                            lookup_kind=METHOD_TO_LOOKUP[method_type],
                            authority=authority,
                        )
                        if pack_artifact is None:
                            pack_artifact = evidence_pack_artifact
                        elif pack_artifact != evidence_pack_artifact:
                            raise CatalogError(
                                f"profile {profile_id} evidence has inconsistent pack artifacts"
                            )
                    for artifact in row["artifacts"]:
                        artifact_path = artifact["path"]
                        prior_hash = evidence_artifacts_by_path.setdefault(
                            artifact_path, artifact["sha256"]
                        )
                        if prior_hash != artifact["sha256"]:
                            raise CatalogError(
                                f"profile {profile_id} has conflicting evidence artifact hashes"
                            )
                        if artifact not in evidence_artifacts:
                            evidence_artifacts.append(artifact)
                    layout_binding = row.get("layout_binding")
                    if not isinstance(layout_binding, dict) or set(layout_binding) != {
                        "layout_id", "revision", "source_sha256"
                    }:
                        raise CatalogError(
                            f"evidence {evidence_id} must pin an exact layout binding"
                        )
                    evidence_layout_id = _require_string(
                        layout_binding.get("layout_id"),
                        f"evidence {evidence_id}.layout_binding.layout_id",
                    )
                    evidence_revision = layout_binding.get("revision")
                    if isinstance(evidence_revision, bool) or not isinstance(evidence_revision, int) or evidence_revision < 1:
                        raise CatalogError(
                            f"evidence {evidence_id} layout revision must be positive"
                        )
                    evidence_source_sha256 = _require_sha256(
                        layout_binding.get("source_sha256"),
                        f"evidence {evidence_id}.layout_binding.source_sha256",
                    )
                    if evidence_layout_id != layout_id:
                        raise CatalogError(
                            f"evidence {evidence_id} layout ID does not match profile"
                        )
                    if layout_revision is None:
                        layout_revision = evidence_revision
                        layout_source_sha256 = evidence_source_sha256
                    elif (
                        layout_revision != evidence_revision
                        or layout_source_sha256 != evidence_source_sha256
                    ):
                        raise CatalogError(
                            f"profile {profile_id} evidence has inconsistent layout bindings"
                        )
                    used_evidence.add(evidence_id)
                blocked_reason = None
                blocked_detail = None
            else:
                if (
                    default_enabled
                    or pack_binding is not None
                    or conversion_binding is not None
                    or evidence_ids
                ):
                    raise CatalogError(
                        f"blocked profile {profile_id} cannot ship bindings/evidence/defaults"
                    )
                blocked_reason = _require_string(
                    blocked_reasons.get(method_type),
                    f"review.blocked_reason_by_method.{method_type}",
                )
                blocked_detail = _require_string(
                    method_override.get(
                        "blocked_detail",
                        (METHOD_BLOCK_DETAIL if authority == "release"
                         else INTERNAL_METHOD_BLOCK_DETAIL)[method_type],
                    ),
                    f"profile override {method_id}.blocked_detail",
                )
            if method_type == "direct":
                input_label = f"{script_labels[source_script]} direct"
            elif method_type == "roman_phonetic":
                input_label = f"Romanized → {script_labels[output_script]}"
            else:
                input_label = (
                    f"{script_labels[source_script]} → "
                    f"{script_labels[output_script]} conversion"
                )
            profiles.append({
                "profile_id": profile_id,
                "target_id": target_id,
                "display_label": display_label,
                "native_label": native_label,
                "language_tag": language_tag,
                "input_label": input_label,
                "scope": scope,
                "group": pack.get("group"),
                "variety": pack.get("variety"),
                "source_script": source_script,
                "output_script": output_script,
                "input_method_id": method_id,
                "method_type": method_type,
                "engine_kind": engine_kind,
                "layout_id": _require_string(
                    layout_id, f"profile {profile_id}.layout_id"
                ),
                "layout_revision": layout_revision,
                "layout_source_sha256": layout_source_sha256,
                "lookup_kind": METHOD_TO_LOOKUP[method_type],
                "pack_binding": pack_binding,
                "pack_artifact": pack_artifact,
                "conversion_binding": conversion_binding,
                "conversion_artifact": conversion_artifact,
                "catalog_readiness": readiness,
                "selectable": selectable,
                "blocked_reason": blocked_reason,
                "blocked_detail": blocked_detail,
                "default_enabled": default_enabled,
                "sort_key": (
                    f"{display_label.casefold()}|{output_script.casefold()}|"
                    f"{method_type}|{profile_id}"
                ),
                "search_aliases": _unique(
                    [
                        target_id,
                        iso_639_3,
                        display_label,
                        native_label,
                        language_tag,
                        input_label,
                        source_script,
                        output_script,
                        script_labels[source_script],
                        script_labels[output_script],
                        pack.get("group") or "",
                        pack.get("variety") or "",
                        method_id,
                    ]
                ),
                "evidence_ids": evidence_ids,
                "evidence_artifacts": evidence_artifacts,
            })

    unused_overrides = set(profile_overrides) - used_overrides
    if unused_overrides:
        raise CatalogError(
            f"review has overrides for unknown methods: {sorted(unused_overrides)}"
        )
    unused_target_overrides = set(target_overrides) - target_ids
    if unused_target_overrides:
        raise CatalogError(
            f"review has overrides for unknown targets: {sorted(unused_target_overrides)}"
        )
    unused_evidence = set(evidence) - used_evidence
    if unused_evidence:
        raise CatalogError(f"review has unused evidence: {sorted(unused_evidence)}")
    expected = review.get("expected_counts")
    if not isinstance(expected, dict) or set(expected) != COUNT_FIELDS:
        raise CatalogError(
            f"review.expected_counts must contain exactly {sorted(COUNT_FIELDS)}"
        )
    expected_counts = {
        name: _require_nonnegative_int(expected[name], f"review.expected_counts.{name}")
        for name in sorted(COUNT_FIELDS)
    }
    actual_counts = {
        "targets": len(targets),
        "profiles": len(profiles),
        "scripts": len(script_ids),
        "selectable": sum(profile["selectable"] for profile in profiles),
    }
    if actual_counts != expected_counts:
        raise CatalogError(
            f"shipping catalog count mismatch: expected {expected_counts}, got {actual_counts}"
        )
    selectable_ids = {
        profile["profile_id"] for profile in profiles if profile["selectable"]
    }
    missing_foundations = FOUNDATION_PROFILE_IDS - selectable_ids
    if missing_foundations:
        raise CatalogError(
            f"missing selectable foundation profiles: {sorted(missing_foundations)}"
        )
    if not any(profile["default_enabled"] for profile in profiles):
        raise CatalogError("shipping catalog needs at least one default-enabled profile")

    pack_ids: dict[str, dict[str, Any]] = {}
    pack_file_names: dict[str, dict[str, Any]] = {}
    converter_ids: dict[str, dict[str, Any]] = {}
    converter_file_names: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        if not profile["selectable"]:
            continue
        if profile["lookup_kind"] == "conversion":
            artifact = profile["conversion_artifact"]
            artifact_kind = "conversion"
            identities = (
                ("converter_id", converter_ids),
                ("file_name", converter_file_names),
            )
        else:
            artifact = profile["pack_artifact"]
            artifact_kind = "pack"
            identities = (
                ("pack_id", pack_ids),
                ("file_name", pack_file_names),
            )
        if not isinstance(artifact, dict):
            raise CatalogError(
                f"selectable profile {profile['profile_id']} has no exact "
                f"{artifact_kind} artifact"
            )
        identity = {key: value for key, value in artifact.items() if key != "validation"}
        for field, index in identities:
            identifier = artifact[field]
            prior = index.setdefault(identifier, identity)
            if prior != identity:
                raise CatalogError(
                    f"conflicting {artifact_kind} artifact reuse for {field} {identifier}"
                )

    return {
        "lock_version": 2,
        "generator": "build_shipping_profile_catalog",
        "generator_version": 2,
        "compiler": compiler_reference,
        "schemas": validated_schema_references,
        "catalog": {
            "path": catalog_path,
            "version": catalog.get("catalog_version"),
            "date": catalog.get("audited_at"),
            "sha256": catalog_sha256,
        },
        "review": {
            "path": review_path,
            "version": review.get("review_version"),
            "date": review.get("reviewed_at"),
            "id": review.get("review_id"),
            "authority": authority,
            "sha256": review_sha256,
        },
        "counts": actual_counts,
        "scripts": sorted(script_ids),
        "targets": targets,
        "profiles": profiles,
    }


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _write_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
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


def _validate_evidence_files(review: dict[str, Any], repository_root: Path) -> None:
    evidence_rows = review.get("evidence")
    if not isinstance(evidence_rows, list):
        return
    repository_root = repository_root.resolve()
    checked: dict[Path, str] = {}
    for evidence_index, evidence in enumerate(evidence_rows):
        if not isinstance(evidence, dict):
            continue
        artifacts = _validate_evidence_artifacts(
            evidence.get("artifacts"),
            f"review.evidence[{evidence_index}].artifacts",
        )
        for artifact in artifacts:
            path = repository_root / artifact["path"]
            parents = [
                repository_root.joinpath(*Path(artifact["path"]).parts[:index])
                for index in range(1, len(Path(artifact["path"]).parts) + 1)
            ]
            if (
                any(candidate.is_symlink() for candidate in parents)
                or not path.resolve().is_relative_to(repository_root)
                or not path.is_file()
            ):
                raise CatalogError(f"evidence artifact is not a regular file: {artifact['path']}")
            actual = checked.get(path)
            if actual is None:
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                actual = digest.hexdigest()
                checked[path] = actual
            if actual != artifact["sha256"]:
                raise CatalogError(
                    f"evidence artifact SHA-256 mismatch: {artifact['path']}"
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog_bytes = args.catalog.read_bytes()
    review_bytes = args.review.read_bytes()
    catalog = _read_object(args.catalog, "resource catalog")
    review = _read_object(args.review, "shipping review")
    _validate_evidence_files(review, args.review.resolve().parent.parent)
    repository_root = Path(__file__).resolve().parents[1]
    compiler_path = repository_root / "tools" / "build_shipping_profile_catalog.py"
    schema_names = {
        "catalog": "resource-catalog.schema.json",
        "review": "shipping-profile-review.schema.json",
        "lock": "shipping-profile-lock.schema.json",
    }
    lock = build_lock(
        catalog,
        review,
        catalog_path=args.catalog.resolve().relative_to(repository_root).as_posix(),
        review_path=args.review.resolve().relative_to(repository_root).as_posix(),
        catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        review_sha256=hashlib.sha256(review_bytes).hexdigest(),
        compiler_reference={
            "path": "tools/build_shipping_profile_catalog.py",
            "sha256": hashlib.sha256(compiler_path.read_bytes()).hexdigest(),
        },
        schema_references={
            name: {
                "path": f"schemas/{file_name}",
                "sha256": hashlib.sha256(
                    (repository_root / "schemas" / file_name).read_bytes()
                ).hexdigest(),
            }
            for name, file_name in schema_names.items()
        },
    )
    encoded = _canonical_bytes(lock)
    if args.check:
        try:
            current = args.output.read_bytes()
        except FileNotFoundError as exc:
            raise SystemExit(f"shipping profile lock is missing: {args.output}") from exc
        if current != encoded:
            raise SystemExit(f"shipping profile lock is stale: {args.output}")
        return 0
    _write_atomic(args.output, encoded)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CatalogError as error:
        raise SystemExit(f"error: {error}") from error
