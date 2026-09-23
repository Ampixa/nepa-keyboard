#!/usr/bin/env python3
"""Exercise installed Nepa Keyman keyboards through the live Linux IBus engine."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile
from dataclasses import asdict, dataclass
from typing import Any

import gi

gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402


KEYBOARD_IDS = (
    "nepa_nepali_romanized",
    "nepa_newa_romanized",
    "nepa_limbu_romanized",
)


@dataclass(frozen=True)
class Case:
    keyboard_id: str
    label: str
    keyval: int
    keycode: int
    state: int
    expected: str


@dataclass(frozen=True)
class Result:
    keyboard_id: str
    label: str
    expected: str
    actual: str
    handled: bool
    passed: bool


def cases() -> list[Case]:
    shift = int(IBus.ModifierType.SHIFT_MASK)
    caps = int(IBus.ModifierType.LOCK_MASK)
    right_alt = int(IBus.ModifierType.MOD5_MASK)
    return [
        Case("nepa_nepali_romanized", "normal-k", ord("k"), 37, 0, "क"),
        Case("nepa_nepali_romanized", "shift-k", ord("K"), 37, shift, "ख"),
        Case("nepa_nepali_romanized", "caps-k", ord("K"), 37, caps, "क्ष"),
        Case(
            "nepa_nepali_romanized",
            "shift-caps-k",
            ord("k"),
            37,
            shift | caps,
            "ख",
        ),
        Case("nepa_newa_romanized", "normal-k", ord("k"), 37, 0, "𑐎"),
        Case("nepa_newa_romanized", "shift-k", ord("K"), 37, shift, "𑐏"),
        Case(
            "nepa_newa_romanized",
            "right-alt-comma",
            ord(","),
            51,
            right_alt,
            "𑐓",
        ),
        Case("nepa_limbu_romanized", "normal-k", ord("k"), 37, 0, "ᤁ"),
        Case("nepa_limbu_romanized", "shift-k", ord("K"), 37, shift, "ᤂ"),
        Case(
            "nepa_limbu_romanized",
            "right-alt-k",
            ord("k"),
            37,
            right_alt,
            "ᤰ",
        ),
        Case(
            "nepa_limbu_romanized",
            "right-alt-comma-gyan",
            ord(","),
            51,
            right_alt,
            "ᤝ",
        ),
        Case(
            "nepa_limbu_romanized",
            "right-alt-backslash-tra",
            ord("\\"),
            43,
            right_alt,
            "ᤞ",
        ),
    ]


def drain_main_context(timeout_seconds: float = 0.25) -> None:
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        dispatched = False
        while context.pending():
            context.iteration(False)
            dispatched = True
        if not dispatched:
            time.sleep(0.005)


def discover_engine_names(bus: IBus.Bus) -> dict[str, str]:
    discovered: dict[str, str] = {}
    for engine in bus.list_engines():
        name = engine.get_name()
        for keyboard_id in KEYBOARD_IDS:
            if name.endswith(f"/{keyboard_id}.kmx"):
                discovered[keyboard_id] = name
    missing = sorted(set(KEYBOARD_IDS) - set(discovered))
    if missing:
        raise RuntimeError(f"installed IBus engines are missing: {missing}")
    return discovered


def wait_for_engine(context: IBus.InputContext, expected_name: str) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        active = context.get_engine()
        if active is not None and active.get_name() == expected_name:
            drain_main_context()
            return
        drain_main_context(0.05)
    active = context.get_engine()
    actual_name = active.get_name() if active is not None else None
    raise RuntimeError(
        f"IBus did not activate {expected_name!r}; active engine is {actual_name!r}"
    )


def run_cases() -> tuple[list[Result], dict[str, str]]:
    IBus.init()
    bus = IBus.Bus()
    if not bus.is_connected():
        raise RuntimeError("unable to connect to the IBus session bus")
    engine_names = discover_engine_names(bus)
    context = bus.create_input_context("nepa-keyman-linux-acceptance")
    commits: list[str] = []

    def on_commit_text(_context: IBus.InputContext, text: IBus.Text) -> None:
        commits.append(text.get_text())

    context.connect("commit-text", on_commit_text)
    context.set_capabilities(IBus.Capabilite.FOCUS)
    context.focus_in()
    results: list[Result] = []
    active_keyboard: str | None = None
    for case in cases():
        if active_keyboard != case.keyboard_id:
            context.set_engine(engine_names[case.keyboard_id])
            wait_for_engine(context, engine_names[case.keyboard_id])
            active_keyboard = case.keyboard_id
        commits.clear()
        handled = bool(context.process_key_event(case.keyval, case.keycode, case.state))
        drain_main_context()
        actual = "".join(commits)
        results.append(
            Result(
                keyboard_id=case.keyboard_id,
                label=case.label,
                expected=case.expected,
                actual=actual,
                handled=handled,
                passed=handled and actual == case.expected,
            )
        )
    context.focus_out()
    return results, engine_names


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="write machine-readable results")
    parser.add_argument(
        "--package",
        type=Path,
        help="bind results to this .kmp and verify its .kmx files are installed",
    )
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def package_binding(package: Path, engines: dict[str, str]) -> dict[str, Any]:
    package_bytes = package.read_bytes()
    installed_matches: dict[str, bool] = {}
    installed_sha256: dict[str, str] = {}
    packaged_sha256: dict[str, str] = {}
    with zipfile.ZipFile(package) as archive:
        for keyboard_id, engine_name in engines.items():
            entry = f"{keyboard_id}.kmx"
            packaged = archive.read(entry)
            installed_path = Path(engine_name.split(":", 1)[1])
            installed = installed_path.read_bytes()
            packaged_sha256[keyboard_id] = sha256_bytes(packaged)
            installed_sha256[keyboard_id] = sha256_bytes(installed)
            installed_matches[keyboard_id] = installed == packaged
    return {
        "path": str(package.resolve()),
        "sha256": sha256_bytes(package_bytes),
        "size": len(package_bytes),
        "packaged_kmx_sha256": packaged_sha256,
        "installed_kmx_sha256": installed_sha256,
        "installed_matches_package": installed_matches,
    }


def main() -> int:
    args = parse_args()
    try:
        results, engines = run_cases()
    except Exception as error:  # noqa: BLE001 - acceptance harness must report context.
        print(f"Linux IBus acceptance failed to start: {error}", file=sys.stderr)
        return 2
    payload: dict[str, Any] = {
        "format_version": 1,
        "platform": "linux-ibus-keyman",
        "engines": engines,
        "results": [asdict(result) for result in results],
        "passed": all(result.passed for result in results),
    }
    if args.package:
        try:
            payload["package"] = package_binding(args.package, engines)
        except Exception as error:  # noqa: BLE001 - report package binding failures.
            print(f"Unable to bind Linux acceptance to package: {error}", file=sys.stderr)
            return 2
        payload["passed"] = payload["passed"] and all(
            payload["package"]["installed_matches_package"].values()
        )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            print(
                f"{status} {result.keyboard_id} {result.label}: "
                f"expected={result.expected!r} actual={result.actual!r} "
                f"handled={result.handled}"
            )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
