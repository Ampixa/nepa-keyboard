"""Platform-neutral state machine for a caret-positioned desktop IME."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .transliteration import TransliterationEngine


TOGGLE_SHORTCUT = "Ctrl+Alt+C"
MAX_COMPOSITION_LENGTH = 128


@dataclass(frozen=True)
class CompositionSnapshot:
    """Complete UI state after one composition operation."""

    roman: str
    preedit: str
    candidates: tuple[str, ...]
    selected_index: int
    candidate_window_enabled: bool

    @property
    def candidate_window_visible(self) -> bool:
        return self.candidate_window_enabled and bool(self.roman and self.candidates)

    @property
    def selected_candidate(self) -> str:
        if not self.candidates:
            return ""
        return self.candidates[self.selected_index]


class DesktopComposer:
    """Own a Roman token, rendered preedit, selection, and candidate visibility."""

    def __init__(
        self,
        engine: TransliterationEngine,
        *,
        candidate_window_enabled: bool = True,
    ):
        self.engine = engine
        self.candidate_window_enabled = bool(candidate_window_enabled)
        self._roman = ""
        self._selected_index = 0

    def snapshot(self) -> CompositionSnapshot:
        if not self._roman:
            candidates: tuple[str, ...] = ()
            preedit = ""
        else:
            preedit = self.engine.transliterate(self._roman)
            # Literal Roman text is always recoverable. Avoid a duplicate when a
            # map deliberately passes an entirely unknown token through.
            candidates = (preedit,) if preedit == self._roman else (preedit, self._roman)
        selected = min(self._selected_index, max(0, len(candidates) - 1))
        return CompositionSnapshot(
            roman=self._roman,
            preedit=preedit,
            candidates=candidates,
            selected_index=selected,
            candidate_window_enabled=self.candidate_window_enabled,
        )

    def append(self, text: str) -> CompositionSnapshot:
        if not isinstance(text, str) or not text:
            raise ValueError("text must be a non-empty string")
        if len(self._roman) + len(text) > MAX_COMPOSITION_LENGTH:
            raise ValueError(
                f"composition cannot exceed {MAX_COMPOSITION_LENGTH} characters"
            )
        self._roman += text
        self._selected_index = 0
        return self.snapshot()

    def backspace(self) -> CompositionSnapshot:
        if self._roman:
            self._roman = self._roman[:-1]
            self._selected_index = 0
        return self.snapshot()

    def move_selection(self, delta: int) -> CompositionSnapshot:
        snapshot = self.snapshot()
        if snapshot.candidates:
            self._selected_index = (
                snapshot.selected_index + delta
            ) % len(snapshot.candidates)
        return self.snapshot()

    def select(self, index: int) -> CompositionSnapshot:
        snapshot = self.snapshot()
        if not 0 <= index < len(snapshot.candidates):
            raise IndexError("candidate index out of range")
        self._selected_index = index
        return self.snapshot()

    def commit(self) -> str:
        value = self.snapshot().selected_candidate
        self.reset()
        return value

    def commit_literal(self) -> str:
        value = self._roman
        self.reset()
        return value

    def reset(self) -> CompositionSnapshot:
        self._roman = ""
        self._selected_index = 0
        return self.snapshot()

    def set_candidate_window_enabled(self, enabled: bool) -> CompositionSnapshot:
        self.candidate_window_enabled = bool(enabled)
        return self.snapshot()

    def toggle_candidate_window(self) -> CompositionSnapshot:
        return self.set_candidate_window_enabled(not self.candidate_window_enabled)


class CandidateWindowSettings:
    """Small atomic JSON store shared by the Linux and Windows adapters."""

    VERSION = 1

    def __init__(self, path: Path | None = None):
        self.path = path or self.default_path()

    @staticmethod
    def default_path() -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "nepa-keyboard" / "desktop-ime.json"

    def load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": self.VERSION, "profiles": {}}
        except (OSError, json.JSONDecodeError):
            return {"version": self.VERSION, "profiles": {}}
        if (
            not isinstance(value, dict)
            or value.get("version") != self.VERSION
            or not isinstance(value.get("profiles"), dict)
        ):
            return {"version": self.VERSION, "profiles": {}}
        return value

    def candidate_window_enabled(self, profile_id: str) -> bool:
        profile = self.load()["profiles"].get(profile_id, {})
        if not isinstance(profile, dict):
            return True
        value = profile.get("candidate_window_enabled", True)
        return value if isinstance(value, bool) else True

    def set_candidate_window_enabled(self, profile_id: str, enabled: bool) -> None:
        value = self.load()
        profiles = value["profiles"]
        profile = profiles.setdefault(profile_id, {})
        if not isinstance(profile, dict):
            profile = {}
            profiles[profile_id] = profile
        profile["candidate_window_enabled"] = bool(enabled)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(value, output, ensure_ascii=False, sort_keys=True, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

