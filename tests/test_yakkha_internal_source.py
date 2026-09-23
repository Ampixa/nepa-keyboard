from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nepa_keyboard.compiler import PackValidationError, compile_pack
from nepa_keyboard.runtime import KeyboardPack
from tools import build_yakkha_internal_source as adapter


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class YakkhaInternalSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "nepali-yakkha.sil-apk.dict.jsonl"
        surfaces = [
            "अक्\u200dखामा",
            "अङ्\u200cखुबा",
            "एकङ्\u200c",
            "एकङ्\u200c",
            "अम\u200cर",
            "अक्\u200d",
            "Yakkha",
            "ए़स्\u200dसीमा",
        ]
        rows = [
            {
                "lang": "ybh",
                "headword": surface,
                "ne": ["नेपाली ग्लस"],
                "en": ["English gloss"],
                "source": "sil-apk/yakkha",
            }
            for surface in surfaces
        ]
        self.input.write_text(
            "".join(
                json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
                for value in rows
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, output: str = "source") -> argparse.Namespace:
        return argparse.Namespace(
            sil_apk_jsonl=self.input,
            output=self.root / output,
            data_version="1.0.0",
            max_suggestions=8,
        )

    def build(self, output: str = "source") -> dict[str, object]:
        fixture_config = dataclasses.replace(
            adapter.CONFIG,
            source_sha256=sha256(self.input),
            expected_data_rows=8,
        )
        with mock.patch.object(adapter, "CONFIG", fixture_config):
            return adapter.build_internal_source(self.args(output))

    def test_builds_headword_only_tables_with_terminal_zwnj_and_stable_ids(self) -> None:
        report = self.build()
        output = self.root / "source"
        forms = read_jsonl(output / "forms.jsonl")
        rejected = read_jsonl(output / "rejected-rows.jsonl")

        self.assertEqual(
            [row["surface"] for row in forms],
            [
                "अक्\u200dखामा",
                "अङ्\u200cखुबा",
                "एकङ्\u200c",
                "एकङ्\u200c",
                "ए़स्\u200dसीमा",
            ],
        )
        self.assertEqual(
            {row["form_id"] for row in forms},
            {
                "ybh:apk:line-000001",
                "ybh:apk:line-000002",
                "ybh:apk:line-000003",
                "ybh:apk:line-000004",
                "ybh:apk:line-000008",
            },
        )
        self.assertTrue(all(row["rank_score"] == adapter.RANK_SCORE for row in forms))
        self.assertNotIn("नेपाली ग्लस", {row["surface"] for row in forms})
        self.assertNotIn("English gloss", {row["surface"] for row in forms})
        self.assertEqual((output / "aliases.jsonl").read_bytes(), b"")
        self.assertEqual(
            rejected,
            [
                {"line": 5, "raw_headword": "अम\u200cर", "reason": "invalid_joiner_context"},
                {"line": 6, "raw_headword": "अक्\u200d", "reason": "invalid_joiner_context"},
                {"line": 7, "raw_headword": "Yakkha", "reason": "outside_devanagari"},
            ],
        )
        self.assertEqual(report["stats"]["accepted_rows"], 5)
        self.assertEqual(report["stats"]["accepted_terminal_zwnj_rows"], 2)
        self.assertEqual(report["stats"]["rejected_rows"], 3)
        self.assertEqual(report["stats"]["distinct_accepted_surfaces"], 4)
        self.assertEqual(report["helper"]["name"], adapter.HELPER_NAME)
        self.assertEqual(report["helper"]["sha256"], adapter.HELPER_SHA256)
        self.assertEqual(report["adapter_sha256"], sha256(Path(adapter.__file__)))
        self.assertTrue(adapter.CONFIG.allow_terminal_zwnj)

        pack = json.loads((output / "pack.json").read_text(encoding="utf-8"))
        source = read_jsonl(output / "sources.jsonl")
        self.assertEqual(pack["pack_id"], "ybh-Deva-NP")
        self.assertEqual(pack["language"], "ybh")
        self.assertEqual(pack["display_name"], "Yakkha")
        self.assertEqual(pack["variety"], "Eastern Kiranti")
        self.assertEqual(pack["allowed_format_characters"], ["U+200C", "U+200D"])
        self.assertEqual(source[0]["source_id"], "ybh-apk")
        self.assertEqual(source[0]["license"], "restricted")
        self.assertEqual(source[0]["redistribution"], "prohibited")

    def test_internal_nkp_is_byte_deterministic_queryable_and_not_releasable(self) -> None:
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
        self.assertEqual(first["manifest"]["counts"]["source_forms"], 5)
        self.assertEqual(first["manifest"]["counts"]["candidate_surfaces"], 4)
        self.assertEqual(first["manifest"]["counts"]["duplicate_surfaces_merged"], 1)
        with KeyboardPack(pack_a) as pack:
            self.assertEqual(
                [row["surface"] for row in pack.lookup("अक्\u200d", "surface")],
                ["अक्\u200dखामा"],
            )
            self.assertEqual(
                [row["surface"] for row in pack.lookup("एकङ्\u200c", "surface")],
                ["एकङ्\u200c"],
            )
        with self.assertRaisesRegex(PackValidationError, "release build blocked"):
            compile_pack(
                self.root / "source-a",
                self.root / "must-not-release.nkp",
                "release",
            )

    def test_helper_identity_is_pinned_before_output_creation(self) -> None:
        with (
            mock.patch.object(adapter, "HELPER_SHA256", "0" * 64),
            self.assertRaisesRegex(adapter.AdapterError, "helper SHA-256 mismatch"),
        ):
            adapter.build_internal_source(self.args("bad-helper"))
        self.assertFalse((self.root / "bad-helper").exists())

    def test_rejects_source_hash_and_ordered_schema_drift(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "SHA-256 mismatch"):
            adapter.build_internal_source(self.args())

        self.input.write_text(
            '{"headword":"अ","lang":"ybh","ne":[],"en":[],'
            '"source":"sil-apk/yakkha"}\n',
            encoding="utf-8",
        )
        drift_config = dataclasses.replace(
            adapter.CONFIG,
            source_sha256=sha256(self.input),
            expected_data_rows=1,
        )
        with (
            mock.patch.object(adapter, "CONFIG", drift_config),
            self.assertRaisesRegex(adapter.AdapterError, "fields.*in order"),
        ):
            adapter.build_internal_source(self.args("schema-drift"))


if __name__ == "__main__":
    unittest.main()
