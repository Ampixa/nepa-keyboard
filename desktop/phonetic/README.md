# Nepa Phonetic desktop input methods

Nepa Phonetic is the composing counterpart to the direct Romanized layouts.
It buffers one Roman token, displays its converted script as marked text, and
asks the operating system to place a candidate window beside the text cursor.
The first beta contains three system input sources:

- Nepali Roman input to Devanagari;
- Nepal Bhasa Roman input to Unicode Newa/Prachalit; and
- Limbu Roman input to Unicode Limbu/Sirijanga.

The current candidate list is deliberately deterministic: the converted form
is first and the exact Roman input is second. It does not yet claim Google's
dictionary size, fuzzy correction, or contextual ranking. The native candidate
UI and the composition lifecycle are in place so additional ranked candidates
can be added without replacing the platform integrations.

## Interaction contract

| Input | Behavior |
|---|---|
| Roman letters | Recompute marked script text and candidates |
| Space | Commit the selected candidate and a space |
| Enter | Commit the selected candidate |
| Arrow keys or Tab | Move between converted and literal candidates |
| `1` or `2` | Select a visible candidate on macOS and Windows |
| Escape | Commit the exact Roman buffer |
| Backspace | Remove one Roman character, then rerender |
| `Ctrl+Alt+C` | Toggle the caret candidate window on Windows/Linux |
| `Control+Option+C` | Toggle the caret candidate window on macOS |

The candidate-window choice defaults to enabled and is persisted per profile.
Disabling it hides the floating window without destroying the active
composition; marked transliterated text remains visible at the caret. Writers
who prefer an immediate physical-key mapping can select the separate **Nepa
Romanized Pro** direct input source.

## Linux

The Linux frontend uses IBus preedit and `IBusLookupTable`, so the desktop IBus
panel owns caret positioning, mouse selection, accessibility, and Wayland/X11
integration.

```sh
sudo desktop/linux/install.sh
desktop/linux/test-installed.sh
```

After installation, log out and back in and add one of the three **Nepa
Phonetic** sources in the desktop keyboard settings. The IBus property menu
also exposes the candidate-window toggle.

The installed Ubuntu 24.04 acceptance on `cdjk` passed all three live engines,
including marked text, visible lookup-table candidates, Space commit, Escape
fallback, and disabling/re-enabling the popup without losing composition. The
machine-readable record is
[`validation/nepa-phonetic-linux-ibus-v1.json`](../../validation/nepa-phonetic-linux-ibus-v1.json).

## macOS

The macOS frontend is a native Swift InputMethodKit application. The package
contains three input-method apps and uses `IMKCandidates` with the
below-selection location hint.

```sh
bash desktop/macos-ime/test-core.sh
bash desktop/macos-ime/build-package.sh
sudo installer -pkg desktop/macos-ime/build/NepaPhonetic-0.2.0.pkg -target /
```

Then log out and back in and add the desired source from **System Settings →
Keyboard → Text Input → Edit**. The input-source menu has a **Show Suggestions
Beside Cursor** checkbox in addition to the keyboard shortcut.

The checked artifact is currently an unsigned engineering package. Set
`MACOS_APPLICATION_SIGNING_IDENTITY`, `MACOS_INSTALLER_SIGNING_IDENTITY`, and
optionally `MACOS_NOTARY_PROFILE` before running the build script to produce a
signed/notarized package. Native Swift vectors and bundle structure pass on
macOS; a selected-input-source GUI run is still required before calling the
macOS adapter live-accepted.

## Windows

The Windows frontend is a three-profile PIME overlay. PIME supplies the signed
TSF host and caret candidate window; the bundled Python services supply the
same offline state machine and reviewed maps used by Linux.

```powershell
python tools\build_windows_pime.py
powershell -ExecutionPolicy Bypass -File desktop\windows\install.ps1
```

PIME 1.3 or newer must already be installed. Restart PIME or sign out after
installation, then add the desired keyboard in Windows Settings. The language
bar has a toggle button in addition to `Ctrl+Alt+C`.

The generated overlay, manifest hashes, deterministic ZIP, and a mocked PIME
protocol replay pass. It is not yet a Windows live acceptance result; that
requires an authorized Windows machine with PIME and real TSF editor clients.

## Shared implementation

- [`src/nepa_keyboard/transliteration.py`](../../src/nepa_keyboard/transliteration.py)
  mirrors the reviewed Android greedy-syllable engine.
- [`src/nepa_keyboard/desktop_composer.py`](../../src/nepa_keyboard/desktop_composer.py)
  owns the Roman buffer, converted/literal candidates, selection, and persisted
  popup setting.
- The three generated JSON assets under Android remain the canonical compiled
  maps; desktop packaging copies those exact bytes.

