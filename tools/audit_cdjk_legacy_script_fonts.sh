#!/usr/bin/env bash
# shellcheck disable=SC2329 # EXIT-trap helper is invoked indirectly.
set -euo pipefail

if [[ "$(hostname -s)" != cdjk ]]; then
  echo "run this read-only Android system-font audit on cdjk" >&2
  exit 1
fi

for required in fc-query find grep losetup mount mountpoint perl sha256sum umount; do
  command -v "$required" >/dev/null
done

font_covers() {
  local code_point="$1"
  local font="$2"
  local charset
  charset="$(fc-query --format='%{charset}\n' "$font" 2>/dev/null || true)"
  perl -e '
    my $point = hex shift @ARGV;
    my $charset = join " ", @ARGV;
    for my $token (split /\s+/, $charset) {
      next unless $token =~ /^([0-9a-f]+)(?:-([0-9a-f]+))?$/i;
      my $start = hex $1;
      my $end = defined $2 ? hex $2 : $start;
      exit 0 if $point >= $start && $point <= $end;
    }
    exit 1;
  ' "$code_point" "$charset"
}

offset=$((2048 * 512))
partition_size=$((5242880 * 512))

for api in 26 27; do
  image="$HOME/Android/Sdk/system-images/android-$api/default/x86_64/system.img"
  mount_point="$(mktemp -d "/tmp/nepa-system-font-api${api}.XXXXXX")"
  loop_device=""
  cleanup() {
    if mountpoint -q "$mount_point"; then
      sudo -n umount "$mount_point"
    fi
    if [[ -n "$loop_device" ]]; then
      sudo -n losetup -d "$loop_device"
    fi
    rmdir "$mount_point"
  }
  trap cleanup EXIT

  loop_device="$(sudo -n losetup --find --show --read-only \
    --offset "$offset" --sizelimit "$partition_size" "$image")"
  sudo -n mount -o ro,noload "$loop_device" "$mount_point"

  newa_fonts=()
  limbu_fonts=()
  while IFS= read -r -d '' font; do
    if font_covers 11400 "$font"; then
      newa_fonts+=("$(basename "$font")")
    fi
    if font_covers 1900 "$font"; then
      limbu_fonts+=("$(basename "$font")")
    fi
  done < <(find "$mount_point/fonts" -maxdepth 1 -type f \
    \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) -print0)

  printf 'api=%s\n' "$api"
  printf 'system_image_sha256=%s\n' "$(sha256sum "$image" | cut -d' ' -f1)"
  printf 'font_file_count=%s\n' \
    "$(find "$mount_point/fonts" -maxdepth 1 -type f | wc -l | tr -d ' ')"
  printf 'newa_u11400_covering_fonts=%s\n' \
    "$([[ ${#newa_fonts[@]} -eq 0 ]] && printf none || IFS=,; printf '%s' "${newa_fonts[*]}")"
  printf 'limbu_u1900_covering_fonts=%s\n' \
    "$([[ ${#limbu_fonts[@]} -eq 0 ]] && printf none || IFS=,; printf '%s' "${limbu_fonts[*]}")"
  printf 'newa_font_config_references=%s\n' \
    "$(grep -ci 'Newa' "$mount_point/etc/fonts.xml" || true)"
  printf 'limbu_font_config_references=%s\n' \
    "$(grep -ci 'NotoSansLimbu-Regular.ttf' "$mount_point/etc/fonts.xml" || true)"
  printf '\n'

  cleanup
  trap - EXIT
done
