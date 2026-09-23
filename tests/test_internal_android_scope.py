from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class InternalAndroidScopeTest(unittest.TestCase):
    def test_cdjk_runners_parse_rss_from_a_stable_numeric_column(self) -> None:
        for relative in (
            "tools/run_cdjk_bantawa_source_probe.sh",
            "tools/run_cdjk_internal_catalog_validation.sh",
            "tools/run_cdjk_nepal_bhasa_source_audit.sh",
            "tools/run_cdjk_relock_validation.sh",
            "tools/run_cdjk_sil_apk_candidate_pack.sh",
            "tools/run_cdjk_sil_apk_layout_matrix.sh",
            "tools/run_cdjk_subtype_compat_validation.sh",
            "tools/run_cdjk_western_magar_source_probe.sh",
            "tools/run_cdjk_yakkha_refresh.sh",
        ):
            with self.subTest(runner=relative):
                runner = source(relative)
                self.assertIn("ps -eo pid=,rss=,comm=,args=", runner)
                self.assertIn("awk '$2 >= 8388608 {print}'", runner)
                self.assertNotIn("ps -eo pid=,comm=,rss=,args=", runner)
                self.assertNotIn("awk '$3 >= 8388608 {print}'", runner)

    def test_internal_runner_has_no_public_or_reader_authorization_gate(self) -> None:
        runner = source("tools/run_cdjk_internal_catalog_validation.sh")
        self.assertNotIn("release_apk=", runner)
        self.assertNotIn("release_lock=", runner)
        self.assertNotIn("public_stage=", runner)
        self.assertNotIn("production_reader_rejected", runner)
        self.assertNotIn("ordinary_reader_rejected", runner)
        self.assertNotIn("-e allowInternal", runner)
        self.assertIn("InternalCatalogPrefixBenchmarkInstrumentation", runner)
        self.assertIn("flock --nonblock --close --conflict-exit-code 75", runner)
        self.assertNotIn("exec 9>/tmp/nepa-keyboard-android-validation.lock", runner)
        self.assertIn("shell ime list -a -s", runner)
        self.assertIn("installed-ime-metadata-status.txt", runner)
        self.assertIn("installed-ime-metadata-timeout-dumpsys.txt", runner)
        self.assertIn("SECONDS - ime_metadata_wait_start >= 120", runner)
        self.assertIn("expected-internal-layout-notices.txt", runner)
        self.assertIn("assets/nepa-conformance/runtime-v2.json", runner)
        self.assertNotIn("assets/nepa-conformance/runtime-v1.json", runner)
        for evidence_flag in (
            "ybh_profile_binding_verified=true",
            "ybh_layout_registry_verified=true",
            "ybh_generated_key_policies_verified=true",
            "ybh_intra_word_punctuation_verified=true",
            "ybh_terminal_zwnj_query_verified=true",
            "ybh_key_dispatch_verified=true",
            "ybh_nepali_layout_isolation_verified=true",
            "ybh_picker_row_selection_verified=true",
            "ybh_pack_input_verified=true",
            "klr_profile_binding_verified=true",
            "klr_layout_registry_verified=true",
            "klr_generated_key_policies_verified=true",
            "klr_atomic_zwj_verified=true",
            "klr_atomic_zwnj_verified=true",
            "klr_intra_word_hyphen_verified=true",
            "klr_key_dispatch_verified=true",
            "klr_nepali_layout_isolation_verified=true",
            "klr_picker_row_selection_verified=true",
            "klr_pack_input_verified=true",
            "dus_profile_binding_verified=true",
            "dus_layout_registry_verified=true",
            "dus_generated_key_policies_verified=true",
            "dus_atomic_zwj_verified=true",
            "dus_atomic_zwnj_verified=true",
            "dus_intra_word_hyphen_verified=true",
            "dus_intra_word_colon_verified=true",
            "dus_key_dispatch_verified=true",
            "dus_nepali_layout_isolation_verified=true",
            "dus_picker_row_selection_verified=true",
            "dus_pack_input_verified=true",
            "nepal_bhasa_roman_profile_binding_verified=true",
            "nepal_bhasa_roman_pack_input_verified=true",
            "internal_catalog_reader_verified=true",
            "internal_catalog_notices_verified=true",
            "subtype_state_foundation_verified=true",
            "tokenized_suggestion_readiness_verified=true",
            "picker_modal_accessibility_foundation_verified=true",
            "picker_hold_accessibility_action_verified=true",
            "language_manager_recycling_saved_state_verified=true",
            "language_manager_sections_verified=true",
            "service_bound_picker_subtype_verified=true",
            "service_bound_globe_subtype_verified=true",
            "platform_subtype_confirmation_verified=true",
            "managed_enabled_subtypes_verified=true",
        ):
            self.assertIn(evidence_flag, runner)
        self.assertIn("spatial_benchmark_iterations=1000", runner)
        self.assertIn("spatial_benchmark_warmups=100", runner)
        self.assertIn("decoder_contract_timeout_seconds=1800", runner)
        self.assertIn("internal_smoke_timeout_seconds=1800", runner)
        self.assertIn('timeout "$internal_smoke_timeout_seconds"', runner)
        self.assertIn('timeout "$decoder_contract_timeout_seconds"', runner)
        self.assertIn('-e iterations "$spatial_benchmark_iterations"', runner)
        self.assertIn('-e warmups "$spatial_benchmark_warmups"', runner)
        self.assertEqual(2, runner.count("-e iterations 10000"))
        self.assertEqual(2, runner.count("-e warmups 1000"))
        self.assertIn("negative_case_count=17", runner)
        self.assertIn("negative_case_pass_count=17", runner)

    def test_dumi_internal_profile_is_relocked_and_exercised_end_to_end(self) -> None:
        relock = source("tools/run_cdjk_relock_validation.sh")
        internal = source("tools/run_cdjk_internal_catalog_validation.sh")
        smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )
        key_spec = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/KeySpec.java"
        )
        composing = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "ComposingSession.java"
        )
        android_build = source("android/ime-app/build.gradle.kts")

        for runner in (relock, internal):
            for guard in (
                '.profile_id == "dus-Deva-NP"',
                '.layout_id == "deva-nepal-dumi-v1"',
                "5688c744ee8b88cb3a24c76379590b99195a90a0e309f625ea578b1ced1e60ac",
                '.pack_artifact.file_name == "dus-Deva-NP.nkp"',
                "efd9626d11c3910361adb50f1e656c67aefc2c6957ee3b47122236b1a6e3dec2",
                ".pack_artifact.candidate_count == 2132",
                '.pack_artifact.validation.expected_surface == "क:फु"',
                '"dus-direct-internal-2026-07-22"',
                "f4150925578f3b07ddb6a1cb766f3785f127ff05d18e49a1ca112364688089c9",
            ):
                with self.subTest(runner=runner, guard=guard):
                    self.assertIn(guard, runner)

        for frozen_input in (
            "test_dumi_internal_source.py",
            "tools/build_dumi_internal_source.py",
            "tools/sil_apk_jsonl_internal_source.py",
            "src/nepa_keyboard/compiler.py",
            "src/nepa_keyboard/runtime.py",
            "catalog/dumi-internal-prefixes-v0.json",
            "catalog/internal-pack-milestones/dus-Deva-NP-v0.json",
        ):
            self.assertIn(frozen_input, relock)
        self.assertIn("assert_dumi_internal_profile", relock)
        self.assertIn("assert_internal_dumi_layout_binding", relock)
        self.assertLess(
            relock.index('assert_dumi_internal_profile "$evidence/a/internal-profiles.lock.json"'),
            relock.index("transaction_started=1"),
        )

        for assertion in (
            "DUMI_DIRECT_ID",
            "DUMI_LAYOUT_ID",
            "verifyDumiProfileAndLayout",
            "verifyDumiKeyDispatch",
            "verifyDumiGeneratedInputPolicies",
            "verifyDumiPackInput",
            '"क:फु"',
            '"कु:ना"',
            '"आम्‍ना-आसाला"',
            '"तःले"',
            '"ब़ह़"',
            '"ॽवाक्ना"',
            '"dus_intra_word_colon_verified"',
            '"dus_pack_input_verified"',
        ):
            self.assertIn(assertion, smoke)
        for result_flag in (
            "dus_profile_binding_verified",
            "dus_layout_registry_verified",
            "dus_generated_key_policies_verified",
            "dus_atomic_zwj_verified",
            "dus_atomic_zwnj_verified",
            "dus_intra_word_hyphen_verified",
            "dus_intra_word_colon_verified",
            "dus_key_dispatch_verified",
            "dus_nepali_layout_isolation_verified",
            "dus_picker_row_selection_verified",
            "dus_pack_input_verified",
        ):
            self.assertIn('"' + result_flag + '"', smoke)
        for contract_source in (key_spec, composing):
            self.assertIn('":".equals(text)', contract_source)
            self.assertIn("slash, backslash, or colon", contract_source)
        self.assertIn('setOf("-", "/", "\\\\", ":")', android_build)
        self.assertIn("slash, backslash, or colon", android_build)

    def test_internal_smoke_uses_catalog_reader_without_public_partition(self) -> None:
        smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )
        self.assertIn("NkpBundle.open(\n                        materialized,", smoke)
        self.assertIn("vector.artifactSha256,\n                        true", smoke)
        self.assertIn('"internal_catalog_reader_verified"', smoke)
        self.assertIn('"internal_catalog_notices_verified"', smoke)
        self.assertNotIn("foundation release packs", smoke)
        self.assertNotIn("ordinary reader", smoke)

        notices = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NoticesActivity.java"
        )
        internal_reader = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "NoticeReaderFactory.java"
        )
        release_reader = source(
            "android/ime-app/src/release/java/com/ampixa/nepakeyboard/ime/"
            "NoticeReaderFactory.java"
        )
        self.assertIn("NoticeReaderFactory.read(", notices)
        self.assertIn("readNoticesForInternalCatalog", internal_reader)
        self.assertIn("NkpBundle.readNotices(file, expectedSha256)", release_reader)
        self.assertNotIn("readNoticesForInternalCatalog", release_reader)

        bundle = source(
            "android/pack-runtime/src/main/java/com/ampixa/nepakeyboard/pack/"
            "NkpBundle.java"
        )
        self.assertIn(
            "return readNotices(file, expectedArtifactSha256, false);", bundle
        )
        self.assertIn("return readNotices(file, expectedArtifactSha256, true);", bundle)
        self.assertIn("public/export boundary", bundle)
        self.assertIn("explicit internal-catalog authority", bundle)
        self.assertNotIn("must never use that opt-in in a production keyboard", bundle)

        registry = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "ReleasePackRegistry.java"
        )
        self.assertIn("internal product catalog", registry)
        self.assertNotIn("Internal research packs", registry)

    def test_internal_benchmark_is_an_isolated_shared_harness_entry(self) -> None:
        internal = source(
            "android/benchmark-app/src/main/java/com/ampixa/nepakeyboard/benchmark/"
            "InternalCatalogPrefixBenchmarkInstrumentation.java"
        )
        shared = source(
            "android/benchmark-app/src/main/java/com/ampixa/nepakeyboard/benchmark/"
            "ReleasePrefixBenchmarkInstrumentation.java"
        )
        self.assertIn("extends ReleasePrefixBenchmarkInstrumentation", internal)
        self.assertIn("return true;", internal)
        self.assertIn('return "internal_catalog_prefix";', internal)
        self.assertIn("validateCatalogAuthority(packs, allowInternal)", shared)
        self.assertIn("NkpBundle.open(\n                packFile,", shared)
        self.assertIn("allowInternal\n        )", shared)

        manifest = source("android/benchmark-app/src/main/AndroidManifest.xml")
        self.assertIn('.ReleasePrefixBenchmarkInstrumentation"', manifest)
        self.assertIn('.InternalCatalogPrefixBenchmarkInstrumentation"', manifest)

        benchmark_gradle = source("android/benchmark-app/build.gradle.kts")
        self.assertIn(
            '.dir("generated/assets/stageInternalExternalPacks")',
            benchmark_gradle,
        )
        self.assertIn(
            '.dir("generated/assets/stageDebugExternalPacks")',
            benchmark_gradle,
        )

    def test_corruption_harness_has_seventeen_integrity_negatives(self) -> None:
        corruption = source(
            "android/benchmark-app/src/main/java/com/ampixa/nepakeyboard/benchmark/"
            "NkpBundleCorruptionInstrumentation.java"
        )
        self.assertNotIn("allowInternal", corruption)
        self.assertNotIn("production_reader_gate", corruption)
        self.assertIn('"truncated_alias_trie_header"', corruption)
        self.assertIn("expectedNegativeCases = 17", corruption)
        self.assertIn('"internal_catalog_reader_verified"', corruption)

    def test_gradle_applies_redistribution_approval_only_to_public_staging(
        self,
    ) -> None:
        gradle = source("android/ime-app/build.gradle.kts")
        self.assertIn("if (enforceRedistributionApproval)", gradle)
        release_stager = gradle.split(
            "abstract class StageExternalReleasePacks",
            1,
        )[1].split("abstract class StageExternalInternalPacks", 1)[0]
        internal_stager = gradle.split(
            "abstract class StageExternalInternalPacks",
            1,
        )[1]
        self.assertIn(
            "final override fun enforceRedistributionApproval(): Boolean = true",
            release_stager,
        )
        self.assertNotIn(
            "enforceRedistributionApproval(): Boolean = false", release_stager
        )
        self.assertIn(
            "final override fun enforceRedistributionApproval(): Boolean = false",
            internal_stager,
        )
        self.assertNotIn(
            "enforceRedistributionApproval(): Boolean = true", internal_stager
        )

    def test_internal_relock_and_build_do_not_consume_public_locks(self) -> None:
        relock = source("tools/run_cdjk_relock_validation.sh")
        pin_updater = source("tools/update_android_lock_pins.py")
        gradle = source("android/ime-app/build.gradle.kts")
        benchmark = source("android/benchmark-app/build.gradle.kts")

        self.assertIn("scope=internal", relock)
        self.assertIn("[--scope internal|all]", relock)
        self.assertIn('if [[ "$scope" == all ]]; then', relock)
        self.assertIn('--scope "$scope"', relock)
        self.assertIn("printf 'scope=%s\\n' \"$scope\"", relock)
        self.assertIn('"internal": frozenset', pin_updater)
        self.assertIn('scope: str = "internal"', pin_updater)
        self.assertIn('default="internal"', pin_updater)
        self.assertIn('enforce_global_contract=scope == "all"', pin_updater)
        self.assertIn(
            'chmod --reference="$evidence/original/$relative"',
            relock,
        )
        self.assertIn(
            'cmp "$evidence/original/$relative" "$repo/$relative"',
            relock,
        )
        self.assertIn("append_directory_tree_inputs android/ime-app/src", relock)
        self.assertIn(
            "append_directory_tree_inputs android/benchmark-app/src/main", relock
        )
        self.assertIn(
            "append_directory_tree_inputs android/pack-runtime/src/main", relock
        )
        static_inputs = relock.split("static_source_inputs=(", 1)[1].split(")", 1)[0]
        tracked_outputs = relock.split("tracked_paths=(", 1)[1].split(")", 1)[0]
        self.assertIn("android/ime-app/build.gradle.kts", tracked_outputs)
        self.assertNotIn("android/ime-app/build.gradle.kts", static_inputs)
        self.assertIn("immutable source overlaps transaction output", relock)
        self.assertEqual(relock.count("\nbuild_source_inputs\n"), 2)
        self.assertIn("ps -eo pid=,rss=,comm=,args=", relock)
        self.assertIn("awk '$2 >= 8388608 {print}'", relock)
        self.assertNotIn("awk '$3 >= 8388608 {print}'", relock)
        self.assertIn(".evidence[]?.artifacts[]?.path", relock)
        self.assertIn(
            "append_review_evidence_inputs catalog/internal-profile-review.json",
            relock,
        )
        self.assertIn("catalog/shipping-profile-review.json", relock)
        self.assertIn("input-source-sha256.after.txt", relock)
        self.assertIn(
            'cmp "$evidence/input-source-sha256.txt" \\\n'
            '  "$evidence/input-source-sha256.after.txt"',
            relock,
        )
        self.assertIn("local restore_status=0", relock)
        self.assertIn('return "$restore_status"', relock)

        internal_variant = gradle.split(
            'onVariants(selector().withBuildType("internal"))',
            1,
        )[1]
        self.assertIn("generateInternalProfileCatalog", internal_variant)
        self.assertIn("generateInternalLayoutRegistry", internal_variant)
        self.assertIn("stageInternalExternalPacks", internal_variant)
        self.assertNotIn("generateShippingProfileCatalog", internal_variant)
        self.assertNotIn("stageReleaseExternalPacks", internal_variant)
        self.assertIn(":ime-app:stageInternalExternalPacks", benchmark)

    def test_newa_internal_beta_is_bound_before_relock_and_apk_use(
        self,
    ) -> None:
        relock = source("tools/run_cdjk_relock_validation.sh")
        internal = source("tools/run_cdjk_internal_catalog_validation.sh")

        for runner in (relock, internal):
            for guard in (
                '.profile_id == "new-Newa-NP"',
                '.catalog_readiness == "beta"',
                ".selectable == true",
                ".default_enabled == false",
                '.layout_id == "newa-nepal-prachalit-v1"',
                ".layout_revision == 1",
                '.pack_binding == "new-Newa-NP"',
                '.pack_artifact.pack_id == "new-Newa-NP"',
                '.pack_artifact.file_name == "new-Newa-NP.nkp"',
                '.pack_artifact.output_script == "Newa"',
                '.source_script == "Newa"',
                '.input_script == "Newa"',
            ):
                self.assertIn(guard, runner)

        self.assertIn("DIRECT_PROFILE_NOT_RELEASE_APPROVED", relock)
        self.assertIn("validate_keyboard_layout_candidate.py", relock)
        self.assertIn("newa-qwerty-direct-candidate.json", relock)
        self.assertIn("newa_internal_profile_binding_verified=true", internal)

        self.assertLess(
            relock.index(
                'assert_newa_internal_profile "$evidence/a/internal-profiles.lock.json"'
            ),
            relock.index("transaction_started=1"),
        )
        internal_layout_guard = relock.index(
            'assert_internal_newa_layout_binding "$evidence/a/internal-layouts-v1.lock.json"'
        )
        candidate_validation = relock.index(
            "run_python tools/validate_keyboard_layout_candidate.py"
        )
        native_review_validation = relock.index(
            "run_python tools/validate_layout_native_review.py"
        )
        transaction_start = relock.index("transaction_started=1")
        layout_install = relock.index(
            'install -m 0644 "$evidence/a/internal-layouts-v1.lock.json"'
        )
        self.assertLess(internal_layout_guard, layout_install)
        self.assertLess(candidate_validation, layout_install)
        self.assertLess(native_review_validation, layout_install)
        self.assertLess(candidate_validation, transaction_start)
        self.assertLess(native_review_validation, transaction_start)
        self.assertLess(
            internal.index("newa_internal_profile_binding_verified=true"),
            internal.index('for apk in "$internal_apk" "$benchmark_apk"'),
        )

        self.assertIn(
            'if [[ "$scope" == all ]]; then\n'
            "  assert_newa_release_profile \\\n"
            '    "$evidence/a/shipping-profiles.lock.json" \\\n'
            "    DIRECT_PROFILE_NOT_RELEASE_APPROVED\n"
            "fi",
            relock,
        )
        self.assertIn("newa-qwerty-direct-native-review.json", relock)
        self.assertIn("newa-qwerty-direct-native-review-candidate.json", relock)
        self.assertIn(
            "jq -S '.candidate' \"$evidence/$run/"
            'newa-qwerty-direct-native-review.json"',
            relock,
        )
        self.assertIn(
            'cmp "$evidence/$run/newa-qwerty-direct-candidate.canonical.json" \\\n'
            '    "$evidence/$run/'
            'newa-qwerty-direct-native-review-candidate.json"',
            relock,
        )
        self.assertIn(".missing_critical_scalar_count == 5", relock)
        self.assertIn(".unresolved_count == 27", relock)
        self.assertIn("bind_layout: false", relock)
        self.assertIn(
            'if [[ "$scope" == all ]]; then\n'
            '  assert_no_release_newa_layout_binding "$evidence/a/layouts-v1.lock.json"\n'
            "fi",
            relock,
        )

        test_loop = relock.index('for test_file in "${test_files[@]}"; do')
        final_inventory = relock.rindex("\nbuild_source_inputs\n")
        inventory_compare = relock.index(
            'cmp "$evidence/input-source-sha256.txt" \\\n'
            '  "$evidence/input-source-sha256.after.txt"'
        )
        installed_compare = relock.index(
            'cmp "$evidence/a/internal-profiles.lock.json" "$internal_profile_lock"'
        )
        self.assertLess(test_loop, final_inventory)
        self.assertLess(final_inventory, inventory_compare)
        self.assertLess(inventory_compare, installed_compare)

    def test_romanized_newa_internal_beta_is_exactly_bound_and_tested(
        self,
    ) -> None:
        relock = source("tools/run_cdjk_relock_validation.sh")
        internal = source("tools/run_cdjk_internal_catalog_validation.sh")
        smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )

        for runner in (relock, internal):
            for guard in (
                '.profile_id == "new-Latn-Deva-NP"',
                '.catalog_readiness == "beta"',
                ".selectable == true",
                '.source_script == "Latn"',
                '.output_script == "Deva"',
                '.lookup_kind == "alias_prefix"',
                '.engine_kind == "alias_decoder"',
                '.layout_id == "latn-qwerty-us-v1"',
                '.pack_binding == "new-Deva-NP"',
                '.pack_artifact.alias_key_count == 1828',
                "c90c7eba644334ef95ae7dfc168d70382083f06ab7fc45a81f33a90052952570",
            ):
                self.assertIn(guard, runner)

        for required in (
            "tools/build_nepal_bhasa_roman_internal_source.py",
            "test_nepal_bhasa_roman_internal_source.py",
            "catalog/nepal-bhasa-roman-internal-prefixes-v0.json",
        ):
            self.assertIn(required, relock)
        self.assertIn("assert_nepal_bhasa_roman_internal_profile", relock)
        self.assertIn("NEPAL_BHASA_ROMAN_ID", smoke)
        self.assertIn("verifyRomanizedNewaProfileAndLayout", smoke)
        self.assertIn("verifyRomanizedNewaPackInput", smoke)
        self.assertIn("Set<String> provenanceArtifacts = new HashSet<>()", smoke)
        self.assertIn(
            'vector.packId + ":" + vector.artifactSha256',
            smoke,
        )
        self.assertIn('"madu"', smoke)
        self.assertIn('"मदु"', smoke)
        self.assertIn("nepal_bhasa_roman_profile_binding_verified", smoke)
        self.assertIn("nepal_bhasa_roman_pack_input_verified", smoke)

    def test_deva_newa_conversion_is_exactly_bound_staged_and_benchmarked(
        self,
    ) -> None:
        relock = source("tools/run_cdjk_relock_validation.sh")
        internal = source("tools/run_cdjk_internal_catalog_validation.sh")

        for runner in (relock, internal):
            for guard in (
                '.profile_id == "new-Deva-Newa-NP"',
                '.lookup_kind == "conversion"',
                '.engine_kind == "converter"',
                '.conversion_binding == "new-Deva-Newa-NP"',
                '.conversion_artifact.converter_id == "new-Deva-Newa-NP"',
                '.conversion_artifact.file_name == "new-Deva-Newa-NP.ncm"',
                "29c88708b3d7aeb741779b7a7464efcb2464e060d7939c7998533d50b11a2d05",
                '.conversion_artifact.release_mode == "internal"',
                '.conversion_artifact.rule_count == 165',
                '["MATCH", "NO_MATCH"]',
            ):
                with self.subTest(runner=runner, guard=guard):
                    self.assertIn(guard, runner)

        for frozen_input in (
            '"$android/conversion-runtime/build.gradle.kts"',
            '"$android/conversion-runtime/consumer-rules.pro"',
            '"$android/conversion-runtime/src/main"',
        ):
            self.assertEqual(internal.count(frozen_input), 2)
        for marker in (
            "expected-internal-conversion-bindings.tsv",
            "expected-internal-conversion-assets.txt",
            "$apk_kind-conversion-assets-sha256.txt",
            "NcmConversionInstrumentation",
            "ncm_canonical_reader_verified=true",
            "ConversionCatalogBenchmarkInstrumentation",
            "benchmark_mode=conversion_catalog_v1",
            "internal-conversion-benchmark.json",
            "iterations_per_profile=10000",
            "warmups_per_profile=1000",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, internal)
        self.assertEqual(internal.count("-e iterations 10000"), 2)
        self.assertEqual(internal.count("-e warmups 1000"), 2)

    def test_nepal_bhasa_internal_milestone_is_tracked_by_relock(self) -> None:
        relock = source("tools/run_cdjk_relock_validation.sh")
        for required in (
            "append_directory_inputs layouts/internal/src",
            "catalog/nepal-bhasa-candidate-pack-v0.json",
            "catalog/nepal-bhasa-internal-prefixes-v0.json",
            "catalog/nepal-bhasa-roman-internal-prefixes-v0.json",
            "catalog/internal-pack-milestones/new-Deva-NP-v0.json",
            "reports/nepal-bhasa-candidate-pack-v0.md",
            "tools/build_nepal_bhasa_internal_source.py",
            "tools/build_nepal_bhasa_roman_internal_source.py",
            "tools/run_cdjk_nepal_bhasa_candidate_pack.sh",
            "test_nepal_bhasa_candidate_pack_runner.py",
            "test_nepal_bhasa_internal_source.py",
            "test_nepal_bhasa_roman_internal_source.py",
        ):
            with self.subTest(required=required):
                self.assertIn(required, relock)
        self.assertNotIn(
            "--candidate layouts/research/deva-nepal-bhasa-v1.json",
            relock,
        )

    def test_internal_layout_notices_are_an_optional_verified_subset(self) -> None:
        gradle = source("android/ime-app/build.gradle.kts")
        runtime = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "LayoutNotices.java"
        )
        debug_smoke = source(
            "android/ime-app/src/debug/java/com/ampixa/nepakeyboard/ime/"
            "ImeSmokeInstrumentation.java"
        )
        internal_smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )
        runner = source("tools/run_cdjk_internal_catalog_validation.sh")
        compiler = source("tools/build_keyboard_layouts.py")

        self.assertIn("MAX_LAYOUTS = 128", compiler)
        self.assertIn("private const val MAX_LAYOUTS = 128", gradle)
        self.assertIn("private static final int MAX_LAYOUTS = 128;", runtime)
        self.assertIn('if (authority == "release") {', gradle)
        self.assertIn("requireExactKeys(license, allowedFields", gradle)
        self.assertIn("requireAllowedKeys(\n                license", gradle)
        self.assertIn("if (value == null)", gradle)
        self.assertIn("hasNoticePath != hasNoticeSha256", gradle)
        self.assertIn("val noticeRows = layouts.mapNotNull(::layoutNoticeRow)", gradle)
        self.assertIn("layouts.mapNotNull { layout ->", gradle)
        self.assertIn("@get:Optional\n    @get:PathSensitive", gradle)
        self.assertIn("!noticeDir.exists() -> emptyList<File>()", gradle)
        self.assertIn(
            "actualNotices.map { it.name }.toSet() != expectedNoticeNames", gradle
        )
        self.assertIn("static final int LAYOUT_NOTICE_COUNT", gradle)
        self.assertIn("static List<String> layoutNoticeIds()", gradle)
        self.assertIn('noticeLayoutIds.isEmpty() -> "Collections.emptyList()"', gradle)

        self.assertNotIn("rows.length() < 1", runtime)
        self.assertIn("GeneratedLayoutRegistry.LAYOUT_NOTICE_COUNT", runtime)
        self.assertIn("GeneratedLayoutRegistry.layoutNoticeIds()", runtime)
        self.assertIn("generated layout notice subset is invalid", runtime)
        self.assertIn('row.isNull("license_url")', runtime)
        self.assertIn("!expectedLayoutIds.isEmpty()", runtime)

        self.assertIn("GeneratedLayoutRegistry.LAYOUT_NOTICE_COUNT", debug_smoke)
        self.assertIn("GeneratedLayoutRegistry.LAYOUT_NOTICE_COUNT", internal_smoke)
        self.assertIn(
            'result.putInt(\n                    "layout_notice_count"', internal_smoke
        )
        self.assertIn('select(type == "object")', runner)
        self.assertIn('has("notice_path") and has("notice_sha256")', runner)
        self.assertIn("internal_layout_notice_count", runner)
        self.assertIn("internal-layout-notice-manifest.json", runner)
        self.assertIn("awk '$0 != \"manifest.json\"'", runner)

    def test_newa_conjunct_joiner_is_mapped_through_android_generation(self) -> None:
        gradle = source("android/ime-app/build.gradle.kts")
        key_spec = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/KeySpec.java"
        )
        session = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "ComposingSession.java"
        )

        for mapping in (
            '"newa_conjunct_joiner",',
            '"newa_conjunct_joiner" -> "NEWA_CONJUNCT_JOINER"',
            '"newa_conjunct_joiner" -> {',
            '"newa_conjunct_joiner" -> "KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER"',
            "$location newa_conjunct_joiner requires input script Newa",
            "$location newa_conjunct_joiner text must be U+200C or U+200D",
        ):
            self.assertIn(mapping, gradle)
        self.assertIn("NEWA_CONJUNCT_JOINER", key_spec)
        self.assertIn(
            "Newa conjunct joiner key must carry U+200C or U+200D",
            key_spec,
        )
        self.assertIn("NEWA_CONJUNCT_JOINER", session)
        self.assertIn("codePoint >= 0x1140e && codePoint <= 0x11434", session)
        self.assertIn(
            'return !"Newa".equals(pendingJoinerScript) || composingAllowed', session
        )

    def test_android_subtype_labels_disambiguate_multiple_methods_per_target(
        self,
    ) -> None:
        gradle = source("android/ime-app/build.gradle.kts")
        self.assertIn("val selectableTargetCounts = selectableRows", gradle)
        self.assertIn('.groupingBy { requiredString(it, "target_id") }', gradle)
        self.assertIn("selectableTargetCounts.getValue(targetId) > 1", gradle)
        self.assertIn('$nativeLabel · ${requiredString(row, "input_label")}', gradle)
        self.assertIn('"nepa-android-subtype-v1\\u0000" + profileId', gradle)
        self.assertIn('android:subtypeId="${subtypeIds.getValue(profileId)}"', gradle)
        self.assertIn("Generated Android subtype IDs collide", gradle)

    def test_tokenized_suggestion_readiness_contract_is_explicit(self) -> None:
        internal_smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )
        engine_api = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionEngine.java"
        )
        snapshot = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionSnapshot.java"
        )
        nkp = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NkpSuggestionEngine.java"
        )
        session = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "ComposingSession.java"
        )
        service = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputMethodService.java"
        )
        view = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputView.java"
        )

        self.assertIn('new SuggestionQuery(english, "h", false)', internal_smoke)
        self.assertIn("missing.suggest(", internal_smoke)
        self.assertIn("internal missing pack is not retryable", internal_smoke)

        for signature in (
            "SuggestionActivation activate(KeyboardProfile profile)",
            "SuggestionActivation suspend()",
            "SuggestionSnapshot suggest(",
            "boolean retry(SuggestionActivation activation)",
        ):
            self.assertIn(signature, engine_api)
        for state in (
            "INACTIVE",
            "LOADING",
            "READY",
            "NO_MATCH",
            "MISSING",
            "CORRUPT",
            "UNAVAILABLE",
        ):
            self.assertIn(state, snapshot)
        self.assertNotIn("void prepare(KeyboardProfile profile)", engine_api)
        self.assertNotIn("prepare(query.profile())", nkp)
        self.assertIn("new ArrayBlockingQueue<>(1)", nkp)
        self.assertIn("loader.execute(task)", nkp)
        self.assertIn("loadingJobsByArtifact.remove(job.key, job)", nkp)
        self.assertIn("activeLoadJob == job", nkp)
        self.assertIn("catch (SecurityException failure)", nkp)
        self.assertIn("catch (IOException failure)", nkp)
        self.assertIn("activation == suggestionActivation", session)
        self.assertIn("composingSession.ownsActivation(activation)", service)
        self.assertIn("inputView.clearSuggestions()", service)
        self.assertIn("listener.onSuggestionRetry()", view)
        self.assertIn("showLanguagePicker(view);", view)

        internal_smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )
        debug_smoke = source(
            "android/ime-app/src/debug/java/com/ampixa/nepakeyboard/ime/"
            "ImeSmokeInstrumentation.java"
        )
        self.assertIn('"tokenized_suggestion_readiness_verified"', internal_smoke)
        self.assertIn('"tokenized_suggestion_readiness_verified"', debug_smoke)
        self.assertIn("old same-profile activation is inactive", debug_smoke)

    def test_android_subtype_and_product_profile_state_are_reconciled(self) -> None:
        preferences = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "LanguagePreferences.java"
        )
        registry = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "AndroidSubtypeRegistry.java"
        )
        service = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputMethodService.java"
        )
        settings = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SettingsActivity.java"
        )

        for token in (
            "KEY_PENDING_SUBTYPE",
            "requestActive(String profileId)",
            "observePlatformProfile(String profileId)",
            "pendingProfile()",
            "state.enabledIds.add(observed.id())",
            "state.pending = state.active",
        ):
            self.assertIn(token, preferences)
        self.assertIn(
            "service.switchInputMethod(inputMethodInfo.getId(), subtype)", registry
        )
        self.assertIn("setInputMethodAndSubtype(", registry)
        self.assertIn("SwitchOutcome requestSwitch(", registry)
        self.assertIn("SwitchPath.INPUT_METHOD_SERVICE", registry)
        self.assertIn("SwitchPath.LEGACY_IME_WINDOW_TOKEN", registry)
        self.assertIn("final boolean dispatched", registry)
        self.assertIn("setExplicitlyEnabledInputMethodSubtypes(", registry)
        self.assertIn("subtype.hashCode() <= 0", registry)
        self.assertIn(
            "profile.localeTag().equalsIgnoreCase(subtype.getLanguageTag())", registry
        )
        self.assertIn("languagePreferences.observePlatformProfile(", service)
        self.assertIn("requestPendingSubtype(boolean callbackMismatch)", service)
        self.assertIn("mismatchedSubtypeCallbacks >= 1", service)
        self.assertIn("AndroidSubtypeRegistry.SwitchOutcome outcome", service)
        self.assertIn("subtypeRegistry.requestSwitch(", service)
        self.assertIn("notifySwitchDispatched(profileId, outcome)", service)
        self.assertIn("languagePreferences.registerStateListener", service)
        self.assertIn("synchronizeEnabledSubtypes()", service)
        self.assertNotIn("return LanguageRegistry.ENGLISH_ID", service)
        self.assertIn("synchronizeAndroidSubtypes()", settings)
        self.assertIn("convertView", settings)
        self.assertIn("LanguageRowHolder", settings)
        self.assertIn("public boolean hasStableIds()", settings)
        self.assertIn("verifyStableProfileIds()", settings)
        self.assertIn("onSaveInstanceState(Bundle outState)", settings)
        self.assertIn(
            "setSelectionFromTop(savedListPosition, savedListOffset)", settings
        )

        internal_smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )
        self.assertIn('"subtype_state_foundation_verified"', internal_smoke)

    def test_first_run_setup_is_resumable_and_observable(self) -> None:
        settings = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SettingsActivity.java"
        )
        strings = source("android/ime-app/src/main/res/values/strings.xml")
        internal_smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )
        architecture = source("docs/product-architecture.md")
        setup_doc = source("docs/android-first-run-setup.md")
        runner = source("tools/run_cdjk_internal_catalog_validation.sh")

        self.assertIn("enum SetupStep", settings)
        for step in (
            "ENABLE_KEYBOARD",
            "SELECT_KEYBOARD",
            "CHOOSE_LANGUAGES",
            "TEST_TYPING",
            "COMPLETE",
        ):
            self.assertIn(step, settings)
        self.assertIn("SetupState derive(", settings)
        self.assertIn("if (!imeEnabled)", settings)
        self.assertIn("else if (!imeSelected)", settings)
        self.assertIn("else if (!languagesReady)", settings)
        self.assertIn("else if (!typingTested)", settings)
        self.assertIn("Settings.Secure.ENABLED_INPUT_METHODS", settings)
        self.assertIn("Settings.Secure.DEFAULT_INPUT_METHOD", settings)
        self.assertIn("registerContentObserver(", settings)
        self.assertIn("manager.getEnabledInputMethodList()", settings)
        self.assertIn("own.getId().equals(selectedId)", settings)
        self.assertIn("languagePreferences.enabledProfiles().size()", settings)
        self.assertIn("setSaveEnabled(false)", settings)
        self.assertIn("View.IMPORTANT_FOR_AUTOFILL_NO", settings)
        self.assertIn("outState.putBoolean(STATE_TYPING_OBSERVED", settings)
        self.assertNotIn("KEY_SETUP_COMPLETE", settings)
        self.assertNotIn("setup_complete_preference", settings)
        self.assertIn("recordTypingObservation(value)", settings)
        self.assertIn("typingObserved && !state.canTestTyping()", settings)
        self.assertIn("View.ACCESSIBILITY_LIVE_REGION_POLITE", settings)
        self.assertIn("new ListView(this)", settings)
        self.assertIn("extends BaseAdapter", settings)

        for resource_name in (
            "setup_enable_title",
            "setup_select_title",
            "setup_languages_title",
            "setup_test_title",
            "setup_complete_title",
            "test_typing_description",
            "enabled_language_count",
        ):
            self.assertIn(f'name="{resource_name}"', strings)

        self.assertIn("verifySetupStateModel()", internal_smoke)
        self.assertIn("observeSetupPlatform(context)", internal_smoke)
        self.assertIn("Settings.Secure.DEFAULT_INPUT_METHOD", internal_smoke)
        self.assertIn("getEnabledInputMethodList()", internal_smoke)
        self.assertIn('setSetupTypingTextForTesting("setup-test")', internal_smoke)
        self.assertIn(
            "setup test text is not restored after instance recreation", internal_smoke
        )
        self.assertIn(
            "observable setup state survives instance recreation", internal_smoke
        )
        self.assertIn('"observable_setup_state_model_verified"', internal_smoke)
        self.assertIn("observable_setup_state_model_verified=true", runner)

        self.assertIn("android-first-run-setup.md", architecture)
        self.assertIn("do not guess one", setup_doc)
        self.assertIn("Do not use `adb shell input text`", setup_doc)
        self.assertIn("Force-stop and relaunch", setup_doc)
        self.assertIn("TalkBack and Switch Access", setup_doc)

    def test_picker_modal_and_manager_foundations_have_narrow_evidence(self) -> None:
        strings = source("android/ime-app/src/main/res/values/strings.xml")
        surface = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "KeyboardSurface.java"
        )
        view = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputView.java"
        )
        settings = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SettingsActivity.java"
        )
        internal_smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )
        debug_smoke = source(
            "android/ime-app/src/debug/java/com/ampixa/nepakeyboard/ime/"
            "ImeSmokeInstrumentation.java"
        )
        runner = source("tools/run_cdjk_internal_catalog_validation.sh")

        self.assertIn('name="language_profile_selected_description"', strings)
        self.assertNotIn('rowDescription += ", selected"', view)
        self.assertIn("R.string.language_profile_selected_description", view)
        self.assertIn("void onLanguagePickerRequested(View source)", surface)
        self.assertIn("showLanguagePicker(source);", view)
        self.assertIn("keyboardContent.setVisibility(INVISIBLE)", view)
        self.assertIn("pickerSheet.setClickable(true)", view)
        self.assertIn("closeLanguagePicker(false, false)", view)
        self.assertIn("pickerBlocksUnderlyingKeyboardForTesting()", view)
        self.assertIn("pickerAccessibilityRestoredForTesting()", view)
        self.assertIn("extends BaseAdapter", view)
        self.assertIn("new ListView(getContext())", view)
        self.assertIn("setSelection(activePosition)", view)
        self.assertIn("pickerRecyclesRowsForTesting()", view)
        self.assertIn(
            "int activePosition = pickerProfileAdapter.positionOf(profile.id())", view
        )
        self.assertIn("activePosition == 0 ? 1 : 0", view)
        self.assertIn("activeRow == rebound", view)
        self.assertIn("activeRow.isActivated()", view)
        self.assertIn("!rebound.isActivated()", view)
        self.assertIn("setProfileSelected(active)", view)
        self.assertIn("row instanceof PickerProfileRow", view)
        self.assertIn("info.setSelected(profileSelected)", view)
        self.assertIn("accessibilitySelectedForTesting()", view)
        self.assertIn("pickerAttachedProfileSelectedForTesting", view)
        self.assertIn("pickerAttachedRowsHaveExactSelectionStateForTesting", view)
        self.assertIn("pickerScrollToProfileForTesting", view)
        self.assertIn("recycleAttachedPickerRowsToward(position)", view)
        self.assertIn("pickerProfileList.scrollListBy", view)
        self.assertIn("remainingSteps = pickerProfileAdapter.getCount()", view)
        self.assertIn("setSelectionFromTop(position, 0)", view)
        self.assertIn("pickerAttachedRowsForTesting", view)
        self.assertIn("extends LinearLayout", view)
        self.assertIn(
            "candidateRow.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_NONE)",
            view,
        )
        self.assertIn("dispatchPopulateAccessibilityEvent", view)
        self.assertIn("candidateAccessibilityContractForTesting", view)
        self.assertIn("candidate.setContentDescription(null)", view)
        self.assertNotIn("view.setSelected(active)", view)
        self.assertIn("TextUtils.isEmpty(holder.marker.getText())", view)
        self.assertIn("!reboundDescription.toString().contains(selectedState)", view)
        self.assertNotIn("new ScrollView(getContext())", view)

        self.assertIn("languageManagerRecyclesRowsForTesting()", settings)
        self.assertIn("getView(1, firstView, languageList)", settings)
        self.assertIn("setOnCheckedChangeListener(null)", settings)
        self.assertIn("setLanguageManagerSelectionFromTopForTesting", settings)
        self.assertIn("PICKER_LAYOUT_TIMEOUT_MS", internal_smoke)
        self.assertIn(
            "String firstPickerProfileId = preferences.enabledProfiles().get(0).id()",
            internal_smoke,
        )
        self.assertNotIn(
            "String firstProfileId = conformance.profiles.get(0).profileId",
            internal_smoke,
        )
        self.assertIn("awaitPickerFirstVisiblePosition", internal_smoke)
        self.assertIn("awaitPickerAttachedProfileSelected", internal_smoke)
        self.assertIn(
            '"maximum enabled picker reaches first position"', internal_smoke
        )
        self.assertIn("List<String> engineSuggestions = awaitSuggestions", internal_smoke)
        self.assertIn("vector.expectedSurface.equals(vector.query)", internal_smoke)
        self.assertIn(
            '" exact validation literal is preserved at tail"', internal_smoke
        )
        self.assertIn(
            "engineSuggestions.get(engineSuggestions.size() - 1)", internal_smoke
        )
        self.assertIn(
            'awaitSessionCandidate(terminal, "टाङ्\\u200c")', internal_smoke
        )
        self.assertIn(
            'awaitSessionCandidate(terminal, "एकङ्\\u200c")', internal_smoke
        )
        self.assertIn(
            "snapshot.candidates().contains(expectedCandidate)", internal_smoke
        )
        self.assertIn(
            "if (expectedSurface.equals(expectedQuery))", internal_smoke
        )
        self.assertIn("snapshot.hasProviderCandidates()", internal_smoke)
        self.assertNotIn(
            '"Sunuwar generated-key pack suggestion"', internal_smoke
        )
        self.assertIn("languageManagerFirstVisibleOffsetForTesting", settings)
        self.assertIn("enum LanguageSection", settings)
        self.assertIn("AVAILABLE_TO_ENABLE", settings)
        self.assertIn("profiles.sort((left, right)", settings)
        self.assertIn("left.sortKey().compareTo(right.sortKey())", settings)
        self.assertIn("languageManagerSectionsOrderedForTesting", settings)
        self.assertIn("languageManagerSectionHeadingsForTesting", settings)
        self.assertIn("setAccessibilityHeading(true)", settings)
        self.assertIn("startsSection(position)", settings)
        self.assertIn("startsLanguage(position)", settings)
        self.assertIn("rebindsLanguageHeadingsForTesting", settings)
        self.assertIn("rebindsGateAndSwitchForTesting", settings)
        self.assertNotIn("catalogReadiness()", settings)

        for evidence_flag in (
            "picker_modal_accessibility_foundation_verified",
            "picker_hold_accessibility_action_verified",
            "picker_attached_max_enabled_recycling_verified",
            "candidate_accessibility_foundation_verified",
            "language_manager_recycling_saved_state_verified",
            "language_manager_sections_verified",
            "language_picker_enabled_only_verified",
            "last_enabled_switch_rejection_verified",
        ):
            self.assertIn(evidence_flag, internal_smoke)
            self.assertIn(evidence_flag + "=true", runner)
        self.assertIn(
            "picker_attached_max_enabled_profiles=$internal_profile_count",
            runner,
        )
        self.assertIn('"$picker_attached_window_rows" -gt 0', runner)
        self.assertIn(
            '"$picker_attached_window_rows" -lt "$internal_profile_count"',
            runner,
        )
        self.assertIn('"$picker_attached_rebound_rows" -gt 0', runner)
        self.assertIn("picker_modal_accessibility_foundation_verified", debug_smoke)
        self.assertIn("picker_hold_accessibility_action_verified", debug_smoke)
        self.assertIn("language_manager_sections_verified", debug_smoke)
        self.assertIn("candidate_accessibility_foundation_verified", debug_smoke)
        self.assertIn("new View.AccessibilityDelegate()", surface)
        self.assertIn("AccessibilityAction.ACTION_LONG_CLICK", surface)
        self.assertIn("R.string.choose_language", surface)
        self.assertIn("return host.performLongClick()", surface)
        self.assertIn("createAccessibilityNodeInfo()", surface)
        self.assertIn("matchingIdCount == 1", surface)
        self.assertIn("&& labelMatches", surface)
        self.assertIn("performPickerHoldAccessibilityActionForTesting", view)
        self.assertIn("shift has no long-click accessibility action", debug_smoke)
        self.assertIn("shift has no long-click accessibility action", internal_smoke)
        self.assertIn("picker opens from accessibility hold", debug_smoke)
        self.assertIn("picker opens from accessibility hold", internal_smoke)
        self.assertNotIn(
            "performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)",
            surface,
        )
        self.assertIn("requestKeyInputFocusForTesting", view)
        self.assertIn("keyHasInputFocusForTesting", view)
        self.assertIn("requestFocusFromTouch()", surface)
        self.assertIn(
            "picker hold source loses input focus while picker is open",
            internal_smoke,
        )
        self.assertIn(
            "picker returns input focus to accessibility hold source",
            internal_smoke,
        )
        self.assertNotIn("suggestionStatusText.setContentDescription", view)
        self.assertIn(
            "candidate accessibility state clears before a status row",
            internal_smoke,
        )
        self.assertIn(
            "profile change clears candidate accessibility state",
            debug_smoke,
        )
        self.assertIn("registerActivityLifecycleCallbacks", internal_smoke)
        self.assertIn("recreatedLatch.await", internal_smoke)
        self.assertIn("original::recreate", internal_smoke)
        self.assertIn(
            "language manager pixel offset survives recreation", internal_smoke
        )
        self.assertIn(
            "disabled selectable profile enters available-to-enable section",
            internal_smoke,
        )
        self.assertIn("blocked profiles start in later section", internal_smoke)
        self.assertIn(
            "preference listener moves disabled profile out of enabled section",
            internal_smoke,
        )
        self.assertIn(
            "in-keyboard picker has exactly the enabled-profile count",
            internal_smoke,
        )
        self.assertIn(
            "in-keyboard picker excludes disabled selectable profile",
            internal_smoke,
        )
        self.assertIn("in-keyboard picker excludes Later profile", internal_smoke)
        self.assertIn(
            "filtered language sections retain stable ordering", internal_smoke
        )
        self.assertIn(
            "same switch rejects repeated attempts to disable final profile",
            internal_smoke,
        )
        self.assertIn("attachEnabledListener(profile, button)", settings)
        self.assertIn('"language_manager_sections_verified"', internal_smoke)
        self.assertIn(
            "pickerHost.setContentView(\n                    holder[0]", internal_smoke
        )
        self.assertIn(
            "stale posted focus cannot reopen picker modal state", internal_smoke
        )
        self.assertIn("internal picker recycles rebound rows", internal_smoke)
        self.assertIn(
            '"picker_attached_max_enabled_recycling_verified"', internal_smoke
        )
        self.assertIn('"picker_attached_max_enabled_profiles"', internal_smoke)
        self.assertIn('"picker_attached_window_rows"', internal_smoke)
        self.assertIn('"picker_attached_rebound_rows"', internal_smoke)
        self.assertIn("new IdentityHashMap<>()", internal_smoke)
        self.assertIn(
            "picker verification uses the maximum enabled selectable set",
            internal_smoke,
        )
        self.assertIn("maximum enabled picker virtualizes rows", internal_smoke)
        self.assertIn("ListView reuses an attached picker row", internal_smoke)
        self.assertIn(
            "recycled top rows never inherit active selection state",
            internal_smoke,
        )
        self.assertIn(
            "active selection persists after attached row recycling",
            internal_smoke,
        )
        self.assertIn(
            "attached active picker row keeps accessibility selected state",
            internal_smoke,
        )
        self.assertIn("picker profile list recycles rebound rows", debug_smoke)

    def test_subtype_compatibility_harness_is_service_bound_and_remote_only(
        self,
    ) -> None:
        activity = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalSubtypeTestActivity.java"
        )
        instrumentation = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalSubtypeCompatibilityInstrumentation.java"
        )
        input_view = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputView.java"
        )
        service = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputMethodService.java"
        )
        manifest = source("android/ime-app/src/internal/AndroidManifest.xml")
        main_runner = source("tools/run_cdjk_internal_catalog_validation.sh")
        compatibility_runner = source("tools/run_cdjk_subtype_compat_validation.sh")
        timeout_ramdisk_builder = source(
            "tools/build_cdjk_android_timeout_ramdisk.sh"
        )

        self.assertIn("SOFT_INPUT_STATE_ALWAYS_VISIBLE", activity)
        self.assertIn("manager.isActive(editor)", activity)
        self.assertIn("onWindowFocusChanged", activity)
        self.assertIn("editor.post(this::showImeForTesting)", activity)
        self.assertIn("editorHasInputFocusForTesting", activity)
        self.assertIn("editorHasWindowFocusForTesting", activity)
        self.assertIn("editorHasViewFocusForTesting", activity)
        self.assertIn("new InputConnectionWrapper(target, false)", activity)
        self.assertIn("AtomicInteger", activity)
        self.assertIn("isPrivateInputType(outAttrs.inputType)", activity)
        self.assertIn("restartAsPasswordForTesting", activity)
        self.assertIn("manager.restartInput(editor)", activity)
        self.assertIn("hideSoftInputFromWindow", activity)
        self.assertIn("Settings.Secure.DEFAULT_INPUT_METHOD", instrumentation)
        self.assertIn("waitForEditorService(host, trace)", instrumentation)
        self.assertIn("SERVICE_REQUEST_INTERVAL_MS", instrumentation)
        self.assertIn("runOnMainSync(host::showImeForTesting)", instrumentation)
        self.assertIn('"focus_driven_ime_readiness_verified"', instrumentation)
        self.assertIn('"initial_editor_window_focus_verified"', instrumentation)
        self.assertIn('"initial_editor_view_focus_verified"', instrumentation)
        self.assertIn('"initial_ime_request_attempts"', instrumentation)
        self.assertIn('"initial_ime_ready_elapsed_ms"', instrumentation)
        self.assertIn("view.showLanguagePicker()", instrumentation)
        self.assertIn("bound picker remains open after layout", instrumentation)
        self.assertIn(
            "view.pickerAttachedProfileSelectedForTesting(LanguageRegistry.ENGLISH_ID)",
            instrumentation,
        )
        self.assertIn("view.performPickerProfileForTesting", instrumentation)
        self.assertIn('view.performKeyIdForTesting("base.r3.k2")', instrumentation)
        self.assertIn("registry.currentProfile()", instrumentation)
        self.assertIn("preferences.pendingProfile() == null", instrumentation)
        self.assertIn('"service_bound_picker_subtype_verified"', instrumentation)
        self.assertIn('"service_bound_globe_subtype_verified"', instrumentation)
        self.assertIn('"platform_subtype_confirmation_verified"', instrumentation)
        self.assertIn("beginDeleteTouchForTesting()", instrumentation)
        self.assertIn("DeleteRepeatController.INITIAL_DELAY_MILLIS", instrumentation)
        self.assertIn("awaitPastRepeatDeadline", instrumentation)
        self.assertIn("passwordPreviousActivation", instrumentation)
        self.assertIn(
            "stateTrace.activationGeneration() > previousActivation",
            instrumentation,
        )
        self.assertIn("waitForIdleSync();", instrumentation)
        self.assertIn(
            "password restart cancels the old held-delete controller",
            instrumentation,
        )
        self.assertIn("LifecycleCancellationEvidence", instrumentation)
        self.assertIn("observedAtMillis", instrumentation)
        self.assertIn("cancellation.dispatchCount", instrumentation)
        self.assertIn("private short delete never reads context", instrumentation)
        self.assertIn("assertDeleteDispatchStoppedAfterCancellation", instrumentation)
        self.assertIn("prevents post-cancellation delete dispatch", instrumentation)
        self.assertIn('"password_restart_cancel_observed_elapsed_ms"', instrumentation)
        self.assertIn('"private_context_read_count"', instrumentation)
        for marker in (
            "service_bound_held_delete_password_restart_cancel_verified",
            "service_bound_held_delete_private_no_context_read_verified",
            "service_bound_held_delete_hide_cancel_verified",
            "service_bound_held_delete_finish_cancel_verified",
            "service_bound_held_delete_post_cancel_dispatch_stability_verified",
        ):
            self.assertIn(f'"{marker}"', instrumentation)
            self.assertIn(f"{marker}=true", main_runner)
            self.assertIn(f"{marker}=true", compatibility_runner)
        self.assertIn("beginDeleteTouchForTesting", input_view)
        self.assertIn("finishDeleteTouchForTesting", input_view)
        self.assertIn("deleteRepeatActiveForTesting", input_view)
        self.assertIn("deleteDispatchCountForTesting", input_view)
        self.assertIn("privateFieldForTesting", service)
        self.assertIn("inputViewActiveForTesting", service)
        self.assertIn("LEGACY_IME_WINDOW_TOKEN", instrumentation)
        self.assertIn("INPUT_METHOD_SERVICE", instrumentation)
        self.assertIn("legacyWindowTokenPresent", instrumentation)
        self.assertIn('"subtype_callback".equals(platformSource)', instrumentation)
        self.assertIn("service == previousService", instrumentation)
        self.assertIn("phase == Phase.PENDING", instrumentation)
        self.assertIn("phase == Phase.DISPATCHED", instrumentation)
        self.assertIn("awaitManagedEnabledSubtypes", instrumentation)
        self.assertIn("getEnabledInputMethodSubtypeList", instrumentation)
        self.assertIn("enabled.size() == expected.size()", instrumentation)
        self.assertIn("InternalSubtypeCompatibilityInstrumentation", manifest)
        self.assertIn('android:exported="false"', manifest)
        self.assertIn("source must exist and output must be new", timeout_ramdisk_builder)
        self.assertIn("system/etc/ramdisk/build.prop", timeout_ramdisk_builder)
        self.assertIn("ro.hw_timeout_multiplier=%s", timeout_ramdisk_builder)
        self.assertIn("overlay.cpio", timeout_ramdisk_builder)
        self.assertIn("oflag=append", timeout_ramdisk_builder)
        self.assertIn("cmp \"$output/ramdisk.cpio\"", timeout_ramdisk_builder)

        self.assertIn("InternalSubtypeCompatibilityInstrumentation", main_runner)
        self.assertIn("service_bound_picker_subtype_verified=true", main_runner)
        self.assertIn("service_bound_globe_subtype_verified=true", main_runner)
        self.assertIn("switch_path=input_method_service", main_runner)
        self.assertIn(
            "same_service_subtype_callback_after_picker_verified=true",
            main_runner,
        )
        self.assertIn(
            "same_service_subtype_callback_after_globe_verified=true",
            main_runner,
        )
        self.assertIn(
            "same_service_subtype_callback_after_picker_verified=true",
            compatibility_runner,
        )
        self.assertIn(
            "same_service_subtype_callback_after_globe_verified=true",
            compatibility_runner,
        )
        self.assertIn("managed_enabled_subtypes_verified=true", main_runner)
        self.assertIn("focus_driven_ime_readiness_verified=true", main_runner)
        self.assertIn("initial_editor_window_focus_verified=true", main_runner)
        self.assertIn("initial_editor_view_focus_verified=true", main_runner)
        self.assertIn(
            "focus_driven_ime_readiness_verified=true",
            compatibility_runner,
        )
        self.assertIn(
            "initial_editor_window_focus_verified=true",
            compatibility_runner,
        )
        self.assertIn(
            "initial_editor_view_focus_verified=true",
            compatibility_runner,
        )
        for readiness_marker in (
            "shell ime list -a -s",
            "installed-ime-metadata-status.txt",
            "installed-ime-metadata-timeout-dumpsys.txt",
            "SECONDS - ime_metadata_wait_start >= 120",
        ):
            self.assertIn(readiness_marker, compatibility_runner)
        self.assertNotIn("-icount", compatibility_runner)
        self.assertIn("-cores 4", compatibility_runner)
        self.assertIn("-memory 4096", compatibility_runner)
        self.assertIn("timeout 1800", compatibility_runner)
        self.assertIn("-cores 4", main_runner)
        self.assertIn("-memory 4096", main_runner)
        for runner in (main_runner, compatibility_runner):
            self.assertIn("-ramdisk", runner)
            self.assertIn("api34-aosp-atd-hw-timeout10-v2", runner)
            self.assertIn(
                "827da7ffbd4071220be81aaee535f75ca81c2a312e2035f7da74d1379f3abe0d",
                runner,
            )
            self.assertIn("timeout-ramdisk-sha256.txt", runner)
            self.assertNotIn("-prop ro.hw_timeout_multiplier=10", runner)
            self.assertIn("getprop ro.hw_timeout_multiplier", runner)
        self.assertIn("private_context_read_count=0", main_runner)
        self.assertIn("private_context_read_count=0", compatibility_runner)
        self.assertIn("internal-apk-source-inputs-sha256.txt", compatibility_runner)
        self.assertIn("internal-apk-stale-inputs.txt", compatibility_runner)
        self.assertIn('find "$input" -type f -newer "$internal_apk"', compatibility_runner)
        self.assertIn('[[ ! -s "$evidence/internal-apk-stale-inputs.txt" ]]', compatibility_runner)
        for runner in (main_runner, compatibility_runner):
            self.assertIn("password_restart_cancel_observed_elapsed_ms", runner)
            self.assertNotIn("require_instrumentation_integer_below", runner)
            self.assertIn("user_zero_unlocked()", runner)
            self.assertIn("shell dumpsys user", runner)
            self.assertIn("RUNNING_UNLOCKED", runner)
            self.assertIn("require_home_ui_ready()", runner)
            self.assertIn("KEYCODE_WAKEUP", runner)
            self.assertIn("shell wm dismiss-keyguard", runner)
            self.assertIn("android.intent.category.HOME", runner)
            self.assertIn("mCurrentFocus=", runner)
            self.assertIn("mFocusedApp=", runner)
            self.assertIn("modal-error-window-is-top", runner)
            self.assertIn("focus_source=", runner)
            self.assertIn("top_window=", runner)
            self.assertIn("wait_for_emulator_ready()", runner)
            self.assertIn("capture_factory_boot_diagnostics()", runner)
            self.assertIn("stabilize_factory_boot()", runner)
            self.assertIn("factory-boot-status.txt", runner)
            self.assertIn("stabilization-offline-status.txt", runner)
            self.assertIn("offline_transition_verified=true", runner)
            self.assertIn("stabilized_boot", runner)
            self.assertIn("am wait-for-broadcast-idle", runner)
            self.assertNotIn("cmd user is-user-unlocked", runner)
            self.assertIn("install_test_apk()", runner)
            self.assertIn("for attempt in 1 2", runner)
            self.assertIn(
                "INSTALL_FAILED_VERIFICATION_FAILURE: Integrity verification timed out",
                runner,
            )
            self.assertIn("successful_attempt=%s", runner)
            self.assertNotIn("settings put global package_verifier_enable", runner)
            self.assertIn("sequence_complete=0", runner)
            self.assertIn("sequence_complete != 1", runner)
            self.assertIn(
                "printf 'sequence_complete=%s\\n'",
                runner,
            )
            self.assertLess(
                runner.rindex("sequence_complete=1"),
                runner.rindex("exit 0"),
            )
        self.assertIn("post-factory-ui", compatibility_runner)
        self.assertIn("factory-boot-broadcast-idle.txt", compatibility_runner)
        self.assertNotIn('stabilize_factory_boot "$serial"', compatibility_runner)
        self.assertIn("post-reboot-ui", main_runner)
        self.assertIn("stabilize_factory_boot emulator-5556", main_runner)
        self.assertIn("INSTRUMENTATION_RESULT: status=ok", main_runner)
        self.assertIn("INSTRUMENTATION_CODE: -1", main_runner)
        self.assertIn("require_instrumentation_result", main_runner)
        self.assertIn("timeout 600", main_runner)
        self.assertIn("manifest_exit_status=0", main_runner)
        self.assertIn("LC_ALL=C find", main_runner)
        self.assertIn("internal-prefix-benchmark.json", main_runner)
        self.assertIn("run-as com.ampixa.nepakeyboard.benchmark", main_runner)
        self.assertIn("process_pss_kb_after_benchmarks", main_runner)
        self.assertNotIn(
            ') >"$evidence/final-evidence-sha256.txt" || true',
            main_runner,
        )
        self.assertIn('"$(hostname -s)" != "cdjk"', compatibility_runner)
        self.assertIn('"$(uname -s)" != Linux', compatibility_runner)
        self.assertIn('"$repo" == /Users/*', compatibility_runner)
        self.assertIn('ID=("?ubuntu"?)', compatibility_runner)
        for api_level in (26, 27, 34):
            self.assertIn(f"  {api_level})", compatibility_runner)
        self.assertIn(
            "expected API must be 26, 27, or 34",
            compatibility_runner,
        )
        self.assertIn("available_kib < 8 * 1024 * 1024", compatibility_runner)
        self.assertIn("12 * 1024 * 1024", compatibility_runner)
        self.assertIn("4 * 1024 * 1024", compatibility_runner)
        self.assertIn("flock -n 9", compatibility_runner)
        self.assertIn("show_ime_with_hard_keyboard 1", compatibility_runner)
        self.assertIn("switch_path=legacy_ime_window_token", compatibility_runner)
        self.assertIn("legacy_window_token_present=true", compatibility_runner)
        self.assertIn("-wipe-data", compatibility_runner)
        self.assertIn("record_post_cleanup_adb", compatibility_runner)
        self.assertIn("INSTRUMENTATION_RESULT: status=ok", compatibility_runner)
        self.assertIn("INSTRUMENTATION_CODE: -1", compatibility_runner)
        self.assertIn("require_instrumentation_result", compatibility_runner)
        self.assertIn("manifest_exit_status=0", compatibility_runner)
        self.assertIn("LC_ALL=C find", compatibility_runner)
        self.assertIn("ro.build.fingerprint", compatibility_runner)
        self.assertIn('cp "$avd_path/config.ini"', compatibility_runner)
        self.assertIn("runtime-conformance-v2.json", compatibility_runner)
        self.assertNotIn("runtime-conformance-v1.json", compatibility_runner)
        self.assertIn(".profile_lock_sha256 == $profile_lock_sha", compatibility_runner)
        self.assertIn(".layout_lock_sha256 == $layout_lock_sha", compatibility_runner)
        self.assertIn(".selectable_profile_count == $selectable", compatibility_runner)
        self.assertNotIn(
            ') >"$evidence/final-evidence-sha256.txt" || true',
            compatibility_runner,
        )

    def test_backspace_v1_markers_are_shared_by_debug_and_internal_smoke(self) -> None:
        debug_smoke = source(
            "android/ime-app/src/debug/java/com/ampixa/nepakeyboard/ime/"
            "ImeSmokeInstrumentation.java"
        )
        internal_smoke = source(
            "android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/"
            "InternalImeSmokeInstrumentation.java"
        )
        vectors = source(
            "android/ime-app/src/decoderContract/java/com/ampixa/nepakeyboard/ime/"
            "BackspaceContractVectors.java"
        )
        runner = source("tools/run_cdjk_internal_catalog_validation.sh")

        self.assertIn("BackspaceContractVectors.verify", debug_smoke)
        self.assertIn("BackspaceContractVectors.verify", internal_smoke)
        self.assertIn("deletePreviousGrapheme()", debug_smoke)
        self.assertIn("deletePreviousGrapheme()", internal_smoke)
        self.assertIn("one hold has a hard dispatch bound", vectors)
        self.assertNotIn(".repeat(", debug_smoke)
        self.assertNotIn(".repeat(", internal_smoke)
        self.assertNotIn(".repeat(", vectors)
        for marker in (
            "backspace_grapheme_vectors_verified",
            "backspace_owned_composition_verified",
            "backspace_committed_context_verified",
            "backspace_fallback_verified",
            "backspace_sink_private_no_read_verified",
            "backspace_suggestion_touch_ownership_verified",
            "backspace_zwj_tailoring_verified",
            "newa_conjunct_joiner_verified",
            "backspace_devanagari_state_rebuild_verified",
            "backspace_selection_contract_verified",
            "backspace_context_completeness_verified",
            "delete_repeat_timing_verified",
            "delete_touch_pointer_ownership_verified",
            "delete_repeat_view_cancellation_verified",
        ):
            self.assertIn(marker, debug_smoke)
            self.assertIn(marker, internal_smoke)
            self.assertIn(marker + "=true", runner)


if __name__ == "__main__":
    unittest.main()
