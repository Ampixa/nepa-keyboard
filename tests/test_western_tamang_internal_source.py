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
from tools import build_western_tamang_internal_source as adapter


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class WesternTamangInternalSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "tdg_nep_lexicon.tsv"
        self.input.write_text(
            "tdg_headword\tnepali_gloss\tenglish_gloss\n"
            "  अ   लब  \tबहु शब्द\tmultiword\n"
            "अँ:\tविस्मय\texclamation\n"
            "अक्\u200dग्रेन्\tजोड\tjoined\n"
            "अङ्\u200cर\tजोड\tjoined\n"
            "वा़से\tनुक्ता\tnukta\n"
            "एः\tस्वर\tvowel\n"
            "एः\tदोहोरिएको\tduplicate\n"
            "क८\tअङ्क\tdigit\n"
            "Tamang\tग्लस\tvalid gloss must not rescue the row\n"
            "क😀\tचिन्ह\tsymbol\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, output: str = "source") -> argparse.Namespace:
        return argparse.Namespace(
            apk_tsv=self.input,
            output=self.root / output,
            data_version="1.0.0",
            max_suggestions=8,
        )

    def build(self, output: str = "source") -> dict[str, object]:
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 10),
        ):
            return adapter.build_internal_source(self.args(output))

    def test_builds_headword_only_tables_with_stable_line_ids(self) -> None:
        report = self.build()
        output = self.root / "source"
        forms = read_jsonl(output / "forms.jsonl")
        rejected = read_jsonl(output / "rejected-rows.jsonl")

        self.assertEqual(
            [row["surface"] for row in forms],
            [
                "अ लब",
                "अँ:",
                "अक्\u200dग्रेन्",
                "अङ्\u200cर",
                "एः",
                "एः",
                "क८",
                "वा़से",
            ],
        )
        self.assertEqual(
            {row["form_id"] for row in forms},
            {
                "tdg:apk:line-000002",
                "tdg:apk:line-000003",
                "tdg:apk:line-000004",
                "tdg:apk:line-000005",
                "tdg:apk:line-000006",
                "tdg:apk:line-000007",
                "tdg:apk:line-000008",
                "tdg:apk:line-000009",
            },
        )
        self.assertTrue(all(row["rank_score"] == adapter.RANK_SCORE for row in forms))
        self.assertEqual((output / "aliases.jsonl").read_bytes(), b"")
        self.assertEqual(
            rejected,
            [
                {
                    "line": 10,
                    "raw_headword": "Tamang",
                    "reason": "outside_devanagari",
                },
                {
                    "line": 11,
                    "raw_headword": "क😀",
                    "reason": "unsupported_symbol",
                },
            ],
        )
        self.assertNotIn("ग्लस", {row["surface"] for row in forms})
        self.assertEqual(report["stats"]["accepted_rows"], 8)
        self.assertEqual(report["stats"]["rejected_rows"], 2)
        self.assertEqual(report["stats"]["normalized_rows"], 1)
        self.assertEqual(report["stats"]["distinct_accepted_surfaces"], 7)

        pack = json.loads((output / "pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["pack_id"], "tdg-Deva-NP")
        self.assertEqual(pack["language"], "tdg")
        self.assertEqual(pack["variety"], "Western Tamang")
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
        self.assertEqual(first["manifest"]["counts"]["source_forms"], 8)
        self.assertEqual(first["manifest"]["counts"]["candidate_surfaces"], 7)
        self.assertEqual(first["manifest"]["counts"]["duplicate_surfaces_merged"], 1)
        self.assertEqual(first["manifest"]["indexes"]["aliases"]["keys"], 0)
        with KeyboardPack(pack_a) as pack:
            self.assertEqual(
                [row["surface"] for row in pack.lookup("अक्\u200d", "surface")],
                ["अक्\u200dग्रेन्"],
            )
            self.assertEqual(
                [row["surface"] for row in pack.lookup("अङ्\u200c", "surface")],
                ["अङ्\u200cर"],
            )
            self.assertEqual(
                [row["surface"] for row in pack.lookup("ए", "surface")],
                ["एः"],
            )
        with self.assertRaisesRegex(PackValidationError, "release build blocked"):
            compile_pack(
                self.root / "source-a",
                self.root / "must-not-release.nkp",
                "release",
            )

    def test_accepts_required_scalars_and_contextual_joiners(self) -> None:
        for surface in (
            "अक्\u200dग्रेन्",
            "अङ्\u200cर",
            "एः",
            "वा़से",
            "क८",
            "अ लब",
        ):
            self.assertIsNone(adapter._validate_surface(surface), surface)

        self.assertEqual(adapter._validate_surface("क\u200dय"), "invalid_joiner_context")
        self.assertEqual(adapter._validate_surface("\u200dक"), "invalid_joiner_context")
        self.assertEqual(
            adapter._validate_surface("क\u2060य"),
            "unsupported_format_character",
        )
        self.assertEqual(adapter._validate_surface("क😀"), "unsupported_symbol")
        self.assertEqual(adapter._validate_surface("Tamang"), "outside_devanagari")
        self.assertEqual(adapter._validate_surface(":"), "no_devanagari_letter")

    def test_rejects_unpinned_malformed_or_drifted_input(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "SHA-256 mismatch"):
            adapter.build_internal_source(self.args())

        self.input.write_text(
            "wrong\theader\nअ\tएक\n",
            encoding="utf-8",
        )
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 1),
            self.assertRaisesRegex(adapter.AdapterError, "header"),
        ):
            adapter.build_internal_source(self.args())

        self.input.write_text(
            "tdg_headword\tnepali_gloss\tenglish_gloss\nअ\tएक\tone\textra\n",
            encoding="utf-8",
        )
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 1),
            self.assertRaisesRegex(adapter.AdapterError, "wrong number of columns"),
        ):
            adapter.build_internal_source(self.args())

        self.input.write_text(
            "tdg_headword\tnepali_gloss\tenglish_gloss\nअ\tएक\tone\n",
            encoding="utf-8",
        )
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 2),
            self.assertRaisesRegex(adapter.AdapterError, "row count mismatch"),
        ):
            adapter.build_internal_source(self.args())

    def test_rejects_invalid_data_version_and_suggestion_bounds(self) -> None:
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 10),
        ):
            invalid_version = self.args("invalid-version")
            invalid_version.data_version = "1"
            with self.assertRaisesRegex(adapter.AdapterError, "semantic"):
                adapter.build_internal_source(invalid_version)

            for value in (0, 33):
                invalid_suggestions = self.args(f"invalid-suggestions-{value}")
                invalid_suggestions.max_suggestions = value
                with self.subTest(max_suggestions=value):
                    with self.assertRaisesRegex(
                        adapter.AdapterError,
                        "max suggestions",
                    ):
                        adapter.build_internal_source(invalid_suggestions)


if __name__ == "__main__":
    unittest.main()
