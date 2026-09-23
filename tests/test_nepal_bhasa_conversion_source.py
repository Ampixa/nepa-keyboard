from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.build_conversion_map import compile_source, convert_text
from tools.build_nepal_bhasa_conversion_source import (
    DEVANAGARI_TABLE_SHA256,
    NEWA_TABLE_SHA256,
    AdapterError,
    TABLE_COUNTS,
    _literal_tables,
    build_source,
)


def table_module(values: dict[str, list[str]]) -> bytes:
    return "\n".join(f"{name} = {value!r}" for name, value in values.items()).encode()


class NepalBhasaConversionSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.deva = {
            "VowelMap": list("अआइईउऊऋॠऌॡएऐओऔ"),
            "VowelSignMap": list("ािीुूृॄॢॣेैोौ"),
            "AyogavahaMap": list("ँंः"),
            "ViramaMap": ["्"],
            "ConsonantMap": list("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह"),
            "SouthConsonantMap": list("ळऴऱऩ"),
            "NuktaConsonantMap": list("क़ख़ग़ज़ड़ढ़फ़य़"),
            "NuktaMap": ["़"],
            "OmMap": ["ॐ"],
            "SignMap": list("ऽ।॥"),
            "NumeralMap": list("०१२३४५६७८९"),
        }
        self.newa = {
            name: [chr(0x11400 + index + offset) for index in range(count)]
            for offset, (name, count) in enumerate(TABLE_COUNTS.items())
        }
        # Use real structural scalars for rules exercised by the compiler.
        self.newa["VowelMap"] = [chr(0x11400 + i) for i in range(14)]
        self.newa["VowelSignMap"] = [chr(0x11435 + i) for i in range(13)]
        self.newa["AyogavahaMap"] = [chr(0x11443 + i) for i in range(3)]
        self.newa["ViramaMap"] = ["𑑂"]
        self.newa["ConsonantMap"] = [
            chr(code_point)
            for code_point in list(range(0x1140E, 0x11413))
            + list(range(0x11414, 0x11419))
            + list(range(0x1141A, 0x1141F))
            + list(range(0x1141F, 0x11424))
            + list(range(0x11425, 0x1142A))
            + [0x1142B, 0x1142C, 0x1142E, 0x11430, 0x11431, 0x11432, 0x11433, 0x11434]
        ]
        self.newa["SouthConsonantMap"] = ["𑐮𑑆", "𑐲𑑆", "𑐬𑑆", "𑐣𑑆"]
        self.newa["NuktaConsonantMap"] = [
            value + "𑑆" for value in self.newa["ConsonantMap"][:8]
        ]
        self.newa["NuktaMap"] = ["𑑆"]
        self.newa["OmMap"] = ["𑑉"]
        self.newa["SignMap"] = ["𑑇", "𑑋", "𑑌"]
        self.newa["NumeralMap"] = [chr(0x11450 + i) for i in range(10)]

    def test_builds_91_direct_and_context_joiner_rules(self) -> None:
        source, counts = build_source(self.deva, self.newa)
        self.assertEqual(sum(counts.values()), 91)
        self.assertEqual(len(source["rules"]), 165)
        artifact = compile_source(source)
        self.assertEqual(convert_text(artifact, "क"), "𑐎")
        self.assertEqual(convert_text(artifact, "क्‍ष"), "𑐎𑑂‍𑐲")
        self.assertIsNone(convert_text(artifact, "कॅ"))

    def test_literal_parser_requires_exact_counts(self) -> None:
        parsed = _literal_tables(table_module(self.deva), "fixture.py")
        self.assertEqual(parsed["ConsonantMap"], self.deva["ConsonantMap"])
        broken = dict(self.deva)
        broken["NumeralMap"] = broken["NumeralMap"][:-1]
        with self.assertRaisesRegex(AdapterError, "count mismatch"):
            _literal_tables(table_module(broken), "fixture.py")

    def test_pinned_hash_constants_are_sha256(self) -> None:
        for value in (DEVANAGARI_TABLE_SHA256, NEWA_TABLE_SHA256):
            self.assertEqual(len(value), 64)
            int(value, 16)
        self.assertEqual(hashlib.sha256(b"").hexdigest().__len__(), 64)


if __name__ == "__main__":
    unittest.main()
