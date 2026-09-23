# cdjk Limbu internal validation runbook

This runbook is the authoritative execution order for the first internal
language expansion. Run every command on `cdjk`; the Mac is only for source
editing, synchronization, and reviewing the returned evidence. Do not run the
steps concurrently.

Start one dedicated Bash session and keep fail-fast behavior enabled for every
command block below. A failed hash, comparison, test, or build must stop before
any dependent artifact is installed:

First enter Bash:

```sh
bash
```

At the new Bash prompt, enable fail-fast behavior before continuing:

```sh
set -euo pipefail
```

## 1. Preflight and clean work area

Before syncing or computing, inspect the host:

```sh
hostname
uptime
free -h
df -h /home /tmp
ps -eo pid,comm,%cpu,%mem,rss --sort=-rss | head -n 20
```

Use these paths unless the host inventory shows a deliberate replacement:

```sh
repo=/home/cdjk/github/llm/nepa-keyboard
limdic=/home/cdjk/github/llm/ltk/limbu/data/limdic_dictionary.tsv
work=/home/cdjk/data/nepa-keyboard/limbu-internal/20260715-v1
uv=$HOME/.local/bin/uv
```

If that work path already exists from an interrupted attempt, choose a new
monotonically increasing suffix. Never reuse or delete an evidence directory.

The local-to-remote sync must exclude build outputs, `.gradle`, `__pycache__`,
and must not use `--delete`; remote `gradlew`, `local.properties`, SDK state,
and evidence directories are not disposable.

Verify the pinned input before starting:

```sh
cd "$repo"
sha256sum "$limdic"
test "$(sha256sum "$limdic" | cut -d' ' -f1)" = \
  fb6d4922943f08473784b7d47ced8f427c34df9f936db24adf9d456442cd9a1e
test ! -e "$work"
mkdir -p "$work/a" "$work/b"
```

## 2. Build the adapter source and NKP twice

```sh
cd "$repo"
for run in a b
do
  PYTHONPATH=src:. "$uv" run --python 3.14 python \
    tools/build_limbu_internal_source.py \
    --limdic-tsv "$limdic" \
    --output "$work/$run/source" \
    >"$work/$run/adapter-stdout.json"

  PYTHONPATH=src:. "$uv" run --python 3.14 python -m nepa_keyboard.compiler \
    build \
    --input "$work/$run/source" \
    --output "$work/$run/lif-Limb-NP.nkp" \
    --mode internal \
    >"$work/$run/compiler-stdout.json"
done

diff -qr "$work/a/source" "$work/b/source"
cmp "$work/a/lif-Limb-NP.nkp" "$work/b/lif-Limb-NP.nkp"
jq -S 'del(.artifact)' "$work/a/lif-Limb-NP.nkp.report.json" \
  >"$work/a/compiler-report.normalized.json"
jq -S 'del(.artifact)' "$work/b/lif-Limb-NP.nkp.report.json" \
  >"$work/b/compiler-report.normalized.json"
cmp "$work/a/compiler-report.normalized.json" \
  "$work/b/compiler-report.normalized.json"
sha256sum "$work"/a/source/* "$work"/a/lif-Limb-NP.nkp \
  "$work"/a/lif-Limb-NP.nkp.report.json
```

Inspect the adapter report, compiler report, manifest counts, accepted/rejected
reason counts, and a bounded sample of sorted accepted/rejected rows. Do not
claim quality from deterministic compilation alone.

## 3. Pin real lookup vectors and evidence

Use the full inspect invocation below to choose one exact smoke query and 8–12
representative Limbu prefixes:

```sh
IFS= read -r prefix
test -n "$prefix"
PYTHONPATH=src:. "$uv" run --python 3.14 python -m nepa_keyboard.compiler \
  inspect \
  --pack "$work/a/lif-Limb-NP.nkp" \
  --index surface \
  --prefix "$prefix"
```

Include short and longer prefixes, combining sequences, small finals, and
native digits only when the dictionary actually contains them. Enter each
observed prefix at the `read` prompt and record the observed candidates and
first candidate for every query.

Record only the chosen prefixes in the canonical, source-controlled query
selection. The finalizer derives candidates, hashes, counts, and expected
surfaces from the artifacts; those are never hand-entered:

```sh
jq -e '
  (keys == ["benchmark_queries", "validation_query"]) and
  (.validation_query | type == "string" and length > 0) and
  (.benchmark_queries | type == "array" and length >= 8 and length <= 12) and
  ([.benchmark_queries[] | type == "string" and length > 0] | all)
' catalog/limbu-internal-prefixes-v0.json >/dev/null
```

The JSON object contains one string `validation_query` and an array of 8–12
strings named `benchmark_queries`. Then generate both authoritative artifacts
and immediately prove they regenerate byte-for-byte:

```sh
finalize_args=(
  --source-a "$work/a/source"
  --source-b "$work/b/source"
  --pack-a "$work/a/lif-Limb-NP.nkp"
  --pack-b "$work/b/lif-Limb-NP.nkp"
  --queries catalog/limbu-internal-prefixes-v0.json
  --shipping-review catalog/shipping-profile-review.json
  --layout-source layouts/internal/src/limb-nepal-phonetic-v1.json
  --evidence-output reports/limbu-internal-pack-v0.json
  --review-output catalog/internal-profile-review.json
  --reviewed-at 2026-07-15
)
PYTHONPATH=src:. "$uv" run --python 3.14 python \
  tools/finalize_limbu_internal_milestone.py "${finalize_args[@]}"
PYTHONPATH=src:. "$uv" run --python 3.14 python \
  tools/finalize_limbu_internal_milestone.py "${finalize_args[@]}" --check
sha256sum reports/limbu-internal-pack-v0.json \
  catalog/internal-profile-review.json \
  | tee "$work/finalized-evidence-sha256.txt"
```

The finalizer verifies both complete adapter-source trees, both NKPs and
compiler reports, every stored member, and every selected lookup. It writes an
internal review with 33 targets, 74 profiles, nine scripts, and three
selectable profiles: English and Nepali default-on, Limbu default-off. It also
records that native-speaker, glyph, accessibility, physical-device, and quality
review remain pending. Do not manually edit artifact hashes, counts, or lookup
results into either generated file.

## 4. Regenerate deterministic locks

Generate the public profile lock first because the catalog/compiler/schemas
may have changed, then the internal profile lock. Build each twice into the
work area, compare, install the identical artifact, and run `--check`.

```sh
cd "$repo"
for lane in shipping internal
do
  if test "$lane" = shipping
  then
    review=catalog/shipping-profile-review.json
    output=catalog/shipping-profiles.lock.json
  else
    review=catalog/internal-profile-review.json
    output=catalog/internal-profiles.lock.json
  fi
  for run in a b
  do
    PYTHONPATH=src:. "$uv" run --python 3.14 python \
      tools/build_shipping_profile_catalog.py \
      --catalog catalog/resources.json \
      --review "$review" \
      --output "$work/$run/$lane-profiles.lock.json"
  done
  cmp "$work/a/$lane-profiles.lock.json" "$work/b/$lane-profiles.lock.json"
  install -m 0644 "$work/a/$lane-profiles.lock.json" "$output"
  PYTHONPATH=src:. "$uv" run --python 3.14 python \
    tools/build_shipping_profile_catalog.py \
    --catalog catalog/resources.json \
    --review "$review" \
    --output "$output" \
    --check
done
```

Then regenerate both layout locks twice:

```sh
cd "$repo"
for run in a b
do
  PYTHONPATH=src:. "$uv" run --python 3.14 python \
    tools/build_keyboard_layouts.py \
    --source-directory layouts/src \
    --profile-lock catalog/shipping-profiles.lock.json \
    --output "$work/$run/release-layouts.lock.json"
  PYTHONPATH=src:. "$uv" run --python 3.14 python \
    tools/build_keyboard_layouts.py \
    --source-directory layouts/internal/src \
    --profile-lock catalog/internal-profiles.lock.json \
    --output "$work/$run/internal-layouts.lock.json"
done
cmp "$work/a/release-layouts.lock.json" "$work/b/release-layouts.lock.json"
cmp "$work/a/internal-layouts.lock.json" "$work/b/internal-layouts.lock.json"
install -m 0644 "$work/a/release-layouts.lock.json" layouts/layouts-v1.lock.json
install -m 0644 "$work/a/internal-layouts.lock.json" \
  layouts/internal/layouts-v1.lock.json
PYTHONPATH=src:. "$uv" run --python 3.14 python \
  tools/build_keyboard_layouts.py \
  --source-directory layouts/src \
  --profile-lock catalog/shipping-profiles.lock.json \
  --output layouts/layouts-v1.lock.json \
  --check
PYTHONPATH=src:. "$uv" run --python 3.14 python \
  tools/build_keyboard_layouts.py \
  --source-directory layouts/internal/src \
  --profile-lock catalog/internal-profiles.lock.json \
  --output layouts/internal/layouts-v1.lock.json \
  --check
sha256sum catalog/shipping-profiles.lock.json \
  catalog/internal-profiles.lock.json \
  layouts/layouts-v1.lock.json \
  layouts/internal/layouts-v1.lock.json \
  | tee "$work/lock-sha256.pre-pin.txt"
```

Pull the four generated locks back to the Mac, compute their SHA-256 values,
and update every exact Gradle pin below with `apply_patch`:

- `generateShippingProfileCatalog.expectedLockSha256`;
- `generateInternalProfileCatalog.expectedLockSha256`;
- `generateLayoutRegistry.expectedLayoutLockSha256` and
  `expectedProfileLockSha256`;
- `generateInternalLayoutRegistry.expectedLayoutLockSha256` and
  `expectedProfileLockSha256`;
- `stageReleaseExternalPacks.expectedProfileLockSha256`;
- `stageDebugExternalPacks.expectedProfileLockSha256`; and
- `stageInternalExternalPacks.expectedProfileLockSha256`.

Sync the pinned source back to `cdjk`, then repeat the two profile-lock
`--check` invocations from the first block and the two layout-lock `--check`
invocations from the second block. Recompute the same four hashes into
`$work/lock-sha256.post-pin.txt` and compare that file with
`lock-sha256.pre-pin.txt`. Do not start Gradle while any pin is absent or
stale.

```sh
sha256sum catalog/shipping-profiles.lock.json \
  catalog/internal-profiles.lock.json \
  layouts/layouts-v1.lock.json \
  layouts/internal/layouts-v1.lock.json \
  >"$work/lock-sha256.post-pin.txt"
cmp "$work/lock-sha256.pre-pin.txt" \
  "$work/lock-sha256.post-pin.txt"
```

The lock compilers are the executable validators; Gradle independently pins
their source and all four schema files. Do not introduce an unpinned schema
tool or network-resolved dependency into this run. The complete Python suite
below exercises the source, review, lock, and negative compiler contracts.

## 5. Remote tests, staging, builds, and emulator

Run the complete Python suite first:

```sh
cd "$repo"
PYTHONPATH=src:. "$uv" run --python 3.14 python -m unittest discover -s tests
```

Use the cached Gradle/JDK/SDK and separate invocations so benchmark-app lane
selection remains unambiguous:

```sh
gradle=$HOME/.gradle/wrapper/dists/gradle-8.11.1-bin/\
bpt9gzteqjrbo1mjrsomdt32c/gradle-8.11.1/bin/gradle
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export ANDROID_HOME=$HOME/android-sdk
export ANDROID_SDK_ROOT=$HOME/android-sdk
gradle_args=(--offline --no-daemon --max-workers=2)
release_packs=/home/cdjk/data/nepa-keyboard/release-packs/20260715-v2/a
internal_packs="$work/combined-packs"

test ! -e "$internal_packs"
mkdir -p "$internal_packs"
install -m 0644 "$release_packs/eng-Latn-US.nkp" \
  "$internal_packs/eng-Latn-US.nkp"
install -m 0644 "$release_packs/npi-Deva-NP.nkp" \
  "$internal_packs/npi-Deva-NP.nkp"
install -m 0644 "$work/a/lif-Limb-NP.nkp" \
  "$internal_packs/lif-Limb-NP.nkp"
test "$(find "$internal_packs" -mindepth 1 -maxdepth 1 | wc -l)" -eq 3
test "$(sha256sum "$internal_packs/eng-Latn-US.nkp" | cut -d' ' -f1)" = \
  f4b6be4c109846522785628204fd6da98287fb81cb461554369f18993066f68d
test "$(sha256sum "$internal_packs/npi-Deva-NP.nkp" | cut -d' ' -f1)" = \
  a0cd1cb8f8cfafa9aea8b04a246fe914bd208dafcd1f849d1e9989428305d933
sha256sum "$internal_packs"/*.nkp

cd "$repo/android"
"$gradle" "${gradle_args[@]}" :ime-app:assembleRelease :ime-app:lintRelease \
  -PnepaReleasePackDir="$release_packs"
"$gradle" "${gradle_args[@]}" :ime-app:assembleDebug :ime-app:lintDebug \
  -PnepaDebugPackDir="$release_packs"
"$gradle" "${gradle_args[@]}" :ime-app:assembleInternal :ime-app:lintInternal \
  -PnepaInternalPackDir="$internal_packs"
"$gradle" "${gradle_args[@]}" \
  :benchmark-app:assembleDebug :benchmark-app:lintDebug \
  -PnepaInternalPackDir="$internal_packs"
```

The combined directory contains only the exact reviewed English, Nepali, and
Limbu NKPs. Public staging selects only public-lock bindings and ignores an
extra unbound file; it does not reject the directory merely because Limbu is
present. Prove exclusion by staging from the combined directory in a separate
invocation and asserting the generated public pack root contains exactly two
NKPs and no Limbu pack:

```sh
"$gradle" "${gradle_args[@]}" \
  -PnepaReleasePackDir="$internal_packs" \
  :ime-app:stageReleaseExternalPacks
public_stage=ime-app/build/generated/assets/stageReleaseExternalPacks/nepa-packs
test "$(find "$public_stage" -maxdepth 1 -type f -name '*.nkp' | wc -l)" -eq 2
test -f "$public_stage/eng-Latn-US.nkp"
test -f "$public_stage/npi-Deva-NP.nkp"
test ! -e "$public_stage/lif-Limb-NP.nkp"
```

The source-controlled runner performs the final APK and runtime audit. It
checks 2/3/3 release/internal/benchmark NKPs, public Limbu exclusion, variant
reader wiring, host headroom, API 34 package-manager readiness, the `.internal`
package and smoke instrumentation, the closed no-opt-in path, the mixed
three-pack benchmark, all 17 corruption cases, emulator cleanup, and final
evidence hashes. It uses TCG with two cores and 3 GiB and never reuses an
evidence directory.

The partial `android-evidence` through `android-evidence-v5` directories from
bounded boot/orchestration diagnostics remain preserved. Run the complete
audited pass into the next new directory:

```sh
cd "$repo"
bash tools/run_cdjk_limbu_android_validation.sh \
  "$work/android-evidence-v6"
grep -Fx 'remote_exit_status=0' \
  "$work/android-evidence-v6/run-status.txt"
grep -F 'status=ok' \
  "$work/android-evidence-v6/internal-ime-smoke.txt"
grep -F 'status=ok' \
  "$work/android-evidence-v6/internal-prefix-benchmark.txt"
grep -F 'negative_case_pass_count=17' \
  "$work/android-evidence-v6/nkp-bundle-corruption.txt"
```

The dedicated corruption instrumentation copies the staged Limbu asset into an
isolated app-cache directory, recomputes the expected outer hash after each
mutation, and therefore reaches the intended member-level gate. Its 17 negative
cases cover the production internal-pack gate, outer SHA, release-mode mismatch,
member hash/size, fractional numeric metadata, missing/compressed/extra members,
exact manifest membership, bounded binary headers, missing files, and symbolic
links. Do not attribute these cases to the product stager: they are proved by
`nkp-bundle-corruption.txt`.

No Limbu production-readiness claim is valid until native-speaker, glyph,
accessibility, physical-device, and quality evaluation evidence is added. This
milestone proves the internal architecture and first selectable expansion.
