#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

if [[ $# -ne 1 || "$1" != /* ]]; then
  echo "usage: $0 /absolute/new/evidence-directory" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence="$1"
uv="$HOME/.local/bin/uv"
raw=/home/cdjk/github/llm/rai-speech-toolkit/dialects/eastern/yakkha/dict/nepali-yakkha.sil-apk.dict.jsonl
spec="$repo/catalog/internal-pack-milestones/ybh-Deva-NP-v0.json"
catalog="$repo/catalog/resources.json"
milestone_evidence="$repo/reports/yakkha-internal-pack-v0.json"
review="$repo/catalog/internal-profile-review.json"
queries="$repo/catalog/yakkha-internal-prefixes-v0.json"
stage=initializing

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != "cdjk"
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this Yakkha refresh must run from the cdjk Ubuntu checkout" >&2
  exit 1
fi
if ! command -v realpath >/dev/null; then
  echo "realpath is required for evidence-path containment checks" >&2
  exit 1
fi
evidence="$(realpath -m -- "$evidence")"
if [[ "$evidence" == "$repo" || "$evidence" == "$repo/"* ]]; then
  echo "evidence directory must be outside the source checkout: $evidence" >&2
  exit 1
fi
if [[ -e "$evidence" ]]; then
  echo "evidence directory already exists: $evidence" >&2
  exit 1
fi
mkdir -p "$evidence/a" "$evidence/b" "$evidence/vectors"

write_evidence_manifest() {
  local temporary_manifest="$evidence/.final-evidence-sha256.txt.tmp"
  rm -f "$temporary_manifest"
  (
    cd "$evidence"
    LC_ALL=C find . -type f \
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

write_status() {
  local test_status="$1"
  local manifest_status="$2"
  local final_status="$3"
  {
    printf 'completed_stage=%s\n' "$stage"
    printf 'test_exit_status=%s\n' "$test_status"
    printf 'manifest_exit_status=%s\n' "$manifest_status"
    printf 'remote_exit_status=%s\n' "$final_status"
  } >"$evidence/run-status.txt"
}

on_exit() {
  local test_status=$?
  trap - EXIT
  set +e
  local final_status=$test_status
  local manifest_status=0
  write_status "$test_status" 0 "$final_status" || final_status=1
  write_evidence_manifest || manifest_status=$?
  if (( manifest_status != 0 )); then
    final_status=1
    write_status "$test_status" "$manifest_status" "$final_status" || true
    # Preserve a content-bound failure record when a second bounded manifest
    # attempt is possible. run-status retains the first nonzero manifest code.
    write_evidence_manifest || true
  fi
  if (( final_status == 0 )); then
    printf 'yakkha_refresh_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

stage=preflight
for required in awk basename cmp df diff find flock free grep hostname jq mkdir \
  mv pgrep ps realpath rm sed sha256sum sort stat timeout tr uname unzip uptime \
  wc xargs "$uv"; do
  if [[ "$required" == /* ]]; then
    [[ -x "$required" ]]
  else
    command -v "$required" >/dev/null
  fi
done
for source in \
  "$spec" \
  "$catalog" \
  "$milestone_evidence" \
  "$review" \
  "$queries" \
  "$repo/tools/build_yakkha_internal_source.py" \
  "$repo/tools/sil_apk_jsonl_internal_source.py" \
  "$repo/tools/finalize_internal_pack_milestone_v1.py" \
  "$repo/tools/run_cdjk_yakkha_refresh.sh" \
  "$repo/src/nepa_keyboard/compiler.py"; do
  [[ -s "$source" && ! -L "$source" ]]
done

exec 9>/tmp/nepa-keyboard-android-validation.lock
if ! flock -n 9; then
  echo "another Nepa validation owns the cdjk lock" >&2
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

available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
evidence_available_kib="$(df -Pk "$evidence" | awk 'NR == 2 {print $4}')"
tmp_available_kib="$(df -Pk /tmp | awk 'NR == 2 {print $4}')"
if [[ ! "$available_kib" =~ ^[0-9]+$ \
      || "$available_kib" -lt $((8 * 1024 * 1024)) ]]; then
  echo "cdjk has less than 8 GiB available memory" >&2
  exit 1
fi
if [[ ! "$evidence_available_kib" =~ ^[0-9]+$ \
      || ! "$tmp_available_kib" =~ ^[0-9]+$ \
      || "$evidence_available_kib" -lt $((2 * 1024 * 1024)) \
      || "$tmp_available_kib" -lt $((1024 * 1024)) ]]; then
  echo "cdjk has insufficient free disk for the Yakkha refresh" >&2
  exit 1
fi
{
  hostname
  uptime
  free -h
  df -h "$evidence" /tmp
  ps -eo pid,comm,%cpu,%mem,rss --sort=-rss | sed -n '1,20p'
} >"$evidence/host-preflight.txt"

stage=raw_identity
expected_resource_count="$(
  jq -r '[.packs[] | select(.id == "ybh") | .resources[]
    | select(.id == "ybh-apk")] | length' "$catalog"
)"
[[ "$expected_resource_count" == 1 ]]
jq --slurpfile spec "$spec" '
  ([.packs[] | select(.id == "ybh") | .resources[]
    | select(.id == "ybh-apk")][0]) as $resource
  | ($spec[0].source) as $source
  | if (
      $resource.id == $source.resource_id
      and ($resource.path | endswith("/" + $source.file_name))
      and $resource.records == $source.expected_data_rows
      and $resource.sha256 == $source.sha256
      and (($resource.bytes | type) == "number" and $resource.bytes > 0)
    ) then {
      catalog: {
        bytes: $resource.bytes,
        path: $resource.path,
        records: $resource.records,
        resource_id: $resource.id,
        sha256: $resource.sha256
      },
      milestone: $source
    } else error("Yakkha catalog and milestone source metadata disagree") end
' "$catalog" >"$evidence/pinned-raw-metadata.json"

expected_file_name="$(jq -r '.milestone.file_name' "$evidence/pinned-raw-metadata.json")"
expected_records="$(jq -r '.milestone.expected_data_rows' "$evidence/pinned-raw-metadata.json")"
expected_bytes="$(jq -r '.catalog.bytes' "$evidence/pinned-raw-metadata.json")"
expected_raw_sha="$(jq -r '.milestone.sha256' "$evidence/pinned-raw-metadata.json")"
[[ "$(basename "$raw")" == "$expected_file_name" ]]
[[ -f "$raw" && ! -L "$raw" && "$(realpath -- "$raw")" == "$raw" ]]
actual_records="$(wc -l <"$raw" | tr -d '[:space:]')"
actual_bytes="$(stat -c '%s' "$raw")"
actual_raw_sha="$(sha256sum "$raw" | awk '{print $1}')"
[[ "$actual_records" == "$expected_records" ]]
[[ "$actual_bytes" == "$expected_bytes" ]]
[[ "$actual_raw_sha" == "$expected_raw_sha" ]]
{
  printf 'path=%s\n' "$raw"
  printf 'records=%s\n' "$actual_records"
  printf 'bytes=%s\n' "$actual_bytes"
  printf 'sha256=%s\n' "$actual_raw_sha"
} >"$evidence/raw-identity.txt"
sha256sum \
  "$spec" \
  "$catalog" \
  "$milestone_evidence" \
  "$review" \
  "$queries" \
  "$repo/tools/build_yakkha_internal_source.py" \
  "$repo/tools/sil_apk_jsonl_internal_source.py" \
  "$repo/tools/finalize_internal_pack_milestone_v1.py" \
  "$repo/tools/run_cdjk_yakkha_refresh.sh" \
  "$repo/src/nepa_keyboard/compiler.py" \
  >"$evidence/input-source-sha256.txt"

run_python() {
  PYTHONPATH=src:. timeout 1200 "$uv" run --python 3.14 python "$@"
}

stage=double_build
cd "$repo"
{
  "$uv" --version
  run_python -VV
  uname -a
} >"$evidence/runtime-versions.txt" 2>&1
for run in a b; do
  run_python tools/build_yakkha_internal_source.py \
    --sil-apk-jsonl "$raw" \
    --output "$evidence/$run/source" \
    >"$evidence/$run/adapter-stdout.json" \
    2>"$evidence/$run/adapter-stderr.txt"
  run_python -m nepa_keyboard.compiler build \
    --input "$evidence/$run/source" \
    --output "$evidence/$run/ybh-Deva-NP.nkp" \
    --mode internal \
    >"$evidence/$run/compiler-stdout.json" \
    2>"$evidence/$run/compiler-stderr.txt"
  jq -S 'del(.artifact)' "$evidence/$run/ybh-Deva-NP.nkp.report.json" \
    >"$evidence/$run/compiler-report.normalized.json"
  (
    cd "$evidence/$run/source"
    LC_ALL=C find . -maxdepth 1 -type f -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 sha256sum
  ) >"$evidence/$run/source-sha256.txt"
done
diff -qr "$evidence/a/source" "$evidence/b/source" \
  >"$evidence/source-tree-diff.txt"
cmp "$evidence/a/adapter-stdout.json" "$evidence/b/adapter-stdout.json"
cmp "$evidence/a/source-sha256.txt" "$evidence/b/source-sha256.txt"
cmp "$evidence/a/compiler-report.normalized.json" \
  "$evidence/b/compiler-report.normalized.json"
cmp "$evidence/a/ybh-Deva-NP.nkp" "$evidence/b/ybh-Deva-NP.nkp"

stage=pack_evidence
jq -e --slurpfile evidence "$milestone_evidence" '
  .stats.rows == $evidence[0].raw_source.records
  and .stats.accepted_rows == $evidence[0].source.accepted_rows
  and .stats.rejected_rows == $evidence[0].source.rejected_rows
  and .stats.distinct_accepted_surfaces
    == $evidence[0].source.distinct_accepted_surfaces
' "$evidence/a/source/adapter-report.json" >/dev/null
jq -e --slurpfile evidence "$milestone_evidence" '
  .artifact_sha256 == $evidence[0].pack.artifact_sha256
  and .artifact_bytes == $evidence[0].pack.artifact_bytes
  and .manifest.pack.pack_id == $evidence[0].pack.pack_id
  and .manifest.pack.language == $evidence[0].pack.language
  and .manifest.pack.output_script == $evidence[0].pack.output_script
  and .manifest.release_mode == $evidence[0].pack.release_mode
  and .manifest.counts.source_forms == $evidence[0].pack.source_form_count
  and .manifest.counts.candidate_surfaces == $evidence[0].pack.candidate_count
  and .manifest.indexes.surface.keys == $evidence[0].pack.surface_key_count
  and .manifest.indexes.aliases.keys == $evidence[0].pack.alias_key_count
' "$evidence/a/ybh-Deva-NP.nkp.report.json" >/dev/null
expected_pack_sha="$(jq -r '.pack.artifact_sha256' "$milestone_evidence")"
expected_pack_bytes="$(jq -r '.pack.artifact_bytes' "$milestone_evidence")"
actual_pack_sha="$(sha256sum "$evidence/a/ybh-Deva-NP.nkp" | awk '{print $1}')"
actual_pack_bytes="$(stat -c '%s' "$evidence/a/ybh-Deva-NP.nkp")"
[[ "$actual_pack_sha" == "$expected_pack_sha" ]]
[[ "$actual_pack_bytes" == "$expected_pack_bytes" ]]
sha256sum \
  "$evidence/a/ybh-Deva-NP.nkp" \
  "$evidence/b/ybh-Deva-NP.nkp" \
  "$evidence/a/ybh-Deva-NP.nkp.report.json" \
  "$evidence/b/ybh-Deva-NP.nkp.report.json" \
  >"$evidence/pack-sha256.txt"

stage=finalizer_check
sha256sum "$milestone_evidence" "$review" \
  >"$evidence/source-controlled-before-finalizer.txt"
reviewed_at="$(jq -r '.reviewed_at' "$milestone_evidence")"
run_python tools/finalize_internal_pack_milestone_v1.py \
  --spec "$spec" \
  --raw-input "$raw" \
  --source-a "$evidence/a/source" \
  --source-b "$evidence/b/source" \
  --pack-a "$evidence/a/ybh-Deva-NP.nkp" \
  --pack-b "$evidence/b/ybh-Deva-NP.nkp" \
  --review-input "$review" \
  --review-output "$review" \
  --evidence-output "$milestone_evidence" \
  --reviewed-at "$reviewed_at" \
  --check \
  >"$evidence/finalizer-check.json" \
  2>"$evidence/finalizer-check.stderr.txt"
sha256sum "$milestone_evidence" "$review" \
  >"$evidence/source-controlled-after-finalizer.txt"
cmp "$evidence/source-controlled-before-finalizer.txt" \
  "$evidence/source-controlled-after-finalizer.txt"
expected_evidence_sha="$(sha256sum "$milestone_evidence" | awk '{print $1}')"
expected_review_sha="$(sha256sum "$review" | awk '{print $1}')"
jq -e \
  --arg evidence_path "$milestone_evidence" \
  --arg evidence_sha "$expected_evidence_sha" \
  --arg review_path "$review" \
  --arg review_sha "$expected_review_sha" '
  .evidence_output == $evidence_path
  and .evidence_sha256 == $evidence_sha
  and .review_output == $review_path
  and .review_sha256 == $review_sha
' "$evidence/finalizer-check.json" >/dev/null

stage=vector_checks
jq -c '.queries.validation, .queries.benchmark[]' "$milestone_evidence" \
  >"$evidence/expected-vectors.jsonl"
: >"$evidence/verified-vectors.jsonl"
vector_index=0
while IFS= read -r expected_vector; do
  query="$(jq -r '.query' <<<"$expected_vector")"
  vector_label="$(printf '%02d' "$vector_index")"
  run_python -m nepa_keyboard.compiler inspect \
    --pack "$evidence/a/ybh-Deva-NP.nkp" \
    --index surface \
    --prefix "$query" \
    >"$evidence/vectors/$vector_label.inspect.json" \
    2>"$evidence/vectors/$vector_label.inspect.stderr.txt"
  jq -S . <<<"$expected_vector" \
    >"$evidence/vectors/$vector_label.expected.json"
  jq -S '{
    expected_surface: .candidates[0].surface,
    query: .prefix,
    returned_candidate_count: (.candidates | length),
    top_surfaces: [.candidates[].surface]
  }' "$evidence/vectors/$vector_label.inspect.json" \
    >"$evidence/vectors/$vector_label.actual.json"
  cmp "$evidence/vectors/$vector_label.expected.json" \
    "$evidence/vectors/$vector_label.actual.json"
  jq -c . "$evidence/vectors/$vector_label.actual.json" \
    >>"$evidence/verified-vectors.jsonl"
  vector_index=$((vector_index + 1))
done <"$evidence/expected-vectors.jsonl"
expected_vector_count="$(
  jq -r '1 + (.queries.benchmark | length)' "$milestone_evidence"
)"
[[ "$vector_index" == "$expected_vector_count" ]]

stage=complete
jq -n \
  --arg pack_sha256 "$actual_pack_sha" \
  --argjson pack_bytes "$actual_pack_bytes" \
  --argjson raw_records "$actual_records" \
  --arg raw_sha256 "$actual_raw_sha" \
  --argjson vector_count "$vector_index" \
  '{
    pack_bytes: $pack_bytes,
    pack_sha256: $pack_sha256,
    raw_records: $raw_records,
    raw_sha256: $raw_sha256,
    status: "ok",
    vector_count: $vector_count
  }' >"$evidence/refresh-summary.json"

exit 0
