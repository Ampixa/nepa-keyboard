#!/usr/bin/env python3
"""Pin Android Gradle tasks to canonical locks and generated assets by scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


GRADLE_PATH = Path("android/ime-app/build.gradle.kts")
LOCK_PATHS = {
    "release_profile": Path("catalog/shipping-profiles.lock.json"),
    "internal_profile": Path("catalog/internal-profiles.lock.json"),
    "release_layout": Path("layouts/layouts-v1.lock.json"),
    "internal_layout": Path("layouts/internal/layouts-v1.lock.json"),
}
ASSET_PATHS = {
    "transliteration_catalog": Path(
        "android/ime-app/src/main/assets/nepa-translit/profiles-v1.json"
    ),
}
PIN_PATHS = {**LOCK_PATHS, **ASSET_PATHS}
PIN_SCOPES = {
    "all": frozenset(PIN_PATHS),
    "internal": frozenset({
        "internal_profile", "internal_layout", "transliteration_catalog"
    }),
}


@dataclass(frozen=True)
class PinSite:
    task_name: str
    property_name: str
    input_name: str


PIN_SITES = (
    PinSite("generateShippingProfileCatalog", "expectedLockSha256", "release_profile"),
    PinSite("generateInternalProfileCatalog", "expectedLockSha256", "internal_profile"),
    PinSite(
        "generateTransliterationProfiles",
        "expectedCatalogSha256",
        "transliteration_catalog",
    ),
    PinSite(
        "generateTransliterationProfiles",
        "expectedProfileLockSha256",
        "internal_profile",
    ),
    PinSite(
        "generateEmptyTransliterationProfiles",
        "expectedCatalogSha256",
        "transliteration_catalog",
    ),
    PinSite(
        "generateEmptyTransliterationProfiles",
        "expectedProfileLockSha256",
        "internal_profile",
    ),
    PinSite("generateLayoutRegistry", "expectedLayoutLockSha256", "release_layout"),
    PinSite("generateLayoutRegistry", "expectedProfileLockSha256", "release_profile"),
    PinSite(
        "generateInternalLayoutRegistry",
        "expectedLayoutLockSha256",
        "internal_layout",
    ),
    PinSite(
        "generateInternalLayoutRegistry",
        "expectedProfileLockSha256",
        "internal_profile",
    ),
    PinSite("stageReleaseExternalPacks", "expectedProfileLockSha256", "release_profile"),
    PinSite("stageDebugExternalPacks", "expectedProfileLockSha256", "release_profile"),
    PinSite("stageInternalExternalPacks", "expectedProfileLockSha256", "internal_profile"),
)

PIN_PROPERTY_NAMES = {
    "expectedLockSha256",
    "expectedLayoutLockSha256",
    "expectedProfileLockSha256",
    "expectedCatalogSha256",
}

TASK_TYPES = {
    "generateShippingProfileCatalog": "GenerateShippingProfileCatalog",
    "generateInternalProfileCatalog": "GenerateShippingProfileCatalog",
    "generateTransliterationProfiles": "GenerateTransliterationProfiles",
    "generateEmptyTransliterationProfiles": "GenerateTransliterationProfiles",
    "generateLayoutRegistry": "GenerateLayoutRegistry",
    "generateInternalLayoutRegistry": "GenerateLayoutRegistry",
    "stageReleaseExternalPacks": "StageExternalReleasePacks",
    "stageDebugExternalPacks": "StageExternalReleasePacks",
    "stageInternalExternalPacks": "StageExternalInternalPacks",
}


class LockPinError(ValueError):
    """Raised when canonical locks or the closed Gradle pin contract are invalid."""


def _read_regular_file(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise LockPinError(f"{label} is missing, symbolic, or not a regular file: {path}")
    return path.read_bytes()


def _pin_hashes(
    repository_root: Path,
    input_names: frozenset[str],
) -> dict[str, str]:
    return {
        name: hashlib.sha256(
            _read_regular_file(repository_root / relative_path, f"{name} pin input")
        ).hexdigest()
        for name, relative_path in PIN_PATHS.items()
        if name in input_names
    }


def _matching_brace(text: str, opening: int, task_name: str) -> int:
    if opening >= len(text) or text[opening] != "{":
        raise LockPinError(f"malformed Gradle task block: {task_name}")
    depth = 0
    index = opening
    state = "code"
    block_comment_depth = 0
    while index < len(text):
        current = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if text.startswith('"""', index):
                state = "triple_string"
                index += 3
                continue
            if current == '"':
                state = "string"
            elif current == "'":
                state = "character"
            elif current == "/" and following == "/":
                state = "line_comment"
                index += 2
                continue
            elif current == "/" and following == "*":
                state = "block_comment"
                block_comment_depth = 1
                index += 2
                continue
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    return index
                if depth < 0:
                    break
        elif state in {"string", "character"}:
            if current == "\\":
                index += 2
                continue
            delimiter = '"' if state == "string" else "'"
            if current == delimiter:
                state = "code"
        elif state == "triple_string":
            if text.startswith('"""', index):
                state = "code"
                index += 3
                continue
        elif state == "line_comment":
            if current == "\n":
                state = "code"
        elif state == "block_comment":
            if current == "/" and following == "*":
                block_comment_depth += 1
                index += 2
                continue
            if current == "*" and following == "/":
                block_comment_depth -= 1
                index += 2
                if block_comment_depth == 0:
                    state = "code"
                continue
        index += 1
    raise LockPinError(f"unterminated or malformed Gradle task block: {task_name}")


def _task_block(text: str, task_name: str) -> tuple[int, int]:
    escaped = re.escape(task_name)
    task_type = re.escape(TASK_TYPES[task_name])
    header = re.compile(
        rf'^val {escaped} = tasks\.register<{task_type}>\(\n'
        rf'    "{escaped}"\n'
        rf'\) \{{$',
        re.MULTILINE,
    )
    matches = list(header.finditer(text))
    declarations = list(
        re.finditer(rf"^val\s+{escaped}\b", text, flags=re.MULTILINE)
    )
    if len(declarations) > 1 or len(matches) > 1:
        raise LockPinError(f"duplicate Gradle task block: {task_name}")
    if not matches:
        if declarations:
            raise LockPinError(f"malformed Gradle task block: {task_name}")
        raise LockPinError(f"missing Gradle task block: {task_name}")
    if len(declarations) != 1:
        raise LockPinError(f"malformed Gradle task block: {task_name}")
    match = matches[0]
    opening = match.end() - 1
    closing = _matching_brace(text, opening, task_name)
    if (
        (closing > 0 and text[closing - 1] != "\n")
        or (closing + 1 < len(text) and text[closing + 1] != "\n")
    ):
        raise LockPinError(f"malformed Gradle task block: {task_name}")
    return match.start(), closing + 1


def _pin_digest_span(
    text: str,
    block_start: int,
    block_end: int,
    site: PinSite,
) -> tuple[int, int]:
    block = text[block_start:block_end]
    property_name = re.escape(site.property_name)
    calls = list(re.finditer(rf"\b{property_name}\s*\.set\s*\(", block))
    if len(calls) != 1:
        raise LockPinError(
            f"Gradle task {site.task_name} must contain exactly one "
            f"{site.property_name}.set call"
        )
    strict = re.compile(
        rf'^    {property_name}\.set\(\n'
        rf'        "(?P<digest>[0-9a-f]{{64}})"\n'
        rf'    \)$',
        re.MULTILINE,
    )
    matches = list(strict.finditer(block))
    if len(matches) != 1:
        raise LockPinError(
            f"malformed Gradle pin in task {site.task_name}: {site.property_name}"
        )
    digest = matches[0].span("digest")
    return block_start + digest[0], block_start + digest[1]


def _updated_gradle(
    text: str,
    hashes: dict[str, str],
    pin_sites: tuple[PinSite, ...],
    *,
    enforce_global_contract: bool,
) -> str:
    task_blocks = {
        task_name: _task_block(text, task_name)
        for task_name in dict.fromkeys(site.task_name for site in pin_sites)
    }
    replacements: list[tuple[int, int, str]] = []
    pin_call_starts: set[int] = set()
    for site in pin_sites:
        block_start, block_end = task_blocks[site.task_name]
        start, end = _pin_digest_span(
            text,
            block_start,
            block_end,
            site,
        )
        if start in pin_call_starts:
            raise LockPinError(
                f"duplicate Gradle pin contract for {site.task_name}.{site.property_name}"
            )
        pin_call_starts.add(start)
        replacements.append((start, end, hashes[site.input_name]))

    property_alternation = "|".join(sorted(map(re.escape, PIN_PROPERTY_NAMES)))
    if enforce_global_contract:
        global_calls = list(
            re.finditer(rf"\b(?:{property_alternation})\s*\.set\s*\(", text)
        )
        if len(global_calls) != len(PIN_SITES):
            raise LockPinError(
                f"Gradle file must contain exactly {len(PIN_SITES)} recognized pin set calls"
            )
    else:
        for task_name, (block_start, block_end) in task_blocks.items():
            expected_count = sum(site.task_name == task_name for site in pin_sites)
            block = text[block_start:block_end]
            actual_count = len(list(re.finditer(
                rf"\b(?:{property_alternation})\s*\.set\s*\(",
                block,
            )))
            if actual_count != expected_count:
                raise LockPinError(
                    f"Gradle task {task_name} must contain exactly "
                    f"{expected_count} recognized internal pin calls"
                )

    updated = text
    for start, end, digest in sorted(replacements, reverse=True):
        updated = updated[:start] + digest + updated[end:]
    return updated


def _write_atomic(path: Path, encoded: bytes) -> None:
    original_mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    try:
        os.fchmod(descriptor, original_mode)
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


def update_android_lock_pins(
    repository_root: Path,
    *,
    check: bool = False,
    scope: str = "internal",
) -> dict[str, object]:
    if scope not in PIN_SCOPES:
        raise LockPinError(f"unsupported lock-pin scope: {scope}")
    repository_root = repository_root.resolve()
    input_names = PIN_SCOPES[scope]
    hashes = _pin_hashes(repository_root, input_names)
    pin_sites = tuple(site for site in PIN_SITES if site.input_name in input_names)
    gradle_path = repository_root / GRADLE_PATH
    encoded = _read_regular_file(gradle_path, "Android Gradle file")
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise LockPinError(f"Android Gradle file must not contain a UTF-8 BOM: {gradle_path}")
    try:
        text = encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LockPinError(f"Android Gradle file must be UTF-8: {gradle_path}") from exc
    updated = _updated_gradle(
        text,
        hashes,
        pin_sites,
        enforce_global_contract=scope == "all",
    )
    updated_bytes = updated.encode("utf-8")
    changed = updated_bytes != encoded
    if changed and not check:
        _write_atomic(gradle_path, updated_bytes)
    status = "stale" if check and changed else "updated" if changed else "current"
    return {
        "changed": changed,
        "hashes": hashes,
        "scope": scope,
        "status": status,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--scope",
        choices=tuple(PIN_SCOPES),
        default="internal",
        help="pin the internal lane (default) or all locks and assets",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = update_android_lock_pins(
            args.repository_root,
            check=args.check,
            scope=args.scope,
        )
    except (LockPinError, OSError) as exc:
        print(
            json.dumps(
                {"error": str(exc), "status": "error"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 1 if args.check and result["changed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
