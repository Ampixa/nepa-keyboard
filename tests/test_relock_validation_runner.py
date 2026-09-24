from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tools" / "run_cdjk_relock_validation.sh"


class RelockValidationRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = RUNNER_PATH.read_text(encoding="utf-8")

    def test_selected_tests_are_one_inventory_for_hashing_and_execution(self) -> None:
        blocks = re.findall(
            r"^\s*test_files=\(\n(.*?)^\s*\)$",
            self.runner,
            re.MULTILINE | re.DOTALL,
        )
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            names = {
                line.strip()
                for line in block.splitlines()
                if line.strip()
            }
            self.assertIn("test_shipping_profile_catalog.py", names)
            self.assertIn("test_keyboard_layouts.py", names)
            self.assertIn("test_conversion_map.py", names)
            self.assertIn("test_nepal_bhasa_conversion_vectors.py", names)
            self.assertIn("test_android_conversion_substrate.py", names)
            self.assertIn("test_bantawa_internal_source.py", names)
            self.assertIn("test_western_magar_internal_source.py", names)
            self.assertIn("test_relock_validation_runner.py", names)
            self.assertIn("test_key_alternates.py", names)
            self.assertIn("test_transliteration_profiles.py", names)
            self.assertIn("test_transliteration_map.py", names)
            self.assertIn("test_transliteration_contrasts.py", names)
            self.assertIn("test_emoji_catalog.py", names)
            self.assertIn("test_finalize_limbu_internal_milestone.py", names)
            self.assertEqual(len(names), len(block.splitlines()))

        inventory_loop = (
            'for test_file in "${test_files[@]}"; do\n'
            '    source_inputs+=("tests/$test_file")\n'
            "  done"
        )
        execution_loop = (
            'for test_file in "${test_files[@]}"; do\n'
            '  run_python -m unittest discover -s tests -p "$test_file"'
        )
        self.assertIn(inventory_loop, self.runner)
        self.assertIn(execution_loop, self.runner)
        self.assertLess(self.runner.index(inventory_loop), self.runner.index(execution_loop))

    def test_conversion_inputs_and_android_sources_are_frozen(self) -> None:
        for required in (
            "catalog/internal-profile-review.json",
            "catalog/internal-pack-milestones/bap-Deva-NP-v0.json",
            "catalog/internal-pack-milestones/mrd-Deva-NP-v0.json",
            "catalog/internal-pack-milestones/thq-Deva-NP-v0.json",
            "tools/build_bantawa_internal_source.py",
            "tools/build_western_magar_internal_source.py",
            "schemas/shipping-profile-review.schema.json",
            "schemas/shipping-profile-lock.schema.json",
            "tools/build_shipping_profile_catalog.py",
            "tools/build_conversion_map.py",
            "converters/internal/src/new-deva-newa-v1.json",
            "reports/nepal-bhasa-deva-newa-internal-map-v0.json",
            "catalog/nepal-bhasa-deva-newa-internal-vectors-v0.json",
            "android/settings.gradle.kts",
            "android/ime-app/build.gradle.kts",
            "android/benchmark-app/build.gradle.kts",
            "android/conversion-runtime/build.gradle.kts",
            "android/conversion-runtime/consumer-rules.pro",
            "android/conversion-runtime/src/main/AndroidManifest.xml",
            "append_directory_tree_inputs android/ime-app/src",
            "append_directory_tree_inputs android/benchmark-app/src/main",
            "append_directory_tree_inputs android/pack-runtime/src/main",
            "append_directory_tree_inputs android/conversion-runtime/src/main",
            ".evidence[]?.artifacts[]?.path",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.runner)
        self.assertEqual(self.runner.count("\nbuild_source_inputs\n"), 2)
        self.assertIn("input-source-sha256.after.txt", self.runner)
        self.assertIn(
            'cmp "$evidence/input-source-sha256.txt" \\\n'
            '  "$evidence/input-source-sha256.after.txt"',
            self.runner,
        )

    def test_python_runtime_is_pinned_without_mutating_the_source_tree(self) -> None:
        self.assertIn('python_bin="$repo/.venv/bin/python"', self.runner)
        self.assertIn("if sys.version_info[:2] != (3, 14):", self.runner)
        self.assertIn('if unicodedata.unidata_version != "16.0.0":', self.runner)
        self.assertIn('PYTHONPATH=src:. timeout 600 "$python_bin" "$@"', self.runner)
        self.assertIn('sha256sum "$python_bin" >"$evidence/python-runtime-sha256.txt"',
                      self.runner)
        self.assertIn('"$evidence/python-runtime-sha256.after.txt"', self.runner)
        self.assertNotIn("uv run", self.runner)

    def test_generated_android_assets_are_transaction_outputs(self) -> None:
        output_paths = (
            "android/ime-app/src/main/assets/nepa-layouts/key-alternates-v1.json",
            "android/ime-app/src/main/assets/nepa-translit/profiles-v1.json",
        )
        tracked_blocks = re.findall(
            r"^\s*tracked_paths=\(\n(.*?)^\s*\)$",
            self.runner,
            re.MULTILINE | re.DOTALL,
        )
        self.assertEqual(len(tracked_blocks), 2)
        for block in tracked_blocks:
            for path in output_paths:
                self.assertIn(path, block)
        for generator in (
            "tools/build_key_alternates.py",
            "tools/build_transliteration_map.py",
            "tools/build_transliteration_profiles.py",
            "tools/build_emoji_catalog.py",
        ):
            self.assertIn(generator, self.runner)
        for reviewed_input in (
            "catalog/key-alternates-v0.json",
            "catalog/transliteration-profiles-v0.json",
            "append_directory_tree_inputs catalog/transliteration",
        ):
            self.assertIn(reviewed_input, self.runner)
        self.assertIn('if [[ "$relative_path" == "$tracked" ]]; then', self.runner)
        self.assertIn("continue 2", self.runner)
        self.assertIn('"$evidence/a/key-alternates-v1.json"', self.runner)
        self.assertIn('"$evidence/b/key-alternates-v1.json"', self.runner)
        self.assertIn('"$evidence/a/transliteration-profiles-v1.json"', self.runner)
        self.assertIn('"$evidence/b/transliteration-profiles-v1.json"', self.runner)
        self.assertIn('--check >"$evidence/key-alternates-check.log"', self.runner)
        self.assertIn('--check >"$evidence/transliteration-profiles-check.log"', self.runner)

    def test_converter_schema_and_two_run_artifact_are_exactly_pinned(self) -> None:
        self.assertIn("assert_conversion_schema_contract", self.runner)
        self.assertIn('.conversion_artifact.converter_id == "new-Deva-Newa-NP"', self.runner)
        self.assertIn('has("conversion_id") | not', self.runner)
        self.assertIn(
            '== "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"',
            self.runner,
        )
        self.assertIn("for run in a b; do", self.runner)
        self.assertIn("run_python tools/build_conversion_map.py", self.runner)
        self.assertIn(
            'cmp "$evidence/a/$newa_converter_file" \\\n'
            '  "$evidence/b/$newa_converter_file"',
            self.runner,
        )
        self.assertIn(
            "newa_converter_sha256="
            "29c88708b3d7aeb741779b7a7464efcb2464e060d7939c7998533d50b11a2d05",
            self.runner,
        )
        self.assertIn(".lock_version == 2", self.runner)
        self.assertIn(".generator_version == 2", self.runner)
        self.assertIn('has("conversion_binding")', self.runner)
        self.assertIn('has("conversion_artifact")', self.runner)
        self.assertLess(
            self.runner.index("assert_conversion_schema_contract schemas/"),
            self.runner.index("transaction_started=1"),
        )
        self.assertLess(
            self.runner.index("run_python tools/build_conversion_map.py"),
            self.runner.index("transaction_started=1"),
        )

    def test_transaction_has_rollback_and_exact_android_pin_checks(self) -> None:
        for required in (
            "trap on_exit EXIT",
            "restore_originals || rollback_status=$?",
            'chmod --reference="$evidence/original/$relative"',
            'cmp "$evidence/original/$relative" "$repo/$relative"',
            'sha256sum "${tracked_paths[@]}" >"$evidence/original-sha256.txt"',
            'sha256sum "${tracked_paths[@]}" >"$evidence/installed-sha256.txt"',
            "run_python tools/update_android_lock_pins.py",
            'cmp "$evidence/android-pin-update-hashes.json"',
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.runner)
        transaction_start = self.runner.index("transaction_started=1")
        first_install = self.runner.index(
            'install -m 0644 "$evidence/a/internal-profiles.lock.json"'
        )
        final_rehash = self.runner.rindex("\nbuild_source_inputs\n")
        installed_compare = self.runner.index(
            'cmp "$evidence/a/internal-profiles.lock.json" "$internal_profile_lock"'
        )
        self.assertLess(transaction_start, first_install)
        self.assertLess(final_rehash, installed_compare)


if __name__ == "__main__":
    unittest.main()
