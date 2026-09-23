#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 2 || "$1" != /* || "$2" != /* ]]; then
  echo "usage: $0 /absolute/repository /absolute/new/candidate-directory" >&2
  exit 2
fi

repo="$1"
work="$2"
raw="$work/thq_nep_lexicon.tsv"
adapter="$work/build_mid_eastern_tharu_internal_source.py"
queries="$work/tharu-candidate-prefix-v0.jsonl"
python="$repo/.venv/bin/python"
expected_raw=575ecfa0b2cbcafe3c4b8783e302f0af5c5a3c7a321b75a61b8bd1fe802d39c5
expected_adapter=b536479971eb99a00254dd4eb2ccdd9e5cd141f0837963764c41b4b7da627180
expected_queries=e70a5b3c9129023e387f6d93d51a2fc78e6f06359721fe523dea66f190b445b0

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
    --apk-tsv "$raw" \
    --output "$work/$run/source" \
    --data-version 1.0.0 \
    --max-suggestions 8 \
    >"$work/$run/adapter-stdout.json" \
    2>"$work/$run/adapter-stderr.txt"
  run_python -m nepa_keyboard.compiler build \
    --input "$work/$run/source" \
    --output "$work/$run/thq-Deva-NP.nkp" \
    --mode internal \
    >"$work/$run/compiler-stdout.json" \
    2>"$work/$run/compiler-stderr.txt"
  unzip -t "$work/$run/thq-Deva-NP.nkp" \
    >"$work/$run/pack-integrity.txt"
done

diff -qr "$work/a/source" "$work/b/source" >"$work/source-diff.txt"
cmp "$work/a/thq-Deva-NP.nkp" "$work/b/thq-Deva-NP.nkp"
sha256sum "$work/a/thq-Deva-NP.nkp" "$work/b/thq-Deva-NP.nkp" \
  >"$work/pack-sha256.txt"
run_python "$repo/tools/validate_pack_queries.py" \
  --queries "$queries" \
  --pack "thq-Deva-NP=$work/a/thq-Deva-NP.nkp" \
  >"$work/prefix-validation.json"
jq -e '.status == "ok" and .counts.total == 6 and .counts.failed == 0' \
  "$work/prefix-validation.json" >/dev/null
{
  sha256sum "$raw" "$adapter" "$queries" \
    "$repo/src/nepa_keyboard/compiler.py" \
    "$repo/tools/validate_pack_queries.py" \
    "$work/run_cdjk_mid_eastern_tharu_candidate_pack.sh"
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
