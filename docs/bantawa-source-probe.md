# Bantawa JSONL source-contract probe

The next dictionary-backed Rai/Kiranti target after Khaling and Dumi is
Bantawa Devanagari direct. Its canonical dictionary is structured JSONL, but it
does not use the reviewed SIL-APK filename or row contract. The first milestone
therefore inventories the raw schema without choosing keyboard semantics.

## Exact scope

The probe pins:

- target `bap`;
- resource `bap-dictionary`;
- pending profile `bap-Deva-NP`;
- direct input method `bap-deva-direct`;
- raw file
  `/home/cdjk/github/llm/rai-speech-toolkit/dialects/central/bantawa/dict/bantawa-english.dict.jsonl`;
- 2,040 JSONL records and 360,086 bytes; and
- SHA-256
  `a69917c00e7a8587f4a38458faf89c95fc9e5ac9cbe6cfb612383438bdf5ae12`.

`tools/audit_bantawa_jsonl_contract.py` requires Python 3.14 with Unicode data
16.0.0. It rejects symbolic input files, invalid UTF-8, BOMs, carriage returns,
missing final LF, blank rows, duplicate keys at any object depth, non-object
rows, and non-finite numbers. It aggregates every exact ordered field and type
signature, then inventories direct strings and string-array elements for each
field independently. The inventory includes JSON types, array-element types,
distinct/nonempty values, NFC and whitespace deltas, script coverage, controls,
format characters, joiner contexts, complete scalar frequencies, and bounded
deterministic examples.

The report explicitly leaves the candidate/headword field, filters,
normalization, joiner policy, layout, prefix vectors, pack, and promotion
unselected. The `bap-romanizer` resource is outside this direct source probe.

## Run after Dumi

The runner takes a completed Dumi measurement tree and a new Bantawa evidence
directory. Both paths must be absolute and canonical, outside the checkout,
and the new directory must not be inside the prerequisite tree.

```sh
ssh cdjk 'cd /home/cdjk/github/llm/nepa-keyboard && \
  bash tools/run_cdjk_bantawa_source_probe.sh \
    /home/cdjk/data/nepa-keyboard/dumi-measurement-20260716-v1 \
    /home/cdjk/data/nepa-keyboard/bantawa-source-probe-20260716-v1'
```

Before any recursive evidence work, the runner acquires the shared cdjk
validation lock and checks host headroom and competing workloads. Before reading
Bantawa content, it then recreates and compares the complete Dumi evidence
manifest, rejects prerequisite symlinks, compares the exact successful Dumi
status, validates its path-bound sequence summary, and captures the prerequisite
hashes. It verifies the pinned Bantawa catalog resource and pending-profile
fields without claiming the complete catalog as a separate expected snapshot.

The focused synthetic auditor suite runs remotely. The raw probe then runs
twice into `a/` and `b/`, the canonical reports must compare byte-for-byte, and
`--check` must reproduce the first report. Catalog, profile lock, layout lock,
and Android pin hashes must stay unchanged. Finally, the complete Dumi tree and
captured hashes are rechecked before the Bantawa sequence summary can be
completed.

Successful evidence contains the two reports, focused test and probe logs,
host preflight, source/state hashes, Dumi prerequisite checks, a fail-closed
`run-status.txt`, `sequence-summary.json`, and a recursive
`final-evidence-sha256.txt`. The finalizer rejects symbolic links and special
filesystem nodes anywhere in the new evidence tree before recording success.

## Stop boundary

Do not infer a native candidate field from its name, script mix, or the first
row. Review the ordered schema, per-field types, script/scalar coverage,
normalization deltas, and joiner contexts from the completed report. Only then
may a Bantawa-specific adapter pin a native surface and row policy. Layout
measurement, prefix vectors, candidate-pack construction, profile promotion,
Android build/runtime validation, and language-quality review are later,
separate milestones.
