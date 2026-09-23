from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DumiMeasurementRunnerTest(unittest.TestCase):
    def runner(self) -> str:
        return (ROOT / "tools/run_cdjk_dumi_measurement.sh").read_text(
            encoding="utf-8"
        )

    def test_runner_requires_verified_khaling_before_relock_and_matrix(self) -> None:
        runner = self.runner()

        prerequisite = "stage=khaling_prerequisite"
        manifest_check = "sha256sum -c final-evidence-sha256.txt"
        prerequisite_verified = "khaling_prerequisite_verified=1"
        dumi_raw_scan = 'actual_raw_sha256="$(sha256sum "$raw"'
        relock_call = 'bash "$relock_runner" "$evidence/relock"'
        matrix_call = 'bash "$matrix_runner"'
        for marker in (
            prerequisite,
            manifest_check,
            prerequisite_verified,
            dumi_raw_scan,
            relock_call,
            matrix_call,
        ):
            self.assertIn(marker, runner)
        self.assertLess(runner.index(prerequisite), runner.index(manifest_check))
        self.assertLess(
            runner.index(manifest_check), runner.index(prerequisite_verified)
        )
        self.assertLess(
            runner.index(prerequisite_verified), runner.index(dumi_raw_scan)
        )
        self.assertLess(runner.index(dumi_raw_scan), runner.index(relock_call))
        self.assertLess(runner.index(relock_call), runner.index(matrix_call))
        for status in (
            "completed_stage=complete",
            "relock_verified=1",
            "matrix_verified=1",
            "sequence_complete=1",
            "remote_exit_status=0",
        ):
            self.assertIn(status, runner)
        self.assertIn("khaling_prerequisite_verified=1", runner)
        self.assertIn("expected_khaling_raw_sha256", runner)
        self.assertIn("recreate_khaling_manifest", runner)
        self.assertIn('find "$khaling_evidence" -type l', runner)
        self.assertIn("expected-khaling-run-status.txt", runner)
        self.assertIn('.evidence_root == $evidence', runner)
        self.assertIn('.relock_evidence == ($evidence + "/relock")', runner)
        self.assertIn("nepali-khaling.sil-apk.dict.jsonl", runner)

    def test_runner_pins_dumi_without_selecting_a_candidate(self) -> None:
        runner = self.runner()

        for marker in (
            "nepali-dumi.sil-apk.dict.jsonl",
            "dus-apk",
            "dus-Deva-NP",
            "dus-deva-direct",
            "sil-apk/dumi",
            "2252",
            "277511",
            "1d8453339c727ee5c63fc4fbf64ec80619ea82cc559b31b9224826e1d0902ffc",
            'layout_id == "pending-dus-deva-direct"',
            "selectable == false",
            "pack_artifact == null",
            "pack_binding == null",
            "remain unselected",
        ):
            self.assertIn(marker, runner)
        self.assertNotIn("--scope all", runner)
        self.assertNotIn("run_cdjk_sil_apk_candidate_pack", runner)
        self.assertNotIn("finalize_internal_pack_milestone", runner)

    def test_runner_binds_read_only_sequence_evidence_fail_closed(self) -> None:
        runner = self.runner()

        for marker in (
            "active-internal-state-after-relock.txt",
            "active-internal-state-after-matrix.txt",
            "internal_state_unchanged_during_matrix: true",
            "dumi_profile_unselected_before_matrix: true",
            "khaling-prerequisite-sha256.txt",
            "khaling-recreated-final-evidence-sha256.before.txt",
            "khaling-recreated-final-evidence-sha256.after.txt",
            "khaling-evidence-manifest-recheck.txt",
            "Khaling prerequisite changed during the Dumi measurement",
            "sequence-summary.json",
            "final-evidence-sha256.txt",
            "khaling_prerequisite_verified=%s",
            "sequence_complete=1",
            "stage=complete",
        ):
            self.assertIn(marker, runner)
        self.assertIn("((.ranking | length) == .layout_count)", runner)
        self.assertIn("((.measured_ranking | length) == .layout_count)", runner)
        self.assertNotIn(".ranking | length == .layout_count", runner)
        self.assertNotIn(".measured_ranking | length == .layout_count", runner)
        self.assertIn(
            'cmp "$evidence/active-internal-state-after-relock.txt"', runner
        )
        matrix_call = 'bash "$matrix_runner"'
        final_recheck = "stage=khaling_prerequisite_recheck"
        sequence_summary = "stage=sequence_summary"
        self.assertLess(runner.index(matrix_call), runner.index(final_recheck))
        self.assertLess(runner.index(final_recheck), runner.index(sequence_summary))
        self.assertLess(
            runner.index(sequence_summary), runner.rindex("sequence_complete=1")
        )


if __name__ == "__main__":
    unittest.main()
