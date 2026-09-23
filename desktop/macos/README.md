# Nepa Romanized Pro for macOS

This directory builds one macOS keyboard-layout bundle with three system input
sources:

- **Nepali (Romanized) - Nepa Pro** → Unicode Devanagari;
- **Nepal Bhasa (Newari Romanized) - Nepa Pro** → Unicode Newa/Prachalit Nepal
  Lipi; and
- **Limbu (Romanized Sirijanga) - Nepa Pro** → Unicode Limbu/Sirijanga.

These are direct QWERTY-positioned layouts in the same product family as MPP
Nepali Romanized and `suvash/nepali-romanized-pro`. They do not buffer a Latin
word and then translate it. The separate composing input method is now
implemented under [`desktop/macos-ime/`](../macos-ime/) using the same reviewed
Android maps. It is intentionally a different system input source, so direct
physical-key behavior is never silently conflated with phonetic composition.

## Source and generation

[`romanized-pro-v1.json`](romanized-pro-v1.json) is the reviewed desktop source.
It records the exact Nepali reference revision and the pinned Keyman Newa and
SIL Limbu desktop mappings. The Newa Option layer exposes all five extended
letters already carried by the Android internal beta. The Limbu Option layer
preserves the pinned SIL right-Alt mappings and provisionally places the two
assigned letters omitted upstream as follows:

- Option + comma: U+191D LIMBU LETTER GYAN;
- Option + backslash: U+191E LIMBU LETTER TRA.

Those two placements require native ergonomic review, but the characters are
not omitted from the engineering bundle.

Generate or verify the checked bundle on `cdjk`:

```sh
python3 tools/build_macos_romanized_bundle.py
python3 tools/build_macos_romanized_bundle.py --check
python3 -m unittest discover -s tests -p 'test_macos_romanized_bundle.py'
```

The deterministic output is under `desktop/macos/generated/`. Command-based
application shortcuts retain Latin key output. Nepali keeps Option as a quick
Latin layer. Newa and Limbu use Option for their extended script characters;
Option+Shift remains Latin uppercase.

## Package, sign, and notarize

Run packaging on an approved macOS host with the required certificates in its
keychain:

```sh
export MACOS_APPLICATION_SIGNING_IDENTITY='Developer ID Application: …'
export MACOS_INSTALLER_SIGNING_IDENTITY='Developer ID Installer: …'
export MACOS_NOTARY_PROFILE='ampixa-notary'
bash desktop/macos/build-package.sh
```

`MACOS_NOTARY_PROFILE` is the profile previously created with
`xcrun notarytool store-credentials`. If the signing variables are omitted, the
same script creates an unsigned local-test package.

After installation, log out and back in, then add an input source from **System
Settings → Keyboard → Text Input → Edit**. Newa and Limbu rendering in target
applications still depends on an installed font with those Unicode blocks.
