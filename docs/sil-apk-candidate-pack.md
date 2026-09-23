# SIL-APK candidate-pack runner

`tools/run_cdjk_sil_apk_candidate_pack.sh` turns one exact, current
layout-audit result into deterministic candidate-pack evidence. It builds the
source tables and NKP twice, compares both builds byte-for-byte, and runs an
explicit list of prefix inspections against both packs. The same remote
transaction first runs the focused adapter policy/determinism/drift test and
records its output.

This is an exploratory internal lane. It does not call the milestone finalizer,
does not edit a profile review or lock, and does not make a support claim. The
runner hashes the resource catalog, internal profile review, internal profile
lock, and internal layout lock before and after the run and fails if any of
them changes.

## Scope

The adapter accepts only the strict SIL Dictionary App Builder JSONL contract
implemented by `tools/sil_apk_jsonl_internal_source.py`: ordered `lang`,
`headword`, `ne`, `en`, and `source` fields, with the language and source tag
matching the catalog binding. Among the 14 dictionary-backed targets that are
not yet internally selectable, the catalog shape currently identifies:

- Khaling: `klr` / `klr-apk`, with an already identified canonical raw path;
- Dumi: `dus` / `dus-apk`, whose first strict remote parse must still prove
  that its rows satisfy the same contract before any candidate claim.

Lohorung and Yakkha use the same contract but already have promoted,
language-pinned adapters. Resources such as Western Magar and Mid-Eastern Tharu
use TSV despite their `*-apk` resource IDs; they must not be passed to this
runner. The other remaining dictionary targets likewise retain their own
source-format and cleanup requirements.

## Measured candidate specification

Run the layout matrix first. Then create a JSON specification that pins the
chosen audit bytes, raw bytes, measured layout ID, explicit row-acceptance
policy, and exploratory prefixes:

```json
{
  "adapter_sha256": "<sha256-of-build-sil-apk-candidate-source.py>",
  "claim_scope": "candidate_only",
  "compiler_sha256": "<sha256-of-src-nepa-keyboard-compiler.py>",
  "data_version": "1.0.0",
  "format_version": 1,
  "inspection_vectors": [
    {
      "expected_first_surface": "<reviewed-surface-1>",
      "prefix": "<reviewed-prefix-1>"
    }
  ],
  "layout_audit_sha256": "<sha256-of-one-matrix-audit>",
  "layout_id": "<measured-layout-id>",
  "max_suggestions": 8,
  "policy": "<conjunct_only-or-terminal_zwnj>",
  "raw_sha256": "<catalog-pinned-raw-sha256>",
  "resource_id": "klr-apk",
  "runtime_sha256": "<sha256-of-src-nepa-keyboard-runtime.py>",
  "source_tag": "sil-apk/khaling",
  "target_id": "klr"
}
```

The specification is parsed with duplicate-key rejection and has an exact field
set. It pins the language adapter, pack compiler, and prefix reader in addition
to the audit and raw input. Prefixes must be unique, non-empty, free of control
characters, and no longer than 128 Unicode scalars. Every vector also pins a
non-empty expected first surface, so an empty or merely deterministic lookup
cannot pass. The
policy is never inferred from the presence of terminal ZWNJ rows. Both
`conjunct_only` and `terminal_zwnj` are measurements in the audit; choosing one
for a candidate is a separate, explicit input.

## Run on cdjk

All four paths must be absolute. The raw file, audit, and specification must be
canonical regular files. The evidence directory must be new, outside the
checkout, and on a filesystem with at least 2 GiB free.

```sh
ssh cdjk 'cd /home/cdjk/github/llm/nepa-keyboard && \
  bash tools/run_cdjk_sil_apk_candidate_pack.sh \
    /home/cdjk/github/llm/rai-speech-toolkit/dialects/western/khaling/dict/nepali-khaling.sil-apk.dict.jsonl \
    /home/cdjk/data/nepa-keyboard/khaling-layout-matrix-20260716-v1/audits/<measured-layout-id>.json \
    /home/cdjk/data/nepa-keyboard/khaling-candidate-spec-v1.json \
    /home/cdjk/data/nepa-keyboard/khaling-candidate-pack-v1'
```

Do not replace `<measured-layout-id>`, the tool hashes, policy, or expected
surfaces until the matrix and candidate rows have been inspected. The runner
re-executes the exact audit in `--check` mode and verifies all three pinned
candidate tools, so a stale audit, layout lock, compiler, runtime reader,
helper, adapter, catalog, or raw dictionary fails before the candidate build.

## Evidence

Successful evidence includes:

- `selected-layout-policy-measurement.json`, preserving the selected audit row
  and both the layout identity and terminal-ZWNJ delta;
- `test-sil-apk-candidate-source.txt`, proving the focused adapter contract on
  the remote Python runtime;
- `a/` and `b/`, containing independently generated source trees, NKPs,
  compiler reports, member inventories, and integrity checks;
- `inspections/` and `inspection-summary.jsonl`, with identical results from
  both packs and the expected first result for every explicit prefix;
- `promotion-state-before.txt` and `promotion-state-after.txt`, which must be
  byte-identical;
- `candidate-pack-summary.json`, which states `profile_promoted: false`;
- `run-status.txt` and a recursive `final-evidence-sha256.txt`.

Candidate evidence can inform a later language-specific adapter, query set,
layout, and milestone spec. It cannot promote a profile by itself.

The shared validation lock is acquired before an atomic evidence-directory
claim. A competing invocation therefore cannot write failure status into the
winner's evidence tree.
