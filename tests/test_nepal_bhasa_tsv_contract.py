from __future__ import annotations

import argparse
import contextlib
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

from tools import audit_nepal_bhasa_tsv_contract as auditor


TRILINGUAL_CATALOG_PATH = (
    "/Users/cdjk/github/llm/nllb-better/data/lexicons_pdf/new_nepali_trilingual.tsv"
)
APK_CATALOG_PATH = (
    "/Users/cdjk/github/llm/nllb-better/data/lexicons_apk/new_apk_eng_lexicon.tsv"
)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def tsv_bytes(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> bytes:
    lines = ["\t".join(header)]
    lines.extend("\t".join(row) for row in rows)
    return ("\n".join(lines) + "\n").encode("utf-8")


class NepalBhasaTsvContractAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.trilingual_raw = self.root / "new_nepali_trilingual.tsv"
        self.apk_raw = self.root / "new_apk_eng_lexicon.tsv"
        self.catalog = self.root / "catalog" / "resources.json"
        self.profile_lock = self.root / "catalog" / "internal-profiles.lock.json"
        self.layout_lock = self.root / "layouts" / "internal" / "layouts-v1.lock.json"
        self.output = self.root / "evidence" / "nepal-bhasa-tsv-contract.json"
        self.trilingual_rows = [
            ("साझा", " नेपाली "),
            ("अर्को; विकल्प", "अर्को"),
            ("क्\u200dख", ""),
            ("", "खाली"),
        ]
        self.apk_rows = [
            ("साझा", "shared", "saajhaa"),
            ("अर्को; विकल्प", "e\u0301; alternate", "arko; vikalpa"),
            ("𑐣𑐾𑐰𑐵", "Newa", "newa"),
            ("", "empty", ""),
        ]
        self.trilingual_bytes = tsv_bytes(("newar", "nepali"), self.trilingual_rows)
        self.apk_bytes = tsv_bytes(
            ("newar", "english", "transliteration"), self.apk_rows
        )
        self.write_inputs()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def layout(layout_id: str, script: str, emitted: str) -> dict[str, object]:
        return {
            "layout_id": layout_id,
            "input_script": script,
            "layers": {
                "base": {
                    "rows": [
                        [{"kind": "text", "text": character} for character in emitted]
                    ],
                },
                "numeric": {"rows": [[{"kind": "action", "text": None}]]},
            },
        }

    @staticmethod
    def profile(
        profile_id: str,
        input_method_id: str,
        source_script: str,
        output_script: str,
        layout_id: str,
    ) -> dict[str, object]:
        lookup_kind, method_type, engine_kind, readiness = {
            "new-Deva-NP": ("surface_prefix", "direct", "layout", "beta"),
            "new-Newa-NP": (
                "surface_prefix",
                "direct",
                "layout",
                "research",
            ),
            "new-Latn-Deva-NP": (
                "alias_prefix",
                "roman_phonetic",
                "alias_decoder",
                "research",
            ),
            "new-Deva-Newa-NP": (
                "conversion",
                "script_conversion",
                "converter",
                "research",
            ),
        }[profile_id]
        return {
            "profile_id": profile_id,
            "target_id": "new",
            "input_method_id": input_method_id,
            "source_script": source_script,
            "output_script": output_script,
            "layout_id": layout_id,
            "layout_revision": None,
            "layout_source_sha256": None,
            "lookup_kind": lookup_kind,
            "method_type": method_type,
            "engine_kind": engine_kind,
            "catalog_readiness": readiness,
            "language_tag": "new-NP",
            "scope": "language",
            "selectable": False,
            "default_enabled": False,
            "pack_artifact": None,
            "pack_binding": None,
            "evidence_ids": [],
            "evidence_artifacts": [],
        }

    def write_inputs(self) -> None:
        self.trilingual_raw.write_bytes(self.trilingual_bytes)
        self.apk_raw.write_bytes(self.apk_bytes)
        self.catalog.parent.mkdir(parents=True, exist_ok=True)
        self.catalog.write_text(
            canonical(
                {
                    "packs": [
                        {
                            "id": "new",
                            "name": "Nepal Bhasa",
                            "iso_639_3": "new",
                            "scope": "language",
                            "scripts": [
                                {
                                    "iso_15924": "Deva",
                                    "name": "Devanagari",
                                    "role": "widely_used",
                                },
                                {
                                    "iso_15924": "Newa",
                                    "name": "Newa/Prachalit Nepal Lipi",
                                    "role": "traditional",
                                },
                            ],
                            "input_methods": [
                                {
                                    "id": "new-deva-direct",
                                    "type": "direct",
                                    "source_script": "Deva",
                                    "output_script": "Deva",
                                    "readiness": "beta",
                                    "engine_kind": "layout",
                                },
                                {
                                    "id": "new-newa-direct",
                                    "type": "direct",
                                    "source_script": "Newa",
                                    "output_script": "Newa",
                                    "readiness": "research",
                                    "engine_kind": "layout",
                                },
                                {
                                    "id": "new-latn-deva",
                                    "type": "roman_phonetic",
                                    "source_script": "Latn",
                                    "output_script": "Deva",
                                    "readiness": "research",
                                    "engine_kind": "alias_decoder",
                                },
                                {
                                    "id": "new-deva-newa",
                                    "type": "script_conversion",
                                    "source_script": "Deva",
                                    "output_script": "Newa",
                                    "readiness": "research",
                                    "engine_kind": "converter",
                                },
                            ],
                            "resources": [
                                {
                                    "id": "new-nepali-trilingual",
                                    "kind": "lexicon",
                                    "path": TRILINGUAL_CATALOG_PATH,
                                    "format": "TSV",
                                    "structured": True,
                                    "quality": "needs_audit",
                                    "records": len(self.trilingual_rows),
                                    "record_unit": "entries",
                                    "bytes": len(self.trilingual_bytes),
                                    "sha256": hashlib.sha256(
                                        self.trilingual_bytes
                                    ).hexdigest(),
                                    "uses": ["candidate_vocabulary", "spellcheck"],
                                    "evidence_type": "attested",
                                },
                                {
                                    "id": "new-apk-english",
                                    "kind": "lexicon",
                                    "path": APK_CATALOG_PATH,
                                    "format": "TSV",
                                    "structured": True,
                                    "quality": "needs_audit",
                                    "records": len(self.apk_rows),
                                    "record_unit": "entries",
                                    "bytes": len(self.apk_bytes),
                                    "sha256": hashlib.sha256(
                                        self.apk_bytes
                                    ).hexdigest(),
                                    "uses": ["candidate_vocabulary", "roman_aliases"],
                                    "evidence_type": "attested",
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        self.profile_lock.write_text(
            canonical(
                {
                    "profiles": [
                        self.profile(
                            "new-Deva-NP",
                            "new-deva-direct",
                            "Deva",
                            "Deva",
                            "pending-new-deva-direct",
                        ),
                        self.profile(
                            "new-Newa-NP",
                            "new-newa-direct",
                            "Newa",
                            "Newa",
                            "pending-new-newa-direct",
                        ),
                        self.profile(
                            "new-Latn-Deva-NP",
                            "new-latn-deva",
                            "Latn",
                            "Deva",
                            "latn-qwerty-us-v1",
                        ),
                        self.profile(
                            "new-Deva-Newa-NP",
                            "new-deva-newa",
                            "Deva",
                            "Newa",
                            "pending-new-deva-newa",
                        ),
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.layout_lock.parent.mkdir(parents=True, exist_ok=True)
        self.layout_lock.write_text(
            canonical(
                {
                    "layouts": [
                        self.layout(
                            "deva-nepal-test-v1",
                            "Deva",
                            "साझाअर्कोविकल्पक्\u200dखनेपाली",
                        ),
                        self.layout(
                            "latin-test-v1", "Latn", "abcdefghijklmnopqrstuvwxyz"
                        ),
                    ],
                }
            ),
            encoding="utf-8",
        )

    def replace_raw(self, resource_id: str, encoded: bytes) -> None:
        raw = {
            "new-nepali-trilingual": self.trilingual_raw,
            "new-apk-english": self.apk_raw,
        }[resource_id]
        raw.write_bytes(encoded)
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        resources = catalog["packs"][0]["resources"]
        resource = next(item for item in resources if item["id"] == resource_id)
        resource["bytes"] = len(encoded)
        resource["sha256"] = hashlib.sha256(encoded).hexdigest()
        self.catalog.write_text(canonical(catalog), encoding="utf-8")

    @contextlib.contextmanager
    def pins(self):
        trilingual_sha = hashlib.sha256(self.trilingual_raw.read_bytes()).hexdigest()
        apk_sha = hashlib.sha256(self.apk_raw.read_bytes()).hexdigest()
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.multiple(
                    auditor,
                    EXPECTED_CATALOG=self.catalog,
                    EXPECTED_PROFILE_LOCK=self.profile_lock,
                    EXPECTED_LAYOUT_LOCK=self.layout_lock,
                    REQUIRED_PYTHON_VERSION=sys.version_info[:2],
                    REQUIRED_UNICODE_VERSION=unicodedata.unidata_version,
                )
            )
            stack.enter_context(
                mock.patch.dict(
                    auditor.TRILINGUAL,
                    {
                        "catalog_path": TRILINGUAL_CATALOG_PATH,
                        "remote_path": self.trilingual_raw,
                        "records": len(self.trilingual_rows),
                        "bytes": len(self.trilingual_raw.read_bytes()),
                        "sha256": trilingual_sha,
                    },
                )
            )
            stack.enter_context(
                mock.patch.dict(
                    auditor.APK,
                    {
                        "catalog_path": APK_CATALOG_PATH,
                        "remote_path": self.apk_raw,
                        "records": len(self.apk_rows),
                        "bytes": len(self.apk_raw.read_bytes()),
                        "sha256": apk_sha,
                    },
                )
            )
            yield

    def args(
        self, *, output: Path | None = None, check: bool = False
    ) -> argparse.Namespace:
        return argparse.Namespace(
            resource_catalog=self.catalog,
            profile_lock=self.profile_lock,
            layout_lock=self.layout_lock,
            trilingual_tsv=self.trilingual_raw,
            apk_tsv=self.apk_raw,
            output=output or self.output,
            check=check,
        )

    def argv(self, *, output: Path | None = None) -> list[str]:
        return [
            "--resource-catalog",
            str(self.catalog),
            "--profile-lock",
            str(self.profile_lock),
            "--layout-lock",
            str(self.layout_lock),
            "--trilingual-tsv",
            str(self.trilingual_raw),
            "--apk-tsv",
            str(self.apk_raw),
            "--output",
            str(output or self.output),
        ]

    def build(self) -> dict[str, object]:
        with self.pins():
            return auditor.build_audit(self.args())

    def test_exact_production_pins_are_checked_in(self) -> None:
        self.assertEqual(auditor.TARGET_ID, "new")
        self.assertEqual(auditor.TARGET_NAME, "Nepal Bhasa")
        self.assertEqual(auditor.TRILINGUAL["resource_id"], "new-nepali-trilingual")
        self.assertEqual(auditor.TRILINGUAL["header"], ("newar", "nepali"))
        self.assertEqual(auditor.TRILINGUAL["records"], 9708)
        self.assertEqual(auditor.TRILINGUAL["bytes"], 543567)
        self.assertEqual(
            auditor.TRILINGUAL["sha256"],
            "4167c21626674fd1e71bd814c6b2bbb33d2d35ab0f5d5bb071b7b43e071d7929",
        )
        self.assertEqual(auditor.APK["resource_id"], "new-apk-english")
        self.assertEqual(auditor.APK["header"], ("newar", "english", "transliteration"))
        self.assertEqual(auditor.APK["records"], 5727)
        self.assertEqual(auditor.APK["bytes"], 404596)
        self.assertEqual(
            auditor.APK["sha256"],
            "470be5aaf526d2dca973044fa5ca9a69b4259854958456145661bd58d4889b41",
        )
        self.assertEqual(auditor.REQUIRED_PYTHON_VERSION, (3, 14))
        self.assertEqual(auditor.REQUIRED_UNICODE_VERSION, "16.0.0")
        self.assertEqual(
            set(auditor.PROFILE_PINS),
            {
                "new-Deva-NP",
                "new-Newa-NP",
                "new-Latn-Deva-NP",
                "new-Deva-Newa-NP",
            },
        )

    def test_sources_remain_separate_and_raw_overlap_is_exact(self) -> None:
        report = self.build()
        contracts = {
            contract["resource_id"]: contract for contract in report["source_contracts"]
        }
        self.assertEqual(
            set(contracts),
            {
                "new-nepali-trilingual",
                "new-apk-english",
            },
        )
        self.assertEqual(
            contracts["new-nepali-trilingual"]["header"],
            ["newar", "nepali"],
        )
        self.assertEqual(
            contracts["new-apk-english"]["header"],
            ["newar", "english", "transliteration"],
        )
        self.assertEqual(contracts["new-nepali-trilingual"]["data_rows"], 4)
        self.assertEqual(contracts["new-apk-english"]["data_rows"], 4)
        overlap = report["cross_source_raw_newar_overlap"]
        self.assertEqual(
            overlap["comparison"],
            "exact raw strings including empty; no normalization or splitting",
        )
        self.assertTrue(overlap["empty_present_in_both"])
        self.assertEqual(overlap["exact_overlap_count"], 3)
        self.assertEqual(
            overlap["exact_overlap_examples"],
            ["", "अर्को; विकल्प", "साझा"],
        )
        self.assertEqual(overlap["exact_nonempty_overlap_count"], 2)
        self.assertEqual(
            overlap["exact_nonempty_overlap_examples"],
            ["अर्को; विकल्प", "साझा"],
        )
        self.assertEqual(overlap["new_nepali_trilingual_unique_count"], 1)
        self.assertEqual(overlap["new_apk_english_unique_count"], 1)
        self.assertEqual(overlap["new_nepali_trilingual_nonempty_unique_count"], 1)
        self.assertEqual(overlap["new_apk_english_nonempty_unique_count"], 1)
        expected_digest = hashlib.sha256(
            json.dumps(
                ["", "अर्को; विकल्प", "साझा"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(overlap["exact_overlap_sha256"], expected_digest)
        for key in (
            "exact_overlap_sha256",
            "exact_nonempty_overlap_sha256",
            "new_apk_english_unique_sha256",
            "new_nepali_trilingual_unique_sha256",
        ):
            self.assertRegex(overlap[key], r"^[0-9a-f]{64}$")
        self.assertEqual(
            [item["resource_id"] for item in report["raw_inputs"]],
            ["new-nepali-trilingual", "new-apk-english"],
        )

    def test_every_column_is_inventoried_without_splitting_or_normalization(
        self,
    ) -> None:
        report = self.build()
        contracts = {
            contract["resource_id"]: contract for contract in report["source_contracts"]
        }
        trilingual_columns = {
            item["column"]: item["string_values"]
            for item in contracts["new-nepali-trilingual"]["column_inventories"]
        }
        apk_columns = {
            item["column"]: item["string_values"]
            for item in contracts["new-apk-english"]["column_inventories"]
        }
        self.assertEqual(set(trilingual_columns), {"newar", "nepali"})
        self.assertEqual(set(apk_columns), {"newar", "english", "transliteration"})
        self.assertEqual(trilingual_columns["newar"]["values"], 4)
        self.assertEqual(trilingual_columns["newar"]["empty_values"], 1)
        self.assertEqual(trilingual_columns["newar"]["semicolon_values"], 1)
        self.assertEqual(
            trilingual_columns["newar"]["semicolon_segment_count_distribution"],
            [{"cells": 1, "segments": 2}],
        )
        self.assertEqual(
            trilingual_columns["newar"]["joiner_contexts"]["values_with_zwj"],
            1,
        )
        self.assertEqual(
            trilingual_columns["nepali"]["leading_or_trailing_whitespace_values"],
            1,
        )
        self.assertEqual(apk_columns["english"]["nfc_changed_values"], 1)
        self.assertEqual(apk_columns["transliteration"]["semicolon_values"], 1)
        self.assertEqual(
            apk_columns["transliteration"]["duplicate_nonempty_value_groups"],
            0,
        )
        self.assertEqual(
            apk_columns["transliteration"]["duplicate_nonempty_extra_occurrences"],
            0,
        )
        self.assertEqual(
            apk_columns["transliteration"]["duplicate_nonempty_values_sha256"],
            hashlib.sha256(b"[]").hexdigest(),
        )
        apk_newar_scripts = apk_columns["newar"]["script_scalar_occurrences"]
        self.assertGreater(apk_newar_scripts["Newa"], 0)
        coverage = contracts["new-apk-english"]["layout_coverage_for_raw_newar_column"][
            0
        ]
        self.assertEqual(coverage["layout_id"], "deva-nepal-test-v1")
        self.assertTrue(
            any(
                scalar.startswith("U+114")
                for scalar in coverage["missing_required_scalars"]
            )
        )
        self.assertIsNone(
            contracts["new-nepali-trilingual"]["transliteration_column_coverage"]
        )
        self.assertEqual(
            contracts["new-apk-english"]["transliteration_column_coverage"],
            {
                "distinct_nonempty_values": 3,
                "empty_values": 1,
                "newar_rows": 4,
                "nonempty_newar_rows": 3,
                "nonempty_newar_rows_with_nonempty_transliteration": 3,
                "nonempty_values": 3,
            },
        )
        for contract in contracts.values():
            self.assertEqual(contract["raw_duplicate_row_groups"], 0)
            self.assertEqual(contract["raw_duplicate_extra_occurrences"], 0)
            self.assertEqual(
                contract["raw_duplicate_rows_sha256"],
                hashlib.sha256(b"[]").hexdigest(),
            )

    def test_duplicate_inventory_reports_full_counts_and_digest(self) -> None:
        inventory = auditor._inventory(["x", "x", "x"])
        duplicates = [{"count": 3, "value": "x"}]
        expected_digest = hashlib.sha256(
            json.dumps(
                duplicates,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(inventory["duplicate_nonempty_value_groups"], 1)
        self.assertEqual(inventory["duplicate_nonempty_extra_occurrences"], 2)
        self.assertEqual(inventory["duplicate_nonempty_values"], duplicates)
        self.assertEqual(inventory["duplicate_nonempty_values_sha256"], expected_digest)

    def test_layout_inventory_counts_every_deva_runtime_text_key_kind(self) -> None:
        emitted = {
            "text": "क",
            "orthographic_word": "‘",
            "intra_word_punctuation": "-",
            "deva_conjunct_joiner": "\u200d",
            "deva_terminal_zwnj": "\u200c",
        }
        self.assertEqual(
            set(emitted),
            auditor.TEXT_KEY_KINDS - {"newa_conjunct_joiner"},
        )
        rows = [[{"kind": kind, "text": text} for kind, text in emitted.items()]]
        layouts = auditor._deva_layouts(
            {
                "layouts": [
                    {
                        "layout_id": "deva-all-text-kinds-v1",
                        "input_script": "Deva",
                        "layers": {"base": {"rows": rows}},
                    }
                ],
            }
        )
        self.assertEqual(
            layouts,
            [
                (
                    "deva-all-text-kinds-v1",
                    {ord(text) for text in emitted.values()},
                )
            ],
        )

    def test_deva_inventory_rejects_newa_only_joiner_kind(self) -> None:
        with self.assertRaisesRegex(
            auditor.AuditError,
            "newa_conjunct_joiner requires input script Newa",
        ):
            auditor._deva_layouts(
                {
                    "layouts": [
                        {
                            "layout_id": "deva-invalid-newa-joiner-v1",
                            "input_script": "Deva",
                            "layers": {
                                "base": {
                                    "rows": [
                                        [
                                            {
                                                "kind": "newa_conjunct_joiner",
                                                "text": "\u200d",
                                            }
                                        ]
                                    ]
                                }
                            },
                        }
                    ],
                }
            )

    def test_all_profiles_and_all_product_decisions_remain_unselected(self) -> None:
        report = self.build()
        bindings = {
            profile["profile_id"]: profile
            for profile in report["profile_bindings"]["profiles"]
        }
        self.assertEqual(set(bindings), set(auditor.PROFILE_PINS))
        for binding in bindings.values():
            self.assertFalse(binding["selectable"])
            self.assertFalse(binding["default_enabled"])
            self.assertIsNone(binding["pack_artifact"])
            self.assertIsNone(binding["pack_binding"])
            self.assertEqual(binding["evidence_ids"], [])
            self.assertEqual(binding["evidence_artifacts"], [])
        self.assertEqual(
            report["selections"],
            {
                "alternative_splitting_policy": None,
                "candidate_columns": {
                    "new-nepali-trilingual": None,
                    "new-apk-english": None,
                },
                "candidate_resource_ids": [],
                "conversion_policy": None,
                "filter_policy": None,
                "joiner_policy": None,
                "layout_ids": [],
                "normalization_policy": None,
                "pack_id": None,
                "prefix_vectors": [],
                "profile_promotions": {
                    profile_id: False for profile_id in auditor.PROFILE_PINS
                },
                "roman_alias_policy": None,
            },
        )
        self.assertIn("No rows were merged", report["claim_scope"])
        self.assertIn("remain unselected", report["claim_scope"])

    def test_rejects_catalog_profile_and_layout_binding_drift(self) -> None:
        catalog_cases = (
            ("name", "Other", "identity drifted"),
            ("iso_639_3", "zzz", "identity drifted"),
        )
        for key, bad, message in catalog_cases:
            with self.subTest(catalog_key=key):
                self.write_inputs()
                value = json.loads(self.catalog.read_text(encoding="utf-8"))
                value["packs"][0][key] = bad
                self.catalog.write_text(canonical(value), encoding="utf-8")
                with self.pins(), self.assertRaisesRegex(auditor.AuditError, message):
                    auditor.build_audit(self.args())

        self.write_inputs()
        value = json.loads(self.catalog.read_text(encoding="utf-8"))
        value["packs"][0]["resources"][0]["uses"] = ["spellcheck"]
        self.catalog.write_text(canonical(value), encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "uses drifted"):
            auditor.build_audit(self.args())

        self.write_inputs()
        value = json.loads(self.catalog.read_text(encoding="utf-8"))
        value["packs"][0]["scripts"][0]["role"] = "other"
        self.catalog.write_text(canonical(value), encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "script Deva"):
            auditor.build_audit(self.args())

        self.write_inputs()
        value = json.loads(self.catalog.read_text(encoding="utf-8"))
        value["packs"][0]["input_methods"][0]["readiness"] = "research"
        self.catalog.write_text(canonical(value), encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "readiness"):
            auditor.build_audit(self.args())

        for key, bad in (
            ("selectable", True),
            ("default_enabled", True),
            ("pack_artifact", {}),
            ("pack_binding", {}),
            ("layout_id", "selected-layout"),
        ):
            with self.subTest(profile_key=key):
                self.write_inputs()
                value = json.loads(self.profile_lock.read_text(encoding="utf-8"))
                value["profiles"][0][key] = bad
                self.profile_lock.write_text(canonical(value), encoding="utf-8")
                with self.pins(), self.assertRaisesRegex(auditor.AuditError, key):
                    auditor.build_audit(self.args())

        self.write_inputs()
        value = json.loads(self.profile_lock.read_text(encoding="utf-8"))
        value["profiles"][1]["evidence_ids"] = ["promotion"]
        self.profile_lock.write_text(canonical(value), encoding="utf-8")
        with (
            self.pins(),
            self.assertRaisesRegex(auditor.AuditError, "promotion evidence"),
        ):
            auditor.build_audit(self.args())

        self.write_inputs()
        value = json.loads(self.profile_lock.read_text(encoding="utf-8"))
        extra_profile = dict(value["profiles"][0])
        extra_profile["profile_id"] = "new-extra-NP"
        value["profiles"].append(extra_profile)
        self.profile_lock.write_text(canonical(value), encoding="utf-8")
        with (
            self.pins(),
            self.assertRaisesRegex(
                auditor.AuditError,
                "profile membership drifted",
            ),
        ):
            auditor.build_audit(self.args())

        self.write_inputs()
        value = json.loads(self.layout_lock.read_text(encoding="utf-8"))
        value["layouts"] = [self.layout("latin-only", "Latn", "abc")]
        self.layout_lock.write_text(canonical(value), encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "no Devanagari"):
            auditor.build_audit(self.args())

    def test_each_tsv_fails_closed_on_mechanical_contract_drift(self) -> None:
        cases = (
            (b"\xef\xbb\xbfnewar\tnepali\na\tb\n", "BOM"),
            (b"newar\tnepali\r\na\tb\r\n", "LF line endings"),
            (b"newar\tnepali\na\tb", "LF-terminated"),
            (b"wrong\tnepali\na\tb\n", "header"),
            (b"newar\tnepali\na\n", "exactly 2 columns"),
            (b"newar\tnepali\na\tb\tc\n", "exactly 2 columns"),
            (b"newar\tnepali\na\t\xff\n", "valid UTF-8"),
            (b"newar\tnepali\na\x00\tb\n", r"U\+0000"),
            (b"newar\tnepali\na\tb\n", "row count must be 4"),
        )
        for encoded, message in cases:
            with self.subTest(source="trilingual", message=message):
                self.write_inputs()
                self.replace_raw("new-nepali-trilingual", encoded)
                with self.pins(), self.assertRaisesRegex(auditor.AuditError, message):
                    auditor.build_audit(self.args())

        apk_cases = (
            (b"newar\tenglish\ttransliteration\na\tb\n", "exactly 3 columns"),
            (b"newar\tenglish\twrong\na\tb\tc\n", "header"),
        )
        for encoded, message in apk_cases:
            with self.subTest(source="apk", message=message):
                self.write_inputs()
                self.replace_raw("new-apk-english", encoded)
                with self.pins(), self.assertRaisesRegex(auditor.AuditError, message):
                    auditor.build_audit(self.args())

    def test_duplicate_json_keys_runtime_and_raw_path_pins_fail_closed(self) -> None:
        self.catalog.write_text(
            '{"packs":[],"packs":[]}\n',
            encoding="utf-8",
        )
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "duplicate key"):
            auditor.build_audit(self.args())

        self.write_inputs()
        with mock.patch.object(auditor, "REQUIRED_PYTHON_VERSION", (0, 0)):
            with self.assertRaisesRegex(auditor.AuditError, "requires Python"):
                auditor._validate_runtime()
        with mock.patch.object(auditor, "REQUIRED_UNICODE_VERSION", "0.0.0"):
            with self.assertRaisesRegex(auditor.AuditError, "requires Unicode data"):
                auditor._validate_runtime()

        wrong = self.root / "wrong-trilingual.tsv"
        wrong.write_bytes(self.trilingual_bytes)
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "canonical path"):
            args = self.args()
            args.trilingual_tsv = wrong
            auditor.build_audit(args)

        noncanonical = self.root / "unused" / ".." / self.trilingual_raw.name
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "canonical path"):
            args = self.args()
            args.trilingual_tsv = noncanonical
            auditor.build_audit(args)

        self.write_inputs()
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "byte count"):
            self.trilingual_raw.write_bytes(self.trilingual_bytes + b"x")
            auditor.build_audit(self.args())

        self.write_inputs()
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "SHA-256"):
            mutated = bytearray(self.trilingual_bytes)
            mutated[-2] = ord("X")
            self.trilingual_raw.write_bytes(mutated)
            auditor.build_audit(self.args())

        self.write_inputs()
        actual = self.root / "actual-trilingual.tsv"
        actual.write_bytes(self.trilingual_bytes)
        self.trilingual_raw.unlink()
        self.trilingual_raw.symlink_to(actual)
        with self.pins(), self.assertRaisesRegex(auditor.AuditError, "canonical path"):
            auditor.build_audit(self.args())

    def test_output_is_canonical_deterministic_and_check_is_exact(self) -> None:
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
        self.assertEqual(
            list(self.output.parent.glob(f".{self.output.name}.*.tmp")), []
        )

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

    def test_output_rejects_protected_symbolic_hardlinked_and_special_paths(
        self,
    ) -> None:
        for protected in (
            self.catalog,
            self.profile_lock,
            self.layout_lock,
            self.trilingual_raw,
            self.apk_raw,
            Path(auditor.__file__).resolve(),
        ):
            with (
                self.subTest(protected=protected),
                self.assertRaisesRegex(auditor.AuditError, "protected input"),
            ):
                auditor._validate_output(self.args(output=protected))

        actual_parent = self.root / "actual-parent"
        actual_parent.mkdir()
        symbolic_parent = self.root / "symbolic-parent"
        symbolic_parent.symlink_to(actual_parent, target_is_directory=True)
        with self.assertRaisesRegex(auditor.AuditError, "symbolic parents"):
            auditor._validate_output(self.args(output=symbolic_parent / "report.json"))

        target = self.root / "existing.json"
        target.write_bytes(b"protected\n")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.symlink_to(target)
        with self.assertRaisesRegex(auditor.AuditError, "symbolic parents"):
            auditor._validate_output(self.args())
        self.assertEqual(target.read_bytes(), b"protected\n")

        self.output.unlink()
        os.link(self.trilingual_raw, self.output)
        with self.assertRaisesRegex(auditor.AuditError, "hard-link"):
            auditor._validate_output(self.args())

        self.output.unlink()
        self.output.mkdir()
        with self.assertRaisesRegex(auditor.AuditError, "regular non-symbolic"):
            auditor._validate_output(self.args())


if __name__ == "__main__":
    unittest.main()
