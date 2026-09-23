#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ $# -ne 5 || "$3" != /* || "$5" != /* ]]; then
  echo "usage: $0 target-id resource-id /absolute/raw.jsonl source-tag /absolute/new/evidence-directory" >&2
  exit 2
fi

target_id="$1"
resource_id="$2"
raw_argument="$3"
source_tag="$4"
evidence_argument="$5"
repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
catalog="$repo/catalog/resources.json"
profile_lock="$repo/catalog/internal-profiles.lock.json"
layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
uv="$HOME/.local/bin/uv"
audit_complete=0
summary_verified=0

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this SIL-APK layout-matrix runner must run from the cdjk Ubuntu checkout" >&2
  exit 1
fi
for value in "$target_id" "$resource_id"; do
  if [[ ! "$value" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
    echo "target and resource IDs must use lowercase catalog-ID syntax" >&2
    exit 2
  fi
done
if [[ ! "$source_tag" =~ ^sil-apk/[a-z0-9][a-z0-9._-]*$ ]]; then
  echo "source tag must use canonical sil-apk/name syntax" >&2
  exit 2
fi

for required in awk basename cmp cp df dirname find flock free grep hostname jq \
  mkdir mv pgrep ps realpath rm sed sha256sum sort timeout uname uptime wc xargs \
  "$uv"; do
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

raw="$(realpath -e -- "$raw_argument")"
if [[ "$raw_argument" != "$raw" || -L "$raw_argument" || ! -f "$raw" ]]; then
  echo "raw SIL-APK JSONL path must be canonical, non-symbolic, and regular" >&2
  exit 1
fi
evidence="$(realpath -m -- "$evidence_argument")"
evidence_parent="$(realpath -e -- "$(dirname -- "$evidence")")"
evidence="$evidence_parent/$(basename -- "$evidence")"
if [[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]; then
  echo "evidence directory must be outside the source checkout" >&2
  exit 1
fi
if [[ -e "$evidence" ]]; then
  echo "evidence directory already exists: $evidence" >&2
  exit 1
fi
mkdir -p "$evidence/audits" "$evidence/logs"

write_manifest() {
  local temporary="$evidence/.final-evidence-sha256.txt.tmp"
  rm -f "$temporary"
  (
    cd "$evidence"
    LC_ALL=C find . -type f \
      ! -name final-evidence-sha256.txt \
      ! -name .final-evidence-sha256.txt.tmp \
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
    printf 'command_exit_status=%s\n' "$command_status"
    printf 'audit_complete=%s\n' "$audit_complete"
    printf 'summary_verified=%s\n' "$summary_verified"
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
  if (( command_status == 0 && (audit_complete != 1 || summary_verified != 1) )); then
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
    printf 'sil_apk_layout_matrix_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

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
  echo "cdjk has insufficient free disk for matrix evidence" >&2
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

for input in \
  "$catalog" \
  "$profile_lock" \
  "$layout_lock" \
  "$repo/schemas/layout-v1.schema.json" \
  "$repo/schemas/layout-lock-v1.schema.json" \
  "$repo/tools/build_keyboard_layouts.py" \
  "$repo/tools/sil_apk_jsonl_internal_source.py" \
  "$repo/tools/audit_sil_apk_layout_gap.py" \
  "$repo/tools/run_cdjk_sil_apk_layout_matrix.sh"; do
  if [[ -L "$input" || ! -s "$input" ]]; then
    echo "canonical input is missing, symbolic, or empty: $input" >&2
    exit 1
  fi
done

cd "$repo"
jq empty "$catalog" "$profile_lock" "$layout_lock"
jq -e --arg target "$target_id" --arg resource "$resource_id" '
  [.packs[] | select(.id == $target)] as $targets
  | ($targets | length) == 1
  and ([$targets[0].resources[] | select(.id == $resource)] | length) == 1
' "$catalog" >/dev/null
jq -S --arg target "$target_id" --arg resource "$resource_id" '
  [.packs[] | select(.id == $target)][0] as $target
  | [$target.resources[] | select(.id == $resource)][0] as $resource
  | {
      target: {id: $target.id, iso_639_3: $target.iso_639_3, name: $target.name},
      resource: $resource
    }
' "$catalog" >"$evidence/catalog-binding.json"
jq -e '
  (.resource.kind == "lexicon")
  and (.resource.format == "JSONL")
  and (.resource.structured == true)
  and (.resource.canonical == true)
  and (.resource.record_unit == "entries")
  and (.resource.uses | type == "array" and index("candidate_vocabulary") != null)
  and (.resource.records | type == "number" and floor == . and . > 0)
  and (.resource.bytes | type == "number" and floor == . and . > 0)
  and (.resource.sha256 | type == "string" and test("^[0-9a-f]{64}$"))
  and (.resource.path | type == "string" and length > 0)
' "$evidence/catalog-binding.json" >/dev/null

expected_records="$(jq -r '.resource.records' "$evidence/catalog-binding.json")"
expected_bytes="$(jq -r '.resource.bytes' "$evidence/catalog-binding.json")"
expected_sha256="$(jq -r '.resource.sha256' "$evidence/catalog-binding.json")"
expected_name="$(jq -r '.resource.path | split("/")[-1]' "$evidence/catalog-binding.json")"
actual_records="$(LC_ALL=C awk 'END {print NR}' "$raw")"
actual_bytes="$(wc -c <"$raw" | awk '{print $1}')"
actual_sha256="$(sha256sum "$raw" | awk '{print $1}')"
if [[ "$(basename -- "$raw")" != "$expected_name" \
      || "$actual_records" != "$expected_records" \
      || "$actual_bytes" != "$expected_bytes" \
      || "$actual_sha256" != "$expected_sha256" ]]; then
  echo "raw filename/count/bytes/SHA do not match the catalog resource" >&2
  exit 1
fi
jq -S -n \
  --arg path "$raw" \
  --arg source_tag "$source_tag" \
  --arg sha256 "$actual_sha256" \
  --argjson records "$actual_records" \
  --argjson bytes "$actual_bytes" \
  '{path: $path, source_tag: $source_tag, sha256: $sha256, records: $records, bytes: $bytes}' \
  >"$evidence/raw-input.json"

sha256sum \
  catalog/resources.json \
  catalog/internal-profiles.lock.json \
  layouts/internal/layouts-v1.lock.json \
  schemas/layout-v1.schema.json \
  schemas/layout-lock-v1.schema.json \
  tools/build_keyboard_layouts.py \
  tools/sil_apk_jsonl_internal_source.py \
  tools/audit_sil_apk_layout_gap.py \
  tools/run_cdjk_sil_apk_layout_matrix.sh \
  >"$evidence/input-source-sha256.txt"
cp "$layout_lock" "$evidence/internal-layouts-v1.lock.json"

run_python() {
  PYTHONPATH=src:. timeout 900 "$uv" run --python 3.14 python "$@"
}

# This check and every audit rebuild the lock, so stale lock/compiler/schema/profile
# combinations fail before a compatibility result can be emitted.
run_python tools/build_keyboard_layouts.py \
  --source-directory layouts/internal/src \
  --profile-lock catalog/internal-profiles.lock.json \
  --output layouts/internal/layouts-v1.lock.json \
  --check >"$evidence/internal-layout-lock-check.log" 2>&1
[[ "$(jq -r '.review.authority' "$profile_lock")" == internal ]]
[[ "$(jq -r '.profile_lock.path' "$layout_lock")" \
  == catalog/internal-profiles.lock.json ]]
[[ "$(jq -r '.source_directory' "$layout_lock")" == layouts/internal/src ]]
cmp -s "$layout_lock" "$evidence/internal-layouts-v1.lock.json"

jq -r '
  [.layouts[] | select(.input_script == "Deva") | .layout_id] | sort | .[]
' "$layout_lock" >"$evidence/layout-ids.txt"
mapfile -t layout_ids <"$evidence/layout-ids.txt"
if (( ${#layout_ids[@]} == 0 )); then
  echo "canonical internal lock has no compiled Devanagari layouts" >&2
  exit 1
fi
if [[ "$(LC_ALL=C sort -u "$evidence/layout-ids.txt" | wc -l | awk '{print $1}')" \
      != "${#layout_ids[@]}" ]]; then
  echo "compiled Devanagari layout IDs are not unique" >&2
  exit 1
fi

for layout_id in "${layout_ids[@]}"; do
  if [[ ! "$layout_id" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
    echo "compiled layout ID is unsafe for evidence paths: $layout_id" >&2
    exit 1
  fi
  output="$evidence/audits/$layout_id.json"
  run_python tools/audit_sil_apk_layout_gap.py \
    --resource-catalog catalog/resources.json \
    --target-id "$target_id" \
    --resource-id "$resource_id" \
    --sil-apk-jsonl "$raw" \
    --source-tag "$source_tag" \
    --layout-lock layouts/internal/layouts-v1.lock.json \
    --layout-id "$layout_id" \
    --output "$output" \
    >"$evidence/logs/$layout_id.json" \
    2>"$evidence/logs/$layout_id.log"
  jq -e --arg output "$output" '
    .status == "passed"
    and .output == $output
    and (.report_sha256 | test("^[0-9a-f]{64}$"))
  ' "$evidence/logs/$layout_id.json" >/dev/null
done
audit_complete=1
cmp -s "$layout_lock" "$evidence/internal-layouts-v1.lock.json"

layout_lock_sha256="$(sha256sum "$layout_lock" | awk '{print $1}')"
jq -S -s \
  --slurpfile binding "$evidence/catalog-binding.json" \
  --slurpfile raw_input "$evidence/raw-input.json" \
  --arg lock_sha256 "$layout_lock_sha256" '
  def failure_reasons:
    ["intra_word_punctuation_context", "joiner_layout_policy",
     "layout_input_policy", "noncomposing_layout_key",
     "terminal_zwnj_layout_policy"];
  def row:
    .policies.terminal_zwnj as $p
    | ($p.single_token_composition.unqueryable_by_reason
      | with_entries(select(.key as $reason | failure_reasons | index($reason))))
      as $failures
    | {
        layout_id: .layout.layout_id,
        reachable_surfaces: (
          $p.distinct_accepted_surfaces
          - $p.single_token_composition.unqueryable_distinct_surfaces
        ),
        missing_input_scalars: $p.missing_input_scalars,
        missing_scalar_count: ($p.missing_input_scalars | length),
        policy_failures_by_reason: $failures,
        policy_failure_rows: ($failures | to_entries | map(.value) | add // 0)
      };
  map(row)
  | sort_by([-.reachable_surfaces, .missing_scalar_count,
             .policy_failure_rows, .layout_id]) as $ranking
  | {
      format_version: 1,
      claim_scope: (
        "Layout-input compatibility only; this ranking does not measure "
        + "or claim language or keyboard quality."
      ),
      target: $binding[0].target,
      resource_id: $binding[0].resource.id,
      raw_input: $raw_input[0],
      layout_lock_sha256: $lock_sha256,
      layout_count: ($ranking | length),
      ranking_basis: [
        "reachable surfaces descending",
        "missing input scalar count ascending",
        "layout-policy failure rows ascending",
        "layout_id ascending"
      ],
      ranking: $ranking
    }
' "$evidence"/audits/*.json >"$evidence/layout-matrix-summary.json.tmp"
mv "$evidence/layout-matrix-summary.json.tmp" \
  "$evidence/layout-matrix-summary.json"
jq -e --argjson count "${#layout_ids[@]}" '
  .format_version == 1
  and (.claim_scope | contains("does not measure"))
  and .layout_count == $count
  and (.ranking | length) == $count
  and ([.ranking[].layout_id] | length == (unique | length))
  and ([.ranking[].reachable_surfaces] | all(. >= 0))
  and ([.ranking[].missing_scalar_count] | all(. >= 0))
  and ([.ranking[].policy_failure_rows] | all(. >= 0))
' "$evidence/layout-matrix-summary.json" >/dev/null
jq -r '.ranking[].layout_id' "$evidence/layout-matrix-summary.json" \
  | LC_ALL=C sort >"$evidence/summary-layout-ids.sorted.txt"
cmp -s "$evidence/layout-ids.txt" "$evidence/summary-layout-ids.sorted.txt"
summary_verified=1
