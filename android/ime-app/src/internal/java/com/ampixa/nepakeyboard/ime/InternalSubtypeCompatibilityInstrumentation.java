package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.inputmethod.InputMethodManager;
import android.view.inputmethod.InputMethodSubtype;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Internal-only service-bound subtype switching evidence for API 26, 27, 34, and 36. */
public final class InternalSubtypeCompatibilityInstrumentation extends Instrumentation {
    private static final String EXPECTED_PACKAGE =
            "com.ampixa.nepakeyboard.ime.internal";
    private static final long SERVICE_READY_TIMEOUT_MS = 120_000L;
    private static final long SERVICE_REQUEST_INTERVAL_MS = 250L;
    private static final long SUBTYPE_CONVERGENCE_TIMEOUT_MS = 120_000L;
    private static final long LIFECYCLE_CONVERGENCE_TIMEOUT_MS = 120_000L;
    private static final long LIFECYCLE_POLL_INTERVAL_MS = 5L;
    private static final long POST_REPEAT_MARGIN_MS = 150L;

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        int resultCode = Activity.RESULT_CANCELED;
        InternalSubtypeTestActivity host = null;
        TransitionTrace trace = new TransitionTrace();
        NepaInputMethodService.setSubtypeTransitionObserverForTesting(trace);
        try {
            Context context = getTargetContext();
            assertEquals("internal application ID", EXPECTED_PACKAGE, context.getPackageName());
            assertTrue(
                    "supported compatibility API",
                    Build.VERSION.SDK_INT == 26
                            || Build.VERSION.SDK_INT == 27
                            || Build.VERSION.SDK_INT == 34
                            || Build.VERSION.SDK_INT == 36
            );

            AndroidSubtypeRegistry registry = AndroidSubtypeRegistry.load(context);
            awaitSelectedInputMethod(context, registry.inputMethodId());

            LanguagePreferences preferences = new LanguagePreferences(context);
            preferences.clearForTesting();

            Intent intent = new Intent(context, InternalSubtypeTestActivity.class);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            host = (InternalSubtypeTestActivity) startActivitySync(intent);
            ServiceReadinessEvidence serviceReadiness = waitForEditorService(host, trace);
            runOnMainSync(() -> {
                NepaInputMethodService service = trace.service();
                assertTrue("bound input method service available", service != null);
                assertTrue(
                        "IME navigation controls match the keyboard surface",
                        service.navigationBarAppearanceMatchesForTesting()
                );
            });
            verifyNavigationBarThemeSwitch(context, trace);

            assertTrue(
                    "English is enabled for compatibility transition",
                    preferences.setEnabled(LanguageRegistry.ENGLISH_ID, true)
            );
            assertTrue(
                    "Nepali is enabled for compatibility transition",
                    preferences.setEnabled(LanguageRegistry.NEPALI_DIRECT_ID, true)
            );

            KeyboardProfile observedInitial = awaitInitialConvergence(registry, preferences);
            if (!LanguageRegistry.ENGLISH_ID.equals(observedInitial.id())) {
                assertTrue(
                        "product normalizes compatibility baseline to English",
                        preferences.requestActive(LanguageRegistry.ENGLISH_ID)
                );
                awaitExactConvergence(
                        registry,
                        preferences,
                        LanguageRegistry.ENGLISH_ID
                );
            }
            for (KeyboardProfile enabled : preferences.enabledProfiles()) {
                if (!LanguageRegistry.ENGLISH_ID.equals(enabled.id())
                        && !LanguageRegistry.NEPALI_DIRECT_ID.equals(enabled.id())) {
                    assertTrue(
                            "compatibility test disables unrelated profile " + enabled.id(),
                            preferences.setEnabled(enabled.id(), false)
                    );
                }
            }
            awaitViewProfile(trace, LanguageRegistry.ENGLISH_ID);

            NepaInputMethodService englishService = trace.service();
            trace.expect(LanguageRegistry.NEPALI_DIRECT_ID);
            runOnMainSync(() -> {
                NepaInputView view = trace.view();
                assertTrue("bound English input view available", view != null);
                view.showLanguagePicker();
                assertTrue("bound picker opens", view.pickerVisibleForTesting());
                assertTrue(
                        "bound picker contains Nepali",
                        view.pickerHasProfileForTesting(LanguageRegistry.NEPALI_DIRECT_ID)
                );
            });
            waitForIdleSync();
            runOnMainSync(() -> {
                NepaInputView view = trace.view();
                assertTrue("bound English input view remains available", view != null);
                assertTrue("bound picker remains open after layout", view.pickerVisibleForTesting());
                assertTrue(
                        "bound attached English row keeps accessibility selected state",
                        view.pickerAttachedProfileSelectedForTesting(LanguageRegistry.ENGLISH_ID)
                );
                assertTrue(
                        "bound picker selects Nepali",
                        view.performPickerProfileForTesting(LanguageRegistry.NEPALI_DIRECT_ID)
                );
            });
            TransitionEvidence pickerEvidence = awaitTransition(
                    registry,
                    preferences,
                    trace,
                    LanguageRegistry.NEPALI_DIRECT_ID,
                    englishService
            );

            verifyPhoneticEmojiEditing(host, trace);

            NepaInputMethodService nepaliService = trace.service();
            trace.expect(LanguageRegistry.ENGLISH_ID);
            runOnMainSync(() -> {
                NepaInputView view = trace.view();
                assertTrue("bound Nepali input view available", view != null);
                assertTrue(
                        "bound globe cycles to English",
                        view.performKeyIdForTesting("base.r3.k2")
                );
            });
            TransitionEvidence globeEvidence = awaitTransition(
                    registry,
                    preferences,
                    trace,
                    LanguageRegistry.ENGLISH_ID,
                    nepaliService
            );
            assertEquals(
                    "picker and globe use the same platform path",
                    pickerEvidence.path,
                    globeEvidence.path
            );
            awaitManagedEnabledSubtypes(context, registry, preferences);
            assertEquals(
                    "Nepa remains selected after subtype transitions",
                    registry.inputMethodId(),
                    Settings.Secure.getString(
                            context.getContentResolver(),
                            Settings.Secure.DEFAULT_INPUT_METHOD
                    )
            );
            verifyNoPersonalizedLearning(host, trace);
            HeldDeleteLifecycleEvidence lifecycleEvidence = verifyHeldDeleteLifecycle(
                    host,
                    trace
            );

            result.putString("status", "ok");
            result.putInt("api_level", Build.VERSION.SDK_INT);
            result.putString("input_method_id", registry.inputMethodId());
            result.putString("observed_initial_profile", observedInitial.id());
            result.putBoolean("focus_driven_ime_readiness_verified", true);
            result.putBoolean("ime_navigation_bar_contrast_verified", true);
            result.putBoolean("ime_navigation_bar_theme_switch_verified", true);
            result.putBoolean(
                    "initial_editor_window_focus_verified",
                    serviceReadiness.windowFocusObserved
            );
            result.putBoolean(
                    "initial_editor_view_focus_verified",
                    serviceReadiness.viewFocusObserved
            );
            result.putInt(
                    "initial_ime_request_attempts",
                    serviceReadiness.requestAttempts
            );
            result.putLong(
                    "initial_ime_ready_elapsed_ms",
                    serviceReadiness.elapsedMillis
            );
            result.putString("initial_profile", LanguageRegistry.ENGLISH_ID);
            result.putString("switched_profile", LanguageRegistry.NEPALI_DIRECT_ID);
            result.putString("restored_profile", LanguageRegistry.ENGLISH_ID);
            result.putBoolean("service_bound_picker_subtype_verified", true);
            result.putBoolean("service_bound_phonetic_emoji_editing_verified", true);
            result.putBoolean("service_bound_globe_subtype_verified", true);
            result.putBoolean("platform_subtype_confirmation_verified", true);
            result.putString("switch_path", pickerEvidence.path.resultName);
            result.putBoolean(
                    "legacy_window_token_present",
                    pickerEvidence.legacyWindowTokenPresent
                            && globeEvidence.legacyWindowTokenPresent
            );
            result.putBoolean(
                    "same_service_subtype_callback_after_picker_verified",
                    pickerEvidence.sameServiceRetained
            );
            result.putBoolean(
                    "same_service_subtype_callback_after_globe_verified",
                    globeEvidence.sameServiceRetained
            );
            result.putString("picker_platform_observation", pickerEvidence.platformSource);
            result.putString("globe_platform_observation", globeEvidence.platformSource);
            result.putBoolean(
                    "managed_enabled_subtypes_verified",
                    Build.VERSION.SDK_INT >= 34
            );
            result.putBoolean(
                    "service_bound_held_delete_password_restart_cancel_verified",
                    true
            );
            result.putBoolean(
                    "service_bound_held_delete_private_no_context_read_verified",
                    true
            );
            result.putBoolean("private_emoji_recents_suppressed_verified", true);
            result.putBoolean("no_personalized_learning_emoji_recents_suppressed_verified", true);
            result.putBoolean(
                    "service_bound_held_delete_hide_cancel_verified",
                    true
            );
            result.putBoolean(
                    "service_bound_held_delete_finish_cancel_verified",
                    true
            );
            result.putBoolean(
                    "service_bound_held_delete_post_cancel_dispatch_stability_verified",
                    true
            );
            result.putLong(
                    "password_restart_cancel_observed_elapsed_ms",
                    lifecycleEvidence.passwordRestartCancelElapsedMillis
            );
            result.putInt(
                    "private_context_read_count",
                    lifecycleEvidence.privateContextReadCount
            );
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            result.putString("status", "error");
            result.putString("error", failure.toString());
        } finally {
            NepaInputMethodService.setSubtypeTransitionObserverForTesting(null);
            if (host != null) {
                InternalSubtypeTestActivity finalHost = host;
                runOnMainSync(finalHost::finish);
            }
        }
        finish(resultCode, result);
    }

    private void verifyPhoneticEmojiEditing(
            InternalSubtypeTestActivity host,
            TransitionTrace trace
    ) {
        KeySpec k = KeySpec.generatedText(
                "test.k", "k", "k", "k", KeySpec.InputPolicy.DEFAULT, 1, null
        );
        KeySpec a = KeySpec.generatedText(
                "test.a", "a", "a", "a", KeySpec.InputPolicy.DEFAULT, 1, null
        );
        runOnMainSync(() -> {
            NepaInputMethodService service = trace.service();
            NepaInputView view = trace.view();
            assertTrue("Nepali service and view are bound", service != null && view != null);
            host.setEditorTextForTesting("");
            if (!view.isTransliterating()) {
                view.toggleTransliteration();
            }
            assertTrue("phonetic input is active", view.isTransliterating());
        });
        waitForIdleSync();
        awaitActiveEditorConnection(host, trace, LanguageRegistry.NEPALI_DIRECT_ID);
        runOnMainSync(() -> {
            NepaInputMethodService service = trace.service();
            service.onKey(k, null);
            service.onKey(a, null);
        });
        awaitEditorText(host, "क", "phonetic text before emoji");

        runOnMainSync(() -> trace.service().onEmojiSelected("🙂"));
        awaitEditorText(host, "क🙂", "emoji follows committed phonetic text");
        runOnMainSync(() -> {
            assertEquals(
                    "ordinary emoji use is remembered",
                    "🙂",
                    new KeyboardPreferences(host).recentEmoji().get(0)
            );
        });
        runOnMainSync(() -> {
            NepaInputMethodService service = trace.service();
            service.onKey(k, null);
            service.onKey(a, null);
        });
        awaitEditorText(host, "क🙂क", "second phonetic token");
        runOnMainSync(() -> trace.service().onEmojiBackspace());
        TransliterationEngine engine = TransliterationCatalog.load(host).forProfile(
                LanguageRegistry.find(LanguageRegistry.NEPALI_DIRECT_ID)
        );
        awaitEditorText(
                host,
                "क🙂" + engine.transliterate("k"),
                "emoji backspace edits the active Roman buffer"
        );
        runOnMainSync(() -> trace.service().onKey(a, null));
        awaitEditorText(host, "क🙂क", "phonetic typing continues after backspace");

        runOnMainSync(() -> trace.service().onEmojiSelected("🙂"));
        awaitEditorText(host, "क🙂क🙂", "second emoji commits once");
        runOnMainSync(() -> {
            NepaInputView view = trace.view();
            view.toggleTransliteration();
        });
        restartEditor(host, trace, "", false, false);
        awaitActiveEditorConnection(host, trace, LanguageRegistry.NEPALI_DIRECT_ID);
    }

    private void verifyNoPersonalizedLearning(
            InternalSubtypeTestActivity host,
            TransitionTrace trace
    ) {
        KeyboardPreferences preferences = new KeyboardPreferences(host);
        runOnMainSync(() -> preferences.recordRecentEmoji("🙂"));
        List<String> recentsBefore = preferences.recentEmoji();
        String emoji = firstUnseenEmoji(host, recentsBefore);
        long previousActivation = trace.activationGeneration();
        runOnMainSync(() -> {
            host.setEditorTextForTesting("");
            host.restartWithoutPersonalizedLearningForTesting();
        });
        awaitInputMode(trace, previousActivation, false);
        awaitActiveEditorConnection(host, trace, LanguageRegistry.ENGLISH_ID);
        runOnMainSync(() -> {
            NepaInputMethodService service = trace.service();
            NepaInputView view = trace.view();
            assertTrue("no-learning service and view are bound", service != null && view != null);
            assertTrue("no-learning editor keeps normal text mode", !service.privateFieldForTesting());
            assertTrue("no-learning editor disables emoji history",
                    !service.emojiHistoryAllowedForTesting());
            if (!view.emojiPanelVisible()) {
                view.toggleEmojiPanel();
            }
            EmojiPanel panel = view.emojiPanelForTesting();
            assertTrue("no-learning emoji panel opens", view.emojiPanelVisible());
            assertTrue("no-learning recents page is selectable",
                    panel.selectPageForTesting(EmojiPanel.RECENTS_CATEGORY_ID));
            assertEquals("no-learning recents are hidden", 0,
                    panel.visibleEmojiCountForTesting());
            view.recordEmojiUse(emoji);
            service.onEmojiSelected(emoji);
        });
        awaitEditorText(host, emoji, "emoji reaches the no-learning editor");
        runOnMainSync(() -> assertEquals(
                "no-learning emoji use is not retained",
                recentsBefore,
                preferences.recentEmoji()
        ));

        restartEditor(host, trace, "", false, false);
        runOnMainSync(() -> {
            assertTrue("normal editor restores emoji history",
                    trace.service().emojiHistoryAllowedForTesting());
            trace.service().onEmojiSelected(emoji);
        });
        awaitEditorText(host, emoji, "emoji reaches the restored normal editor");
        runOnMainSync(() -> assertEquals(
                "normal emoji use is remembered",
                emoji,
                preferences.recentEmoji().get(0)
        ));
    }

    private void awaitEditorText(
            InternalSubtypeTestActivity host,
            String expected,
            String label
    ) {
        long deadline = SystemClock.elapsedRealtime() + 10_000L;
        String[] observed = new String[1];
        while (SystemClock.elapsedRealtime() < deadline) {
            runOnMainSync(() -> observed[0] = host.editorTextForTesting());
            if (expected.equals(observed[0])) {
                return;
            }
            SystemClock.sleep(20L);
        }
        throw new AssertionError(label + ": expected=" + expected + " actual=" + observed[0]);
    }

    private void awaitSelectedInputMethod(Context context, String expected) {
        long deadline = SystemClock.elapsedRealtime() + SERVICE_READY_TIMEOUT_MS;
        String observed = null;
        while (SystemClock.elapsedRealtime() < deadline) {
            observed = Settings.Secure.getString(
                    context.getContentResolver(),
                    Settings.Secure.DEFAULT_INPUT_METHOD
            );
            if (expected.equals(observed)) {
                return;
            }
            SystemClock.sleep(25L);
        }
        throw new AssertionError(
                "Nepa is the selected IME: expected=" + expected + " actual=" + observed
        );
    }

    private void awaitActiveEditorConnection(
            InternalSubtypeTestActivity host,
            TransitionTrace trace,
            String profileId
    ) {
        long deadline = SystemClock.elapsedRealtime() + SERVICE_READY_TIMEOUT_MS;
        long nextRequestAt = 0L;
        while (SystemClock.elapsedRealtime() < deadline) {
            boolean[] ready = new boolean[1];
            boolean[] focused = new boolean[1];
            runOnMainSync(() -> {
                NepaInputMethodService service = trace.service();
                NepaInputView view = trace.view();
                focused[0] = host.editorHasInputFocusForTesting();
                ready[0] = focused[0]
                        && host.editorIsServedForTesting()
                        && service != null
                        && service.inputViewActiveForTesting()
                        && service.getCurrentInputConnection() != null
                        && view != null
                        && view.profile() != null
                        && profileId.equals(view.profile().id());
            });
            if (ready[0]) {
                return;
            }
            long now = SystemClock.elapsedRealtime();
            if (focused[0] && now >= nextRequestAt) {
                runOnMainSync(host::showImeForTesting);
                nextRequestAt = now + SERVICE_REQUEST_INTERVAL_MS;
            }
            SystemClock.sleep(25L);
        }
        throw new AssertionError("editor did not bind to active profile " + profileId);
    }

    private HeldDeleteLifecycleEvidence verifyHeldDeleteLifecycle(
            InternalSubtypeTestActivity host,
            TransitionTrace trace
    ) {
        restartEditor(host, trace, "xe\u0301", false, true);
        NepaInputView normalView = trace.view();
        assertTrue("normal bound view available for password restart", normalView != null);
        long passwordPreviousActivation = trace.activationGeneration();
        long[] passwordStarted = new long[1];
        runOnMainSync(() -> {
            passwordStarted[0] = SystemClock.uptimeMillis();
            assertTrue(
                    "normal held delete starts before password restart",
                    normalView.beginDeleteTouchForTesting()
            );
            assertEquals(
                    "normal held delete removes one complete grapheme immediately",
                    "x",
                    host.editorTextForTesting()
            );
            host.restartAsPasswordForTesting();
        });
        LifecycleCancellationEvidence passwordCancellation = awaitLifecycleCancellation(
                "password restart",
                trace,
                normalView,
                passwordStarted[0],
                true,
                passwordPreviousActivation,
                null
        );
        assertDeleteDispatchStoppedAfterCancellation(
                "password restart",
                normalView,
                passwordCancellation
        );
        runOnMainSync(() -> {
            assertTrue(
                    "password restart cancels the old held-delete controller",
                    !normalView.deleteRepeatActiveForTesting()
            );
            assertEquals(
                    "password restart never reads private context",
                    0,
                    host.privateContextReadCountForTesting()
            );
        });

        restartEditor(host, trace, "ab", true, false);
        assertTrue("private bound view available", trace.view() != null);
        List<String> recentsBefore = new KeyboardPreferences(host).recentEmoji();
        String privateEmoji = firstUnseenEmoji(host, recentsBefore);
        runOnMainSync(() -> {
            NepaInputMethodService service = trace.service();
            assertTrue("private service remains bound", service != null);
            service.onEmojiSelected(privateEmoji);
        });
        awaitEditorText(host, "ab" + privateEmoji, "emoji reaches the private editor");
        runOnMainSync(() -> {
            assertEquals(
                    "private emoji use is not retained",
                    recentsBefore,
                    new KeyboardPreferences(host).recentEmoji()
            );
        });
        restartEditor(host, trace, "ab", true, false);
        NepaInputView privateView = trace.view();
        assertTrue("private bound view available after reset", privateView != null);
        runOnMainSync(() -> {
            assertTrue(
                    "private short delete starts",
                    privateView.beginDeleteTouchForTesting()
            );
            assertTrue(
                    "private short delete finishes",
                    privateView.finishDeleteTouchForTesting(false)
            );
            assertTrue(
                    "private short delete does not leave repeat armed",
                    !privateView.deleteRepeatActiveForTesting()
            );
            assertEquals(
                    "private short delete never reads context",
                    0,
                    host.privateContextReadCountForTesting()
            );
        });
        awaitEditorText(host, "a", "private short delete mutates text");
        int privateContextReads = host.privateContextReadCountForTesting();

        restartEditor(host, trace, "ab", false, true);
        NepaInputView hideView = trace.view();
        assertTrue("normal bound view available for hide", hideView != null);
        long[] hideStarted = new long[1];
        runOnMainSync(() -> {
            hideStarted[0] = SystemClock.uptimeMillis();
            assertTrue("held delete starts before hide", hideView.beginDeleteTouchForTesting());
            assertEquals("hide fixture dispatches one immediate delete", "a", host.editorTextForTesting());
            host.hideImeForTesting();
        });
        LifecycleCancellationEvidence hideCancellation = awaitLifecycleCancellation(
                "IME hide",
                trace,
                hideView,
                hideStarted[0],
                false,
                -1L,
                null
        );
        assertDeleteDispatchStoppedAfterCancellation(
                "IME hide",
                hideView,
                hideCancellation
        );

        long hiddenActivation = trace.activationGeneration();
        runOnMainSync(() -> host.showImeForTesting());
        awaitInputMode(trace, hiddenActivation, false);
        restartEditor(host, trace, "ab", false, true);
        NepaInputView finishView = trace.view();
        assertTrue("normal bound view available for finish", finishView != null);
        long[] finishStarted = new long[1];
        runOnMainSync(() -> {
            finishStarted[0] = SystemClock.uptimeMillis();
            assertTrue(
                    "held delete starts before Activity finish",
                    finishView.beginDeleteTouchForTesting()
            );
            assertEquals(
                    "finish fixture dispatches one immediate delete",
                    "a",
                    host.editorTextForTesting()
            );
            host.finish();
        });
        LifecycleCancellationEvidence finishCancellation = awaitLifecycleCancellation(
                "Activity finish",
                trace,
                finishView,
                finishStarted[0],
                false,
                -1L,
                host
        );
        assertDeleteDispatchStoppedAfterCancellation(
                "Activity finish",
                finishView,
                finishCancellation
        );
        return new HeldDeleteLifecycleEvidence(
                passwordCancellation.elapsedMillis,
                privateContextReads
        );
    }

    private static String firstUnseenEmoji(
            InternalSubtypeTestActivity host,
            List<String> recents
    ) {
        for (EmojiCatalog.Category category : EmojiCatalog.load(host).categories()) {
            for (String emoji : category.emoji()) {
                if (!recents.contains(emoji)) {
                    return emoji;
                }
            }
        }
        throw new AssertionError("emoji catalog has no unseen private-field fixture");
    }

    private void restartEditor(
            InternalSubtypeTestActivity host,
            TransitionTrace trace,
            String text,
            boolean privateMode,
            boolean resetContextReads
    ) {
        long previousActivation = trace.activationGeneration();
        runOnMainSync(() -> {
            host.setEditorTextForTesting(text);
            if (resetContextReads) {
                host.resetContextReadCountsForTesting();
            }
            if (privateMode) {
                host.restartAsPasswordForTesting();
            } else {
                host.restartAsNormalForTesting();
            }
        });
        awaitInputMode(trace, previousActivation, privateMode);
    }

    private void awaitInputMode(
            TransitionTrace trace,
            long previousActivation,
            boolean expectedPrivate
    ) {
        long deadline = SystemClock.elapsedRealtime() + LIFECYCLE_CONVERGENCE_TIMEOUT_MS;
        boolean[] ready = new boolean[1];
        while (SystemClock.elapsedRealtime() < deadline) {
            runOnMainSync(() -> {
                NepaInputMethodService service = trace.service();
                ready[0] = trace.activationGeneration() > previousActivation
                        && service != null
                        && service.inputViewActiveForTesting()
                        && service.getCurrentInputConnection() != null
                        && service.privateFieldForTesting() == expectedPrivate;
            });
            if (ready[0]) {
                return;
            }
            SystemClock.sleep(25L);
        }
        throw new AssertionError(
                "editor did not restart in " + (expectedPrivate ? "private" : "normal") + " mode"
        );
    }

    private LifecycleCancellationEvidence awaitLifecycleCancellation(
            String label,
            TransitionTrace stateTrace,
            NepaInputView ownerView,
            long startedAtMillis,
            boolean requirePrivate,
            long previousActivation,
            InternalSubtypeTestActivity finishingHost
    ) {
        long convergenceDeadline = SystemClock.elapsedRealtime()
                + LIFECYCLE_CONVERGENCE_TIMEOUT_MS;
        boolean[] cancelled = new boolean[1];
        long[] dispatchCount = new long[1];
        long[] observedAtMillis = new long[1];
        while (SystemClock.elapsedRealtime() < convergenceDeadline) {
            runOnMainSync(() -> {
                NepaInputMethodService service = stateTrace == null
                        ? null
                        : stateTrace.service();
                // A finished editor may hand the IME directly to the launcher or
                // another client, so service inactivity is not a stable invariant.
                // Require destruction of the owning Activity for that path instead.
                boolean lifecycleState = finishingHost != null
                        ? finishingHost.destroyedForTesting()
                        : stateTrace == null
                        || (service != null
                        && (requirePrivate
                        ? stateTrace.activationGeneration() > previousActivation
                        && service.inputViewActiveForTesting()
                        && service.privateFieldForTesting()
                        : !service.inputViewActiveForTesting()));
                cancelled[0] = !ownerView.deleteRepeatActiveForTesting()
                        && lifecycleState;
                if (cancelled[0]) {
                    dispatchCount[0] = ownerView.deleteDispatchCountForTesting();
                    observedAtMillis[0] = SystemClock.uptimeMillis();
                }
            });
            if (cancelled[0]) {
                return new LifecycleCancellationEvidence(
                        observedAtMillis[0] - startedAtMillis,
                        observedAtMillis[0],
                        dispatchCount[0]
                );
            }
            SystemClock.sleep(LIFECYCLE_POLL_INTERVAL_MS);
        }
        throw new AssertionError(label + " did not cancel delete during lifecycle convergence");
    }

    private void assertDeleteDispatchStoppedAfterCancellation(
            String label,
            NepaInputView ownerView,
            LifecycleCancellationEvidence cancellation
    ) {
        awaitPastRepeatDeadline(cancellation.observedAtMillis);
        runOnMainSync(() -> {
            assertTrue(
                    label + " leaves the held-delete controller inactive",
                    !ownerView.deleteRepeatActiveForTesting()
            );
            assertEquals(
                    label + " prevents post-cancellation delete dispatch",
                    cancellation.dispatchCount,
                    ownerView.deleteDispatchCountForTesting()
            );
        });
    }

    private void awaitPastRepeatDeadline(long startedAtMillis) {
        long target = startedAtMillis
                + DeleteRepeatController.INITIAL_DELAY_MILLIS
                + POST_REPEAT_MARGIN_MS;
        long remaining = target - SystemClock.uptimeMillis();
        if (remaining > 0L) {
            SystemClock.sleep(remaining);
        }
        waitForIdleSync();
    }

    private ServiceReadinessEvidence waitForEditorService(
            InternalSubtypeTestActivity host,
            TransitionTrace trace
    ) {
        long startedAt = SystemClock.elapsedRealtime();
        long deadline = startedAt + SERVICE_READY_TIMEOUT_MS;
        long nextRequestAt = startedAt;
        int requestAttempts = 0;
        boolean[] served = new boolean[1];
        boolean[] windowFocused = new boolean[1];
        boolean[] viewFocused = new boolean[1];
        boolean windowFocusObserved = false;
        boolean viewFocusObserved = false;
        while (SystemClock.elapsedRealtime() < deadline) {
            runOnMainSync(() -> {
                served[0] = host.editorIsServedForTesting();
                windowFocused[0] = host.editorHasWindowFocusForTesting();
                viewFocused[0] = host.editorHasViewFocusForTesting();
            });
            windowFocusObserved |= windowFocused[0];
            viewFocusObserved |= viewFocused[0];
            if (served[0] && trace.inputViewReady(Build.VERSION.SDK_INT)) {
                return new ServiceReadinessEvidence(
                        requestAttempts,
                        SystemClock.elapsedRealtime() - startedAt,
                        windowFocusObserved,
                        viewFocusObserved
                );
            }
            long observedAt = SystemClock.elapsedRealtime();
            // InputMethodManager can continue reporting the editor as served
            // after instrumentation has replaced the same-package IME process.
            // Keep requesting the IME until the service-side view is observable,
            // rather than treating that stale client state as readiness.
            if (windowFocused[0]
                    && viewFocused[0]
                    && observedAt >= nextRequestAt) {
                runOnMainSync(host::showImeForTesting);
                requestAttempts++;
                nextRequestAt = observedAt + SERVICE_REQUEST_INTERVAL_MS;
            }
            SystemClock.sleep(25L);
        }
        throw new AssertionError(
                "internal editor did not acquire the selected IME service"
                        + " after focus-driven requests=" + requestAttempts
                        + ", window-focus-observed=" + windowFocusObserved
                        + ", view-focus-observed=" + viewFocusObserved
        );
    }

    private KeyboardProfile awaitInitialConvergence(
            AndroidSubtypeRegistry registry,
            LanguagePreferences preferences
    ) {
        long deadline = SystemClock.elapsedRealtime() + SUBTYPE_CONVERGENCE_TIMEOUT_MS;
        while (SystemClock.elapsedRealtime() < deadline) {
            KeyboardProfile platform = registry.currentProfile();
            KeyboardProfile active = preferences.activeProfile();
            if (platform != null
                    && platform.id().equals(active.id())
                    && preferences.pendingProfile() == null) {
                return platform;
            }
            SystemClock.sleep(25L);
        }
        throw new AssertionError("initial Android/product subtype state did not converge");
    }

    private void awaitExactConvergence(
            AndroidSubtypeRegistry registry,
            LanguagePreferences preferences,
            String expectedProfileId
    ) {
        long deadline = SystemClock.elapsedRealtime() + SUBTYPE_CONVERGENCE_TIMEOUT_MS;
        while (SystemClock.elapsedRealtime() < deadline) {
            KeyboardProfile platform = registry.currentProfile();
            KeyboardProfile active = preferences.activeProfile();
            if (platform != null
                    && expectedProfileId.equals(platform.id())
                    && expectedProfileId.equals(active.id())
                    && preferences.pendingProfile() == null) {
                return;
            }
            SystemClock.sleep(25L);
        }
        throw new AssertionError(
                "Android/product subtype state did not converge to " + expectedProfileId
        );
    }

    private TransitionEvidence awaitTransition(
            AndroidSubtypeRegistry registry,
            LanguagePreferences preferences,
            TransitionTrace trace,
            String expectedProfileId,
            NepaInputMethodService previousService
    ) {
        long deadline = SystemClock.elapsedRealtime() + SUBTYPE_CONVERGENCE_TIMEOUT_MS;
        String[] lastViewProfile = new String[1];
        while (SystemClock.elapsedRealtime() < deadline) {
            KeyboardProfile platform = registry.currentProfile();
            KeyboardProfile active = preferences.activeProfile();
            boolean productConverged = platform != null
                    && expectedProfileId.equals(platform.id())
                    && expectedProfileId.equals(active.id())
                    && preferences.pendingProfile() == null;
            boolean[] viewConverged = new boolean[1];
            runOnMainSync(() -> {
                NepaInputView view = trace.view();
                lastViewProfile[0] = view == null || view.profile() == null
                        ? null : view.profile().id();
                viewConverged[0] = view != null
                        && view.profile() != null
                        && expectedProfileId.equals(view.profile().id());
            });
            TransitionEvidence evidence = trace.evidence(
                    expectedProfileId,
                    previousService,
                    Build.VERSION.SDK_INT
            );
            if (productConverged && viewConverged[0] && evidence != null) {
                return evidence;
            }
            SystemClock.sleep(25L);
        }
        KeyboardProfile platform = registry.currentProfile();
        KeyboardProfile active = preferences.activeProfile();
        KeyboardProfile pending = preferences.pendingProfile();
        throw new AssertionError(
                "service-bound picker/globe transition did not converge to "
                        + expectedProfileId
                        + ": platform=" + (platform == null ? null : platform.id())
                        + " active=" + (active == null ? null : active.id())
                        + " pending=" + (pending == null ? null : pending.id())
                        + " view=" + lastViewProfile[0]
                        + " trace=" + trace.debugSnapshot(previousService)
        );
    }

    private void awaitViewProfile(TransitionTrace trace, String expectedProfileId) {
        long deadline = SystemClock.elapsedRealtime() + SUBTYPE_CONVERGENCE_TIMEOUT_MS;
        while (SystemClock.elapsedRealtime() < deadline) {
            boolean[] matches = new boolean[1];
            runOnMainSync(() -> {
                NepaInputView view = trace.view();
                matches[0] = view != null
                        && view.profile() != null
                        && expectedProfileId.equals(view.profile().id());
            });
            if (matches[0]) {
                return;
            }
            SystemClock.sleep(25L);
        }
        throw new AssertionError("bound input view did not show " + expectedProfileId);
    }

    private void verifyNavigationBarThemeSwitch(Context context, TransitionTrace trace) {
        KeyboardPreferences preferences = new KeyboardPreferences(context);
        String originalTheme = preferences.themeId();
        try {
            preferences.setThemeId("black");
            awaitThemeAndNavigationBar(trace, "black");
            preferences.setThemeId("white");
            awaitThemeAndNavigationBar(trace, "white");
        } finally {
            preferences.setThemeId(originalTheme);
            awaitThemeAndNavigationBar(trace, originalTheme);
        }
    }

    private void awaitThemeAndNavigationBar(TransitionTrace trace, String expectedThemeId) {
        long deadline = SystemClock.elapsedRealtime() + SUBTYPE_CONVERGENCE_TIMEOUT_MS;
        while (SystemClock.elapsedRealtime() < deadline) {
            boolean[] converged = new boolean[1];
            runOnMainSync(() -> {
                NepaInputMethodService service = trace.service();
                NepaInputView view = trace.view();
                converged[0] = service != null
                        && view != null
                        && view.activeThemeForTesting() != null
                        && expectedThemeId.equals(view.activeThemeForTesting().id())
                        && service.navigationBarAppearanceMatchesForTesting();
            });
            if (converged[0]) {
                return;
            }
            SystemClock.sleep(25L);
        }
        throw new AssertionError(
                "IME navigation controls did not match theme " + expectedThemeId
        );
    }

    @SuppressWarnings("deprecation")
    private void awaitManagedEnabledSubtypes(
            Context context,
            AndroidSubtypeRegistry registry,
            LanguagePreferences preferences
    ) {
        if (Build.VERSION.SDK_INT < 34) {
            return;
        }
        InputMethodManager manager = context.getSystemService(InputMethodManager.class);
        assertTrue("input method manager available for API 34+ subtype set", manager != null);
        Set<Integer> expected = new HashSet<>();
        for (KeyboardProfile profile : preferences.enabledProfiles()) {
            InputMethodSubtype subtype = registry.subtypeForProfile(profile.id());
            assertTrue("enabled profile has exact subtype", subtype != null);
            expected.add(subtype.hashCode());
        }

        long deadline = SystemClock.elapsedRealtime() + SUBTYPE_CONVERGENCE_TIMEOUT_MS;
        while (SystemClock.elapsedRealtime() < deadline) {
            List<InputMethodSubtype> enabled = manager.getEnabledInputMethodSubtypeList(
                    registry.inputMethodInfoForTesting(),
                    false
            );
            Set<Integer> actual = new HashSet<>();
            boolean exactCatalogSubtypes = enabled.size() == expected.size();
            for (InputMethodSubtype subtype : enabled) {
                if (registry.profileForSubtype(subtype) == null
                        || !actual.add(subtype.hashCode())) {
                    exactCatalogSubtypes = false;
                    break;
                }
            }
            if (exactCatalogSubtypes && expected.equals(actual)) {
                return;
            }
            SystemClock.sleep(25L);
        }
        throw new AssertionError("API 34+ managed subtype set did not converge");
    }

    private static void assertTrue(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void assertEquals(String label, Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected + " actual=" + actual);
        }
    }

    private static final class TransitionTrace
            implements NepaInputMethodService.SubtypeTransitionObserver {
        private enum Phase {
            IDLE,
            EXPECTING,
            PENDING,
            DISPATCHED,
            PLATFORM_CONFIRMED
        }

        private NepaInputMethodService service;
        private NepaInputView view;
        private boolean activeViewLegacyTokenPresent;
        private String expectedProfileId;
        private Phase phase = Phase.IDLE;
        private boolean dispatchLegacyTokenPresent;
        private AndroidSubtypeRegistry.SwitchPath path;
        private String platformSource;
        private String lastObservedProfileId;
        private String lastActiveProfileId;
        private String lastPendingProfileId;
        private String lastPlatformSource;
        private boolean lastDispatchAccepted;
        private long activationGeneration;

        @Override
        public synchronized void onInputViewActive(
                NepaInputMethodService service,
                NepaInputView view,
                boolean legacyWindowTokenPresent
        ) {
            if (activationGeneration == Long.MAX_VALUE) {
                throw new AssertionError("input-view activation generation exhausted");
            }
            activationGeneration++;
            this.service = service;
            this.view = view;
            activeViewLegacyTokenPresent = legacyWindowTokenPresent;
        }

        @Override
        public synchronized void onProductProfilePending(
                String profileId,
                String pendingProfileId
        ) {
            if (profileId.equals(expectedProfileId)
                    && profileId.equals(pendingProfileId)
                    && phase == Phase.EXPECTING) {
                phase = Phase.PENDING;
            }
        }

        @Override
        public synchronized void onSwitchDispatched(
                String profileId,
                AndroidSubtypeRegistry.SwitchPath path,
                boolean legacyWindowTokenPresent,
                boolean dispatched
        ) {
            lastDispatchAccepted = dispatched;
            if (profileId.equals(expectedProfileId)
                    && dispatched
                    && phase == Phase.PENDING) {
                this.path = path;
                dispatchLegacyTokenPresent = legacyWindowTokenPresent;
                phase = Phase.DISPATCHED;
            }
        }

        @Override
        public synchronized void onPlatformProfileObserved(
                String source,
                String observedProfileId,
                String activeProfileId,
                String pendingProfileId
        ) {
            lastPlatformSource = source;
            lastObservedProfileId = observedProfileId;
            lastActiveProfileId = activeProfileId;
            lastPendingProfileId = pendingProfileId;
            if (expectedProfileId != null
                    && expectedProfileId.equals(observedProfileId)
                    && expectedProfileId.equals(activeProfileId)
                    && pendingProfileId == null
                    && phase == Phase.DISPATCHED) {
                platformSource = source;
                phase = Phase.PLATFORM_CONFIRMED;
            }
        }

        synchronized void expect(String profileId) {
            expectedProfileId = profileId;
            phase = Phase.EXPECTING;
            dispatchLegacyTokenPresent = false;
            path = null;
            platformSource = null;
            lastObservedProfileId = null;
            lastActiveProfileId = null;
            lastPendingProfileId = null;
            lastPlatformSource = null;
            lastDispatchAccepted = false;
        }

        synchronized String debugSnapshot(NepaInputMethodService previousService) {
            return "phase=" + phase
                    + ", path=" + path
                    + ", dispatchAccepted=" + lastDispatchAccepted
                    + ", observed=" + lastObservedProfileId
                    + ", observedActive=" + lastActiveProfileId
                    + ", observedPending=" + lastPendingProfileId
                    + ", observationSource=" + lastPlatformSource
                    + ", sameService=" + (service == previousService);
        }

        synchronized boolean inputViewReady(int sdk) {
            return service != null
                    && view != null
                    && (sdk >= 28 || activeViewLegacyTokenPresent);
        }

        synchronized NepaInputMethodService service() {
            return service;
        }

        synchronized NepaInputView view() {
            return view;
        }

        synchronized long activationGeneration() {
            return activationGeneration;
        }

        synchronized TransitionEvidence evidence(
                String profileId,
                NepaInputMethodService previousService,
                int sdk
        ) {
            if (!profileId.equals(expectedProfileId)
                    || phase != Phase.PLATFORM_CONFIRMED
                    || path == null) {
                return null;
            }
            boolean legacy = sdk <= 27;
            if (legacy
                    && (path != AndroidSubtypeRegistry.SwitchPath.LEGACY_IME_WINDOW_TOKEN
                    || !dispatchLegacyTokenPresent)) {
                return null;
            }
            boolean sameServiceRetained = service == previousService;
            if (!legacy
                    && path != AndroidSubtypeRegistry.SwitchPath.INPUT_METHOD_SERVICE) {
                return null;
            }
            if (!sameServiceRetained || !"subtype_callback".equals(platformSource)) {
                return null;
            }
            return new TransitionEvidence(
                    path,
                    dispatchLegacyTokenPresent,
                    sameServiceRetained,
                    platformSource
            );
        }
    }

    private static final class ServiceReadinessEvidence {
        final int requestAttempts;
        final long elapsedMillis;
        final boolean windowFocusObserved;
        final boolean viewFocusObserved;

        ServiceReadinessEvidence(
                int requestAttempts,
                long elapsedMillis,
                boolean windowFocusObserved,
                boolean viewFocusObserved
        ) {
            this.requestAttempts = requestAttempts;
            this.elapsedMillis = elapsedMillis;
            this.windowFocusObserved = windowFocusObserved;
            this.viewFocusObserved = viewFocusObserved;
        }
    }

    private static final class HeldDeleteLifecycleEvidence {
        final long passwordRestartCancelElapsedMillis;
        final int privateContextReadCount;

        HeldDeleteLifecycleEvidence(
                long passwordRestartCancelElapsedMillis,
                int privateContextReadCount
        ) {
            this.passwordRestartCancelElapsedMillis = passwordRestartCancelElapsedMillis;
            this.privateContextReadCount = privateContextReadCount;
        }
    }

    private static final class LifecycleCancellationEvidence {
        final long elapsedMillis;
        final long observedAtMillis;
        final long dispatchCount;

        LifecycleCancellationEvidence(
                long elapsedMillis,
                long observedAtMillis,
                long dispatchCount
        ) {
            this.elapsedMillis = elapsedMillis;
            this.observedAtMillis = observedAtMillis;
            this.dispatchCount = dispatchCount;
        }
    }

    private static final class TransitionEvidence {
        final AndroidSubtypeRegistry.SwitchPath path;
        final boolean legacyWindowTokenPresent;
        final boolean sameServiceRetained;
        final String platformSource;

        TransitionEvidence(
                AndroidSubtypeRegistry.SwitchPath path,
                boolean legacyWindowTokenPresent,
                boolean sameServiceRetained,
                String platformSource
        ) {
            this.path = path;
            this.legacyWindowTokenPresent = legacyWindowTokenPresent;
            this.sameServiceRetained = sameServiceRetained;
            this.platformSource = platformSource;
        }
    }
}
