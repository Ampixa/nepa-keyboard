from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_sil_apk_candidate_source as candidate


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class SilApkCandidateSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "nepali-fixture.sil-apk.dict.jsonl"
        surfaces = ("अक्\u200dख", "टाङ्\u200c", "Latin")
        self.raw.write_text(
            "".join(
                json.dumps(
                    {
                        "lang": "fix",
                        "headword": surface,
                        "ne": [],
                        "en": [],
                        "source": "sil-apk/fixture",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
                for surface in surfaces
            ),
            encoding="utf-8",
        )
        encoded = self.raw.read_bytes()
        self.catalog = self.root / "resources.json"
        self.catalog.write_text(
            canonical(
                {
                    "packs": [
                        {
                            "id": "fix",
                            "iso_639_3": "fix",
                            "name": "Fixture",
                            "resources": [
                                {
                                    "bytes": len(encoded),
                                    "canonical": True,
                                    "format": "JSONL",
                                    "id": "fix-apk",
                                    "kind": "lexicon",
                                    "license": "restricted",
                                    "path": (
                                        "/inventory/"
                                        "nepali-fixture.sil-apk.dict.jsonl"
                                    ),
                                    "record_unit": "entries",
                                    "records": len(surfaces),
                                    "redistribution": "prohibited",
                                    "sha256": hashlib.sha256(encoded).hexdigest(),
                                    "structured": True,
                                    "uses": ["candidate_vocabulary"],
                                }
                            ],
                            "variety": "Test Kiranti",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(
        self,
        policy: str,
        output: str,
        *,
        source_tag: str = "sil-apk/fixture",
    ) -> argparse.Namespace:
        return argparse.Namespace(
            resource_catalog=self.catalog,
            target_id="fix",
            resource_id="fix-apk",
            sil_apk_jsonl=self.raw,
            source_tag=source_tag,
            policy=policy,
            output=self.root / output,
            data_version="1.0.0",
            max_suggestions=8,
        )

    def test_builds_both_explicit_policies_without_inference(self) -> None:
        conjunct = candidate.build_candidate_source(
            self.args("conjunct_only", "conjunct")
        )
        terminal = candidate.build_candidate_source(
            self.args("terminal_zwnj", "terminal")
        )

        conjunct_forms = read_jsonl(self.root / "conjunct" / "forms.jsonl")
        terminal_forms = read_jsonl(self.root / "terminal" / "forms.jsonl")
        self.assertEqual([row["surface"] for row in conjunct_forms], ["अक्\u200dख"])
        self.assertEqual(
            [row["surface"] for row in terminal_forms],
            ["अक्\u200dख", "टाङ्\u200c"],
        )
        self.assertEqual(
            {row["form_id"] for row in terminal_forms},
            {"fix:apk:line-000001", "fix:apk:line-000002"},
        )
        self.assertFalse(conjunct["joiner_policy"]["allow_terminal_zwnj"])
        self.assertTrue(terminal["joiner_policy"]["allow_terminal_zwnj"])
        self.assertEqual(conjunct["stats"]["accepted_rows"], 1)
        self.assertEqual(terminal["stats"]["accepted_rows"], 2)

        pack = json.loads(
            (self.root / "terminal" / "pack.json").read_text(encoding="utf-8")
        )
        source = read_jsonl(self.root / "terminal" / "sources.jsonl")[0]
        self.assertEqual(pack["pack_id"], "fix-Deva-NP")
        self.assertEqual(pack["language"], "fix")
        self.assertEqual(pack["display_name"], "Fixture")
        self.assertEqual(pack["variety"], "Test Kiranti")
        self.assertEqual(source["source_id"], "fix-apk")
        self.assertEqual(source["license"], "restricted")
        self.assertEqual(source["redistribution"], "prohibited")

    def test_source_generation_is_byte_deterministic(self) -> None:
        candidate.build_candidate_source(self.args("terminal_zwnj", "a"))
        candidate.build_candidate_source(self.args("terminal_zwnj", "b"))
        for name in (
            "adapter-report.json",
            "aliases.jsonl",
            "forms.jsonl",
            "pack.json",
            "rejected-rows.jsonl",
            "sources.jsonl",
        ):
            self.assertEqual(
                (self.root / "a" / name).read_bytes(),
                (self.root / "b" / name).read_bytes(),
            )

    def test_rejects_catalog_source_and_helper_drift(self) -> None:
        with self.assertRaisesRegex(candidate.CandidateError, "source tag"):
            candidate.build_candidate_source(
                self.args("conjunct_only", "bad-source", source_tag="sil-apk/other")
            )

        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["packs"][0]["resources"][0]["canonical"] = False
        self.catalog.write_text(canonical(catalog), encoding="utf-8")
        with self.assertRaisesRegex(candidate.CandidateError, "structured and canonical"):
            candidate.build_candidate_source(self.args("conjunct_only", "noncanonical"))

        catalog["packs"][0]["resources"][0]["canonical"] = True
        self.catalog.write_text(canonical(catalog), encoding="utf-8")
        with (
            mock.patch.object(candidate, "HELPER_SHA256", "0" * 64),
            self.assertRaisesRegex(candidate.CandidateError, "helper SHA-256 mismatch"),
        ):
            candidate.build_candidate_source(self.args("conjunct_only", "bad-helper"))

    def test_strict_json_reader_rejects_duplicate_candidate_spec_keys(self) -> None:
        duplicate = self.root / "duplicate-spec.json"
        duplicate.write_text(
            '{"claim_scope":"candidate_only","claim_scope":"other"}\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(candidate.CandidateError, "duplicate JSON key"):
            candidate.read_strict_json_object(duplicate, "candidate spec")

    def test_remote_runner_gates_this_test_and_promotion_state(self) -> None:
        runner = (
            candidate.ADAPTER_PATH.parent / "run_cdjk_sil_apk_candidate_pack.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "-m unittest discover -s tests -p test_sil_apk_candidate_source.py",
            runner,
        )
        self.assertIn("adapter_test_verified=1", runner)
        self.assertIn("promotion_state_unchanged=1", runner)
        self.assertIn("object_pairs_hook=strict_object", runner)
        self.assertIn("duplicate_surfaces_merged", runner)
        self.assertIn("expected_first_surface", runner)
        self.assertIn("runtime_sha256", runner)
        self.assertIn(r'test("[\u0000-\u001F\u007F]")', runner)
        self.assertNotIn(r'test("[\\u0000-\\u001F\\u007F]")', runner)
        self.assertNotIn("finalize_internal_pack_milestone", runner)


if __name__ == "__main__":
    unittest.main()
