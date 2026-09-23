#!/usr/bin/env python3
"""Create a bounded Nepali v0 build directory from the audited frequency TSV.

This adapter is intentionally separate from the compiler. It converts one
source's conventions into canonical forms and aliases; the compiler remains
language-independent.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


DEV_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "w",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}

DEV_INDEPENDENT_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}

DEV_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu",
    "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
}

HALANT = "्"
ANUSVARA = "ं"
CHANDRABINDU = "ँ"
VISARGA = "ः"
NUKTA = "़"


def devanagari_to_roman_key(word: str) -> str:
    """Reverse-key generator matching the audited Nepali serving seed."""
    output: list[str] = []
    characters = list(word)
    for index, character in enumerate(characters):
        if character in DEV_CONSONANTS:
            output.append(DEV_CONSONANTS[character])
            following = characters[index + 1] if index + 1 < len(characters) else ""
            if following not in DEV_MATRAS and following != HALANT:
                output.append("a")
        elif character in DEV_MATRAS:
            output.append(DEV_MATRAS[character])
        elif character in DEV_INDEPENDENT_VOWELS:
            output.append(DEV_INDEPENDENT_VOWELS[character])
        elif character in (ANUSVARA, CHANDRABINDU):
            output.append("n")
        elif character == VISARGA:
            output.append("h")
        elif character in (HALANT, NUKTA, "‌", "‍"):
            continue
        else:
            return ""
    return "".join(output)


def fold_roman(roman: str) -> str:
    """Create the permissive lookup key used by the current Nepali seed."""
    result = roman.lower()
    for source, target in (
        ("chh", "c"), ("ch", "c"),
        ("kh", "k"), ("gh", "g"), ("jh", "j"),
        ("th", "t"), ("dh", "d"), ("bh", "b"), ("ph", "f"),
        ("sh", "s"),
        ("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"),
        ("w", "b"), ("v", "b"), ("z", "j"),
    ):
        result = result.replace(source, target)
    return result[:-1] if result.endswith("a") and len(result) > 2 else result


def stable_form_id(surface: str) -> str:
    digest = hashlib.sha256(("npi\0" + surface).encode("utf-8")).hexdigest()[:20]
    return f"npi:{digest}"


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def build_source(args: argparse.Namespace) -> dict[str, int]:
    args.output.mkdir(parents=True, exist_ok=True)
    forms: list[dict[str, object]] = []
    aliases: list[dict[str, object]] = []
    seen_surfaces: set[str] = set()
    skipped = 0

    with args.word_frequency.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            if len(forms) >= args.limit:
                break
            surface = row.get("token", "")
            try:
                count = int(row.get("count", ""))
            except ValueError:
                skipped += 1
                continue
            if count < args.min_count or surface in seen_surfaces or any(char.isspace() for char in surface):
                skipped += 1
                continue
            roman = devanagari_to_roman_key(surface)
            if not roman:
                skipped += 1
                continue

            form_id = stable_form_id(surface)
            rank_score = round(1000 * math.log1p(count))
            forms.append({
                "form_id": form_id,
                "surface": surface,
                "rank_score": rank_score,
                "source_ids": ["npi-word-frequency"],
                "evidence": "attested",
            })
            seen_surfaces.add(surface)

            alias_variants = [(roman, "reverse_roman_full", 0)]
            folded = fold_roman(roman)
            if folded and folded != roman:
                alias_variants.append((folded, "reverse_roman_folded", -150))
            for alias, scheme, rank_delta in alias_variants:
                aliases.append({
                    "alias": alias,
                    "form_id": form_id,
                    "rank_delta": rank_delta,
                    "scheme": scheme,
                    "source_ids": ["npi-word-frequency"],
                    "evidence": "generated",
                })

    pack = {
        "pack_id": "npi-Deva-NP",
        "language": "npi",
        "display_name": "Nepali",
        "variety": None,
        "output_script": "Deva",
        "region": "NP",
        "data_version": args.data_version,
        "max_suggestions": args.max_suggestions,
    }
    source = {
        "source_id": "npi-word-frequency",
        "title": "Nepali frontend word frequency",
        "path": args.provenance_path or str(args.word_frequency),
        "method": "attested_frequency_extraction",
        "license": args.license,
        "redistribution": args.redistribution,
        "domains": ["mixed_web", "general"],
        "notes": "Roman aliases are generated by the audited Nepali reverse-key seed and remain generated evidence.",
    }

    (args.output / "pack.json").write_text(canonical_json(pack) + "\n", encoding="utf-8")
    write_jsonl(args.output / "sources.jsonl", [source])
    write_jsonl(args.output / "forms.jsonl", forms)
    write_jsonl(args.output / "aliases.jsonl", aliases)
    summary = {
        "forms": len(forms),
        "alias_rows": len(aliases),
        "skipped_rows_before_limit": skipped,
    }
    (args.output / "adapter-summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--word-frequency", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=25000)
    parser.add_argument("--min-count", type=int, default=2)
    parser.add_argument("--data-version", default="0.1.0")
    parser.add_argument("--max-suggestions", type=int, default=8)
    parser.add_argument("--license", default="unknown")
    parser.add_argument(
        "--redistribution",
        choices=("allowed", "system", "prohibited", "permission_required", "unknown"),
        default="unknown",
    )
    parser.add_argument("--provenance-path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be positive")
    summary = build_source(args)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
