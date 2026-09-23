from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from tools import audit_bantawa_jsonl_contract as auditor


CATALOG_RAW_PATH = (
    "/Users/cdjk/github/llm/rai-speech-toolkit/dialects/central/"
    "bantawa/dict/bantawa-english.dict.jsonl"
)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def scalar_count(inventory: dict[str, object], code_point: str) -> int:
    rows = inventory["complete_scalar_frequencies"]
    assert isinstance(rows, list)
    return next(
        int(row["count"])
        for row in rows
        if isinstance(row, dict) and row["code_point"] == code_point
    )


class BantawaJsonlContractAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "bantawa-english.dict.jsonl"
        self.catalog = self.root / "catalog" / "resources.json"
        self.output = self.root / "evidence" / "bantawa-jsonl-contract.json"
        self.rows = [
            {
                "native": " क्\u200dख  ",
                "english": "alpha\tbeta",
                "aliases": ["ए", "A", 7],
                "meta": None,
                "flag": True,
            },
            {
                "native": "e\u0301",
                "english": "",
                "aliases": [],
                "meta": {"source": "fixture"},
                "flag": False,
            },
            {
                "english": "gamma",
                "native": "टाङ्\u200c",
                "aliases": ["Ω", "A"],
                "meta": 3,
                "flag": 1.5,
            },
        ]
        self.valid_bytes = "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in self.rows
        ).encode("utf-8")
        self.write_input(self.valid_bytes, records=len(self.rows))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_input(self, encoded: bytes, *, records: int) -> None:
        self.expected_records = records
        self.raw.parent.mkdir(parents=True, exist_ok=True)
        self.raw.write_bytes(encoded)
        self.catalog.parent.mkdir(parents=True, exist_ok=True)
        self.catalog.write_text(
            canonical({
                "packs": [{
                    "id": "bap",
                    "name": "Bantawa",
                    "iso_639_3": "bap",
                    "resources": [{
                        "id": "bap-dictionary",
                        "kind": "lexicon",
                        "path": CATALOG_RAW_PATH,
                        "format": "JSONL",
                        "structured": True,
                        "canonical": True,
                        "uses": ["candidate_vocabulary"],
                        "record_unit": "entries",
                        "records": records,
                        "bytes": len(encoded),
                        "sha256": hashlib.sha256(encoded).hexdigest(),
                    }],
                }],
            }),
            encoding="utf-8",
        )

    def pins(self):
        encoded = self.raw.read_bytes()
        return mock.patch.multiple(
            auditor,
            EXPECTED_CATALOG_PATH=self.catalog,
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
            bantawa_jsonl=self.raw,
            output=self.output,
            check=check,
        )

    def build(self) -> dict[str, object]:
        with self.pins():
            return auditor.build_audit(self.args())

    def test_exact_production_identity_and_runtime_pins_are_checked_in(self) -> None:
        self.assertEqual(auditor.EXPECTED_TARGET_ID, "bap")
        self.assertEqual(auditor.EXPECTED_TARGET_NAME, "Bantawa")
        self.assertEqual(auditor.EXPECTED_ISO_639_3, "bap")
        self.assertEqual(auditor.EXPECTED_RESOURCE_ID, "bap-dictionary")
        self.assertEqual(auditor.EXPECTED_CATALOG_RESOURCE_PATH, CATALOG_RAW_PATH)
        self.assertEqual(
            str(auditor.EXPECTED_REMOTE_RAW_PATH),
            "/home/cdjk/github/llm/rai-speech-toolkit/dialects/central/"
            "bantawa/dict/bantawa-english.dict.jsonl",
        )
        self.assertEqual(auditor.EXPECTED_RECORDS, 2_040)
        self.assertEqual(auditor.EXPECTED_BYTES, 360_086)
        self.assertEqual(
            auditor.EXPECTED_SHA256,
            "a69917c00e7a8587f4a38458faf89c95fc9e5ac9cbe6cfb612383438bdf5ae12",
        )
        self.assertEqual(auditor.REQUIRED_PYTHON_VERSION, (3, 14))
        self.assertEqual(auditor.REQUIRED_UNICODE_VERSION, "16.0.0")

    def test_aggregates_ordered_signatures_and_independent_field_types(self) -> None:
        contract = self.build()["jsonl_contract"]
        self.assertEqual(contract["rows"], 3)
        self.assertEqual(contract["ordered_field_signatures"], [
            {
                "count": 1,
                "fields": ["english", "native", "aliases", "meta", "flag"],
            },
            {
                "count": 2,
                "fields": ["native", "english", "aliases", "meta", "flag"],
            },
        ])
        type_signatures = contract["ordered_field_type_signatures"]
        self.assertEqual(type_signatures, [
            {
                "count": 1,
                "fields": [
                    {"field": "english", "json_type": "string"},
                    {"field": "native", "json_type": "string"},
                    {"field": "aliases", "json_type": "array"},
                    {"field": "meta", "json_type": "number"},
                    {"field": "flag", "json_type": "number"},
                ],
            },
            {
                "count": 1,
                "fields": [
                    {"field": "native", "json_type": "string"},
                    {"field": "english", "json_type": "string"},
                    {"field": "aliases", "json_type": "array"},
                    {"field": "meta", "json_type": "null"},
                    {"field": "flag", "json_type": "boolean"},
                ],
            },
            {
                "count": 1,
                "fields": [
                    {"field": "native", "json_type": "string"},
                    {"field": "english", "json_type": "string"},
                    {"field": "aliases", "json_type": "array"},
                    {"field": "meta", "json_type": "object"},
                    {"field": "flag", "json_type": "boolean"},
                ],
            },
        ])

        fields = {row["field"]: row for row in contract["field_inventories"]}
        self.assertEqual(set(fields), {"aliases", "english", "flag", "meta", "native"})
        self.assertEqual(fields["aliases"]["json_types"], {"array": 3})
        self.assertEqual(
            fields["aliases"]["array_element_types"],
            {"number": 1, "string": 4},
        )
        self.assertEqual(fields["aliases"]["empty_arrays"], 1)
        self.assertEqual(fields["aliases"]["distinct_arrays"], 3)
        self.assertEqual(
            fields["aliases"]["array_lengths"],
            [
                {"count": 1, "length": 0},
                {"count": 1, "length": 2},
                {"count": 1, "length": 3},
            ],
        )
        self.assertEqual(fields["flag"]["json_types"], {"boolean": 2, "number": 1})
        self.assertEqual(
            fields["meta"]["json_types"],
            {"null": 1, "number": 1, "object": 1},
        )
        for field in fields.values():
            self.assertEqual(field["rows_present"], 3)
            self.assertEqual(field["rows_missing"], 0)

    def test_inventories_string_and_string_array_values_without_selection(self) -> None:
        report = self.build()
        contract = report["jsonl_contract"]
        fields = {row["field"]: row for row in contract["field_inventories"]}

        native = fields["native"]["direct_string_values"]
        self.assertEqual(native["values"], 3)
        self.assertEqual(native["distinct_values"], 3)
        self.assertEqual(native["nonempty_values"], 3)
        self.assertEqual(native["nfc_changed_values"], 1)
        self.assertEqual(native["strip_changed_values"], 1)
        self.assertEqual(native["collapsed_whitespace_changed_values"], 1)
        self.assertEqual(native["values_with_devanagari_letters"], 2)
        self.assertEqual(native["values_with_latin_letters"], 1)
        self.assertEqual(native["values_with_other_letters"], 0)
        self.assertEqual(native["values_with_format_characters"], 2)
        self.assertEqual(native["values_with_control_characters"], 0)
        self.assertEqual(native["joiners"]["ZWJ"], {
            "code_point": "U+200D",
            "contexts": {"after_virama_before_letter": 1},
            "occurrences": 1,
            "values": 1,
        })
        self.assertEqual(native["joiners"]["ZWNJ"], {
            "code_point": "U+200C",
            "contexts": {"after_virama_terminal": 1},
            "occurrences": 1,
            "values": 1,
        })
        self.assertEqual(scalar_count(native, "U+200C"), 1)
        self.assertEqual(scalar_count(native, "U+200D"), 1)
        self.assertEqual(len(native["examples"]), 3)

        aliases = fields["aliases"]["array_string_elements"]
        self.assertEqual(aliases["values"], 4)
        self.assertEqual(aliases["distinct_values"], 3)
        self.assertEqual(aliases["values_with_devanagari_letters"], 1)
        self.assertEqual(aliases["values_with_latin_letters"], 2)
        self.assertEqual(aliases["values_with_other_letters"], 1)
        self.assertEqual(scalar_count(aliases, "U+0041"), 2)
        self.assertEqual(scalar_count(aliases, "U+03A9"), 1)

        english = fields["english"]["direct_string_values"]
        self.assertEqual(english["values"], 3)
        self.assertEqual(english["nonempty_values"], 2)
        self.assertEqual(english["nonblank_after_strip_values"], 2)
        self.assertEqual(english["values_with_control_characters"], 1)
        self.assertEqual(english["collapsed_whitespace_changed_values"], 1)
        self.assertEqual(scalar_count(english, "U+0009"), 1)
        self.assertEqual(
            english["control_scalar_frequencies"][0]["code_point"],
            "U+0009",
        )

        self.assertEqual(report["selections"], {
            "candidate_field": None,
            "filter_policy": None,
            "headword_field": None,
            "joiner_policy": None,
            "layout_id": None,
            "normalization_policy": None,
            "pack_id": None,
            "prefix_vectors": [],
            "profile_promotion": False,
        })
        self.assertIn("remain unselected", report["claim_scope"])

    def test_rejects_invalid_jsonl_mechanics_before_inventory(self) -> None:
        cases = (
            (b"\xef\xbb\xbf{}\n", "BOM"),
            (b"{}\r\n", "LF line endings"),
            (b"{}", "LF-terminated"),
            (b"{}\n\n", "blank"),
            (b" \t \n", "blank"),
            (b"\xff\n", "valid UTF-8"),
            (b"[]\n", "must be an object"),
            (b'{"value":NaN}\n', "non-finite"),
            (b'{"value":1e999}\n', "non-finite"),
        )
        for encoded, message in cases:
            with self.subTest(message=message):
                self.write_input(encoded, records=1)
                with self.pins(), self.assertRaisesRegex(auditor.AuditError, message):
                    auditor.build_audit(self.args())

    def test_rejects_duplicate_keys_at_every_object_depth(self) -> None:
        cases = (
            b'{"native":"a","native":"b"}\n',
            b'{"native":"a","meta":{"x":1,"x":2}}\n',
        )
        for encoded in cases:
            with self.subTest(encoded=encoded):
                self.write_input(encoded, records=1)
                with self.pins(), self.assertRaisesRegex(
                    auditor.AuditError,
                    "duplicate JSON key",
                ):
                    auditor.build_audit(self.args())

    def test_rejects_unpaired_surrogates_recursively(self) -> None:
        cases = (
            b'{"native":"\\ud800"}\n',
            b'{"meta":{"value":"\\udfff"}}\n',
            b'{"items":["ok", "\\ud800"]}\n',
            b'{"\\udfff":"value"}\n',
        )
        for encoded in cases:
            with self.subTest(encoded=encoded):
                self.write_input(encoded, records=1)
                with self.pins(), self.assertRaisesRegex(
                    auditor.AuditError,
                    "Unicode scalar",
                ):
                    auditor.build_audit(self.args())

    def test_scalar_labels_use_minimum_four_hex_digits(self) -> None:
        self.assertEqual(auditor._scalar_label(0x41), "U+0041")
        self.assertEqual(auditor._scalar_label(0x11B00), "U+11B00")
        self.assertEqual(auditor._scalar_label(0x1F600), "U+1F600")

    def test_rejects_symbolic_raw_input(self) -> None:
        actual = self.root / "actual.jsonl"
        actual.write_bytes(self.valid_bytes)
        self.raw.unlink()
        self.raw.symlink_to(actual)
        with self.pins(), self.assertRaisesRegex(
            auditor.AuditError,
            "regular non-symbolic file",
        ):
            auditor.build_audit(self.args())

    def test_catalog_binding_rejects_any_exact_pin_drift(self) -> None:
        mutations = (
            ("target.name", "name", "Other", "target name"),
            ("target.iso", "iso_639_3", "zzz", "ISO 639-3"),
            ("resource.kind", "kind", "corpus", "kind"),
            ("resource.path", "path", "/wrong", "path"),
            ("resource.format", "format", "JSON", "format"),
            ("resource.structured", "structured", False, "structured"),
            ("resource.structured-type", "structured", 1, "structured"),
            ("resource.canonical", "canonical", False, "canonical"),
            ("resource.canonical-type", "canonical", 1, "canonical"),
            ("resource.unit", "record_unit", "lines", "record_unit"),
            ("resource.records", "records", 2, "records"),
            ("resource.bytes", "bytes", 1, "bytes"),
            ("resource.sha", "sha256", "0" * 64, "sha256"),
        )
        for label, key, bad_value, message in mutations:
            with self.subTest(label=label):
                self.write_input(self.valid_bytes, records=len(self.rows))
                catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
                target = catalog["packs"][0]
                destination = target if label.startswith("target.") else target["resources"][0]
                destination[key] = bad_value
                self.catalog.write_text(canonical(catalog), encoding="utf-8")
                with self.pins(), self.assertRaisesRegex(auditor.AuditError, message):
                    auditor.build_audit(self.args())

        self.write_input(self.valid_bytes, records=len(self.rows))
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["packs"][0]["resources"][0]["id"] = "other"
        self.catalog.write_text(canonical(catalog), encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(
            auditor.AuditError,
            "exactly one bap-dictionary",
        ):
            auditor.build_audit(self.args())

        self.write_input(self.valid_bytes, records=len(self.rows))
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["packs"][0]["id"] = "other"
        self.catalog.write_text(canonical(catalog), encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(
            auditor.AuditError,
            "exactly one bap target",
        ):
            auditor.build_audit(self.args())

    def test_runtime_contract_fails_closed(self) -> None:
        with mock.patch.object(auditor, "REQUIRED_PYTHON_VERSION", (0, 0)):
            with self.assertRaisesRegex(auditor.AuditError, "requires Python"):
                auditor._validate_runtime()
        with mock.patch.object(auditor, "REQUIRED_UNICODE_VERSION", "0.0.0"):
            with self.assertRaisesRegex(auditor.AuditError, "requires Unicode data"):
                auditor._validate_runtime()

    def test_output_is_canonical_atomic_and_check_is_exact(self) -> None:
        argv = [
            "--resource-catalog",
            str(self.catalog),
            "--bantawa-jsonl",
            str(self.raw),
            "--output",
            str(self.output),
        ]
        with self.pins(), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(auditor.main(argv), 0)
        first = self.output.read_bytes()
        self.assertEqual(first, auditor._canonical_bytes(json.loads(first)))

        with self.pins(), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(auditor.main(argv), 0)
        self.assertEqual(self.output.read_bytes(), first)

        before_check = self.output.stat().st_mtime_ns
        with self.pins(), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(auditor.main([*argv, "--check"]), 0)
        self.assertEqual(self.output.read_bytes(), first)
        self.assertEqual(self.output.stat().st_mtime_ns, before_check)
        self.assertEqual(list(self.output.parent.glob(f".{self.output.name}.*.tmp")), [])

        self.output.write_bytes(b"{}\n")
        with (
            self.pins(),
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as raised,
        ):
            auditor.main([*argv, "--check"])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.output.read_bytes(), b"{}\n")

    def test_output_rejects_source_overlap_and_symbolic_parent(self) -> None:
        protected = (
            (self.raw, "Bantawa raw JSONL"),
            (self.catalog, "resource catalog"),
            (Path(auditor.__file__).resolve(), "auditor source"),
        )
        for path, label in protected:
            with self.subTest(label=label), self.assertRaisesRegex(
                auditor.AuditError,
                label,
            ):
                auditor._validate_output_path(path, self.catalog, self.raw)

        actual_parent = self.root / "actual-output-parent"
        actual_parent.mkdir()
        symbolic_parent = self.root / "symbolic-output-parent"
        symbolic_parent.symlink_to(actual_parent, target_is_directory=True)
        with self.assertRaisesRegex(auditor.AuditError, "symbolic parents"):
            auditor._validate_output_path(
                symbolic_parent / "report.json",
                self.catalog,
                self.raw,
            )

        actual_output = self.root / "actual-report.json"
        actual_output.write_bytes(b"protected target\n")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.symlink_to(actual_output)
        argv = [
            "--resource-catalog",
            str(self.catalog),
            "--bantawa-jsonl",
            str(self.raw),
            "--output",
            str(self.output),
        ]
        with (
            self.pins(),
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as raised,
        ):
            auditor.main(argv)
        self.assertEqual(raised.exception.code, 2)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(actual_output.read_bytes(), b"protected target\n")


if __name__ == "__main__":
    unittest.main()
