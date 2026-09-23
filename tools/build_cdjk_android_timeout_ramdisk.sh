#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 || "$1" != /* || "$2" != /* || ! "$3" =~ ^[1-9][0-9]*$ ]]; then
  echo "usage: $0 /absolute/source-ramdisk.img /absolute/new-output-directory multiplier" >&2
  exit 2
fi

source_ramdisk="$1"
output="$2"
multiplier="$3"
lz4="${LZ4_BIN:-$(command -v lz4 || true)}"

if [[ "$(uname -s)" != Linux
      || "$(hostname -s)" != cdjk
      || "$output" == /Users/* ]]; then
  echo "this builder must run on cdjk with a non-/Users output" >&2
  exit 1
fi
if [[ ! -f "$source_ramdisk" || -e "$output" ]]; then
  echo "source must exist and output must be new" >&2
  exit 1
fi
for executable in "$lz4" "$(command -v cpio)"; do
  [[ -x "$executable" ]]
done

mkdir -p \
  "$output/source-root/system/etc/ramdisk" \
  "$output/overlay-root/system/etc/ramdisk"
status=1
on_exit() {
  local exit_status=$?
  trap - EXIT
  if (( status == 0 && exit_status == 0 )); then
    printf 'remote_exit_status=0\n' >"$output/run-status.txt"
  else
    printf 'remote_exit_status=%s\n' "${exit_status:-1}" >"$output/run-status.txt" || true
  fi
  exit "$exit_status"
}
trap on_exit EXIT

"$lz4" -d "$source_ramdisk" "$output/source.cpio" \
  >"$output/decompress.log" 2>&1
(
  cd "$output/source-root"
  cpio -idm --no-absolute-filenames system/etc/ramdisk/build.prop \
    <"$output/source.cpio" >"$output/extract.log" 2>&1
)

source_build_prop="$output/source-root/system/etc/ramdisk/build.prop"
overlay_build_prop="$output/overlay-root/system/etc/ramdisk/build.prop"
[[ -f "$source_build_prop" ]]
cp "$source_build_prop" "$overlay_build_prop"
if grep -Eq '^ro\.hw_timeout_multiplier=' "$overlay_build_prop"; then
  echo "source ramdisk already defines ro.hw_timeout_multiplier" >&2
  exit 1
fi
{
  printf '\n# Slow software-emulator timeout scaling (AOSP Build.HW_TIMEOUT_MULTIPLIER).\n'
  printf 'ro.hw_timeout_multiplier=%s\n' "$multiplier"
} >>"$overlay_build_prop"

find "$output/overlay-root" -exec touch -h -d '@0' {} +
(
  cd "$output/overlay-root"
  find . -print0 \
    | LC_ALL=C sort -z \
    | cpio --null -o -H newc --owner=0:0 --reproducible \
      >"$output/overlay.cpio" 2>"$output/create.log"
)
cp "$output/source.cpio" "$output/ramdisk.cpio"
dd if="$output/overlay.cpio" of="$output/ramdisk.cpio" \
  oflag=append conv=notrunc status=none
"$lz4" -l -12 "$output/ramdisk.cpio" "$output/ramdisk.img" \
  >"$output/compress.log" 2>&1
"$lz4" -d "$output/ramdisk.img" "$output/roundtrip.cpio" \
  >"$output/roundtrip.log" 2>&1
cmp "$output/ramdisk.cpio" "$output/roundtrip.cpio"

cp "$overlay_build_prop" "$output/ramdisk-build.prop"
grep -Fx "ro.hw_timeout_multiplier=$multiplier" "$output/ramdisk-build.prop"
sha256sum \
  "$source_ramdisk" \
  "$lz4" \
  "$output/source.cpio" \
  "$output/overlay.cpio" \
  "$output/ramdisk.cpio" \
  "$output/ramdisk.img" \
  "$output/ramdisk-build.prop" \
  >"$output/artifact-sha256.txt"
printf 'multiplier=%s\n' "$multiplier" >"$output/build-parameters.txt"
status=0
