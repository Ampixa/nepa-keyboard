"""PIME/TSF adapter for one generated Nepa phonetic profile."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from keycodes import (  # type: ignore[import-not-found]
    VK_BACK,
    VK_CONTROL,
    VK_DOWN,
    VK_ESCAPE,
    VK_LEFT,
    VK_MENU,
    VK_RETURN,
    VK_RIGHT,
    VK_SPACE,
    VK_TAB,
    VK_UP,
)
from textService import TextService  # type: ignore[import-not-found]


PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from nepa_keyboard.desktop_composer import (  # noqa: E402
    CandidateWindowSettings,
    DesktopComposer,
)
from nepa_keyboard.transliteration import TransliterationEngine  # noqa: E402


TOGGLE_COMMAND = 101


class NepaTextService(TextService):
    """Windows TSF service hosted by PIME's signed frontend."""

    def __init__(self, client):
        super().__init__(client)
        profile = json.loads((PLUGIN_ROOT / "profile.json").read_text(encoding="utf-8"))
        self.profile_id = profile["profile_id"]
        self.profile_name = profile["display_name"]
        self.settings = CandidateWindowSettings()
        engine = TransliterationEngine.from_path(PLUGIN_ROOT / profile["asset_name"])
        self.composer = DesktopComposer(
            engine,
            candidate_window_enabled=self.settings.candidate_window_enabled(
                self.profile_id
            ),
        )

    def onActivate(self):
        super().onActivate()
        self.customizeUI(candFontSize=20, candPerRow=1, candUseCursor=True)
        self.setSelKeys("12")
        self.addButton(
            "nepa-candidate-window",
            text="Nepa",
            tooltip="Caret suggestions (Ctrl+Alt+C)",
            commandId=TOGGLE_COMMAND,
            type="toggle",
            toggled=self.composer.candidate_window_enabled,
        )
        self._publish()

    def onDeactivate(self):
        self._commit()
        self.removeButton("nepa-candidate-window")
        super().onDeactivate()

    def onCompositionTerminated(self, forced):
        self.composer.reset()
        super().onCompositionTerminated(forced)

    def filterKeyDown(self, keyEvent):
        control = keyEvent.isKeyDown(VK_CONTROL)
        alt = keyEvent.isKeyDown(VK_MENU)
        if control and alt and keyEvent.keyCode in (ord("C"), ord("c")):
            return True
        if control or alt:
            return False
        if self.composer.snapshot().roman:
            return True
        if keyEvent.keyCode in (VK_BACK, VK_RETURN, VK_ESCAPE, VK_SPACE, VK_TAB):
            return False
        return self._accepted_character(keyEvent) is not None

    def onKeyDown(self, keyEvent):
        control = keyEvent.isKeyDown(VK_CONTROL)
        alt = keyEvent.isKeyDown(VK_MENU)
        if control and alt and keyEvent.keyCode in (ord("C"), ord("c")):
            self._toggle_candidate_window()
            return True
        if control or alt:
            return False

        snapshot = self.composer.snapshot()
        if keyEvent.keyCode == VK_BACK:
            if not snapshot.roman:
                return False
            self.composer.backspace()
            self._publish()
            return True
        if keyEvent.keyCode == VK_ESCAPE:
            if not snapshot.roman:
                return False
            self._commit(literal=True)
            return True
        if keyEvent.keyCode in (VK_LEFT, VK_UP):
            if not snapshot.roman:
                return False
            self.composer.move_selection(-1)
            self._publish()
            return True
        if keyEvent.keyCode in (VK_RIGHT, VK_DOWN, VK_TAB):
            if not snapshot.roman:
                return False
            self.composer.move_selection(1)
            self._publish()
            return True
        if keyEvent.keyCode == VK_RETURN:
            if not snapshot.roman:
                return False
            self._commit()
            return True
        if keyEvent.keyCode == VK_SPACE:
            if not snapshot.roman:
                return False
            self._commit(suffix=" ")
            return True

        # Candidate selection keys win only while a list is visible.
        if (
            snapshot.candidate_window_visible
            and keyEvent.keyCode in (ord("1"), ord("2"))
        ):
            index = keyEvent.keyCode - ord("1")
            if index < len(snapshot.candidates):
                self.composer.select(index)
                self._commit()
                return True

        character = self._accepted_character(keyEvent)
        if character is not None:
            try:
                self.composer.append(character)
            except ValueError:
                self._commit()
                self.composer.append(character)
            self._publish()
            return True
        if snapshot.roman and keyEvent.isPrintableChar():
            self._commit(suffix=chr(keyEvent.charCode))
            return True
        return False

    def onCommand(self, commandId, commandType):
        if commandId == TOGGLE_COMMAND:
            self._toggle_candidate_window()

    def _accepted_character(self, keyEvent):
        if not keyEvent.isPrintableChar():
            return None
        character = chr(keyEvent.charCode)
        return character if character.isascii() and (
            character.isalnum() or character in "_.:"
        ) else None

    def _toggle_candidate_window(self):
        snapshot = self.composer.toggle_candidate_window()
        self.settings.set_candidate_window_enabled(
            self.profile_id, snapshot.candidate_window_enabled
        )
        self.changeButton(
            "nepa-candidate-window",
            toggled=snapshot.candidate_window_enabled,
            tooltip="Caret suggestions (Ctrl+Alt+C)",
        )
        state = "on" if snapshot.candidate_window_enabled else "off"
        self.showMessage(f"Caret suggestions {state}", duration=1)
        self._publish()

    def _commit(self, literal=False, suffix=""):
        value = (
            self.composer.commit_literal() if literal else self.composer.commit()
        )
        self.setCommitString(value + suffix)
        self.setCompositionString("")
        self.setShowCandidates(False)

    def _publish(self):
        snapshot = self.composer.snapshot()
        self.setCompositionString(snapshot.preedit)
        self.setCompositionCursor(len(snapshot.preedit))
        self.setCandidateList(list(snapshot.candidates))
        if snapshot.candidates:
            self.setCandidateCursor(snapshot.selected_index)
        self.setShowCandidates(snapshot.candidate_window_visible)

