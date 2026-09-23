from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from tools import audit_western_magar_tsv_contract as auditor


CATALOG_RAW_PATH = (
    "/Users/cdjk/github/llm/nllb-better/data/lexicons_apk/"
    "mrd_nep_lexicon.tsv"
)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def tsv_bytes(rows: list[tuple[str, str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(("mrd_headword", "nepali_gloss", "english_gloss"))
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def scalar_count(inventory: dict[str, object], code_point: str) -> int:
    frequencies = inventory["complete_scalar_frequencies"]
    assert isinstance(frequencies, list)
    return next(
        int(row["count"])
        for row in frequencies
        if isinstance(row, dict) and row["code_point"] == code_point
    )


class WesternMagarTsvContractAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "mrd_nep_lexicon.tsv"
        self.catalog = self.root / "catalog" / "resources.json"
        self.profile_lock = self.root / "catalog" / "internal-profiles.lock.json"
        self.layout_lock = self.root / "layouts" / "internal" / "layouts-v1.lock.json"
        self.output = self.root / "evidence" / "western-magar-tsv-contract.json"
        self.rows = [
            (" क्\u200dख  ", "नेपाली", "alpha\tbeta"),
            ("टाङ्\u200c", "", "e\u0301"),
            ("मगर", " अर्थ ", ""),
        ]
        self.valid_bytes = tsv_bytes(self.rows)
        self.write_inputs(self.valid_bytes, records=len(self.rows))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_inputs(self, encoded: bytes, *, records: int) -> None:
        self.expected_records = records
        self.raw.parent.mkdir(parents=True, exist_ok=True)
        self.raw.write_bytes(encoded)
        self.catalog.parent.mkdir(parents=True, exist_ok=True)
        self.catalog.write_text(
            canonical({
                "packs": [{
                    "id": "mrd",
                    "name": "Western Magar",
                    "iso_639_3": "mrd",
                    "input_methods": [{
                        "id": "mrd-deva-direct",
                        "type": "direct",
                        "source_script": "Deva",
                        "output_script": "Deva",
                        "readiness": "beta",
                        "engine_kind": "layout",
                    }],
                    "resources": [{
                        "id": "mrd-apk",
                        "kind": "lexicon",
                        "path": CATALOG_RAW_PATH,
                        "format": "TSV",
                        "structured": True,
                        "canonical": True,
                        "uses": ["candidate_vocabulary", "spellcheck"],
                        "record_unit": "entries",
                        "records": records,
                        "bytes": len(encoded),
                        "sha256": hashlib.sha256(encoded).hexdigest(),
                    }],
                }],
            }),
            encoding="utf-8",
        )
        self.profile_lock.write_text(
            canonical({
                "profiles": [{
                    "profile_id": "mrd-Deva-NP",
                    "target_id": "mrd",
                    "display_label": "Western Magar",
                    "native_label": "Western Magar",
                    "input_method_id": "mrd-deva-direct",
                    "source_script": "Deva",
                    "output_script": "Deva",
                    "method_type": "direct",
                    "engine_kind": "layout",
                    "lookup_kind": "surface_prefix",
                    "layout_id": "pending-mrd-deva-direct",
                    "layout_revision": None,
                    "layout_source_sha256": None,
                    "pack_artifact": None,
                    "pack_binding": None,
                    "selectable": False,
                    "default_enabled": False,
                }],
            }),
            encoding="utf-8",
        )
        self.layout_lock.parent.mkdir(parents=True, exist_ok=True)
        self.layout_lock.write_text(
            canonical({
                "layouts": [
                    self.layout(
                        "deva-basic",
                        "Deva",
                        "क्खटाङ्मगरनेपालीअर्थ्",
                    ),
                    self.layout(
                        "deva-joiners",
                        "Deva",
                        "क्खटाङ्मगरनेपालीअर्थ्\u200c\u200d",
                    ),
                    self.layout("latin", "Latn", "abcdefghijklmnopqrstuvwxyz"),
                ],
            }),
            encoding="utf-8",
        )

    @staticmethod
    def layout(layout_id: str, script: str, emitted: str) -> dict[str, object]:
        return {
            "layout_id": layout_id,
            "input_script": script,
            "layers": {
                "base": {
                    "rows": [[
                        {
                            "kind": "text",
                            "text": character,
                        }
                        for character in emitted
                    ]],
                },
                "numeric": {
                    "rows": [[{"kind": "action", "text": None}]],
                },
            },
        }

    def pins(self):
        encoded = self.raw.read_bytes()
        return mock.patch.multiple(
            auditor,
            EXPECTED_CATALOG_PATH=self.catalog,
            EXPECTED_PROFILE_LOCK_PATH=self.profile_lock,
            EXPECTED_LAYOUT_LOCK_PATH=self.layout_lock,
            EXPECTED_REMOTE_RAW_PATH=self.raw,
            EXPECTED_CATALOG_RESOURCE_PATH=CATALOG_RAW_PATH,
            EXPECTED_RECORDS=self.expected_records,
            EXPECTED_BYTES=len(encoded),
            EXPECTED_SHA256=hashlib.sha256(encoded).hexdigest(),
            REQUIRED_PYTHON_VERSION=sys.version_info[:2],
            REQUIRED_UNICODE_VERSION=unicodedata.unidata_version,
        )

    def args(self, *, check: bool = False) -> argparse.Namespace:
        return argparse.Namespace(
            resource_catalog=self.catalog,
            profile_lock=self.profile_lock,
            layout_lock=self.layout_lock,
            western_magar_tsv=self.raw,
            output=self.output,
            check=check,
        )

    def build(self) -> dict[str, object]:
        with self.pins():
            return auditor.build_audit(self.args())

    def argv(self) -> list[str]:
        return [
            "--resource-catalog",
            str(self.catalog),
            "--profile-lock",
            str(self.profile_lock),
            "--layout-lock",
            str(self.layout_lock),
            "--western-magar-tsv",
            str(self.raw),
            "--output",
            str(self.output),
        ]

    def test_exact_production_identity_and_runtime_pins_are_checked_in(self) -> None:
        self.assertEqual(auditor.EXPECTED_TARGET_ID, "mrd")
        self.assertEqual(auditor.EXPECTED_TARGET_NAME, "Western Magar")
        self.assertEqual(auditor.EXPECTED_ISO_639_3, "mrd")
        self.assertEqual(auditor.EXPECTED_RESOURCE_ID, "mrd-apk")
        self.assertEqual(auditor.EXPECTED_PROFILE_ID, "mrd-Deva-NP")
        self.assertEqual(auditor.EXPECTED_INPUT_METHOD_ID, "mrd-deva-direct")
        self.assertEqual(auditor.EXPECTED_LOOKUP_KIND, "surface_prefix")
        self.assertEqual(auditor.EXPECTED_HEADER, (
            "mrd_headword",
            "nepali_gloss",
            "english_gloss",
        ))
        self.assertEqual(auditor.EXPECTED_CATALOG_RESOURCE_PATH, CATALOG_RAW_PATH)
        self.assertEqual(
            str(auditor.EXPECTED_REMOTE_RAW_PATH),
            "/home/cdjk/github/llm/nllb-better/data/lexicons_apk/"
            "mrd_nep_lexicon.tsv",
        )
        self.assertEqual(auditor.EXPECTED_RECORDS, 1_264)
        self.assertEqual(auditor.EXPECTED_BYTES, 68_724)
        self.assertEqual(
            auditor.EXPECTED_SHA256,
            "d55d34e4c4d754ee1bbcf3382f3250690e53884020c06305e34bfc1a7948591a",
        )
        self.assertEqual(auditor.REQUIRED_PYTHON_VERSION, (3, 14))
        self.assertEqual(auditor.REQUIRED_UNICODE_VERSION, "16.0.0")

    def test_inventories_every_column_without_selecting_semantics(self) -> None:
        report = self.build()
        contract = report["tsv_contract"]
        self.assertEqual(contract["header"], list(auditor.EXPECTED_HEADER))
        self.assertEqual(contract["data_rows"], 3)
        columns = {
            item["column"]: item["string_values"]
            for item in contract["column_inventories"]
        }
        self.assertEqual(set(columns), set(auditor.EXPECTED_HEADER))

        headword = columns["mrd_headword"]
        self.assertEqual(headword["values"], 3)
        self.assertEqual(headword["null_values"], 0)
        self.assertEqual(headword["empty_values"], 0)
        self.assertEqual(headword["strip_changed_values"], 1)
        self.assertEqual(headword["collapsed_whitespace_changed_values"], 1)
        self.assertEqual(headword["values_with_devanagari_letters"], 3)
        self.assertEqual(headword["values_with_format_characters"], 2)
        self.assertEqual(headword["joiners"]["ZWJ"], {
            "code_point": "U+200D",
            "contexts": {"after_virama_before_letter": 1},
            "occurrences": 1,
            "values": 1,
        })
        self.assertEqual(headword["joiners"]["ZWNJ"], {
            "code_point": "U+200C",
            "contexts": {"after_virama_terminal": 1},
            "occurrences": 1,
            "values": 1,
        })
        self.assertEqual(scalar_count(headword, "U+200C"), 1)
        self.assertEqual(scalar_count(headword, "U+200D"), 1)

        nepali = columns["nepali_gloss"]
        self.assertEqual(nepali["values"], 3)
        self.assertEqual(nepali["empty_values"], 1)
        self.assertEqual(nepali["nonblank_after_strip_values"], 2)
        self.assertEqual(nepali["strip_changed_values"], 1)

        english = columns["english_gloss"]
        self.assertEqual(english["empty_values"], 1)
        self.assertEqual(english["nfc_changed_values"], 1)
        self.assertEqual(english["values_with_control_characters"], 1)
        self.assertEqual(scalar_count(english, "U+0009"), 1)

        self.assertEqual(report["selections"], {
            "candidate_column": None,
            "filter_policy": None,
            "headword_column": None,
            "joiner_policy": None,
            "layout_id": None,
            "normalization_policy": None,
            "pack_id": None,
            "prefix_vectors": [],
            "profile_promotion": False,
        })
        self.assertIn("remain unselected", report["claim_scope"])

    def test_reports_all_devanagari_layouts_as_neutral_scalar_coverage(self) -> None:
        report = self.build()
        self.assertEqual(
            report["layout_evidence"]["deva_layout_ids"],
            ["deva-basic", "deva-joiners"],
        )
        self.assertEqual(
            report["layout_evidence"]["coverage_semantics"],
            "exact non-whitespace scalar emission only",
        )
        columns = {
            item["column"]: item["string_values"]
            for item in report["tsv_contract"]["column_inventories"]
        }
        coverage = {
            item["layout_id"]: item
            for item in columns["mrd_headword"]["layout_scalar_coverage"]
        }
        self.assertEqual(
            coverage["deva-basic"]["missing_distinct_nonwhitespace_scalars"],
            2,
        )
        self.assertEqual(
            coverage["deva-basic"]["missing_nonwhitespace_scalar_occurrences"],
            2,
        )
        self.assertEqual(
            coverage["deva-joiners"]["missing_distinct_nonwhitespace_scalars"],
            0,
        )
        self.assertEqual(coverage["deva-joiners"]["values_fully_scalar_covered"], 3)

    def test_catalog_and_pending_profile_are_bound_exactly(self) -> None:
        report = self.build()
        self.assertEqual(report["profile_binding"]["profile_id"], "mrd-Deva-NP")
        self.assertEqual(
            report["profile_binding"]["input_method_id"],
            "mrd-deva-direct",
        )
        self.assertEqual(report["profile_binding"]["lookup_kind"], "surface_prefix")
        self.assertEqual(
            report["profile_binding"]["layout_id"],
            "pending-mrd-deva-direct",
        )
        self.assertFalse(report["profile_binding"]["selectable"])
        self.assertEqual(report["raw_input"]["resource_id"], "mrd-apk")

    def test_rejects_invalid_tsv_mechanics_before_inventory(self) -> None:
        header = b"mrd_headword\tnepali_gloss\tenglish_gloss"
        cases = (
            (b"\xef\xbb\xbf" + header + b"\na\tb\tc\n", "BOM"),
            (header + b"\r\na\tb\tc\r\n", "LF line endings"),
            (header + b"\na\tb\tc", "LF-terminated"),
            (header + b"\na\tb\x00\tc\n", "NUL"),
            (b"wrong\theader\there\na\tb\tc\n", "header"),
            (header + b"\na\tb\n", "exactly 3 columns"),
            (header + b"\na\tb\tc\td\n", "exactly 3 columns"),
            (header + b"\na\tb\t\xff\n", "valid UTF-8"),
        )
        for encoded, message in cases:
            with self.subTest(message=message):
                self.write_inputs(encoded, records=1)
                with self.pins(), self.assertRaisesRegex(auditor.AuditError, message):
                    auditor.build_audit(self.args())

    def test_rejects_duplicate_catalog_and_profile_keys(self) -> None:
        duplicate_catalog = (
            '{"packs":[{"id":"mrd","id":"mrd"}]}\n'
        )
        self.catalog.write_text(duplicate_catalog, encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "duplicate JSON key"):
            auditor.build_audit(self.args())

        self.write_inputs(self.valid_bytes, records=len(self.rows))
        duplicate_profile = (
            '{"profiles":[{"profile_id":"mrd-Deva-NP",'
            '"profile_id":"mrd-Deva-NP"}]}\n'
        )
        self.profile_lock.write_text(duplicate_profile, encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "duplicate JSON key"):
            auditor.build_audit(self.args())

    def test_rejects_catalog_and_profile_pin_drift(self) -> None:
        catalog_mutations = (
            ("target", "name", "Other", "target name"),
            ("target", "iso_639_3", "zzz", "iso_639_3"),
            ("method", "source_script", "Latn", "source_script"),
            ("method", "readiness", "research", "readiness"),
            ("resource", "path", "/wrong", "path"),
            ("resource", "format", "CSV", "format"),
            ("resource", "structured", 1, "structured"),
            ("resource", "canonical", False, "canonical"),
            ("resource", "records", 4, "records"),
            ("resource", "bytes", 1, "bytes"),
            ("resource", "sha256", "0" * 64, "sha256"),
        )
        for destination, key, bad, message in catalog_mutations:
            with self.subTest(destination=destination, key=key):
                self.write_inputs(self.valid_bytes, records=len(self.rows))
                value = json.loads(self.catalog.read_text(encoding="utf-8"))
                target = value["packs"][0]
                item = {
                    "target": target,
                    "method": target["input_methods"][0],
                    "resource": target["resources"][0],
                }[destination]
                item[key] = bad
                self.catalog.write_text(canonical(value), encoding="utf-8")
                with self.pins(), self.assertRaisesRegex(auditor.AuditError, message):
                    auditor.build_audit(self.args())

        profile_mutations = (
            ("target_id", "other"),
            ("input_method_id", "other"),
            ("lookup_kind", "alias_prefix"),
            ("layout_id", "deva-basic"),
            ("layout_revision", 1),
            ("pack_artifact", {}),
            ("selectable", True),
        )
        for key, bad in profile_mutations:
            with self.subTest(profile_key=key):
                self.write_inputs(self.valid_bytes, records=len(self.rows))
                value = json.loads(self.profile_lock.read_text(encoding="utf-8"))
                value["profiles"][0][key] = bad
                self.profile_lock.write_text(canonical(value), encoding="utf-8")
                with self.pins(), self.assertRaisesRegex(auditor.AuditError, key):
                    auditor.build_audit(self.args())

    def test_rejects_bad_layout_contract_without_selecting_one(self) -> None:
        value = json.loads(self.layout_lock.read_text(encoding="utf-8"))
        value["layouts"].append(value["layouts"][0])
        self.layout_lock.write_text(canonical(value), encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "repeats layout_id"):
            auditor.build_audit(self.args())

        self.write_inputs(self.valid_bytes, records=len(self.rows))
        value = json.loads(self.layout_lock.read_text(encoding="utf-8"))
        value["layouts"] = [self.layout("latin", "Latn", "abc")]
        self.layout_lock.write_text(canonical(value), encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "no Devanagari layouts"):
            auditor.build_audit(self.args())

    def test_rejects_symbolic_raw_and_unpaired_surrogates(self) -> None:
        actual = self.root / "actual.tsv"
        actual.write_bytes(self.valid_bytes)
        self.raw.unlink()
        self.raw.symlink_to(actual)
        with self.pins(), self.assertRaisesRegex(
            auditor.AuditError,
            "regular non-symbolic file",
        ):
            auditor.build_audit(self.args())
        with self.assertRaisesRegex(auditor.AuditError, "Unicode scalar"):
            auditor._validate_unicode_scalars("\ud800", "fixture")

    def test_runtime_contract_fails_closed(self) -> None:
        with mock.patch.object(auditor, "REQUIRED_PYTHON_VERSION", (0, 0)):
            with self.assertRaisesRegex(auditor.AuditError, "requires Python"):
                auditor._validate_runtime()
        with mock.patch.object(auditor, "REQUIRED_UNICODE_VERSION", "0.0.0"):
            with self.assertRaisesRegex(auditor.AuditError, "requires Unicode data"):
                auditor._validate_runtime()

    def test_output_is_canonical_atomic_and_check_is_exact(self) -> None:
        with self.pins(), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(auditor.main(self.argv()), 0)
        first = self.output.read_bytes()
        self.assertEqual(first, auditor._canonical_bytes(json.loads(first)))

        with self.pins(), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(auditor.main(self.argv()), 0)
        self.assertEqual(self.output.read_bytes(), first)

        before_check = self.output.stat().st_mtime_ns
        with self.pins(), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(auditor.main([*self.argv(), "--check"]), 0)
        self.assertEqual(self.output.stat().st_mtime_ns, before_check)
        self.assertEqual(list(self.output.parent.glob(f".{self.output.name}.*.tmp")), [])

        self.output.write_bytes(b"{}\n")
        with (
            self.pins(),
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as raised,
        ):
            auditor.main([*self.argv(), "--check"])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.output.read_bytes(), b"{}\n")

    def test_output_rejects_protected_symbolic_and_special_paths(self) -> None:
        protected = (
            (self.raw, "Western Magar raw TSV"),
            (self.catalog, "resource catalog"),
            (self.profile_lock, "profile lock"),
            (self.layout_lock, "layout lock"),
            (Path(auditor.__file__).resolve(), "auditor source"),
        )
        for path, label in protected:
            with self.subTest(label=label), self.assertRaisesRegex(
                auditor.AuditError,
                label,
            ):
                auditor._validate_output_path(
                    path,
                    self.catalog,
                    self.profile_lock,
                    self.layout_lock,
                    self.raw,
                )

        actual_parent = self.root / "actual-output-parent"
        actual_parent.mkdir()
        symbolic_parent = self.root / "symbolic-output-parent"
        symbolic_parent.symlink_to(actual_parent, target_is_directory=True)
        with self.assertRaisesRegex(auditor.AuditError, "symbolic parents"):
            auditor._validate_output_path(
                symbolic_parent / "report.json",
                self.catalog,
                self.profile_lock,
                self.layout_lock,
                self.raw,
            )

        actual_output = self.root / "actual-report.json"
        actual_output.write_bytes(b"protected target\n")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.symlink_to(actual_output)
        with (
            self.pins(),
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as raised,
        ):
            auditor.main(self.argv())
        self.assertEqual(raised.exception.code, 2)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(actual_output.read_bytes(), b"protected target\n")

        self.output.unlink()
        self.output.mkdir()
        with self.assertRaisesRegex(auditor.AuditError, "regular non-symbolic"):
            auditor._validate_output_path(
                self.output,
                self.catalog,
                self.profile_lock,
                self.layout_lock,
                self.raw,
            )

        self.output.rmdir()
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.output)
            try:
                with self.assertRaisesRegex(auditor.AuditError, "regular non-symbolic"):
                    auditor._validate_output_path(
                        self.output,
                        self.catalog,
                        self.profile_lock,
                        self.layout_lock,
                        self.raw,
                    )
            finally:
                self.output.unlink()


if __name__ == "__main__":
    unittest.main()
