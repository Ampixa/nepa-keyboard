# Language coverage and dictionary strategy

Audit date: 2026-07-15

## What the local collection supports

The current collection is sufficient to begin building offline keyboard packs.
It is not yet sufficient to call every discovered language production-ready.

The catalog currently identifies 30 dictionary/lexicon artifacts across 22
language or variety targets. Every one now has a SHA-256 identity, including
all 14 resources marked canonical. See
[`../reports/dictionary-resource-inventory-v1.md`](../reports/dictionary-resource-inventory-v1.md).

- The Nepali frontend contains 648,574 frequency rows and the local Hunspell
  dictionary contains 36,850 rows.
- Limbu has a structured 8,798-row Limdic dictionary, 2,541 Pangloss entries,
  Sirijanga and Devanagari text, and a 50,179-row combined parallel corpus.
- The Rai toolkit reports 43,645 dictionary rows and 227,789 parallel rows
  across separately identified Kiranti languages.
- Dhimal has 11,341 induced Nepali-Dhimal rows and 8,782 Webonary rows.
- The SSD contains Bible text for 20 language codes and audio-only material for
  another 27. Scripture is useful for vocabulary evidence and low-weight
  frequency, but is too domain-specific to rank a keyboard by itself.
- The Matribhasa reference directory currently contains 342 PDF files. This is
  a reference-library count, not a dictionary count: it includes duplicates,
  grammars, textbooks, and corpora.

The inventory records observed files. Internal support depends on normalization,
native-speaker review, held-out keyboard evaluation, and runtime evidence.
License status remains provenance metadata and matters only if a separate
public/export artifact is requested.

## Coverage model

A user-visible keyboard is the intersection of four independently versioned
objects:

```text
language or variety + output script + input method + language-data pack
```

The reviewed runtime projection is checked into
[`../catalog/shipping-profiles.lock.json`](../catalog/shipping-profiles.lock.json).
It contains all 33 targets and 74 input-method identities, but only English
direct and Nepali direct are selectable. Research readiness in this document
cannot bypass that separate review lock.

This produces identities such as `lif-Limb-NP`, `lif-Deva-NP`, `new-Newa-NP`,
and `new-Deva-NP`. UI collections may group related packs, but do not merge
their vocabularies. In particular:

- Rai is a collection containing Athpahariya, Bantawa, Chamling, Dumi, Khaling,
  Koyu, Kulung, Lohorung, Sampang, Thulung, Yakkha, and other distinct packs.
- Eastern and Western Tamang remain distinct.
- Eastern and Western Magar remain distinct.
- Dangaura, Rana, Kochila/Chitwania, and other Tharu varieties remain distinct.

## Proposed cohorts

### Cohort 0: platform foundation

- English direct QWERTY with the reviewed ESDB/SCOWL vocabulary and
  FrequencyWords ranking-only release pack.
- Nepali direct Devanagari with the reviewed Google/OpenSLR release pack.
- Roman-to-Devanagari Nepali as a separately gated alias input method.

### Cohort 1: prove the multi-script design

- Limbu: Sirijanga, Devanagari, and Roman input aliases.
- Nepal Bhasa: Devanagari and Newa output packs, plus Roman input aliases.
- Sunuwar: Devanagari first; native Sunuwar script remains a separately gated
  output pack.
- Dhimal: Devanagari direct and Roman input.

Limbu proves a strong native-script dictionary path. Nepal Bhasa proves that
one language can have two output-script artifacts without treating converted
text as attested native-script text.

### Cohort 2: structured local lexicons

- Athpahariya, Lohorung, Kulung, Sampang, Bantawa, Yakkha, Khaling, and Dumi.
- Central Gurung, Eastern and Western Tamang, and Eastern and Western Magar.
- Sherpa and Kochila/Chitwania Tharu after source and variety review.

### Cohort 3: corpus/reference extraction

- Maithili, including a separately gated Tirhuta output pack.
- Bhojpuri, Doteli, Rajbanshi, Dangaura Tharu, Rana Tharu, Thulung, and Chamling.
- Santali/Ol Chiki, which has a strong native-script corpus but still needs a
  curated spell/correction lexicon and Nepal-usage review.

## Native-script evidence

| Script | Local evidence | Current implication |
|---|---|---|
| Limbu/Sirijanga | Structured bilingual dictionary, wordlist, Bible and curriculum text | Candidate generation and Roman aliases can begin |
| Newa/Prachalit | 441-page PAGE-XML HTR dataset and 285 genuine born-digital lines | Layout and script model are viable; generated conversions must remain labeled |
| Ol Chiki | 204,651 majority-Ol-Chiki Santali Wikipedia lines | Strong frequency source; dictionary and Nepal-variety review still needed |
| Tirhuta | At least 149 periodical issues, roughly 12 GB, in legacy font encoding | Build the legacy-font-to-Unicode converter before claiming a corpus |
| Sunuwar | 79 native-script lines plus much larger Devanagari lexical resources | Direct layout research; prediction should start in Devanagari |
| Kirat Rai | 101 native-script lines | Layout/orthography research only, not a generic Rai dictionary |
| Lepcha | Fewer than 2,000 verified Unicode characters in the harvested web corpus | Research only until a real corpus or legacy-font converter is available |
| Gurung Khema | Provenance/reference material without a substantive corpus | Layout research only |

## Build-data model

Auditable build data should preserve the distinctions erased by a flat word
list:

- `lexeme`: language, variety, lemma, part of speech, homonym identity, and
  optional Nepali/English gloss.
- `form`: script-specific surface form, inflection/variant type, evidence type,
  and confidence.
- `alias`: many-to-many input spelling mapped to a form. Roman spelling is an
  input path, not the canonical word.
- `frequency`: per-source and per-domain counts. Do not destructively collapse
  them into one raw count.
- `source`: path/URI, hash, extraction method, license, review status, and exact
  locator where available.

Store authoritative forms in NFC. Never overwrite them with a search-normalized
or NFKC form. Generated script conversions and induced lexicon entries must stay
marked as generated until reviewed or independently attested.

## Ranking policy

An initial score can combine normalized frequency with source quality and a
form prior. Domain evidence remains separate so the weights can be retuned.

Suggested starting domain weights:

| Domain | Weight |
|---|---:|
| conversational/chat | 1.20 |
| general prose | 1.00 |
| news/Wikipedia | 0.80 |
| textbook | 0.60 |
| religious | 0.25 |
| dictionary headword | 0.15 |
| synthetic/generated | 0.10 |

Dictionary membership proves that a candidate exists; it does not prove that
the candidate is frequent. Bible data must have a capped contribution, and its
proper names require explicit filtering.

## Internal production gates

1. **Unicode:** valid UTF-8, NFC, allowed-script checks, combining-mark checks,
   and no unapproved controls or mojibake.
2. **Identity:** duplicates, homographs, orthographic variants, and script
   variants are linked rather than overwritten.
3. **Language/variety:** contamination is measured; umbrella groups are never
   used as a substitute for a language label.
4. **Evidence:** every supported form has provenance. Generated and induced forms
   pass a higher confidence threshold.
5. **Ranking:** top-candidate manual review, domain-balance report, proper-name
   share, and Roman-alias collision analysis.
6. **Keyboard quality:** at least 300 curated input-to-target cases for beta,
   prefix recall at five, Roman top-three accuracy, held-out token coverage, and
   keystroke savings.
7. **Runtime:** deterministic build, checksummed bundle, corrupt-pack handling,
   bounded memory, and a sub-10 ms P95 prefix lookup target on a reference phone.

Public/export packaging has an additional isolated redistribution-and-notice
gate. It does not block internal packs, layouts, benchmarks, emulators, APKs,
or language ordering.

The shipping-profile generator enforces a bootstrap distinction. English and
direct Nepali are the two architecture-foundation profiles; their
current evidence proves layout, redistribution, notice UI, release pack, and
emulator runtime wiring, but does not make the unresolved speaker/phone work
disappear. Any non-foundation profile must mechanically add native-speaker
review, quality evaluation, physical-device runtime, and accessibility review
before it can become public/export-selectable or be called production-ready.
Internal engineering profiles may be selectable earlier so their exact runtime
artifact, layout, picker, and provider integration can be exercised without
making a support claim. A regression test proves that layout + pack + emulator evidence alone
cannot enable Limbu or any other third profile in the public/export lock.
Foundation status controls only the extra evidence gates; it no longer defines
the complete selectable set. A positive synthetic fixture proves that a third
profile can pass when every expansion gate and exact artifact binding is
present, without changing the current two-profile release lock.

Every selectable row now binds either a complete pack artifact or a complete
conversion artifact, plus its language/script identity, validation vectors,
and content-hashed evidence reports. Pack rows additionally bind candidate and
surface/alias index counts. Android requires the staged profile set to equal
the selectable set and rejects an artifact whose identity differs from the
profile binding. This makes “reviewed profile but missing Android artifact” a
build failure rather than a selectable keyboard with empty suggestions.

## Runtime artifact

The auditable tables should compile to a small immutable `.nkp` bundle rather
than being queried directly on the phone:

```text
manifest.json
surface.trie
aliases.trie
candidates.bin
scores.bin
notices.json
```

The v0 format uses a deterministic prefix trie with materialized top candidates
at every node. A later format may replace this with a minimal FST/DAFSA after
Android memory and latency benchmarks justify the complexity. The base keyboard
pack needs words, aliases, and ranks—not full dictionary definitions.
Definitions and source detail can live in an optional dictionary add-on. `core`
and `full` pack tiers allow small downloads without discarding the long tail.

Script-conversion methods use a separate canonical `.ncm` artifact rather than
pretending generated text is dictionary-attested. Conversion map v1 is bounded,
NFC-only, leftmost-longest, complete-token, and fail-closed on any unmapped
position; its first Android milestone is documented in
[`reports/nepal-bhasa-deva-newa-internal-android-milestone-v0.md`](../reports/nepal-bhasa-deva-newa-internal-android-milestone-v0.md).
