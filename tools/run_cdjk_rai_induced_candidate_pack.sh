#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 3 || "$1" != /* || "$2" != /* ]]; then
  echo "usage: $0 /absolute/repository /absolute/new/candidate-directory aph|kle|rav" >&2
  exit 2
fi

repo="$1"
work="$2"
language="$3"
case "$language" in
  aph)
    source_file=nepali-athpariya.induced-lexicon.jsonl
    expected_raw=077f42e4bb6fe1141ad4ee73eb83e715d7df4572ffb2c7d7e47dc4feb40769c4
    expected_queries=25a2ed966d78d18f68588a91ff0a27bd4c8dbee0811f92b1c5a891e8f329ff7d
    ;;
  kle)
    source_file=nepali-kulung.induced-lexicon.jsonl
    expected_raw=88ecad091dd207a48ae8c058d82471c08c942d06f7284c5e6345e26b2b1bb8ae
    expected_queries=1136fdf874c40cad28b7d4638e0b08ad27f234bab5364f37c276b20d88251d70
    ;;
  rav)
    source_file=nepali-sampang.induced-lexicon.jsonl
    expected_raw=ec65236b227bb5f8396f7ba7a8adc31b8b053bee91d9b0a1e0dd5da8b3b3fbd7
    expected_queries=7d7aa9eab16c6c544100c6a5b9439ad1a8a9f6c47e39ec7997087ad57e2de71a
    ;;
  *)
    echo "language must be aph, kle, or rav" >&2
    exit 2
    ;;
esac

raw="$work/$source_file"
adapter="$work/build_rai_induced_candidate_source.py"
queries="$work/$language-induced-candidate-prefix-v0.jsonl"
python="$repo/.venv/bin/python"
pack_id="$language-Deva-NP"
expected_adapter=9ae13244588302f6a34c9692c7d41d0d4b473621d112f8c8d0f3459ea63d04eb

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
    --language "$language" \
    --induced-jsonl "$raw" \
    --output "$work/$run/source" \
    --data-version 1.0.0 \
    --max-suggestions 8 \
    >"$work/$run/adapter-stdout.json" \
    2>"$work/$run/adapter-stderr.txt"
  run_python -m nepa_keyboard.compiler build \
    --input "$work/$run/source" \
    --output "$work/$run/$pack_id.nkp" \
    --mode internal \
    >"$work/$run/compiler-stdout.json" \
    2>"$work/$run/compiler-stderr.txt"
  unzip -t "$work/$run/$pack_id.nkp" \
    >"$work/$run/pack-integrity.txt"
done

diff -qr "$work/a/source" "$work/b/source" >"$work/source-diff.txt"
cmp "$work/a/$pack_id.nkp" "$work/b/$pack_id.nkp"
sha256sum "$work/a/$pack_id.nkp" "$work/b/$pack_id.nkp" \
  >"$work/pack-sha256.txt"
run_python "$repo/tools/validate_pack_queries.py" \
  --queries "$queries" \
  --pack "$pack_id=$work/a/$pack_id.nkp" \
  >"$work/prefix-validation.json"
jq -e '.status == "ok" and .counts.total == 6 and .counts.failed == 0' \
  "$work/prefix-validation.json" >/dev/null
{
  sha256sum "$raw" "$adapter" "$queries" \
    "$repo/src/nepa_keyboard/compiler.py" \
    "$repo/tools/validate_pack_queries.py" \
    "$work/run_cdjk_rai_induced_candidate_pack.sh"
  sha256sum "$work/a/source/adapter-report.json"
} >"$work/input-and-report-sha256.txt"
printf 'language=%s\nsource_trees_identical=true\npacks_identical=true\nprefix_cases=6\nprefix_failed=0\n' \
  "$language" >"$work/run-status.txt"
(
  cd "$work"
  LC_ALL=C find . -type f ! -name final-evidence-sha256.txt -print0 \
    | LC_ALL=C sort -z | xargs -0 sha256sum
) >"$work/final-evidence-sha256.txt"
cat "$work/a/source/adapter-report.json"
cat "$work/pack-sha256.txt"
