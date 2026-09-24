from __future__ import annotations

import unittest
from unittest import mock

from tools import build_eastern_magar_candidate_source as adapter


class EasternMagarCandidateSourceTest(unittest.TestCase):
    def test_induced_rows_use_only_magar_headwords_with_neutral_rank(self) -> None:
        raw = (
            "mgp\tnpi\tscore\tp_fwd\tp_rev\tcooc\n"
            "वास्टै\tधेरै\t0.8555\t0.8643\t0.8468\t205\n"
            "मट्टै\tमात्र\t0.7942\t0.8300\t0.7584\t149\n"
            "दुई शब्द\tphrase\t0.1002\t0.2\t0.3\t3\n"
        ).encode("utf-8")
        with mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 3):
            forms, rejected, stats = adapter._read_rows(raw)

        self.assertEqual({row["surface"] for row in forms}, {"वास्टै", "मट्टै"})
        self.assertEqual({row["evidence"] for row in forms}, {"induced"})
        self.assertEqual({row["rank_score"] for row in forms}, {adapter.RANK_SCORE})
        self.assertEqual([(row["line"], row["reason"]) for row in rejected],
                         [(4, "contains_whitespace")])
        self.assertEqual(stats["accepted_rows"], 2)
        self.assertEqual(stats["rejected_rows"], 1)
        self.assertEqual(stats["score_gte_0_5_rows"], 2)
        self.assertEqual(stats["score_lt_0_4_rows"], 1)

    def test_rejects_wrong_contract_and_invalid_confidence(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "header"):
            adapter._read_rows(b"npi\tmgp\tscore\tp_fwd\tp_rev\tcooc\n")
        with mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 1):
            with self.assertRaisesRegex(adapter.AdapterError, "out-of-range score"):
                adapter._read_rows(
                    "mgp\tnpi\tscore\tp_fwd\tp_rev\tcooc\n"
                    "वास्टै\tधेरै\t1.2\t0.8\t0.9\t5\n".encode("utf-8")
                )
        self.assertEqual(adapter._validate_surface("्"), "no_devanagari_letter")
        self.assertEqual(adapter._validate_surface("दुई शब्द"), "contains_whitespace")


if __name__ == "__main__":
    unittest.main()
