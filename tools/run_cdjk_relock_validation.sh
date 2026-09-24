#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helpers are invoked indirectly.
set -euo pipefail

scope=internal
case $# in
  1)
    evidence="$1"
    ;;
  3)
    if [[ "$1" != --scope ]] || [[ "$2" != internal && "$2" != all ]]; then
      echo "usage: $0 [--scope internal|all] /absolute/new/evidence-directory" >&2
      exit 2
    fi
    scope="$2"
    evidence="$3"
    ;;
  *)
    echo "usage: $0 [--scope internal|all] /absolute/new/evidence-directory" >&2
    exit 2
    ;;
esac
if [[ "$evidence" != /* ]]; then
  echo "evidence directory must be absolute" >&2
  exit 2
fi

repo="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$repo/.venv/bin/python"
shipping_profile_lock="$repo/catalog/shipping-profiles.lock.json"
internal_profile_lock="$repo/catalog/internal-profiles.lock.json"
release_layout_lock="$repo/layouts/layouts-v1.lock.json"
internal_layout_lock="$repo/layouts/internal/layouts-v1.lock.json"
transaction_started=0
transaction_committed=0

tracked_paths=(
  catalog/internal-profiles.lock.json
  layouts/internal/layouts-v1.lock.json
  android/ime-app/build.gradle.kts
  android/ime-app/src/main/assets/nepa-layouts/key-alternates-v1.json
  android/ime-app/src/main/assets/nepa-translit/profiles-v1.json
)
if [[ "$scope" == all ]]; then
  tracked_paths=(
    catalog/shipping-profiles.lock.json
    catalog/internal-profiles.lock.json
    layouts/layouts-v1.lock.json
    layouts/internal/layouts-v1.lock.json
    android/ime-app/build.gradle.kts
    android/ime-app/src/main/assets/nepa-layouts/key-alternates-v1.json
    android/ime-app/src/main/assets/nepa-translit/profiles-v1.json
  )
fi

test_files=(
  test_bantawa_jsonl_contract.py
  test_bantawa_internal_source.py
  test_bantawa_source_probe_runner.py
  test_central_gurung_candidate_source.py
  test_central_gurung_internal_source.py
  test_dumi_measurement_runner.py
  test_dumi_internal_source.py
  test_khaling_internal_source.py
  test_khaling_measurement_runner.py
  test_nepal_bhasa_source_audit_runner.py
  test_nepal_bhasa_tsv_contract.py
  test_nepal_bhasa_candidate_pack_runner.py
  test_nepal_bhasa_internal_source.py
  test_nepal_bhasa_newa_internal_source.py
  test_nepal_bhasa_roman_internal_source.py
  test_conversion_map.py
  test_nepal_bhasa_conversion_source.py
  test_nepal_bhasa_conversion_vectors.py
  test_shipping_profile_catalog.py
  test_keyboard_layouts.py
  test_keyboard_layout_candidate.py
  test_layout_native_review.py
  test_mid_eastern_tharu_internal_source.py
  test_eastern_tamang_candidate_source.py
  test_eastern_magar_candidate_source.py
  test_lepcha_candidate_source.py
  test_sherpa_candidate_source.py
  test_rai_induced_candidate_source.py
  test_finalize_internal_pack_milestone.py
  test_western_magar_source_probe_runner.py
  test_western_magar_tsv_contract.py
  test_western_magar_internal_source.py
  test_update_android_lock_pins.py
  test_internal_android_scope.py
  test_android_conversion_substrate.py
  test_relock_validation_runner.py
  test_key_alternates.py
  test_transliteration_profiles.py
  test_transliteration_map.py
  test_transliteration_contrasts.py
  test_emoji_catalog.py
  test_finalize_limbu_internal_milestone.py
)
if [[ "$scope" == all ]]; then
  test_files=(
    test_shipping_profile_catalog.py
    test_keyboard_layouts.py
    test_audit_sil_apk_layout_gap.py
    test_finalize_internal_pack_milestone.py
    test_bantawa_jsonl_contract.py
    test_bantawa_internal_source.py
    test_bantawa_source_probe_runner.py
    test_central_gurung_candidate_source.py
    test_central_gurung_internal_source.py
    test_dumi_measurement_runner.py
    test_dumi_internal_source.py
    test_khaling_internal_source.py
    test_khaling_measurement_runner.py
    test_nepal_bhasa_source_audit_runner.py
    test_nepal_bhasa_tsv_contract.py
    test_nepal_bhasa_candidate_pack_runner.py
    test_nepal_bhasa_internal_source.py
    test_nepal_bhasa_newa_internal_source.py
    test_nepal_bhasa_roman_internal_source.py
    test_conversion_map.py
    test_nepal_bhasa_conversion_source.py
    test_nepal_bhasa_conversion_vectors.py
    test_keyboard_layout_candidate.py
    test_layout_native_review.py
    test_mid_eastern_tharu_internal_source.py
    test_eastern_tamang_candidate_source.py
    test_eastern_magar_candidate_source.py
    test_lepcha_candidate_source.py
    test_sherpa_candidate_source.py
    test_rai_induced_candidate_source.py
    test_western_magar_source_probe_runner.py
    test_western_magar_tsv_contract.py
    test_western_magar_internal_source.py
    test_update_android_lock_pins.py
    test_internal_android_scope.py
    test_android_conversion_substrate.py
    test_relock_validation_runner.py
    test_key_alternates.py
    test_transliteration_profiles.py
    test_transliteration_map.py
    test_transliteration_contrasts.py
    test_emoji_catalog.py
    test_finalize_limbu_internal_milestone.py
  )
fi

# The default transaction is the internal product lane. Public/export locks
# are read and modified only by the explicit `--scope all` maintenance path.

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != "cdjk"
      || "$repo" == /Users/*
      || ! -r /proc/meminfo
      || ! -r /etc/os-release ]] \
    || ! grep -Eq '^ID=("?ubuntu"?)$' /etc/os-release; then
  echo "this relock runner must run from the cdjk Ubuntu checkout" >&2
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
mkdir -p "$evidence/a" "$evidence/b" "$evidence/original"

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

restore_originals() {
  local relative
  local restore_status=0
  for relative in "${tracked_paths[@]}"; do
    if [[ ! -f "$evidence/original/$relative" \
          || -L "$evidence/original/$relative" ]]; then
      echo "missing or symbolic rollback copy: $relative" >&2
      restore_status=1
      continue
    fi
    if ! install -m 0644 "$evidence/original/$relative" "$repo/$relative"; then
      restore_status=1
      continue
    fi
    if ! chmod --reference="$evidence/original/$relative" "$repo/$relative"; then
      restore_status=1
    fi
    if ! cmp "$evidence/original/$relative" "$repo/$relative"; then
      restore_status=1
    fi
  done
  if ! (
    cd "$repo"
    sha256sum "${tracked_paths[@]}"
  ) >"$evidence/rollback-sha256.txt"; then
    restore_status=1
  fi
  return "$restore_status"
}

on_exit() {
  local test_status=$?
  trap - EXIT
  set +e
  local rollback_status=0
  if (( test_status != 0 && transaction_started != 0 && transaction_committed == 0 )); then
    restore_originals || rollback_status=$?
  fi
  local final_status=$test_status
  if (( rollback_status != 0 )); then
    final_status=1
  fi
  if (( final_status == 0 && transaction_started != 0 )); then
    transaction_committed=1
  fi
  local manifest_status=0
  if ! {
    printf 'test_exit_status=%s\n' "$test_status"
    printf 'transaction_started=%s\n' "$transaction_started"
    printf 'transaction_committed=%s\n' "$transaction_committed"
    printf 'rollback_exit_status=%s\n' "$rollback_status"
    printf 'manifest_exit_status=0\n'
    printf 'remote_exit_status=%s\n' "$final_status"
  } >"$evidence/run-status.txt"; then
    manifest_status=1
  else
    write_evidence_manifest || manifest_status=$?
  fi
  if (( manifest_status != 0 )); then
    transaction_committed=0
    final_status=1
    if (( transaction_started != 0 && rollback_status == 0 )); then
      restore_originals || rollback_status=$?
    fi
    {
      printf 'test_exit_status=%s\n' "$test_status"
      printf 'transaction_started=%s\n' "$transaction_started"
      printf 'transaction_committed=%s\n' "$transaction_committed"
      printf 'rollback_exit_status=%s\n' "$rollback_status"
      printf 'manifest_exit_status=%s\n' "$manifest_status"
      printf 'remote_exit_status=%s\n' "$final_status"
    } >"$evidence/run-status.txt" || true
    # A second bounded attempt content-binds the failure and rollback. The
    # original nonzero manifest status remains authoritative in run-status.
    write_evidence_manifest || true
  fi
  if (( final_status == 0 )); then
    printf 'relock_complete evidence=%s\n' "$evidence"
  fi
  exit "$final_status"
}
trap on_exit EXIT

available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
if [[ ! "$available_kib" =~ ^[0-9]+$ ]] || (( available_kib < 8 * 1024 * 1024 )); then
  echo "cdjk has less than 8 GiB available memory" >&2
  exit 1
fi
home_available_kib="$(df -Pk /home | awk 'NR == 2 {print $4}')"
tmp_available_kib="$(df -Pk /tmp | awk 'NR == 2 {print $4}')"
evidence_available_kib="$(df -Pk "$evidence" | awk 'NR == 2 {print $4}')"
if [[ ! "$home_available_kib" =~ ^[0-9]+$ \
      || ! "$tmp_available_kib" =~ ^[0-9]+$ \
      || ! "$evidence_available_kib" =~ ^[0-9]+$ \
      || "$home_available_kib" -lt $((4 * 1024 * 1024)) \
      || "$tmp_available_kib" -lt $((2 * 1024 * 1024)) \
      || "$evidence_available_kib" -lt $((4 * 1024 * 1024)) ]]; then
  echo "cdjk has insufficient free disk for deterministic relocking" >&2
  exit 1
fi

for required in awk chmod cmp cp df find flock free grep hostname install jq mkdir \
  mv pgrep ps realpath rm sed sha256sum sort timeout uname uptime xargs \
  "$python_bin"; do
  if [[ "$required" == /* ]]; then
    [[ -x "$required" ]]
  else
    command -v "$required" >/dev/null
  fi
done
if ! "$python_bin" -c '
import sys
import unicodedata
if sys.version_info[:2] != (3, 14):
    raise SystemExit("Python 3.14 is required")
if unicodedata.unidata_version != "16.0.0":
    raise SystemExit("Unicode 16.0.0 is required")
print("python=" + sys.version.split()[0])
print("unicode=" + unicodedata.unidata_version)
' >"$evidence/python-runtime.txt"; then
  echo "cdjk relock requires Python 3.14 with Unicode 16.0.0" >&2
  exit 1
fi
sha256sum "$python_bin" >"$evidence/python-runtime-sha256.txt"
for relative in "${tracked_paths[@]}"; do
  [[ -f "$repo/$relative" && -s "$repo/$relative" && ! -L "$repo/$relative" ]]
done
static_source_inputs=(
  catalog/resources.json
  catalog/internal-profile-review.json
  schemas/resource-catalog.schema.json
  schemas/shipping-profile-review.schema.json
  schemas/shipping-profile-lock.schema.json
  schemas/layout-v1.schema.json
  schemas/layout-lock-v1.schema.json
  schemas/layout-native-review-v1.schema.json
  tools/build_shipping_profile_catalog.py
  tools/build_keyboard_layouts.py
  tools/build_key_alternates.py
  tools/build_transliteration_map.py
  tools/build_transliteration_profiles.py
  tools/build_emoji_catalog.py
  catalog/key-alternates-v0.json
  catalog/transliteration-profiles-v0.json
  tools/build_khaling_internal_source.py
  tools/build_dumi_internal_source.py
  tools/sil_apk_jsonl_internal_source.py
  src/nepa_keyboard/compiler.py
  src/nepa_keyboard/runtime.py
  tools/validate_keyboard_layout_candidate.py
  tools/validate_layout_native_review.py
  tools/update_android_lock_pins.py
  tools/audit_bantawa_jsonl_contract.py
  tools/build_bantawa_internal_source.py
  tools/build_central_gurung_candidate_source.py
  tools/build_central_gurung_internal_source.py
  tools/build_mid_eastern_tharu_internal_source.py
  tools/build_eastern_tamang_candidate_source.py
  tools/build_eastern_magar_candidate_source.py
  tools/build_lepcha_candidate_source.py
  tools/build_sherpa_candidate_source.py
  tools/build_rai_induced_candidate_source.py
  tools/run_cdjk_lepcha_candidate_pack.sh
  tools/run_cdjk_sherpa_candidate_pack.sh
  validation/lepcha-candidate-prefix-v0.jsonl
  validation/sherpa-candidate-prefix-v0.jsonl
  reports/sherpa-scalar-inventory-v0.json
  tools/build_western_magar_internal_source.py
  tools/audit_nepal_bhasa_tsv_contract.py
  tools/build_nepal_bhasa_internal_source.py
  tools/build_nepal_bhasa_newa_internal_source.py
  tools/build_nepal_bhasa_roman_internal_source.py
  tools/build_conversion_map.py
  tools/build_nepal_bhasa_conversion_source.py
  tools/run_cdjk_nepal_bhasa_conversion_map.sh
  tools/audit_western_magar_tsv_contract.py
  tools/run_cdjk_bantawa_source_probe.sh
  tools/run_cdjk_dumi_measurement.sh
  tools/run_cdjk_khaling_measurement.sh
  tools/run_cdjk_nepal_bhasa_source_audit.sh
  tools/run_cdjk_nepal_bhasa_candidate_pack.sh
  tools/run_cdjk_internal_catalog_validation.sh
  tools/run_cdjk_sil_apk_candidate_pack.sh
  tools/run_cdjk_sil_apk_layout_matrix.sh
  tools/run_cdjk_western_magar_source_probe.sh
  tools/run_cdjk_relock_validation.sh
  tools/run_cdjk_subtype_compat_validation.sh
  tools/run_cdjk_yakkha_refresh.sh
  docs/android-first-run-setup.md
  docs/cdjk-relock-validation.md
  docs/bantawa-source-probe.md
  docs/nepal-bhasa-input-reference-audit.md
  docs/newa-qwerty-direct-candidate.md
  docs/nepal-bhasa-source-audit.md
  docs/product-architecture.md
  docs/sil-apk-layout-matrix-audit.md
  docs/western-magar-source-probe.md
  android/settings.gradle.kts
  android/benchmark-app/build.gradle.kts
  android/pack-runtime/build.gradle.kts
  android/pack-runtime/consumer-rules.pro
  catalog/nepal-bhasa-candidate-pack-v0.json
  catalog/khaling-internal-prefixes-v0.json
  catalog/internal-pack-milestones/klr-Deva-NP-v0.json
  catalog/dumi-internal-prefixes-v0.json
  catalog/internal-pack-milestones/dus-Deva-NP-v0.json
  catalog/bantawa-internal-prefixes-v0.json
  catalog/internal-pack-milestones/bap-Deva-NP-v0.json
  catalog/western-magar-internal-prefixes-v0.json
  catalog/internal-pack-milestones/mrd-Deva-NP-v0.json
  catalog/internal-pack-milestones/thq-Deva-NP-v0.json
  catalog/central-gurung-internal-prefixes-v0.json
  catalog/internal-pack-milestones/gvr-Deva-NP-v0.json
  reports/evidence/central-gurung-candidate-v0/gvr_nep_lexicon.tsv
  reports/central-gurung-candidate-policy-v0.md
  catalog/tharu-internal-prefixes-v0.json
  reports/evidence/mid-eastern-tharu-layout-scalar-check-v0.json
  reports/bantawa-layout-candidate-v0.md
  reports/western-magar-candidate-policy-v0.md
  catalog/nepal-bhasa-internal-prefixes-v0.json
  catalog/nepal-bhasa-newa-internal-prefixes-v0.json
  catalog/nepal-bhasa-roman-internal-prefixes-v0.json
  catalog/nepal-bhasa-deva-newa-internal-vectors-v0.json
  catalog/internal-pack-milestones/new-Deva-NP-v0.json
  catalog/internal-pack-milestones/new-Newa-NP-v0.json
  converters/internal/src/new-deva-newa-v1.json
  reports/nepal-bhasa-candidate-pack-v0.md
  reports/nepal-bhasa-deva-newa-internal-map-v0.json
  android/conversion-runtime/build.gradle.kts
  android/conversion-runtime/consumer-rules.pro
  android/conversion-runtime/src/main/AndroidManifest.xml
)
source_inputs=()

append_directory_inputs() {
  local relative_directory="$1"
  local absolute_path
  [[ -d "$repo/$relative_directory" && ! -L "$repo/$relative_directory" ]]
  while IFS= read -r -d '' absolute_path; do
    source_inputs+=("${absolute_path#"$repo/"}")
  done < <(
    LC_ALL=C find "$repo/$relative_directory" -mindepth 1 -maxdepth 1 -print0 \
      | LC_ALL=C sort -z
  )
}

append_directory_tree_inputs() {
  local relative_directory="$1"
  local absolute_path
  local relative_path
  local tracked
  [[ -d "$repo/$relative_directory" && ! -L "$repo/$relative_directory" ]]
  if find "$repo/$relative_directory" -type l -print -quit | grep -q .; then
    echo "source directory tree contains a symbolic link: $relative_directory" >&2
    exit 1
  fi
  while IFS= read -r -d '' absolute_path; do
    relative_path="${absolute_path#"$repo/"}"
    for tracked in "${tracked_paths[@]}"; do
      if [[ "$relative_path" == "$tracked" ]]; then
        continue 2
      fi
    done
    source_inputs+=("$relative_path")
  done < <(
    LC_ALL=C find "$repo/$relative_directory" -type f -size +0c -print0 \
      | LC_ALL=C sort -z
  )
}

append_review_evidence_inputs() {
  local review_file
  local evidence_path
  while IFS= read -r evidence_path; do
    source_inputs+=("$evidence_path")
  done < <(
    for review_file in "$@"; do
      jq -r '.evidence[]?.artifacts[]?.path' "$repo/$review_file"
    done | LC_ALL=C sort -u
  )
}

build_source_inputs() {
  local test_file
  source_inputs=("${static_source_inputs[@]}")
  for test_file in "${test_files[@]}"; do
    source_inputs+=("tests/$test_file")
  done
  append_directory_inputs layouts/internal/src
  append_directory_inputs layouts/internal/notices
  append_directory_inputs layouts/research
  append_directory_inputs layouts/reviews
  append_directory_tree_inputs android/ime-app/src
  append_directory_tree_inputs catalog/transliteration
  append_directory_tree_inputs android/benchmark-app/src/main
  append_directory_tree_inputs android/pack-runtime/src/main
  append_directory_tree_inputs android/conversion-runtime/src/main
  if [[ "$scope" == all ]]; then
    append_review_evidence_inputs \
      catalog/internal-profile-review.json \
      catalog/shipping-profile-review.json
    source_inputs+=(
      catalog/shipping-profile-review.json
      tools/audit_sil_apk_layout_gap.py
      tools/finalize_internal_pack_milestone_v1.py
    )
    append_directory_inputs layouts/src
    append_directory_inputs layouts/notices
  else
    append_review_evidence_inputs catalog/internal-profile-review.json
  fi
}

validate_source_inputs() {
  local source
  local tracked
  local resolved_source
  for source in "${source_inputs[@]}"; do
    if [[ ! -f "$repo/$source" || ! -s "$repo/$source" || -L "$repo/$source" ]]; then
      echo "immutable source input is not a nonempty regular file: $source" >&2
      return 1
    fi
    resolved_source="$(realpath -e -- "$repo/$source")" || return 1
    if [[ "$source" == /* || "$resolved_source" != "$repo/"* ]]; then
      echo "immutable source input escapes the checkout: $source" >&2
      return 1
    fi
    for tracked in "${tracked_paths[@]}"; do
      if [[ "$source" == "$tracked" ]]; then
        echo "immutable source overlaps transaction output: $source" >&2
        return 1
      fi
    done
  done
}

build_source_inputs
validate_source_inputs

exec 9>/tmp/nepa-keyboard-android-validation.lock
if ! flock -n 9; then
  echo "another Nepa Android or relock validation owns the cdjk lock" >&2
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
  df -h "$evidence" /home /tmp
  ps -eo pid,comm,%cpu,%mem,rss --sort=-rss | sed -n '1,20p'
} >"$evidence/host-preflight.txt"

cd "$repo"
for relative in "${tracked_paths[@]}"; do
  mkdir -p "$evidence/original/$(dirname "$relative")"
  cp -p -- "$relative" "$evidence/original/$relative"
done
sha256sum "${tracked_paths[@]}" >"$evidence/original-sha256.txt"
sha256sum "${source_inputs[@]}" >"$evidence/input-source-sha256.txt"
printf 'scope=%s\n' "$scope" >"$evidence/relock-scope.txt"

run_python() {
  PYTHONPATH=src:. timeout 600 "$python_bin" "$@"
}

assert_conversion_schema_contract() {
  local schema="$1"
  jq -e '
    .["$defs"].conversion_artifact as $artifact
    | $artifact.additionalProperties == false
      and ($artifact.required | sort) == [
        "artifact_sha256", "converter_id", "file_name", "language",
        "output_script", "release_mode", "rule_count", "source_script",
        "validation"
      ]
      and ($artifact.properties | keys | sort) == [
        "artifact_sha256", "converter_id", "file_name", "language",
        "output_script", "release_mode", "rule_count", "source_script",
        "validation"
      ]
      and $artifact.properties.converter_id.pattern
        == "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
      and ($artifact.properties | has("conversion_id") | not)
      and $artifact.properties.file_name.pattern
        == "^[A-Za-z0-9._-]+\\.ncm$"
  ' "$schema" >/dev/null
}

assert_newa_internal_profile() {
  local lock="$1"
  jq -e '
    ([.profiles[] | select(.profile_id == "new-Newa-NP")]) as $rows
    | ($rows | length) == 1
      and ($rows[0] |
        .catalog_readiness == "beta"
        and .selectable == true
        and .default_enabled == false
        and .layout_id == "newa-nepal-prachalit-v1"
        and .layout_revision == 1
        and (.layout_source_sha256 | test("^[0-9a-f]{64}$"))
        and .pack_binding == "new-Newa-NP"
        and .pack_artifact.pack_id == "new-Newa-NP"
        and .pack_artifact.file_name == "new-Newa-NP.nkp"
        and .pack_artifact.output_script == "Newa"
        and .pack_artifact.release_mode == "internal"
        and .pack_artifact.candidate_count > 0
        and (.pack_artifact.artifact_sha256 | test("^[0-9a-f]{64}$"))
        and (.evidence_ids | length) == 1
        and (.evidence_artifacts | length) == 1
        and .blocked_reason == null)
  ' "$lock" >/dev/null
}

assert_nepal_bhasa_roman_internal_profile() {
  local lock="$1"
  jq -e '
    ([.profiles[]
      | select(.profile_id == "new-Deva-NP" or .profile_id == "new-Latn-Deva-NP")]
      | sort_by(.profile_id)) as $rows
    | ($rows | length) == 2
      and ($rows[0] |
        .profile_id == "new-Deva-NP"
        and .catalog_readiness == "beta"
        and .selectable == true
        and .lookup_kind == "surface_prefix"
        and .layout_id == "deva-nepal-bhasa-v1"
        and .pack_binding == "new-Deva-NP"
        and .pack_artifact.artifact_sha256 == "c90c7eba644334ef95ae7dfc168d70382083f06ab7fc45a81f33a90052952570"
        and .pack_artifact.alias_key_count == 1828)
      and ($rows[1] |
        .profile_id == "new-Latn-Deva-NP"
        and .catalog_readiness == "beta"
        and .selectable == true
        and .default_enabled == false
        and .source_script == "Latn"
        and .output_script == "Deva"
        and .lookup_kind == "alias_prefix"
        and .engine_kind == "alias_decoder"
        and .layout_id == "latn-qwerty-us-v1"
        and .layout_revision == 1
        and .pack_binding == "new-Deva-NP"
        and .pack_artifact.pack_id == "new-Deva-NP"
        and .pack_artifact.file_name == "new-Deva-NP.nkp"
        and .pack_artifact.artifact_sha256 == "c90c7eba644334ef95ae7dfc168d70382083f06ab7fc45a81f33a90052952570"
        and .pack_artifact.candidate_count == 5417
        and .pack_artifact.surface_key_count == 5417
        and .pack_artifact.alias_key_count == 1828
        and .pack_artifact.release_mode == "internal"
        and .evidence_ids == ["new-roman-internal-2026-07-21"]
        and .blocked_reason == null)
  ' "$lock" >/dev/null
}

assert_nepal_bhasa_conversion_internal_profile() {
  local lock="$1"
  jq -e '
    .lock_version == 2
    and .generator_version == 2
    and ([.profiles[]
      | has("pack_binding")
        and has("pack_artifact")
        and has("conversion_binding")
        and has("conversion_artifact")] | all)
    and (([.profiles[] | select(.profile_id == "new-Deva-Newa-NP")]) as $rows
    | ($rows | length) == 1
      and ($rows[0] |
        .catalog_readiness == "beta"
        and .selectable == true
        and .default_enabled == false
        and .source_script == "Deva"
        and .output_script == "Newa"
        and .lookup_kind == "conversion"
        and .engine_kind == "converter"
        and .layout_id == "deva-nepal-bhasa-v1"
        and .layout_revision == 1
        and .pack_binding == null
        and .pack_artifact == null
        and .conversion_binding == "new-Deva-Newa-NP"
        and (.conversion_artifact | keys | sort) == [
          "artifact_sha256", "converter_id", "file_name", "language",
          "output_script", "release_mode", "rule_count", "source_script",
          "validation"
        ]
        and .conversion_artifact.converter_id == "new-Deva-Newa-NP"
        and .conversion_artifact.file_name == "new-Deva-Newa-NP.ncm"
        and .conversion_artifact.artifact_sha256 == "29c88708b3d7aeb741779b7a7464efcb2464e060d7939c7998533d50b11a2d05"
        and .conversion_artifact.language == "new"
        and .conversion_artifact.source_script == "Deva"
        and .conversion_artifact.output_script == "Newa"
        and .conversion_artifact.release_mode == "internal"
        and .conversion_artifact.rule_count == 165
        and ([.conversion_artifact.validation.vectors[].expected_status] | unique)
          == ["MATCH", "NO_MATCH"]
        and ([.conversion_artifact.validation.vectors[]
          | select(.expected_status == "MATCH" and (.expected_output | type) == "string")]
          | length) > 0
        and ([.conversion_artifact.validation.vectors[]
          | select(.expected_status == "NO_MATCH" and .expected_output == null)]
          | length) > 0
        and .evidence_ids == ["new-deva-newa-internal-2026-07-21"]
        and (.evidence_artifacts | length) == 2
        and .blocked_reason == null))
  ' "$lock" >/dev/null
}

assert_dumi_internal_profile() {
  local lock="$1"
  jq -e '
    ([.profiles[] | select(.profile_id == "dus-Deva-NP")]) as $rows
    | ($rows | length) == 1
      and ($rows[0] |
        .catalog_readiness == "beta"
        and .selectable == true
        and .default_enabled == false
        and .source_script == "Deva"
        and .output_script == "Deva"
        and .lookup_kind == "surface_prefix"
        and .engine_kind == "layout"
        and .layout_id == "deva-nepal-dumi-v1"
        and .layout_revision == 1
        and .layout_source_sha256 == "5688c744ee8b88cb3a24c76379590b99195a90a0e309f625ea578b1ced1e60ac"
        and .pack_binding == "dus-Deva-NP"
        and .pack_artifact.pack_id == "dus-Deva-NP"
        and .pack_artifact.file_name == "dus-Deva-NP.nkp"
        and .pack_artifact.artifact_sha256 == "efd9626d11c3910361adb50f1e656c67aefc2c6957ee3b47122236b1a6e3dec2"
        and .pack_artifact.candidate_count == 2132
        and .pack_artifact.surface_key_count == 2132
        and .pack_artifact.alias_key_count == 0
        and .pack_artifact.release_mode == "internal"
        and .pack_artifact.validation.query == "क"
        and .pack_artifact.validation.expected_surface == "क:फु"
        and (.pack_artifact.validation.benchmark_queries | length) == 10
        and .evidence_ids == ["dus-direct-internal-2026-07-22"]
        and .evidence_artifacts == [{
          path: "reports/dumi-internal-pack-v0.json",
          sha256: "f4150925578f3b07ddb6a1cb766f3785f127ff05d18e49a1ca112364688089c9"
        }]
        and .blocked_reason == null)
  ' "$lock" >/dev/null
}

assert_new_internal_profile() {
  local lock="$1"
  local profile_id="$2"
  local layout_id="$3"
  local layout_sha256="$4"
  local pack_sha256="$5"
  local candidate_count="$6"
  local validation_query="$7"
  local expected_surface="$8"
  local evidence_id="$9"
  local evidence_path="${10}"
  local evidence_sha256="${11}"
  jq -e \
    --arg profile_id "$profile_id" \
    --arg layout_id "$layout_id" \
    --arg layout_sha256 "$layout_sha256" \
    --arg pack_sha256 "$pack_sha256" \
    --argjson candidate_count "$candidate_count" \
    --arg validation_query "$validation_query" \
    --arg expected_surface "$expected_surface" \
    --arg evidence_id "$evidence_id" \
    --arg evidence_path "$evidence_path" \
    --arg evidence_sha256 "$evidence_sha256" '
    ([.profiles[] | select(.profile_id == $profile_id)]) as $rows
    | ($rows | length) == 1
      and ($rows[0] |
        .selectable == true
        and .default_enabled == false
        and .source_script == "Deva"
        and .output_script == "Deva"
        and .lookup_kind == "surface_prefix"
        and .engine_kind == "layout"
        and .layout_id == $layout_id
        and .layout_revision == 1
        and .layout_source_sha256 == $layout_sha256
        and .pack_binding == $profile_id
        and .pack_artifact.pack_id == $profile_id
        and .pack_artifact.file_name == ($profile_id + ".nkp")
        and .pack_artifact.artifact_sha256 == $pack_sha256
        and .pack_artifact.candidate_count == $candidate_count
        and .pack_artifact.surface_key_count == $candidate_count
        and .pack_artifact.alias_key_count == 0
        and .pack_artifact.release_mode == "internal"
        and .pack_artifact.validation.query == $validation_query
        and .pack_artifact.validation.expected_surface == $expected_surface
        and .evidence_ids == [$evidence_id]
        and .evidence_artifacts == [{
          path: $evidence_path,
          sha256: $evidence_sha256
        }]
        and .blocked_reason == null)
  ' "$lock" >/dev/null
}

assert_newa_release_profile() {
  local lock="$1"
  local expected_blocked_reason="$2"
  jq -e --arg expected_blocked_reason "$expected_blocked_reason" '
    ([.profiles[] | select(.profile_id == "new-Newa-NP")]) as $rows
    | ($rows | length) == 1
      and ($rows[0] |
        .catalog_readiness == "beta"
        and .selectable == false
        and .default_enabled == false
        and .layout_id == "pending-new-newa-direct"
        and .layout_revision == null
        and .layout_source_sha256 == null
        and .pack_binding == null
        and .pack_artifact == null
        and .evidence_ids == []
        and .evidence_artifacts == []
        and .blocked_reason == $expected_blocked_reason)
  ' "$lock" >/dev/null
}

assert_internal_newa_layout_binding() {
  local lock="$1"
  jq -e '
    ([.profile_bindings[]
      | select(.profile_id == "new-Newa-NP"
          and .source_script == "Newa"
          and .layout_id == "newa-nepal-prachalit-v1"
          and .revision == 1)]
      | length) == 1
    and ([.profile_bindings[]
      | select(.profile_id == "new-Deva-Newa-NP"
          and .source_script == "Deva"
          and .layout_id == "deva-nepal-bhasa-v1"
          and .revision == 1)]
      | length) == 1
    and ([.layouts[]
      | select(.layout_id == "newa-nepal-prachalit-v1"
          and .input_script == "Newa"
          and .revision == 1)]
      | length) == 1
  ' "$lock" >/dev/null
}

assert_internal_dumi_layout_binding() {
  local lock="$1"
  jq -e '
    ([.profile_bindings[]
      | select(.profile_id == "dus-Deva-NP"
          and .source_script == "Deva"
          and .layout_id == "deva-nepal-dumi-v1"
          and .revision == 1)]
      | length) == 1
    and ([.layouts[]
      | select(.layout_id == "deva-nepal-dumi-v1"
          and .input_script == "Deva"
          and .revision == 1)]
      | length) == 1
  ' "$lock" >/dev/null
}

assert_no_release_newa_layout_binding() {
  local lock="$1"
  jq -e '
    ([.profile_bindings[]
      | select(.profile_id == "new-Newa-NP" or .source_script == "Newa")]
      | length) == 0
    and ([.layouts[] | select(.input_script == "Newa")] | length) == 0
  ' "$lock" >/dev/null
}

assert_conversion_schema_contract schemas/shipping-profile-review.schema.json
assert_conversion_schema_contract schemas/shipping-profile-lock.schema.json
jq -S '.["$defs"].conversion_artifact' \
  schemas/shipping-profile-review.schema.json \
  >"$evidence/conversion-review-artifact-schema.json"
jq -S '.["$defs"].conversion_artifact' \
  schemas/shipping-profile-lock.schema.json \
  >"$evidence/conversion-lock-artifact-schema.json"
cmp "$evidence/conversion-review-artifact-schema.json" \
  "$evidence/conversion-lock-artifact-schema.json"

newa_converter_id=new-Deva-Newa-NP
newa_converter_sha256=29c88708b3d7aeb741779b7a7464efcb2464e060d7939c7998533d50b11a2d05
newa_converter_file=new-Deva-Newa-NP.ncm
jq -e \
  --arg converter_id "$newa_converter_id" \
  --arg artifact_sha256 "$newa_converter_sha256" \
  --arg file_name "$newa_converter_file" '
    ([.evidence[]
      | select(.profile_id == "new-Deva-Newa-NP"
          and .evidence_id == "new-deva-newa-internal-2026-07-21")]) as $rows
    | ($rows | length) == 1
      and ($rows[0].conversion_artifact | keys | sort) == [
        "artifact_sha256", "converter_id", "file_name", "language",
        "output_script", "release_mode", "rule_count", "source_script",
        "validation"
      ]
      and $rows[0].conversion_artifact.converter_id == $converter_id
      and $rows[0].conversion_artifact.file_name == $file_name
      and $rows[0].conversion_artifact.artifact_sha256 == $artifact_sha256
      and $rows[0].conversion_artifact.rule_count == 165
      and $rows[0].conversion_artifact.release_mode == "internal"
      and ([ $rows[0].conversion_artifact.validation.vectors[]
        | .expected_status ] | unique) == ["MATCH", "NO_MATCH"]
      and (.profile_overrides["new-deva-newa"].conversion_binding
        == $converter_id)
      and (.profile_overrides["new-deva-newa"] | has("pack_binding") | not)
  ' catalog/internal-profile-review.json >/dev/null
for run in a b; do
  run_python tools/build_conversion_map.py \
    converters/internal/src/new-deva-newa-v1.json \
    "$evidence/$run/$newa_converter_file" \
    >"$evidence/$run/conversion-map-compiler.json"
  jq -e \
    --arg converter_id "$newa_converter_id" \
    --arg artifact_sha256 "$newa_converter_sha256" \
    --arg output "$evidence/$run/$newa_converter_file" '
      (keys | sort) == [
        "artifact_sha256", "converter_id", "output", "rule_count"
      ]
      and .converter_id == $converter_id
      and .artifact_sha256 == $artifact_sha256
      and .output == $output
      and .rule_count == 165
    ' "$evidence/$run/conversion-map-compiler.json" >/dev/null
done
cmp "$evidence/a/$newa_converter_file" \
  "$evidence/b/$newa_converter_file"
[[ "$(sha256sum "$evidence/a/$newa_converter_file" | awk '{print $1}')" \
  == "$newa_converter_sha256" ]]
jq -e --arg converter_id "$newa_converter_id" '
  (keys | sort) == [
    "algorithm", "converter_id", "format", "format_version", "joiner_policy",
    "language", "mapping_version", "normalization", "output_script",
    "rule_count", "rules", "source_script", "unmapped_policy"
  ]
  and .format == "nepa-conversion-map"
  and .format_version == 1
  and .converter_id == $converter_id
  and .language == "new"
  and .source_script == "Deva"
  and .output_script == "Newa"
  and .rule_count == 165
  and .unmapped_policy == "no-match"
' "$evidence/a/$newa_converter_file" >/dev/null

for run in a b; do
  if [[ "$scope" == all ]]; then
    run_python tools/build_shipping_profile_catalog.py \
      --catalog catalog/resources.json \
      --review catalog/shipping-profile-review.json \
      --output "$evidence/$run/shipping-profiles.lock.json" \
      >"$evidence/$run/shipping-profile-build.log" 2>&1
  fi
  run_python tools/build_shipping_profile_catalog.py \
    --catalog catalog/resources.json \
    --review catalog/internal-profile-review.json \
    --output "$evidence/$run/internal-profiles.lock.json" \
    >"$evidence/$run/internal-profile-build.log" 2>&1
done
if [[ "$scope" == all ]]; then
  cmp "$evidence/a/shipping-profiles.lock.json" \
    "$evidence/b/shipping-profiles.lock.json"
fi
cmp "$evidence/a/internal-profiles.lock.json" \
  "$evidence/b/internal-profiles.lock.json"
assert_newa_internal_profile "$evidence/a/internal-profiles.lock.json"
assert_nepal_bhasa_roman_internal_profile \
  "$evidence/a/internal-profiles.lock.json"
assert_nepal_bhasa_conversion_internal_profile \
  "$evidence/a/internal-profiles.lock.json"
assert_dumi_internal_profile "$evidence/a/internal-profiles.lock.json"
assert_new_internal_profile \
  "$evidence/a/internal-profiles.lock.json" \
  bap-Deva-NP deva-nepal-bantawa-v1 \
  c469ed3c08c999a397025371dbf259a0f252f7e81cb032710c11ea0bf9b8289b \
  bccf336f1abd1fe1154d3fda6afd6d5b6187468a899adb613b248b44ca58f8c4 \
  1714 'अ' 'अ' bap-direct-internal-2026-09-24 \
  reports/bantawa-internal-pack-v0.json \
  28fe56a37567390a86e14f2845ac79784ba072c69d85460a026cc7d93b6dd270
assert_new_internal_profile \
  "$evidence/a/internal-profiles.lock.json" \
  mrd-Deva-NP deva-nepal-western-magar-v1 \
  f1f9699d071287b7d747e3c7744a3c1efb9f1f8ca242f8421c02e70392bd8cb1 \
  6d5061f9359a1d641af66c31471501a8de3652aab98c2999f94026d80be98aeb \
  1219 '-ऐ' '-ऐ' mrd-direct-internal-2026-09-24 \
  reports/western-magar-internal-pack-v0.json \
  f760878e3f0ee96790cf04ac25e49e69c9e77f07a23bd530570ce4d8e0809f1a
assert_new_internal_profile \
  "$evidence/a/internal-profiles.lock.json" \
  thq-Deva-NP deva-nepal-mid-eastern-tharu-v1 \
  db316037bebc211c8b76bd9219f0dcf43ad8ad7639c291cb6e608fad24d210b4 \
  d3c284fadeedc5e863e8364b5db496174fcf57f5acfeed38f16e2f679e1dfb18 \
  2980 'अइठ' 'अइठल' thq-direct-internal-2026-09-24 \
  reports/mid-eastern-tharu-internal-pack-v0.json \
  8eaaa307984cfbbb57ef316533bda9581928b753d0069de1a99274b9718f96a5
assert_new_internal_profile \
  "$evidence/a/internal-profiles.lock.json" \
  gvr-Deva-NP deva-nepal-central-gurung-v1 \
  fbf366fc4a1dd560d5dbdc8128a40169a4e596c2ab0f047975e466f3ec72f5b4 \
  f4d128e1b77aa6e9012448addf7f45bd140301f98767f1dd934e3d21e86fafda \
  286 'ऱ' 'ऱा' gvr-direct-internal-2026-09-24 \
  reports/central-gurung-internal-pack-v0.json \
  08bb6546501fa40dfeba5f8abf5d380de59f65879051d9f164e8ce3f0cca5eb6
if [[ "$scope" == all ]]; then
  assert_newa_release_profile \
    "$evidence/a/shipping-profiles.lock.json" \
    DIRECT_PROFILE_NOT_RELEASE_APPROVED
fi
for run in a b; do
  run_python tools/validate_keyboard_layout_candidate.py \
    --candidate layouts/research/newa-nepal-qwerty-direct-v1.json \
    >"$evidence/$run/newa-qwerty-direct-candidate.json"
done
cmp "$evidence/a/newa-qwerty-direct-candidate.json" \
  "$evidence/b/newa-qwerty-direct-candidate.json"
jq -e '
  .candidate_validation_version == 1
  and .status == "research"
  and .selectable == false
  and .default_enabled == false
  and .layout_id == "newa-nepal-qwerty-direct-v1"
  and .input_script == "Newa"
  and (.source.sha256 | test("^[0-9a-f]{64}$"))
  and (.compiled_sha256 | test("^[0-9a-f]{64}$"))
  and (.compiler.sha256 | test("^[0-9a-f]{64}$"))
  and (.source_schema.sha256 | test("^[0-9a-f]{64}$"))
' "$evidence/a/newa-qwerty-direct-candidate.json" >/dev/null
for run in a b; do
  run_python tools/validate_layout_native_review.py \
    --review layouts/reviews/newa-nepal-qwerty-direct-v1.review.json \
    >"$evidence/$run/newa-qwerty-direct-native-review.json"
done
cmp "$evidence/a/newa-qwerty-direct-native-review.json" \
  "$evidence/b/newa-qwerty-direct-native-review.json"
for run in a b; do
  jq -S '.' "$evidence/$run/newa-qwerty-direct-candidate.json" \
    >"$evidence/$run/newa-qwerty-direct-candidate.canonical.json"
  jq -S '.candidate' "$evidence/$run/newa-qwerty-direct-native-review.json" \
    >"$evidence/$run/newa-qwerty-direct-native-review-candidate.json"
  cmp "$evidence/$run/newa-qwerty-direct-candidate.canonical.json" \
    "$evidence/$run/newa-qwerty-direct-native-review-candidate.json"
done
jq -e '
  .native_review_validation_version == 1
  and .review_id == "newa-nepal-qwerty-direct-v1-native-review"
  and .review_profile == "newa_qwerty_direct_v1"
  and .status == "pending"
  and .section_count == 4
  and .decision_count == 8
  and .coverage_item_count == 15
  and .missing_critical_scalar_count == 5
  and .unresolved_count == 27
  and .profile_effect == {
    profile_id: "new-Newa-NP",
    selectable: false,
    default_enabled: false,
    bind_layout: false
  }
  and (.review.sha256 | test("^[0-9a-f]{64}$"))
  and (.candidate.compiled_sha256 | test("^[0-9a-f]{64}$"))
  and (.contract.schema.sha256 | test("^[0-9a-f]{64}$"))
  and (.contract.validator.sha256 | test("^[0-9a-f]{64}$"))
' "$evidence/a/newa-qwerty-direct-native-review.json" >/dev/null

transaction_started=1
if [[ "$scope" == all ]]; then
  install -m 0644 "$evidence/a/shipping-profiles.lock.json" "$shipping_profile_lock"
fi
install -m 0644 "$evidence/a/internal-profiles.lock.json" "$internal_profile_lock"
if [[ "$scope" == all ]]; then
  run_python tools/build_shipping_profile_catalog.py \
    --catalog catalog/resources.json \
    --review catalog/shipping-profile-review.json \
    --output catalog/shipping-profiles.lock.json \
    --check >"$evidence/shipping-profile-check.log" 2>&1
fi
run_python tools/build_shipping_profile_catalog.py \
  --catalog catalog/resources.json \
  --review catalog/internal-profile-review.json \
  --output catalog/internal-profiles.lock.json \
  --check >"$evidence/internal-profile-check.log" 2>&1

for run in a b; do
  if [[ "$scope" == all ]]; then
    run_python tools/build_keyboard_layouts.py \
      --source-directory layouts/src \
      --profile-lock catalog/shipping-profiles.lock.json \
      --output "$evidence/$run/layouts-v1.lock.json" \
      >"$evidence/$run/release-layout-build.log" 2>&1
  fi
  run_python tools/build_keyboard_layouts.py \
    --source-directory layouts/internal/src \
    --profile-lock catalog/internal-profiles.lock.json \
    --output "$evidence/$run/internal-layouts-v1.lock.json" \
    >"$evidence/$run/internal-layout-build.log" 2>&1
done
if [[ "$scope" == all ]]; then
  cmp "$evidence/a/layouts-v1.lock.json" "$evidence/b/layouts-v1.lock.json"
fi
cmp "$evidence/a/internal-layouts-v1.lock.json" \
  "$evidence/b/internal-layouts-v1.lock.json"
assert_internal_newa_layout_binding "$evidence/a/internal-layouts-v1.lock.json"
assert_internal_dumi_layout_binding "$evidence/a/internal-layouts-v1.lock.json"
if [[ "$scope" == all ]]; then
  assert_no_release_newa_layout_binding "$evidence/a/layouts-v1.lock.json"
fi
if [[ "$scope" == all ]]; then
  install -m 0644 "$evidence/a/layouts-v1.lock.json" "$release_layout_lock"
fi
install -m 0644 "$evidence/a/internal-layouts-v1.lock.json" "$internal_layout_lock"
if [[ "$scope" == all ]]; then
  run_python tools/build_keyboard_layouts.py \
    --source-directory layouts/src \
    --profile-lock catalog/shipping-profiles.lock.json \
    --output layouts/layouts-v1.lock.json \
    --check >"$evidence/release-layout-check.log" 2>&1
fi
run_python tools/build_keyboard_layouts.py \
  --source-directory layouts/internal/src \
  --profile-lock catalog/internal-profiles.lock.json \
  --output layouts/internal/layouts-v1.lock.json \
  --check >"$evidence/internal-layout-check.log" 2>&1

for run in a b; do
  run_python tools/build_key_alternates.py \
    --source catalog/key-alternates-v0.json \
    --layout-lock layouts/internal/layouts-v1.lock.json \
    --output "$evidence/$run/key-alternates-v1.json" \
    >"$evidence/$run/key-alternates-build.log" 2>&1
  run_python tools/build_transliteration_profiles.py \
    --source catalog/transliteration-profiles-v0.json \
    --profile-lock catalog/internal-profiles.lock.json \
    --asset-directory android/ime-app/src/main/assets/nepa-translit \
    --map-source-directory catalog/transliteration \
    --output "$evidence/$run/transliteration-profiles-v1.json" \
    >"$evidence/$run/transliteration-profiles-build.log" 2>&1
done
cmp "$evidence/a/key-alternates-v1.json" \
  "$evidence/b/key-alternates-v1.json"
cmp "$evidence/a/transliteration-profiles-v1.json" \
  "$evidence/b/transliteration-profiles-v1.json"
install -m 0644 "$evidence/a/key-alternates-v1.json" \
  android/ime-app/src/main/assets/nepa-layouts/key-alternates-v1.json
install -m 0644 "$evidence/a/transliteration-profiles-v1.json" \
  android/ime-app/src/main/assets/nepa-translit/profiles-v1.json
run_python tools/build_key_alternates.py \
  --source catalog/key-alternates-v0.json \
  --layout-lock layouts/internal/layouts-v1.lock.json \
  --output android/ime-app/src/main/assets/nepa-layouts/key-alternates-v1.json \
  --check >"$evidence/key-alternates-check.log" 2>&1
run_python tools/build_transliteration_profiles.py \
  --source catalog/transliteration-profiles-v0.json \
  --profile-lock catalog/internal-profiles.lock.json \
  --asset-directory android/ime-app/src/main/assets/nepa-translit \
  --map-source-directory catalog/transliteration \
  --output android/ime-app/src/main/assets/nepa-translit/profiles-v1.json \
  --check >"$evidence/transliteration-profiles-check.log" 2>&1

run_python tools/update_android_lock_pins.py \
  --repository-root "$repo" \
  --scope "$scope" \
  >"$evidence/android-pin-update.json"
run_python tools/update_android_lock_pins.py \
  --repository-root "$repo" \
  --scope "$scope" \
  --check >"$evidence/android-pin-check.json"
pin_keys_json='["internal_layout","internal_profile","transliteration_catalog"]'
if [[ "$scope" == all ]]; then
  pin_keys_json='[
    "internal_layout", "internal_profile", "release_layout", "release_profile",
    "transliteration_catalog"
  ]'
fi
jq -e --arg scope "$scope" --argjson expected_keys "$pin_keys_json" '
  .scope == $scope and
  (.status == "updated" or .status == "current") and
  (.changed | type == "boolean") and
  (.hashes | keys == $expected_keys) and
  ([.hashes[] | test("^[0-9a-f]{64}$")] | all)
' "$evidence/android-pin-update.json" >/dev/null
jq -e --arg scope "$scope" --argjson expected_keys "$pin_keys_json" '
  .scope == $scope and
  .status == "current" and
  .changed == false and
  (.hashes | keys == $expected_keys) and
  ([.hashes[] | test("^[0-9a-f]{64}$")] | all)
' "$evidence/android-pin-check.json" >/dev/null
jq -S '.hashes' "$evidence/android-pin-update.json" \
  >"$evidence/android-pin-update-hashes.json"
jq -S '.hashes' "$evidence/android-pin-check.json" \
  >"$evidence/android-pin-check-hashes.json"
cmp "$evidence/android-pin-update-hashes.json" \
  "$evidence/android-pin-check-hashes.json"

json_inputs=(
  catalog/resources.json
  schemas/resource-catalog.schema.json
  schemas/layout-v1.schema.json
  schemas/layout-lock-v1.schema.json
  schemas/layout-native-review-v1.schema.json
  catalog/internal-profiles.lock.json
  layouts/internal/layouts-v1.lock.json
)
if [[ "$scope" == all ]]; then
  json_inputs+=(
    catalog/shipping-profiles.lock.json
    layouts/layouts-v1.lock.json
  )
fi
for schema_or_lock in "${json_inputs[@]}"; do
  jq empty "$schema_or_lock"
done
[[ "$(jq -r '.review.authority' catalog/internal-profiles.lock.json)" == internal ]]
[[ "$(jq -r '.profile_lock.path' layouts/internal/layouts-v1.lock.json)" \
  == catalog/internal-profiles.lock.json ]]
if [[ "$scope" == all ]]; then
  [[ "$(jq -r '.review.authority' catalog/shipping-profiles.lock.json)" == release ]]
  [[ "$(jq -r '.profile_lock.path' layouts/layouts-v1.lock.json)" \
    == catalog/shipping-profiles.lock.json ]]
fi

for test_file in "${test_files[@]}"; do
  run_python -m unittest discover -s tests -p "$test_file" \
    >"$evidence/${test_file%.py}.log" 2>&1
done

build_source_inputs
validate_source_inputs
sha256sum "${source_inputs[@]}" >"$evidence/input-source-sha256.after.txt"
cmp "$evidence/input-source-sha256.txt" \
  "$evidence/input-source-sha256.after.txt"
sha256sum "$python_bin" >"$evidence/python-runtime-sha256.after.txt"
cmp "$evidence/python-runtime-sha256.txt" \
  "$evidence/python-runtime-sha256.after.txt"

cmp "$evidence/a/internal-profiles.lock.json" "$internal_profile_lock"
cmp "$evidence/a/internal-layouts-v1.lock.json" "$internal_layout_lock"
cmp "$evidence/a/key-alternates-v1.json" \
  android/ime-app/src/main/assets/nepa-layouts/key-alternates-v1.json
cmp "$evidence/a/transliteration-profiles-v1.json" \
  android/ime-app/src/main/assets/nepa-translit/profiles-v1.json
if [[ "$scope" == all ]]; then
  cmp "$evidence/a/shipping-profiles.lock.json" "$shipping_profile_lock"
  cmp "$evidence/a/layouts-v1.lock.json" "$release_layout_lock"
fi
sha256sum "${tracked_paths[@]}" >"$evidence/installed-sha256.txt"
