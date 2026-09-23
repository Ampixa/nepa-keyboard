from __future__ import annotations

import json
import unittest

from tools import sil_apk_jsonl_internal_source as helper


def config(**overrides: object) -> helper.SilApkConfig:
    values: dict[str, object] = {
        "adapter_name": "fixture_adapter",
        "adapter_version": 1,
        "pack_id": "fix-Deva-NP",
        "source_id": "fix-apk",
        "source_sha256": "0" * 64,
        "expected_data_rows": 1,
        "language": "fix",
        "source_tag": "sil-apk/fixture",
        "file_name": "fixture.jsonl",
        "display_name": "Fixture",
        "variety": None,
        "stable_id_prefix": "fix:apk",
        "source_title": "Fixture lexicon",
        "license_id": "restricted",
        "redistribution": "prohibited",
        "allow_terminal_zwnj": True,
    }
    values.update(overrides)
    return helper.SilApkConfig(**values)


def row(
    headword: object = "अ",
    *,
    lang: object = "fix",
    ne: object = None,
    en: object = None,
    source: object = "sil-apk/fixture",
) -> str:
    value = {
        "lang": lang,
        "headword": headword,
        "ne": ["एक"] if ne is None else ne,
        "en": ["one"] if en is None else en,
        "source": source,
    }
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class SilApkJsonlInternalSourceTest(unittest.TestCase):
    def test_joiner_policy_is_closed_and_terminal_zwnj_is_opt_in(self) -> None:
        accepted = (
            "अक्\u200dख",
            "अङ्\u200cख",
        )
        for surface in accepted:
            self.assertIsNone(
                helper.validate_surface(surface, allow_terminal_zwnj=False),
                surface,
            )

        self.assertIsNone(
            helper.validate_surface("एकङ्\u200c", allow_terminal_zwnj=True)
        )
        self.assertEqual(
            helper.validate_surface("एकङ्\u200c", allow_terminal_zwnj=False),
            "invalid_joiner_context",
        )
        for surface in (
            "एकङ्\u200d",
            "अम्\u200dर\u200cमाफु",
            "अम\u200cर",
            "\u200cअ",
        ):
            self.assertEqual(
                helper.validate_surface(surface, allow_terminal_zwnj=True),
                "invalid_joiner_context",
                surface,
            )
        self.assertEqual(
            helper.validate_surface("अ\u2060क", allow_terminal_zwnj=True),
            "unsupported_format_character",
        )
        self.assertEqual(
            helper.validate_surface("अ😀", allow_terminal_zwnj=True),
            "unsupported_symbol",
        )
        self.assertEqual(
            helper.validate_surface("Lohorung", allow_terminal_zwnj=True),
            "outside_devanagari",
        )

    def test_parser_requires_exact_order_schema_tags_and_types(self) -> None:
        parsed = helper._parse_row(row(), 1, config())
        self.assertEqual(parsed["headword"], "अ")

        wrong_order = (
            '{"headword":"अ","lang":"fix","ne":[],"en":[],'
            '"source":"sil-apk/fixture"}'
        )
        with self.assertRaisesRegex(helper.AdapterError, "fields.*in order"):
            helper._parse_row(wrong_order, 1, config())

        duplicate = (
            '{"lang":"fix","headword":"अ","headword":"आ","ne":[],'
            '"en":[],"source":"sil-apk/fixture"}'
        )
        with self.assertRaisesRegex(helper.AdapterError, "duplicate JSON key"):
            helper._parse_row(duplicate, 1, config())

        for encoded, message in (
            (row(lang="other"), "language"),
            (row(source="other"), "source"),
            (row(headword=[]), "headword"),
            (row(ne="एक"), "ne"),
            (row(en=[1]), "en"),
            ("[]", "object"),
            ("{", "invalid JSON"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(helper.AdapterError, message):
                    helper._parse_row(encoded, 1, config())

    def test_stream_contract_rejects_encoding_line_and_count_drift(self) -> None:
        with self.assertRaisesRegex(helper.AdapterError, "BOM"):
            helper._read_rows(b"\xef\xbb\xbf" + row().encode() + b"\n", config())
        with self.assertRaisesRegex(helper.AdapterError, "UTF-8"):
            helper._read_rows(b"\xff\n", config())
        with self.assertRaisesRegex(helper.AdapterError, "LF-terminated"):
            helper._read_rows(row().encode(), config())
        with self.assertRaisesRegex(helper.AdapterError, "LF line endings"):
            helper._read_rows(row().encode() + b"\r\n", config())
        with self.assertRaisesRegex(helper.AdapterError, "blank"):
            helper._read_rows(row().encode() + b"\n\n", config(expected_data_rows=2))
        with self.assertRaisesRegex(helper.AdapterError, "row count mismatch"):
            helper._read_rows(row().encode() + b"\n", config(expected_data_rows=2))


if __name__ == "__main__":
    unittest.main()
