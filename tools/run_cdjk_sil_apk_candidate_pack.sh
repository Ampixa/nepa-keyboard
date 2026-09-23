#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ $# -ne 4 || "$1" != /* || "$2" != /* || "$3" != /* || "$4" != /* ]]; then
  echo "usage: $0 /absolute/raw.jsonl /absolute/layout-audit.json /absolute/candidate-spec.json /absolute/new/evidence-directory" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
raw_argument="$1"
audit_argument="$2"
spec_argument="$3"
evidence_argument="$4"
catalog="$repo/catalog/resources.json"
profile_review="$repo/catalog/internal-profile-review.json"
profile_lock="$repo/catalog/internal-profiles.lock.json"
layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
uv="$HOME/.local/bin/uv"
stage=initializing
adapter_test_verified=0
audit_verified=0
double_build_verified=0
inspect_verified=0
promotion_state_unchanged=0

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this SIL-APK candidate-pack runner must run from the cdjk Ubuntu checkout" >&2
  exit 1
fi

for required in awk basename cmp cp df diff dirname find flock free grep hostname \
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

canonical_regular() {
  local argument="$1"
  local label="$2"
  local canonical
  canonical="$(realpath -e -- "$argument")"
  if [[ "$argument" != "$canonical" || -L "$argument" || ! -f "$canonical" ]]; then
    echo "$label must be a canonical, non-symbolic regular file: $argument" >&2
    return 1
  fi
  printf '%s\n' "$canonical"
}

raw="$(canonical_regular "$raw_argument" "raw SIL-APK JSONL")"
audit="$(canonical_regular "$audit_argument" "layout audit")"
spec="$(canonical_regular "$spec_argument" "candidate spec")"
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
exec 9>/tmp/nepa-keyboard-android-validation.lock
if ! flock -n 9; then
  echo "another Nepa Android, relock, or corpus validation owns the cdjk lock" >&2
  exit 1
fi
if ! mkdir "$evidence"; then
  echo "could not atomically claim evidence directory: $evidence" >&2
  exit 1
fi
mkdir -p \
  "$evidence/a/source" \
  "$evidence/b/source" \
  "$evidence/inspections" \
  "$evidence/logs"

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
    printf 'completed_stage=%s\n' "$stage"
    printf 'command_exit_status=%s\n' "$command_status"
    printf 'adapter_test_verified=%s\n' "$adapter_test_verified"
    printf 'audit_verified=%s\n' "$audit_verified"
    printf 'double_build_verified=%s\n' "$double_build_verified"
    printf 'inspect_verified=%s\n' "$inspect_verified"
    printf 'promotion_state_unchanged=%s\n' "$promotion_state_unchanged"
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
  if (( command_status == 0 \
        && (adapter_test_verified != 1 \
            || audit_verified != 1 \
            || double_build_verified != 1 \
            || inspect_verified != 1 \
            || promotion_state_unchanged != 1) )); then
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
    printf 'sil_apk_candidate_pack_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

stage=preflight
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
  echo "cdjk has insufficient free disk for candidate-pack evidence" >&2
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
  "$profile_review" \
  "$profile_lock" \
  "$layout_lock" \
  "$repo/schemas/layout-v1.schema.json" \
  "$repo/schemas/layout-lock-v1.schema.json" \
  "$repo/tools/build_keyboard_layouts.py" \
  "$repo/tools/sil_apk_jsonl_internal_source.py" \
  "$repo/tools/build_sil_apk_candidate_source.py" \
  "$repo/tools/audit_sil_apk_layout_gap.py" \
  "$repo/tools/run_cdjk_sil_apk_candidate_pack.sh" \
  "$repo/tests/test_sil_apk_candidate_source.py" \
  "$repo/src/nepa_keyboard/compiler.py" \
  "$repo/src/nepa_keyboard/runtime.py"; do
  if [[ -L "$input" || ! -s "$input" ]]; then
    echo "canonical input is missing, symbolic, or empty: $input" >&2
    exit 1
  fi
done

cd "$repo"
run_python() {
  PYTHONPATH=src:. timeout 1200 "$uv" run --python 3.14 python "$@"
}

jq empty "$catalog" "$profile_review" "$profile_lock" "$layout_lock" "$audit" "$spec"
sha256sum "$catalog" "$profile_review" "$profile_lock" "$layout_lock" \
  >"$evidence/promotion-state-before.txt"
run_python -c '
import json
import sys
from pathlib import Path

def strict_object(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = child
    return value

path = Path(sys.argv[1])
encoded = path.read_bytes()
if encoded.startswith(b"\xef\xbb\xbf"):
    raise ValueError("candidate spec must not contain a UTF-8 BOM")
value = json.loads(encoded.decode("utf-8"), object_pairs_hook=strict_object)
if not isinstance(value, dict):
    raise ValueError("candidate spec must be a JSON object")
print("candidate_spec_strict_json_verified=true")
' "$spec" >"$evidence/candidate-spec-strict-check.txt"
jq -e '
  (keys | sort) == [
    "adapter_sha256",
    "claim_scope",
    "compiler_sha256",
    "data_version",
    "format_version",
    "inspection_vectors",
    "layout_audit_sha256",
    "layout_id",
    "max_suggestions",
    "policy",
    "raw_sha256",
    "resource_id",
    "runtime_sha256",
    "source_tag",
    "target_id"
  ]
  and .format_version == 1
  and .claim_scope == "candidate_only"
  and (.target_id | test("^[a-z0-9][a-z0-9._-]*$"))
  and (.resource_id | test("^[a-z0-9][a-z0-9._-]*$"))
  and (.source_tag | test("^sil-apk/[a-z0-9][a-z0-9._-]*$"))
  and (.layout_id | test("^[a-z0-9][a-z0-9._-]*$"))
  and (.adapter_sha256 | test("^[0-9a-f]{64}$"))
  and (.compiler_sha256 | test("^[0-9a-f]{64}$"))
  and (.runtime_sha256 | test("^[0-9a-f]{64}$"))
  and (.layout_audit_sha256 | test("^[0-9a-f]{64}$"))
  and (.raw_sha256 | test("^[0-9a-f]{64}$"))
  and (.policy == "conjunct_only" or .policy == "terminal_zwnj")
  and (.data_version | test("^[0-9]+\\.[0-9]+\\.[0-9]+$"))
  and (.max_suggestions | type == "number" and floor == . and . >= 1 and . <= 32)
  and (.inspection_vectors | type == "array" and length >= 1 and length <= 64)
  and (all(.inspection_vectors[];
    type == "object"
    and (keys | sort) == ["expected_first_surface", "prefix"]
    and (.prefix | type == "string" and length >= 1 and length <= 128)
    and (.expected_first_surface
      | type == "string" and length >= 1 and length <= 256)
    and (.prefix | test("[\u0000-\u001F\u007F]") | not)
    and (.expected_first_surface | test("[\u0000-\u001F\u007F]") | not)
  ))
  and ([.inspection_vectors[].prefix] | length == (unique | length))
' "$spec" >/dev/null

target_id="$(jq -r '.target_id' "$spec")"
resource_id="$(jq -r '.resource_id' "$spec")"
source_tag="$(jq -r '.source_tag' "$spec")"
layout_id="$(jq -r '.layout_id' "$spec")"
policy="$(jq -r '.policy' "$spec")"
data_version="$(jq -r '.data_version' "$spec")"
max_suggestions="$(jq -r '.max_suggestions' "$spec")"
expected_raw_sha="$(jq -r '.raw_sha256' "$spec")"
expected_audit_sha="$(jq -r '.layout_audit_sha256' "$spec")"
expected_adapter_sha="$(jq -r '.adapter_sha256' "$spec")"
expected_compiler_sha="$(jq -r '.compiler_sha256' "$spec")"
expected_runtime_sha="$(jq -r '.runtime_sha256' "$spec")"
actual_raw_sha="$(sha256sum "$raw" | awk '{print $1}')"
actual_audit_sha="$(sha256sum "$audit" | awk '{print $1}')"
actual_adapter_sha="$(sha256sum tools/build_sil_apk_candidate_source.py | awk '{print $1}')"
actual_compiler_sha="$(sha256sum src/nepa_keyboard/compiler.py | awk '{print $1}')"
actual_runtime_sha="$(sha256sum src/nepa_keyboard/runtime.py | awk '{print $1}')"
[[ "$actual_raw_sha" == "$expected_raw_sha" ]]
[[ "$actual_audit_sha" == "$expected_audit_sha" ]]
[[ "$actual_adapter_sha" == "$expected_adapter_sha" ]]
[[ "$actual_compiler_sha" == "$expected_compiler_sha" ]]
[[ "$actual_runtime_sha" == "$expected_runtime_sha" ]]

jq -e \
  --arg target "$target_id" \
  --arg resource "$resource_id" \
  --arg source_tag "$source_tag" \
  --arg layout "$layout_id" \
  --arg raw_sha "$actual_raw_sha" '
  .format_version == 1
  and .input.target_id == $target
  and .input.resource_id == $resource
  and .input.source_tag == $source_tag
  and .input.sha256 == $raw_sha
  and .layout.layout_id == $layout
  and .layout.layout_lock_path == "layouts/internal/layouts-v1.lock.json"
  and (.policies | keys | sort) == ["conjunct_only", "terminal_zwnj"]
' "$audit" >/dev/null

cp "$audit" "$evidence/layout-audit.json"
cp "$spec" "$evidence/candidate-spec.json"
sha256sum \
  catalog/resources.json \
  catalog/internal-profile-review.json \
  catalog/internal-profiles.lock.json \
  layouts/internal/layouts-v1.lock.json \
  schemas/layout-v1.schema.json \
  schemas/layout-lock-v1.schema.json \
  tools/build_keyboard_layouts.py \
  tools/sil_apk_jsonl_internal_source.py \
  tools/build_sil_apk_candidate_source.py \
  tools/audit_sil_apk_layout_gap.py \
  tools/run_cdjk_sil_apk_candidate_pack.sh \
  tests/test_sil_apk_candidate_source.py \
  src/nepa_keyboard/compiler.py \
  src/nepa_keyboard/runtime.py \
  >"$evidence/input-source-sha256.txt"

stage=audit_check
{
  "$uv" --version
  run_python -VV
  uname -a
} >"$evidence/runtime-versions.txt" 2>&1
stage=adapter_test
run_python -m unittest discover -s tests -p test_sil_apk_candidate_source.py \
  >"$evidence/test-sil-apk-candidate-source.txt" 2>&1
adapter_test_verified=1

stage=audit_check
run_python tools/audit_sil_apk_layout_gap.py \
  --resource-catalog catalog/resources.json \
  --target-id "$target_id" \
  --resource-id "$resource_id" \
  --sil-apk-jsonl "$raw" \
  --source-tag "$source_tag" \
  --layout-lock layouts/internal/layouts-v1.lock.json \
  --layout-id "$layout_id" \
  --output "$audit" \
  --check \
  >"$evidence/audit-check.json" \
  2>"$evidence/audit-check.stderr.txt"
jq -e --arg audit "$audit" --arg sha "$actual_audit_sha" '
  .status == "passed"
  and .output == $audit
  and .report_sha256 == $sha
' "$evidence/audit-check.json" >/dev/null
jq -S --arg policy "$policy" '
  {
    claim_scope: (
      "Measured candidate input only; this does not select a production layout "
      + "or promote a profile."
    ),
    input: .input,
    layout: .layout,
    policy_id: $policy,
    policy_measurements: .policies[$policy],
    terminal_zwnj_delta: .terminal_zwnj_delta
  }
' "$audit" >"$evidence/selected-layout-policy-measurement.json"
audit_verified=1

stage=double_build
language="$(jq -r '.input.language' "$audit")"
if [[ ! "$language" =~ ^[a-z]{3}$ ]]; then
  echo "audited language is not a lowercase ISO 639-3 code" >&2
  exit 1
fi
pack_id="$language-Deva-NP"
for run in a b; do
  run_python tools/build_sil_apk_candidate_source.py \
    --resource-catalog catalog/resources.json \
    --target-id "$target_id" \
    --resource-id "$resource_id" \
    --sil-apk-jsonl "$raw" \
    --source-tag "$source_tag" \
    --policy "$policy" \
    --data-version "$data_version" \
    --max-suggestions "$max_suggestions" \
    --output "$evidence/$run/source" \
    >"$evidence/$run/adapter-stdout.json" \
    2>"$evidence/$run/adapter-stderr.txt"
  run_python -m nepa_keyboard.compiler build \
    --input "$evidence/$run/source" \
    --output "$evidence/$run/$pack_id.nkp" \
    --mode internal \
    >"$evidence/$run/compiler-stdout.json" \
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

jq -e \
  --slurpfile audit "$audit" \
  --arg adapter_sha "$actual_adapter_sha" \
  --arg policy "$policy" '
  .adapter_sha256 == $adapter_sha
  and .joiner_policy.allow_terminal_zwnj == ($policy == "terminal_zwnj")
  and .stats.accepted_rows == $audit[0].policies[$policy].accepted_rows
  and .stats.accepted_terminal_zwnj_rows
    == $audit[0].policies[$policy].accepted_terminal_zwnj_rows
  and .stats.distinct_accepted_surfaces
    == $audit[0].policies[$policy].distinct_accepted_surfaces
  and .stats.rejected_rows == $audit[0].policies[$policy].rejected_rows
  and .stats.normalized_rows == $audit[0].policies[$policy].normalized_rows
' "$evidence/a/source/adapter-report.json" >/dev/null
jq -e \
  --slurpfile audit "$audit" \
  --arg pack_id "$pack_id" \
  --arg language "$language" \
  --arg data_version "$data_version" \
  --arg policy "$policy" \
  --argjson max_suggestions "$max_suggestions" '
  .manifest.pack.pack_id == $pack_id
  and .manifest.pack.language == $language
  and .manifest.pack.output_script == "Deva"
  and .manifest.pack.data_version == $data_version
  and .manifest.pack.max_suggestions == $max_suggestions
  and .manifest.release_mode == "internal"
  and .manifest.counts.source_forms
    == $audit[0].policies[$policy].accepted_rows
  and .manifest.counts.candidate_surfaces
    == $audit[0].policies[$policy].distinct_accepted_surfaces
  and .manifest.counts.duplicate_surfaces_merged
    == ($audit[0].policies[$policy].accepted_rows
      - $audit[0].policies[$policy].distinct_accepted_surfaces)
  and .manifest.counts.alias_rows == 0
  and .manifest.counts.alias_keys == 0
  and .manifest.counts.alias_collisions == 0
  and .manifest.counts.sources_used == 1
  and .manifest.indexes.surface.keys
    == $audit[0].policies[$policy].distinct_accepted_surfaces
  and .manifest.indexes.aliases.keys == 0
' "$evidence/a/$pack_id.nkp.report.json" >/dev/null
pack_sha="$(sha256sum "$evidence/a/$pack_id.nkp" | awk '{print $1}')"
pack_bytes="$(stat -c '%s' "$evidence/a/$pack_id.nkp")"
sha256sum \
  "$evidence/a/$pack_id.nkp" \
  "$evidence/b/$pack_id.nkp" \
  "$evidence/a/$pack_id.nkp.report.json" \
  "$evidence/b/$pack_id.nkp.report.json" \
  >"$evidence/pack-sha256.txt"
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
    run_python -m nepa_keyboard.compiler inspect \
      --pack "$evidence/$run/$pack_id.nkp" \
      --index surface \
      --prefix="$prefix" \
      >"$evidence/inspections/$label.$run.json" \
      2>"$evidence/logs/$label.$run.inspect.stderr.txt"
  done
  cmp "$evidence/inspections/$label.a.json" \
    "$evidence/inspections/$label.b.json"
  jq -e \
    --arg expected "$expected_first_surface" \
    --arg prefix "$prefix" \
    --argjson maximum "$max_suggestions" '
    .index == "surface"
    and .prefix == $prefix
    and (.candidates | type == "array" and length >= 1 and length <= $maximum)
    and .candidates[0].surface == $expected
    and (all(.candidates[];
      (.surface | type == "string" and length > 0)
      and (.candidate_id | type == "number" and floor == . and . >= 0)
      and (.score | type == "number" and floor == .)
    ))
  ' "$evidence/inspections/$label.a.json" >/dev/null
  jq -c \
    --arg expected "$expected_first_surface" \
    --argjson index "$inspect_count" '
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
expected_inspect_count="$(jq -r '.inspection_vectors | length' "$spec")"
[[ "$inspect_count" -eq "$expected_inspect_count" ]]
inspect_verified=1

stage=promotion_guard
sha256sum "$catalog" "$profile_review" "$profile_lock" "$layout_lock" \
  >"$evidence/promotion-state-after.txt"
cmp "$evidence/promotion-state-before.txt" "$evidence/promotion-state-after.txt"
promotion_state_unchanged=1

stage=complete
jq -S -n \
  --arg adapter_sha256 "$actual_adapter_sha" \
  --arg audit_sha256 "$actual_audit_sha" \
  --arg compiler_sha256 "$actual_compiler_sha" \
  --arg layout_id "$layout_id" \
  --arg pack_id "$pack_id" \
  --arg pack_sha256 "$pack_sha" \
  --arg policy "$policy" \
  --arg raw_sha256 "$actual_raw_sha" \
  --arg resource_id "$resource_id" \
  --arg runtime_sha256 "$actual_runtime_sha" \
  --arg target_id "$target_id" \
  --argjson inspect_count "$inspect_count" \
  --argjson pack_bytes "$pack_bytes" '
  {
    adapter_sha256: $adapter_sha256,
    claim_scope: "Candidate build evidence only; no profile was promoted.",
    compiler_sha256: $compiler_sha256,
    inspect_count: $inspect_count,
    layout_audit_sha256: $audit_sha256,
    layout_id: $layout_id,
    pack_bytes: $pack_bytes,
    pack_id: $pack_id,
    pack_sha256: $pack_sha256,
    packs_byte_identical: true,
    policy: $policy,
    profile_promoted: false,
    raw_sha256: $raw_sha256,
    resource_id: $resource_id,
    runtime_sha256: $runtime_sha256,
    source_trees_byte_identical: true,
    status: "ok",
    target_id: $target_id
  }
' >"$evidence/candidate-pack-summary.json"

exit 0
