# Windows and macOS live acceptance

Use the exact candidate at
`desktop/keyman/build/nepa_romanized_pro.kmp`. Its accepted Linux-candidate
SHA-256 is:

```text
92a2a6115d3ddab8bba140ccde067c26a5972ce2793587e4d0bda87ffb1becde
```

Do not rebuild between platforms. Testing the same bytes is what establishes
cross-platform parity.

## Windows 10 or 11

1. Install Keyman 17 or newer.
2. Copy `nepa_romanized_pro.kmp` to the Windows test machine.
3. Confirm the SHA-256 in PowerShell:

   ```powershell
   Get-FileHash .\nepa_romanized_pro.kmp -Algorithm SHA256
   ```

4. Locate `kmshell.exe`, normally at
   `%ProgramFiles(x86)%\Keyman\Keyman Desktop\kmshell.exe`.
5. In elevated PowerShell, install the package:

   ```powershell
   $kmshell = "${env:ProgramFiles(x86)}\Keyman\Keyman Desktop\kmshell.exe"
   & $kmshell -s -i "$PWD\nepa_romanized_pro.kmp"
   ```

6. In a normal, non-elevated PowerShell session, register all three keyboards
   for the current user:

   ```powershell
   $kmshell = "${env:ProgramFiles(x86)}\Keyman\Keyman Desktop\kmshell.exe"
   & $kmshell -s -ikl nepa_nepali_romanized ne
   & $kmshell -s -ikl nepa_newa_romanized new-Newa
   & $kmshell -s -ikl nepa_limbu_romanized lif-Limb
   ```

7. Open Notepad, select each keyboard from the Windows input selector, and run
   the vectors below.
8. Copy the result from Notepad and compare the Unicode text, even if the test
   machine renders Newa or Limbu as missing-glyph boxes.
9. Repeat the normal and Shift cases in one Chromium-based browser field and
   one Microsoft Office field to cover TSF application classes.

## macOS 13 or newer

1. Install Keyman 17 or newer. With Homebrew this is:

   ```sh
   brew install --cask keyman
   ```

2. Add Keyman under **System Settings → Keyboard → Text Input → Edit** and
   grant the permissions requested by macOS.
3. Confirm the package SHA-256:

   ```sh
   shasum -a 256 nepa_romanized_pro.kmp
   ```

4. Double-click `nepa_romanized_pro.kmp` and accept installation, or drag it
   into Keyman Configuration.
5. Enable all three Nepa keyboards, select each from the Keyman input menu, and
   run the vectors below in TextEdit plain-text mode.
6. Repeat the normal and Shift cases in one browser field and one office-style
   editor.
7. Confirm Right Option reaches the Right-Alt layer. Left Option is deliberately
   not claimed by the shared Keyman package.

The native Keyman-independent macOS installer is a separate candidate at
`desktop/macos/build/NepaRomanizedPro-0.1.0.pkg`. After it is signed and
notarized, install it, log out and back in, add each **Nepa Pro** input source,
and replay the same vectors using Option for the extended layer.

## Required vectors

| Keyboard | Keystroke | Expected Unicode text |
| --- | --- | --- |
| Nepa Nepali Romanized | `k` | `क` |
| Nepa Nepali Romanized | Shift+`k` | `ख` |
| Nepa Nepali Romanized | Caps Lock, then `k` | `क्ष` |
| Nepa Nepali Romanized | Caps Lock, then Shift+`k` | `ख` |
| Nepa Newa Romanized | `k` | `𑐎` |
| Nepa Newa Romanized | Shift+`k` | `𑐏` |
| Nepa Newa Romanized | Right Alt/Right Option+`,` | `𑐓` |
| Nepa Limbu Romanized | `k` | `ᤁ` |
| Nepa Limbu Romanized | Shift+`k` | `ᤂ` |
| Nepa Limbu Romanized | Right Alt/Right Option+`k` | `ᤰ` |
| Nepa Limbu Romanized | Right Alt/Right Option+`,` | `ᤝ` |
| Nepa Limbu Romanized | Right Alt/Right Option+`\` | `ᤞ` |

Record the OS build, Keyman version, application versions, package SHA-256,
and pass/fail result for every vector. A platform is not accepted from
compiler success alone.
