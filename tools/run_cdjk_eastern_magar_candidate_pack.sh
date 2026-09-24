#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 2 || "$1" != /* || "$2" != /* ]]; then
  echo "usage: $0 /absolute/repository /absolute/new/candidate-directory" >&2
  exit 2
fi

repo="$1"
work="$2"
raw="$work/mgp-npi.tsv"
adapter="$work/build_eastern_magar_candidate_source.py"
queries="$work/eastern-magar-candidate-prefix-v0.jsonl"
python="$repo/.venv/bin/python"
expected_raw=3df7a496e56bb7cef17c7f6462224546d4cbe1d0ca4747cff81783da1366a7ae
expected_adapter=eaeb4f378f459fd447dc2a9a4f6ee42e27f69fe306f62c64168de259347d218d
expected_queries=71f483d3905ec300762aaf596ee9ead241cba2955e5da46780b8231b2b4b07d0

if [[ "$(uname -s)" != Linux || "$(hostname -s)" != cdjk ]]; then
  echo "the candidate build requires cdjk Ubuntu" >&2
  exit 1
fi
if [[ ! -f "$repo/src/nepa_keyboard/compiler.py" || ! -x "$python"
      || ! -f "$raw" || ! -f "$adapter" || ! -f "$queries"
      || -e "$work/a" || -e "$work/b" ]]; then
  echo "missing input or candidate output already exists" >&2
  exit 1
fi
printf '%s  %s\n' "$expected_raw" "$raw" \
  "$expected_adapter" "$adapter" \
  "$expected_queries" "$queries" | sha256sum -c -

available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
disk_kib="$(df -Pk "$work" | awk 'NR == 2 {print $4}')"
if (( available_kib < 8 * 1024 * 1024 || disk_kib < 4 * 1024 * 1024 )); then
  echo "insufficient host memory or disk" >&2
  exit 1
fi
exec 9>/tmp/nepa-keyboard-android-validation.lock
flock -n 9 || { echo "another Nepa validation owns the lock" >&2; exit 1; }
{
  hostname
  uptime
  free -h
  df -h "$work"
  ps -eo pid,comm,rss,%cpu --sort=-rss | sed -n '1,16p'
} >"$work/host-preflight.txt"

run_python() {
  (
    ulimit -v 2097152
    cd "$repo"
    nice -n 10 env PYTHONPATH="$repo/src:$repo" timeout 60 \
      "$python" "$@"
  )
}

for run in a b; do
  mkdir -p "$work/$run/source"
  run_python "$adapter" \
    --induced-tsv "$raw" \
    --output "$work/$run/source" \
    --data-version 1.0.0 \
    --max-suggestions 8 \
    >"$work/$run/adapter-stdout.json" \
    2>"$work/$run/adapter-stderr.txt"
  run_python -m nepa_keyboard.compiler build \
    --input "$work/$run/source" \
    --output "$work/$run/mgp-Deva-NP.nkp" \
    --mode internal \
    >"$work/$run/compiler-stdout.json" \
    2>"$work/$run/compiler-stderr.txt"
  unzip -t "$work/$run/mgp-Deva-NP.nkp" \
    >"$work/$run/pack-integrity.txt"
done

diff -qr "$work/a/source" "$work/b/source" >"$work/source-diff.txt"
cmp "$work/a/mgp-Deva-NP.nkp" "$work/b/mgp-Deva-NP.nkp"
sha256sum "$work/a/mgp-Deva-NP.nkp" "$work/b/mgp-Deva-NP.nkp" \
  >"$work/pack-sha256.txt"
run_python "$repo/tools/validate_pack_queries.py" \
  --queries "$queries" \
  --pack "mgp-Deva-NP=$work/a/mgp-Deva-NP.nkp" \
  >"$work/prefix-validation.json"
jq -e '.status == "ok" and .counts.total == 6 and .counts.failed == 0' \
  "$work/prefix-validation.json" >/dev/null
{
  sha256sum "$raw" "$adapter" "$queries" \
    "$repo/src/nepa_keyboard/compiler.py" \
    "$repo/tools/validate_pack_queries.py" \
    "$work/run_cdjk_eastern_magar_candidate_pack.sh"
  sha256sum "$work/a/source/adapter-report.json"
} >"$work/input-and-report-sha256.txt"
printf 'source_trees_identical=true\npacks_identical=true\nprefix_cases=6\nprefix_failed=0\n' \
  >"$work/run-status.txt"
(
  cd "$work"
  LC_ALL=C find . -type f ! -name final-evidence-sha256.txt -print0 \
    | LC_ALL=C sort -z | xargs -0 sha256sum
) >"$work/final-evidence-sha256.txt"
cat "$work/a/source/adapter-report.json"
cat "$work/pack-sha256.txt"
