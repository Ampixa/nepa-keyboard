from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nepa_keyboard.desktop_composer import (
    CandidateWindowSettings,
    DesktopComposer,
)
from nepa_keyboard.transliteration import (
    TransliterationEngine,
    TransliterationMapError,
)


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "android/ime-app/src/main/assets/nepa-translit"
SOURCES = ROOT / "catalog/transliteration"
PROFILE_ASSETS = {
    "npi-Latn-Deva-v0": "npi-Latn-Deva-v1.json",
    "new-Latn-Newa-v0": "new-Latn-Newa-v1.json",
    "lif-Latn-Limb-v0": "lif-Latn-Limb-v1.json",
}


class TransliterationEngineTest(unittest.TestCase):
    def test_replays_every_reviewed_vector_for_the_three_desktop_profiles(self) -> None:
        for map_id, asset_name in PROFILE_ASSETS.items():
            engine = TransliterationEngine.from_path(ASSETS / asset_name)
            source = json.loads((SOURCES / f"{map_id}.json").read_text(encoding="utf-8"))
            self.assertTrue(source["vectors"], map_id)
            for vector in source["vectors"]:
                with self.subTest(map=map_id, roman=vector["input"]):
                    self.assertEqual(vector["output"], engine.transliterate(vector["input"]))

    def test_unknown_input_is_never_lost(self) -> None:
        engine = TransliterationEngine.from_path(ASSETS / "npi-Latn-Deva-v1.json")
        self.assertEqual("@क", engine.transliterate("@ka"))

    def test_rejects_an_unknown_algorithm(self) -> None:
        asset = json.loads((ASSETS / "npi-Latn-Deva-v1.json").read_text(encoding="utf-8"))
        asset["algorithm"] = "invented"
        with self.assertRaisesRegex(TransliterationMapError, "algorithm"):
            TransliterationEngine(asset)


class DesktopComposerTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = TransliterationEngine.from_path(ASSETS / "npi-Latn-Deva-v1.json")
        self.composer = DesktopComposer(engine)

    def test_google_style_composition_and_literal_fallback(self) -> None:
        for character in "namaste":
            snapshot = self.composer.append(character)
        self.assertEqual("namaste", snapshot.roman)
        self.assertEqual("नमस्ते", snapshot.preedit)
        self.assertEqual(("नमस्ते", "namaste"), snapshot.candidates)
        self.assertEqual("नमस्ते", self.composer.commit())
        self.assertEqual("", self.composer.snapshot().roman)

    def test_candidate_window_can_be_toggled_without_losing_composition(self) -> None:
        self.composer.append("nepaal")
        disabled = self.composer.toggle_candidate_window()
        self.assertFalse(disabled.candidate_window_visible)
        self.assertEqual("नेपाल", disabled.preedit)
        enabled = self.composer.toggle_candidate_window()
        self.assertTrue(enabled.candidate_window_visible)
        self.assertEqual("नेपाल", enabled.preedit)

    def test_user_can_select_and_commit_literal_roman_text(self) -> None:
        self.composer.append("namaste")
        self.composer.select(1)
        self.assertEqual("namaste", self.composer.commit())

    def test_escape_style_literal_commit_and_backspace(self) -> None:
        self.composer.append("nepaal")
        self.assertEqual("नेपा", self.composer.backspace().preedit)
        # Backspace operates on the exact Roman buffer and then rerenders it.
        self.assertEqual("nepaa", self.composer.snapshot().roman)
        self.assertEqual("nepaa", self.composer.commit_literal())

    def test_settings_are_per_profile_and_persist_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = CandidateWindowSettings(path)
            self.assertTrue(settings.candidate_window_enabled("npi"))
            settings.set_candidate_window_enabled("npi", False)
            self.assertFalse(CandidateWindowSettings(path).candidate_window_enabled("npi"))
            self.assertTrue(CandidateWindowSettings(path).candidate_window_enabled("new"))


if __name__ == "__main__":
    unittest.main()
