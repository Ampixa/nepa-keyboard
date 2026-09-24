from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from tools import audit_sil_apk_layout_gap as auditor


ROOT = Path(__file__).resolve().parents[1]


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


class SilApkLayoutGapAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "nepali-fixture.sil-apk.dict.jsonl"
        surfaces = (
            "अक्\u200dख",
            "टाङ्\u200c",
            "पे-पा",
            "इ",
            "अ",
            "अ",
            "Latin",
            "अम\u200cर",
        )
        self.raw.write_text(
            "".join(
                json.dumps({
                    "lang": "fix",
                    "headword": surface,
                    "ne": [],
                    "en": [],
                    "source": "sil-apk/fixture",
                }, ensure_ascii=False, separators=(",", ":")) + "\n"
                for surface in surfaces
            ),
            encoding="utf-8",
        )
        raw_bytes = self.raw.read_bytes()
        self.catalog = self.root / "catalog" / "resources.json"
        self.catalog.parent.mkdir()
        self.catalog.write_text(canonical({
            "packs": [{
                "id": "fix",
                "name": "Fixture",
                "iso_639_3": "fix",
                "variety": "Test Kiranti",
                "resources": [{
                    "id": "fix-apk",
                    "kind": "lexicon",
                    "path": "/inventory/nepali-fixture.sil-apk.dict.jsonl",
                    "format": "JSONL",
                    "structured": True,
                    "canonical": True,
                    "uses": ["candidate_vocabulary"],
                    "record_unit": "entries",
                    "records": len(surfaces),
                    "bytes": len(raw_bytes),
                    "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                    "license": "restricted",
                    "redistribution": "prohibited",
                }],
            }],
        }), encoding="utf-8")
        self.layout_lock = self.root / "layouts" / "internal" / "layouts-v1.lock.json"
        self.layout_lock.parent.mkdir(parents=True)
        self.write_layout(complete=False)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def text_key(key_id: str, text: str, kind: str = "text") -> dict[str, object]:
        return {
            "action": None,
            "content_description": text,
            "hold_action": None,
            "key_id": key_id,
            "kind": kind,
            "label": text,
            "text": text,
            "width_units": 100,
        }

    @staticmethod
    def action_key(key_id: str) -> dict[str, object]:
        return {
            "action": "enter",
            "content_description": "Enter",
            "hold_action": None,
            "key_id": key_id,
            "kind": "action",
            "label": "Enter",
            "text": None,
            "width_units": 100,
        }

    def write_layout(
        self,
        *,
        complete: bool,
        transforms: object = None,
        zwnj_kind: str = "deva_terminal_zwnj",
    ) -> None:
        base_text = "अक्खटाङ्पेरामेा्"
        base = [
            self.text_key(f"base.r0.k{index}", character)
            for index, character in enumerate(dict.fromkeys(base_text))
        ]
        if complete:
            base.extend((
                self.text_key(f"base.r0.k{len(base)}", "इ"),
                self.text_key(
                    f"base.r0.k{len(base) + 1}",
                    "\u200d",
                    "deva_conjunct_joiner",
                ),
                self.text_key(
                    f"base.r0.k{len(base) + 2}",
                    "\u200c",
                    zwnj_kind,
                ),
            ))
        hyphen_kind = "intra_word_punctuation" if complete else "text"
        layout = {
            "layout_id": "deva-fixture-v1",
            "input_script": "Deva",
            "revision": 1,
            "source": {"sha256": "1" * 64},
            "transforms": [] if transforms is None else transforms,
            "layers": {
                "base": {"rows": [base, [self.action_key("base.r1.k0")]]},
                "shift": {"rows": [[self.text_key("shift.r0.k0", "अ")]]},
                "symbols": {"rows": [[
                    self.text_key("symbols.r0.k0", "-", hyphen_kind),
                ]]},
                "numeric": {"rows": [[self.text_key("numeric.r0.k0", "1")]]},
            },
        }
        self.layout_lock.write_text(canonical({"layouts": [layout]}), encoding="utf-8")

    def args(self) -> argparse.Namespace:
        return argparse.Namespace(
            resource_catalog=self.catalog,
            target_id="fix",
            resource_id="fix-apk",
            sil_apk_jsonl=self.raw,
            source_tag="sil-apk/fixture",
            layout_lock=self.layout_lock,
            layout_id="deva-fixture-v1",
            output=self.root / "audit.json",
            check=False,
        )

    @staticmethod
    def fixture_lock(path: Path) -> tuple[dict[str, object], bytes, dict[str, object]]:
        encoded = path.read_bytes()
        return json.loads(encoded), encoded, {"fixture": True}

    def build_args(self, args: argparse.Namespace) -> dict[str, object]:
        with (
            mock.patch.object(auditor, "REPOSITORY_ROOT", self.root),
            mock.patch.object(
                auditor,
                "_verify_layout_lock",
                side_effect=self.fixture_lock,
            ),
            mock.patch.object(
                auditor,
                "REQUIRED_UNICODE_VERSION",
                unicodedata.unidata_version,
            ),
        ):
            return auditor.build_audit(args)

    def build(self) -> dict[str, object]:
        return self.build_args(self.args())

    def test_reports_terminal_delta_missing_keys_and_noncomposing_punctuation(self) -> None:
        report = self.build()
        conjunct = report["policies"]["conjunct_only"]
        terminal = report["policies"]["terminal_zwnj"]

        self.assertEqual(conjunct["accepted_rows"], 5)
        self.assertEqual(conjunct["rejected_rows"], 3)
        self.assertEqual(
            conjunct["rejected_by_reason"],
            {"invalid_joiner_context": 2, "outside_devanagari": 1},
        )
        self.assertEqual(conjunct["missing_input_scalars"], ["इ", "\u200d"])
        self.assertEqual(conjunct["noncomposing_present_scalars"], ["-"])

        self.assertEqual(terminal["accepted_rows"], 6)
        self.assertEqual(terminal["accepted_terminal_zwnj_rows"], 1)
        self.assertEqual(
            terminal["missing_input_scalars"],
            ["इ", "\u200c", "\u200d"],
        )
        self.assertEqual(terminal["duplicate_groups"], 1)
        self.assertEqual(terminal["duplicate_rows_merged_by_pack"], 1)
        self.assertEqual(
            terminal["single_token_composition"]["unqueryable_by_reason"],
            {
                "missing_text_field_input": 3,
                "noncomposing_layout_key": 1,
            },
        )
        self.assertEqual(report["terminal_zwnj_delta"], {
            "additional_accepted_rows": 1,
            "additional_distinct_surfaces": 1,
            "bounded_examples": [{"line": 2, "surface": "टाङ्\u200c"}],
            "example_limit": 32,
            "requires_terminal_zwnj_to_retain_rows": True,
        })
        self.assertEqual(
            report["layout"]["layout_lock_path"],
            "layouts/internal/layouts-v1.lock.json",
        )
        self.assertEqual(report["resource_catalog"]["path"], "catalog/resources.json")

    def test_inventory_complete_policy_layout_clears_input_gaps(self) -> None:
        self.write_layout(complete=True)
        report = self.build()
        terminal = report["policies"]["terminal_zwnj"]
        self.assertEqual(terminal["missing_input_scalars"], [])
        self.assertEqual(terminal["noncomposing_present_scalars"], [])
        inventory = {row["scalar"]: row for row in terminal["scalar_inventory"]}
        self.assertEqual(inventory["-"]["layout_kinds"], ["intra_word_punctuation"])
        self.assertTrue(inventory["\u200c"]["contextual_composing_access"])
        self.assertTrue(inventory["\u200d"]["contextual_composing_access"])
        self.assertEqual(terminal["single_token_composition"]["unqueryable_rows"], 0)

    def test_conjunct_zwnj_key_does_not_claim_terminal_coverage(self) -> None:
        self.write_layout(complete=True, zwnj_kind="deva_conjunct_joiner")
        terminal = self.build()["policies"]["terminal_zwnj"]
        self.assertEqual(terminal["missing_input_scalars"], [])
        self.assertEqual(
            terminal["single_token_composition"]["unqueryable_by_reason"],
            {"terminal_zwnj_layout_policy": 1},
        )
        example = terminal["single_token_composition"]["bounded_unqueryable_examples"][0]
        self.assertEqual(example["surface"], "टाङ्\u200c")

    def test_surface_simulation_rejects_leading_chained_and_boundary_punctuation(self) -> None:
        access = {
            "प": [{"key_id": "base.r0.k0", "kind": "text", "layer": "base"}],
            "ा": [{"key_id": "base.r0.k1", "kind": "text", "layer": "base"}],
            "-": [{
                "key_id": "symbols.r0.k0",
                "kind": "intra_word_punctuation",
                "layer": "symbols",
            }],
            "/": [{
                "key_id": "symbols.r0.k1",
                "kind": "intra_word_punctuation",
                "layer": "symbols",
            }],
        }
        self.assertEqual(
            auditor._surface_gap("-पा", access)["reason"],
            "intra_word_punctuation_context",
        )
        self.assertEqual(
            auditor._surface_gap("पा-/पा", access)["reason"],
            "intra_word_punctuation_context",
        )
        self.assertEqual(
            auditor._surface_gap("पा पा", access)["reason"],
            "word_boundary_scalar",
        )

    def test_surface_simulation_accepts_any_valid_key_path(self) -> None:
        access = {
            "प": [{"key_id": "base.r0.k0", "kind": "text", "layer": "base"}],
            "-": [
                {
                    "key_id": "base.r0.k1",
                    "kind": "text",
                    "layer": "base",
                },
                {
                    "key_id": "symbols.r0.k0",
                    "kind": "intra_word_punctuation",
                    "layer": "symbols",
                },
            ],
        }
        self.assertIsNone(auditor._surface_gap("प-प", access))

    def test_rejects_catalog_source_layout_and_unicode_drift(self) -> None:
        bad_args = self.args()
        bad_args.source_tag = "sil-apk/not-fixture"
        with self.assertRaisesRegex(auditor.AuditError, "source tag"):
            self.build_args(bad_args)

        self.write_layout(complete=False, transforms=[{"from": "अ", "to": "आ"}])
        with self.assertRaisesRegex(auditor.AuditError, "transforms"):
            self.build()

        self.write_layout(complete=False)
        with (
            mock.patch.object(auditor, "REPOSITORY_ROOT", self.root),
            mock.patch.object(auditor, "REQUIRED_UNICODE_VERSION", "0.0.0"),
            self.assertRaisesRegex(auditor.AuditError, "Unicode data"),
        ):
            auditor.build_audit(self.args())

        encoded = self.raw.read_bytes().replace("अ".encode(), "आ".encode(), 1)
        self.raw.write_bytes(encoded)
        with self.assertRaisesRegex(auditor.AuditError, "byte count|SHA-256"):
            self.build()

    def test_rejects_noncanonical_catalog_resource(self) -> None:
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["packs"][0]["resources"][0]["canonical"] = False
        self.catalog.write_text(canonical(catalog), encoding="utf-8")
        with self.assertRaisesRegex(auditor.AuditError, "must be canonical"):
            self.build()

    def test_rejects_unstructured_or_noncandidate_catalog_resource(self) -> None:
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        resource = catalog["packs"][0]["resources"][0]
        resource["structured"] = False
        self.catalog.write_text(canonical(catalog), encoding="utf-8")
        with self.assertRaisesRegex(auditor.AuditError, "must be structured"):
            self.build()

        resource["structured"] = True
        resource["uses"] = ["analysis"]
        self.catalog.write_text(canonical(catalog), encoding="utf-8")
        with self.assertRaisesRegex(auditor.AuditError, "candidate vocabulary"):
            self.build()

    def test_layout_binding_rejects_invalid_policy_payload_and_numeric_only_access(self) -> None:
        lock = json.loads(self.layout_lock.read_text(encoding="utf-8"))
        numeric_access = auditor._layout_binding(lock, "deva-fixture-v1")[1]
        self.assertNotIn("1", numeric_access)

        key = lock["layouts"][0]["layers"]["symbols"]["rows"][0][0]
        key["kind"] = "deva_terminal_zwnj"
        with self.assertRaisesRegex(auditor.AuditError, r"U\+200C"):
            auditor._layout_binding(lock, "deva-fixture-v1")

    def test_current_internal_layout_lock_rebuilds_exactly(self) -> None:
        lock, encoded, verification = auditor._verify_layout_lock(
            ROOT / "layouts" / "internal" / "layouts-v1.lock.json"
        )
        self.assertEqual(lock["layout_count"], 15)
        self.assertEqual(
            verification["compiler"]["sha256"],
            auditor.EXPECTED_LAYOUT_COMPILER_SHA256,
        )
        self.assertEqual(lock["compiler"], verification["compiler"])
        mutated = json.loads(encoded)
        mutated["layouts"][0]["display_name"] = "Mutated"
        mutated_path = self.root / "mutated-layout-lock.json"
        mutated_path.write_text(canonical(mutated), encoding="utf-8")
        with self.assertRaisesRegex(auditor.AuditError, "stale or not canonical"):
            auditor._verify_layout_lock(mutated_path)

    def test_helper_semantics_are_pinned_before_row_audit(self) -> None:
        with (
            mock.patch.object(auditor, "EXPECTED_HELPER_SHA256", "0" * 64),
            self.assertRaisesRegex(auditor.AuditError, "helper SHA-256 mismatch"),
        ):
            auditor._verify_helper_identity()

    def test_layout_compiler_semantics_are_pinned_before_lock_rebuild(self) -> None:
        with (
            mock.patch.object(auditor, "EXPECTED_LAYOUT_COMPILER_SHA256", "0" * 64),
            self.assertRaisesRegex(auditor.AuditError, "compiler SHA-256 mismatch"),
        ):
            auditor._verify_layout_compiler_identity()

    def test_layout_compiler_reference_rejects_path_drift(self) -> None:
        alternate = self.root / "tools" / "alternate-layout-compiler.py"
        alternate.parent.mkdir(exist_ok=True)
        alternate.write_text("# fixture\n", encoding="utf-8")
        reference = {
            "path": "tools/alternate-layout-compiler.py",
            "sha256": hashlib.sha256(alternate.read_bytes()).hexdigest(),
        }
        with (
            mock.patch.object(auditor, "REPOSITORY_ROOT", self.root),
            self.assertRaisesRegex(auditor.AuditError, r"\.path must be"),
        ):
            auditor._verified_reference(
                reference,
                "tools/build_keyboard_layouts.py",
                "layout lock compiler",
            )

    def test_report_is_byte_deterministic(self) -> None:
        first = auditor._canonical_bytes(self.build())
        second = auditor._canonical_bytes(self.build())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
