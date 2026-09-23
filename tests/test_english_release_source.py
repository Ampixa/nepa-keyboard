from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from nepa_keyboard.compiler import compile_pack
from nepa_keyboard.runtime import KeyboardPack
from tools import build_english_release_source as adapter


COMMIT = "a" * 40
FREQUENCY_COMMIT = "525f9b560de45753a5ea01069454e72e9aa541c6"
LICENSE_NOTICE = "Copyright fixture\n\nPermission is granted for this test fixture.\n"
HEL_FORMS = [
    "held",
    "helicopter",
    "helicoptered",
    "helicoptering",
    "helicopters",
    "heliport",
    "heliports",
    "helium",
    "hell",
    "hellish",
    "hello",
    "helm",
    "helmet",
    "help",
]
HEL_CONTENT = "".join(f"{word}\n" for word in HEL_FORMS).encode("ascii")
TIER_CONTENT = {
    35: b"Apple\ncan't\ncommon\nApple\n bad\ncaf\xc3\xa9\ndash-word\n" + HEL_CONTENT,
    50: b"Apple\ncan't\ncommon\nmiddle\ncan't\n" + HEL_CONTENT,
    60: b"Apple\ncan't\ncommon\nmiddle\nrare\nO'Neill\ntwo words\n\n" + HEL_CONTENT,
}
FREQUENCY_CONTENT = (
    b"hello 1000000\n"
    b"help 10\n"
    b"common 100\n"
    b"apple 50\n"
    b"o'neill 25\n"
    b"can't 20\n"
    b"outside 9999999\n"
    b"dash-word 500\n"
    b"bad not-a-count\n"
    b"rare 0\n"
    b"common 5\n"
)
FREQUENCY_README = """# FrequencyWords

The 2018 lists use the tokenized OpenSubtitles2018 source.

### License
MIT License for code.
CC-by-sa-4.0 for content.
"""
CC_BY_SA_LEGALCODE = """Creative Commons Attribution-ShareAlike 4.0 International Public License

This fixture represents the Licensed Material and Adapted Material clauses.
"""
EXPECTED_SURFACES = sorted([
    "Apple", "can't", "common", "middle", "O'Neill", "rare", *HEL_FORMS,
])


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class EnglishReleaseSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _arguments(self, root: Path) -> tuple[object, Path, dict[int, Path]]:
        root.mkdir(parents=True, exist_ok=True)
        inputs: dict[int, Path] = {}
        command = []
        for tier in adapter.TIERS:
            path = root / f"scowl-us-{tier}.txt"
            path.write_bytes(TIER_CONTENT[tier])
            inputs[tier] = path
            command.extend([
                f"--size-{tier}",
                str(path),
                f"--size-{tier}-sha256",
                hashlib.sha256(TIER_CONTENT[tier]).hexdigest(),
            ])
        notice = root / "Copyright"
        notice.write_text(LICENSE_NOTICE, encoding="utf-8")
        frequency = root / "en_50k.txt"
        frequency.write_bytes(FREQUENCY_CONTENT)
        frequency_readme = root / "FrequencyWords-README.md"
        frequency_readme.write_text(FREQUENCY_README, encoding="utf-8")
        frequency_legalcode = root / "CC-BY-SA-4.0-legalcode.txt"
        frequency_legalcode.write_text(CC_BY_SA_LEGALCODE, encoding="utf-8")
        output = root / "output"
        command.extend([
            "--output",
            str(output),
            "--upstream-commit",
            COMMIT,
            "--source-url",
            f"https://github.com/en-wl/wordlist/tree/{COMMIT}",
            "--license-url",
            f"https://github.com/en-wl/wordlist/blob/{COMMIT}/Copyright",
            "--license-notice-file",
            str(notice),
            "--frequency-file",
            str(frequency),
            "--frequency-sha256",
            hashlib.sha256(FREQUENCY_CONTENT).hexdigest(),
            "--frequency-commit",
            FREQUENCY_COMMIT,
            "--frequency-source-url",
            (
                "https://github.com/hermitdave/FrequencyWords/blob/"
                f"{FREQUENCY_COMMIT}/content/2018/en/en_50k.txt"
            ),
            "--frequency-readme",
            str(frequency_readme),
            "--frequency-readme-sha256",
            hashlib.sha256(FREQUENCY_README.encode("utf-8")).hexdigest(),
            "--frequency-legalcode-file",
            str(frequency_legalcode),
            "--data-version",
            "1.2.3",
            "--max-suggestions",
            "6",
        ])
        return adapter.build_parser().parse_args(command), output, inputs

    def test_builds_notice_complete_release_tables_and_filter_report(self) -> None:
        args, output, inputs = self._arguments(self.root / "fixture")
        report = adapter.build_source(args)

        self.assertEqual(
            sorted(path.name for path in output.iterdir()),
            [
                "adapter-report.json",
                "aliases.jsonl",
                "forms.jsonl",
                "pack.json",
                "sources.jsonl",
            ],
        )
        pack = read_json(output / "pack.json")
        self.assertEqual(pack["pack_id"], "eng-Latn-US")
        self.assertEqual(pack["artifact_license"], "CC-BY-SA-4.0")
        self.assertEqual(pack["surface_lookup_normalization"], "NFC+ASCII-lower")
        self.assertEqual((output / "aliases.jsonl").read_bytes(), b"")

        forms = read_jsonl(output / "forms.jsonl")
        self.assertEqual([row["surface"] for row in forms], EXPECTED_SURFACES)
        self.assertNotIn("outside", [row["surface"] for row in forms])
        scores = {row["surface"]: row["rank_score"] for row in forms}
        self.assertEqual(scores["Apple"], 3000 + round(1000 * math.log1p(50)))
        self.assertEqual(scores["middle"], 2000)
        self.assertEqual(scores["O'Neill"], 1000 + round(1000 * math.log1p(25)))
        self.assertEqual(scores["common"], 3000 + round(1000 * math.log1p(105)))

        forms_by_surface = {row["surface"]: row for row in forms}
        self.assertEqual(
            forms_by_surface["hello"]["source_ids"],
            [adapter.SOURCE_ID, adapter.FREQUENCY_SOURCE_ID],
        )
        self.assertEqual(forms_by_surface["middle"]["source_ids"], [adapter.SOURCE_ID])

        sources = {
            row["source_id"]: row for row in read_jsonl(output / "sources.jsonl")
        }
        source = sources[adapter.SOURCE_ID]
        for field_name in ("sha256", "source_url", "license_url", "license_notice"):
            self.assertTrue(source[field_name])
        self.assertEqual(source["upstream_commit"], COMMIT)
        self.assertEqual(source["license_notice"], LICENSE_NOTICE.strip())

        frequency_source = sources[adapter.FREQUENCY_SOURCE_ID]
        self.assertEqual(frequency_source["license"], "CC-BY-SA-4.0")
        self.assertEqual(
            frequency_source["sha256"],
            hashlib.sha256(FREQUENCY_CONTENT).hexdigest(),
        )
        self.assertEqual(frequency_source["upstream_commit"], FREQUENCY_COMMIT)
        for required_text in (
            "FrequencyWords / OpenSubtitles 2018 attribution",
            "Changes by Nepa Keyboard",
            FREQUENCY_README.strip(),
            CC_BY_SA_LEGALCODE.strip(),
        ):
            self.assertIn(required_text, frequency_source["license_notice"])

        self.assertEqual(report["counts"]["forms"], len(EXPECTED_SURFACES))
        self.assertEqual(report["counts"]["forms_ranked_by_frequency"], 6)
        self.assertEqual(report["counts"]["frequency_keys_matched"], 6)
        self.assertEqual(report["counts"]["frequency_keys_not_in_esdb"], 1)
        self.assertEqual(report["counts"]["frequency_rejected_rows"], 3)
        self.assertEqual(report["counts"]["duplicate_rows_within_tiers"], 2)
        self.assertEqual(report["counts"]["membership_counts"], {
            "35_50_60": 17,
            "50_60": 1,
            "60": 2,
        })
        self.assertEqual(report["counts"]["rejected_by_reason"], {
            "blank": 1,
            "embedded_whitespace": 1,
            "non_ascii": 1,
            "surrounding_whitespace": 1,
            "unsupported_punctuation": 1,
        })
        self.assertEqual(len(report["rejected_rows"]), 5)
        self.assertEqual(
            [
                (row["tier"], row["line"], row["value"], row["reason"])
                for row in report["rejected_rows"]
            ],
            [
                (35, 5, " bad", "surrounding_whitespace"),
                (35, 6, "café", "non_ascii"),
                (35, 7, "dash-word", "unsupported_punctuation"),
                (60, 7, "two words", "embedded_whitespace"),
                (60, 8, "", "blank"),
            ],
        )
        self.assertEqual(
            [item["duplicate_rows"] for item in report["inputs"]],
            [1, 1, 0],
        )
        self.assertEqual(
            [item["sha256"] for item in report["inputs"]],
            [hashlib.sha256(TIER_CONTENT[tier]).hexdigest() for tier in adapter.TIERS],
        )
        self.assertEqual(
            report["frequency"]["sha256"],
            hashlib.sha256(FREQUENCY_CONTENT).hexdigest(),
        )
        self.assertEqual(report["frequency"]["duplicate_rows_aggregated"], 1)
        self.assertEqual(report["frequency"]["rejected_by_reason"], {
            "invalid_count": 1,
            "key_unsupported_punctuation": 1,
            "nonpositive_count": 1,
        })
        self.assertEqual(
            [
                (row["line"], row["value"], row["reason"])
                for row in report["frequency"]["rejected_row_details"]
            ],
            [
                (8, "dash-word 500", "key_unsupported_punctuation"),
                (9, "bad not-a-count", "invalid_count"),
                (10, "rare 0", "nonpositive_count"),
            ],
        )
        self.assertEqual(
            report["ranking_formula"]["frequency_bonus"],
            "round(1000 * log1p(count))",
        )

        digest = hashlib.sha256()
        digest.update(b"nepa-keyboard:esdb-scowl-input-set:v1\0")
        for tier in adapter.TIERS:
            filename = inputs[tier].name.encode("utf-8")
            content = TIER_CONTENT[tier]
            digest.update(tier.to_bytes(2, "big"))
            digest.update(len(filename).to_bytes(8, "big"))
            digest.update(filename)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        self.assertEqual(source["sha256"], digest.hexdigest())
        self.assertEqual(report["composite_sha256"], digest.hexdigest())
        self.assertEqual(
            report["composite_sha256_domain_hex"],
            b"nepa-keyboard:esdb-scowl-input-set:v1\0".hex(),
        )

        compiled = self.root / "eng-Latn-US.nkp"
        compiler_report = compile_pack(output, compiled, "release")
        self.assertEqual(
            compiler_report["manifest"]["counts"]["candidate_surfaces"],
            len(EXPECTED_SURFACES),
        )
        self.assertEqual(compiler_report["manifest"]["counts"]["alias_rows"], 0)
        with KeyboardPack(compiled) as keyboard_pack:
            self.assertEqual(keyboard_pack.lookup("hel", "surface")[0]["surface"], "hello")

    def test_rejects_unpinned_or_mislicensed_frequency_inputs(self) -> None:
        args, output, _ = self._arguments(self.root / "frequency-hash")
        args.frequency_sha256 = "0" * 64
        with self.assertRaisesRegex(adapter.AdapterError, "frequency SHA-256 mismatch"):
            adapter.build_source(args)
        self.assertFalse(output.exists())

        args, output, _ = self._arguments(self.root / "frequency-readme")
        invalid_readme = "# FrequencyWords\n\nMIT License for code and content.\n"
        args.frequency_readme.write_text(invalid_readme, encoding="utf-8")
        args.frequency_readme_sha256 = hashlib.sha256(
            invalid_readme.encode("utf-8")
        ).hexdigest()
        with self.assertRaisesRegex(adapter.AdapterError, "CC-by-sa-4.0 for content"):
            adapter.build_source(args)
        self.assertFalse(output.exists())

        args, output, _ = self._arguments(self.root / "frequency-legalcode")
        args.frequency_legalcode_file.write_text(
            "Creative Commons Attribution 4.0 International Public License\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(adapter.AdapterError, "Attribution-ShareAlike 4.0"):
            adapter.build_source(args)
        self.assertFalse(output.exists())

        args, output, _ = self._arguments(self.root / "frequency-url")
        args.frequency_source_url = (
            "https://github.com/hermitdave/FrequencyWords/blob/main/"
            "content/2018/en/en_50k.txt"
        )
        with self.assertRaisesRegex(adapter.AdapterError, "complete path segment"):
            adapter.build_source(args)
        self.assertFalse(output.exists())

    def test_output_is_deterministic_across_directories(self) -> None:
        first_args, first_output, _ = self._arguments(self.root / "first")
        second_args, second_output, _ = self._arguments(self.root / "second")
        adapter.build_source(first_args)
        adapter.build_source(second_args)

        for filename in (
            "pack.json",
            "sources.jsonl",
            "forms.jsonl",
            "aliases.jsonl",
            "adapter-report.json",
        ):
            with self.subTest(filename=filename):
                self.assertEqual(
                    (first_output / filename).read_bytes(),
                    (second_output / filename).read_bytes(),
                )

    def test_rejects_hash_mismatch_and_unpinned_source_url(self) -> None:
        args, output, _ = self._arguments(self.root / "bad")
        args.size_35_sha256 = "0" * 64
        with self.assertRaisesRegex(adapter.AdapterError, "size-35 SHA-256 mismatch"):
            adapter.build_source(args)
        self.assertFalse(output.exists())

        args, output, _ = self._arguments(self.root / "unpinned")
        args.source_url = "https://github.com/en-wl/wordlist/tree/v2"
        with self.assertRaisesRegex(adapter.AdapterError, "complete path segment"):
            adapter.build_source(args)
        self.assertFalse(output.exists())

    def test_rejects_non_cumulative_tiers(self) -> None:
        args, output, inputs = self._arguments(self.root / "non-cumulative")
        content = b"Apple\ncan't\nmiddle\n"
        inputs[50].write_bytes(content)
        args.size_50_sha256 = hashlib.sha256(content).hexdigest()
        with self.assertRaisesRegex(adapter.AdapterError, "not cumulative"):
            adapter.build_source(args)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
