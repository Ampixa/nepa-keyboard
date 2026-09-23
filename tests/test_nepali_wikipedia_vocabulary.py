from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_nepali_wikipedia_vocabulary as wikipedia


def sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NepaliWikipediaVocabularyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dump = self.root / "fixture.xml.bz2"
        self.dump_license = self.root / "dumps-legal.html"
        self.terms = self.root / "terms.html"
        self.cc_by_sa = self.root / "cc-by-sa.txt"
        encoded = """<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <page><title>नेपाल भाषा</title><ns>0</ns><id>10</id><revision><id>100</id><text>नेपाल नेपाल भाषा हो।</text></revision></page>
  <page><title>अर्को</title><ns>0</ns><id>11</id><revision><id>101</id><text>अर्को भाषा नेपाल</text></revision></page>
  <page><title>वार्ता</title><ns>1</ns><id>12</id><revision><id>102</id><text>गोप्य गोप्य</text></revision></page>
</mediawiki>""".encode("utf-8")
        self.dump.write_bytes(bz2.compress(encoded))
        self.dump_license.write_text(
            "Fixture Attribution-Share-Alike 4.0 dump notice.",
            encoding="utf-8",
        )
        self.terms.write_text("Fixture CC BY-SA 4.0 terms.", encoding="utf-8")
        self.cc_by_sa.write_text(
            "Fixture Attribution-ShareAlike 4.0 International legal code.",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def pins(self):
        return mock.patch.multiple(
            wikipedia,
            DUMP_SHA1=sha1(self.dump),
            DUMP_SHA256=sha256(self.dump),
            DUMP_BYTES=self.dump.stat().st_size,
            DUMP_LICENSE_INFO_SHA256=sha256(self.dump_license),
            DUMP_LICENSE_INFO_BYTES=self.dump_license.stat().st_size,
            WIKIMEDIA_TERMS_SHA256=sha256(self.terms),
            WIKIMEDIA_TERMS_BYTES=self.terms.stat().st_size,
            LICENSE_SHA256=sha256(self.cc_by_sa),
            LICENSE_BYTES=self.cc_by_sa.stat().st_size,
        )

    def args(self, output: Path) -> argparse.Namespace:
        return argparse.Namespace(
            dump=self.dump,
            dump_license=self.dump_license,
            terms=self.terms,
            cc_by_sa_license=self.cc_by_sa,
            output_dir=output,
        )

    def test_builds_deterministic_namespace_zero_frequency_table(self) -> None:
        first = self.root / "first"
        second = self.root / "second"
        with self.pins():
            first_manifest = wikipedia.build(self.args(first))
            second_manifest = wikipedia.build(self.args(second))

        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(
            (first / "vocabulary.jsonl").read_bytes(),
            (second / "vocabulary.jsonl").read_bytes(),
        )
        self.assertEqual(
            (first / "manifest.json").read_bytes(),
            (second / "manifest.json").read_bytes(),
        )
        self.assertEqual(
            (first / "attribution-pages.jsonl").read_bytes(),
            (second / "attribution-pages.jsonl").read_bytes(),
        )
        rows = [
            json.loads(line)
            for line in (first / "vocabulary.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        self.assertEqual(rows[0], {"count": 4, "rank": 1, "surface": "नेपाल"})
        self.assertFalse(any(row["surface"] == "गोप्य" for row in rows))
        self.assertEqual(first_manifest["counts"]["main_namespace_pages"], 2)
        self.assertEqual(
            first_manifest["counts"]["non_main_namespace_pages_skipped"],
            1,
        )
        self.assertFalse(
            first_manifest["selection_contract"]["evaluation_data_consumed"]
        )
        self.assertEqual(
            first_manifest["redistribution"]["gate"],
            wikipedia.SHIPPING_GATE,
        )
        self.assertFalse(first_manifest["redistribution"]["shipping_authority"])
        attribution_rows = [
            json.loads(line)
            for line in (first / "attribution-pages.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        self.assertEqual(len(attribution_rows), 2)
        self.assertEqual(
            attribution_rows[0],
            {
                "page_id": 10,
                "page_url": "https://ne.wikipedia.org/?curid=10",
                "revision_id": 100,
                "revision_url": "https://ne.wikipedia.org/w/index.php?oldid=100",
                "title": "नेपाल भाषा",
            },
        )
        self.assertTrue(first_manifest["redistribution"]["attribution_index_included"])
        self.assertEqual(
            first_manifest["output"]["attribution_pages"]["rows"],
            2,
        )

    def test_rejects_unpinned_dump(self) -> None:
        output = self.root / "bad"
        with self.assertRaisesRegex(
            wikipedia.WikipediaVocabularyError,
            "Wikipedia dump pin mismatch",
        ):
            wikipedia.build(self.args(output))
        self.assertFalse(output.exists())

    def test_rejects_changed_legal_document_without_output(self) -> None:
        output = self.root / "bad-legal"
        pins = self.pins()
        with pins:
            self.terms.write_text("changed CC BY-SA 4.0 terms", encoding="utf-8")
            with self.assertRaisesRegex(
                wikipedia.WikipediaVocabularyError,
                "Wikimedia Terms of Use pin mismatch",
            ):
                wikipedia.build(self.args(output))
        self.assertFalse(output.exists())

    def test_refuses_to_overwrite_existing_evidence(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        marker = output / "marker"
        marker.write_text("preserve", encoding="utf-8")
        with self.pins(), self.assertRaisesRegex(
            wikipedia.WikipediaVocabularyError,
            "refusing to overwrite evidence",
        ):
            wikipedia.build(self.args(output))
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
