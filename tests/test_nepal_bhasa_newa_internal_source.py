from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nepa_keyboard.compiler import compile_pack
from nepa_keyboard.runtime import KeyboardPack
from tools import build_nepal_bhasa_newa_internal_source as adapter


class NepalBhasaNewaInternalSourceTests(unittest.TestCase):
    def _build(self, raw: bytes, output: Path) -> dict[str, object]:
        source = output.parent / "fixture.txt"
        source.write_bytes(raw)
        with (
            mock.patch.object(adapter, "SOURCE_SHA256", hashlib.sha256(raw).hexdigest()),
            mock.patch.object(adapter, "EXPECTED_DATA_ROWS", len(raw.decode("utf-8").splitlines())),
        ):
            return adapter.build_internal_source(
                argparse.Namespace(
                    prachalit_corpus=source,
                    output=output,
                    data_version="1.0.0",
                    max_suggestions=8,
                )
            )

    def test_strict_attested_tokenization_and_frequency_ranking(self) -> None:
        raw = (
            "𑐣𑐾𑐥𑐵𑐮 𑐣𑐾𑐥𑐵𑐮𑑋 Latin\n"
            "𑐎𑑂‍𑐰 𑐎𑑂‍\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "source"
            report = self._build(raw, output)
            forms = [
                json.loads(line)
                for line in (output / "forms.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            by_surface = {row["surface"]: row for row in forms}

            self.assertEqual(set(by_surface), {"𑐎𑑂‍𑐰", "𑐣𑐾𑐥𑐵𑐮"})
            self.assertEqual(by_surface["𑐣𑐾𑐥𑐵𑐮"]["rank_score"], 1002)
            self.assertEqual(by_surface["𑐎𑑂‍𑐰"]["rank_score"], 1001)
            self.assertTrue(all(row["evidence"] == "attested" for row in forms))
            self.assertEqual(report["stats"]["accepted_rows"], 3)
            self.assertEqual(report["stats"]["rejected_rows"], 2)
            self.assertEqual(report["stats"]["rejected_outside_newa"], 1)
            self.assertEqual(report["stats"]["rejected_invalid_joiner_context"], 1)
            self.assertEqual((output / "aliases.jsonl").read_bytes(), b"")

    def test_source_and_pack_are_byte_deterministic_and_queryable(self) -> None:
        raw = "𑐣𑐾𑐥𑐵𑐮 𑐣𑐾𑐥𑐵𑐮𑐮𑐶𑐥𑐶\n".encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_a = root / "a"
            source_b = root / "b"
            self._build(raw, source_a)
            self._build(raw, source_b)
            self.assertEqual(
                {path.name: path.read_bytes() for path in source_a.iterdir()},
                {path.name: path.read_bytes() for path in source_b.iterdir()},
            )

            pack_a = root / "pack-a" / "new-Newa-NP.nkp"
            pack_b = root / "pack-b" / "new-Newa-NP.nkp"
            compile_pack(source_a, pack_a, "internal")
            compile_pack(source_b, pack_b, "internal")
            self.assertEqual(pack_a.read_bytes(), pack_b.read_bytes())
            with KeyboardPack(pack_a) as pack:
                rows = pack.lookup("𑐣𑐾", "surface")
            self.assertEqual(rows[0]["surface"], "𑐣𑐾𑐥𑐵𑐮")

    def test_rejects_source_hash_and_non_nfc_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.txt"
            source.write_text("𑐣𑐾𑐥𑐵𑐮\n", encoding="utf-8")
            args = argparse.Namespace(
                prachalit_corpus=source,
                output=root / "out",
                data_version="1.0.0",
                max_suggestions=8,
            )
            with self.assertRaisesRegex(adapter.AdapterError, "SHA-256 mismatch"):
                adapter.build_internal_source(args)

            raw = "e\u0301\n".encode("utf-8")
            # The adapter rejects normalization drift before script filtering.
            with self.assertRaisesRegex(adapter.AdapterError, "not NFC"):
                self._build(raw, root / "non-nfc")


if __name__ == "__main__":
    unittest.main()
