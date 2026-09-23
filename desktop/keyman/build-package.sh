#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SOURCE_DIR="$ROOT/desktop/keyman/generated/source"
BUILD_DIR="$ROOT/desktop/keyman/build"
KMC_VERSION=17.0.335

python3 "$ROOT/tools/build_keyman_romanized_package.py" --check
mkdir -p "$BUILD_DIR"

for generated_name in \
  nepa_nepali_romanized.kmx nepa_nepali_romanized.js \
  nepa_newa_romanized.kmx nepa_newa_romanized.js \
  nepa_limbu_romanized.kmx nepa_limbu_romanized.js \
  nepa_romanized_pro.kmp checksums.sha256
do
  rm -f "$BUILD_DIR/$generated_name"
done

if [[ -n "${KMC:-}" ]]; then
  KMC_COMMAND=("$KMC")
else
  KMC_COMMAND=(npx --yes "@keymanapp/kmc@$KMC_VERSION")
fi

for keyboard_id in \
  nepa_nepali_romanized \
  nepa_newa_romanized \
  nepa_limbu_romanized
do
  "${KMC_COMMAND[@]}" build -w \
    -o "$BUILD_DIR/$keyboard_id.kmx" \
    "$SOURCE_DIR/$keyboard_id.kmn"
done

"${KMC_COMMAND[@]}" build -w \
  -o "$BUILD_DIR/nepa_romanized_pro.kmp" \
  "$SOURCE_DIR/nepa_romanized_pro.kps"

(
  cd "$BUILD_DIR"
  sha256sum \
    nepa_nepali_romanized.kmx \
    nepa_newa_romanized.kmx \
    nepa_limbu_romanized.kmx \
    nepa_romanized_pro.kmp \
    > checksums.sha256
)

echo "Built $BUILD_DIR/nepa_romanized_pro.kmp"
