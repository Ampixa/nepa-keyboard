#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ ($# -ne 3 && $# -ne 4) || "$1" != /* ]]; then
  echo "usage: $0 /absolute/new/evidence-directory avd-name expected-api [render-only]" >&2
  exit 2
fi

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence="$1"
avd_name="$2"
expected_api="$3"
validation_mode="${4:-full}"
if [[ "$validation_mode" != full && "$validation_mode" != render-only ]]; then
  echo "validation mode must be full or render-only" >&2
  exit 2
fi
android="$repo/android"
adb=/home/cdjk/android-sdk/platform-tools/adb
emulator=/home/cdjk/Android/Sdk/emulator/emulator
internal_apk="$android/ime-app/build/outputs/apk/internal/ime-app-internal.apk"
internal_lock="$repo/catalog/internal-profiles.lock.json"
internal_layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
timeout_ramdisk_root=""
timeout_ramdisk=""
expected_timeout_ramdisk_sha256=""
base_ramdisk=""
expected_base_ramdisk_sha256=""
base_system=""
expected_base_system_sha256=""
base_vendor=""
expected_base_vendor_sha256=""
base_encryption_key=""
expected_base_encryption_key_sha256=""
ramdisk_mode=""
runtime_timeout_mode=""
serial='emulator-5558'
ime_component='com.ampixa.nepakeyboard.ime.internal/com.ampixa.nepakeyboard.ime.NepaInputMethodService'
emulator_pid=""
sequence_complete=0
emulator_boot_args=()

case "$expected_api" in
  26)
    base_ramdisk='/home/cdjk/Android/Sdk/system-images/android-26/default/x86_64/ramdisk.img'
    expected_base_ramdisk_sha256='2be5c37057f4054d03dc9bab4fb592d97c6cefd83e9f03c939739e73f999ed6f'
    base_system='/home/cdjk/Android/Sdk/system-images/android-26/default/x86_64/system.img'
    expected_base_system_sha256='082079003418387d3c8523b6e88084bcec7cabf7568de4bba6f70ff72a195177'
    base_vendor='/home/cdjk/Android/Sdk/system-images/android-26/default/x86_64/vendor.img'
    expected_base_vendor_sha256='8ce4d5b5624eb0fe6077d8ae31a18d229b174d61c93fb2f47672cf2a80b4dc63'
    base_encryption_key='/home/cdjk/Android/Sdk/system-images/android-26/default/x86_64/encryptionkey.img'
    expected_base_encryption_key_sha256='30e14955ebf1352266dc2ff8067e68104607e750abb9d3b36582b8af909fcb58'
    ramdisk_mode='stock-legacy-ramdisk'
    runtime_timeout_mode='writable-system-overlay'
    emulator_boot_args=(-writable-system)
    ;;
  27)
    base_ramdisk='/home/cdjk/Android/Sdk/system-images/android-27/default/x86_64/ramdisk.img'
    expected_base_ramdisk_sha256='9510912cdb5f1503b990f000905e1fffdaee31b75cd84292362d8a02fac49c7e'
    base_system='/home/cdjk/Android/Sdk/system-images/android-27/default/x86_64/system.img'
    expected_base_system_sha256='f4bc9f12584f4f25b122a3881d0c9a2db17be62934e219a7e5ecf28b59162c04'
    base_vendor='/home/cdjk/Android/Sdk/system-images/android-27/default/x86_64/vendor.img'
    expected_base_vendor_sha256='44b7dee2e04695060f3d4870c7e9b66eee6138383256ace8fe8e5f84f547e889'
    base_encryption_key='/home/cdjk/Android/Sdk/system-images/android-27/default/x86_64/encryptionkey.img'
    expected_base_encryption_key_sha256='30e14955ebf1352266dc2ff8067e68104607e750abb9d3b36582b8af909fcb58'
    ramdisk_mode='stock-legacy-ramdisk'
    runtime_timeout_mode='writable-system-overlay'
    emulator_boot_args=(-writable-system)
    ;;
  34)
    timeout_ramdisk_root='/home/cdjk/data/nepa-keyboard/android-runtime/api34-aosp-atd-hw-timeout10-v2'
    timeout_ramdisk="$timeout_ramdisk_root/ramdisk.img"
    expected_timeout_ramdisk_sha256='827da7ffbd4071220be81aaee535f75ca81c2a312e2035f7da74d1379f3abe0d'
    base_ramdisk='/home/cdjk/Android/Sdk/system-images/android-34/aosp_atd/x86_64/ramdisk.img'
    expected_base_ramdisk_sha256='ce39429f5c8bc2dcf15e346943d6a7ed48d0e8e1005e688a5928ee1d26d8e404'
    ramdisk_mode='pinned-api34-timeout'
    runtime_timeout_mode='pinned-ramdisk'
    emulator_boot_args=(-ramdisk "$timeout_ramdisk")
    ;;
  *)
    echo "expected API must be 26, 27, or 34" >&2
    exit 2
    ;;
esac

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != "cdjk"
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
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
    timeout 20 "$adb" -s "$serial" emu kill >/dev/null 2>&1 || true
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
    LC_ALL=C find . -maxdepth 1 -type f \
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
    if ! "$adb" devices | grep -q "^${serial}[[:space:]]"; then
      break
    fi
    attempts=$((attempts + 1))
    sleep 1
  done
  "$adb" devices >"$evidence/post-cleanup-adb.txt"
  ! grep -q "^${serial}[[:space:]]" "$evidence/post-cleanup-adb.txt"
}

on_exit() {
  local test_status=$?
  trap - EXIT
  set +e
  if (( test_status != 0 )) \
      && [[ -n "$emulator_pid" ]] \
      && kill -0 "$emulator_pid" 2>/dev/null; then
    timeout 30 "$adb" -s "$serial" shell dumpsys input_method \
      >"$evidence/failure-input-method-dumpsys.txt" 2>&1
    timeout 30 "$adb" -s "$serial" logcat -d -v threadtime \
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
  {
    printf 'test_exit_status=%s\n' "$test_status"
    printf 'cleanup_exit_status=%s\n' "$cleanup_status"
    printf 'sequence_complete=%s\n' "$sequence_complete"
    printf 'manifest_exit_status=0\n'
    printf 'remote_exit_status=%s\n' "$final_status"
  } >"$evidence/run-status.txt" || true
  write_evidence_manifest || manifest_status=$?
  if (( manifest_status != 0 )); then
    final_status=1
    {
      printf 'test_exit_status=%s\n' "$test_status"
      printf 'cleanup_exit_status=%s\n' "$cleanup_status"
      printf 'sequence_complete=%s\n' "$sequence_complete"
      printf 'manifest_exit_status=%s\n' "$manifest_status"
      printf 'remote_exit_status=%s\n' "$final_status"
    } >"$evidence/run-status.txt" || true
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
  local runner_serial="$1"
  timeout 10 "$adb" -s "$runner_serial" shell dumpsys user 2>/dev/null \
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
  local keyguard_source=""
  local keyguard_ready=0
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
    keyguard_ready=0
    keyguard_source=""
    if (( expected_api <= 27 )); then
      if grep -Eq 'inputRestricted=false' "${output_prefix}-window-policy.txt"; then
        keyguard_ready=1
        keyguard_source=legacy-input-restricted
      fi
    elif ! grep -Eq \
        '(mKeyguardShowing|showingAndNotOccluded|inputRestricted)=true' \
        "${output_prefix}-window-policy.txt" \
        && grep -Eq \
        '(mKeyguardShowing|showingAndNotOccluded|inputRestricted)=false' \
        "${output_prefix}-window-policy.txt"; then
      keyguard_ready=1
      keyguard_source=modern-keyguard-fields
    fi
    if grep -Eq 'mWakefulness=Awake|mInteractive=true' \
        "${output_prefix}-power.txt" \
      && (( keyguard_ready == 1 )) \
      && (( focus_ready == 1 )); then
      {
        printf 'status=ok\n'
        printf 'attempts=%s\n' "$attempts"
        printf 'elapsed_seconds=%s\n' "$((SECONDS - started_at))"
        printf 'home_component=%s\n' "$home_component"
        printf 'focus_source=%s\n' "$focus_source"
        printf 'keyguard_source=%s\n' "$keyguard_source"
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
    printf 'keyguard_source=%s\n' "$keyguard_source"
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

capture_adb_with_retries() {
  local output_file="$1"
  local stderr_file="$2"
  local timeout_seconds="$3"
  shift 3
  local attempt
  local temporary_output="${output_file}.tmp"
  local temporary_stderr="${stderr_file}.tmp"
  for attempt in $(seq 1 30); do
    if timeout "$timeout_seconds" "$adb" -s "$serial" "$@" \
        >"$temporary_output" 2>"$temporary_stderr"; then
      mv "$temporary_output" "$output_file"
      mv "$temporary_stderr" "$stderr_file"
      printf 'successful_attempt=%s\n' "$attempt" \
        >"${output_file}.attempts.txt"
      return 0
    fi
    if ! kill -0 "$emulator_pid" 2>/dev/null; then
      break
    fi
    sleep 3
  done
  mv "$temporary_output" "$output_file" 2>/dev/null || true
  mv "$temporary_stderr" "$stderr_file" 2>/dev/null || true
  printf 'successful_attempt=none\n' >"${output_file}.attempts.txt"
  return 1
}

provision_legacy_timeout_overlay() {
  local source_property="$evidence/legacy-source-prop.default"
  local provisioned_property="$evidence/legacy-provisioned-prop.default"
  local roundtrip_property="$evidence/legacy-roundtrip-prop.default"
  local transition_seen=0
  local transition_started=$SECONDS
  local device_state=""
  local boot_value=""

  capture_adb_with_retries \
    "$evidence/legacy-shell-id.raw.txt" \
    "$evidence/legacy-shell-id.stderr.txt" 30 shell id
  tr -d '\r' <"$evidence/legacy-shell-id.raw.txt" \
    >"$evidence/legacy-shell-id.txt"
  grep -Fq 'uid=2000(shell)' "$evidence/legacy-shell-id.txt"
  capture_adb_with_retries \
    "$evidence/legacy-su-id.raw.txt" \
    "$evidence/legacy-su-id.stderr.txt" 30 shell su 0 id
  tr -d '\r' <"$evidence/legacy-su-id.raw.txt" \
    >"$evidence/legacy-su-id.txt"
  grep -Fq 'uid=0(root)' "$evidence/legacy-su-id.txt"

  capture_adb_with_retries \
    "$evidence/legacy-remount.txt" \
    "$evidence/legacy-remount.stderr.txt" 30 \
    shell su 0 mount -o rw,remount /system
  capture_adb_with_retries \
    "$evidence/legacy-mounts.raw.txt" \
    "$evidence/legacy-mounts.stderr.txt" 30 shell mount
  tr -d '\r' <"$evidence/legacy-mounts.raw.txt" \
    >"$evidence/legacy-mounts.txt"
  grep ' /system ' "$evidence/legacy-mounts.txt" \
    >"$evidence/legacy-system-mount.txt"
  grep -Eq ' /system .*\(rw[,)]' "$evidence/legacy-system-mount.txt"

  capture_adb_with_retries \
    "$source_property" "$evidence/legacy-source-prop.stderr.txt" 30 \
    shell su 0 cat /system/etc/prop.default
  [[ -s "$source_property" ]]
  if grep -Eq '^ro\.hw_timeout_multiplier=' "$source_property"; then
    echo "stock legacy property file already contains timeout multiplier" >&2
    return 1
  fi
  grep -v '^ro\.hw_timeout_multiplier=' "$source_property" \
    >"$provisioned_property"
  {
    printf '\n'
    printf '# Slow software-emulator timeout scaling (AOSP Build.HW_TIMEOUT_MULTIPLIER).\n'
    printf 'ro.hw_timeout_multiplier=10\n'
  } >>"$provisioned_property"
  capture_adb_with_retries \
    "$evidence/legacy-property-push.txt" \
    "$evidence/legacy-property-push.stderr.txt" 60 \
    push "$provisioned_property" /data/local/tmp/nepa-prop.default
  capture_adb_with_retries \
    "$evidence/legacy-property-copy.txt" \
    "$evidence/legacy-property-copy.stderr.txt" 30 \
    shell su 0 cp /data/local/tmp/nepa-prop.default /system/etc/prop.default
  capture_adb_with_retries \
    "$evidence/legacy-property-sync.txt" \
    "$evidence/legacy-property-sync.stderr.txt" 30 shell su 0 sync
  capture_adb_with_retries \
    "$roundtrip_property" "$evidence/legacy-roundtrip-prop.stderr.txt" 30 \
    shell su 0 cat /system/etc/prop.default
  cmp "$provisioned_property" "$roundtrip_property"
  grep -Fx 'ro.hw_timeout_multiplier=10' "$roundtrip_property"
  sha256sum "$source_property" "$provisioned_property" "$roundtrip_property" \
    >"$evidence/legacy-property-files-sha256.txt"

  capture_adb_with_retries \
    "$evidence/legacy-reboot.txt" "$evidence/legacy-reboot.stderr.txt" 30 reboot
  while (( SECONDS - transition_started < 120 )); do
    device_state="$(
      timeout 5 "$adb" -s "$serial" get-state 2>/dev/null || true
    )"
    boot_value="$(
      timeout 5 "$adb" -s "$serial" shell getprop sys.boot_completed \
        2>/dev/null | tr -d '\r' || true
    )"
    if [[ "$device_state" != device || "$boot_value" != 1 ]]; then
      transition_seen=1
      break
    fi
    sleep 1
  done
  {
    printf 'offline_transition_verified=%s\n' \
      "$([[ "$transition_seen" == 1 ]] && printf true || printf false)"
    printf 'elapsed_seconds=%s\n' "$((SECONDS - transition_started))"
    printf 'device_state=%s\n' "${device_state:-unavailable}"
    printf 'boot_completed=%s\n' "${boot_value:-unset}"
  } >"$evidence/legacy-reboot-transition.txt"
  [[ "$transition_seen" == 1 ]]
  timeout 600 "$adb" -s "$serial" wait-for-device
  wait_for_emulator_ready \
    "$serial" legacy_timeout_reboot \
    "$evidence/legacy-timeout-reboot-status.txt" 1200
  capture_adb_with_retries \
    "$evidence/legacy-timeout-device-property.raw.txt" \
    "$evidence/legacy-timeout-device-property.stderr.txt" 30 \
    shell getprop ro.hw_timeout_multiplier
  tr -d '\r' <"$evidence/legacy-timeout-device-property.raw.txt" \
    >"$evidence/legacy-timeout-device-property.txt"
  grep -Fx '10' "$evidence/legacy-timeout-device-property.txt"
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
  timeout 600 "$adb" -s "$runner_serial" wait-for-device
  wait_for_emulator_ready \
    "$runner_serial" stabilized_boot "$evidence/boot-status.txt" 1200
  timeout 600 "$adb" -s "$runner_serial" shell am wait-for-broadcast-idle \
    | tr -d '\r' >"$evidence/stabilization-broadcast-idle.txt"
  require_home_ui_ready \
    "$runner_serial" "$evidence/post-reboot-ui" 180
}

install_test_apk() {
  local runner_serial="$1"
  local apk="$2"
  local label="$3"
  local attempt
  local install_log
  for attempt in 1 2; do
    install_log="$evidence/${label}-install-attempt-${attempt}.txt"
    if timeout 240 "$adb" -s "$runner_serial" install --no-streaming -r -t "$apk" \
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

run_script_rendering() {
  timeout 600 "$adb" -s "$serial" shell am instrument -w -r \
    com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.InternalScriptRenderingInstrumentation \
    | tr -d '\r' \
    | tee "$evidence/script-rendering.txt"
  require_instrumentation_success "$evidence/script-rendering.txt"
  grep -F "api_level=$expected_api" "$evidence/script-rendering.txt"
  for result in \
    profile_id=new-Newa-NP \
    newa_font_sha256=dc8aea050ac05dea01c6a81e6a70d4a7506998a11c6e1ecaaa854b7ff18f9fc6 \
    newa_base_keys_bundled_font_verified=true \
    newa_shift_keys_bundled_font_verified=true \
    newa_symbol_keys_bundled_font_verified=true \
    newa_candidate_bundled_font_verified=true \
    newa_sample_glyph_coverage_verified=true \
    newa_pixel_width_geometry_verified=true \
    render_file=ime-script-rendering-newa-api${expected_api}.png \
    render_width=1080; do
    require_instrumentation_result "$evidence/script-rendering.txt" "$result"
  done
  local render_file="ime-script-rendering-newa-api${expected_api}.png"
  timeout 60 "$adb" -s "$serial" exec-out run-as \
    com.ampixa.nepakeyboard.ime.internal cat "files/$render_file" \
    >"$evidence/$render_file"
  [[ -s "$evidence/$render_file" ]]
  sha256sum "$evidence/$render_file" >"$evidence/script-rendering-sha256.txt"
}

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
  ps -eo pid,comm,%cpu,%mem,rss --sort=-rss | sed -n '1,20p'
} >"$evidence/host-preflight.txt"

home_available_kib="$(df -Pk /home | awk 'NR == 2 {print $4}')"
tmp_available_kib="$(df -Pk /tmp | awk 'NR == 2 {print $4}')"
if [[ ! "$home_available_kib" =~ ^[0-9]+$ \
      || ! "$tmp_available_kib" =~ ^[0-9]+$ \
      || "$home_available_kib" -lt $((12 * 1024 * 1024)) \
      || "$tmp_available_kib" -lt $((4 * 1024 * 1024)) ]]; then
  echo "cdjk has insufficient free disk for Android validation" >&2
  exit 1
fi

for required in awk cmp cp cut df find flock free grep hostname jq mv pgrep ps \
  rm sed seq sort timeout tr unzip uptime xargs sha256sum "$adb" "$emulator"; do
  if [[ "$required" == /* ]]; then
    [[ -x "$required" ]]
  else
    command -v "$required" >/dev/null
  fi
done
exec 9>/tmp/nepa-keyboard-android-validation.lock
if ! flock -n 9; then
  echo "another Nepa Android validation owns the cdjk lock" >&2
  exit 1
fi
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
for executable in "$adb" "$emulator"; do
  [[ -x "$executable" ]]
done
[[ -s "$internal_apk" ]]
[[ -s "$internal_lock" ]]
[[ -s "$internal_layout_lock" ]]
[[ -s "$base_ramdisk" ]]
if [[ -n "$base_system" ]]; then
  [[ -s "$base_system" ]]
fi
if [[ -n "$base_vendor" ]]; then
  [[ -s "$base_vendor" ]]
fi
if [[ -n "$base_encryption_key" ]]; then
  [[ -s "$base_encryption_key" ]]
fi
if [[ -n "$timeout_ramdisk" ]]; then
  [[ -s "$timeout_ramdisk" ]]
fi

# Bind the focused runtime proof to the source tree it inspects. The build is
# intentionally an outer cdjk step, so reject a conventional-path APK when any
# of its source inputs are newer instead of silently installing stale bytecode.
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

[[ "$(sha256sum "$base_ramdisk" | cut -d' ' -f1)" \
  == "$expected_base_ramdisk_sha256" ]]
if [[ -n "$base_system" ]]; then
  [[ "$(sha256sum "$base_system" | cut -d' ' -f1)" \
    == "$expected_base_system_sha256" ]]
fi
if [[ -n "$base_vendor" ]]; then
  [[ "$(sha256sum "$base_vendor" | cut -d' ' -f1)" \
    == "$expected_base_vendor_sha256" ]]
fi
if [[ -n "$base_encryption_key" ]]; then
  [[ "$(sha256sum "$base_encryption_key" | cut -d' ' -f1)" \
    == "$expected_base_encryption_key_sha256" ]]
fi
if [[ -n "$timeout_ramdisk" ]]; then
  [[ "$(sha256sum "$timeout_ramdisk" | cut -d' ' -f1)" \
    == "$expected_timeout_ramdisk_sha256" ]]
  grep -Fx 'remote_exit_status=0' "$timeout_ramdisk_root/run-status.txt"
  grep -Fx 'multiplier=10' "$timeout_ramdisk_root/build-parameters.txt"
  sha256sum "$base_ramdisk" "$timeout_ramdisk" \
    >"$evidence/timeout-ramdisk-sha256.txt"
  cp "$timeout_ramdisk_root/artifact-sha256.txt" \
    "$evidence/timeout-ramdisk-build-artifact-sha256.txt"
else
  sha256sum "$base_ramdisk" >"$evidence/base-ramdisk-sha256.txt"
fi
if [[ -n "$base_system" ]]; then
  sha256sum "$base_system" >"$evidence/base-system-sha256.txt"
fi
if [[ -n "$base_vendor" ]]; then
  sha256sum "$base_vendor" >"$evidence/base-vendor-sha256.txt"
fi
if [[ -n "$base_encryption_key" ]]; then
  sha256sum "$base_encryption_key" \
    >"$evidence/base-encryption-key-sha256.txt"
fi
printf 'ramdisk_mode=%s\n' "$ramdisk_mode" >"$evidence/ramdisk-mode.txt"
printf 'runtime_timeout_mode=%s\n' "$runtime_timeout_mode" \
  >"$evidence/runtime-timeout-mode.txt"
printf 'validation_mode=%s\n' "$validation_mode" >"$evidence/validation-mode.txt"
sha256sum "$internal_apk" >"$evidence/internal-apk-sha256.txt"
sha256sum "$internal_lock" "$internal_layout_lock" \
  >"$evidence/lock-sha256.txt"
cp "$internal_lock" "$evidence/internal-profiles.lock.json"
cp "$internal_layout_lock" "$evidence/internal-layouts-v1.lock.json"
unzip -p "$internal_apk" assets/nepa-conformance/runtime-v2.json \
  >"$evidence/runtime-conformance-v2.json"
profile_lock_sha="$(sha256sum "$internal_lock" | cut -d' ' -f1)"
layout_lock_sha="$(sha256sum "$internal_layout_lock" | cut -d' ' -f1)"
jq -e \
  --arg profile_lock_sha "$profile_lock_sha" \
  --arg layout_lock_sha "$layout_lock_sha" \
  --argjson selectable "$(jq '.counts.selectable' "$internal_lock")" \
  '.profile_lock_sha256 == $profile_lock_sha
   and .layout_lock_sha256 == $layout_lock_sha
   and .selectable_profile_count == $selectable
   and (.profiles | length) == $selectable' \
  "$evidence/runtime-conformance-v2.json"
sha256sum "$evidence/runtime-conformance-v2.json" \
  >"$evidence/runtime-conformance-sha256.txt"
"$emulator" -version >"$evidence/emulator-version.txt" 2>&1
"$emulator" -list-avds >"$evidence/available-avds.txt"
grep -Fx "$avd_name" "$evidence/available-avds.txt"
avd_ini="$HOME/.android/avd/${avd_name}.ini"
[[ -s "$avd_ini" ]]
cp "$avd_ini" "$evidence/avd.ini"
avd_path="$(awk -F= '$1 == "path" {sub(/^[^=]*=/, ""); print; exit}' "$avd_ini")"
[[ "$avd_path" == /* && "$avd_path" != /Users/* ]]
[[ -s "$avd_path/config.ini" ]]
cp "$avd_path/config.ini" "$evidence/avd-config.ini"

"$adb" start-server >/dev/null
if "$adb" devices | grep -q "^${serial}[[:space:]]"; then
  echo "$serial is already in use" >&2
  exit 1
fi

"$emulator" \
  -avd "$avd_name" \
  -port 5558 \
  -accel off \
  -cores 4 \
  -memory 4096 \
  -gpu swiftshader_indirect \
  "${emulator_boot_args[@]}" \
  -no-window \
  -no-audio \
  -no-boot-anim \
  -no-snapshot \
  -wipe-data \
  >"$evidence/emulator.log" 2>&1 &
emulator_pid=$!

timeout 600 "$adb" -s "$serial" wait-for-device
if [[ "$expected_api" == 34 ]]; then
  wait_for_emulator_ready \
    "$serial" factory_boot "$evidence/factory-boot-status.txt" 1800
  capture_factory_boot_diagnostics "$serial"
  timeout 600 "$adb" -s "$serial" shell am wait-for-broadcast-idle \
    | tr -d '\r' >"$evidence/factory-boot-broadcast-idle.txt"
  require_home_ui_ready \
    "$serial" "$evidence/post-factory-ui" 180
else
  wait_for_emulator_ready \
    "$serial" emulator "$evidence/boot-status.txt" 900
  provision_legacy_timeout_overlay
fi

timeout 10 "$adb" -s "$serial" shell dumpsys user \
  | tr -d '\r' >"$evidence/user-state.txt"
[[ "$(user_zero_unlocked "$serial")" == true ]]

{
  "$adb" -s "$serial" shell getprop ro.build.version.sdk
  "$adb" -s "$serial" shell getprop ro.product.cpu.abi
  "$adb" -s "$serial" shell getprop ro.kernel.qemu
  "$adb" -s "$serial" shell getprop sys.boot_completed
  "$adb" -s "$serial" shell getprop ro.hw_timeout_multiplier
} | tr -d '\r' >"$evidence/device-properties.txt"
grep -Fx "$expected_api" "$evidence/device-properties.txt"
[[ "$(sed -n '3p' "$evidence/device-properties.txt")" == 1 ]]
[[ "$(sed -n '4p' "$evidence/device-properties.txt")" == 1 ]]
[[ "$(sed -n '5p' "$evidence/device-properties.txt")" == 10 ]]
for property in \
  ro.build.fingerprint \
  ro.system.build.fingerprint \
  ro.build.description \
  ro.build.id \
  ro.build.version.incremental \
  ro.build.version.security_patch \
  ro.product.cpu.abilist; do
  printf '%s=' "$property" >>"$evidence/device-identity.txt"
  "$adb" -s "$serial" shell getprop "$property" \
    | tr -d '\r' >>"$evidence/device-identity.txt"
done
"$adb" -s "$serial" shell settings put secure show_ime_with_hard_keyboard 1

install_test_apk "$serial" "$internal_apk" internal-ime
"$adb" -s "$serial" shell pm list instrumentation \
  >"$evidence/instrumentations.txt"
grep -F 'InternalSubtypeCompatibilityInstrumentation' \
  "$evidence/instrumentations.txt"
grep -F 'InternalScriptRenderingInstrumentation' \
  "$evidence/instrumentations.txt"
run_script_rendering
if [[ "$validation_mode" == render-only ]]; then
  sequence_complete=1
  exit 0
fi
ime_metadata_wait_start=$SECONDS
ime_metadata_attempts=0
while true; do
  ime_metadata_attempts=$((ime_metadata_attempts + 1))
  timeout 10 "$adb" -s "$serial" shell ime list -a -s \
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
    timeout 20 "$adb" -s "$serial" shell dumpsys input_method \
      >"$evidence/installed-ime-metadata-timeout-dumpsys.txt" 2>&1 || true
    echo "installed input-method metadata readiness timed out" >&2
    exit 1
  fi
  sleep 1
done
"$adb" -s "$serial" shell ime enable "$ime_component" \
  >"$evidence/ime-enable.txt"
"$adb" -s "$serial" shell ime set "$ime_component" \
  >"$evidence/ime-set.txt"
"$adb" -s "$serial" shell settings get secure default_input_method \
  | tr -d '\r' >"$evidence/default-ime.txt"
grep -Fx "$ime_component" "$evidence/default-ime.txt"
require_home_ui_ready "$serial" "$evidence/pre-instrument-ui" 180

timeout 1800 "$adb" -s "$serial" shell am instrument -w -r \
  com.ampixa.nepakeyboard.ime.internal/\
com.ampixa.nepakeyboard.ime.InternalSubtypeCompatibilityInstrumentation \
  | tr -d '\r' \
  | tee "$evidence/subtype-compatibility.txt"
require_instrumentation_success "$evidence/subtype-compatibility.txt"
grep -F "api_level=$expected_api" "$evidence/subtype-compatibility.txt"
grep -F 'service_bound_picker_subtype_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'service_bound_phonetic_emoji_editing_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'service_bound_globe_subtype_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'platform_subtype_confirmation_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'service_bound_held_delete_password_restart_cancel_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'service_bound_held_delete_private_no_context_read_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'private_emoji_recents_suppressed_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'service_bound_held_delete_hide_cancel_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'service_bound_held_delete_finish_cancel_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'service_bound_held_delete_post_cancel_dispatch_stability_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'focus_driven_ime_readiness_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'initial_editor_window_focus_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -F 'initial_editor_view_focus_verified=true' \
  "$evidence/subtype-compatibility.txt"
grep -Eq \
  '^INSTRUMENTATION_RESULT: password_restart_cancel_observed_elapsed_ms=[0-9]+$' \
  "$evidence/subtype-compatibility.txt"
if (( expected_api <= 27 )); then
  grep -F 'switch_path=legacy_ime_window_token' \
    "$evidence/subtype-compatibility.txt"
  grep -F 'legacy_window_token_present=true' \
    "$evidence/subtype-compatibility.txt"
  grep -F 'managed_enabled_subtypes_verified=false' \
    "$evidence/subtype-compatibility.txt"
else
  grep -F 'switch_path=input_method_service' \
    "$evidence/subtype-compatibility.txt"
  grep -F 'same_service_subtype_callback_after_picker_verified=true' \
    "$evidence/subtype-compatibility.txt"
  grep -F 'same_service_subtype_callback_after_globe_verified=true' \
    "$evidence/subtype-compatibility.txt"
  grep -F 'managed_enabled_subtypes_verified=true' \
    "$evidence/subtype-compatibility.txt"
fi
for result in \
  service_bound_picker_subtype_verified=true \
  service_bound_globe_subtype_verified=true \
  platform_subtype_confirmation_verified=true \
  service_bound_held_delete_password_restart_cancel_verified=true \
  service_bound_held_delete_private_no_context_read_verified=true \
  service_bound_held_delete_hide_cancel_verified=true \
  service_bound_held_delete_finish_cancel_verified=true \
  focus_driven_ime_readiness_verified=true \
  initial_editor_window_focus_verified=true \
  initial_editor_view_focus_verified=true \
  private_context_read_count=0; do
  require_instrumentation_result "$evidence/subtype-compatibility.txt" "$result"
done
if (( expected_api <= 27 )); then
  for result in \
    switch_path=legacy_ime_window_token \
    legacy_window_token_present=true \
    managed_enabled_subtypes_verified=false; do
    require_instrumentation_result "$evidence/subtype-compatibility.txt" "$result"
  done
else
  for result in \
    switch_path=input_method_service \
    same_service_subtype_callback_after_picker_verified=true \
    same_service_subtype_callback_after_globe_verified=true \
    managed_enabled_subtypes_verified=true; do
    require_instrumentation_result "$evidence/subtype-compatibility.txt" "$result"
  done
fi

timeout 60 "$adb" -s "$serial" shell dumpsys input_method \
  >"$evidence/input-method-dumpsys.txt"
timeout 60 "$adb" -s "$serial" shell dumpsys window \
  >"$evidence/window-dumpsys.txt"
timeout 60 "$adb" -s "$serial" logcat -d -v threadtime \
  >"$evidence/logcat.txt"

sequence_complete=1
exit 0
