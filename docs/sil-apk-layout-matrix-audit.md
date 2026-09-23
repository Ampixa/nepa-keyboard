# SIL-APK layout-matrix audit

`tools/run_cdjk_sil_apk_layout_matrix.sh` compares one catalog-pinned SIL-APK
dictionary with every compiled Devanagari layout in the canonical internal
layout lock. It is a remote-only compatibility audit, not a layout selection
or language-quality judgment.

## Run on cdjk

The five positional arguments are the catalog target ID, catalog resource ID,
absolute canonical raw JSONL path, source tag, and a new absolute evidence
directory outside the checkout. The evidence directory's parent must already
exist.

Khaling is the next target. The preferred command is the Khaling-specific
sequence runner:

```sh
ssh cdjk 'cd /home/cdjk/github/llm/nepa-keyboard && \
  bash tools/run_cdjk_khaling_measurement.sh \
    /home/cdjk/data/nepa-keyboard/khaling-measurement-20260716-v1'
```

That runner first executes the default internal relock transaction and requires
its committed success evidence. It then runs the layout matrix against the
installed lock bytes, proves that the matrix did not change either internal
lock or the Android internal pins, and emits one recursive manifest over both
child evidence trees. A successful relock remains the valid active internal
state if the later matrix fails; rerun with a new evidence directory after
fixing the matrix failure.

Dumi is queued second, but its runner cannot execute before the successful
Khaling evidence above exists and verifies byte-for-byte. It takes that
completed evidence as a required first argument and a new Dumi evidence path as
the second:

```sh
ssh cdjk 'cd /home/cdjk/github/llm/nepa-keyboard && \
  bash tools/run_cdjk_dumi_measurement.sh \
    /home/cdjk/data/nepa-keyboard/khaling-measurement-20260716-v1 \
    /home/cdjk/data/nepa-keyboard/dumi-measurement-20260716-v1'
```

The Dumi runner verifies the recursive Khaling manifest, success status, exact
Khaling sequence summary, and raw identity before it can relock or invoke the
matrix. It then pins `dus`, `dus-apk`, `dus-Deva-NP`, `dus-deva-direct`, and the
canonical Dumi JSONL identity. Before measurement it requires the Dumi profile
to remain unselectable, unbound to a pack, and on its pending layout. The first
successful run is also the strict remote parse proof for Dumi's SIL-APK rows.
Neither runner selects a layout, joiner policy, prefix vector, or promotion
from its measured ranking.

Bantawa follows Dumi in the Rai/Kiranti sequence, but it is not a SIL-APK
resource and must not be passed to this matrix. Its Dumi-gated first-parse lane
is documented in [`bantawa-source-probe.md`](bantawa-source-probe.md). That
probe stops at ordered JSON field/type and per-field scalar evidence; a
Bantawa-specific adapter and format-neutral layout matrix come only after the
report is reviewed.

The lower-level matrix command remains available for other resources or after
an independently verified relock:

```sh
ssh cdjk 'cd /home/cdjk/github/llm/nepa-keyboard && \
  bash tools/run_cdjk_sil_apk_layout_matrix.sh \
    klr \
    klr-apk \
    /home/cdjk/github/llm/rai-speech-toolkit/dialects/western/khaling/dict/nepali-khaling.sil-apk.dict.jsonl \
    sil-apk/khaling \
    /home/cdjk/data/nepa-keyboard/khaling-layout-matrix-20260716-v1'
```

The matrix runner refuses non-cdjk/non-Ubuntu hosts, serializes against the shared
Android/validation lock, checks host capacity and competing workloads, and
never creates or updates a catalog, profile lock, layout lock, or review. It
requires the existing internal layout lock to rebuild byte-for-byte before it
enumerates layouts. Each audit independently repeats the canonical-lock check.

The raw filename, record count, byte count, and SHA-256 must match the exact
catalog target/resource binding. Layout IDs are selected by
`input_script == "Deva"` and sorted before execution.

## Evidence and interpretation

The new evidence directory contains:

- `audits/<layout-id>.json`: the complete auditor report for every Devanagari
  layout;
- `layout-matrix-summary.json`: a jq-generated compatibility ranking;
- `catalog-binding.json`, `raw-input.json`, `layout-ids.txt`, source hashes,
  host preflight, and per-layout logs;
- `run-status.txt`: fail-closed completion state; and
- `final-evidence-sha256.txt`: recursively discovered, path-sorted SHA-256
  bindings for all evidence files except the manifest itself.

The summary uses the auditor's terminal-ZWNJ inventory as a common comparison
basis. It sorts by reachable distinct surfaces descending, missing input scalar
count ascending, recognized layout-policy failure rows ascending, then layout
ID. These measurements only identify input-access gaps against this dictionary.
They do not prove orthographic suitability, native-speaker preference,
ergonomics, prediction quality, or production readiness.

After a layout and row-acceptance policy have been selected explicitly from
this evidence, the remote-only
[`run_cdjk_sil_apk_candidate_pack.sh`](../tools/run_cdjk_sil_apk_candidate_pack.sh)
can double-build and inspect an unpromoted candidate pack. See
[`sil-apk-candidate-pack.md`](sil-apk-candidate-pack.md). The candidate runner
does not infer the measured target's layout or terminal-ZWNJ policy from the
ranking.
