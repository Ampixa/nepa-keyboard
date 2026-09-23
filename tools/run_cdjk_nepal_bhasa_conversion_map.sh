#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /home/cdjk/data/nepa-keyboard/conversions/newa/<new-run>" >&2
  exit 2
fi

repo="$(cd "$(dirname "$0")/.." && pwd -P)"
evidence="$1"
case "$evidence" in
  /home/cdjk/data/nepa-keyboard/conversions/newa/*) ;;
  *)
    echo "evidence path must be under the canonical cdjk Newa conversion root" >&2
    exit 2
    ;;
esac
if [[ -e "$evidence" ]]; then
  echo "refusing to reuse evidence path: $evidence" >&2
  exit 2
fi

mkdir -p "$evidence/a" "$evidence/b" "$evidence/upstream"
status="$evidence/run-status.txt"
printf 'completed_stage=initializing\nsequence_complete=0\nexit_status=running\n' > "$status"
failed() {
  code=$?
  printf 'completed_stage=failed\nsequence_complete=0\nexit_status=%s\n' "$code" > "$status"
  exit "$code"
}
trap failed EXIT

python_bin=/home/cdjk/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14
upstream=/home/cdjk/data/nepa-keyboard/upstream/aksharamukha-python-9ad8cce3cac4900dea63b149ca077e691a8916a9
deva="$upstream/aksharamukha/ScriptMap/MainIndic/Devanagari.py"
newa="$upstream/aksharamukha/ScriptMap/MainIndic/Newa.py"
forms=/home/cdjk/data/nepa-keyboard/nepal-bhasa-roman/20260721-v4/a/source/forms.jsonl

{
  hostname
  date --iso-8601=seconds
  free -h
  df -h /home
  "$python_bin" --version
  "$python_bin" -c 'import unicodedata; print(unicodedata.unidata_version)'
  ps -eo pid,comm,rss,%cpu --sort=-rss | head -n 15
} > "$evidence/host-preflight.txt"

available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
available_disk_kib="$(df -Pk /home | awk 'NR==2 {print $4}')"
if (( available_kib < 8388608 )); then
  echo "less than 8 GiB memory available" >&2
  exit 3
fi
if (( available_disk_kib < 20971520 )); then
  echo "less than 20 GiB disk available" >&2
  exit 3
fi
if pgrep -af '[q]emu-system|[e]mulator|[G]radleDaemon|python.*(train|align|infer)' \
    > "$evidence/conflicting-processes.txt"; then
  echo "conflicting Android or compute process detected" >&2
  exit 3
fi

test -x "$python_bin"
test "$("$python_bin" -c 'import unicodedata; print(unicodedata.unidata_version)')" = 16.0.0
printf '%s  %s\n' \
  f453abe3dc86605a68eddbcb1440e56809597565c7fd3c93c4779bf2ea222916 "$deva" \
  5845afdd9618afeddd09cf9b40675a28ba2bdf01bbcccb23be30e5d68d7fe09f "$newa" \
  095349addc2b3610015d9c70c23005b9138c435dc38c00633ee2b4847629f886 "$forms" \
  > "$evidence/expected-input-sha256.txt"
sha256sum -c "$evidence/expected-input-sha256.txt" > "$evidence/input-sha256-check.txt"
install -m 0644 "$deva" "$evidence/upstream/Devanagari.py"
install -m 0644 "$newa" "$evidence/upstream/Newa.py"
git -C "$upstream" rev-parse HEAD > "$evidence/upstream/commit.txt"
test "$(cat "$evidence/upstream/commit.txt")" = 9ad8cce3cac4900dea63b149ca077e691a8916a9

cd "$repo"
PYTHONPATH=. "$python_bin" tests/test_conversion_map.py \
  > "$evidence/test_conversion_map.txt" 2>&1
PYTHONPATH=. "$python_bin" tests/test_nepal_bhasa_conversion_source.py \
  > "$evidence/test_nepal_bhasa_conversion_source.txt" 2>&1
if [[ -f tests/test_nepal_bhasa_conversion_vectors.py ]]; then
  PYTHONPATH=. "$python_bin" tests/test_nepal_bhasa_conversion_vectors.py \
    > "$evidence/test_nepal_bhasa_conversion_vectors.txt" 2>&1
fi

for side in a b; do
  PYTHONPATH=. "$python_bin" tools/build_nepal_bhasa_conversion_source.py \
    --devanagari-table "$deva" \
    --newa-table "$newa" \
    --forms-jsonl "$forms" \
    --output-source "$evidence/$side/new-deva-newa-v1.json" \
    --output-report "$evidence/$side/source-report.json" \
    > "$evidence/$side/source-stdout.json"
  PYTHONPATH=. "$python_bin" tools/build_conversion_map.py \
    "$evidence/$side/new-deva-newa-v1.json" \
    "$evidence/$side/new-Deva-Newa-NP.ncm" \
    > "$evidence/$side/compiler-stdout.json"
done

cmp "$evidence/a/new-deva-newa-v1.json" "$evidence/b/new-deva-newa-v1.json"
cmp "$evidence/a/source-report.json" "$evidence/b/source-report.json"
cmp "$evidence/a/new-Deva-Newa-NP.ncm" "$evidence/b/new-Deva-Newa-NP.ncm"
cmp "$evidence/a/new-deva-newa-v1.json" converters/internal/src/new-deva-newa-v1.json
cmp "$evidence/a/source-report.json" reports/nepal-bhasa-deva-newa-internal-map-v0.json

jq -e '
  .counts.direct_rules == 91
  and .counts.joiner_rules == 74
  and .counts.total_rules == 165
  and .candidate_coverage.forms == 9647
  and .candidate_coverage.converted_forms == 9620
  and .candidate_coverage.no_match_forms == 27
  and .candidate_coverage.distinct_surfaces == 5417
  and .candidate_coverage.converted_surfaces == 5390
  and .candidate_coverage.no_match_surfaces == 27
  and .candidate_coverage.forms_jsonl_sha256
      == "095349addc2b3610015d9c70c23005b9138c435dc38c00633ee2b4847629f886"
' "$evidence/a/source-report.json" > "$evidence/coverage-gate.txt"
jq -e '
  .format == "nepa-conversion-map"
  and .format_version == 1
  and .converter_id == "new-Deva-Newa-NP"
  and .source_script == "Deva"
  and .output_script == "Newa"
  and .rule_count == 165
  and .unmapped_policy == "no-match"
' "$evidence/a/new-Deva-Newa-NP.ncm" > "$evidence/artifact-gate.txt"

(cd "$evidence" && sha256sum \
  a/new-deva-newa-v1.json \
  a/source-report.json \
  a/new-Deva-Newa-NP.ncm) \
  > "$evidence/artifact-sha256.txt"
printf 'completed_stage=complete\nsequence_complete=1\nexit_status=0\n' > "$status"
trap - EXIT

(cd "$evidence" && \
  find . -type f ! -name final-evidence-sha256.txt -print0 \
    | sort -z \
    | xargs -0 sha256sum) \
  > "$evidence/final-evidence-sha256.txt"
echo nepal_bhasa_conversion_map_complete
