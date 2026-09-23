from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nepa_keyboard.compiler import PackValidationError, compile_pack
from nepa_keyboard.runtime import KeyboardPack
from tools import build_limbu_internal_source as adapter


HEADER = "id\theadword_limbu\tdesc_devanagari\tgroup\tdefinition\tipa\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class LimbuInternalSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "limdic_dictionary.tsv"
        self.input.write_text(
            HEADER
            + "00001\tᤀ\t/अ/\tAA\tfirst\t['ɔ']\n"
            + "00002\tᤀ᤹ᤡ\t/अ?इ/\tAA\tsecond\t['ɔ']\n"
            + "00003\tᤀ\t/अ/\tAA\tduplicate surface\t['ɔ']\n"
            + "00004\tᤀ/ᤡ\t/अ इ/\tAA\tunsplit variant\t[]\n"
            + "00005\tᤀ(ᤡ)\t/अ इ/\tAA\tparenthetical variant\t[]\n"
            + "00006\tनेपाल\tनेपाल\tAA\twrong script\t[]\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, output: Path) -> argparse.Namespace:
        return argparse.Namespace(
            limdic_tsv=self.input,
            output=output,
            data_version="1.0.0",
            max_suggestions=4,
        )

    def pins(self):
        return mock.patch.multiple(
            adapter,
            LIMDIC_SHA256=sha256(self.input),
            EXPECTED_DATA_ROWS=6,
        )

    def test_builds_deterministic_direct_internal_pack(self) -> None:
        first = self.root / "first"
        second = self.root / "second"
        with self.pins():
            first_report = adapter.build_internal_source(self.args(first))
            second_report = adapter.build_internal_source(self.args(second))

        for filename in (
            "pack.json",
            "sources.jsonl",
            "forms.jsonl",
            "aliases.jsonl",
            "rejected-rows.jsonl",
            "adapter-report.json",
        ):
            self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())

        forms = read_jsonl(first / "forms.jsonl")
        self.assertEqual([row["form_id"] for row in forms], [
            "lif:limdic:00001",
            "lif:limdic:00003",
            "lif:limdic:00002",
        ])
        self.assertTrue(all(row["rank_score"] == adapter.RANK_SCORE for row in forms))
        self.assertEqual((first / "aliases.jsonl").read_bytes(), b"")
        rejected = read_jsonl(first / "rejected-rows.jsonl")
        self.assertEqual([row["reason"] for row in rejected], [
            "outside_limbu_block",
            "outside_limbu_block",
            "outside_limbu_block",
        ])
        self.assertEqual(first_report["stats"]["accepted_rows"], 3)
        self.assertEqual(first_report["stats"]["distinct_accepted_surfaces"], 2)
        self.assertEqual(first_report, second_report)

        first_pack = self.root / "first.nkp"
        second_pack = self.root / "second.nkp"
        first_compile = compile_pack(first, first_pack, "internal")
        second_compile = compile_pack(second, second_pack, "internal")
        self.assertEqual(first_pack.read_bytes(), second_pack.read_bytes())
        self.assertEqual(first_compile["artifact_sha256"], second_compile["artifact_sha256"])
        self.assertEqual(first_compile["manifest"]["release_mode"], "internal")
        self.assertEqual(first_compile["manifest"]["counts"]["source_forms"], 3)
        self.assertEqual(first_compile["manifest"]["counts"]["candidate_surfaces"], 2)
        self.assertEqual(first_compile["manifest"]["counts"]["duplicate_surfaces_merged"], 1)
        self.assertEqual(first_compile["manifest"]["counts"]["alias_keys"], 0)
        with KeyboardPack(first_pack) as pack:
            self.assertEqual(pack.lookup("ᤀ᤹", "surface")[0]["surface"], "ᤀ᤹ᤡ")

        with self.assertRaisesRegex(PackValidationError, "release build blocked"):
            compile_pack(first, self.root / "must-not-release.nkp", "release")

    def test_rejects_hash_count_header_and_duplicate_id_drift(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "SHA-256 mismatch"):
            adapter.build_internal_source(self.args(self.root / "bad-hash"))

        with mock.patch.object(adapter, "LIMDIC_SHA256", sha256(self.input)):
            with self.assertRaisesRegex(adapter.AdapterError, "row count mismatch"):
                adapter.build_internal_source(self.args(self.root / "bad-count"))

        self.input.write_text("wrong\theader\n", encoding="utf-8")
        with mock.patch.multiple(
            adapter,
            LIMDIC_SHA256=sha256(self.input),
            EXPECTED_DATA_ROWS=0,
        ):
            with self.assertRaisesRegex(adapter.AdapterError, "header"):
                adapter.build_internal_source(self.args(self.root / "bad-header"))

        self.input.write_text(
            HEADER
            + "same\tᤀ\t/अ/\tAA\tfirst\t[]\n"
            + "same\tᤡ\t/इ/\tAA\tsecond\t[]\n",
            encoding="utf-8",
        )
        with mock.patch.multiple(
            adapter,
            LIMDIC_SHA256=sha256(self.input),
            EXPECTED_DATA_ROWS=2,
        ):
            with self.assertRaisesRegex(adapter.AdapterError, "repeats stable id"):
                adapter.build_internal_source(self.args(self.root / "duplicate-id"))


if __name__ == "__main__":
    unittest.main()
