#!/usr/bin/env python3
"""IBus frontend for the Nepa caret-positioned phonetic input method."""

from __future__ import annotations

import argparse
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402


REPOSITORY = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY / "src"
if SOURCE_ROOT.is_dir() and str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from nepa_keyboard.desktop_composer import (  # noqa: E402
    CandidateWindowSettings,
    DesktopComposer,
)
from nepa_keyboard.transliteration import TransliterationEngine  # noqa: E402


COMPONENT_NAME = "org.ampixa.NepaKeyboard.Phonetic"
ENGINE_PREFIX = "nepa-phonetic-"
TOGGLE_PROPERTY = "candidate-window"
VERSION = "0.2.0"


@dataclass(frozen=True)
class Profile:
    engine_name: str
    profile_id: str
    display_name: str
    language: str
    symbol: str
    asset_name: str


PROFILES = (
    Profile(
        f"{ENGINE_PREFIX}nepali",
        "npi-Latn-Deva-v0",
        "Nepali Phonetic — Nepa",
        "ne",
        "ने",
        "npi-Latn-Deva-v1.json",
    ),
    Profile(
        f"{ENGINE_PREFIX}newa",
        "new-Latn-Newa-v0",
        "Nepal Bhasa Phonetic (Newa) — Nepa",
        "new",
        "𑐣𑐾",
        "new-Latn-Newa-v1.json",
    ),
    Profile(
        f"{ENGINE_PREFIX}limbu",
        "lif-Latn-Limb-v0",
        "Limbu Phonetic (Sirijanga) — Nepa",
        "lif",
        "ᤕᤠ",
        "lif-Latn-Limb-v1.json",
    ),
)
PROFILE_BY_ENGINE = {profile.engine_name: profile for profile in PROFILES}


def asset_directory() -> Path:
    candidates = (
        REPOSITORY / "desktop/ime/generated/maps",
        REPOSITORY / "android/ime-app/src/main/assets/nepa-translit",
        Path("/usr/share/nepa-keyboard/transliteration"),
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise RuntimeError("Nepa transliteration assets are not installed")


class NepaEngine(IBus.Engine):
    """One IBus session; IBus positions its lookup table at the editor caret."""

    def __init__(
        self,
        bus: IBus.Bus,
        object_path: str,
        profile: Profile,
        settings: CandidateWindowSettings | None = None,
    ) -> None:
        super().__init__(connection=bus.get_connection(), object_path=object_path)
        self.profile = profile
        self.settings = settings or CandidateWindowSettings()
        engine = TransliterationEngine.from_path(asset_directory() / profile.asset_name)
        self.composer = DesktopComposer(
            engine,
            candidate_window_enabled=self.settings.candidate_window_enabled(
                profile.profile_id
            ),
        )
        self.private_field = False
        self.lookup_table = IBus.LookupTable.new(9, 0, True, False)
        self.lookup_table.set_orientation(IBus.Orientation.HORIZONTAL)
        self._publish()

    def do_enable(self) -> None:
        self._register_properties()
        self._publish()

    def do_disable(self) -> None:
        self._commit_current()
        self._hide_ui()

    def do_focus_in(self) -> None:
        self._register_properties()
        self._publish()

    def do_focus_out(self) -> None:
        self._commit_current()
        self._hide_ui()

    def do_reset(self) -> None:
        self.composer.reset()
        self._publish()

    def do_set_content_type(self, purpose: int, _hints: int) -> None:
        private_purposes = {
            int(IBus.InputPurpose.PASSWORD),
            int(IBus.InputPurpose.PIN),
        }
        private = int(purpose) in private_purposes
        if private != self.private_field:
            self._commit_current()
            self.private_field = private
            self._publish()

    def do_property_activate(self, prop_name: str, _state: int) -> None:
        if prop_name == TOGGLE_PROPERTY:
            self._toggle_candidate_window()

    def do_candidate_clicked(self, index: int, _button: int, _state: int) -> None:
        snapshot = self.composer.snapshot()
        if 0 <= index < len(snapshot.candidates):
            self.composer.select(index)
            self._commit_current()

    def do_page_up(self) -> bool:
        return False

    def do_page_down(self) -> bool:
        return False

    def do_cursor_up(self) -> bool:
        if not self.composer.snapshot().roman:
            return False
        self.composer.move_selection(-1)
        self._publish()
        return True

    def do_cursor_down(self) -> bool:
        if not self.composer.snapshot().roman:
            return False
        self.composer.move_selection(1)
        self._publish()
        return True

    def do_process_key_event(self, keyval: int, _keycode: int, state: int) -> bool:
        if state & int(IBus.ModifierType.RELEASE_MASK):
            return False

        control = bool(state & int(IBus.ModifierType.CONTROL_MASK))
        alt = bool(state & int(IBus.ModifierType.MOD1_MASK))
        key_name = IBus.keyval_name(keyval) or ""
        if control and alt and key_name.lower() == "c":
            self._toggle_candidate_window()
            return True

        # Application shortcuts and password/PIN fields must not be intercepted.
        if control or alt or self.private_field:
            return False

        snapshot = self.composer.snapshot()
        if keyval == IBus.KEY_BackSpace:
            if not snapshot.roman:
                return False
            self.composer.backspace()
            self._publish()
            return True
        if keyval == IBus.KEY_Escape:
            if not snapshot.roman:
                return False
            self._commit_literal()
            return True
        if keyval in (IBus.KEY_Up, IBus.KEY_Left):
            return self.do_cursor_up()
        if keyval in (IBus.KEY_Down, IBus.KEY_Right, IBus.KEY_Tab):
            return self.do_cursor_down()
        if keyval in (IBus.KEY_Return, IBus.KEY_KP_Enter):
            if not snapshot.roman:
                return False
            self._commit_current()
            return True
        if keyval == IBus.KEY_space:
            if not snapshot.roman:
                return False
            self._commit_current(" ")
            return True

        character = chr(keyval) if 0x20 <= keyval <= 0x7E else ""
        if character and (character.isalnum() or character in "_.:"):
            try:
                self.composer.append(character)
            except ValueError:
                self._commit_current()
                self.composer.append(character)
            self._publish()
            return True
        if character and snapshot.roman:
            self._commit_current(character)
            return True
        return False

    def _register_properties(self) -> None:
        enabled = self.composer.candidate_window_enabled
        prop = IBus.Property(
            key=TOGGLE_PROPERTY,
            prop_type=IBus.PropType.TOGGLE,
            label=IBus.Text.new_from_string("Caret suggestions"),
            icon="",
            tooltip=IBus.Text.new_from_string(
                "Show transliteration candidates beside the text cursor (Ctrl+Alt+C)"
            ),
            sensitive=True,
            visible=True,
            state=IBus.PropState.CHECKED if enabled else IBus.PropState.UNCHECKED,
        )
        props = IBus.PropList()
        props.append(prop)
        self.register_properties(props)

    def _toggle_candidate_window(self) -> None:
        snapshot = self.composer.toggle_candidate_window()
        self.settings.set_candidate_window_enabled(
            self.profile.profile_id, snapshot.candidate_window_enabled
        )
        self._register_properties()
        state = "on" if snapshot.candidate_window_enabled else "off"
        self.update_auxiliary_text(
            IBus.Text.new_from_string(f"Caret suggestions {state}"), True
        )
        GLib.timeout_add(1200, self._hide_auxiliary)
        self._publish()

    def _hide_auxiliary(self) -> bool:
        self.hide_auxiliary_text()
        return False

    def _commit_current(self, suffix: str = "") -> None:
        value = self.composer.commit()
        if value or suffix:
            self.commit_text(IBus.Text.new_from_string(value + suffix))
        self._publish()

    def _commit_literal(self) -> None:
        value = self.composer.commit_literal()
        if value:
            self.commit_text(IBus.Text.new_from_string(value))
        self._publish()

    def _hide_ui(self) -> None:
        self.update_preedit_text(IBus.Text.new_from_string(""), 0, False)
        self.lookup_table.clear()
        self.update_lookup_table(self.lookup_table, False)

    def _publish(self) -> None:
        snapshot = self.composer.snapshot()
        self.update_preedit_text(
            IBus.Text.new_from_string(snapshot.preedit),
            len(snapshot.preedit),
            bool(snapshot.preedit),
        )
        self.lookup_table.clear()
        for candidate in snapshot.candidates:
            self.lookup_table.append_candidate(IBus.Text.new_from_string(candidate))
        if snapshot.candidates:
            self.lookup_table.set_cursor_pos(snapshot.selected_index)
        self.update_lookup_table(
            self.lookup_table, snapshot.candidate_window_visible
        )


class NepaFactory(IBus.Factory):
    def __init__(self, bus: IBus.Bus) -> None:
        super().__init__(connection=bus.get_connection(), object_path=IBus.PATH_FACTORY)
        self.bus = bus
        self.serial = 0

    def do_create_engine(self, engine_name: str) -> NepaEngine:
        profile = PROFILE_BY_ENGINE.get(engine_name)
        if profile is None:
            raise ValueError(f"unknown Nepa engine {engine_name!r}")
        object_path = f"/org/ampixa/NepaKeyboard/engine/{self.serial}"
        self.serial += 1
        return NepaEngine(self.bus, object_path, profile)


def component() -> IBus.Component:
    value = IBus.Component(
        name=COMPONENT_NAME,
        description="Nepa offline phonetic input methods",
        version=VERSION,
        license="Internal",
        author="Ampixa",
        homepage="https://github.com/suvash/nepali-romanized-pro",
        textdomain="nepa-keyboard",
    )
    for profile in PROFILES:
        value.add_engine(
            IBus.EngineDesc(
                name=profile.engine_name,
                longname=profile.display_name,
                description="Offline Roman input with a caret-positioned candidate list",
                language=profile.language,
                license="Internal",
                author="Ampixa",
                icon="",
                layout="us",
                symbol=profile.symbol,
            )
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ibus",
        action="store_true",
        help="run after activation from an installed IBus component",
    )
    args = parser.parse_args()
    IBus.init()
    bus = IBus.Bus()
    if not bus.is_connected():
        print("Unable to connect to the IBus session bus", file=sys.stderr)
        return 2
    loop = GLib.MainLoop()
    _factory = NepaFactory(bus)
    if args.ibus:
        bus.request_name(COMPONENT_NAME, 0)
    else:
        bus.register_component(component())
    bus.connect("disconnected", lambda *_args: loop.quit())
    signal.signal(signal.SIGTERM, lambda *_args: loop.quit())
    signal.signal(signal.SIGINT, lambda *_args: loop.quit())
    loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
