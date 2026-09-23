#!/usr/bin/env python3
"""Compile reviewed keyboard-layout sources into a deterministic v1 lock.

The shipping-profile lock remains the authority for which profiles are
selectable. This compiler only proves that every selectable profile resolves
to a validated layout whose input script matches the profile source script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


LAYOUT_FORMAT_VERSION = 1
LAYOUT_LOCK_VERSION = 1
GENERATOR_VERSION = 1
UNICODE_DATA_VERSION = "16.0.0"
TRANSFORM_SEMANTICS = "append_then_longest_suffix_once"
LAYERS = ("base", "shift", "symbols", "numeric")
DEVICE_FORMS = {"phone", "tablet"}
FIELD_LAYER_MAP = {
    "text": "base",
    "number": "numeric",
    "phone": "numeric",
    "datetime": "numeric",
}
ACTIONS = {"shift", "delete", "enter", "space", "language", "symbols", "letters"}
HOLD_ACTIONS = {"open_language_picker"}
TEXT_KEY_KINDS = {
    "text",
    "orthographic_word",
    "intra_word_punctuation",
    "deva_conjunct_joiner",
    "deva_terminal_zwnj",
    "newa_conjunct_joiner",
}
ORTHOGRAPHIC_WORD_TEXTS = {"\u2018"}
INTRA_WORD_PUNCTUATION_TEXTS = {"-", "/", "\\", ":"}
CONJUNCT_JOINERS = {"\u200c", "\u200d"}
TEMPLATES = {"${profile.native_name}", "${profile.display_name}"}
MAX_ROWS_PER_LAYER = 8
MAX_KEYS_PER_ROW = 20
MAX_TEXT_SCALARS = 16
MAX_TRANSFORMS = 1024
MAX_TRANSFORM_FROM_SCALARS = 16
MAX_TRANSFORM_TO_SCALARS = 32
MAX_LAYOUTS = 128
MAX_NOTICE_BYTES = 64 * 1024
EXPECTED_LAYER_ACTIONS = {
    "base": ["shift", "symbols", "language", "space", "delete", "enter"],
    "shift": ["shift", "symbols", "language", "space", "delete", "enter"],
    "symbols": ["letters", "symbols", "language", "space", "delete", "enter"],
    "numeric": ["space", "delete", "enter"],
}
SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "Deva": ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x11B00, 0x11B5F)),
    "Limb": ((0x1900, 0x194F),),
    "Newa": ((0x11400, 0x1147F),),
    "Olck": ((0x1C50, 0x1C7F),),
    "Tirh": ((0x11480, 0x114DF),),
    "Sunu": ((0x11BC0, 0x11BFF),),
    "Lepc": ((0x1C00, 0x1C4F),),
    "Tibt": ((0x0F00, 0x0FFF),),
    "Latn": (
        (0x0041, 0x005A),
        (0x0061, 0x007A),
        (0x00C0, 0x024F),
        (0x1E00, 0x1EFF),
    ),
}
FOUNDATION_PROFILE_IDS = {"eng-Latn-US", "npi-Deva-NP"}
PROFILE_COUNT_FIELDS = {"targets", "profiles", "scripts", "selectable"}
REDISTRIBUTION_VALUES = {
    "allowed",
    "prohibited",
    "permission_required",
    "unknown",
    "system",
}
LICENSE_BASE_FIELDS = {"id", "copyright", "redistribution"}
LICENSE_NOTICE_FIELDS = {"notice_path", "notice_sha256"}
LICENSE_OPTIONAL_FIELDS = LICENSE_NOTICE_FIELDS | {"license_url"}
BLOCKED_REASON_BY_AUTHORITY = {
    "release": {
        "direct": "DIRECT_PROFILE_NOT_RELEASE_APPROVED",
        "roman_phonetic": "ROMAN_ALIAS_NOT_RELEASE_APPROVED",
        "script_conversion": "SCRIPT_CONVERTER_NOT_RELEASE_APPROVED",
    },
    "internal": {
        "direct": "DIRECT_PROFILE_NOT_INTERNAL_READY",
        "roman_phonetic": "ROMAN_ALIAS_NOT_INTERNAL_READY",
        "script_conversion": "SCRIPT_CONVERTER_NOT_INTERNAL_READY",
    },
}


class LayoutError(ValueError):
    """Raised when a source cannot safely produce a layout lock."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LayoutError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        encoded = path.read_bytes()
    except FileNotFoundError as exc:
        raise LayoutError(f"missing {label}: {path}") from exc
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise LayoutError(f"{label} must not contain a UTF-8 BOM: {path}")
    try:
        text = encoded.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                LayoutError(f"unsupported JSON number: {token}")
            ),
        )
    except UnicodeDecodeError as exc:
        raise LayoutError(f"{label} must be UTF-8: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LayoutError(f"invalid JSON in {label}: {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise LayoutError(f"{label} must be a JSON object: {path}")
    return value, encoded


def _require_exact_keys(
    value: dict[str, Any],
    required: set[str],
    optional: set[str],
    location: str,
) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise LayoutError(f"{location} is missing fields: {', '.join(missing)}")
    if unknown:
        raise LayoutError(f"{location} has unknown fields: {', '.join(unknown)}")


def _require_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LayoutError(f"{location} must be a non-empty string")
    return value


def _require_int(value: object, location: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LayoutError(f"{location} must be an integer")
    if not minimum <= value <= maximum:
        raise LayoutError(f"{location} must be between {minimum} and {maximum}")
    return value


def _require_sha256(value: object, location: str) -> str:
    digest = _require_string(value, location)
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise LayoutError(f"{location} must be a lowercase SHA-256 digest")
    return digest


def _require_nfc(value: object, location: str, *, allow_templates: bool = False) -> str:
    text = _require_string(value, location)
    if unicodedata.normalize("NFC", text) != text:
        raise LayoutError(f"{location} must already be NFC")
    for character in text:
        codepoint = ord(character)
        category = unicodedata.category(character)
        if 0xD800 <= codepoint <= 0xDFFF or category in {
            "Cc",
            "Cn",
            "Cs",
            "Co",
            "Zl",
            "Zp",
        }:
            raise LayoutError(f"{location} contains unsafe U+{codepoint:04X}")
        if category == "Cf":
            raise LayoutError(
                f"{location} contains unsupported format U+{codepoint:04X}"
            )
    if "${" in text:
        if not allow_templates:
            raise LayoutError(f"{location} must not contain a profile template")
        _validate_template(text, location)
    return text


def _validate_text_script(text: str, input_script: str, location: str) -> None:
    ranges = SCRIPT_RANGES.get(input_script)
    if ranges is None:
        raise LayoutError(f"{location} uses unsupported input script {input_script}")
    for character in text:
        category = unicodedata.category(character)
        if category[0] not in {"L", "M", "N"}:
            continue
        codepoint = ord(character)
        if category[0] == "N" and 0x0030 <= codepoint <= 0x0039:
            continue
        if not any(start <= codepoint <= end for start, end in ranges):
            raise LayoutError(
                f"{location} contains U+{codepoint:04X} outside declared input script "
                f"{input_script}"
            )


def _validate_template(value: str, location: str) -> None:
    remaining = value
    while "${" in remaining:
        start = remaining.index("${")
        end = remaining.find("}", start)
        if end < 0:
            raise LayoutError(f"{location} contains an incomplete profile template")
        token = remaining[start : end + 1]
        if token not in TEMPLATES:
            raise LayoutError(f"{location} contains unsupported template {token}")
        remaining = remaining[end + 1 :]
    if "}" in remaining:
        raise LayoutError(f"{location} contains an unmatched template delimiter")


def _validate_layout_id(value: object, location: str) -> str:
    layout_id = _require_string(value, location)
    if not layout_id[0].isalnum() or any(
        not (character.islower() or character.isdigit() or character in "._-")
        for character in layout_id
    ):
        raise LayoutError(f"{location} must use lowercase ASCII identifier syntax")
    if not layout_id.isascii():
        raise LayoutError(f"{location} must be ASCII")
    return layout_id


def _validate_script(value: object, location: str) -> str:
    script = _require_string(value, location)
    if (
        len(script) != 4
        or not script.isascii()
        or not (script[0].isupper() and script[1:].islower() and script.isalpha())
    ):
        raise LayoutError(f"{location} must be an ISO 15924 code")
    return script


def _validate_input_reference(value: object, location: str) -> None:
    if not isinstance(value, dict):
        raise LayoutError(f"{location} must be an object")
    _require_exact_keys(value, {"path", "sha256"}, set(), location)
    _require_string(value["path"], f"{location}.path")
    _require_sha256(value["sha256"], f"{location}.sha256")


def _validate_profile_lock(profile_lock: dict[str, Any]) -> str:
    _require_exact_keys(
        profile_lock,
        {
            "lock_version",
            "generator",
            "generator_version",
            "compiler",
            "schemas",
            "catalog",
            "review",
            "counts",
            "scripts",
            "targets",
            "profiles",
        },
        set(),
        "shipping-profile lock",
    )
    lock_version = profile_lock["lock_version"]
    generator_version = profile_lock["generator_version"]
    if (
        isinstance(lock_version, bool)
        or isinstance(generator_version, bool)
        or (lock_version, generator_version) not in {(1, 1), (2, 2)}
    ):
        raise LayoutError("shipping-profile lock version/generator version is invalid")
    if profile_lock["generator"] != "build_shipping_profile_catalog":
        raise LayoutError("shipping-profile lock generator is invalid")
    _validate_input_reference(
        profile_lock["compiler"], "shipping-profile lock compiler"
    )
    schemas = profile_lock["schemas"]
    if not isinstance(schemas, dict) or set(schemas) != {"catalog", "review", "lock"}:
        raise LayoutError("shipping-profile lock schemas are invalid")
    for name, reference in schemas.items():
        _validate_input_reference(reference, f"shipping-profile lock {name} schema")
    counts = profile_lock["counts"]
    if not isinstance(counts, dict) or set(counts) != PROFILE_COUNT_FIELDS:
        raise LayoutError("shipping-profile lock counts are invalid")
    for name, value in counts.items():
        minimum = 2 if name == "selectable" else 1
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise LayoutError(f"shipping-profile lock counts.{name} is invalid")
    scripts = profile_lock["scripts"]
    if (
        not isinstance(scripts, list)
        or len(scripts) != counts["scripts"]
        or len(set(scripts)) != len(scripts)
        or scripts != sorted(scripts)
    ):
        raise LayoutError("shipping-profile lock script set is invalid")
    for index, script in enumerate(scripts):
        _validate_script(script, f"shipping-profile lock scripts[{index}]")
    targets = profile_lock["targets"]
    profiles = profile_lock["profiles"]
    if not isinstance(targets, list) or len(targets) != counts["targets"]:
        raise LayoutError("shipping-profile lock target array is invalid")
    if not isinstance(profiles, list) or len(profiles) != counts["profiles"]:
        raise LayoutError("shipping-profile lock profile array is invalid")
    for name in ("catalog", "review"):
        reference = profile_lock[name]
        if not isinstance(reference, dict):
            raise LayoutError(
                f"shipping-profile lock {name} reference must be an object"
            )
        _require_sha256(reference.get("sha256"), f"shipping-profile lock {name}.sha256")
    review_authority = profile_lock["review"].get("authority")
    if review_authority not in {"release", "internal"}:
        raise LayoutError("shipping-profile lock review authority is invalid")

    profile_ids: set[str] = set()
    selectable_ids: set[str] = set()
    for index, profile in enumerate(profiles):
        location = f"shipping-profile lock profiles[{index}]"
        if not isinstance(profile, dict):
            raise LayoutError(f"{location} must be an object")
        if lock_version == 2 and not {
            "pack_binding",
            "pack_artifact",
            "conversion_binding",
            "conversion_artifact",
        }.issubset(profile):
            raise LayoutError(f"{location} is missing v2 artifact binding fields")
        profile_id = _require_string(
            profile.get("profile_id"), f"{location}.profile_id"
        )
        if profile_id in profile_ids:
            raise LayoutError(f"duplicate shipping profile ID: {profile_id}")
        profile_ids.add(profile_id)
        _validate_layout_id(profile.get("layout_id"), f"{location}.layout_id")
        source_script = _validate_script(
            profile.get("source_script"), f"{location}.source_script"
        )
        output_script = _validate_script(
            profile.get("output_script"), f"{location}.output_script"
        )
        if source_script not in scripts or output_script not in scripts:
            raise LayoutError(f"{location} uses an undeclared script")
        selectable = profile.get("selectable")
        default_enabled = profile.get("default_enabled")
        evidence_ids = profile.get("evidence_ids")
        method_type = profile.get("method_type")
        lookup_kind = profile.get("lookup_kind")
        expected_blocked_reason = BLOCKED_REASON_BY_AUTHORITY[review_authority].get(
            method_type
        )
        if expected_blocked_reason is None:
            raise LayoutError(f"{location}.method_type is invalid")
        if not isinstance(selectable, bool) or not isinstance(default_enabled, bool):
            raise LayoutError(f"{location} selectability flags must be booleans")
        if not isinstance(evidence_ids, list) or any(
            not isinstance(item, str) or not item for item in evidence_ids
        ):
            raise LayoutError(f"{location}.evidence_ids must be strings")
        if selectable:
            selectable_ids.add(profile_id)
            pack_artifact = profile.get("pack_artifact")
            conversion_artifact = profile.get("conversion_artifact")
            evidence_artifacts = profile.get("evidence_artifacts")
            has_pack_pair = (
                isinstance(profile.get("pack_binding"), str)
                and bool(profile.get("pack_binding"))
                and isinstance(pack_artifact, dict)
                and pack_artifact.get("pack_id") == profile.get("pack_binding")
            )
            has_conversion_pair = (
                isinstance(profile.get("conversion_binding"), str)
                and bool(profile.get("conversion_binding"))
                and isinstance(conversion_artifact, dict)
                and conversion_artifact.get("converter_id")
                == profile.get("conversion_binding")
            )
            expected_artifact = (
                conversion_artifact if lookup_kind == "conversion" else pack_artifact
            )
            if (
                (
                    lookup_kind == "conversion"
                    and (not has_conversion_pair or has_pack_pair)
                )
                or (
                    lookup_kind in {"surface_prefix", "alias_prefix"}
                    and (not has_pack_pair or has_conversion_pair)
                )
                or lookup_kind not in {"surface_prefix", "alias_prefix", "conversion"}
                or (
                    lookup_kind == "conversion"
                    and (
                        profile.get("pack_binding") is not None
                        or pack_artifact is not None
                    )
                )
                or (
                    lookup_kind != "conversion"
                    and (
                        profile.get("conversion_binding") is not None
                        or conversion_artifact is not None
                    )
                )
                or profile.get("blocked_reason") is not None
                or profile.get("blocked_detail") is not None
                or not evidence_ids
                or not isinstance(evidence_artifacts, list)
                or not evidence_artifacts
                or not isinstance(expected_artifact, dict)
                or expected_artifact.get("release_mode") not in {"release", "internal"}
                or (
                    review_authority == "release"
                    and expected_artifact.get("release_mode") != "release"
                )
                or isinstance(profile.get("layout_revision"), bool)
                or not isinstance(profile.get("layout_revision"), int)
                or profile.get("layout_revision") < 1
            ):
                raise LayoutError(
                    f"selectable profile {profile_id} has invalid shipping authority"
                )
            _require_sha256(
                profile.get("layout_source_sha256"),
                f"selectable profile {profile_id}.layout_source_sha256",
            )
        elif (
            default_enabled
            or profile.get("pack_binding") is not None
            or profile.get("pack_artifact") is not None
            or profile.get("conversion_binding") is not None
            or profile.get("conversion_artifact") is not None
            or profile.get("blocked_reason") is None
            or profile.get("blocked_detail") is None
            or evidence_ids
            or profile.get("evidence_artifacts") != []
            or profile.get("layout_revision") is not None
            or profile.get("layout_source_sha256") is not None
        ):
            raise LayoutError(f"blocked profile {profile_id} has shipping authority")
        elif profile.get("blocked_reason") != expected_blocked_reason:
            raise LayoutError(
                f"blocked profile {profile_id} reason does not match "
                f"{review_authority} authority"
            )
    if len(selectable_ids) != counts["selectable"]:
        raise LayoutError("shipping-profile selectable count is invalid")
    missing_foundations = FOUNDATION_PROFILE_IDS - selectable_ids
    if missing_foundations:
        raise LayoutError(
            f"shipping-profile lock is missing foundations: {sorted(missing_foundations)}"
        )
    return review_authority


def _compile_key(
    key: object,
    layer_id: str,
    row_index: int,
    key_index: int,
    input_script: str,
) -> dict[str, Any]:
    location = f"layers.{layer_id}.rows[{row_index}][{key_index}]"
    key_id = f"{layer_id}.r{row_index}.k{key_index}"
    if isinstance(key, str):
        text = _require_nfc(key, location)
        if len(text) > MAX_TEXT_SCALARS:
            raise LayoutError(f"{location} exceeds {MAX_TEXT_SCALARS} Unicode scalars")
        _validate_text_script(text, input_script, location)
        return {
            "key_id": key_id,
            "kind": "text",
            "label": text,
            "text": text,
            "content_description": text,
            "action": None,
            "width_units": 100,
            "hold_action": None,
        }
    if not isinstance(key, dict):
        raise LayoutError(f"{location} must be a text string or key object")
    if "kind" in key:
        _require_exact_keys(
            key,
            {"kind", "text", "label", "content_description"},
            set(),
            location,
        )
        kind = _require_string(key["kind"], f"{location}.kind")
        if kind not in TEXT_KEY_KINDS:
            raise LayoutError(f"{location}.kind is unsupported: {kind}")
        label = _require_nfc(key["label"], f"{location}.label")
        description = _require_nfc(
            key["content_description"],
            f"{location}.content_description",
        )
        if kind in {
            "deva_conjunct_joiner",
            "deva_terminal_zwnj",
            "newa_conjunct_joiner",
        }:
            text = _require_string(key["text"], f"{location}.text")
            if (
                kind
                in {
                    "deva_conjunct_joiner",
                    "newa_conjunct_joiner",
                }
                and text not in CONJUNCT_JOINERS
            ):
                raise LayoutError(f"{location}.text must be exactly U+200C or U+200D")
            if kind == "deva_terminal_zwnj" and text != "\u200c":
                raise LayoutError(f"{location}.text must be exactly U+200C")
            required_script = "Newa" if kind == "newa_conjunct_joiner" else "Deva"
            if input_script != required_script:
                raise LayoutError(
                    f"{location} {kind} requires input script {required_script}"
                )
        else:
            text = _require_nfc(key["text"], f"{location}.text")
            if len(text) > MAX_TEXT_SCALARS:
                raise LayoutError(
                    f"{location}.text exceeds {MAX_TEXT_SCALARS} Unicode scalars"
                )
            if kind == "orthographic_word" and text not in ORTHOGRAPHIC_WORD_TEXTS:
                raise LayoutError(f"{location}.text must be exactly U+2018")
            if (
                kind == "intra_word_punctuation"
                and text not in INTRA_WORD_PUNCTUATION_TEXTS
            ):
                raise LayoutError(
                    f"{location}.text must be exactly hyphen, slash, backslash, or colon"
                )
            _validate_text_script(text, input_script, f"{location}.text")
        return {
            "key_id": key_id,
            "kind": kind,
            "label": label,
            "text": text,
            "content_description": description,
            "action": None,
            "width_units": 100,
            "hold_action": None,
        }
    _require_exact_keys(
        key,
        {"action", "label", "content_description", "width_units"},
        {"hold_action"},
        location,
    )
    action = _require_string(key["action"], f"{location}.action")
    if action not in ACTIONS:
        raise LayoutError(f"{location}.action is unsupported: {action}")
    label = _require_nfc(key["label"], f"{location}.label", allow_templates=True)
    description = _require_nfc(
        key["content_description"],
        f"{location}.content_description",
        allow_templates=True,
    )
    width = _require_int(key["width_units"], f"{location}.width_units", 25, 1000)
    hold_action = key.get("hold_action")
    if hold_action is not None:
        hold_action = _require_string(hold_action, f"{location}.hold_action")
        if hold_action not in HOLD_ACTIONS:
            raise LayoutError(f"{location}.hold_action is unsupported: {hold_action}")
        if action not in {"space", "language"}:
            raise LayoutError(
                f"{location}.hold_action is only valid for space or language"
            )
    return {
        "key_id": key_id,
        "kind": "action",
        "label": label,
        "text": None,
        "content_description": description,
        "action": action,
        "width_units": width,
        "hold_action": hold_action,
    }


def _compile_layer(value: object, layer_id: str, input_script: str) -> dict[str, Any]:
    location = f"layers.{layer_id}"
    if not isinstance(value, dict):
        raise LayoutError(f"{location} must be an object")
    _require_exact_keys(value, {"rows"}, set(), location)
    rows = value["rows"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS_PER_LAYER:
        raise LayoutError(f"{location}.rows must contain 1..{MAX_ROWS_PER_LAYER} rows")
    compiled_rows: list[list[dict[str, Any]]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, list) or not 1 <= len(row) <= MAX_KEYS_PER_ROW:
            raise LayoutError(
                f"{location}.rows[{row_index}] must contain 1..{MAX_KEYS_PER_ROW} keys"
            )
        compiled_rows.append(
            [
                _compile_key(key, layer_id, row_index, key_index, input_script)
                for key_index, key in enumerate(row)
            ]
        )
    text_values = [
        key["text"]
        for row in compiled_rows
        for key in row
        if key["kind"] in TEXT_KEY_KINDS
    ]
    if len(text_values) != len(set(text_values)):
        raise LayoutError(f"{location} contains duplicate text keys")
    action_locations = [
        (row_index, key["action"])
        for row_index, row in enumerate(compiled_rows)
        for key in row
        if key["kind"] == "action"
    ]
    if [action for _, action in action_locations] != EXPECTED_LAYER_ACTIONS[layer_id]:
        raise LayoutError(f"{location} does not match the closed v1 action sequence")
    if any(row_index != len(compiled_rows) - 1 for row_index, _ in action_locations):
        raise LayoutError(f"{location} action keys must be in the final row")
    if any(key["kind"] != "action" for key in compiled_rows[-1]):
        raise LayoutError(f"{location} final row must contain only actions")
    if layer_id in {"base", "shift"} and not any(
        any(
            start <= ord(character) <= end for start, end in SCRIPT_RANGES[input_script]
        )
        for text in text_values
        for character in text
        if unicodedata.category(character)[0] in {"L", "M", "N"}
    ):
        raise LayoutError(
            f"{location} has no key from declared input script {input_script}"
        )
    return {"rows": compiled_rows}


def _compile_transforms(value: object, input_script: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > MAX_TRANSFORMS:
        raise LayoutError(
            f"transforms must be an array with at most {MAX_TRANSFORMS} entries"
        )
    validated: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(value):
        location = f"transforms[{index}]"
        if not isinstance(row, dict):
            raise LayoutError(f"{location} must be an object")
        _require_exact_keys(row, {"from", "to"}, set(), location)
        source = _require_nfc(row["from"], f"{location}.from")
        target = _require_nfc(row["to"], f"{location}.to")
        if len(source) > MAX_TRANSFORM_FROM_SCALARS:
            raise LayoutError(f"{location}.from exceeds the bounded suffix length")
        if len(target) > MAX_TRANSFORM_TO_SCALARS:
            raise LayoutError(f"{location}.to exceeds the bounded replacement length")
        _validate_text_script(source, input_script, f"{location}.from")
        _validate_text_script(target, input_script, f"{location}.to")
        if source == target:
            raise LayoutError(f"{location} is an identity transform")
        if source in seen:
            raise LayoutError(f"duplicate transform suffix: {source!r}")
        seen.add(source)
        validated.append((source, target))
    validated.sort(key=lambda item: (-len(item[0]), item[0], item[1]))
    return [
        {"transform_id": f"t{index}", "from": source, "to": target}
        for index, (source, target) in enumerate(validated)
    ]


def _compile_license(
    source: dict[str, Any],
    path: Path,
    notice_directory: Path,
    notice_path_prefix: Path,
    authority: str,
) -> dict[str, str] | None:
    location = f"{path}.license"
    if "license" not in source:
        if authority == "release":
            raise LayoutError(f"{location} is required for release")
        return None

    license_row = source["license"]
    if not isinstance(license_row, dict):
        raise LayoutError(f"{location} must be an object")
    if authority == "release":
        _require_exact_keys(
            license_row,
            LICENSE_BASE_FIELDS | LICENSE_OPTIONAL_FIELDS,
            set(),
            location,
        )
    else:
        _require_exact_keys(
            license_row,
            LICENSE_BASE_FIELDS,
            LICENSE_OPTIONAL_FIELDS,
            location,
        )

    has_notice_path = "notice_path" in license_row
    has_notice_sha256 = "notice_sha256" in license_row
    if has_notice_path != has_notice_sha256:
        raise LayoutError(
            f"{location}.notice_path and notice_sha256 must be provided together"
        )

    redistribution = license_row["redistribution"]
    if redistribution not in REDISTRIBUTION_VALUES:
        raise LayoutError(f"{location}.redistribution is invalid")
    if authority == "release" and redistribution != "allowed":
        raise LayoutError(f"{location}.redistribution must be allowed for release")

    compiled_license = {
        "id": _require_string(license_row["id"], f"{location}.id"),
        "copyright": _require_nfc(license_row["copyright"], f"{location}.copyright"),
        "redistribution": redistribution,
    }

    if "license_url" in license_row:
        license_url = _require_string(
            license_row["license_url"], f"{location}.license_url"
        )
        if not license_url.startswith("https://"):
            raise LayoutError(f"{location}.license_url must use HTTPS")
        compiled_license["license_url"] = license_url

    if has_notice_path:
        notice_path = _require_string(
            license_row["notice_path"], f"{location}.notice_path"
        )
        notice_relative = Path(notice_path)
        if (
            notice_relative.parent != notice_path_prefix
            or notice_relative.name in {"", ".", "..", "manifest.json"}
            or any(
                character
                not in (
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
                )
                for character in notice_relative.name
            )
        ):
            raise LayoutError(f"{location}.notice_path is unsafe or reserved")
        notice_file = notice_directory / notice_relative.name
        if notice_file.is_symlink() or not notice_file.is_file():
            raise LayoutError(
                f"{location} notice is missing or not a regular file: {notice_path}"
            )
        notice_bytes = notice_file.read_bytes()
        if not notice_bytes or notice_bytes.startswith(b"\xef\xbb\xbf"):
            raise LayoutError(f"{location} notice must be non-empty UTF-8 without BOM")
        if len(notice_bytes) > MAX_NOTICE_BYTES:
            raise LayoutError(
                f"{location} notice exceeds the {MAX_NOTICE_BYTES}-byte runtime bound"
            )
        try:
            notice_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LayoutError(f"{location} notice must be UTF-8") from exc
        notice_sha256 = _require_sha256(
            license_row["notice_sha256"], f"{location}.notice_sha256"
        )
        if hashlib.sha256(notice_bytes).hexdigest() != notice_sha256:
            raise LayoutError(f"{location} notice SHA-256 mismatch")
        compiled_license["notice_path"] = notice_path
        compiled_license["notice_sha256"] = notice_sha256

    return compiled_license


def _validate_notice_inventory(
    notice_directory: Path,
    layouts: list[dict[str, Any]],
) -> None:
    expected_rows: list[str] = []
    for layout in layouts:
        license_row = layout["license"]
        if isinstance(license_row, dict) and "notice_path" in license_row:
            expected_rows.append(Path(license_row["notice_path"]).name)
    if len(expected_rows) != len(set(expected_rows)):
        raise LayoutError("every compiled layout notice must have a distinct asset")
    expected = set(expected_rows)

    if notice_directory.is_symlink():
        raise LayoutError("layout notice directory must not be symbolic")
    if not notice_directory.exists():
        if expected:
            raise LayoutError(f"layout notice directory is missing: {notice_directory}")
        return
    if not notice_directory.is_dir():
        raise LayoutError(
            f"layout notice directory is not a directory: {notice_directory}"
        )

    entries = sorted(notice_directory.iterdir(), key=lambda path: path.name)
    unsupported = [
        entry.name for entry in entries if entry.is_symlink() or not entry.is_file()
    ]
    if unsupported:
        raise LayoutError(
            f"layout notice directory has unsupported entries: {unsupported}"
        )
    actual = {entry.name for entry in entries}
    if actual != expected:
        raise LayoutError(
            "layout notice directory does not exactly match compiled notice pairs: "
            f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )


def _compile_layout(
    source: dict[str, Any],
    path: Path,
    source_bytes: bytes,
    notice_directory: Path,
    notice_path_prefix: Path,
    authority: str,
) -> dict[str, Any]:
    required = {
        "layout_format_version",
        "layout_id",
        "revision",
        "display_name",
        "input_script",
        "direction",
        "normalization",
        "unicode_data_version",
        "device_forms",
        "authors",
        "provenance",
        "field_layer_map",
        "layers",
        "transforms",
    }
    _require_exact_keys(source, required, {"license"}, path.as_posix())
    if source["layout_format_version"] != LAYOUT_FORMAT_VERSION:
        raise LayoutError(f"{path}: unsupported layout_format_version")
    layout_id = _validate_layout_id(source["layout_id"], f"{path}.layout_id")
    if path.stem != layout_id:
        raise LayoutError(f"layout ID/path mismatch: {layout_id} != {path.stem}")
    revision = _require_int(source["revision"], f"{path}.revision", 1, 2**31 - 1)
    display_name = _require_nfc(source["display_name"], f"{path}.display_name")
    input_script = _validate_script(source["input_script"], f"{path}.input_script")
    direction = _require_string(source["direction"], f"{path}.direction")
    if direction not in {"ltr", "rtl"}:
        raise LayoutError(f"{path}.direction must be ltr or rtl")
    if source["normalization"] != "NFC":
        raise LayoutError(f"{path}.normalization must be NFC")
    if source["unicode_data_version"] != UNICODE_DATA_VERSION:
        raise LayoutError(f"{path}.unicode_data_version must be {UNICODE_DATA_VERSION}")
    if unicodedata.unidata_version != UNICODE_DATA_VERSION:
        raise LayoutError(
            f"compiler Unicode database must be {UNICODE_DATA_VERSION}, got "
            f"{unicodedata.unidata_version}"
        )

    forms = source["device_forms"]
    if (
        not isinstance(forms, list)
        or not forms
        or any(not isinstance(item, str) for item in forms)
    ):
        raise LayoutError(f"{path}.device_forms must be a non-empty string array")
    if len(forms) != len(set(forms)) or not set(forms).issubset(DEVICE_FORMS):
        raise LayoutError(
            f"{path}.device_forms contains duplicates or unsupported forms"
        )
    if "phone" not in forms:
        raise LayoutError(f"{path}.device_forms must include phone")

    authors = source["authors"]
    if not isinstance(authors, list) or not authors:
        raise LayoutError(f"{path}.authors must be a non-empty array")
    validated_authors = [
        _require_nfc(author, f"{path}.authors[{index}]")
        for index, author in enumerate(authors)
    ]
    if len(validated_authors) != len(set(validated_authors)):
        raise LayoutError(f"{path}.authors contains duplicates")

    compiled_license = _compile_license(
        source,
        path,
        notice_directory,
        notice_path_prefix,
        authority,
    )

    provenance = source["provenance"]
    if not isinstance(provenance, list) or not provenance:
        raise LayoutError(f"{path}.provenance must be a non-empty array")
    compiled_provenance: list[dict[str, str]] = []
    for index, row in enumerate(provenance):
        location = f"{path}.provenance[{index}]"
        if not isinstance(row, dict):
            raise LayoutError(f"{location} must be an object")
        _require_exact_keys(
            row,
            {"kind", "source", "revision", "sha256", "note"},
            {"source_url"},
            location,
        )
        kind = _require_string(row["kind"], f"{location}.kind")
        if kind not in {"project_authored", "adapted", "standard_reference"}:
            raise LayoutError(f"{location}.kind is unsupported")
        compiled_row = {
            "kind": kind,
            "source": _require_nfc(row["source"], f"{location}.source"),
            "revision": _require_nfc(row["revision"], f"{location}.revision"),
            "sha256": _require_sha256(row["sha256"], f"{location}.sha256"),
            "note": _require_nfc(row["note"], f"{location}.note"),
        }
        if "source_url" in row:
            source_url = _require_string(row["source_url"], f"{location}.source_url")
            if not source_url.startswith("https://"):
                raise LayoutError(f"{location}.source_url must use HTTPS")
            compiled_row["source_url"] = source_url
        compiled_provenance.append(compiled_row)

    if source["field_layer_map"] != FIELD_LAYER_MAP:
        raise LayoutError(f"{path}.field_layer_map must match the closed v1 field map")
    layers = source["layers"]
    if not isinstance(layers, dict) or set(layers) != set(LAYERS):
        raise LayoutError(f"{path}.layers must contain exactly {', '.join(LAYERS)}")

    return {
        "layout_id": layout_id,
        "revision": revision,
        "display_name": display_name,
        "input_script": input_script,
        "direction": direction,
        "normalization": "NFC",
        "unicode_data_version": UNICODE_DATA_VERSION,
        "device_forms": forms,
        "authors": validated_authors,
        "license": compiled_license,
        "provenance": compiled_provenance,
        "field_layer_map": dict(FIELD_LAYER_MAP),
        "source": {
            "path": path.as_posix(),
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
        },
        "layers": {
            layer_id: _compile_layer(layers[layer_id], layer_id, input_script)
            for layer_id in LAYERS
        },
        "transforms": _compile_transforms(source["transforms"], input_script),
    }


def build_lock(
    source_directory: Path,
    profile_lock: dict[str, Any],
    *,
    profile_lock_path: str,
    profile_lock_sha256: str,
    source_path_prefix: str = "layouts/src",
    notice_directory: Path | None = None,
    compiler_reference: dict[str, str] | None = None,
    schema_references: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not source_directory.is_dir():
        raise LayoutError(f"layout source directory is missing: {source_directory}")
    entries = sorted(source_directory.iterdir(), key=lambda path: path.name)
    unexpected = [
        entry.name
        for entry in entries
        if entry.is_symlink() or not entry.is_file() or entry.suffix != ".json"
    ]
    if unexpected:
        raise LayoutError(
            f"layout source directory has unsupported entries: {unexpected}"
        )
    if not entries:
        raise LayoutError("layout source directory has no JSON sources")
    if len(entries) > MAX_LAYOUTS:
        raise LayoutError(
            f"layout source directory exceeds the {MAX_LAYOUTS}-layout runtime bound"
        )

    notice_directory = notice_directory or source_directory.parent / "notices"
    notice_path_prefix = Path(source_path_prefix).parent / "notices"
    if (
        hashlib.sha256(_canonical_bytes(profile_lock)).hexdigest()
        != profile_lock_sha256
    ):
        raise LayoutError(
            "shipping-profile lock object does not match its claimed SHA-256"
        )
    authority = _validate_profile_lock(profile_lock)
    if compiler_reference is None or schema_references is None:
        raise LayoutError("compiler and schema references are required")
    _validate_input_reference(compiler_reference, "compiler reference")
    if set(schema_references) != {"source", "lock"}:
        raise LayoutError("schema references must contain source and lock")
    for name, reference in schema_references.items():
        _validate_input_reference(reference, f"{name} schema reference")

    layouts: list[dict[str, Any]] = []
    layout_ids: set[str] = set()
    for path in entries:
        source, encoded = _read_object(path, "layout source")
        display_path = Path(source_path_prefix) / path.name
        compiled = _compile_layout(
            source,
            display_path,
            encoded,
            notice_directory,
            notice_path_prefix,
            authority,
        )
        if compiled["layout_id"] in layout_ids:
            raise LayoutError(f"duplicate layout ID: {compiled['layout_id']}")
        layout_ids.add(compiled["layout_id"])
        layouts.append(compiled)
    layouts.sort(key=lambda row: row["layout_id"])
    _validate_notice_inventory(notice_directory, layouts)

    profiles = profile_lock.get("profiles")
    if not isinstance(profiles, list):
        raise LayoutError("shipping-profile lock has no profiles array")
    bindings: dict[str, str] = {}
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            raise LayoutError(f"shipping-profile profiles[{index}] must be an object")
        if profile.get("selectable") is not True:
            continue
        profile_id = _require_string(
            profile.get("profile_id"), f"profiles[{index}].profile_id"
        )
        layout_id = _validate_layout_id(
            profile.get("layout_id"), f"profile {profile_id}.layout_id"
        )
        source_script = _validate_script(
            profile.get("source_script"), f"profile {profile_id}.source_script"
        )
        if profile_id in bindings:
            raise LayoutError(f"duplicate selectable profile ID: {profile_id}")
        matching = next(
            (layout for layout in layouts if layout["layout_id"] == layout_id), None
        )
        if matching is None:
            raise LayoutError(
                f"selectable profile {profile_id} has no compiled layout: {layout_id}"
            )
        if matching["input_script"] != source_script:
            raise LayoutError(
                f"profile {profile_id} source script {source_script} does not match "
                f"layout {layout_id} input script {matching['input_script']}"
            )
        if matching["revision"] != profile.get("layout_revision"):
            raise LayoutError(
                f"profile {profile_id} reviewed layout revision does not match {layout_id}"
            )
        if matching["source"]["sha256"] != profile.get("layout_source_sha256"):
            raise LayoutError(
                f"profile {profile_id} reviewed layout source SHA-256 does not match {layout_id}"
            )
        bindings[profile_id] = layout_id
    if not bindings:
        raise LayoutError("shipping-profile lock has no selectable layout bindings")
    if set(bindings.values()) != layout_ids:
        unbound = sorted(layout_ids - set(bindings.values()))
        raise LayoutError(
            f"compiled layout sources are not selectable-profile bound: {unbound}"
        )

    return {
        "layout_lock_version": LAYOUT_LOCK_VERSION,
        "generator": "build_keyboard_layouts",
        "generator_version": GENERATOR_VERSION,
        "unicode_data_version": UNICODE_DATA_VERSION,
        "transform_semantics": TRANSFORM_SEMANTICS,
        "compiler": compiler_reference,
        "schemas": schema_references,
        "source_directory": source_path_prefix,
        "profile_lock": {
            "path": profile_lock_path,
            "sha256": profile_lock_sha256,
        },
        "profile_bindings": [
            {
                "profile_id": profile_id,
                "layout_id": layout_id,
                "source_script": next(
                    layout["input_script"]
                    for layout in layouts
                    if layout["layout_id"] == layout_id
                ),
                "revision": next(
                    layout["revision"]
                    for layout in layouts
                    if layout["layout_id"] == layout_id
                ),
                "source_sha256": next(
                    layout["source"]["sha256"]
                    for layout in layouts
                    if layout["layout_id"] == layout_id
                ),
            }
            for profile_id, layout_id in sorted(bindings.items())
        ],
        "layout_count": len(layouts),
        "layouts": layouts,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--profile-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile_lock, profile_bytes = _read_object(
        args.profile_lock, "shipping-profile lock"
    )
    repository_root = Path(__file__).resolve().parents[1]
    compiler_path = repository_root / "tools" / "build_keyboard_layouts.py"
    source_schema_path = repository_root / "schemas" / "layout-v1.schema.json"
    lock_schema_path = repository_root / "schemas" / "layout-lock-v1.schema.json"
    compiler_reference = {
        "path": "tools/build_keyboard_layouts.py",
        "sha256": hashlib.sha256(compiler_path.read_bytes()).hexdigest(),
    }
    schema_references = {
        "source": {
            "path": "schemas/layout-v1.schema.json",
            "sha256": hashlib.sha256(source_schema_path.read_bytes()).hexdigest(),
        },
        "lock": {
            "path": "schemas/layout-lock-v1.schema.json",
            "sha256": hashlib.sha256(lock_schema_path.read_bytes()).hexdigest(),
        },
    }
    lock = build_lock(
        args.source_directory,
        profile_lock,
        profile_lock_path=args.profile_lock.resolve()
        .relative_to(repository_root)
        .as_posix(),
        profile_lock_sha256=hashlib.sha256(profile_bytes).hexdigest(),
        source_path_prefix=args.source_directory.resolve()
        .relative_to(repository_root)
        .as_posix(),
        compiler_reference=compiler_reference,
        schema_references=schema_references,
    )
    encoded = _canonical_bytes(lock)
    if args.check:
        try:
            current = args.output.read_bytes()
        except FileNotFoundError as exc:
            raise SystemExit(f"layout lock is missing: {args.output}") from exc
        if current != encoded:
            raise SystemExit(f"layout lock is stale: {args.output}")
        return 0
    _write_atomic(args.output, encoded)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LayoutError as error:
        raise SystemExit(f"error: {error}") from error
