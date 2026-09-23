# Deterministic internal catalog/layout relock on cdjk

Run the default transaction whenever the internal resource catalog review, a
bound conversion source, an internal layout source, or one of the frozen audit
inputs changes without changing shared compiler or schema bytes. A shared
profile/layout compiler or schema change requires the combined transaction
below because both release and internal locks pin those inputs. The local Mac
is used only to edit and synchronize source. Python validation and all
generated-lock work run on `cdjk`.

The default internal transaction covers exactly these three source-controlled
outputs together:

- `catalog/internal-profiles.lock.json`;
- `layouts/internal/layouts-v1.lock.json`; and
- the four internal lock-hash pins in `android/ime-app/build.gradle.kts`.

It does not read, rebuild, check, install, compare, roll back, or repin the
public/export profile or layout locks. Internal product coverage is compiled
from engineering readiness; source metadata remains provenance and never gates
the internal transaction.

## Synchronize source

Synchronize the current source tree to
`/home/cdjk/github/llm/nepa-keyboard` without `--delete`. Exclude build output,
Gradle state, Python cache, and local Android SDK state. The remote checkout's
`android/local.properties`, cached wrapper distribution, and evidence paths
must survive synchronization.

Before running, verify that `tools/update_android_lock_pins.py` and
`tools/run_cdjk_relock_validation.sh` on `cdjk` match the local source bytes.
The pin updater also defaults to the internal scope; use `--scope all` only for
the explicit combined maintenance transaction below.

## Run the internal transaction

Choose a new evidence directory outside the source checkout. Never reuse or
delete a previous attempt:

```sh
cd /home/cdjk/github/llm/nepa-keyboard
bash tools/run_cdjk_relock_validation.sh \
  /home/cdjk/data/nepa-keyboard/relock/internal-20260716-v1
```

The runner refuses non-`cdjk` hosts, `/Users` worktrees, and evidence paths
inside the checkout (which could contaminate closed compiler inputs). It
records host headroom, rejects concurrent emulators, Gradle, heavy Python, and
high-RSS processes, and owns the same host lock as Android validation.

It then:

1. saves exact rollback copies of the two internal locks and the Gradle file;
2. requires identical conversion-artifact contracts in the review and lock
   schemas, validates the exact `new-Deva-Newa-NP` review binding, compiles its
   `.ncm` twice, compares the bytes, and checks the pinned SHA-256, 165-rule
   count, identity, scripts, and complete no-match policy;
3. builds the internal profile lock twice, compares the bytes, and requires
   exact bindings for direct Prachalit, Roman-to-Devanagari, and
   Devanagari-to-Prachalit alongside the preceding profiles; the converter must
   bind an NCM and no NKP;
4. before installing transaction outputs, compiles the isolated QWERTY-direct
   research candidate twice, validates the bound pending native-review packet
   twice, and cross-compares the embedded candidate evidence; this proves its
   109-key inventory, five critical missing scalars, 27 unresolved items, and
   no-profile-effect state;
5. installs the candidate internal profile lock and verifies it with `--check`;
6. builds the internal layout lock twice against the canonical profile path,
   compares the bytes, and requires exactly one Newa layout plus the exact
   `new-Newa-NP` profile binding; the public layout lock remains Newa-free;
7. installs the internal layout lock and verifies it with `--check`;
8. derives only the four Android internal pins from the two installed lock
   bytes;
9. runs the pin-updater unit suite, conversion compiler/source/vector tests,
   Android conversion-substrate checks, the focused Android internal-scope
   contract tests, the Khaling/Dumi measurement-runner sequencing and identity
   contracts, the neutral Bantawa source-probe contract, the dual-resource
   neutral Nepal Bhasa TSV audit contract, the isolated Newa research-layout
   contract, and the Bantawa-gated neutral Western Magar TSV source-probe
   contract, then independently re-enumerates and rehashes every immutable
   source input; and
10. commits the transaction only after every check passes.

Any failure after installation restores both original internal locks and the
original Gradle file. Public/export locks are outside the transaction and stay
byte-for-byte untouched. The evidence directory remains immutable diagnostic
input for the next attempt. A successful run ends with:

```text
relock_complete evidence=/absolute/evidence/path
```

and `run-status.txt` must contain:

```text
transaction_committed=1
rollback_exit_status=0
manifest_exit_status=0
remote_exit_status=0
```

`input-source-sha256.txt` covers the compilers, schemas, reviews, focused tests,
their Android source dependencies, documentation, and every internal
layout/notice source. It also derives the complete evidence-artifact path set
from the active profile reviews, so every report read by the profile compiler
is inside the same immutable inventory. `input-source-sha256.after.txt` is
generated after the
focused tests from a fresh directory enumeration and must compare byte-for-byte
with the initial inventory before the transaction can commit. Immutable inputs
are required to be disjoint from transaction outputs; the mutable Gradle pin
file is instead bound by original/installed hashes and pin-update/check
evidence. The cumulative locks do not embed the isolated
research review; the review is an independent fail-closed transaction guard.
The input inventory also includes every direct child of `layouts/research`;
those files are validated separately and never added to a cumulative source
lane. The inventory test rejects any direct child that is not a regular JSON
candidate and compiles each accepted candidate through the same imported
compiler. The deterministic Newa report is stored as
`a/newa-qwerty-direct-candidate.json` and compared with the independent `b`
run. The corresponding pending review report is stored as
`a/newa-qwerty-direct-native-review.json` and compared independently as well.
The candidate object embedded in each native-review report must also compare
byte-for-byte with the standalone candidate report. Both read-only guards run
before any transaction-managed file is installed.
`final-evidence-sha256.txt` then content-binds those source hashes, both compiled
NCM copies, the conversion schema projections, candidates, review packet,
checks, test logs, original files, installed hashes, pin results, and host
preflight.

## Combined shared-compiler/schema maintenance

The separate public/export boundary remains available only through the
explicit combined scope:

```sh
cd /home/cdjk/github/llm/nepa-keyboard
bash tools/run_cdjk_relock_validation.sh --scope all \
  /home/cdjk/data/nepa-keyboard/relock/all-20260716-v1
```

This mode performs the historical five-file transaction: both profile locks,
both layout locks, and all nine Gradle pins. It also runs the broader public and
internal compiler/test set. Use it for shared compiler/schema changes; do not
use it for an internal-only review or layout-source change.

## Return generated files

After a successful default run, copy the three internal outputs above from
`cdjk` back to this workspace byte-for-byte. Confirm that their hashes match
`installed-sha256.txt` and that the pin updater succeeds with `--scope internal
--check` on `cdjk` after the round trip. Do not hand-enter or guess any digest.

Only then stage the exact `a/new-Deva-Newa-NP.ncm` beside the internal NKPs and
run Gradle compilation, lint, APK audits, emulator smoke tests, prefix
benchmarks, and the conversion benchmark on `cdjk`. Lock determinism proves the
compiler boundary; it does not substitute for Android compilation or runtime
evidence.
