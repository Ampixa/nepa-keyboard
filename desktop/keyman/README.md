# Nepa Romanized Pro for Windows, macOS, and Linux

This directory contains the shared Keyman desktop package for the first three
direct Romanized input profiles:

- Nepali to Unicode Devanagari;
- Nepal Bhasa/Newari to Unicode Newa (Prachalit Nepal Lipi); and
- Limbu to Unicode Limbu (Sirijanga).

The package uses the same checked mapping specification as the native macOS
bundle: `desktop/macos/romanized-pro-v1.json`. The generated `.kmn` and `.kps`
sources are under `generated/`. Do not edit them directly.

## Generate and verify sources

```sh
python3 tools/build_keyman_romanized_package.py
python3 tools/build_keyman_romanized_package.py --check
python3 -m unittest discover -s tests -p 'test_keyman_romanized_package.py'
```

## Build the cross-platform package

Run the bounded build on the approved Ubuntu build host:

```sh
desktop/keyman/build-package.sh
```

The script pins `@keymanapp/kmc` 17.0.335 and emits
`desktop/keyman/build/nepa_romanized_pro.kmp`. Keyman 17 or newer is required
on the target computer.

## Linux live acceptance

On Ubuntu, install the Keyman/IBus runtime, install the generated package, and
run the isolated live-engine test:

```sh
sudo apt-get install keyman
km-package-install -f desktop/keyman/build/nepa_romanized_pro.kmp
desktop/keyman/test-linux.sh
```

The test creates a temporary Xvfb, D-Bus, and IBus session, activates each of
the three installed engines, sends hardware key events through IBus, and
asserts the committed Unicode output. It covers Normal, Shift, Caps Lock,
Shift+Caps Lock, Right Alt, and the provisional Limbu GYAN and TRA keys.

## Modifier behavior

- Normal and Shift reproduce the checked direct layouts.
- Caps Lock exposes the Nepali conjunct shortcuts inherited from Nepali
  Romanized Pro.
- Right Alt/AltGr exposes extended Newa and Limbu characters. On macOS use
  Right Option.
- Ctrl and Command combinations are not intercepted, preserving application
  shortcuts.

The native `.keylayout` bundle under `desktop/macos/` remains available for a
macOS installation that does not depend on Keyman. Cross-platform acceptance,
however, is performed against the single `.kmp` so Windows, macOS, and Linux
exercise the same compiled keyboard rules.

This Keyman package remains the immediate physical-key-mapping mode. The
caret-positioned composing mode, including its persisted candidate-window
toggle, is documented separately in [`desktop/phonetic/README.md`](../phonetic/README.md).
