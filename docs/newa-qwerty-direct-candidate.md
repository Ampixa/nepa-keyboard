# Newa QWERTY-direct research candidate

`layouts/research/newa-nepal-qwerty-direct-v1.json` is the first declarative
direct-input candidate for `new-Newa-NP`. It is intentionally outside both
`layouts/src` and `layouts/internal/src`; that exact research artifact is not
selectable, default-enabled, or included in either cumulative layout lock.
The internal engineering beta is the separately identified
`layouts/internal/src/newa-nepal-prachalit-v1.json`, derived from this mapping
with a visible row for the five missing murmured letters. Its internal
selectability does not change this candidate's pending native-review state.

The name “QWERTY direct” is deliberate. Latin key positions emit Newa scalars.
This is not Latin-word romanization and does not provide word decoding.

## Pinned mapping decisions

The phone base follows the pinned FUTO Android layout's QWERTY order. The
pinned Keyman phone and desktop sources provide an independent implementation
check and resolve mobile-only questions:

- FUTO and Keyman agree on the ten principal top-row outputs and most home-row
  outputs.
- The mobile sources compress desktop keys and disagree about some long-press
  placement. Layout v1 has no long-press declaration, so the candidate keeps
  primary direct outputs on base/shift and exposes atomic Newa signs on the
  symbol layer. It does not reinterpret a long-press alternate as a word rule.
- Shift-L uses U+1142F NEWA LETTER LHA from Keyman's phone and desktop mappings,
  instead of FUTO's U+1144C sign at that slot. U+1144C remains available in the
  shifted punctuation position.
- The base punctuation key uses U+1144B NEWA DANDA from Keyman's phone layout;
  FUTO's U+1144D NEWA COMMA remains on the symbol layer. This disputed mobile
  slot needs native review before promotion.
- The shifted punctuation row uses atomic U+1144C rather than FUTO's
  two-scalar RA+U-vowel sequence. This avoids adding an unreviewed shortcut
  deletion contract.
- U+11449 NEWA OM is an atomic symbol-layer key. The candidate does not inherit
  Keyman's phone-layer ZWNJ+OM sequence.
- U+11442 VIRAMA and explicit U+200D/U+200C controls are separate keys. The
  controls use the closed `newa_conjunct_joiner` runtime policy and cannot be
  emitted as generic text.

Newa digits are available on the symbol layer. ASCII digits remain on the
numeric layer because number, phone, and datetime editors use that layer.

## Deterministic validation boundary

Run the validator on cdjk:

```sh
python3 -m tools.validate_keyboard_layout_candidate \
  --candidate layouts/research/newa-nepal-qwerty-direct-v1.json
```

The validator accepts only one direct regular JSON child of `layouts/research`,
reuses the closed layout-v1 compiler in memory, writes nothing, and emits the
source, compiler, schema, and compiled-layout hashes. It has no profile-lock,
promotion, output, or lock-writing option.

The repository tests separately assert that the exact candidate is absent from
both cumulative source directories and layout locks. They also distinguish the
bound internal-beta derivative from the blocked public/export profile.
Community review uses the
[shareable PNG and native-speaker worksheet](community/newa-native-review-v1.md).

## Pending native-review packet

The deterministic packet at
`layouts/reviews/newa-nepal-qwerty-direct-v1.review.json` binds this candidate's
source, compiler, source schema, native-review schema, and review validator. It
enumerates all 109 non-action base, shift, symbol, and numeric keys by stable
key ID. It is explicitly `pending`, has 27 unresolved section, decision, and
coverage items, and has no profile-binding, selectability, or default authority.

The packet makes the currently measured repertoire gap concrete: five of the
six atomic murmured resonants listed in the input-reference audit are not yet
reachable, while U+1142F NEWA LETTER LHA is on Shift-L. It also records the
U+1144B/U+1144D punctuation choice, atomic U+1144C and U+11449 behavior,
separate VIRAMA/ZWJ/ZWNJ access, long-press strategy, and accessibility naming
as explicit decisions rather than implementation assumptions. The
accessibility decision covers all 109 text keys, not only the invisible
joiners.

Validate it on cdjk without writing generated files:

```sh
python3 -m tools.validate_layout_native_review \
  --review layouts/reviews/newa-nepal-qwerty-direct-v1.review.json
```

The pending packet leaves `compiled_sha256` null. The validator still emits the
derived compiled hash in its evidence report. A completed `accepted` or
`rejected` review must bind that exact hash, identify the Nepal Bhasa reviewer
and date, and satisfy the closed decision-state rules. Only `accepted` requires
every section, decision, and coverage item to be accepted and forbids retaining
any missing critical scalar. It also requires the selected punctuation,
joiner, repertoire, and layer decisions to describe the bound compiled
candidate exactly, and requires every text key to carry an explicit spoken
description instead of a glyph-only description. A `pending` packet must
remain wholly unresolved; partial unattributed decisions are rejected.
Neither completed status changes a profile by itself.

The accepted accessibility policy is machine-checked against the compiled
candidate. English names must equal the Unicode names of the emitted scalars;
bilingual names must pair a meaningful native name with that exact Unicode
name; native-only names must be meaningful, consistent for repeated output,
and distinct across different output. The native reviewer remains responsible
for the linguistic correctness of native names.

## Gates before promotion

This source is a review artifact, not production approval. Promotion still
requires:

1. native-speaker review of base, shift, sign, and future long-press placement;
2. an explicit layout-v2 long-press design or a reviewed decision to keep
   alternatives on shift/symbol layers;
3. API 26, 27, and 34 rendering, shaping, editing, and accessibility evidence;
4. physical-device validation, including third-party editor font fallback;
5. broader candidate-quality evidence beyond the small attested internal pack;
6. an accepted native-review packet and public/export profile-review change,
   followed by transactional cumulative relocking on cdjk.

Reserved U+1145C, private-use characters, U+FFFD, generic joiner text, and
unassigned scalars remain excluded.
