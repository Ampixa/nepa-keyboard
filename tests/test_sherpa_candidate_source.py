from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_sherpa_candidate_source as adapter


ROOT = Path(__file__).resolve().parents[1]


class SherpaCandidateSourceTest(unittest.TestCase):
    def test_token_boundaries_and_conjunct_joiners(self) -> None:
        tokens = list(adapter._tokens("क्‍योक, नामा! abc १२ अङ"))
        self.assertEqual(tokens, ["क्‍योक", "नामा", "अङ"])
        self.assertTrue(all(adapter._token_rejection(token) is None for token in tokens))
        self.assertEqual(adapter._token_rejection("क्‍"), "invalid_joiner_context")
        self.assertEqual(adapter._token_rejection("कि‍म"), "invalid_joiner_context")
        self.assertEqual(adapter._token_rejection("ाक"), "leading_mark")

    def test_rejects_manifest_path_outside_pinned_tree(self) -> None:
        row = {
            "bible_id": "XSRXSR",
            "fileset_id": "XSRWBT",
            "fileset_type": "text_plain",
            "status": "downloaded",
            "book_id": "JAS",
            "chapter": 1,
            "path": "/tmp/JAS/B20_JAS_001.json",
        }
        with self.assertRaisesRegex(adapter.AdapterError, "escapes pinned source root"):
            adapter._relative_chapter_path(row)

    def test_research_layout_covers_every_accepted_scalar(self) -> None:
        inventory = json.loads((ROOT / "reports/sherpa-scalar-inventory-v0.json").read_text())
        required = {
            chr(int(row["codepoint"][2:], 16)) for row in inventory["scalars"]
        }
        basic = json.loads((ROOT / "layouts/internal/src/deva-nepal-basic-v1.json").read_text())
        candidate = json.loads((ROOT / "layouts/research/deva-nepal-sherpa-v1.json").read_text())

        def emitted(layout: dict[str, object]) -> set[str]:
            result: set[str] = set()
            for layer in layout["layers"].values():
                for row in layer["rows"]:
                    for key in row:
                        result.update(key if isinstance(key, str) else key.get("text", ""))
            return result

        self.assertEqual(required - emitted(basic), set("इईए\u200c\u200d"))
        self.assertEqual(required - emitted(candidate), set())
        for layer in ("base", "shift"):
            row = candidate["layers"][layer]["rows"][3]
            self.assertEqual(row[:3], ["इ", "ई", "ए"])
            self.assertEqual(
                [(key["kind"], key["text"]) for key in row[3:]],
                [("deva_conjunct_joiner", "\u200d"), ("deva_conjunct_joiner", "\u200c")],
            )

    def test_pinned_snapshot_build_and_chapter_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "metadata"
            metadata.mkdir()
            chapter = root / "text/XSRWBT/JAS/B20_JAS_001.json"
            chapter.parent.mkdir(parents=True)
            manifest_row = {
                "bible_id": "XSRXSR",
                "book_id": "JAS",
                "chapter": 1,
                "fileset_id": "XSRWBT",
                "fileset_type": "text_plain",
                "path": str(adapter.SOURCE_PREFIX / "text/XSRWBT/JAS/B20_JAS_001.json"),
                "status": "downloaded",
            }
            manifest = (json.dumps(manifest_row) + "\n").encode()
            (metadata / "text_manifest.jsonl").write_bytes(manifest)
            verse = {
                "book_id": "JAS",
                "chapter": 1,
                "verse_start": 1,
                "verse_end": 1,
                "verse_text": "क्‍योक, नामा! अङ",
                "book_name": "English text cannot become a candidate",
            }
            chapter_bytes = (json.dumps([verse], ensure_ascii=False) + "\n").encode()
            chapter.write_bytes(chapter_bytes)
            relative = "XSRXSR_Sherpa/text/XSRWBT/JAS/B20_JAS_001.json"
            tree = hashlib.sha256(
                f"{relative}\0{hashlib.sha256(chapter_bytes).hexdigest()}\n".encode()
            ).hexdigest()
            args = argparse.Namespace(
                source_root=root,
                output=root / "output",
                data_version="1.0.0",
                max_suggestions=8,
            )
            with mock.patch.multiple(
                adapter,
                MANIFEST_SHA256=hashlib.sha256(manifest).hexdigest(),
                TREE_SHA256=tree,
                EXPECTED_FILES=1,
                EXPECTED_VERSES=1,
                EXPECTED_OCCURRENCES=3,
                EXPECTED_SURFACES=3,
            ):
                report = adapter.build_candidate_source(args)
                forms = [
                    json.loads(line)
                    for line in (args.output / "forms.jsonl").read_text().splitlines()
                ]
                self.assertEqual({row["surface"] for row in forms}, {"क्‍योक", "नामा", "अङ"})
                self.assertEqual({row["rank_score"] for row in forms}, {adapter.RANK_SCORE})
                self.assertEqual(report["input"]["stats"]["accepted_occurrences"], 3)
                chapter.write_bytes(chapter_bytes + b" ")
                with self.assertRaisesRegex(adapter.AdapterError, "tree SHA-256"):
                    adapter.build_candidate_source(args)


if __name__ == "__main__":
    unittest.main()
