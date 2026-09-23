#!/usr/bin/env python3
"""Validate one non-selectable research layout without changing layout locks."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

if __package__:
    from tools import build_keyboard_layouts as layout_compiler
else:
    import build_keyboard_layouts as layout_compiler  # type: ignore[import-not-found]


LayoutError = layout_compiler.LayoutError
_canonical_bytes = layout_compiler._canonical_bytes
_compile_layout = layout_compiler._compile_layout
_read_object = layout_compiler._read_object


CANDIDATE_VALIDATION_VERSION = 1
RESEARCH_SOURCE_DIRECTORY = Path("layouts/research")


def _require_regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise LayoutError(f"{label} must be a direct regular file: {path}")


def validate_candidate(
    candidate_path: Path,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Compile a research candidate in memory and return deterministic evidence."""

    root = (repository_root or Path(__file__).resolve().parents[1]).resolve()
    research_directory = root / RESEARCH_SOURCE_DIRECTORY
    if research_directory.is_symlink() or not research_directory.is_dir():
        raise LayoutError(
            f"research layout directory must be a direct directory: {research_directory}"
        )

    supplied_path = candidate_path
    if not supplied_path.is_absolute():
        supplied_path = Path.cwd() / supplied_path
    _require_regular_file(supplied_path, "research layout candidate")
    resolved_path = supplied_path.resolve()
    if resolved_path.parent != research_directory or resolved_path.suffix != ".json":
        raise LayoutError(
            "research layout candidate must be one direct .json child of "
            f"{research_directory}"
        )

    compiler_path = Path(layout_compiler.__file__).resolve()
    compiler_root = compiler_path.parents[1]
    source_schema_path = compiler_root / "schemas" / "layout-v1.schema.json"
    _require_regular_file(compiler_path, "layout compiler")
    _require_regular_file(source_schema_path, "layout source schema")

    source, source_bytes = _read_object(resolved_path, "research layout candidate")
    display_path = RESEARCH_SOURCE_DIRECTORY / resolved_path.name
    compiled = _compile_layout(
        source,
        display_path,
        source_bytes,
        root / "layouts" / "internal" / "notices",
        Path("layouts/internal/notices"),
        "internal",
    )
    return {
        "candidate_validation_version": CANDIDATE_VALIDATION_VERSION,
        "status": "research",
        "selectable": False,
        "default_enabled": False,
        "layout_id": compiled["layout_id"],
        "input_script": compiled["input_script"],
        "source": compiled["source"],
        "compiled_sha256": hashlib.sha256(_canonical_bytes(compiled)).hexdigest(),
        "compiler": {
            "path": "tools/build_keyboard_layouts.py",
            "sha256": hashlib.sha256(compiler_path.read_bytes()).hexdigest(),
        },
        "source_schema": {
            "path": "schemas/layout-v1.schema.json",
            "sha256": hashlib.sha256(source_schema_path.read_bytes()).hexdigest(),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sys.stdout.buffer.write(_canonical_bytes(validate_candidate(args.candidate)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LayoutError as error:
        raise SystemExit(f"error: {error}") from error
