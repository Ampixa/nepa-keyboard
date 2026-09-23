#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ $# -ne 1 || "$1" != /* ]]; then
  echo "usage: $0 /absolute/new/evidence-directory" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence="$1"
android="$repo/android"
adb=/home/cdjk/android-sdk/platform-tools/adb
emulator=/home/cdjk/Android/Sdk/emulator/emulator
internal_apk="$android/ime-app/build/outputs/apk/internal/ime-app-internal.apk"
benchmark_apk="$android/benchmark-app/build/outputs/apk/debug/benchmark-app-debug.apk"
ime_component='com.ampixa.nepakeyboard.ime.internal/com.ampixa.nepakeyboard.ime.NepaInputMethodService'
internal_lock="$repo/catalog/internal-profiles.lock.json"
internal_layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
transliteration_profiles="$repo/android/ime-app/src/main/assets/nepa-translit/profiles-v1.json"
timeout_ramdisk_root='/home/cdjk/data/nepa-keyboard/android-runtime/api34-aosp-atd-hw-timeout10-v2'
timeout_ramdisk="$timeout_ramdisk_root/ramdisk.img"
expected_timeout_ramdisk_sha256='827da7ffbd4071220be81aaee535f75ca81c2a312e2035f7da74d1379f3abe0d'
base_ramdisk='/home/cdjk/Android/Sdk/system-images/android-34/aosp_atd/x86_64/ramdisk.img'
expected_base_ramdisk_sha256='ce39429f5c8bc2dcf15e346943d6a7ed48d0e8e1005e688a5928ee1d26d8e404'
emulator_pid=""
sequence_complete=0
decoder_contract_timeout_seconds=1800
internal_smoke_timeout_seconds=1800
spatial_benchmark_profile=canonical_tcg_v1
spatial_benchmark_iterations=1000
spatial_benchmark_warmups=100

# This runner proves the internal product. Public/export pack separation and
# approval checks are outside this boundary; internal provenance remains checked.

grep -Fq 'NkpBundle.open(file, expectedSha256, true)' \
  "$android/ime-app/src/candidate/java/com/ampixa/nepakeyboard/ime/SuggestionEngineFactory.java"
grep -Fq 'NkpBundle.readNoticesForInternalCatalog(file, expectedSha256)' \
  "$android/ime-app/src/candidate/java/com/ampixa/nepakeyboard/ime/NoticeReaderFactory.java"

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != "cdjk"
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this validation script must run on cdjk" >&2
  exit 1
fi
if ! command -v realpath >/dev/null; then
  echo "realpath is required for evidence-path containment checks" >&2
  exit 1
fi
evidence="$(realpath -m -- "$evidence")"
if [[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]; then
  echo "evidence directory must be outside the source checkout: $evidence" >&2
  exit 1
fi
if [[ "${NEPA_ANDROID_VALIDATION_LOCKED:-0}" != 1 ]]; then
  lock_status=0
  if flock --nonblock --close --conflict-exit-code 75 \
      /tmp/nepa-keyboard-android-validation.lock \
      env NEPA_ANDROID_VALIDATION_LOCKED=1 \
      bash "$repo/tools/run_cdjk_internal_catalog_validation.sh" "$evidence"; then
    exit 0
  else
    lock_status=$?
  fi
  if (( lock_status == 75 )); then
    echo "another Nepa Android validation owns the cdjk lock" >&2
  fi
  exit "$lock_status"
fi
if [[ -e "$evidence" ]]; then
  echo "evidence directory already exists: $evidence" >&2
  exit 1
fi
mkdir -p "$evidence"

cleanup_emulator() {
  if [[ -n "$emulator_pid" ]]; then
    timeout 20 "$adb" -s emulator-5556 emu kill >/dev/null 2>&1 || true
    local attempts=0
    while kill -0 "$emulator_pid" 2>/dev/null && (( attempts < 20 )); do
      attempts=$((attempts + 1))
      sleep 1
    done
    if kill -0 "$emulator_pid" 2>/dev/null; then
      kill "$emulator_pid" 2>/dev/null || true
    fi
    attempts=0
    while kill -0 "$emulator_pid" 2>/dev/null && (( attempts < 5 )); do
      attempts=$((attempts + 1))
      sleep 1
    done
    if kill -0 "$emulator_pid" 2>/dev/null; then
      kill -9 "$emulator_pid" 2>/dev/null || true
    fi
    attempts=0
    while kill -0 "$emulator_pid" 2>/dev/null && (( attempts < 5 )); do
      attempts=$((attempts + 1))
      sleep 1
    done
    if kill -0 "$emulator_pid" 2>/dev/null; then
      return 1
    fi
    wait "$emulator_pid" 2>/dev/null || true
    emulator_pid=""
  fi
  return 0
}

write_evidence_manifest() {
  local temporary_manifest="$evidence/.final-evidence-sha256.txt.tmp"
  rm -f "$temporary_manifest"
  (
    cd "$evidence"
    LC_ALL=C find . -type f \
      ! -name final-evidence-sha256.txt \
      ! -name .final-evidence-sha256.txt.tmp \
      -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 -r sha256sum
  ) >"$temporary_manifest" || {
    rm -f "$temporary_manifest"
    return 1
  }
  mv "$temporary_manifest" "$evidence/final-evidence-sha256.txt"
}

record_post_cleanup_adb() {
  local attempts=0
  while (( attempts < 30 )); do
    if ! "$adb" devices | grep -q '^emulator-5556[[:space:]]'; then
      break
    fi
    attempts=$((attempts + 1))
    sleep 1
  done
  "$adb" devices >"$evidence/post-cleanup-adb.txt"
  ! grep -q '^emulator-5556[[:space:]]' "$evidence/post-cleanup-adb.txt"
}

on_exit() {
  local test_status=$?
  trap - EXIT
  set +e
  if (( test_status != 0 )) \
      && [[ -n "$emulator_pid" ]] \
      && kill -0 "$emulator_pid" 2>/dev/null; then
    timeout 30 "$adb" -s emulator-5556 shell dumpsys input_method \
      >"$evidence/failure-input-method-dumpsys.txt" 2>&1
    timeout 30 "$adb" -s emulator-5556 logcat -d -v threadtime \
      >"$evidence/failure-logcat.txt" 2>&1
  fi
  local cleanup_status=0
  cleanup_emulator || cleanup_status=$?
  record_post_cleanup_adb 2>/dev/null || cleanup_status=1
  local final_status=$test_status
  if (( final_status == 0 && sequence_complete != 1 )); then
    final_status=1
  fi
  if (( final_status == 0 && cleanup_status != 0 )); then
    final_status=1
  fi
  local manifest_status=0
  if ! {
    printf 'test_exit_status=%s\n' "$test_status"
    printf 'cleanup_exit_status=%s\n' "$cleanup_status"
    printf 'sequence_complete=%s\n' "$sequence_complete"
    printf 'manifest_exit_status=0\n'
    printf 'remote_exit_status=%s\n' "$final_status"
  } >"$evidence/run-status.txt"; then
    manifest_status=1
  else
    write_evidence_manifest || manifest_status=$?
  fi
  if (( manifest_status != 0 )); then
    final_status=1
    {
      printf 'test_exit_status=%s\n' "$test_status"
      printf 'cleanup_exit_status=%s\n' "$cleanup_status"
      printf 'sequence_complete=%s\n' "$sequence_complete"
      printf 'manifest_exit_status=%s\n' "$manifest_status"
      printf 'remote_exit_status=%s\n' "$final_status"
    } >"$evidence/run-status.txt" || true
    # A second bounded attempt content-binds the fail-closed status when possible.
    write_evidence_manifest || true
  fi
  if (( final_status == 0 )); then
    printf 'validation_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

require_instrumentation_success() {
  local output_file="$1"
  grep -Fx 'INSTRUMENTATION_RESULT: status=ok' "$output_file"
  grep -Fx 'INSTRUMENTATION_CODE: -1' "$output_file"
  ! grep -Eq '^INSTRUMENTATION_(FAILED|ABORTED):' "$output_file"
}

require_instrumentation_result() {
  local output_file="$1"
  local result="$2"
  grep -Fx "INSTRUMENTATION_RESULT: $result" "$output_file"
}

user_zero_unlocked() {
  local serial="$1"
  timeout 10 "$adb" -s "$serial" shell dumpsys user 2>/dev/null \
    | tr -d '\r' \
    | awk '
      /UserInfo\{0:/ { in_user_zero = 1 }
      in_user_zero && /[Ss]tate[:=][[:space:]]*RUNNING_UNLOCKED/ {
        print "true"
        exit
      }
      in_user_zero && /UserInfo\{[1-9][0-9]*:/ { exit }
    '
}

require_home_ui_ready() {
  local runner_serial="$1"
  local output_prefix="$2"
  local timeout_seconds="$3"
  local home_component
  local home_package
  local home_class
  local home_full_component
  local started_at=$SECONDS
  local attempts=0
  local current_focus=""
  local focused_app=""
  local top_window=""
  local focus_source=""
  local focus_ready=0
  local reason=""

  timeout 10 "$adb" -s "$runner_serial" shell input keyevent KEYCODE_WAKEUP \
    >"${output_prefix}-wakeup.txt" 2>&1 || {
      printf 'status=failed\nreason=wakeup-command-failed\n' \
        >"${output_prefix}-status.txt"
      return 1
    }
  timeout 10 "$adb" -s "$runner_serial" shell wm dismiss-keyguard \
    >"${output_prefix}-dismiss-keyguard.txt" 2>&1 || {
      printf 'status=failed\nreason=dismiss-keyguard-command-failed\n' \
        >"${output_prefix}-status.txt"
      return 1
    }
  timeout 10 "$adb" -s "$runner_serial" shell cmd package resolve-activity \
    --brief -a android.intent.action.MAIN -c android.intent.category.HOME \
    | tr -d '\r' >"${output_prefix}-home-component.txt"
  home_component="$(tail -n 1 "${output_prefix}-home-component.txt")"
  if [[ ! "$home_component" =~ ^[A-Za-z0-9._]+/[A-Za-z0-9._]+$ ]]; then
    printf 'status=failed\nreason=invalid-home-component\nhome_component=%s\n' \
      "$home_component" >"${output_prefix}-status.txt"
    return 1
  fi
  home_package="${home_component%%/*}"
  home_class="${home_component#*/}"
  if [[ "$home_class" == .* ]]; then
    home_class="${home_package}${home_class}"
  fi
  home_full_component="${home_package}/${home_class}"
  timeout 60 "$adb" -s "$runner_serial" shell am start -W \
    -a android.intent.action.MAIN -c android.intent.category.HOME \
    | tr -d '\r' >"${output_prefix}-home-start.txt" || {
      printf 'status=failed\nreason=home-start-failed\nhome_component=%s\n' \
        "$home_component" >"${output_prefix}-status.txt"
      return 1
    }

  while (( SECONDS - started_at < timeout_seconds )); do
    attempts=$((attempts + 1))
    timeout 10 "$adb" -s "$runner_serial" shell dumpsys power \
      | tr -d '\r' >"${output_prefix}-power.txt" || reason=power-dumpsys-failed
    timeout 10 "$adb" -s "$runner_serial" shell dumpsys window policy \
      | tr -d '\r' >"${output_prefix}-window-policy.txt" \
      || reason=window-policy-dumpsys-failed
    timeout 10 "$adb" -s "$runner_serial" shell dumpsys window windows \
      | tr -d '\r' >"${output_prefix}-window-windows.txt" \
      || reason=window-windows-dumpsys-failed
    if [[ -n "$reason" ]]; then
      break
    fi
    current_focus="$(
      sed -n '/mCurrentFocus=/{s/^[[:space:]]*//;p;q;}' \
        "${output_prefix}-window-windows.txt"
    )"
    focused_app="$(
      sed -n '/mFocusedApp=/{s/^[[:space:]]*//;p;q;}' \
        "${output_prefix}-window-windows.txt"
    )"
    top_window="$(
      sed -n '/^  Window #0 /{s/^[[:space:]]*//;p;q;}' \
        "${output_prefix}-window-windows.txt"
    )"
    if grep -Eiq \
      'Application (Not Responding|Error)|System UI.*(not responding|isn.t responding)|has stopped|keeps stopping' \
      <<<"$current_focus $top_window"; then
      reason=modal-error-window-is-top
      break
    fi
    focus_ready=0
    focus_source=""
    if [[ -n "$current_focus" && -n "$focused_app" ]] \
      && { [[ "$current_focus" == *" $home_component"* ]] \
        || [[ "$current_focus" == *" $home_full_component"* ]]; } \
      && { [[ "$focused_app" == *" $home_component"* ]] \
        || [[ "$focused_app" == *" $home_full_component"* ]]; }; then
      focus_ready=1
      focus_source=global-focus-fields
    elif [[ "$top_window" == *" $home_component"* ]] \
        || [[ "$top_window" == *" $home_full_component"* ]]; then
      focus_ready=1
      focus_source=top-window
    fi
    if grep -Eq 'mWakefulness=Awake|mInteractive=true' \
        "${output_prefix}-power.txt" \
      && ! grep -Eq \
        '(mKeyguardShowing|showingAndNotOccluded|inputRestricted)=true' \
        "${output_prefix}-window-policy.txt" \
      && grep -Eq \
        '(mKeyguardShowing|showingAndNotOccluded|inputRestricted)=false' \
        "${output_prefix}-window-policy.txt" \
      && (( focus_ready == 1 )); then
      {
        printf 'status=ok\n'
        printf 'attempts=%s\n' "$attempts"
        printf 'elapsed_seconds=%s\n' "$((SECONDS - started_at))"
        printf 'home_component=%s\n' "$home_component"
        printf 'focus_source=%s\n' "$focus_source"
        printf 'current_focus=%s\n' "$current_focus"
        printf 'focused_app=%s\n' "$focused_app"
        printf 'top_window=%s\n' "$top_window"
      } >"${output_prefix}-status.txt"
      return 0
    fi
    sleep 1
  done
  if [[ -z "$reason" ]]; then
    reason=home-ui-readiness-timeout
  fi
  {
    printf 'status=failed\n'
    printf 'reason=%s\n' "$reason"
    printf 'attempts=%s\n' "$attempts"
    printf 'elapsed_seconds=%s\n' "$((SECONDS - started_at))"
    printf 'home_component=%s\n' "$home_component"
    printf 'focus_source=%s\n' "$focus_source"
    printf 'current_focus=%s\n' "$current_focus"
    printf 'focused_app=%s\n' "$focused_app"
    printf 'top_window=%s\n' "$top_window"
  } >"${output_prefix}-status.txt"
  return 1
}

wait_for_emulator_ready() {
  local runner_serial="$1"
  local phase="$2"
  local status_file="$3"
  local timeout_seconds="$4"
  local started_at=$SECONDS
  local checks=0
  local boot_value=""
  local package_value=""
  local unlocked_value=""
  while true; do
    boot_value="$(
      timeout 10 "$adb" -s "$runner_serial" shell getprop sys.boot_completed \
        2>/dev/null | tr -d '\r' || true
    )"
    package_value="$(
      timeout 10 "$adb" -s "$runner_serial" shell pm path android \
        2>/dev/null | tr -d '\r' || true
    )"
    unlocked_value="$(user_zero_unlocked "$runner_serial" || true)"
    if [[ "$boot_value" == 1
          && "$package_value" == package:*
          && "$unlocked_value" == true ]]; then
      printf '%s_ready elapsed_seconds=%s\n' \
        "$phase" "$((SECONDS - started_at))" | tee "$status_file"
      return 0
    fi
    checks=$((checks + 1))
    if (( checks % 6 == 0 )); then
      printf '%s_wait elapsed_seconds=%s boot=%s unlocked=%s package=%s\n' \
        "$phase" \
        "$((SECONDS - started_at))" \
        "${boot_value:-unset}" \
        "${unlocked_value:-unset}" \
        "${package_value:-unavailable}"
    fi
    if ! kill -0 "$emulator_pid" 2>/dev/null; then
      echo "emulator process exited during $phase readiness" >&2
      return 1
    fi
    if (( SECONDS - started_at >= timeout_seconds )); then
      echo "$phase readiness timed out" >&2
      return 1
    fi
    sleep 5
  done
}

capture_factory_boot_diagnostics() {
  local runner_serial="$1"
  timeout 30 "$adb" -s "$runner_serial" logcat -d -v threadtime \
    >"$evidence/factory-boot-logcat.txt" 2>&1 || true
  timeout 30 "$adb" -s "$runner_serial" shell dumpsys power \
    >"$evidence/factory-boot-power.txt" 2>&1 || true
  timeout 30 "$adb" -s "$runner_serial" shell dumpsys window policy \
    >"$evidence/factory-boot-window-policy.txt" 2>&1 || true
  timeout 30 "$adb" -s "$runner_serial" shell dumpsys window windows \
    >"$evidence/factory-boot-window-windows.txt" 2>&1 || true
  {
    printf '[cpu]\n'
    cat /proc/pressure/cpu
    printf '[memory]\n'
    cat /proc/pressure/memory
    printf '[io]\n'
    cat /proc/pressure/io
  } >"$evidence/factory-boot-host-pressure.txt"
}

stabilize_factory_boot() {
  local runner_serial="$1"
  capture_factory_boot_diagnostics "$runner_serial"
  timeout 30 "$adb" -s "$runner_serial" shell sync \
    >"$evidence/stabilization-sync.txt" 2>&1
  timeout 30 "$adb" -s "$runner_serial" reboot \
    >"$evidence/stabilization-reboot.txt" 2>&1
  local transition_started=$SECONDS
  local device_state=""
  local boot_value=""
  while (( SECONDS - transition_started < 120 )); do
    device_state="$(
      timeout 5 "$adb" -s "$runner_serial" get-state 2>/dev/null || true
    )"
    boot_value="$(
      timeout 5 "$adb" -s "$runner_serial" shell getprop sys.boot_completed \
        2>/dev/null | tr -d '\r' || true
    )"
    if [[ "$device_state" != device || "$boot_value" != 1 ]]; then
      {
        printf 'offline_transition_verified=true\n'
        printf 'elapsed_seconds=%s\n' "$((SECONDS - transition_started))"
        printf 'device_state=%s\n' "${device_state:-unavailable}"
        printf 'boot_completed=%s\n' "${boot_value:-unset}"
      } >"$evidence/stabilization-offline-status.txt"
      break
    fi
    sleep 1
  done
  grep -Fx 'offline_transition_verified=true' \
    "$evidence/stabilization-offline-status.txt"
  timeout 180 "$adb" -s "$runner_serial" wait-for-device
  wait_for_emulator_ready \
    "$runner_serial" stabilized_boot "$evidence/boot-status.txt" 600
  timeout 180 "$adb" -s "$runner_serial" shell am wait-for-broadcast-idle \
    | tr -d '\r' >"$evidence/stabilization-broadcast-idle.txt"
  require_home_ui_ready \
    "$runner_serial" "$evidence/post-reboot-ui" 180
}

install_test_apk() {
  local serial="$1"
  local apk="$2"
  local label="$3"
  local attempt
  local install_log
  for attempt in 1 2; do
    install_log="$evidence/${label}-install-attempt-${attempt}.txt"
    if timeout 240 "$adb" -s "$serial" install --no-streaming -r -t "$apk" \
      2>&1 | tee "$install_log"; then
      grep -Fx 'Success' "$install_log"
      printf 'successful_attempt=%s\n' "$attempt" \
        >"$evidence/${label}-install-summary.txt"
      return 0
    fi
    if (( attempt == 1 )) \
        && grep -Fq \
          'INSTALL_FAILED_VERIFICATION_FAILURE: Integrity verification timed out' \
          "$install_log"; then
      sleep 30
      continue
    fi
    return 1
  done
  return 1
}

available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
if [[ ! "$available_kib" =~ ^[0-9]+$ ]] || (( available_kib < 8 * 1024 * 1024 )); then
  echo "cdjk has less than 8 GiB available memory" >&2
  exit 1
fi
home_available_kib="$(df -Pk /home | awk 'NR == 2 {print $4}')"
tmp_available_kib="$(df -Pk /tmp | awk 'NR == 2 {print $4}')"
evidence_available_kib="$(df -Pk -- "$evidence" | awk 'NR == 2 {print $4}')"
if [[ ! "$home_available_kib" =~ ^[0-9]+$ \
      || ! "$tmp_available_kib" =~ ^[0-9]+$ \
      || ! "$evidence_available_kib" =~ ^[0-9]+$ \
      || "$home_available_kib" -lt $((12 * 1024 * 1024)) \
      || "$tmp_available_kib" -lt $((4 * 1024 * 1024)) \
      || "$evidence_available_kib" -lt $((4 * 1024 * 1024)) ]]; then
  echo "cdjk has insufficient free disk for Android validation" >&2
  exit 1
fi
{
  hostname
  uptime
  free -h
  df -h /home /tmp "$evidence"
  ps -eo pid,comm,%cpu,%mem,rss --sort=-rss | sed -n '1,20p'
} >"$evidence/host-preflight.txt"

for required in awk cp cut df diff find flock free grep hostname jq mv pgrep ps \
  realpath rm sed sort timeout tr unzip uptime wc xargs zipinfo sha256sum "$adb" \
  "$emulator"; do
  if [[ "$required" == /* ]]; then
    [[ -x "$required" ]]
  else
    command -v "$required" >/dev/null
  fi
done
if pgrep -af '[q]emu-system|[e]mulator' >"$evidence/preexisting-emulators.txt"; then
  echo "another emulator is already running on cdjk" >&2
  exit 1
fi
if pgrep -af '[p]ython.*(train|align|inference|mms|torch)' \
  >"$evidence/preexisting-heavy-python.txt"; then
  echo "a heavy Python workload is already running on cdjk" >&2
  exit 1
fi
if pgrep -af '[g]radle|[k]otlinc|[j]ava.*(GradleDaemon|org\.gradle|kotlinc)' \
  >"$evidence/preexisting-android-builds.txt"; then
  echo "another Android/Gradle workload is already running on cdjk" >&2
  exit 1
fi
ps -eo pid=,rss=,comm=,args= \
  | awk '$2 >= 8388608 {print}' >"$evidence/preexisting-high-rss-processes.txt"
if [[ -s "$evidence/preexisting-high-rss-processes.txt" ]]; then
  echo "a process already uses at least 8 GiB RSS on cdjk" >&2
  exit 1
fi
for file in "$internal_lock" "$internal_layout_lock"; do
  [[ -s "$file" ]]
done
jq -e '
  .lock_version == 2
  and .generator == "build_shipping_profile_catalog"
  and .generator_version == 2
  and .review.authority == "internal"
' "$internal_lock" >/dev/null
jq -e '
  ([.profiles[] | select(.profile_id == "klr-Deva-NP")]) as $rows
  | ($rows | length) == 1
    and ($rows[0] |
      .catalog_readiness == "beta"
      and .selectable == true
      and .default_enabled == false
      and .source_script == "Deva"
      and .output_script == "Deva"
      and .lookup_kind == "surface_prefix"
      and .engine_kind == "layout"
      and .layout_id == "deva-nepal-khaling-v1"
      and .layout_revision == 1
      and .layout_source_sha256 == "9d605bbc80d2462af3a9921cbbc2174b5f2fbff1e21e37e268264667f7f79d13"
      and .pack_binding == "klr-Deva-NP"
      and .pack_artifact.pack_id == "klr-Deva-NP"
      and .pack_artifact.file_name == "klr-Deva-NP.nkp"
      and .pack_artifact.artifact_sha256 == "7dad743ed9ac8102e4443aa0d36b46b03cf2d84c1818728bb5da2d1ff0b45865"
      and .pack_artifact.candidate_count == 4016
      and .pack_artifact.surface_key_count == 4016
      and .pack_artifact.alias_key_count == 0
      and .pack_artifact.release_mode == "internal"
      and .pack_artifact.validation.query == "क"
      and .pack_artifact.validation.expected_surface == "कइना़"
      and (.pack_artifact.validation.benchmark_queries | length) == 10
      and .evidence_ids == ["klr-direct-internal-2026-07-22"]
      and .blocked_reason == null)
' "$internal_lock" >/dev/null
jq -e '
  ([.profile_bindings[]
    | select(.profile_id == "klr-Deva-NP"
        and .source_script == "Deva"
        and .layout_id == "deva-nepal-khaling-v1"
        and .revision == 1)]
    | length) == 1
  and ([.layouts[]
    | select(.layout_id == "deva-nepal-khaling-v1"
        and .input_script == "Deva"
        and .revision == 1)]
    | length) == 1
' "$internal_layout_lock" >/dev/null
printf '%s\n' 'khaling_internal_profile_binding_verified=true' \
  >"$evidence/khaling-internal-profile-binding.txt"
jq -e '
  ([.profiles[] | select(.profile_id == "dus-Deva-NP")]) as $rows
  | ($rows | length) == 1
    and ($rows[0] |
      .catalog_readiness == "beta"
      and .selectable == true
      and .default_enabled == false
      and .source_script == "Deva"
      and .output_script == "Deva"
      and .lookup_kind == "surface_prefix"
      and .engine_kind == "layout"
      and .layout_id == "deva-nepal-dumi-v1"
      and .layout_revision == 1
      and .layout_source_sha256 == "5688c744ee8b88cb3a24c76379590b99195a90a0e309f625ea578b1ced1e60ac"
      and .pack_binding == "dus-Deva-NP"
      and .pack_artifact.pack_id == "dus-Deva-NP"
      and .pack_artifact.file_name == "dus-Deva-NP.nkp"
      and .pack_artifact.artifact_sha256 == "efd9626d11c3910361adb50f1e656c67aefc2c6957ee3b47122236b1a6e3dec2"
      and .pack_artifact.candidate_count == 2132
      and .pack_artifact.surface_key_count == 2132
      and .pack_artifact.alias_key_count == 0
      and .pack_artifact.release_mode == "internal"
      and .pack_artifact.validation.query == "क"
      and .pack_artifact.validation.expected_surface == "क:फु"
      and (.pack_artifact.validation.benchmark_queries | length) == 10
      and .evidence_ids == ["dus-direct-internal-2026-07-22"]
      and .evidence_artifacts == [{
        path: "reports/dumi-internal-pack-v0.json",
        sha256: "f4150925578f3b07ddb6a1cb766f3785f127ff05d18e49a1ca112364688089c9"
      }]
      and .blocked_reason == null)
' "$internal_lock" >/dev/null
jq -e '
  ([.profile_bindings[]
    | select(.profile_id == "dus-Deva-NP"
        and .source_script == "Deva"
        and .layout_id == "deva-nepal-dumi-v1"
        and .revision == 1)]
    | length) == 1
  and ([.layouts[]
    | select(.layout_id == "deva-nepal-dumi-v1"
        and .input_script == "Deva"
        and .revision == 1)]
    | length) == 1
' "$internal_layout_lock" >/dev/null
printf '%s\n' 'dumi_internal_profile_binding_verified=true' \
  >"$evidence/dumi-internal-profile-binding.txt"
jq -e '
  ([.profiles[] | select(.profile_id == "new-Newa-NP")]) as $rows
  | ($rows | length) == 1
    and ($rows[0] |
      .catalog_readiness == "beta"
      and .selectable == true
      and .default_enabled == false
      and .layout_id == "newa-nepal-prachalit-v1"
      and .layout_revision == 1
      and (.layout_source_sha256 | test("^[0-9a-f]{64}$"))
      and .pack_binding == "new-Newa-NP"
      and .pack_artifact.pack_id == "new-Newa-NP"
      and .pack_artifact.file_name == "new-Newa-NP.nkp"
      and .pack_artifact.output_script == "Newa"
      and .pack_artifact.release_mode == "internal"
      and .pack_artifact.candidate_count > 0
      and (.pack_artifact.artifact_sha256 | test("^[0-9a-f]{64}$"))
      and (.evidence_ids | length) == 1
      and (.evidence_artifacts | length) == 1
      and .blocked_reason == null)
' "$internal_lock" >/dev/null
jq -e '
  ([.profiles[]
    | select(.profile_id == "new-Deva-NP" or .profile_id == "new-Latn-Deva-NP")]
    | sort_by(.profile_id)) as $rows
  | ($rows | length) == 2
    and ($rows[0] |
      .profile_id == "new-Deva-NP"
      and .catalog_readiness == "beta"
      and .selectable == true
      and .lookup_kind == "surface_prefix"
      and .layout_id == "deva-nepal-bhasa-v1"
      and .pack_binding == "new-Deva-NP"
      and .pack_artifact.artifact_sha256 == "c90c7eba644334ef95ae7dfc168d70382083f06ab7fc45a81f33a90052952570"
      and .pack_artifact.alias_key_count == 1828)
    and ($rows[1] |
      .profile_id == "new-Latn-Deva-NP"
      and .catalog_readiness == "beta"
      and .selectable == true
      and .default_enabled == false
      and .source_script == "Latn"
      and .output_script == "Deva"
      and .lookup_kind == "alias_prefix"
      and .engine_kind == "alias_decoder"
      and .layout_id == "latn-qwerty-us-v1"
      and .layout_revision == 1
      and .pack_binding == "new-Deva-NP"
      and .pack_artifact.pack_id == "new-Deva-NP"
      and .pack_artifact.file_name == "new-Deva-NP.nkp"
      and .pack_artifact.artifact_sha256 == "c90c7eba644334ef95ae7dfc168d70382083f06ab7fc45a81f33a90052952570"
      and .pack_artifact.candidate_count == 5417
      and .pack_artifact.surface_key_count == 5417
      and .pack_artifact.alias_key_count == 1828
      and .pack_artifact.release_mode == "internal"
      and .evidence_ids == ["new-roman-internal-2026-07-21"]
      and .blocked_reason == null)
' "$internal_lock" >/dev/null
jq -e '
  .lock_version == 2
  and .generator_version == 2
  and ([.profiles[]
    | has("pack_binding")
      and has("pack_artifact")
      and has("conversion_binding")
      and has("conversion_artifact")] | all)
  and (([.profiles[] | select(.profile_id == "new-Deva-Newa-NP")]) as $rows
  | ($rows | length) == 1
    and ($rows[0] |
      .catalog_readiness == "beta"
      and .selectable == true
      and .default_enabled == false
      and .source_script == "Deva"
      and .output_script == "Newa"
      and .lookup_kind == "conversion"
      and .engine_kind == "converter"
      and .layout_id == "deva-nepal-bhasa-v1"
      and .layout_revision == 1
      and .pack_binding == null
      and .pack_artifact == null
      and .conversion_binding == "new-Deva-Newa-NP"
      and (.conversion_artifact | keys | sort) == [
        "artifact_sha256", "converter_id", "file_name", "language",
        "output_script", "release_mode", "rule_count", "source_script",
        "validation"
      ]
      and .conversion_artifact.converter_id == "new-Deva-Newa-NP"
      and .conversion_artifact.file_name == "new-Deva-Newa-NP.ncm"
      and .conversion_artifact.artifact_sha256 == "29c88708b3d7aeb741779b7a7464efcb2464e060d7939c7998533d50b11a2d05"
      and .conversion_artifact.language == "new"
      and .conversion_artifact.source_script == "Deva"
      and .conversion_artifact.output_script == "Newa"
      and .conversion_artifact.release_mode == "internal"
      and .conversion_artifact.rule_count == 165
      and ([.conversion_artifact.validation.vectors[].expected_status] | unique)
        == ["MATCH", "NO_MATCH"]
      and .blocked_reason == null))
' "$internal_lock" >/dev/null
jq -e '
  ([.profile_bindings[]
    | select(.profile_id == "new-Newa-NP"
        and .source_script == "Newa"
        and .layout_id == "newa-nepal-prachalit-v1"
        and .revision == 1)]
    | length) == 1
  and ([.profile_bindings[]
    | select(.profile_id == "new-Deva-Newa-NP"
        and .source_script == "Deva"
        and .layout_id == "deva-nepal-bhasa-v1"
        and .revision == 1)]
    | length) == 1
  and ([.layouts[]
    | select(.layout_id == "newa-nepal-prachalit-v1"
        and .input_script == "Newa"
        and .revision == 1)]
    | length) == 1
' "$internal_layout_lock" >/dev/null
printf '%s\n' 'newa_internal_profile_binding_verified=true' \
  >"$evidence/newa-internal-profile-binding.txt"
printf '%s\n' 'nepal_bhasa_roman_internal_profile_binding_verified=true' \
  >"$evidence/nepal-bhasa-roman-internal-profile-binding.txt"
printf '%s\n' 'nepal_bhasa_deva_newa_internal_profile_binding_verified=true' \
  >"$evidence/nepal-bhasa-deva-newa-internal-profile-binding.txt"
profile_lock_sha="$(sha256sum "$internal_lock" | cut -d' ' -f1)"
layout_lock_sha="$(sha256sum "$internal_layout_lock" | cut -d' ' -f1)"

jq -r '.profiles[]
  | select(.selectable and .pack_artifact != null)
  | [
      .profile_id,
      .pack_artifact.file_name,
      .pack_artifact.artifact_sha256
    ]
  | @tsv' "$internal_lock" | LC_ALL=C sort \
  >"$evidence/expected-internal-pack-bindings.tsv"
internal_lock_profile_count="$(jq -r '.counts.selectable' "$internal_lock")"
internal_transliteration_profile_count="$(
  jq -r '.profile_count' "$transliteration_profiles"
)"
internal_profile_count=$((
  internal_lock_profile_count + internal_transliteration_profile_count
))
internal_pack_binding_count="$(
  wc -l <"$evidence/expected-internal-pack-bindings.tsv"
)"
jq -r '.profiles[]
  | select(.selectable and .conversion_artifact != null)
  | [
      .profile_id,
      .conversion_artifact.file_name,
      .conversion_artifact.artifact_sha256,
      .conversion_artifact.converter_id,
      .conversion_artifact.language,
      .conversion_artifact.source_script,
      .conversion_artifact.output_script,
      .conversion_artifact.rule_count,
      .conversion_artifact.release_mode
    ]
  | @tsv' "$internal_lock" | LC_ALL=C sort \
  >"$evidence/expected-internal-conversion-bindings.tsv"
internal_conversion_binding_count="$(
  wc -l <"$evidence/expected-internal-conversion-bindings.tsv"
)"
[[ $((internal_pack_binding_count + internal_conversion_binding_count)) \
  -eq "$internal_lock_profile_count" ]]
cut -f2 "$evidence/expected-internal-pack-bindings.tsv" | LC_ALL=C sort -u \
  >"$evidence/expected-internal-packs.txt"
cut -f2,3 "$evidence/expected-internal-pack-bindings.tsv" | LC_ALL=C sort -u \
  >"$evidence/expected-internal-pack-identities.tsv"
internal_pack_asset_count="$(wc -l <"$evidence/expected-internal-packs.txt")"
internal_pack_identity_count="$(
  wc -l <"$evidence/expected-internal-pack-identities.tsv"
)"
# A filename may serve multiple profiles, but it must identify exactly one byte stream.
[[ "$internal_pack_asset_count" -eq "$internal_pack_identity_count" ]]
{
  sed 's#^#assets/nepa-packs/#' "$evidence/expected-internal-packs.txt"
  printf '%s\n' \
    assets/nepa-packs/benchmark-vectors.json \
    assets/nepa-packs/manifest.json
} | LC_ALL=C sort >"$evidence/expected-internal-pack-assets.txt"
grep -Fx 'eng-Latn-US.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'npi-Deva-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'lif-Limb-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'dhi-Deva-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'suz-Deva-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'tdg-Deva-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'lbr-Deva-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'ybh-Deva-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'klr-Deva-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'dus-Deva-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'new-Deva-NP.nkp' "$evidence/expected-internal-packs.txt"
grep -Fx 'new-Newa-NP.nkp' "$evidence/expected-internal-packs.txt"
cut -f2 "$evidence/expected-internal-conversion-bindings.tsv" \
  | LC_ALL=C sort -u >"$evidence/expected-internal-conversions.txt"
cut -f2,3 "$evidence/expected-internal-conversion-bindings.tsv" \
  | LC_ALL=C sort -u >"$evidence/expected-internal-conversion-identities.tsv"
internal_conversion_asset_count="$(
  wc -l <"$evidence/expected-internal-conversions.txt"
)"
internal_conversion_identity_count="$(
  wc -l <"$evidence/expected-internal-conversion-identities.tsv"
)"
[[ "$internal_conversion_asset_count" -eq "$internal_conversion_identity_count" ]]
[[ "$internal_conversion_binding_count" -eq 1 ]]
grep -Fx 'new-Deva-Newa-NP.ncm' \
  "$evidence/expected-internal-conversions.txt"
{
  sed 's#^#assets/nepa-conversions/#' \
    "$evidence/expected-internal-conversions.txt"
  printf '%s\n' \
    assets/nepa-conversions/benchmark-vectors.json \
    assets/nepa-conversions/manifest.json
} | LC_ALL=C sort >"$evidence/expected-internal-conversion-assets.txt"

for apk in "$internal_apk" "$benchmark_apk"; do
  [[ -s "$apk" ]]
done

# Bind runtime evidence to the source tree that the runner actually inspected.
# A clean outer cdjk build remains mandatory; this freshness check prevents an
# older APK at the conventional path from certifying newer synced source.
internal_source_inputs=(
  "$android/build.gradle.kts"
  "$android/gradle.properties"
  "$android/settings.gradle.kts"
  "$android/ime-app/build.gradle.kts"
  "$android/ime-app/src/main"
  "$android/ime-app/src/internal"
  "$android/ime-app/src/decoderContract"
  "$android/pack-runtime/build.gradle.kts"
  "$android/pack-runtime/src/main"
  "$android/conversion-runtime/build.gradle.kts"
  "$android/conversion-runtime/consumer-rules.pro"
  "$android/conversion-runtime/src/main"
)
{
  for input in "${internal_source_inputs[@]}"; do
    if [[ -d "$input" ]]; then
      find "$input" -type f -print0
    else
      printf '%s\0' "$input"
    fi
  done
} | LC_ALL=C sort -z \
  | xargs -0 sha256sum >"$evidence/internal-apk-source-inputs-sha256.txt"
{
  for input in "${internal_source_inputs[@]}"; do
    if [[ -d "$input" ]]; then
      find "$input" -type f -newer "$internal_apk" -print
    elif [[ "$input" -nt "$internal_apk" ]]; then
      printf '%s\n' "$input"
    fi
  done
} | LC_ALL=C sort -u >"$evidence/internal-apk-stale-inputs.txt"
[[ ! -s "$evidence/internal-apk-stale-inputs.txt" ]]

# The benchmark APK supplies the timed prefix and corruption evidence, so bind
# it independently to its module, shared reader, and build configuration.
benchmark_source_inputs=(
  "$android/build.gradle.kts"
  "$android/gradle.properties"
  "$android/settings.gradle.kts"
  "$android/benchmark-app/build.gradle.kts"
  "$android/benchmark-app/src/main"
  "$android/ime-app/build.gradle.kts"
  "$android/pack-runtime/build.gradle.kts"
  "$android/pack-runtime/src/main"
  "$android/conversion-runtime/build.gradle.kts"
  "$android/conversion-runtime/consumer-rules.pro"
  "$android/conversion-runtime/src/main"
)
{
  for input in "${benchmark_source_inputs[@]}"; do
    if [[ -d "$input" ]]; then
      find "$input" -type f -print0
    else
      printf '%s\0' "$input"
    fi
  done
} | LC_ALL=C sort -z \
  | xargs -0 sha256sum >"$evidence/benchmark-apk-source-inputs-sha256.txt"
{
  for input in "${benchmark_source_inputs[@]}"; do
    if [[ -d "$input" ]]; then
      find "$input" -type f -newer "$benchmark_apk" -print
    elif [[ "$input" -nt "$benchmark_apk" ]]; then
      printf '%s\n' "$input"
    fi
  done
} | LC_ALL=C sort -u >"$evidence/benchmark-apk-stale-inputs.txt"
[[ ! -s "$evidence/benchmark-apk-stale-inputs.txt" ]]

sha256sum "$internal_apk" "$benchmark_apk" \
  >"$evidence/apk-sha256.txt"
zipinfo -1 "$internal_apk" >"$evidence/internal-apk-files.txt"
zipinfo -1 "$benchmark_apk" >"$evidence/benchmark-apk-files.txt"
sed -n 's#^assets/nepa-packs/\([^/]*\.nkp\)$#\1#p' \
  "$evidence/internal-apk-files.txt" | LC_ALL=C sort \
  >"$evidence/actual-internal-packs.txt"
sed -n 's#^assets/nepa-packs/\([^/]*\.nkp\)$#\1#p' \
  "$evidence/benchmark-apk-files.txt" | LC_ALL=C sort \
  >"$evidence/actual-benchmark-packs.txt"
grep '^assets/nepa-packs/' "$evidence/internal-apk-files.txt" \
  | awk '!/\/$/' | LC_ALL=C sort \
  >"$evidence/actual-internal-pack-assets.txt"
grep '^assets/nepa-packs/' "$evidence/benchmark-apk-files.txt" \
  | awk '!/\/$/' | LC_ALL=C sort \
  >"$evidence/actual-benchmark-pack-assets.txt"
sed -n 's#^assets/nepa-conversions/\([^/]*\.ncm\)$#\1#p' \
  "$evidence/internal-apk-files.txt" | LC_ALL=C sort \
  >"$evidence/actual-internal-conversions.txt"
sed -n 's#^assets/nepa-conversions/\([^/]*\.ncm\)$#\1#p' \
  "$evidence/benchmark-apk-files.txt" | LC_ALL=C sort \
  >"$evidence/actual-benchmark-conversions.txt"
grep '^assets/nepa-conversions/' "$evidence/internal-apk-files.txt" \
  | awk '!/\/$/' | LC_ALL=C sort \
  >"$evidence/actual-internal-conversion-assets.txt"
grep '^assets/nepa-conversions/' "$evidence/benchmark-apk-files.txt" \
  | awk '!/\/$/' | LC_ALL=C sort \
  >"$evidence/actual-benchmark-conversion-assets.txt"
[[ "$(grep -Fxc 'assets/nepa-conformance/runtime-v2.json' \
  "$evidence/internal-apk-files.txt")" -eq 1 ]]
diff -u "$evidence/expected-internal-packs.txt" "$evidence/actual-internal-packs.txt"
diff -u "$evidence/expected-internal-packs.txt" "$evidence/actual-benchmark-packs.txt"
diff -u \
  "$evidence/expected-internal-pack-assets.txt" \
  "$evidence/actual-internal-pack-assets.txt"
diff -u \
  "$evidence/expected-internal-pack-assets.txt" \
  "$evidence/actual-benchmark-pack-assets.txt"
diff -u \
  "$evidence/expected-internal-conversions.txt" \
  "$evidence/actual-internal-conversions.txt"
diff -u \
  "$evidence/expected-internal-conversions.txt" \
  "$evidence/actual-benchmark-conversions.txt"
diff -u \
  "$evidence/expected-internal-conversion-assets.txt" \
  "$evidence/actual-internal-conversion-assets.txt"
diff -u \
  "$evidence/expected-internal-conversion-assets.txt" \
  "$evidence/actual-benchmark-conversion-assets.txt"
for apk_kind in internal benchmark; do
  if [[ "$apk_kind" == internal ]]; then
    pack_apk="$internal_apk"
  else
    pack_apk="$benchmark_apk"
  fi
  : >"$evidence/$apk_kind-pack-assets-sha256.txt"
  while IFS=$'\t' read -r profile_id pack_name expected_pack_sha; do
    actual_pack_sha="$(
      unzip -p "$pack_apk" "assets/nepa-packs/$pack_name" \
        | sha256sum | cut -d' ' -f1
    )"
    [[ "$actual_pack_sha" == "$expected_pack_sha" ]]
    printf '%s\t%s\t%s\n' \
      "$profile_id" "$actual_pack_sha" "assets/nepa-packs/$pack_name" \
      >>"$evidence/$apk_kind-pack-assets-sha256.txt"
  done <"$evidence/expected-internal-pack-bindings.tsv"
done
for apk_kind in internal benchmark; do
  if [[ "$apk_kind" == internal ]]; then
    conversion_apk="$internal_apk"
  else
    conversion_apk="$benchmark_apk"
  fi
  : >"$evidence/$apk_kind-conversion-assets-sha256.txt"
  while IFS=$'\t' read -r profile_id map_name expected_map_sha \
      converter_id language source_script output_script rule_count release_mode; do
    actual_map_sha="$(
      unzip -p "$conversion_apk" "assets/nepa-conversions/$map_name" \
        | sha256sum | cut -d' ' -f1
    )"
    [[ "$actual_map_sha" == "$expected_map_sha" ]]
    printf '%s\t%s\t%s\n' \
      "$profile_id" "$actual_map_sha" "assets/nepa-conversions/$map_name" \
      >>"$evidence/$apk_kind-conversion-assets-sha256.txt"
  done <"$evidence/expected-internal-conversion-bindings.tsv"
done
# Notices remain provenance and APK-integrity evidence, never a clearance gate.
jq -r '.layouts[]
  | . as $layout
  | .license?
  | select(type == "object")
  | select(has("notice_path") and has("notice_sha256"))
  | [
      $layout.layout_id,
      (.notice_path | split("/")[-1]),
      .notice_sha256
    ]
  | @tsv' "$internal_layout_lock" | LC_ALL=C sort \
  >"$evidence/expected-internal-layout-notice-bindings.tsv"
internal_layout_notice_count="$(
  wc -l <"$evidence/expected-internal-layout-notice-bindings.tsv"
)"
cut -f2 "$evidence/expected-internal-layout-notice-bindings.tsv" \
  | LC_ALL=C sort -u >"$evidence/expected-internal-layout-notices.txt"
cut -f2,3 "$evidence/expected-internal-layout-notice-bindings.tsv" \
  | LC_ALL=C sort -u \
  >"$evidence/expected-internal-layout-notice-identities.tsv"
internal_layout_notice_asset_count="$(
  wc -l <"$evidence/expected-internal-layout-notices.txt"
)"
internal_layout_notice_identity_count="$(
  wc -l <"$evidence/expected-internal-layout-notice-identities.tsv"
)"
# A notice may describe multiple layouts, but a basename cannot identify two files.
[[ "$internal_layout_notice_asset_count" \
  -eq "$internal_layout_notice_identity_count" ]]
{
  printf 'selectable_profile_count=%s\n' "$internal_profile_count"
  printf 'lock_selectable_profile_count=%s\n' "$internal_lock_profile_count"
  printf 'transliteration_only_profile_count=%s\n' \
    "$internal_transliteration_profile_count"
  printf 'pack_binding_count=%s\n' "$internal_pack_binding_count"
  printf 'unique_pack_asset_count=%s\n' "$internal_pack_asset_count"
  printf 'conversion_binding_count=%s\n' "$internal_conversion_binding_count"
  printf 'unique_conversion_asset_count=%s\n' \
    "$internal_conversion_asset_count"
  printf 'layout_notice_binding_count=%s\n' "$internal_layout_notice_count"
  printf 'unique_layout_notice_asset_count=%s\n' \
    "$internal_layout_notice_asset_count"
} >"$evidence/internal-catalog-counts.txt"
sed -n 's#^assets/nepa-layout-notices/\([^/]*\)$#\1#p' \
  "$evidence/internal-apk-files.txt" | awk '$0 != "manifest.json"' \
  | awk 'NF' | LC_ALL=C sort \
  >"$evidence/actual-internal-layout-notices.txt"
{
  sed 's#^#assets/nepa-layout-notices/#' \
    "$evidence/expected-internal-layout-notices.txt"
  printf '%s\n' assets/nepa-layout-notices/manifest.json
} | LC_ALL=C sort >"$evidence/expected-internal-layout-notice-assets.txt"
grep '^assets/nepa-layout-notices/' "$evidence/internal-apk-files.txt" \
  | awk '!/\/$/' | LC_ALL=C sort \
  >"$evidence/actual-internal-layout-notice-assets.txt"
diff -u \
  "$evidence/expected-internal-layout-notices.txt" \
  "$evidence/actual-internal-layout-notices.txt"
diff -u \
  "$evidence/expected-internal-layout-notice-assets.txt" \
  "$evidence/actual-internal-layout-notice-assets.txt"
[[ "$(grep -Fxc 'assets/nepa-layout-notices/manifest.json' \
  "$evidence/internal-apk-files.txt")" -eq 1 ]]
unzip -p "$internal_apk" assets/nepa-layout-notices/manifest.json \
  >"$evidence/internal-layout-notice-manifest.json"
jq -S --arg layout_lock_sha "$layout_lock_sha" '
  {
    format_version: 1,
    layout_lock_sha256: $layout_lock_sha,
    layouts: [
      .layouts[]
      | . as $layout
      | .license? as $license
      | select(($license | type) == "object")
      | select(
          ($license | has("notice_path"))
          and ($license | has("notice_sha256"))
        )
      | {
          layout_id: $layout.layout_id,
          display_name: $layout.display_name,
          license_id: $license.id,
          copyright: $license.copyright,
          license_url: (
            if ($license | has("license_url"))
            then $license.license_url
            else null
            end
          ),
          notice_asset_path: (
            "nepa-layout-notices/" + ($license.notice_path | split("/")[-1])
          ),
          notice_sha256: $license.notice_sha256,
          source_url: (
            [$layout.provenance[] | .source_url? | select(type == "string")][0]
            // null
          )
        }
    ]
  }
' "$internal_layout_lock" >"$evidence/expected-internal-layout-notice-manifest.json"
jq -S . "$evidence/internal-layout-notice-manifest.json" \
  >"$evidence/actual-internal-layout-notice-manifest.canonical.json"
diff -u \
  "$evidence/expected-internal-layout-notice-manifest.json" \
  "$evidence/actual-internal-layout-notice-manifest.canonical.json"
jq -e --argjson expected "$internal_layout_notice_count" \
  '.layouts | length == $expected' \
  "$evidence/internal-layout-notice-manifest.json"
jq -r '.layouts[].notice_asset_path | split("/")[-1]' \
  "$evidence/internal-layout-notice-manifest.json" | LC_ALL=C sort -u \
  >"$evidence/manifest-internal-layout-notices.txt"
diff -u \
  "$evidence/expected-internal-layout-notices.txt" \
  "$evidence/manifest-internal-layout-notices.txt"
: >"$evidence/internal-layout-notice-assets-sha256.txt"
while IFS=$'\t' read -r layout_id notice_name expected_notice_sha; do
  actual_notice_sha="$(
    unzip -p "$internal_apk" "assets/nepa-layout-notices/$notice_name" \
      | sha256sum | cut -d' ' -f1
  )"
  [[ "$actual_notice_sha" == "$expected_notice_sha" ]]
  printf '%s\t%s\t%s\n' \
    "$layout_id" "$actual_notice_sha" "assets/nepa-layout-notices/$notice_name" \
    >>"$evidence/internal-layout-notice-assets-sha256.txt"
done <"$evidence/expected-internal-layout-notice-bindings.tsv"
runtime_conformance_sha="$(
  unzip -p "$internal_apk" assets/nepa-conformance/runtime-v2.json \
    | sha256sum | cut -d' ' -f1
)"
grep -Fq 'NkpBundle.open(file, expectedSha256, true)' \
  "$android/ime-app/src/internal/java/com/ampixa/nepakeyboard/ime/SuggestionEngineFactory.java"
sha256sum "$internal_lock" "$internal_layout_lock" \
  >"$evidence/lock-sha256.txt"
cp "$internal_lock" "$evidence/internal-profiles.lock.json"
cp "$internal_layout_lock" "$evidence/internal-layouts-v1.lock.json"
[[ -s "$timeout_ramdisk" ]]
[[ -s "$base_ramdisk" ]]
[[ "$(sha256sum "$timeout_ramdisk" | cut -d' ' -f1)" \
  == "$expected_timeout_ramdisk_sha256" ]]
[[ "$(sha256sum "$base_ramdisk" | cut -d' ' -f1)" \
  == "$expected_base_ramdisk_sha256" ]]
grep -Fx 'remote_exit_status=0' "$timeout_ramdisk_root/run-status.txt"
grep -Fx 'multiplier=10' "$timeout_ramdisk_root/build-parameters.txt"
sha256sum "$base_ramdisk" "$timeout_ramdisk" \
  >"$evidence/timeout-ramdisk-sha256.txt"
cp "$timeout_ramdisk_root/artifact-sha256.txt" \
  "$evidence/timeout-ramdisk-build-artifact-sha256.txt"

"$emulator" -version >"$evidence/emulator-version.txt" 2>&1
"$emulator" -list-avds >"$evidence/available-avds.txt"
grep -Fx test_atd "$evidence/available-avds.txt"
test_atd_ini="$HOME/.android/avd/test_atd.ini"
[[ -s "$test_atd_ini" ]]
cp "$test_atd_ini" "$evidence/test_atd.ini"
test_atd_path="$(awk -F= '$1 == "path" {sub(/^[^=]*=/, ""); print; exit}' "$test_atd_ini")"
[[ "$test_atd_path" == /* && "$test_atd_path" != /Users/* ]]
[[ -s "$test_atd_path/config.ini" ]]
cp "$test_atd_path/config.ini" "$evidence/test_atd-config.ini"
"$adb" start-server >/dev/null
if "$adb" devices | grep -q '^emulator-5556[[:space:]]'; then
  echo "emulator-5556 is already in use" >&2
  exit 1
fi
"$emulator" \
  -avd test_atd \
  -port 5556 \
  -accel off \
  -cores 4 \
  -memory 4096 \
  -gpu swiftshader_indirect \
  -ramdisk "$timeout_ramdisk" \
  -no-window \
  -no-audio \
  -no-boot-anim \
  -no-snapshot \
  -wipe-data \
  >"$evidence/emulator.log" 2>&1 &
emulator_pid=$!

timeout 120 "$adb" -s emulator-5556 wait-for-device
wait_for_emulator_ready \
  emulator-5556 factory_boot "$evidence/factory-boot-status.txt" 900
stabilize_factory_boot emulator-5556

timeout 10 "$adb" -s emulator-5556 shell dumpsys user \
  | tr -d '\r' >"$evidence/user-state.txt"
[[ "$(user_zero_unlocked emulator-5556)" == true ]]

{
  "$adb" -s emulator-5556 shell getprop ro.build.version.sdk
  "$adb" -s emulator-5556 shell getprop ro.product.cpu.abi
  "$adb" -s emulator-5556 shell getprop ro.kernel.qemu
  "$adb" -s emulator-5556 shell getprop sys.boot_completed
  "$adb" -s emulator-5556 shell getprop ro.hw_timeout_multiplier
  "$adb" -s emulator-5556 shell pm path android
} >"$evidence/device-properties.txt"
grep -Fx '34' "$evidence/device-properties.txt"
[[ "$(sed -n '2p' "$evidence/device-properties.txt")" == 'x86_64' ]]
[[ "$(sed -n '3p' "$evidence/device-properties.txt")" == '1' ]]
[[ "$(sed -n '5p' "$evidence/device-properties.txt")" == '10' ]]
for property in \
  ro.build.fingerprint \
  ro.system.build.fingerprint \
  ro.build.description \
  ro.build.id \
  ro.build.version.incremental \
  ro.build.version.security_patch \
  ro.product.cpu.abilist; do
  printf '%s=' "$property" >>"$evidence/device-identity.txt"
  "$adb" -s emulator-5556 shell getprop "$property" \
    | tr -d '\r' >>"$evidence/device-identity.txt"
done
"$adb" -s emulator-5556 shell settings put secure show_ime_with_hard_keyboard 1

install_test_apk emulator-5556 "$internal_apk" internal-ime
"$adb" -s emulator-5556 shell pm path com.ampixa.nepakeyboard.ime.internal \
  >"$evidence/internal-package-path.txt"
"$adb" -s emulator-5556 shell pm list instrumentation \
  >"$evidence/instrumentations-internal.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.ime.internal/com.ampixa.nepakeyboard.ime.InternalImeSmokeInstrumentation (target=com.ampixa.nepakeyboard.ime.internal)' \
  "$evidence/instrumentations-internal.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.ime.internal/com.ampixa.nepakeyboard.ime.DecoderContractInstrumentation (target=com.ampixa.nepakeyboard.ime.internal)' \
  "$evidence/instrumentations-internal.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.ime.internal/com.ampixa.nepakeyboard.ime.NcmConversionInstrumentation (target=com.ampixa.nepakeyboard.ime.internal)' \
  "$evidence/instrumentations-internal.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.ime.internal/com.ampixa.nepakeyboard.ime.SpatialDecoderBenchmarkInstrumentation (target=com.ampixa.nepakeyboard.ime.internal)' \
  "$evidence/instrumentations-internal.txt"
ime_metadata_wait_start=$SECONDS
ime_metadata_attempts=0
while true; do
  ime_metadata_attempts=$((ime_metadata_attempts + 1))
  timeout 10 "$adb" -s emulator-5556 shell ime list -a -s \
    2>"$evidence/installed-ime-metadata.stderr.txt" \
    | tr -d '\r' >"$evidence/installed-ime-metadata.txt" || true
  ime_metadata_count="$(grep -Fxc "$ime_component" \
    "$evidence/installed-ime-metadata.txt" || true)"
  if [[ "$ime_metadata_count" == 1 ]]; then
    {
      printf 'attempts=%s\n' "$ime_metadata_attempts"
      printf 'elapsed_seconds=%s\n' "$((SECONDS - ime_metadata_wait_start))"
      printf 'component=%s\n' "$ime_component"
    } >"$evidence/installed-ime-metadata-status.txt"
    break
  fi
  if ! kill -0 "$emulator_pid" 2>/dev/null; then
    echo "emulator exited while waiting for input-method metadata" >&2
    exit 1
  fi
  if (( SECONDS - ime_metadata_wait_start >= 120 )); then
    timeout 20 "$adb" -s emulator-5556 shell dumpsys input_method \
      >"$evidence/installed-ime-metadata-timeout-dumpsys.txt" 2>&1 || true
    echo "installed input-method metadata readiness timed out" >&2
    exit 1
  fi
  sleep 1
done
printf 'timeout_seconds=%s\n' "$internal_smoke_timeout_seconds" \
  >"$evidence/internal-ime-smoke-parameters.txt"
timeout "$internal_smoke_timeout_seconds" \
  "$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.InternalImeSmokeInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-ime-smoke.txt"
require_instrumentation_success "$evidence/internal-ime-smoke.txt"
grep -F "available_profiles=$internal_profile_count" "$evidence/internal-ime-smoke.txt"
grep -F "staged_packs=$internal_pack_binding_count" \
  "$evidence/internal-ime-smoke.txt"
grep -F 'runtime_conformance_asset_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'runtime_conformance_profile_set_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'runtime_conformance_profile_fields_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'runtime_conformance_layer_fingerprints_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'runtime_conformance_stable_key_dispatch_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'runtime_conformance_picker_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'runtime_conformance_pack_vector_profile_set_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F "keyboard_render_count=$internal_profile_count" \
  "$evidence/internal-ime-smoke.txt"
grep -F 'all_selectable_keyboard_renders_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'dhimal_profile_binding_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dhimal_layout_registry_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dhimal_generated_key_policies_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dhimal_atomic_zwnj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dhimal_key_dispatch_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dhimal_picker_row_selection_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dhimal_pack_input_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'sunuwar_profile_binding_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'sunuwar_generated_key_policies_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'sunuwar_leading_orthographic_word_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'sunuwar_atomic_zwj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'sunuwar_picker_row_selection_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'sunuwar_pack_input_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_profile_binding_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_layout_registry_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_generated_key_policies_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_atomic_zwj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_atomic_zwnj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_stable_key_dispatch_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_key_dispatch_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_nepali_layout_isolation_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_picker_row_selection_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'tdg_pack_input_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_profile_binding_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_layout_registry_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_generated_key_policies_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_internal_zwj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_internal_zwnj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_terminal_zwnj_query_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_terminal_zwnj_boundary_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_terminal_zwnj_candidate_replacement_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_terminal_zwnj_delete_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_terminal_zwnj_invalid_continuation_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_terminal_zwnj_private_field_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_terminal_zwnj_profile_switch_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_terminal_zwj_rejected_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_key_dispatch_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_nepali_layout_isolation_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_picker_row_selection_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'lbr_pack_input_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'ybh_profile_binding_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'ybh_layout_registry_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'ybh_generated_key_policies_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'ybh_intra_word_punctuation_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'ybh_terminal_zwnj_query_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'ybh_key_dispatch_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'ybh_nepali_layout_isolation_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'ybh_picker_row_selection_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'ybh_pack_input_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_profile_binding_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_layout_registry_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_generated_key_policies_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_atomic_zwj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_atomic_zwnj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_intra_word_hyphen_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_key_dispatch_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_nepali_layout_isolation_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_picker_row_selection_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'klr_pack_input_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_profile_binding_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_layout_registry_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_generated_key_policies_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_atomic_zwj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_atomic_zwnj_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_intra_word_hyphen_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_intra_word_colon_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_key_dispatch_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_nepali_layout_isolation_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_picker_row_selection_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'dus_pack_input_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'nepal_bhasa_roman_profile_binding_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'nepal_bhasa_roman_pack_input_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'newa_profile_binding_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'newa_layout_registry_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'newa_extended_letters_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'newa_key_dispatch_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'newa_picker_row_selection_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'newa_pack_input_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'internal_catalog_reader_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'internal_catalog_notices_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'newa_conjunct_joiner_verified=true' "$evidence/internal-ime-smoke.txt"
grep -F 'subtype_state_foundation_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'tokenized_suggestion_readiness_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'candidate_accessibility_foundation_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'observable_setup_state_model_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'activity_system_bar_insets_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'picker_modal_accessibility_foundation_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'picker_hold_accessibility_action_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'picker_attached_max_enabled_recycling_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F "picker_attached_max_enabled_profiles=$internal_profile_count" \
  "$evidence/internal-ime-smoke.txt"
picker_attached_window_rows="$(sed -n \
  's/^INSTRUMENTATION_RESULT: picker_attached_window_rows=//p' \
  "$evidence/internal-ime-smoke.txt")"
picker_attached_rebound_rows="$(sed -n \
  's/^INSTRUMENTATION_RESULT: picker_attached_rebound_rows=//p' \
  "$evidence/internal-ime-smoke.txt")"
[[ "$picker_attached_window_rows" =~ ^[0-9]+$ \
  && "$picker_attached_window_rows" -gt 0 \
  && "$picker_attached_window_rows" -lt "$internal_profile_count" ]]
[[ "$picker_attached_rebound_rows" =~ ^[0-9]+$ \
  && "$picker_attached_rebound_rows" -gt 0 ]]
grep -F 'language_manager_recycling_saved_state_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'language_manager_sections_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'language_picker_enabled_only_verified=true' \
  "$evidence/internal-ime-smoke.txt"
grep -F 'last_enabled_switch_rejection_verified=true' \
  "$evidence/internal-ime-smoke.txt"
for result in \
  backspace_grapheme_vectors_verified=true \
  backspace_owned_composition_verified=true \
  backspace_committed_context_verified=true \
  backspace_fallback_verified=true \
  backspace_sink_private_no_read_verified=true \
  backspace_suggestion_touch_ownership_verified=true \
  backspace_zwj_tailoring_verified=true \
  newa_conjunct_joiner_verified=true \
  backspace_devanagari_state_rebuild_verified=true \
  backspace_selection_contract_verified=true \
  backspace_context_completeness_verified=true \
  delete_repeat_timing_verified=true \
  delete_touch_pointer_ownership_verified=true \
  delete_repeat_view_cancellation_verified=true; do
  require_instrumentation_result "$evidence/internal-ime-smoke.txt" "$result"
done
grep -E 'internal_catalog_notice_sources=[1-9][0-9]*' \
  "$evidence/internal-ime-smoke.txt"
grep -F "layout_notice_count=$internal_layout_notice_count" \
  "$evidence/internal-ime-smoke.txt"
grep -F "profile_lock_sha256=$profile_lock_sha" "$evidence/internal-ime-smoke.txt"
grep -F "layout_lock_sha256=$layout_lock_sha" "$evidence/internal-ime-smoke.txt"
grep -F "runtime_conformance_sha256=$runtime_conformance_sha" \
  "$evidence/internal-ime-smoke.txt"

mkdir "$evidence/keyboard-renders"
{
  jq -r '.profiles[] | select(.selectable) | .profile_id' "$internal_lock"
  jq -r '.profiles[].profile_id' "$transliteration_profiles"
} | LC_ALL=C sort -u >"$evidence/expected-keyboard-render-profiles.txt"
[[ "$(wc -l <"$evidence/expected-keyboard-render-profiles.txt")" \
  -eq "$internal_profile_count" ]]
while IFS= read -r profile_id; do
  [[ "$profile_id" =~ ^[A-Za-z0-9-]+$ ]]
  render_name="ime-internal-${profile_id}.png"
  timeout 60 "$adb" -s emulator-5556 exec-out \
    run-as com.ampixa.nepakeyboard.ime.internal \
    cat "files/$render_name" \
    >"$evidence/keyboard-renders/$render_name"
  [[ "$(stat -c '%s' "$evidence/keyboard-renders/$render_name")" -gt 1024 ]]
  [[ "$(od -An -tx1 -N8 "$evidence/keyboard-renders/$render_name" \
    | tr -d ' \n')" == 89504e470d0a1a0a ]]
done <"$evidence/expected-keyboard-render-profiles.txt"
(
  cd "$evidence/keyboard-renders"
  sha256sum ./*.png | LC_ALL=C sort
) >"$evidence/keyboard-render-sha256.txt"
[[ "$(wc -l <"$evidence/keyboard-render-sha256.txt")" \
  -eq "$internal_profile_count" ]]

timeout 600 "$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.ShellPreferenceInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-shell-preferences.txt"
require_instrumentation_success "$evidence/internal-shell-preferences.txt"
for result in \
  shell_preference_defaults_verified=true \
  shell_preference_height_render_verified=true \
  shell_preference_touch_floor_verified=true \
  shell_preference_key_preview_verified=true \
  shell_preference_feedback_verified=true \
  shell_preference_alternates_verified=true \
  shell_preference_theme_verified=true \
  shell_preference_persistence_verified=true; do
  require_instrumentation_result \
    "$evidence/internal-shell-preferences.txt" "$result"
done

timeout 600 "$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.TransliterationInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-transliteration.txt"
require_instrumentation_success "$evidence/internal-transliteration.txt"
for result in \
  transliteration_vectors_verified=true \
  transliteration_session_verified=true \
  transliteration_contrasts_verified=true \
  transliteration_supplement_verified=true \
  transliteration_unbound_maps_verified=true \
  transliteration_lifecycle_verified=true \
  transliteration_live_typing_verified=true; do
  require_instrumentation_result \
    "$evidence/internal-transliteration.txt" "$result"
done

timeout 600 "$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.EmojiPanelInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-emoji-panel.txt"
require_instrumentation_success "$evidence/internal-emoji-panel.txt"
for result in \
  emoji_catalog_verified=true \
  emoji_recents_verified=true \
  emoji_panel_verified=true \
  emoji_backspace_wired=true \
  emoji_touch_targets_verified=true; do
  require_instrumentation_result "$evidence/internal-emoji-panel.txt" "$result"
done

timeout 600 "$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.NcmConversionInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-ncm-conversion.txt"
require_instrumentation_success "$evidence/internal-ncm-conversion.txt"
for result in \
  ncm_canonical_reader_verified=true \
  ncm_leftmost_longest_verified=true \
  ncm_no_match_verified=true \
  ncm_conversion_category_verified=true \
  ncm_async_off_main_verified=true \
  ncm_router_activation_verified=true; do
  require_instrumentation_result \
    "$evidence/internal-ncm-conversion.txt" "$result"
done

{
  printf 'timeout_seconds=%s\n' "$decoder_contract_timeout_seconds"
  printf 'serial_pack_ready_phase_count=4\n'
  printf 'pack_ready_timeout_ms=300000\n'
} >"$evidence/decoder-contract-run-profile.txt"
timeout "$decoder_contract_timeout_seconds" \
  "$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.DecoderContractInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-decoder-contract.txt"
require_instrumentation_success "$evidence/internal-decoder-contract.txt"
for result in \
  'decoder_contract_verified=true' \
  'literal_candidate_verified=true' \
  'stale_result_rejection_verified=true' \
  'expired_result_fallback_verified=true' \
  'nkp_exact_prefix_provider_verified=true' \
  'functional_query_api_isolation_verified=true' \
  'async_decoder_off_main_verified=true' \
  'async_decoder_controlled_release_verified=true' \
  'async_decoder_deadline_outcome_verified=true' \
  'async_spatial_deadline_outcome_verified=true' \
  'private_field_provider_isolation_verified=true' \
  'candidate_query_binding_verified=true' \
  'nkp_ordinal_provider_score_verified=true' \
  'profile_object_identity_verified=true' \
  'async_decoder_latest_wins_verified=true' \
  'spatial_touch_provenance_verified=true' \
  'spatial_functional_provider_verified=true' \
  'spatial_deadline_outcome_separated_verified=true' \
  'spatial_english_prefix_verified=true' \
  'spatial_nepali_prefix_verified=true' \
  'spatial_bounded_beam_verified=true' \
  'spatial_clean_exact_fast_path_verified=true' \
  'instrumentation_pack_ready_timeout_ms=300000' \
  'backspace_grapheme_vectors_verified=true' \
  'backspace_owned_composition_verified=true' \
  'backspace_committed_context_verified=true' \
  'backspace_fallback_verified=true' \
  'backspace_sink_private_no_read_verified=true' \
  'backspace_suggestion_touch_ownership_verified=true' \
  'backspace_zwj_tailoring_verified=true' \
  'newa_conjunct_joiner_verified=true' \
  'backspace_devanagari_state_rebuild_verified=true' \
  'backspace_selection_contract_verified=true' \
  'backspace_context_completeness_verified=true' \
  'delete_repeat_timing_verified=true' \
  'delete_touch_pointer_ownership_verified=true' \
  'delete_repeat_view_cancellation_verified=true'; do
  require_instrumentation_result \
    "$evidence/internal-decoder-contract.txt" "$result"
done

{
  printf 'profile=%s\n' "$spatial_benchmark_profile"
  printf 'iterations_per_metric=%s\n' "$spatial_benchmark_iterations"
  printf 'warmups_per_metric=%s\n' "$spatial_benchmark_warmups"
  printf 'timeout_seconds=1800\n'
  printf 'latency_budget_enforced=false\n'
  printf 'reference_physical_iterations_per_metric=10000\n'
  printf 'reference_physical_warmups_per_metric=1000\n'
} >"$evidence/spatial-benchmark-run-profile.txt"
timeout 1800 "$adb" -s emulator-5556 shell am instrument -w -r \
  -e iterations "$spatial_benchmark_iterations" \
  -e warmups "$spatial_benchmark_warmups" \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.SpatialDecoderBenchmarkInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-spatial-decoder-benchmark.txt"
require_instrumentation_success "$evidence/internal-spatial-decoder-benchmark.txt"
grep -F 'benchmark_mode=spatial_decoder_v1' \
  "$evidence/internal-spatial-decoder-benchmark.txt"
grep -F 'profile_count=2' "$evidence/internal-spatial-decoder-benchmark.txt"
grep -F 'pack_ready_timeout_ms=300000' \
  "$evidence/internal-spatial-decoder-benchmark.txt"
grep -F "iterations_per_metric=$spatial_benchmark_iterations" \
  "$evidence/internal-spatial-decoder-benchmark.txt"
grep -F "warmups_per_metric=$spatial_benchmark_warmups" \
  "$evidence/internal-spatial-decoder-benchmark.txt"
grep -F 'spatial_beam_limit=16' \
  "$evidence/internal-spatial-decoder-benchmark.txt"
grep -F 'latency_budget_enforced=false' \
  "$evidence/internal-spatial-decoder-benchmark.txt"
grep -F 'functional_query_deadline_enforced=false' \
  "$evidence/internal-spatial-decoder-benchmark.txt"
grep -F 'deadline_outcome_coverage=DecoderContractInstrumentation' \
  "$evidence/internal-spatial-decoder-benchmark.txt"
for result in \
  english_exact_verified=true \
  english_clean_center_parity_verified=true \
  english_boundary_correction_verified=true \
  nepali_exact_verified=true \
  nepali_clean_center_parity_verified=true \
  nepali_boundary_correction_verified=true \
  spatial_literal_preservation_verified=true \
  spatial_beam_bound_verified=true \
  spatial_clean_exact_fast_path_verified=true; do
  require_instrumentation_result \
    "$evidence/internal-spatial-decoder-benchmark.txt" "$result"
done
timeout 60 "$adb" -s emulator-5556 exec-out \
  run-as com.ampixa.nepakeyboard.ime.internal \
  cat files/spatial-decoder-benchmark.json \
  >"$evidence/internal-spatial-decoder-benchmark.json"
jq -e \
  --argjson expected_iterations "$spatial_benchmark_iterations" \
  --argjson expected_warmups "$spatial_benchmark_warmups" \
  '.status == "ok"
   and .benchmark_mode == "spatial_decoder_v1"
   and .profile_count == 2
   and .pack_ready_timeout_ms == 300000
   and .iterations_per_metric == $expected_iterations
   and .warmups_per_metric == $expected_warmups
   and .spatial_beam_limit == 16
   and .latency_budget_ns == 10000000
   and .latency_budget_enforced == false
   and .functional_query_deadline_enforced == false
   and .deadline_outcome_coverage == "DecoderContractInstrumentation"
   and .english_exact_top_surface == "hello"
   and .english_boundary_raw == "jell"
   and .nepali_exact_top_surface == "नमस्कार"
   and .nepali_boundary_raw == "ममस्"
   and .english_exact_beam_count == 0
   and .nepali_exact_beam_count == 0
   and (.english_clean_center_beam_min >= 1)
   and (.english_clean_center_beam_max <= .spatial_beam_limit)
   and (.english_clean_center_beam_mean >= .english_clean_center_beam_min)
   and (.english_clean_center_beam_mean <= .english_clean_center_beam_max)
   and (.english_boundary_correction_beam_count >= 1)
   and (.english_boundary_correction_beam_count <= .spatial_beam_limit)
   and .english_clean_exact_fast_path_eligible == "true"
   and .english_boundary_full_path_verified == "true"
   and (.nepali_clean_center_beam_min >= 1)
   and (.nepali_clean_center_beam_max <= .spatial_beam_limit)
   and (.nepali_clean_center_beam_mean >= .nepali_clean_center_beam_min)
   and (.nepali_clean_center_beam_mean <= .nepali_clean_center_beam_max)
   and (.nepali_boundary_correction_beam_count >= 1)
   and (.nepali_boundary_correction_beam_count <= .spatial_beam_limit)
   and .nepali_clean_exact_fast_path_eligible == "true"
   and .nepali_boundary_full_path_verified == "true"
   and .english_exact_verified == "true"
   and .english_clean_center_parity_verified == "true"
   and .english_boundary_correction_verified == "true"
   and .nepali_exact_verified == "true"
   and .nepali_clean_center_parity_verified == "true"
   and .nepali_boundary_correction_verified == "true"
   and .spatial_literal_preservation_verified == "true"
   and .spatial_beam_bound_verified == "true"
   and .spatial_clean_exact_fast_path_verified == "true"' \
  "$evidence/internal-spatial-decoder-benchmark.json"
while IFS=$'\t' read -r profile_id pack_id artifact_sha layout_id layout_revision layout_sha; do
  case "$profile_id" in
    eng-Latn-US) label=english ;;
    npi-Deva-NP) label=nepali ;;
    *) continue ;;
  esac
  jq -e \
    --arg label "$label" \
    --arg pack_id "$pack_id" \
    --arg artifact_sha "$artifact_sha" \
    --arg layout_id "$layout_id" \
    --argjson layout_revision "$layout_revision" \
    --arg layout_sha "$layout_sha" \
    '.[$label + "_pack_id"] == $pack_id
     and .[$label + "_artifact_sha256"] == $artifact_sha
     and .[$label + "_layout_id"] == $layout_id
     and .[$label + "_layout_revision"] == $layout_revision
     and .[$label + "_layout_source_sha256"] == $layout_sha' \
    "$evidence/internal-spatial-decoder-benchmark.json"
done < <(
  jq -r '.profiles[]
    | select(.profile_id == "eng-Latn-US" or .profile_id == "npi-Deva-NP")
    | [
        .profile_id,
        .pack_artifact.pack_id,
        .pack_artifact.artifact_sha256,
        .layout_id,
        .layout_revision,
        .layout_source_sha256
      ] | @tsv' "$internal_lock"
)
for label in english nepali; do
  for path in exact clean_center boundary_correction; do
    prefix="${label}_${path}"
    jq -e --arg prefix "$prefix" \
      '(.[$prefix + "_mean_ns"] | type) == "number"
       and .[$prefix + "_mean_ns"] >= 0
       and (.[$prefix + "_p50_ns"] | type) == "number"
       and .[$prefix + "_p50_ns"] >= 0
       and (.[$prefix + "_p95_ns"] | type) == "number"
       and .[$prefix + "_p95_ns"] >= .[$prefix + "_p50_ns"]
       and (.[$prefix + "_p99_ns"] | type) == "number"
       and .[$prefix + "_p99_ns"] >= .[$prefix + "_p95_ns"]
       and (.[$prefix + "_max_ns"] | type) == "number"
       and .[$prefix + "_max_ns"] >= .[$prefix + "_p99_ns"]
       and (.[$prefix + "_checksum"] | type) == "number"
       and (.[$prefix + "_allocated_bytes"] | type) == "number"
       and .[$prefix + "_allocated_bytes"] >= 0
       and (.[$prefix + "_allocated_bytes_per_op"] | type) == "number"
       and .[$prefix + "_allocated_bytes_per_op"] >= 0
       and (.[$prefix + "_gc_count_delta"] | type) == "number"
       and .[$prefix + "_gc_count_delta"] >= 0
       and (.[$prefix + "_java_heap_used_before_bytes"] | type) == "number"
       and .[$prefix + "_java_heap_used_before_bytes"] >= 0
       and (.[$prefix + "_java_heap_used_after_bytes"] | type) == "number"
       and .[$prefix + "_java_heap_used_after_bytes"] >= 0
       and (.[$prefix + "_process_pss_before_kb"] | type) == "number"
       and .[$prefix + "_process_pss_before_kb"] >= 0
       and (.[$prefix + "_process_pss_after_kb"] | type) == "number"
       and .[$prefix + "_process_pss_after_kb"] >= 0' \
      "$evidence/internal-spatial-decoder-benchmark.json"
  done
done

"$adb" -s emulator-5556 shell ime enable "$ime_component" \
  >"$evidence/subtype-ime-enable.txt"
"$adb" -s emulator-5556 shell ime set "$ime_component" \
  >"$evidence/subtype-ime-set.txt"
"$adb" -s emulator-5556 shell settings get secure default_input_method \
  | tr -d '\r' >"$evidence/subtype-default-ime.txt"
grep -Fx "$ime_component" "$evidence/subtype-default-ime.txt"
require_home_ui_ready emulator-5556 "$evidence/pre-subtype-ui" 180
timeout 600 "$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.InternalSubtypeCompatibilityInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-subtype-compatibility.txt"
require_instrumentation_success "$evidence/internal-subtype-compatibility.txt"
grep -F 'api_level=34' "$evidence/internal-subtype-compatibility.txt"
grep -F 'service_bound_picker_subtype_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'service_bound_phonetic_emoji_editing_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'service_bound_globe_subtype_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'platform_subtype_confirmation_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'switch_path=input_method_service' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'same_service_subtype_callback_after_picker_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'same_service_subtype_callback_after_globe_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'managed_enabled_subtypes_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'focus_driven_ime_readiness_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'initial_editor_window_focus_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'initial_editor_view_focus_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'service_bound_held_delete_password_restart_cancel_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'service_bound_held_delete_private_no_context_read_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'private_emoji_recents_suppressed_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'service_bound_held_delete_hide_cancel_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'service_bound_held_delete_finish_cancel_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -F 'service_bound_held_delete_post_cancel_dispatch_stability_verified=true' \
  "$evidence/internal-subtype-compatibility.txt"
grep -Eq \
  '^INSTRUMENTATION_RESULT: password_restart_cancel_observed_elapsed_ms=[0-9]+$' \
  "$evidence/internal-subtype-compatibility.txt"
for result in \
  service_bound_picker_subtype_verified=true \
  service_bound_phonetic_emoji_editing_verified=true \
  service_bound_globe_subtype_verified=true \
  platform_subtype_confirmation_verified=true \
  switch_path=input_method_service \
  same_service_subtype_callback_after_picker_verified=true \
  same_service_subtype_callback_after_globe_verified=true \
  managed_enabled_subtypes_verified=true \
  focus_driven_ime_readiness_verified=true \
  initial_editor_window_focus_verified=true \
  initial_editor_view_focus_verified=true \
  service_bound_held_delete_password_restart_cancel_verified=true \
  service_bound_held_delete_private_no_context_read_verified=true \
  private_emoji_recents_suppressed_verified=true \
  service_bound_held_delete_hide_cancel_verified=true \
  service_bound_held_delete_finish_cancel_verified=true \
  service_bound_held_delete_post_cancel_dispatch_stability_verified=true \
  private_context_read_count=0; do
  require_instrumentation_result \
    "$evidence/internal-subtype-compatibility.txt" "$result"
done
timeout 60 "$adb" -s emulator-5556 shell dumpsys input_method \
  >"$evidence/subtype-input-method-dumpsys.txt"

install_test_apk emulator-5556 "$benchmark_apk" benchmark
"$adb" -s emulator-5556 shell pm list instrumentation \
  >"$evidence/instrumentations-all.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.benchmark/.NkpBundleCorruptionInstrumentation (target=com.ampixa.nepakeyboard.benchmark)' \
  "$evidence/instrumentations-all.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.benchmark/.InternalCatalogPrefixBenchmarkInstrumentation (target=com.ampixa.nepakeyboard.benchmark)' \
  "$evidence/instrumentations-all.txt"
grep -F 'instrumentation:com.ampixa.nepakeyboard.benchmark/.ConversionCatalogBenchmarkInstrumentation (target=com.ampixa.nepakeyboard.benchmark)' \
  "$evidence/instrumentations-all.txt"
timeout 1800 "$adb" -s emulator-5556 shell am instrument -w -r \
  -e iterations 10000 \
  -e warmups 1000 \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.InternalCatalogPrefixBenchmarkInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-prefix-benchmark.txt"
require_instrumentation_success "$evidence/internal-prefix-benchmark.txt"
grep -F 'benchmark_mode=internal_catalog_prefix' "$evidence/internal-prefix-benchmark.txt"
grep -F "pack_count=$internal_pack_binding_count" \
  "$evidence/internal-prefix-benchmark.txt"
grep -F 'iterations_per_metric=10000' "$evidence/internal-prefix-benchmark.txt"
grep -F 'warmups_per_pack=1000' "$evidence/internal-prefix-benchmark.txt"
while IFS=$'\t' read -r profile_id pack_id artifact_sha release_mode candidate_count; do
  label="${profile_id//-/_}"
  grep -F "${label}_pack_id=$pack_id" "$evidence/internal-prefix-benchmark.txt"
  grep -F "${label}_artifact_sha256=$artifact_sha" \
    "$evidence/internal-prefix-benchmark.txt"
  grep -F "${label}_release_mode=$release_mode" \
    "$evidence/internal-prefix-benchmark.txt"
  grep -F "${label}_candidate_count=$candidate_count" \
    "$evidence/internal-prefix-benchmark.txt"
done < <(
  jq -r '.profiles[] | select(.selectable and .pack_artifact != null) | [
    .profile_id,
    .pack_artifact.pack_id,
    .pack_artifact.artifact_sha256,
    .pack_artifact.release_mode,
    .pack_artifact.candidate_count
  ] | @tsv' "$internal_lock"
)

timeout 60 "$adb" -s emulator-5556 exec-out \
  run-as com.ampixa.nepakeyboard.benchmark \
  cat files/catalog-prefix-benchmark.json \
  >"$evidence/internal-prefix-benchmark.json"
jq -e \
  --argjson pack_count "$internal_pack_binding_count" \
  '.status == "ok"
   and .benchmark_mode == "internal_catalog_prefix"
   and .pack_count == $pack_count
   and .iterations_per_metric == 10000
   and .warmups_per_pack == 1000
   and (.process_pss_kb_after_benchmarks | type == "number" and . >= 0)' \
  "$evidence/internal-prefix-benchmark.json"
while IFS=$'\t' read -r profile_id source_script output_script; do
  label="${profile_id//-/_}"
  metric_kind='surface'
  if [[ "$source_script" != "$output_script" ]]; then
    metric_kind='alias'
  fi
  for metric in \
    "${label}_asset_copy_and_sha_ns" \
    "${label}_verified_load_ns" \
    "${label}_process_pss_kb"; do
    jq -e --arg metric "$metric" \
      'has($metric) and (.[$metric] | type == "number" and . >= 0)' \
      "$evidence/internal-prefix-benchmark.json"
  done
  for family in ids full; do
    prefix="${label}_${metric_kind}_${family}"
    for suffix in mean_ns p50_ns p95_ns p99_ns max_ns; do
      jq -e --arg metric "${prefix}_${suffix}" \
        'has($metric) and (.[$metric] | type == "number" and . >= 0)' \
        "$evidence/internal-prefix-benchmark.json"
    done
    jq -e --arg metric "${prefix}_checksum" \
      'has($metric) and (.[$metric] | type == "number")' \
      "$evidence/internal-prefix-benchmark.json"
  done
done < <(
  jq -r '.profiles[] | select(.selectable and .pack_artifact != null) | [
    .profile_id,
    .source_script,
    .pack_artifact.output_script
  ] | @tsv' "$internal_lock"
)

timeout 1800 "$adb" -s emulator-5556 shell am instrument -w -r \
  -e iterations 10000 \
  -e warmups 1000 \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.ConversionCatalogBenchmarkInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/internal-conversion-benchmark.txt"
require_instrumentation_success "$evidence/internal-conversion-benchmark.txt"
grep -F 'benchmark_mode=conversion_catalog_v1' \
  "$evidence/internal-conversion-benchmark.txt"
grep -F "conversion_profile_count=$internal_conversion_binding_count" \
  "$evidence/internal-conversion-benchmark.txt"
grep -F 'iterations_per_profile=10000' \
  "$evidence/internal-conversion-benchmark.txt"
grep -F 'warmups_per_profile=1000' \
  "$evidence/internal-conversion-benchmark.txt"
while IFS=$'\t' read -r profile_id map_name expected_map_sha \
    converter_id language source_script output_script rule_count release_mode; do
  label="${profile_id//-/_}"
  grep -F "${label}_converter_id=$converter_id" \
    "$evidence/internal-conversion-benchmark.txt"
  grep -F "${label}_artifact_sha256=$expected_map_sha" \
    "$evidence/internal-conversion-benchmark.txt"
  grep -F "${label}_rule_count=$rule_count" \
    "$evidence/internal-conversion-benchmark.txt"
done <"$evidence/expected-internal-conversion-bindings.tsv"
timeout 60 "$adb" -s emulator-5556 exec-out \
  run-as com.ampixa.nepakeyboard.benchmark \
  cat files/conversion-catalog-benchmark.json \
  >"$evidence/internal-conversion-benchmark.json"
jq -e \
  --argjson profile_count "$internal_conversion_binding_count" \
  '.status == "ok"
   and .benchmark_mode == "conversion_catalog_v1"
   and .conversion_profile_count == $profile_count
   and .iterations_per_profile == 10000
   and .warmups_per_profile == 1000
   and (.process_pss_kb_after_benchmarks | type == "number" and . >= 0)' \
  "$evidence/internal-conversion-benchmark.json"
while IFS=$'\t' read -r profile_id map_name expected_map_sha \
    converter_id language source_script output_script rule_count release_mode; do
  label="${profile_id//-/_}"
  for metric in \
    "${label}_asset_copy_and_sha_ns" \
    "${label}_verified_load_ns" \
    "${label}_mean_ns" \
    "${label}_p50_ns" \
    "${label}_p95_ns" \
    "${label}_p99_ns" \
    "${label}_max_ns" \
    "${label}_process_pss_kb"; do
    jq -e --arg metric "$metric" \
      'has($metric) and (.[$metric] | type == "number" and . >= 0)' \
      "$evidence/internal-conversion-benchmark.json"
  done
  jq -e \
    --arg id_metric "${label}_converter_id" \
    --arg converter_id "$converter_id" \
    --arg sha_metric "${label}_artifact_sha256" \
    --arg sha "$expected_map_sha" \
    --arg rule_metric "${label}_rule_count" \
    --argjson rule_count "$rule_count" \
    --arg vector_metric "${label}_verified_vector_count" \
    '.[ $id_metric ] == $converter_id
     and .[ $sha_metric ] == $sha
     and .[ $rule_metric ] == $rule_count
     and (.[ $vector_metric ] | type == "number" and . >= 2)' \
    "$evidence/internal-conversion-benchmark.json"
done <"$evidence/expected-internal-conversion-bindings.tsv"

timeout 600 "$adb" -s emulator-5556 shell am instrument -w -r \
  com.ampixa.nepakeyboard.benchmark/\
com.ampixa.nepakeyboard.benchmark.NkpBundleCorruptionInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/nkp-bundle-corruption.txt"
require_instrumentation_success "$evidence/nkp-bundle-corruption.txt"
grep -F 'negative_case_count=17' "$evidence/nkp-bundle-corruption.txt"
grep -F 'negative_case_pass_count=17' "$evidence/nkp-bundle-corruption.txt"
grep -F 'internal_catalog_reader_verified=true' "$evidence/nkp-bundle-corruption.txt"

sequence_complete=1
exit 0
