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
from tools import build_bantawa_internal_source as adapter


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class BantawaInternalSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dictionary = self.root / "bantawa.jsonl"
        rows = [
            self.row("ka", "first"),
            self.row("kɨ", "lossy collision"),
            self.row("kʰa", "aspirated"),
            self.row("a\u0303", "nasal"),
        ]
        self.dictionary.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        self.transliterator = self.root / "bantawa_deva2ipa.py"
        self.transliterator.write_text(
            "IPA_TO_DEVA = {'ka':'का','kɨ':'का','kʰa':'खा','a\\u0303':'अँ'}\n"
            "DEVA_TO_IPA = {'का':'ka','खा':'kʰa','अँ':'a\\u0303'}\n"
            "def ipa2deva(text): return IPA_TO_DEVA[text]\n"
            "def deva2ipa(text): return DEVA_TO_IPA[text]\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def row(headword: str, gloss: str) -> dict[str, object]:
        return {
            "lang": "bap",
            "headword": headword,
            "pos": "n",
            "conj": None,
            "en": gloss,
            "n_examples": 0,
            "source": adapter.EXPECTED_ROW_SOURCE,
        }

    def args(self, output: str = "source") -> argparse.Namespace:
        return argparse.Namespace(
            dictionary_jsonl=self.dictionary,
            transliterator_python=self.transliterator,
            output=self.root / output,
            data_version="1.0.0",
            max_suggestions=8,
        )

    def build(self, output: str = "source") -> dict[str, object]:
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.dictionary)),
            mock.patch.object(
                adapter,
                "TRANSLITERATOR_SHA256",
                sha256(self.transliterator),
            ),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 4),
        ):
            return adapter.build_internal_source(self.args(output))

    def test_builds_generated_devanagari_surfaces_and_records_loss(self) -> None:
        report = self.build()
        output = self.root / "source"
        forms = read_jsonl(output / "forms.jsonl")
        self.assertEqual([row["surface"] for row in forms], ["अँ", "का", "का", "खा"])
        self.assertEqual({row["evidence"] for row in forms}, {"generated"})
        self.assertEqual((output / "aliases.jsonl").read_bytes(), b"")
        self.assertEqual((output / "rejected-rows.jsonl").read_bytes(), b"")
        stats = report["measurement"]["stats"]
        self.assertEqual(stats["exact_roundtrip_rows"], 3)
        self.assertEqual(stats["accountable_lossy_roundtrip_rows"], 1)
        self.assertEqual(stats["distinct_generated_surfaces"], 3)
        self.assertEqual(stats["collision_surfaces_across_distinct_headwords"], 1)
        self.assertEqual(report["aliases"]["rows"], 0)

    def test_internal_pack_is_deterministic_queryable_and_release_blocked(self) -> None:
        self.build("source-a")
        self.build("source-b")
        filenames = (
            "pack.json",
            "sources.jsonl",
            "forms.jsonl",
            "aliases.jsonl",
            "rejected-rows.jsonl",
            "adapter-report.json",
        )
        for filename in filenames:
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
        self.assertEqual(first["manifest"]["counts"]["candidate_surfaces"], 3)
        self.assertEqual(first["manifest"]["counts"]["duplicate_surfaces_merged"], 1)
        with KeyboardPack(pack_a) as pack:
            self.assertEqual(
                [row["surface"] for row in pack.lookup("क", "surface")],
                ["का"],
            )
            self.assertEqual(
                [row["surface"] for row in pack.lookup("ख", "surface")],
                ["खा"],
            )
        with self.assertRaisesRegex(PackValidationError, "release build blocked"):
            compile_pack(self.root / "source-a", self.root / "release.nkp", "release")

    def test_rejects_unexplained_conversion_and_unpinned_inputs(self) -> None:
        with self.assertRaisesRegex(adapter.AdapterError, "dictionary SHA-256 mismatch"):
            adapter.build_internal_source(self.args())

        self.transliterator.write_text(
            "def ipa2deva(text): return 'का'\n"
            "def deva2ipa(text): return 'wrong'\n",
            encoding="utf-8",
        )
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.dictionary)),
            mock.patch.object(
                adapter,
                "TRANSLITERATOR_SHA256",
                sha256(self.transliterator),
            ),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 4),
            self.assertRaisesRegex(adapter.AdapterError, "unexplained round-trip"),
        ):
            adapter.build_internal_source(self.args())

    def test_rejects_schema_drift_and_noncanonical_transliterator(self) -> None:
        rows = [self.row("ka", "first")]
        rows[0]["extra"] = "drift"
        self.dictionary.write_text(
            json.dumps(rows[0], ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.dictionary)),
            mock.patch.object(
                adapter,
                "TRANSLITERATOR_SHA256",
                sha256(self.transliterator),
            ),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", 1),
            self.assertRaisesRegex(adapter.AdapterError, "fields do not match"),
        ):
            adapter.build_internal_source(self.args())

        self.transliterator.unlink()
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", sha256(self.dictionary)),
            self.assertRaisesRegex(adapter.AdapterError, "regular non-symbolic"),
        ):
            adapter.build_internal_source(self.args())


if __name__ == "__main__":
    unittest.main()
