# Android cancellable decoder contract v1

Date: 2026-07-16  
Status: source and canonical API 34 cdjk emulator evidence passed; focused API
26/27 service compatibility also passed; physical-editor latency and quality
evidence pending

## Contract now present in source

`ComposingSession` dispatches one immutable `SuggestionQuery` for the exact
keyboard-owned token. The request captures:

- the process-local field/profile `SuggestionActivation` by identity;
- the immutable `KeyboardProfile`, exact profile ID, compiled layout ID,
  positive layout revision, and compiled layout-source SHA-256;
- the composing token, monotonically increasing request generation, creation
  time, and monotonic deadline;
- a process-local cancellation token; and
- an optional immutable `TouchSequence` aligned exactly with the composing
  token and versioned layout identity.

Private fields cannot construct a bounded decoder request. The service also
skips dispatch for private and non-predictive fields, and the generic and NKP
provider entry points retain defensive rejection before lookup.

The production service now uses `SuggestionEngine.submit`, never its synchronous
compatibility method. `NkpSuggestionEngine` queues lookup on one named decoder
worker with capacity for only the running request and the latest queued request.
Submission performs bounded validation and queue insertion; normalization, trie
lookup, candidate resolution, and result construction run off the IME thread.
Pack opening uses a separate bounded latest-wins worker, so obsolete queued
profile loads cannot accumulate ahead of the current profile.
Decoder lookup holds an identity-based bundle lease. Profile switching retires
the old bundle immediately from catalog ownership, while physical close waits
for the last non-cooperative in-flight lookup to release its lease.
The deadline includes queue time. The main handler arbitrates completion and a
50 ms timeout, and a timeout immediately preserves the literal-only snapshot.
The API rejects budgets above 250 ms and decoder submissions above 64 code
points or 256 UTF-16 units.

Each edit, delete, commit, field transition, profile transition, retry, and
superseding request cancels the preceding token and queued/running future.
`Future.cancel(true)` is cooperative: correctness never depends on work stopping
immediately. A non-cooperative hung provider cannot mutate the UI, although it
would occupy the sole decoder worker and delay the latest queued request.

`SuggestionSnapshot` owns the exact request object and exposes an immutable,
bounded N-best list of at most three `SuggestionCandidate` values. Categories
are `LITERAL`, `EXACT`, `DICTIONARY`, `TRANSLITERATION`, and `CORRECTION`.
`CORRECTION` is API vocabulary only: it grants no commit behavior, and the
keyboard still performs no automatic correction.

## Spatial Tap Decoder v1

English direct and Nepali direct now have a bounded spatial-prefix path in
source. A real text-key `MotionEvent` snapshots normalized keyboard-local key
bounds and the up coordinate. The snapshot contains no window/screen
coordinate, has at most 64 text keys, and is tied to the source layout ID,
revision, source hash, and render generation. Programmatic and accessibility
clicks remain fully operable but explicitly record non-spatial provenance; the
IME never fabricates a center point for them.

Every composing edit preserves touch evidence only while each emitted key
stroke remains exactly aligned with the token. Joiner buffering, failed editor
updates, incompatible deletion, field/profile transitions, commits, and other
ambiguous transformations discard the evidence and safely fall back to exact
prefix lookup.

For each spatial stroke the decoder considers at most three compatible word
keys. It keeps at most 16 deterministic beams and looks up at most eight NKP
surface IDs per beam. The literal selected-key path is retained even when it
would otherwise fall outside the beam. A zero-cost clean exact path is protected
from lexical override. When every stroke has real spatial provenance at exactly
zero selected-key cost and the exact beam can fill both provider slots, the
decoder publishes the identically ranked exact-beam hits after one capped trie
lookup. Sparse or missing exact results retain the full correction path, as do
mixed, non-spatial, off-center, and boundary sequences. The fallback beam builder
computes each stroke's three alternatives once instead of once per incoming
beam; this changes no candidates or ranking. Outside the clean center case,
ranking combines fixed-point
tap cost with a signed log2 bucket of the pack score and trie rank; this bounds
the influence of differently scaled int32 pack scores while allowing a strong
nearby-key word to beat a weak boundary hit. A nearby-key path is labeled
`CORRECTION`, while the raw composing token remains the one explicit `LITERAL`
candidate. Suggestion lookup cannot replace or commit editor text.

The focused platform acceptance uses the staged English and Nepali bundles. It
checks clean-prefix parity for `hell` and `नमस्`, nearby-key recovery while
preserving raw `jell` and `ममस्`, the 16-beam ceiling, real down/up capture, and
non-spatial click provenance. The center-tap non-regression matrix covers nine
English and six Nepali staged-pack prefixes using the compiled physical key IDs
and full rendered geometry. Both correction vectors also traverse
`ComposingSession` and the off-main NKP worker. These are deterministic contract
vectors, not a claim of corpus-level correction quality.

Real-pack provider and ranking checks use an activation-bound functional-test
query with no wall-clock deadline. This prevents unaccelerated emulator speed
from turning correct provider output into an expired literal-only fallback.
The instrumentation also proves that this query type is rejected by the
one-argument production decoder API and the asynchronous production queue.
Production deadline semantics remain separate and strict: bounded and
controlled async tests retain the 250 ms maximum, reject late provider output,
and require an expired result to contain only the literal candidate.
Both focused instrumentations allow up to 300 seconds for a cold NKP loader to
become ready under unaccelerated TCG. This is a fail-closed test-setup ceiling,
is emitted as evidence, and does not alter product query deadlines or block
literal typing while a pack loads.

The same MotionEvent-derived vectors are shared with
`SpatialDecoderBenchmarkInstrumentation`. That harness times the production
provider and ranking path through `NkpSuggestionEngine.suggest` for English and
Nepali across three request shapes: empty-touch exact prefix, clean-center
spatial prefix, and boundary correction. Its functional query is deliberately
unbounded so the harness measures and reports slow results instead of dropping
them at the production deadline; an optional P95 budget remains independently
enforceable. It captures strokes before timing and records P50/P95/P99/max/mean
latency, allocation and GC deltas, Java heap and process PSS observations, beam
counts, and the exact staged pack and compiled layout identities. The existing
`benchmark-app` remains the lower-level NKP reader/trie benchmark; no spatial
decoder is duplicated there.

Every accepted, query-owned, non-inactive snapshot contains exactly one
`LITERAL` candidate whose text is byte-for-byte the composing token. The strip
binds each button to the exact `SuggestionQuery` and `SuggestionCandidate`, not
only its displayed string. A stale accessibility or click action therefore
cannot commit a candidate from an older generation. Queryless presentation
snapshots and direct legacy calls remain test compatibility APIs and do not gain
the production field-ownership guarantee.

The session accepts provider candidates only when all of these remain true
after lookup:

1. the result owns the exact request object and activation;
2. the request object and numeric generation are still current;
3. the activation owns the exact immutable profile object captured at activate;
4. its cancellation token is not cancelled; and
5. provider work completed before its monotonic deadline.

A stale, cancelled, null, wrongly-owned, or late callback leaves the newer
snapshot untouched. A current provider result that crosses its deadline, or a
provider runtime failure, leaves a ready literal-only fallback. The service
sets its destroyed state before closing workers, and every posted callback
rechecks lifecycle and exact request ownership. These are responsiveness and
presentation-safety rules, not decoder-quality evidence.

## Current providers

`NkpSuggestionEngine` retains the verified exact-prefix path and adds Spatial
Tap Decoder v1 for the English-direct and Nepali-direct profile IDs. Exact
surface-prefix results are `EXACT`, alias-prefix results are
`TRANSLITERATION`, spatial nearby-key results are `CORRECTION`, and raw input
is `LITERAL`. Spatial ranking combines bounded normalized tap distance with
the authoritative NKP trie order and stored candidate score. It does not yet
use preceding words, neural language models, personalization, or calibrated
confidence.

Because NKP v0 does not retain the alias-adjusted effective score, the adapter
exposes a descending provider-local ordinal for returned UI results instead of
mislabeling the base dictionary score as the query score. Scores are not
calibrated across providers.

## Backspace v1 interaction

Deletion still cancels the exact active suggestion generation before changing
text. Source now deletes one Android-ICU grapheme from keyboard-owned
composition and removes every touch stroke aligned with that deleted suffix;
ambiguous alignment discards spatial evidence, and retained Devanagari or Newa
text rebuilds its script-tail state after a confirmed editor update. The Newa
action boundary removes a resolved U+11442 + ZWJ/ZWNJ + consonant continuation,
including attached marks, without exposing the joiner; bare conjunct input
still unwinds consonant and virama taps separately. Private/non-composing Newa
input suppresses the buffered joiner because the privacy fallback cannot read
context safely. With no active composition and a known collapsed cursor, the
editor adapter may inspect at
most 64 UTF-16 units immediately before the cursor for that delete operation
only. The value is not retained and cannot enter a `SuggestionQuery`; private
fields use the no-read, one-code-point fallback. A known selection is replaced
without reading its contents. Its selection snapshot is consumed before the
editor mutation, so an immediate second press or held repeat cannot reuse the
old selected range; until a fresh editor callback arrives, it uses the
no-context delete-key compatibility path. Unknown selection state uses that
same path. Null, short, truncated, unsupported, or rejected editor behavior
also falls back. A successful commit fallback after a partial composing delete
rebuilds the retained Devanagari tail exactly as the composing-text path does.

The rendered delete key dispatches once on down and holds at a fixed bounded
cadence through one generation-owned callback. Owning-pointer release, cancel,
layer/profile rerender, explicit IME lifecycle cancellation, and detach stop
it. Programmatic and accessibility clicks remain one-shot. Shared
debug/internal vectors cover Latin combining text, Nepali matras and
conjunct/joiner sequences, Newa ZWJ/ZWNJ buffering and marked continuations,
clipped Newa context, unrelated-ZWJ boundaries, supplementary scalars, emoji
ZWJ family, modifier and regional-indicator sequences, CRLF, selection,
short/truncated context, fallback/private isolation, suggestion/touch
ownership, pointer ownership, and view cancellation. Service lifecycle calls
are exercised by a real bound-IME harness that starts a held delete and then
restarts the editor as a password field, hides the IME, or finishes the editor.
Once the IME main thread observes lifecycle cancellation, a monotonic dispatch
sequence must remain unchanged for a full repeat interval. Repeats that occur
before the delayed main loop observes cancellation are not mislabeled as
post-cancellation failures. The password connection wraps the real editor
`InputConnection` and counts context reads. API 34, 26, and 27 passed
cancellation, post-cancel dispatch stability, and zero-private-read checks;
physical-editor evidence remains pending. The old-API evidence is in
[`../reports/android-api26-27-compat-v1.md`](../reports/android-api26-27-compat-v1.md).

The provider reserves at most two N-best slots for unique NKP results and one
for literal input. If an NKP surface exactly equals the raw token, the literal
candidate owns that text so the result remains unique and explicitly literal.

This establishes the contract needed for broader spatial quality evaluation,
dictionary, transliteration, context, and personalization providers. It does
not claim that Romanized Nepali is quality-ready or that autocorrection is
safe.

## Remote acceptance and canonical API 34 evidence

Do not build or run this validation on the Mac. After checking `free -h`, disk,
and relevant Gradle/emulator processes on cdjk, sync the repository without
`--delete` and run the static acceptance there:

```sh
cd /path/to/nepa-keyboard
python3 -m unittest tests.test_android_decoder_contract
```

With JDK 17, the cached Gradle 8.11.1 distribution, Android SDK variables, and
the exact staged pack directory already used by the catalog validation, run
sequentially with at most two workers:

```sh
cd android
"$GRADLE" --offline --no-daemon --max-workers=2 \
  -PnepaDebugPackDir="$PACKS" \
  :ime-app:assembleDebug :ime-app:lintDebug
```

The focused instrumentation source is shared only by the `debug` and `internal`
build types; it is absent from `release`. Install the debug APK on the inspected
cdjk API 34 emulator and run it directly:

```sh
adb -s "$SERIAL" install --no-streaming -r -t \
  ime-app/build/outputs/apk/debug/ime-app-debug.apk
adb -s "$SERIAL" shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime/\
com.ampixa.nepakeyboard.ime.DecoderContractInstrumentation
```

Acceptance requires `status=ok`, result code `-1`, the twenty-two core decoder
flags below, and the fourteen Backspace/input-policy flags in the second block:

```text
decoder_contract_verified=true
literal_candidate_verified=true
stale_result_rejection_verified=true
expired_result_fallback_verified=true
nkp_exact_prefix_provider_verified=true
functional_query_api_isolation_verified=true
async_decoder_off_main_verified=true
async_decoder_controlled_release_verified=true
async_decoder_deadline_outcome_verified=true
async_spatial_deadline_outcome_verified=true
private_field_provider_isolation_verified=true
candidate_query_binding_verified=true
nkp_ordinal_provider_score_verified=true
profile_object_identity_verified=true
async_decoder_latest_wins_verified=true
spatial_touch_provenance_verified=true
spatial_functional_provider_verified=true
spatial_deadline_outcome_separated_verified=true
spatial_english_prefix_verified=true
spatial_nepali_prefix_verified=true
spatial_bounded_beam_verified=true
spatial_clean_exact_fast_path_verified=true
```

The same result bundle must report
`instrumentation_pack_ready_timeout_ms=300000`.
The canonical TCG runner records a 1,800-second outer contract timeout in
`decoder-contract-run-profile.txt`. That outer bound safely contains the four
serial instrumentation-only pack-readiness phases, each of which remains
fail-closed at 300 seconds; it does not change the product request deadline.

```text
backspace_grapheme_vectors_verified=true
backspace_owned_composition_verified=true
backspace_committed_context_verified=true
backspace_fallback_verified=true
backspace_sink_private_no_read_verified=true
backspace_suggestion_touch_ownership_verified=true
backspace_zwj_tailoring_verified=true
backspace_devanagari_state_rebuild_verified=true
newa_conjunct_joiner_verified=true
backspace_selection_contract_verified=true
backspace_context_completeness_verified=true
delete_repeat_timing_verified=true
delete_touch_pointer_ownership_verified=true
delete_repeat_view_cancellation_verified=true
```

Run the production spatial benchmark on the same installed APK. Emulator
results establish a regression baseline and do not enforce a phone-latency
claim:

```sh
adb -s "$SERIAL" shell am instrument -w -r \
  -e iterations 1000 \
  -e warmups 100 \
  com.ampixa.nepakeyboard.ime/\
com.ampixa.nepakeyboard.ime.SpatialDecoderBenchmarkInstrumentation
```

Acceptance requires two profiles; clean-center parity; `jell` → `hello` and
`ममस्` → `नमस्कार` correction; one unchanged literal per result; every spatial
beam count in `1..16`; clean-center fast-path eligibility with boundary
full-path retention; and nonnegative latency, allocation, GC, heap, and PSS
observations. A physical reference-device run can additionally enforce the
initial interaction budget with `-e iterations 10000 -e warmups 1000 -e
maxP95Ns 10000000`. The canonical unaccelerated cdjk lane uses the minimum
supported 1,000 measured iterations and 100 warmups per metric: this is enough
for TCG regression characterization and leaves the 10,000/1,000 profile for a
physical reference device. Allocation and memory regression budgets must be
based on observed physical-device evidence rather than invented before the
first baseline.

The canonical internal catalog runner invokes both focused instrumentations
against the actual internal runtime-artifact catalog and fails unless all 36
decoder and Backspace/input-policy flags plus the nine spatial-benchmark
correctness flags are present:

```sh
tools/run_cdjk_internal_catalog_validation.sh /absolute/new/evidence-directory
```

The runner records separate deterministic source-input hash manifests for the
internal IME and raw-prefix benchmark APKs. It fails if any inspected module
source, manifest, shared pack reader, or relevant Gradle input is newer than
the APK that supplies its evidence. This is a stale-artifact guard, not a
substitute for the clean outer cdjk build.

The canonical API 34 chain passed on cdjk for all 14 internal profiles. The
runtime-v2 catalog contains 13 NKP bindings backed by 12 unique packs plus one
NCM converter. Its report and 119-entry manifest are
[`dumi-internal-android-milestone-v0.md`](../reports/dumi-internal-android-milestone-v0.md)
and
[`evidence/dumi-internal-android-v0`](../reports/evidence/dumi-internal-android-v0/).
The evidence includes the 14-profile IME smoke, focused NCM routing checks,
decoder contract, retained-service subtype/lifecycle harness, spatial
benchmark, 13-binding prefix benchmark, conversion benchmark, and 17 NKP
corruption cases. API 26/27 service compatibility passed; representative
physical-device editor, memory, accessibility, quality, and latency evidence
remain open. NCM cancellation/race and corruption matrices also remain open. Emulator
measurements do not enforce the physical-phone latency gate.

Candidate presentation has a separate script-font invariant. Newa text uses
the app's exact bundled `Noto Sans Newa` face because pinned API 26/27 system
images do not cover `U+11400`; Limbu continues to use the registered platform
font on those images. Internal instrumentation pins the font bytes, verifies
Newa key and candidate typeface selection and glyph coverage, and records
1080-pixel renders on API 26, 27, and 34. See
[`../reports/android-newa-font-fallback-v1.md`](../reports/android-newa-font-fallback-v1.md).
