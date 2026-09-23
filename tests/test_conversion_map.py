from __future__ import annotations

import copy
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from tools.build_conversion_map import (
    ALGORITHM,
    JOINER_POLICY,
    MAX_ARTIFACT_BYTES,
    MAX_RULES,
    NORMALIZATION,
    SOURCE_FORMAT,
    SOURCE_FORMAT_VERSION,
    UNMAPPED_POLICY,
    ConversionMapError,
    _canonical_bytes,
    compile_bytes,
    compile_file,
    compile_source,
    convert_text,
    validate_artifact,
)


DEVA_KA = "\u0915"
DEVA_SSA = "\u0937"
DEVA_VIRAMA = "\u094d"
NEWA_KA = "\U0001140e"
NEWA_SSA = "\U00011431"
NEWA_VIRAMA = "\U00011442"


def source(rules: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "source_format": SOURCE_FORMAT,
        "source_format_version": SOURCE_FORMAT_VERSION,
        "converter_id": "new-Deva-Newa-NP",
        "mapping_version": "1.0.0",
        "language": "new",
        "source_script": "Deva",
        "output_script": "Newa",
        "normalization": NORMALIZATION,
        "algorithm": ALGORITHM,
        "unmapped_policy": UNMAPPED_POLICY,
        "joiner_policy": JOINER_POLICY,
        "rules": rules
        if rules is not None
        else [
            {"from": DEVA_KA, "to": NEWA_KA},
            {"from": DEVA_VIRAMA, "to": NEWA_VIRAMA},
            {"from": DEVA_SSA, "to": NEWA_SSA},
        ],
    }


class ConversionMapCompilerTest(unittest.TestCase):
    def test_compiles_canonical_utf8_with_derived_count(self) -> None:
        first = source(
            [
                {"from": DEVA_SSA, "to": NEWA_SSA},
                {"from": DEVA_KA, "to": NEWA_KA},
            ]
        )
        second = source(list(reversed(first["rules"])))

        first_bytes = compile_bytes(json.dumps(first, ensure_ascii=False).encode())
        second_bytes = compile_bytes(json.dumps(second, ensure_ascii=False).encode())

        self.assertEqual(first_bytes, second_bytes)
        self.assertTrue(first_bytes.endswith(b"\n"))
        self.assertFalse(first_bytes.startswith(b"\xef\xbb\xbf"))
        artifact = json.loads(first_bytes)
        self.assertEqual(artifact["format"], "nepa-conversion-map")
        self.assertEqual(artifact["format_version"], 1)
        self.assertEqual(artifact["rule_count"], 2)
        self.assertEqual(
            artifact["rules"],
            [
                {"from": DEVA_KA, "to": NEWA_KA},
                {"from": DEVA_SSA, "to": NEWA_SSA},
            ],
        )
        self.assertIn(NEWA_KA.encode("utf-8"), first_bytes)
        self.assertNotIn(b"\\ud804", first_bytes)
        self.assertEqual(first_bytes, _canonical_bytes(artifact))

    def test_leftmost_longest_uses_codepoint_sequences(self) -> None:
        conjunct = DEVA_KA + DEVA_VIRAMA + DEVA_SSA
        artifact = compile_source(
            source(
                [
                    {"from": DEVA_KA, "to": NEWA_KA},
                    {"from": DEVA_VIRAMA, "to": NEWA_VIRAMA},
                    {"from": DEVA_SSA, "to": NEWA_SSA},
                    {"from": conjunct, "to": NEWA_KA},
                ]
            )
        )
        self.assertEqual(convert_text(artifact, conjunct), NEWA_KA)
        self.assertEqual(
            convert_text(artifact, DEVA_KA + DEVA_SSA),
            NEWA_KA + NEWA_SSA,
        )

    def test_unmapped_or_out_of_script_input_is_no_match(self) -> None:
        artifact = compile_source(source([{"from": DEVA_KA, "to": NEWA_KA}]))
        self.assertIsNone(convert_text(artifact, DEVA_KA + DEVA_SSA))
        self.assertIsNone(convert_text(artifact, "a"))
        self.assertIsNone(convert_text(artifact, ""))

    def test_context_valid_joiner_rule_and_complete_conversion(self) -> None:
        deva_suffix = DEVA_VIRAMA + "\u200d" + DEVA_KA
        newa_suffix = NEWA_VIRAMA + "\u200d" + NEWA_KA
        artifact = compile_source(
            source(
                [
                    {"from": DEVA_KA, "to": NEWA_KA},
                    {"from": deva_suffix, "to": newa_suffix},
                ]
            )
        )
        self.assertEqual(
            convert_text(artifact, DEVA_KA + deva_suffix),
            NEWA_KA + newa_suffix,
        )
        self.assertIsNone(convert_text(artifact, deva_suffix))

    def test_rejects_invalid_joiner_context_on_either_side(self) -> None:
        invalid_source = source(
            [{"from": DEVA_KA + "\u200d" + DEVA_SSA, "to": NEWA_KA}]
        )
        with self.assertRaisesRegex(ConversionMapError, "joiner"):
            compile_source(invalid_source)

        invalid_target = source(
            [{"from": DEVA_KA, "to": NEWA_KA + "\u200c" + NEWA_SSA}]
        )
        with self.assertRaisesRegex(ConversionMapError, "joiner"):
            compile_source(invalid_target)

    def test_rejects_wrong_scripts_and_non_nfc(self) -> None:
        wrong_source = source([{"from": "a", "to": NEWA_KA}])
        with self.assertRaisesRegex(ConversionMapError, "out-of-script"):
            compile_source(wrong_source)

        wrong_target = source([{"from": DEVA_KA, "to": DEVA_KA}])
        with self.assertRaisesRegex(ConversionMapError, "out-of-script"):
            compile_source(wrong_target)

        decomposed = "\u0928\u093c"
        self.assertNotEqual(decomposed, unicodedata.normalize("NFC", decomposed))
        non_nfc = source([{"from": decomposed, "to": NEWA_KA}])
        with self.assertRaisesRegex(ConversionMapError, "must be NFC"):
            compile_source(non_nfc)

    def test_rejects_duplicates_unknown_fields_and_duplicate_json_keys(self) -> None:
        duplicate = source(
            [
                {"from": DEVA_KA, "to": NEWA_KA},
                {"from": DEVA_KA, "to": NEWA_SSA},
            ]
        )
        with self.assertRaisesRegex(ConversionMapError, "duplicate rule source"):
            compile_source(duplicate)

        unknown = source()
        unknown["note"] = "not part of v1"
        with self.assertRaisesRegex(ConversionMapError, "unknown"):
            compile_source(unknown)

        duplicate_key = (
            b'{"source_format":"nepa-conversion-map-source",'
            b'"source_format":"nepa-conversion-map-source"}'
        )
        with self.assertRaisesRegex(ConversionMapError, "duplicate JSON key"):
            compile_bytes(duplicate_key)

    def test_rejects_bom_empty_rules_and_rule_bounds(self) -> None:
        with self.assertRaisesRegex(ConversionMapError, "BOM"):
            compile_bytes(b"\xef\xbb\xbf{}")

        with self.assertRaisesRegex(ConversionMapError, "1..1024"):
            compile_source(source([]))

        with self.assertRaisesRegex(ConversionMapError, "1..1024"):
            compile_source(
                source(
                    [
                        {"from": DEVA_KA + chr(0x0966 + index % 10), "to": NEWA_KA}
                        for index in range(MAX_RULES + 1)
                    ]
                )
            )

        with self.assertRaisesRegex(ConversionMapError, "exceeds 8 code points"):
            compile_source(
                source([{"from": DEVA_KA * 9, "to": NEWA_KA}])
            )
        with self.assertRaisesRegex(ConversionMapError, "exceeds 16 code points"):
            compile_source(
                source([{"from": DEVA_KA, "to": NEWA_KA * 17}])
            )

        oversized = source()
        oversized["mapping_version"] = "1" * MAX_ARTIFACT_BYTES + ".0.0"
        with self.assertRaisesRegex(ConversionMapError, "artifact exceeds"):
            compile_source(oversized)

    def test_artifact_validation_rejects_count_and_order_drift(self) -> None:
        artifact = compile_source(source())
        wrong_count = copy.deepcopy(artifact)
        wrong_count["rule_count"] += 1
        with self.assertRaisesRegex(ConversionMapError, "rule_count"):
            validate_artifact(wrong_count)

        wrong_order = copy.deepcopy(artifact)
        wrong_order["rules"].reverse()
        with self.assertRaisesRegex(ConversionMapError, "canonical order"):
            validate_artifact(wrong_order)

        wrong_rules = copy.deepcopy(artifact)
        wrong_rules["rules"] = 1
        with self.assertRaisesRegex(ConversionMapError, "rules must be an array"):
            validate_artifact(wrong_rules)

    def test_compile_file_requires_ncm_and_replaces_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "map.json"
            output_path = root / "map.ncm"
            source_path.write_text(
                json.dumps(source(), ensure_ascii=False), encoding="utf-8"
            )
            output_path.write_bytes(b"old")

            artifact = compile_file(source_path, output_path)

            self.assertEqual(output_path.read_bytes(), _canonical_bytes(artifact))
            with self.assertRaisesRegex(ConversionMapError, r"\.ncm"):
                compile_file(source_path, root / "map.json")


if __name__ == "__main__":
    unittest.main()
