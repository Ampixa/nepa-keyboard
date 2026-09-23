from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BantawaSourceProbeRunnerTest(unittest.TestCase):
    def runner(self) -> str:
        return (ROOT / "tools/run_cdjk_bantawa_source_probe.sh").read_text(
            encoding="utf-8"
        )

    def test_completed_dumi_gate_precedes_every_bantawa_scan_or_probe(self) -> None:
        runner = self.runner()

        prerequisite = "stage=dumi_prerequisite"
        manifest_recreation = (
            '"$evidence/dumi-recreated-final-evidence-sha256.before.txt"'
        )
        verified = "dumi_prerequisite_verified=1"
        host_preflight = "stage=host_preflight"
        raw_scan = 'actual_raw_sha256="$(sha256sum "$raw"'
        focused_tests = "stage=focused_tests"
        double_parse = "stage=double_parse"
        for marker in (
            prerequisite,
            manifest_recreation,
            verified,
            host_preflight,
            raw_scan,
            focused_tests,
            double_parse,
        ):
            self.assertIn(marker, runner)
        self.assertLess(runner.index(host_preflight), runner.index(prerequisite))
        self.assertLess(runner.index(prerequisite), runner.index(manifest_recreation))
        self.assertLess(runner.index(manifest_recreation), runner.index(verified))
        self.assertLess(runner.index(verified), runner.index(raw_scan))
        self.assertLess(runner.index(raw_scan), runner.index(focused_tests))
        self.assertLess(runner.index(focused_tests), runner.index(double_parse))
        self.assertIn("dumi-recreated-final-evidence-sha256.before.txt", runner)
        self.assertIn("expected-dumi-run-status.txt", runner)
        self.assertIn('.evidence_root == $evidence', runner)
        self.assertIn("nepali-dumi.sil-apk.dict.jsonl", runner)

    def test_probe_pins_bantawa_and_leaves_all_semantics_unselected(self) -> None:
        runner = self.runner()

        for marker in (
            "bantawa-english.dict.jsonl",
            "bap-dictionary",
            "bap-Deva-NP",
            "bap-deva-direct",
            "2040",
            "360086",
            "a69917c00e7a8587f4a38458faf89c95fc9e5ac9cbe6cfb612383438bdf5ae12",
            'layout_id == "pending-bap-deva-direct"',
            "selectable == false",
            "pack_artifact == null",
            "pack_binding == null",
            ".selections.candidate_field == null",
            ".selections.headword_field == null",
            ".selections.filter_policy == null",
            ".selections.normalization_policy == null",
            ".selections.joiner_policy == null",
            ".selections.layout_id == null",
            ".selections.prefix_vectors == []",
            ".selections.pack_id == null",
            ".selections.profile_promotion == false",
            "remain unselected",
        ):
            self.assertIn(marker, runner)
        self.assertNotIn("run_cdjk_relock_validation", runner)
        self.assertNotIn("run_cdjk_sil_apk_layout_matrix", runner)
        self.assertNotIn("run_cdjk_sil_apk_candidate_pack", runner)
        self.assertNotIn("finalize_internal_pack_milestone", runner)
        self.assertNotIn("license", runner.lower())
        self.assertNotIn("redistribut", runner.lower())

    def test_double_parse_state_and_prerequisite_are_bound_fail_closed(self) -> None:
        runner = self.runner()

        for marker in (
            "test_bantawa_jsonl_contract.py",
            "a/bantawa-source-contract-v0.json",
            "b/bantawa-source-contract-v0.json",
            'cmp "$evidence/a/bantawa-source-contract-v0.json"',
            "--check",
            "project-state.before.txt",
            "project-state.after.txt",
            "dumi-recreated-final-evidence-sha256.after.txt",
            "Dumi prerequisite changed during the Bantawa source probe",
            "dumi-evidence-manifest-recheck.txt",
            "sequence-summary.json",
            "final-evidence-sha256.txt",
            "focused_tests_verified=%s",
            "double_parse_verified=%s",
            "state_unchanged=%s",
            "sequence_complete=1",
            "stage=complete",
            'find "$evidence" -type l -print -quit',
            'find "$evidence" ! -type d ! -type f -print -quit',
            "Bantawa evidence tree contains a symbolic link",
            "Bantawa evidence tree contains a special filesystem node",
            'cmp "$evidence/expected-dumi-run-status.txt"',
            ".evidence_root == $evidence",
            ".raw_input.path == $raw",
            ".raw_input.sha256 == $raw_sha256",
            ".dumi_prerequisite.evidence_root == $d_evidence",
            ".dumi_prerequisite.final_manifest_sha256 == $d_manifest_sha256",
            ".dumi_prerequisite.run_status_sha256 == $d_status_sha256",
            ".dumi_prerequisite.sequence_summary_sha256 == $d_summary_sha256",
            ".report.path == $report",
            ".report.sha256 == $report_sha256",
        ):
            self.assertIn(marker, runner)
        recheck = "stage=dumi_prerequisite_recheck"
        summary = "stage=sequence_summary"
        self.assertLess(runner.index("stage=double_parse"), runner.index(recheck))
        self.assertLess(runner.index(recheck), runner.index(summary))
        self.assertLess(runner.index(summary), runner.rindex("sequence_complete=1"))

    def test_paths_and_host_preflight_fail_closed_before_recursive_work(self) -> None:
        runner = self.runner()

        for marker in (
            '[[ -L "$dumi_argument" || ! -d "$dumi_argument" ]]',
            'dumi_evidence="$(realpath -e -- "$dumi_argument")"',
            '[[ "$dumi_evidence" != "$dumi_argument" ]]',
            'evidence_parent="$(realpath -e -- "$(dirname -- "$2")")"',
            '[[ "$evidence" != "$2" ]]',
            '[[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]',
            '[[ "$evidence" == "$dumi_evidence"',
            'exec 9>/tmp/nepa-keyboard-android-validation.lock',
            "flock -n 9",
            "available_kib < 8 * 1024 * 1024",
            "evidence_available_kib < 2 * 1024 * 1024",
            "preexisting-heavy-python.txt",
            "preexisting-android-builds.txt",
            "preexisting-high-rss-processes.txt",
        ):
            self.assertIn(marker, runner)
        self.assertLess(
            runner.index("stage=host_preflight"),
            runner.index("stage=dumi_prerequisite"),
        )


if __name__ == "__main__":
    unittest.main()
