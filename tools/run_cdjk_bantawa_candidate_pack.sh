#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ $# -ne 3 || "$1" != /* || "$2" != /* || "$3" != /* ]]; then
  echo "usage: $0 /absolute/completed-bantawa-source-probe /absolute/bantawa-transliterator.py /absolute/new/evidence-directory" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
raw=/home/cdjk/github/llm/rai-speech-toolkit/dialects/central/bantawa/dict/bantawa-english.dict.jsonl
catalog="$repo/catalog/resources.json"
profile_review="$repo/catalog/internal-profile-review.json"
profile_lock="$repo/catalog/internal-profiles.lock.json"
layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
android_pins="$repo/android/ime-app/build.gradle.kts"
spec="$repo/catalog/bantawa-candidate-pack-v0.json"
adapter="$repo/tools/build_bantawa_internal_source.py"
auditor="$repo/tools/audit_bantawa_candidate_layout.py"
compiler="$repo/src/nepa_keyboard/compiler.py"
runtime="$repo/src/nepa_keyboard/runtime.py"
uv="$HOME/.local/bin/uv"
stage=initializing
prerequisite_verified=0
focused_tests_verified=0
double_build_verified=0
layout_audit_verified=0
inspection_verified=0
state_unchanged=0
sequence_complete=0

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this Bantawa candidate-pack runner must run from the cdjk Ubuntu checkout" >&2
  exit 1
fi

for required in awk basename cmp cp df diff dirname find flock free grep \
  hostname jq mkdir mv pgrep ps realpath rm sed sha256sum sort stat timeout \
  uname unzip uptime wc xargs "$uv"; do
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

canonical_directory() {
  local argument="$1"
  local label="$2"
  if [[ -L "$argument" || ! -d "$argument" ]]; then
    echo "$label must be a non-symbolic directory: $argument" >&2
    return 1
  fi
  local canonical
  canonical="$(realpath -e -- "$argument")"
  if [[ "$canonical" != "$argument" ]]; then
    echo "$label path must be canonical: $argument" >&2
    return 1
  fi
  printf '%s\n' "$canonical"
}

canonical_regular() {
  local argument="$1"
  local label="$2"
  if [[ -L "$argument" || ! -f "$argument" ]]; then
    echo "$label must be a non-symbolic regular file: $argument" >&2
    return 1
  fi
  local canonical
  canonical="$(realpath -e -- "$argument")"
  if [[ "$canonical" != "$argument" ]]; then
    echo "$label path must be canonical: $argument" >&2
    return 1
  fi
  printf '%s\n' "$canonical"
}

prerequisite="$(canonical_directory "$1" "Bantawa source-probe prerequisite")"
transliterator="$(canonical_regular "$2" "Bantawa transliterator")"
evidence_parent="$(realpath -e -- "$(dirname -- "$3")")"
evidence="$evidence_parent/$(basename -- "$3")"
if [[ "$evidence" != "$3" ]]; then
  echo "new evidence path must be canonical" >&2
  exit 1
fi
for path in "$prerequisite" "$transliterator" "$evidence"; do
  if [[ "$path" == "$repo" || "$path" == "$repo/"* ]]; then
    echo "prerequisite, transliterator, and evidence must be outside the checkout" >&2
    exit 1
  fi
done
if [[ "$evidence" == "$prerequisite" || "$evidence" == "$prerequisite/"* ]]; then
  echo "new evidence must not be inside the prerequisite tree" >&2
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
mkdir -p "$evidence/a/source" "$evidence/b/source" \
  "$evidence/inspections" "$evidence/logs"

write_manifest() {
  local temporary="$evidence/.final-evidence-sha256.txt.tmp"
  rm -f "$temporary"
  if find "$evidence" -type l -print -quit | grep -q .; then
    echo "Bantawa candidate evidence contains a symbolic link" >&2
    return 1
  fi
  if find "$evidence" ! -type d ! -type f -print -quit | grep -q .; then
    echo "Bantawa candidate evidence contains a special filesystem node" >&2
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

recreate_prerequisite_manifest() {
  local output="$1"
  if find "$prerequisite" -type l -print -quit | grep -q .; then
    echo "Bantawa source-probe prerequisite contains a symbolic link" >&2
    return 1
  fi
  (
    cd "$prerequisite"
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
    printf 'prerequisite_verified=%s\n' "$prerequisite_verified"
    printf 'focused_tests_verified=%s\n' "$focused_tests_verified"
    printf 'double_build_verified=%s\n' "$double_build_verified"
    printf 'layout_audit_verified=%s\n' "$layout_audit_verified"
    printf 'inspection_verified=%s\n' "$inspection_verified"
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
    printf 'bantawa_candidate_pack_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

stage=input_validation
for input in "$raw" "$catalog" "$profile_review" "$profile_lock" \
  "$layout_lock" "$android_pins" "$spec" "$adapter" "$auditor" \
  "$compiler" "$runtime" \
  "$repo/tests/test_bantawa_internal_source.py" \
  "$repo/tests/test_bantawa_candidate_layout.py" \
  "$repo/tests/test_bantawa_candidate_pack_runner.py" \
  "$repo/tools/run_cdjk_bantawa_candidate_pack.sh"; do
  if [[ -L "$input" || ! -s "$input" ]]; then
    echo "canonical input is missing, symbolic, or empty: $input" >&2
    exit 1
  fi
done
if [[ "$(realpath -e -- "$raw")" != "$raw" ]]; then
  echo "Bantawa dictionary path is not canonical" >&2
  exit 1
fi
jq empty "$catalog" "$profile_review" "$profile_lock" "$layout_lock" "$spec"

stage=host_preflight
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
  echo "cdjk has insufficient free disk for candidate evidence" >&2
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

run_python() {
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
    timeout 900 "$uv" run --python 3.14 python "$@"
}

stage=prerequisite
for input in "$prerequisite/final-evidence-sha256.txt" \
  "$prerequisite/run-status.txt" "$prerequisite/sequence-summary.json"; do
  if [[ -L "$input" || ! -s "$input" ]]; then
    echo "source-probe prerequisite file is missing, symbolic, or empty: $input" >&2
    exit 1
  fi
done
recreate_prerequisite_manifest \
  "$evidence/prerequisite-manifest-recreated.before.txt"
cmp "$prerequisite/final-evidence-sha256.txt" \
  "$evidence/prerequisite-manifest-recreated.before.txt"
(
  cd "$prerequisite"
  sha256sum -c final-evidence-sha256.txt
) >"$evidence/prerequisite-manifest-check.txt"
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
} >"$evidence/expected-prerequisite-status.txt"
cmp "$evidence/expected-prerequisite-status.txt" "$prerequisite/run-status.txt"
jq -e --arg prerequisite "$prerequisite" '
  .format_version == 1
  and .target_id == "bap"
  and .resource_id == "bap-dictionary"
  and .profile_id == "bap-Deva-NP"
  and .raw_input.records == 2040
  and .raw_input.bytes == 360086
  and .raw_input.sha256 == "a69917c00e7a8587f4a38458faf89c95fc9e5ac9cbe6cfb612383438bdf5ae12"
  and .evidence_root == $prerequisite
  and .focused_tests_verified == true
  and .double_parse_verified == true
  and .project_state_unchanged == true
  and .selections_remain_unselected == true
' "$prerequisite/sequence-summary.json" >/dev/null
prerequisite_manifest_sha256="$(sha256sum \
  "$prerequisite/final-evidence-sha256.txt" | awk '{print $1}')"
prerequisite_status_sha256="$(sha256sum \
  "$prerequisite/run-status.txt" | awk '{print $1}')"
prerequisite_summary_sha256="$(sha256sum \
  "$prerequisite/sequence-summary.json" | awk '{print $1}')"
sha256sum "$prerequisite/final-evidence-sha256.txt" \
  "$prerequisite/run-status.txt" "$prerequisite/sequence-summary.json" \
  >"$evidence/prerequisite-sha256.txt"
prerequisite_verified=1

stage=spec_and_pins
actual_raw_sha="$(sha256sum "$raw" | awk '{print $1}')"
actual_transliterator_sha="$(sha256sum "$transliterator" | awk '{print $1}')"
actual_adapter_sha="$(sha256sum "$adapter" | awk '{print $1}')"
actual_auditor_sha="$(sha256sum "$auditor" | awk '{print $1}')"
actual_compiler_sha="$(sha256sum "$compiler" | awk '{print $1}')"
actual_runtime_sha="$(sha256sum "$runtime" | awk '{print $1}')"
actual_layout_lock_sha="$(sha256sum "$layout_lock" | awk '{print $1}')"
layout_id="$(jq -r '.layout_id' "$spec")"
layout_source_sha="$(jq -r \
  --arg layout "$layout_id" \
  '.layouts[] | select(.layout_id == $layout) | .source.sha256' \
  "$layout_lock")"

jq -e '
  (keys | sort) == [
    "adapter_sha256", "auditor_sha256", "claim_scope", "compiler_sha256",
    "data_version", "expected_counts", "format_version", "inspection_vectors",
    "layout_audit_sha256", "layout_id", "layout_lock_sha256",
    "layout_source_sha256", "max_suggestions", "raw_sha256", "resource_id",
    "runtime_sha256", "target_id", "transliterator_resource_id",
    "transliterator_sha256"
  ]
  and .format_version == 1
  and .claim_scope == "candidate_only_generated_devanagari"
  and .target_id == "bap"
  and .resource_id == "bap-dictionary"
  and .transliterator_resource_id == "bap-romanizer"
  and .layout_id == "deva-nepal-dumi-v1"
  and (.data_version | test("^[0-9]+\\.[0-9]+\\.[0-9]+$"))
  and (.max_suggestions | type == "number" and floor == . and . >= 1 and . <= 32)
  and (.inspection_vectors | type == "array" and length >= 1 and length <= 64)
  and (all(.inspection_vectors[];
    type == "object"
    and (keys | sort) == ["expected_first_surface", "prefix"]
    and (.prefix | type == "string" and length > 0)
    and (.expected_first_surface | type == "string" and length > 0)
  ))
  and ([.inspection_vectors[].prefix] | length == (unique | length))
  and (.expected_counts == {
    accountable_lossy_roundtrip_rows: 347,
    candidate_surfaces: 1714,
    collision_surfaces_across_distinct_headwords: 78,
    distinct_input_headwords: 1792,
    duplicate_surfaces_merged: 326,
    exact_roundtrip_rows: 1693,
    non_nfc_input_headword_rows: 10,
    source_forms: 2040,
    sources_used: 2
  })
' "$spec" >/dev/null
[[ "$actual_raw_sha" == "$(jq -r '.raw_sha256' "$spec")" ]]
[[ "$actual_transliterator_sha" == "$(jq -r '.transliterator_sha256' "$spec")" ]]
[[ "$actual_adapter_sha" == "$(jq -r '.adapter_sha256' "$spec")" ]]
[[ "$actual_auditor_sha" == "$(jq -r '.auditor_sha256' "$spec")" ]]
[[ "$actual_compiler_sha" == "$(jq -r '.compiler_sha256' "$spec")" ]]
[[ "$actual_runtime_sha" == "$(jq -r '.runtime_sha256' "$spec")" ]]
[[ "$actual_layout_lock_sha" == "$(jq -r '.layout_lock_sha256' "$spec")" ]]
[[ "$layout_source_sha" == "$(jq -r '.layout_source_sha256' "$spec")" ]]
[[ "$(wc -c <"$raw" | awk '{print $1}')" == 360086 ]]
[[ "$(awk 'END {print NR}' "$raw")" == 2040 ]]
[[ "$(wc -c <"$transliterator" | awk '{print $1}')" == 14511 ]]

jq -e \
  --arg raw_sha "$actual_raw_sha" \
  --arg transliterator_sha "$actual_transliterator_sha" '
  [.packs[] | select(.id == "bap")] as $targets
  | ($targets | length) == 1
  and $targets[0].iso_639_3 == "bap"
  and ([$targets[0].input_methods[]
    | select(.id == "bap-deva-direct" and .readiness == "research")]
    | length) == 1
  and ([$targets[0].resources[]
    | select(.id == "bap-dictionary"
      and .records == 2040 and .bytes == 360086 and .sha256 == $raw_sha)]
    | length) == 1
  and ([$targets[0].resources[]
    | select(.id == "bap-romanizer"
      and .bytes == 14511 and .sha256 == $transliterator_sha)]
    | length) == 1
' "$catalog" >/dev/null
jq -e '
  [.profiles[] | select(.profile_id == "bap-Deva-NP")] as $profiles
  | ($profiles | length) == 1
  and $profiles[0].selectable == false
  and $profiles[0].layout_id == "pending-bap-deva-direct"
  and $profiles[0].pack_artifact == null
  and $profiles[0].pack_binding == null
' "$profile_lock" >/dev/null

cp "$spec" "$evidence/candidate-spec.json"
sha256sum "$raw" "$transliterator" "$catalog" "$profile_review" \
  "$profile_lock" "$layout_lock" "$android_pins" "$spec" "$adapter" \
  "$auditor" "$compiler" "$runtime" \
  "$repo/tests/test_bantawa_internal_source.py" \
  "$repo/tests/test_bantawa_candidate_layout.py" \
  "$repo/tests/test_bantawa_candidate_pack_runner.py" \
  "$repo/tools/run_cdjk_bantawa_candidate_pack.sh" \
  >"$evidence/input-source-sha256.txt"
sha256sum "$catalog" "$profile_review" "$profile_lock" "$layout_lock" \
  "$android_pins" >"$evidence/project-state.before.txt"

stage=focused_tests
cd "$repo"
{
  "$uv" --version
  run_python -VV
  uname -a
} >"$evidence/runtime-versions.txt" 2>&1
run_python -m unittest tests.test_bantawa_internal_source \
  tests.test_bantawa_candidate_layout tests.test_bantawa_candidate_pack_runner \
  >"$evidence/logs/focused-tests.txt" 2>&1
focused_tests_verified=1

stage=double_build
data_version="$(jq -r '.data_version' "$spec")"
max_suggestions="$(jq -r '.max_suggestions' "$spec")"
pack_id=bap-Deva-NP
for run in a b; do
  run_python tools/build_bantawa_internal_source.py \
    --dictionary-jsonl "$raw" \
    --transliterator-python "$transliterator" \
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

jq -e --slurpfile spec "$spec" --arg adapter_sha "$actual_adapter_sha" '
  .adapter_sha256 == $adapter_sha
  and .pack_id == "bap-Deva-NP"
  and .aliases.rows == 0
  and .conversion.transliterator_sha256 == $spec[0].transliterator_sha256
  and .measurement.stats.rows == $spec[0].expected_counts.source_forms
  and .measurement.stats.accepted_rows == $spec[0].expected_counts.source_forms
  and .measurement.stats.distinct_input_headwords
    == $spec[0].expected_counts.distinct_input_headwords
  and .measurement.stats.distinct_generated_surfaces
    == $spec[0].expected_counts.candidate_surfaces
  and .measurement.stats.duplicate_surface_rows
    == $spec[0].expected_counts.duplicate_surfaces_merged
  and .measurement.stats.exact_roundtrip_rows
    == $spec[0].expected_counts.exact_roundtrip_rows
  and .measurement.stats.accountable_lossy_roundtrip_rows
    == $spec[0].expected_counts.accountable_lossy_roundtrip_rows
  and .measurement.stats.non_nfc_input_headword_rows
    == $spec[0].expected_counts.non_nfc_input_headword_rows
  and .measurement.stats.collision_surfaces_across_distinct_headwords
    == $spec[0].expected_counts.collision_surfaces_across_distinct_headwords
' "$evidence/a/source/adapter-report.json" >/dev/null
jq -e --slurpfile spec "$spec" '
  .manifest.pack.pack_id == "bap-Deva-NP"
  and .manifest.pack.language == "bap"
  and .manifest.pack.output_script == "Deva"
  and .manifest.pack.data_version == $spec[0].data_version
  and .manifest.pack.max_suggestions == $spec[0].max_suggestions
  and .manifest.release_mode == "internal"
  and .manifest.counts.source_forms == $spec[0].expected_counts.source_forms
  and .manifest.counts.candidate_surfaces
    == $spec[0].expected_counts.candidate_surfaces
  and .manifest.counts.duplicate_surfaces_merged
    == $spec[0].expected_counts.duplicate_surfaces_merged
  and .manifest.counts.sources_used == $spec[0].expected_counts.sources_used
  and .manifest.counts.alias_rows == 0
  and .manifest.counts.alias_keys == 0
  and .manifest.counts.alias_collisions == 0
  and .manifest.indexes.surface.keys == $spec[0].expected_counts.candidate_surfaces
  and .manifest.indexes.aliases.keys == 0
' "$evidence/a/$pack_id.nkp.report.json" >/dev/null
set +e
run_python -m nepa_keyboard.compiler build \
  --input "$evidence/a/source" \
  --output "$evidence/must-not-release.nkp" \
  --mode release \
  >"$evidence/logs/release-negative.stdout.txt" \
  2>"$evidence/logs/release-negative.stderr.txt"
release_status=$?
set -e
printf 'release_negative_exit_status=%s\n' "$release_status" \
  >"$evidence/release-negative-status.txt"
if (( release_status == 0 )) || [[ -e "$evidence/must-not-release.nkp" ]]; then
  echo "internal Bantawa source unexpectedly passed the release gate" >&2
  exit 1
fi
pack_sha256="$(sha256sum "$evidence/a/$pack_id.nkp" | awk '{print $1}')"
pack_bytes="$(stat -c '%s' "$evidence/a/$pack_id.nkp")"
sha256sum "$evidence/a/$pack_id.nkp" "$evidence/b/$pack_id.nkp" \
  "$evidence/a/$pack_id.nkp.report.json" \
  "$evidence/b/$pack_id.nkp.report.json" >"$evidence/pack-sha256.txt"
double_build_verified=1

stage=layout_audit
for run in a b; do
  run_python tools/audit_bantawa_candidate_layout.py \
    --forms-jsonl "$evidence/$run/source/forms.jsonl" \
    --layout-lock "$layout_lock" \
    --layout-id "$layout_id" \
    --output "$evidence/$run/layout-audit.json" \
    >"$evidence/logs/$run.layout-audit.stdout.json" \
    2>"$evidence/logs/$run.layout-audit.stderr.txt"
done
cmp "$evidence/a/layout-audit.json" "$evidence/b/layout-audit.json"
layout_audit_sha256="$(sha256sum "$evidence/a/layout-audit.json" | awk '{print $1}')"
[[ "$layout_audit_sha256" == "$(jq -r '.layout_audit_sha256' "$spec")" ]]
jq -e --slurpfile spec "$spec" '
  .status == "passed"
  and .forms.rows == $spec[0].expected_counts.source_forms
  and .forms.distinct_surfaces == $spec[0].expected_counts.candidate_surfaces
  and .layout.layout_id == $spec[0].layout_id
  and .layout.layout_lock_sha256 == $spec[0].layout_lock_sha256
  and .layout.source_sha256 == $spec[0].layout_source_sha256
  and .unsupported_scalars == []
' "$evidence/a/layout-audit.json" >/dev/null
run_python tools/audit_bantawa_candidate_layout.py \
  --forms-jsonl "$evidence/a/source/forms.jsonl" \
  --layout-lock "$layout_lock" \
  --layout-id "$layout_id" \
  --output "$evidence/a/layout-audit.json" \
  --check >"$evidence/logs/layout-audit-check.stdout.json" \
  2>"$evidence/logs/layout-audit-check.stderr.txt"
layout_audit_verified=1

stage=inspection
jq -c '.inspection_vectors[]' "$spec" >"$evidence/inspection-vectors.jsonl"
: >"$evidence/inspection-summary.jsonl"
inspect_count=0
while IFS= read -r vector; do
  prefix="$(jq -r '.prefix' <<<"$vector")"
  expected="$(jq -r '.expected_first_surface' <<<"$vector")"
  label="$(printf '%03d' "$inspect_count")"
  for run in a b; do
    run_python -m nepa_keyboard.compiler inspect \
      --pack "$evidence/$run/$pack_id.nkp" \
      --index surface --prefix="$prefix" \
      >"$evidence/inspections/$label.$run.json" \
      2>"$evidence/logs/$label.$run.inspect.stderr.txt"
  done
  cmp "$evidence/inspections/$label.a.json" \
    "$evidence/inspections/$label.b.json"
  jq -e --arg prefix "$prefix" --arg expected "$expected" \
    --argjson maximum "$max_suggestions" '
    .index == "surface"
    and .prefix == $prefix
    and (.candidates | type == "array" and length >= 1 and length <= $maximum)
    and .candidates[0].surface == $expected
  ' "$evidence/inspections/$label.a.json" >/dev/null
  jq -c --arg expected "$expected" --argjson index "$inspect_count" '
    {
      candidate_count: (.candidates | length),
      expected_first_surface: $expected,
      index: $index,
      prefix: .prefix,
      top_surfaces: [.candidates[].surface]
    }
  ' "$evidence/inspections/$label.a.json" >>"$evidence/inspection-summary.jsonl"
  inspect_count=$((inspect_count + 1))
done <"$evidence/inspection-vectors.jsonl"
[[ "$inspect_count" == "$(jq -r '.inspection_vectors | length' "$spec")" ]]
inspection_verified=1

stage=state_and_prerequisite_recheck
sha256sum "$catalog" "$profile_review" "$profile_lock" "$layout_lock" \
  "$android_pins" >"$evidence/project-state.after.txt"
cmp "$evidence/project-state.before.txt" "$evidence/project-state.after.txt"
state_unchanged=1
recreate_prerequisite_manifest \
  "$evidence/prerequisite-manifest-recreated.after.txt"
cmp "$prerequisite/final-evidence-sha256.txt" \
  "$evidence/prerequisite-manifest-recreated.after.txt"
(
  cd "$prerequisite"
  sha256sum -c final-evidence-sha256.txt
) >"$evidence/prerequisite-manifest-recheck.txt"
if [[ "$(sha256sum "$prerequisite/final-evidence-sha256.txt" | awk '{print $1}')" \
        != "$prerequisite_manifest_sha256"
      || "$(sha256sum "$prerequisite/run-status.txt" | awk '{print $1}')" \
        != "$prerequisite_status_sha256"
      || "$(sha256sum "$prerequisite/sequence-summary.json" | awk '{print $1}')" \
        != "$prerequisite_summary_sha256" ]]; then
  echo "Bantawa source-probe prerequisite changed during candidate construction" >&2
  exit 1
fi

stage=sequence_summary
jq -S -n \
  --arg evidence "$evidence" \
  --arg prerequisite "$prerequisite" \
  --arg prerequisite_manifest_sha256 "$prerequisite_manifest_sha256" \
  --arg prerequisite_status_sha256 "$prerequisite_status_sha256" \
  --arg prerequisite_summary_sha256 "$prerequisite_summary_sha256" \
  --arg raw "$raw" --arg raw_sha256 "$actual_raw_sha" \
  --arg transliterator "$transliterator" \
  --arg transliterator_sha256 "$actual_transliterator_sha" \
  --arg pack "$evidence/a/$pack_id.nkp" --arg pack_sha256 "$pack_sha256" \
  --arg layout_id "$layout_id" --arg layout_audit_sha256 "$layout_audit_sha256" \
  --argjson pack_bytes "$pack_bytes" \
  --slurpfile counts <(jq '.expected_counts' "$spec") '
  {
    format_version: 1,
    claim_scope: (
      "Deterministic internal generated-Devanagari Bantawa candidate pack only; "
      + "native spelling, ranking quality, casual Roman input, dedicated layout, "
      + "profile promotion, Android runtime, and production approval remain open."
    ),
    target_id: "bap",
    resource_id: "bap-dictionary",
    transliterator_resource_id: "bap-romanizer",
    profile_id: "bap-Deva-NP",
    evidence_root: $evidence,
    source_probe_prerequisite: {
      verified: true,
      evidence_root: $prerequisite,
      final_manifest_sha256: $prerequisite_manifest_sha256,
      run_status_sha256: $prerequisite_status_sha256,
      sequence_summary_sha256: $prerequisite_summary_sha256
    },
    raw_input: {path: $raw, sha256: $raw_sha256, records: 2040, bytes: 360086},
    transliterator_input: {
      path: $transliterator, sha256: $transliterator_sha256, bytes: 14511
    },
    generated_candidates: $counts[0],
    pack: {path: $pack, sha256: $pack_sha256, bytes: $pack_bytes},
    layout_measurement: {
      layout_id: $layout_id,
      audit_sha256: $layout_audit_sha256,
      scalar_reachability_passed: true,
      production_layout_selected: false
    },
    focused_tests_verified: true,
    double_build_verified: true,
    release_gate_negative_verified: true,
    inspection_verified: true,
    project_state_unchanged: true,
    profile_promoted: false
  }
' >"$evidence/sequence-summary.json"
jq -e --arg evidence "$evidence" --arg pack_sha256 "$pack_sha256" \
  --arg layout_audit_sha256 "$layout_audit_sha256" '
  .format_version == 1
  and .target_id == "bap"
  and .evidence_root == $evidence
  and .source_probe_prerequisite.verified == true
  and .pack.sha256 == $pack_sha256
  and .generated_candidates.source_forms == 2040
  and .generated_candidates.candidate_surfaces == 1714
  and .generated_candidates.exact_roundtrip_rows == 1693
  and .generated_candidates.accountable_lossy_roundtrip_rows == 347
  and .layout_measurement.audit_sha256 == $layout_audit_sha256
  and .layout_measurement.scalar_reachability_passed == true
  and .layout_measurement.production_layout_selected == false
  and .focused_tests_verified == true
  and .double_build_verified == true
  and .release_gate_negative_verified == true
  and .inspection_verified == true
  and .project_state_unchanged == true
  and .profile_promoted == false
' "$evidence/sequence-summary.json" >/dev/null
sequence_complete=1
stage=complete
