#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SOURCE_DIR="$ROOT/desktop/macos-ime/Sources"
BUILD_DIR="$ROOT/desktop/macos-ime/build"
APP_ROOT="$BUILD_DIR/apps"
PACKAGE_ROOT="$BUILD_DIR/package-root"
VERSION=0.2.0

rm -rf "$APP_ROOT" "$PACKAGE_ROOT"
mkdir -p "$APP_ROOT" "$PACKAGE_ROOT/Library/Input Methods"

binary=$(mktemp /tmp/nepa-phonetic.XXXXXX)
cleanup() { rm -f "$binary"; }
trap cleanup EXIT

swiftc -O \
  -module-name NepaPhonetic \
  -framework Cocoa \
  -framework InputMethodKit \
  "$SOURCE_DIR/Transliteration.swift" \
  "$SOURCE_DIR/NepaInputController.swift" \
  "$SOURCE_DIR/AppDelegate.swift" \
  -o "$binary"

profiles=(nepali newa limbu)
names=("Nepali Phonetic - Nepa" "Nepal Bhasa Phonetic Newa - Nepa" "Limbu Phonetic Sirijanga - Nepa")
bundle_ids=(com.ampixa.nepakeyboard.inputmethod.nepali com.ampixa.nepakeyboard.inputmethod.newa com.ampixa.nepakeyboard.inputmethod.limbu)
languages=(ne new lif)
scripts=(Deva Newa Limb)
assets=(npi-Latn-Deva-v1.json new-Latn-Newa-v1.json lif-Latn-Limb-v1.json)
profile_ids=(npi-Latn-Deva-v0 new-Latn-Newa-v0 lif-Latn-Limb-v0)

for index in 0 1 2
do
  app="$APP_ROOT/${names[$index]}.app"
  contents="$app/Contents"
  resources="$contents/Resources"
  mkdir -p "$contents/MacOS" "$resources"
  install -m 0755 "$binary" "$contents/MacOS/NepaPhonetic"
  install -m 0644 \
    "$ROOT/android/ime-app/src/main/assets/nepa-translit/${assets[$index]}" \
    "$resources/${assets[$index]}"
  python3 - \
    "$resources/profile.json" \
    "$contents/Info.plist" \
    "${profile_ids[$index]}" \
    "${assets[$index]}" \
    "${names[$index]}" \
    "${bundle_ids[$index]}" \
    "${languages[$index]}" \
    "${scripts[$index]}" \
    "$VERSION" <<'PY'
import json
import plistlib
import sys
from pathlib import Path
Path(sys.argv[1]).write_text(
    json.dumps({"profile_id": sys.argv[3], "asset_name": sys.argv[4]}, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
name, bundle_id, language, script, version = sys.argv[5:10]
with Path(sys.argv[2]).open("wb") as output:
    plistlib.dump(
        {
            "CFBundleDevelopmentRegion": "en",
            "CFBundleDisplayName": name,
            "CFBundleExecutable": "NepaPhonetic",
            "CFBundleIdentifier": bundle_id,
            "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleName": name,
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": version,
            "CFBundleVersion": "2",
            "LSBackgroundOnly": True,
            "NSPrincipalClass": "NepaPhonetic.NSManualApplication",
            "InputMethodConnectionName": f"{bundle_id}_Connection",
            "InputMethodServerControllerClass": "NepaPhonetic.NepaInputController",
            "TISInputSourceID": bundle_id,
            "TISIntendedLanguage": language,
            "tsInputMethodCharacterRepertoireKey": [script],
        },
        output,
        sort_keys=True,
    )
PY
  plutil -lint "$contents/Info.plist" >/dev/null
  if [[ -n ${MACOS_APPLICATION_SIGNING_IDENTITY:-} ]]; then
    codesign --force --options runtime --timestamp \
      --sign "$MACOS_APPLICATION_SIGNING_IDENTITY" "$app"
  fi
  ditto --norsrc --noextattr --noqtn --noacl \
    "$app" "$PACKAGE_ROOT/Library/Input Methods/${names[$index]}.app"
done

component="$BUILD_DIR/NepaPhonetic-component.pkg"
unsigned="$BUILD_DIR/NepaPhonetic-$VERSION.pkg"
xattr -cr "$PACKAGE_ROOT"
COPYFILE_DISABLE=1 pkgbuild \
  --root "$PACKAGE_ROOT" \
  --identifier com.ampixa.nepakeyboard.phonetic.pkg \
  --version "$VERSION" \
  --install-location / \
  "$component"

if [[ -n ${MACOS_INSTALLER_SIGNING_IDENTITY:-} ]]; then
  productsign --sign "$MACOS_INSTALLER_SIGNING_IDENTITY" "$component" "$unsigned"
else
  cp "$component" "$unsigned"
fi

if [[ -n ${MACOS_NOTARY_PROFILE:-} ]]; then
  xcrun notarytool submit "$unsigned" --keychain-profile "$MACOS_NOTARY_PROFILE" --wait
  xcrun stapler staple "$unsigned"
fi

shasum -a 256 "$unsigned"
