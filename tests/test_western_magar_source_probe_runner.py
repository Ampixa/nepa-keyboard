from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WesternMagarSourceProbeRunnerTest(unittest.TestCase):
    def runner(self) -> str:
        return (ROOT / "tools/run_cdjk_western_magar_source_probe.sh").read_text(
            encoding="utf-8"
        )

    def test_completed_bantawa_gate_precedes_every_western_magar_scan(self) -> None:
        runner = self.runner()

        host_preflight = "stage=host_preflight"
        prerequisite = "stage=bantawa_prerequisite"
        manifest_recreation = (
            '"$evidence/bantawa-recreated-final-evidence-sha256.before.txt"'
        )
        verified = "bantawa_prerequisite_verified=1"
        raw_scan = 'actual_raw_sha256="$(sha256sum "$raw"'
        focused_tests = "stage=focused_tests"
        double_parse = "stage=double_parse"
        for marker in (
            host_preflight,
            prerequisite,
            manifest_recreation,
            verified,
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

    def test_probe_pins_inputs_and_leaves_keyboard_semantics_unselected(self) -> None:
        runner = self.runner()

        for marker in (
            "/home/cdjk/github/llm/nllb-better/data/lexicons_apk/mrd_nep_lexicon.tsv",
            "mrd-apk",
            "mrd-Deva-NP",
            "mrd-deva-direct",
            "1264",
            "68724",
            "d55d34e4c4d754ee1bbcf3382f3250690e53884020c06305e34bfc1a7948591a",
            'layout_id == "pending-mrd-deva-direct"',
            "selectable == false",
            "pack_artifact == null",
            "pack_binding == null",
            ".selections.candidate_column == null",
            ".selections.headword_column == null",
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
        for excluded in (
            "run_cdjk_relock_validation",
            "run_cdjk_sil_apk_layout_matrix",
            "run_cdjk_sil_apk_candidate_pack",
            "finalize_internal_pack_milestone",
        ):
            self.assertNotIn(excluded, runner)
        for excluded in ("lic" + "ense", "redis" + "tribut"):
            self.assertNotIn(excluded, runner.lower())

    def test_double_parse_and_all_runtime_inputs_are_hash_bound(self) -> None:
        runner = self.runner()

        for marker in (
            "audit_western_magar_tsv_contract.py",
            "test_western_magar_tsv_contract.py",
            "--profile-lock",
            "--layout-lock",
            "--western-magar-tsv",
            "a/western-magar-source-contract-v0.json",
            "b/western-magar-source-contract-v0.json",
            'cmp "$evidence/a/western-magar-source-contract-v0.json"',
            "--check",
            "NR > 1 {count++} END {print count + 0}",
            '.tsv_contract.header == [',
            '"mrd_headword", "nepali_gloss", "english_gloss"',
            ".tsv_contract.columns_per_row == 3",
            ".tsv_contract.data_rows == 1264",
            '.tsv_contract.encoding == "UTF-8"',
            ".tsv_contract.lf_terminated == true",
            "(.tsv_contract.column_inventories | length) == 3",
            ".profile_binding.sha256 == $profile_lock_sha256",
            ".layout_evidence.sha256 == $layout_lock_sha256",
            "input-source-sha256.before.txt",
            "input-source-sha256.after.txt",
            'cmp "$evidence/input-source-sha256.before.txt"',
            '"$catalog"',
            '"$profile_lock"',
            '"$layout_lock"',
            '"$auditor"',
            '"$runner"',
            ".inputs.resource_catalog.sha256 == $catalog_sha256",
            ".inputs.internal_profile_lock.sha256 == $profile_lock_sha256",
            ".inputs.internal_layout_lock.sha256 == $layout_lock_sha256",
            ".inputs.auditor.sha256 == $auditor_sha256",
            ".inputs.focused_test.sha256 == $focused_test_sha256",
            ".inputs.runner.sha256 == $runner_sha256",
            "focused_tests_verified=%s",
            "double_parse_verified=%s",
            "inputs_unchanged=%s",
            "sequence_complete=1",
            "stage=complete",
        ):
            self.assertIn(marker, runner)
        recheck = "stage=input_recheck"
        prerequisite_recheck = "stage=bantawa_prerequisite_recheck"
        summary = "stage=sequence_summary"
        self.assertLess(
            runner.index("stage=focused_tests"), runner.index("stage=double_parse")
        )
        self.assertLess(runner.index("stage=double_parse"), runner.index(recheck))
        self.assertLess(runner.index(recheck), runner.index(prerequisite_recheck))
        self.assertLess(runner.index(prerequisite_recheck), runner.index(summary))
        self.assertLess(runner.index(summary), runner.rindex("sequence_complete=1"))

    def test_bantawa_tree_status_manifest_report_and_summary_are_exact(self) -> None:
        runner = self.runner()

        for marker in (
            "expected-bantawa-run-status.txt",
            "dumi_prerequisite_verified=1",
            "focused_tests_verified=1",
            "double_parse_verified=1",
            "state_unchanged=1",
            'cmp "$evidence/expected-bantawa-run-status.txt"',
            "bantawa-prerequisite-final-evidence-sha256.txt",
            "bantawa-prerequisite-sha256.txt",
            "bantawa-recreated-final-evidence-sha256.after.txt",
            "bantawa-evidence-manifest-recheck.txt",
            "Bantawa prerequisite changed during the Western Magar source probe",
            '.raw_input.sha256 == $raw_sha256',
            '.report.path == $report',
            '.report.sha256 == $report_sha256',
            ".bantawa_prerequisite.evidence_root == $b_evidence",
            ".bantawa_prerequisite.final_manifest_sha256 == $b_manifest_sha256",
            ".bantawa_prerequisite.manifest_entry_count == $b_manifest_entry_count",
            ".bantawa_prerequisite.run_status_sha256 == $b_status_sha256",
            ".bantawa_prerequisite.sequence_summary_sha256 == $b_summary_sha256",
            ".bantawa_prerequisite.report_sha256 == $b_report_sha256",
        ):
            self.assertIn(marker, runner)

    def test_both_evidence_trees_reject_links_and_special_nodes(self) -> None:
        runner = self.runner()

        for marker in (
            'find "$evidence" -type l -print -quit',
            'find "$evidence" ! -type d ! -type f -print -quit',
            "Western Magar evidence tree contains a symbolic link",
            "Western Magar evidence tree contains a special filesystem node",
            'find "$bantawa_evidence" -type l -print -quit',
            'find "$bantawa_evidence" ! -type d ! -type f -print -quit',
            "Bantawa prerequisite tree contains a symbolic link",
            "Bantawa prerequisite tree contains a special filesystem node",
        ):
            self.assertIn(marker, runner)

    def test_paths_and_cdjk_preflight_fail_closed_before_recursive_work(self) -> None:
        runner = self.runner()

        for marker in (
            '[[ -L "$bantawa_argument" || ! -d "$bantawa_argument" ]]',
            'bantawa_evidence="$(realpath -e -- "$bantawa_argument")"',
            '[[ "$bantawa_evidence" != "$bantawa_argument" ]]',
            'evidence_parent="$(realpath -e -- "$(dirname -- "$2")")"',
            '[[ "$evidence" != "$2" ]]',
            '[[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]',
            '[[ "$evidence" == "$bantawa_evidence"',
            "exec 9>/tmp/nepa-keyboard-android-validation.lock",
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
            runner.index("stage=bantawa_prerequisite"),
        )


if __name__ == "__main__":
    unittest.main()
