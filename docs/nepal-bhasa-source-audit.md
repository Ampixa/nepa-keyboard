# Nepal Bhasa dual-TSV source audit

Nepal Bhasa is the next multi-script architecture track. The first milestone
audits the two pinned Devanagari lexicons together in one deterministic
transaction, while keeping their schemas and measurements separate. It does
not merge their rows or choose keyboard candidates.

## Exact inputs

The audit pins these independent resources:

- `new-nepali-trilingual`: header `newar<TAB>nepali`, 9,708 data rows,
  543,567 bytes, and SHA-256
  `4167c21626674fd1e71bd814c6b2bbb33d2d35ab0f5d5bb071b7b43e071d7929`;
- `new-apk-english`: header
  `newar<TAB>english<TAB>transliteration`, 5,727 data rows, 404,596 bytes,
  and SHA-256
  `470be5aaf526d2dca973044fa5ca9a69b4259854958456145661bd58d4889b41`.

On cdjk the canonical raw paths are expected under:

```text
/home/cdjk/github/llm/nllb-better/data/lexicons_pdf/new_nepali_trilingual.tsv
/home/cdjk/github/llm/nllb-better/data/lexicons_apk/new_apk_eng_lexicon.tsv
```

The audit records exact row shape, empty and duplicate values, normalization
and whitespace deltas, script and scalar inventories, controls and format
characters, joiner contexts, multiword cells, semicolon-bearing cells, and
transliteration-column coverage. Duplicate examples are bounded, while full
duplicate-group counts and deterministic digests make the complete result
verifiable. It also records exact raw overlap, including empty strings,
between the two columns named `newar`; separate nonempty counts and full-set
digests keep that source comparison explicit. The overlap is not a merged
candidate vocabulary.

## Four separate keyboard products

The catalog already distinguishes four Nepal Bhasa profiles, and this audit
must not collapse them:

1. `new-Deva-NP`: direct Devanagari input and output;
2. `new-Newa-NP`: direct Newa/Prachalit Nepal Lipi input and output;
3. `new-Latn-Deva-NP`: Romanized input to Devanagari through reviewed aliases;
4. `new-Deva-Newa-NP`: explicit Devanagari-to-Newa script conversion.

Both dictionaries in this milestone use Devanagari headword columns. They do
not constitute an attested Newa-script dictionary. Converted forms must remain
identified as generated until independently reviewed or attested.

## Execution boundary

`tools/audit_nepal_bhasa_tsv_contract.py` requires Python 3.14 with Unicode
data 16.0.0. Full-file parsing and the double-run determinism check execute on
cdjk, not on the orchestration Mac. The remote runner binds the raw files,
catalog, profile and layout locks, auditor, focused tests, report hashes, and
unchanged project state into one fail-closed evidence tree.

From the canonical cdjk checkout, choose a new evidence directory outside the
repository and run:

```sh
cd /home/cdjk/github/llm/nepa-keyboard
bash tools/run_cdjk_nepal_bhasa_source_audit.sh \
  /home/cdjk/data/nepa-keyboard/source-audits/nepal-bhasa-20260716-v1
```

The runner refuses a reused or noncanonical evidence path, concurrent Android
or corpus work, insufficient host headroom, and any input drift. Success ends
with `nepal_bhasa_source_audit_complete` and a `run-status.txt` whose completed
stage is `complete`, whose sequence flag is `1`, and whose exit statuses are
zero. The evidence manifest recursively binds both generated reports, logs,
summary, status, and the before/after source hashes.

## Historical stop boundary

The source audit leaves all of these decisions unset:

- candidate-resource and candidate-column selection;
- semicolon alternative splitting;
- row filters and normalization policy;
- direct Devanagari or Newa layout selection;
- joiner/conjunct policy;
- Roman alias generation;
- Devanagari-to-Newa conversion policy;
- prefix vectors, pack identity, and profile promotion.

Those were the deliberate stop conditions of the source-audit transaction;
they are not the current implementation status. Subsequent isolated milestones
now provide:

- the direct `new-Deva-NP` pack and layout, recorded in
  [`reports/nepal-bhasa-internal-android-milestone-v0.md`](../reports/nepal-bhasa-internal-android-milestone-v0.md);
- the attested 2,318-surface Unicode Newa/Prachalit pack and
  repertoire-complete internal layout, recorded in
  [`reports/nepal-bhasa-newa-internal-android-milestone-v0.md`](../reports/nepal-bhasa-newa-internal-android-milestone-v0.md);
- the measured Roman-to-Devanagari alias layer, recorded in
  [`reports/nepal-bhasa-roman-internal-android-milestone-v0.md`](../reports/nepal-bhasa-roman-internal-android-milestone-v0.md); and
- the frozen mechanical Devanagari-to-Newa source, strict NCM runtime, and
  canonical API 34 acceptance, recorded in the
  [converter milestone](../reports/nepal-bhasa-deva-newa-internal-android-milestone-v0.md),
  [`reports/nepal-bhasa-deva-newa-internal-map-v0.json`](../reports/nepal-bhasa-deva-newa-internal-map-v0.json),
  and the [input-method status audit](nepal-bhasa-input-reference-audit.md#devanagari-to-newa-conversion-boundary).

These remain four products. In particular, converted output is generated
Unicode Newa text, not an attested dictionary surface, and none of these
milestones claims Ranjana input or output.
