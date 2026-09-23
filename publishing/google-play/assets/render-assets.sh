#!/usr/bin/env bash
set -euo pipefail

asset_dir="$(cd "$(dirname "$0")" && pwd)"
source_dir="$asset_dir/source-renders"
output_dir="$asset_dir/rendered"
magick_bin="${MAGICK_BIN:-magick}"

font_regular="/System/Library/Fonts/Supplemental/Arial.ttf"
font_bold="/System/Library/Fonts/Supplemental/Arial Bold.ttf"

for required in \
  "$source_dir/setup-complete-api36.png" \
  "$source_dir/ime-internal-eng-Latn-US.png" \
  "$source_dir/ime-internal-npi-Deva-NP.png" \
  "$source_dir/ime-internal-lif-Limb-NP.png" \
  "$source_dir/ime-internal-new-Newa-NP.png" \
  "$font_regular" \
  "$font_bold"; do
  if [[ ! -f "$required" ]]; then
    echo "Missing required asset input: $required" >&2
    exit 1
  fi
done

mkdir -p "$output_dir/phone-screenshots"

# The Play icon mirrors the adaptive launcher icon: indigo background with the
# white keyboard-grid foreground, without a pre-applied rounded mask.
"$magick_bin" \
  -size 512x512 xc:'#4F46A5' \
  -fill '#FFFFFF' \
  -draw 'rectangle 137,180 185,228 rectangle 204,180 251,228 rectangle 270,180 318,228 rectangle 337,180 375,228 rectangle 137,247 180,294 rectangle 199,247 247,294 rectangle 266,247 313,294 rectangle 332,247 375,294 rectangle 156,313 356,351' \
  -alpha on -define png:color-type=6 \
  "$output_dir/icon-512.png"

# The feature graphic uses a real accepted keyboard render as the experience
# preview and keeps all important content away from the crop-prone edges.
"$magick_bin" \
  -size 1024x500 xc:'#4F46A5' \
  -fill '#6E66BA' -draw 'circle 960,40 700,300' \
  -fill '#FFFFFF' -font "$font_bold" -pointsize 62 \
  -draw "text 62,185 'Nepa Keyboard'" \
  -fill '#E8E5FF' -font "$font_regular" -pointsize 31 \
  -draw "text 64,242 'Type in the languages of Nepal'" \
  -fill '#FFFFFF' -font "$font_regular" -pointsize 24 \
  -draw "text 64,305 '16 language profiles  •  offline-first'" \
  \( "$source_dir/ime-internal-eng-Latn-US.png" -resize 460x317! \) \
  -geometry +548+92 -composite \
  -alpha off -depth 8 -type TrueColor -define png:color-type=2 \
  "$output_dir/feature-graphic-1024x500.png"

# Keep the setup screen as captured. Cropping 480 px from the top retains the
# complete setup card and keyboard while converting 1080x2400 to Play's 9:16
# recommended portrait ratio without scaling or distortion.
"$magick_bin" \
  "$source_dir/setup-complete-api36.png" \
  -crop 1080x1920+0+480 +repage \
  -fill '#F7F6FC' -draw 'rectangle 0,0 1080,64' \
  -alpha off -depth 8 -type TrueColor -define png:color-type=2 \
  "$output_dir/phone-screenshots/01-setup-and-privacy.png"

render_keyboard_screenshot() {
  local title="$1"
  local subtitle="$2"
  local source="$3"
  local output="$4"

  "$magick_bin" \
    -size 1080x1920 xc:'#F6F4FB' \
    -fill '#4F46A5' -draw 'roundrectangle 72,94 216,108 7,7' \
    -fill '#1D1B20' -font "$font_bold" -pointsize 76 \
    -draw "text 72,268 '$title'" \
    -fill '#625F69' -font "$font_regular" -pointsize 38 \
    -draw "text 74,340 '$subtitle'" \
    -fill '#FFFFFF' -stroke '#E3E0EA' -strokewidth 2 \
    -draw 'roundrectangle 72,454 1008,1025 28,28' \
    -stroke none -fill '#29272E' -font "$font_bold" -pointsize 38 \
    -draw "text 120,548 'Nepa Keyboard'" \
    -fill '#696570' -font "$font_regular" -pointsize 30 \
    -draw "text 120,610 'Offline input with explicit language profiles'" \
    -fill '#ECE9F5' -draw 'roundrectangle 120,706 356,790 42,42 roundrectangle 380,706 650,790 42,42 roundrectangle 674,706 922,790 42,42' \
    -fill '#34313B' -font "$font_regular" -pointsize 28 \
    -draw "text 165,760 'Direct input' text 426,760 'Phonetic mode' text 731,760 'No network'" \
    "$source" -geometry +0+1175 -composite \
    -alpha off -depth 8 -type TrueColor -define png:color-type=2 \
    "$output"
}

render_keyboard_screenshot \
  'Type in Nepali' \
  'Direct and phonetic input' \
  "$source_dir/ime-internal-npi-Deva-NP.png" \
  "$output_dir/phone-screenshots/02-nepali-keyboard.png"

render_keyboard_screenshot \
  'Switch languages' \
  '16 profiles across languages of Nepal' \
  "$source_dir/ime-internal-lif-Limb-NP.png" \
  "$output_dir/phone-screenshots/03-language-profiles.png"

render_keyboard_screenshot \
  'Write in Newa' \
  'Bundled script font support' \
  "$source_dir/ime-internal-new-Newa-NP.png" \
  "$output_dir/phone-screenshots/04-newa-keyboard.png"

"$magick_bin" identify \
  "$output_dir/icon-512.png" \
  "$output_dir/feature-graphic-1024x500.png" \
  "$output_dir/phone-screenshots/"*.png
