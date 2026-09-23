from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.build_keyboard_layouts import LayoutError, _canonical_bytes
from tools.validate_keyboard_layout_candidate import (
    RESEARCH_SOURCE_DIRECTORY,
    build_parser,
    validate_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_NAME = "newa-nepal-qwerty-direct-v1.json"
NEPAL_BHASA_CANDIDATE_NAME = "deva-nepal-bhasa-v1.json"
CANDIDATE_NAMES = [CANDIDATE_NAME]


class KeyboardLayoutCandidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "layouts" / "research").mkdir(parents=True)
        (self.root / "layouts" / "internal" / "notices").mkdir(parents=True)
        shutil.copy2(
            ROOT / "layouts" / "research" / CANDIDATE_NAME,
            self.root / "layouts" / "research" / CANDIDATE_NAME,
        )
        self.candidate = self.root / "layouts" / "research" / CANDIDATE_NAME

    def tearDown(self) -> None:
        self.temp.cleanup()

    def read_candidate(self) -> dict[str, object]:
        return json.loads(self.candidate.read_text(encoding="utf-8"))

    def write_candidate(self, value: dict[str, object]) -> None:
        self.candidate.write_bytes(_canonical_bytes(value))

    def test_checked_candidate_compiles_to_deterministic_research_evidence(
        self,
    ) -> None:
        first = validate_candidate(self.candidate, repository_root=self.root)
        second = validate_candidate(self.candidate, repository_root=self.root)
        self.assertEqual(_canonical_bytes(first), _canonical_bytes(second))
        self.assertEqual(first["candidate_validation_version"], 1)
        self.assertEqual(first["status"], "research")
        self.assertFalse(first["selectable"])
        self.assertFalse(first["default_enabled"])
        self.assertEqual(first["layout_id"], "newa-nepal-qwerty-direct-v1")
        self.assertEqual(first["input_script"], "Newa")
        self.assertEqual(
            first["source"],
            {
                "path": f"{RESEARCH_SOURCE_DIRECTORY}/{CANDIDATE_NAME}",
                "sha256": hashlib.sha256(self.candidate.read_bytes()).hexdigest(),
            },
        )
        self.assertEqual(len(first["compiled_sha256"]), 64)

    def test_compiler_evidence_is_bound_to_the_imported_implementation(self) -> None:
        spoofed_compiler = self.root / "tools" / "build_keyboard_layouts.py"
        spoofed_compiler.parent.mkdir()
        spoofed_compiler.write_text("not the imported compiler\n", encoding="utf-8")

        report = validate_candidate(self.candidate, repository_root=self.root)
        imported_compiler = ROOT / "tools" / "build_keyboard_layouts.py"
        self.assertEqual(
            report["compiler"],
            {
                "path": "tools/build_keyboard_layouts.py",
                "sha256": hashlib.sha256(imported_compiler.read_bytes()).hexdigest(),
            },
        )
        self.assertNotEqual(
            report["compiler"]["sha256"],
            hashlib.sha256(spoofed_compiler.read_bytes()).hexdigest(),
        )

    def test_every_checked_research_candidate_validates(self) -> None:
        candidates = sorted((ROOT / RESEARCH_SOURCE_DIRECTORY).iterdir())
        self.assertEqual([path.name for path in candidates], CANDIDATE_NAMES)
        for candidate in candidates:
            with self.subTest(candidate=candidate.name):
                self.assertTrue(candidate.is_file())
                self.assertFalse(candidate.is_symlink())
                self.assertEqual(candidate.suffix, ".json")
                report = validate_candidate(candidate, repository_root=ROOT)
                self.assertEqual(report["status"], "research")
                self.assertFalse(report["selectable"])

    def test_nepal_bhasa_internal_layout_covers_the_accepted_pack_repertoire(self) -> None:
        layout = ROOT / "layouts" / "internal" / "src" / NEPAL_BHASA_CANDIDATE_NAME
        source = json.loads(layout.read_text(encoding="utf-8"))
        spec = json.loads(
            (ROOT / "catalog" / "nepal-bhasa-candidate-pack-v0.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(source["layout_id"], "deva-nepal-bhasa-v1")
        self.assertEqual(source["input_script"], "Deva")
        self.assertEqual(
            source["layers"]["base"]["rows"][3][:4],
            ["इ", "ई", "ए", "ऱ"],
        )
        self.assertEqual(
            [
                (row["kind"], row["text"])
                for row in source["layers"]["base"]["rows"][3][4:]
            ],
            [
                ("text", "ः"),
                ("text", "़"),
                ("deva_conjunct_joiner", "\u200d"),
                ("deva_conjunct_joiner", "\u200c"),
            ],
        )
        self.assertEqual(
            [
                (row["kind"], row["text"])
                for row in source["layers"]["shift"]["rows"][3][4:]
            ],
            [
                ("text", "ॅ"),
                ("text", "ॉ"),
                ("text", "॑"),
                ("text", "॒"),
            ],
        )
        self.assertEqual(
            source["layers"]["symbols"]["rows"][3],
            ["०", "१", "२", "३", "४", "५", "६", "७", "८", "९"],
        )

        emitted: set[int] = set()
        for layer in source["layers"].values():
            for row in layer["rows"]:
                for key in row:
                    if isinstance(key, str):
                        emitted.update(map(ord, key))
                    elif isinstance(key, dict) and isinstance(key.get("text"), str):
                        emitted.update(map(ord, key["text"]))
        required = {
            int(label.removeprefix("U+"), 16)
            for label in spec["expected"]["required_scalars"]
        }
        self.assertEqual(required - emitted, set())

    def test_nepal_bhasa_internal_layout_is_bound_and_preserves_basic_rows(self) -> None:
        layout = ROOT / "layouts" / "internal" / "src" / NEPAL_BHASA_CANDIDATE_NAME
        source = json.loads(layout.read_text(encoding="utf-8"))
        basic = json.loads(
            (ROOT / "layouts" / "internal" / "src" / "deva-nepal-basic-v1.json").read_text(
                encoding="utf-8"
            )
        )
        for layer_id in ("base", "shift"):
            self.assertEqual(
                source["layers"][layer_id]["rows"][:3],
                basic["layers"][layer_id]["rows"][:3],
            )
            self.assertEqual(
                source["layers"][layer_id]["rows"][-1],
                basic["layers"][layer_id]["rows"][-1],
            )
        self.assertEqual(
            source["layers"]["numeric"],
            basic["layers"]["numeric"],
        )

        layout_lock = json.loads(
            (ROOT / "layouts" / "internal" / "layouts-v1.lock.json").read_text(
                encoding="utf-8"
            )
        )
        compiled = next(
            row
            for row in layout_lock["layouts"]
            if row["layout_id"] == "deva-nepal-bhasa-v1"
        )
        self.assertEqual(compiled["source"]["sha256"], hashlib.sha256(layout.read_bytes()).hexdigest())
        self.assertIn(
            "new-Deva-NP",
            {row["profile_id"] for row in layout_lock["profile_bindings"]},
        )
        profile_lock = json.loads(
            (ROOT / "catalog" / "internal-profiles.lock.json").read_text(
                encoding="utf-8"
            )
        )
        profile = next(
            row for row in profile_lock["profiles"] if row["profile_id"] == "new-Deva-NP"
        )
        self.assertEqual(profile["layout_id"], "deva-nepal-bhasa-v1")
        self.assertTrue(profile["selectable"])
        self.assertFalse(profile["default_enabled"])
        self.assertEqual(profile["pack_binding"], "new-Deva-NP")
        self.assertEqual(
            profile["pack_artifact"]["artifact_sha256"],
            "c90c7eba644334ef95ae7dfc168d70382083f06ab7fc45a81f33a90052952570",
        )
        self.assertEqual(profile["pack_artifact"]["alias_key_count"], 1828)

    def test_qwerty_rows_and_reference_pins_are_explicit(self) -> None:
        source = json.loads(
            (ROOT / RESEARCH_SOURCE_DIRECTORY / CANDIDATE_NAME).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            source["layers"]["base"]["rows"][:2],
            [
                ["𑐚", "𑑁", "𑐾", "𑐬", "𑐟", "𑐫", "𑐸", "𑐶", "𑑀", "𑐥"],
                ["𑐵", "𑐳", "𑐡", "𑐦", "𑐐", "𑐴", "𑐖", "𑐎", "𑐮"],
            ],
        )
        base_row_three = source["layers"]["base"]["rows"][2]
        self.assertEqual(
            base_row_three[:9],
            ["𑐲", "𑐕", "𑐔", "𑐰", "𑐧", "𑐣", "𑐩", "𑑋", "𑑂"],
        )
        self.assertEqual(
            [(key["kind"], key["text"]) for key in base_row_three[9:]],
            [
                ("newa_conjunct_joiner", "\u200d"),
                ("newa_conjunct_joiner", "\u200c"),
            ],
        )
        self.assertEqual(
            source["layers"]["shift"]["rows"][:3],
            [
                ["𑐛", "𑐍", "𑐿", "𑐺", "𑐠", "𑐘", "𑐹", "𑐷", "𑐌", "𑐦"],
                ["𑐁", "𑐱", "𑐢", "𑐄", "𑐑", "𑐀", "𑐗", "𑐏", "𑐯"],
                ["𑐆", "𑐝", "𑐕", "𑑃", "𑐨", "𑐞", "𑑄", "𑑌", "𑐒"],
            ],
        )
        self.assertEqual(
            source["layers"]["symbols"]["rows"][0],
            ["𑑑", "𑑒", "𑑓", "𑑔", "𑑕", "𑑖", "𑑗", "𑑘", "𑑙", "𑑐"],
        )

        pins = {
            row["source"]: (row["revision"], row["sha256"])
            for row in source["provenance"]
        }
        self.assertEqual(
            pins,
            {
                "newa_romanized.yaml": (
                    "futo-keyboard-layouts-da68b2ad377b6bb4ef2d2fe61333b8459838e73b",
                    "d1d9e56cb132566a8895bbe04a12b12534ec5fa6f605cd63389c6627973aa8f6",
                ),
                "newa_romanized.keyman-touch-layout": (
                    "keyman-keyboards-f5059868da69d0d677cad897ae922f03d857a943",
                    "8936cf14bfde3848759c6906d21ab132aa0ace924986254692eccf2338e8bcad",
                ),
                "newa_romanized.kmn": (
                    "keyman-keyboards-f5059868da69d0d677cad897ae922f03d857a943",
                    "cdb9b65ddb6fc8bbe1d85e23cfe0e05ffb9f64ae98d3496f1a0d9bf889b648ef",
                ),
                "UnicodeData.txt": (
                    "Unicode-16.0.0",
                    "ff58e5823bd095166564a006e47d111130813dcf8bf234ef79fa51a870edb48f",
                ),
            },
        )

        serialized = json.dumps(source, ensure_ascii=False)
        self.assertNotIn("\U0001145c", serialized)
        self.assertNotIn("\ufffd", serialized)
        self.assertFalse(
            any(0xE000 <= ord(character) <= 0xF8FF for character in serialized)
        )

    def test_research_candidate_is_separate_from_internal_beta_layout(
        self,
    ) -> None:
        research_layout_id = "newa-nepal-qwerty-direct-v1"
        internal_layout_id = "newa-nepal-prachalit-v1"
        source_directory = ROOT / "layouts" / "internal" / "src"
        self.assertFalse((source_directory / CANDIDATE_NAME).exists())
        self.assertTrue((source_directory / f"{internal_layout_id}.json").is_file())

        lock_path = ROOT / "layouts" / "internal" / "layouts-v1.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertNotIn(
            research_layout_id,
            {row["layout_id"] for row in lock["layouts"]},
        )
        self.assertIn(
            internal_layout_id,
            {row["layout_id"] for row in lock["layouts"]},
        )
        self.assertTrue(
            any(
                row["profile_id"] == "new-Newa-NP"
                and row["source_script"] == "Newa"
                and row["layout_id"] == internal_layout_id
                for row in lock["profile_bindings"]
            )
        )

    def test_newa_profile_is_bound_as_internal_beta(self) -> None:
        lock_path = ROOT / "catalog" / "internal-profiles.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        profile = next(
            row for row in lock["profiles"] if row["profile_id"] == "new-Newa-NP"
        )
        expected = {
            "catalog_readiness": "beta",
            "selectable": True,
            "default_enabled": False,
            "layout_id": "newa-nepal-prachalit-v1",
            "layout_revision": 1,
            "layout_source_sha256": "dca07de46cc09f53c430c6b57702c3e56137316ead7ebb0f209e535e62020448",
            "pack_binding": "new-Newa-NP",
            "blocked_reason": None,
        }
        self.assertEqual(
            {key: profile[key] for key in expected},
            expected,
        )
        self.assertEqual(profile["pack_artifact"]["output_script"], "Newa")
        self.assertEqual(profile["pack_artifact"]["candidate_count"], 2318)
        self.assertEqual(len(profile["evidence_ids"]), 1)
        self.assertEqual(len(profile["evidence_artifacts"]), 1)

    def test_validator_has_no_lock_write_or_promotion_options(self) -> None:
        actions = {
            option
            for action in build_parser()._actions
            for option in action.option_strings
        }
        self.assertEqual(actions, {"-h", "--help", "--candidate"})

    def test_rejects_outside_nested_symlink_and_non_json_candidates(self) -> None:
        outside = self.root / CANDIDATE_NAME
        shutil.copy2(self.candidate, outside)
        nested = self.candidate.parent / "nested"
        nested.mkdir()
        nested_candidate = nested / CANDIDATE_NAME
        shutil.copy2(self.candidate, nested_candidate)
        non_json = self.candidate.with_suffix(".txt")
        shutil.copy2(self.candidate, non_json)
        symlink = self.candidate.parent / "linked.json"
        symlink.symlink_to(self.candidate)

        for path, message in (
            (outside, "direct .json child"),
            (nested_candidate, "direct .json child"),
            (non_json, "direct .json child"),
            (symlink, "direct regular file"),
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(LayoutError, message):
                    validate_candidate(path, repository_root=self.root)

    def test_rejects_duplicate_keys_and_layout_id_path_mismatch(self) -> None:
        original = self.candidate.read_text(encoding="utf-8")
        self.candidate.write_text(
            original.replace(
                '"revision": 1,',
                '"revision": 1,\n  "revision": 1,',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(LayoutError, "duplicate JSON key"):
            validate_candidate(self.candidate, repository_root=self.root)

        self.candidate.write_text(original, encoding="utf-8")
        source = self.read_candidate()
        source["layout_id"] = "different-layout-v1"
        self.write_candidate(source)
        with self.assertRaisesRegex(LayoutError, "layout ID/path mismatch"):
            validate_candidate(self.candidate, repository_root=self.root)

    def test_rejects_generic_joiner_and_wrong_script_joiner(self) -> None:
        source = self.read_candidate()
        source["layers"]["base"]["rows"][0][0] = "\u200d"
        self.write_candidate(source)
        with self.assertRaisesRegex(LayoutError, r"unsupported format U\+200D"):
            validate_candidate(self.candidate, repository_root=self.root)

        source = self.read_candidate()
        source["layers"]["base"]["rows"][0][0] = source["layers"]["base"]["rows"][2][9]
        source["input_script"] = "Deva"
        self.write_candidate(source)
        with self.assertRaisesRegex(LayoutError, "requires input script Newa"):
            validate_candidate(self.candidate, repository_root=self.root)


if __name__ == "__main__":
    unittest.main()
