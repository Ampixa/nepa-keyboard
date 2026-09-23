# Western Magar TSV source-contract probe

Western Magar Devanagari direct is the next dictionary-backed target after the
completed Bantawa source measurement. Its first milestone measures the pinned
TSV as it exists; it does not choose keyboard semantics or promote the pending
profile.

## Exact scope

The probe pins:

- target `mrd`;
- resource `mrd-apk`;
- pending profile `mrd-Deva-NP`;
- direct input method `mrd-deva-direct`;
- raw file
  `/home/cdjk/github/llm/nllb-better/data/lexicons_apk/mrd_nep_lexicon.tsv`;
- 1,264 TSV records and 68,724 bytes; and
- SHA-256
  `d55d34e4c4d754ee1bbcf3382f3250690e53884020c06305e34bfc1a7948591a`.

`tools/audit_western_magar_tsv_contract.py` runs under Python 3.14 with Unicode
data 16.0.0. It requires the exact header `mrd_headword`, `nepali_gloss`, and
`english_gloss`, three columns per row, 1,264 data rows, UTF-8, LF termination,
and no implicit null representation. For each ordered column it records the
index and a deterministic string/scalar inventory. Its report also binds the
pending profile and records neutral scalar-emission coverage for every
Devanagari layout in the internal layout lock. That coverage does not select a
layout. The report leaves the candidate and headword columns, filtering,
normalization, joiner handling, layout, prefix vectors, a pack, and profile
promotion unselected.

The runner separately verifies the exact `mrd-apk` catalog metadata and the
pending `mrd-Deva-NP` profile state. It records hashes for the auditor, resource
catalog, internal profile lock, internal layout lock, raw input, and runner.

## Run after Bantawa

The runner accepts a completed immutable Bantawa evidence directory and a new
Western Magar evidence directory. Both paths must be absolute and canonical,
outside the checkout, and the new directory must be outside the prerequisite
tree.

```sh
ssh cdjk 'cd /home/cdjk/github/llm/nepa-keyboard && \
  bash tools/run_cdjk_western_magar_source_probe.sh \
    /home/cdjk/data/nepa-keyboard/bantawa-source-probe-20260716-v1 \
    /home/cdjk/data/nepa-keyboard/western-magar-source-probe-20260716-v1'
```

Before recursively traversing the prerequisite, the runner acquires the shared
cdjk validation lock and checks memory, disk, emulators, build processes, heavy
Python work, and high-RSS processes. It then rejects links and special nodes in
the entire Bantawa tree, recreates and compares its complete manifest, verifies
every listed file, compares the exact successful run status, and validates the
path-bound Bantawa sequence summary and report identity. The complete Bantawa
manifest is preserved in the new evidence, and the manifest, status, summary,
and report hashes are captured.

The focused synthetic auditor suite runs on cdjk first. The Western Magar
auditor then runs twice into `a/` and `b/`; the reports must match
byte-for-byte. A third `--check` pass must reproduce the first report. The test
suite is itself hash-bound with every other runtime input, and the complete
Bantawa tree is rechecked before the final sequence summary is written.

Successful evidence includes both reports and their logs, host preflight,
before/after input hashes, the preserved and independently recreated Bantawa
manifests, exact prerequisite hashes, a fail-closed `run-status.txt`, a
path-bound `sequence-summary.json`, and a recursive
`final-evidence-sha256.txt`. Finalization rejects links and special nodes in the
new evidence tree before recording success.

## Stop boundary

The completed report is measurement evidence, not a keyboard adapter. Review
its TSV shape, per-column text inventory, script and scalar coverage,
normalization deltas, whitespace, controls, format characters, and joiner
contexts before selecting any candidate surface or row policy. Layout work,
prefix vectors, candidate-pack construction, profile promotion, Android
build/runtime validation, and language-quality review remain later, separate
milestones.
