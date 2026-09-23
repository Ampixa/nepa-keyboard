from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

from tools.build_windows_pime import (
    OUTPUT,
    PROFILES,
    VERSION,
    build_zip,
    is_payload_file,
    prepare_tree,
)


ROOT = Path(__file__).resolve().parents[1]


class WindowsPimePackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = prepare_tree(OUTPUT / "PIME")
        cls.archive = OUTPUT / f"Nepa-Phonetic-PIME-{VERSION}.zip"
        build_zip(OUTPUT / "PIME", cls.archive)

    def test_contains_three_independent_system_input_services(self) -> None:
        self.assertEqual(3, len(self.manifest["profiles"]))
        for profile in PROFILES:
            directory = OUTPUT / "PIME/python/input_methods" / profile["directory"]
            ime = json.loads((directory / "ime.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["guid"], ime["guid"])
            self.assertEqual("NepaTextService", ime["serviceName"])
            self.assertTrue((directory / profile["asset_name"]).is_file())

    def test_manifest_binds_every_payload_file(self) -> None:
        tree = OUTPUT / "PIME"
        actual = {}
        for path in sorted(tree.rglob("*")):
            if is_payload_file(path) and path.name != "manifest.json":
                actual[path.relative_to(tree).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        self.assertEqual(self.manifest["files"], actual)

    def test_archive_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory) / "other.zip"
            build_zip(OUTPUT / "PIME", other)
            self.assertEqual(self.archive.read_bytes(), other.read_bytes())
        with zipfile.ZipFile(self.archive) as archive:
            self.assertIn("PIME/manifest.json", archive.namelist())

    def test_pime_adapter_composes_toggles_and_commits(self) -> None:
        keycodes = types.ModuleType("keycodes")
        values = {
            "VK_BACK": 8,
            "VK_TAB": 9,
            "VK_RETURN": 13,
            "VK_CONTROL": 17,
            "VK_MENU": 18,
            "VK_ESCAPE": 27,
            "VK_SPACE": 32,
            "VK_LEFT": 37,
            "VK_UP": 38,
            "VK_RIGHT": 39,
            "VK_DOWN": 40,
        }
        for name, value in values.items():
            setattr(keycodes, name, value)

        class FakeTextService:
            def __init__(self, client):
                self.client = client
                self.compositionString = ""
                self.commitString = ""
                self.candidateList = []
                self.candidateCursor = 0
                self.showCandidates = False

            def onActivate(self): pass
            def onDeactivate(self): pass
            def onCompositionTerminated(self, forced): pass
            def addButton(self, *args, **kwargs): pass
            def removeButton(self, *args, **kwargs): pass
            def changeButton(self, *args, **kwargs): pass
            def customizeUI(self, **kwargs): pass
            def setSelKeys(self, keys): self.selectionKeys = keys
            def setCompositionString(self, value): self.compositionString = value
            def setCompositionCursor(self, value): self.compositionCursor = value
            def setCommitString(self, value): self.commitString = value
            def setCandidateList(self, value): self.candidateList = value
            def setCandidateCursor(self, value): self.candidateCursor = value
            def setShowCandidates(self, value): self.showCandidates = value
            def showMessage(self, *args, **kwargs): pass

        text_service = types.ModuleType("textService")
        text_service.TextService = FakeTextService

        class Event:
            def __init__(self, character: str = "", key_code: int | None = None, down=()):
                self.charCode = ord(character) if character else 0
                self.keyCode = key_code if key_code is not None else self.charCode
                self._down = set(down)

            def isKeyDown(self, key_code): return key_code in self._down
            def isPrintableChar(self): return 0x20 < self.charCode < 0x7F

        plugin = OUTPUT / "PIME/python/input_methods/nepa_nepali_phonetic"
        module_name = "nepa_test_pime_adapter"
        original_modules = {
            name: sys.modules.get(name) for name in ("keycodes", "textService")
        }
        with tempfile.TemporaryDirectory() as settings:
            previous_config = os.environ.get("XDG_CONFIG_HOME")
            try:
                os.environ["XDG_CONFIG_HOME"] = settings
                sys.modules["keycodes"] = keycodes
                sys.modules["textService"] = text_service
                spec = importlib.util.spec_from_file_location(module_name, plugin / "ime_nepa.py")
                self.assertIsNotNone(spec)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                assert spec is not None and spec.loader is not None
                spec.loader.exec_module(module)
                service = module.NepaTextService(None)
                service.onActivate()
                for character in "namaste":
                    event = Event(character)
                    self.assertTrue(service.filterKeyDown(event))
                    self.assertTrue(service.onKeyDown(event))
                self.assertEqual("नमस्ते", service.compositionString)
                self.assertEqual(["नमस्ते", "namaste"], service.candidateList)
                self.assertTrue(service.showCandidates)

                toggle = Event("c", down=(values["VK_CONTROL"], values["VK_MENU"]))
                service.onKeyDown(toggle)
                self.assertEqual("नमस्ते", service.compositionString)
                self.assertFalse(service.showCandidates)
                service.onKeyDown(toggle)
                self.assertTrue(service.showCandidates)

                service.onKeyDown(Event(key_code=values["VK_DOWN"]))
                service.onKeyDown(Event(key_code=values["VK_RETURN"]))
                self.assertEqual("namaste", service.commitString)
                self.assertEqual("", service.compositionString)
            finally:
                if previous_config is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = previous_config
                sys.modules.pop(module_name, None)
                for name, module in original_modules.items():
                    if module is None:
                        sys.modules.pop(name, None)
                    else:
                        sys.modules[name] = module


if __name__ == "__main__":
    unittest.main()
