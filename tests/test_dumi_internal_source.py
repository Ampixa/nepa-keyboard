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
from tools import build_dumi_internal_source as adapter


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class DumiInternalSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "nepali-dumi.sil-apk.dict.jsonl"
        surfaces = [
            "आम्‍ना-आसाला",
            "आर्‌खु",
            "क:फु",
            "तःले",
            "ब़ह़",
            "ॽवाक्ना",
            "क:फु",
            "टाङ्‌",
            "अक्‍",
            "Dumi",
        ]
        rows = [
            {
                "lang": "dus",
                "headword": surface,
                "ne": ["नेपाली ग्लस"],
                "en": ["English gloss"],
                "source": "sil-apk/dumi",
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
            expected_data_rows=10,
        )
        with mock.patch.object(adapter, "CONFIG", fixture_config):
            return adapter.build_internal_source(self.args(output))

    def test_builds_headword_only_tables_with_reviewed_dumi_scalars(self) -> None:
        report = self.build()
        output = self.root / "source"
        forms = read_jsonl(output / "forms.jsonl")
        rejected = read_jsonl(output / "rejected-rows.jsonl")

        self.assertEqual(
            [row["surface"] for row in forms],
            [
                "आम्‍ना-आसाला",
                "आर्‌खु",
                "क:फु",
                "क:फु",
                "तःले",
                "ब़ह़",
                "ॽवाक्ना",
            ],
        )
        self.assertEqual(
            {row["form_id"] for row in forms},
            {f"dus:apk:line-{line:06d}" for line in range(1, 8)},
        )
        self.assertTrue(all(row["rank_score"] == adapter.RANK_SCORE for row in forms))
        self.assertNotIn("नेपाली ग्लस", {row["surface"] for row in forms})
        self.assertEqual((output / "aliases.jsonl").read_bytes(), b"")
        self.assertEqual(
            rejected,
            [
                {
                    "line": 8,
                    "raw_headword": "टाङ्‌",
                    "reason": "invalid_joiner_context",
                },
                {
                    "line": 9,
                    "raw_headword": "अक्‍",
                    "reason": "invalid_joiner_context",
                },
                {"line": 10, "raw_headword": "Dumi", "reason": "outside_devanagari"},
            ],
        )
        self.assertEqual(report["stats"]["accepted_rows"], 7)
        self.assertEqual(report["stats"]["accepted_terminal_zwnj_rows"], 0)
        self.assertEqual(report["stats"]["distinct_accepted_surfaces"], 6)
        self.assertEqual(report["stats"]["rejected_rows"], 3)

        pack = json.loads((output / "pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["pack_id"], "dus-Deva-NP")
        self.assertEqual(pack["language"], "dus")
        self.assertEqual(pack["variety"], "Western Kiranti")
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
        self.assertEqual(first["manifest"]["counts"]["source_forms"], 7)
        self.assertEqual(first["manifest"]["counts"]["candidate_surfaces"], 6)
        with KeyboardPack(pack_a) as pack:
            self.assertEqual(
                [row["surface"] for row in pack.lookup("आम्‍", "surface")],
                ["आम्‍ना-आसाला"],
            )
            self.assertEqual(
                [row["surface"] for row in pack.lookup("क:", "surface")],
                ["क:फु"],
            )
            self.assertEqual(
                [row["surface"] for row in pack.lookup("तः", "surface")],
                ["तःले"],
            )
        with self.assertRaisesRegex(PackValidationError, "release build blocked"):
            compile_pack(
                self.root / "source-a",
                self.root / "must-not-release.nkp",
                "release",
            )

    def test_rejects_helper_hash_source_hash_and_schema_drift(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "SHA-256 mismatch"):
            adapter.build_internal_source(self.args())
        with (
            mock.patch.object(adapter, "HELPER_SHA256", "0" * 64),
            self.assertRaisesRegex(adapter.AdapterError, "helper SHA-256 mismatch"),
        ):
            adapter.build_internal_source(self.args("bad-helper"))

        self.input.write_text(
            '{"headword":"अ","lang":"dus","ne":[],"en":[],'
            '"source":"sil-apk/dumi"}\n',
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
