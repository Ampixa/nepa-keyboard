from __future__ import annotations

import unittest
from unittest import mock

from tools import build_western_magar_internal_source as adapter


class WesternMagarInternalSourceTest(unittest.TestCase):
    def test_candidate_selection_preserves_reviewed_joiners_and_bound_forms(self) -> None:
        raw = (
            "mrd_headword\tnepali_gloss\tenglish_gloss\n"
            "अक्\u200dग\tग्लस\tgloss\n"
            "अक्\u200c\tग्लस\tgloss\n"
            "*ढेम\tग्लस\tgloss\n"
            "गाँ\u200dके\tग्लस\tgloss\n"
            "-आक-\tग्लस\tgloss\n"
            "र/म\tग्लस\tgloss\n"
        ).encode("utf-8")
        with mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 6):
            forms, rejected, stats = adapter._read_rows(raw)

        self.assertEqual(
            {row["surface"] for row in forms},
            {"अक्\u200dग", "अक्\u200c", "-आक-", "र/म"},
        )
        self.assertEqual(
            {(row["line"], row["reason"]) for row in rejected},
            {(4, "editorial_asterisk"), (5, "invalid_joiner_context")},
        )
        self.assertEqual(stats["accepted_rows"], 4)
        self.assertEqual(stats["rejected_rows"], 2)
        self.assertEqual(stats["distinct_accepted_surfaces"], 4)
        self.assertTrue(all(row["source_ids"] == ["mrd-apk"] for row in forms))

    def test_terminal_zwnj_requires_virama_and_devanagari_base(self) -> None:
        self.assertIsNone(adapter._validate_surface("अक्\u200c"))
        self.assertEqual(
            adapter._validate_surface("अक\u200c"),
            "invalid_joiner_context",
        )
        self.assertEqual(
            adapter._validate_surface("्\u200c"),
            "invalid_joiner_context",
        )


if __name__ == "__main__":
    unittest.main()
