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
from tools import build_nepal_bhasa_internal_source as adapter


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class NepalBhasaInternalSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "new_nepali_trilingual.tsv"
        self.input.write_text(
            "newar\tnepali\n"
            "  अ   लब  \tबहु शब्द\n"
            "अक्\u200dग्रे\tजोड\n"
            "अङ्\u200cर\tजोड\n"
            "क; ख\tवैकल्पिक लेखाइ\n"
            "ऱक१\tदुर्लभ चिन्ह\n"
            "अक्\u200c\tअन्तिम हलन्त\n"
            "एः\tस्वर\n"
            "एः\tदोहोरिएको\n"
            "ः\tएक्लो मात्रा\n"
            "Newar\tग्लसले पङ्क्ति बचाउनु हुँदैन\n"
            "क😀\tचिन्ह\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, output: str = "source") -> argparse.Namespace:
        return argparse.Namespace(
            trilingual_tsv=self.input,
            output=self.root / output,
            data_version="1.0.0",
            max_suggestions=8,
        )

    def build(self, output: str = "source") -> dict[str, object]:
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 11),
        ):
            return adapter.build_internal_source(self.args(output))

    def test_builds_only_unsplit_newar_cells_with_stable_line_ids(self) -> None:
        report = self.build()
        output = self.root / "source"
        forms = read_jsonl(output / "forms.jsonl")
        rejected = read_jsonl(output / "rejected-rows.jsonl")

        self.assertEqual(
            [row["surface"] for row in forms],
            [
                "अक्\u200dग्रे",
                "अङ्\u200cर",
                "एः",
                "एः",
                "ऱक१",
            ],
        )
        self.assertEqual(
            {row["form_id"] for row in forms},
            {
                "new:trilingual:line-000003",
                "new:trilingual:line-000004",
                "new:trilingual:line-000006",
                "new:trilingual:line-000008",
                "new:trilingual:line-000009",
            },
        )
        self.assertTrue(all(row["rank_score"] == adapter.RANK_SCORE for row in forms))
        self.assertEqual((output / "aliases.jsonl").read_bytes(), b"")
        self.assertEqual(
            rejected,
            [
                {
                    "line": 2,
                    "raw_headword": "  अ   लब  ",
                    "reason": "whitespace_headword",
                },
                {
                    "line": 5,
                    "raw_headword": "क; ख",
                    "reason": "alternative_delimiter",
                },
                {
                    "line": 7,
                    "raw_headword": "अक्\u200c",
                    "reason": "invalid_joiner_context",
                },
                {"line": 10, "raw_headword": "ः", "reason": "no_devanagari_letter"},
                {"line": 11, "raw_headword": "Newar", "reason": "outside_devanagari"},
                {"line": 12, "raw_headword": "क😀", "reason": "unsupported_symbol"},
            ],
        )
        self.assertNotIn("क; ख", {row["surface"] for row in forms})
        self.assertNotIn("क", {row["surface"] for row in forms})
        self.assertNotIn("ख", {row["surface"] for row in forms})
        self.assertNotIn("बहु शब्द", {row["surface"] for row in forms})
        self.assertEqual(report["candidate_column"], "newar")
        self.assertEqual(report["excluded_columns"], ["nepali"])
        self.assertEqual(report["alternative_splitting"], adapter.SPLITTING_POLICY)
        self.assertEqual(report["policies"]["joiners"], adapter.JOINER_POLICY)
        self.assertEqual(report["stats"]["accepted_rows"], 5)
        self.assertEqual(report["stats"]["rejected_rows"], 6)
        self.assertEqual(report["stats"]["normalized_rows"], 0)
        self.assertEqual(report["stats"]["distinct_accepted_surfaces"], 4)
        scalar_rows = report["accepted_scalar_inventory"]["frequencies"]
        self.assertEqual(
            {row["scalar"] for row in scalar_rows},
            {
                "U+0903",
                "U+0905",
                "U+090F",
                "U+0915",
                "U+0917",
                "U+0919",
                "U+0930",
                "U+0931",
                "U+0947",
                "U+094D",
                "U+0967",
                "U+200C",
                "U+200D",
            },
        )

        pack = json.loads((output / "pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["pack_id"], "new-Deva-NP")
        self.assertEqual(pack["language"], "new")
        self.assertEqual(pack["output_script"], "Deva")
        self.assertEqual(pack["allowed_format_characters"], ["U+200C", "U+200D"])

    def test_internal_nkp_is_byte_deterministic_and_queryable(self) -> None:
        self.build("source-a")
        self.build("source-b")
        for filename in (
            "pack.json",
            "sources.jsonl",
            "forms.jsonl",
            "aliases.jsonl",
            "rejected-rows.jsonl",
            "adapter-report.json",
        ):
            self.assertEqual(
                (self.root / "source-a" / filename).read_bytes(),
                (self.root / "source-b" / filename).read_bytes(),
            )

        pack_a = self.root / "a.nkp"
        pack_b = self.root / "b.nkp"
        first = compile_pack(self.root / "source-a", pack_a, "internal")
        second = compile_pack(self.root / "source-b", pack_b, "internal")

        self.assertEqual(pack_a.read_bytes(), pack_b.read_bytes())
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["manifest"]["release_mode"], "internal")
        self.assertEqual(first["manifest"]["counts"]["source_forms"], 5)
        self.assertEqual(first["manifest"]["counts"]["candidate_surfaces"], 4)
        self.assertEqual(first["manifest"]["counts"]["duplicate_surfaces_merged"], 1)
        self.assertEqual(first["manifest"]["indexes"]["aliases"]["keys"], 0)
        with KeyboardPack(pack_a) as pack:
            self.assertEqual(
                [row["surface"] for row in pack.lookup("अक्\u200d", "surface")],
                ["अक्\u200dग्रे"],
            )
            self.assertEqual(
                [row["surface"] for row in pack.lookup("ऱक", "surface")],
                ["ऱक१"],
            )
        with self.assertRaisesRegex(PackValidationError, "release build blocked"):
            compile_pack(
                self.root / "source-a",
                self.root / "must-not-release.nkp",
                "release",
            )

    def test_accepts_required_scalars_and_contextual_joiners(self) -> None:
        for surface in (
            "अक्\u200dग्रे",
            "अङ्\u200cर",
            "ऱक१",
            "कॅ",
            "कॉ",
            "क॑",
            "क॒",
        ):
            self.assertIsNone(adapter._validate_surface(surface), surface)

        self.assertEqual(adapter._validate_surface("क\u200dय"), "invalid_joiner_context")
        self.assertEqual(adapter._validate_surface("\u200dक"), "invalid_joiner_context")
        self.assertEqual(adapter._validate_surface("अक्\u200c"), "invalid_joiner_context")
        self.assertEqual(
            adapter._validate_surface("क\u2060य"),
            "unsupported_format_character",
        )
        self.assertEqual(adapter._validate_surface("क😀"), "unsupported_symbol")
        self.assertEqual(adapter._validate_surface("Newar"), "outside_devanagari")
        self.assertEqual(adapter._validate_surface("ः"), "no_devanagari_letter")

    def test_rejects_unpinned_malformed_or_drifted_input(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "SHA-256 mismatch"):
            adapter.build_internal_source(self.args())

        self.input.write_text("wrong\theader\nअ\tएक\n", encoding="utf-8")
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 1),
            self.assertRaisesRegex(adapter.AdapterError, "header"),
        ):
            adapter.build_internal_source(self.args())

        self.input.write_text(
            "newar\tnepali\nअ\tएक\textra\n",
            encoding="utf-8",
        )
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 1),
            self.assertRaisesRegex(adapter.AdapterError, "wrong number of columns"),
        ):
            adapter.build_internal_source(self.args())

        self.input.write_text("newar\tnepali\nअ\tएक\n", encoding="utf-8")
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 2),
            self.assertRaisesRegex(adapter.AdapterError, "row count mismatch"),
        ):
            adapter.build_internal_source(self.args())

    def test_rejects_invalid_data_version_and_suggestion_bounds(self) -> None:
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 11),
        ):
            invalid_version = self.args("invalid-version")
            invalid_version.data_version = "1"
            with self.assertRaisesRegex(adapter.AdapterError, "semantic"):
                adapter.build_internal_source(invalid_version)

            for value in (0, 33):
                invalid_suggestions = self.args(f"invalid-suggestions-{value}")
                invalid_suggestions.max_suggestions = value
                with self.subTest(max_suggestions=value):
                    with self.assertRaisesRegex(adapter.AdapterError, "max suggestions"):
                        adapter.build_internal_source(invalid_suggestions)


if __name__ == "__main__":
    unittest.main()
