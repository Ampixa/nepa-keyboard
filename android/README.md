# Android runtime v2

The Android project contains four deliberately separate modules:

- `pack-runtime`: a UI-independent Java reader for deterministic v0 `.nkp`
  bundles.
- `conversion-runtime`: a UI-independent strict reader for canonical v1
  `.ncm` conversion maps.
- `benchmark-app`: a platform-instrumentation APK for correctness checks and
  prefix-lookup and conversion measurements.
- `ime-app`: the product-shaped `InputMethodService`, generated language
  layouts, setup flow, and scalable language picker.

The generated IME registry contains all 74 reviewed input-method identities
across 33 language/variety targets and nine scripts. The public/export lock
selects English QWERTY and direct Nepali Devanagari. The cumulative internal
lock selects those two plus Limbu direct, Dhimal Devanagari direct, Sunuwar
Devanagari direct, Western Tamang Devanagari direct, and Lohorung Devanagari
direct, plus Yakkha, Nepal Bhasa Devanagari direct, Romanized Nepal Bhasa to
Devanagari, Nepal Bhasa Prachalit/Newa direct, and Nepal Bhasa Devanagari-to-
Prachalit conversion, plus Dumi Devanagari direct; the other 60 identities
remain visible but disabled with
explicit readiness reasons. Catalog presence never grants a runtime-artifact
binding. The internal boundary contains 13 NKP profile bindings backed by 12
unique packs and one NCM binding, for 14 selectable profiles in total. The app
has no internet permission. Each
build derives one exact artifact binding per selectable profile from its
complete SHA-pinned lock, and the public build cannot stage internal-only
artifacts.

Text fields use an explicit composing session. Candidate selection replaces the
active token, while space and ordinary punctuation commit literal input without
silent autocorrection. A closed layout policy may keep exactly hyphen, slash,
backslash, or colon inside an existing keyboard-owned token; it cannot start a
token or chain repeated punctuation. Password and other non-predictive fields
bypass composition and provider lookup. A routing engine activates exactly one
SHA-pinned NKP or NCM provider and loads it asynchronously. The public/export
variant uses the public NKP reader; the internal product uses the verified
internal NKP and NCM readers. Provider readiness refreshes the candidate strip
on the IME thread. Leaving a field suspends prediction without reparsing the
same retained artifact on the next ordinary field.

The composing boundary now submits immutable, cancellation-owned decoder
requests to a bounded latest-wins active-provider worker, with exact
activation/profile/layout identity, a generation, and a monotonic deadline.
The IME thread publishes the literal path immediately and never performs trie
lookup. Main-handler completion and timeout arbitration reject cancelled,
wrong-generation, late, or wrongly-owned results. Candidate buttons retain the
exact query and typed candidate binding. NKP remains an exact-prefix provider
with ordinal provider-local scores; NCM remains a complete-token mechanical
conversion provider. Neither is an autocorrect or language-quality claim.
Canonical API 34 software-emulator acceptance passed for the 14-profile
internal catalog. The focused real-editor service and held-delete lifecycle
harness also passed on API 26 and 27; physical-device evidence remains open.
See [`../docs/android-decoder-contract-v1.md`](../docs/android-decoder-contract-v1.md)
and [`../reports/android-api26-27-compat-v1.md`](../reports/android-api26-27-compat-v1.md).

Newa/Prachalit labels do not rely on Android's system-font set. The app bundles
one exact `Noto Sans Newa` resource and selects it only for visible strings
containing Newa code points, including keys, suggestions, and recycling picker
rows. A read-only audit found no Newa font on the pinned API 26/27 images while
confirming their native Limbu font. Exact-font, glyph, geometry, and PNG render
instrumentation passed on API 26, 27, and 34. See
[`../reports/android-newa-font-fallback-v1.md`](../reports/android-newa-font-fallback-v1.md).

Inside the keyboard, tapping the globe cycles enabled profiles. Long-pressing
the globe or space opens a bounded, recycling `ListView` picker; the language
chip in the candidate strip opens the same picker. The setup Activity uses
recycler-safe row types and holders, collision-checked stable profile IDs, and
searchable filtering. It captures the query and first-visible position/top offset across
full-view renders and saved-instance restoration, exposes all reviewed blocked
reasons, versions preferences against the generated catalog, and prevents the
last profile from being disabled.

The full manager sorts matching profiles into three stable sections: Enabled,
Available to enable, and Later. “Available” is the generated selectable state
with an exact pack or conversion-artifact binding, not a claim that the
runtime artifact has already loaded. Runtime failures remain visible through
the keyboard suggestion state. Section rows retain the language/variety
grouping and generated sort-key order. The in-keyboard picker intentionally
remains a fast enabled-only list.
Internal instrumentation disables one selectable profile and requires the
picker IDs to equal the remaining enabled set while excluding that profile and
every Later profile.

Globe and space also publish one localized Android accessibility long-click
action labeled “Choose language.” Invoking that node action follows the same
real long-click path into the picker; the ordinary key description and tap
dispatch remain unchanged. Debug and internal smoke instrumentation cover the
English and Nepali base layers, absence on shift, picker open/close, and
profile-rerender freshness. The attached internal case also requires input
focus to leave the invoking globe while the picker is open and return to that
same key after close. The canonical 14-profile API 34 run passed these cases;
physical assistive-technology review remains required.

The setup header is an observable, resumable five-step flow: enable the exact
Nepa IME, select it as Android's default, keep at least one selectable language,
test a real edit, and complete. It observes Android and profile state instead
of persisting a completion flag, never saves test text, and returns to the
first unmet step after a platform regression. API 26/27 service-bound subtype
and held-delete lifecycle acceptance passed; physical accessibility acceptance
remains open.

The in-keyboard picker source marks the active row selected, blocks underlying
keyboard touch and hardware focus, hides background descendants from
accessibility while open, and assigns a pane title and heading on supported
APIs. Generation-guarded callbacks move focus to the title and restore the
invoking control on close; external Manage/Other actions close without stealing
focus back. Suggestion-status changes use a polite live region. These manager
and modal changes passed the canonical API 34 instrumentation, including the
attached focus case; physical assistive-technology evidence remains open.
Rapid candidate changes explicitly avoid parent live-region announcements on
every key; each visible candidate is
instead a distinct focusable action with an exact spoken label, and hidden
slots clear stale labels when a shorter result set replaces them.

Language state is persisted as an enabled set plus active and pending-platform
profiles. Generated Android subtypes have deterministic collision-checked IDs
and exact profile/language-tag bindings. System selections auto-enable the
chosen profile; globe, picker, Settings, and active-disable fallback selections
request Android's matching subtype and stay pending until confirmed. API 28+
uses `InputMethodService.switchInputMethod`, API 26-27 uses the attached IME
window token, and API 34+ mirrors the product-enabled set through the managed
subtype API. A failed platform switch leaves literal typing operational.

The exact-hash layout generator emits a bounded
`assets/nepa-conformance/runtime-v2.json` projection for every selectable
profile. Internal instrumentation verifies the asset hash, both source-lock
hashes, every exposed runtime field, four complete rendered-layer
fingerprints, stable-key dispatch, picker selection/persistence, and exact
agreement with generated pack and conversion vectors. Language-specific
Unicode regressions remain explicit alongside this scalable routine coverage.

The reader verifies the outer artifact SHA-256 when supplied, requires
ZIP-STORE members, verifies every required member's declared size and SHA-256,
checks format and release metadata, and validates all binary table bounds and
references before lookup.

## Pack-reader authorities

The isolated public/export entry point uses:

```java
NkpBundle pack = NkpBundle.open(packFile, expectedSha256);
```

That entry point rejects every `release_mode=internal` bundle. The internal
product uses the verified internal-reader entry point through its internal
variant; this is not an implementation or validation gate for internal packs.

The legacy single-pack benchmark still requires an explicit adb opt-in. The
catalog benchmark instead has separate public and internal instrumentation
entry points over one shared exact-hash harness.

Both Gradle staging authorities validate the archive/member allowlist,
metadata identity, candidate count, source provenance, and notice integrity.
Only the separate public/export authority interprets provenance as approval;
internal staging does not. Supplying a pack directory does not replace the
shared integrity checks.

## Build on cdjk

Android builds and emulation are remote-only. The shipping IME now targets API
36 and uses Android Gradle Plugin 8.12.2, which requires JDK 17, Gradle 8.13,
and an SDK containing `platforms;android-36`. The prior cached Gradle 8.11.1
command is historical and must not be used for a release candidate. Use the
pinned Gradle 8.13 installation on `cdjk`, then set `GRADLE` to that
exact executable and use `$HOME/Android/Sdk` until API 36 is also installed in
`$HOME/android-sdk`. The current host paths are
`$HOME/gradle-8.13`, `/usr/lib/jvm/java-17-openjdk-amd64`, and
`$HOME/Android/Sdk`.

Relock the internal catalog and layouts first when their inputs change. This
default command touches only the internal locks and their four Gradle pins;
see [`../docs/cdjk-relock-validation.md`](../docs/cdjk-relock-validation.md).

```sh
bash tools/run_cdjk_relock_validation.sh \
  /home/cdjk/data/nepa-keyboard/relock/internal-20260716-v1
```

```sh
cd android
GRADLE="$HOME/gradle-8.13/bin/gradle"
PACKS=/home/cdjk/data/nepa-keyboard/release-packs/20260715-v2/a
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
ANDROID_HOME="$HOME/Android/Sdk" \
ANDROID_SDK_ROOT="$HOME/Android/Sdk" \
  "$GRADLE" --offline --no-daemon --max-workers=2 \
  -PnepaDebugPackDir="$PACKS" \
  :pack-runtime:assembleDebug \
  :benchmark-app:assembleDebug \
  :ime-app:assembleDebug \
  :pack-runtime:lintDebug \
  :benchmark-app:lintDebug \
  :ime-app:lintDebug
```

Build and inspect the product release boundary separately:

```sh
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
ANDROID_HOME="$HOME/Android/Sdk" \
ANDROID_SDK_ROOT="$HOME/Android/Sdk" \
  "$GRADLE" --offline --no-daemon --max-workers=2 \
  -PnepaReleasePackDir="$PACKS" \
  :ime-app:assembleRelease \
  :ime-app:lintRelease
```

Compile and lint the full internal-product Play candidate separately. This
does not require signing material and is the reproducible pre-signing gate:

```sh
PACKS="$HOME/nepa-release-inputs/current"
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
ANDROID_HOME="$HOME/Android/Sdk" \
ANDROID_SDK_ROOT="$HOME/Android/Sdk" \
  "$GRADLE" --offline --no-daemon --max-workers=2 \
  -PnepaInternalPackDir="$PACKS" \
  :ime-app:compileCandidateJavaWithJavac \
  :ime-app:lintCandidate \
  :ime-app:lintInternal
```

Run `:ime-app:bundleCandidate` only after ignored
`android/keystore.properties` points to the owner-approved permanent upload
key. Candidate bundling fails closed when that signing configuration is absent.

The release APK must contain neither `ImePreviewActivity` nor
`ImeSmokeInstrumentation`, must request no permissions, and must contain
exactly
`nepa-packs/{eng-Latn-US.nkp,npi-Deva-NP.nkp,manifest.json,benchmark-vectors.json}`
plus
`nepa-layout-notices/{manifest.json,ampixa-layouts-mit.txt,xkb-data-2.41-2ubuntu1.1.copyright}`
with the reviewed hashes. Omitting `nepaReleasePackDir` intentionally fails the
release build. A debug build without `nepaDebugPackDir` remains dictionary-
packless but retains the required layout notices.

The generated profile and layout tasks pin the complete reviewed lock hashes.
They refuse a changed lock even if it is otherwise parseable, then revalidate
the compilers, schemas, sources, evidence hashes, notices, exact
profile/artifact bindings, and runtime layout limits before generating Java,
system subtypes, or assets. Public/export generation additionally evaluates
redistribution approval; internal generation records provenance without using
it as a gate.

## Licenses and attributions

Every pack already embeds compiler-verified source rows in `notices.json`. The
bounded reader verifies the outer artifact, manifest, notice member, release
mode, provenance structure, and notice fields without loading candidates or
tries. The Settings Activity links to a non-exported, virtualized notice list
with per-source details and external source/license actions. Only the separate
public/export reader additionally treats approval metadata as a release rule.

The internal variant routes the same screen through
`readNoticesForInternalCatalog`. It keeps the artifact, member, mode, and core
source-provenance checks, accepts internal catalog provenance without a public
approval decision, and treats absent source/license links as optional UI data.

Declarative layout notices use a separate bounded manifest tied to the exact
layout-lock SHA and an independently generated exact manifest-byte hash. The
runtime requires exact generated-layout membership, safe unique asset paths,
strict UTF-8 without BOM, and matching manifest/notice hashes before it
displays any layout attribution. Compiler and Gradle also reserve the generated
`manifest.json` name and enforce the same notice-filename alphabet.

The app itself still requests no internet permission. A pack whose notice
member, artifact hash, release mode, provenance structure, or pack identity
does not verify is omitted rather than displayed as trusted. Emulator evidence
and the public/export-only Wikimedia attribution review are documented in
[`../reports/android-pack-notices-v0.md`](../reports/android-pack-notices-v0.md).
That review does not constrain internal packs or language rollout.

## IME smoke instrumentation

The debug APK includes a platform-only harness. Wait for the emulator user to
reach `RUNNING_UNLOCKED`, then run:

```sh
adb -s emulator-5556 install --no-streaming -r -t \
  ime-app/build/outputs/apk/debug/ime-app-debug.apk

adb -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime/\
com.ampixa.nepakeyboard.ime.ImeSmokeInstrumentation
```

The same debug APK exposes a focused decoder-contract entry point:

```sh
adb -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime/\
com.ampixa.nepakeyboard.ime.DecoderContractInstrumentation
```

It checks immutable request fields, exact profile-object ownership, typed and
ordinal provider metadata, the literal path, generation cancellation,
stale-result rejection, query-owned candidate commits, deadline fallback,
private-field isolation, functional-query isolation from both production entry
points, and a real staged English NKP submission whose callback completes off
the Android main thread.

The harness checks profile gates, language-state invariants, both key layers,
actual key-view callbacks, IME registration metadata, permission absence, and
offscreen English/picker/Nepali renders. It also checks incremental Unicode
composition, private-field bypass, profile transition, stale-candidate
rejection, and exact replacement through a real Android `InputConnection`.
The tokenized suggestion-state checks distinguish loading, ready, verified
no-match, missing, integrity rejection, and transient unavailability; prove
that literal typing remains available; require explicit transient retry; and
reject callbacks from a superseded same-profile field activation.
When release packs are staged it additionally forces cold materialization,
opens every selectable binding through the public/export reader, validates
IDs/hashes/counts/provenance, dispatches the reviewed surface/alias lookup vector,
verifies the lightweight notice reader and notices Activity, and proves
asynchronous profile switching. Current
release-pack evidence is in
[`../reports/android-release-packs-v0.md`](../reports/android-release-packs-v0.md).

## Internal service-bound subtype compatibility

The internal variant also contains a real-editor service harness. It clicks the
live picker row from English to Nepali and the live globe key back to English,
then requires the recorded product-pending event, actual platform dispatch
outcome, ordered exact Android subtype observation, cleared pending state, and
matching bound input-view profile. API 26/27 must record a non-null attached
IME window token and the legacy path. API 34 must record the service API, a
same-service subtype callback after each switch, and the full exact managed
enabled-subtype set with no unmapped or duplicate rows.

The full internal catalog runner includes this probe on API 34. Once the
already-built internal APK and an API-specific AVD exist on `cdjk`, the focused
remote-only runner can exercise one compatibility API without invoking Gradle:

```sh
tools/run_cdjk_subtype_compat_validation.sh \
  /absolute/new/evidence-directory avd-name 26
```

Use the same command with expected API `27` or `34`. The runner refuses non-
Ubuntu/non-`cdjk` hosts and `/Users` worktrees, requires 8 GiB available, rejects
pre-existing emulators, Android builds, heavy Python jobs, or an 8 GiB RSS
process, and enforces free-disk minima before wiping AVD user state. It waits
for an unlocked user. For API 26/27 it pins the stock image hashes, provisions
the Android timeout multiplier only in a disposable `-writable-system` AVD
overlay through `su 0`, round-trips the property bytes, and requires the
rebooted guest to expose the exact value. It requires
`INSTRUMENTATION_CODE: -1`, records the AVD configuration, emulator version,
device build fingerprints, IME/window/log evidence, and a fail-closed SHA-256
evidence manifest, then cleans up its emulator. The canonical API 34 `test_atd`
x86_64 software-emulator run passed and is recorded in
[`../reports/yakkha-internal-android-milestone-v0.md`](../reports/yakkha-internal-android-milestone-v0.md).
The exact-artifact API 26/27 runs passed and are recorded in
[`../reports/android-api26-27-compat-v1.md`](../reports/android-api26-27-compat-v1.md).
Pass `render-only` as a fourth argument to run the exact bundled-script font,
glyph-coverage, geometry, and PNG proof without depending on Launcher/SystemUI
focus. Full mode performs that proof after install before continuing into the
service-bound suite.

## Release prefix benchmark

Build `benchmark-app` with `nepaDebugPackDir`, install it, and invoke the
release-only instrumentation without an internal override:

```sh
adb -s emulator-5556 install --no-streaming -r -t \
  benchmark-app/build/outputs/apk/debug/benchmark-app-debug.apk

adb -s emulator-5556 shell am instrument -w -r \
  -e iterations 10000 \
  -e warmups 1000 \
com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.ReleasePrefixBenchmarkInstrumentation
```

The harness validates the generated manifest and review-bound vectors,
production-opens every selected pack, checks its reviewed first candidate, and
reports per-profile cold copy, verified load, PSS, and P50/P95/P99 surface or
alias lookup as declared. English keeps additional uppercase/negative checks.
Results and limitations are in
[`../reports/android-release-packs-v0.md`](../reports/android-release-packs-v0.md).

## Internal catalog prefix benchmark

Build `benchmark-app` with `nepaInternalPackDir`, install it on the remote API
34 emulator, and invoke the internal catalog entry point without a licensing
or reader-authorization flag:

```sh
adb -s emulator-5556 shell am instrument -w -r \
  -e iterations 10000 \
  -e warmups 1000 \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.InternalCatalogPrefixBenchmarkInstrumentation
```

It preserves the same manifest, artifact SHA, identity, candidate-count,
lookup, timing, and memory checks for all 13 NKP-bound profile bindings backed
by the 12 unique internal-catalog packs. Conversion-backed profiles are tested
by the separate harness below.

## Internal conversion benchmark

The same remotely built `benchmark-app` contains a correctness-first NCM
benchmark. It verifies the conversion manifest, exact artifact identity, all
review-bound positive and no-match vectors, and then measures complete-token
conversion:

```sh
adb -s emulator-5556 shell am instrument -w -r \
  -e iterations 10000 \
  -e warmups 1000 \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.ConversionCatalogBenchmarkInstrumentation
```

The canonical API 34 run verified one 165-rule NCM profile and all 15 vectors.
Its timing field named `asset_copy_and_sha_ns` currently covers asset copy;
SHA-256 verification and strict parsing occur inside `verified_load_ns`.
Conversion percentiles time only `NcmBundle.convert` after verified loading.

## Production spatial decoder benchmark

The debug/internal IME APK also contains a focused benchmark for the production
spatial provider and ranking path. It shares the English and Nepali MotionEvent
vectors with decoder-contract acceptance and measures empty-touch exact lookup,
clean-center spatial lookup, and boundary correction without reimplementing the
decoder in `benchmark-app`. Functional benchmark queries have no wall-clock
deadline so slow TCG results are measured rather than dropped; the decoder
contract separately enforces the production deadline and late-result fallback:

```sh
adb -s emulator-5556 shell am instrument -w -r \
  -e iterations 1000 \
  -e warmups 100 \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.SpatialDecoderBenchmarkInstrumentation
```

The report is written as `files/spatial-decoder-benchmark.json` in the IME app
data directory. The canonical API 34 JSON is
[`../reports/evidence/nepal-bhasa-internal-android-v0/internal-spatial-decoder-benchmark.json`](../reports/evidence/nepal-bhasa-internal-android-v0/internal-spatial-decoder-benchmark.json).
Emulator output is regression evidence only; the canonical cdjk runner uses
1,000 measured iterations and 100 warmups per metric and does not pass
`maxP95Ns`. On a physical reference phone, use 10,000 iterations, 1,000 warmups,
and add `-e maxP95Ns 10000000` to enforce the initial 10 ms P95 budget for every
exact, clean-center, and boundary path.
Cold pack readiness in these focused TCG instrumentations has a separate
300-second fail-closed ceiling, reported as `pack_ready_timeout_ms`; it does not
change the production request deadline or make the IME block while loading.
The decoder-contract wrapper uses a 1,800-second outer timeout so its four
serial readiness phases can each reach that explicit ceiling without the host
wrapper terminating an otherwise valid test early.

## Legacy internal benchmark

The internal benchmark pack is a generated, ignored asset. Stage it only on
the remote host and verify its hash before building:

```sh
install -m 0644 ../dist/npi-Deva-NP-pilot.nkp \
  benchmark-app/src/main/assets/benchmark.nkp
sha256sum benchmark-app/src/main/assets/benchmark.nkp
```

### Run the legacy harness on a remote emulator

Install with non-streaming adb when using the software-emulated test AVD:

```sh
adb -s emulator-5556 install --no-streaming -r -t \
  benchmark-app/build/outputs/apk/debug/benchmark-app-debug.apk
```

First confirm the benchmark gate remains closed:

```sh
adb -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.PrefixBenchmarkInstrumentation
```

Then run the internal benchmark with an explicit opt-in and expected artifact
hash:

```sh
adb -s emulator-5556 shell am instrument -w -r \
  -e allowInternal true \
  -e expectedSha256 \
  b219ccce305baf5472f45d639cd452cba8dcbd24dde2602073ce77e985d4c0aa \
  -e iterations 20000 \
  -e warmups 2000 \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.PrefixBenchmarkInstrumentation
```

The current measured evidence and its limitations are in
[`../reports/android-v0-prefix-benchmark.md`](../reports/android-v0-prefix-benchmark.md).

## Quality-gated Romanized Nepali benchmark

The Roman candidate uses a separate benchmark-only staging property. It passes
through the same exact-hash, member-integrity, identity, provenance, and quality
checks as product packs, but its generated assets are not yet attached to an
IME variant. `npi-Latn-Deva-NP` remains engineering-blocked by its unresolved
quality/evaluation and runtime-integration work, not by internal licensing.

Build on `cdjk` with the preserved candidate directory:

```sh
PACKS=/home/cdjk/data/nepa-keyboard/release-packs/20260715-v4-roman-model/a
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
ANDROID_HOME="$HOME/Android/Sdk" \
ANDROID_SDK_ROOT="$HOME/Android/Sdk" \
  "$GRADLE" --offline --no-daemon --max-workers=2 \
  -PnepaRomanCandidatePackDir="$PACKS" \
  :benchmark-app:assembleDebug \
  :benchmark-app:lintDebug
```

`nepaDebugPackDir` and `nepaRomanCandidatePackDir` are mutually exclusive for
one benchmark APK. Invoke the dedicated instrumentation on the remote emulator:

```sh
adb -s emulator-5556 install --no-streaming -r -t \
  benchmark-app/build/outputs/apk/debug/benchmark-app-debug.apk

adb -s emulator-5556 shell am instrument -w -r \
  -e iterations 10000 \
  -e warmups 1000 \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.RomanCandidatePrefixBenchmarkInstrumentation
```

The harness production-opens only pack SHA-256
`09eb5b7496855c94593dc3b71c47e44221d62c4def2f57b4aa0507e7d6edf05f`,
checks representative Roman and Devanagari lookups, and reports copy, verified
open, PSS, and P50/P95/P99 alias lookup. Results and the remaining quality gate
are in
[`../reports/nepali-roman-model-v0.md`](../reports/nepali-roman-model-v0.md).
