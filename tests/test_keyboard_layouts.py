from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.build_keyboard_layouts import (
    LayoutError,
    MAX_LAYOUTS,
    MAX_NOTICE_BYTES,
    _canonical_bytes,
    build_lock,
    main,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = ROOT / "layouts" / "src"
PROFILE_LOCK_PATH = ROOT / "catalog" / "shipping-profiles.lock.json"
GOLDEN_PATH = ROOT / "layouts" / "goldens" / "layout-v0-parity.json"


class KeyboardLayoutsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.layouts = self.root / "layouts"
        shutil.copytree(ROOT / "layouts", self.layouts)
        self.source = self.layouts / "src"
        self.profile_bytes = PROFILE_LOCK_PATH.read_bytes()
        self.profile_lock = json.loads(self.profile_bytes)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(
        self,
        profile_lock: dict[str, object] | None = None,
        *,
        source_directory: Path | None = None,
        source_path_prefix: str = "layouts/src",
        profile_lock_path: str = "catalog/shipping-profiles.lock.json",
    ) -> dict[str, object]:
        selected_profile_lock = copy.deepcopy(
            profile_lock if profile_lock is not None else self.profile_lock
        )
        return build_lock(
            source_directory or self.source,
            selected_profile_lock,
            profile_lock_path=profile_lock_path,
            profile_lock_sha256=hashlib.sha256(
                _canonical_bytes(selected_profile_lock)
            ).hexdigest(),
            source_path_prefix=source_path_prefix,
            compiler_reference={
                "path": "tools/build_keyboard_layouts.py",
                "sha256": hashlib.sha256(
                    (ROOT / "tools" / "build_keyboard_layouts.py").read_bytes()
                ).hexdigest(),
            },
            schema_references={
                name: {
                    "path": f"schemas/{file_name}",
                    "sha256": hashlib.sha256(
                        (ROOT / "schemas" / file_name).read_bytes()
                    ).hexdigest(),
                }
                for name, file_name in {
                    "source": "layout-v1.schema.json",
                    "lock": "layout-lock-v1.schema.json",
                }.items()
            },
        )

    def internal_profile_lock(
        self, *, include_limbu: bool = False
    ) -> dict[str, object]:
        profile_lock = copy.deepcopy(self.profile_lock)
        profile_lock["review"]["authority"] = "internal"
        internal_reasons = {
            "direct": "DIRECT_PROFILE_NOT_INTERNAL_READY",
            "roman_phonetic": "ROMAN_ALIAS_NOT_INTERNAL_READY",
            "script_conversion": "SCRIPT_CONVERTER_NOT_INTERNAL_READY",
        }
        for profile in profile_lock["profiles"]:
            if not profile["selectable"]:
                profile["blocked_reason"] = internal_reasons[profile["method_type"]]
        if not include_limbu:
            return profile_lock

        internal_sources = self.layouts / "internal" / "src"
        internal_layouts = {
            "eng-Latn-US": "latn-qwerty-us-v1",
            "npi-Deva-NP": "deva-nepal-basic-v1",
        }
        for profile_id, layout_id in internal_layouts.items():
            profile = next(
                row
                for row in profile_lock["profiles"]
                if row["profile_id"] == profile_id
            )
            profile["layout_source_sha256"] = hashlib.sha256(
                (internal_sources / f"{layout_id}.json").read_bytes()
            ).hexdigest()

        limbu = next(
            row
            for row in profile_lock["profiles"]
            if row["profile_id"] == "lif-Limb-NP"
        )
        limbu.update(
            {
                "layout_id": "limb-nepal-phonetic-v1",
                "layout_revision": 1,
                "layout_source_sha256": hashlib.sha256(
                    (internal_sources / "limb-nepal-phonetic-v1.json").read_bytes()
                ).hexdigest(),
                "pack_binding": "lif-Limb-NP",
                "pack_artifact": {
                    "pack_id": "lif-Limb-NP",
                    "file_name": "lif-Limb-NP.nkp",
                    "artifact_sha256": "1" * 64,
                    "language": "lif",
                    "output_script": "Limb",
                    "artifact_license": "LicenseRef-Internal",
                    "release_mode": "internal",
                    "candidate_count": 1,
                    "surface_key_count": 1,
                    "alias_key_count": 0,
                    "validation": {
                        "query": "ᤀ",
                        "expected_surface": "ᤀ",
                        "benchmark_queries": ["ᤀ"],
                    },
                },
                "selectable": True,
                "blocked_reason": None,
                "blocked_detail": None,
                "default_enabled": False,
                "evidence_ids": ["fixture-limbu-internal"],
                "evidence_artifacts": [
                    {"path": "fixture/limbu.json", "sha256": "2" * 64}
                ],
            }
        )
        profile_lock["counts"]["selectable"] = 3
        return profile_lock

    def source_path(self, layout_id: str) -> Path:
        return self.source / f"{layout_id}.json"

    def read_source(self, layout_id: str) -> dict[str, object]:
        return json.loads(self.source_path(layout_id).read_text(encoding="utf-8"))

    def write_source(self, layout_id: str, value: dict[str, object]) -> None:
        self.source_path(layout_id).write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def bind_source_hash(
        self,
        profile_lock: dict[str, object],
        profile_id: str,
        layout_id: str,
    ) -> None:
        profile = next(
            row for row in profile_lock["profiles"] if row["profile_id"] == profile_id
        )
        profile["layout_source_sha256"] = hashlib.sha256(
            self.source_path(layout_id).read_bytes()
        ).hexdigest()

    @staticmethod
    def profile_selection_and_pack_state(
        profile_lock: dict[str, object],
    ) -> dict[str, tuple[object, ...]]:
        return {
            profile["profile_id"]: (
                profile["selectable"],
                profile["default_enabled"],
                profile["pack_binding"],
                profile["pack_artifact"],
                profile["evidence_ids"],
                profile["evidence_artifacts"],
            )
            for profile in profile_lock["profiles"]
        }

    def newa_joiner_fixture(self) -> tuple[dict[str, object], str]:
        layout_id = "newa-conjunct-fixture-v1"
        source = self.read_source("deva-nepal-basic-v1")
        source["layout_id"] = layout_id
        source["display_name"] = "Newa conjunct fixture"
        source["input_script"] = "Newa"
        for layer_id in ("base", "shift"):
            next_newa_scalar = 0x11400
            for row in source["layers"][layer_id]["rows"][:-1]:
                for key_index, key in enumerate(row):
                    if isinstance(key, str) and any(
                        0x0900 <= ord(character) <= 0x097F for character in key
                    ):
                        row[key_index] = chr(next_newa_scalar)
                        next_newa_scalar += 1
        source["layers"]["base"]["rows"].insert(
            -1,
            [
                {
                    "kind": "newa_conjunct_joiner",
                    "text": "\u200d",
                    "label": "ZWJ",
                    "content_description": "Newa zero width joiner",
                },
                {
                    "kind": "newa_conjunct_joiner",
                    "text": "\u200c",
                    "label": "ZWNJ",
                    "content_description": "Newa zero width non-joiner",
                },
            ],
        )
        self.source_path("deva-nepal-basic-v1").unlink()
        self.write_source(layout_id, source)

        profile_lock = copy.deepcopy(self.profile_lock)
        profile = next(
            row
            for row in profile_lock["profiles"]
            if row["profile_id"] == "npi-Deva-NP"
        )
        profile["layout_id"] = layout_id
        profile["source_script"] = "Newa"
        self.bind_source_hash(profile_lock, "npi-Deva-NP", layout_id)
        return profile_lock, layout_id

    def test_exact_layout_and_selectable_binding_set(self) -> None:
        lock = self.build()
        self.assertEqual(lock["layout_count"], 2)
        layouts = {row["layout_id"]: row for row in lock["layouts"]}
        self.assertEqual(set(layouts), {"deva-nepal-basic-v1", "latn-qwerty-us-v1"})
        self.assertEqual(layouts["deva-nepal-basic-v1"]["input_script"], "Deva")
        self.assertEqual(layouts["latn-qwerty-us-v1"]["input_script"], "Latn")
        self.assertTrue(
            all(
                row["license"]["redistribution"] == "allowed"
                for row in layouts.values()
            )
        )
        self.assertEqual(
            lock["profile_bindings"],
            [
                {
                    "profile_id": "eng-Latn-US",
                    "layout_id": "latn-qwerty-us-v1",
                    "source_script": "Latn",
                    "revision": 1,
                    "source_sha256": "fc0ae5dfa73e3d034d1e48303c3d1b26fc493ac45e5d327a0f4f7b2cd1d02be3",
                },
                {
                    "profile_id": "npi-Deva-NP",
                    "layout_id": "deva-nepal-basic-v1",
                    "source_script": "Deva",
                    "revision": 1,
                    "source_sha256": "bca603b0a101f8c4be47fd6625c4e0bd0c7e7f1370f88c0e4028450b5ccbcade",
                },
            ],
        )

    def test_newa_research_candidate_is_absent_from_release_lane(self) -> None:
        candidate_name = "newa-nepal-qwerty-direct-v1.json"
        candidate_id = "newa-nepal-qwerty-direct-v1"
        self.assertTrue((ROOT / "layouts" / "research" / candidate_name).is_file())
        self.assertFalse((SOURCE_DIRECTORY / candidate_name).exists())

        lock = json.loads(
            (ROOT / "layouts" / "layouts-v1.lock.json").read_text(encoding="utf-8")
        )
        self.assertNotIn(
            candidate_id,
            {row["layout_id"] for row in lock["layouts"]},
        )
        self.assertFalse(
            any(row["source_script"] == "Newa" for row in lock["profile_bindings"])
        )

        profile = next(
            row
            for row in self.profile_lock["profiles"]
            if row["profile_id"] == "new-Newa-NP"
        )
        expected = {
            "catalog_readiness": "beta",
            "selectable": False,
            "default_enabled": False,
            "layout_id": "pending-new-newa-direct",
            "layout_revision": None,
            "layout_source_sha256": None,
            "pack_binding": None,
            "pack_artifact": None,
            "evidence_ids": [],
            "evidence_artifacts": [],
            "blocked_reason": "DIRECT_PROFILE_NOT_RELEASE_APPROVED",
        }
        self.assertEqual(
            {key: profile[key] for key in expected},
            expected,
        )

    def test_schemas_model_optional_source_and_nullable_compiled_license(self) -> None:
        source_schema = json.loads(
            (ROOT / "schemas" / "layout-v1.schema.json").read_text(encoding="utf-8")
        )
        lock_schema = json.loads(
            (ROOT / "schemas" / "layout-lock-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("license", source_schema["required"])
        for license_schema in (
            source_schema["$defs"]["license"],
            lock_schema["$defs"]["license"],
        ):
            self.assertEqual(
                set(license_schema["required"]),
                {"id", "copyright", "redistribution"},
            )
            self.assertEqual(
                license_schema["dependentRequired"],
                {
                    "notice_path": ["notice_sha256"],
                    "notice_sha256": ["notice_path"],
                },
            )
        self.assertEqual(
            lock_schema["$defs"]["layout"]["properties"]["license"]["oneOf"],
            [
                {"type": "null"},
                {"$ref": "#/$defs/license"},
            ],
        )
        self.assertEqual(lock_schema["properties"]["layout_count"]["maximum"], 128)
        self.assertEqual(lock_schema["properties"]["layouts"]["maxItems"], 128)
        self.assertEqual(
            lock_schema["properties"]["profile_bindings"]["maxItems"],
            128,
        )
        self.assertIn(
            "newa_conjunct_joiner",
            lock_schema["$defs"]["compiled_key"]["properties"]["kind"]["enum"],
        )

    def test_source_schema_closes_newa_joiner_payload_and_script(self) -> None:
        source_schema = json.loads(
            (ROOT / "schemas" / "layout-v1.schema.json").read_text(encoding="utf-8")
        )
        newa_joiner = next(
            variant
            for variant in source_schema["$defs"]["key"]["oneOf"]
            if variant.get("properties", {}).get("kind", {}).get("const")
            == "newa_conjunct_joiner"
        )
        self.assertEqual(
            newa_joiner["properties"]["text"]["enum"],
            [
                "\u200c",
                "\u200d",
            ],
        )
        script_condition = source_schema["allOf"][0]
        self.assertEqual(
            script_condition["if"]["properties"]["input_script"],
            {"not": {"const": "Newa"}},
        )
        for layer_id in ("base", "shift", "symbols", "numeric"):
            self.assertEqual(
                script_condition["then"]["properties"]["layers"]["properties"][
                    layer_id
                ],
                {"$ref": "#/$defs/layer_without_newa_joiners"},
            )

    def test_reviewed_third_profile_can_reuse_a_compiled_layout(self) -> None:
        profile_lock = copy.deepcopy(self.profile_lock)
        profile = next(
            row
            for row in profile_lock["profiles"]
            if row["profile_id"] == "dhi-Deva-NP"
        )
        profile_lock["counts"]["selectable"] = 3
        profile.update(
            {
                "layout_id": "deva-nepal-basic-v1",
                "layout_revision": 1,
                "layout_source_sha256": (
                    "bca603b0a101f8c4be47fd6625c4e0bd0c7e7f1370f88c0e4028450b5ccbcade"
                ),
                "pack_binding": "dhi-Deva-NP",
                "pack_artifact": {
                    "pack_id": "dhi-Deva-NP",
                    "release_mode": "release",
                },
                "selectable": True,
                "blocked_reason": None,
                "blocked_detail": None,
                "default_enabled": False,
                "evidence_ids": ["fixture-expansion-evidence"],
                "evidence_artifacts": [
                    {"path": "fixture/evidence.json", "sha256": "1" * 64}
                ],
            }
        )

        lock = self.build(profile_lock)
        self.assertEqual(
            {row["profile_id"] for row in lock["profile_bindings"]},
            {"dhi-Deva-NP", "eng-Latn-US", "npi-Deva-NP"},
        )
        self.assertEqual(lock["layout_count"], 2)

    def test_v2_conversion_profile_can_reuse_a_compiled_input_layout(self) -> None:
        profile_lock = copy.deepcopy(self.profile_lock)
        profile_lock["lock_version"] = 2
        profile_lock["generator_version"] = 2
        for row in profile_lock["profiles"]:
            row["conversion_binding"] = None
            row["conversion_artifact"] = None

        profile = next(
            row
            for row in profile_lock["profiles"]
            if row["profile_id"] == "new-Deva-Newa-NP"
        )
        profile_lock["counts"]["selectable"] = 3
        profile.update(
            {
                "layout_id": "deva-nepal-basic-v1",
                "layout_revision": 1,
                "layout_source_sha256": hashlib.sha256(
                    self.source_path("deva-nepal-basic-v1").read_bytes()
                ).hexdigest(),
                "pack_binding": None,
                "pack_artifact": None,
                "conversion_binding": "new-Deva-Newa-NP",
                "conversion_artifact": {
                    "converter_id": "new-Deva-Newa-NP",
                    "file_name": "new-Deva-Newa-NP.ncm",
                    "artifact_sha256": "3" * 64,
                    "language": "new",
                    "source_script": "Deva",
                    "output_script": "Newa",
                    "release_mode": "release",
                    "rule_count": 128,
                    "validation": {
                        "vectors": [
                            {
                                "input": "क",
                                "expected_status": "MATCH",
                                "expected_output": "𑐎",
                            },
                            {
                                "input": "a",
                                "expected_status": "NO_MATCH",
                                "expected_output": None,
                            },
                        ]
                    },
                },
                "selectable": True,
                "blocked_reason": None,
                "blocked_detail": None,
                "default_enabled": False,
                "evidence_ids": ["fixture-newa-conversion-evidence"],
                "evidence_artifacts": [
                    {"path": "fixture/newa.json", "sha256": "4" * 64}
                ],
            }
        )

        lock = self.build(profile_lock)
        self.assertEqual(
            {row["profile_id"] for row in lock["profile_bindings"]},
            {"eng-Latn-US", "new-Deva-Newa-NP", "npi-Deva-NP"},
        )
        self.assertEqual(lock["layout_count"], 2)

    def test_v2_profile_lock_requires_all_four_artifact_binding_fields(self) -> None:
        profile_lock = copy.deepcopy(self.profile_lock)
        profile_lock["lock_version"] = 2
        profile_lock["generator_version"] = 2
        profile_lock["profiles"][0].pop("pack_binding")
        with self.assertRaisesRegex(LayoutError, "missing v2 artifact binding fields"):
            self.build(profile_lock)

    def test_rejects_non_integer_profile_lock_counts(self) -> None:
        profile_lock = copy.deepcopy(self.profile_lock)
        profile_lock["counts"]["selectable"] = True
        with self.assertRaisesRegex(LayoutError, "counts.selectable"):
            self.build(profile_lock)

    def test_output_is_byte_deterministic_and_check_detects_drift(self) -> None:
        first = _canonical_bytes(self.build())
        second = _canonical_bytes(self.build())
        self.assertEqual(first, second)
        output = self.root / "layouts.lock.json"
        output.write_bytes(first)
        arguments = [
            "--source-directory",
            str(SOURCE_DIRECTORY),
            "--profile-lock",
            str(PROFILE_LOCK_PATH),
            "--output",
            str(output),
            "--check",
        ]
        self.assertEqual(main(arguments), 0)
        output.write_bytes(first + b" ")
        with self.assertRaisesRegex(SystemExit, "stale"):
            main(arguments)

    def test_compiled_layout_matches_independent_v0_behavior_golden(self) -> None:
        golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(golden["golden_version"], 1)
        compiled = {row["layout_id"]: row for row in self.build()["layouts"]}
        self.assertEqual(set(compiled), set(golden["layouts"]))
        for layout_id, expected in golden["layouts"].items():
            with self.subTest(layout_id=layout_id):
                profile = expected["profile"]
                actual_layers: dict[str, object] = {}
                for layer_id, layer in compiled[layout_id]["layers"].items():
                    rows = []
                    for row in layer["rows"]:
                        projected_row = []
                        for key in row:
                            if key["kind"] == "text":
                                projected_row.append(key["text"])
                            else:
                                label = self.resolve_templates(key["label"], profile)
                                description = self.resolve_templates(
                                    key["content_description"], profile
                                )
                                projected_row.append(
                                    [
                                        key["action"],
                                        label,
                                        description,
                                        key["width_units"],
                                        key["hold_action"],
                                    ]
                                )
                        rows.append(projected_row)
                    actual_layers[layer_id] = rows
                self.assertEqual(actual_layers, expected["layers"])

    @staticmethod
    def resolve_templates(value: str, profile: dict[str, str]) -> str:
        return value.replace("${profile.native_name}", profile["native_name"]).replace(
            "${profile.display_name}", profile["display_name"]
        )

    def test_stable_key_ids_cover_every_physical_slot(self) -> None:
        for layout in self.build()["layouts"]:
            for layer_id, layer in layout["layers"].items():
                expected_ids = [
                    f"{layer_id}.r{row_index}.k{key_index}"
                    for row_index, row in enumerate(layer["rows"])
                    for key_index, _ in enumerate(row)
                ]
                actual_ids = [key["key_id"] for row in layer["rows"] for key in row]
                self.assertEqual(actual_ids, expected_ids)
                self.assertEqual(len(actual_ids), len(set(actual_ids)))

    def test_transform_order_is_deterministic_and_longest_suffix_first(self) -> None:
        source = self.read_source("latn-qwerty-us-v1")
        source["transforms"] = [
            {"from": "a~", "to": "ã"},
            {"from": "n~", "to": "ñ"},
            {"from": "can~", "to": "cañ"},
        ]
        self.write_source("latn-qwerty-us-v1", source)
        profile_lock = copy.deepcopy(self.profile_lock)
        english = next(
            row
            for row in profile_lock["profiles"]
            if row["profile_id"] == "eng-Latn-US"
        )
        english["layout_source_sha256"] = hashlib.sha256(
            self.source_path("latn-qwerty-us-v1").read_bytes()
        ).hexdigest()
        layout = next(
            row
            for row in self.build(profile_lock)["layouts"]
            if row["layout_id"] == "latn-qwerty-us-v1"
        )
        self.assertEqual(
            layout["transforms"],
            [
                {"transform_id": "t0", "from": "can~", "to": "cañ"},
                {"transform_id": "t1", "from": "a~", "to": "ã"},
                {"transform_id": "t2", "from": "n~", "to": "ñ"},
            ],
        )

    def test_rejects_duplicate_json_keys(self) -> None:
        path = self.source_path("latn-qwerty-us-v1")
        encoded = path.read_text(encoding="utf-8")
        path.write_text(
            encoded.replace('"revision": 1,', '"revision": 1,\n  "revision": 1,'),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(LayoutError, "duplicate JSON key"):
            self.build()

    def test_rejects_non_nfc_and_unsafe_text(self) -> None:
        for bad_value, message in (
            ("e\u0301", "NFC"),
            ("x\n", "unsafe"),
            ("\u200d", "unsupported format"),
        ):
            with self.subTest(value=repr(bad_value)):
                source = self.read_source("latn-qwerty-us-v1")
                source["layers"]["base"]["rows"][0][0] = bad_value
                self.write_source("latn-qwerty-us-v1", source)
                with self.assertRaisesRegex(LayoutError, message):
                    self.build()
                shutil.copy2(
                    SOURCE_DIRECTORY / "latn-qwerty-us-v1.json",
                    self.source_path("latn-qwerty-us-v1"),
                )

    def test_rejects_letter_or_mark_outside_declared_input_script(self) -> None:
        source = self.read_source("latn-qwerty-us-v1")
        source["layers"]["base"]["rows"][0][0] = "क"
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(LayoutError, "outside declared input script Latn"):
            self.build()

    def test_explicit_text_orthographic_word_and_deva_joiners_compile(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        source["layers"]["base"]["rows"].insert(
            -1,
            [
                {
                    "kind": "text",
                    "text": "़",
                    "label": "◌़",
                    "content_description": "Devanagari sign nukta",
                },
                {
                    "kind": "orthographic_word",
                    "text": "‘",
                    "label": "‘",
                    "content_description": "Orthographic word mark",
                },
                {
                    "kind": "deva_conjunct_joiner",
                    "text": "\u200d",
                    "label": "ZWJ",
                    "content_description": "Devanagari zero width joiner",
                },
                {
                    "kind": "deva_conjunct_joiner",
                    "text": "\u200c",
                    "label": "ZWNJ",
                    "content_description": "Devanagari zero width non-joiner",
                },
            ],
        )
        self.write_source("deva-nepal-basic-v1", source)
        profile_lock = copy.deepcopy(self.profile_lock)
        self.bind_source_hash(
            profile_lock,
            "npi-Deva-NP",
            "deva-nepal-basic-v1",
        )

        lock = self.build(profile_lock)
        layout = next(
            row for row in lock["layouts"] if row["layout_id"] == "deva-nepal-basic-v1"
        )
        compiled = {
            key["text"]: key
            for row in layout["layers"]["base"]["rows"]
            for key in row
            if key["text"] is not None
        }
        self.assertEqual(compiled["़"]["kind"], "text")
        self.assertEqual(compiled["़"]["label"], "◌़")
        self.assertEqual(compiled["‘"]["kind"], "orthographic_word")
        self.assertEqual(compiled["\u200d"]["kind"], "deva_conjunct_joiner")
        self.assertEqual(compiled["\u200c"]["kind"], "deva_conjunct_joiner")
        for text in ("़", "‘", "\u200d", "\u200c"):
            self.assertEqual(compiled[text]["width_units"], 100)
            self.assertIsNone(compiled[text]["action"])
            self.assertIsNone(compiled[text]["hold_action"])

    def test_newa_joiners_compile_deterministically_for_synthetic_binding(self) -> None:
        # The cumulative compiler requires every source to be bound to a selectable
        # profile. This isolated fixture temporarily rebinds the already-selectable
        # Nepali profile; it is not evidence for an unselected shipping layout.
        selection_and_pack_before = self.profile_selection_and_pack_state(
            self.profile_lock
        )
        profile_lock, layout_id = self.newa_joiner_fixture()
        self.assertEqual(
            self.profile_selection_and_pack_state(profile_lock),
            selection_and_pack_before,
        )

        first = self.build(profile_lock)
        second = self.build(profile_lock)
        self.assertEqual(_canonical_bytes(first), _canonical_bytes(second))
        self.assertEqual(
            self.profile_selection_and_pack_state(profile_lock),
            selection_and_pack_before,
        )
        self.assertEqual(
            {binding["profile_id"] for binding in first["profile_bindings"]},
            {"eng-Latn-US", "npi-Deva-NP"},
        )
        layout = next(row for row in first["layouts"] if row["layout_id"] == layout_id)
        compiled = {
            key["text"]: key
            for row in layout["layers"]["base"]["rows"]
            for key in row
            if key["text"] is not None
        }
        self.assertEqual(compiled["\u200d"]["kind"], "newa_conjunct_joiner")
        self.assertEqual(compiled["\u200c"]["kind"], "newa_conjunct_joiner")

    def test_newa_joiner_payload_and_script_are_closed(self) -> None:
        profile_lock, layout_id = self.newa_joiner_fixture()
        original = self.read_source(layout_id)
        for text, message in (
            ("\u2060", r"exactly U\+200C or U\+200D"),
            ("\u200c\u200d", r"exactly U\+200C or U\+200D"),
            ("", "non-empty string"),
        ):
            with self.subTest(text=repr(text)):
                source = copy.deepcopy(original)
                source["layers"]["base"]["rows"][-2][0]["text"] = text
                self.write_source(layout_id, source)
                self.bind_source_hash(profile_lock, "npi-Deva-NP", layout_id)
                with self.assertRaisesRegex(LayoutError, message):
                    self.build(profile_lock)

        source = self.read_source("latn-qwerty-us-v1")
        source["layers"]["base"]["rows"].insert(
            -1,
            [
                {
                    "kind": "newa_conjunct_joiner",
                    "text": "\u200d",
                    "label": "ZWJ",
                    "content_description": "Newa zero width joiner",
                }
            ],
        )
        self.write_source("latn-qwerty-us-v1", source)
        self.bind_source_hash(profile_lock, "eng-Latn-US", "latn-qwerty-us-v1")
        with self.assertRaisesRegex(LayoutError, "requires input script Newa"):
            self.build(profile_lock)

    def test_orthographic_word_payload_is_closed(self) -> None:
        for text in ("’", "ab"):
            with self.subTest(text=repr(text)):
                source = self.read_source("deva-nepal-basic-v1")
                source["layers"]["base"]["rows"][0][0] = {
                    "kind": "orthographic_word",
                    "text": text,
                    "label": "word mark",
                    "content_description": "Orthographic word mark",
                }
                self.write_source("deva-nepal-basic-v1", source)
                with self.assertRaisesRegex(LayoutError, r"exactly U\+2018"):
                    self.build()
                shutil.copy2(
                    SOURCE_DIRECTORY / "deva-nepal-basic-v1.json",
                    self.source_path("deva-nepal-basic-v1"),
                )

    def test_intra_word_punctuation_payload_is_explicit_and_closed(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        symbols = source["layers"]["symbols"]["rows"]
        replacements = ((1, 5, "-"), (2, 7, "/"), (2, 3, ":"))
        for row_index, key_index, text in replacements:
            symbols[row_index][key_index] = {
                "kind": "intra_word_punctuation",
                "text": text,
                "label": text,
                "content_description": f"Intra-word {text}",
            }
        symbols[2].append(
            {
                "kind": "intra_word_punctuation",
                "text": "\\",
                "label": "\\",
                "content_description": "Intra-word backslash",
            }
        )
        self.write_source("deva-nepal-basic-v1", source)
        profile_lock = copy.deepcopy(self.profile_lock)
        self.bind_source_hash(profile_lock, "npi-Deva-NP", "deva-nepal-basic-v1")
        lock = self.build(profile_lock)
        layout = next(
            row for row in lock["layouts"] if row["layout_id"] == "deva-nepal-basic-v1"
        )
        compiled_symbols = layout["layers"]["symbols"]["rows"]
        self.assertEqual(compiled_symbols[1][5]["kind"], "intra_word_punctuation")
        self.assertEqual(compiled_symbols[2][3]["kind"], "intra_word_punctuation")
        self.assertEqual(compiled_symbols[2][7]["kind"], "intra_word_punctuation")
        self.assertEqual(compiled_symbols[2][9]["kind"], "intra_word_punctuation")

        for text in ("_", "--", "‐"):
            with self.subTest(text=repr(text)):
                source = self.read_source("deva-nepal-basic-v1")
                source["layers"]["symbols"]["rows"][0][0] = {
                    "kind": "intra_word_punctuation",
                    "text": text,
                    "label": "connector",
                    "content_description": "Intra-word punctuation",
                }
                self.write_source("deva-nepal-basic-v1", source)
                with self.assertRaisesRegex(
                    LayoutError,
                    "exactly hyphen, slash, backslash, or colon",
                ):
                    self.build(profile_lock)

    def test_deva_joiner_payload_and_script_are_closed(self) -> None:
        for text, message in (
            ("\u2060", r"exactly U\+200C or U\+200D"),
            ("\u200c\u200d", r"exactly U\+200C or U\+200D"),
            ("", "non-empty string"),
        ):
            with self.subTest(text=repr(text)):
                source = self.read_source("deva-nepal-basic-v1")
                source["layers"]["base"]["rows"][0][0] = {
                    "kind": "deva_conjunct_joiner",
                    "text": text,
                    "label": "joiner",
                    "content_description": "Devanagari conjunct joiner",
                }
                self.write_source("deva-nepal-basic-v1", source)
                with self.assertRaisesRegex(LayoutError, message):
                    self.build()
                shutil.copy2(
                    SOURCE_DIRECTORY / "deva-nepal-basic-v1.json",
                    self.source_path("deva-nepal-basic-v1"),
                )

        source = self.read_source("latn-qwerty-us-v1")
        source["layers"]["base"]["rows"][0][0] = {
            "kind": "deva_conjunct_joiner",
            "text": "\u200d",
            "label": "ZWJ",
            "content_description": "Devanagari zero width joiner",
        }
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(LayoutError, "requires input script Deva"):
            self.build()

    def test_deva_terminal_zwnj_policy_is_explicit_and_closed(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        source["layers"]["base"]["rows"][0][0] = {
            "kind": "deva_terminal_zwnj",
            "text": "\u200c",
            "label": "ZWNJ",
            "content_description": "Terminal-capable zero width non-joiner",
        }
        self.write_source("deva-nepal-basic-v1", source)
        profile_lock = copy.deepcopy(self.profile_lock)
        self.bind_source_hash(profile_lock, "npi-Deva-NP", "deva-nepal-basic-v1")
        lock = self.build(profile_lock)
        layout = next(
            row for row in lock["layouts"] if row["layout_id"] == "deva-nepal-basic-v1"
        )
        self.assertEqual(
            layout["layers"]["base"]["rows"][0][0]["kind"],
            "deva_terminal_zwnj",
        )

        for text in ("\u200d", "\u200c\u200d"):
            with self.subTest(text=repr(text)):
                source["layers"]["base"]["rows"][0][0]["text"] = text
                self.write_source("deva-nepal-basic-v1", source)
                with self.assertRaisesRegex(LayoutError, r"exactly U\+200C"):
                    self.build(profile_lock)

        shutil.copy2(
            SOURCE_DIRECTORY / "deva-nepal-basic-v1.json",
            self.source_path("deva-nepal-basic-v1"),
        )
        latin = self.read_source("latn-qwerty-us-v1")
        latin["layers"]["base"]["rows"][0][0] = {
            "kind": "deva_terminal_zwnj",
            "text": "\u200c",
            "label": "ZWNJ",
            "content_description": "Terminal-capable zero width non-joiner",
        }
        self.write_source("latn-qwerty-us-v1", latin)
        with self.assertRaisesRegex(LayoutError, "requires input script Deva"):
            self.build()

    def test_generic_text_still_rejects_joiners(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        source["layers"]["base"]["rows"][0][0] = {
            "kind": "text",
            "text": "\u200d",
            "label": "ZWJ",
            "content_description": "Generic format character",
        }
        self.write_source("deva-nepal-basic-v1", source)
        with self.assertRaisesRegex(LayoutError, r"unsupported format U\+200D"):
            self.build()

    def test_duplicate_payload_across_text_kinds_is_rejected(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        source["layers"]["base"]["rows"].insert(
            -1,
            [
                {
                    "kind": "text",
                    "text": "‘",
                    "label": "punctuation",
                    "content_description": "Generic punctuation",
                },
                {
                    "kind": "orthographic_word",
                    "text": "‘",
                    "label": "word mark",
                    "content_description": "Orthographic word mark",
                },
            ],
        )
        self.write_source("deva-nepal-basic-v1", source)
        with self.assertRaisesRegex(LayoutError, "duplicate text keys"):
            self.build()

    def test_explicit_text_key_object_is_exact(self) -> None:
        for mutation, message in (
            (("remove", "content_description"), "missing fields"),
            (("add", "width_units"), "unknown fields"),
            (("replace", "kind"), "kind is unsupported"),
        ):
            with self.subTest(mutation=mutation):
                source = self.read_source("deva-nepal-basic-v1")
                key = {
                    "kind": "text",
                    "text": "़",
                    "label": "◌़",
                    "content_description": "Devanagari sign nukta",
                }
                operation, field = mutation
                if operation == "remove":
                    del key[field]
                elif operation == "add":
                    key[field] = 100
                else:
                    key[field] = "macro"
                source["layers"]["base"]["rows"][0][0] = key
                self.write_source("deva-nepal-basic-v1", source)
                with self.assertRaisesRegex(LayoutError, message):
                    self.build()
                shutil.copy2(
                    SOURCE_DIRECTORY / "deva-nepal-basic-v1.json",
                    self.source_path("deva-nepal-basic-v1"),
                )

    def test_rejects_unapproved_redistribution(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        source["license"]["redistribution"] = "unknown"
        self.write_source("deva-nepal-basic-v1", source)
        with self.assertRaisesRegex(
            LayoutError, "redistribution must be allowed for release"
        ):
            self.build()

    def test_release_authority_requires_complete_six_field_license(self) -> None:
        original = self.read_source("deva-nepal-basic-v1")
        cases = (
            (None, "license is required for release"),
            ("license_url", "license is missing fields: license_url"),
            ("notice_path", "license is missing fields: notice_path"),
        )
        for removed_field, message in cases:
            with self.subTest(removed_field=removed_field):
                source = copy.deepcopy(original)
                if removed_field is None:
                    del source["license"]
                else:
                    del source["license"][removed_field]
                self.write_source("deva-nepal-basic-v1", source)
                with self.assertRaisesRegex(LayoutError, message):
                    self.build()
        self.write_source("deva-nepal-basic-v1", original)

    def test_internal_authority_compiles_absent_license_canonically_to_null(
        self,
    ) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        notice_name = Path(source["license"]["notice_path"]).name
        del source["license"]
        self.write_source("deva-nepal-basic-v1", source)
        (self.layouts / "notices" / notice_name).unlink()
        profile_lock = self.internal_profile_lock()
        self.bind_source_hash(
            profile_lock,
            "npi-Deva-NP",
            "deva-nepal-basic-v1",
        )

        first = self.build(profile_lock)
        second = self.build(profile_lock)
        deva = next(
            row for row in first["layouts"] if row["layout_id"] == "deva-nepal-basic-v1"
        )
        self.assertIsNone(deva["license"])
        self.assertEqual(_canonical_bytes(first), _canonical_bytes(second))

    def test_internal_authority_preserves_partial_license_fields(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        notice_name = Path(source["license"]["notice_path"]).name
        source["license"] = {
            "id": "LicenseRef-Internal",
            "copyright": "Ampixa internal layout",
            "license_url": "https://example.test/internal-layout",
            "redistribution": "unknown",
        }
        self.write_source("deva-nepal-basic-v1", source)
        (self.layouts / "notices" / notice_name).unlink()
        profile_lock = self.internal_profile_lock()
        self.bind_source_hash(
            profile_lock,
            "npi-Deva-NP",
            "deva-nepal-basic-v1",
        )

        compiled = self.build(profile_lock)
        deva = next(
            row
            for row in compiled["layouts"]
            if row["layout_id"] == "deva-nepal-basic-v1"
        )
        self.assertEqual(deva["license"], source["license"])

    def test_internal_authority_supports_an_empty_notice_inventory(self) -> None:
        profile_lock = self.internal_profile_lock()
        for profile_id, layout_id in (
            ("eng-Latn-US", "latn-qwerty-us-v1"),
            ("npi-Deva-NP", "deva-nepal-basic-v1"),
        ):
            source = self.read_source(layout_id)
            notice_name = Path(source["license"]["notice_path"]).name
            del source["license"]
            self.write_source(layout_id, source)
            (self.layouts / "notices" / notice_name).unlink()
            self.bind_source_hash(profile_lock, profile_id, layout_id)

        compiled = self.build(profile_lock)
        self.assertEqual(compiled["layout_count"], 2)
        self.assertTrue(all(row["license"] is None for row in compiled["layouts"]))

    def test_internal_partial_license_requires_core_fields_and_https_url(self) -> None:
        original = self.read_source("deva-nepal-basic-v1")
        profile_lock = self.internal_profile_lock()
        for missing_field in ("id", "copyright", "redistribution"):
            with self.subTest(missing_field=missing_field):
                source = copy.deepcopy(original)
                source["license"] = {
                    "id": "LicenseRef-Internal",
                    "copyright": "Ampixa internal layout",
                    "redistribution": "unknown",
                }
                del source["license"][missing_field]
                self.write_source("deva-nepal-basic-v1", source)
                with self.assertRaisesRegex(
                    LayoutError,
                    f"license is missing fields: {missing_field}",
                ):
                    self.build(profile_lock)

        source = copy.deepcopy(original)
        source["license"] = {
            "id": "LicenseRef-Internal",
            "copyright": "Ampixa internal layout",
            "license_url": "http://example.test/internal-layout",
            "redistribution": "unknown",
        }
        self.write_source("deva-nepal-basic-v1", source)
        with self.assertRaisesRegex(LayoutError, "license_url must use HTTPS"):
            self.build(profile_lock)

    def test_internal_authority_rejects_one_sided_notice_fields(self) -> None:
        original = self.read_source("deva-nepal-basic-v1")
        profile_lock = self.internal_profile_lock()
        for missing_field in ("notice_path", "notice_sha256"):
            with self.subTest(missing_field=missing_field):
                source = copy.deepcopy(original)
                del source["license"][missing_field]
                self.write_source("deva-nepal-basic-v1", source)
                with self.assertRaisesRegex(
                    LayoutError,
                    "notice_path and notice_sha256 must be provided together",
                ):
                    self.build(profile_lock)

        source = copy.deepcopy(original)
        source["license"]["redistribution"] = "unknown"
        source["license"]["notice_sha256"] = "0" * 64
        self.write_source("deva-nepal-basic-v1", source)
        with self.assertRaisesRegex(LayoutError, "notice SHA-256 mismatch"):
            self.build(profile_lock)

    def test_internal_authority_rejects_explicit_null_license(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        source["license"] = None
        self.write_source("deva-nepal-basic-v1", source)
        with self.assertRaisesRegex(LayoutError, "license must be an object"):
            self.build(self.internal_profile_lock())

    def test_internal_authority_preserves_unknown_redistribution_metadata(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        source["license"]["redistribution"] = "unknown"
        self.write_source("deva-nepal-basic-v1", source)
        profile_lock = self.internal_profile_lock()
        nepali = next(
            row
            for row in profile_lock["profiles"]
            if row["profile_id"] == "npi-Deva-NP"
        )
        nepali["layout_source_sha256"] = hashlib.sha256(
            self.source_path("deva-nepal-basic-v1").read_bytes()
        ).hexdigest()
        compiled = self.build(profile_lock)
        deva = next(
            row
            for row in compiled["layouts"]
            if row["layout_id"] == "deva-nepal-basic-v1"
        )
        self.assertEqual(deva["license"]["redistribution"], "unknown")

    def test_actual_internal_source_lane_compiles_with_lane_relative_notices(
        self,
    ) -> None:
        internal_sources = self.layouts / "internal" / "src"
        internal_profile_lock = json.loads(
            (ROOT / "catalog/internal-profiles.lock.json").read_text(encoding="utf-8")
        )
        compiled = self.build(
            internal_profile_lock,
            source_directory=internal_sources,
            source_path_prefix="layouts/internal/src",
            profile_lock_path="catalog/internal-profiles.lock.json",
        )
        self.assertEqual(compiled["layout_count"], 12)
        self.assertEqual(
            {row["layout_id"] for row in compiled["layouts"]},
            {
                "deva-nepal-basic-v1",
                "deva-nepal-bhasa-v1",
                "deva-nepal-dhimal-v1",
                "deva-nepal-dumi-v1",
                "deva-nepal-extended-v1",
                "deva-nepal-khaling-v1",
                "deva-nepal-lohorung-v1",
                "deva-nepal-western-tamang-v1",
                "deva-nepal-yakkha-v1",
                "latn-qwerty-us-v1",
                "limb-nepal-phonetic-v1",
                "newa-nepal-prachalit-v1",
            },
        )
        self.assertTrue(
            all(
                row["license"]["notice_path"].startswith("layouts/internal/notices/")
                for row in compiled["layouts"]
                if row["license"] is not None
            )
        )
        nepal_bhasa = next(
            row
            for row in compiled["layouts"]
            if row["layout_id"] == "deva-nepal-bhasa-v1"
        )
        self.assertIsNone(nepal_bhasa["license"])

    def test_rejects_authority_changed_without_matching_block_policy(self) -> None:
        profile_lock = copy.deepcopy(self.profile_lock)
        profile_lock["review"]["authority"] = "internal"
        with self.assertRaisesRegex(
            LayoutError, "reason does not match internal authority"
        ):
            self.build(profile_lock)

    def test_rejects_notice_path_from_another_source_lane(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        source["license"]["notice_path"] = (
            "layouts/internal/notices/xkb-data-2.41-2ubuntu1.1.copyright"
        )
        self.write_source("deva-nepal-basic-v1", source)
        with self.assertRaisesRegex(LayoutError, "notice_path is unsafe or reserved"):
            self.build()

    def test_rejects_unknown_action_template_and_hold_semantics(self) -> None:
        cases = (
            ("action", "launch_app", "action is unsupported"),
            ("label", "${profile.secret}", "unsupported template"),
            ("hold_action", "open_language_picker", "only valid for space or language"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                source = self.read_source("latn-qwerty-us-v1")
                key = source["layers"]["base"]["rows"][-1][0]
                key[field] = value
                self.write_source("latn-qwerty-us-v1", source)
                with self.assertRaisesRegex(LayoutError, message):
                    self.build()
                shutil.copy2(
                    SOURCE_DIRECTORY / "latn-qwerty-us-v1.json",
                    self.source_path("latn-qwerty-us-v1"),
                )

    def test_rejects_duplicate_identity_and_oversized_transform(self) -> None:
        cases = (
            (
                [{"from": "ab", "to": "x"}, {"from": "ab", "to": "y"}],
                "duplicate transform",
            ),
            ([{"from": "ab", "to": "ab"}], "identity transform"),
            ([{"from": "abcdefghijklmnopq", "to": "x"}], "bounded suffix"),
        )
        for transforms, message in cases:
            with self.subTest(message=message):
                source = self.read_source("latn-qwerty-us-v1")
                source["transforms"] = transforms
                self.write_source("latn-qwerty-us-v1", source)
                with self.assertRaisesRegex(LayoutError, message):
                    self.build()
                shutil.copy2(
                    SOURCE_DIRECTORY / "latn-qwerty-us-v1.json",
                    self.source_path("latn-qwerty-us-v1"),
                )

    def test_rejects_missing_selectable_layout(self) -> None:
        source = self.read_source("deva-nepal-basic-v1")
        notice_name = Path(source["license"]["notice_path"]).name
        self.source_path("deva-nepal-basic-v1").unlink()
        (self.layouts / "notices" / notice_name).unlink()
        with self.assertRaisesRegex(LayoutError, "has no compiled layout"):
            self.build()

    def test_rejects_profile_layout_input_script_mismatch(self) -> None:
        profile_lock = copy.deepcopy(self.profile_lock)
        profile = next(
            row
            for row in profile_lock["profiles"]
            if row["profile_id"] == "npi-Deva-NP"
        )
        profile["source_script"] = "Latn"
        with self.assertRaisesRegex(LayoutError, "does not match"):
            self.build(profile_lock)

    def test_rejects_profile_object_with_claimed_official_hash(self) -> None:
        profile_lock = copy.deepcopy(self.profile_lock)
        profile_lock["profiles"][0]["source_script"] = "Deva"
        with self.assertRaisesRegex(LayoutError, "does not match its claimed SHA-256"):
            build_lock(
                self.source,
                profile_lock,
                profile_lock_path="catalog/shipping-profiles.lock.json",
                profile_lock_sha256=hashlib.sha256(self.profile_bytes).hexdigest(),
                compiler_reference={"path": "tool", "sha256": "0" * 64},
                schema_references={
                    "source": {"path": "source", "sha256": "1" * 64},
                    "lock": {"path": "lock", "sha256": "2" * 64},
                },
            )

    def test_rejects_notice_hash_drift_and_wrong_unicode_database_declaration(
        self,
    ) -> None:
        source = self.read_source("latn-qwerty-us-v1")
        source["license"]["notice_sha256"] = "0" * 64
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(LayoutError, "notice SHA-256 mismatch"):
            self.build()
        shutil.copy2(
            SOURCE_DIRECTORY / "latn-qwerty-us-v1.json",
            self.source_path("latn-qwerty-us-v1"),
        )
        source = self.read_source("latn-qwerty-us-v1")
        source["unicode_data_version"] = "15.0.0"
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(LayoutError, "unicode_data_version"):
            self.build()

    def test_rejects_reserved_generated_notice_manifest_name(self) -> None:
        notice = self.layouts / "notices" / "manifest.json"
        notice.write_text("reserved\n", encoding="utf-8")
        source = self.read_source("latn-qwerty-us-v1")
        source["license"]["notice_path"] = "layouts/notices/manifest.json"
        source["license"]["notice_sha256"] = hashlib.sha256(
            notice.read_bytes()
        ).hexdigest()
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(LayoutError, "unsafe or reserved"):
            self.build()

    def test_rejects_notice_bom_and_invalid_utf8(self) -> None:
        original_source = self.read_source("latn-qwerty-us-v1")
        notice_name = Path(original_source["license"]["notice_path"]).name
        notice = self.layouts / "notices" / notice_name
        original_notice = notice.read_bytes()
        cases = (
            (b"\xef\xbb\xbf" + original_notice, "without BOM"),
            (b"\xff", "must be UTF-8"),
        )
        for encoded, message in cases:
            with self.subTest(message=message):
                notice.write_bytes(encoded)
                source = copy.deepcopy(original_source)
                source["license"]["notice_sha256"] = hashlib.sha256(encoded).hexdigest()
                self.write_source("latn-qwerty-us-v1", source)
                with self.assertRaisesRegex(LayoutError, message):
                    self.build()
        notice.write_bytes(original_notice)

    def test_rejects_notice_above_android_runtime_bound(self) -> None:
        source = self.read_source("latn-qwerty-us-v1")
        notice_name = Path(source["license"]["notice_path"]).name
        notice = self.layouts / "notices" / notice_name
        encoded = b"x" * (MAX_NOTICE_BYTES + 1)
        notice.write_bytes(encoded)
        source["license"]["notice_sha256"] = hashlib.sha256(encoded).hexdigest()
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(LayoutError, "65536-byte runtime bound"):
            self.build()

    def test_notice_directory_must_exactly_match_compiled_notice_pairs(self) -> None:
        notice_directory = self.layouts / "notices"
        extra = notice_directory / "extra.txt"
        extra.write_text("extra\n", encoding="utf-8")
        with self.assertRaisesRegex(LayoutError, "does not exactly match"):
            self.build()
        extra.unlink()

        unexpected_directory = notice_directory / "nested"
        unexpected_directory.mkdir()
        with self.assertRaisesRegex(LayoutError, "unsupported entries"):
            self.build()
        unexpected_directory.rmdir()

        unexpected_symlink = notice_directory / "linked.txt"
        unexpected_symlink.symlink_to("ampixa-layouts-mit.txt")
        with self.assertRaisesRegex(LayoutError, "unsupported entries"):
            self.build()

    def test_compiled_layout_notices_must_use_distinct_assets(self) -> None:
        deva = self.read_source("deva-nepal-basic-v1")
        english = self.read_source("latn-qwerty-us-v1")
        old_english_notice = Path(english["license"]["notice_path"]).name
        english["license"]["notice_path"] = deva["license"]["notice_path"]
        english["license"]["notice_sha256"] = deva["license"]["notice_sha256"]
        self.write_source("latn-qwerty-us-v1", english)
        (self.layouts / "notices" / old_english_notice).unlink()
        profile_lock = copy.deepcopy(self.profile_lock)
        self.bind_source_hash(
            profile_lock,
            "eng-Latn-US",
            "latn-qwerty-us-v1",
        )
        with self.assertRaisesRegex(LayoutError, "distinct asset"):
            self.build(profile_lock)

    def test_rejects_more_than_android_runtime_layout_bound(self) -> None:
        original = self.source_path("latn-qwerty-us-v1")
        existing_count = len(list(self.source.iterdir()))
        for index in range(MAX_LAYOUTS - existing_count + 1):
            shutil.copy2(original, self.source / f"extra-{index:02d}.json")
        with self.assertRaisesRegex(
            LayoutError,
            f"{MAX_LAYOUTS}-layout runtime bound",
        ):
            self.build()

    def test_rejects_out_of_range_layout_width(self) -> None:
        source = self.read_source("latn-qwerty-us-v1")
        source["layers"]["base"]["rows"][-1][0]["width_units"] = 2**63
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(
            LayoutError, "width_units must be between 25 and 1000"
        ):
            self.build()

    def test_rejects_duplicate_text_and_incomplete_action_row(self) -> None:
        source = self.read_source("latn-qwerty-us-v1")
        source["layers"]["base"]["rows"][0][1] = "q"
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(LayoutError, "duplicate text keys"):
            self.build()
        shutil.copy2(
            SOURCE_DIRECTORY / "latn-qwerty-us-v1.json",
            self.source_path("latn-qwerty-us-v1"),
        )
        source = self.read_source("latn-qwerty-us-v1")
        source["layers"]["numeric"]["rows"][-1].pop()
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(LayoutError, "closed v1 action sequence"):
            self.build()

    def test_rejects_unbound_layout_source(self) -> None:
        source = self.read_source("latn-qwerty-us-v1")
        source["layout_id"] = "latn-unbound-v1"
        notice_name = "latn-unbound-v1.notice.txt"
        original_notice_name = Path(source["license"]["notice_path"]).name
        notice_bytes = (
            self.layouts / "notices" / original_notice_name
        ).read_bytes() + b"\nUnbound layout test fixture.\n"
        (self.layouts / "notices" / notice_name).write_bytes(notice_bytes)
        source["license"]["notice_path"] = f"layouts/notices/{notice_name}"
        source["license"]["notice_sha256"] = hashlib.sha256(notice_bytes).hexdigest()
        self.write_source("latn-unbound-v1", source)
        with self.assertRaisesRegex(LayoutError, "not selectable-profile bound"):
            self.build()

    def test_rejects_layout_id_path_mismatch_and_unexpected_entries(self) -> None:
        source = self.read_source("latn-qwerty-us-v1")
        source["layout_id"] = "latn-other-v1"
        self.write_source("latn-qwerty-us-v1", source)
        with self.assertRaisesRegex(LayoutError, "ID/path mismatch"):
            self.build()
        shutil.copy2(
            SOURCE_DIRECTORY / "latn-qwerty-us-v1.json",
            self.source_path("latn-qwerty-us-v1"),
        )
        (self.source / "README.md").write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(LayoutError, "unsupported entries"):
            self.build()


if __name__ == "__main__":
    unittest.main()
