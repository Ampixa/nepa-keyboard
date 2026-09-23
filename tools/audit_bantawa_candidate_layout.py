#!/usr/bin/env python3
"""Prove that generated Bantawa candidate scalars are typeable by one v1 layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


FORMAT_VERSION = 1
AUDITOR_NAME = "audit_bantawa_candidate_layout"
AUDITOR_VERSION = 1
EXPECTED_LAYERS = ("base", "shift", "symbols", "numeric")


class AuditError(ValueError):
    """Raised when candidate or layout inputs violate the audit contract."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AuditError(f"{label} is not a regular non-symbolic file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AuditError(f"cannot read {label} {path}: {exc}") from exc


def _decode_json(encoded: bytes, label: str) -> object:
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise AuditError(f"{label} must not contain a UTF-8 BOM")
    try:
        return json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                AuditError(f"{label} contains non-finite number {token!r}")
            ),
        )
    except UnicodeError as exc:
        raise AuditError(f"{label} is not UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AuditError(f"{label} is invalid JSON: {exc.msg}") from exc


def _read_forms(path: Path) -> tuple[bytes, list[str]]:
    encoded = _read_regular(path, "forms.jsonl")
    if b"\r" in encoded or not encoded.endswith(b"\n"):
        raise AuditError("forms.jsonl must use LF and end with LF")
    try:
        lines = encoded.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise AuditError(f"forms.jsonl is not UTF-8: {exc}") from exc
    surfaces: list[str] = []
    for line_number, line in enumerate(lines, 1):
        if not line:
            raise AuditError(f"forms.jsonl line {line_number} is blank")
        row = _decode_json(line.encode("utf-8"), f"forms.jsonl line {line_number}")
        if not isinstance(row, dict):
            raise AuditError(f"forms.jsonl line {line_number} must be an object")
        surface = row.get("surface")
        if not isinstance(surface, str) or not surface:
            raise AuditError(f"forms.jsonl line {line_number} has no surface")
        if unicodedata.normalize("NFC", surface) != surface:
            raise AuditError(f"forms.jsonl line {line_number} surface is not NFC")
        surfaces.append(surface)
    if not surfaces:
        raise AuditError("forms.jsonl must contain at least one surface")
    return encoded, surfaces


def _layout_text_scalars(layout: dict[str, Any]) -> tuple[set[str], list[dict[str, str]]]:
    layers = layout.get("layers")
    if not isinstance(layers, dict) or set(layers) != set(EXPECTED_LAYERS):
        raise AuditError("selected layout does not have the canonical four layers")
    scalars: set[str] = set()
    key_texts: list[dict[str, str]] = []
    for layer_name in EXPECTED_LAYERS:
        layer = layers[layer_name]
        if not isinstance(layer, dict) or not isinstance(layer.get("rows"), list):
            raise AuditError(f"selected layout layer {layer_name} has invalid rows")
        for row in layer["rows"]:
            if not isinstance(row, list):
                raise AuditError(f"selected layout layer {layer_name} has a non-array row")
            for key in row:
                if not isinstance(key, dict):
                    raise AuditError(f"selected layout layer {layer_name} has a non-object key")
                text = key.get("text")
                if text is None:
                    continue
                if not isinstance(text, str) or not text:
                    raise AuditError(f"selected layout layer {layer_name} has invalid key text")
                key_id = key.get("key_id")
                if not isinstance(key_id, str) or not key_id:
                    raise AuditError(f"selected layout layer {layer_name} key has no key_id")
                scalars.update(text)
                key_texts.append({"key_id": key_id, "layer": layer_name, "text": text})
    key_texts.sort(key=lambda item: (item["layer"], item["key_id"], item["text"]))
    return scalars, key_texts


def build_report(forms_path: Path, layout_lock_path: Path, layout_id: str) -> dict[str, object]:
    forms_bytes, surfaces = _read_forms(forms_path)
    lock_bytes = _read_regular(layout_lock_path, "layout lock")
    lock = _decode_json(lock_bytes, "layout lock")
    if not isinstance(lock, dict) or not isinstance(lock.get("layouts"), list):
        raise AuditError("layout lock must contain a layouts array")
    matches = [
        item
        for item in lock["layouts"]
        if isinstance(item, dict) and item.get("layout_id") == layout_id
    ]
    if len(matches) != 1:
        raise AuditError(f"layout lock must contain exactly one {layout_id!r} layout")
    layout = matches[0]
    if layout.get("input_script") != "Deva":
        raise AuditError("selected Bantawa layout must have Deva input_script")
    source = layout.get("source")
    if not isinstance(source, dict):
        raise AuditError("selected layout has no source identity")
    source_path = source.get("path")
    source_sha256 = source.get("sha256")
    if not isinstance(source_path, str) or not isinstance(source_sha256, str):
        raise AuditError("selected layout source identity is incomplete")

    layout_scalars, key_texts = _layout_text_scalars(layout)
    frequencies: Counter[str] = Counter(character for surface in surfaces for character in surface)
    required_scalars = sorted(frequencies, key=ord)
    unsupported = [character for character in required_scalars if character not in layout_scalars]
    scalar_rows = [
        {
            "category": unicodedata.category(character),
            "character": character,
            "code_point": f"U+{ord(character):04X}",
            "count": frequencies[character],
            "name": unicodedata.name(character, "<unnamed>"),
            "typeable": character in layout_scalars,
        }
        for character in required_scalars
    ]
    return {
        "auditor": {
            "name": AUDITOR_NAME,
            "path": "tools/audit_bantawa_candidate_layout.py",
            "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "version": AUDITOR_VERSION,
        },
        "claim_scope": (
            "Generated candidate scalar reachability through one compiled layout; "
            "not native spelling, ergonomic, ranking, or production approval"
        ),
        "format_version": FORMAT_VERSION,
        "forms": {
            "distinct_surfaces": len(set(surfaces)),
            "rows": len(surfaces),
            "sha256": hashlib.sha256(forms_bytes).hexdigest(),
        },
        "layout": {
            "input_script": "Deva",
            "key_text_count": len(key_texts),
            "layout_id": layout_id,
            "layout_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
            "source_path": source_path,
            "source_sha256": source_sha256,
        },
        "required_scalars": scalar_rows,
        "status": "passed" if not unsupported else "failed",
        "unsupported_scalars": [
            {
                "character": character,
                "code_point": f"U+{ord(character):04X}",
            }
            for character in unsupported
        ],
    }


def _write_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forms-jsonl", type=Path, required=True)
    parser.add_argument("--layout-lock", type=Path, required=True)
    parser.add_argument("--layout-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_report(args.forms_jsonl, args.layout_lock, args.layout_id)
        encoded = _canonical_bytes(report)
        if args.check:
            existing = _read_regular(args.output, "existing audit report")
            if existing != encoded:
                raise AuditError("existing audit report does not match regenerated bytes")
        else:
            if args.output.exists():
                raise AuditError(f"refusing to replace existing output: {args.output}")
            _write_atomic(args.output, encoded)
        if report["status"] != "passed":
            raise AuditError("selected layout does not cover every candidate scalar")
    except AuditError as exc:
        parser.error(str(exc))
    print(
        _canonical_bytes(
            {
                "output": str(args.output),
                "report_sha256": hashlib.sha256(encoded).hexdigest(),
                "status": report["status"],
            }
        ).decode("utf-8"),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
