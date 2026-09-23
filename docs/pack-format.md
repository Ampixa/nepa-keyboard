# Nepa Keyboard pack format v0

The v0 format separates auditable build tables from the compact artifact loaded
by a keyboard. It deliberately fixes the Android-facing boundary before an
Android implementation is added.

## Source directory

Each build consumes one directory:

```text
pack.json
sources.jsonl
forms.jsonl
aliases.jsonl
```

`pack.json` identifies one language, variety, and output-script artifact. A
language with two output scripts produces two artifacts, for example
`lif-Limb-NP` and `lif-Deva-NP`.

`sources.jsonl` records provenance and redistribution status. `forms.jsonl`
contains authoritative NFC surface forms and integer rank scores.
`aliases.jsonl` contains input paths such as casual or academic Roman spellings;
aliases are never treated as canonical output.

Every form and alias must cite at least one source. An `allowed` release source
must also carry a pinned SHA-256, source URL, license URL, and the notice text
that will be embedded in `notices.json`. The compiler rejects a release that
omits any of these fields; changing only a redistribution label is therefore
not enough to turn research data into a shipping artifact.

If any used source is `CC-BY-SA-4.0`, `pack.json` must also declare
`"artifact_license":"CC-BY-SA-4.0"`. Release compilation fails if the
share-alike status is present only on a source row and omitted from the pack.

Row contracts are defined by
[`source-row.schema.json`](../schemas/source-row.schema.json),
[`form-row.schema.json`](../schemas/form-row.schema.json), and
[`alias-row.schema.json`](../schemas/alias-row.schema.json). Deterministic
lookup cases use
[`validation-query.schema.json`](../schemas/validation-query.schema.json).

The schemas are intentionally small enough to review as TSV/JSONL while the
canonical data model grows toward lexeme, form, alias, frequency, and evidence
tables.

### `pack.json`

Required fields:

```json
{
  "pack_id": "npi-Deva-NP",
  "language": "npi",
  "display_name": "Nepali",
  "output_script": "Deva",
  "region": "NP",
  "data_version": "0.1.0",
  "max_suggestions": 8,
  "surface_lookup_normalization": "NFC"
}
```

`surface_lookup_normalization` defaults to `NFC`. English packs may select
`NFC+ASCII-lower`: canonical candidate casing remains unchanged, while ASCII
`A` through `Z` are lowered identically when the surface trie is built and
queried. The deliberately narrow mode avoids relying on different full-Unicode
case-fold implementations in Python and Android.

### `sources.jsonl`

Every source has a stable ID, extraction method, license label, and one of these
redistribution states: `allowed`, `system`, `prohibited`,
`permission_required`, or `unknown`.

Release-mode builds fail if any used source is not `allowed` or `system`.
Internal builds retain restricted sources and clearly label the artifact as
internal.

### `forms.jsonl`

```json
{"form_id":"npi:...","surface":"नेपाल","rank_score":9182,"source_ids":["npi-frequency"],"evidence":"attested"}
```

Surface forms must already be NFC. Controls are rejected, except explicitly
allowed joiners. Letter characters outside the declared output script are
rejected. Duplicate surfaces are merged deterministically while retaining
source and form IDs.

### `aliases.jsonl`

```json
{"alias":"nepal","form_id":"npi:...","rank_delta":0,"scheme":"reverse_roman_folded","source_ids":["npi-frequency"],"evidence":"generated"}
```

Alias keys are normalized independently using NFC and case folding. Collisions
are expected: one Roman key can lead to multiple words, ranked by the effective
form score plus `rank_delta`.

## Runtime `.nkp`

An `.nkp` file is a deterministic ZIP-STORE container with fixed member
timestamps and lexically ordered members:

```text
manifest.json
notices.json
candidates.bin
scores.bin
surface.trie
aliases.trie
```

ZIP-STORE is used in v0 so byte reproducibility does not depend on a particular
zlib implementation. Artifact members are checksummed in `manifest.json`; a
sidecar build report records the final artifact checksum.

### Candidate and score tables

`candidates.bin` begins with `NKCAND1\0`, a little-endian `uint32` count, a
`count + 1` offset table, and concatenated UTF-8 strings. Candidate IDs are the
lexical order of canonical surface strings.

`scores.bin` begins with `NKSCORE1`, the same count, and one little-endian signed
`int32` score per candidate.

### Prefix tries

`surface.trie` and `aliases.trie` begin with `NKTRIE1\0`. Each node stores
sorted Unicode-codepoint edges and up to `max_suggestions` candidate IDs. The
candidate list is materialized at every prefix node, so the Android runtime
does not scan descendants during a keystroke.

The binary layout is little-endian:

```text
header:  8-byte magic, uint32 nodes, uint32 edges, uint32 values,
         uint16 max_suggestions, uint16 reserved
node:    uint32 first_edge, uint16 edge_count,
         uint32 first_value, uint16 value_count
edge:    uint32 Unicode scalar, uint32 child_node
value:   uint32 candidate_id
```

The Android reader should memory-map the bundle members after extraction,
traverse one code point per input step, and resolve returned IDs through the
candidate offset table. Android builds, emulator tests, and benchmarks run on
the `cdjk` Ubuntu host under the repository host-safety policy.
