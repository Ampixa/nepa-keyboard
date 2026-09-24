#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 3 || "$1" != /* || "$2" != /* || "$3" != /* ]]; then
  echo "usage: $0 /absolute/repository /absolute/source-root /absolute/new/evidence-directory" >&2
  exit 2
fi

repo="$1"
source_root="$2"
work="$3"
python="$repo/.venv/bin/python"
adapter="$repo/tools/build_sherpa_candidate_source.py"
queries="$repo/validation/sherpa-candidate-prefix-v0.jsonl"
expected_manifest=9924c7c640129bdb486c11e634b790b43470a8af2dacac39709c9aa06e8a6dfe
expected_adapter=e8348a03e57d540cbdc6b49fbf2c0949075e7eb6c634f2d43e84de8cfa17e9e2
expected_queries=b12187fd095d46fa5f79875eb17aeb5d8ed36787b2145eb675da4b018b9f8b82

if [[ "$(uname -s)" != Linux || "$(hostname -s)" != cdjk ]]; then
  echo "the Sherpa candidate build requires cdjk Ubuntu" >&2
  exit 1
fi
if [[ ! -x "$python" || ! -f "$repo/src/nepa_keyboard/compiler.py"
      || ! -f "$adapter" || ! -f "$queries"
      || ! -d "$source_root/text/XSRWBT"
      || ! -f "$source_root/metadata/text_manifest.jsonl"
      || -e "$work" ]]; then
  echo "missing input or evidence directory already exists" >&2
  exit 1
fi
printf '%s  %s\n' "$expected_manifest" "$source_root/metadata/text_manifest.jsonl" \
  "$expected_adapter" "$adapter" \
  "$expected_queries" "$queries" | sha256sum -c -

available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
disk_kib="$(df -Pk "$source_root" | awk 'NR == 2 {print $4}')"
if (( available_kib < 8 * 1024 * 1024 || disk_kib < 4 * 1024 * 1024 )); then
  echo "insufficient host memory or disk" >&2
  exit 1
fi
exec 9>/tmp/nepa-keyboard-android-validation.lock
flock -n 9 || { echo "another Nepa validation owns the lock" >&2; exit 1; }
mkdir -p "$work/a/source" "$work/b/source" "$work/source-metadata"
{
  hostname
  uptime
  free -h
  df -h "$work"
  nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader
  ps -eo pid,comm,rss,%cpu --sort=-rss | sed -n '1,16p'
} >"$work/host-preflight.txt"
cp "$source_root/metadata/text_manifest.jsonl" "$work/source-metadata/"
cp "$source_root/metadata/bible.json" "$work/source-metadata/"
(
  cd "$source_root"
  LC_ALL=C find text/XSRWBT -type f -name '*.json' -print0 \
    | LC_ALL=C sort -z | xargs -0 sha256sum
) >"$work/source-files-sha256.txt"

run_python() {
  (
    ulimit -v 2097152
    cd "$repo"
    nice -n 10 env PYTHONPATH="$repo/src:$repo" timeout 60 "$python" "$@"
  )
}

for run in a b; do
  run_python "$adapter" \
    --source-root "$source_root" \
    --output "$work/$run/source" \
    --data-version 1.0.0 \
    --max-suggestions 8 \
    >"$work/$run/adapter-stdout.json" \
    2>"$work/$run/adapter-stderr.txt"
  run_python -m nepa_keyboard.compiler build \
    --input "$work/$run/source" \
    --output "$work/$run/xsr-Deva-NP.nkp" \
    --mode internal \
    >"$work/$run/compiler-stdout.json" \
    2>"$work/$run/compiler-stderr.txt"
  unzip -t "$work/$run/xsr-Deva-NP.nkp" \
    >"$work/$run/pack-integrity.txt"
done

diff -qr "$work/a/source" "$work/b/source" >"$work/source-diff.txt"
cmp "$work/a/xsr-Deva-NP.nkp" "$work/b/xsr-Deva-NP.nkp"
sha256sum "$work/a/xsr-Deva-NP.nkp" "$work/b/xsr-Deva-NP.nkp" \
  >"$work/pack-sha256.txt"
run_python "$repo/tools/validate_pack_queries.py" \
  --queries "$queries" \
  --pack "xsr-Deva-NP=$work/a/xsr-Deva-NP.nkp" \
  >"$work/prefix-validation.json"
jq -e '.status == "ok" and .counts.total == 6 and .counts.failed == 0' \
  "$work/prefix-validation.json" >/dev/null
{
  sha256sum "$adapter" "$queries" "$repo/src/nepa_keyboard/compiler.py" \
    "$repo/tools/validate_pack_queries.py" "$repo/tools/run_cdjk_sherpa_candidate_pack.sh"
  sha256sum "$source_root/metadata/text_manifest.jsonl" \
    "$source_root/metadata/bible.json" "$work/a/source/adapter-report.json"
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
