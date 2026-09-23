#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
DEST_LIB=/usr/lib/nepa-keyboard
DEST_DATA=/usr/share/nepa-keyboard/transliteration
DEST_COMPONENT=/usr/share/ibus/component/nepa-keyboard.xml

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 2
fi

install -d "$DEST_LIB/nepa_keyboard" "$DEST_DATA" "$(dirname "$DEST_COMPONENT")"
install -m 0755 "$ROOT/desktop/linux/nepa_ibus_engine.py" "$DEST_LIB/nepa-ibus-engine"
install -m 0644 \
  "$ROOT/src/nepa_keyboard/__init__.py" \
  "$ROOT/src/nepa_keyboard/desktop_composer.py" \
  "$ROOT/src/nepa_keyboard/transliteration.py" \
  "$DEST_LIB/nepa_keyboard/"
for asset in npi-Latn-Deva-v1.json new-Latn-Newa-v1.json lif-Latn-Limb-v1.json
do
  install -m 0644 \
    "$ROOT/android/ime-app/src/main/assets/nepa-translit/$asset" \
    "$DEST_DATA/$asset"
done
install -m 0644 "$ROOT/desktop/linux/nepa-keyboard.xml" "$DEST_COMPONENT"
ibus write-cache

echo "Installed Nepa phonetic IBus engines. Log out and back in, then add the"
echo "desired Nepa Phonetic input source in your desktop keyboard settings."

