#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || "$1" != /* ]]; then
  echo "usage: $0 /absolute/new/evidence-directory" >&2
  exit 2
fi

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence="$1"
android="$repo/android"
adb=/home/cdjk/android-sdk/platform-tools/adb
emulator=/home/cdjk/Android/Sdk/emulator/emulator
debug_apk="$android/ime-app/build/outputs/apk/debug/ime-app-debug.apk"
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
    emulator_pid=""
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

[[ -s "$debug_apk" ]]
sha256sum "$debug_apk" >"$evidence/apk-sha256.txt"
zipinfo -1 "$debug_apk" >"$evidence/apk-files.txt"
[[ "$(grep -Ec '^assets/nepa-packs/.+\.nkp$' "$evidence/apk-files.txt")" -eq 2 ]]
grep -Fx 'assets/nepa-packs/eng-Latn-US.nkp' "$evidence/apk-files.txt"
grep -Fx 'assets/nepa-packs/npi-Deva-NP.nkp' "$evidence/apk-files.txt"
! grep -Fq 'assets/nepa-packs/lif-Limb-NP.nkp' "$evidence/apk-files.txt"
sha256sum \
  "$repo/layouts/layouts-v1.lock.json" \
  "$repo/layouts/internal/layouts-v1.lock.json" \
  >"$evidence/layout-lock-sha256.txt"

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

"$adb" -s emulator-5556 install --no-streaming -r -t "$debug_apk"
"$adb" -s emulator-5556 shell pm enable com.ampixa.nepakeyboard.ime >/dev/null
ime_deadline=$((SECONDS + 120))
while true; do
  "$adb" -s emulator-5556 shell ime list -a \
    | tr -d '\r' >"$evidence/ime-list.txt"
  if grep -Fq 'com.ampixa.nepakeyboard.ime/.NepaInputMethodService' \
      "$evidence/ime-list.txt"; then
    break
  fi
  if (( SECONDS >= ime_deadline )); then
    echo "installed IME did not appear in the Android input-method registry" >&2
    exit 1
  fi
  sleep 2
done
"$adb" -s emulator-5556 shell pm list instrumentation \
  | tee "$evidence/instrumentations.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.ime/.ImeSmokeInstrumentation (target=com.ampixa.nepakeyboard.ime)' \
  "$evidence/instrumentations.txt"
"$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime/com.ampixa.nepakeyboard.ime.ImeSmokeInstrumentation \
  | tee "$evidence/ime-smoke.txt"
grep -F 'status=ok' "$evidence/ime-smoke.txt"
grep -F 'orthographic_word_policy_verified=true' "$evidence/ime-smoke.txt"
grep -F 'deva_joiner_policy_verified=true' "$evidence/ime-smoke.txt"
grep -F 'android_deva_joiner_codepoints_verified=true' "$evidence/ime-smoke.txt"

trap - EXIT
cleanup_emulator
"$adb" devices >"$evidence/post-cleanup-adb.txt"
! grep -q '^emulator-' "$evidence/post-cleanup-adb.txt"
printf 'remote_exit_status=0\n' >"$evidence/run-status.txt"
sha256sum "$evidence"/*.txt "$evidence/emulator.log" \
  >"$evidence/evidence-sha256.txt"
printf 'validation_complete evidence=%s\n' "$evidence"
