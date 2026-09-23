# Google Play publishing handoff

Package: `com.ampixa.nepakeyboard.ime`  
App name: `Nepa Keyboard`  
Initial track: `internal`  
Default listing locale: `en-US`  
Planned price: free

Record approvals and public contact details in `owner-inputs.md`; never put
credentials or key material there.

## One-command local preflight

Run the read-only publishing preflight from any directory:

```sh
publishing/google-play/preflight.sh
```

It checks the fixed package and version, candidate signing gate, listing-copy
limits, privacy and Data safety drafts, inspected asset hashes, `gps` and
`gps-mcp` installation/registration, credential and signing-file permissions,
owner approvals, and signed-AAB presence. It never prints credential or
keystore values. Exit `0` means the local handoff is ready for validate-only
Play calls, exit `2` identifies expected owner-controlled inputs that are still
waiting, and exit `1` identifies an invalid prepared input that must be fixed.

The defaults can be overridden without editing the script using
`PLAY_PACKAGE`, `GPS_ACCOUNT`, `GOOGLE_APPLICATION_CREDENTIALS`,
`KEYSTORE_PROPERTIES`, and `CANDIDATE_AAB`.

The package name is permanent once used in Play Console. Confirm it before
creating the app. Google documents the required Play Console creation choices
and declarations here:
<https://support.google.com/googleplay/android-developer/answer/9859152>

## Account inputs still required

1. The Play Console developer account that should own the app.
2. A public support email shown on the listing.
3. A stable public HTTPS URL for `publishing/privacy-policy.md`.
4. The Google Group or email addresses for internal testers.
5. Either the Google Cloud project to use for automation, or approval to create
   a dedicated project named for Nepa Keyboard.

Only two generic Cloud projects are visible to the currently authenticated
`gcloud` user, so neither is selected automatically. Once the owner chooses a
project, enable `androidpublisher.googleapis.com`, create a dedicated service
account, invite its email under Play Console **Users and permissions**, and
grant only the app/release/listing permissions needed for this package. Google
documents that two-console setup here:
<https://developers.google.com/android-publisher/getting_started>

Save the downloaded service-account JSON outside the repository at
`~/.config/gps/service-account.json` with mode `0600`. Then register it and the
app with `gps`:

```sh
gps accounts add nepa \
  --credentials ~/.config/gps/service-account.json \
  --default-package com.ampixa.nepakeyboard.ime \
  --default
gps apps add com.ampixa.nepakeyboard.ime \
  --account nepa \
  --name "Nepa Keyboard" \
  --default
gps whoami --account nepa
```

Do not paste the JSON key into chat, documentation, or the repository.

## Artifact and signing

The Play artifact is `:ime-app:bundleCandidate`, not `bundleRelease`.
`candidate` uses the full internal catalog while retaining the permanent base
package. Use Play App Signing with a separate upload key. Google recommends a
new upload key for new apps and manages the app-signing key by default:
<https://support.google.com/googleplay/android-developer/answer/9842756>

The current candidate remains unsigned and unbuilt, while the exact candidate
sources compile and lint with `No issues found`. Generate the upload key only
after confirming the permanent package and back it up outside this host.
Never commit a keystore or its passwords. Candidate assembly and bundling are
fail-closed until ignored `android/keystore.properties` exists, contains all
four values shown in `android/keystore.properties.example`, and points to a real
keystore. Keep the real properties file mode `0600`.

The complete signing path was exercised with a disposable one-year RSA key on
2026-08-09. The resulting AAB passed Bundletool validation, produced an APK with
valid v2/v3 signatures, installed as the permanent package on API 36, registered
as an IME, displayed its keyboard, and completed setup typing. The disposable
key, AAB, generated APK set, installed package, and temporary properties file
were then removed so they cannot be mistaken for upload credentials or an
uploadable release. Evidence is in
`../../reports/evidence/nepa-release-api36-v1/candidate-aab-acceptance.txt`.

Before upload, verify all of the following from the exact signed AAB:

- package `com.ampixa.nepakeyboard.ime`;
- version code is new and version name is intentional;
- target API meets the submission date's requirement;
- bundle signature matches the recorded upload certificate;
- full 16-profile candidate inputs match the accepted internal build;
- release notes and evidence hashes identify the exact AAB.

## Listing and compliance

The `en-US` listing files in this directory are within Google's current limits
of 30 characters for the title, 80 for the short description, and 4,000 for the
full description. Upload listing text only after the app exists. Fresh Play
graphics are ready under `assets/rendered/`: one 512 x 512 RGBA icon, one
1024 x 500 non-alpha feature graphic, and four 1080 x 1920 non-alpha phone
screenshots derived from the accepted API 36 UI. `assets/validate-assets.sh`
checks dimensions, bit depth, alpha, icon size, screenshot count, and the 2:1
dimension-ratio ceiling before upload. Alt text and source provenance are in
`assets/README.md`.

`data-safety-review.md` records source facts but is not a declaration payload.
The Play account owner must approve the final answers. Google states that the
developer is responsible for complete and accurate declarations:
<https://support.google.com/googleplay/android-developer/answer/10787469>

## Release sequence

1. **Complete:** candidate Android tests, benchmarks, fresh render inspection,
   and Play-asset validation.
2. Create or confirm the Play app and Play App Signing enrollment.
3. Configure the service account and prove read access with `gps whoami` and a
   track/listing read.
4. Build and sign the candidate AAB, then verify package, target, version,
   signature, size, and content hashes.
5. Upload to internal testing, add testers, and install through the Play opt-in
   link on a physical phone.
6. Re-run the first-run, typing, language, emoji, accessibility, and upgrade
   flows against the Play-delivered build.
7. Keep wider rollout closed until the internal acceptance report is complete.

## Authenticated command sequence

After the app record exists and `gps whoami --account nepa` succeeds, use
validate-only writes before the committed writes. Keep global `--confirm` on
every write, including validate-only calls.

```zsh
package=com.ampixa.nepakeyboard.ime
locale=en-US

gps --account nepa --package "$package" --confirm listings update "$locale" \
  --title "$(< publishing/google-play/en-US/title.txt)" \
  --short-description "$(< publishing/google-play/en-US/short-description.txt)" \
  --full-description "$(< publishing/google-play/en-US/full-description.txt)" \
  --validate-only
```

Repeat without `--validate-only` only after reviewing the result. Image uploads
use the operation registry because `gps listings` does not expose image writes
as dedicated subcommands:

```zsh
gps --account nepa --confirm call gps_upload_image \
  '{"packageName":"com.ampixa.nepakeyboard.ime","language":"en-US","imageType":"icon","filePath":"publishing/google-play/assets/rendered/icon-512.png","validateOnly":true}'

gps --account nepa --confirm call gps_upload_image \
  '{"packageName":"com.ampixa.nepakeyboard.ime","language":"en-US","imageType":"featureGraphic","filePath":"publishing/google-play/assets/rendered/feature-graphic-1024x500.png","validateOnly":true}'
```

Validate each phone screenshot with `imageType` set to `phoneScreenshots`, then
repeat the calls with `validateOnly` set to `false`. Use `gps_list_images`
between validation and committed uploads to avoid accidental duplicates.

The Publisher API tester endpoint accepts Google Groups. Configure individual
email lists in Play Console, or provide one Group address and run:

```zsh
gps --account nepa --package "$package" --confirm testers update internal \
  --google-groups testers@example.com
```

Finally validate the release edit, then commit the same artifact to internal:

```zsh
gps --account nepa --package "$package" --confirm deploy \
  --file /secure/path/nepa-keyboard-v1.aab \
  --track internal \
  --release-notes "$(< publishing/google-play/en-US/internal-release-notes.txt)" \
  --validate-only

gps --account nepa --package "$package" --confirm deploy \
  --file /secure/path/nepa-keyboard-v1.aab \
  --track internal \
  --release-notes "$(< publishing/google-play/en-US/internal-release-notes.txt)"
```
