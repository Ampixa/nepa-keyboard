#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
binary=$(mktemp /tmp/nepa-macos-core-test.XXXXXX)
cleanup() { rm -f "$binary"; }
trap cleanup EXIT

swiftc \
  "$ROOT/desktop/macos-ime/Sources/Transliteration.swift" \
  "$ROOT/desktop/macos-ime/Tests/CoreSelfTest.swift" \
  -o "$binary"
"$binary" "$ROOT"

