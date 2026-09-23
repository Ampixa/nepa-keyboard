from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_cdjk_nepal_bhasa_candidate_pack.sh"
SPEC = ROOT / "catalog/nepal-bhasa-candidate-pack-v0.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NepalBhasaCandidatePackRunnerTest(unittest.TestCase):
    def test_runner_is_cdjk_only_double_build_and_candidate_only(self) -> None:
        runner = RUNNER.read_text(encoding="utf-8")
        subprocess.run(["bash", "-n", str(RUNNER)], check=True)

        self.assertIn('[[ "$(uname -s)" != Linux', runner)
        self.assertIn('"$(hostname -s)" != cdjk', runner)
        self.assertIn("preexisting-heavy-python", runner)
        self.assertIn("preexisting-android-builds", runner)
        self.assertIn("for run in a b; do", runner)
        self.assertIn("build_nepal_bhasa_internal_source.py", runner)
        self.assertIn("audit_nepal_bhasa_tsv_contract.py", runner)
        self.assertIn("--check", runner)
        self.assertIn("-m nepa_keyboard.compiler build", runner)
        self.assertIn("-m nepa_keyboard.compiler inspect", runner)
        self.assertIn("--mode internal", runner)
        self.assertIn('cmp "$evidence/a/$pack_id.nkp"', runner)
        self.assertIn("promotion-state-before.txt", runner)
        self.assertIn("promotion-state-after.txt", runner)
        self.assertIn("promotion_state_unchanged=1", runner)
        self.assertIn("profile_promoted: false", runner)
        self.assertIn("layout_id: null", runner)
        self.assertIn("final-evidence-sha256.txt", runner)
        self.assertNotIn("finalize_internal_pack_milestone_v1.py", runner)

    def test_spec_pins_sources_code_counts_policies_and_vectors(self) -> None:
        spec = json.loads(SPEC.read_text(encoding="utf-8"))
        self.assertEqual(spec["format_version"], 1)
        self.assertEqual(spec["claim_scope"], "candidate_only")
        self.assertEqual(spec["target_id"], "new")
        self.assertEqual(spec["resource_id"], "new-nepali-trilingual")
        self.assertEqual(spec["candidate_column"], "newar")
        self.assertEqual(spec["pack_id"], "new-Deva-NP")
        self.assertIsNone(spec["layout_id"])
        self.assertEqual(spec["layout_policy"], "unselected; candidate artifact only")
        self.assertEqual(
            spec["adapter_sha256"],
            sha256(ROOT / "tools/build_nepal_bhasa_internal_source.py"),
        )
        self.assertEqual(
            spec["compiler_sha256"],
            sha256(ROOT / "src/nepa_keyboard/compiler.py"),
        )
        self.assertEqual(
            spec["runtime_sha256"],
            sha256(ROOT / "src/nepa_keyboard/runtime.py"),
        )
        self.assertEqual(
            spec["locked_state_sha256"],
            {
                "android_gradle": (
                    "5f5490c5ccaed9b80763b46339e34fe7c2e96ab00afc75089412ca5d101d18ac"
                ),
                "layout_lock": (
                    "7e56ed18acf7c4134c2473dab1dfd64452a6698db4c17d70ff9ec4e3972987c0"
                ),
                "profile_lock": (
                    "3fad647edc8303193985bcad96134390ab86ea53c636bcbb7363b79968cd7334"
                ),
            },
        )
        self.assertEqual(
            spec["raw_sha256"],
            "4167c21626674fd1e71bd814c6b2bbb33d2d35ab0f5d5bb071b7b43e071d7929",
        )
        self.assertEqual(spec["expected"]["source_rows"], 9708)
        self.assertEqual(spec["expected"]["accepted_rows"], 9647)
        self.assertEqual(spec["expected"]["rejected_rows"], 61)
        self.assertEqual(spec["expected"]["candidate_surfaces"], 5417)
        self.assertEqual(spec["expected"]["duplicate_surfaces_merged"], 4230)
        self.assertEqual(len(spec["expected"]["required_scalars"]), 66)
        self.assertEqual(len(spec["inspection_vectors"]), 5)
        self.assertEqual(
            set(spec["policies"]),
            {"aliases", "filter", "joiners", "normalization", "ranking", "splitting"},
        )

    def test_runner_tracks_every_state_and_implementation_input(self) -> None:
        runner = RUNNER.read_text(encoding="utf-8")
        for path in (
            "catalog/resources.json",
            "catalog/internal-profile-review.json",
            "catalog/internal-profiles.lock.json",
            "layouts/internal/layouts-v1.lock.json",
            "android/ime-app/build.gradle.kts",
            "tools/build_nepal_bhasa_internal_source.py",
            "tools/audit_nepal_bhasa_tsv_contract.py",
            "src/nepa_keyboard/compiler.py",
            "src/nepa_keyboard/runtime.py",
            "tests/test_nepal_bhasa_internal_source.py",
            "tests/test_nepal_bhasa_candidate_pack_runner.py",
        ):
            with self.subTest(path=path):
                self.assertIn(path, runner)


if __name__ == "__main__":
    unittest.main()
