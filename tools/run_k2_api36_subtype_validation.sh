#!/usr/bin/env bash
set -euo pipefail

if [[ ($# -ne 4 && $# -ne 5) || "$1" != /* || "$2" != /* ]]; then
  echo "usage: $0 /absolute/new/evidence-dir /absolute/internal.apk expected-sha256 avd-name [matrix]" >&2
  exit 2
fi
if [[ $# -eq 5 && "$5" != matrix ]]; then
  echo "optional fifth argument must be matrix" >&2
  exit 2
fi

evidence="$1"
apk="$2"
expected_apk_sha256="$3"
avd="$4"
matrix_mode="${5:-subtype}"
sdk="$HOME/android-nepa-toolchain/sdk"
adb="$sdk/platform-tools/adb"
emulator="$sdk/emulator/emulator"
serial='emulator-5556'
package=com.ampixa.nepakeyboard.ime.internal
component="$package/com.ampixa.nepakeyboard.ime.NepaInputMethodService"
instrumentation="$package/com.ampixa.nepakeyboard.ime.InternalSubtypeCompatibilityInstrumentation"
emulator_pid=""
instrumentation_pid=""
sequence_complete=0

if [[ "$(uname -s)" != Darwin || "$(hostname -s)" != Khatra-Dev-Nepals-Mac-Studio ]]; then
  echo "this API 36 runner is restricted to the approved k2 host" >&2
  exit 1
fi
if [[ -e "$evidence" || ! -f "$apk" || ! -x "$adb" || ! -x "$emulator" ]]; then
  echo "evidence directory, APK, or Android toolchain is invalid" >&2
  exit 1
fi
if [[ ! "$expected_apk_sha256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "expected APK SHA-256 must contain 64 lowercase hex digits" >&2
  exit 2
fi
actual_apk_sha256="$(shasum -a 256 "$apk" | awk '{print $1}')"
if [[ "$actual_apk_sha256" != "$expected_apk_sha256" ]]; then
  echo "APK SHA-256 does not match the exact source build" >&2
  exit 1
fi
if [[ ! -s "$HOME/.android/avd/$avd.ini" ]]; then
  echo "the dedicated API 36 AVD is missing" >&2
  exit 1
fi
if [[ "$("$emulator" -list-avds | grep -Fxc "$avd")" != 1 ]]; then
  echo "the dedicated API 36 AVD is not registered" >&2
  exit 1
fi

page_size="$(sysctl -n hw.pagesize)"
free_pages="$(vm_stat | awk '/Pages free:/ {gsub(/\./, "", $3); print $3}')"
free_kib="$((free_pages * page_size / 1024))"
available_pages="$(vm_stat | awk '
  /Pages (free|inactive|speculative|purgeable):/ {
    gsub(/\./, "", $3)
    total += $3
  }
  END {printf "%.0f\n", total}
')"
available_kib="$((available_pages * page_size / 1024))"
pressure_free_percent="$(memory_pressure | awk '
  /System-wide memory free percentage:/ {
    gsub(/%/, "", $NF)
    print $NF
  }
')"
disk_kib="$(df -Pk "$HOME" | awk 'NR == 2 {print $4}')"
cpu_count="$(sysctl -n hw.ncpu)"
load_one="$(sysctl -n vm.loadavg | awk '{print $2}')"
if (( available_kib < 24 * 1024 * 1024 \
      || pressure_free_percent < 30 \
      || disk_kib < 12 * 1024 * 1024 )) \
    || ! awk -v load="$load_one" -v cpu="$cpu_count" 'BEGIN {exit !(load < cpu / 2)}'; then
  echo "k2 has insufficient memory, disk, or CPU headroom for the emulator" >&2
  exit 1
fi
"$adb" start-server >/dev/null
if "$adb" devices | grep -Eq '^emulator-[0-9]+[[:space:]]'; then
  echo "an Android emulator is already running on k2" >&2
  exit 1
fi

mkdir -p "$evidence"
cleanup() {
  local original_status=$?
  trap - EXIT
  set +e
  if (( original_status != 0 )) \
      && [[ "$("$adb" -s "$serial" get-state 2>/dev/null)" == device ]]; then
    "$adb" -s "$serial" logcat -d -v threadtime \
      >"$evidence/failure-logcat.txt" 2>&1
    "$adb" -s "$serial" shell dumpsys input_method \
      >"$evidence/failure-input-method-dumpsys.txt" 2>&1
  fi
  if [[ -n "$instrumentation_pid" ]] && kill -0 "$instrumentation_pid" 2>/dev/null; then
    kill "$instrumentation_pid" 2>/dev/null
  fi
  if [[ -n "$emulator_pid" ]] && kill -0 "$emulator_pid" 2>/dev/null; then
    "$adb" -s "$serial" emu kill >/dev/null 2>&1
    for (( attempt=0; attempt<30; attempt++ )); do
      kill -0 "$emulator_pid" 2>/dev/null || break
      sleep 1
    done
    kill "$emulator_pid" 2>/dev/null
    wait "$emulator_pid" 2>/dev/null
  fi
  "$adb" devices >"$evidence/post-cleanup-adb.txt" 2>&1
  local final_status=$original_status
  if (( final_status == 0 && sequence_complete != 1 )); then
    final_status=1
  fi
  if grep -Eq '^emulator-5556[[:space:]]' "$evidence/post-cleanup-adb.txt"; then
    final_status=1
  fi
  {
    printf 'test_exit_status=%s\n' "$original_status"
    printf 'sequence_complete=%s\n' "$sequence_complete"
    printf 'remote_exit_status=%s\n' "$final_status"
  } >"$evidence/run-status.txt"
  (
    cd "$evidence"
    find . -type f ! -name final-sha256.txt -print \
      | sort \
      | xargs shasum -a 256
  ) >"$evidence/final-sha256.txt"
  exit "$final_status"
}
trap cleanup EXIT

{
  hostname
  uptime
  vm_stat
  df -h "$HOME"
  ps -axo pid,comm,%cpu,%mem,rss | sort -k5 -nr | sed -n '1,20p'
  printf 'free_kib=%s\navailable_kib=%s\npressure_free_percent=%s\n' \
    "$free_kib" "$available_kib" "$pressure_free_percent"
  printf 'disk_kib=%s\nload_one=%s\ncpu_count=%s\n' \
    "$disk_kib" "$load_one" "$cpu_count"
} >"$evidence/host-preflight.txt"
printf '%s  %s\n' "$actual_apk_sha256" "$apk" >"$evidence/apk-sha256.txt"
"$emulator" -version >"$evidence/emulator-version.txt" 2>&1
cp "$HOME/.android/avd/$avd.ini" "$evidence/avd.ini"
cp "$HOME/.android/avd/$avd.avd/config.ini" "$evidence/avd-config.ini"

"$emulator" -avd "$avd" -port 5556 -cores 4 -memory 4096 \
  -gpu swiftshader -no-window -no-audio -no-boot-anim \
  -no-snapshot -wipe-data >"$evidence/emulator.log" 2>&1 &
emulator_pid=$!

boot_ready=0
for (( attempt=0; attempt<180; attempt++ )); do
  if ! kill -0 "$emulator_pid" 2>/dev/null; then
    echo "emulator exited before Android booted" >&2
    exit 1
  fi
  boot_value="$("$adb" -s "$serial" shell getprop sys.boot_completed 2>/dev/null \
    | tr -d '\r' || true)"
  if [[ "$boot_value" == 1 ]]; then
    boot_ready=1
    break
  fi
  sleep 5
done
if (( boot_ready != 1 )); then
  echo "API 36 emulator did not finish booting" >&2
  exit 1
fi
"$adb" -s "$serial" shell getprop ro.build.version.sdk \
  | tr -d '\r' >"$evidence/api-level.txt"
grep -Fx 36 "$evidence/api-level.txt"
"$adb" -s "$serial" shell input keyevent KEYCODE_WAKEUP
"$adb" -s "$serial" shell wm dismiss-keyguard
"$adb" -s "$serial" install -r -t "$apk" >"$evidence/install.txt" 2>&1
grep -Fx Success "$evidence/install.txt"
ime_ready=0
for (( attempt=0; attempt<60; attempt++ )); do
  "$adb" -s "$serial" shell ime list -a -s \
    | tr -d '\r' >"$evidence/available-imes.txt"
  if grep -Fxq "$component" "$evidence/available-imes.txt"; then
    ime_ready=1
    break
  fi
  sleep 2
done
if (( ime_ready != 1 )); then
  echo "installed IME metadata did not become visible" >&2
  exit 1
fi
alternate_ime="$(grep '^com.google.android.inputmethod.latin/' \
  "$evidence/available-imes.txt" | head -1)"
if [[ -z "$alternate_ime" ]]; then
  echo "Gboard is unavailable for the controlled API 36 rebind" >&2
  exit 1
fi
enable_ready=0
for (( attempt=0; attempt<60; attempt++ )); do
  if "$adb" -s "$serial" shell ime enable "$component" \
      >"$evidence/ime-enable.txt" 2>&1; then
    enable_ready=1
    break
  fi
  sleep 2
done
if (( enable_ready != 1 )); then
  echo "Android did not accept the installed IME for user 0" >&2
  exit 1
fi
printf 'enable_attempts=%s\n' "$((attempt + 1))" >"$evidence/ime-enable-status.txt"
"$adb" -s "$serial" shell ime set "$alternate_ime" >"$evidence/ime-set.txt"
"$adb" -s "$serial" shell settings get secure default_input_method \
  | tr -d '\r' >"$evidence/default-ime.txt"
grep -Fx "$alternate_ime" "$evidence/default-ime.txt"

"$adb" -s "$serial" shell am instrument -w -r "$instrumentation" \
  >"$evidence/subtype-compatibility.txt" 2>&1 &
instrumentation_pid=$!
instrumentation_owner=0
for (( attempt=0; attempt<80; attempt++ )); do
  if [[ -n "$("$adb" -s "$serial" shell pidof "$package" 2>/dev/null \
      | tr -d '\r')" ]]; then
    instrumentation_owner=1
    break
  fi
  kill -0 "$instrumentation_pid" 2>/dev/null || break
  sleep 0.25
done
if (( instrumentation_owner != 1 )); then
  echo "instrumentation did not acquire the app process" >&2
  exit 1
fi
"$adb" -s "$serial" shell ime set "$component" >"$evidence/rebind-nepa.txt"
"$adb" -s "$serial" shell settings get secure default_input_method \
  | tr -d '\r' >"$evidence/rebound-default-ime.txt"
grep -Fx "$component" "$evidence/rebound-default-ime.txt"
for (( attempt=0; attempt<120; attempt++ )); do
  kill -0 "$instrumentation_pid" 2>/dev/null || break
  sleep 5
done
if kill -0 "$instrumentation_pid" 2>/dev/null; then
  echo "service-bound instrumentation exceeded its 10-minute bound" >&2
  exit 1
fi
wait "$instrumentation_pid"
instrumentation_pid=""
grep -Fx 'INSTRUMENTATION_RESULT: status=ok' "$evidence/subtype-compatibility.txt"
grep -Fx 'INSTRUMENTATION_CODE: -1' "$evidence/subtype-compatibility.txt"
for result in \
  api_level=36 \
  service_bound_picker_subtype_verified=true \
  service_bound_phonetic_emoji_editing_verified=true \
  private_emoji_recents_suppressed_verified=true \
  no_personalized_learning_emoji_recents_suppressed_verified=true \
  service_bound_globe_subtype_verified=true \
  platform_subtype_confirmation_verified=true \
  service_bound_held_delete_private_no_context_read_verified=true \
  private_context_read_count=0; do
  grep -Fx "INSTRUMENTATION_RESULT: $result" "$evidence/subtype-compatibility.txt"
done

if [[ "$matrix_mode" == matrix ]]; then
  "$adb" -s "$serial" shell ime set "$alternate_ime" \
    >"$evidence/matrix-alternate-ime.txt"
  for test_class in \
    EmojiPanelInstrumentation \
    TransliterationInstrumentation \
    ShellPreferenceInstrumentation \
    InternalScriptRenderingInstrumentation \
    InternalImeSmokeInstrumentation; do
    output="$evidence/$test_class.txt"
    "$adb" -s "$serial" shell am instrument -w -r \
      "$package/com.ampixa.nepakeyboard.ime.$test_class" >"$output" 2>&1 &
    instrumentation_pid=$!
    for (( attempt=0; attempt<120; attempt++ )); do
      kill -0 "$instrumentation_pid" 2>/dev/null || break
      sleep 5
    done
    if kill -0 "$instrumentation_pid" 2>/dev/null; then
      echo "$test_class exceeded its 10-minute bound" >&2
      exit 1
    fi
    wait "$instrumentation_pid"
    instrumentation_pid=""
    grep -Fx 'INSTRUMENTATION_RESULT: status=ok' "$output"
    grep -Fx 'INSTRUMENTATION_CODE: -1' "$output"
  done
fi
sequence_complete=1
