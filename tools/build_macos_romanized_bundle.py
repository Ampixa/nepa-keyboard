#!/usr/bin/env python3
"""Build the deterministic Nepa Romanized Pro macOS keyboard-layout bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "desktop" / "macos" / "romanized-pro-v1.json"
DEFAULT_OUTPUT = ROOT / "desktop" / "macos" / "generated"

KEY_CODES = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "equal": 24,
    "9": 25,
    "7": 26,
    "hyphen": 27,
    "8": 28,
    "0": 29,
    "rbracket": 30,
    "o": 31,
    "u": 32,
    "lbracket": 33,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "quote": 39,
    "k": 40,
    "semicolon": 41,
    "backslash": 42,
    "comma": 43,
    "slash": 44,
    "n": 45,
    "m": 46,
    "period": 47,
    "backquote": 50,
}

LATIN = {
    "a": "a", "s": "s", "d": "d", "f": "f", "h": "h", "g": "g",
    "z": "z", "x": "x", "c": "c", "v": "v", "b": "b", "q": "q",
    "w": "w", "e": "e", "r": "r", "y": "y", "t": "t", "1": "1",
    "2": "2", "3": "3", "4": "4", "6": "6", "5": "5", "equal": "=",
    "9": "9", "7": "7", "hyphen": "-", "8": "8", "0": "0",
    "rbracket": "]", "o": "o", "u": "u", "lbracket": "[", "i": "i",
    "p": "p", "l": "l", "j": "j", "quote": "'", "k": "k",
    "semicolon": ";", "backslash": "\\", "comma": ",", "slash": "/",
    "n": "n", "m": "m", "period": ".", "backquote": "`",
}

LATIN_SHIFT = {
    **{key: value.upper() for key, value in LATIN.items() if value.isalpha()},
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^",
    "7": "&", "8": "*", "9": "(", "0": ")", "equal": "+",
    "hyphen": "_", "rbracket": "}", "lbracket": "{", "quote": '"',
    "semicolon": ":", "backslash": "|", "comma": "<", "slash": "?",
    "period": ">", "backquote": "~",
}

# Non-printing, keypad, navigation, and function-key behavior retained from the
# proven macOS reference layout. C0 values are rendered as XML 1.1 character refs.
COMMON_OUTPUTS = {
    36: "\r", 48: "\t", 49: " ", 51: "\b", 52: "\x03", 53: "\x1b",
    64: "\x10", 65: ".", 66: "\x1d", 67: "*", 69: "+", 70: "\x1c",
    71: "\x1b", 72: "\x1f", 75: "/", 76: "\x03", 77: "\x1e", 78: "-",
    79: "\x10", 80: "\x10", 81: "=", 82: "0", 83: "1", 84: "2",
    85: "3", 86: "4", 87: "5", 88: "6", 89: "7", 91: "8", 92: "9",
    96: "\x10", 97: "\x10", 98: "\x10", 99: "\x10", 100: "\x10",
    101: "\x10", 102: "\x10", 103: "\x10", 104: "\x10", 105: "\x10",
    106: "\x10", 107: "\x10", 108: "\x10", 109: "\x10", 110: "\x10",
    111: "\x10", 112: "\x10", 113: "\x10", 114: "\x05", 115: "\x01",
    116: "\x0b", 117: "\x7f", 118: "\x10", 119: "\x04", 120: "\x10",
    121: "\x0c", 122: "\x10", 123: "\x1c", 124: "\x1d", 125: "\x1f",
    126: "\x1e",
}

CONTROL_OVERRIDES = {
    "a": "\x01", "s": "\x13", "d": "\x04", "f": "\x06", "h": "\x08",
    "g": "\x07", "z": "\x1a", "x": "\x18", "c": "\x03", "v": "\x16",
    "b": "\x02", "q": "\x11", "w": "\x17", "e": "\x05", "r": "\x12",
    "y": "\x19", "t": "\x14", "hyphen": "\x1f", "rbracket": "\x1d",
    "o": "\x0f", "u": "\x15", "lbracket": "\x1b", "i": "\x09",
    "p": "\x10", "l": "\x0c", "j": "\x0a", "k": "\x0b",
    "backslash": "\x1c", "n": "\x0e", "m": "\x0d",
}

SCRIPT_RANGES = {
    "Deva": ((0x0900, 0x097F),),
    "Newa": ((0x11400, 0x1147F),),
    "Limb": ((0x1900, 0x194F),),
}


class BuildError(ValueError):
    """Raised when a source or generated bundle violates the contract."""


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise BuildError(f"root must be an object: {path}")
    return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def base_map(base: str, resolved: dict[str, dict[int, str]]) -> dict[int, str]:
    if base == "normal":
        if "normal" not in resolved:
            raise BuildError("normal layer must be resolved before it can be inherited")
        return dict(resolved["normal"])
    if base == "latin":
        labels = LATIN
    elif base == "latin_shift":
        labels = LATIN_SHIFT
    else:
        raise BuildError(f"unsupported layer base: {base}")
    values = dict(COMMON_OUTPUTS)
    values.update({KEY_CODES[key]: output for key, output in labels.items()})
    return values


def validate_output(profile: dict[str, Any], layer: str, key: str, output: str) -> None:
    if not isinstance(output, str):
        raise BuildError(f"{profile['profile_id']} {layer}.{key} output must be a string")
    if unicodedata.normalize("NFC", output) != output:
        raise BuildError(f"{profile['profile_id']} {layer}.{key} output is not NFC")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in output):
        raise BuildError(f"{profile['profile_id']} {layer}.{key} contains a surrogate")
    ranges = SCRIPT_RANGES[profile["output_script"]]
    for char in output:
        scalar = ord(char)
        if scalar < 0x80 or scalar in {0x200C, 0x200D, 0x0964, 0x0965}:
            continue
        if not any(first <= scalar <= last for first, last in ranges):
            raise BuildError(
                f"{profile['profile_id']} {layer}.{key} emits foreign U+{scalar:04X}"
            )


def resolve_layers(profile: dict[str, Any]) -> dict[str, dict[int, str]]:
    declared = profile.get("layers")
    if not isinstance(declared, dict):
        raise BuildError(f"{profile['profile_id']} layers must be an object")
    resolved: dict[str, dict[int, str]] = {}
    for layer in ("normal", "shift", "caps", "option", "option_shift"):
        source = declared.get(layer)
        if not isinstance(source, dict):
            raise BuildError(f"{profile['profile_id']} is missing layer {layer}")
        values = base_map(source.get("base", ""), resolved)
        overrides = source.get("overrides")
        if not isinstance(overrides, dict):
            raise BuildError(f"{profile['profile_id']} {layer}.overrides must be an object")
        for key, output in overrides.items():
            if key not in KEY_CODES:
                raise BuildError(f"{profile['profile_id']} {layer} has unknown key {key}")
            validate_output(profile, layer, key, output)
            values[KEY_CODES[key]] = output
        resolved[layer] = values

    resolved["command"] = base_map("latin", resolved)
    control = base_map("latin", resolved)
    control.update({KEY_CODES[key]: output for key, output in CONTROL_OVERRIDES.items()})
    resolved["control"] = control

    complete_output = "".join(
        value
        for layer in ("normal", "shift", "caps", "option", "option_shift")
        for value in resolved[layer].values()
    )
    for required in profile.get("required_outputs", []):
        if not isinstance(required, str) or required not in complete_output:
            raise BuildError(f"{profile['profile_id']} is missing required output {required!r}")
    return resolved


def xml_attribute(value: str) -> str:
    pieces: list[str] = []
    for char in value:
        scalar = ord(char)
        if scalar < 0x20 or scalar == 0x7F or scalar in {0x200C, 0x200D}:
            pieces.append(f"&#x{scalar:04X};")
        elif char == "&":
            pieces.append("&amp;")
        elif char == "<":
            pieces.append("&lt;")
        elif char == ">":
            pieces.append("&gt;")
        elif char == '"':
            pieces.append("&quot;")
        else:
            pieces.append(char)
    return "".join(pieces)


def render_key_map(index: int, values: dict[int, str]) -> list[str]:
    lines = [f'        <keyMap index="{index}">']
    for code, output in sorted(values.items()):
        lines.append(f'            <key code="{code}" output="{xml_attribute(output)}"/>')
    lines.append("        </keyMap>")
    return lines


def render_keylayout(profile: dict[str, Any]) -> str:
    layers = resolve_layers(profile)
    ordered = (
        layers["normal"], layers["shift"], layers["caps"], layers["command"],
        layers["option"], layers["option_shift"], layers["control"],
    )
    maxout = max(
        len(output.encode("utf-16-le")) // 2
        for layer in ordered
        for output in layer.values()
    )
    name = xml_attribute(profile["name"])
    lines = [
        '<?xml version="1.1" encoding="UTF-8"?>',
        '<!DOCTYPE keyboard SYSTEM "file://localhost/System/Library/DTDs/KeyboardLayout.dtd">',
        '<!-- Generated by tools/build_macos_romanized_bundle.py; do not edit. -->',
        (
            f'<keyboard group="{profile["keyboard_group"]}" '
            f'id="{profile["keyboard_id"]}" name="{name}" maxout="{maxout}">'
        ),
        "    <layouts>",
        '        <layout first="0" last="0" mapSet="nepa" modifiers="nepa-modifiers"/>',
        "    </layouts>",
        '    <modifierMap id="nepa-modifiers" defaultIndex="6">',
        '        <keyMapSelect mapIndex="0"><modifier keys=""/></keyMapSelect>',
        '        <keyMapSelect mapIndex="1"><modifier keys="anyShift caps?"/></keyMapSelect>',
        '        <keyMapSelect mapIndex="2"><modifier keys="caps"/></keyMapSelect>',
        (
            '        <keyMapSelect mapIndex="3"><modifier '
            'keys="anyShift? caps? anyOption? command"/></keyMapSelect>'
        ),
        '        <keyMapSelect mapIndex="4"><modifier keys="caps? anyOption"/></keyMapSelect>',
        (
            '        <keyMapSelect mapIndex="5"><modifier '
            'keys="anyShift caps? anyOption"/></keyMapSelect>'
        ),
        '        <keyMapSelect mapIndex="6">',
        '            <modifier keys="anyShift caps? option? command? control"/>',
        '            <modifier keys="shift? caps? anyOption command? control"/>',
        '            <modifier keys="caps? anyOption? command? control"/>',
        '        </keyMapSelect>',
        "    </modifierMap>",
        '    <keyMapSet id="nepa">',
    ]
    for index, values in enumerate(ordered):
        lines.extend(render_key_map(index, values))
    lines.extend(("    </keyMapSet>", "</keyboard>", ""))
    return "\n".join(lines)


def validate_spec(spec: dict[str, Any]) -> None:
    if spec.get("format_version") != 1:
        raise BuildError("format_version must be 1")
    bundle = spec.get("bundle")
    if not isinstance(bundle, dict):
        raise BuildError("bundle must be an object")
    for field in ("identifier", "name", "version", "build"):
        if not isinstance(bundle.get(field), str) or not bundle[field]:
            raise BuildError(f"bundle.{field} must be a non-empty string")
    profiles = spec.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != 3:
        raise BuildError("the v1 desktop bundle must contain exactly three profiles")
    seen: dict[str, set[Any]] = {field: set() for field in ("profile_id", "name", "slug", "keyboard_id")}
    for profile in profiles:
        if not isinstance(profile, dict):
            raise BuildError("each profile must be an object")
        for field in seen:
            value = profile.get(field)
            if value in seen[field]:
                raise BuildError(f"duplicate profile {field}: {value}")
            seen[field].add(value)
        if profile.get("source_script") != "Latn":
            raise BuildError(f"{profile['profile_id']} source_script must be Latn")
        if profile.get("output_script") not in SCRIPT_RANGES:
            raise BuildError(f"{profile['profile_id']} has unsupported output_script")
        if not isinstance(profile.get("language_tag"), str) or not profile["language_tag"]:
            raise BuildError(f"{profile['profile_id']} language_tag is required")
        provenance = profile.get("provenance")
        if not isinstance(provenance, list) or not provenance:
            raise BuildError(f"{profile['profile_id']} provenance is required")
        for source in provenance:
            if not isinstance(source, dict):
                raise BuildError(f"{profile['profile_id']} provenance rows must be objects")
            digest = source.get("sha256")
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise BuildError(f"{profile['profile_id']} has an invalid provenance SHA-256")
            if source.get("kind") == "project_binding":
                relative = source.get("source")
                if not isinstance(relative, str) or not relative:
                    raise BuildError(f"{profile['profile_id']} project binding path is required")
                bound_path = ROOT / relative
                if not bound_path.is_file():
                    raise BuildError(f"{profile['profile_id']} project binding is missing: {relative}")
                actual = sha256_bytes(bound_path.read_bytes())
                if actual != digest:
                    raise BuildError(
                        f"{profile['profile_id']} project binding SHA-256 mismatch: {relative}"
                    )
        resolve_layers(profile)


def plist_bytes(value: dict[str, Any]) -> bytes:
    return plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=True)


def build_tree(spec_path: Path, destination: Path) -> None:
    spec_bytes = spec_path.read_bytes()
    spec = read_json(spec_path)
    validate_spec(spec)
    bundle_meta = spec["bundle"]
    bundle_name = f'{bundle_meta["name"]}.bundle'
    bundle = destination / bundle_name
    contents = bundle / "Contents"
    resources = contents / "Resources"
    resources.mkdir(parents=True)

    info: dict[str, Any] = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleIdentifier": bundle_meta["identifier"],
        "CFBundleName": bundle_meta["name"],
        "CFBundlePackageType": "BNDL",
        "CFBundleShortVersionString": bundle_meta["version"],
        "CFBundleVersion": bundle_meta["build"],
    }
    localized_names: list[str] = []
    for profile in spec["profiles"]:
        name = profile["name"]
        info[f"KLInfo_{name}"] = {
            "TICapsLockLanguageSwitchCapable": False,
            "TISInputSourceID": f'{bundle_meta["identifier"]}.{profile["slug"]}',
            "TISIntendedLanguage": profile["language_tag"],
        }
        localized_names.append(f'"{name}" = "{name}";')
        (resources / f"{name}.keylayout").write_text(
            render_keylayout(profile), encoding="utf-8", newline="\n"
        )

    (contents / "Info.plist").write_bytes(plist_bytes(info))
    (contents / "version.plist").write_bytes(
        plist_bytes(
            {
                "BuildVersion": bundle_meta["build"],
                "ProjectName": bundle_meta["name"],
                "SourceVersion": bundle_meta["version"],
            }
        )
    )
    localization = resources / "en.lproj"
    localization.mkdir()
    (localization / "InfoPlist.strings").write_text(
        "\n".join(localized_names) + "\n", encoding="utf-8", newline="\n"
    )

    generated_files = sorted(path for path in bundle.rglob("*") if path.is_file())
    manifest = {
        "format_version": 1,
        "bundle": bundle_name,
        "bundle_identifier": bundle_meta["identifier"],
        "bundle_version": bundle_meta["version"],
        "profile_ids": [profile["profile_id"] for profile in spec["profiles"]],
        "spec_path": spec_path.relative_to(ROOT).as_posix(),
        "spec_sha256": sha256_bytes(spec_bytes),
        "files": [
            {
                "path": path.relative_to(destination).as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
                "size": path.stat().st_size,
            }
            for path in generated_files
        ],
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def tree_snapshot(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def materialize(spec_path: Path, output: Path, check: bool) -> None:
    output_parent = output.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = Path(tempfile.mkdtemp(prefix="nepa-macos-bundle-", dir=output_parent))
    candidate = temporary_parent / "generated"
    candidate.mkdir()
    try:
        build_tree(spec_path, candidate)
        if check:
            expected = tree_snapshot(output)
            actual = tree_snapshot(candidate)
            if expected != actual:
                missing = sorted(set(actual) - set(expected))
                extra = sorted(set(expected) - set(actual))
                changed = sorted(
                    path for path in set(actual) & set(expected) if actual[path] != expected[path]
                )
                raise BuildError(
                    "generated macOS bundle is stale: "
                    f"missing={missing}, extra={extra}, changed={changed}"
                )
            return
        if output.exists():
            shutil.rmtree(output)
        os.replace(candidate, output)
    finally:
        shutil.rmtree(temporary_parent, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    materialize(args.spec.resolve(), args.output.resolve(), args.check)
    mode = "verified" if args.check else "built"
    print(f"macOS Romanized Pro bundle {mode}: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
