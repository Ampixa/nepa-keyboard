from __future__ import annotations

import hashlib
import json
import unicodedata
import unittest
from pathlib import Path

from tools.build_conversion_map import compile_bytes, convert_text


ROOT = Path(__file__).resolve().parents[1]
VECTORS_PATH = ROOT / "catalog/nepal-bhasa-deva-newa-internal-vectors-v0.json"
MURMURED_NEWA_LETTERS = frozenset("𑐓𑐙𑐤𑐪𑐭𑐯")
FORBIDDEN_OUTPUT_SCALARS = frozenset("ʽ↑↓")


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


class NepalBhasaConversionVectorsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vector_bytes = VECTORS_PATH.read_bytes()
        cls.vectors = json.loads(cls.vector_bytes)
        source_entry = cls.vectors["source"]
        report_entry = cls.vectors["report"]
        cls.source_path = ROOT / source_entry["path"]
        cls.report_path = ROOT / report_entry["path"]
        cls.source_bytes = cls.source_path.read_bytes()
        cls.report_bytes = cls.report_path.read_bytes()
        cls.artifact_bytes = compile_bytes(cls.source_bytes)
        cls.artifact = json.loads(cls.artifact_bytes)

    def test_fixture_and_pinned_inputs_are_canonical_and_identical(self) -> None:
        self.assertEqual(self.vector_bytes, canonical_bytes(self.vectors))
        self.assertEqual(
            set(self.vectors),
            {
                "artifact",
                "converter_id",
                "mapping_version",
                "murmur_noncontraction_vectors",
                "negative_vectors",
                "positive_vectors",
                "report",
                "source",
                "vector_format",
                "vector_format_version",
            },
        )
        self.assertEqual(
            (self.vectors["vector_format"], self.vectors["vector_format_version"]),
            ("nepa-conversion-validation-vectors", 1),
        )
        self.assertEqual(
            hashlib.sha256(self.source_bytes).hexdigest(),
            self.vectors["source"]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(self.report_bytes).hexdigest(),
            self.vectors["report"]["sha256"],
        )
        report = json.loads(self.report_bytes)
        self.assertEqual(report["source_sha256"], self.vectors["source"]["sha256"])
        self.assertEqual(report["converter_id"], self.vectors["converter_id"])
        self.assertEqual(report["mapping_version"], self.vectors["mapping_version"])

    def test_compiled_artifact_identity_and_rule_count(self) -> None:
        expected = self.vectors["artifact"]
        self.assertEqual(hashlib.sha256(self.artifact_bytes).hexdigest(), expected["sha256"])
        self.assertEqual(self.artifact["rule_count"], 165)
        self.assertEqual(self.artifact["rule_count"], expected["rule_count"])
        self.assertEqual(self.artifact["converter_id"], self.vectors["converter_id"])
        self.assertEqual(self.artifact["mapping_version"], self.vectors["mapping_version"])

    def test_positive_vectors_are_exact_and_output_only_safe_newa(self) -> None:
        self.assertEqual(len(self.vectors["positive_vectors"]), 9)
        for vector in self.vectors["positive_vectors"]:
            with self.subTest(input=vector["input"]):
                self.assertEqual(
                    vector["input"], unicodedata.normalize("NFC", vector["input"])
                )
                output = convert_text(self.artifact, vector["input"])
                self.assertEqual(output, vector["expected"])
                self.assertEqual(output, unicodedata.normalize("NFC", output))
                self.assertFalse(
                    any(
                        unicodedata.name(character, "").startswith("DEVANAGARI")
                        for character in output
                    )
                )
                self.assertTrue(FORBIDDEN_OUTPUT_SCALARS.isdisjoint(output))

    def test_negative_vectors_are_all_no_match(self) -> None:
        self.assertEqual(len(self.vectors["negative_vectors"]), 45)
        for vector in self.vectors["negative_vectors"]:
            with self.subTest(input=vector["input"], reason=vector["reason"]):
                self.assertIsNone(convert_text(self.artifact, vector["input"]))

    def test_murmured_letters_are_never_contracted(self) -> None:
        self.assertEqual(len(self.vectors["murmur_noncontraction_vectors"]), 6)
        for vector in self.vectors["murmur_noncontraction_vectors"]:
            with self.subTest(input=vector["input"]):
                output = convert_text(self.artifact, vector["input"])
                self.assertEqual(output, vector["expected"])
                self.assertTrue(MURMURED_NEWA_LETTERS.isdisjoint(output))
        for rule in self.artifact["rules"]:
            self.assertTrue(MURMURED_NEWA_LETTERS.isdisjoint(rule["to"]))


if __name__ == "__main__":
    unittest.main()
