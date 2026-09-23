#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

for command_name in xvfb-run dbus-run-session ibus-daemon ibus python3
do
  if ! command -v "$command_name" >/dev/null; then
    echo "Missing Linux acceptance dependency: $command_name" >&2
    exit 2
  fi
done

export NEPA_KEYBOARD_ROOT="$ROOT"
result_file=$(mktemp)
session_log=$(mktemp)
cleanup_outer() {
  rm -f "$result_file" "$session_log"
}
trap cleanup_outer EXIT
export NEPA_RESULT_FILE="$result_file"

if ! xvfb-run -a dbus-run-session -- bash -c '
  set -euo pipefail
  daemon_log=$(mktemp)
  ibus-daemon --replace --xim --panel disable >"$daemon_log" 2>&1 &
  ibus_pid=$!
  cleanup() {
    kill "$ibus_pid" 2>/dev/null || true
    rm -f "$daemon_log"
  }
  trap cleanup EXIT

  attempt=0
  while :
  do
    ibus_address=$(ibus address 2>/dev/null || true)
    case "$ibus_address" in
      unix:*) break ;;
    esac
    attempt=$((attempt + 1))
    if [[ "$attempt" -ge 50 ]]; then
      echo "IBus failed to start; daemon log follows:" >&2
      sed -n "1,200p" "$daemon_log" >&2
      exit 2
    fi
    sleep 0.1
  done

  export IBUS_ADDRESS="$ibus_address"
  python3 "$NEPA_KEYBOARD_ROOT/tools/test_keyman_linux_ibus.py" \
    --json \
    --package "$NEPA_KEYBOARD_ROOT/desktop/keyman/build/nepa_romanized_pro.kmp" \
    > "$NEPA_RESULT_FILE"
' >"$session_log" 2>&1
then
  echo "Linux IBus acceptance session failed; log follows:" >&2
  sed -n '1,240p' "$session_log" >&2
  if [[ -s "$result_file" ]]; then
    cat "$result_file" >&2
  fi
  exit 1
fi

cat "$result_file"
