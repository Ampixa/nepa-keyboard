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
from tools import build_dhimal_internal_source as adapter


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class DhimalInternalSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "dict_webonary_nep_dhi.tsv"
        self.input.write_text(
            "nepali\tdhimal\tpos\tsource\n"
            "हजुर\tअउ\tवि.बो.\tdict_sil_webonary\n"
            "शब्द\tक्\u200dय\tn\tdict_sil_webonary\n"
            "दुई\t  क   ख  \tn\tdict_sil_webonary\n"
            "अमान्य\tDhimal\tn\tdict_sil_webonary\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, output: str = "source") -> argparse.Namespace:
        return argparse.Namespace(
            webonary_tsv=self.input,
            output=self.root / output,
            data_version="1.0.0",
            max_suggestions=8,
        )

    def build(self, output: str = "source") -> dict[str, object]:
        with (
            mock.patch.object(adapter, "WEBONARY_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 4),
        ):
            return adapter.build_internal_source(self.args(output))

    def test_builds_sorted_direct_only_tables_with_stable_line_ids(self) -> None:
        report = self.build()
        output = self.root / "source"
        forms = read_jsonl(output / "forms.jsonl")
        rejected = read_jsonl(output / "rejected-rows.jsonl")

        self.assertEqual([row["surface"] for row in forms], ["अउ", "क ख", "क्\u200dय"])
        self.assertEqual(
            {row["form_id"] for row in forms},
            {
                "dhi:webonary:line-000002",
                "dhi:webonary:line-000003",
                "dhi:webonary:line-000004",
            },
        )
        self.assertEqual((output / "aliases.jsonl").read_bytes(), b"")
        self.assertEqual(rejected, [{
            "line": 5,
            "raw_headword": "Dhimal",
            "reason": "outside_devanagari",
        }])
        self.assertEqual(report["stats"]["accepted_rows"], 3)
        self.assertEqual(report["stats"]["rejected_rows"], 1)
        self.assertEqual(report["stats"]["normalized_rows"], 1)
        pack = json.loads((output / "pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["pack_id"], "dhi-Deva-NP")
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
        self.assertEqual(first["manifest"]["counts"]["candidate_surfaces"], 3)
        self.assertEqual(first["manifest"]["indexes"]["aliases"]["keys"], 0)
        with KeyboardPack(pack_a) as pack:
            self.assertEqual(
                [row["surface"] for row in pack.lookup("क", "surface")],
                ["क ख", "क्\u200dय"],
            )
        with self.assertRaisesRegex(PackValidationError, "release build blocked"):
            compile_pack(self.root / "source-a", self.root / "must-not-release.nkp", "release")

    def test_requires_valid_joiner_context_and_rejects_symbols(self) -> None:
        self.assertIsNone(adapter._validate_surface("क्\u200dय"))
        self.assertEqual(adapter._validate_surface("क\u200dय"), "invalid_joiner_context")
        self.assertEqual(adapter._validate_surface("\u200dक"), "invalid_joiner_context")
        self.assertEqual(adapter._validate_surface("्\u200dक"), "invalid_joiner_context")
        self.assertEqual(adapter._validate_surface("क😀"), "unsupported_symbol")

    def test_rejects_unpinned_input_and_wrong_source_tag(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "SHA-256 mismatch"):
            adapter.build_internal_source(self.args())

        self.input.write_text(
            "nepali\tdhimal\tpos\tsource\n"
            "हजुर\tअउ\tवि.बो.\twrong-source\n",
            encoding="utf-8",
        )
        with (
            mock.patch.object(adapter, "WEBONARY_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 1),
            self.assertRaisesRegex(adapter.AdapterError, "unexpected source tag"),
        ):
            adapter.build_internal_source(self.args())

        self.input.write_text(
            "nepali\tdhimal\tpos\tsource\n"
            "हजुर\tअउ\tवि.बो.\tdict_sil_webonary\n",
            encoding="utf-8",
        )
        with (
            mock.patch.object(adapter, "WEBONARY_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 2),
            self.assertRaisesRegex(adapter.AdapterError, "row count mismatch"),
        ):
            adapter.build_internal_source(self.args())

        self.input.write_text("wrong\theader\n", encoding="utf-8")
        with (
            mock.patch.object(adapter, "WEBONARY_SHA256", sha256(self.input)),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 0),
            self.assertRaisesRegex(adapter.AdapterError, "header"),
        ):
            adapter.build_internal_source(self.args())


if __name__ == "__main__":
    unittest.main()
