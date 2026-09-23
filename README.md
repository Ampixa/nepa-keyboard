# Nepa Keyboard

Nepa Keyboard is an offline-first keyboard project for the languages and scripts
used in Nepal. The project treats these as separate concerns:

- **Language or variety**: the vocabulary and grammar being entered, such as
  Nepali, Limbu, Nepal Bhasa, Athpahariya, or Dangaura Tharu.
- **Output script**: the Unicode text emitted by the keyboard, such as
  Devanagari, Limbu (Sirijanga), Newa, or Ol Chiki.
- **Input method**: direct layout, phonetic/roman input, or a script conversion
  method.
- **Language data**: canonical words, surface forms, aliases, frequencies,
  provenance, and validation evidence.

This separation is essential. “Rai” is an umbrella identity rather than one
interchangeable dictionary, and Tamang, Magar, and Tharu resources also need
variety-aware packs. A script layout can be made before a predictive dictionary
is ready, but the two readiness claims must not be confused.

## Community review: Nepal Bhasa

[Open or share the working Devanagari beta's 1440 × 900 keyboard PNG](docs/community/nepal-bhasa-deva-layout-preview-v1.png),
then [copy its native-speaker review worksheet](docs/community/nepal-bhasa-deva-layout-review-v1.md#native-speaker-review-worksheet).
The Devanagari method is the ninth selectable internal engineering profile and
has canonical API 34 emulator evidence, but it still needs native-speaker and
physical-phone review.

Direct Prachalit/Newa-script typing is the tenth selectable internal beta.
Its [current internal-beta preview](docs/community/newa-prachalit-internal-preview-v1.png) and
[worksheet](docs/community/newa-native-review-v1.md#native-speaker-review-worksheet)
show the repertoire-complete internal derivative, including five provisional
letters on a symbols row. The immutable research proposal is retained in the
worksheet for comparison. The mapping remains open to native placement and
accessibility review.

Romanized Nepal Bhasa to Devanagari is the eleventh selectable internal beta.
It covers 1,974 of the 5,417 direct candidates with 1,828 measured ASCII keys;
it does not claim Romanized Prachalit output.

In this repository, **Newa** is the Unicode script identity used for the
U+11400–U+1147F text emitted by the Prachalit Nepal Lipi profile. **Prachalit
Nepal Lipi** is the user-facing writing-tradition label for that profile.
Ranjana is a distinct script tradition and is not an alias for this profile;
the current layout, pack, and converter make no Ranjana-output claim. The
[input-method status audit](docs/nepal-bhasa-input-reference-audit.md#current-implementation-status)
records the exact product boundaries and remaining review work.

Devanagari-to-Newa conversion is the twelfth selectable, non-default internal
beta. It reuses the reviewed Nepal Bhasa Devanagari layout and offers a
mechanically generated Unicode Newa candidate plus the literal Devanagari
input. It is not an attested Newa dictionary. Its
[source report](reports/nepal-bhasa-deva-newa-internal-map-v0.json) and
[canonical validation vectors](catalog/nepal-bhasa-deva-newa-internal-vectors-v0.json)
pin the measured coverage and no-match behavior. The
[community conversion worksheet](docs/community/nepal-bhasa-deva-newa-conversion-review-v1.md)
separates the remaining orthographic questions from runtime acceptance. The
[12-profile milestone](reports/nepal-bhasa-deva-newa-internal-android-milestone-v0.md)
records the generated lock, clean build, and canonical API 34 proof.

Dumi Devanagari direct is the 14th selectable, non-default internal beta. Its
2,132-surface deterministic pack is bound to a Dumi-specific layout with
attested colon composition, visarga, nukta, conjunct joiners, and the
Devanagari glottal-stop letter. The
[14-profile milestone](reports/dumi-internal-android-milestone-v0.md) records
the all-scope relock, clean build, API 34 behavior, and measured prefix lookup.

## Current work

The primary product lane is internal and targets every dictionary-backed
language. License and redistribution status are retained as provenance but do
not block or rank internal packs, layouts, builds, benchmarks, emulators, or
APKs. The existing public/export lane remains separate and fail-closed.

- [`catalog/resources.json`](catalog/resources.json) is the audited registry of
  local dictionaries, corpora, and script resources.
- [`reports/dictionary-resource-inventory-v1.md`](reports/dictionary-resource-inventory-v1.md)
  records the 22 dictionary-backed targets and the exact SHA-pinned identity of
  all 30 dictionary/lexicon resources.
- [`schemas/resource-catalog.schema.json`](schemas/resource-catalog.schema.json)
  defines the registry format and readiness vocabulary.
- [`schemas/shipping-profile-review.schema.json`](schemas/shipping-profile-review.schema.json)
  defines the reviewed profile, exact pack or conversion artifact,
  validation-vector, and evidence-hash input.
- [`catalog/shipping-profiles.lock.json`](catalog/shipping-profiles.lock.json)
  is the deterministic reviewed Android boundary: 33 targets, 74 input methods,
  nine scripts, and only two currently selectable profiles.
- [`catalog/internal-profiles.lock.json`](catalog/internal-profiles.lock.json)
  is the cumulative internal product boundary: the same 74-profile catalog with
  English, Nepali, Limbu, Dhimal, Sunuwar, Western Tamang, Lohorung, Yakkha,
  Nepal Bhasa Devanagari direct, Romanized Nepal Bhasa to Devanagari, and Nepal
  Bhasa Prachalit/Newa direct, Devanagari-to-Prachalit conversion, Khaling
  direct, and Dumi direct currently selectable as engineering profiles. These
  14 profiles use 13 NKP bindings backed by 12 unique packs, one NCM converter,
  and 12 unique layouts. They span four selectable output scripts and cover 11
  of the 22 dictionary-backed targets; 11 targets still need a selectable
  profile.
- [`docs/coverage-strategy.md`](docs/coverage-strategy.md) explains launch
  cohorts and the quality gates required before a pack ships.
- [`docs/host-safety.md`](docs/host-safety.md) requires all Android and compute
  workloads to run on the `cdjk` Ubuntu machine or another approved remote host.
- [`docs/community/newa-native-review-v1.md`](docs/community/newa-native-review-v1.md)
  is the shareable Newa QWERTY-direct research preview and native-speaker
  feedback form. The original mapping remains a research-only review artifact
  with five known missing letters and 27 unresolved review items; the internal
  beta is a separate repertoire-complete derivative with those five letters on
  an explicit symbols row. The [shareable 1440 × 900 PNG](docs/community/newa-prachalit-internal-preview-v1.png)
  and [native-speaker worksheet](docs/community/newa-native-review-v1.md#native-speaker-review-worksheet)
  are included. Native placement and accessibility feedback still applies to
  the internal beta and must not be confused with an accepted review.
- [`docs/cdjk-relock-validation.md`](docs/cdjk-relock-validation.md) defines the
  transactional double-build, rollback, exact-pin, and evidence procedure for
  the four generated catalog/layout locks.
- [`docs/cdjk-yakkha-refresh.md`](docs/cdjk-yakkha-refresh.md) defines the
  remote-only deterministic refresh and vector replay for the eighth internal
  pack used by the canonical eight-profile Android evidence.
- [`docs/sil-apk-layout-matrix-audit.md`](docs/sil-apk-layout-matrix-audit.md)
  defines the reusable cdjk-only audit that compares a catalog-pinned SIL-APK
  dictionary with every compiled Devanagari layout without claiming language
  or keyboard quality.
- [`docs/sil-apk-candidate-pack.md`](docs/sil-apk-candidate-pack.md) defines the
  candidate-only double-build and prefix-inspection lane that consumes one
  exact matrix audit plus an explicit layout and terminal-ZWNJ policy without
  promoting a profile.
- [`docs/pack-format.md`](docs/pack-format.md) defines the deterministic v0
  build tables and Android-facing `.nkp` binary format.
- [`docs/layout-format.md`](docs/layout-format.md) defines the deterministic
  declarative layout-v1 compiler, exact English/Nepali parity contract, and
  explicit complex-script limits.
- [`docs/android-decoder-contract-v1.md`](docs/android-decoder-contract-v1.md)
  defines the generation-bound cancellable N-best request/result API, literal
  fallback, current NKP provider limits, and canonical API 34 cdjk evidence.
- [`docs/product-architecture.md`](docs/product-architecture.md) defines the
  Gboard-informed IME behavior, language-profile model, picker, and production
  gates for all cataloged languages.
- [`reports/keyboard-reference-research-v0.md`](reports/keyboard-reference-research-v0.md)
  audits mature Android keyboard implementations and primary research, then
  records the concrete adopt/adapt/avoid decisions for the next runtime.
- [`reports/language-picker-production-gap-v0.md`](reports/language-picker-production-gap-v0.md)
  audits the generated language manager and in-keyboard picker against the
  daily-IME goal, then defines the subtype, readiness, accessibility,
  lifecycle, and decoder work still required for production use.
- [`reports/limbu-pack-readiness-v0.md`](reports/limbu-pack-readiness-v0.md)
  records the pinned dictionary and layout references, Nepal-specific
  orthography questions, and the evidence needed for a first selectable Limbu
  profile.
- [`reports/dhimal-pack-readiness-v0.md`](reports/dhimal-pack-readiness-v0.md)
  records the pinned Devanagari source, real deterministic adapter run, rejected
  joiner audit, and complete accepted-scalar layout inventory.
- [`reports/western-tamang-pack-readiness-v0.md`](reports/western-tamang-pack-readiness-v0.md)
  records the pinned APK lexicon, deterministic headword-only adapter, rejected
  joiner audit, and exact seven-scalar layout gap.
- [`reports/lohorung-pack-readiness-v0.md`](reports/lohorung-pack-readiness-v0.md)
  records the pinned SIL-APK JSONL, reusable strict adapter, terminal-ZWNJ
  contract, deterministic pack, and exact ten-scalar layout gap.
- [`reports/yakkha-pack-readiness-v0.md`](reports/yakkha-pack-readiness-v0.md)
  records the pinned SIL-APK JSONL, independently audited terminal-ZWNJ
  requirement, deterministic pack, exact scalar gap, and closed intra-word
  punctuation contract.
- [`reports/profile-expansion-v1.md`](reports/profile-expansion-v1.md) records
  the data-driven third-profile architecture, exact pack binding, generic
  Android subtype/smoke/benchmark path, and the still-closed Dhimal/Limbu
  release decisions.
- [`reports/sunuwar-internal-android-milestone-v0.md`](reports/sunuwar-internal-android-milestone-v0.md)
  records the deterministic fourth profile, reusable internal-pack finalizer,
  extended Devanagari input policies, four-pack APK boundary, and API 34
  benchmark evidence.
- [`reports/dhimal-internal-android-milestone-v0.md`](reports/dhimal-internal-android-milestone-v0.md)
  records the deterministic fifth profile, inventory-complete Dhimal layout,
  five-pack picker/runtime proof, and API 34 benchmark evidence.
- [`reports/western-tamang-internal-android-milestone-v0.md`](reports/western-tamang-internal-android-milestone-v0.md)
  records the deterministic sixth profile, inventory-complete Western Tamang
  layout, generated all-profile runtime conformance, and six-pack API 34 proof.
- [`reports/lohorung-internal-android-milestone-v0.md`](reports/lohorung-internal-android-milestone-v0.md)
  records the deterministic seventh profile, inventory-complete Lohorung
  layout, terminal-ZWNJ composing semantics, generated conformance, and
  seven-pack API 34 proof.
- [`reports/yakkha-internal-android-milestone-v0.md`](reports/yakkha-internal-android-milestone-v0.md)
  records the historical eight-profile API 34 software-emulator chain, decoder
  and retained-service subtype contracts, and eight-pack prefix benchmark.
- [`reports/nepal-bhasa-internal-android-milestone-v0.md`](reports/nepal-bhasa-internal-android-milestone-v0.md)
  records the historical nine-profile API 34 chain, the selectable
  Nepal Bhasa Devanagari pack/layout, and the nine-pack prefix benchmark.
- [`reports/nepal-bhasa-newa-internal-android-milestone-v0.md`](reports/nepal-bhasa-newa-internal-android-milestone-v0.md)
  records the historical ten-profile API 34 chain, the attested
  Prachalit/Newa pack, the repertoire-complete internal layout, and the
  ten-pack prefix benchmark.
- [`reports/nepal-bhasa-roman-internal-android-milestone-v0.md`](reports/nepal-bhasa-roman-internal-android-milestone-v0.md)
  records the historical 11-profile API 34 chain, the measured Roman
  alias policy, the shared direct/Roman pack identity, and the 11-binding
  prefix benchmark.
- [`reports/nepal-bhasa-deva-newa-internal-android-milestone-v0.md`](reports/nepal-bhasa-deva-newa-internal-android-milestone-v0.md)
  records the historical 12-profile API 34 chain, strict conversion
  runtime, 15-vector replay, and conversion benchmark.
- [`reports/khaling-internal-android-milestone-v0.md`](reports/khaling-internal-android-milestone-v0.md)
  records the historical 13-profile API 34 chain and the deterministic
  Khaling pack/layout promotion.
- [`reports/dumi-internal-android-milestone-v0.md`](reports/dumi-internal-android-milestone-v0.md)
  records the current canonical 14-profile API 34 chain, Dumi-specific layout,
  deterministic 2,132-surface pack, and 13-binding prefix benchmark.
- [`android/README.md`](android/README.md) documents pack format v0, Android
  runtime v2, the isolated public/export boundary, and remote benchmarks.
- [`desktop/macos/README.md`](desktop/macos/README.md) documents the
  deterministic three-input-source **Nepa Romanized Pro** macOS bundle:
  Nepali to Devanagari, Nepal Bhasa/Newari to Newa/Prachalit, and Limbu to
  Sirijanga. All three are included in the first desktop scope.
- [`desktop/keyman/README.md`](desktop/keyman/README.md) documents the shared
  Windows, macOS, and Linux Keyman package for those same three input sources.
  Linux live IBus acceptance passes 12/12 vectors; the exact remaining Windows
  and macOS acceptance boundary is recorded in
  [`reports/desktop-cross-platform-readiness-v0.md`](reports/desktop-cross-platform-readiness-v0.md).
- [`desktop/phonetic/README.md`](desktop/phonetic/README.md) documents the new
  Google-style composing desktop input methods. They show converted and literal
  candidates beside the caret for Nepali, Nepal Bhasa/Newa, and Limbu, with a
  persisted enable/disable toggle. The installed Linux IBus path is live-tested;
  native macOS and Windows packages and their current acceptance boundaries are
  documented there.

## Pack compiler

The dependency-free compiler validates provenance, Unicode, script identity,
alias collisions, and release permissions before producing a bundle:

```sh
nepa-pack build --input data/build/npi-Deva-NP --output dist/npi-Deva-NP.nkp
nepa-pack inspect --pack dist/npi-Deva-NP.nkp --index aliases --prefix nepal
```

Compilation and tests run on `cdjk`, not on the local Mac.

The first remotely built artifact is documented in
[`reports/npi-Deva-NP-pilot.md`](reports/npi-Deva-NP-pilot.md): 25,000 Nepali
forms, 44,899 Roman keys, deterministic output, and a 5.45 MiB internal pack.

The Android reader and API 34 prefix baseline are documented in
[`reports/android-v0-prefix-benchmark.md`](reports/android-v0-prefix-benchmark.md).
That historical single-pack harness proved the isolated public/export reader
rejected an internal artifact and that an explicit internal authority could
still verify and benchmark it. The current internal catalog uses its dedicated
product reader and catalog benchmark entry points.

The first product-shaped English/Nepali IME, language picker, release isolation,
and remote runtime checks are documented in
[`reports/android-ime-v0.md`](reports/android-ime-v0.md).

Incremental composing, exact candidate replacement, the asynchronous
release-only pack adapter, and its API 34 evidence are documented in
[`reports/android-ime-composing-v0.md`](reports/android-ime-composing-v0.md).

The reviewed English/Nepali release bindings, fail-closed Gradle staging,
staged IME smoke test, APK audit, and per-pack API 34 lookup benchmark are
documented in
[`reports/android-release-packs-v0.md`](reports/android-release-packs-v0.md).

The current shipping review additionally content-binds those historical
evidence reports and exact pack artifact/index metadata. Android derives pack
staging, validation vectors, and system subtypes from the complete SHA-pinned
profile lock; there is no separate language-specific release-pack list.

The generated 74-profile Android registry, searchable virtualized language
manager, bounded in-keyboard picker, and remote gate evidence are documented in
[`reports/android-shipping-profile-catalog-v0.md`](reports/android-shipping-profile-catalog-v0.md).

The cumulative internal boundary now selects English, Nepali, Limbu, Dhimal,
Sunuwar, Western Tamang, Lohorung, Yakkha, Nepal Bhasa Devanagari, and Nepal
Bhasa Prachalit/Newa direct, Romanized Nepal Bhasa to Devanagari, and
Devanagari-to-Prachalit conversion, Khaling direct, and Dumi direct. The
canonical API 34 software-emulator chain passed for all 14 engineering
profiles, including conversion routing,
decoder, retained-service subtype/lifecycle, spatial, prefix, conversion, and
corruption gates. The evidence and its physical-device, API 26/27,
accessibility, native-review, and quality limitations are explicit in
[`reports/dumi-internal-android-milestone-v0.md`](reports/dumi-internal-android-milestone-v0.md).

The layout-v1 compiler covers the English and direct Nepali phone layouts from
reviewed JSON, binds them to the exact profile lock, and matches an independent
v0 behavior golden. The cumulative internal compiler currently covers 12
unique layouts bound to 14 selectable profiles. All four checked-in generated
locks and their Android pins were rebuilt in the deterministic all-scope
transaction on `cdjk`; future replacement hashes must come from that
transaction, never from a local or hand-edited regeneration.

The raw source assets remain in their existing repositories and on the mounted
SSD. This repository records their provenance and builds compact keyboard
artifacts; it does not silently copy or relicense them.
