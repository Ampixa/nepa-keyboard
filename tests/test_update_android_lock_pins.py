from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.update_android_lock_pins import (
    GRADLE_PATH,
    LOCK_PATHS,
    PIN_SITES,
    TASK_TYPES,
    LockPinError,
    main,
    update_android_lock_pins,
)


ROOT = Path(__file__).resolve().parents[1]
OLD_PIN = "0" * 64


def task_block(task_name: str) -> str:
    properties = [
        site.property_name for site in PIN_SITES if site.task_name == task_name
    ]
    pins = "".join(
        f'    {property_name}.set(\n        "{OLD_PIN}"\n    )\n'
        for property_name in properties
    )
    return (
        f"val {task_name} = tasks.register<{TASK_TYPES[task_name]}>(\n"
        f'    "{task_name}"\n'
        ") {\n"
        f"{pins}"
        "}\n"
    )


class UpdateAndroidLockPinsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.payloads = {
            name: f"fixture-{index}-{name}\n".encode("utf-8")
            for index, name in enumerate(LOCK_PATHS, start=1)
        }
        for name, relative_path in LOCK_PATHS.items():
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.payloads[name])
        self.gradle_path = self.root / GRADLE_PATH
        self.gradle_path.parent.mkdir(parents=True, exist_ok=True)
        self.write_gradle(self.fixture_gradle())

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def fixture_gradle() -> str:
        blocks = "\n".join(task_block(name) for name in TASK_TYPES)
        return (
            "// This identical-looking value is outside the closed pin sites.\n"
            f'// untouched = "{OLD_PIN}"\n\n'
            f"{blocks}"
        )

    def write_gradle(self, text: str) -> None:
        self.gradle_path.write_text(text, encoding="utf-8")

    def expected_hashes(self) -> dict[str, str]:
        return {
            name: hashlib.sha256(payload).hexdigest()
            for name, payload in self.payloads.items()
        }

    def test_updates_exactly_nine_sites_atomically_and_preserves_mode(self) -> None:
        os.chmod(self.gradle_path, 0o640)
        original_inode = self.gradle_path.stat().st_ino

        result = update_android_lock_pins(self.root, scope="all")

        self.assertEqual(result["status"], "updated")
        self.assertTrue(result["changed"])
        self.assertEqual(result["hashes"], self.expected_hashes())
        updated = self.gradle_path.read_text(encoding="utf-8")
        expected_counts = {
            "release_profile": 4,
            "internal_profile": 3,
            "release_layout": 1,
            "internal_layout": 1,
        }
        for name, count in expected_counts.items():
            self.assertEqual(updated.count(self.expected_hashes()[name]), count)
        self.assertIn(f'// untouched = "{OLD_PIN}"', updated)
        self.assertEqual(self.gradle_path.stat().st_mode & 0o777, 0o640)
        self.assertNotEqual(self.gradle_path.stat().st_ino, original_inode)

        second = update_android_lock_pins(self.root, scope="all")
        self.assertEqual(second["status"], "current")
        self.assertFalse(second["changed"])

    def test_check_is_read_only_and_main_emits_compact_json(self) -> None:
        original = self.gradle_path.read_bytes()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main([
                "--repository-root",
                str(self.root),
                "--scope",
                "all",
                "--check",
            ])
        self.assertEqual(status, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(self.gradle_path.read_bytes(), original)
        stale = json.loads(stdout.getvalue())
        self.assertEqual(stale["status"], "stale")
        self.assertTrue(stale["changed"])
        self.assertEqual(stale["hashes"], self.expected_hashes())
        self.assertNotIn(" ", stdout.getvalue())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main([
                "--repository-root",
                str(self.root),
                "--scope",
                "all",
            ]), 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "updated")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(
                main([
                    "--repository-root",
                    str(self.root),
                    "--scope",
                    "all",
                    "--check",
                ]),
                0,
            )
        self.assertEqual(json.loads(stdout.getvalue())["status"], "current")

    def test_default_internal_scope_does_not_read_or_parse_public_lane(self) -> None:
        for lock_name in ("release_profile", "release_layout"):
            (self.root / LOCK_PATHS[lock_name]).unlink()
        public_tasks = {
            "generateShippingProfileCatalog",
            "generateLayoutRegistry",
            "stageReleaseExternalPacks",
            "stageDebugExternalPacks",
        }
        internal_only_gradle = self.fixture_gradle()
        for task_name in public_tasks:
            internal_only_gradle = internal_only_gradle.replace(
                task_block(task_name),
                "",
            )
        self.write_gradle(internal_only_gradle)

        result = update_android_lock_pins(self.root)

        expected = self.expected_hashes()
        self.assertEqual(result["scope"], "internal")
        self.assertEqual(
            result["hashes"],
            {
                "internal_profile": expected["internal_profile"],
                "internal_layout": expected["internal_layout"],
            },
        )
        updated = self.gradle_path.read_text(encoding="utf-8")
        self.assertEqual(updated.count(expected["internal_profile"]), 3)
        self.assertEqual(updated.count(expected["internal_layout"]), 1)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main([
                "--repository-root",
                str(self.root),
                "--check",
            ])
        self.assertEqual(status, 0)
        checked = json.loads(stdout.getvalue())
        self.assertEqual(checked["scope"], "internal")
        self.assertEqual(checked["status"], "current")

    def test_rejects_missing_duplicate_and_malformed_task_blocks(self) -> None:
        task_name = "generateShippingProfileCatalog"
        block = task_block(task_name)
        cases = (
            ("missing", "missing", self.fixture_gradle().replace(block, "")),
            ("duplicate", "duplicate", self.fixture_gradle() + "\n" + block),
            (
                "malformed_header",
                "malformed",
                self.fixture_gradle().replace(
                    f'    "{task_name}"\n) {{',
                    f'    "{task_name}"\n)',
                    1,
                ),
            ),
            (
                "wrong_type",
                "malformed",
                self.fixture_gradle().replace(
                    "tasks.register<GenerateShippingProfileCatalog>",
                    "tasks.register<GenerateLayoutRegistry>",
                    1,
                ),
            ),
            (
                "malformed_closing_line",
                "malformed",
                self.fixture_gradle().replace("}\n", "} trailing\n", 1),
            ),
            (
                "unterminated",
                "unterminated",
                self.fixture_gradle().replace("}\n", "", 1),
            ),
        )
        for label, expected, text in cases:
            with self.subTest(label=label):
                self.write_gradle(text)
                with self.assertRaisesRegex(LockPinError, expected):
                    update_android_lock_pins(self.root, scope="all")

    def test_rejects_missing_duplicate_malformed_and_extra_pin_calls(self) -> None:
        snippet = (
            "    expectedLockSha256.set(\n"
            f'        "{OLD_PIN}"\n'
            "    )\n"
        )
        cases = (
            (
                "missing",
                "exactly one",
                self.fixture_gradle().replace(snippet, "", 1),
            ),
            (
                "duplicate",
                "exactly one",
                self.fixture_gradle().replace(snippet, snippet + snippet, 1),
            ),
            (
                "malformed",
                "malformed",
                self.fixture_gradle().replace(
                    snippet,
                    snippet.replace(OLD_PIN, "A" * 64),
                    1,
                ),
            ),
            (
                "extra",
                "exactly nine",
                self.fixture_gradle()
                + (
                    "\nval unrelated = tasks.register<StageExternalReleasePacks>(\n"
                    '    "unrelated"\n'
                    ") {\n"
                    "    expectedProfileLockSha256.set(\n"
                    f'        "{OLD_PIN}"\n'
                    "    )\n"
                    "}\n"
                ),
            ),
        )
        for label, expected, text in cases:
            with self.subTest(label=label):
                self.write_gradle(text)
                with self.assertRaisesRegex(LockPinError, expected):
                    update_android_lock_pins(self.root, scope="all")

    def test_rejects_symbolic_canonical_lock(self) -> None:
        lock_path = self.root / LOCK_PATHS["release_profile"]
        lock_path.unlink()
        lock_path.symlink_to(self.root / LOCK_PATHS["internal_profile"])
        with self.assertRaisesRegex(LockPinError, "symbolic"):
            update_android_lock_pins(self.root, scope="all")

    def test_repository_gradle_matches_the_closed_internal_contract(self) -> None:
        result = update_android_lock_pins(ROOT, check=True, scope="internal")
        internal_sites = [
            site
            for site in PIN_SITES
            if site.lock_name in {"internal_profile", "internal_layout"}
        ]
        self.assertEqual(len(internal_sites), 4)
        self.assertEqual(
            set(result["hashes"]),
            {"internal_profile", "internal_layout"},
        )
        self.assertIn(result["status"], {"current", "stale"})


if __name__ == "__main__":
    unittest.main()
