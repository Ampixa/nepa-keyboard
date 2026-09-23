#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || "$1" != /* ]]; then
  echo "usage: $0 /absolute/new/nepal-bhasa-candidate-pack-evidence" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
trilingual_raw=/home/cdjk/github/llm/nllb-better/data/lexicons_pdf/new_nepali_trilingual.tsv
apk_raw=/home/cdjk/github/llm/nllb-better/data/lexicons_apk/new_apk_eng_lexicon.tsv
source_audit=/home/cdjk/data/nepa-keyboard/source-audits/nepal-bhasa-20260720-v2/a/nepal-bhasa-source-contract-v0.json
spec="$repo/catalog/nepal-bhasa-candidate-pack-v0.json"
catalog="$repo/catalog/resources.json"
profile_review="$repo/catalog/internal-profile-review.json"
profile_lock="$repo/catalog/internal-profiles.lock.json"
layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
android_pins="$repo/android/ime-app/build.gradle.kts"
adapter="$repo/tools/build_nepal_bhasa_internal_source.py"
auditor="$repo/tools/audit_nepal_bhasa_tsv_contract.py"
compiler="$repo/src/nepa_keyboard/compiler.py"
runtime="$repo/src/nepa_keyboard/runtime.py"
adapter_test="$repo/tests/test_nepal_bhasa_internal_source.py"
runner="$repo/tools/run_cdjk_nepal_bhasa_candidate_pack.sh"
runner_test="$repo/tests/test_nepal_bhasa_candidate_pack_runner.py"
uv="$HOME/.local/bin/uv"
stage=initializing
host_preflight_verified=0
focused_tests_verified=0
source_audit_verified=0
double_build_verified=0
inspect_verified=0
promotion_state_unchanged=0
sequence_complete=0

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this Nepal Bhasa candidate-pack runner must run on cdjk Ubuntu" >&2
  exit 1
fi

for required in awk basename cmp df diff dirname find flock free grep hostname \
  jq mkdir mv pgrep ps realpath rm sed sha256sum sort stat timeout uname unzip \
  uptime wc xargs "$uv"; do
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
  echo "new evidence path must be absolute and canonical" >&2
  exit 1
fi
if [[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]; then
  echo "evidence directory must be outside the source checkout" >&2
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
mkdir "$evidence/a" "$evidence/b" "$evidence/inspections" "$evidence/logs"

write_manifest() {
  local temporary="$evidence/.final-evidence-sha256.txt.tmp"
  rm -f "$temporary"
  if find "$evidence" -type l -print -quit | grep -q .; then
    echo "evidence tree contains a symbolic link" >&2
    return 1
  fi
  if find "$evidence" ! -type d ! -type f -print -quit | grep -q .; then
    echo "evidence tree contains a special filesystem node" >&2
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
  ) >"$temporary"
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
    printf 'source_audit_verified=%s\n' "$source_audit_verified"
    printf 'double_build_verified=%s\n' "$double_build_verified"
    printf 'inspect_verified=%s\n' "$inspect_verified"
    printf 'promotion_state_unchanged=%s\n' "$promotion_state_unchanged"
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
    printf 'nepal_bhasa_candidate_pack_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

exec 9>/home/cdjk/data/nepa-keyboard/.nepal-bhasa-candidate-pack.lock
if ! flock -n 9; then
  echo "another Nepal Bhasa candidate-pack transaction is running" >&2
  exit 1
fi

stage=host_preflight
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

run_python() {
  PYTHONPATH=src:. "$uv" run --python 3.14 python "$@"
}

verify_profiles() {
  jq -e '
    [.profiles[] | select(.target_id == "new")] as $profiles
    | ($profiles | length) == 4
    and ([$profiles[].profile_id] | sort) == [
      "new-Deva-NP",
      "new-Deva-Newa-NP",
      "new-Latn-Deva-NP",
      "new-Newa-NP"
    ]
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

stage=input_contract
for input in "$trilingual_raw" "$apk_raw" "$source_audit" "$spec" "$catalog" \
  "$profile_review" "$profile_lock" "$layout_lock" "$android_pins" "$adapter" \
  "$auditor" "$compiler" "$runtime" "$adapter_test" "$runner" "$runner_test"; do
  if [[ -L "$input" || ! -f "$input" ]]; then
    echo "required input is not a regular non-symbolic file: $input" >&2
    exit 1
  fi
done

run_python - "$spec" >"$evidence/spec-strict-check.txt" <<'PY'
import json
import math
import pathlib
import sys

def pairs(items):
    value = {}
    for key, child in items:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = child
    return value

def constant(value):
    raise ValueError(f"non-finite JSON value: {value}")

path = pathlib.Path(sys.argv[1])
raw = path.read_bytes()
if raw.startswith(b"\xef\xbb\xbf"):
    raise ValueError("candidate spec has a UTF-8 BOM")
value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
if not isinstance(value, dict):
    raise ValueError("candidate spec must be one object")
print("candidate_spec_strict_json_verified=true")
PY

jq -e '
  (keys | sort) == [
    "adapter_sha256", "candidate_column", "claim_scope", "compiler_sha256",
    "data_version", "expected", "format_version", "inspection_vectors",
    "layout_id", "layout_policy", "locked_state_sha256", "max_suggestions",
    "pack_id", "policies", "raw_sha256", "resource_id", "runtime_sha256",
    "source_audit_sha256", "target_id"
  ]
  and .format_version == 1
  and .claim_scope == "candidate_only"
  and .target_id == "new"
  and .resource_id == "new-nepali-trilingual"
  and .candidate_column == "newar"
  and .pack_id == "new-Deva-NP"
  and .layout_id == null
  and .layout_policy == "unselected; candidate artifact only"
  and .data_version == "1.0.0"
  and .max_suggestions == 8
  and (.expected.required_scalars | length) == 66
  and (.inspection_vectors | length) == 5
  and all(.inspection_vectors[];
    (.prefix | type == "string" and length > 0)
    and (.expected_first_surface | type == "string" and length > 0)
  )
' "$spec" >/dev/null

expected_raw_sha="$(jq -r '.raw_sha256' "$spec")"
expected_audit_sha="$(jq -r '.source_audit_sha256' "$spec")"
expected_adapter_sha="$(jq -r '.adapter_sha256' "$spec")"
expected_compiler_sha="$(jq -r '.compiler_sha256' "$spec")"
expected_runtime_sha="$(jq -r '.runtime_sha256' "$spec")"
[[ "$(sha256sum "$trilingual_raw" | awk '{print $1}')" == "$expected_raw_sha" ]]
[[ "$(sha256sum "$source_audit" | awk '{print $1}')" == "$expected_audit_sha" ]]
[[ "$(sha256sum "$adapter" | awk '{print $1}')" == "$expected_adapter_sha" ]]
[[ "$(sha256sum "$compiler" | awk '{print $1}')" == "$expected_compiler_sha" ]]
[[ "$(sha256sum "$runtime" | awk '{print $1}')" == "$expected_runtime_sha" ]]
[[ "$(sha256sum "$profile_lock" | awk '{print $1}')" \
    == "$(jq -r '.locked_state_sha256.profile_lock' "$spec")" ]]
[[ "$(sha256sum "$layout_lock" | awk '{print $1}')" \
    == "$(jq -r '.locked_state_sha256.layout_lock' "$spec")" ]]
[[ "$(sha256sum "$android_pins" | awk '{print $1}')" \
    == "$(jq -r '.locked_state_sha256.android_gradle' "$spec")" ]]

verify_profiles
jq -e '
  .selections.candidate_resource_ids == []
  and .selections.candidate_columns == {
    "new-apk-english": null,
    "new-nepali-trilingual": null
  }
  and .selections.pack_id == null
  and .selections.layout_ids == []
  and all(.selections.profile_promotions[]; . == false)
  and ([.profile_bindings.profiles[] | select(.selectable == true)] | length) == 0
' "$source_audit" >/dev/null

cp "$spec" "$evidence/candidate-spec.json"
cp "$source_audit" "$evidence/source-audit.json"
sha256sum "$trilingual_raw" "$apk_raw" "$source_audit" "$spec" "$catalog" \
  "$profile_review" "$profile_lock" "$layout_lock" "$android_pins" "$adapter" \
  "$auditor" "$compiler" "$runtime" "$adapter_test" "$runner" "$runner_test" \
  >"$evidence/input-source-sha256.txt"
sha256sum "$catalog" "$profile_review" "$profile_lock" "$layout_lock" \
  "$android_pins" >"$evidence/promotion-state-before.txt"

stage=focused_tests
(
  cd "$repo"
  run_python -m unittest discover -s tests -p test_nepal_bhasa_internal_source.py
  run_python -m unittest discover -s tests -p test_nepal_bhasa_candidate_pack_runner.py
) >"$evidence/focused-tests.txt" 2>&1
focused_tests_verified=1

stage=source_audit_check
(
  cd "$repo"
  run_python tools/audit_nepal_bhasa_tsv_contract.py \
    --resource-catalog "$catalog" \
    --profile-lock "$profile_lock" \
    --layout-lock "$layout_lock" \
    --trilingual-tsv "$trilingual_raw" \
    --apk-tsv "$apk_raw" \
    --output "$source_audit" \
    --check
) >"$evidence/source-audit-check.json" 2>"$evidence/source-audit-check.stderr.txt"
jq -e --arg output "$source_audit" --arg sha "$expected_audit_sha" '
  .status == "passed"
  and .output == $output
  and .report_sha256 == $sha
' "$evidence/source-audit-check.json" >/dev/null
source_audit_verified=1

stage=double_build
data_version="$(jq -r '.data_version' "$spec")"
max_suggestions="$(jq -r '.max_suggestions' "$spec")"
pack_id="$(jq -r '.pack_id' "$spec")"
for run in a b; do
  (
    cd "$repo"
    run_python tools/build_nepal_bhasa_internal_source.py \
      --trilingual-tsv "$trilingual_raw" \
      --data-version "$data_version" \
      --max-suggestions "$max_suggestions" \
      --output "$evidence/$run/source"
  ) >"$evidence/$run/adapter-stdout.json" \
    2>"$evidence/$run/adapter-stderr.txt"
  (
    cd "$repo"
    run_python -m nepa_keyboard.compiler build \
      --input "$evidence/$run/source" \
      --output "$evidence/$run/$pack_id.nkp" \
      --mode internal
  ) >"$evidence/$run/compiler-stdout.json" \
    2>"$evidence/$run/compiler-stderr.txt"
  jq -S 'del(.artifact)' "$evidence/$run/$pack_id.nkp.report.json" \
    >"$evidence/$run/compiler-report.normalized.json"
  (
    cd "$evidence/$run/source"
    LC_ALL=C find . -maxdepth 1 -type f -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 sha256sum
  ) >"$evidence/$run/source-sha256.txt"
  unzip -t "$evidence/$run/$pack_id.nkp" \
    >"$evidence/$run/pack-integrity.txt"
  unzip -Z1 "$evidence/$run/$pack_id.nkp" \
    | LC_ALL=C sort >"$evidence/$run/pack-members.txt"
done
diff -qr "$evidence/a/source" "$evidence/b/source" \
  >"$evidence/source-tree-diff.txt"
cmp "$evidence/a/adapter-stdout.json" "$evidence/b/adapter-stdout.json"
cmp "$evidence/a/source-sha256.txt" "$evidence/b/source-sha256.txt"
cmp "$evidence/a/compiler-report.normalized.json" \
  "$evidence/b/compiler-report.normalized.json"
cmp "$evidence/a/pack-members.txt" "$evidence/b/pack-members.txt"
cmp "$evidence/a/$pack_id.nkp" "$evidence/b/$pack_id.nkp"

jq -e --slurpfile spec "$spec" '
  .adapter_sha256 == $spec[0].adapter_sha256
  and .candidate_column == $spec[0].candidate_column
  and .claim_scope == "candidate_only; no profile or layout is selected"
  and .excluded_columns == ["nepali"]
  and .policies == $spec[0].policies
  and .stats.rows == $spec[0].expected.source_rows
  and .stats.accepted_rows == $spec[0].expected.accepted_rows
  and .stats.rejected_rows == $spec[0].expected.rejected_rows
  and .stats.rejected_invalid_joiner_context
    == $spec[0].expected.rejected_invalid_joiner_context
  and .stats.rejected_no_devanagari_letter
    == $spec[0].expected.rejected_no_devanagari_letter
  and .stats.distinct_accepted_surfaces == $spec[0].expected.candidate_surfaces
  and .stats.normalized_rows == 0
  and [.accepted_scalar_inventory.frequencies[].scalar]
    == $spec[0].expected.required_scalars
' "$evidence/a/source/adapter-report.json" >/dev/null

jq -e --slurpfile spec "$spec" '
  .manifest.pack.pack_id == $spec[0].pack_id
  and .manifest.pack.language == "new"
  and .manifest.pack.output_script == "Deva"
  and .manifest.pack.data_version == $spec[0].data_version
  and .manifest.pack.max_suggestions == $spec[0].max_suggestions
  and .manifest.release_mode == "internal"
  and .manifest.counts.source_forms == $spec[0].expected.accepted_rows
  and .manifest.counts.candidate_surfaces == $spec[0].expected.candidate_surfaces
  and .manifest.counts.duplicate_surfaces_merged
    == $spec[0].expected.duplicate_surfaces_merged
  and .manifest.counts.alias_rows == 0
  and .manifest.counts.alias_keys == 0
  and .manifest.counts.alias_collisions == 0
  and .manifest.counts.sources_used == 1
  and .manifest.indexes.surface.keys == $spec[0].expected.candidate_surfaces
  and .manifest.indexes.aliases.keys == 0
' "$evidence/a/$pack_id.nkp.report.json" >/dev/null

pack_sha="$(sha256sum "$evidence/a/$pack_id.nkp" | awk '{print $1}')"
pack_bytes="$(stat -c '%s' "$evidence/a/$pack_id.nkp")"
[[ "$pack_sha" == "$(jq -r '.expected.pack_sha256' "$spec")" ]]
[[ "$pack_bytes" == "$(jq -r '.expected.pack_bytes' "$spec")" ]]
sha256sum "$evidence/a/$pack_id.nkp" "$evidence/b/$pack_id.nkp" \
  "$evidence/a/$pack_id.nkp.report.json" \
  "$evidence/b/$pack_id.nkp.report.json" >"$evidence/pack-sha256.txt"
double_build_verified=1

stage=inspect
jq -c '.inspection_vectors[]' "$spec" >"$evidence/inspection-vectors.jsonl"
inspect_count=0
: >"$evidence/inspection-summary.jsonl"
while IFS= read -r vector; do
  prefix="$(jq -r '.prefix' <<<"$vector")"
  expected_first_surface="$(jq -r '.expected_first_surface' <<<"$vector")"
  label="$(printf '%03d' "$inspect_count")"
  for run in a b; do
    (
      cd "$repo"
      run_python -m nepa_keyboard.compiler inspect \
        --pack "$evidence/$run/$pack_id.nkp" \
        --index surface \
        --prefix="$prefix"
    ) >"$evidence/inspections/$label.$run.json" \
      2>"$evidence/logs/$label.$run.inspect.stderr.txt"
  done
  cmp "$evidence/inspections/$label.a.json" \
    "$evidence/inspections/$label.b.json"
  jq -e --arg expected "$expected_first_surface" --arg prefix "$prefix" \
    --argjson maximum "$max_suggestions" '
    .index == "surface"
    and .prefix == $prefix
    and (.candidates | type == "array" and length >= 1 and length <= $maximum)
    and .candidates[0].surface == $expected
    and all(.candidates[];
      (.surface | type == "string" and length > 0)
      and (.candidate_id | type == "number" and floor == . and . >= 0)
      and (.score | type == "number" and floor == .)
    )
  ' "$evidence/inspections/$label.a.json" >/dev/null
  jq -c --arg expected "$expected_first_surface" --argjson index "$inspect_count" '
    {
      candidate_count: (.candidates | length),
      expected_first_surface: $expected,
      index: $index,
      prefix: .prefix,
      top_surfaces: [.candidates[].surface]
    }
  ' "$evidence/inspections/$label.a.json" \
    >>"$evidence/inspection-summary.jsonl"
  inspect_count=$((inspect_count + 1))
done <"$evidence/inspection-vectors.jsonl"
[[ "$inspect_count" == "$(jq -r '.inspection_vectors | length' "$spec")" ]]
inspect_verified=1

stage=promotion_guard
verify_profiles
sha256sum "$catalog" "$profile_review" "$profile_lock" "$layout_lock" \
  "$android_pins" >"$evidence/promotion-state-after.txt"
cmp "$evidence/promotion-state-before.txt" "$evidence/promotion-state-after.txt"
promotion_state_unchanged=1

stage=complete
jq -S -n \
  --arg adapter_sha256 "$expected_adapter_sha" \
  --arg audit_sha256 "$expected_audit_sha" \
  --arg compiler_sha256 "$expected_compiler_sha" \
  --arg pack_id "$pack_id" \
  --arg pack_sha256 "$pack_sha" \
  --arg raw_sha256 "$expected_raw_sha" \
  --arg runtime_sha256 "$expected_runtime_sha" \
  --argjson accepted_rows "$(jq -r '.expected.accepted_rows' "$spec")" \
  --argjson candidate_surfaces "$(jq -r '.expected.candidate_surfaces' "$spec")" \
  --argjson inspect_count "$inspect_count" \
  --argjson pack_bytes "$pack_bytes" '
  {
    accepted_rows: $accepted_rows,
    adapter_sha256: $adapter_sha256,
    candidate_surfaces: $candidate_surfaces,
    claim_scope: "Candidate build evidence only; no layout or profile was selected.",
    compiler_sha256: $compiler_sha256,
    inspect_count: $inspect_count,
    layout_id: null,
    pack_bytes: $pack_bytes,
    pack_id: $pack_id,
    pack_sha256: $pack_sha256,
    packs_byte_identical: true,
    profile_promoted: false,
    raw_sha256: $raw_sha256,
    runtime_sha256: $runtime_sha256,
    source_audit_sha256: $audit_sha256,
    source_trees_byte_identical: true,
    status: "ok"
  }
' >"$evidence/candidate-pack-summary.json"
sequence_complete=1
exit 0
