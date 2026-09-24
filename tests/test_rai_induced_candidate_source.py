from __future__ import annotations

import json
import unittest

from tools import build_rai_induced_candidate_source as adapter


def row(surface: str, *, language: str = "aph", score: float = 0.3) -> str:
    return json.dumps({
        "rai": surface,
        "nepali": "अलग",
        "score": score,
        "cooc": 3,
        "p_rai_given_nep": 0.4,
        "p_nep_given_rai": 0.5,
        "lang": language,
        "method": "ibm1-symmetrized",
        "source": "induced/bible",
    }, ensure_ascii=False)


class RaiInducedCandidateSourceTest(unittest.TestCase):
    def test_preserves_valid_joiners_and_rejects_editorial_shapes(self) -> None:
        spec = adapter.RaiSpec("aph", "Athpahariya", "fixture.jsonl", "0" * 64, 5)
        raw = "\n".join((
            row("आग्\u200dयाँ"),
            row("आग्\u200cयाँ"),
            row("आग्\u200c"),
            row("अ“गा"),
            row("आग\u200dया"),
        )) + "\n"
        forms, rejected, stats = adapter._read_rows(raw.encode("utf-8"), spec)
        self.assertEqual(
            {form["surface"] for form in forms},
            {"आग्\u200dयाँ", "आग्\u200cयाँ", "आग्\u200c"},
        )
        self.assertEqual({form["evidence"] for form in forms}, {"induced"})
        self.assertEqual({form["rank_score"] for form in forms}, {adapter.RANK_SCORE})
        self.assertEqual(
            [(item["line"], item["reason"]) for item in rejected],
            [(4, "editorial_quote"), (5, "invalid_joiner_context")],
        )
        self.assertEqual(stats["accepted_joiner_rows"], 3)
        self.assertEqual(stats["rejected_rows"], 2)

    def test_requires_matching_language_and_numeric_contract(self) -> None:
        spec = adapter.RaiSpec("aph", "Athpahariya", "fixture.jsonl", "0" * 64, 1)
        with self.assertRaisesRegex(adapter.AdapterError, "source contract"):
            adapter._read_rows((row("आगा", language="kle") + "\n").encode(), spec)
        with self.assertRaisesRegex(adapter.AdapterError, "out-of-range score"):
            adapter._read_rows((row("आगा", score=1.2) + "\n").encode(), spec)
        self.assertEqual(adapter._validate_surface("्"), "no_devanagari_letter")
        self.assertEqual(adapter._validate_surface("आग्\u200d\u200cया"), "invalid_joiner_context")


if __name__ == "__main__":
    unittest.main()
