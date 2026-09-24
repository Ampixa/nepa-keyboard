from __future__ import annotations

import unittest
from unittest import mock

from tools import build_lepcha_candidate_source as adapter


class LepchaCandidateSourceTest(unittest.TestCase):
    def test_separates_lemmas_from_script_reference_entries(self) -> None:
        raw = (
            "ᰀᰈᰫ\n"
            "ᰁᰩᰵ\n"
            "ᰀ\n"
            "ᰦ\n"
            "-ᰀᰦ\n"
            "ᰀᰈ ᰁᰩ\n"
        ).encode("utf-8")
        with mock.patch.object(adapter, "EXPECTED_ROWS", 6):
            forms, rejected, stats = adapter._read_rows(raw)
        self.assertEqual({form["surface"] for form in forms}, {"ᰀᰈᰫ", "ᰁᰩᰵ"})
        self.assertEqual({form["rank_score"] for form in forms}, {adapter.RANK_SCORE})
        self.assertEqual(
            [(row["line"], row["reason"]) for row in rejected],
            [
                (3, "standalone_script_letter"),
                (4, "no_lepcha_letter"),
                (5, "outside_lepcha"),
                (6, "contains_whitespace"),
            ],
        )
        self.assertEqual(stats["accepted_rows"], 2)
        self.assertEqual(stats["rejected_rows"], 4)

    def test_rejects_digits_and_zero_width_space(self) -> None:
        self.assertEqual(adapter._validate_surface("᱁"), "non_letter_mark")
        self.assertEqual(adapter._validate_surface("ᰀ\u200bᰁ"), "outside_lepcha")


if __name__ == "__main__":
    unittest.main()
