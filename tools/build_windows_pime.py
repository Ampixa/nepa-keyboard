#!/usr/bin/env python3
"""Build a deterministic three-profile PIME overlay for Windows."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "desktop/windows/pime/ime_nepa.py"
ASSETS = ROOT / "android/ime-app/src/main/assets/nepa-translit"
OUTPUT = ROOT / "desktop/windows/build"
VERSION = "0.2.0"
PROFILES = (
    {
        "directory": "nepa_nepali_phonetic",
        "name": "Nepali Phonetic — Nepa",
        "profile_id": "npi-Latn-Deva-v0",
        "asset_name": "npi-Latn-Deva-v1.json",
        "guid": "{05AFA9C5-4E8F-4ADC-89BD-49913BBA2882}",
        "locale": "ne-NP",
    },
    {
        "directory": "nepa_newa_phonetic",
        "name": "Nepal Bhasa Phonetic (Newa) — Nepa",
        "profile_id": "new-Latn-Newa-v0",
        "asset_name": "new-Latn-Newa-v1.json",
        "guid": "{441A58E7-E7C2-4EC9-89D0-1B51152FAD40}",
        "locale": "new-NP",
    },
    {
        "directory": "nepa_limbu_phonetic",
        "name": "Limbu Phonetic (Sirijanga) — Nepa",
        "profile_id": "lif-Latn-Limb-v0",
        "asset_name": "lif-Latn-Limb-v1.json",
        "guid": "{670B76E0-850C-416B-B412-40A0F7300576}",
        "locale": "ne-NP",
    },
)


def is_payload_file(path: Path) -> bool:
    return path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def prepare_tree(destination: Path) -> dict[str, object]:
    resolved = destination.resolve()
    expected_parent = OUTPUT.resolve()
    if resolved != expected_parent / "PIME":
        raise ValueError(f"refusing unexpected output directory {resolved}")
    if destination.exists():
        shutil.rmtree(destination)
    input_methods = destination / "python/input_methods"
    input_methods.mkdir(parents=True)

    files: dict[str, str] = {}
    for profile in PROFILES:
        target = input_methods / str(profile["directory"])
        package = target / "nepa_keyboard"
        package.mkdir(parents=True)
        shutil.copy2(SOURCE, target / "ime_nepa.py")
        for module_name in ("__init__.py", "desktop_composer.py", "transliteration.py"):
            shutil.copy2(ROOT / "src/nepa_keyboard" / module_name, package / module_name)
        shutil.copy2(ASSETS / str(profile["asset_name"]), target / str(profile["asset_name"]))
        (target / "profile.json").write_bytes(
            canonical(
                {
                    "profile_id": profile["profile_id"],
                    "display_name": profile["name"],
                    "asset_name": profile["asset_name"],
                }
            )
        )
        (target / "ime.json").write_bytes(
            canonical(
                {
                    "name": profile["name"],
                    "version": VERSION,
                    "guid": profile["guid"],
                    "locale": profile["locale"],
                    "fallbackLocale": "ne-NP",
                    "icon": "",
                    "win8_icon": "",
                    "moduleName": "ime_nepa",
                    "serviceName": "NepaTextService",
                }
            )
        )

    for path in sorted(destination.rglob("*")):
        if is_payload_file(path):
            files[path.relative_to(destination).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    manifest: dict[str, object] = {
        "format_version": 1,
        "product": "Nepa Phonetic PIME overlay",
        "version": VERSION,
        "profiles": [profile["profile_id"] for profile in PROFILES],
        "files": files,
    }
    (destination / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def build_zip(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if not is_payload_file(path):
                continue
            relative = path.relative_to(source.parent).as_posix()
            info = zipfile.ZipInfo(relative, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    tree = OUTPUT / "PIME"
    archive = OUTPUT / f"Nepa-Phonetic-PIME-{VERSION}.zip"
    if args.check:
        if not tree.is_dir() or not archive.is_file():
            print("windows_pime_check=missing")
            return 3
        expected_manifest = json.loads((tree / "manifest.json").read_text())
        actual_files = {}
        for path in sorted(tree.rglob("*")):
            if is_payload_file(path) and path.name != "manifest.json":
                actual_files[path.relative_to(tree).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        if expected_manifest.get("files") != actual_files:
            print("windows_pime_check=drifted")
            return 3
        print("windows_pime_check=ok")
        return 0
    manifest = prepare_tree(tree)
    build_zip(tree, archive)
    print(f"windows_pime_profiles={len(manifest['profiles'])}")
    print(f"windows_pime_archive={archive}")
    print(f"windows_pime_sha256={hashlib.sha256(archive.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
