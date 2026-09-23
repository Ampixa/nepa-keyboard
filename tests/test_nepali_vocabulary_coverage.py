from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools import build_nepali_roman_release_source as roman_adapter
from tools import build_nepali_wikipedia_vocabulary as wikipedia_adapter
from tools import evaluate_nepali_vocabulary_coverage as evaluator


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NepaliVocabularyCoverageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.direct = self.root / "forms.jsonl"
        self.wikipedia = self.root / "vocabulary.jsonl"
        self.attribution = self.root / "attribution-pages.jsonl"
        self.manifest = self.root / "manifest.json"
        self.archive = self.root / "nep.zip"

        direct_rows = [
            {"form_id": "npi:nepal", "surface": "नेपाल"},
            {"form_id": "npi:bhasa", "surface": "भाषा"},
        ]
        self.direct.write_text(
            "".join(canonical_json(row) + "\n" for row in direct_rows),
            encoding="utf-8",
        )
        wikipedia_rows = [
            {"count": 10, "rank": 1, "surface": "नेपाल"},
            {"count": 9, "rank": 2, "surface": "बाहिर"},
            {"count": 8, "rank": 3, "surface": "अर्को"},
            {"count": 7, "rank": 4, "surface": "हराएको"},
        ]
        self.wikipedia.write_text(
            "".join(canonical_json(row) + "\n" for row in wikipedia_rows),
            encoding="utf-8",
        )
        attribution_rows = [
            {
                "page_id": 10,
                "page_url": "https://ne.wikipedia.org/?curid=10",
                "revision_id": 100,
                "revision_url": "https://ne.wikipedia.org/w/index.php?oldid=100",
                "title": "पहिलो",
            },
            {
                "page_id": 11,
                "page_url": "https://ne.wikipedia.org/?curid=11",
                "revision_id": 101,
                "revision_url": "https://ne.wikipedia.org/w/index.php?oldid=101",
                "title": "दोस्रो",
            },
        ]
        self.attribution.write_text(
            "".join(canonical_json(row) + "\n" for row in attribution_rows),
            encoding="utf-8",
        )
        manifest = {
            "generator_version": wikipedia_adapter.GENERATOR_VERSION,
            "input": {
                "date": wikipedia_adapter.DUMP_DATE,
                "sha1": wikipedia_adapter.DUMP_SHA1,
                "sha256": wikipedia_adapter.DUMP_SHA256,
                "bytes": wikipedia_adapter.DUMP_BYTES,
                "namespace": 0,
                "legal_documents": {
                    "dump_license_information": {
                        "bytes": wikipedia_adapter.DUMP_LICENSE_INFO_BYTES,
                        "sha256": wikipedia_adapter.DUMP_LICENSE_INFO_SHA256,
                        "source_url": wikipedia_adapter.DUMP_LICENSE_INFO_URL,
                    },
                    "terms_of_use": {
                        "bytes": wikipedia_adapter.WIKIMEDIA_TERMS_BYTES,
                        "sha256": wikipedia_adapter.WIKIMEDIA_TERMS_SHA256,
                        "source_url": wikipedia_adapter.WIKIMEDIA_TERMS_URL,
                        "revision": wikipedia_adapter.WIKIMEDIA_TERMS_REVISION,
                    },
                    "cc_by_sa_legalcode": {
                        "bytes": wikipedia_adapter.LICENSE_BYTES,
                        "sha256": wikipedia_adapter.LICENSE_SHA256,
                        "source_url": wikipedia_adapter.LICENSE_URL,
                    },
                },
            },
            "output": {
                "rows": 4,
                "sha256": sha256(self.wikipedia),
                "attribution_pages": {
                    "rows": 2,
                    "sha256": sha256(self.attribution),
                },
            },
            "redistribution": {
                "shipping_authority": False,
                "gate": wikipedia_adapter.SHIPPING_GATE,
                "attribution_index_included": True,
            },
            "selection_contract": {"evaluation_data_consumed": False},
        }
        self.manifest.write_text(canonical_json(manifest) + "\n", encoding="utf-8")

        self.test_rows = [
            {
                "unique_identifier": "nep1",
                "native word": "नेपाल",
                "english word": "nepal",
                "source": "AK-Freq",
            },
            {
                "unique_identifier": "nep2",
                "native word": "बाहिर",
                "english word": "bahira",
                "source": "AK-Freq",
            },
            {
                "unique_identifier": "nep3",
                "native word": "अर्को",
                "english word": "arko",
                "source": "AK-NEI",
            },
            {
                "unique_identifier": "nep4",
                "native word": "अनुपस्थित",
                "english word": "anupasthita",
                "source": "AK-NEI",
            },
        ]
        member = "".join(canonical_json(row) + "\n" for row in self.test_rows)
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("nep_test.json", member)
        self.member_sha256 = hashlib.sha256(member.encode("utf-8")).hexdigest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def pins(self):
        return (
            mock.patch.multiple(
                roman_adapter,
                DIRECT_SOURCE_SHA256={"forms.jsonl": sha256(self.direct)},
                DIRECT_FORM_COUNT=2,
                AKSHARANTAR_ARCHIVE_SHA256=sha256(self.archive),
                AKSHARANTAR_MEMBER_SHA256={"nep_test.json": self.member_sha256},
                AKSHARANTAR_MEMBER_ROWS={"nep_test.json": len(self.test_rows)},
            ),
            mock.patch.multiple(
                evaluator,
                WIKIPEDIA_VOCABULARY_SHA256=sha256(self.wikipedia),
                WIKIPEDIA_MANIFEST_SHA256=sha256(self.manifest),
                WIKIPEDIA_ROWS=4,
                WIKIPEDIA_ATTRIBUTION_SHA256=sha256(self.attribution),
                WIKIPEDIA_ATTRIBUTION_ROWS=2,
                CUTOFFS=(0, 1, 2, 4),
            ),
        )

    def args(self, output: Path) -> argparse.Namespace:
        return argparse.Namespace(
            direct_forms=self.direct,
            wikipedia_vocabulary=self.wikipedia,
            wikipedia_manifest=self.manifest,
            wikipedia_attribution=self.attribution,
            aksharantar_archive=self.archive,
            output=output,
        )

    def test_builds_deterministic_aggregate_only_fixed_cutoff_curve(self) -> None:
        first = self.root / "first.json"
        second = self.root / "second.json"
        first_pins, first_eval_pins = self.pins()
        with first_pins, first_eval_pins:
            report = evaluator.evaluate(self.args(first))
        second_pins, second_eval_pins = self.pins()
        with second_pins, second_eval_pins:
            evaluator.evaluate(self.args(second))

        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(
            [row["covered_test_rows"] for row in report["curve"]],
            [1, 1, 2, 3],
        )
        self.assertEqual(
            [row["candidate_union_rows"] for row in report["curve"]],
            [2, 2, 3, 5],
        )
        self.assertEqual(
            report["curve"][2]["by_source"]["AK-Freq"]["covered_rows"],
            2,
        )
        self.assertTrue(report["contract"]["evaluation_only"])
        self.assertFalse(report["contract"]["report_contains_target_identities"])
        serialized = first.read_text(encoding="utf-8")
        for target in ("नेपाल", "बाहिर", "अर्को", "अनुपस्थित"):
            self.assertNotIn(target, serialized)

    def test_refuses_to_overwrite_evaluation_evidence(self) -> None:
        output = self.root / "existing.json"
        output.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(
            evaluator.CoverageEvaluationError,
            "refusing to overwrite evidence",
        ):
            evaluator.evaluate(self.args(output))
        self.assertEqual(output.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
