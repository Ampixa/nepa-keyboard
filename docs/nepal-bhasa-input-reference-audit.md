# Nepal Bhasa input reference audit

Nepal Bhasa remains four separate keyboard products. Direct Devanagari,
direct Newa/Prachalit input, Latin-to-Devanagari aliases, and
Devanagari-to-Newa conversion have separate artifacts and evidence and must
not share promotion claims.

## Current implementation status

This document began as a pre-implementation reference audit. The repository
now contains evidence-backed internal implementations for all four products:

| Product | Implemented boundary | Primary evidence |
| --- | --- | --- |
| `new-Deva-NP` | Direct Devanagari layout and 5,417-surface pack | [internal Android milestone](../reports/nepal-bhasa-internal-android-milestone-v0.md) |
| `new-Newa-NP` | Direct Unicode Newa layout and 2,318 attested Newa-script surfaces | [Prachalit/Newa milestone](../reports/nepal-bhasa-newa-internal-android-milestone-v0.md) and [pack report](../reports/nepal-bhasa-newa-internal-pack-v0.json) |
| `new-Latn-Deva-NP` | Roman alias lookup into the direct Devanagari pack | [Roman milestone](../reports/nepal-bhasa-roman-internal-android-milestone-v0.md) and [pack report](../reports/nepal-bhasa-roman-internal-pack-v0.json) |
| `new-Deva-Newa-NP` | Frozen Devanagari-to-Unicode-Newa mechanical conversion map and strict runtime | [map report](../reports/nepal-bhasa-deva-newa-internal-map-v0.json), [vectors](../catalog/nepal-bhasa-deva-newa-internal-vectors-v0.json), and [source](../converters/internal/src/new-deva-newa-v1.json) |

All four methods are now selectable, non-default internal engineering profiles.
The generated
[`catalog/internal-profiles.lock.json`](../catalog/internal-profiles.lock.json)
contains 12 selectable profiles: 11 NKP bindings backed by 10 unique packs and
one NCM converter. The completed relock, clean build, 15-vector replay, and
canonical API 34 result are recorded in the
[converter Android milestone](../reports/nepal-bhasa-deva-newa-internal-android-milestone-v0.md).

## Terminology boundary

The project uses **Newa** for the Unicode script identity and scalar block
U+11400–U+1147F. It uses **Prachalit Nepal Lipi** as the user-facing label for
the direct Nepal Bhasa writing method represented with those Unicode Newa
characters. **Nepal Bhasa** (also labeled “Newari” by some external products)
is the language identity, not a script name. These labels do not authorize
substituting another script.

In particular, **Ranjana is not a synonym for Unicode Newa/Prachalit in this
product**. None of the current
[`newa-nepal-prachalit-v1` layout](../layouts/internal/src/newa-nepal-prachalit-v1.json),
[`new-Newa-NP` pack evidence](../reports/nepal-bhasa-newa-internal-pack-v0.json),
or [Devanagari-to-Newa map](../reports/nepal-bhasa-deva-newa-internal-map-v0.json)
claims or emits Ranjana. Any future Ranjana input or output requires a distinct
script identity, repertoire, layout, data source, review, and runtime evidence.

## Direct Newa references

Direct Newa input is implemented as an internal beta, but there is no
CLDR-standard Newa keyboard and no native acceptance claim. The implementation
triangulates these references rather than treating one layout as normative:

- [Unicode 16 Newa
  chapter](https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-13/#G27503)
  defines the U+11400–U+1147F script, conjunct behavior, virama, repha, and
  VIRAMA+ZWJ half/eyelash RA behavior.
- [Unicode Newa encoding proposal](https://www.unicode.org/L2/L2014/14285r-newa.pdf#page=12)
  records a community-reviewed modern Nepal Bhasa repertoire. It is the best
  starting point for separating everyday keys from Sanskrit and historic
  long-press or symbol-layer characters.
- [Keyman Newa Traditional](https://keyman.com/keyboards/newa_traditional),
  [Newa Romanized](https://keyman.com/keyboards/newa_romanized), and
  [Traditional Extended](https://keyman.com/keyboards/newa_traditional_extended)
  are working Unicode implementations with mobile layers and conjunct input.
- FUTO publishes Android-native QWERTY-positioned direct and traditional
  definitions in its
  [Newa layout directory](https://github.com/futo-org/futo-keyboard-layouts/tree/main/Newa).
  Their
  [merged implementation](https://github.com/futo-org/futo-keyboard-layouts/pull/159)
  is a useful Android reference.
- The [CLDR keyboard tree](https://github.com/unicode-org/cldr/tree/main/keyboards/3.0)
  currently contains no Newa definition.
- Gboard lists Newari in its
  [supported-language documentation](https://support.google.com/gboard/answer/6380730?hl=en-GB),
  but does not publicly identify the subtype's output script or layout. A
  current installed Gboard subtype must be inspected before making parity
  claims.

The reference called “Newa Romanized” is a direct keyboard: Latin QWERTY key
positions emit Newa scalars. It is not a decoder that accepts Latin words.
To prevent that ambiguity, the two declarative layout candidates should use
IDs such as:

- `newa-nepal-qwerty-direct-v1`;
- `newa-nepal-traditional-v1`.

The research candidates are not selected or promoted by this audit.
Native-speaker review must still decide the preferred default and long-press
organization.

The first QWERTY-direct research source remains explicitly non-selectable as
[`layouts/research/newa-nepal-qwerty-direct-v1.json`](../layouts/research/newa-nepal-qwerty-direct-v1.json)
candidate. Its pinned source decisions, isolated validator, and promotion gates
are recorded in
[`docs/newa-qwerty-direct-candidate.md`](newa-qwerty-direct-candidate.md).
The community-facing handoff is the
[shareable PNG and native-speaker worksheet](community/newa-native-review-v1.md).
The selectable internal beta is a separate repertoire-complete derivative,
[`layouts/internal/src/newa-nepal-prachalit-v1.json`](../layouts/internal/src/newa-nepal-prachalit-v1.json),
which exposes the five letters missing from the research candidate on an
explicit symbols row. Availability does not imply that placement is accepted.

## Shaping and repertoire contract

The direct layout should cover the modern Nepal Bhasa subset across base,
shift, long-press, and symbol layers. The six murmured resonants U+11413,
U+11419, U+11424, U+1142A, U+1142D, and U+1142F are atomic characters, not
HA-based conjunct shortcuts.

Golden rendering and editing vectors must include:

- KA + VIRAMA + SSA and JA + VIRAMA + NA;
- RA + VIRAMA + consonant for default repha;
- RA + VIRAMA + ZWJ + consonant for explicit half/eyelash RA;
- consonant + VIRAMA + ZWNJ for visible or nonjoining virama;
- contextual AI, O, and AU forms;
- JA and RA with U and UU;
- every consonant combined in logical order with every supported dependent
  vowel.

Keyman and another Android Newa keyboard use ZWJ in sequences described as
reph, while Unicode assigns VIRAMA+ZWJ the explicit half/eyelash form. This is
a native-review and shaping-test question, not a behavior to copy blindly.
The layout-v1 input policy therefore treats both ZWJ and ZWNJ as conjunct-only
controls: it buffers either control after a keyboard-owned Newa consonant and
U+11442 and materializes it only with a following Newa consonant. The current
policy does not emit a word-terminal ZWNJ; that would require a separate,
explicitly reviewed policy and query contract.
Private and otherwise non-composing fields suppress the buffered control and
commit the following consonant literally. This preserves the no-context-read
privacy boundary without creating a control sequence that generic code-point
backspace could orphan.

Output must be NFC, contain no PUA or U+FFFD, avoid reserved U+1145C, and never
split supplementary-plane surrogate pairs.
[Noto Sans Newa](https://notofonts.github.io/newa/) is the keyboard-label and
candidate-UI font reference. Current AOSP includes
it as an `und-Newa` fallback, but committed text still renders with the target
application's font. The direct and conversion profiles passed the canonical
API 34 software-emulator chain. API 26/27 and representative physical-device
rendering remain open. Older Android paths must detect Newa by scalar range
because `Character.UnicodeScript.NEWA` is only available from API 34.

## Editing and accessibility contract

While composition state exists, one backspace should undo one user action. A
shortcut that emitted a multi-scalar conjunct or RA+VIRAMA+ZWJ sequence should
delete atomically. For the conjunct-control policy, the following consonant
materializes the buffered joiner and consonant together, so backspace removes
that pair and retains the preceding consonant and U+11442. If dependent marks
have already attached to the continuation grapheme, the safe fallback removes
them with the pair rather than expose the joiner. Manually tapped consonant,
virama, and consonant without a joiner should unwind tap by tap.
Restart, cursor movement, selection deletion, held delete, and
lost-composition fallback require explicit vectors, and none may leave an
isolated joiner.

Every key needs a virtual accessibility node and a spoken Newa character name.
Invisible controls must announce “zero width joiner” or “zero width
non-joiner,” and every long-press or conjunct shortcut needs a unique spoken
description. The
[Android guidance](https://developer.android.com/guide/topics/ui/accessibility/views/custom-views)
is the runtime contract for the custom keyboard surface.

## Latin alias boundary

The pinned APK transliteration column now supplies the conservative internal
`new-Latn-Deva-NP` alias set. The measured implementation covers 1,974 of the
5,417 direct Devanagari surfaces with 1,828 distinct ASCII keys. It retains 135
colliding keys, with at most three targets for one exact key. Those figures and
the six frozen queries are bound by the
[Roman pack report](../reports/nepal-bhasa-roman-internal-pack-v0.json) and
[Android milestone](../reports/nepal-bhasa-roman-internal-android-milestone-v0.md).

This is a measured academic-transliteration alias baseline, not a complete
casual spelling model. Native-speaker review, spelling expansion, held-out
quality evaluation, and field testing remain open. It outputs Devanagari
dictionary candidates and does not infer Roman-to-Newa or Roman-to-Ranjana
text.

Keyman's QWERTY-positioned direct layout can inform touch placement, but it
does not validate the APK's word-level transliteration convention. Any
Latin-to-Newa candidates additionally need attested Newa spellings or an
explicit generated-conversion label.

## Devanagari-to-Newa conversion boundary

`new-Deva-Newa-NP` is a deterministic scalar-map product, not a dictionary
pack and not language-aware transliteration. Its canonical source has 165
rules: 91 direct mappings and 74 context-valid ZWJ/ZWNJ mappings. The compiled
artifact SHA-256 is
`29c88708b3d7aeb741779b7a7464efcb2464e060d7939c7998533d50b11a2d05`.
The exact source, coverage report, and positive/no-match vectors are:

- [`converters/internal/src/new-deva-newa-v1.json`](../converters/internal/src/new-deva-newa-v1.json);
- [`reports/nepal-bhasa-deva-newa-internal-map-v0.json`](../reports/nepal-bhasa-deva-newa-internal-map-v0.json);
- [`catalog/nepal-bhasa-deva-newa-internal-vectors-v0.json`](../catalog/nepal-bhasa-deva-newa-internal-vectors-v0.json).

On the measured Devanagari candidate inventory, the strict map converts 5,390
of 5,417 distinct surfaces (99.501569%) and 9,620 of 9,647 forms
(99.720120%).
The 27 no-match surfaces contain one or more of U+0945, U+0949, U+0951, or
U+0952, for which the v1 map deliberately defines no approximate Newa output.
Malformed joiners, mixed scripts, non-NFC input, and every other unmapped
scalar also produce a complete no-match.

The converter does **not** contract HA/virama/resonant sequences or
resonant/virama/HA sequences into the six atomic Newa murmured letters. For
example, `न्ह` maps mechanically to `𑐣𑑂𑐴`, not U+11424 NEWA LETTER NHA.
Atomic NGHA, NYHA, NHA, MHA, RHA, and LHA remain directly typeable in the
Prachalit layout. Inferring them from Devanagari sequences is deferred until
native orthographic review.

The generated-lock transaction, clean Android build, staged artifact replay,
15-vector benchmark replay, and API 34 runtime chain are complete. Remaining
conversion work is native orthographic review, especially the murmur policy
and the four unsupported marks. Physical-phone, API 26/27, TalkBack,
representative-font/editor, cancellation/race instrumentation, NCM corruption
matrix, and held-out language-quality testing remain production requirements
across the Newa lanes. The
[community conversion worksheet](community/nepal-bhasa-deva-newa-conversion-review-v1.md)
collects the decisions without conflating them with direct-layout review.
