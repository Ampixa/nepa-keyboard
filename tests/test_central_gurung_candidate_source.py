from __future__ import annotations

import unittest
from unittest import mock

from tools import build_central_gurung_candidate_source as adapter


class CentralGurungCandidateSourceTest(unittest.TestCase):
    def test_headerless_source_keeps_only_single_gurung_words(self) -> None:
        raw = (
            "नक्यु\tकुकुर\tDog\n"
            "-\tजनावर\tAnimal\n"
            "थप्ल्या म्ही\tमान्छे\tPerson\n"
            "प्रें/प्रेंद्\tनाम\tName\n"
            "ऱा\tबाख्रा\tGoat\n"
        ).encode("utf-8")
        with mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 5):
            forms, rejected, stats = adapter._read_rows(raw)

        self.assertEqual({row["surface"] for row in forms}, {"नक्यु", "ऱा"})
        self.assertEqual(
            [(row["line"], row["reason"]) for row in rejected],
            [
                (2, "dash_placeholder"),
                (3, "contains_whitespace"),
                (4, "outside_devanagari"),
            ],
        )
        self.assertEqual(stats["accepted_rows"], 2)
        self.assertEqual(stats["rejected_rows"], 3)
        self.assertEqual(stats["distinct_accepted_surfaces"], 2)
        self.assertTrue(
            all(row["source_ids"] == ["gvr-nepali-lexicon"] for row in forms)
        )

    def test_rejects_wrong_columns_and_detached_marks(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "number of columns"):
            adapter._read_rows("नक्यु\tकुकुर\n".encode("utf-8"))
        self.assertEqual(adapter._validate_surface("्"), "no_devanagari_letter")
        self.assertEqual(adapter._validate_surface("मि'"), "outside_devanagari")


if __name__ == "__main__":
    unittest.main()
