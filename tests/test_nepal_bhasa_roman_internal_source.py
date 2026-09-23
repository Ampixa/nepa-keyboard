from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nepa_keyboard.compiler import compile_pack
from tools import build_nepal_bhasa_internal_source as direct
from tools import build_nepal_bhasa_roman_internal_source as adapter


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class NepalBhasaRomanInternalSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.trilingual = self.root / "trilingual.tsv"
        self.apk = self.root / "apk.tsv"
        self.trilingual.write_text(
            "newar\tnepali\n"
            "च\tx\n"
            "चा\ty\n"
            "अँ\tz\n"
            "अं\tq\n"
            "आं\tr\n",
            encoding="utf-8",
        )
        self.apk.write_text(
            "newar\tenglish\ttransliteration\n"
            "च; चा\tfirst\tca; cā\n"
            "अँ; अं; आं\tsecond\taṁ; aɱ; āṁ\n"
            "च च\tmultiword\tca ca\n"
            "क\tabsent\tka\n"
            "च;; चा;\tinterior and trailing\tca;; cā;\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self, output: Path) -> dict[str, object]:
        with (
            mock.patch.object(
                direct,
                "SOURCE_SHA256",
                hashlib.sha256(self.trilingual.read_bytes()).hexdigest(),
            ),
            mock.patch.object(direct, "EXPECTED_DATA_ROWS", 5),
            mock.patch.object(
                adapter,
                "APK_SHA256",
                hashlib.sha256(self.apk.read_bytes()).hexdigest(),
            ),
            mock.patch.object(adapter, "EXPECTED_APK_ROWS", 5),
        ):
            return adapter.build_internal_source(
                argparse.Namespace(
                    trilingual_tsv=self.trilingual,
                    apk_tsv=self.apk,
                    output=output,
                    data_version="1.1.0",
                    max_suggestions=8,
                )
            )

    def test_explicit_ascii_fold_is_bounded(self) -> None:
        self.assertEqual(adapter._fold_ascii_alias("cāḥ"), "cah")
        self.assertEqual(adapter._fold_ascii_alias("aɱ"), "am")
        self.assertEqual(adapter._fold_ascii_alias("é"), "e")
        self.assertGreater(
            adapter._alias_rank_delta("ca", exact_ascii=False),
            adapter._alias_rank_delta("caka", exact_ascii=True),
        )
        with self.assertRaises(adapter.RomanAdapterError):
            adapter._fold_ascii_alias("ø")

    def test_builds_only_exact_single_token_direct_intersection(self) -> None:
        output = self.root / "output"
        report = self.build(output)
        aliases = read_jsonl(output / "aliases.jsonl")
        rejected = read_jsonl(output / "rejected-rows.jsonl")

        self.assertEqual(report["candidate_coverage"]["ratio"], "5/5")
        self.assertEqual(report["aliases"]["stats"]["accepted_pair_occurrences"], 7)
        self.assertEqual(report["aliases"]["stats"]["matched_trailing_empty_positions"], 1)
        self.assertEqual(report["aliases"]["stats"]["rows_with_matched_trailing_delimiter"], 1)
        self.assertEqual(report["aliases"]["stats"]["accepted_academic_pairs"], 5)
        self.assertEqual(
            report["aliases"]["stats"]["duplicate_academic_pair_occurrences"], 2
        )
        self.assertEqual(report["aliases"]["stats"]["accepted_ascii_pairs"], 5)
        self.assertEqual(report["aliases"]["stats"]["accepted_exact_ascii_pairs"], 1)
        self.assertEqual(report["aliases"]["stats"]["accepted_folded_ascii_pairs"], 4)
        self.assertEqual(len(aliases), 5)
        self.assertEqual(
            {row["reason"] for row in rejected if row.get("source_id") == adapter.APK_SOURCE_ID},
            {
                "multiword_surface",
                "paired_empty_segment",
                "surface_absent_from_direct_pack",
            },
        )
        ascii_summary = report["aliases"]["ascii"]
        self.assertEqual(ascii_summary["distinct_keys"], 2)
        self.assertEqual(ascii_summary["collision_key_count"], 2)
        self.assertEqual(ascii_summary["max_targets_per_exact_key"], 3)
        self.assertEqual(
            {row["alias"] for row in ascii_summary["collision_examples"]},
            {"am", "ca"},
        )

        pack = self.root / "new-Deva-NP.nkp"
        compiler_report = compile_pack(output, pack)
        self.assertEqual(
            compiler_report["manifest"]["counts"]["candidate_surfaces"], 5
        )
        self.assertGreater(
            compiler_report["manifest"]["indexes"]["aliases"]["keys"], 0
        )

    def test_output_is_byte_deterministic(self) -> None:
        first = self.root / "first"
        second = self.root / "second"
        first_report = self.build(first)
        second_report = self.build(second)
        self.assertEqual(first_report, second_report)
        for name in (
            "adapter-report.json",
            "aliases.jsonl",
            "forms.jsonl",
            "pack.json",
            "rejected-rows.jsonl",
            "sources.jsonl",
        ):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_rejects_asymmetric_semicolon_shape(self) -> None:
        self.apk.write_text(
            "newar\tenglish\ttransliteration\n"
            "च; चा\tbad\tca\n",
            encoding="utf-8",
        )
        with (
            mock.patch.object(
                direct,
                "SOURCE_SHA256",
                hashlib.sha256(self.trilingual.read_bytes()).hexdigest(),
            ),
            mock.patch.object(direct, "EXPECTED_DATA_ROWS", 5),
            mock.patch.object(
                adapter,
                "APK_SHA256",
                hashlib.sha256(self.apk.read_bytes()).hexdigest(),
            ),
            mock.patch.object(adapter, "EXPECTED_APK_ROWS", 1),
        ):
            with self.assertRaisesRegex(
                adapter.RomanAdapterError, "asymmetric semicolon segments"
            ):
                adapter.build_internal_source(
                    argparse.Namespace(
                        trilingual_tsv=self.trilingual,
                        apk_tsv=self.apk,
                        output=self.root / "broken",
                        data_version="1.1.0",
                        max_suggestions=8,
                    )
                )

    def test_rejects_utf8_bom(self) -> None:
        payload = self.apk.read_bytes()
        with self.assertRaisesRegex(adapter.RomanAdapterError, "must not contain"):
            adapter._build_alias_rows(b"\xef\xbb\xbf" + payload, {"च": "fixture"})


if __name__ == "__main__":
    unittest.main()
