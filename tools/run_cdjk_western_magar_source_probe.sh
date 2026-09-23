#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ $# -ne 2 || "$1" != /* || "$2" != /* ]]; then
  echo "usage: $0 /absolute/completed-bantawa-evidence /absolute/new/western-magar-evidence" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
raw=/home/cdjk/github/llm/nllb-better/data/lexicons_apk/mrd_nep_lexicon.tsv
catalog="$repo/catalog/resources.json"
profile_lock="$repo/catalog/internal-profiles.lock.json"
layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
auditor="$repo/tools/audit_western_magar_tsv_contract.py"
focused_test="$repo/tests/test_western_magar_tsv_contract.py"
runner="$repo/tools/run_cdjk_western_magar_source_probe.sh"
uv="$HOME/.local/bin/uv"
expected_raw_sha256=d55d34e4c4d754ee1bbcf3382f3250690e53884020c06305e34bfc1a7948591a
expected_bantawa_raw_sha256=a69917c00e7a8587f4a38458faf89c95fc9e5ac9cbe6cfb612383438bdf5ae12
stage=initializing
bantawa_prerequisite_verified=0
focused_tests_verified=0
double_parse_verified=0
inputs_unchanged=0
sequence_complete=0

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this Western Magar source probe must run from the cdjk Ubuntu checkout" >&2
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

bantawa_argument="$1"
if [[ -L "$bantawa_argument" || ! -d "$bantawa_argument" ]]; then
  echo "Bantawa prerequisite must be a non-symbolic evidence directory" >&2
  exit 1
fi
bantawa_evidence="$(realpath -e -- "$bantawa_argument")"
if [[ "$bantawa_evidence" != "$bantawa_argument" ]]; then
  echo "Bantawa evidence path must be canonical" >&2
  exit 1
fi
if [[ "$bantawa_evidence" == "$repo" || "$bantawa_evidence" == "$repo/"* ]]; then
  echo "Bantawa evidence directory must be outside the source checkout" >&2
  exit 1
fi

evidence_parent="$(realpath -e -- "$(dirname -- "$2")")"
evidence="$evidence_parent/$(basename -- "$2")"
if [[ "$evidence" != "$2" ]]; then
  echo "new Western Magar evidence path must be canonical" >&2
  exit 1
fi
if [[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]; then
  echo "Western Magar evidence directory must be outside the source checkout" >&2
  exit 1
fi
if [[ "$evidence" == "$bantawa_evidence" || "$evidence" == "$bantawa_evidence/"* ]]; then
  echo "Western Magar evidence must not modify the Bantawa prerequisite tree" >&2
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
    echo "Western Magar evidence tree contains a symbolic link" >&2
    return 1
  fi
  if find "$evidence" ! -type d ! -type f -print -quit | grep -q .; then
    echo "Western Magar evidence tree contains a special filesystem node" >&2
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

recreate_bantawa_manifest() {
  local output="$1"
  if find "$bantawa_evidence" -type l -print -quit | grep -q .; then
    echo "Bantawa prerequisite tree contains a symbolic link" >&2
    return 1
  fi
  if find "$bantawa_evidence" ! -type d ! -type f -print -quit | grep -q .; then
    echo "Bantawa prerequisite tree contains a special filesystem node" >&2
    return 1
  fi
  (
    cd "$bantawa_evidence"
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
    printf 'bantawa_prerequisite_verified=%s\n' "$bantawa_prerequisite_verified"
    printf 'focused_tests_verified=%s\n' "$focused_tests_verified"
    printf 'double_parse_verified=%s\n' "$double_parse_verified"
    printf 'inputs_unchanged=%s\n' "$inputs_unchanged"
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
    printf 'western_magar_source_probe_complete evidence=%s\n' "$evidence"
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
  "$auditor" \
  "$focused_test" \
  "$runner"; do
  if [[ -L "$input" || ! -s "$input" ]]; then
    echo "canonical input is missing, symbolic, or empty: $input" >&2
    exit 1
  fi
done
if [[ "$(realpath -e -- "$raw")" != "$raw" ]]; then
  echo "Western Magar raw input path is not canonical" >&2
  exit 1
fi

stage=host_preflight
exec 9>/tmp/nepa-keyboard-android-validation.lock
if ! flock -n 9; then
  echo "another Nepa Android or corpus validation owns the cdjk lock" >&2
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
  echo "cdjk has insufficient free disk for Western Magar source evidence" >&2
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

stage=bantawa_prerequisite
bantawa_report="$bantawa_evidence/a/bantawa-source-contract-v0.json"
for prerequisite in \
  "$bantawa_evidence/final-evidence-sha256.txt" \
  "$bantawa_evidence/run-status.txt" \
  "$bantawa_evidence/sequence-summary.json" \
  "$bantawa_report"; do
  if [[ -L "$prerequisite" || ! -s "$prerequisite" ]]; then
    echo "Bantawa prerequisite file is missing, symbolic, or empty: $prerequisite" >&2
    exit 1
  fi
done
recreate_bantawa_manifest \
  "$evidence/bantawa-recreated-final-evidence-sha256.before.txt"
cmp "$bantawa_evidence/final-evidence-sha256.txt" \
  "$evidence/bantawa-recreated-final-evidence-sha256.before.txt"
(
  cd "$bantawa_evidence"
  sha256sum -c final-evidence-sha256.txt
) >"$evidence/bantawa-evidence-manifest-check.txt"
tee "$evidence/bantawa-prerequisite-final-evidence-sha256.txt" \
  <"$bantawa_evidence/final-evidence-sha256.txt" >/dev/null
cmp "$bantawa_evidence/final-evidence-sha256.txt" \
  "$evidence/bantawa-prerequisite-final-evidence-sha256.txt"
{
  printf 'completed_stage=complete\n'
  printf 'dumi_prerequisite_verified=1\n'
  printf 'focused_tests_verified=1\n'
  printf 'double_parse_verified=1\n'
  printf 'state_unchanged=1\n'
  printf 'sequence_complete=1\n'
  printf 'command_exit_status=0\n'
  printf 'manifest_exit_status=0\n'
  printf 'remote_exit_status=0\n'
} >"$evidence/expected-bantawa-run-status.txt"
cmp "$evidence/expected-bantawa-run-status.txt" "$bantawa_evidence/run-status.txt"
bantawa_report_sha256="$(sha256sum "$bantawa_report" | awk '{print $1}')"
jq -e \
  --arg raw_sha256 "$expected_bantawa_raw_sha256" \
  --arg evidence "$bantawa_evidence" \
  --arg report "$bantawa_report" \
  --arg report_sha256 "$bantawa_report_sha256" '
  .format_version == 1
  and .target_id == "bap"
  and .resource_id == "bap-dictionary"
  and .profile_id == "bap-Deva-NP"
  and .input_method_id == "bap-deva-direct"
  and .raw_input.path == (
    "/home/cdjk/github/llm/rai-speech-toolkit/dialects/central/"
    + "bantawa/dict/bantawa-english.dict.jsonl"
  )
  and .raw_input.records == 2040
  and .raw_input.bytes == 360086
  and .raw_input.sha256 == $raw_sha256
  and .dumi_prerequisite.verified == true
  and .evidence_root == $evidence
  and .report.path == $report
  and .report.sha256 == $report_sha256
  and (.report.field_count | type == "number" and . > 0)
  and (.report.ordered_field_signature_count | type == "number" and . > 0)
  and (.report.ordered_type_signature_count | type == "number" and . > 0)
  and .focused_tests_verified == true
  and .double_parse_verified == true
  and .project_state_unchanged == true
  and .selections_remain_unselected == true
  and (.claim_scope | contains("remain unselected"))
' "$bantawa_evidence/sequence-summary.json" >/dev/null
bantawa_manifest_sha256="$(sha256sum \
  "$bantawa_evidence/final-evidence-sha256.txt" | awk '{print $1}')"
bantawa_status_sha256="$(sha256sum \
  "$bantawa_evidence/run-status.txt" | awk '{print $1}')"
bantawa_summary_sha256="$(sha256sum \
  "$bantawa_evidence/sequence-summary.json" | awk '{print $1}')"
bantawa_manifest_entry_count="$(LC_ALL=C awk 'END {print NR}' \
  "$bantawa_evidence/final-evidence-sha256.txt")"
if [[ ! "$bantawa_manifest_entry_count" =~ ^[0-9]+$ \
      || "$bantawa_manifest_entry_count" == 0 ]]; then
  echo "Bantawa prerequisite manifest is empty" >&2
  exit 1
fi
sha256sum \
  "$bantawa_evidence/final-evidence-sha256.txt" \
  "$bantawa_evidence/run-status.txt" \
  "$bantawa_evidence/sequence-summary.json" \
  "$bantawa_report" \
  >"$evidence/bantawa-prerequisite-sha256.txt"
bantawa_prerequisite_verified=1

stage=western_magar_input_validation
actual_raw_sha256="$(sha256sum "$raw" | awk '{print $1}')"
actual_raw_records="$(LC_ALL=C awk 'NR > 1 {count++} END {print count + 0}' "$raw")"
actual_raw_bytes="$(wc -c <"$raw" | awk '{print $1}')"
if [[ "$actual_raw_sha256" != "$expected_raw_sha256"
      || "$actual_raw_records" != 1264
      || "$actual_raw_bytes" != 68724 ]]; then
  echo "Western Magar raw input identity does not match the catalog pin" >&2
  exit 1
fi
jq -e --arg sha256 "$expected_raw_sha256" '
  [.packs[] | select(.id == "mrd")] as $targets
  | ($targets | length) == 1
  and $targets[0].iso_639_3 == "mrd"
  and ([$targets[0].input_methods[] | select(.id == "mrd-deva-direct")]
       | length) == 1
  and ([$targets[0].resources[] | select(.id == "mrd-apk")]
       | length) == 1
  and ([$targets[0].resources[] | select(.id == "mrd-apk")][0]
       | .format == "TSV"
         and .structured == true
         and .records == 1264
         and .bytes == 68724
         and .sha256 == $sha256
         and .canonical == true)
' "$catalog" >/dev/null
jq -e '
  [.profiles[] | select(.profile_id == "mrd-Deva-NP")] as $profiles
  | ($profiles | length) == 1
  and $profiles[0].target_id == "mrd"
  and $profiles[0].input_method_id == "mrd-deva-direct"
  and $profiles[0].layout_id == "pending-mrd-deva-direct"
  and $profiles[0].selectable == false
  and $profiles[0].pack_artifact == null
  and $profiles[0].pack_binding == null
' "$profile_lock" >/dev/null
catalog_sha256="$(sha256sum "$catalog" | awk '{print $1}')"
profile_lock_sha256="$(sha256sum "$profile_lock" | awk '{print $1}')"
layout_lock_sha256="$(sha256sum "$layout_lock" | awk '{print $1}')"
auditor_sha256="$(sha256sum "$auditor" | awk '{print $1}')"
focused_test_sha256="$(sha256sum "$focused_test" | awk '{print $1}')"
runner_sha256="$(sha256sum "$runner" | awk '{print $1}')"
sha256sum \
  "$raw" \
  "$catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$auditor" \
  "$focused_test" \
  "$runner" \
  >"$evidence/input-source-sha256.before.txt"

run_python() {
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
    timeout 900 "$uv" run --python 3.14 python "$@"
}

stage=focused_tests
cd "$repo"
run_python -m unittest discover -s tests -p test_western_magar_tsv_contract.py \
  >"$evidence/logs/test-western-magar-tsv-contract.txt" 2>&1
focused_tests_verified=1

stage=double_parse
run_python tools/audit_western_magar_tsv_contract.py \
  --resource-catalog catalog/resources.json \
  --profile-lock catalog/internal-profiles.lock.json \
  --layout-lock layouts/internal/layouts-v1.lock.json \
  --western-magar-tsv "$raw" \
  --output "$evidence/a/western-magar-source-contract-v0.json" \
  >"$evidence/logs/a.json" 2>"$evidence/logs/a.log"
run_python tools/audit_western_magar_tsv_contract.py \
  --resource-catalog catalog/resources.json \
  --profile-lock catalog/internal-profiles.lock.json \
  --layout-lock layouts/internal/layouts-v1.lock.json \
  --western-magar-tsv "$raw" \
  --output "$evidence/b/western-magar-source-contract-v0.json" \
  >"$evidence/logs/b.json" 2>"$evidence/logs/b.log"
cmp "$evidence/a/western-magar-source-contract-v0.json" \
  "$evidence/b/western-magar-source-contract-v0.json"
run_python tools/audit_western_magar_tsv_contract.py \
  --resource-catalog catalog/resources.json \
  --profile-lock catalog/internal-profiles.lock.json \
  --layout-lock layouts/internal/layouts-v1.lock.json \
  --western-magar-tsv "$raw" \
  --output "$evidence/a/western-magar-source-contract-v0.json" \
  --check >"$evidence/logs/check.json" 2>"$evidence/logs/check.log"
report="$evidence/a/western-magar-source-contract-v0.json"
report_sha256="$(sha256sum "$report" | awk '{print $1}')"
for log in "$evidence/logs/a.json" "$evidence/logs/b.json" \
  "$evidence/logs/check.json"; do
  jq -e --arg sha256 "$report_sha256" '
    .status == "passed"
    and .report_sha256 == $sha256
  ' "$log" >/dev/null
done
jq -e \
  --arg raw "$raw" \
  --arg raw_sha256 "$expected_raw_sha256" \
  --arg catalog_sha256 "$catalog_sha256" \
  --arg profile_lock_sha256 "$profile_lock_sha256" \
  --arg layout_lock_sha256 "$layout_lock_sha256" \
  --arg auditor_sha256 "$auditor_sha256" '
  .format_version == 1
  and .auditor.name == "audit_western_magar_tsv_contract"
  and .auditor.path == "tools/audit_western_magar_tsv_contract.py"
  and .auditor.sha256 == $auditor_sha256
  and .auditor.version == 1
  and .raw_input.target_id == "mrd"
  and .raw_input.resource_id == "mrd-apk"
  and .raw_input.path == $raw
  and .raw_input.records == 1264
  and .raw_input.bytes == 68724
  and .raw_input.sha256 == $raw_sha256
  and .raw_input.resource_catalog_sha256 == $catalog_sha256
  and .runtime_contract.python_major_minor == "3.14"
  and .runtime_contract.unicode_data_version == "16.0.0"
  and .profile_binding.profile_id == "mrd-Deva-NP"
  and .profile_binding.target_id == "mrd"
  and .profile_binding.input_method_id == "mrd-deva-direct"
  and .profile_binding.lookup_kind == "surface_prefix"
  and .profile_binding.layout_id == "pending-mrd-deva-direct"
  and .profile_binding.selectable == false
  and .profile_binding.default_enabled == false
  and .profile_binding.sha256 == $profile_lock_sha256
  and .layout_evidence.sha256 == $layout_lock_sha256
  and .layout_evidence.coverage_semantics == (
    "exact non-whitespace scalar emission only"
  )
  and (.layout_evidence.deva_layout_ids | type == "array" and length > 0)
  and .tsv_contract.header == [
    "mrd_headword", "nepali_gloss", "english_gloss"
  ]
  and .tsv_contract.columns_per_row == 3
  and .tsv_contract.data_rows == 1264
  and .tsv_contract.encoding == "UTF-8"
  and .tsv_contract.lf_terminated == true
  and .tsv_contract.null_representation == (
    "none; empty TSV fields are inventoried as empty strings"
  )
  and (.tsv_contract.column_inventories | length) == 3
  and [.tsv_contract.column_inventories[].column] == [
    "mrd_headword", "nepali_gloss", "english_gloss"
  ]
  and [.tsv_contract.column_inventories[].index] == [0, 1, 2]
  and all(.tsv_contract.column_inventories[]; .string_values | type == "object")
  and .selections.candidate_column == null
  and .selections.headword_column == null
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

stage=input_recheck
sha256sum \
  "$raw" \
  "$catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$auditor" \
  "$focused_test" \
  "$runner" \
  >"$evidence/input-source-sha256.after.txt"
cmp "$evidence/input-source-sha256.before.txt" \
  "$evidence/input-source-sha256.after.txt"
inputs_unchanged=1

stage=bantawa_prerequisite_recheck
recreate_bantawa_manifest \
  "$evidence/bantawa-recreated-final-evidence-sha256.after.txt"
cmp "$bantawa_evidence/final-evidence-sha256.txt" \
  "$evidence/bantawa-recreated-final-evidence-sha256.after.txt"
cmp "$bantawa_evidence/final-evidence-sha256.txt" \
  "$evidence/bantawa-prerequisite-final-evidence-sha256.txt"
(
  cd "$bantawa_evidence"
  sha256sum -c final-evidence-sha256.txt
) >"$evidence/bantawa-evidence-manifest-recheck.txt"
if [[ "$(sha256sum "$bantawa_evidence/final-evidence-sha256.txt" \
          | awk '{print $1}')" != "$bantawa_manifest_sha256"
      || "$(sha256sum "$bantawa_evidence/run-status.txt" \
          | awk '{print $1}')" != "$bantawa_status_sha256"
      || "$(sha256sum "$bantawa_evidence/sequence-summary.json" \
          | awk '{print $1}')" != "$bantawa_summary_sha256"
      || "$(sha256sum "$bantawa_report" \
          | awk '{print $1}')" != "$bantawa_report_sha256" ]]; then
  echo "Bantawa prerequisite changed during the Western Magar source probe" >&2
  exit 1
fi

stage=sequence_summary
jq -S -n \
  --arg evidence "$evidence" \
  --arg raw "$raw" \
  --arg raw_sha256 "$expected_raw_sha256" \
  --arg catalog "$catalog" \
  --arg catalog_sha256 "$catalog_sha256" \
  --arg profile_lock "$profile_lock" \
  --arg profile_lock_sha256 "$profile_lock_sha256" \
  --arg layout_lock "$layout_lock" \
  --arg layout_lock_sha256 "$layout_lock_sha256" \
  --arg auditor "$auditor" \
  --arg auditor_sha256 "$auditor_sha256" \
  --arg focused_test "$focused_test" \
  --arg focused_test_sha256 "$focused_test_sha256" \
  --arg runner "$runner" \
  --arg runner_sha256 "$runner_sha256" \
  --arg report "$report" \
  --arg report_sha256 "$report_sha256" \
  --arg b_evidence "$bantawa_evidence" \
  --arg b_manifest_sha256 "$bantawa_manifest_sha256" \
  --arg b_status_sha256 "$bantawa_status_sha256" \
  --arg b_summary_sha256 "$bantawa_summary_sha256" \
  --arg b_report "$bantawa_report" \
  --arg b_report_sha256 "$bantawa_report_sha256" \
  --argjson b_manifest_entry_count "$bantawa_manifest_entry_count" '
  {
    format_version: 1,
    claim_scope: (
      "Measured Western Magar raw TSV structure and scalar inventory only; "
      + "candidate and headword columns, filters, normalization, joiner policy, "
      + "layout, prefix vectors, pack, and profile promotion remain unselected."
    ),
    target_id: "mrd",
    resource_id: "mrd-apk",
    profile_id: "mrd-Deva-NP",
    input_method_id: "mrd-deva-direct",
    raw_input: {
      path: $raw,
      records: 1264,
      bytes: 68724,
      sha256: $raw_sha256
    },
    inputs: {
      resource_catalog: {path: $catalog, sha256: $catalog_sha256},
      internal_profile_lock: {path: $profile_lock, sha256: $profile_lock_sha256},
      internal_layout_lock: {path: $layout_lock, sha256: $layout_lock_sha256},
      auditor: {path: $auditor, sha256: $auditor_sha256},
      focused_test: {path: $focused_test, sha256: $focused_test_sha256},
      runner: {path: $runner, sha256: $runner_sha256}
    },
    bantawa_prerequisite: {
      verified: true,
      evidence_root: $b_evidence,
      final_manifest_path: ($b_evidence + "/final-evidence-sha256.txt"),
      final_manifest_sha256: $b_manifest_sha256,
      manifest_entry_count: $b_manifest_entry_count,
      run_status_path: ($b_evidence + "/run-status.txt"),
      run_status_sha256: $b_status_sha256,
      sequence_summary_path: ($b_evidence + "/sequence-summary.json"),
      sequence_summary_sha256: $b_summary_sha256,
      report_path: $b_report,
      report_sha256: $b_report_sha256,
      preserved_manifest_path: (
        $evidence + "/bantawa-prerequisite-final-evidence-sha256.txt"
      )
    },
    evidence_root: $evidence,
    report: {
      path: $report,
      sha256: $report_sha256,
      rows: 1264
    },
    focused_tests_verified: true,
    double_parse_verified: true,
    inputs_unchanged: true,
    selections_remain_unselected: true
  }
' >"$evidence/sequence-summary.json"
jq -e \
  --arg evidence "$evidence" \
  --arg raw "$raw" \
  --arg raw_sha256 "$expected_raw_sha256" \
  --arg catalog "$catalog" \
  --arg catalog_sha256 "$catalog_sha256" \
  --arg profile_lock "$profile_lock" \
  --arg profile_lock_sha256 "$profile_lock_sha256" \
  --arg layout_lock "$layout_lock" \
  --arg layout_lock_sha256 "$layout_lock_sha256" \
  --arg auditor "$auditor" \
  --arg auditor_sha256 "$auditor_sha256" \
  --arg focused_test "$focused_test" \
  --arg focused_test_sha256 "$focused_test_sha256" \
  --arg runner "$runner" \
  --arg runner_sha256 "$runner_sha256" \
  --arg report "$report" \
  --arg report_sha256 "$report_sha256" \
  --arg b_evidence "$bantawa_evidence" \
  --arg b_manifest_sha256 "$bantawa_manifest_sha256" \
  --arg b_status_sha256 "$bantawa_status_sha256" \
  --arg b_summary_sha256 "$bantawa_summary_sha256" \
  --arg b_report "$bantawa_report" \
  --arg b_report_sha256 "$bantawa_report_sha256" \
  --argjson b_manifest_entry_count "$bantawa_manifest_entry_count" '
  .format_version == 1
  and .target_id == "mrd"
  and .resource_id == "mrd-apk"
  and .profile_id == "mrd-Deva-NP"
  and .input_method_id == "mrd-deva-direct"
  and .evidence_root == $evidence
  and .raw_input.path == $raw
  and .raw_input.records == 1264
  and .raw_input.bytes == 68724
  and .raw_input.sha256 == $raw_sha256
  and .inputs.resource_catalog.path == $catalog
  and .inputs.resource_catalog.sha256 == $catalog_sha256
  and .inputs.internal_profile_lock.path == $profile_lock
  and .inputs.internal_profile_lock.sha256 == $profile_lock_sha256
  and .inputs.internal_layout_lock.path == $layout_lock
  and .inputs.internal_layout_lock.sha256 == $layout_lock_sha256
  and .inputs.auditor.path == $auditor
  and .inputs.auditor.sha256 == $auditor_sha256
  and .inputs.focused_test.path == $focused_test
  and .inputs.focused_test.sha256 == $focused_test_sha256
  and .inputs.runner.path == $runner
  and .inputs.runner.sha256 == $runner_sha256
  and .bantawa_prerequisite.verified == true
  and .bantawa_prerequisite.evidence_root == $b_evidence
  and .bantawa_prerequisite.final_manifest_path == (
    $b_evidence + "/final-evidence-sha256.txt"
  )
  and .bantawa_prerequisite.final_manifest_sha256 == $b_manifest_sha256
  and .bantawa_prerequisite.manifest_entry_count == $b_manifest_entry_count
  and .bantawa_prerequisite.run_status_path == ($b_evidence + "/run-status.txt")
  and .bantawa_prerequisite.run_status_sha256 == $b_status_sha256
  and .bantawa_prerequisite.sequence_summary_path == (
    $b_evidence + "/sequence-summary.json"
  )
  and .bantawa_prerequisite.sequence_summary_sha256 == $b_summary_sha256
  and .bantawa_prerequisite.report_path == $b_report
  and .bantawa_prerequisite.report_sha256 == $b_report_sha256
  and .bantawa_prerequisite.preserved_manifest_path == (
    $evidence + "/bantawa-prerequisite-final-evidence-sha256.txt"
  )
  and .report.path == $report
  and .report.sha256 == $report_sha256
  and .report.rows == 1264
  and .focused_tests_verified == true
  and .double_parse_verified == true
  and .inputs_unchanged == true
  and .selections_remain_unselected == true
  and (.claim_scope | contains("remain unselected"))
' "$evidence/sequence-summary.json" >/dev/null
sequence_complete=1
stage=complete
