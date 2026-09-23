# Google Play graphics

These are deterministic Google Play assets derived from the accepted Android
16 / API 36 candidate UI. `source-renders/` contains the exact instrumentation
and interactive captures used as inputs. `render-assets.sh` produces the files
under `rendered/`, and `validate-assets.sh` checks the current Play dimensions,
bit depth, alpha-channel, file-size, screenshot-count, and aspect-ratio rules.
It also requires every rendered asset to match the visually inspected hashes in
`checksums.sha256`.

Run on macOS with ImageMagick 7:

```sh
./publishing/google-play/assets/render-assets.sh
./publishing/google-play/assets/validate-assets.sh
```

## Upload mapping

| Play field | File |
| --- | --- |
| App icon | `rendered/icon-512.png` |
| Feature graphic | `rendered/feature-graphic-1024x500.png` |
| Phone screenshots | `rendered/phone-screenshots/*.png` in numeric order |

Suggested alt text, each below 140 characters:

1. `Completed Nepa Keyboard setup with the privacy notice and English keyboard visible.`
2. `Nepali direct keyboard with the script-neutral phonetic toggle and language controls.`
3. `Limbu keyboard showing language switching and the offline input controls.`
4. `Nepal Bhasa keyboard rendered with the bundled Newa script font.`

The first screenshot is a cropped real device capture. The other screenshots
place current, unmodified keyboard renders on simple listing cards; no key,
label, language, or product behavior is fabricated. Re-render after any visible
candidate UI change.

Google's current preview-asset requirements are documented at:
<https://support.google.com/googleplay/android-developer/answer/9866151>
