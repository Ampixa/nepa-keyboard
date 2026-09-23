from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import audit_bantawa_candidate_layout as auditor


class BantawaCandidateLayoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.forms = self.root / "forms.jsonl"
        self.forms.write_text(
            '{"surface":"अँ"}\n{"surface":"क्मा"}\n',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_lock(self, texts: list[str]) -> Path:
        layers = {}
        for index, layer_name in enumerate(auditor.EXPECTED_LAYERS):
            layer_texts = texts if index == 0 else ["."]
            layers[layer_name] = {
                "rows": [[
                    {
                        "key_id": f"{layer_name}.r0.k{key_index}",
                        "text": text,
                    }
                    for key_index, text in enumerate(layer_texts)
                ]]
            }
        lock = {
            "layouts": [
                {
                    "input_script": "Deva",
                    "layout_id": "deva-test-v1",
                    "layers": layers,
                    "source": {"path": "layout.json", "sha256": "0" * 64},
                }
            ]
        }
        path = self.root / "lock.json"
        path.write_text(
            json.dumps(lock, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def test_passes_when_every_generated_scalar_is_reachable(self) -> None:
        report = auditor.build_report(
            self.forms,
            self.write_lock(["अ", "ँ", "क", "्", "म", "ा"]),
            "deva-test-v1",
        )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["unsupported_scalars"], [])
        self.assertEqual(report["forms"]["rows"], 2)
        self.assertEqual(report["forms"]["distinct_surfaces"], 2)

    def test_reports_missing_scalar_without_guessing(self) -> None:
        report = auditor.build_report(
            self.forms,
            self.write_lock(["अ", "क", "्", "म", "ा"]),
            "deva-test-v1",
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(
            report["unsupported_scalars"],
            [{"character": "ँ", "code_point": "U+0901"}],
        )

    def test_rejects_duplicate_json_keys(self) -> None:
        self.forms.write_text(
            '{"surface":"अ","surface":"क"}\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(auditor.AuditError, "duplicate JSON key"):
            auditor.build_report(
                self.forms,
                self.write_lock(["अ", "क"]),
                "deva-test-v1",
            )


if __name__ == "__main__":
    unittest.main()
