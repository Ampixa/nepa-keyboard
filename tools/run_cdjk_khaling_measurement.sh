#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ $# -ne 1 || "$1" != /* ]]; then
  echo "usage: $0 /absolute/new/evidence-directory" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
raw=/home/cdjk/github/llm/rai-speech-toolkit/dialects/western/khaling/dict/nepali-khaling.sil-apk.dict.jsonl
relock_runner="$repo/tools/run_cdjk_relock_validation.sh"
matrix_runner="$repo/tools/run_cdjk_sil_apk_layout_matrix.sh"
profile_lock="$repo/catalog/internal-profiles.lock.json"
layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
android_pins="$repo/android/ime-app/build.gradle.kts"
expected_raw_sha256=442415559f1ec6191b2624e27439cc22438aaf24d19b4124571c826774c2adb4
stage=initializing
relock_verified=0
matrix_verified=0
sequence_complete=0

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this Khaling measurement must run from the cdjk Ubuntu checkout" >&2
  exit 1
fi

for required in awk bash basename cmp dirname find grep hostname jq mkdir mv \
  realpath rm sha256sum sort tee uname xargs; do
  command -v "$required" >/dev/null || {
    echo "required command is missing: $required" >&2
    exit 1
  }
done

evidence_parent="$(realpath -e -- "$(dirname -- "$1")")"
evidence="$evidence_parent/$(basename -- "$1")"
if [[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]; then
  echo "evidence directory must be outside the source checkout" >&2
  exit 1
fi
if [[ -e "$evidence" ]]; then
  echo "evidence directory already exists: $evidence" >&2
  exit 1
fi
mkdir "$evidence"

write_manifest() {
  local temporary="$evidence/.final-evidence-sha256.txt.tmp"
  rm -f "$temporary"
  (
    cd "$evidence"
    LC_ALL=C find . -type f \
      ! -path ./final-evidence-sha256.txt \
      ! -path ./.final-evidence-sha256.txt.tmp \
      -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 -r sha256sum
  ) >"$temporary" || {
    rm -f "$temporary"
    return 1
  }
  mv "$temporary" "$evidence/final-evidence-sha256.txt"
}

write_status() {
  local command_status="$1"
  local manifest_status="$2"
  local final_status="$3"
  local temporary="$evidence/.run-status.txt.tmp"
  {
    printf 'completed_stage=%s\n' "$stage"
    printf 'relock_verified=%s\n' "$relock_verified"
    printf 'matrix_verified=%s\n' "$matrix_verified"
    printf 'sequence_complete=%s\n' "$sequence_complete"
    printf 'command_exit_status=%s\n' "$command_status"
    printf 'manifest_exit_status=%s\n' "$manifest_status"
    printf 'remote_exit_status=%s\n' "$final_status"
  } >"$temporary"
  mv "$temporary" "$evidence/run-status.txt"
}

on_exit() {
  local command_status=$?
  trap - EXIT
  set +e
  local final_status=$command_status
  local manifest_status=0
  if (( command_status == 0 && sequence_complete != 1 )); then
    final_status=1
  fi
  write_status "$command_status" 0 "$final_status" || manifest_status=$?
  if (( manifest_status == 0 )); then
    write_manifest || manifest_status=$?
  fi
  if (( manifest_status != 0 )); then
    final_status=1
    write_status "$command_status" "$manifest_status" "$final_status" || true
    write_manifest || true
  fi
  if (( final_status == 0 )); then
    printf 'khaling_measurement_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

stage=input_validation
for input in \
  "$raw" \
  "$profile_lock" \
  "$layout_lock" \
  "$android_pins" \
  "$relock_runner" \
  "$matrix_runner" \
  "$repo/tools/run_cdjk_khaling_measurement.sh"; do
  if [[ -L "$input" || ! -s "$input" ]]; then
    echo "canonical input is missing, symbolic, or empty: $input" >&2
    exit 1
  fi
done
if [[ "$(realpath -e -- "$raw")" != "$raw" ]]; then
  echo "Khaling raw input path is not canonical" >&2
  exit 1
fi
actual_raw_sha256="$(sha256sum "$raw" | awk '{print $1}')"
if [[ "$actual_raw_sha256" != "$expected_raw_sha256" ]]; then
  echo "Khaling raw input SHA-256 does not match the catalog pin" >&2
  exit 1
fi
sha256sum \
  "$raw" \
  "$profile_lock" \
  "$layout_lock" \
  "$android_pins" \
  "$relock_runner" \
  "$matrix_runner" \
  "$repo/tools/run_cdjk_khaling_measurement.sh" \
  >"$evidence/input-source-sha256.txt"

stage=internal_relock
bash "$relock_runner" "$evidence/relock" 2>&1 \
  | tee "$evidence/relock.stdout.txt"
grep -Fx 'transaction_committed=1' "$evidence/relock/run-status.txt"
grep -Fx 'rollback_exit_status=0' "$evidence/relock/run-status.txt"
grep -Fx 'manifest_exit_status=0' "$evidence/relock/run-status.txt"
grep -Fx 'remote_exit_status=0' "$evidence/relock/run-status.txt"
grep -Fx "relock_complete evidence=$evidence/relock" \
  "$evidence/relock.stdout.txt"
relock_verified=1
sha256sum "$profile_lock" "$layout_lock" "$android_pins" \
  >"$evidence/active-internal-state-after-relock.txt"

stage=layout_matrix
bash "$matrix_runner" \
  klr \
  klr-apk \
  "$raw" \
  sil-apk/khaling \
  "$evidence/layout-matrix" 2>&1 \
  | tee "$evidence/layout-matrix.stdout.txt"
grep -Fx 'audit_complete=1' "$evidence/layout-matrix/run-status.txt"
grep -Fx 'summary_verified=1' "$evidence/layout-matrix/run-status.txt"
grep -Fx 'manifest_exit_status=0' "$evidence/layout-matrix/run-status.txt"
grep -Fx 'remote_exit_status=0' "$evidence/layout-matrix/run-status.txt"
grep -Fx "sil_apk_layout_matrix_complete evidence=$evidence/layout-matrix" \
  "$evidence/layout-matrix.stdout.txt"
jq -e --arg raw_sha256 "$expected_raw_sha256" '
  .format_version == 1
  and .target.id == "klr"
  and .target.iso_639_3 == "klr"
  and .resource_id == "klr-apk"
  and .raw_input.source_tag == "sil-apk/khaling"
  and .raw_input.sha256 == $raw_sha256
  and .raw_input.records == 4513
  and .raw_input.bytes == 558925
  and (.layout_count | type == "number" and . > 0)
  and ((.ranking | length) == .layout_count)
' "$evidence/layout-matrix/layout-matrix-summary.json" >/dev/null
matrix_verified=1
sha256sum "$profile_lock" "$layout_lock" "$android_pins" \
  >"$evidence/active-internal-state-after-matrix.txt"
cmp "$evidence/active-internal-state-after-relock.txt" \
  "$evidence/active-internal-state-after-matrix.txt"

stage=sequence_summary
jq -S -n \
  --slurpfile matrix "$evidence/layout-matrix/layout-matrix-summary.json" \
  --arg evidence "$evidence" \
  --arg raw "$raw" \
  --arg raw_sha256 "$expected_raw_sha256" '
  {
    format_version: 1,
    claim_scope: (
      "Measured Khaling layout-input compatibility only; layout, joiner "
      + "policy, prefix vectors, and production promotion remain unselected."
    ),
    target_id: "klr",
    resource_id: "klr-apk",
    source_tag: "sil-apk/khaling",
    raw_input: {
      path: $raw,
      records: 4513,
      bytes: 558925,
      sha256: $raw_sha256
    },
    evidence_root: $evidence,
    relock_evidence: ($evidence + "/relock"),
    layout_matrix_evidence: ($evidence + "/layout-matrix"),
    internal_state_unchanged_during_matrix: true,
    layout_lock_sha256: $matrix[0].layout_lock_sha256,
    layout_count: $matrix[0].layout_count,
    measured_ranking: $matrix[0].ranking
  }
' >"$evidence/sequence-summary.json"
jq -e '
  .format_version == 1
  and .target_id == "klr"
  and .resource_id == "klr-apk"
  and .internal_state_unchanged_during_matrix == true
  and (.layout_count | type == "number" and . > 0)
  and ((.measured_ranking | length) == .layout_count)
  and (.claim_scope | contains("remain unselected"))
' "$evidence/sequence-summary.json" >/dev/null
sequence_complete=1
stage=complete
