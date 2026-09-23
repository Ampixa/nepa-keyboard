#!/usr/bin/env bash
set -euo pipefail

asset_dir="$(cd "$(dirname "$0")" && pwd)"
rendered_dir="$asset_dir/rendered"
magick_bin="${MAGICK_BIN:-magick}"

fail() {
  echo "Play asset validation failed: $*" >&2
  exit 1
}

read_image_fields() {
  "$magick_bin" identify -quiet -format '%w %h %[channels] %z\n' "$1"
}

icon="$rendered_dir/icon-512.png"
feature="$rendered_dir/feature-graphic-1024x500.png"

[[ -f "$icon" ]] || fail "missing $icon"
[[ -f "$feature" ]] || fail "missing $feature"

read -r width height channels channel_count depth < <(read_image_fields "$icon")
[[ "$width" == 512 && "$height" == 512 ]] || fail "icon must be 512x512"
[[ "$depth" == 8 ]] || fail "icon must use 8-bit channels"
[[ "$channels" == *a* ]] || fail "icon must contain an alpha channel"
(( $(wc -c < "$icon") <= 1048576 )) || fail "icon exceeds 1 MiB"

read -r width height channels channel_count depth < <(read_image_fields "$feature")
[[ "$width" == 1024 && "$height" == 500 ]] || fail "feature graphic must be 1024x500"
[[ "$depth" == 8 ]] || fail "feature graphic must use 8-bit channels"
[[ "$channels" != *a* ]] || fail "feature graphic must not contain alpha"

screenshots=()
while IFS= read -r screenshot; do
  screenshots+=("$screenshot")
done < <(find "$rendered_dir/phone-screenshots" -type f -name '*.png' | sort)
(( ${#screenshots[@]} >= 2 )) || fail "at least two phone screenshots are required"
(( ${#screenshots[@]} <= 8 )) || fail "at most eight phone screenshots are allowed"

for screenshot in "${screenshots[@]}"; do
  read -r width height channels channel_count depth < <(read_image_fields "$screenshot")
  [[ "$depth" == 8 ]] || fail "$screenshot must use 8-bit channels"
  [[ "$channels" != *a* ]] || fail "$screenshot must not contain alpha"
  (( width >= 320 && height >= 320 )) || fail "$screenshot is below the 320 px minimum"
  (( width <= 3840 && height <= 3840 )) || fail "$screenshot exceeds the 3840 px maximum"
  if (( width > height )); then
    (( width <= height * 2 )) || fail "$screenshot exceeds the 2:1 dimension ratio"
  else
    (( height <= width * 2 )) || fail "$screenshot exceeds the 2:1 dimension ratio"
  fi
done

(cd "$asset_dir" && shasum -a 256 -c checksums.sha256 >/dev/null) \
  || fail "rendered asset hashes differ from the inspected upload set"

echo "Play asset validation passed: 1 icon, 1 feature graphic, ${#screenshots[@]} phone screenshots"
