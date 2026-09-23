from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class KhalingMeasurementRunnerTest(unittest.TestCase):
    def test_runner_orders_committed_internal_relock_before_matrix(self) -> None:
        runner = (ROOT / "tools/run_cdjk_khaling_measurement.sh").read_text(
            encoding="utf-8"
        )

        relock_call = 'bash "$relock_runner" "$evidence/relock"'
        matrix_call = 'bash "$matrix_runner"'
        self.assertIn(relock_call, runner)
        self.assertIn(matrix_call, runner)
        self.assertLess(runner.index(relock_call), runner.index(matrix_call))
        self.assertIn("'transaction_committed=1'", runner)
        self.assertIn("'rollback_exit_status=0'", runner)
        self.assertIn("'remote_exit_status=0'", runner)
        self.assertIn("relock_verified=1", runner)
        self.assertNotIn("--scope all", runner)

    def test_runner_pins_exact_khaling_resource_and_raw_identity(self) -> None:
        runner = (ROOT / "tools/run_cdjk_khaling_measurement.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("nepali-khaling.sil-apk.dict.jsonl", runner)
        self.assertIn("klr-apk", runner)
        self.assertIn("sil-apk/khaling", runner)
        self.assertIn(
            "442415559f1ec6191b2624e27439cc22438aaf24d19b4124571c826774c2adb4",
            runner,
        )
        self.assertIn(".raw_input.records == 4513", runner)
        self.assertIn(".raw_input.bytes == 558925", runner)

    def test_runner_proves_matrix_is_read_only_and_content_binds_evidence(self) -> None:
        runner = (ROOT / "tools/run_cdjk_khaling_measurement.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("active-internal-state-after-relock.txt", runner)
        self.assertIn("active-internal-state-after-matrix.txt", runner)
        self.assertIn("internal_state_unchanged_during_matrix: true", runner)
        self.assertIn("sequence-summary.json", runner)
        self.assertIn("final-evidence-sha256.txt", runner)
        self.assertIn("((.ranking | length) == .layout_count)", runner)
        self.assertIn("((.measured_ranking | length) == .layout_count)", runner)
        self.assertNotIn(".ranking | length == .layout_count", runner)
        self.assertNotIn(".measured_ranking | length == .layout_count", runner)
        self.assertIn("sequence_complete=1", runner)
        self.assertIn('stage=complete', runner)


if __name__ == "__main__":
    unittest.main()
