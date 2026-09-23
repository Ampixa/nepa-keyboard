# Production keyboard architecture

Date: 2026-07-15

## Product goal

Nepa Keyboard should support every language or named variety for which the
project has a usable dictionary. This is an internal product, so source-license
or redistribution status does not rank or block language coverage, packs,
layouts, builds, benchmarks, emulators, or internal APKs. The audited catalog
currently has 33 language/variety targets across nine output scripts.

Public/export packaging is a separate, fail-closed downstream lane. It may use
only the subset whose redistribution requirements have been satisfied, but it
must never reduce or reorder the internal product catalog.

English and Nepali are the architecture proof, not the final scope. A profile
is the explicit combination:

```text
language or variety + output script + input method + exact runtime artifact
```

This lets one language expose direct and Roman input without pretending they
are separate languages, and lets Limbu or Nepal Bhasa expose multiple output
scripts without merging their evidence. A runtime artifact may be a dictionary
pack or a strict conversion map; the profile must declare which provider owns
it.

The first public beta target is two languages and two output scripts: English
in Latin and Nepali in Devanagari. The long-term catalog is currently 33 named
language/variety targets across nine scripts. A catalog entry becomes a
production-supported keyboard only after its dictionary, layout/input method,
native review, quality evaluation, and runtime evidence pass; raw resource
presence is not a support claim.

## What to learn from Gboard

The useful model is behavioral, not a copy of proprietary code, models, or
visual assets:

1. **The basics are immediate and reliable.** Google describes Gboard first in
   terms of speed and reliability, before optional modes such as glide, voice,
   and handwriting. The keyboard must appear before large dictionaries load.
2. **Languages are independent of the phone language.** A user adds a keyboard
   language and layout without changing Android's display language.
3. **Switching is always close.** Gboard supports a visible language key and a
   long-press on space. Nepa Keyboard uses tap-to-cycle plus a long-press sheet
   listing enabled profiles.
4. **The candidate strip is stable chrome.** Prediction engines may differ by
   language, but selection behavior and placement do not.
5. **The layout follows the field.** Numeric, phone, password, URL, and normal
   text fields require different behavior. Suggestions must never read or show
   password content.
6. **Language management scales.** Enabling a language and selecting the
   current language are separate actions; unavailable profiles state their
   gating reason instead of silently failing.

Official behavior references:

- [Gboard language setup and switching](https://support.google.com/gboard/answer/7068494?hl=en)
- [Gboard Play listing](https://play.google.com/store/apps/details?id=com.google.android.inputmethod.latin)
- [Android IME implementation guide](https://developer.android.com/develop/ui/views/touch-and-input/creating-input-method)

The broader source and literature review is recorded in
[`../reports/keyboard-reference-research-v0.md`](../reports/keyboard-reference-research-v0.md).
It audits pinned AOSP-derived, FlorisBoard, AnySoftKeyboard, Indic Keyboard,
and Keyman implementations plus published touch, transliteration,
code-switching, and personalization research. No external code or language
data was imported.

The resulting next-runtime decisions are:

1. keep the native, offline, exact-hash pack boundary and explicit profile
   identity;
2. replace language-specific Java layout arrays with a compiled declarative
   layout and contextual-Unicode-transform artifact;
3. preserve touch coordinates and let a cancellable N-best decoder combine
   spatial, dictionary, transliteration, and ranking evidence;
4. retain literal input as a candidate and require confidence evidence before
   any future silent correction;
5. keep first personalization local, erasable, and excluded from private
   fields; and
6. finish per-key virtual accessibility semantics, remotely validate the modal
   picker behavior, and obtain physical TalkBack/lifecycle evidence before
   calling any profile production-supported.

## Android module boundaries

| Module or boundary | Responsibility |
|---|---|
| `ime-app` | `InputMethodService`, field-aware keyboard UI, setup, language picker, profile state |
| `pack-runtime` | Verification and bounded lookup for release `.nkp` bundles |
| `KeyboardProfile` | Language, script, input method, layout, and availability identity |
| `SuggestionEngine` | Profile-specific prediction boundary; must return nothing for private fields |
| `LanguagePreferences` | Atomic enabled, active, and pending-platform profile state with safe fallback |
| `AndroidSubtypeRegistry` | Exact generated profile-to-platform subtype identity and API-specific synchronization |

`ComposingSession` owns the exact token emitted by this keyboard. It does not
reconstruct words by reading arbitrary text before the cursor. The profile's
`LookupKind` selects surface-prefix or Roman-alias lookup independently of the
visual `LayoutKind`.

The application declares no internet permission. It must not log keys, text
around the cursor, candidates, or password-field content.

## First architecture proof

| Profile | Current behavior | Gate |
|---|---|---|
| `eng-Latn-US` | Direct QWERTY, composing, and release-pack surface prediction | Ranking/user review and physical-device evidence remain |
| `npi-Deva-NP` | Direct Devanagari composing and release-pack surface prediction | Speaker review and physical-device evidence remain |
| `npi-Latn-Deva-NP` | Declared but not selectable | Requires a reviewed casual-Roman alias pack and quality evidence |

The cumulative internal engineering lane additionally selects Limbu direct,
Dhimal Devanagari direct, Sunuwar Devanagari direct, and Western Tamang
Devanagari direct, plus Lohorung Devanagari direct with a reviewed
terminal-ZWNJ input policy and Yakkha Devanagari direct with independently
audited terminal-ZWNJ and closed intra-word punctuation policies. Nepal Bhasa
adds direct Devanagari, direct Prachalit/Newa, Romanized-to-Devanagari, and
Devanagari-to-Newa conversion profiles. Khaling and Dumi add independently
measured direct Devanagari packs; Dumi also proves an attested intra-word colon
contract plus visarga and glottal-stop input. These
profiles prove the data-driven expansion architecture; their open speaker,
quality, accessibility, glyph, and physical-device gates prevent that
selectability from being mistaken for production support.

Candidate taps now replace the active composing span. Literal input is committed
on space, punctuation, Enter, or profile change; v0 performs no silent
autocorrection. The source now also has the first asynchronous decoder-v1
boundary: each request binds the exact activation, immutable profile/layout,
generation, monotonic deadline, and cancellation token; a bounded latest-wins
worker invokes the exact NKP or NCM provider off the IME thread; typed N-best
results contain an explicit literal candidate; and stale, cancelled, expired,
or wrongly-owned provider results cannot reach the strip. Candidate commits
retain exact query ownership. Spatial Tap Decoder v1 now preserves versioned
keyboard-local touch geometry and performs a bounded nearby-key surface-prefix
search for direct
English and Nepali. Programmatic/accessibility clicks explicitly remain
non-spatial, correction candidates never auto-commit, and the raw token remains
available. A shared debug/internal instrumentation now benchmarks the exact
production English/Nepali decoder path for exact, clean-center, and boundary
requests while retaining staged-artifact and compiled-layout identity. Canonical
API 34 software-emulator build, instrumentation, and benchmark evidence passed
for the 14 internal profiles; physical-device and quality evidence remain
open. See
[`android-decoder-contract-v1.md`](android-decoder-contract-v1.md).
Public/export builds generate exact-hash bindings for the
reviewed English and Nepali packs; internal builds independently bind every
profile selected by the cumulative internal lock. Missing, corrupt, or
mislabeled data fails the build or produces no candidates. Artifact
verification runs off the IME thread. The IME distinguishes inactive, loading,
ready, verified-no-match, missing, integrity-rejected, and transiently
unavailable states instead of treating every condition as an empty candidate
list. A fresh
process-local activation token is issued for every field/profile preparation,
including two successive fields using the same profile. Background completion
may reuse an immutable verified artifact for the current token, but an old token,
query, candidate list, or failure UI cannot cross a field or profile boundary.
Only the active profile's provider artifact remains resident.

Language selection uses a persisted `enabled/active/pending` reducer. Exact
Android subtype observations win when there is no newer product request and
auto-enable that profile for quick switching. Globe, picker, Settings, and
active-disable fallback selections remain pending until Android confirms the
same generated subtype. Locale-only, removed, or malformed subtype state never
falls back silently to English. Generated subtype IDs are deterministic and
collision-checked; runtime resolution also requires the profile extra, language
tag, keyboard mode, and installed IME identity to agree. API 28+ uses the
service switch API, API 26-27 uses the attached IME-window token compatibility
path, and API 34+ mirrors the product-enabled set through Android's managed
subtype API. Platform failure never disables literal typing.

An internal-only compatibility harness hosts a real editor and observes the
bound service. It drives the live picker and globe controls, records the
branch-derived legacy-window-token or service-API dispatch outcome, enforces
pending/dispatch/platform callback order, waits for pending-state clearance and
post-callback live-view convergence, and compares the full API 34 managed
subtype set without filtering unknown rows. Canonical API 34 execution passed,
and the focused legacy-window-token compatibility path passed on API 26/27;
physical-device evidence remains open. Same-IME
profile changes are
accepted only after Android delivers the subtype callback to the retained
service, the pending product request clears, and the live view shows the exact
profile; a service restart is not expected for a subtype change within the
current IME.

Script presentation is explicit where the platform baseline is insufficient.
Pinned API 26/27 system-font inspection found native Limbu coverage but no
Newa coverage, so Newa keys, suggestions, and picker text select a bundled
exact-hash `Noto Sans Newa` typeface. The selector is code-point-aware and
restores the normal system typeface for recycled non-Newa views. Focused
font/glyph/geometry renders passed on API 26, 27, and 34; see
[`../reports/android-newa-font-fallback-v1.md`](../reports/android-newa-font-fallback-v1.md).

Literal typing, composition, deletion, and commit never depend on pack state.
Loading and failure status occupies the candidate area without masquerading as
a candidate: transient I/O exposes an exact-token retry, while missing or
integrity-rejected data offers the existing language picker. A verified lookup
with no result says only that there is no dictionary suggestion; it is not a
claim that the typed word or language is invalid.

Installed pack provenance is user-visible through a non-exported, virtualized
Settings surface. Its lightweight internal reader verifies the artifact,
manifest, bounded notice member, release mode, and provenance structure without
loading the prediction indexes. The separate public/export reader may
additionally enforce approval metadata. Links are delegated to another app;
Nepa Keyboard retains no internet permission.

The final clean-APK API 34 software-emulator proof measured warm
full-suggestion P95 at 6.953 ms for English and 5.270 ms for Nepali. Those
results prove the v0 lookup shape, not physical-device production latency.
Cold verified open took 70.060 s and 10.830 s under TCG, so first-candidate
latency on representative phones is a
mandatory unresolved gate. See
[`../reports/android-release-packs-v0.md`](../reports/android-release-packs-v0.md).

## Definition of production-usable

The architecture is production-usable when the signed keyboard can be dogfooded
as a daily IME, not merely when layouts render. For the first English/Nepali
release this means:

1. every bundled dictionary is deterministic, provenance-recorded, SHA-pinned,
   and rejected if corrupt or mislabeled;
2. composing, replacement, deletion, editor actions, language switching, and
   private-field behavior pass service-bound tests on representative physical
   Android phones;
3. keyboard startup remains responsive while packs load, suggestion lookup is
   below the physical-device latency budget, and memory stays bounded;
4. English and Nepali layouts, ranking, correction, and Roman aliases have
   native/user review against curated evaluation cases;
5. accessibility, themes, screen sizes, rotation, setup, backup exclusion,
   crash recovery, update/rollback, signing, and store delivery are verified;
6. the app requests no network access and records no typed text telemetry; and
7. adding another language is a generated profile/pack operation that must pass
   the same gates, not a fork of the IME.

## Language picker contract

The launcher Activity uses the observable, resumable first-run model documented
in [android-first-run-setup.md](android-first-run-setup.md). Enablement and
selection come from the exact Android IME state, language readiness comes from
the actual enabled-profile set, and completion additionally requires an edit in
the non-persistent test field. There is no durable setup-complete flag, and a
platform regression returns the user to the first unmet step.

- Tapping the globe cycles enabled profiles.
- Long-pressing the globe or space opens an in-keyboard picker.
- The picker keeps fixed close/management actions around a bounded scrolling
  list of enabled profiles.
- The setup Activity uses a searchable `ListView` for the full generated
  catalog. Its source recycles holder-backed rows with stable IDs and saves the
  query plus first-visible position/offset across renders and instance-state
  recreation.
- The setup activity enables or disables profiles and prevents a zero-language
  state.
- Product selections update the exact Android subtype; a system selection of a
  known disabled subtype enables and activates it instead of being ignored.
- Profiles missing usable data, a compiled layout, or required quality evidence
  remain visible but disabled with an explicit reason.
- Adding a language must not require a new IME service or a fork of the UI.

The in-keyboard picker source exposes selected-row semantics, removes the
underlying keyboard from touch, hardware-focus, and accessibility interaction
while open, moves focus to its title, and restores the prior invoking-control
focus and tree state on close. Suggestion-status messages use a polite live
region. Candidate results deliberately do not auto-announce their changing
parent on every keystroke; every visible candidate remains a separately
focusable, labelled action, and hidden slots clear stale accessibility labels.
The remote-only service-bound harness now covers held-delete cancellation on a
normal-to-password restart, IME hide, and editor finish through the real IME
view and a wrapped editor `InputConnection`; it also gates on zero private
context reads. Canonical API 34 execution passed the retained-service subtype,
managed-enabled-set, focus, privacy, and post-cancellation dispatch contracts.
API 26/27 passed the applicable legacy subtype, focus, privacy, and
post-cancellation dispatch contracts; physical TalkBack/Switch Access evidence
remains pending. See
[`../reports/android-api26-27-compat-v1.md`](../reports/android-api26-27-compat-v1.md).
The
maximum-enabled attached-row scroll/recycling case passed on the API 34
software emulator but still needs physical accessibility review.

## Production gates

Before a profile is called supported, it needs:

1. A deterministic, provenance-recorded dictionary pack or versioned
   conversion artifact appropriate to the method.
2. A versioned layout or input-method specification.
3. Native-speaker review and at least 300 curated input-to-target cases.
4. Prefix recall, top-three accuracy, collision, coverage, and keystroke-saving
   evidence appropriate to the input method.
5. Sub-10 ms P95 suggestion lookup on a reference physical phone.
6. Bounded load time and memory, corrupt-artifact recovery, and rollback.
7. Field-aware behavior, accessibility review, and no typed-text telemetry.

An optional public/export artifact additionally requires its own redistribution
and notice checks. Those checks are not internal product-readiness gates.

The same profile contract is generated for all 74 cataloged input methods, but
generation and internal engineering selectability are not support claims. The
public/export lane selects English and direct Nepali. The cumulative internal
lane currently selects those two plus Limbu, Dhimal, Sunuwar, Western Tamang,
Lohorung, Yakkha, Khaling, Dumi, Nepal Bhasa Devanagari direct, Nepal Bhasa
Prachalit/Newa direct, Romanized Nepal Bhasa to Devanagari, and Nepal Bhasa
Devanagari-to-Prachalit conversion; the other 60 profiles remain visible and
blocked. At the target level, 11 of the 22
dictionary-backed languages or named varieties now have a selectable direct
profile, leaving 11 dictionary-backed
targets to implement.

An internal profile may become engineering-selectable after its deterministic
pack or converter, exact layout, and validation vectors are bound. API-level
emulator evidence is then required before its Android milestone is considered
validated.
Speaker, quality, accessibility, glyph, and physical-device gates remain
explicitly open until production support is earned. Android derives staging,
validation vectors, generated system subtypes, picker/migration counts, and
smoke/benchmark cases from that reviewed lock. The layout generator also emits
a bounded, exact-hash runtime-conformance asset for every selectable profile;
instrumentation verifies every runtime field, all four rendered-layer
fingerprints, stable-key dispatch, picker selection/persistence, and agreement
with the pack or conversion vectors without adding cohort-specific binding
boilerplate. A missing or conflicting runtime-artifact binding fails before
packaging, and alias profiles must declare a non-empty alias index.

## Declarative layout boundary

The first layout-v1 compiler now represents the existing English QWERTY and
direct Nepali phone layouts as reviewed JSON and emits one deterministic lock.
The layout input script is distinct from the candidate output script, so the
Latin QWERTY layout can later serve Romanized Nepali without sharing profile or
dictionary identity. Selectable profile bindings are checked against the exact
shipping-profile lock and must match input scripts.

V1 is a behavior-preserving migration, not a complex-script readiness claim.
It supports four complete layers, stable positional key IDs, integer geometry,
explicit accessibility text and language-picker holds, plus bounded exact
suffix transforms. Android rejects transforms until its keyboard-owned
composing transform runtime is implemented. Character popups, general joiner
input beyond the closed Devanagari conjunct and terminal-ZWNJ policies,
and tablet geometry remain later-version work. Backspace v1 implements a
separate bounded runtime deletion contract; its API-level and physical-editor
evidence remains open. See
[`layout-format.md`](layout-format.md).
