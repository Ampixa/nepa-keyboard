#!/usr/bin/env bash
set -uo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"

package_name="${PLAY_PACKAGE:-com.ampixa.nepakeyboard.ime}"
gps_account="${GPS_ACCOUNT:-nepa}"
credentials_path="${GOOGLE_APPLICATION_CREDENTIALS:-$HOME/.config/gps/service-account.json}"
keystore_properties="${KEYSTORE_PROPERTIES:-$repo_root/android/keystore.properties}"
aab_path="${CANDIDATE_AAB:-$repo_root/android/ime-app/build/outputs/bundle/candidate/ime-app-candidate.aab}"
owner_inputs="$script_dir/owner-inputs.md"
build_file="$repo_root/android/ime-app/build.gradle.kts"

pass_count=0
wait_count=0
fail_count=0

pass() {
  pass_count=$((pass_count + 1))
  printf 'PASS  %s\n' "$*"
}

wait_for() {
  wait_count=$((wait_count + 1))
  printf 'WAIT  %s\n' "$*"
}

fail() {
  fail_count=$((fail_count + 1))
  printf 'FAIL  %s\n' "$*" >&2
}

portable_mode() {
  if stat -f '%Lp' "$1" >/dev/null 2>&1; then
    stat -f '%Lp' "$1"
  else
    stat -c '%a' "$1"
  fi
}

trimmed_character_count() {
  tr -d '\r\n' < "$1" | wc -m | tr -d '[:space:]'
}

json_registry_has() {
  local kind="$1"
  local expected="$2"
  local payload="$3"
  if command -v jq >/dev/null 2>&1; then
    if [[ "$kind" == "account" ]]; then
      printf '%s' "$payload" | jq -e --arg expected "$expected" '
        .accounts
        | map(if type == "string" then . else (.id // .name // .account // "") end)
        | index($expected) != null
      ' >/dev/null 2>&1
    else
      printf '%s' "$payload" | jq -e --arg expected "$expected" '
        .apps
        | map(if type == "string" then . else (.packageName // .package // .id // "") end)
        | index($expected) != null
      ' >/dev/null 2>&1
    fi
  else
    printf '%s' "$payload" | grep -Fq "\"$expected\""
  fi
}

echo "Google Play publishing preflight"
echo "package=$package_name"
echo "account=$gps_account"

if [[ -f "$build_file" ]]; then
  configured_package="$(sed -n 's/^[[:space:]]*applicationId = "\([^"]*\)".*/\1/p' "$build_file" | head -n 1)"
  configured_version_code="$(sed -n 's/^[[:space:]]*versionCode = \([0-9][0-9]*\).*/\1/p' "$build_file" | head -n 1)"
  configured_version_name="$(sed -n 's/^[[:space:]]*versionName = "\([^"]*\)".*/\1/p' "$build_file" | head -n 1)"
  if [[ "$configured_package" == "$package_name" ]]; then
    pass "candidate package matches build configuration"
  else
    fail "candidate package mismatch: expected $package_name, found ${configured_package:-missing}"
  fi
  if [[ -n "$configured_version_code" && -n "$configured_version_name" ]]; then
    pass "candidate version is $configured_version_code / $configured_version_name"
  else
    fail "candidate version is missing from the Android build configuration"
  fi
  if grep -Fq 'create("candidate")' "$build_file" \
      && grep -Fq 'dependsOn(verifyCandidateSigningConfiguration)' "$build_file"; then
    pass "candidate build type and fail-closed signing gate are present"
  else
    fail "candidate build type or signing gate is missing"
  fi
else
  fail "missing Android build configuration"
fi

listing_failed=0
for relative in \
  en-US/title.txt \
  en-US/short-description.txt \
  en-US/full-description.txt \
  en-US/internal-release-notes.txt \
  data-safety-review.md; do
  if [[ ! -s "$script_dir/$relative" ]]; then
    fail "missing or empty publishing input: $relative"
    listing_failed=1
  fi
done
if [[ ! -s "$repo_root/publishing/privacy-policy.md" ]]; then
  fail "missing or empty privacy-policy draft"
  listing_failed=1
fi
if (( listing_failed == 0 )); then
  title_count="$(trimmed_character_count "$script_dir/en-US/title.txt")"
  short_count="$(trimmed_character_count "$script_dir/en-US/short-description.txt")"
  full_count="$(trimmed_character_count "$script_dir/en-US/full-description.txt")"
  notes_count="$(trimmed_character_count "$script_dir/en-US/internal-release-notes.txt")"
  if (( title_count > 0 && title_count <= 30 \
      && short_count > 0 && short_count <= 80 \
      && full_count > 0 && full_count <= 4000 \
      && notes_count > 0 && notes_count <= 500 )); then
    pass "en-US listing copy and release notes are within Play length limits"
  else
    fail "listing length gate failed (title=$title_count short=$short_count full=$full_count notes=$notes_count)"
  fi
  pass "privacy-policy and Data safety review drafts are present"
fi

asset_output="$("$script_dir/assets/validate-assets.sh" 2>&1)"
asset_status=$?
if (( asset_status == 0 )); then
  pass "$asset_output"
else
  fail "$asset_output"
fi

if command -v gps >/dev/null 2>&1; then
  pass "gps CLI is installed"
  account_payload="$(gps accounts list --json 2>/dev/null)"
  if json_registry_has account "$gps_account" "$account_payload"; then
    pass "gps account '$gps_account' is registered"
  else
    wait_for "register gps account '$gps_account' after the service-account key is available"
  fi
  app_payload="$(gps apps list --json 2>/dev/null)"
  if json_registry_has app "$package_name" "$app_payload"; then
    pass "package is present in the local gps app registry"
  else
    wait_for "register package $package_name in the local gps app registry"
  fi
else
  fail "gps CLI is not installed"
fi

if command -v gps-mcp >/dev/null 2>&1; then
  pass "gps-mcp server is installed"
else
  fail "gps-mcp server is not installed"
fi
if [[ -f "$HOME/.codex/config.toml" ]] \
    && grep -Fq 'command = "gps-mcp"' "$HOME/.codex/config.toml"; then
  pass "gps-mcp is registered with Codex"
else
  wait_for "register gps-mcp with Codex"
fi
if [[ -f "$HOME/.claude.json" ]] \
    && grep -Eq '"command"[[:space:]]*:[[:space:]]*"gps-mcp"' "$HOME/.claude.json"; then
  pass "gps-mcp is registered with Claude"
else
  wait_for "register gps-mcp with Claude"
fi

case "$credentials_path" in
  "$repo_root"|"$repo_root"/*)
    fail "service-account credentials must remain outside the repository"
    ;;
  *)
    if [[ ! -f "$credentials_path" ]]; then
      wait_for "service-account JSON is absent at $credentials_path"
    else
      credential_mode="$(portable_mode "$credentials_path")"
      if [[ "$credential_mode" == "600" ]]; then
        pass "service-account JSON permissions are 0600"
      else
        fail "service-account JSON permissions must be 0600, found $credential_mode"
      fi
      if command -v jq >/dev/null 2>&1 \
          && jq -e '.type == "service_account" and (.client_email | type == "string") and (.private_key | type == "string")' \
              "$credentials_path" >/dev/null 2>&1; then
        pass "service-account JSON has the required credential fields"
      elif command -v jq >/dev/null 2>&1; then
        fail "service-account JSON is malformed or missing required fields"
      else
        wait_for "install jq to validate credential structure without displaying it"
      fi
    fi
    ;;
esac

if [[ -f "$owner_inputs" ]]; then
  unchecked_count="$(grep -c '^- \[ \]' "$owner_inputs" || true)"
  placeholder_count="$(grep -c '____________________________' "$owner_inputs" || true)"
  if (( unchecked_count == 0 )); then
    pass "owner-controlled choices and declarations are recorded"
  else
    wait_for "$unchecked_count owner-controlled approvals or declarations remain unchecked"
  fi
  if (( placeholder_count == 0 )); then
    pass "required owner account, contact, automation, and tester fields are filled"
  else
    wait_for "$placeholder_count owner-input fields still contain placeholders"
  fi
else
  fail "missing owner input record"
fi

if [[ ! -f "$keystore_properties" ]]; then
  wait_for "permanent candidate signing properties are absent"
else
  properties_mode="$(portable_mode "$keystore_properties")"
  if [[ "$properties_mode" == "600" ]]; then
    pass "candidate signing properties permissions are 0600"
  else
    fail "candidate signing properties permissions must be 0600, found $properties_mode"
  fi
  property_failure=0
  for property_name in storeFile storePassword keyAlias keyPassword; do
    property_value="$(sed -n "s/^${property_name}=//p" "$keystore_properties" | head -n 1)"
    if [[ -z "$property_value" || "$property_value" == replace-with-* ]]; then
      fail "candidate signing property $property_name is missing or still a placeholder"
      property_failure=1
    fi
  done
  if (( property_failure == 0 )); then
    pass "candidate signing properties contain all required non-placeholder values"
    configured_store="$(sed -n 's/^storeFile=//p' "$keystore_properties" | head -n 1)"
    if [[ "$configured_store" == /* ]]; then
      resolved_store="$configured_store"
    else
      resolved_store="$repo_root/android/$configured_store"
    fi
    if [[ -f "$resolved_store" ]]; then
      pass "candidate upload keystore exists outside this report"
    else
      fail "candidate upload keystore path does not exist"
    fi
  fi
fi

if [[ -f "$aab_path" ]]; then
  if unzip -tqq "$aab_path" >/dev/null 2>&1; then
    pass "candidate AAB is structurally readable"
    pass "candidate AAB SHA-256: $(shasum -a 256 "$aab_path" | awk '{print $1}')"
  else
    fail "candidate AAB is not a readable bundle archive"
  fi
else
  wait_for "signed candidate AAB has not been produced"
fi

printf '\nSUMMARY pass=%d wait=%d fail=%d\n' "$pass_count" "$wait_count" "$fail_count"
if (( fail_count > 0 )); then
  echo "RESULT=INVALID"
  exit 1
fi
if (( wait_count > 0 )); then
  echo "RESULT=WAITING_OWNER_INPUTS"
  exit 2
fi
echo "RESULT=READY_FOR_VALIDATE_ONLY_PUBLISHING"
