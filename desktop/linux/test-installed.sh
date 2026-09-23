#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
for required in \
  /usr/lib/nepa-keyboard/nepa-ibus-engine \
  /usr/share/ibus/component/nepa-keyboard.xml
do
  if [[ ! -f "$required" ]]; then
    echo "Installed Nepa IBus file is missing: $required" >&2
    exit 2
  fi
done

result_file=$(mktemp)
session_log=$(mktemp)
settings_dir=$(mktemp -d)
cleanup_outer() {
  rm -f "$result_file" "$session_log"
  rm -rf "$settings_dir"
}
trap cleanup_outer EXIT
export NEPA_ROOT="$ROOT"
export NEPA_RESULT_FILE="$result_file"
export NEPA_SETTINGS_DIR="$settings_dir"

if ! xvfb-run -a dbus-run-session -- bash -c '
  set -euo pipefail
  export XDG_CONFIG_HOME="$NEPA_SETTINGS_DIR"
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
    case "$ibus_address" in unix:*) break ;; esac
    attempt=$((attempt + 1))
    if [[ "$attempt" -ge 50 ]]; then
      sed -n "1,200p" "$daemon_log" >&2
      exit 2
    fi
    sleep 0.1
  done
  export IBUS_ADDRESS="$ibus_address"
  python3 "$NEPA_ROOT/tools/test_nepa_linux_ibus.py" --installed --json \
    >"$NEPA_RESULT_FILE"
' >"$session_log" 2>&1
then
  echo "Installed Linux Nepa IBus acceptance failed; log follows:" >&2
  sed -n '1,260p' "$session_log" >&2
  [[ ! -s "$result_file" ]] || cat "$result_file" >&2
  exit 1
fi

cat "$result_file"
