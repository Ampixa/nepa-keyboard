# Observable Android first-run setup

`SettingsActivity` presents setup as a resumable state machine rather than a
stored `setup_complete` preference. Each render and Android settings callback
re-evaluates the current facts:

1. **Enable keyboard** is complete only when the exact Nepa input-method ID is
   present in `InputMethodManager.getEnabledInputMethodList()`.
2. **Select keyboard** is complete only when that installed input-method ID
   exactly equals `Settings.Secure.DEFAULT_INPUT_METHOD`.
3. **Choose languages** is complete when the product profile state contains at
   least one enabled, selectable profile. The existing searchable, recycled
   `ListView` remains the management surface and enforces the non-empty set.
4. **Test typing** is complete only after a non-empty edit is observed in the
   setup test field while the first three conditions are simultaneously true.
5. **Complete** is therefore derived from all four current conditions. If
   Android disables or deselects Nepa Keyboard, typing evidence is invalidated
   and setup resumes at the first unmet step.

The Activity observes both secure IME settings with a `ContentObserver`,
refreshes again from `onResume`, and observes process-local language preference
changes. It never treats launching Android settings or the input-method picker
as success. The typing field disables view-state saving and autofill, and the
typed test text is never copied into preferences or the instance-state bundle.
Only a session-scoped `typing observed` boolean survives Activity recreation;
there is no durable setup-complete flag. A process restart therefore resumes
from observable Android and language state and asks for a fresh typing test.

## Remote validation on cdjk

Run all builds and Android work on `cdjk` after checking memory, disk, running
Gradle/Java/Python processes, and emulator ownership. Never run these commands
on the Mac.

First run the existing internal build and API 34 smoke transaction with a new
evidence directory. `InternalImeSmokeInstrumentation` checks the complete
state-transition matrix, compares the Activity model with independent reads of
the enabled/default IME state, verifies that test text persistence is disabled,
and checks instance recreation. Require ordinary instrumentation success and
the result field:

```text
observable_setup_state_model_verified=true
```

Then perform the service-bound UI acceptance sequence on a clean API 34 AVD:

1. Record `adb shell ime list -s` and
   `adb shell settings get secure default_input_method`. Preserve the existing
   non-Nepa default component for restoration; do not guess one.
2. Launch
   `com.ampixa.nepakeyboard.ime.internal/.SettingsActivity`. With Nepa Keyboard
   disabled, verify that **Enable Nepa Keyboard** is the next step.
3. Use Android's keyboard settings UI to enable the exact internal service and
   return. Verify that the Activity updates from the settings observation and
   now requests **Select Nepa Keyboard**; opening settings alone must not
   advance the step.
4. Open the system input-method picker. Cancel it once and verify no state
   change. Open it again, select Nepa Keyboard, and verify that Android's
   `default_input_method` equals the exact component before accepting the
   **Test typing** state.
5. Open **Review enabled languages**, change the enabled set, and verify the
   displayed count follows the real manager state while the list still scrolls,
   filters, recycles rows, and refuses a zero-language set.
6. Tap the setup test editor and type a visible key with the rendered Nepa
   keyboard. Do not use `adb shell input text`, because that would not prove an
   IME interaction. Verify **Setup complete** only after the actual edit.
7. Rotate/recreate the Activity and verify the derived complete state survives
   without restoring the typed text. Switch the default IME to the previously
   recorded non-Nepa component, return, and verify setup regresses to **Select
   Nepa Keyboard**. Switch back and verify a fresh typing test is required.
8. Force-stop and relaunch the app. Enabled, selected, and language steps must
   still match Android/product state, while the session-only typing step is not
   claimed complete.
9. Repeat the flow with TalkBack and Switch Access: each step must announce its
   number, title, and `Complete`, `Next`, or `Waiting` state; buttons and both
   editors must retain at least 48 dp touch targets and logical focus order.

Capture the AVD identity, APK hash, before/after enabled and default IME values,
instrumentation output, screenshots or accessibility recordings for every
state, rotation result, and post-force-stop result in the remote evidence
directory.
