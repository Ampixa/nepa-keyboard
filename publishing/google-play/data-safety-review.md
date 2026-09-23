# Google Play Data safety review

Do not submit a Data safety payload until the Play account owner approves the
answers in Play Console. The current source supports the following review facts:

- The main manifest has no `android.permission.INTERNET` permission.
- The app contains no advertising or analytics SDK dependency.
- Typed text, editor context, suggestions, transliteration, and script
  conversion are processed on the device.
- Keyboard preferences and recent emoji are stored on the device.
- Android backup is disabled and the setup test field disables saved state and
  autofill.
- A source or license link is handed to a separate installed application; Nepa
  Keyboard does not fetch the URL itself.

The account owner must confirm that the final candidate contains no additional
SDK, service, crash reporting, telemetry, account, or server behavior before
answering that no user data is collected or shared. Preserve the approved Play
Console export with the release evidence.
