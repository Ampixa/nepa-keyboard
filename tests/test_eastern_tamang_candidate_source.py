from __future__ import annotations

import unittest
from unittest import mock

from tools import build_eastern_tamang_candidate_source as adapter


class EasternTamangCandidateSourceTest(unittest.TestCase):
    def test_only_clean_single_tamang_segments_become_candidates(self) -> None:
        raw = (
            "nepali\ttamang\tenglish\n"
            "कोइला\tमेप्सोल्; गोसोल्।\tCoal\n"
            "कुनै\tथेबा जुम्बि; किन्बा।\tAny\n"
            "नाम\tनाम (पुरा०); सेना०र; पेत्पाl; छेः।\tName\n"
        ).encode("utf-8")
        with mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 3):
            forms, rejected, stats = adapter._read_rows(raw)

        self.assertEqual(
            {row["surface"] for row in forms},
            {"मेप्सोल्", "गोसोल्", "किन्बा", "छेः"},
        )
        self.assertEqual(
            [(row["line"], row["segment"], row["reason"]) for row in rejected],
            [
                (3, 1, "contains_whitespace"),
                (4, 1, "contains_whitespace"),
                (4, 2, "non_letter_mark"),
                (4, 3, "outside_devanagari"),
            ],
        )
        self.assertEqual(stats["rows"], 3)
        self.assertEqual(stats["accepted_segments"], 4)
        self.assertEqual(stats["rejected_segments"], 4)
        self.assertEqual(stats["separator_empty_segments"], 3)
        self.assertEqual(stats["segments"], 11)
        self.assertTrue(all(row["source_ids"] == ["taj-app"] for row in forms))
        self.assertTrue(all("Coal" not in row["surface"] for row in forms))

    def test_rejects_wrong_tsv_contract_and_detached_marks(self) -> None:
        wrong_header = b"tamang\tnepali\tenglish\n"
        with self.assertRaisesRegex(adapter.AdapterError, "header"):
            adapter._read_rows(wrong_header)
        self.assertEqual(adapter._validate_surface("्"), "no_devanagari_letter")
        self.assertEqual(adapter._validate_surface("अक्\u200dग"), "outside_devanagari")


if __name__ == "__main__":
    unittest.main()
