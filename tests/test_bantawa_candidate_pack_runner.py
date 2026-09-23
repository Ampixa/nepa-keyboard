from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BantawaCandidatePackRunnerTest(unittest.TestCase):
    def runner(self) -> str:
        return (ROOT / "tools/run_cdjk_bantawa_candidate_pack.sh").read_text(
            encoding="utf-8"
        )

    def test_verified_source_probe_precedes_candidate_work(self) -> None:
        runner = self.runner()
        for marker in (
            "stage=prerequisite",
            "prerequisite-manifest-recreated.before.txt",
            "expected-prerequisite-status.txt",
            ".selections_remain_unselected == true",
            "prerequisite_verified=1",
            "stage=double_build",
            "stage=layout_audit",
            "stage=inspection",
            "prerequisite-manifest-recreated.after.txt",
        ):
            self.assertIn(marker, runner)
        self.assertLess(runner.index("stage=prerequisite"), runner.index("prerequisite_verified=1"))
        self.assertLess(runner.index("prerequisite_verified=1"), runner.index("stage=double_build"))
        self.assertLess(runner.index("stage=double_build"), runner.index("stage=layout_audit"))
        self.assertLess(runner.index("stage=layout_audit"), runner.index("stage=inspection"))

    def test_double_build_layout_and_release_gates_are_fail_closed(self) -> None:
        runner = self.runner()
        for marker in (
            "build_bantawa_internal_source.py",
            "audit_bantawa_candidate_layout.py",
            'for run in a b; do',
            'cmp "$evidence/a/$pack_id.nkp"',
            "duplicate_surfaces_merged",
            "accountable_lossy_roundtrip_rows",
            "collision_surfaces_across_distinct_headwords",
            "--mode release",
            "release_negative_exit_status",
            "must-not-release.nkp",
            "unsupported_scalars == []",
            "--check",
            "inspection-summary.jsonl",
        ):
            self.assertIn(marker, runner)

    def test_remote_host_and_immutable_evidence_guards_remain_present(self) -> None:
        runner = self.runner()
        for marker in (
            '"$(hostname -s)" != cdjk',
            "flock -n 9",
            "available_kib < 8 * 1024 * 1024",
            "preexisting-heavy-python.txt",
            "preexisting-android-builds.txt",
            'find "$evidence" -type l -print -quit',
            'find "$evidence" ! -type d ! -type f -print -quit',
            "project-state.before.txt",
            "project-state.after.txt",
            "sequence-summary.json",
            "final-evidence-sha256.txt",
            "sequence_complete=1",
            "stage=complete",
        ):
            self.assertIn(marker, runner)


if __name__ == "__main__":
    unittest.main()
