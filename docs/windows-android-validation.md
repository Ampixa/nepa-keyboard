# Windows Android validation host

The Windows host is the current Android build and device-test machine. Use the
SSH alias `windows` from the Mac. Its checkout is
`C:\Users\User\nepa-keyboard`; the portable tool root is
`C:\Users\User\nepa-android-tools`. Keep Gradle, SDK downloads, emulators,
and ADB workloads on Windows, in accordance with [host safety](host-safety.md).

## Installed tools

| Component | Windows location | Version |
| --- | --- | --- |
| JDK | `nepa-android-tools\jdk17` | Temurin 17.0.20.1 |
| Gradle | `nepa-android-tools\gradle-8.13` | 8.13 |
| Android SDK | `nepa-android-tools\sdk` | Platform 36, Build Tools 35.0.0, Platform Tools 37.0.1 |
| Android emulator images | SDK `system-images` | Google APIs API 26, 27, 34, 36; Google Play API 36 |
| Internal pack inputs | `nepa-android-tools\pack-inputs-v17` | 17 files, verified against `reports/evidence/production-readiness-20260924/pack-inputs-v17-sha256.txt` |

The Temurin, Gradle, and Android command-line tool downloads were checked
against their published SHA-256 values. The repository checkout must preserve
LF line endings for pinned input hashes. Clone with
`git -c core.autocrlf=false clone --config core.autocrlf=false`, or verify the
checkout against the lock hashes after transfer. `.gitattributes` defines the
line-ending policy for subsequent checkouts.

Before a new emulator or build, check Windows free RAM, C: free space, and
running emulator/Gradle processes. Run one emulator at a time. The validation
runners also record their own headroom check.

## Build the internal APK

In PowerShell on Windows:

```powershell
$root = Join-Path $env:USERPROFILE 'nepa-android-tools'
$env:JAVA_HOME = Join-Path $root 'jdk17'
$env:ANDROID_HOME = Join-Path $root 'sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$gradle = Join-Path $root 'gradle-8.13\bin\gradle.bat'
$packs = Join-Path $root 'pack-inputs-v17'
Set-Location (Join-Path $env:USERPROFILE 'nepa-keyboard\android')
& $gradle --no-daemon --max-workers=2 --console=plain "-PnepaInternalPackDir=$packs" :ime-app:assembleInternal
& $gradle --no-daemon --max-workers=2 --console=plain "-PnepaInternalPackDir=$packs" :ime-app:lintInternal :ime-app:compileCandidateJavaWithJavac :ime-app:lintCandidate
```

The APK is
`android\ime-app\build\outputs\apk\internal\ime-app-internal.apk`. Check
its SHA-256 after every source or test edit. The September 24 preview with 18
lock-backed profiles has SHA-256
`2e878e3257f3d36cba2e45804ec2711ce17450457ca2b344d41b38eb35877689`.
This is an internal preview APK, not a signed Play deliverable.

## Run emulator and phone checks

From the Windows checkout, use
`tools\run_windows_cross_api_subtype_validation.ps1` with `-Apk`, `-Api`,
`-Avd`, and a fresh `-Evidence` directory. Add
`-RequireNoPersonalizedLearning` for the current APK. AVD names are
`nepa_api26_windows`, `nepa_api27_windows`, `nepa_api34_windows`, and
`nepa_api36_windows`; the second API 36 image uses
`nepa_api36_play_windows`. The runner starts and stops its emulator, validates the
API level and APK hash, and retains all six instrumentation results even if
the service suite fails.

For the Samsung Android 14 phone attached to Windows, use
`tools\run_windows_physical_validation.ps1` with `-Apk`,
`-ExpectedSha256`, `-Serial RZCTC0M17SJ`, and a fresh `-Evidence` directory.
The runner saves the original default IME, performs the six suites, restores
the original IME, and disables the test IME. Check `run-status.txt`,
`suite-summary.txt`, `restored-default-ime.txt`, and the evidence hashes
afterward. Automated instrumentation does not substitute for a person's
touch, TalkBack, or Switch Access acceptance.

## Current limits

The API 26, 27, and 34 emulators and Samsung API 34 phone passed all six
suites with the current preview APK. The Windows API 36 Google APIs and Google
Play images pass five suites, while the service-bound suite times out waiting
to observe the selected IME input view. The older v11 APK has the same initial
failure on the Google APIs image. [Live diagnostics](../reports/evidence/production-readiness-20260924/api36-windows-diagnostics/)
show Nepa selected, bound, and visible despite the missing test callback.
Treat API 36 service behavior as unresolved until an independent run or a
diagnosed fix passes. The guarded full relock still awaits available Ubuntu
compute; the preview locks and staged packs were validated separately.

Windows-native Python 3.14 runs the source test suite, but the current suite
contains POSIX path and newline assumptions and does not pass completely on
Windows. The isolated Ubuntu preview passed all 528 Python tests with three
skipped. WSL is not yet ready on Windows because its kernel component is
missing. A `wsl --update` attempt exited with “Catastrophic failure”; no host
reboot was performed.
