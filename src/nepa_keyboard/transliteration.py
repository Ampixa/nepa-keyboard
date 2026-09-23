"""Dependency-free Roman-to-script transliteration shared by desktop IMEs.

The implementation deliberately mirrors Android's ``TransliterationEngine``.
Keeping the algorithm here, rather than in each platform adapter, gives Linux
and Windows the same composition behavior and provides golden vectors for the
independent native macOS implementation.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any, Mapping


MAX_ROMAN_KEY = 8
SUPPORTED_ALGORITHM = "greedy-syllable-v1"


class TransliterationMapError(ValueError):
    """Raised when a generated transliteration map is malformed."""


def _string_table(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TransliterationMapError(f"{field} must be an object")
    result: dict[str, str] = {}
    for key, output in value.items():
        if not isinstance(key, str) or not key or len(key) > MAX_ROMAN_KEY:
            raise TransliterationMapError(
                f"{field} keys must be non-empty strings of at most {MAX_ROMAN_KEY} characters"
            )
        if not isinstance(output, str):
            raise TransliterationMapError(f"{field}[{key!r}] must be a string")
        result[key] = output
    return result


class TransliterationEngine:
    """Greedy syllable transliterator loaded from one generated JSON map."""

    def __init__(self, asset: Mapping[str, Any]):
        if asset.get("algorithm") != SUPPORTED_ALGORITHM:
            raise TransliterationMapError(
                f"algorithm must be {SUPPORTED_ALGORITHM!r}"
            )
        self.map_id = self._required_string(asset, "map_id")
        self.language = self._required_string(asset, "language")
        self.output_script = self._required_string(asset, "output_script")
        self.consonants = _string_table(asset.get("consonants"), "consonants")
        self.independent_vowels = _string_table(
            asset.get("independent_vowels"), "independent_vowels"
        )
        self.vowel_signs = _string_table(asset.get("vowel_signs"), "vowel_signs")
        self.standalone = _string_table(asset.get("standalone"), "standalone")
        self.final_forms = _string_table(asset.get("final_forms"), "final_forms")
        self.words = _string_table(asset.get("words"), "words")
        self.virama = self._string(asset, "virama")
        self.explicit_virama = self._string(asset, "explicit_virama")
        self.final_consonant = self._required_string(asset, "final_consonant")
        if self.final_consonant not in {"inherent", "virama", "final_form"}:
            raise TransliterationMapError(
                "final_consonant must be inherent, virama, or final_form"
            )
        if self.final_consonant == "final_form":
            if self.virama or self.explicit_virama or not self.final_forms:
                raise TransliterationMapError(
                    "final_form maps need coda letters and must not declare a virama"
                )
        elif not self.virama:
            raise TransliterationMapError("a virama is required for this map")

    @classmethod
    def from_path(cls, path: Path) -> "TransliterationEngine":
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TransliterationMapError(f"cannot read map {path}: {error}") from error
        if not isinstance(value, dict):
            raise TransliterationMapError("map root must be an object")
        return cls(value)

    @staticmethod
    def _required_string(asset: Mapping[str, Any], field: str) -> str:
        value = asset.get(field)
        if not isinstance(value, str) or not value:
            raise TransliterationMapError(f"{field} must be a non-empty string")
        return value

    @staticmethod
    def _string(asset: Mapping[str, Any], field: str) -> str:
        value = asset.get(field)
        if not isinstance(value, str):
            raise TransliterationMapError(f"{field} must be a string")
        return value

    @staticmethod
    def _longest(table: Mapping[str, str], text: str, position: int) -> str | None:
        limit = min(MAX_ROMAN_KEY, len(text) - position)
        for length in range(limit, 0, -1):
            candidate = text[position : position + length]
            if candidate in table:
                return candidate
        return None

    def transliterate(self, text: str) -> str:
        """Transliterate a complete Roman token without dropping unknown input."""

        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not text:
            return ""
        whole = self.words.get(text)
        if whole is not None:
            return whole

        output: list[str] = []
        position = 0
        while position < len(text):
            consonant_key = self._longest(self.consonants, text, position)
            if consonant_key is not None:
                after = position + len(consonant_key)
                coda = self.final_forms.get(consonant_key)
                closing = (
                    self.final_consonant == "final_form"
                    and coda is not None
                    and self._longest(self.vowel_signs, text, after) is None
                )
                output.append(coda if closing else self.consonants[consonant_key])
                position = after
                if closing:
                    continue
                vowel_key = self._longest(self.vowel_signs, text, position)
                if vowel_key is not None:
                    output.append(self.vowel_signs[vowel_key])
                    position += len(vowel_key)
                elif self.explicit_virama and text.startswith(
                    self.explicit_virama, position
                ):
                    output.append(self.virama)
                    position += len(self.explicit_virama)
                elif self.final_consonant == "final_form":
                    continue
                elif position >= len(text) and self.final_consonant == "inherent":
                    continue
                else:
                    output.append(self.virama)
                continue

            vowel_key = self._longest(self.independent_vowels, text, position)
            if vowel_key is not None:
                output.append(self.independent_vowels[vowel_key])
                position += len(vowel_key)
                continue
            standalone_key = self._longest(self.standalone, text, position)
            if standalone_key is not None:
                output.append(self.standalone[standalone_key])
                position += len(standalone_key)
                continue
            output.append(text[position])
            position += 1
        return unicodedata.normalize("NFC", "".join(output))

