from __future__ import annotations

import copy
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from tools.build_shipping_profile_catalog import (
    BASE_REQUIRED_EVIDENCE_GATES,
    CatalogError,
    EXPANSION_REQUIRED_EVIDENCE_GATES,
    FOUNDATION_PROFILE_IDS,
    INTERNAL_CONVERSION_REQUIRED_EVIDENCE_GATES,
    INTERNAL_REQUIRED_EVIDENCE_GATES,
    _canonical_bytes,
    _validate_evidence_files,
    build_lock,
    main,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "resources.json"
REVIEW_PATH = ROOT / "catalog" / "shipping-profile-review.json"


class ShippingProfileCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog_bytes = CATALOG_PATH.read_bytes()
        cls.review_bytes = REVIEW_PATH.read_bytes()
        cls.catalog = json.loads(cls.catalog_bytes)
        cls.review = json.loads(cls.review_bytes)

    def build(
        self,
        catalog: dict[str, object] | None = None,
        review: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return build_lock(
            copy.deepcopy(catalog if catalog is not None else self.catalog),
            copy.deepcopy(review if review is not None else self.review),
            catalog_sha256=hashlib.sha256(self.catalog_bytes).hexdigest(),
            review_sha256=hashlib.sha256(self.review_bytes).hexdigest(),
            compiler_reference={
                "path": "tools/build_shipping_profile_catalog.py",
                "sha256": hashlib.sha256(
                    (ROOT / "tools" / "build_shipping_profile_catalog.py").read_bytes()
                ).hexdigest(),
            },
            schema_references={
                name: {
                    "path": f"schemas/{file_name}",
                    "sha256": hashlib.sha256(
                        (ROOT / "schemas" / file_name).read_bytes()
                    ).hexdigest(),
                }
                for name, file_name in {
                    "catalog": "resource-catalog.schema.json",
                    "review": "shipping-profile-review.schema.json",
                    "lock": "shipping-profile-lock.schema.json",
                }.items()
            },
        )

    def internal_conversion_review(self) -> tuple[dict[str, object], str]:
        review = copy.deepcopy(self.review)
        review["authority"] = "internal"
        review["review_id"] = "internal-conversion-fixture"
        review["blocked_reason_by_method"] = {
            "direct": "DIRECT_PROFILE_NOT_INTERNAL_READY",
            "roman_phonetic": "ROMAN_ALIAS_NOT_INTERNAL_READY",
            "script_conversion": "SCRIPT_CONVERTER_NOT_INTERNAL_READY",
        }
        for evidence in review["evidence"]:
            evidence["gates"] = sorted(
                set(evidence["gates"]) | INTERNAL_REQUIRED_EVIDENCE_GATES
            )
        profile = next(
            row
            for row in self.build()["profiles"]
            if row["input_method_id"] == "new-deva-newa"
        )
        evidence_id = "new-deva-newa-internal-fixture"
        review["expected_counts"]["selectable"] = 3
        review["profile_overrides"]["new-deva-newa"] = {
            "profile_id": profile["profile_id"],
            "layout_id": "deva-nepal-bhasa-v1",
            "conversion_binding": profile["profile_id"],
            "selectable": True,
            "default_enabled": False,
            "evidence_ids": [evidence_id],
        }
        review["evidence"].append({
            "evidence_id": evidence_id,
            "profile_id": profile["profile_id"],
            "status": "passed",
            "gates": sorted(INTERNAL_CONVERSION_REQUIRED_EVIDENCE_GATES),
            "layout_binding": {
                "layout_id": "deva-nepal-bhasa-v1",
                "revision": 1,
                "source_sha256": "f9088679a904a8129e02b8202740564537e616d24b85637c1489038c35d93ac8",
            },
            "conversion_artifact": {
                "converter_id": profile["profile_id"],
                "file_name": "new-Deva-Newa-NP.ncm",
                "artifact_sha256": "9" * 64,
                "language": "new",
                "source_script": "Deva",
                "output_script": "Newa",
                "release_mode": "internal",
                "rule_count": 128,
                "validation": {
                    "vectors": [
                        {
                            "input": "क",
                            "expected_status": "MATCH",
                            "expected_output": "𑐎",
                        },
                        {
                            "input": "a",
                            "expected_status": "NO_MATCH",
                            "expected_output": None,
                        },
                    ]
                },
            },
            "artifacts": [
                {"path": "fixture/new-deva-newa.json", "sha256": "a" * 64}
            ],
        })
        return review, profile["profile_id"]

    def test_exact_catalog_shape_and_selectable_set(self) -> None:
        lock = self.build()
        self.assertEqual(
            lock["counts"],
            {"targets": 33, "profiles": 74, "scripts": 9, "selectable": 2},
        )
        self.assertEqual(
            lock["scripts"],
            ["Deva", "Latn", "Lepc", "Limb", "Newa", "Olck", "Sunu", "Tibt", "Tirh"],
        )
        profiles = lock["profiles"]
        self.assertEqual(
            {row["profile_id"] for row in profiles if row["selectable"]},
            {"eng-Latn-US", "npi-Deva-NP"},
        )
        self.assertEqual(lock["generator"], "build_shipping_profile_catalog")
        self.assertEqual(lock["lock_version"], 2)
        self.assertEqual(lock["generator_version"], 2)
        self.assertEqual(lock["review"]["authority"], "release")
        self.assertEqual(
            lock["compiler"]["sha256"],
            hashlib.sha256(
                (ROOT / "tools" / "build_shipping_profile_catalog.py").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(set(lock["schemas"]), {"catalog", "review", "lock"})

    def test_every_dictionary_resource_has_an_exact_identity(self) -> None:
        dictionary_kinds = {"dictionary", "lexicon", "spelling"}
        resources = [
            (pack["id"], resource)
            for pack in self.catalog["packs"]
            for resource in pack.get("resources", [])
            if resource["kind"] in dictionary_kinds
        ]
        self.assertEqual(len(resources), 30)
        self.assertEqual(len({pack_id for pack_id, _ in resources}), 22)
        self.assertEqual(
            sum(1 for _, resource in resources if resource.get("canonical") is True),
            14,
        )
        for pack_id, resource in resources:
            with self.subTest(pack_id=pack_id, resource_id=resource["id"]):
                self.assertRegex(resource.get("sha256", ""), r"^[0-9a-f]{64}$")

    def test_internal_product_gaps_exclude_public_export_clearance_work(self) -> None:
        clearance = re.compile(
            r"\b(?:licen[cs]e|redistribut\w*|permission|rights|clearance)\b",
            re.IGNORECASE,
        )
        public_export_rows = 0
        for pack in self.catalog["packs"]:
            for gap in pack.get("gaps", []):
                with self.subTest(pack_id=pack["id"], gap=gap):
                    self.assertIsNone(clearance.search(gap))
            public_export_rows += len(pack.get("public_export_gaps", []))
        self.assertGreater(public_export_rows, 0)

    def test_foundation_evidence_does_not_enable_a_third_profile(self) -> None:
        review = copy.deepcopy(self.review)
        limbu_profile = next(
            row
            for row in self.build()["profiles"]
            if row["input_method_id"] == "lif-limb-direct"
        )
        evidence_id = "lif-layout-pack-only-fixture"
        review["profile_overrides"]["lif-limb-direct"] = {
            "profile_id": limbu_profile["profile_id"],
            "layout_id": "limb-sirijanga-v1",
            "pack_binding": limbu_profile["profile_id"],
            "selectable": True,
            "default_enabled": True,
            "evidence_ids": [evidence_id],
        }
        review["evidence"].append({
            "evidence_id": evidence_id,
            "profile_id": limbu_profile["profile_id"],
            "status": "passed",
            "gates": sorted(BASE_REQUIRED_EVIDENCE_GATES),
            "layout_binding": {
                "layout_id": "limb-sirijanga-v1",
                "revision": 1,
                "source_sha256": "0" * 64,
            },
            "pack_artifact": {
                "pack_id": limbu_profile["profile_id"],
                "file_name": "lif-Limb-NP.nkp",
                "artifact_sha256": "1" * 64,
                "language": "lif",
                "output_script": "Limb",
                "artifact_license": "MIT",
                "release_mode": "release",
                "candidate_count": 1,
                "surface_key_count": 1,
                "alias_key_count": 0,
                "validation": {
                    "query": "ᤁ",
                    "expected_surface": "ᤁ",
                    "benchmark_queries": ["ᤁ"],
                },
            },
            "artifacts": [{"path": "fixture-only", "sha256": "2" * 64}],
        })
        with self.assertRaisesRegex(CatalogError, "accessibility_review"):
            self.build(review=review)
        self.assertEqual(FOUNDATION_PROFILE_IDS, {"eng-Latn-US", "npi-Deva-NP"})
        self.assertEqual(
            EXPANSION_REQUIRED_EVIDENCE_GATES,
            {
                "native_speaker_review",
                "quality_evaluation",
                "physical_device_runtime",
                "accessibility_review",
            },
        )

    def test_full_expansion_evidence_can_enable_a_reviewed_third_profile(self) -> None:
        review = copy.deepcopy(self.review)
        dhimal_profile = next(
            row
            for row in self.build()["profiles"]
            if row["input_method_id"] == "dhi-deva-direct"
        )
        evidence_id = "dhi-expansion-fixture"
        review["expected_counts"]["selectable"] = 3
        review["profile_overrides"]["dhi-deva-direct"] = {
            "profile_id": dhimal_profile["profile_id"],
            "layout_id": "deva-nepal-basic-v1",
            "pack_binding": dhimal_profile["profile_id"],
            "selectable": True,
            "default_enabled": False,
            "evidence_ids": [evidence_id],
        }
        review["evidence"].append({
            "evidence_id": evidence_id,
            "profile_id": dhimal_profile["profile_id"],
            "status": "passed",
            "gates": sorted(
                BASE_REQUIRED_EVIDENCE_GATES | EXPANSION_REQUIRED_EVIDENCE_GATES
            ),
            "layout_binding": {
                "layout_id": "deva-nepal-basic-v1",
                "revision": 1,
                "source_sha256": "bca603b0a101f8c4be47fd6625c4e0bd0c7e7f1370f88c0e4028450b5ccbcade",
            },
            "pack_artifact": {
                "pack_id": dhimal_profile["profile_id"],
                "file_name": "dhi-Deva-NP.nkp",
                "artifact_sha256": "3" * 64,
                "language": "dhi",
                "output_script": "Deva",
                "artifact_license": "CC-BY-SA-4.0",
                "release_mode": "release",
                "candidate_count": 2,
                "surface_key_count": 2,
                "alias_key_count": 0,
                "validation": {
                    "query": "धि",
                    "expected_surface": "धिमाल",
                    "benchmark_queries": ["धि", "धिम"],
                },
            },
            "artifacts": [
                {"path": "fixture/dhi-review.json", "sha256": "4" * 64}
            ],
        })

        lock = self.build(review=review)
        selected = [row for row in lock["profiles"] if row["selectable"]]
        self.assertEqual(lock["counts"]["selectable"], 3)
        self.assertEqual(
            {row["profile_id"] for row in selected},
            FOUNDATION_PROFILE_IDS | {dhimal_profile["profile_id"]},
        )
        promoted = next(
            row for row in selected if row["profile_id"] == dhimal_profile["profile_id"]
        )
        self.assertFalse(promoted["default_enabled"])
        self.assertEqual(promoted["pack_artifact"]["surface_key_count"], 2)
        self.assertEqual(promoted["evidence_artifacts"][0]["sha256"], "4" * 64)

    def test_internal_authority_promotes_limbu_without_release_or_license_gates(self) -> None:
        review = copy.deepcopy(self.review)
        review["authority"] = "internal"
        review["review_id"] = "internal-profiles-fixture"
        review["blocked_reason_by_method"] = {
            "direct": "DIRECT_PROFILE_NOT_INTERNAL_READY",
            "roman_phonetic": "ROMAN_ALIAS_NOT_INTERNAL_READY",
            "script_conversion": "SCRIPT_CONVERTER_NOT_INTERNAL_READY",
        }
        for evidence in review["evidence"]:
            evidence["gates"] = sorted(
                set(evidence["gates"]) | INTERNAL_REQUIRED_EVIDENCE_GATES
            )
        review["expected_counts"]["selectable"] = 3
        limbu_profile = next(
            row for row in self.build()["profiles"]
            if row["input_method_id"] == "lif-limb-direct"
        )
        evidence_id = "lif-internal-fixture"
        review["profile_overrides"]["lif-limb-direct"] = {
            "profile_id": limbu_profile["profile_id"],
            "layout_id": "limb-nepal-phonetic-v1",
            "pack_binding": limbu_profile["profile_id"],
            "selectable": True,
            "default_enabled": False,
            "evidence_ids": [evidence_id],
        }
        review["evidence"].append({
            "evidence_id": evidence_id,
            "profile_id": limbu_profile["profile_id"],
            "status": "passed",
            "gates": sorted(INTERNAL_REQUIRED_EVIDENCE_GATES),
            "layout_binding": {
                "layout_id": "limb-nepal-phonetic-v1",
                "revision": 1,
                "source_sha256": "aee3a4193111469125c58b527db6dbae6677c1046d9c2eccd4cf855984928ac1",
            },
            "pack_artifact": {
                "pack_id": limbu_profile["profile_id"],
                "file_name": "lif-Limb-NP.nkp",
                "artifact_sha256": "7" * 64,
                "language": "lif",
                "output_script": "Limb",
                "artifact_license": "LicenseRef-Internal",
                "release_mode": "internal",
                "candidate_count": 2,
                "surface_key_count": 2,
                "alias_key_count": 0,
                "validation": {
                    "query": "ᤀ",
                    "expected_surface": "ᤀ",
                    "benchmark_queries": ["ᤀ", "ᤁ", "ᤕ"],
                },
            },
            "artifacts": [
                {"path": "fixture/lif-internal.json", "sha256": "8" * 64}
            ],
        })

        lock = self.build(review=review)
        promoted = next(
            row for row in lock["profiles"]
            if row["profile_id"] == limbu_profile["profile_id"]
        )
        self.assertEqual(lock["review"]["authority"], "internal")
        self.assertEqual(lock["counts"]["selectable"], 3)
        self.assertTrue(promoted["selectable"])
        self.assertFalse(promoted["default_enabled"])
        self.assertEqual(promoted["output_script"], "Limb")
        blocked = next(row for row in lock["profiles"] if not row["selectable"])
        self.assertIn("INTERNAL", blocked["blocked_reason"])
        self.assertIn("internal", blocked["blocked_detail"].lower())

    def test_internal_conversion_profile_uses_distinct_artifact_lane(self) -> None:
        review, profile_id = self.internal_conversion_review()

        lock = self.build(review=review)
        promoted = next(
            row for row in lock["profiles"] if row["profile_id"] == profile_id
        )
        self.assertEqual(lock["counts"]["selectable"], 3)
        self.assertTrue(promoted["selectable"])
        self.assertEqual(promoted["lookup_kind"], "conversion")
        self.assertIsNone(promoted["pack_binding"])
        self.assertIsNone(promoted["pack_artifact"])
        self.assertEqual(promoted["conversion_binding"], profile_id)
        self.assertEqual(promoted["conversion_artifact"]["converter_id"], profile_id)
        self.assertEqual(
            {
                vector["expected_status"]
                for vector in promoted["conversion_artifact"]["validation"]["vectors"]
            },
            {"MATCH", "NO_MATCH"},
        )
        self.assertTrue(
            all(
                {
                    "pack_binding",
                    "pack_artifact",
                    "conversion_binding",
                    "conversion_artifact",
                }.issubset(profile)
                for profile in lock["profiles"]
            )
        )

    def test_internal_conversion_requires_its_gate_and_both_vector_outcomes(self) -> None:
        review, _ = self.internal_conversion_review()
        evidence = review["evidence"][-1]
        evidence["gates"].remove("internal_converter")
        evidence["gates"].append("internal_pack")
        with self.assertRaisesRegex(CatalogError, "internal_converter"):
            self.build(review=review)

        review, _ = self.internal_conversion_review()
        vectors = review["evidence"][-1]["conversion_artifact"]["validation"][
            "vectors"
        ]
        vectors[1] = {
            "input": "ख",
            "expected_status": "MATCH",
            "expected_output": "𑐏",
        }
        with self.assertRaisesRegex(CatalogError, "one MATCH and one NO_MATCH"):
            self.build(review=review)

        review, _ = self.internal_conversion_review()
        review["evidence"][-1]["conversion_artifact"]["validation"]["vectors"][1][
            "expected_output"
        ] = "unexpected"
        with self.assertRaisesRegex(CatalogError, "must be null for NO_MATCH"):
            self.build(review=review)

    def test_conversion_profile_rejects_pack_lane_data(self) -> None:
        review, _ = self.internal_conversion_review()
        review["profile_overrides"]["new-deva-newa"]["pack_binding"] = "wrong-lane"
        with self.assertRaisesRegex(CatalogError, "cannot carry a pack binding"):
            self.build(review=review)

        review, _ = self.internal_conversion_review()
        evidence = review["evidence"][-1]
        evidence["pack_artifact"] = review["evidence"][0]["pack_artifact"]
        del evidence["conversion_artifact"]
        with self.assertRaisesRegex(CatalogError, "cannot carry a pack artifact"):
            self.build(review=review)

    def test_rejects_conflicting_ncm_identity_reuse(self) -> None:
        review, first_profile_id = self.internal_conversion_review()
        second_profile = next(
            row
            for row in self.build()["profiles"]
            if row["input_method_id"] == "mai-deva-tirh"
        )
        evidence_id = "mai-deva-tirh-internal-fixture"
        review["expected_counts"]["selectable"] = 4
        review["profile_overrides"]["mai-deva-tirh"] = {
            "profile_id": second_profile["profile_id"],
            "layout_id": "deva-nepal-basic-v1",
            "conversion_binding": first_profile_id,
            "selectable": True,
            "default_enabled": False,
            "evidence_ids": [evidence_id],
        }
        review["evidence"].append({
            "evidence_id": evidence_id,
            "profile_id": second_profile["profile_id"],
            "status": "passed",
            "gates": sorted(INTERNAL_CONVERSION_REQUIRED_EVIDENCE_GATES),
            "layout_binding": {
                "layout_id": "deva-nepal-basic-v1",
                "revision": 1,
                "source_sha256": "bca603b0a101f8c4be47fd6625c4e0bd0c7e7f1370f88c0e4028450b5ccbcade",
            },
            "conversion_artifact": {
                "converter_id": first_profile_id,
                "file_name": "mai-Deva-Tirh-NP.ncm",
                "artifact_sha256": "b" * 64,
                "language": "mai",
                "source_script": "Deva",
                "output_script": "Tirh",
                "release_mode": "internal",
                "rule_count": 64,
                "validation": {
                    "vectors": [
                        {
                            "input": "क",
                            "expected_status": "MATCH",
                            "expected_output": "𑒀",
                        },
                        {
                            "input": "a",
                            "expected_status": "NO_MATCH",
                            "expected_output": None,
                        },
                    ]
                },
            },
            "artifacts": [
                {"path": "fixture/mai-deva-tirh.json", "sha256": "c" * 64}
            ],
        })

        with self.assertRaisesRegex(
            CatalogError, "conflicting conversion artifact reuse for converter_id"
        ):
            self.build(review=review)

        file_conflict = copy.deepcopy(review)
        file_conflict["profile_overrides"]["mai-deva-tirh"][
            "conversion_binding"
        ] = second_profile["profile_id"]
        artifact = file_conflict["evidence"][-1]["conversion_artifact"]
        artifact["converter_id"] = second_profile["profile_id"]
        artifact["file_name"] = "new-Deva-Newa-NP.ncm"
        with self.assertRaisesRegex(
            CatalogError, "conflicting conversion artifact reuse for file_name"
        ):
            self.build(review=file_conflict)

    def test_reviewed_alias_profile_can_share_an_exact_output_pack(self) -> None:
        review = copy.deepcopy(self.review)
        roman_profile = next(
            row
            for row in self.build()["profiles"]
            if row["input_method_id"] == "npi-latn-deva"
        )
        direct_evidence = next(
            row
            for row in review["evidence"]
            if row["profile_id"] == "npi-Deva-NP"
        )
        shared = direct_evidence["pack_artifact"]
        shared.update({
            "file_name": "npi-Deva-NP-shared.nkp",
            "artifact_sha256": "5" * 64,
            "alias_key_count": 12,
        })
        evidence_id = "npi-roman-expansion-fixture"
        review["expected_counts"]["selectable"] = 3
        review["profile_overrides"]["npi-latn-deva"] = {
            "profile_id": roman_profile["profile_id"],
            "layout_id": "latn-qwerty-us-v1",
            "pack_binding": "npi-Deva-NP",
            "selectable": True,
            "default_enabled": False,
            "evidence_ids": [evidence_id],
        }
        roman_artifact = copy.deepcopy(shared)
        roman_artifact["validation"] = {
            "query": "nepal",
            "expected_surface": "नेपाल",
            "benchmark_queries": ["ne", "nep", "nepal"],
        }
        review["evidence"].append({
            "evidence_id": evidence_id,
            "profile_id": roman_profile["profile_id"],
            "status": "passed",
            "gates": sorted(
                BASE_REQUIRED_EVIDENCE_GATES | EXPANSION_REQUIRED_EVIDENCE_GATES
            ),
            "layout_binding": {
                "layout_id": "latn-qwerty-us-v1",
                "revision": 1,
                "source_sha256": "fc0ae5dfa73e3d034d1e48303c3d1b26fc493ac45e5d327a0f4f7b2cd1d02be3",
            },
            "pack_artifact": roman_artifact,
            "artifacts": [
                {"path": "fixture/npi-roman-review.json", "sha256": "6" * 64}
            ],
        })

        lock = self.build(review=review)
        direct = next(row for row in lock["profiles"] if row["profile_id"] == "npi-Deva-NP")
        roman = next(row for row in lock["profiles"] if row["profile_id"] == roman_profile["profile_id"])
        self.assertTrue(roman["selectable"])
        self.assertFalse(roman["default_enabled"])
        self.assertEqual(direct["pack_binding"], roman["pack_binding"])
        self.assertEqual(
            direct["pack_artifact"]["artifact_sha256"],
            roman["pack_artifact"]["artifact_sha256"],
        )
        self.assertEqual(roman["lookup_kind"], "alias_prefix")

        broken = copy.deepcopy(review)
        broken["evidence"][-1]["pack_artifact"]["alias_key_count"] = 0
        with self.assertRaisesRegex(CatalogError, "no alias-prefix index"):
            self.build(review=broken)

    def test_blocked_profiles_have_no_shipping_authority(self) -> None:
        profiles = self.build()["profiles"]
        for profile in profiles:
            with self.subTest(profile_id=profile["profile_id"]):
                self.assertTrue(
                    {
                        "pack_binding",
                        "pack_artifact",
                        "conversion_binding",
                        "conversion_artifact",
                    }.issubset(profile)
                )
                if profile["selectable"]:
                    self.assertIsNone(profile["blocked_reason"])
                    self.assertIsNone(profile["blocked_detail"])
                    self.assertTrue(profile["default_enabled"])
                    self.assertEqual(
                        profile["pack_binding"], profile["pack_artifact"]["pack_id"]
                    )
                    self.assertIsNone(profile["conversion_binding"])
                    self.assertIsNone(profile["conversion_artifact"])
                    self.assertTrue(profile["evidence_artifacts"])
                    self.assertTrue(profile["evidence_ids"])
                    self.assertEqual(profile["layout_revision"], 1)
                    self.assertRegex(profile["layout_source_sha256"], r"^[0-9a-f]{64}$")
                else:
                    self.assertIsNotNone(profile["blocked_reason"])
                    self.assertTrue(profile["blocked_detail"])
                    self.assertFalse(profile["default_enabled"])
                    self.assertIsNone(profile["pack_binding"])
                    self.assertIsNone(profile["pack_artifact"])
                    self.assertIsNone(profile["conversion_binding"])
                    self.assertIsNone(profile["conversion_artifact"])
                    self.assertEqual(profile["evidence_ids"], [])
                    self.assertEqual(profile["evidence_artifacts"], [])
                    self.assertIsNone(profile["layout_revision"])
                    self.assertIsNone(profile["layout_source_sha256"])

    def test_visual_layout_is_independent_from_roman_lookup(self) -> None:
        profiles = self.build()["profiles"]
        roman = [row for row in profiles if row["method_type"] == "roman_phonetic"]
        self.assertTrue(roman)
        self.assertTrue(all(row["layout_id"] == "latn-qwerty-us-v1" for row in roman))
        self.assertTrue(all(row["lookup_kind"] == "alias_prefix" for row in roman))

    def test_named_varieties_and_rai_languages_remain_distinct(self) -> None:
        targets = {row["target_id"]: row for row in self.build()["targets"]}
        self.assertEqual(targets["gvr"]["scope"], "variety")
        self.assertEqual(targets["gvr"]["group"], "Gurung")
        self.assertEqual(targets["gvr"]["variety"], "Central Gurung")
        self.assertEqual(targets["bap"]["scope"], "language")
        self.assertEqual(targets["bap"]["group"], "Rai/Kiranti")
        self.assertEqual(targets["bap"]["display_label"], "Bantawa")
        self.assertNotIn("rai", targets)

    def test_output_is_byte_deterministic_and_check_detects_drift(self) -> None:
        first = _canonical_bytes(self.build())
        second = _canonical_bytes(self.build())
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "shipping-profiles.lock.json"
            arguments = [
                "--catalog", str(CATALOG_PATH),
                "--review", str(REVIEW_PATH),
                "--output", str(output),
            ]
            self.assertEqual(main(arguments), 0)
            self.assertEqual(main(arguments + ["--check"]), 0)
            output.write_bytes(output.read_bytes() + b" ")
            with self.assertRaisesRegex(SystemExit, "stale"):
                main(arguments + ["--check"])

    def test_evidence_artifact_files_are_content_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "evidence.txt"
            artifact.write_bytes(b"reviewed evidence\n")
            review = {
                "evidence": [{
                    "artifacts": [{
                        "path": "evidence.txt",
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }]
                }]
            }
            _validate_evidence_files(review, root)
            artifact.write_bytes(b"drifted evidence\n")
            with self.assertRaisesRegex(CatalogError, "SHA-256 mismatch"):
                _validate_evidence_files(review, root)

    def test_rejects_count_drift(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["packs"].pop()
        with self.assertRaisesRegex(CatalogError, "count mismatch"):
            self.build(catalog=catalog)

    def test_rejects_non_integer_or_extra_review_counts(self) -> None:
        review = copy.deepcopy(self.review)
        review["expected_counts"]["selectable"] = True
        with self.assertRaisesRegex(CatalogError, "non-negative integer"):
            self.build(review=review)
        review = copy.deepcopy(self.review)
        review["expected_counts"]["extra"] = 0
        with self.assertRaisesRegex(CatalogError, "contain exactly"):
            self.build(review=review)

    def test_rejects_unbound_pack_artifact(self) -> None:
        review = copy.deepcopy(self.review)
        review["evidence"][0]["pack_artifact"]["pack_id"] = "other-pack"
        with self.assertRaisesRegex(CatalogError, "does not match pack_binding"):
            self.build(review=review)

    def test_rejects_unknown_review_overrides(self) -> None:
        review = copy.deepcopy(self.review)
        review["target_overrides"]["zzz"] = {"native_label": "Unknown"}
        with self.assertRaisesRegex(CatalogError, "unknown targets"):
            self.build(review=review)

    def test_rejects_missing_release_evidence_gate(self) -> None:
        review = copy.deepcopy(self.review)
        review["evidence"][0]["gates"].remove("redistribution_review")
        with self.assertRaisesRegex(CatalogError, "does not pass required gates"):
            self.build(review=review)

    def test_release_authority_rejects_internal_pack_mode(self) -> None:
        review = copy.deepcopy(self.review)
        review["evidence"][0]["pack_artifact"]["release_mode"] = "internal"
        with self.assertRaisesRegex(CatalogError, "internal pack to release authority"):
            self.build(review=review)

    def test_authority_rejects_mismatched_blocked_reason_policy(self) -> None:
        review = copy.deepcopy(self.review)
        review["blocked_reason_by_method"]["direct"] = "DIRECT_PROFILE_NOT_INTERNAL_READY"
        with self.assertRaisesRegex(CatalogError, "does not match release authority"):
            self.build(review=review)

        review = copy.deepcopy(self.review)
        review["authority"] = "internal"
        with self.assertRaisesRegex(CatalogError, "does not match internal authority"):
            self.build(review=review)

    def test_rejects_unpinned_or_inconsistent_layout_evidence(self) -> None:
        review = copy.deepcopy(self.review)
        del review["evidence"][0]["layout_binding"]
        with self.assertRaisesRegex(CatalogError, "must contain exactly"):
            self.build(review=review)
        review = copy.deepcopy(self.review)
        review["evidence"][0]["layout_binding"]["layout_id"] = "latn-other-v1"
        with self.assertRaisesRegex(CatalogError, "does not match profile"):
            self.build(review=review)

    def test_rejects_method_engine_mismatch(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["packs"][0]["input_methods"][0]["engine_kind"] = "alias_decoder"
        with self.assertRaisesRegex(CatalogError, "incompatible"):
            self.build(catalog=catalog)

    def test_rejects_unsafe_script_direction(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["packs"][1]["input_methods"][1]["source_script"] = "Deva"
        with self.assertRaisesRegex(CatalogError, "Roman method"):
            self.build(catalog=catalog)


if __name__ == "__main__":
    unittest.main()
