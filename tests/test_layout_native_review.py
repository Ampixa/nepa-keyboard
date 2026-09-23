from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
import unicodedata
from pathlib import Path

from tools.build_keyboard_layouts import LayoutError, _canonical_bytes
from tools.validate_keyboard_layout_candidate import validate_candidate
from tools.validate_layout_native_review import (
    _validate_accepted_candidate_decisions,
    _validate_completed_decision_consistency,
    build_parser,
    validate_review,
)


ROOT = Path(__file__).resolve().parents[1]
REVIEW_NAME = "newa-nepal-qwerty-direct-v1.review.json"
CANDIDATE_NAME = "newa-nepal-qwerty-direct-v1.json"


class LayoutNativeReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.research = self.root / "layouts" / "research"
        self.reviews = self.root / "layouts" / "reviews"
        self.notices = self.root / "layouts" / "internal" / "notices"
        self.research.mkdir(parents=True)
        self.reviews.mkdir(parents=True)
        self.notices.mkdir(parents=True)
        self.candidate = self.research / CANDIDATE_NAME
        self.review = self.reviews / REVIEW_NAME
        shutil.copy2(ROOT / "layouts" / "research" / CANDIDATE_NAME, self.candidate)
        shutil.copy2(ROOT / "layouts" / "reviews" / REVIEW_NAME, self.review)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def read_review(self) -> dict[str, object]:
        return json.loads(self.review.read_text(encoding="utf-8"))

    def write_review(self, value: dict[str, object]) -> None:
        self.review.write_bytes(_canonical_bytes(value))

    def read_candidate(self) -> dict[str, object]:
        return json.loads(self.candidate.read_text(encoding="utf-8"))

    def write_candidate(self, value: dict[str, object]) -> None:
        self.candidate.write_bytes(_canonical_bytes(value))

    def bind_candidate_source(self, review: dict[str, object]) -> None:
        review["candidate"]["source_sha256"] = hashlib.sha256(
            self.candidate.read_bytes()
        ).hexdigest()

    def test_pending_packet_is_deterministic_complete_and_non_promoting(self) -> None:
        first = validate_review(self.review, repository_root=self.root)
        second = validate_review(self.review, repository_root=self.root)
        self.assertEqual(_canonical_bytes(first), _canonical_bytes(second))
        self.assertEqual(first["native_review_validation_version"], 1)
        self.assertEqual(first["review_profile"], "newa_qwerty_direct_v1")
        self.assertEqual(first["status"], "pending")
        self.assertEqual(first["section_count"], 4)
        self.assertEqual(first["decision_count"], 8)
        self.assertEqual(first["coverage_item_count"], 15)
        self.assertEqual(first["missing_critical_scalar_count"], 5)
        self.assertEqual(first["unresolved_count"], 27)
        self.assertEqual(
            first["profile_effect"],
            {
                "profile_id": "new-Newa-NP",
                "selectable": False,
                "default_enabled": False,
                "bind_layout": False,
            },
        )
        self.assertEqual(
            first["candidate"]["source"]["sha256"],
            hashlib.sha256(self.candidate.read_bytes()).hexdigest(),
        )
        self.assertEqual(len(first["candidate"]["compiled_sha256"]), 64)

    def test_checked_review_inventory_is_closed_and_validated(self) -> None:
        entries = sorted((ROOT / "layouts" / "reviews").iterdir())
        self.assertEqual([path.name for path in entries], [REVIEW_NAME])
        for entry in entries:
            self.assertTrue(entry.is_file())
            self.assertFalse(entry.is_symlink())
            self.assertTrue(entry.name.endswith(".review.json"))
            report = validate_review(entry, repository_root=ROOT)
            self.assertEqual(report["status"], "pending")

    def test_packet_enumerates_every_non_action_candidate_key_once(self) -> None:
        packet = self.read_review()
        section_keys = [
            key_id for section in packet["sections"] for key_id in section["key_ids"]
        ]
        self.assertEqual(len(section_keys), 109)
        self.assertEqual(len(section_keys), len(set(section_keys)))
        self.assertEqual(
            {section["section_id"] for section in packet["sections"]},
            {"base_grid", "shift_grid", "symbols_grid", "numeric_grid"},
        )

    def test_compiler_schema_and_validator_evidence_are_bound_to_loaded_code(
        self,
    ) -> None:
        report = validate_review(self.review, repository_root=self.root)
        self.assertEqual(
            report["contract"]["schema"]["sha256"],
            hashlib.sha256(
                (ROOT / "schemas" / "layout-native-review-v1.schema.json").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            report["contract"]["validator"]["sha256"],
            hashlib.sha256(
                (ROOT / "tools" / "validate_layout_native_review.py").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            report["candidate"]["compiler"]["sha256"],
            hashlib.sha256(
                (ROOT / "tools" / "build_keyboard_layouts.py").read_bytes()
            ).hexdigest(),
        )

    def test_rejects_contract_candidate_and_compiled_hash_drift(self) -> None:
        mutations = (
            ("schema", "review.contract.schema SHA-256 mismatch"),
            ("validator", "review.contract.validator SHA-256 mismatch"),
            ("candidate", "review.candidate source SHA-256 mismatch"),
            ("compiled", "review.candidate compiled SHA-256 mismatch"),
        )
        original = self.read_review()
        for mutation, message in mutations:
            with self.subTest(mutation=mutation):
                packet = copy.deepcopy(original)
                if mutation in {"schema", "validator"}:
                    packet["contract"][mutation]["sha256"] = "0" * 64
                elif mutation == "candidate":
                    packet["candidate"]["source_sha256"] = "0" * 64
                else:
                    packet["candidate"]["compiled_sha256"] = "0" * 64
                self.write_review(packet)
                with self.assertRaisesRegex(LayoutError, message):
                    validate_review(self.review, repository_root=self.root)
        self.write_review(original)

    def test_rejects_incomplete_sections_decisions_and_coverage_bindings(self) -> None:
        mutations = (
            (
                lambda packet: packet["sections"][0]["key_ids"].pop(),
                "do not cover the compiled base layer",
            ),
            (
                lambda packet: packet["decisions"].pop(),
                "closed decision count",
            ),
            (
                lambda packet: packet["decisions"][0]["options"].reverse(),
                "key and option contract",
            ),
            (
                lambda packet: packet["decisions"][0].update(
                    {"question": "A misleading replacement question"}
                ),
                "question does not match",
            ),
            (
                lambda packet: packet["coverage"][0].update(
                    {"key_ids": ["base.r0.k0"], "availability": "covered"}
                ),
                "key_ids do not match",
            ),
        )
        original = self.read_review()
        for mutate, message in mutations:
            with self.subTest(message=message):
                packet = copy.deepcopy(original)
                mutate(packet)
                self.write_review(packet)
                with self.assertRaisesRegex(LayoutError, message):
                    validate_review(self.review, repository_root=self.root)
        self.write_review(original)

    def test_pending_review_cannot_claim_resolution_or_profile_effect(self) -> None:
        original = self.read_review()
        for mutate, message in (
            (
                lambda packet: packet["decisions"][0].update(
                    {"selected_option": "keep_u1144b"}
                ),
                "pending decision must be unresolved",
            ),
            (
                lambda packet: packet["decisions"][0].update(
                    {
                        "state": "accepted",
                        "selected_option": "keep_u1144b",
                    }
                ),
                "requires every item to remain pending",
            ),
            (
                lambda packet: packet["profile_effect"].update({"selectable": True}),
                "closed no-promotion state",
            ),
            (
                lambda packet: packet["profile_effect"].update({"selectable": 0}),
                "closed no-promotion state",
            ),
            (
                lambda packet: packet.update({"status": "accepted"}),
                "completed review must bind compiled_sha256",
            ),
        ):
            packet = copy.deepcopy(original)
            mutate(packet)
            self.write_review(packet)
            with self.assertRaisesRegex(LayoutError, message):
                validate_review(self.review, repository_root=self.root)
        self.write_review(original)

    def test_integer_constants_reject_json_booleans(self) -> None:
        original = self.read_review()
        for field, mutate in (
            (
                "review.review_format_version",
                lambda packet: packet.update({"review_format_version": True}),
            ),
            (
                "review.candidate.revision",
                lambda packet: packet["candidate"].update({"revision": True}),
            ),
        ):
            with self.subTest(field=field):
                packet = copy.deepcopy(original)
                mutate(packet)
                self.write_review(packet)
                with self.assertRaisesRegex(LayoutError, f"{field} must be an integer"):
                    validate_review(self.review, repository_root=self.root)
        self.write_review(original)

    def test_accepted_decisions_must_match_candidate_and_accessibility(self) -> None:
        packet = self.read_review()
        decisions = packet["decisions"]
        for decision in decisions:
            decision["selected_option"] = decision["options"][0]
        next(row for row in decisions if row["decision_id"] == "murmured_resonants")[
            "selected_option"
        ] = "accept_shift_symbol_coverage"
        accessibility_decision = next(
            row for row in decisions if row["decision_id"] == "accessibility_names"
        )
        accessibility_decision["selected_option"] = "native_newa_names"

        key_ids = [
            key_id for section in packet["sections"] for key_id in section["key_ids"]
        ]
        key_index = {
            key_id: {
                "text": key_id,
                "content_description": f"Spoken {key_id}",
            }
            for key_id in key_ids
        }
        key_index["base.r2.k7"]["text"] = "\U0001144b"
        key_index["shift.r1.k8"]["text"] = "\U0001142f"
        key_index["shift.r2.k7"]["text"] = "\U0001144c"
        key_index["symbols.r2.k4"]["text"] = "\U00011449"
        key_index["base.r2.k8"]["text"] = "\U00011442"
        key_index["base.r2.k9"]["text"] = "\u200d"
        key_index["base.r2.k10"]["text"] = "\u200c"
        for key_id, text in zip(
            (
                "shift.r0.k0",
                "shift.r0.k1",
                "shift.r0.k2",
                "shift.r0.k3",
                "shift.r0.k4",
            ),
            ("\U00011413", "\U00011419", "\U00011424", "\U0001142a", "\U0001142d"),
            strict=True,
        ):
            key_index[key_id]["text"] = text

        _validate_completed_decision_consistency(decisions)
        _validate_accepted_candidate_decisions(decisions, key_index)

        accessibility_decision["selected_option"] = "english_unicode_names"
        for key in key_index.values():
            key["content_description"] = " + ".join(
                unicodedata.name(character) for character in key["text"]
            )
        _validate_accepted_candidate_decisions(decisions, key_index)

        accessibility_decision["selected_option"] = "bilingual_names"
        for key_id, key in key_index.items():
            english_name = " + ".join(
                unicodedata.name(character) for character in key["text"]
            )
            key["content_description"] = f"Native {key_id} · {english_name}"
        _validate_accepted_candidate_decisions(decisions, key_index)

        accessibility_decision["selected_option"] = "native_newa_names"
        for key_id, key in key_index.items():
            key["content_description"] = f"Spoken {key_id}"

        base_decision = next(
            row for row in decisions if row["decision_id"] == "base_punctuation"
        )
        base_decision["selected_option"] = "use_u1144d"
        with self.assertRaisesRegex(LayoutError, "base_punctuation.*bound candidate"):
            _validate_accepted_candidate_decisions(decisions, key_index)
        base_decision["selected_option"] = "keep_u1144b"

        key_index["numeric.r0.k0"]["text"] = "1"
        key_index["numeric.r0.k0"]["content_description"] = "1"
        with self.assertRaisesRegex(LayoutError, "meaningful native spoken name"):
            _validate_accepted_candidate_decisions(decisions, key_index)

        for key in key_index.values():
            key["content_description"] = "x"
        with self.assertRaisesRegex(LayoutError, "meaningful native spoken name"):
            _validate_accepted_candidate_decisions(decisions, key_index)

        resonant_decision = next(
            row for row in decisions if row["decision_id"] == "murmured_resonants"
        )
        resonant_decision["selected_option"] = "require_layout_v2_longpress"
        with self.assertRaisesRegex(LayoutError, "inconsistent.*long-press"):
            _validate_completed_decision_consistency(decisions)

    def test_current_missing_repertoire_cannot_be_accepted(
        self,
    ) -> None:
        packet = self.read_review()
        packet["status"] = "accepted"
        packet["candidate"]["compiled_sha256"] = validate_candidate(
            self.candidate,
            repository_root=self.root,
        )["compiled_sha256"]
        for section in packet["sections"]:
            section["state"] = "accepted"
        for decision in packet["decisions"]:
            decision["state"] = "accepted"
            decision["selected_option"] = decision["options"][0]
        for coverage in packet["coverage"]:
            coverage["review_state"] = "accepted"
        packet["reviewer"] = {
            "name": "Native review fixture",
            "native_language": "Nepal Bhasa",
            "experience": "Fixture demonstrating the completed contract",
        }
        packet["reviewed_at"] = "2026-07-16"
        self.write_review(packet)

        with self.assertRaisesRegex(LayoutError, "missing critical Newa scalars"):
            validate_review(self.review, repository_root=self.root)

        packet["coverage"][0]["review_state"] = "pending"
        self.write_review(packet)
        with self.assertRaisesRegex(LayoutError, "cannot contain unresolved items"):
            validate_review(self.review, repository_root=self.root)

    def test_completed_rejection_binds_candidate_reviewer_and_decisions(self) -> None:
        packet = self.read_review()
        packet["status"] = "rejected"
        packet["candidate"]["compiled_sha256"] = validate_candidate(
            self.candidate,
            repository_root=self.root,
        )["compiled_sha256"]
        for section in packet["sections"]:
            section["state"] = "accepted"
        for decision in packet["decisions"]:
            decision["state"] = "accepted"
            decision["selected_option"] = decision["options"][0]
        packet["decisions"][0]["state"] = "rejected"
        for coverage in packet["coverage"]:
            coverage["review_state"] = "accepted"
        packet["reviewer"] = {
            "name": "Native review fixture",
            "native_language": "Nepal Bhasa",
            "experience": "Fixture demonstrating the rejected contract",
        }
        packet["reviewed_at"] = "2026-07-16"
        self.write_review(packet)

        report = validate_review(self.review, repository_root=self.root)
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["unresolved_count"], 0)

        packet["reviewer"]["name"] = "\u200d"
        self.write_review(packet)
        with self.assertRaisesRegex(LayoutError, r"unsafe U\+200D"):
            validate_review(self.review, repository_root=self.root)

        packet["reviewer"]["name"] = "Native review fixture"
        packet["reviewed_at"] = "20260716"
        self.write_review(packet)
        with self.assertRaisesRegex(LayoutError, "must use YYYY-MM-DD"):
            validate_review(self.review, repository_root=self.root)

    def test_rejects_forbidden_candidate_scalar_even_when_source_hash_is_rebound(
        self,
    ) -> None:
        candidate = self.read_candidate()
        candidate["layers"]["base"]["rows"][0][0] = "\ufffd"
        self.write_candidate(candidate)
        packet = self.read_review()
        self.bind_candidate_source(packet)
        self.write_review(packet)
        with self.assertRaisesRegex(LayoutError, r"contains forbidden U\+FFFD"):
            validate_review(self.review, repository_root=self.root)

    def test_rejects_duplicate_json_keys_and_unsafe_review_paths(self) -> None:
        encoded = self.review.read_text(encoding="utf-8")
        self.review.write_text(
            encoded.replace(
                '"review_format_version": 1,',
                '"review_format_version": 1,\n  "review_format_version": 1,',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(LayoutError, "duplicate JSON key"):
            validate_review(self.review, repository_root=self.root)

        self.review.write_text(encoded, encoding="utf-8")
        outside = self.root / REVIEW_NAME
        shutil.copy2(self.review, outside)
        with self.assertRaisesRegex(LayoutError, "direct .review.json child"):
            validate_review(outside, repository_root=self.root)
        symlink = self.reviews / "linked.review.json"
        symlink.symlink_to(self.review)
        with self.assertRaisesRegex(LayoutError, "regular file"):
            validate_review(symlink, repository_root=self.root)

    def test_cli_has_no_output_lock_or_promotion_options(self) -> None:
        actions = {
            option
            for action in build_parser()._actions
            for option in action.option_strings
        }
        self.assertEqual(actions, {"-h", "--help", "--review"})


if __name__ == "__main__":
    unittest.main()
