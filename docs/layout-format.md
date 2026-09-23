# Declarative keyboard layout v1

Date: 2026-07-16

## Purpose

Layout v1 replaces language-specific Java key arrays with reviewed data while
preserving the current Android behavior exactly. It deliberately describes
only capabilities the runtime can enforce today. A layout or dictionary does
not by itself make a language profile selectable.

The reviewed profile lock remains authoritative for selectability. The layout
compiler requires every selectable profile to resolve to a compiled layout and
requires the profile `source_script` to equal the layout `input_script`.
Blocked profiles remain blocked even when they can reuse an implemented visual
layout.

The public/export checked artifacts are:

- source schema: `schemas/layout-v1.schema.json`;
- compiled-lock schema: `schemas/layout-lock-v1.schema.json`;
- source layouts: `layouts/src/*.json`;
- independent behavior golden: `layouts/goldens/layout-v0-parity.json`;
- compiler: `tools/build_keyboard_layouts.py`; and
- canonical runtime input: `layouts/layouts-v1.lock.json`.

The cumulative internal product uses the same schemas and compiler with
`layouts/internal/src/*.json`, `layouts/internal/notices/*`,
`catalog/internal-profiles.lock.json`, and
`layouts/internal/layouts-v1.lock.json`. Internal resource-license labels are
provenance only and do not gate implementation or selectability.

## Source contract

Each source is one UTF-8 JSON object named `<layout_id>.json`. The compiler
rejects a byte-order mark, duplicate JSON keys, unknown fields, path/identity
mismatches, non-NFC text, unsafe controls, generic format characters, symlinks,
and unexpected source-directory entries. The exact script-bound Devanagari and
Newa joiner objects described below are the only format-character exceptions.

V1 has four complete layers:

- `base` and `shift` for normal text fields;
- `symbols`; and
- `numeric` for number, phone, and datetime fields.

A text key is a non-empty NFC string and compiles to a stable positional key ID
such as `base.r0.k0`, width 100, identical label/text/accessibility content,
and no action. Six exact text-bearing object forms add reviewed semantics
without turning the layout format into an arbitrary macro language:

- `text` supplies a text payload, custom visible label, and custom content
  description. It retains ordinary token behavior and supports dotted-circle
  labels for combining-mark keys.
- `orthographic_word` currently permits only U+2018. It joins an existing
  keyboard composing token and may begin one as reviewed orthographic word
  content. The same code point under ordinary `text` remains punctuation.
- `intra_word_punctuation` permits only hyphen, slash, backslash, or colon. It may
  join a keyboard-owned composing token only when that token currently ends in
  a letter, digit, or combining mark. It cannot begin a token, and a second
  connector cannot chain immediately after the first; ordinary punctuation in
  other profiles retains its word-boundary behavior. This closed policy makes
  attested Yakkha dictionary forms queryable without globally redefining
  punctuation as word content.
- `deva_conjunct_joiner` permits only U+200C or U+200D and only when
  `input_script` is `Deva`. The runtime buffers it only after a keyboard-owned
  Devanagari letter followed by U+094D, then emits it atomically with the next
  Devanagari letter. It never writes an isolated joiner.
- `newa_conjunct_joiner` permits only U+200C or U+200D and only when
  `input_script` is `Newa`. The runtime buffers it only after a keyboard-owned
  Newa consonant followed by U+11442, then emits it with the next Newa
  consonant.
  Backspace removes that emitted joiner and continuation together while
  retaining the preceding Newa consonant and virama; if attached marks have
  already joined the continuation grapheme, they are removed with it so no
  isolated joiner is exposed. Private or otherwise non-composing fields drop
  the buffered Newa joiner and commit the following consonant literally rather
  than create a sequence that cannot be deleted safely without reading editor
  context. This kind is conjunct-only; it does not define a word-terminal ZWNJ
  policy.
- `deva_terminal_zwnj` permits only U+200C and only when `input_script` is
  `Deva`. It has the same conjunct behavior, but may remain pending after a
  valid keyboard-owned letter-plus-virama tail. The pending scalar participates
  in suggestion lookup without being written alone; a following letter, word
  boundary, or complete candidate materializes it atomically. Delete, invalid
  continuation, private-field entry, reset, and profile switch clear it.
  Terminal ZWJ is not supported.

All text-bearing objects compile to width 100 with null action and hold fields.
Their exact source fields are `kind`, `text`, `label`, and
`content_description`; templates and extra fields are rejected. Generic text
continues to reject all format characters. An action key explicitly declares:

- one closed action from `shift`, `delete`, `enter`, `space`, `language`,
  `symbols`, or `letters`;
- label and content description;
- integer `width_units`; and
- optional `open_language_picker` hold behavior, valid only on space or the
  language key.

Only `${profile.native_name}` and `${profile.display_name}` templates are
accepted. The generated Android registry resolves them against the exact
active profile, which lets one Latin visual layout serve English direct input
and later Roman input without merging their dictionaries or output scripts.

Every source preserves authors and provenance. The public/export lane requires
its complete notice metadata separately. Internal sources may omit the license
object entirely or retain only known metadata; this never affects internal
selectability. When a notice is present, its path and SHA-256 occur together
and are lane-relative under `layouts/notices/...` or
`layouts/internal/notices/...`.

## Deterministic compilation

Run compilation and validation on `cdjk`, not on the orchestration Mac:

```sh
PYTHONPATH=src:. ~/.local/bin/uv run --python 3.14 python \
  tools/build_keyboard_layouts.py \
  --source-directory layouts/src \
  --profile-lock catalog/shipping-profiles.lock.json \
  --output layouts/layouts-v1.lock.json

PYTHONPATH=src:. ~/.local/bin/uv run --python 3.14 python \
  tools/build_keyboard_layouts.py \
  --source-directory layouts/src \
  --profile-lock catalog/shipping-profiles.lock.json \
  --output layouts/layouts-v1.lock.json \
  --check

PYTHONPATH=src:. ~/.local/bin/uv run --python 3.14 python \
  tools/build_keyboard_layouts.py \
  --source-directory layouts/internal/src \
  --profile-lock catalog/internal-profiles.lock.json \
  --output layouts/internal/layouts-v1.lock.json \
  --check
```

The compiler expands every key, orders layouts and transforms deterministically,
records exact source/profile-lock SHA-256 digests, serializes sorted UTF-8 JSON,
and writes atomically. Context transforms are bounded exact suffix rewrites,
sorted longest-first with stable IDs. Duplicate suffixes, identity rewrites,
non-NFC text, and oversized rules fail compilation.

The compiler and Android runtime share a 128-layout bound, enough for the full
33-target/74-profile catalog without making allocation unbounded. Notice files
are nonempty strict UTF-8, at most 65,536 bytes each, distinct per referenced
layout, and must exactly match the notice directory inventory. Zero-notice
internal catalogs are valid and still receive a deterministic empty manifest.

The current English and Nepali sources intentionally contain no transforms.
Android must reject non-empty transform data until the keyboard-owned
composing-session transform engine exists; ignoring declared transforms would
be a behavior and security bug.

## Milestone layout derivation

The internal pack finalizer preserves its original milestone-spec v1 contract
for existing profiles. Milestone-spec v2 adds a bounded, strictly sorted
`layout.operations` array for inventory-complete derived layouts. It supports
only three operations:

- `insert_row_before_actions` inserts one complete non-action row;
- `append_keys_to_row` appends an explicit non-empty key list to one existing
  row; and
- `replace_key` replaces one exact existing key position.

V2 permits at most 16 operations, rejects duplicate targets, unknown fields,
unknown operations, invalid layer or index types, and non-canonical ordering,
and pins the exact layout notice SHA-256. After applying the declared
operations to the pinned base layout, the finalizer compares the entire derived
layout object with the reviewed source. Any undeclared mutation therefore
fails even if the changed source is independently rehashed.

Milestone-spec v3 preserves the v2 operation contract and makes internal layout
license metadata an explicit override. `layout.license: null` removes the
license inherited from the base layout. An object replaces the inherited object
exactly; it requires non-empty `id` and `copyright` values plus a supported
`redistribution` label, and may add an HTTPS `license_url`. `notice_path` and
`notice_sha256` are optional but must occur together. The finalizer reads and
hashes a notice file only when that pair is present. This metadata records
internal provenance and is not an internal build or rollout gate.

## V0 parity evidence

The independent golden projects the old Java behavior rather than copying the
compiler output. It covers all four layers for both layouts, including text,
shift pairs, shared symbol/numeric rows, action order, labels, accessibility
descriptions, integer widths, profile-template resolution, and language-picker
holds.

At the input-policy milestone, all 33 layout compiler/parity/negative tests
passed, including the closed orthographic-word and Devanagari-joiner contract.
That historical repository snapshot passed 100 tests in 0.479 seconds on
`cdjk`; five layout sources and both layout locks validated against their Draft
2020-12 schemas. Its API 34 runtime result is recorded in
[`reports/layout-input-policy-v1.md`](../reports/layout-input-policy-v1.md).
Python 3.14 is required because the lock pins Unicode database 16.0.0; older
system Python builds fail closed rather than silently changing character
classification.

The cumulative internal source boundary has 12 unique layouts and 14
selectable engineering profiles. It includes English, Nepali, Limbu, Dhimal,
Sunuwar, Western Tamang, Lohorung, Yakkha, Nepal Bhasa Devanagari direct,
Prachalit/Newa direct, Romanized Nepal Bhasa to Devanagari, and
Devanagari-to-Prachalit conversion, Khaling direct, and Dumi direct. The Roman
profile reuses the Latin layout;
the converter reuses the Nepal Bhasa Devanagari layout. The original research-
only Newa candidate remains outside the cumulative locks; the selectable
Prachalit beta is a separate repertoire-complete derivative. The checked-in
generated locks are maintained by the transactional double-build on `cdjk`
described in
[`docs/cdjk-relock-validation.md`](cdjk-relock-validation.md). Canonical API 34
smoke, generated conformance, decoder, retained-service subtype/lifecycle,
corruption, prefix, and conversion benchmark evidence for all 14 internal
profiles is recorded in
[`reports/dumi-internal-android-milestone-v0.md`](../reports/dumi-internal-android-milestone-v0.md).

The release layout sources remain content-addressed as:

- English: `fc0ae5dfa73e3d034d1e48303c3d1b26fc493ac45e5d327a0f4f7b2cd1d02be3`;
- Nepali: `bca603b0a101f8c4be47fd6625c4e0bd0c7e7f1370f88c0e4028450b5ccbcade`.

Every regenerated lock pins the exact compiler, source schema, lock schema, and
profile-lock bytes used for that transaction. Android independently pins the
resulting profile and layout locks.

The public/export lock emits the complete selectable profile-binding set rather
than discarding it after validation; that lane contains exactly English and
direct Nepali. Text keys and transform strings reject any
letter or combining mark outside the declared input script; unassigned,
private-use, control, surrogate, and separator code points are rejected.
Generic format characters remain rejected; only the exact script-bound
Devanagari and Newa joiner kinds bypass that rule.

## Android lock boundaries

Android assembly refuses any layout or shipping-profile lock whose complete
SHA-256 differs from the reviewed release locks. The Gradle generator then
rechecks the pinned compiler, schemas, sources, notices, exact profile
revision/source bindings, closed action rows, duplicate text, script/scalar
bounds, hold semantics, and `redistribution: allowed` decisions. This prevents
a hand-edited compiled lock from reaching the runtime merely because it fits a
weaker parser.

The internal variants independently pin the complete internal profile and
layout locks and stage every pack or conversion map selected by that cumulative
catalog. They do not weaken or mutate the separate public/export lock boundary.

The generator stages one bounded notice per layout plus a deterministic
manifest. The app verifies the manifest's lock SHA, exact generated-layout
membership, safe unique paths, strict UTF-8, and every notice SHA before
display. The current MIT and xkeyboard-config aggregate notices have SHA-256
`e3345ee3ac889ba468ad63830a6ad1ee28f3da609608047d058a6bac9dd9fa8e`
and `739ff5404b852466ed201799e49bb5dc0f4eafe0876bf9aa74499f306b7b1786`.

## Explicit v1 limits

V1 does not claim character popups, arbitrary macros, regex transforms,
general editor-history transforms, tablet geometry, handwriting, or glide
typing. It also does not solve font coverage in other apps. Backspace behavior
is a separate runtime contract rather than layout data: Backspace v1 deletes an
owned composing grapheme and may inspect at most 64 UTF-16 units immediately
before the cursor solely to delete committed text. That method-local text is
not retained or sent to suggestions, private fields never request it, and an
incomplete or rejected boundary falls back to one code point. A known selected
range is replaced without reading its contents, and that selection snapshot is
consumed before mutation so a rapid second delete cannot reuse it; unknown
selection state uses a delete-key compatibility event and does not request
context. Its special
word-content policies are deliberately closed: only the three reviewed Yakkha
intra-word punctuation scalars, Devanagari ZWJ/ZWNJ continuation and
terminal-ZWNJ state, and Newa conjunct-only ZWJ/ZWNJ continuation are
supported. Devanagari resolved conjuncts retain the complete-trailing-grapheme
Backspace v1 behavior. Newa uses a narrower action boundary: deleting a
resolved U+11442 + joiner + consonant tail removes the joiner and following
consonant together while retaining the preceding consonant and U+11442. Any
marks already attached to that continuation grapheme are included in the safe
delete. A manually tapped Newa consonant + U+11442 + consonant sequence without
a joiner continues to unwind tap by tap. The canonical API 34 instrumentation
passed these direct-Newa cases. API 26/27 and representative physical-editor
evidence remain pending; correct rendering and editing remain Android/device
obligations.

Before Limbu, Sunuwar, Newa, or another complex-script profile is considered
production-ready, it needs Unicode-scalar-safe label sizing, reviewed
combining/joiner policy, deterministic deletion semantics, native-speaker
review, accessibility evidence, and physical-device rendering tests. Internal
engineering selectability is architecture evidence, not a claim that these
production gates passed. A debug-only synthetic Unicode fixture may exercise
rendering, but it is not a language pack or production-readiness approval.

The Android lock verifier now recognizes the same nine explicit Unicode-16
script block ranges as the Python compiler, including Sunuwar characters that
Java 17's older Unicode tables classify as unassigned. This removes a
language-specific generator branch; it does not waive shaping, sequence,
deletion, font, accessibility, native-review, or physical-device gates. Layout
v1 also has a closed Newa conjunct-joiner policy for U+200C and U+200D after
U+11442. It remains separate from the Devanagari conjunct and terminal-ZWNJ
policies, and no Newa terminal-ZWNJ behavior is implied.
