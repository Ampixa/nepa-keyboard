from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from nepa_keyboard.compiler import compile_pack
from tools import build_nepali_roman_release_source as adapter
from tools import evaluate_nepali_roman_pack as evaluator
from tools import generate_indicxlit_nepali_aliases as indicxlit


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value: object) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member_sha256(path: Path, member: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return hashlib.sha256(archive.read(member)).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class NepaliRomanReleaseSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.direct = self.root / "direct"
        self.direct.mkdir()
        self.google = self.root / "lexicon.tsv"
        self.card = self.root / "README.md"
        self.cc_by = self.root / "cc-by.txt"
        self.cc0 = self.root / "cc0.txt"
        self.archive = self.root / "nep.zip"
        self.indicxlit_aliases = self.root / "indicxlit-aliases.jsonl"
        self.indicxlit_manifest = self.root / "indicxlit-manifest.json"
        self.indicxlit_license = self.root / "indicxlit-LICENSE"

        self.forms = [
            {
                "form_id": "npi:akshar",
                "surface": "अक्षर",
                "rank_score": 800,
                "source_ids": [adapter.GOOGLE_SOURCE_ID],
                "evidence": "attested",
            },
            {
                "form_id": "npi:nepal",
                "surface": "नेपाल",
                "rank_score": 1000,
                "source_ids": [adapter.GOOGLE_SOURCE_ID],
                "evidence": "attested",
            },
            {
                "form_id": "npi:phul",
                "surface": "फूल",
                "rank_score": 900,
                "source_ids": [adapter.GOOGLE_SOURCE_ID],
                "evidence": "attested",
            },
            {
                "form_id": "npi:bachan",
                "surface": "वचन",
                "rank_score": 700,
                "source_ids": [adapter.GOOGLE_SOURCE_ID],
                "evidence": "attested",
            },
        ]
        write_json(
            self.direct / "pack.json",
            {
                "pack_id": adapter.PACK_ID,
                "language": "npi",
                "display_name": "Nepali",
                "variety": None,
                "output_script": "Deva",
                "region": "NP",
                "data_version": "1.0.0",
                "max_suggestions": 8,
                "artifact_license": "CC-BY-SA-4.0",
                "allowed_format_characters": ["U+200C", "U+200D"],
            },
        )
        write_jsonl(
            self.direct / "sources.jsonl",
            [
                {
                    "source_id": adapter.GOOGLE_SOURCE_ID,
                    "title": "Fixture Google Nepali lexicon",
                    "method": "nfc_devanagari_headword_extraction",
                    "license": "CC-BY-4.0",
                    "redistribution": "allowed",
                    "sha256": "a" * 64,
                    "source_url": "https://example.test/lexicon.tsv",
                    "project_url": "https://example.test/google",
                    "license_url": adapter.CC_BY_4_LEGALCODE_URL,
                    "license_notice": (
                        "Fixture extracts spellings and omits the pronunciations."
                    ),
                    "changes": "Fixture spelling extraction.",
                }
            ],
        )
        write_jsonl(self.direct / "forms.jsonl", self.forms)
        (self.direct / "aliases.jsonl").write_bytes(b"")
        write_json(self.direct / "adapter-report.json", {"direct_only": True})

        self.google.write_text(
            "# Fixture pronunciation lexicon\n"
            "अक्षर\tax k . tsh y ax r\n"
            "नेपाल\tn e . p aa l\n"
            "फूल\tph u l\n"
            "वचन\tb ax . ts ax n\n"
            "बाहिर\tb aa . h i r\n",
            encoding="utf-8",
        )
        self.card.write_text(
            "Nepali (nep)\n"
            "Manually collected data: Released under CC-BY license.\n"
            "Mined dataset (from Samanantar and IndicCorp): Released under CC0 license.\n"
            "We do not own any of the text from which this data has been extracted.\n",
            encoding="utf-8",
        )
        self.cc_by.write_text(
            "Creative Commons Attribution 4.0 International fixture legalcode.",
            encoding="utf-8",
        )
        self.cc0.write_text(
            "Creative Commons CC0 1.0 Universal fixture legalcode.",
            encoding="utf-8",
        )
        self.train_rows = [
            {
                "unique_identifier": "nep1",
                "native word": "नेपाल",
                "english word": "nepal",
                "source": "AK-Freq",
                "score": None,
            },
            {
                "unique_identifier": "nep2",
                "native word": "फूल",
                "english word": "phul",
                "source": "IndicCorp",
                "score": -0.1,
            },
            {
                "unique_identifier": "nep3",
                "native word": "अक्षर",
                "english word": "akshar",
                "source": "Wikidata",
                "score": None,
            },
            {
                "unique_identifier": "nep4",
                "native word": "बाहिर",
                "english word": "bahira",
                "source": "AK-Freq",
                "score": None,
            },
        ]
        self.valid_rows = [
            {
                "unique_identifier": "nep1",
                "native word": "वचन",
                "english word": "devonly",
                "source": "AK-Uni",
                "score": None,
            }
        ]
        self.test_rows = [
            {
                "unique_identifier": "nep1",
                "native word": "नेपाल",
                "english word": "nepal",
                "source": "AK-Freq",
            },
            {
                "unique_identifier": "nep2",
                "native word": "फूल",
                "english word": "ful",
                "source": "AK-Freq",
            },
            {
                "unique_identifier": "nep3",
                "native word": "अक्षर",
                "english word": "akshar",
                "source": "AK-NEI",
            },
            {
                "unique_identifier": "nep4",
                "native word": "बाहिर",
                "english word": "secret",
                "source": "AK-Freq",
            },
        ]
        self.write_archive()
        self.write_indicxlit_fixture()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_archive(self) -> None:
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_STORED) as archive:
            for member, rows in (
                ("nep_test.json", self.test_rows),
                ("nep_train.json", self.train_rows),
                ("nep_valid.json", self.valid_rows),
            ):
                archive.writestr(
                    member,
                    "".join(canonical_json(row) + "\n" for row in rows),
                )

    def write_indicxlit_fixture(self) -> None:
        rows = [
            {
                "alias": alias,
                "beam_rank": 1,
                "form_id": form["form_id"],
                "surface": form["surface"],
            }
            for alias, form in zip(
                ("akshar", "nepal", "ful", "bachan"),
                self.forms,
                strict=True,
            )
        ]
        write_jsonl(self.indicxlit_aliases, rows)
        self.indicxlit_license.write_text(
            "MIT License\n\nCopyright (c) 2022 AI4Bhārat\n\nFixture terms.",
            encoding="utf-8",
        )
        write_json(
            self.indicxlit_manifest,
            {
                "generator": "generate_indicxlit_nepali_aliases",
                "generator_version": indicxlit.GENERATOR_VERSION,
                "pack_id": adapter.PACK_ID,
                "model_direction": "Nepali Devanagari to Roman",
                "decoding": {
                    "beam": 4,
                    "nbest": 4,
                    "batch_size": 4,
                    "cpu": True,
                    "seed": 1,
                    "threads": 1,
                    "fairseq_task": "translation_multi_simple_epoch",
                    "source_language": "ne",
                    "target_language": "en",
                    "encoder_langtok": "src",
                },
                "inputs": {
                    "direct_forms": {
                        "sha256": sha256(self.direct / "forms.jsonl"),
                        "rows": len(self.forms),
                    },
                    "model_archive": {
                        "sha256": indicxlit.INDICXLIT_MODEL_ARCHIVE_SHA256,
                        "checkpoint_sha256": indicxlit.INDICXLIT_CHECKPOINT_SHA256,
                        "ne_dictionary_sha256": indicxlit.INDICXLIT_NE_DICT_SHA256,
                        "en_dictionary_sha256": indicxlit.INDICXLIT_EN_DICT_SHA256,
                    },
                    "indicxlit": {
                        "commit": indicxlit.INDICXLIT_REPO_COMMIT,
                        "license": "MIT",
                        "license_sha256": sha256(self.indicxlit_license),
                        "lang_list_sha256": indicxlit.INDICXLIT_LANG_LIST_SHA256,
                    },
                },
                "outputs": {
                    "aliases_sha256": sha256(self.indicxlit_aliases),
                    "fairseq_output_sha256": "b" * 64,
                    "counts": {
                        "forms": len(self.forms),
                        "alias_rows": len(rows),
                    },
                },
                "evaluation_data_consumed": False,
            },
        )

    def fixture_constants(self):
        direct_hashes = {
            filename: sha256(self.direct / filename)
            for filename in adapter.DIRECT_SOURCE_SHA256
        }
        member_hashes = {
            member: member_sha256(self.archive, member)
            for member in adapter.AKSHARANTAR_MEMBER_SHA256
        }
        member_rows = {
            "nep_train.json": len(self.train_rows),
            "nep_valid.json": len(self.valid_rows),
            "nep_test.json": len(self.test_rows),
        }
        return mock.patch.multiple(
            adapter,
            DIRECT_SOURCE_SHA256=direct_hashes,
            DIRECT_FORM_COUNT=len(self.forms),
            AKSHARANTAR_ARCHIVE_SHA256=sha256(self.archive),
            AKSHARANTAR_CARD_SHA256=sha256(self.card),
            AKSHARANTAR_MEMBER_SHA256=member_hashes,
            AKSHARANTAR_MEMBER_ROWS=member_rows,
            GOOGLE_LEXICON_SHA256=sha256(self.google),
            CC_BY_4_LEGALCODE_SHA256=sha256(self.cc_by),
            CC0_1_LEGALCODE_SHA256=sha256(self.cc0),
        )

    def args(self, output: Path) -> argparse.Namespace:
        return argparse.Namespace(
            direct_source=self.direct,
            aksharantar_archive=self.archive,
            aksharantar_card=self.card,
            google_lexicon=self.google,
            cc_by_license=self.cc_by,
            cc0_license=self.cc0,
            output=output,
            data_version="1.1.0",
            max_suggestions=8,
            indicxlit_aliases=None,
            indicxlit_manifest=None,
            indicxlit_license=None,
        )

    def test_builds_deterministic_release_source_without_rights_or_split_leakage(self) -> None:
        first = self.root / "first"
        second = self.root / "second"
        with self.fixture_constants():
            first_report = adapter.build_release_source(self.args(first))
            second_report = adapter.build_release_source(self.args(second))

        for filename in (
            "pack.json",
            "sources.jsonl",
            "forms.jsonl",
            "aliases.jsonl",
            "adapter-report.json",
        ):
            self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())
        self.assertEqual(
            (first / "forms.jsonl").read_bytes(),
            (self.direct / "forms.jsonl").read_bytes(),
        )

        aliases = read_jsonl(first / "aliases.jsonl")
        self.assertTrue(any(row["alias"] == "nepal" for row in aliases))
        self.assertTrue(any(row["alias"] == "akshar" for row in aliases))
        self.assertTrue(any(row["alias"] == "ful" for row in aliases))
        self.assertFalse(any(row["alias"] == "devonly" for row in aliases))
        self.assertFalse(any(row["alias"] == "secret" for row in aliases))
        self.assertFalse(
            any("indiccorp" in str(row["scheme"]).lower() for row in aliases)
        )
        self.assertEqual(
            first_report["split_contract"]["join_stats"]["excluded_rights_IndicCorp"],
            1,
        )
        self.assertFalse(
            first_report["split_contract"]["members"]["nep_valid.json"]["used_in_pack"]
        )
        self.assertFalse(
            first_report["split_contract"]["members"]["nep_test.json"]["used_in_pack"]
        )
        self.assertEqual(first_report, second_report)

        sources = {
            row["source_id"]: row for row in read_jsonl(first / "sources.jsonl")
        }
        self.assertIn(adapter.AKSHARANTAR_FREQ_SOURCE_ID, sources)
        self.assertIn(adapter.AKSHARANTAR_WIKIDATA_SOURCE_ID, sources)
        self.assertNotIn("omits the pronunciations", sources[adapter.GOOGLE_SOURCE_ID]["license_notice"])
        self.assertIn("phoneme-to-Roman", sources[adapter.GOOGLE_SOURCE_ID]["license_notice"])

        compiled = self.root / "roman.nkp"
        compile_report = compile_pack(first, compiled, "release")
        self.assertEqual(compile_report["manifest"]["counts"]["candidate_surfaces"], 4)
        self.assertGreater(compile_report["manifest"]["counts"]["alias_keys"], 4)

    def test_rejects_unpinned_inputs_and_unreviewed_joined_source(self) -> None:
        with self.assertRaisesRegex(adapter.RomanAdapterError, "direct source pack.json SHA-256 mismatch"):
            adapter.build_release_source(self.args(self.root / "unpatched"))

        self.train_rows.append(
            {
                "unique_identifier": "nep5",
                "native word": "नेपाल",
                "english word": "nepaal",
                "source": "Mystery",
                "score": None,
            }
        )
        self.write_archive()
        with self.fixture_constants():
            with self.assertRaisesRegex(adapter.RomanAdapterError, "unreviewed Aksharantar source"):
                adapter.build_release_source(self.args(self.root / "mystery"))

    def test_rejects_wrong_license_family(self) -> None:
        self.cc_by.write_text("MIT License", encoding="utf-8")
        with self.fixture_constants():
            with self.assertRaisesRegex(adapter.RomanAdapterError, "Attribution 4.0 International"):
                adapter.build_release_source(self.args(self.root / "wrong-license"))

    def test_held_out_evaluator_reports_full_population_and_minimum(self) -> None:
        source = self.root / "source"
        pack = self.root / "roman.nkp"
        with self.fixture_constants():
            adapter.build_release_source(self.args(source))
            compile_pack(source, pack, "release")
            report = evaluator.evaluate(
                argparse.Namespace(
                    pack=pack,
                    aksharantar_archive=self.archive,
                    minimum_cases=3,
                    output=None,
                    include_cases=False,
                )
            )
            with self.assertRaisesRegex(evaluator.EvaluationError, "minimum is 5"):
                evaluator.evaluate(
                    argparse.Namespace(
                        pack=pack,
                        aksharantar_archive=self.archive,
                        minimum_cases=5,
                        output=None,
                        include_cases=False,
                    )
                )

        self.assertEqual(report["population"]["test_rows"], 4)
        self.assertEqual(report["population"]["eligible_rows"], 3)
        self.assertEqual(report["population"]["ineligible_target_rows"], 1)
        self.assertEqual(report["population"]["target_vocabulary_coverage"], 0.75)
        self.assertEqual(report["metrics"]["closed_vocabulary"]["top1"], 3)
        self.assertEqual(report["metrics"]["closed_vocabulary"]["top1_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["end_to_end"]["top1"], 3)
        self.assertEqual(report["metrics"]["end_to_end"]["top1_accuracy"], 0.75)
        self.assertEqual(
            report["metrics"]["by_source"]["AK-Freq"]["eligible_rows"],
            2,
        )
        self.assertEqual(
            report["metrics"]["by_source"]["AK-Freq"]["target_vocabulary_coverage"],
            2 / 3,
        )
        self.assertTrue(
            report["evaluation_source"]["held_out_from_pack_alias_build"]
        )
        self.assertNotIn("cases", report)

    def test_accepts_pinned_indicxlit_generation_without_evaluation_input(self) -> None:
        output = self.root / "with-model"
        args = self.args(output)
        args.indicxlit_aliases = self.indicxlit_aliases
        args.indicxlit_manifest = self.indicxlit_manifest
        args.indicxlit_license = self.indicxlit_license
        with self.fixture_constants(), mock.patch.object(
            indicxlit,
            "INDICXLIT_LICENSE_SHA256",
            sha256(self.indicxlit_license),
        ):
            report = adapter.build_release_source(args)

        self.assertTrue(
            report["rights_decisions"]["indicxlit_model_aliases_included"]
        )
        self.assertEqual(report["indicxlit_aliases"]["forms"], 4)
        model_rows = [
            row
            for row in read_jsonl(output / "aliases.jsonl")
            if row["source_ids"] == [adapter.INDICXLIT_SOURCE_ID]
        ]
        self.assertEqual(len(model_rows), 4)
        self.assertTrue(all(row["evidence"] == "generated" for row in model_rows))
        sources = {
            row["source_id"]: row for row in read_jsonl(output / "sources.jsonl")
        }
        self.assertEqual(sources[adapter.INDICXLIT_SOURCE_ID]["license"], "MIT")

        first_semantic_hash = report["indicxlit_aliases"][
            "semantic_manifest_sha256"
        ]
        manifest = json.loads(self.indicxlit_manifest.read_text(encoding="utf-8"))
        manifest["outputs"]["fairseq_output_sha256"] = "c" * 64
        write_json(self.indicxlit_manifest, manifest)
        second_output = self.root / "with-model-second-run"
        second_args = self.args(second_output)
        second_args.indicxlit_aliases = self.indicxlit_aliases
        second_args.indicxlit_manifest = self.indicxlit_manifest
        second_args.indicxlit_license = self.indicxlit_license
        with self.fixture_constants(), mock.patch.object(
            indicxlit,
            "INDICXLIT_LICENSE_SHA256",
            sha256(self.indicxlit_license),
        ):
            second_report = adapter.build_release_source(second_args)
        self.assertEqual(
            first_semantic_hash,
            second_report["indicxlit_aliases"]["semantic_manifest_sha256"],
        )
        for filename in (
            "pack.json",
            "sources.jsonl",
            "forms.jsonl",
            "aliases.jsonl",
            "adapter-report.json",
        ):
            self.assertEqual(
                (output / filename).read_bytes(),
                (second_output / filename).read_bytes(),
            )

        manifest["evaluation_data_consumed"] = True
        write_json(self.indicxlit_manifest, manifest)
        leaked_args = self.args(self.root / "leaked-model")
        leaked_args.indicxlit_aliases = self.indicxlit_aliases
        leaked_args.indicxlit_manifest = self.indicxlit_manifest
        leaked_args.indicxlit_license = self.indicxlit_license
        with self.fixture_constants(), mock.patch.object(
            indicxlit,
            "INDICXLIT_LICENSE_SHA256",
            sha256(self.indicxlit_license),
        ):
            with self.assertRaisesRegex(
                adapter.RomanAdapterError, "evaluation_data_consumed=false"
            ):
                adapter.build_release_source(leaked_args)


if __name__ == "__main__":
    unittest.main()
