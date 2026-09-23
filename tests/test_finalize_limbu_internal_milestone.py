from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nepa_keyboard.compiler import compile_pack
from tools import build_limbu_internal_source as adapter
from tools import build_keyboard_layouts as layout_builder
from tools import build_shipping_profile_catalog as profile_builder
from tools import finalize_limbu_internal_milestone as finalizer


ROOT = Path(__file__).resolve().parents[1]
HEADER = "id\theadword_limbu\tdesc_devanagari\tgroup\tdefinition\tipa\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FinalizeLimbuInternalMilestoneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        (self.root / "catalog").mkdir(parents=True)
        shutil.copy2(
            ROOT / "catalog" / "shipping-profile-review.json",
            self.root / "catalog" / "shipping-profile-review.json",
        )
        shutil.copytree(
            ROOT / "layouts" / "internal",
            self.root / "layouts" / "internal",
        )
        # This test preserves the immutable three-profile Limbu milestone. The
        # cumulative current lane adds later languages and layouts through
        # separate versioned finalizers.
        for later_layout in (
            "deva-nepal-dhimal-v1.json",
            "deva-nepal-dumi-v1.json",
            "deva-nepal-extended-v1.json",
            "deva-nepal-khaling-v1.json",
            "deva-nepal-lohorung-v1.json",
            "deva-nepal-western-tamang-v1.json",
            "deva-nepal-yakkha-v1.json",
        ):
            later_path = self.root / "layouts/internal/src" / later_layout
            later_source = json.loads(later_path.read_text(encoding="utf-8"))
            notice_name = Path(later_source["license"]["notice_path"]).name
            later_path.unlink()
            (self.root / "layouts/internal/notices" / notice_name).unlink()
        for later_unlicensed_layout in (
            "deva-nepal-bhasa-v1.json",
            "newa-nepal-prachalit-v1.json",
        ):
            (self.root / "layouts/internal/src" / later_unlicensed_layout).unlink()
        (self.root / "src" / "nepa_keyboard").mkdir(parents=True)
        shutil.copy2(
            ROOT / "src" / "nepa_keyboard" / "compiler.py",
            self.root / "src" / "nepa_keyboard" / "compiler.py",
        )
        self.input = self.root / "limdic.tsv"
        rows = [
            f"{index:05d}\t{chr(0x18FF + index)}\t/x/\tAA\tword {index}\t[]\n"
            for index in range(1, 9)
        ]
        self.input.write_text(HEADER + "".join(rows), encoding="utf-8")
        self.source_a = self.root / "a" / "source"
        self.source_b = self.root / "b" / "source"
        self.pack_a = self.root / "a" / "lif-Limb-NP.nkp"
        self.pack_b = self.root / "b" / "lif-Limb-NP.nkp"
        self.queries = self.root / "catalog" / "limbu-internal-prefixes-v0.json"
        self.queries.write_text(json.dumps({
            "benchmark_queries": [chr(codepoint) for codepoint in range(0x1900, 0x1908)],
            "validation_query": chr(0x1900),
        }, ensure_ascii=False), encoding="utf-8")
        self.evidence = self.root / "reports" / "limbu-internal-pack-v0.json"
        self.review = self.root / "catalog" / "internal-profile-review.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def adapter_args(self, output: Path) -> argparse.Namespace:
        return argparse.Namespace(
            limdic_tsv=self.input,
            output=output,
            data_version="1.0.0",
            max_suggestions=8,
        )

    def finalizer_args(self, *, check: bool = False) -> argparse.Namespace:
        return argparse.Namespace(
            source_a=self.source_a,
            source_b=self.source_b,
            pack_a=self.pack_a,
            pack_b=self.pack_b,
            queries=self.queries,
            shipping_review=self.root / "catalog" / "shipping-profile-review.json",
            layout_source=self.root / "layouts" / "internal" / "src"
            / "limb-nepal-phonetic-v1.json",
            evidence_output=self.root / "reports" / "limbu-internal-pack-v0.json",
            review_output=self.root / "catalog" / "internal-profile-review.json",
            reviewed_at="2026-07-15",
            check=check,
        )

    def build_fixture(self) -> mock._patch:
        pins = mock.patch.multiple(
            adapter,
            LIMDIC_SHA256=sha256(self.input),
            EXPECTED_DATA_ROWS=8,
        )
        with pins:
            adapter.build_internal_source(self.adapter_args(self.source_a))
            adapter.build_internal_source(self.adapter_args(self.source_b))
            compile_pack(self.source_a, self.pack_a, "internal")
            compile_pack(self.source_b, self.pack_b, "internal")
        return mock.patch.multiple(
            adapter,
            LIMDIC_SHA256=sha256(self.input),
            EXPECTED_DATA_ROWS=8,
        )

    def test_finalizes_exact_evidence_and_internal_review_deterministically(self) -> None:
        pins = self.build_fixture()
        with (
            pins,
            mock.patch.object(finalizer, "REPOSITORY_ROOT", self.root),
            mock.patch.object(
                finalizer,
                "_loaded_compiler_source",
                return_value=self.root / "src/nepa_keyboard/compiler.py",
            ),
        ):
            evidence, review = finalizer.finalize(self.finalizer_args())
            finalizer.finalize(self.finalizer_args(check=True))

        self.assertTrue(evidence["determinism"]["source_trees_identical"])
        self.assertTrue(evidence["determinism"]["pack_bytes_identical"])
        self.assertEqual(evidence["pack"]["release_mode"], "internal")
        self.assertEqual(evidence["pack"]["candidate_count"], 8)
        self.assertEqual(
            evidence["queries"]["validation"]["expected_first_surface"],
            chr(0x1900),
        )
        self.assertEqual(review["authority"], "internal")
        self.assertEqual(review["expected_counts"]["selectable"], 3)
        limb = next(row for row in review["evidence"] if row["profile_id"] == "lif-Limb-NP")
        self.assertEqual(limb["gates"], sorted(finalizer.INTERNAL_GATES))
        self.assertEqual(limb["pack_artifact"]["artifact_sha256"], sha256(self.pack_a))
        self.assertEqual(limb["pack_artifact"]["validation"]["query"], chr(0x1900))
        self.assertEqual(
            limb["artifacts"][0]["sha256"],
            sha256(self.evidence),
        )
        foundation_layout_hashes = {
            row["profile_id"]: row["layout_binding"]["source_sha256"]
            for row in review["evidence"]
            if row["profile_id"] in finalizer.FOUNDATION_PROFILE_IDS
        }
        self.assertEqual(foundation_layout_hashes, {
            "eng-Latn-US": sha256(
                self.root / "layouts/internal/src/latn-qwerty-us-v1.json"
            ),
            "npi-Deva-NP": sha256(
                self.root / "layouts/internal/src/deva-nepal-basic-v1.json"
            ),
        })

        catalog_bytes = (ROOT / "catalog/resources.json").read_bytes()
        catalog = json.loads(catalog_bytes)
        review_bytes = finalizer._canonical_bytes(review)
        reference = {"path": "fixture", "sha256": "1" * 64}
        profile_lock = profile_builder.build_lock(
            catalog,
            review,
            catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
            review_sha256=hashlib.sha256(review_bytes).hexdigest(),
            compiler_reference=reference,
            schema_references={
                name: reference
                for name in ("catalog", "review", "lock")
            },
            review_path="catalog/internal-profile-review.json",
        )
        profile_bytes = profile_builder._canonical_bytes(profile_lock)
        layout_lock = layout_builder.build_lock(
            self.root / "layouts/internal/src",
            profile_lock,
            profile_lock_path="catalog/internal-profiles.lock.json",
            profile_lock_sha256=hashlib.sha256(profile_bytes).hexdigest(),
            source_path_prefix="layouts/internal/src",
            compiler_reference=reference,
            schema_references={
                name: reference for name in ("source", "lock")
            },
        )
        self.assertEqual(len(layout_lock["profile_bindings"]), 3)

    def test_rejects_source_tree_drift_before_writing_outputs(self) -> None:
        pins = self.build_fixture()
        with (self.source_b / "forms.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("\n")
        with (
            pins,
            mock.patch.object(finalizer, "REPOSITORY_ROOT", self.root),
            mock.patch.object(
                finalizer,
                "_loaded_compiler_source",
                return_value=self.root / "src/nepa_keyboard/compiler.py",
            ),
            self.assertRaisesRegex(finalizer.FinalizeError, "source trees"),
        ):
            finalizer.finalize(self.finalizer_args())
        self.assertFalse(self.evidence.exists())
        self.assertFalse(self.review.exists())

    def test_rejects_reused_input_paths_and_file_identities(self) -> None:
        self.build_fixture()
        same_source = self.finalizer_args()
        same_source.source_b = self.source_a
        with (
            mock.patch.object(finalizer, "REPOSITORY_ROOT", self.root),
            self.assertRaisesRegex(
                finalizer.FinalizeError,
                "source directory paths must be distinct",
            ),
        ):
            finalizer.finalize(same_source)

        self.pack_b.unlink()
        self.pack_b.hardlink_to(self.pack_a)
        with (
            mock.patch.object(finalizer, "REPOSITORY_ROOT", self.root),
            self.assertRaisesRegex(
                finalizer.FinalizeError,
                "NKP inputs must not be the same file identity",
            ),
        ):
            finalizer.finalize(self.finalizer_args())

        self.assertFalse(self.evidence.exists())
        self.assertFalse(self.review.exists())

    def test_rejects_pack_not_derived_from_its_paired_source_tree(self) -> None:
        pins = self.build_fixture()
        for source in (self.source_a, self.source_b):
            forms_path = source / "forms.jsonl"
            forms = [
                json.loads(line)
                for line in forms_path.read_text(encoding="utf-8").splitlines()
            ]
            forms[0]["rank_score"] += 1
            forms_path.write_text(
                "".join(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ) + "\n"
                    for row in forms
                ),
                encoding="utf-8",
            )

        with (
            pins,
            mock.patch.object(finalizer, "REPOSITORY_ROOT", self.root),
            mock.patch.object(
                finalizer,
                "_loaded_compiler_source",
                return_value=self.root / "src/nepa_keyboard/compiler.py",
            ),
            self.assertRaisesRegex(
                finalizer.FinalizeError,
                "run a NKP is not derived from its source tree",
            ),
        ):
            finalizer.finalize(self.finalizer_args())

        self.assertFalse(self.evidence.exists())
        self.assertFalse(self.review.exists())

    def test_rejects_loaded_compiler_outside_repository_binding(self) -> None:
        with (
            mock.patch.object(finalizer, "REPOSITORY_ROOT", self.root),
            self.assertRaisesRegex(
                finalizer.FinalizeError,
                "loaded pack compiler is not the repository source",
            ),
        ):
            finalizer._loaded_compiler_source()


if __name__ == "__main__":
    unittest.main()
