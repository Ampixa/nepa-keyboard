# Nepal Bhasa Devanagari-to-Prachalit conversion review v1

Date: 2026-07-21

This is a community review sheet for the internal `new-Deva-Newa-NP` beta.
The method lets a person type Nepal Bhasa in Devanagari and offers a generated
Unicode Newa candidate, labeled **Prachalit Nepal Lipi** in the keyboard. It is
separate from both the direct Prachalit keyboard and the Romanized Nepal Bhasa
keyboard.

The converter is deliberately mechanical. It applies a frozen Unicode mapping
to the complete composing token and returns no conversion if any character is
unsupported. Its output is therefore not evidence that a spelling is natural,
modern, or preferred by Nepal Bhasa writers.

## What to try

Please type the Devanagari text in the left column and inspect the first
generated candidate. Keep the original Devanagari candidate available for
comparison.

| Devanagari input | Generated Newa output | What it exercises |
| --- | --- | --- |
| `अँ` | `𑐀𑑃` | independent vowel and candrabindu |
| `मदु` | `𑐩𑐡𑐸` | common letters and dependent vowel |
| `नेपालभाषा` | `𑐣𑐾𑐥𑐵𑐮𑐨𑐵𑐲𑐵` | longer complete token |
| `क्‍ष` | `𑐎𑑂‍𑐲` | virama plus ZWJ |
| `क्‌ष` | `𑐎𑑂‌𑐲` | virama plus ZWNJ |
| `न्ह` | `𑐣𑑂𑐴` | intentionally uncontracted murmured-letter sequence |
| `कॅ` | no conversion | unsupported Devanagari candra-E mark |
| `क॒थं` | no conversion | unsupported Vedic stress mark |

The last two rows are intentional no-match cases. The beta does not guess a
visually similar Newa character for U+0945, U+0949, U+0951, or U+0952.

## Decisions we need from native writers

1. Are the ordinary letter, vowel-sign, numeral, and punctuation mappings
   orthographically acceptable for present-day Nepal Bhasa?
2. Should a sequence such as `न्ह` remain `𑐣𑑂𑐴`, or should any reviewed
   Devanagari sequences produce an atomic Newa murmured letter such as `𑐤`?
   Please give real word examples for every proposed contraction.
3. Do the ZWJ and ZWNJ examples produce the intended conjunct forms in the
   editors and fonts you actually use?
4. Should the four currently unsupported marks always cause no conversion, or
   is there a documented Newa equivalent for a specific use?
5. Is showing the generated Newa form first and the literal Devanagari form
   second understandable, or should the ordering or labels change?
6. Is **Prachalit Nepal Lipi** the clearest community-facing label for the
   Unicode Newa output in this context?

## Feedback template

```text
Device and Android version:
App or editor:
Font, if known:
Devanagari input:
Generated Newa output shown:
Expected Newa spelling:
Is this a mapping, spelling, shaping, or keyboard-label problem?
Should the converter return no match instead?
Notes or source reference:
```

Screenshots are useful for shaping problems, but please also copy the actual
Unicode text so that a font problem is not mistaken for a mapping problem.

## Exact engineering boundary

The v1 map has 165 rules: 91 direct mappings and 74 virama/joiner-preserving
mappings. Against the measured 5,417-surface Devanagari inventory it converts
5,390 surfaces (99.501569%) and rejects 27. Murmured-letter contraction is
disabled pending this review.

The compiled `new-Deva-Newa-NP.ncm` artifact is 5,859 bytes with SHA-256
`29c88708b3d7aeb741779b7a7464efcb2464e060d7939c7998533d50b11a2d05`.
The exact [source report](../../reports/nepal-bhasa-deva-newa-internal-map-v0.json),
[validation vectors](../../catalog/nepal-bhasa-deva-newa-internal-vectors-v0.json),
and [authored source](../../converters/internal/src/new-deva-newa-v1.json) are
available for technical review.

This method emits Unicode Newa characters for the project's Prachalit Nepal
Lipi lane. It does not emit Ranjana and must not be used as evidence that
Ranjana and Prachalit are the same script.
