from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools import finalize_internal_pack_milestone_v1 as finalizer


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FinalizeInternalPackMilestoneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_canonical_sunuwar_spec_and_layout_contract(self) -> None:
        spec_path = (
            finalizer.REPOSITORY_ROOT
            / "catalog/internal-pack-milestones/suz-Deva-NP-v0.json"
        )
        spec, encoded = finalizer._validate_spec(spec_path)

        self.assertEqual(encoded, finalizer._canonical_bytes(spec))
        self.assertEqual(spec["pack"]["pack_id"], "suz-Deva-NP")
        self.assertEqual(
            finalizer._verify_layout(spec),
            {
                "layout_id": "deva-nepal-extended-v1",
                "revision": 1,
                "source_path": "layouts/internal/src/deva-nepal-extended-v1.json",
                "source_sha256": "ce8f8420c2d685e76a8ac44e8ba9bb44f73d7f17bcfa78e9617863e993734619",
            },
        )

    def test_canonical_dhimal_spec_and_layout_contract(self) -> None:
        spec_path = (
            finalizer.REPOSITORY_ROOT
            / "catalog/internal-pack-milestones/dhi-Deva-NP-v0.json"
        )
        spec, encoded = finalizer._validate_spec(spec_path)

        self.assertEqual(encoded, finalizer._canonical_bytes(spec))
        self.assertEqual(spec["pack"]["pack_id"], "dhi-Deva-NP")
        self.assertEqual(
            finalizer._verify_layout(spec),
            {
                "layout_id": "deva-nepal-dhimal-v1",
                "revision": 1,
                "source_path": "layouts/internal/src/deva-nepal-dhimal-v1.json",
                "source_sha256": "2685cf503604390e5a049ce8732152d8c739a41626e7929f3acb6263aa63ca68",
            },
        )

    def test_canonical_western_tamang_spec_and_layout_contract(self) -> None:
        spec_path = (
            finalizer.REPOSITORY_ROOT
            / "catalog/internal-pack-milestones/tdg-Deva-NP-v0.json"
        )
        spec, encoded = finalizer._validate_spec(spec_path)

        self.assertEqual(encoded, finalizer._canonical_bytes(spec))
        self.assertEqual(spec["pack"]["pack_id"], "tdg-Deva-NP")
        self.assertEqual(
            finalizer._verify_layout(spec),
            {
                "layout_id": "deva-nepal-western-tamang-v1",
                "revision": 1,
                "source_path": (
                    "layouts/internal/src/deva-nepal-western-tamang-v1.json"
                ),
                "source_sha256": (
                    "fe8a19fda41baf9df799e401f6134bd5308e5258814ff87fc4d6ae81760a0fd8"
                ),
            },
        )

    def test_canonical_mid_eastern_tharu_spec_and_layout_contract(self) -> None:
        spec_path = (
            finalizer.REPOSITORY_ROOT
            / "catalog/internal-pack-milestones/thq-Deva-NP-v0.json"
        )
        spec, encoded = finalizer._validate_spec(spec_path)

        self.assertEqual(encoded, finalizer._canonical_bytes(spec))
        self.assertEqual(spec["pack"]["pack_id"], "thq-Deva-NP")
        self.assertEqual(
            [operation["kind"] for operation in spec["layout"]["operations"]],
            [
                "insert_row_before_actions",
                "insert_row_before_actions",
                "insert_row_before_actions",
                "replace_key",
                "replace_key",
            ],
        )
        self.assertEqual(
            finalizer._verify_layout(spec),
            {
                "layout_id": "deva-nepal-mid-eastern-tharu-v1",
                "revision": 1,
                "source_path": "layouts/internal/src/deva-nepal-mid-eastern-tharu-v1.json",
                "source_sha256": "db316037bebc211c8b76bd9219f0dcf43ad8ad7639c291cb6e608fad24d210b4",
            },
        )

    def test_canonical_lohorung_spec_and_layout_contract(self) -> None:
        spec_path = (
            finalizer.REPOSITORY_ROOT
            / "catalog/internal-pack-milestones/lbr-Deva-NP-v0.json"
        )
        spec, encoded = finalizer._validate_spec(spec_path)

        self.assertEqual(encoded, finalizer._canonical_bytes(spec))
        self.assertEqual(spec["pack"]["pack_id"], "lbr-Deva-NP")
        self.assertEqual(spec["adapter"]["input_argument"], "sil_apk_jsonl")
        self.assertEqual(
            finalizer._verify_layout(spec),
            {
                "layout_id": "deva-nepal-lohorung-v1",
                "revision": 1,
                "source_path": "layouts/internal/src/deva-nepal-lohorung-v1.json",
                "source_sha256": (
                    "bc76bd393b072b3ad71a4df375e57454fd1cc1ef6f41f8e15a0e6ce57e96ae6e"
                ),
            },
        )

    def test_canonical_yakkha_v2_spec_and_layout_contract(self) -> None:
        spec_path = (
            finalizer.REPOSITORY_ROOT
            / "catalog/internal-pack-milestones/ybh-Deva-NP-v0.json"
        )
        spec, encoded = finalizer._validate_spec(spec_path)

        self.assertEqual(encoded, finalizer._canonical_bytes(spec))
        self.assertEqual(spec["spec_version"], 2)
        self.assertEqual(spec["pack"]["pack_id"], "ybh-Deva-NP")
        self.assertEqual(spec["adapter"]["input_argument"], "sil_apk_jsonl")
        self.assertEqual(
            [operation["kind"] for operation in spec["layout"]["operations"]],
            [
                "insert_row_before_actions",
                "insert_row_before_actions",
                "append_keys_to_row",
                "replace_key",
                "replace_key",
            ],
        )
        self.assertEqual(
            finalizer._verify_layout(spec),
            {
                "layout_id": "deva-nepal-yakkha-v1",
                "revision": 1,
                "source_path": "layouts/internal/src/deva-nepal-yakkha-v1.json",
                "source_sha256": (
                    "6bc33cb0bf5d2582a609e0e4ca987d099763f7b87af3aa76013c02faca7562b4"
                ),
            },
        )

    def test_canonical_nepal_bhasa_v3_spec_and_layout_contract(self) -> None:
        spec_path = (
            finalizer.REPOSITORY_ROOT
            / "catalog/internal-pack-milestones/new-Deva-NP-v0.json"
        )
        spec, encoded = finalizer._validate_spec(spec_path)

        self.assertEqual(encoded, finalizer._canonical_bytes(spec))
        self.assertEqual(spec["spec_version"], 3)
        self.assertEqual(spec["pack"]["pack_id"], "new-Deva-NP")
        self.assertEqual(spec["adapter"]["input_argument"], "trilingual_tsv")
        self.assertEqual(
            [operation["kind"] for operation in spec["layout"]["operations"]],
            [
                "insert_row_before_actions",
                "insert_row_before_actions",
                "insert_row_before_actions",
            ],
        )
        self.assertEqual(
            [
                operation["layer_id"]
                for operation in spec["layout"]["operations"]
            ],
            ["base", "shift", "symbols"],
        )
        self.assertEqual(
            finalizer._verify_layout(spec),
            {
                "layout_id": "deva-nepal-bhasa-v1",
                "revision": 1,
                "source_path": (
                    "layouts/internal/src/deva-nepal-bhasa-v1.json"
                ),
                "source_sha256": (
                    "f9088679a904a8129e02b8202740564537e616d24b85637c1489038c35d93ac8"
                ),
            },
        )

    def test_v2_layout_operations_are_closed_and_sorted(self) -> None:
        real_spec = json.loads(
            (
                finalizer.REPOSITORY_ROOT
                / "catalog/internal-pack-milestones/ybh-Deva-NP-v0.json"
            ).read_text(encoding="utf-8")
        )
        cases = []

        empty = copy.deepcopy(real_spec)
        empty["layout"]["operations"] = []
        cases.append((empty, "non-empty array"))

        unsorted = copy.deepcopy(real_spec)
        unsorted["layout"]["operations"][0], unsorted["layout"]["operations"][1] = (
            unsorted["layout"]["operations"][1],
            unsorted["layout"]["operations"][0],
        )
        cases.append((unsorted, "strictly sorted"))

        unknown = copy.deepcopy(real_spec)
        unknown["layout"]["operations"][0]["kind"] = "arbitrary_rewrite"
        cases.append((unknown, "kind is unsupported"))

        boolean_index = copy.deepcopy(real_spec)
        boolean_index["layout"]["operations"][2]["row_index"] = True
        cases.append((boolean_index, "row_index must be non-negative"))

        bad_key_index = copy.deepcopy(real_spec)
        bad_key_index["layout"]["operations"][3]["key_index"] = -1
        cases.append((bad_key_index, "key_index must be non-negative"))

        for index, (spec, message) in enumerate(cases):
            with self.subTest(message=message):
                root = self.root / f"case-{index}"
                path = root / "catalog/internal-pack-milestones/ybh-Deva-NP-v0.json"
                path.parent.mkdir(parents=True)
                path.write_bytes(finalizer._canonical_bytes(spec))
                with (
                    mock.patch.object(finalizer, "REPOSITORY_ROOT", root),
                    self.assertRaisesRegex(finalizer.FinalizeError, message),
                ):
                    finalizer._validate_spec(path)

    def _write_v3_spec(self, name: str, license_value: object) -> tuple[Path, Path]:
        spec = json.loads(
            (
                finalizer.REPOSITORY_ROOT
                / "catalog/internal-pack-milestones/ybh-Deva-NP-v0.json"
            ).read_text(encoding="utf-8")
        )
        spec["spec_version"] = 3
        spec["layout"].pop("license_notice_path")
        spec["layout"].pop("license_notice_sha256")
        spec["layout"]["license"] = license_value
        root = self.root / name
        path = root / "catalog/internal-pack-milestones/ybh-Deva-NP-v0.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(finalizer._canonical_bytes(spec))
        return root, path

    def test_v3_layout_license_accepts_null_and_exact_partial_object(self) -> None:
        partial = {
            "copyright": "Copyright 2026 Ampixa",
            "id": "LicenseRef-Internal",
            "redistribution": "unknown",
        }
        full = {
            **partial,
            "license_url": "https://example.test/license",
            "notice_path": "layouts/internal/notices/test.txt",
            "notice_sha256": "a" * 64,
        }
        for name, license_value in (
            ("null", None),
            ("partial", partial),
            ("full", full),
        ):
            with self.subTest(name=name):
                root, path = self._write_v3_spec(name, license_value)
                with mock.patch.object(finalizer, "REPOSITORY_ROOT", root):
                    spec, encoded = finalizer._validate_spec(path)
                self.assertEqual(spec["spec_version"], 3)
                self.assertEqual(spec["layout"]["license"], license_value)
                self.assertEqual(encoded, finalizer._canonical_bytes(spec))

    def test_v3_layout_license_is_closed_and_fail_closed(self) -> None:
        valid = {
            "copyright": "Copyright 2026 Ampixa",
            "id": "LicenseRef-Internal",
            "redistribution": "unknown",
        }
        cases = [
            ("scalar", "internal", "null or an object"),
            (
                "missing-core",
                {"id": "LicenseRef-Internal", "redistribution": "unknown"},
                "must contain id, copyright, redistribution",
            ),
            (
                "unknown-field",
                {**valid, "comment": "not part of the contract"},
                "only the optional",
            ),
            (
                "http-url",
                {**valid, "license_url": "http://example.test/license"},
                "must use HTTPS",
            ),
            (
                "unknown-redistribution",
                {**valid, "redistribution": "sometimes"},
                "redistribution is unsupported",
            ),
            (
                "unpaired-path",
                {**valid, "notice_path": "layouts/internal/notices/test.txt"},
                "must be paired",
            ),
            (
                "unpaired-hash",
                {**valid, "notice_sha256": "a" * 64},
                "must be paired",
            ),
            (
                "unsafe-notice",
                {
                    **valid,
                    "notice_path": "../test.txt",
                    "notice_sha256": "a" * 64,
                },
                "must be a layout notice path",
            ),
        ]
        for name, license_value, message in cases:
            with self.subTest(name=name):
                root, path = self._write_v3_spec(name, license_value)
                with (
                    mock.patch.object(finalizer, "REPOSITORY_ROOT", root),
                    self.assertRaisesRegex(finalizer.FinalizeError, message),
                ):
                    finalizer._validate_spec(path)

    def test_query_selection_is_canonical_and_fail_closed(self) -> None:
        path = self.root / "queries.json"
        value = {"benchmark_queries": ["‘", "क्\u200dष"], "validation_query": "‘आ"}
        path.write_bytes(finalizer._canonical_bytes(value))

        validation, benchmarks, digest = finalizer._query_selection(path)
        self.assertEqual(validation, "‘आ")
        self.assertEqual(benchmarks, ["‘", "क्\u200dष"])
        self.assertEqual(digest, sha256(path))

        path.write_bytes(
            finalizer._canonical_bytes(
                {"benchmark_queries": ["‘आ"], "validation_query": "‘आ"}
            )
        )
        with self.assertRaisesRegex(finalizer.FinalizeError, "unique"):
            finalizer._query_selection(path)

        path.write_bytes(
            finalizer._canonical_bytes(
                {"benchmark_queries": ["क ख"], "validation_query": "‘आ"}
            )
        )
        with self.assertRaisesRegex(finalizer.FinalizeError, "whitespace"):
            finalizer._query_selection(path)

        path.write_text('{"validation_query":"‘आ","benchmark_queries":["क"]}\n')
        with self.assertRaisesRegex(finalizer.FinalizeError, "canonical"):
            finalizer._query_selection(path)

    def _source_tree(self, name: str) -> Path:
        root = self.root / name
        root.mkdir()
        for filename in sorted(finalizer.SOURCE_FILES):
            (root / filename).write_text(f"{filename}\n", encoding="utf-8")
        return root

    def test_source_tree_comparison_rejects_hardlinks_and_drift(self) -> None:
        source_a = self._source_tree("a")
        source_b = self._source_tree("b")
        first, second = finalizer._compare_source_trees(source_a, source_b)
        self.assertEqual(first, second)

        linked = source_b / "forms.jsonl"
        linked.unlink()
        os.link(source_a / "forms.jsonl", linked)
        with self.assertRaisesRegex(finalizer.FinalizeError, "file identity"):
            finalizer._compare_source_trees(source_a, source_b)

        linked.unlink()
        linked.write_text("drift\n", encoding="utf-8")
        with self.assertRaisesRegex(finalizer.FinalizeError, "not byte-identical"):
            finalizer._compare_source_trees(source_a, source_b)

    def test_adapter_regeneration_rejects_identically_mutated_trees(self) -> None:
        raw = self.root / "raw.tsv"
        raw.write_text("headword\nआ\n", encoding="utf-8")
        adapter_sha = "a" * 64
        report = {
            "adapter": "fixture_adapter",
            "adapter_sha256": adapter_sha,
            "adapter_version": 1,
        }

        def build(args: argparse.Namespace) -> dict[str, object]:
            args.output.mkdir(parents=True)
            payloads = {
                "adapter-report.json": finalizer._canonical_bytes(report),
                "aliases.jsonl": b"",
                "forms.jsonl": '{"surface":"आ"}\n'.encode("utf-8"),
                "pack.json": b"{}\n",
                "rejected-rows.jsonl": b"",
                "sources.jsonl": b"{}\n",
            }
            for filename, encoded in payloads.items():
                (args.output / filename).write_bytes(encoded)
            return report

        module = types.SimpleNamespace(
            AdapterError=ValueError,
            build_internal_source=build,
        )
        spec = {
            # A version-1 spec: no auxiliary input, so the regenerator must be
            # given None for it and must never look for one.
            "spec_version": 1,
            "adapter": {
                "input_argument": "apk_tsv",
                "name": "fixture_adapter",
                "sha256": adapter_sha,
                "version": 1,
            },
            "source": {
                "data_version": "1.0.0",
                "max_suggestions": 8,
            },
        }
        source_a = self.root / "source-a"
        source_b = self.root / "source-b"
        build(
            argparse.Namespace(
                apk_tsv=raw,
                output=source_a,
                data_version="1.0.0",
                max_suggestions=8,
            )
        )
        build(
            argparse.Namespace(
                apk_tsv=raw,
                output=source_b,
                data_version="1.0.0",
                max_suggestions=8,
            )
        )
        for root in (source_a, source_b):
            (root / "forms.jsonl").write_text('{"surface":"ई"}\n', encoding="utf-8")

        with self.assertRaisesRegex(finalizer.FinalizeError, "not derived"):
            finalizer._regenerate_and_compare_sources(
                module,
                spec,
                raw,
                None,
                source_a,
                source_b,
            )

    def test_layout_verifier_rejects_sibling_layer_drift_even_if_rehashed(self) -> None:
        real_root = finalizer.REPOSITORY_ROOT
        spec = json.loads(
            (
                real_root / "catalog/internal-pack-milestones/suz-Deva-NP-v0.json"
            ).read_text(encoding="utf-8")
        )
        for relative in (
            spec["layout"]["base_path"],
            spec["paths"]["layout_source"],
            spec["layout"]["license_notice_path"],
            "reports/dictionary-resource-inventory-v1.md",
        ):
            source = real_root / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        layout_path = self.root / spec["paths"]["layout_source"]
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        layout["layers"]["numeric"]["rows"][0][0] = "०"
        layout_path.write_bytes(finalizer._canonical_bytes(layout))
        spec["layout"]["source_sha256"] = sha256(layout_path)

        with (
            mock.patch.object(finalizer, "REPOSITORY_ROOT", self.root),
            self.assertRaisesRegex(finalizer.FinalizeError, "base transformation"),
        ):
            finalizer._verify_layout(spec)

    def test_v2_layout_verifier_rejects_symbol_policy_drift_even_if_rehashed(self) -> None:
        real_root = finalizer.REPOSITORY_ROOT
        spec = json.loads(
            (
                real_root / "catalog/internal-pack-milestones/ybh-Deva-NP-v0.json"
            ).read_text(encoding="utf-8")
        )
        for relative in (
            spec["layout"]["base_path"],
            spec["paths"]["layout_source"],
            spec["layout"]["license_notice_path"],
            "reports/yakkha-pack-readiness-v0.md",
        ):
            source = real_root / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        layout_path = self.root / spec["paths"]["layout_source"]
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        layout["layers"]["symbols"]["rows"][2][7]["kind"] = "text"
        layout_path.write_bytes(finalizer._canonical_bytes(layout))
        spec["layout"]["source_sha256"] = sha256(layout_path)

        with (
            mock.patch.object(finalizer, "REPOSITORY_ROOT", self.root),
            self.assertRaisesRegex(finalizer.FinalizeError, "base transformation"),
        ):
            finalizer._verify_layout(spec)

    def _v3_layout_fixture(
        self,
        name: str,
        license_value: object,
    ) -> tuple[Path, dict[str, object]]:
        real_root = finalizer.REPOSITORY_ROOT
        spec = json.loads(
            (
                real_root / "catalog/internal-pack-milestones/ybh-Deva-NP-v0.json"
            ).read_text(encoding="utf-8")
        )
        spec["spec_version"] = 3
        spec["layout"].pop("license_notice_path")
        spec["layout"].pop("license_notice_sha256")
        spec["layout"]["license"] = license_value
        root = self.root / name
        for relative in (
            spec["layout"]["base_path"],
            spec["paths"]["layout_source"],
            "reports/yakkha-pack-readiness-v0.md",
        ):
            source = real_root / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        layout_path = root / spec["paths"]["layout_source"]
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        if license_value is None:
            layout.pop("license")
        else:
            layout["license"] = copy.deepcopy(license_value)
        layout_path.write_bytes(finalizer._canonical_bytes(layout))
        spec["layout"]["source_sha256"] = sha256(layout_path)
        return root, spec

    def test_v3_layout_license_null_removes_inherited_base_license(self) -> None:
        root, spec = self._v3_layout_fixture("v3-null-layout", None)
        with mock.patch.object(finalizer, "REPOSITORY_ROOT", root):
            verified = finalizer._verify_layout(spec)
        self.assertEqual(verified["layout_id"], "deva-nepal-yakkha-v1")

    def test_v3_layout_partial_license_replaces_inherited_object_exactly(self) -> None:
        partial = {
            "copyright": "Copyright 2026 Ampixa",
            "id": "LicenseRef-Internal",
            "redistribution": "unknown",
        }
        root, spec = self._v3_layout_fixture("v3-partial-layout", partial)
        with mock.patch.object(finalizer, "REPOSITORY_ROOT", root):
            verified = finalizer._verify_layout(spec)
        self.assertEqual(verified["layout_id"], "deva-nepal-yakkha-v1")
        self.assertFalse((root / "layouts/internal/notices").exists())

    def test_v3_layout_notice_is_verified_only_for_a_declared_pair(self) -> None:
        notice_bytes = b"Internal layout notice fixture.\n"
        license_value = {
            "copyright": "Copyright 2026 Ampixa",
            "id": "LicenseRef-Internal",
            "notice_path": "layouts/internal/notices/v3-fixture.txt",
            "notice_sha256": hashlib.sha256(notice_bytes).hexdigest(),
            "redistribution": "unknown",
        }
        root, spec = self._v3_layout_fixture("v3-notice-layout", license_value)
        notice_path = root / license_value["notice_path"]
        notice_path.parent.mkdir(parents=True)
        notice_path.write_bytes(notice_bytes)
        with mock.patch.object(finalizer, "REPOSITORY_ROOT", root):
            finalizer._verify_layout(spec)

        notice_path.write_bytes(b"changed\n")
        with (
            mock.patch.object(finalizer, "REPOSITORY_ROOT", root),
            self.assertRaisesRegex(finalizer.FinalizeError, "notice bytes"),
        ):
            finalizer._verify_layout(spec)

    def test_pack_verifier_rejects_non_store_members_before_parsing(self) -> None:
        spec = {
            "pack": {
                "artifact_license": "LicenseRef-Internal",
                "file_name": "fixture.nkp",
                "language": "suz",
                "output_script": "Deva",
                "pack_id": "fixture",
            },
            "source": {"data_version": "1.0.0", "max_suggestions": 8},
        }
        pack = self.root / "fixture.nkp"
        with zipfile.ZipFile(pack, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(finalizer.PACK_MEMBERS):
                archive.writestr(name, b"{}")

        with self.assertRaisesRegex(finalizer.FinalizeError, "ZIP-STORE"):
            finalizer._verified_pack(pack, spec)

    def test_cumulative_review_upsert_is_idempotent_and_preserves_foundation(self) -> None:
        review_path = self.root / "review.json"
        foundation_evidence = {"evidence_id": "foundation"}
        review = {
            "authority": "internal",
            "evidence": [foundation_evidence],
            "expected_counts": {
                "profiles": 2,
                "scripts": 1,
                "selectable": 1,
                "targets": 2,
            },
            "profile_overrides": {
                "foundation-direct": {"profile_id": "foundation", "selectable": True}
            },
            "review_version": 1,
        }
        review_path.write_bytes(finalizer._canonical_bytes(review))
        args = argparse.Namespace(review_input=review_path, reviewed_at="2026-07-15")
        spec = {
            "pack": {
                "file_name": "suz-Deva-NP.nkp",
                "language": "suz",
                "output_script": "Deva",
                "pack_id": "suz-Deva-NP",
            },
            "paths": {"evidence_output": "reports/sunuwar-internal-pack-v0.json"},
            "profile": {
                "default_enabled": False,
                "input_method_id": "suz-deva-direct",
            },
        }
        evidence = {
            "layout": {
                "layout_id": "deva-nepal-extended-v1",
                "revision": 1,
                "source_sha256": "b" * 64,
            },
            "pack": {"artifact_sha256": "c" * 64},
            "queries": {
                "benchmark": [{"query": "‘"}],
                "validation": {"expected_surface": "‘आ", "query": "‘आ"},
            },
        }
        manifest = {
            "counts": {"candidate_surfaces": 10},
            "indexes": {"aliases": {"keys": 0}, "surface": {"keys": 10}},
            "pack": {"artifact_license": "LicenseRef-Internal"},
        }
        evidence_bytes = finalizer._canonical_bytes(evidence)

        with mock.patch.object(finalizer, "_validate_review_with_catalog"):
            first = finalizer._build_review(
                args,
                spec,
                evidence,
                evidence_bytes,
                manifest,
            )
        self.assertIn("foundation-direct", first["profile_overrides"])
        self.assertEqual(first["expected_counts"]["selectable"], 2)
        self.assertEqual(
            {row["evidence_id"] for row in first["evidence"]},
            {"foundation", "suz-direct-internal-2026-07-15"},
        )

        review_path.write_bytes(finalizer._canonical_bytes(first))
        with mock.patch.object(finalizer, "_validate_review_with_catalog"):
            second = finalizer._build_review(
                args,
                spec,
                evidence,
                evidence_bytes,
                manifest,
            )
        self.assertEqual(first, second)

        first["profile_overrides"]["suz-deva-direct"]["layout_id"] = "different"
        review_path.write_bytes(finalizer._canonical_bytes(first))
        with (
            mock.patch.object(finalizer, "_validate_review_with_catalog"),
            self.assertRaisesRegex(finalizer.FinalizeError, "different existing"),
        ):
            finalizer._build_review(
                args,
                spec,
                evidence,
                evidence_bytes,
                manifest,
            )


if __name__ == "__main__":
    unittest.main()
