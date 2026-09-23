#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || "$1" != /* ]]; then
  echo "usage: $0 /absolute/new/nepal-bhasa-source-evidence" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
trilingual_raw=/home/cdjk/github/llm/nllb-better/data/lexicons_pdf/new_nepali_trilingual.tsv
apk_raw=/home/cdjk/github/llm/nllb-better/data/lexicons_apk/new_apk_eng_lexicon.tsv
catalog="$repo/catalog/resources.json"
profile_lock="$repo/catalog/internal-profiles.lock.json"
layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
android_pins="$repo/android/ime-app/build.gradle.kts"
auditor="$repo/tools/audit_nepal_bhasa_tsv_contract.py"
focused_test="$repo/tests/test_nepal_bhasa_tsv_contract.py"
runner="$repo/tools/run_cdjk_nepal_bhasa_source_audit.sh"
runner_test="$repo/tests/test_nepal_bhasa_source_audit_runner.py"
uv="$HOME/.local/bin/uv"
expected_trilingual_sha256=4167c21626674fd1e71bd814c6b2bbb33d2d35ab0f5d5bb071b7b43e071d7929
expected_apk_sha256=470be5aaf526d2dca973044fa5ca9a69b4259854958456145661bd58d4889b41
stage=initializing
host_preflight_verified=0
focused_tests_verified=0
generate_check_verified=0
deterministic_second_generation_verified=0
profiles_remained_unselected=0
inputs_unchanged=0
sequence_complete=0

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this Nepal Bhasa source audit must run from the cdjk Ubuntu checkout" >&2
  exit 1
fi

for required in awk basename cmp df dirname find flock free grep hostname jq \
  mkdir mv pgrep ps realpath rm sed sha256sum sort timeout uname uptime wc \
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

evidence_argument="$1"
evidence_parent_argument="$(dirname -- "$evidence_argument")"
if [[ -L "$evidence_parent_argument" || ! -d "$evidence_parent_argument" ]]; then
  echo "evidence parent must be an existing non-symbolic directory" >&2
  exit 1
fi
evidence_parent="$(realpath -e -- "$evidence_parent_argument")"
evidence="$evidence_parent/$(basename -- "$evidence_argument")"
if [[ "$evidence" != "$evidence_argument" ]]; then
  echo "new Nepal Bhasa evidence path must be absolute and canonical" >&2
  exit 1
fi
if [[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]; then
  echo "Nepal Bhasa evidence directory must be outside the source checkout" >&2
  exit 1
fi
if [[ -e "$evidence" || -L "$evidence" ]]; then
  echo "evidence directory already exists: $evidence" >&2
  exit 1
fi
mkdir "$evidence"
if [[ -L "$evidence" || ! -d "$evidence"
      || "$(realpath -e -- "$evidence")" != "$evidence" ]]; then
  echo "created evidence directory is not canonical and non-symbolic" >&2
  exit 1
fi
mkdir "$evidence/a" "$evidence/b" "$evidence/logs"

write_manifest() {
  local temporary="$evidence/.final-evidence-sha256.txt.tmp"
  rm -f "$temporary"
  if find "$evidence" -type l -print -quit | grep -q .; then
    echo "Nepal Bhasa evidence tree contains a symbolic link" >&2
    return 1
  fi
  if find "$evidence" ! -type d ! -type f -print -quit | grep -q .; then
    echo "Nepal Bhasa evidence tree contains a special filesystem node" >&2
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

write_status() {
  local command_status="$1"
  local manifest_status="$2"
  local final_status="$3"
  local temporary="$evidence/.run-status.txt.tmp"
  {
    printf 'completed_stage=%s\n' "$stage"
    printf 'host_preflight_verified=%s\n' "$host_preflight_verified"
    printf 'focused_tests_verified=%s\n' "$focused_tests_verified"
    printf 'generate_check_verified=%s\n' "$generate_check_verified"
    printf 'deterministic_second_generation_verified=%s\n' \
      "$deterministic_second_generation_verified"
    printf 'profiles_remained_unselected=%s\n' "$profiles_remained_unselected"
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
    printf 'nepal_bhasa_source_audit_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

stage=input_metadata_validation
for input in \
  "$trilingual_raw" \
  "$apk_raw" \
  "$catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$android_pins" \
  "$auditor" \
  "$focused_test" \
  "$runner" \
  "$runner_test"; do
  if [[ -L "$input" || ! -f "$input" || ! -s "$input" ]]; then
    echo "canonical input is missing, symbolic, special, or empty: $input" >&2
    exit 1
  fi
  if [[ "$(realpath -e -- "$input")" != "$input" ]]; then
    echo "canonical input path resolves elsewhere: $input" >&2
    exit 1
  fi
done

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
  echo "cdjk has insufficient free disk for Nepal Bhasa source evidence" >&2
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
host_preflight_verified=1

verify_profiles() {
  jq -e '
    [.profiles[] | select(.target_id == "new")] as $profiles
    | ($profiles | length) == 4
    and ([$profiles[] | select(
      .profile_id == "new-Deva-NP"
      and .input_method_id == "new-deva-direct"
      and .source_script == "Deva"
      and .output_script == "Deva"
      and .layout_id == "pending-new-deva-direct"
    )] | length) == 1
    and ([$profiles[] | select(
      .profile_id == "new-Newa-NP"
      and .input_method_id == "new-newa-direct"
      and .source_script == "Newa"
      and .output_script == "Newa"
      and .layout_id == "pending-new-newa-direct"
    )] | length) == 1
    and ([$profiles[] | select(
      .profile_id == "new-Latn-Deva-NP"
      and .input_method_id == "new-latn-deva"
      and .source_script == "Latn"
      and .output_script == "Deva"
      and .layout_id == "latn-qwerty-us-v1"
    )] | length) == 1
    and ([$profiles[] | select(
      .profile_id == "new-Deva-Newa-NP"
      and .input_method_id == "new-deva-newa"
      and .source_script == "Deva"
      and .output_script == "Newa"
      and .layout_id == "pending-new-deva-newa"
    )] | length) == 1
    and all($profiles[];
      .selectable == false
      and .default_enabled == false
      and .pack_artifact == null
      and .pack_binding == null
      and .evidence_ids == []
      and .evidence_artifacts == []
    )
  ' "$profile_lock" >/dev/null
}

verify_catalog() {
  jq -e \
    --arg trilingual_sha256 "$expected_trilingual_sha256" \
    --arg apk_sha256 "$expected_apk_sha256" '
    [.packs[] | select(.id == "new")] as $targets
    | ($targets | length) == 1
    and $targets[0].name == "Nepal Bhasa"
    and $targets[0].iso_639_3 == "new"
    and ([$targets[0].resources[] | select(
      .id == "new-nepali-trilingual"
      and .path == (
        "/Users/cdjk/github/llm/nllb-better/data/lexicons_pdf/"
        + "new_nepali_trilingual.tsv"
      )
      and .format == "TSV"
      and .structured == true
      and .records == 9708
      and .bytes == 543567
      and .sha256 == $trilingual_sha256
    )] | length) == 1
    and ([$targets[0].resources[] | select(
      .id == "new-apk-english"
      and .path == (
        "/Users/cdjk/github/llm/nllb-better/data/lexicons_apk/"
        + "new_apk_eng_lexicon.tsv"
      )
      and .format == "TSV"
      and .structured == true
      and .records == 5727
      and .bytes == 404596
      and .sha256 == $apk_sha256
    )] | length) == 1
  ' "$catalog" >/dev/null
}

verify_raw_inputs() {
  local trilingual_sha256 trilingual_records trilingual_bytes trilingual_header
  local apk_sha256 apk_records apk_bytes apk_header
  trilingual_sha256="$(sha256sum "$trilingual_raw" | awk '{print $1}')"
  trilingual_records="$(LC_ALL=C awk 'NR > 1 {count++} END {print count + 0}' \
    "$trilingual_raw")"
  trilingual_bytes="$(wc -c <"$trilingual_raw" | awk '{print $1}')"
  trilingual_header="$(LC_ALL=C awk 'NR == 1 {print; exit}' "$trilingual_raw")"
  apk_sha256="$(sha256sum "$apk_raw" | awk '{print $1}')"
  apk_records="$(LC_ALL=C awk 'NR > 1 {count++} END {print count + 0}' "$apk_raw")"
  apk_bytes="$(wc -c <"$apk_raw" | awk '{print $1}')"
  apk_header="$(LC_ALL=C awk 'NR == 1 {print; exit}' "$apk_raw")"
  if [[ "$trilingual_sha256" != "$expected_trilingual_sha256"
        || "$trilingual_records" != 9708
        || "$trilingual_bytes" != 543567
        || "$trilingual_header" != $'newar\tnepali' ]]; then
    echo "Nepal Bhasa trilingual TSV identity does not match its exact pin" >&2
    return 1
  fi
  if [[ "$apk_sha256" != "$expected_apk_sha256"
        || "$apk_records" != 5727
        || "$apk_bytes" != 404596
        || "$apk_header" != $'newar\tenglish\ttransliteration' ]]; then
    echo "Nepal Bhasa APK TSV identity does not match its exact pin" >&2
    return 1
  fi
}

stage=pinned_input_validation
# The shared lock and host preflight above intentionally precede these raw scans.
verify_raw_inputs
verify_catalog
verify_profiles
profiles_remained_unselected=1

catalog_sha256="$(sha256sum "$catalog" | awk '{print $1}')"
profile_lock_sha256="$(sha256sum "$profile_lock" | awk '{print $1}')"
layout_lock_sha256="$(sha256sum "$layout_lock" | awk '{print $1}')"
android_pins_sha256="$(sha256sum "$android_pins" | awk '{print $1}')"
auditor_sha256="$(sha256sum "$auditor" | awk '{print $1}')"
focused_test_sha256="$(sha256sum "$focused_test" | awk '{print $1}')"
runner_sha256="$(sha256sum "$runner" | awk '{print $1}')"
runner_test_sha256="$(sha256sum "$runner_test" | awk '{print $1}')"
sha256sum \
  "$trilingual_raw" \
  "$apk_raw" \
  "$catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$android_pins" \
  "$auditor" \
  "$focused_test" \
  "$runner" \
  "$runner_test" \
  >"$evidence/input-source-sha256.before.txt"

run_python() {
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
    timeout 900 "$uv" run --python 3.14 python "$@"
}

stage=runtime_contract
runtime_identity="$(run_python -c '
import sys, unicodedata
print(f"{sys.version_info.major}.{sys.version_info.minor}/{unicodedata.unidata_version}")
')"
if [[ "$runtime_identity" != "3.14/16.0.0" ]]; then
  echo "remote Python runtime must be Python 3.14 with Unicode data 16.0.0" >&2
  exit 1
fi
printf '%s\n' "$runtime_identity" >"$evidence/python-unicode-runtime.txt"

stage=focused_tests
cd "$repo"
run_python -m unittest discover -s tests -p test_nepal_bhasa_tsv_contract.py \
  >"$evidence/logs/test-nepal-bhasa-tsv-contract.txt" 2>&1
run_python -m unittest discover -s tests \
  -p test_nepal_bhasa_source_audit_runner.py \
  >"$evidence/logs/test-nepal-bhasa-source-audit-runner.txt" 2>&1
focused_tests_verified=1

stage=generate_and_check
run_python tools/audit_nepal_bhasa_tsv_contract.py \
  --resource-catalog "$catalog" \
  --profile-lock "$profile_lock" \
  --layout-lock "$layout_lock" \
  --trilingual-tsv "$trilingual_raw" \
  --apk-tsv "$apk_raw" \
  --output "$evidence/a/nepal-bhasa-source-contract-v0.json" \
  >"$evidence/logs/generate-a.json" 2>"$evidence/logs/generate-a.log"
run_python tools/audit_nepal_bhasa_tsv_contract.py \
  --resource-catalog "$catalog" \
  --profile-lock "$profile_lock" \
  --layout-lock "$layout_lock" \
  --trilingual-tsv "$trilingual_raw" \
  --apk-tsv "$apk_raw" \
  --output "$evidence/a/nepal-bhasa-source-contract-v0.json" \
  --check >"$evidence/logs/check-a.json" 2>"$evidence/logs/check-a.log"
generate_check_verified=1

stage=deterministic_second_generation
run_python tools/audit_nepal_bhasa_tsv_contract.py \
  --resource-catalog "$catalog" \
  --profile-lock "$profile_lock" \
  --layout-lock "$layout_lock" \
  --trilingual-tsv "$trilingual_raw" \
  --apk-tsv "$apk_raw" \
  --output "$evidence/b/nepal-bhasa-source-contract-v0.json" \
  >"$evidence/logs/generate-b.json" 2>"$evidence/logs/generate-b.log"
cmp "$evidence/a/nepal-bhasa-source-contract-v0.json" \
  "$evidence/b/nepal-bhasa-source-contract-v0.json"
deterministic_second_generation_verified=1

report="$evidence/a/nepal-bhasa-source-contract-v0.json"
report_sha256="$(sha256sum "$report" | awk '{print $1}')"
for log in "$evidence/logs/generate-a.json" "$evidence/logs/check-a.json" \
  "$evidence/logs/generate-b.json"; do
  jq -e --arg sha256 "$report_sha256" '
    .status == "passed"
    and .report_sha256 == $sha256
  ' "$log" >/dev/null
done

stage=report_contract_validation
jq -e \
  --arg trilingual_raw "$trilingual_raw" \
  --arg trilingual_sha256 "$expected_trilingual_sha256" \
  --arg apk_raw "$apk_raw" \
  --arg apk_sha256 "$expected_apk_sha256" \
  --arg catalog_sha256 "$catalog_sha256" \
  --arg profile_lock_sha256 "$profile_lock_sha256" \
  --arg layout_lock_sha256 "$layout_lock_sha256" \
  --arg auditor_sha256 "$auditor_sha256" '
  .format_version == 1
  and .auditor.name == "audit_nepal_bhasa_tsv_contract"
  and .auditor.path == "tools/audit_nepal_bhasa_tsv_contract.py"
  and .auditor.sha256 == $auditor_sha256
  and .auditor.version == 1
  and .catalog_binding.target_id == "new"
  and .catalog_binding.path == "catalog/resources.json"
  and .catalog_binding.sha256 == $catalog_sha256
  and .catalog_binding.resource_ids == [
    "new-nepali-trilingual", "new-apk-english"
  ]
  and .profile_bindings.path == "catalog/internal-profiles.lock.json"
  and .profile_bindings.sha256 == $profile_lock_sha256
  and (.profile_bindings.profiles | length) == 4
  and [.profile_bindings.profiles[].profile_id] == [
    "new-Deva-NP",
    "new-Newa-NP",
    "new-Latn-Deva-NP",
    "new-Deva-Newa-NP"
  ]
  and all(.profile_bindings.profiles[];
    .selectable == false
    and .default_enabled == false
    and .pack_artifact == null
    and .pack_binding == null
    and .evidence_ids == []
    and .evidence_artifacts == []
  )
  and .layout_evidence.path == "layouts/internal/layouts-v1.lock.json"
  and .layout_evidence.sha256 == $layout_lock_sha256
  and .layout_evidence.coverage_semantics == (
    "exact non-whitespace scalar emission only"
  )
  and (.layout_evidence.deva_layout_ids | type == "array" and length > 0)
  and .runtime_contract.python_major_minor == "3.14"
  and .runtime_contract.unicode_data_version == "16.0.0"
  and .raw_inputs == [
    {
      bytes: 543567,
      path: $trilingual_raw,
      records: 9708,
      resource_id: "new-nepali-trilingual",
      sha256: $trilingual_sha256
    },
    {
      bytes: 404596,
      path: $apk_raw,
      records: 5727,
      resource_id: "new-apk-english",
      sha256: $apk_sha256
    }
  ]
  and (.source_contracts | length) == 2
  and .source_contracts[0].resource_id == "new-nepali-trilingual"
  and .source_contracts[0].header == ["newar", "nepali"]
  and .source_contracts[0].columns_per_row == 2
  and .source_contracts[0].data_rows == 9708
  and (.source_contracts[0].column_inventories | length) == 2
  and .source_contracts[1].resource_id == "new-apk-english"
  and .source_contracts[1].header == [
    "newar", "english", "transliteration"
  ]
  and .source_contracts[1].columns_per_row == 3
  and .source_contracts[1].data_rows == 5727
  and (.source_contracts[1].column_inventories | length) == 3
  and all(.source_contracts[].column_inventories[];
    (.column | type == "string")
    and (.index | type == "number")
    and (.string_values | type == "object")
    and (.string_values.duplicate_nonempty_extra_occurrences | type == "number")
    and (.string_values.duplicate_nonempty_value_groups | type == "number")
    and (.string_values.duplicate_nonempty_values | type == "array")
    and all(.string_values.duplicate_nonempty_values[];
      (.count | type == "number") and (.value | type == "string")
    )
    and (.string_values.duplicate_nonempty_values_sha256
      | test("^[0-9a-f]{64}$"))
  )
  and all(.source_contracts[];
    .encoding == "UTF-8"
    and .lf_terminated == true
    and (.layout_coverage_for_raw_newar_column | type == "array")
    and all(.layout_coverage_for_raw_newar_column[];
      (.layout_id | type == "string")
      and (.covered_required_scalars | type == "number")
      and (.emitted_scalars | type == "number")
      and (.missing_required_scalars | type == "array")
      and all(.missing_required_scalars[]; type == "string")
      and (.required_scalars | type == "number")
    )
    and (.raw_duplicate_extra_occurrences | type == "number")
    and (.raw_duplicate_row_groups | type == "number")
    and (.raw_duplicate_rows | type == "array")
    and (.raw_duplicate_rows_sha256 | test("^[0-9a-f]{64}$"))
  )
  and .source_contracts[0].transliteration_column_coverage == null
  and (.source_contracts[1].transliteration_column_coverage | type == "object")
  and all([
    .source_contracts[1].transliteration_column_coverage.distinct_nonempty_values,
    .source_contracts[1].transliteration_column_coverage.empty_values,
    .source_contracts[1].transliteration_column_coverage.newar_rows,
    .source_contracts[1].transliteration_column_coverage.nonempty_newar_rows,
    .source_contracts[1].transliteration_column_coverage
      .nonempty_newar_rows_with_nonempty_transliteration,
    .source_contracts[1].transliteration_column_coverage.nonempty_values
  ][]; type == "number")
  and .cross_source_raw_newar_overlap.comparison == (
    "exact raw strings including empty; no normalization or splitting"
  )
  and (.cross_source_raw_newar_overlap.empty_present_in_both | type == "boolean")
  and (.cross_source_raw_newar_overlap.exact_overlap_count | type == "number")
  and (.cross_source_raw_newar_overlap.exact_overlap_examples | type == "array")
  and (.cross_source_raw_newar_overlap.exact_overlap_sha256
    | test("^[0-9a-f]{64}$"))
  and (.cross_source_raw_newar_overlap.exact_nonempty_overlap_count
    | type == "number")
  and (.cross_source_raw_newar_overlap.exact_nonempty_overlap_examples
    | type == "array")
  and (.cross_source_raw_newar_overlap.exact_nonempty_overlap_sha256
    | test("^[0-9a-f]{64}$"))
  and (.cross_source_raw_newar_overlap.new_apk_english_nonempty_unique_count
    | type == "number")
  and (.cross_source_raw_newar_overlap.new_apk_english_unique_count | type == "number")
  and (.cross_source_raw_newar_overlap.new_apk_english_unique_sha256
    | test("^[0-9a-f]{64}$"))
  and (.cross_source_raw_newar_overlap.new_nepali_trilingual_nonempty_unique_count
    | type == "number")
  and (.cross_source_raw_newar_overlap.new_nepali_trilingual_unique_count | type == "number")
  and (.cross_source_raw_newar_overlap.new_nepali_trilingual_unique_sha256
    | test("^[0-9a-f]{64}$"))
  and .selections.alternative_splitting_policy == null
  and .selections.candidate_columns == {
    "new-nepali-trilingual": null,
    "new-apk-english": null
  }
  and .selections.candidate_resource_ids == []
  and .selections.conversion_policy == null
  and .selections.filter_policy == null
  and .selections.joiner_policy == null
  and .selections.layout_ids == []
  and .selections.normalization_policy == null
  and .selections.pack_id == null
  and .selections.prefix_vectors == []
  and .selections.roman_alias_policy == null
  and .selections.profile_promotions == {
    "new-Deva-NP": false,
    "new-Newa-NP": false,
    "new-Latn-Deva-NP": false,
    "new-Deva-Newa-NP": false
  }
  and (.claim_scope | contains("No rows were merged"))
  and (.claim_scope | contains("remain unselected"))
' "$report" >/dev/null

stage=input_recheck
verify_raw_inputs
verify_catalog
verify_profiles
sha256sum \
  "$trilingual_raw" \
  "$apk_raw" \
  "$catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$android_pins" \
  "$auditor" \
  "$focused_test" \
  "$runner" \
  "$runner_test" \
  >"$evidence/input-source-sha256.after.txt"
cmp "$evidence/input-source-sha256.before.txt" \
  "$evidence/input-source-sha256.after.txt"
inputs_unchanged=1

stage=sequence_summary
summary_temporary="$evidence/.sequence-summary.json.tmp"
jq -S -n \
  --arg evidence "$evidence" \
  --arg trilingual_raw "$trilingual_raw" \
  --arg trilingual_sha256 "$expected_trilingual_sha256" \
  --arg apk_raw "$apk_raw" \
  --arg apk_sha256 "$expected_apk_sha256" \
  --arg catalog "$catalog" \
  --arg catalog_sha256 "$catalog_sha256" \
  --arg profile_lock "$profile_lock" \
  --arg profile_lock_sha256 "$profile_lock_sha256" \
  --arg layout_lock "$layout_lock" \
  --arg layout_lock_sha256 "$layout_lock_sha256" \
  --arg android_pins "$android_pins" \
  --arg android_pins_sha256 "$android_pins_sha256" \
  --arg auditor "$auditor" \
  --arg auditor_sha256 "$auditor_sha256" \
  --arg focused_test "$focused_test" \
  --arg focused_test_sha256 "$focused_test_sha256" \
  --arg runner "$runner" \
  --arg runner_sha256 "$runner_sha256" \
  --arg runner_test "$runner_test" \
  --arg runner_test_sha256 "$runner_test_sha256" \
  --arg report "$report" \
  --arg report_sha256 "$report_sha256" \
  --slurpfile audit "$report" '
  $audit[0] as $audit
  | {
    format_version: 1,
    claim_scope: (
      "Deterministic neutral audit of two separate pinned Nepal Bhasa TSV "
      + "contracts and their exact raw newar-column overlap. No rows or "
      + "candidate vocabularies were merged; all pack and input decisions "
      + "remain unselected."
    ),
    target_id: "new",
    evidence_root: $evidence,
    raw_inputs: [
      {
        resource_id: "new-nepali-trilingual",
        path: $trilingual_raw,
        records: 9708,
        bytes: 543567,
        sha256: $trilingual_sha256
      },
      {
        resource_id: "new-apk-english",
        path: $apk_raw,
        records: 5727,
        bytes: 404596,
        sha256: $apk_sha256
      }
    ],
    inputs: {
      resource_catalog: {path: $catalog, sha256: $catalog_sha256},
      internal_profile_lock: {path: $profile_lock, sha256: $profile_lock_sha256},
      internal_layout_lock: {path: $layout_lock, sha256: $layout_lock_sha256},
      android_pins: {path: $android_pins, sha256: $android_pins_sha256},
      auditor: {path: $auditor, sha256: $auditor_sha256},
      focused_test: {path: $focused_test, sha256: $focused_test_sha256},
      runner: {path: $runner, sha256: $runner_sha256},
      runner_test: {path: $runner_test, sha256: $runner_test_sha256}
    },
    report: {path: $report, sha256: $report_sha256},
    source_contracts: ($audit.source_contracts | map({
      resource_id,
      header,
      columns_per_row,
      data_rows
    })),
    cross_source_raw_newar_overlap: $audit.cross_source_raw_newar_overlap,
    profiles: $audit.profile_bindings.profiles,
    focused_tests_verified: true,
    generate_check_verified: true,
    deterministic_second_generation_verified: true,
    profiles_remained_unselected: true,
    project_inputs_unchanged: true,
    selections_remain_neutral: true
  }
' >"$summary_temporary"
mv "$summary_temporary" "$evidence/sequence-summary.json"

jq -e \
  --arg evidence "$evidence" \
  --arg report "$report" \
  --arg report_sha256 "$report_sha256" \
  --arg auditor_sha256 "$auditor_sha256" \
  --arg focused_test_sha256 "$focused_test_sha256" \
  --arg runner_sha256 "$runner_sha256" \
  --arg runner_test_sha256 "$runner_test_sha256" '
  .format_version == 1
  and .target_id == "new"
  and .evidence_root == $evidence
  and .report.path == $report
  and .report.sha256 == $report_sha256
  and (.source_contracts | length) == 2
  and [.source_contracts[].resource_id] == [
    "new-nepali-trilingual", "new-apk-english"
  ]
  and .cross_source_raw_newar_overlap.comparison == (
    "exact raw strings including empty; no normalization or splitting"
  )
  and (.cross_source_raw_newar_overlap.empty_present_in_both | type == "boolean")
  and (.cross_source_raw_newar_overlap.exact_overlap_count | type == "number")
  and (.cross_source_raw_newar_overlap.exact_overlap_sha256
    | test("^[0-9a-f]{64}$"))
  and (.cross_source_raw_newar_overlap.exact_nonempty_overlap_count
    | type == "number")
  and (.cross_source_raw_newar_overlap.exact_nonempty_overlap_sha256
    | test("^[0-9a-f]{64}$"))
  and (.cross_source_raw_newar_overlap.new_apk_english_nonempty_unique_count
    | type == "number")
  and (.cross_source_raw_newar_overlap.new_apk_english_unique_count
    | type == "number")
  and (.cross_source_raw_newar_overlap.new_apk_english_unique_sha256
    | test("^[0-9a-f]{64}$"))
  and (.cross_source_raw_newar_overlap.new_nepali_trilingual_nonempty_unique_count
    | type == "number")
  and (.cross_source_raw_newar_overlap.new_nepali_trilingual_unique_count
    | type == "number")
  and (.cross_source_raw_newar_overlap.new_nepali_trilingual_unique_sha256
    | test("^[0-9a-f]{64}$"))
  and (.profiles | length) == 4
  and all(.profiles[];
    .selectable == false
    and .default_enabled == false
    and .pack_artifact == null
    and .pack_binding == null
    and .evidence_ids == []
    and .evidence_artifacts == []
  )
  and .inputs.auditor.sha256 == $auditor_sha256
  and .inputs.focused_test.sha256 == $focused_test_sha256
  and .inputs.runner.sha256 == $runner_sha256
  and .inputs.runner_test.sha256 == $runner_test_sha256
  and .focused_tests_verified == true
  and .generate_check_verified == true
  and .deterministic_second_generation_verified == true
  and .profiles_remained_unselected == true
  and .project_inputs_unchanged == true
  and .selections_remain_neutral == true
  and (.claim_scope | contains("No rows or candidate vocabularies were merged"))
  and (.claim_scope | contains("remain unselected"))
' "$evidence/sequence-summary.json" >/dev/null

stage=complete
sequence_complete=1
