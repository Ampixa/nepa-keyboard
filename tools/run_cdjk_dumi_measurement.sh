#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ $# -ne 2 || "$1" != /* || "$2" != /* ]]; then
  echo "usage: $0 /absolute/completed-khaling-evidence /absolute/new/dumi-evidence" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
raw=/home/cdjk/github/llm/rai-speech-toolkit/dialects/western/dumi/dict/nepali-dumi.sil-apk.dict.jsonl
relock_runner="$repo/tools/run_cdjk_relock_validation.sh"
matrix_runner="$repo/tools/run_cdjk_sil_apk_layout_matrix.sh"
profile_lock="$repo/catalog/internal-profiles.lock.json"
layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
resource_catalog="$repo/catalog/resources.json"
android_pins="$repo/android/ime-app/build.gradle.kts"
expected_raw_sha256=1d8453339c727ee5c63fc4fbf64ec80619ea82cc559b31b9224826e1d0902ffc
expected_khaling_raw_sha256=442415559f1ec6191b2624e27439cc22438aaf24d19b4124571c826774c2adb4
stage=initializing
khaling_prerequisite_verified=0
relock_verified=0
matrix_verified=0
sequence_complete=0

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this Dumi measurement must run from the cdjk Ubuntu checkout" >&2
  exit 1
fi

for required in awk bash basename cmp dirname find grep hostname jq mkdir mv \
  realpath rm sha256sum sort tee uname wc xargs; do
  command -v "$required" >/dev/null || {
    echo "required command is missing: $required" >&2
    exit 1
  }
done

khaling_argument="$1"
if [[ -L "$khaling_argument" || ! -d "$khaling_argument" ]]; then
  echo "Khaling prerequisite must be a non-symbolic evidence directory" >&2
  exit 1
fi
khaling_evidence="$(realpath -e -- "$khaling_argument")"
if [[ "$khaling_evidence" != "$khaling_argument" ]]; then
  echo "Khaling evidence path must be canonical" >&2
  exit 1
fi
if [[ "$khaling_evidence" == "$repo" || "$khaling_evidence" == "$repo/"* ]]; then
  echo "Khaling evidence directory must be outside the source checkout" >&2
  exit 1
fi

evidence_parent="$(realpath -e -- "$(dirname -- "$2")")"
evidence="$evidence_parent/$(basename -- "$2")"
if [[ "$evidence" != "$2" ]]; then
  echo "new Dumi evidence path must be canonical" >&2
  exit 1
fi
if [[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]; then
  echo "evidence directory must be outside the source checkout" >&2
  exit 1
fi
if [[ "$evidence" == "$khaling_evidence"
      || "$evidence" == "$khaling_evidence/"* ]]; then
  echo "Dumi evidence must not modify the Khaling prerequisite tree" >&2
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

recreate_khaling_manifest() {
  local output="$1"
  if find "$khaling_evidence" -type l -print -quit | grep -q .; then
    echo "Khaling prerequisite tree contains a symbolic link" >&2
    return 1
  fi
  (
    cd "$khaling_evidence"
    LC_ALL=C find . -type f \
      ! -path ./final-evidence-sha256.txt \
      ! -path ./.final-evidence-sha256.txt.tmp \
      -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 -r sha256sum
  ) >"$output"
}

write_status() {
  local command_status="$1"
  local manifest_status="$2"
  local final_status="$3"
  local temporary="$evidence/.run-status.txt.tmp"
  {
    printf 'completed_stage=%s\n' "$stage"
    printf 'khaling_prerequisite_verified=%s\n' "$khaling_prerequisite_verified"
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
    printf 'dumi_measurement_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

stage=input_validation
for input in \
  "$raw" \
  "$resource_catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$android_pins" \
  "$relock_runner" \
  "$matrix_runner" \
  "$repo/tools/run_cdjk_dumi_measurement.sh"; do
  if [[ -L "$input" || ! -s "$input" ]]; then
    echo "canonical input is missing, symbolic, or empty: $input" >&2
    exit 1
  fi
done
if [[ "$(realpath -e -- "$raw")" != "$raw" ]]; then
  echo "Dumi raw input path is not canonical" >&2
  exit 1
fi

stage=khaling_prerequisite
for prerequisite in \
  "$khaling_evidence/final-evidence-sha256.txt" \
  "$khaling_evidence/run-status.txt" \
  "$khaling_evidence/sequence-summary.json"; do
  if [[ -L "$prerequisite" || ! -s "$prerequisite" ]]; then
    echo "Khaling prerequisite file is missing, symbolic, or empty: $prerequisite" >&2
    exit 1
  fi
done
recreate_khaling_manifest \
  "$evidence/khaling-recreated-final-evidence-sha256.before.txt"
cmp "$khaling_evidence/final-evidence-sha256.txt" \
  "$evidence/khaling-recreated-final-evidence-sha256.before.txt"
(
  cd "$khaling_evidence"
  sha256sum -c final-evidence-sha256.txt
) >"$evidence/khaling-evidence-manifest-check.txt"
{
  printf 'completed_stage=complete\n'
  printf 'relock_verified=1\n'
  printf 'matrix_verified=1\n'
  printf 'sequence_complete=1\n'
  printf 'command_exit_status=0\n'
  printf 'manifest_exit_status=0\n'
  printf 'remote_exit_status=0\n'
} >"$evidence/expected-khaling-run-status.txt"
cmp "$evidence/expected-khaling-run-status.txt" \
  "$khaling_evidence/run-status.txt"
jq -e \
  --arg raw_sha256 "$expected_khaling_raw_sha256" \
  --arg evidence "$khaling_evidence" '
  .format_version == 1
  and .target_id == "klr"
  and .resource_id == "klr-apk"
  and .source_tag == "sil-apk/khaling"
  and .raw_input.path == (
    "/home/cdjk/github/llm/rai-speech-toolkit/dialects/western/"
    + "khaling/dict/nepali-khaling.sil-apk.dict.jsonl"
  )
  and .raw_input.sha256 == $raw_sha256
  and .raw_input.records == 4513
  and .raw_input.bytes == 558925
  and .evidence_root == $evidence
  and .relock_evidence == ($evidence + "/relock")
  and .layout_matrix_evidence == ($evidence + "/layout-matrix")
  and .internal_state_unchanged_during_matrix == true
  and (.claim_scope | contains("remain unselected"))
' "$khaling_evidence/sequence-summary.json" >/dev/null
khaling_manifest_sha256="$(sha256sum \
  "$khaling_evidence/final-evidence-sha256.txt" | awk '{print $1}')"
khaling_status_sha256="$(sha256sum \
  "$khaling_evidence/run-status.txt" | awk '{print $1}')"
khaling_summary_sha256="$(sha256sum \
  "$khaling_evidence/sequence-summary.json" | awk '{print $1}')"
sha256sum \
  "$khaling_evidence/final-evidence-sha256.txt" \
  "$khaling_evidence/run-status.txt" \
  "$khaling_evidence/sequence-summary.json" \
  >"$evidence/khaling-prerequisite-sha256.txt"
khaling_prerequisite_verified=1

stage=dumi_input_validation
actual_raw_sha256="$(sha256sum "$raw" | awk '{print $1}')"
actual_raw_records="$(LC_ALL=C awk 'END {print NR}' "$raw")"
actual_raw_bytes="$(wc -c <"$raw" | awk '{print $1}')"
if [[ "$actual_raw_sha256" != "$expected_raw_sha256"
      || "$actual_raw_records" != 2252
      || "$actual_raw_bytes" != 277511 ]]; then
  echo "Dumi raw input identity does not match the catalog pin" >&2
  exit 1
fi
sha256sum \
  "$raw" \
  "$resource_catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$android_pins" \
  "$relock_runner" \
  "$matrix_runner" \
  "$repo/tools/run_cdjk_dumi_measurement.sh" \
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
jq -e '
  [.packs[] | select(.id == "dus")] as $targets
  | ($targets | length) == 1
  and $targets[0].iso_639_3 == "dus"
  and ([$targets[0].input_methods[] | select(.id == "dus-deva-direct")]
       | length) == 1
  and ([$targets[0].resources[] | select(.id == "dus-apk")]
       | length) == 1
' "$resource_catalog" >/dev/null
jq -e '
  [.profiles[] | select(.profile_id == "dus-Deva-NP")] as $profiles
  | ($profiles | length) == 1
  and $profiles[0].target_id == "dus"
  and $profiles[0].input_method_id == "dus-deva-direct"
  and $profiles[0].layout_id == "pending-dus-deva-direct"
  and $profiles[0].selectable == false
  and $profiles[0].pack_artifact == null
  and $profiles[0].pack_binding == null
' "$profile_lock" >/dev/null
relock_verified=1
sha256sum "$profile_lock" "$layout_lock" "$android_pins" \
  >"$evidence/active-internal-state-after-relock.txt"

stage=layout_matrix
bash "$matrix_runner" \
  dus \
  dus-apk \
  "$raw" \
  sil-apk/dumi \
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
  and .target.id == "dus"
  and .target.iso_639_3 == "dus"
  and .resource_id == "dus-apk"
  and .raw_input.source_tag == "sil-apk/dumi"
  and .raw_input.sha256 == $raw_sha256
  and .raw_input.records == 2252
  and .raw_input.bytes == 277511
  and (.layout_count | type == "number" and . > 0)
  and ((.ranking | length) == .layout_count)
' "$evidence/layout-matrix/layout-matrix-summary.json" >/dev/null
matrix_verified=1
sha256sum "$profile_lock" "$layout_lock" "$android_pins" \
  >"$evidence/active-internal-state-after-matrix.txt"
cmp "$evidence/active-internal-state-after-relock.txt" \
  "$evidence/active-internal-state-after-matrix.txt"

stage=khaling_prerequisite_recheck
recreate_khaling_manifest \
  "$evidence/khaling-recreated-final-evidence-sha256.after.txt"
cmp "$khaling_evidence/final-evidence-sha256.txt" \
  "$evidence/khaling-recreated-final-evidence-sha256.after.txt"
(
  cd "$khaling_evidence"
  sha256sum -c final-evidence-sha256.txt
) >"$evidence/khaling-evidence-manifest-recheck.txt"
if [[ "$(sha256sum "$khaling_evidence/final-evidence-sha256.txt" \
          | awk '{print $1}')" != "$khaling_manifest_sha256"
      || "$(sha256sum "$khaling_evidence/run-status.txt" \
          | awk '{print $1}')" != "$khaling_status_sha256"
      || "$(sha256sum "$khaling_evidence/sequence-summary.json" \
          | awk '{print $1}')" != "$khaling_summary_sha256" ]]; then
  echo "Khaling prerequisite changed during the Dumi measurement" >&2
  exit 1
fi

stage=sequence_summary
jq -S -n \
  --slurpfile matrix "$evidence/layout-matrix/layout-matrix-summary.json" \
  --arg evidence "$evidence" \
  --arg raw "$raw" \
  --arg raw_sha256 "$expected_raw_sha256" \
  --arg k_evidence "$khaling_evidence" \
  --arg k_manifest_sha256 "$khaling_manifest_sha256" \
  --arg k_status_sha256 "$khaling_status_sha256" \
  --arg k_summary_sha256 "$khaling_summary_sha256" '
  {
    format_version: 1,
    claim_scope: (
      "Measured Dumi layout-input compatibility only; layout, joiner "
      + "policy, prefix vectors, and production promotion remain unselected."
    ),
    target_id: "dus",
    resource_id: "dus-apk",
    profile_id: "dus-Deva-NP",
    input_method_id: "dus-deva-direct",
    source_tag: "sil-apk/dumi",
    raw_input: {
      path: $raw,
      records: 2252,
      bytes: 277511,
      sha256: $raw_sha256
    },
    khaling_prerequisite: {
      verified: true,
      evidence_root: $k_evidence,
      final_manifest_sha256: $k_manifest_sha256,
      run_status_sha256: $k_status_sha256,
      sequence_summary_sha256: $k_summary_sha256
    },
    evidence_root: $evidence,
    relock_evidence: ($evidence + "/relock"),
    layout_matrix_evidence: ($evidence + "/layout-matrix"),
    dumi_profile_unselected_before_matrix: true,
    internal_state_unchanged_during_matrix: true,
    layout_lock_sha256: $matrix[0].layout_lock_sha256,
    layout_count: $matrix[0].layout_count,
    measured_ranking: $matrix[0].ranking
  }
' >"$evidence/sequence-summary.json"
jq -e '
  .format_version == 1
  and .target_id == "dus"
  and .resource_id == "dus-apk"
  and .profile_id == "dus-Deva-NP"
  and .input_method_id == "dus-deva-direct"
  and .khaling_prerequisite.verified == true
  and .dumi_profile_unselected_before_matrix == true
  and .internal_state_unchanged_during_matrix == true
  and (.layout_count | type == "number" and . > 0)
  and ((.measured_ranking | length) == .layout_count)
  and (.claim_scope | contains("remain unselected"))
' "$evidence/sequence-summary.json" >/dev/null
sequence_complete=1
stage=complete
