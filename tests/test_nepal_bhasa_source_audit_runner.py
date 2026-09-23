from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_cdjk_nepal_bhasa_source_audit.sh"


class NepalBhasaSourceAuditRunnerStaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RUNNER.read_text(encoding="utf-8")

    def assertContainsAll(self, *needles: str) -> None:
        for needle in needles:
            with self.subTest(needle=needle):
                self.assertIn(needle, self.source)

    def test_runs_only_on_cdjk_ubuntu_with_one_new_absolute_evidence_root(self) -> None:
        self.assertContainsAll(
            "if [[ $# -ne 1 || \"$1\" != /* ]]",
            "$(uname -s)\" != Linux",
            "$(hostname -s)\" != cdjk",
            "^ID=(\"?ubuntu\"?)$",
            "if [[ -e \"$evidence\" || -L \"$evidence\" ]]",
            "evidence directory already exists",
            "must be outside the source checkout",
        )
        self.assertNotIn("prerequisite", self.source.lower())

    def test_binds_exact_raw_tsv_pins_and_headers(self) -> None:
        self.assertContainsAll(
            "/home/cdjk/github/llm/nllb-better/data/lexicons_pdf/new_nepali_trilingual.tsv",
            "/home/cdjk/github/llm/nllb-better/data/lexicons_apk/new_apk_eng_lexicon.tsv",
            "4167c21626674fd1e71bd814c6b2bbb33d2d35ab0f5d5bb071b7b43e071d7929",
            "470be5aaf526d2dca973044fa5ca9a69b4259854958456145661bd58d4889b41",
            "$trilingual_records\" != 9708",
            "$trilingual_bytes\" != 543567",
            "$trilingual_header\" != $'newar\\tnepali'",
            "$apk_records\" != 5727",
            "$apk_bytes\" != 404596",
            "$apk_header\" != $'newar\\tenglish\\ttransliteration'",
        )

    def test_rejects_noncanonical_symbolic_special_or_empty_inputs(self) -> None:
        self.assertContainsAll(
            "if [[ -L \"$input\" || ! -f \"$input\" || ! -s \"$input\" ]]",
            "$(realpath -e -- \"$input\")\" != \"$input\"",
            "canonical input is missing, symbolic, special, or empty",
            "canonical input path resolves elsewhere",
        )

    def test_preflights_host_before_any_raw_scan(self) -> None:
        self.assertContainsAll(
            "exec 9>/tmp/nepa-keyboard-android-validation.lock",
            "flock -n 9",
            "/^MemAvailable:/",
            "available_kib < 8 * 1024 * 1024",
            "evidence_available_kib < 2 * 1024 * 1024",
            "tmp_available_kib < 1024 * 1024",
            "[q]emu-system|[e]mulator",
            "[p]ython.*(train|align|inference|mms|torch)",
            "[g]radle|[k]otlinc|[j]ava.*(GradleDaemon|org\\.gradle|kotlinc)",
            "ps -eo pid=,rss=,comm=,args=",
            "$2 >= 8388608",
        )
        self.assertLess(
            self.source.index("stage=host_preflight"),
            self.source.index("stage=pinned_input_validation"),
        )
        self.assertLess(
            self.source.index("host_preflight_verified=1"),
            self.source.index("verify_raw_inputs\n"),
        )

    def test_hashes_every_bound_source_before_and_after(self) -> None:
        self.assertContainsAll(
            'catalog="$repo/catalog/resources.json"',
            'profile_lock="$repo/catalog/internal-profiles.lock.json"',
            'layout_lock="$repo/layouts/internal/layouts-v1.lock.json"',
            'android_pins="$repo/android/ime-app/build.gradle.kts"',
            'auditor="$repo/tools/audit_nepal_bhasa_tsv_contract.py"',
            'focused_test="$repo/tests/test_nepal_bhasa_tsv_contract.py"',
            'runner="$repo/tools/run_cdjk_nepal_bhasa_source_audit.sh"',
            'runner_test="$repo/tests/test_nepal_bhasa_source_audit_runner.py"',
            'input-source-sha256.before.txt',
            'input-source-sha256.after.txt',
            'cmp "$evidence/input-source-sha256.before.txt"',
        )
        for variable in (
            "trilingual_raw",
            "apk_raw",
            "catalog",
            "profile_lock",
            "layout_lock",
            "android_pins",
            "auditor",
            "focused_test",
            "runner",
            "runner_test",
        ):
            with self.subTest(variable=variable):
                self.assertGreaterEqual(self.source.count(f'  "${variable}" \\\n'), 2)

    def test_binds_all_four_neutral_profiles(self) -> None:
        self.assertContainsAll(
            '($profiles | length) == 4',
            '.profile_id == "new-Deva-NP"',
            '.input_method_id == "new-deva-direct"',
            '.layout_id == "pending-new-deva-direct"',
            '.profile_id == "new-Newa-NP"',
            '.input_method_id == "new-newa-direct"',
            '.layout_id == "pending-new-newa-direct"',
            '.profile_id == "new-Latn-Deva-NP"',
            '.input_method_id == "new-latn-deva"',
            '.layout_id == "latn-qwerty-us-v1"',
            '.profile_id == "new-Deva-Newa-NP"',
            '.input_method_id == "new-deva-newa"',
            '.layout_id == "pending-new-deva-newa"',
            ".selectable == false",
            ".default_enabled == false",
            ".pack_artifact == null",
            ".pack_binding == null",
            ".evidence_ids == []",
            ".evidence_artifacts == []",
        )

    def test_runs_focused_test_and_exact_auditor_cli_under_pinned_runtime(self) -> None:
        self.assertContainsAll(
            'runtime_identity\" != "3.14/16.0.0"',
            "test_nepal_bhasa_tsv_contract.py",
            "test_nepal_bhasa_source_audit_runner.py",
            "tools/audit_nepal_bhasa_tsv_contract.py",
            '--resource-catalog "$catalog"',
            '--profile-lock "$profile_lock"',
            '--layout-lock "$layout_lock"',
            '--trilingual-tsv "$trilingual_raw"',
            '--apk-tsv "$apk_raw"',
            '--output "$evidence/a/nepal-bhasa-source-contract-v0.json"',
            '--output "$evidence/b/nepal-bhasa-source-contract-v0.json"',
        )
        self.assertEqual(self.source.count("--resource-catalog \"$catalog\""), 3)
        self.assertEqual(self.source.count("--trilingual-tsv \"$trilingual_raw\""), 3)
        self.assertGreaterEqual(
            self.source.count("test_nepal_bhasa_source_audit_runner.py"),
            2,
        )
        self.assertIn(
            "test-nepal-bhasa-source-audit-runner.txt",
            self.source,
        )

    def test_generate_check_and_second_generation_are_strictly_ordered(self) -> None:
        generate = self.source.index("stage=generate_and_check")
        check = self.source.index("  --check >", generate)
        second = self.source.index("stage=deterministic_second_generation")
        compare = self.source.index(
            'cmp "$evidence/a/nepal-bhasa-source-contract-v0.json"', second
        )
        self.assertLess(generate, check)
        self.assertLess(check, second)
        self.assertLess(second, compare)

    def test_validates_report_identity_inputs_layout_and_runtime(self) -> None:
        self.assertContainsAll(
            '.auditor.name == "audit_nepal_bhasa_tsv_contract"',
            '.auditor.path == "tools/audit_nepal_bhasa_tsv_contract.py"',
            ".auditor.sha256 == $auditor_sha256",
            ".auditor.version == 1",
            '.catalog_binding.target_id == "new"',
            '.catalog_binding.path == "catalog/resources.json"',
            ".catalog_binding.sha256 == $catalog_sha256",
            '"new-nepali-trilingual", "new-apk-english"',
            '.profile_bindings.path == "catalog/internal-profiles.lock.json"',
            ".profile_bindings.sha256 == $profile_lock_sha256",
            '.layout_evidence.path == "layouts/internal/layouts-v1.lock.json"',
            ".layout_evidence.sha256 == $layout_lock_sha256",
            '"exact non-whitespace scalar emission only"',
            '.runtime_contract.python_major_minor == "3.14"',
            '.runtime_contract.unicode_data_version == "16.0.0"',
            ".raw_inputs == [",
            "bytes: 543567",
            "records: 9708",
            "bytes: 404596",
            "records: 5727",
        )

    def test_validates_separate_source_contracts_and_all_scalar_layout_counts(self) -> None:
        self.assertContainsAll(
            'source_contracts[0].resource_id == "new-nepali-trilingual"',
            'source_contracts[0].header == ["newar", "nepali"]',
            ".source_contracts[0].columns_per_row == 2",
            ".source_contracts[0].data_rows == 9708",
            'source_contracts[1].resource_id == "new-apk-english"',
            '"newar", "english", "transliteration"',
            ".source_contracts[1].columns_per_row == 3",
            ".source_contracts[1].data_rows == 5727",
            ".source_contracts[].column_inventories[]",
            ".string_values.duplicate_nonempty_extra_occurrences",
            ".string_values.duplicate_nonempty_value_groups",
            ".string_values.duplicate_nonempty_values | type == \"array\"",
            ".string_values.duplicate_nonempty_values_sha256",
            ".layout_coverage_for_raw_newar_column",
            ".covered_required_scalars | type == \"number\"",
            ".emitted_scalars | type == \"number\"",
            ".missing_required_scalars | type == \"array\"",
            ".required_scalars | type == \"number\"",
        )

    def test_validates_duplicate_and_transliteration_diagnostics(self) -> None:
        self.assertContainsAll(
            ".raw_duplicate_extra_occurrences | type == \"number\"",
            ".raw_duplicate_row_groups | type == \"number\"",
            ".raw_duplicate_rows | type == \"array\"",
            ".raw_duplicate_rows_sha256 | test(\"^[0-9a-f]{64}$\")",
            ".source_contracts[0].transliteration_column_coverage == null",
            ".source_contracts[1].transliteration_column_coverage | type == \"object\"",
            ".distinct_nonempty_values",
            ".empty_values",
            ".newar_rows",
            ".nonempty_newar_rows",
            ".nonempty_newar_rows_with_nonempty_transliteration",
            ".nonempty_values",
        )

    def test_validates_full_raw_overlap_contract_counts_and_digests(self) -> None:
        self.assertContainsAll(
            '"exact raw strings including empty; no normalization or splitting"',
            ".empty_present_in_both | type == \"boolean\"",
            ".exact_overlap_count | type == \"number\"",
            ".exact_overlap_examples | type == \"array\"",
            ".exact_overlap_sha256",
            ".exact_nonempty_overlap_count",
            ".exact_nonempty_overlap_examples",
            ".exact_nonempty_overlap_sha256",
            ".new_apk_english_nonempty_unique_count",
            ".new_apk_english_unique_count",
            ".new_apk_english_unique_sha256",
            ".new_nepali_trilingual_nonempty_unique_count",
            ".new_nepali_trilingual_unique_count",
            ".new_nepali_trilingual_unique_sha256",
            'test("^[0-9a-f]{64}$")',
        )

    def test_validates_every_neutral_selection(self) -> None:
        self.assertContainsAll(
            ".selections.alternative_splitting_policy == null",
            '.selections.candidate_columns == {',
            '"new-nepali-trilingual": null',
            '"new-apk-english": null',
            ".selections.candidate_resource_ids == []",
            ".selections.conversion_policy == null",
            ".selections.filter_policy == null",
            ".selections.joiner_policy == null",
            ".selections.layout_ids == []",
            ".selections.normalization_policy == null",
            ".selections.pack_id == null",
            ".selections.prefix_vectors == []",
            ".selections.roman_alias_policy == null",
            '"new-Deva-NP": false',
            '"new-Newa-NP": false',
            '"new-Latn-Deva-NP": false',
            '"new-Deva-Newa-NP": false',
        )

    def test_writes_summary_status_and_recursive_manifest_atomically(self) -> None:
        self.assertContainsAll(
            'summary_temporary="$evidence/.sequence-summary.json.tmp"',
            'mv "$summary_temporary" "$evidence/sequence-summary.json"',
            'temporary="$evidence/.run-status.txt.tmp"',
            'mv "$temporary" "$evidence/run-status.txt"',
            'temporary="$evidence/.final-evidence-sha256.txt.tmp"',
            'mv "$temporary" "$evidence/final-evidence-sha256.txt"',
            'find "$evidence" -type l -print -quit',
            'find "$evidence" ! -type d ! -type f -print -quit',
            "LC_ALL=C find . -type f",
            "LC_ALL=C sort -z",
            "xargs -0 -r sha256sum",
            "cross_source_raw_newar_overlap: $audit.cross_source_raw_newar_overlap",
            "runner_test: {path: $runner_test, sha256: $runner_test_sha256}",
            ".inputs.runner_test.sha256 == $runner_test_sha256",
            "No rows or candidate vocabularies were merged",
            "selections_remain_neutral: true",
            "stage=complete",
            "sequence_complete=1",
        )

    def test_has_no_outward_or_promotion_build_side_effects(self) -> None:
        forbidden = (
            "ssh ",
            "scp ",
            "rsync ",
            "curl ",
            "wget ",
            "run_cdjk_relock_validation",
            "run_cdjk_sil_apk_layout_matrix",
            "run_cdjk_sil_apk_candidate_pack",
            "finalize_internal_pack_milestone",
            "./gradlew",
            "adb ",
            "lic" + "ense",
            "redis" + "tribut",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, self.source.lower())


if __name__ == "__main__":
    unittest.main()
