#!/usr/bin/env python3
"""Live IBus acceptance for the caret-positioned Nepa phonetic engines."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass

import gi

gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402


ENGINE_VECTORS = {
    "nepa-phonetic-nepali": ("namaste", "नमस्ते"),
    "nepa-phonetic-newa": ("namaste", "𑐣𑐩𑐳𑑂𑐟𑐾"),
    "nepa-phonetic-limbu": ("kepa", "ᤁᤧᤐ"),
}


@dataclass(frozen=True)
class Result:
    engine: str
    roman: str
    preedit: str
    committed: str
    candidates: tuple[str, ...]
    candidate_visible: bool
    passed: bool


def drain(timeout: float = 0.12) -> None:
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dispatched = False
        while context.pending():
            context.iteration(False)
            dispatched = True
        if not dispatched:
            time.sleep(0.003)


def wait_for(condition, label: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        drain(0.03)
        if condition():
            return
    raise RuntimeError(f"timed out waiting for {label}")


def send(context: IBus.InputContext, character: str) -> bool:
    return bool(context.process_key_event(ord(character), 0, 0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--installed",
        action="store_true",
        help="discover engines from installed component metadata",
    )
    args = parser.parse_args()

    IBus.init()
    bus = IBus.Bus()
    if not bus.is_connected():
        raise RuntimeError("unable to connect to IBus")
    def registered_engine_names() -> set[str]:
        engines = bus.list_engines() if args.installed else bus.list_active_engines()
        return {engine.get_name() for engine in engines}

    wait_for(
        lambda: set(ENGINE_VECTORS).issubset(registered_engine_names()),
        "registered Nepa engines",
    )

    context = bus.create_input_context("nepa-phonetic-live-acceptance")
    commits: list[str] = []
    preedits: list[tuple[str, bool]] = []
    lookups: list[tuple[tuple[str, ...], bool]] = []

    context.connect(
        "commit-text", lambda _context, text: commits.append(text.get_text())
    )
    context.connect(
        "update-preedit-text",
        lambda _context, text, _cursor, visible: preedits.append(
            (text.get_text(), bool(visible))
        ),
    )

    def on_lookup(_context, table, visible) -> None:
        values = tuple(
            table.get_candidate(index).get_text()
            for index in range(table.get_number_of_candidates())
        )
        lookups.append((values, bool(visible)))

    context.connect("update-lookup-table", on_lookup)
    context.set_capabilities(
        IBus.Capabilite.FOCUS | IBus.Capabilite.PREEDIT_TEXT | IBus.Capabilite.LOOKUP_TABLE
    )
    context.focus_in()

    results: list[Result] = []
    for engine_name, (roman, expected) in ENGINE_VECTORS.items():
        context.set_engine(engine_name)
        wait_for(
            lambda: context.get_engine() is not None
            and context.get_engine().get_name() == engine_name,
            f"activation of {engine_name}",
        )
        commits.clear()
        preedits.clear()
        lookups.clear()
        handled = all(send(context, character) for character in roman)
        wait_for(
            lambda: bool(preedits) and preedits[-1][0] == expected,
            f"preedit {expected}",
        )
        wait_for(
            lambda: bool(lookups) and expected in lookups[-1][0] and lookups[-1][1],
            f"visible candidate {expected}",
        )
        context.process_key_event(IBus.KEY_space, 0, 0)
        wait_for(lambda: "".join(commits) == expected + " ", "committed candidate")
        candidates, visible = lookups[-2] if len(lookups) >= 2 else lookups[-1]
        results.append(
            Result(
                engine=engine_name,
                roman=roman,
                preedit=expected,
                committed="".join(commits),
                candidates=candidates,
                candidate_visible=visible,
                passed=handled
                and candidates[:2] == (expected, roman)
                and "".join(commits) == expected + " ",
            )
        )

    # The shortcut changes visibility without destroying the active composition.
    context.set_engine("nepa-phonetic-nepali")
    wait_for(
        lambda: context.get_engine() is not None
        and context.get_engine().get_name() == "nepa-phonetic-nepali",
        "Nepali reactivation",
    )
    preedits.clear()
    lookups.clear()
    for character in "nepaal":
        send(context, character)
    wait_for(lambda: bool(lookups) and lookups[-1][1], "initial candidate visibility")
    toggle_state = int(IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK)
    context.process_key_event(ord("c"), 0, toggle_state)
    wait_for(lambda: bool(lookups) and not lookups[-1][1], "disabled candidate window")
    disabled_preedit_preserved = bool(preedits) and preedits[-1][0] == "नेपाल"
    context.process_key_event(ord("c"), 0, toggle_state)
    wait_for(lambda: bool(lookups) and lookups[-1][1], "re-enabled candidate window")
    reenabled = bool(lookups) and lookups[-1][1]
    context.process_key_event(IBus.KEY_Escape, 0, 0)
    wait_for(lambda: commits and commits[-1] == "nepaal", "literal Escape commit")

    payload = {
        "format_version": 1,
        "platform": "linux-ibus-nepa-phonetic",
        "results": [asdict(result) for result in results],
        "candidate_toggle": {
            "disabled_without_losing_preedit": disabled_preedit_preserved,
            "reenabled": reenabled,
            "literal_escape_commit": bool(commits) and commits[-1] == "nepaal",
        },
    }
    payload["passed"] = all(result.passed for result in results) and all(
        payload["candidate_toggle"].values()
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for result in results:
            print(("PASS" if result.passed else "FAIL"), result)
        print("PASS" if payload["passed"] else "FAIL", "candidate toggle")
    context.focus_out()
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
