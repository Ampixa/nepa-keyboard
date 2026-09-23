#!/usr/bin/env python3
"""Compile reviewed Roman-to-script transliteration maps into deterministic assets.

Nepal's minority-language scripts are abugidas: a consonant carries an inherent vowel,
other vowels attach as signs, and a bare consonant needs an explicit virama. Plain
codepoint substitution cannot express that, so this compiler assembles syllables.

Every target character is declared by its Unicode name rather than a literal, so the
source is auditable against the Unicode database and a typo becomes a build failure
instead of a silently wrong letter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

SOURCE_FORMAT = "nepa-transliteration-map-source"
SOURCE_FORMAT_VERSION = 1
ASSET_VERSION = 1
NORMALIZATION = "NFC"
ALGORITHM = "greedy-syllable-v1"
UNICODE_DATA_VERSION = "16.0.0"

SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "Deva": ((0x0900, 0x097F), (0xA8E0, 0xA8FF)),
    "Lepc": ((0x1C00, 0x1C4F),),
    "Limb": ((0x1900, 0x194F),),
    "Newa": ((0x11400, 0x1147F),),
    "Tirh": ((0x11480, 0x114DF),),
}
# Roman input is restricted so a map can never emit through unreviewed keys.
# ":" marks vowel length, the convention descriptive grammars of these
# languages already use. A phonemic contrast needs a key of its own, and
# doubling the vowel is unavailable where the doubled form already means an
# explicit vowel sign rather than a long one.
ROMAN_ALPHABET = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:")
# How a consonant at the very end of the input is rendered.
FINAL_CONSONANT_POLICIES = {"inherent", "virama", "final_form"}
MAX_ROMAN_KEY = 8
MAX_OUTPUT_SCALARS = 12
MAX_RULES = 4096


class TransliterationError(ValueError):
    """Raised when a source cannot safely produce a transliteration asset."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TransliterationError(message)


def _resolve(
    names: list[str],
    location: str,
    script: str,
    *,
    allow_empty: bool = False,
) -> str:
    """Resolve a list of Unicode names to a string, checked against the script block."""
    if not names:
        # Only the inherent vowel legitimately renders nothing after a consonant.
        _require(allow_empty, f"{location} must name at least one character")
        return ""
    _require(
        len(names) <= MAX_OUTPUT_SCALARS,
        f"{location} exceeds {MAX_OUTPUT_SCALARS} characters",
    )
    resolved = []
    ranges = SCRIPT_RANGES[script]
    for index, name in enumerate(names):
        entry_location = f"{location}[{index}]"
        _require(isinstance(name, str) and bool(name.strip()), f"{entry_location} must be a name")
        try:
            character = unicodedata.lookup(name)
        except KeyError as unknown:
            raise TransliterationError(f"{entry_location} is not a Unicode name: {name}") from unknown
        codepoint = ord(character)
        # Joiners are script-neutral and legitimately used for conjunct control.
        if codepoint not in (0x200C, 0x200D):
            _require(
                any(start <= codepoint <= end for start, end in ranges),
                f"{entry_location} U+{codepoint:04X} is outside the {script} block",
            )
        resolved.append(character)
    text = "".join(resolved)
    _require(
        unicodedata.normalize(NORMALIZATION, text) == text,
        f"{location} must already be {NORMALIZATION}",
    )
    return text


def _validate_roman(key: str, location: str, *, allow_empty: bool = False) -> None:
    if not key and allow_empty:
        return
    _require(isinstance(key, str) and bool(key), f"{location} must be a non-empty string")
    _require(len(key) <= MAX_ROMAN_KEY, f"{location} exceeds {MAX_ROMAN_KEY} characters")
    unsupported = sorted(set(key) - ROMAN_ALPHABET)
    _require(not unsupported, f"{location} uses unsupported input {unsupported}")


def _build_section(
    source: dict[str, Any],
    field: str,
    script: str,
    *,
    required: bool = True,
    allow_empty: bool = False,
) -> dict[str, str]:
    raw = source.get(field)
    if raw is None:
        _require(not required, f"{field} is required")
        return {}
    _require(isinstance(raw, dict), f"{field} must be an object")
    resolved: dict[str, str] = {}
    for key, names in raw.items():
        location = f"{field}.{key}"
        _validate_roman(key, location)
        resolved[key] = _resolve(names, location, script, allow_empty=allow_empty)
    return resolved


def _verify_contrasts(source: dict[str, Any], asset: dict[str, Any]) -> None:
    """Prove the map can still express the distinctions the language needs.

    A map can spell every golden vector correctly and still be unable to write a
    phonemic contrast at all, which silently merges distinct words. Vectors do not
    catch that; these two checks do, and they run inside the builder so no caller
    can obtain an asset that has skipped them.
    """
    emitted: set[str] = set()
    for section in (
        "consonants", "independent_vowels", "vowel_signs",
        "standalone", "final_forms", "words",
    ):
        for value in asset.get(section, {}).values():
            emitted.update(value)
    emitted.update(asset.get("virama", ""))

    for index, name in enumerate(source.get("required_characters", [])):
        location = f"required_characters[{index}]"
        _require(isinstance(name, str) and bool(name), f"{location} must be a name")
        try:
            character = unicodedata.lookup(name)
        except KeyError as unknown:
            raise TransliterationError(f"{location} is not a Unicode name: {name}") from unknown
        _require(
            character in emitted,
            f"{name} is declared phonemically contrastive but no rule emits it",
        )

    for index, contrast in enumerate(source.get("contrasts", [])):
        location = f"contrasts[{index}]"
        _require(
            isinstance(contrast, dict) and set(contrast) == {"feature", "pair", "gloss"},
            f"{location} fields must be exactly feature, gloss and pair",
        )
        pair = contrast["pair"]
        _require(
            isinstance(pair, list) and len(pair) == 2 and all(isinstance(x, str) for x in pair),
            f"{location}.pair must hold exactly two Roman inputs",
        )
        left, right = (transliterate(asset, side) for side in pair)
        _require(
            left != right,
            f"{location} ({contrast['feature']}) collapses: "
            f"{pair[0]!r} and {pair[1]!r} both render {left!r}",
        )


def build_asset(source_path: Path) -> dict[str, Any]:
    raw = source_path.read_bytes()
    _require(not raw.startswith(b"\xef\xbb\xbf"), "source must not contain a BOM")
    source = json.loads(raw.decode("utf-8"))
    _require(isinstance(source, dict), "source must be a JSON object")
    _require(
        source.get("source_format") == SOURCE_FORMAT
        and source.get("source_format_version") == SOURCE_FORMAT_VERSION,
        "source declares an unsupported format",
    )
    _require(
        unicodedata.unidata_version == UNICODE_DATA_VERSION,
        f"compiler Unicode database must be {UNICODE_DATA_VERSION}, "
        f"got {unicodedata.unidata_version}",
    )
    script = source["output_script"]
    _require(script in SCRIPT_RANGES, f"unsupported output script: {script}")
    _require(source.get("source_script") == "Latn", "source_script must be Latn")

    consonants = _build_section(source, "consonants", script)
    independent_vowels = _build_section(source, "independent_vowels", script)
    vowel_signs = _build_section(source, "vowel_signs", script, allow_empty=True)
    standalone = _build_section(source, "standalone", script, required=False)
    final_forms = _build_section(source, "final_forms", script, required=False)
    words = _build_section(source, "words", script, required=False)

    virama = _resolve(source["virama"], "virama", script, allow_empty=True)
    final_policy = source["final_consonant"]
    _require(
        final_policy in FINAL_CONSONANT_POLICIES,
        f"final_consonant must be one of {sorted(FINAL_CONSONANT_POLICIES)}",
    )
    if final_policy == "final_form":
        # Scripts without a virama mark a coda with a dedicated letter, so every
        # consonant that may close a syllable needs one declared.
        _require(
            bool(final_forms),
            "final_consonant final_form requires a final_forms table",
        )
        unknown = sorted(set(final_forms) - set(consonants))
        _require(not unknown, f"final_forms names undeclared consonants: {unknown}")
    explicit_virama = source["explicit_virama"]
    _validate_roman(explicit_virama, "explicit_virama", allow_empty=True)
    if final_policy == "final_form":
        # This script has no virama, so neither a virama character nor a key that
        # would request one may be declared.
        _require(not virama, "final_form maps must not declare a virama")
        _require(
            not explicit_virama,
            "final_form maps must not declare an explicit virama key",
        )
    else:
        _require(bool(virama), "a virama is required unless the policy is final_form")
    _require(
        explicit_virama not in consonants
        and explicit_virama not in independent_vowels
        and explicit_virama not in standalone,
        "explicit_virama must not collide with another rule",
    )
    inherent = source["inherent_vowel"]
    _validate_roman(inherent, "inherent_vowel")
    _require(
        inherent in vowel_signs or inherent in independent_vowels,
        "inherent_vowel must be a declared vowel",
    )
    _require(
        vowel_signs.get(inherent, "") == "",
        "inherent_vowel must map to an empty vowel sign",
    )

    # Every vowel that can follow a consonant needs a sign, and every sign needs an
    # independent form, or the engine could not render the vowel in both positions.
    missing_independent = sorted(set(vowel_signs) - set(independent_vowels))
    _require(
        not missing_independent,
        f"vowel signs without an independent form: {missing_independent}",
    )

    total = (
        len(final_forms)
        + len(consonants)
        + len(independent_vowels)
        + len(vowel_signs)
        + len(standalone)
        + len(words)
    )
    _require(0 < total <= MAX_RULES, f"rule count must be 1 to {MAX_RULES}")

    asset = {
        "asset_version": ASSET_VERSION,
        "generator": "build_transliteration_map",
        "map_id": source["map_id"],
        "language": source["language"],
        "source_script": "Latn",
        "output_script": script,
        "normalization": NORMALIZATION,
        "algorithm": ALGORITHM,
        "unicode_data_version": UNICODE_DATA_VERSION,
        "inherent_vowel": inherent,
        "virama": virama,
        "final_consonant": final_policy,
        "explicit_virama": explicit_virama,
        "consonants": dict(sorted(consonants.items())),
        "independent_vowels": dict(sorted(independent_vowels.items())),
        "vowel_signs": dict(sorted(vowel_signs.items())),
        "standalone": dict(sorted(standalone.items())),
        "final_forms": dict(sorted(final_forms.items())),
        "words": dict(sorted(words.items())),
        "rule_count": total,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }
    _verify_contrasts(source, asset)
    return asset


def transliterate(asset: dict[str, Any], text: str) -> str:
    """Greedy syllable assembly. Mirrors the runtime engine exactly."""
    consonants = asset["consonants"]
    independent = asset["independent_vowels"]
    signs = asset["vowel_signs"]
    standalone = asset["standalone"]
    words = asset["words"]
    virama = asset["virama"]
    final_policy = asset["final_consonant"]
    explicit_virama = asset["explicit_virama"]
    final_forms = asset.get("final_forms", {})

    if text in words:
        return words[text]

    def longest(table: dict[str, str], position: int) -> tuple[str, str] | None:
        for length in range(min(MAX_ROMAN_KEY, len(text) - position), 0, -1):
            candidate = text[position : position + length]
            if candidate in table:
                return candidate, table[candidate]
        return None

    output: list[str] = []
    position = 0
    while position < len(text):
        consonant = longest(consonants, position)
        if consonant is not None:
            key, value = consonant
            after = position + len(key)
            closing = (
                final_policy == "final_form"
                and key in final_forms
                and longest(signs, after) is None
            )
            # A coda consonant takes its dedicated final letter rather than the
            # full form, which is how this script closes a syllable.
            output.append(final_forms[key] if closing else value)
            position = after
            if closing:
                continue
            vowel = longest(signs, position)
            if vowel is not None:
                vowel_key, vowel_value = vowel
                output.append(vowel_value)
                position += len(vowel_key)
            elif explicit_virama and text.startswith(explicit_virama, position):
                # The writer asked for a dead consonant explicitly.
                output.append(virama)
                position += len(explicit_virama)
            elif final_policy == "final_form":
                # No virama exists in this script. A consonant with no coda form and
                # no vowel keeps its full letter and its inherent vowel.
                pass
            elif position >= len(text) and final_policy == "inherent":
                # A word-final consonant carries its inherent vowel, which is how
                # these scripts are actually written. An explicit dead consonant is
                # still reachable through the declared virama key.
                pass
            else:
                output.append(virama)
            continue
        vowel = longest(independent, position)
        if vowel is not None:
            key, value = vowel
            output.append(value)
            position += len(key)
            continue
        other = longest(standalone, position)
        if other is not None:
            key, value = other
            output.append(value)
            position += len(key)
            continue
        # Unmapped input passes through so the writer never loses characters.
        output.append(text[position])
        position += 1
    result = "".join(output)
    return unicodedata.normalize(NORMALIZATION, result)


def canonical_bytes(asset: dict[str, Any]) -> bytes:
    return (json.dumps(asset, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    source_path = args.source.resolve()
    asset = build_asset(source_path)

    # Golden vectors travel with the source and are proven before the asset is written.
    source = json.loads(source_path.read_bytes().decode("utf-8"))
    for index, vector in enumerate(source.get("vectors", [])):
        produced = transliterate(asset, vector["input"])
        _require(
            produced == vector["output"],
            f"vector[{index}] {vector['input']!r}: expected {vector['output']!r}, got {produced!r}",
        )

    payload = canonical_bytes(asset)
    if args.check:
        _require(args.output.is_file(), f"missing asset: {args.output}")
        _require(args.output.read_bytes() == payload, "asset does not match its source")
        print(f"transliteration_check=ok map={asset['map_id']} rules={asset['rule_count']}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"transliteration_map={asset['map_id']}")
    print(f"transliteration_rules={asset['rule_count']}")
    print(f"transliteration_vectors={len(source.get('vectors', []))}")
    print(f"transliteration_sha256={hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TransliterationError as failure:
        print(f"error: {failure}", file=sys.stderr)
        sys.exit(2)
