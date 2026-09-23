#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
generated_dir="${script_dir}/generated"
bundle_name="Nepa Romanized Pro.bundle"
build_dir="${script_dir}/build"
stage_dir="$(mktemp -d "${TMPDIR:-/tmp}/nepa-romanized-stage.XXXXXX")"
export COPYFILE_DISABLE=1

cleanup() {
  rm -rf "${stage_dir}"
}
trap cleanup EXIT

python3 "${repo_root}/tools/build_macos_romanized_bundle.py" --check

mkdir -p "${build_dir}" "${stage_dir}/Library/Keyboard Layouts"
ditto --norsrc --noextattr \
  "${generated_dir}/${bundle_name}" \
  "${stage_dir}/Library/Keyboard Layouts/${bundle_name}"

staged_bundle="${stage_dir}/Library/Keyboard Layouts/${bundle_name}"
xattr -cr "${staged_bundle}"
if [[ -n "${MACOS_APPLICATION_SIGNING_IDENTITY:-}" ]]; then
  codesign --force --timestamp --options runtime \
    --sign "${MACOS_APPLICATION_SIGNING_IDENTITY}" "${staged_bundle}"
fi

component_pkg="${build_dir}/NepaRomanizedPro-component.pkg"
final_pkg="${build_dir}/NepaRomanizedPro-0.1.0.pkg"

pkgbuild \
  --root "${stage_dir}" \
  --install-location / \
  --identifier com.ampixa.nepa.romanized-pro.install \
  --version 0.1.0 \
  "${component_pkg}"

product_args=(--package "${component_pkg}")
if [[ -n "${MACOS_INSTALLER_SIGNING_IDENTITY:-}" ]]; then
  product_args+=(--sign "${MACOS_INSTALLER_SIGNING_IDENTITY}")
fi
productbuild "${product_args[@]}" "${final_pkg}"

pkgutil --check-signature "${final_pkg}" || true

if [[ -n "${MACOS_NOTARY_PROFILE:-}" ]]; then
  xcrun notarytool submit "${final_pkg}" \
    --keychain-profile "${MACOS_NOTARY_PROFILE}" --wait
  xcrun stapler staple "${final_pkg}"
  xcrun stapler validate "${final_pkg}"
fi

echo "macOS package built: ${final_pkg}"
