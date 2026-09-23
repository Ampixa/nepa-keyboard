#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || "$1" != /* ]]; then
  echo "usage: $0 /absolute/new/evidence-directory" >&2
  exit 2
fi

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence="$1"
work="$(dirname "$evidence")"
android="$repo/android"
adb=/home/cdjk/android-sdk/platform-tools/adb
emulator=/home/cdjk/Android/Sdk/emulator/emulator
release_apk="$android/ime-app/build/outputs/apk/release/ime-app-release-unsigned.apk"
internal_apk="$android/ime-app/build/outputs/apk/internal/ime-app-internal.apk"
benchmark_apk="$android/benchmark-app/build/outputs/apk/debug/benchmark-app-debug.apk"
public_stage="$android/ime-app/build/generated/assets/stageReleaseExternalPacks/nepa-packs"
emulator_pid=""

if [[ "$(hostname -s)" != "cdjk" ]]; then
  echo "this validation script must run on cdjk" >&2
  exit 1
fi
if [[ -e "$evidence" ]]; then
  echo "evidence directory already exists: $evidence" >&2
  exit 1
fi
mkdir -p "$evidence"

cleanup_emulator() {
  if [[ -n "$emulator_pid" ]]; then
    timeout 20 "$adb" -s emulator-5556 emu kill >/dev/null 2>&1 || true
    wait "$emulator_pid" 2>/dev/null || true
  fi
}

on_exit() {
  status=$?
  trap - EXIT
  printf 'remote_exit_status=%s\n' "$status" >"$evidence/run-status.txt" || true
  cleanup_emulator
  exit "$status"
}
trap on_exit EXIT

available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
if [[ ! "$available_kib" =~ ^[0-9]+$ ]] || (( available_kib < 8 * 1024 * 1024 )); then
  echo "cdjk has less than 8 GiB available memory" >&2
  exit 1
fi
{
  hostname
  uptime
  free -h
  df -h /home /tmp
  ps -eo pid,comm,%cpu,%mem,rss --sort=-rss | head -n 20
} >"$evidence/host-preflight.txt"

if [[ "$(find "$public_stage" -maxdepth 1 -type f -name '*.nkp' | wc -l)" -ne 2 ]]; then
  echo "public staging does not contain exactly two NKPs" >&2
  exit 1
fi
[[ -f "$public_stage/eng-Latn-US.nkp" ]]
[[ -f "$public_stage/npi-Deva-NP.nkp" ]]
[[ ! -e "$public_stage/lif-Limb-NP.nkp" ]]

for apk in "$release_apk" "$internal_apk" "$benchmark_apk"; do
  [[ -s "$apk" ]]
done
sha256sum "$release_apk" "$internal_apk" "$benchmark_apk" \
  | tee "$evidence/apk-sha256.txt"
zipinfo -1 "$release_apk" >"$evidence/release-apk-files.txt"
zipinfo -1 "$internal_apk" >"$evidence/internal-apk-files.txt"
zipinfo -1 "$benchmark_apk" >"$evidence/benchmark-apk-files.txt"
[[ "$(grep -Ec '^assets/nepa-packs/.+\.nkp$' "$evidence/release-apk-files.txt")" -eq 2 ]]
[[ "$(grep -Ec '^assets/nepa-packs/.+\.nkp$' "$evidence/internal-apk-files.txt")" -eq 3 ]]
[[ "$(grep -Ec '^assets/nepa-packs/.+\.nkp$' "$evidence/benchmark-apk-files.txt")" -eq 3 ]]
! grep -Fq 'assets/nepa-packs/lif-Limb-NP.nkp' "$evidence/release-apk-files.txt"
grep -Fx 'assets/nepa-packs/lif-Limb-NP.nkp' "$evidence/internal-apk-files.txt"
grep -Fx 'assets/nepa-packs/lif-Limb-NP.nkp' "$evidence/benchmark-apk-files.txt"
! grep -Fq 'NkpBundle.open(file, expectedSha256, true)' \
  "$android/ime-app/src/release/java/com/ampixa/nepakeyboard/ime/SuggestionEngineFactory.java"
grep -Fq 'NkpBundle.open(file, expectedSha256, true)' \
  "$android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/SuggestionEngineFactory.java"

"$emulator" -list-avds | grep -Fx test_atd
"$adb" start-server >/dev/null
if "$adb" devices | grep -q '^emulator-5556[[:space:]]'; then
  echo "emulator-5556 is already in use" >&2
  exit 1
fi
"$emulator" \
  -avd test_atd \
  -port 5556 \
  -accel off \
  -cores 2 \
  -memory 3072 \
  -gpu swiftshader_indirect \
  -no-window \
  -no-audio \
  -no-boot-anim \
  -no-snapshot \
  >"$evidence/emulator.log" 2>&1 &
emulator_pid=$!

timeout 120 "$adb" -s emulator-5556 wait-for-device
start_seconds=$SECONDS
checks=0
while true; do
  boot_value="$(
    timeout 10 "$adb" -s emulator-5556 shell getprop sys.boot_completed \
      2>/dev/null | tr -d '\r' || true
  )"
  package_value="$(
    timeout 10 "$adb" -s emulator-5556 shell pm path android \
      2>/dev/null | tr -d '\r' || true
  )"
  if [[ "$boot_value" == 1 && "$package_value" == package:* ]]; then
    printf 'emulator_ready elapsed_seconds=%s\n' "$((SECONDS - start_seconds))" \
      | tee "$evidence/boot-status.txt"
    break
  fi
  checks=$((checks + 1))
  if (( checks % 6 == 0 )); then
    printf 'emulator_wait elapsed_seconds=%s boot=%s package=%s\n' \
      "$((SECONDS - start_seconds))" \
      "${boot_value:-unset}" \
      "${package_value:-unavailable}"
  fi
  if ! kill -0 "$emulator_pid" 2>/dev/null; then
    echo "emulator process exited before readiness" >&2
    exit 1
  fi
  if (( SECONDS - start_seconds >= 900 )); then
    echo "emulator readiness timed out" >&2
    exit 1
  fi
  sleep 5
done

{
  "$adb" -s emulator-5556 shell getprop ro.build.version.sdk
  "$adb" -s emulator-5556 shell getprop ro.product.cpu.abi
  "$adb" -s emulator-5556 shell getprop ro.kernel.qemu
  "$adb" -s emulator-5556 shell getprop sys.boot_completed
  "$adb" -s emulator-5556 shell pm path android
} >"$evidence/device-properties.txt"

"$adb" -s emulator-5556 install --no-streaming -r -t "$internal_apk"
"$adb" -s emulator-5556 shell pm path com.ampixa.nepakeyboard.ime.internal \
  | tee "$evidence/internal-package-path.txt"
"$adb" -s emulator-5556 shell pm list instrumentation \
  | tee "$evidence/instrumentations-internal.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.ime.internal/com.ampixa.nepakeyboard.ime.InternalImeSmokeInstrumentation (target=com.ampixa.nepakeyboard.ime.internal)' \
  "$evidence/instrumentations-internal.txt"
"$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.InternalImeSmokeInstrumentation \
  | tee "$evidence/internal-ime-smoke.txt"
grep -F 'status=ok' "$evidence/internal-ime-smoke.txt"
grep -F 'internal_catalog_reader_verified=true' "$evidence/internal-ime-smoke.txt"

"$adb" -s emulator-5556 install --no-streaming -r -t "$benchmark_apk"
"$adb" -s emulator-5556 shell pm list instrumentation \
  | tee "$evidence/instrumentations-all.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.benchmark/.NkpBundleCorruptionInstrumentation (target=com.ampixa.nepakeyboard.benchmark)' \
  "$evidence/instrumentations-all.txt"
"$adb" -s emulator-5556 shell am instrument -w -r \
  -e iterations 10000 \
  -e warmups 1000 \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.InternalCatalogPrefixBenchmarkInstrumentation \
  | tee "$evidence/internal-prefix-benchmark.txt"
grep -F 'status=ok' "$evidence/internal-prefix-benchmark.txt"
grep -F 'benchmark_mode=internal_catalog_prefix' "$evidence/internal-prefix-benchmark.txt"

"$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.NkpBundleCorruptionInstrumentation \
  | tee "$evidence/nkp-bundle-corruption.txt"
grep -F 'status=ok' "$evidence/nkp-bundle-corruption.txt"
grep -F 'negative_case_count=17' "$evidence/nkp-bundle-corruption.txt"
grep -F 'negative_case_pass_count=17' "$evidence/nkp-bundle-corruption.txt"

trap - EXIT
cleanup_emulator
printf 'remote_exit_status=0\n' >"$evidence/run-status.txt"
sha256sum "$evidence"/*.txt "$evidence/emulator.log" \
  "$repo/catalog/shipping-profiles.lock.json" \
  "$repo/catalog/internal-profiles.lock.json" \
  "$repo/layouts/layouts-v1.lock.json" \
  "$repo/layouts/internal/layouts-v1.lock.json" \
  | tee "$evidence/final-evidence-sha256.txt"
printf 'validation_complete evidence=%s\n' "$evidence"
