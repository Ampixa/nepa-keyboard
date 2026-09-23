#!/usr/bin/env python3
"""Validate a pending or completed native layout-review packet without writes."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

if __package__:
    from tools import build_keyboard_layouts as layout_compiler
    from tools import validate_keyboard_layout_candidate as candidate_validator
else:
    import build_keyboard_layouts as layout_compiler  # type: ignore[import-not-found]
    import validate_keyboard_layout_candidate as candidate_validator  # type: ignore[import-not-found]


LayoutError = layout_compiler.LayoutError
_canonical_bytes = layout_compiler._canonical_bytes
_compile_layout = layout_compiler._compile_layout
_read_object = layout_compiler._read_object

NATIVE_REVIEW_VALIDATION_VERSION = 1
REVIEW_FORMAT_VERSION = 1
REVIEW_DIRECTORY = Path("layouts/reviews")
REVIEW_SCHEMA_PATH = Path("schemas/layout-native-review-v1.schema.json")
VALIDATOR_PATH = Path("tools/validate_layout_native_review.py")
EXPECTED_REVIEW_ID = "newa-nepal-qwerty-direct-v1-native-review"
EXPECTED_REVIEW_PROFILE = "newa_qwerty_direct_v1"
EXPECTED_CANDIDATE_PATH = Path("layouts/research/newa-nepal-qwerty-direct-v1.json")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
KEY_ID_RE = re.compile(r"^(base|shift|symbols|numeric)\.r[0-9]+\.k[0-9]+$")
DECISION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
CODEPOINT_RE = re.compile(r"^U\+([0-9A-F]{4,6})$")
FULL_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
REVIEW_STATES = {"pending", "accepted", "rejected"}

SECTION_LAYERS = {
    "base_grid": "base",
    "shift_grid": "shift",
    "symbols_grid": "symbols",
    "numeric_grid": "numeric",
}

DECISION_CONTRACT: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "base_punctuation": (
        ("base.r2.k7",),
        ("keep_u1144b", "use_u1144d"),
    ),
    "shift_lha": (
        ("shift.r1.k8",),
        ("keep_u1142f", "use_u1144c"),
    ),
    "shifted_punctuation": (
        ("shift.r2.k7",),
        ("keep_atomic_u1144c", "use_ra_u_shortcut"),
    ),
    "atomic_om": (
        ("symbols.r2.k4",),
        ("keep_atomic_u11449", "use_context_sequence"),
    ),
    "joiner_access": (
        ("base.r2.k8", "base.r2.k9", "base.r2.k10"),
        ("keep_separate_keys", "redesign_access"),
    ),
    "murmured_resonants": (
        ("shift.r1.k8",),
        (
            "require_all_directly",
            "require_layout_v2_longpress",
            "accept_shift_symbol_coverage",
        ),
    ),
    "long_press_strategy": (
        (),
        ("shift_symbol_layers", "requires_layout_v2_longpress"),
    ),
    "accessibility_names": (
        (),
        ("english_unicode_names", "native_newa_names", "bilingual_names"),
    ),
}

DECISION_QUESTIONS = {
    "base_punctuation": (
        "Should the base punctuation key keep U+1144B NEWA DANDA or use "
        "U+1144D NEWA COMMA?"
    ),
    "shift_lha": (
        "Should Shift-L keep U+1142F NEWA LETTER LHA or use U+1144C NEWA DOUBLE DANDA?"
    ),
    "shifted_punctuation": (
        "Should the shifted punctuation key keep atomic U+1144C or expose the "
        "RA plus U-vowel shortcut?"
    ),
    "atomic_om": (
        "Should the symbols layer keep atomic U+11449 NEWA OM instead of a "
        "contextual sequence?"
    ),
    "joiner_access": (
        "Should VIRAMA, ZWJ, and ZWNJ remain three separate conjunct-input keys?"
    ),
    "murmured_resonants": (
        "How must the six atomic murmured resonants be exposed before promotion?"
    ),
    "long_press_strategy": (
        "Can shift and symbol layers carry the reviewed alternatives, or is "
        "layout-v2 long-press required?"
    ),
    "accessibility_names": (
        "Which spoken naming policy should all text keys use, including explicit "
        "Newa character names?"
    ),
}

COVERAGE_CONTRACT: tuple[tuple[int, str, str], ...] = (
    (0x11413, "NEWA LETTER NGHA", "review"),
    (0x11419, "NEWA LETTER NYHA", "review"),
    (0x11424, "NEWA LETTER NHA", "review"),
    (0x1142A, "NEWA LETTER MHA", "review"),
    (0x1142D, "NEWA LETTER RHA", "review"),
    (0x1142F, "NEWA LETTER LHA", "review"),
    (0x11442, "NEWA SIGN VIRAMA", "review"),
    (0x11449, "NEWA OM", "review"),
    (0x1144B, "NEWA DANDA", "review"),
    (0x1144C, "NEWA DOUBLE DANDA", "review"),
    (0x1144D, "NEWA COMMA", "review"),
    (0x200C, "ZERO WIDTH NON-JOINER", "review"),
    (0x200D, "ZERO WIDTH JOINER", "review"),
    (0x1145C, "RESERVED NEWA U+1145C", "forbidden"),
    (0xFFFD, "REPLACEMENT CHARACTER", "forbidden"),
)


def _exact_fields(value: dict[str, Any], expected: set[str], location: str) -> None:
    actual = set(value)
    if actual != expected:
        raise LayoutError(
            f"{location} must contain exactly {sorted(expected)}, got {sorted(actual)}"
        )


def _object(value: object, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LayoutError(f"{location} must be an object")
    return value


def _array(value: object, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise LayoutError(f"{location} must be an array")
    return value


def _integer(value: object, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LayoutError(f"{location} must be an integer")
    return value


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LayoutError(f"{location} must be a non-empty string")
    if unicodedata.normalize("NFC", value) != value:
        raise LayoutError(f"{location} must be NFC")
    for character in value:
        codepoint = ord(character)
        if unicodedata.category(character) in {
            "Cc",
            "Cf",
            "Cs",
            "Co",
            "Cn",
            "Zl",
            "Zp",
        }:
            raise LayoutError(f"{location} contains unsafe U+{codepoint:04X}")
    return value


def _human_evidence(value: object, location: str) -> str:
    text = _string(value, location)
    if not any(unicodedata.category(character).startswith("L") for character in text):
        raise LayoutError(f"{location} must contain a visible letter")
    return text


def _sha256(value: object, location: str) -> str:
    digest = _string(value, location)
    if not SHA256_RE.fullmatch(digest):
        raise LayoutError(f"{location} must be a lowercase SHA-256 digest")
    return digest


def _regular_file(path: Path, location: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise LayoutError(f"{location} must be a regular file: {path}")


def _validate_input_reference(
    value: object,
    *,
    expected_path: str,
    actual_path: Path,
    location: str,
) -> dict[str, str]:
    row = _object(value, location)
    _exact_fields(row, {"path", "sha256"}, location)
    if row["path"] != expected_path:
        raise LayoutError(f"{location}.path must be {expected_path}")
    _regular_file(actual_path, location)
    digest = _sha256(row["sha256"], f"{location}.sha256")
    actual = hashlib.sha256(actual_path.read_bytes()).hexdigest()
    if digest != actual:
        raise LayoutError(f"{location} SHA-256 mismatch")
    return {"path": expected_path, "sha256": actual}


def _validate_review_path(review_path: Path, root: Path) -> Path:
    review_directory = root / REVIEW_DIRECTORY
    if review_directory.is_symlink() or not review_directory.is_dir():
        raise LayoutError(f"native review directory is invalid: {review_directory}")
    supplied = review_path if review_path.is_absolute() else Path.cwd() / review_path
    _regular_file(supplied, "native review packet")
    resolved = supplied.resolve()
    if resolved.parent != review_directory or not resolved.name.endswith(
        ".review.json"
    ):
        raise LayoutError(
            "native review packet must be one direct .review.json child of "
            f"{review_directory}"
        )
    return resolved


def _compile_candidate(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_path = root / EXPECTED_CANDIDATE_PATH
    report = candidate_validator.validate_candidate(
        candidate_path,
        repository_root=root,
    )
    source, source_bytes = _read_object(candidate_path, "research layout candidate")
    compiled = _compile_layout(
        source,
        EXPECTED_CANDIDATE_PATH,
        source_bytes,
        root / "layouts" / "internal" / "notices",
        Path("layouts/internal/notices"),
        "internal",
    )
    return report, compiled


def _text_key_index(
    compiled: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_text: dict[str, list[str]] = {}
    for layer_id in ("base", "shift", "symbols", "numeric"):
        for row in compiled["layers"][layer_id]["rows"]:
            for key in row:
                if key["kind"] == "action":
                    continue
                key_id = key["key_id"]
                text = key["text"]
                if key_id in by_id:
                    raise LayoutError(
                        f"compiled candidate has duplicate key ID {key_id}"
                    )
                by_id[key_id] = key
                by_text.setdefault(text, []).append(key_id)
    for key_ids in by_text.values():
        key_ids.sort()
    return by_id, by_text


def _validate_sections(
    value: object,
    compiled: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    rows = _array(value, "review.sections")
    if len(rows) != len(SECTION_LAYERS):
        raise LayoutError("review.sections must contain the four closed layer sections")
    by_id: dict[str, dict[str, Any]] = {}
    pending: list[str] = []
    validated: list[dict[str, Any]] = []
    for index, value_row in enumerate(rows):
        location = f"review.sections[{index}]"
        row = _object(value_row, location)
        _exact_fields(
            row, {"section_id", "key_ids", "state", "reviewer_note"}, location
        )
        section_id = _string(row["section_id"], f"{location}.section_id")
        if section_id not in SECTION_LAYERS or section_id in by_id:
            raise LayoutError(f"{location}.section_id is unsupported or duplicate")
        layer_id = SECTION_LAYERS[section_id]
        expected_key_ids = [
            key["key_id"]
            for compiled_row in compiled["layers"][layer_id]["rows"]
            for key in compiled_row
            if key["kind"] != "action"
        ]
        key_ids = _array(row["key_ids"], f"{location}.key_ids")
        if key_ids != expected_key_ids:
            raise LayoutError(
                f"{location}.key_ids do not cover the compiled {layer_id} layer"
            )
        state = _string(row["state"], f"{location}.state")
        if state not in REVIEW_STATES:
            raise LayoutError(f"{location}.state is unsupported")
        reviewer_note = row["reviewer_note"]
        if reviewer_note is not None:
            reviewer_note = _string(reviewer_note, f"{location}.reviewer_note")
        if state == "pending":
            pending.append(section_id)
        validated_row = {
            "section_id": section_id,
            "key_ids": key_ids,
            "state": state,
            "reviewer_note": reviewer_note,
        }
        by_id[section_id] = validated_row
        validated.append(validated_row)
    if set(by_id) != set(SECTION_LAYERS):
        raise LayoutError("review.sections does not match the closed section inventory")
    return validated, pending


def _validate_decisions(
    value: object,
    key_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    rows = _array(value, "review.decisions")
    if len(rows) != len(DECISION_CONTRACT):
        raise LayoutError("review.decisions does not match the closed decision count")
    by_id: dict[str, dict[str, Any]] = {}
    pending: list[str] = []
    validated: list[dict[str, Any]] = []
    for index, value_row in enumerate(rows):
        location = f"review.decisions[{index}]"
        row = _object(value_row, location)
        _exact_fields(
            row,
            {
                "decision_id",
                "question",
                "key_ids",
                "options",
                "state",
                "selected_option",
                "reviewer_note",
            },
            location,
        )
        decision_id = _string(row["decision_id"], f"{location}.decision_id")
        if not DECISION_ID_RE.fullmatch(decision_id) or decision_id in by_id:
            raise LayoutError(f"{location}.decision_id is invalid or duplicate")
        contract = DECISION_CONTRACT.get(decision_id)
        if contract is None:
            raise LayoutError(f"{location}.decision_id is not in the closed contract")
        key_ids = _array(row["key_ids"], f"{location}.key_ids")
        options = _array(row["options"], f"{location}.options")
        expected_key_ids = (
            list(key_index)
            if decision_id == "accessibility_names"
            else list(contract[0])
        )
        if key_ids != expected_key_ids or options != list(contract[1]):
            raise LayoutError(f"{location} does not match its key and option contract")
        if any(
            not isinstance(key_id, str)
            or not KEY_ID_RE.fullmatch(key_id)
            or key_id not in key_index
            for key_id in key_ids
        ):
            raise LayoutError(f"{location}.key_ids reference an unknown key")
        question = _string(row["question"], f"{location}.question")
        if question != DECISION_QUESTIONS[decision_id]:
            raise LayoutError(f"{location}.question does not match the closed contract")
        state = _string(row["state"], f"{location}.state")
        if state not in REVIEW_STATES:
            raise LayoutError(f"{location}.state is unsupported")
        selected = row["selected_option"]
        if selected is not None:
            selected = _string(selected, f"{location}.selected_option")
            if selected not in options:
                raise LayoutError(f"{location}.selected_option is not an option")
        note = row["reviewer_note"]
        if note is not None:
            note = _string(note, f"{location}.reviewer_note")
        if state == "pending":
            if selected is not None or note is not None:
                raise LayoutError(f"{location} pending decision must be unresolved")
            pending.append(decision_id)
        elif selected is None:
            raise LayoutError(f"{location} resolved decision must select an option")
        validated_row = {
            "decision_id": decision_id,
            "question": question,
            "key_ids": key_ids,
            "options": options,
            "state": state,
            "selected_option": selected,
            "reviewer_note": note,
        }
        by_id[decision_id] = validated_row
        validated.append(validated_row)
    if set(by_id) != set(DECISION_CONTRACT):
        raise LayoutError("review.decisions is missing a required decision")
    return validated, pending


def _validate_coverage(
    value: object,
    by_text: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], list[str], int]:
    rows = _array(value, "review.coverage")
    if len(rows) != len(COVERAGE_CONTRACT):
        raise LayoutError("review.coverage does not match the closed coverage count")
    expected = {
        codepoint: (name, policy) for codepoint, name, policy in COVERAGE_CONTRACT
    }
    seen: set[int] = set()
    pending: list[str] = []
    missing_count = 0
    validated: list[dict[str, Any]] = []
    for index, value_row in enumerate(rows):
        location = f"review.coverage[{index}]"
        row = _object(value_row, location)
        _exact_fields(
            row,
            {"codepoint", "name", "key_ids", "availability", "review_state"},
            location,
        )
        codepoint_label = _string(row["codepoint"], f"{location}.codepoint")
        match = CODEPOINT_RE.fullmatch(codepoint_label)
        if match is None:
            raise LayoutError(f"{location}.codepoint is invalid")
        codepoint = int(match.group(1), 16)
        if codepoint in seen or codepoint not in expected:
            raise LayoutError(f"{location}.codepoint is unsupported or duplicate")
        seen.add(codepoint)
        expected_name, policy = expected[codepoint]
        if row["name"] != expected_name:
            raise LayoutError(f"{location}.name does not match the closed contract")
        actual_key_ids = by_text.get(chr(codepoint), [])
        key_ids = _array(row["key_ids"], f"{location}.key_ids")
        if key_ids != actual_key_ids:
            raise LayoutError(f"{location}.key_ids do not match the compiled candidate")
        expected_availability = (
            "forbidden"
            if policy == "forbidden"
            else ("covered" if actual_key_ids else "missing")
        )
        if row["availability"] != expected_availability:
            raise LayoutError(f"{location}.availability does not match the candidate")
        if policy == "forbidden" and actual_key_ids:
            raise LayoutError(f"{location} forbidden scalar is present")
        if expected_availability == "missing":
            missing_count += 1
        state = _string(row["review_state"], f"{location}.review_state")
        if state not in REVIEW_STATES:
            raise LayoutError(f"{location}.review_state is unsupported")
        if state == "pending":
            pending.append(codepoint_label)
        validated.append(
            {
                "codepoint": codepoint_label,
                "name": expected_name,
                "key_ids": key_ids,
                "availability": expected_availability,
                "review_state": state,
            }
        )
    if seen != set(expected):
        raise LayoutError("review.coverage is missing a required scalar")
    return validated, pending, missing_count


def _validate_reviewer(
    reviewer_value: object,
    reviewed_at_value: object,
) -> tuple[dict[str, str] | None, str | None]:
    if reviewer_value is None:
        reviewer = None
    else:
        reviewer_row = _object(reviewer_value, "review.reviewer")
        _exact_fields(
            reviewer_row,
            {"name", "native_language", "experience"},
            "review.reviewer",
        )
        if reviewer_row["native_language"] != "Nepal Bhasa":
            raise LayoutError("review.reviewer.native_language must be Nepal Bhasa")
        reviewer = {
            "name": _human_evidence(
                reviewer_row["name"],
                "review.reviewer.name",
            ),
            "native_language": "Nepal Bhasa",
            "experience": _human_evidence(
                reviewer_row["experience"],
                "review.reviewer.experience",
            ),
        }
    if reviewed_at_value is None:
        reviewed_at = None
    else:
        reviewed_at = _string(reviewed_at_value, "review.reviewed_at")
        if not FULL_DATE_RE.fullmatch(reviewed_at):
            raise LayoutError("review.reviewed_at must use YYYY-MM-DD")
        try:
            date.fromisoformat(reviewed_at)
        except ValueError as exc:
            raise LayoutError("review.reviewed_at must be an ISO date") from exc
    if (reviewer is None) != (reviewed_at is None):
        raise LayoutError("review.reviewer and reviewed_at must be paired")
    return reviewer, reviewed_at


def _validate_candidate_safety(key_index: dict[str, dict[str, Any]]) -> None:
    for key_id, key in key_index.items():
        text = key["text"]
        for character in text:
            codepoint = ord(character)
            if codepoint in {0x1145C, 0xFFFD} or 0xE000 <= codepoint <= 0xF8FF:
                raise LayoutError(
                    f"compiled candidate {key_id} contains forbidden U+{codepoint:04X}"
                )


def _validate_completed_decision_consistency(
    decisions: list[dict[str, Any]],
) -> None:
    selected = {row["decision_id"]: row["selected_option"] for row in decisions}
    requires_long_press = (
        selected["murmured_resonants"] == "require_layout_v2_longpress"
    )
    if requires_long_press != (
        selected["long_press_strategy"] == "requires_layout_v2_longpress"
    ):
        raise LayoutError(
            "completed review has inconsistent murmured-resonant and long-press decisions"
        )


def _validate_accepted_candidate_decisions(
    decisions: list[dict[str, Any]],
    key_index: dict[str, dict[str, Any]],
) -> None:
    selected = {row["decision_id"]: row["selected_option"] for row in decisions}
    expected_text = {
        "base_punctuation": ("base.r2.k7", "\U0001144b", "keep_u1144b"),
        "shift_lha": ("shift.r1.k8", "\U0001142f", "keep_u1142f"),
        "shifted_punctuation": (
            "shift.r2.k7",
            "\U0001144c",
            "keep_atomic_u1144c",
        ),
        "atomic_om": ("symbols.r2.k4", "\U00011449", "keep_atomic_u11449"),
    }
    for decision_id, (key_id, text, candidate_option) in expected_text.items():
        if (
            key_index[key_id]["text"] != text
            or selected[decision_id] != candidate_option
        ):
            raise LayoutError(
                f"accepted {decision_id} decision does not match the bound candidate"
            )

    joiner_texts = tuple(
        key_index[key_id]["text"]
        for key_id in ("base.r2.k8", "base.r2.k9", "base.r2.k10")
    )
    if joiner_texts != ("\U00011442", "\u200d", "\u200c") or (
        selected["joiner_access"] != "keep_separate_keys"
    ):
        raise LayoutError(
            "accepted joiner_access decision does not match the bound candidate"
        )

    resonants = {
        "\U00011413",
        "\U00011419",
        "\U00011424",
        "\U0001142a",
        "\U0001142d",
        "\U0001142f",
    }
    resonant_key_ids = {
        key_id for key_id, key in key_index.items() if key["text"] in resonants
    }
    if (
        len(resonant_key_ids) != len(resonants)
        or any(
            not key_id.startswith(("shift.", "symbols.")) for key_id in resonant_key_ids
        )
        or selected["murmured_resonants"] != "accept_shift_symbol_coverage"
    ):
        raise LayoutError(
            "accepted murmured_resonants decision does not match the bound candidate"
        )
    if selected["long_press_strategy"] != "shift_symbol_layers":
        raise LayoutError(
            "accepted long_press_strategy decision does not match layout v1"
        )

    naming_policy = selected["accessibility_names"]
    text_to_description: dict[str, str] = {}
    description_to_text: dict[str, str] = {}
    for key_id, key in key_index.items():
        text = key["text"]
        description = key["content_description"]
        try:
            unicode_name = " + ".join(unicodedata.name(character) for character in text)
        except ValueError as exc:
            raise LayoutError(
                f"accepted accessibility_names cannot name unassigned text at {key_id}"
            ) from exc
        if naming_policy == "english_unicode_names":
            if description != unicode_name:
                raise LayoutError(
                    "accepted English accessibility policy requires exact Unicode "
                    f"names; mismatch at {key_id}"
                )
        elif naming_policy == "native_newa_names":
            if (
                description == unicode_name
                or sum(
                    unicodedata.category(character).startswith("L")
                    for character in description
                )
                < 2
            ):
                raise LayoutError(
                    "accepted native accessibility policy requires a meaningful "
                    f"native spoken name at {key_id}"
                )
        elif naming_policy == "bilingual_names":
            native_name, separator, english_name = description.rpartition(" · ")
            if (
                not separator
                or english_name != unicode_name
                or sum(
                    unicodedata.category(character).startswith("L")
                    for character in native_name
                )
                < 2
            ):
                raise LayoutError(
                    "accepted bilingual accessibility policy requires a native name "
                    f"and exact Unicode name at {key_id}"
                )
        else:
            raise LayoutError("accepted accessibility naming policy is unsupported")

        previous_description = text_to_description.setdefault(text, description)
        if previous_description != description:
            raise LayoutError(
                "accepted accessibility policy assigns conflicting names to the "
                f"same text at {key_id}"
            )
        previous_text = description_to_text.setdefault(description, text)
        if previous_text != text:
            raise LayoutError(
                "accepted accessibility policy reuses one spoken name for different "
                f"text at {key_id}"
            )


def validate_review(
    review_path: Path,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    root = (repository_root or Path(__file__).resolve().parents[1]).resolve()
    resolved_review = _validate_review_path(review_path, root)
    review, review_bytes = _read_object(resolved_review, "native review packet")
    _exact_fields(
        review,
        {
            "review_format_version",
            "review_id",
            "review_profile",
            "status",
            "contract",
            "candidate",
            "sections",
            "decisions",
            "coverage",
            "reviewer",
            "reviewed_at",
            "profile_effect",
            "notes",
        },
        "review",
    )
    if (
        _integer(review["review_format_version"], "review.review_format_version")
        != REVIEW_FORMAT_VERSION
    ):
        raise LayoutError("review.review_format_version must be 1")
    if review["review_id"] != EXPECTED_REVIEW_ID:
        raise LayoutError(f"review.review_id must be {EXPECTED_REVIEW_ID}")
    if review["review_profile"] != EXPECTED_REVIEW_PROFILE:
        raise LayoutError(f"review.review_profile must be {EXPECTED_REVIEW_PROFILE}")
    status = _string(review["status"], "review.status")
    if status not in REVIEW_STATES:
        raise LayoutError("review.status is unsupported")

    compiler_path = Path(layout_compiler.__file__).resolve()
    compiler_root = compiler_path.parents[1]
    validator_path = Path(__file__).resolve()
    schema_path = compiler_root / REVIEW_SCHEMA_PATH
    contract = _object(review["contract"], "review.contract")
    _exact_fields(contract, {"schema", "validator"}, "review.contract")
    validated_contract = {
        "schema": _validate_input_reference(
            contract["schema"],
            expected_path=REVIEW_SCHEMA_PATH.as_posix(),
            actual_path=schema_path,
            location="review.contract.schema",
        ),
        "validator": _validate_input_reference(
            contract["validator"],
            expected_path=VALIDATOR_PATH.as_posix(),
            actual_path=validator_path,
            location="review.contract.validator",
        ),
    }

    candidate_report, compiled = _compile_candidate(root)
    candidate = _object(review["candidate"], "review.candidate")
    _exact_fields(
        candidate,
        {
            "path",
            "layout_id",
            "revision",
            "input_script",
            "source_sha256",
            "compiler",
            "source_schema",
            "compiled_sha256",
        },
        "review.candidate",
    )
    if candidate["path"] != EXPECTED_CANDIDATE_PATH.as_posix():
        raise LayoutError("review.candidate.path is not the pinned research candidate")
    if candidate["layout_id"] != candidate_report["layout_id"]:
        raise LayoutError("review.candidate.layout_id mismatch")
    if (
        _integer(candidate["revision"], "review.candidate.revision")
        != compiled["revision"]
    ):
        raise LayoutError("review.candidate.revision mismatch")
    if candidate["input_script"] != candidate_report["input_script"]:
        raise LayoutError("review.candidate.input_script mismatch")
    if (
        _sha256(candidate["source_sha256"], "review.candidate.source_sha256")
        != candidate_report["source"]["sha256"]
    ):
        raise LayoutError("review.candidate source SHA-256 mismatch")
    if candidate["compiler"] != candidate_report["compiler"]:
        raise LayoutError("review.candidate compiler reference mismatch")
    if candidate["source_schema"] != candidate_report["source_schema"]:
        raise LayoutError("review.candidate source-schema reference mismatch")
    compiled_sha256 = candidate["compiled_sha256"]
    if compiled_sha256 is not None:
        compiled_sha256 = _sha256(
            compiled_sha256,
            "review.candidate.compiled_sha256",
        )
        if compiled_sha256 != candidate_report["compiled_sha256"]:
            raise LayoutError("review.candidate compiled SHA-256 mismatch")

    key_index, by_text = _text_key_index(compiled)
    _validate_candidate_safety(key_index)
    sections, pending_sections = _validate_sections(review["sections"], compiled)
    decisions, pending_decisions = _validate_decisions(
        review["decisions"],
        key_index,
    )
    coverage, pending_coverage, missing_count = _validate_coverage(
        review["coverage"],
        by_text,
    )
    reviewer, reviewed_at = _validate_reviewer(
        review["reviewer"],
        review["reviewed_at"],
    )

    profile_effect = _object(review["profile_effect"], "review.profile_effect")
    expected_profile_effect = {
        "profile_id": "new-Newa-NP",
        "selectable": False,
        "default_enabled": False,
        "bind_layout": False,
    }
    _exact_fields(
        profile_effect,
        set(expected_profile_effect),
        "review.profile_effect",
    )
    if profile_effect["profile_id"] != expected_profile_effect["profile_id"] or any(
        profile_effect[field] is not False
        for field in ("selectable", "default_enabled", "bind_layout")
    ):
        raise LayoutError(
            "review.profile_effect must remain the closed no-promotion state"
        )
    notes = _array(review["notes"], "review.notes")
    validated_notes = [
        _string(note, f"review.notes[{index}]") for index, note in enumerate(notes)
    ]
    if not validated_notes or len(validated_notes) != len(set(validated_notes)):
        raise LayoutError("review.notes must contain unique non-empty notes")

    unresolved = pending_sections + pending_decisions + pending_coverage
    states = [row["state"] for row in sections + decisions] + [
        row["review_state"] for row in coverage
    ]
    if status == "pending":
        if reviewer is not None or reviewed_at is not None:
            raise LayoutError("pending review must not claim a completed reviewer")
        if any(state != "pending" for state in states):
            raise LayoutError("pending review requires every item to remain pending")
        if len(unresolved) != len(states):
            raise LayoutError("pending review must contain only unresolved items")
    else:
        if compiled_sha256 is None:
            raise LayoutError("completed review must bind compiled_sha256")
        if reviewer is None or reviewed_at is None:
            raise LayoutError("completed review requires reviewer identity and date")
        if unresolved:
            raise LayoutError("completed review cannot contain unresolved items")
        _validate_completed_decision_consistency(decisions)
        if status == "accepted" and any(state != "accepted" for state in states):
            raise LayoutError("accepted review requires every item to be accepted")
        if status == "accepted" and missing_count:
            raise LayoutError(
                "accepted review cannot retain missing critical Newa scalars"
            )
        if status == "accepted":
            _validate_accepted_candidate_decisions(decisions, key_index)
        if status == "rejected" and "rejected" not in states:
            raise LayoutError("rejected review requires at least one rejected item")

    return {
        "native_review_validation_version": NATIVE_REVIEW_VALIDATION_VERSION,
        "review_id": EXPECTED_REVIEW_ID,
        "review_profile": EXPECTED_REVIEW_PROFILE,
        "status": status,
        "review": {
            "path": (REVIEW_DIRECTORY / resolved_review.name).as_posix(),
            "sha256": hashlib.sha256(review_bytes).hexdigest(),
        },
        "contract": validated_contract,
        "candidate": candidate_report,
        "section_count": len(sections),
        "decision_count": len(decisions),
        "coverage_item_count": len(coverage),
        "missing_critical_scalar_count": missing_count,
        "unresolved_count": len(unresolved),
        "profile_effect": expected_profile_effect,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sys.stdout.buffer.write(_canonical_bytes(validate_review(args.review)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LayoutError as error:
        raise SystemExit(f"error: {error}") from error
