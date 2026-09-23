from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from nepa_keyboard.compiler import PackValidationError, compile_pack
from nepa_keyboard.runtime import KeyboardPack


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


class CompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "pack.json").write_text(
            json.dumps(
                {
                    "pack_id": "npi-Deva-NP",
                    "language": "npi",
                    "display_name": "Nepali",
                    "output_script": "Deva",
                    "region": "NP",
                    "data_version": "0.1.0",
                    "max_suggestions": 4,
                }
            ),
            encoding="utf-8",
        )
        self.source_rows = [
            {
                "source_id": "open",
                "title": "Open fixture",
                "method": "fixture",
                "license": "CC0-1.0",
                "redistribution": "allowed",
                "sha256": "0" * 64,
                "source_url": "https://example.invalid/open-fixture",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "license_notice": "Open fixture dedicated to the public domain under CC0-1.0.",
            }
        ]
        self.form_rows = [
            {"form_id": "npi:nepal", "surface": "नेपाल", "rank_score": 100, "source_ids": ["open"], "evidence": "attested"},
            {"form_id": "npi:nepali", "surface": "नेपाली", "rank_score": 90, "source_ids": ["open"], "evidence": "attested"},
            {"form_id": "npi:namaste", "surface": "नमस्ते", "rank_score": 80, "source_ids": ["open"], "evidence": "attested"},
        ]
        self.alias_rows = [
            {"alias": "nepal", "form_id": "npi:nepal", "rank_delta": 0, "scheme": "fixture", "source_ids": ["open"], "evidence": "generated"},
            {"alias": "nepali", "form_id": "npi:nepali", "rank_delta": 0, "scheme": "fixture", "source_ids": ["open"], "evidence": "generated"},
            {"alias": "namaste", "form_id": "npi:namaste", "rank_delta": 0, "scheme": "fixture", "source_ids": ["open"], "evidence": "generated"},
        ]
        self._write_tables()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_tables(self) -> None:
        write_jsonl(self.source / "sources.jsonl", self.source_rows)
        write_jsonl(self.source / "forms.jsonl", self.form_rows)
        write_jsonl(self.source / "aliases.jsonl", self.alias_rows)

    def test_build_and_prefix_lookup(self) -> None:
        output = self.root / "demo.nkp"
        report = compile_pack(self.source, output, "release")
        self.assertEqual(report["manifest"]["counts"]["candidate_surfaces"], 3)
        with KeyboardPack(output) as pack:
            self.assertEqual(
                [row["surface"] for row in pack.lookup("ने", "surface")],
                ["नेपाल", "नेपाली"],
            )
            self.assertEqual(
                [row["surface"] for row in pack.lookup("NEP", "aliases")],
                ["नेपाल", "नेपाली"],
            )

    def test_artifact_is_byte_deterministic(self) -> None:
        first = self.root / "first.nkp"
        second = self.root / "second.nkp"
        compile_pack(self.source, first, "release")
        compile_pack(self.source, second, "release")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))

    def test_ascii_lower_surface_lookup_preserves_candidate_casing(self) -> None:
        metadata = json.loads((self.source / "pack.json").read_text(encoding="utf-8"))
        metadata.update({
            "pack_id": "eng-Latn-US",
            "language": "eng",
            "display_name": "English",
            "output_script": "Latn",
            "region": "US",
        })
        metadata["surface_lookup_normalization"] = "NFC+ASCII-lower"
        (self.source / "pack.json").write_text(json.dumps(metadata), encoding="utf-8")
        self.form_rows = [
            {
                "form_id": "eng:hello",
                "surface": "Hello",
                "rank_score": 100,
                "source_ids": ["open"],
                "evidence": "attested",
            }
        ]
        self.alias_rows = []
        self._write_tables()
        output = self.root / "ascii-lower.nkp"
        report = compile_pack(self.source, output, "release")
        self.assertEqual(report["manifest"]["normalization"]["surface_lookup"], "NFC+ASCII-lower")
        with KeyboardPack(output) as pack:
            self.assertEqual([row["surface"] for row in pack.lookup("hEL", "surface")], ["Hello"])

    def test_rejects_unknown_surface_lookup_normalization(self) -> None:
        metadata = json.loads((self.source / "pack.json").read_text(encoding="utf-8"))
        metadata["surface_lookup_normalization"] = "Unicode-casefold"
        (self.source / "pack.json").write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaisesRegex(PackValidationError, "surface_lookup_normalization"):
            compile_pack(self.source, self.root / "bad-normalization.nkp", "release")

    def test_release_rejects_restricted_source(self) -> None:
        self.source_rows[0]["redistribution"] = "permission_required"
        self._write_tables()
        with self.assertRaisesRegex(PackValidationError, "release build blocked"):
            compile_pack(self.source, self.root / "blocked.nkp", "release")
        compile_pack(self.source, self.root / "internal.nkp", "internal")

    def test_release_requires_pinned_source_and_license_notice(self) -> None:
        for field_name in ("sha256", "source_url", "license_url", "license_notice"):
            with self.subTest(field_name=field_name):
                original = self.source_rows[0].pop(field_name)
                self._write_tables()
                with self.assertRaisesRegex(PackValidationError, field_name):
                    compile_pack(self.source, self.root / f"missing-{field_name}.nkp", "release")
                self.source_rows[0][field_name] = original
        self._write_tables()

    def test_release_requires_share_alike_artifact_declaration(self) -> None:
        self.source_rows[0]["license"] = "CC-BY-SA-4.0"
        self._write_tables()
        with self.assertRaisesRegex(PackValidationError, "artifact_license=CC-BY-SA-4.0"):
            compile_pack(self.source, self.root / "missing-share-alike.nkp", "release")

        metadata = json.loads((self.source / "pack.json").read_text(encoding="utf-8"))
        metadata["artifact_license"] = "CC-BY-SA-4.0"
        (self.source / "pack.json").write_text(json.dumps(metadata), encoding="utf-8")
        compile_pack(self.source, self.root / "declared-share-alike.nkp", "release")

    def test_rejects_form_without_provenance(self) -> None:
        self.form_rows[0]["source_ids"] = []
        self._write_tables()
        with self.assertRaisesRegex(PackValidationError, "non-empty list"):
            compile_pack(self.source, self.root / "unproven-form.nkp", "release")

    def test_rejects_alias_without_provenance(self) -> None:
        self.alias_rows[0]["source_ids"] = []
        self._write_tables()
        with self.assertRaisesRegex(PackValidationError, "non-empty list"):
            compile_pack(self.source, self.root / "unproven-alias.nkp", "release")

    def test_rejects_non_nfc_surface(self) -> None:
        # The trailing Latin sequence is deliberately decomposed (e + acute),
        # so NFC validation fires before the separate script-range check.
        self.form_rows[0]["surface"] = "नेपालe\u0301"
        self._write_tables()
        with self.assertRaisesRegex(PackValidationError, "NFC"):
            compile_pack(self.source, self.root / "bad.nkp")

    def test_rejects_letter_outside_output_script(self) -> None:
        self.form_rows[0]["surface"] = "नेपालx"
        self._write_tables()
        with self.assertRaisesRegex(PackValidationError, "outside declared script"):
            compile_pack(self.source, self.root / "bad.nkp")

    def test_alias_collision_is_ranked_and_reported(self) -> None:
        self.alias_rows.append(
            {"alias": "nepal", "form_id": "npi:nepali", "rank_delta": 20, "scheme": "fixture", "source_ids": ["open"], "evidence": "generated"}
        )
        self._write_tables()
        output = self.root / "collision.nkp"
        report = compile_pack(self.source, output, "release")
        self.assertEqual(report["manifest"]["counts"]["alias_collisions"], 1)
        with KeyboardPack(output) as pack:
            self.assertEqual(
                [row["surface"] for row in pack.lookup("nepal", "aliases")],
                ["नेपाली", "नेपाल"],
            )


if __name__ == "__main__":
    unittest.main()
