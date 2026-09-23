#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ $# -ne 2 || "$1" != /* || "$2" != /* ]]; then
  echo "usage: $0 /absolute/completed-dumi-evidence /absolute/new/bantawa-evidence" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
raw=/home/cdjk/github/llm/rai-speech-toolkit/dialects/central/bantawa/dict/bantawa-english.dict.jsonl
catalog="$repo/catalog/resources.json"
profile_lock="$repo/catalog/internal-profiles.lock.json"
layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
android_pins="$repo/android/ime-app/build.gradle.kts"
auditor="$repo/tools/audit_bantawa_jsonl_contract.py"
focused_test="$repo/tests/test_bantawa_jsonl_contract.py"
uv="$HOME/.local/bin/uv"
expected_raw_sha256=a69917c00e7a8587f4a38458faf89c95fc9e5ac9cbe6cfb612383438bdf5ae12
expected_dumi_raw_sha256=1d8453339c727ee5c63fc4fbf64ec80619ea82cc559b31b9224826e1d0902ffc
stage=initializing
dumi_prerequisite_verified=0
focused_tests_verified=0
double_parse_verified=0
state_unchanged=0
sequence_complete=0

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this Bantawa source probe must run from the cdjk Ubuntu checkout" >&2
  exit 1
fi

for required in awk basename cmp df dirname find flock free grep hostname jq \
  mkdir mv pgrep ps realpath rm sed sha256sum sort tee timeout uname uptime wc \
  xargs "$uv"; do
  if [[ "$required" == /* ]]; then
    [[ -x "$required" ]] || {
      echo "required executable is missing: $required" >&2
      exit 1
    }
  else
    command -v "$required" >/dev/null || {
      echo "required command is missing: $required" >&2
      exit 1
    }
  fi
done

dumi_argument="$1"
if [[ -L "$dumi_argument" || ! -d "$dumi_argument" ]]; then
  echo "Dumi prerequisite must be a non-symbolic evidence directory" >&2
  exit 1
fi
dumi_evidence="$(realpath -e -- "$dumi_argument")"
if [[ "$dumi_evidence" != "$dumi_argument" ]]; then
  echo "Dumi evidence path must be canonical" >&2
  exit 1
fi
if [[ "$dumi_evidence" == "$repo" || "$dumi_evidence" == "$repo/"* ]]; then
  echo "Dumi evidence directory must be outside the source checkout" >&2
  exit 1
fi

evidence_parent="$(realpath -e -- "$(dirname -- "$2")")"
evidence="$evidence_parent/$(basename -- "$2")"
if [[ "$evidence" != "$2" ]]; then
  echo "new Bantawa evidence path must be canonical" >&2
  exit 1
fi
if [[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]; then
  echo "Bantawa evidence directory must be outside the source checkout" >&2
  exit 1
fi
if [[ "$evidence" == "$dumi_evidence" || "$evidence" == "$dumi_evidence/"* ]]; then
  echo "Bantawa evidence must not modify the Dumi prerequisite tree" >&2
  exit 1
fi
if [[ -e "$evidence" ]]; then
  echo "evidence directory already exists: $evidence" >&2
  exit 1
fi
mkdir -p "$evidence/a" "$evidence/b" "$evidence/logs"

write_manifest() {
  local temporary="$evidence/.final-evidence-sha256.txt.tmp"
  rm -f "$temporary"
  if find "$evidence" -type l -print -quit | grep -q .; then
    echo "Bantawa evidence tree contains a symbolic link" >&2
    return 1
  fi
  if find "$evidence" ! -type d ! -type f -print -quit | grep -q .; then
    echo "Bantawa evidence tree contains a special filesystem node" >&2
    return 1
  fi
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

recreate_dumi_manifest() {
  local output="$1"
  if find "$dumi_evidence" -type l -print -quit | grep -q .; then
    echo "Dumi prerequisite tree contains a symbolic link" >&2
    return 1
  fi
  (
    cd "$dumi_evidence"
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
    printf 'dumi_prerequisite_verified=%s\n' "$dumi_prerequisite_verified"
    printf 'focused_tests_verified=%s\n' "$focused_tests_verified"
    printf 'double_parse_verified=%s\n' "$double_parse_verified"
    printf 'state_unchanged=%s\n' "$state_unchanged"
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
    printf 'bantawa_source_probe_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

stage=input_metadata_validation
for input in \
  "$raw" \
  "$catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$android_pins" \
  "$auditor" \
  "$focused_test" \
  "$repo/tools/run_cdjk_bantawa_source_probe.sh"; do
  if [[ -L "$input" || ! -s "$input" ]]; then
    echo "canonical input is missing, symbolic, or empty: $input" >&2
    exit 1
  fi
done
if [[ "$(realpath -e -- "$raw")" != "$raw" ]]; then
  echo "Bantawa raw input path is not canonical" >&2
  exit 1
fi

stage=host_preflight
exec 9>/tmp/nepa-keyboard-android-validation.lock
if ! flock -n 9; then
  echo "another Nepa Android, relock, or corpus validation owns the cdjk lock" >&2
  exit 1
fi
available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
evidence_available_kib="$(df -Pk "$evidence_parent" | awk 'NR == 2 {print $4}')"
tmp_available_kib="$(df -Pk /tmp | awk 'NR == 2 {print $4}')"
if [[ ! "$available_kib" =~ ^[0-9]+$ ]] \
    || (( available_kib < 8 * 1024 * 1024 )); then
  echo "cdjk has less than 8 GiB available memory" >&2
  exit 1
fi
if [[ ! "$evidence_available_kib" =~ ^[0-9]+$ \
      || ! "$tmp_available_kib" =~ ^[0-9]+$ ]] \
    || (( evidence_available_kib < 2 * 1024 * 1024 \
          || tmp_available_kib < 1024 * 1024 )); then
  echo "cdjk has insufficient free disk for Bantawa source evidence" >&2
  exit 1
fi
if pgrep -af '[q]emu-system|[e]mulator' >"$evidence/preexisting-emulators.txt"; then
  echo "an Android emulator is already running on cdjk" >&2
  exit 1
fi
if pgrep -af '[p]ython.*(train|align|inference|mms|torch)' \
  >"$evidence/preexisting-heavy-python.txt"; then
  echo "a heavy Python workload is already running on cdjk" >&2
  exit 1
fi
if pgrep -af '[g]radle|[k]otlinc|[j]ava.*(GradleDaemon|org\.gradle|kotlinc)' \
  >"$evidence/preexisting-android-builds.txt"; then
  echo "another Android or Gradle workload is already running on cdjk" >&2
  exit 1
fi
ps -eo pid=,rss=,comm=,args= \
  | awk '$2 >= 8388608 {print}' >"$evidence/preexisting-high-rss-processes.txt"
if [[ -s "$evidence/preexisting-high-rss-processes.txt" ]]; then
  echo "a process already uses at least 8 GiB RSS on cdjk" >&2
  exit 1
fi
{
  hostname
  uptime
  free -h
  df -h "$evidence_parent" /tmp
  ps -eo pid,comm,%cpu,%mem,rss --sort=-rss | sed -n '1,20p'
} >"$evidence/host-preflight.txt"

stage=dumi_prerequisite
for prerequisite in \
  "$dumi_evidence/final-evidence-sha256.txt" \
  "$dumi_evidence/run-status.txt" \
  "$dumi_evidence/sequence-summary.json"; do
  if [[ -L "$prerequisite" || ! -s "$prerequisite" ]]; then
    echo "Dumi prerequisite file is missing, symbolic, or empty: $prerequisite" >&2
    exit 1
  fi
done
recreate_dumi_manifest \
  "$evidence/dumi-recreated-final-evidence-sha256.before.txt"
cmp "$dumi_evidence/final-evidence-sha256.txt" \
  "$evidence/dumi-recreated-final-evidence-sha256.before.txt"
(
  cd "$dumi_evidence"
  sha256sum -c final-evidence-sha256.txt
) >"$evidence/dumi-evidence-manifest-check.txt"
{
  printf 'completed_stage=complete\n'
  printf 'khaling_prerequisite_verified=1\n'
  printf 'relock_verified=1\n'
  printf 'matrix_verified=1\n'
  printf 'sequence_complete=1\n'
  printf 'command_exit_status=0\n'
  printf 'manifest_exit_status=0\n'
  printf 'remote_exit_status=0\n'
} >"$evidence/expected-dumi-run-status.txt"
cmp "$evidence/expected-dumi-run-status.txt" "$dumi_evidence/run-status.txt"
jq -e \
  --arg raw_sha256 "$expected_dumi_raw_sha256" \
  --arg evidence "$dumi_evidence" '
  .format_version == 1
  and .target_id == "dus"
  and .resource_id == "dus-apk"
  and .profile_id == "dus-Deva-NP"
  and .input_method_id == "dus-deva-direct"
  and .source_tag == "sil-apk/dumi"
  and .raw_input.path == (
    "/home/cdjk/github/llm/rai-speech-toolkit/dialects/western/"
    + "dumi/dict/nepali-dumi.sil-apk.dict.jsonl"
  )
  and .raw_input.sha256 == $raw_sha256
  and .raw_input.records == 2252
  and .raw_input.bytes == 277511
  and .khaling_prerequisite.verified == true
  and .evidence_root == $evidence
  and .relock_evidence == ($evidence + "/relock")
  and .layout_matrix_evidence == ($evidence + "/layout-matrix")
  and .dumi_profile_unselected_before_matrix == true
  and .internal_state_unchanged_during_matrix == true
  and (.claim_scope | contains("remain unselected"))
' "$dumi_evidence/sequence-summary.json" >/dev/null
dumi_manifest_sha256="$(sha256sum \
  "$dumi_evidence/final-evidence-sha256.txt" | awk '{print $1}')"
dumi_status_sha256="$(sha256sum \
  "$dumi_evidence/run-status.txt" | awk '{print $1}')"
dumi_summary_sha256="$(sha256sum \
  "$dumi_evidence/sequence-summary.json" | awk '{print $1}')"
sha256sum \
  "$dumi_evidence/final-evidence-sha256.txt" \
  "$dumi_evidence/run-status.txt" \
  "$dumi_evidence/sequence-summary.json" \
  >"$evidence/dumi-prerequisite-sha256.txt"
dumi_prerequisite_verified=1

stage=bantawa_input_validation
actual_raw_sha256="$(sha256sum "$raw" | awk '{print $1}')"
actual_raw_records="$(LC_ALL=C awk 'END {print NR}' "$raw")"
actual_raw_bytes="$(wc -c <"$raw" | awk '{print $1}')"
if [[ "$actual_raw_sha256" != "$expected_raw_sha256"
      || "$actual_raw_records" != 2040
      || "$actual_raw_bytes" != 360086 ]]; then
  echo "Bantawa raw input identity does not match the catalog pin" >&2
  exit 1
fi
jq -e '
  [.packs[] | select(.id == "bap")] as $targets
  | ($targets | length) == 1
  and $targets[0].iso_639_3 == "bap"
  and ([$targets[0].input_methods[] | select(.id == "bap-deva-direct")]
       | length) == 1
  and ([$targets[0].resources[] | select(.id == "bap-dictionary")]
       | length) == 1
' "$catalog" >/dev/null
jq -e '
  [.profiles[] | select(.profile_id == "bap-Deva-NP")] as $profiles
  | ($profiles | length) == 1
  and $profiles[0].target_id == "bap"
  and $profiles[0].input_method_id == "bap-deva-direct"
  and $profiles[0].layout_id == "pending-bap-deva-direct"
  and $profiles[0].selectable == false
  and $profiles[0].pack_artifact == null
  and $profiles[0].pack_binding == null
' "$profile_lock" >/dev/null
sha256sum \
  "$raw" \
  "$catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$android_pins" \
  "$auditor" \
  "$focused_test" \
  "$repo/tools/run_cdjk_bantawa_source_probe.sh" \
  >"$evidence/input-source-sha256.txt"
sha256sum "$catalog" "$profile_lock" "$layout_lock" "$android_pins" \
  >"$evidence/project-state.before.txt"

run_python() {
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
    timeout 900 "$uv" run --python 3.14 python "$@"
}

stage=focused_tests
cd "$repo"
run_python -m unittest discover -s tests -p test_bantawa_jsonl_contract.py \
  >"$evidence/logs/test-bantawa-jsonl-contract.txt" 2>&1
focused_tests_verified=1

stage=double_parse
run_python tools/audit_bantawa_jsonl_contract.py \
  --resource-catalog catalog/resources.json \
  --bantawa-jsonl "$raw" \
  --output "$evidence/a/bantawa-source-contract-v0.json" \
  >"$evidence/logs/a.json" 2>"$evidence/logs/a.log"
run_python tools/audit_bantawa_jsonl_contract.py \
  --resource-catalog catalog/resources.json \
  --bantawa-jsonl "$raw" \
  --output "$evidence/b/bantawa-source-contract-v0.json" \
  >"$evidence/logs/b.json" 2>"$evidence/logs/b.log"
cmp "$evidence/a/bantawa-source-contract-v0.json" \
  "$evidence/b/bantawa-source-contract-v0.json"
run_python tools/audit_bantawa_jsonl_contract.py \
  --resource-catalog catalog/resources.json \
  --bantawa-jsonl "$raw" \
  --output "$evidence/a/bantawa-source-contract-v0.json" \
  --check >"$evidence/logs/check.json" 2>"$evidence/logs/check.log"
report="$evidence/a/bantawa-source-contract-v0.json"
report_sha256="$(sha256sum "$report" | awk '{print $1}')"
for log in "$evidence/logs/a.json" "$evidence/logs/b.json" \
  "$evidence/logs/check.json"; do
  jq -e --arg sha256 "$report_sha256" '
    .status == "passed"
    and .report_sha256 == $sha256
  ' "$log" >/dev/null
done
jq -e --arg raw_sha256 "$expected_raw_sha256" '
  .format_version == 1
  and .auditor.name == "audit_bantawa_jsonl_contract"
  and .raw_input.target_id == "bap"
  and .raw_input.resource_id == "bap-dictionary"
  and .raw_input.path == (
    "/home/cdjk/github/llm/rai-speech-toolkit/dialects/central/"
    + "bantawa/dict/bantawa-english.dict.jsonl"
  )
  and .raw_input.records == 2040
  and .raw_input.bytes == 360086
  and .raw_input.sha256 == $raw_sha256
  and .runtime_contract.python_major_minor == "3.14"
  and .runtime_contract.unicode_data_version == "16.0.0"
  and .jsonl_contract.rows == 2040
  and (.jsonl_contract.ordered_field_signatures | length) > 0
  and ([.jsonl_contract.ordered_field_signatures[].count] | add) == 2040
  and (.jsonl_contract.ordered_field_type_signatures | length) > 0
  and ([.jsonl_contract.ordered_field_type_signatures[].count] | add) == 2040
  and (.jsonl_contract.field_inventories | length) > 0
  and .selections.candidate_field == null
  and .selections.headword_field == null
  and .selections.filter_policy == null
  and .selections.normalization_policy == null
  and .selections.joiner_policy == null
  and .selections.layout_id == null
  and .selections.prefix_vectors == []
  and .selections.pack_id == null
  and .selections.profile_promotion == false
  and (.claim_scope | contains("remain unselected"))
' "$report" >/dev/null
double_parse_verified=1

stage=state_comparison
sha256sum "$catalog" "$profile_lock" "$layout_lock" "$android_pins" \
  >"$evidence/project-state.after.txt"
cmp "$evidence/project-state.before.txt" "$evidence/project-state.after.txt"
state_unchanged=1

stage=dumi_prerequisite_recheck
recreate_dumi_manifest \
  "$evidence/dumi-recreated-final-evidence-sha256.after.txt"
cmp "$dumi_evidence/final-evidence-sha256.txt" \
  "$evidence/dumi-recreated-final-evidence-sha256.after.txt"
(
  cd "$dumi_evidence"
  sha256sum -c final-evidence-sha256.txt
) >"$evidence/dumi-evidence-manifest-recheck.txt"
if [[ "$(sha256sum "$dumi_evidence/final-evidence-sha256.txt" \
          | awk '{print $1}')" != "$dumi_manifest_sha256"
      || "$(sha256sum "$dumi_evidence/run-status.txt" \
          | awk '{print $1}')" != "$dumi_status_sha256"
      || "$(sha256sum "$dumi_evidence/sequence-summary.json" \
          | awk '{print $1}')" != "$dumi_summary_sha256" ]]; then
  echo "Dumi prerequisite changed during the Bantawa source probe" >&2
  exit 1
fi

stage=sequence_summary
field_count="$(jq -r '.jsonl_contract.field_inventories | length' "$report")"
field_signature_count="$(jq -r \
  '.jsonl_contract.ordered_field_signatures | length' "$report")"
type_signature_count="$(jq -r \
  '.jsonl_contract.ordered_field_type_signatures | length' "$report")"
jq -S -n \
  --arg evidence "$evidence" \
  --arg raw "$raw" \
  --arg raw_sha256 "$expected_raw_sha256" \
  --arg report "$report" \
  --arg report_sha256 "$report_sha256" \
  --arg d_evidence "$dumi_evidence" \
  --arg d_manifest_sha256 "$dumi_manifest_sha256" \
  --arg d_status_sha256 "$dumi_status_sha256" \
  --arg d_summary_sha256 "$dumi_summary_sha256" \
  --argjson field_count "$field_count" \
  --argjson field_signature_count "$field_signature_count" \
  --argjson type_signature_count "$type_signature_count" '
  {
    format_version: 1,
    claim_scope: (
      "Measured Bantawa raw JSONL schema and per-field scalar inventory only; "
      + "candidate and headword fields, filters, normalization, joiner policy, "
      + "layout, prefix vectors, pack, and profile promotion remain unselected."
    ),
    target_id: "bap",
    resource_id: "bap-dictionary",
    profile_id: "bap-Deva-NP",
    input_method_id: "bap-deva-direct",
    raw_input: {
      path: $raw,
      records: 2040,
      bytes: 360086,
      sha256: $raw_sha256
    },
    dumi_prerequisite: {
      verified: true,
      evidence_root: $d_evidence,
      final_manifest_sha256: $d_manifest_sha256,
      run_status_sha256: $d_status_sha256,
      sequence_summary_sha256: $d_summary_sha256
    },
    evidence_root: $evidence,
    report: {
      path: $report,
      sha256: $report_sha256,
      field_count: $field_count,
      ordered_field_signature_count: $field_signature_count,
      ordered_type_signature_count: $type_signature_count
    },
    focused_tests_verified: true,
    double_parse_verified: true,
    project_state_unchanged: true,
    selections_remain_unselected: true
  }
' >"$evidence/sequence-summary.json"
jq -e \
  --arg evidence "$evidence" \
  --arg raw "$raw" \
  --arg raw_sha256 "$expected_raw_sha256" \
  --arg report "$report" \
  --arg report_sha256 "$report_sha256" \
  --arg d_evidence "$dumi_evidence" \
  --arg d_manifest_sha256 "$dumi_manifest_sha256" \
  --arg d_status_sha256 "$dumi_status_sha256" \
  --arg d_summary_sha256 "$dumi_summary_sha256" '
  .format_version == 1
  and .target_id == "bap"
  and .resource_id == "bap-dictionary"
  and .profile_id == "bap-Deva-NP"
  and .input_method_id == "bap-deva-direct"
  and .evidence_root == $evidence
  and .raw_input.path == $raw
  and .raw_input.records == 2040
  and .raw_input.bytes == 360086
  and .raw_input.sha256 == $raw_sha256
  and .dumi_prerequisite.verified == true
  and .dumi_prerequisite.evidence_root == $d_evidence
  and .dumi_prerequisite.final_manifest_sha256 == $d_manifest_sha256
  and .dumi_prerequisite.run_status_sha256 == $d_status_sha256
  and .dumi_prerequisite.sequence_summary_sha256 == $d_summary_sha256
  and .report.path == $report
  and .report.sha256 == $report_sha256
  and .focused_tests_verified == true
  and .double_parse_verified == true
  and .project_state_unchanged == true
  and .selections_remain_unselected == true
  and (.report.field_count | type == "number" and . > 0)
  and (.report.ordered_field_signature_count | type == "number" and . > 0)
  and (.report.ordered_type_signature_count | type == "number" and . > 0)
  and (.claim_scope | contains("remain unselected"))
' "$evidence/sequence-summary.json" >/dev/null
sequence_complete=1
stage=complete
