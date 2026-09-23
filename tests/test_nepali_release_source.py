from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nepa_keyboard.compiler import compile_pack
from tools import build_nepali_release_source as adapter


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class NepaliReleaseSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.google_lexicon = self.root / "lexicon.tsv"
        self.google_lexicon.write_text(
            "# Copyright 2018 Google Inc.\n"
            "# CC BY 4.0\n"
            "नेपाल\tn e p aa l\n"
            "साझा\ts aa jh aa\n"
            "कोश\tk o s\n"
            "क़िला\tk i l aa\n"
            "गर्\u200dयो\tg ax r y o\n"
            "क्\u200cष\tk ss\n"
            "English\te ng l i s\n"
            "दुई शब्द\td u i\n"
            "१२३\to n e\n"
            "ालाई\ta l a i\n"
            "स\u200dंयुक्त\ts a m y u k t a\n"
            "ग्रन्थ्\u200dालाई\tg r a n th a l a i\n",
            encoding="utf-8",
        )
        self.google_license = self.root / "cc-by-4.0.txt"
        self.google_license.write_text(
            "Creative Commons Attribution 4.0 International\n"
            "Fixture full CC BY legalcode.",
            encoding="utf-8",
        )
        self.openslr_transcripts = self.root / "utt_spk_text.tsv"
        self.openslr_transcripts.write_text(
            "utt1\tspk1\t१२३ नेपाल। नेपाल साझा; ा\n"
            "utt2\tspk2\t१२३ नेपाल। नेपाल साझा; ा\n"
            "utt3\tspk3\tसमाचार, नयाँ-mail गर्\u200dयो स\u200dंयुक्त ग्रन्थ्\u200dालाई\n",
            encoding="utf-8",
        )
        self.openslr_license = self.root / "cc-by-sa-4.0.txt"
        self.openslr_license.write_text(
            "Creative Commons Attribution-ShareAlike 4.0 International\n"
            "Fixture full CC BY-SA legalcode.",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, output: Path) -> argparse.Namespace:
        return argparse.Namespace(
            google_lexicon=self.google_lexicon,
            google_license=self.google_license,
            google_commit=adapter.GOOGLE_PINNED_COMMIT,
            openslr_transcripts=self.openslr_transcripts,
            openslr_license=self.openslr_license,
            output=output,
            data_version="1.0.0",
            max_suggestions=4,
        )

    def pinned_fixture_hashes(self):
        return mock.patch.multiple(
            adapter,
            GOOGLE_LEXICON_SHA256=sha256(self.google_lexicon),
            OPENSLR_TRANSCRIPTS_SHA256=sha256(self.openslr_transcripts),
        )

    def test_builds_deterministic_direct_union_with_provenance(self) -> None:
        first = self.root / "first"
        second = self.root / "second"
        with self.pinned_fixture_hashes():
            first_report = adapter.build_release_source(self.args(first))
            second_report = adapter.build_release_source(self.args(second))

        for filename in (
            "pack.json",
            "sources.jsonl",
            "forms.jsonl",
            "aliases.jsonl",
            "adapter-report.json",
        ):
            self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())

        self.assertEqual((first / "aliases.jsonl").read_bytes(), b"")
        pack = json.loads((first / "pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["artifact_license"], "CC-BY-SA-4.0")
        self.assertEqual(pack["allowed_format_characters"], ["U+200C", "U+200D"])

        forms = {row["surface"]: row for row in read_jsonl(first / "forms.jsonl")}
        normalized_qila = adapter._canonical_token("क़िला")
        self.assertIsNotNone(normalized_qila)
        self.assertEqual(
            set(forms),
            {
                "नेपाल",
                "साझा",
                "कोश",
                normalized_qila,
                "गर्\u200dयो",
                "क्\u200cष",
                "समाचार",
                "नयाँ",
            },
        )
        self.assertNotIn("ालाई", forms)
        self.assertNotIn("स", forms)
        self.assertNotIn("ंयुक्त", forms)
        self.assertNotIn("ग्रन्थ्", forms)
        self.assertEqual(
            forms["नेपाल"]["rank_score"],
            1000 + round(1000 * math.log1p(2)),
        )
        self.assertEqual(
            forms["साझा"]["rank_score"],
            1000 + round(1000 * math.log1p(1)),
        )
        self.assertEqual(forms["कोश"]["rank_score"], 1000)
        self.assertEqual(
            forms["समाचार"]["rank_score"],
            round(1000 * math.log1p(1)),
        )
        self.assertEqual(
            forms["गर्\u200dयो"]["rank_score"],
            1000 + round(1000 * math.log1p(1)),
        )
        self.assertEqual(
            forms["नेपाल"]["source_ids"],
            [adapter.GOOGLE_SOURCE_ID, adapter.OPENSLR_SOURCE_ID],
        )
        self.assertEqual(forms["समाचार"]["source_ids"], [adapter.OPENSLR_SOURCE_ID])
        self.assertEqual(forms["कोश"]["source_ids"], [adapter.GOOGLE_SOURCE_ID])
        self.assertEqual(
            forms["गर्\u200dयो"]["source_ids"],
            [adapter.GOOGLE_SOURCE_ID, adapter.OPENSLR_SOURCE_ID],
        )

        sources = {row["source_id"]: row for row in read_jsonl(first / "sources.jsonl")}
        google = sources[adapter.GOOGLE_SOURCE_ID]
        openslr = sources[adapter.OPENSLR_SOURCE_ID]
        self.assertEqual(google["sha256"], sha256(self.google_lexicon))
        self.assertEqual(google["license_sha256"], sha256(self.google_license))
        self.assertIn(adapter.GOOGLE_PINNED_COMMIT, google["source_url"])
        self.assertIn("Copyright 2018 Google Inc.", google["license_notice"])
        self.assertIn("Fixture full CC BY legalcode.", google["license_notice"])
        self.assertEqual(openslr["sha256"], sha256(self.openslr_transcripts))
        self.assertEqual(openslr["license_sha256"], sha256(self.openslr_license))
        self.assertIn("Copyright 2016, 2017, 2018 Google, Inc.", openslr["license_notice"])
        self.assertIn("Fixture full CC BY-SA legalcode.", openslr["license_notice"])

        self.assertEqual(first_report["counts"], {
            "forms": 8,
            "google_only": 3,
            "openslr_only": 2,
            "both_sources": 3,
            "alias_rows": 0,
        })
        google_stats = first_report["source_stats"][adapter.GOOGLE_SOURCE_ID]
        self.assertEqual(google_stats["retained_joiner_tokens"], 2)
        self.assertEqual(google_stats["retained_joiner_characters"], 2)
        self.assertEqual(google_stats["retained_zwnj"], 1)
        self.assertEqual(google_stats["retained_zwj"], 1)
        self.assertEqual(google_stats["rejected_invalid_joiner_rows"], 2)
        openslr_stats = first_report["source_stats"][adapter.OPENSLR_SOURCE_ID]
        self.assertEqual(openslr_stats["rows"], 3)
        self.assertEqual(openslr_stats["unique_prompts"], 2)
        self.assertEqual(openslr_stats["duplicate_prompt_rows"], 1)
        self.assertEqual(openslr_stats["token_occurrences"], 6)
        self.assertEqual(openslr_stats["rejected_invalid_runs"], 3)
        self.assertEqual(openslr_stats["rejected_invalid_joiner_runs"], 2)
        self.assertEqual(openslr_stats["retained_joiner_tokens"], 1)
        self.assertEqual(openslr_stats["retained_joiner_characters"], 1)
        self.assertEqual(openslr_stats["retained_zwnj"], 0)
        self.assertEqual(openslr_stats["retained_zwj"], 1)
        self.assertEqual(
            first_report["ranking"]["formula"],
            "(1000 if google_attested else 0) + round(1000 * log1p(deduplicated_openslr54_token_count))",
        )
        self.assertEqual(first_report, second_report)

        compiled = self.root / "release.nkp"
        compile_report = compile_pack(first, compiled, "release")
        self.assertEqual(compile_report["manifest"]["counts"]["candidate_surfaces"], 8)
        self.assertEqual(compile_report["manifest"]["counts"]["alias_rows"], 0)
        self.assertEqual(
            compile_report["manifest"]["pack"]["allowed_format_characters"],
            ["U+200C", "U+200D"],
        )

    def test_joiner_context_validation_rejects_whole_runs(self) -> None:
        self.assertEqual(adapter._canonical_token("गर्\u200dयो"), "गर्\u200dयो")
        self.assertEqual(adapter._canonical_token("क्\u200cष"), "क्\u200cष")
        for invalid in (
            "ालाई",
            "\u200dगर",
            "गर्\u200d",
            "स\u200dंयुक्त",
            "ग्रन्थ्\u200dालाई",
        ):
            self.assertIsNone(adapter._canonical_token(invalid))
        self.assertEqual(
            adapter._extract_transcript_tokens(
                "अ स\u200dंयुक्त ग्रन्थ्\u200dालाई आ गर्\u200dयो"
            ),
            ["अ", "आ", "गर्\u200dयो"],
        )

    def test_rejects_unpinned_sources_commit_and_wrong_license_family(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "Google Nepali lexicon SHA-256 mismatch"):
            adapter.build_release_source(self.args(self.root / "bad-source"))

        wrong_commit = self.args(self.root / "bad-commit")
        wrong_commit.google_commit = "0" * 40
        with self.assertRaisesRegex(adapter.AdapterError, "audited pin"):
            adapter.build_release_source(wrong_commit)

        self.google_license.write_text("MIT License", encoding="utf-8")
        with self.pinned_fixture_hashes():
            with self.assertRaisesRegex(adapter.AdapterError, "Attribution 4.0 International"):
                adapter.build_release_source(self.args(self.root / "bad-license"))

    def test_rejects_malformed_openslr_rows(self) -> None:
        self.openslr_transcripts.write_text("missing-tabs\n", encoding="utf-8")
        with self.pinned_fixture_hashes():
            with self.assertRaisesRegex(adapter.AdapterError, "file ID, speaker ID, and text"):
                adapter.build_release_source(self.args(self.root / "malformed"))


if __name__ == "__main__":
    unittest.main()
