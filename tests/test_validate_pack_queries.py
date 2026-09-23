from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from nepa_keyboard.compiler import compile_pack
from tools.validate_pack_queries import (
    QueryValidationError,
    load_queries,
    main,
    validate_queries,
)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


class ValidatePackQueriesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = self.root / "source"
        source.mkdir()
        (source / "pack.json").write_text(
            json.dumps(
                {
                    "pack_id": "eng-Latn-US",
                    "language": "eng",
                    "display_name": "English",
                    "output_script": "Latn",
                    "region": "US",
                    "data_version": "0.1.0",
                    "max_suggestions": 4,
                }
            ),
            encoding="utf-8",
        )
        write_jsonl(
            source / "sources.jsonl",
            [
                {
                    "source_id": "fixture",
                    "title": "Validation fixture",
                    "method": "fixture",
                    "license": "CC0-1.0",
                    "redistribution": "allowed",
                    "sha256": "0" * 64,
                    "source_url": "https://example.invalid/validation-fixture",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "license_notice": "Test-only fixture dedicated under CC0-1.0.",
                }
            ],
        )
        write_jsonl(
            source / "forms.jsonl",
            [
                {
                    "form_id": "eng:hello",
                    "surface": "hello",
                    "rank_score": 100,
                    "source_ids": ["fixture"],
                    "evidence": "attested",
                },
                {
                    "form_id": "eng:help",
                    "surface": "help",
                    "rank_score": 90,
                    "source_ids": ["fixture"],
                    "evidence": "attested",
                },
            ],
        )
        write_jsonl(
            source / "aliases.jsonl",
            [
                {
                    "alias": "hi",
                    "form_id": "eng:hello",
                    "rank_delta": 0,
                    "scheme": "fixture",
                    "source_ids": ["fixture"],
                    "evidence": "generated",
                }
            ],
        )
        self.pack = self.root / "fixture.nkp"
        compile_pack(source, self.pack, "release")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _query_file(self, rows: list[dict[str, object]], name: str = "queries.jsonl") -> Path:
        path = self.root / name
        write_jsonl(path, rows)
        return path

    def test_surface_alias_and_empty_cases_pass_deterministically(self) -> None:
        query_file = self._query_file(
            [
                {
                    "case_id": "surface.hello",
                    "profile_id": "eng-Latn-US",
                    "pack_id": "eng-Latn-US",
                    "index": "surface",
                    "query": "he",
                    "expected_surface": "hello",
                    "max_rank": 1,
                    "review_status": "fixture",
                },
                {
                    "case_id": "alias.hi",
                    "profile_id": "eng-Latn-US",
                    "pack_id": "eng-Latn-US",
                    "index": "aliases",
                    "query": "HI",
                    "expected_surface": "hello",
                    "max_rank": 1,
                    "review_status": "fixture",
                },
                {
                    "case_id": "alias.empty",
                    "profile_id": "eng-Latn-US",
                    "pack_id": "eng-Latn-US",
                    "index": "aliases",
                    "query": "missing",
                    "expect_empty": True,
                    "review_status": "fixture",
                },
            ]
        )
        rows = load_queries(query_file)
        first = validate_queries(rows, {"eng-Latn-US": self.pack})
        second = validate_queries(rows, {"eng-Latn-US": self.pack})

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["counts"], {"failed": 0, "passed": 3, "total": 3})
        self.assertEqual([case["case_id"] for case in first["cases"]], [
            "alias.empty",
            "alias.hi",
            "surface.hello",
        ])

    def test_rank_failure_returns_nonzero_cli_status(self) -> None:
        query_file = self._query_file(
            [
                {
                    "case_id": "surface.rank",
                    "profile_id": "eng-Latn-US",
                    "pack_id": "eng-Latn-US",
                    "index": "surface",
                    "query": "he",
                    "expected_surface": "help",
                    "max_rank": 1,
                    "review_status": "fixture",
                }
            ]
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(
                [
                    "--queries",
                    str(query_file),
                    "--pack",
                    f"eng-Latn-US={self.pack}",
                ]
            )

        summary = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["counts"], {"failed": 1, "passed": 0, "total": 1})
        self.assertEqual(summary["cases"][0]["observed_rank"], 2)

    def test_schema_requires_one_complete_expectation(self) -> None:
        query_file = self._query_file(
            [
                {
                    "case_id": "invalid.expectation",
                    "profile_id": "eng-Latn-US",
                    "pack_id": "eng-Latn-US",
                    "index": "surface",
                    "query": "he",
                    "expected_surface": "hello",
                    "review_status": "fixture",
                }
            ]
        )
        with self.assertRaisesRegex(QueryValidationError, "must appear together"):
            load_queries(query_file)


if __name__ == "__main__":
    unittest.main()
