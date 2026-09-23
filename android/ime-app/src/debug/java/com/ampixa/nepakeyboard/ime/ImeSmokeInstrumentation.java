package com.ampixa.nepakeyboard.ime;

import android.Manifest;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputMethodInfo;
import android.view.inputmethod.InputMethodManager;
import android.view.inputmethod.InputMethodSubtype;
import android.widget.EditText;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/** Platform-only architecture checks that run in the debug APK on cdjk. */
public final class ImeSmokeInstrumentation extends Instrumentation {
    private static final long TCG_PACK_READY_TIMEOUT_MS = 120_000L;
    private static final String PACK_VECTOR_ASSET = "nepa-packs/benchmark-vectors.json";
    private static final String ZERO_SHA256 =
            "00000000000000000000000000000000"
                    + "00000000000000000000000000000000";
    private static final int MAX_PACK_VECTOR_BYTES = 256 * 1024;

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        int resultCode = Activity.RESULT_CANCELED;
        try {
            Context context = getTargetContext();
            List<ReleasePackSpec> releasePacks = ReleasePackRegistry.installed(context);
            int defaultProfileCount = defaultEnabledProfileCount();
            assertEquals(
                    "declared targets",
                    GeneratedProfileCatalog.TARGET_COUNT,
                    LanguageRegistry.targetCountForTesting()
            );
            assertEquals(
                    "declared profiles",
                    GeneratedProfileCatalog.PROFILE_COUNT,
                    LanguageRegistry.all().size()
            );
            assertEquals(
                    "declared scripts",
                    GeneratedProfileCatalog.SCRIPT_COUNT,
                    LanguageRegistry.scriptCountForTesting()
            );
            assertEquals(
                    "available profiles",
                    GeneratedProfileCatalog.SELECTABLE_COUNT,
                    LanguageRegistry.available().size()
            );
            KeyboardProfile roman = LanguageRegistry.find(LanguageRegistry.NEPALI_ROMAN_ID);
            assertTrue("Romanized Nepali must exist", roman != null);
            assertTrue(
                    "Romanized Nepali must remain gated",
                    roman.availability() == KeyboardProfile.Availability.BLOCKED
            );
            assertTrue(
                    "Romanized Nepali uses alias lookup",
                    roman.lookupKind() == KeyboardProfile.LookupKind.ALIAS_PREFIX
            );
            assertTrue(
                    "Romanized Nepali keeps a compiled Latin visual layout separate from alias lookup",
                    KeyboardLayouts.hasLayoutForTesting(roman.layoutId())
                            && "Latn".equals(KeyboardLayouts.inputScriptForTesting(roman.layoutId()))
            );
            boolean unavailableLayoutRejected = false;
            try {
                KeyboardLayouts.forProfile(roman, false, false, false);
            } catch (IllegalStateException expected) {
                unavailableLayoutRejected = true;
            }
            assertTrue("gated profile rejected before layout resolution", unavailableLayoutRejected);
            KeyboardProfile bantawa = LanguageRegistry.find("bap-Deva-NP");
            assertTrue("named Bantawa profile exists", bantawa != null);
            assertTrue("Bantawa searchable under Rai/Kiranti", SettingsActivity.matchesProfileForTesting(
                    bantawa,
                    "rai"
            ));
            assertTrue("generic Rai profile must not exist", LanguageRegistry.find("rai") == null);
            assertTrue("Roman input is searchable", SettingsActivity.matchesProfileForTesting(
                    roman,
                    "romanized"
            ));
            assertEquals(
                    "explicit subtype profile",
                    LanguageRegistry.NEPALI_DIRECT_ID,
                    NepaInputMethodService.profileIdForSubtypeForTesting(
                            LanguageRegistry.NEPALI_DIRECT_ID,
                            "ne-NP"
                    )
            );
            assertEquals(
                    "mismatched exact subtype is rejected",
                    null,
                    NepaInputMethodService.profileIdForSubtypeForTesting(
                            LanguageRegistry.NEPALI_DIRECT_ID,
                            "en-US"
                    )
            );
            assertEquals(
                    "locale-only subtype is ambiguous",
                    null,
                    NepaInputMethodService.profileIdForSubtypeForTesting(null, "ne-NP")
            );
            for (KeyboardProfile candidate : LanguageRegistry.all()) {
                if (!candidate.isAvailable()) {
                    assertTrue("blocked reason", candidate.blockedReason() != null);
                    assertTrue("blocked detail", candidate.blockedDetail() != null);
                    assertTrue("blocked default", !candidate.defaultEnabled());
                }
            }

            LanguagePreferences preferences = new LanguagePreferences(context, "ime_smoke_profiles");
            preferences.clearForTesting();
            verifyPreferenceMigration(context);
            verifyPreferencePlatformReconciliation(context);
            assertEquals(
                    "default enabled", defaultProfileCount, preferences.enabledProfiles().size()
            );
            assertTrue("disable English", preferences.setEnabled(LanguageRegistry.ENGLISH_ID, false));
            assertEquals(
                    "fallback active profile",
                    LanguageRegistry.NEPALI_DIRECT_ID,
                    preferences.activeProfile().id()
            );
            assertTrue(
                    "cannot disable final profile",
                    !preferences.setEnabled(LanguageRegistry.NEPALI_DIRECT_ID, false)
            );
            assertTrue("re-enable English", preferences.setEnabled(LanguageRegistry.ENGLISH_ID, true));
            assertTrue("select English", preferences.setActive(LanguageRegistry.ENGLISH_ID));
            assertTrue(
                    "cannot enable gated Romanized Nepali",
                    !preferences.setEnabled(LanguageRegistry.NEPALI_ROMAN_ID, true)
            );
            assertTrue(
                    "cannot select gated Romanized Nepali",
                    !preferences.setActive(LanguageRegistry.NEPALI_ROMAN_ID)
            );
            assertEquals(
                    "cycle profile",
                    LanguageRegistry.NEPALI_DIRECT_ID,
                    preferences.cycle().id()
            );
            preferences.clearForTesting();

            KeyboardProfile english = LanguageRegistry.find(LanguageRegistry.ENGLISH_ID);
            KeyboardProfile nepali = LanguageRegistry.find(LanguageRegistry.NEPALI_DIRECT_ID);
            verifySuggestionReadinessContract(context, english);
            PackEvidence packEvidence = verifyReleasePacks(context, releasePacks);
            ComposingEvidence composing = verifyComposingSemantics(
                    context,
                    english,
                    nepali,
                    roman
            );
            BackspaceContractVectors.verify(this, context, english, nepali);
            KeyboardLayouts.Layout englishBase = KeyboardLayouts.forProfile(
                    english,
                    false,
                    false,
                    false
            );
            assertTrue("English q", englishBase.containsText("q"));
            assertTrue("English shift", KeyboardLayouts.forProfile(english, true, false, false).containsText("Q"));
            assertTrue("Nepali base", KeyboardLayouts.forProfile(nepali, false, false, false).containsText("ट"));
            assertTrue("Nepali shift", KeyboardLayouts.forProfile(nepali, true, false, false).containsText("ठ"));
            assertTrue("Nepali virama", KeyboardLayouts.forProfile(nepali, false, false, false).containsText("्"));
            assertTrue("numeric layer", KeyboardLayouts.forProfile(nepali, false, false, true).containsText("0"));
            KeySpec qKey = englishBase.keyForTesting("base.r0.k0");
            assertTrue("generated q key exists", qKey != null);
            assertEquals("generated q stable key ID", "base.r0.k0", qKey.keyId());
            assertEquals("generated q integer width", 100, qKey.widthUnits());
            assertTrue(
                    "generated q default input policy",
                    qKey.inputPolicy() == KeySpec.InputPolicy.DEFAULT
            );
            KeySpec orthographicWordKey = KeySpec.generatedText(
                    "fixture.orthographic",
                    "‘",
                    "‘",
                    "Orthographic word mark",
                    KeySpec.InputPolicy.ORTHOGRAPHIC_WORD,
                    100,
                    null
            );
            KeySpec conjunctJoinerKey = KeySpec.generatedText(
                    "fixture.joiner",
                    "ZWJ",
                    "\u200d",
                    "Devanagari zero width joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    100,
                    null
            );
            KeySpec newaConjunctJoinerKey = KeySpec.generatedText(
                    "fixture.newa-joiner",
                    "ZWJ",
                    "\u200d",
                    "Newa zero width joiner",
                    KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER,
                    100,
                    null
            );
            assertTrue(
                    "orthographic key policy",
                    orthographicWordKey.inputPolicy() == KeySpec.InputPolicy.ORTHOGRAPHIC_WORD
            );
            assertTrue(
                    "joiner key policy",
                    conjunctJoinerKey.inputPolicy()
                            == KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertTrue(
                    "Newa joiner key policy",
                    newaConjunctJoinerKey.inputPolicy()
                            == KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER
            );
            boolean invalidNewaJoinerRejected = false;
            try {
                KeySpec.generatedText(
                        "fixture.invalid-newa-joiner",
                        "word joiner",
                        "\u2060",
                        "Invalid Newa joiner payload",
                        KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER,
                        100,
                        null
                );
            } catch (IllegalArgumentException expected) {
                invalidNewaJoinerRejected = true;
            }
            assertTrue("invalid Newa joiner payload rejected", invalidNewaJoinerRejected);
            KeySpec languageKey = englishBase.keyForTesting("base.r3.k2");
            assertTrue("generated language key exists", languageKey != null);
            assertTrue(
                    "generated language hold action",
                    languageKey.holdAction() == KeySpec.HoldAction.OPEN_LANGUAGE_PICKER
            );

            PackageManager packageManager = context.getPackageManager();
            ComponentName service = new ComponentName(context, NepaInputMethodService.class);
            assertEquals(
                    "IME bind permission",
                    Manifest.permission.BIND_INPUT_METHOD,
                    packageManager.getServiceInfo(service, 0).permission
            );
            assertEquals(
                    "no internet permission",
                    PackageManager.PERMISSION_DENIED,
                    packageManager.checkPermission(Manifest.permission.INTERNET, context.getPackageName())
            );
            InputMethodManager inputMethodManager = (InputMethodManager) context.getSystemService(
                    Context.INPUT_METHOD_SERVICE
            );
            InputMethodInfo ownInputMethod = null;
            for (InputMethodInfo candidate : inputMethodManager.getInputMethodList()) {
                if (candidate.getPackageName().equals(service.getPackageName())
                        && candidate.getServiceName().equals(service.getClassName())) {
                    ownInputMethod = candidate;
                    break;
                }
            }
            assertTrue("generated IME metadata is installed", ownInputMethod != null);
            AndroidSubtypeRegistry subtypeRegistry = AndroidSubtypeRegistry.load(context);
            assertEquals(
                    "subtype registry IME identity",
                    ownInputMethod.getId(),
                    subtypeRegistry.inputMethodId()
            );
            Set<String> subtypeProfiles = new HashSet<>();
            Set<Integer> subtypeIds = new HashSet<>();
            for (int index = 0; index < ownInputMethod.getSubtypeCount(); index++) {
                InputMethodSubtype subtype = ownInputMethod.getSubtypeAt(index);
                String profileId = subtype.getExtraValueOf("profile");
                assertTrue("generated subtype profile is unique", subtypeProfiles.add(profileId));
                assertTrue("generated subtype ID is positive", subtype.hashCode() > 0);
                assertTrue("generated subtype ID is unique", subtypeIds.add(subtype.hashCode()));
                KeyboardProfile subtypeProfile = LanguageRegistry.find(profileId);
                assertTrue(
                        "generated subtype resolves through registry",
                        subtypeProfile != null
                                && subtypeProfile == subtypeRegistry.profileForSubtype(subtype)
                                && subtype.equals(subtypeRegistry.subtypeForProfile(profileId))
                );
                assertEquals(
                        "generated subtype language tag",
                        subtypeProfile.localeTag(),
                        subtype.getLanguageTag()
                );
                assertEquals(
                        "generated subtype display label",
                        expectedSubtypeLabel(subtypeProfile),
                        subtype.getDisplayName(
                                context,
                                ownInputMethod.getPackageName(),
                                ownInputMethod.getServiceInfo().applicationInfo
                        ).toString()
                );
            }
            Set<String> availableProfileIds = new HashSet<>();
            for (KeyboardProfile profile : LanguageRegistry.available()) {
                availableProfileIds.add(profile.id());
            }
            assertEquals("generated subtype profile set", availableProfileIds, subtypeProfiles);

            Intent settingsIntent = new Intent(context, SettingsActivity.class);
            settingsIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            SettingsActivity settingsActivity = (SettingsActivity) startActivitySync(settingsIntent);
            int[] settingsCounts = new int[2];
            runOnMainSync(() -> {
                assertTrue(
                        "language manager uses scrolling container",
                        settingsActivity.languageManagerScrollsForTesting()
                );
                assertTrue(
                        "language manager uses stable row IDs",
                        settingsActivity.languageManagerHasStableIdsForTesting()
                );
                assertEquals(
                        "language manager view types",
                        2,
                        settingsActivity.languageManagerViewTypeCountForTesting()
                );
                assertEquals(
                        "debug enabled section count",
                        LanguageRegistry.available().size(),
                        settingsActivity.languageManagerSectionCountForTesting(
                                SettingsActivity.LanguageSection.ENABLED
                        )
                );
                assertEquals(
                        "debug available-to-enable section starts empty",
                        0,
                        settingsActivity.languageManagerSectionCountForTesting(
                                SettingsActivity.LanguageSection.AVAILABLE_TO_ENABLE
                        )
                );
                assertEquals(
                        "debug later section count",
                        LanguageRegistry.all().size() - LanguageRegistry.available().size(),
                        settingsActivity.languageManagerSectionCountForTesting(
                                SettingsActivity.LanguageSection.LATER
                        )
                );
                assertTrue(
                        "debug language manager sections are ordered",
                        settingsActivity.languageManagerSectionsOrderedForTesting()
                );
                assertTrue(
                        "debug language manager section headings are accessible",
                        settingsActivity.languageManagerSectionHeadingsForTesting()
                );
                assertTrue(
                        "language manager recycles and rebinds rows",
                        settingsActivity.languageManagerRecyclesRowsForTesting()
                );
                Set<Long> managerIds = new HashSet<>();
                for (KeyboardProfile profile : LanguageRegistry.all()) {
                    assertTrue(
                            "language manager stable ID is unique",
                            managerIds.add(SettingsActivity.stableProfileIdForTesting(profile.id()))
                    );
                }
                settingsCounts[0] = settingsActivity.visibleLanguageProfilesForTesting();
                assertEquals(
                        "language manager shows all profiles",
                        GeneratedProfileCatalog.PROFILE_COUNT,
                        settingsCounts[0]
                );
                settingsActivity.setLanguageQueryForTesting("bantawa");
                assertEquals(
                        "language manager query state",
                        "bantawa",
                        settingsActivity.languageQueryForTesting()
                );
                settingsCounts[1] = settingsActivity.visibleLanguageProfilesForTesting();
                assertEquals("language manager filters a named language", 2, settingsCounts[1]);
                settingsActivity.setLanguageQueryForTesting("no-such-language");
                assertEquals(
                        "language manager empty state",
                        0,
                        settingsActivity.visibleLanguageProfilesForTesting()
                );
                settingsActivity.finish();
            });

            int noticeUiSources = 0;
            int layoutNoticeCount = 0;
            {
                Intent noticesIntent = new Intent(context, NoticesActivity.class);
                noticesIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                NoticesActivity noticesActivity = (NoticesActivity) startActivitySync(
                        noticesIntent
                );
                long noticeDeadline = SystemClock.elapsedRealtime() + 30_000L;
                while (!noticesActivity.noticesReadyForTesting()
                        && SystemClock.elapsedRealtime() < noticeDeadline) {
                    SystemClock.sleep(25L);
                }
                assertTrue("license notices load", noticesActivity.noticesReadyForTesting());
                noticeUiSources = noticesActivity.visibleNoticeSourcesForTesting();
                assertEquals(
                        "dictionary notice source count",
                        packEvidence.noticeSources,
                        noticeUiSources
                );
                layoutNoticeCount = noticesActivity.visibleLayoutNoticesForTesting();
                assertEquals(
                        "layout notice count",
                        GeneratedLayoutRegistry.LAYOUT_NOTICE_COUNT,
                        layoutNoticeCount
                );
                runOnMainSync(() -> {
                    assertTrue(
                            "license notices use a virtualized list",
                            noticesActivity.noticeListIsVirtualizedForTesting()
                    );
                    noticesActivity.finish();
                });
            }

            NepaInputView[] holder = new NepaInputView[1];
            RecordingListener recordingListener = new RecordingListener();
            runOnMainSync(() -> {
                holder[0] = new NepaInputView(context, recordingListener);
                holder[0].setProfile(nepali);
                assertTrue("tap Nepali key", holder[0].performTextKeyForTesting("ट"));
            });
            NepaInputView inputView = holder[0];
            assertEquals("rendered rows", 4, inputView.renderedRowCountForTesting());
            assertEquals("Nepali callback", "ट", recordingListener.lastText);

            File[] renders = new File[3];
            runOnMainSync(() -> {
                inputView.setProfile(english);
                verifyPickerHoldAccessibilityContract(
                        context,
                        inputView,
                        recordingListener,
                        english,
                        nepali
                );
                inputView.setSuggestionSnapshot(SuggestionSnapshot.ready(
                        new SuggestionActivation(1, english.id()),
                        Arrays.asList("hello", "help", "held")
                ));
                assertTrue(
                        "candidate accessibility contract",
                        inputView.candidateAccessibilityContractForTesting()
                );
                inputView.setSuggestionSnapshot(SuggestionSnapshot.ready(
                        new SuggestionActivation(2, english.id()),
                        Collections.singletonList("hello")
                ));
                assertEquals("single ready candidate", 1, inputView.visibleCandidateCountForTesting());
                assertTrue(
                        "hidden candidate slots clear stale accessibility labels",
                        inputView.candidateAccessibilityContractForTesting()
                );
                inputView.setSuggestionSnapshot(SuggestionSnapshot.ready(
                        new SuggestionActivation(3, english.id()),
                        Arrays.asList("hello", "help", "held")
                ));
                assertTrue("tap English key", inputView.performTextKeyForTesting("q"));
                renders[0] = render(context, inputView, "ime-english.png");
                verifyPixelKeyboardGeometry(inputView, "English");
                inputView.showLanguagePicker();
                assertTrue("picker visible", inputView.pickerVisibleForTesting());
                assertTrue(
                        "picker is accessibility-modal",
                        inputView.pickerIsAccessibilityModalForTesting()
                );
                assertTrue(
                        "picker blocks underlying keyboard interaction",
                        inputView.pickerBlocksUnderlyingKeyboardForTesting()
                );
                assertTrue(
                        "active picker row is selected",
                        inputView.pickerProfileSelectedForTesting(english.id())
                );
                CharSequence selectedDescription =
                        inputView.pickerProfileDescriptionForTesting(english.id());
                assertTrue(
                        "active picker row has localized selected description",
                        selectedDescription != null
                                && selectedDescription.toString().contains(
                                context.getString(R.string.selected_state)
                        )
                );
                assertEquals(
                        "picker controls",
                        4 + defaultProfileCount,
                        inputView.pickerChildCountForTesting()
                );
                assertEquals(
                        "picker profile rows",
                        defaultProfileCount,
                        inputView.pickerProfileCountForTesting()
                );
                assertTrue(
                        "picker profile list scrolls",
                        inputView.pickerUsesScrollingContainerForTesting()
                );
                assertTrue(
                        "picker profile list recycles rebound rows",
                        inputView.pickerRecyclesRowsForTesting()
                );
                renders[1] = render(context, inputView, "ime-picker.png");
                assertTrue("picker hide action closes", inputView.hidePicker());
                assertTrue(
                        "picker hide restores accessibility state",
                        inputView.pickerAccessibilityRestoredForTesting()
                );
                inputView.setProfile(nepali);
                inputView.setSuggestionSnapshot(SuggestionSnapshot.ready(
                        new SuggestionActivation(2, nepali.id()),
                        Arrays.asList("नेपाल", "नेपाली", "नमस्ते")
                ));
                assertEquals("ready candidate count", 3, inputView.visibleCandidateCountForTesting());
                renders[2] = render(context, inputView, "ime-nepali.png");
                verifyPixelKeyboardGeometry(inputView, "Nepali");

                inputView.setProfile(english);
                assertEquals(
                        "profile change clears suggestion state",
                        SuggestionSnapshot.Status.INACTIVE,
                        inputView.suggestionStatusForTesting()
                );
                assertEquals(
                        "profile change clears candidates",
                        0,
                        inputView.visibleCandidateCountForTesting()
                );
                assertTrue(
                        "profile change clears candidate accessibility state",
                        inputView.candidateAccessibilityContractForTesting()
                );
                SuggestionActivation uiActivation = new SuggestionActivation(3, english.id());
                inputView.setSuggestionSnapshot(SuggestionSnapshot.state(
                        uiActivation,
                        SuggestionSnapshot.Status.NO_MATCH
                ));
                assertEquals(
                        "no-match status is explicit",
                        SuggestionSnapshot.Status.NO_MATCH,
                        inputView.suggestionStatusForTesting()
                );
                assertTrue(
                        "no-match status is not actionable",
                        !inputView.performSuggestionRecoveryForTesting()
                );
                assertTrue(
                        "non-ready status clears candidate accessibility state",
                        inputView.candidateAccessibilityContractForTesting()
                );
                inputView.setSuggestionSnapshot(SuggestionSnapshot.state(
                        uiActivation,
                        SuggestionSnapshot.Status.UNAVAILABLE
                ));
                assertTrue(
                        "unavailable status exposes retry",
                        inputView.performSuggestionRecoveryForTesting()
                );
                assertEquals("retry status callback", 1, recordingListener.retryCount);
                inputView.setSuggestionSnapshot(SuggestionSnapshot.state(
                        uiActivation,
                        SuggestionSnapshot.Status.MISSING
                ));
                assertTrue(
                        "missing status opens language picker",
                        inputView.performSuggestionRecoveryForTesting()
                );
                assertTrue("missing recovery picker visible", inputView.pickerVisibleForTesting());
                assertTrue("missing recovery picker closes", inputView.hidePicker());
                assertTrue(
                        "missing recovery restores accessibility state",
                        inputView.pickerAccessibilityRestoredForTesting()
                );
                inputView.setSuggestionSnapshot(SuggestionSnapshot.state(
                        new SuggestionActivation(4, nepali.id()),
                        SuggestionSnapshot.Status.CORRUPT
                ));
                assertEquals(
                        "foreign-profile status is rejected by view",
                        SuggestionSnapshot.Status.INACTIVE,
                        inputView.suggestionStatusForTesting()
                );
            });
            assertEquals("English callback", "q", recordingListener.lastText);
            for (File render : renders) {
                assertTrue("render exists", render != null && render.isFile() && render.length() > 1024);
            }

            result.putString("status", "ok");
            result.putInt("declared_profiles", LanguageRegistry.all().size());
            result.putInt("declared_targets", LanguageRegistry.targetCountForTesting());
            result.putInt("declared_scripts", LanguageRegistry.scriptCountForTesting());
            result.putInt("available_profiles", LanguageRegistry.available().size());
            result.putInt("generated_subtypes", subtypeProfiles.size());
            result.putString(
                    "layout_lock_sha256",
                    GeneratedLayoutRegistry.LAYOUT_LOCK_SHA256
            );
            result.putString("release_pack_mode", packEvidence.mode);
            result.putInt("release_pack_count", packEvidence.count);
            result.putBoolean("release_pack_engine_switching", packEvidence.engineSwitching);
            result.putInt("dictionary_notice_sources", noticeUiSources);
            result.putInt("layout_notice_count", layoutNoticeCount);
            result.putBoolean(
                    "layout_notices_verified",
                    layoutNoticeCount == GeneratedLayoutRegistry.LAYOUT_NOTICE_COUNT
            );
            result.putBoolean("dictionary_notices_verified", packEvidence.count == 0
                    || noticeUiSources == packEvidence.noticeSources);
            result.putBoolean("romanized_nepali_release_gated", true);
            result.putBoolean("internet_permission_absent", true);
            result.putBoolean("language_manager_scrollable", true);
            result.putBoolean("language_manager_sections_verified", true);
            result.putInt("language_manager_profiles", settingsCounts[0]);
            result.putInt("language_manager_bantawa_matches", settingsCounts[1]);
            result.putBoolean("composing_candidate_replacement", composing.candidateReplacement);
            result.putBoolean("android_input_connection_replacement", composing.androidReplacement);
            result.putBoolean("orthographic_word_policy_verified", composing.orthographicWord);
            result.putBoolean("deva_joiner_policy_verified", composing.devaJoiner);
            result.putBoolean("android_deva_joiner_codepoints_verified", composing.androidJoiner);
            result.putBoolean("backspace_grapheme_vectors_verified", true);
            result.putBoolean("backspace_owned_composition_verified", true);
            result.putBoolean("backspace_committed_context_verified", true);
            result.putBoolean("backspace_fallback_verified", true);
            result.putBoolean("backspace_sink_private_no_read_verified", true);
            result.putBoolean("backspace_suggestion_touch_ownership_verified", true);
            result.putBoolean("backspace_zwj_tailoring_verified", true);
            result.putBoolean("newa_conjunct_joiner_verified", true);
            result.putBoolean("backspace_devanagari_state_rebuild_verified", true);
            result.putBoolean("backspace_selection_contract_verified", true);
            result.putBoolean("backspace_context_completeness_verified", true);
            result.putBoolean("delete_repeat_timing_verified", true);
            result.putBoolean("delete_touch_pointer_ownership_verified", true);
            result.putBoolean("delete_repeat_view_cancellation_verified", true);
            result.putBoolean("subtype_state_foundation_verified", true);
            result.putBoolean("tokenized_suggestion_readiness_verified", true);
            result.putBoolean("candidate_accessibility_foundation_verified", true);
            result.putBoolean("picker_modal_accessibility_foundation_verified", true);
            result.putBoolean("picker_hold_accessibility_action_verified", true);
            result.putBoolean("pixel_keyboard_geometry_verified", true);
            result.putBoolean("language_delete_separate_rows_verified", true);
            result.putBoolean("compact_language_control_verified", true);
            result.putInt("fixture_suggestion_calls", composing.suggestionCalls);
            result.putInt("nepali_rendered_rows", inputView.renderedRowCountForTesting());
            result.putInt("picker_controls", inputView.pickerChildCountForTesting());
            result.putInt("picker_profile_rows", inputView.pickerProfileCountForTesting());
            result.putBoolean(
                    "picker_profile_list_scrollable",
                    inputView.pickerUsesScrollingContainerForTesting()
            );
            result.putString("english_render", renders[0].getAbsolutePath());
            result.putString("picker_render", renders[1].getAbsolutePath());
            result.putString("nepali_render", renders[2].getAbsolutePath());
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            result.putString("status", "error");
            result.putString("error", failure.toString());
        }
        finish(resultCode, result);
    }

    private static void verifyPickerHoldAccessibilityContract(
            Context context,
            NepaInputView inputView,
            RecordingListener listener,
            KeyboardProfile english,
            KeyboardProfile nepali
    ) {
        CharSequence actionLabel = context.getString(R.string.choose_language);
        for (KeyboardProfile profile : Arrays.asList(english, nepali)) {
            inputView.setProfile(profile);
            KeyboardLayouts.Layout layout = KeyboardLayouts.forProfile(
                    profile,
                    false,
                    false,
                    false
            );
            for (String keyId : Arrays.asList("base.r3.k2", "base.r3.k3")) {
                KeySpec key = layout.keyForTesting(keyId);
                assertTrue(profile.id() + " picker hold key exists", key != null);
                assertEquals(
                        profile.id() + " picker hold content description unchanged " + keyId,
                        key.contentDescription(),
                        inputView.keyContentDescriptionForTesting(keyId)
                );
                assertTrue(
                        profile.id() + " labeled picker hold accessibility action " + keyId,
                        inputView.pickerHoldAccessibilityActionMatchesForTesting(
                                keyId,
                                actionLabel
                        )
                );
                assertTrue(
                        profile.id() + " picker hold accessibility dispatch " + keyId,
                        inputView.performPickerHoldAccessibilityActionForTesting(keyId)
                );
                assertTrue(
                        profile.id() + " picker opens from accessibility hold " + keyId,
                        inputView.pickerVisibleForTesting()
                );
                assertTrue(
                        profile.id() + " picker closes after accessibility hold " + keyId,
                        inputView.hidePicker()
                );
                assertTrue(
                        profile.id() + " picker modal state resets after hold " + keyId,
                        inputView.pickerAccessibilityRestoredForTesting()
                );
            }
            assertTrue(
                    profile.id() + " shift has no long-click accessibility action",
                    inputView.longClickAccessibilityActionAbsentForTesting("base.r3.k0")
            );
            assertTrue(
                    profile.id() + " ordinary globe tap dispatches",
                    inputView.performKeyIdForTesting("base.r3.k2")
            );
            assertEquals(
                    profile.id() + " ordinary globe tap action",
                    KeySpec.Action.LANGUAGE,
                    listener.lastKey.action()
            );
            assertTrue(
                    profile.id() + " ordinary space tap dispatches",
                    inputView.performKeyIdForTesting("base.r3.k3")
            );
            assertEquals(
                    profile.id() + " ordinary space tap action",
                    KeySpec.Action.SPACE,
                    listener.lastKey.action()
            );
        }
        inputView.setProfile(english);
        inputView.setProfile(nepali);
        inputView.setProfile(english);
        assertTrue(
                "picker hold action survives repeated profile rerender",
                inputView.pickerHoldAccessibilityActionMatchesForTesting(
                        "base.r3.k2",
                        actionLabel
                )
        );
    }

    private static void verifyPreferenceMigration(Context context) {
        String name = "ime_smoke_profile_migration";
        SharedPreferences raw = context.getSharedPreferences(name, Context.MODE_PRIVATE);
        raw.edit().clear().commit();

        Set<String> allProfileIds = new HashSet<>();
        for (KeyboardProfile profile : LanguageRegistry.all()) {
            allProfileIds.add(profile.id());
        }
        raw.edit()
                .putStringSet("enabled", allProfileIds)
                .putString("catalog_id", "stale-catalog")
                .commit();
        LanguagePreferences migrated = new LanguagePreferences(context, name);
        assertEquals(
                "catalog migration filters blocked rows",
                LanguageRegistry.available().size(),
                migrated.enabledProfiles().size()
        );

        raw.edit()
                .putStringSet("enabled", new HashSet<>())
                .putString("catalog_id", "stale-catalog")
                .commit();
        assertEquals("zero-profile migration restores fallback", 1, migrated.enabledProfiles().size());

        Set<String> oneProfile = new HashSet<>();
        oneProfile.add(LanguageRegistry.NEPALI_DIRECT_ID);
        raw.edit()
                .putStringSet("enabled", oneProfile)
                .putString("pending_subtype", LanguageRegistry.ENGLISH_ID)
                .putString("catalog_id", "stale-catalog")
                .commit();
        assertEquals("one-profile migration preserves selection", 1, migrated.enabledProfiles().size());
        assertEquals(
                "one-profile migration identity",
                LanguageRegistry.NEPALI_DIRECT_ID,
                migrated.enabledProfiles().get(0).id()
        );
        assertTrue("catalog migration filters stale pending subtype", migrated.pendingProfile() == null);
        raw.edit().clear().commit();
    }

    private static void verifyPreferencePlatformReconciliation(Context context) {
        LanguagePreferences preferences = new LanguagePreferences(
                context,
                "ime_smoke_profile_reconciliation"
        );
        preferences.clearForTesting();
        assertTrue(
                "request active Nepali",
                preferences.requestActive(LanguageRegistry.NEPALI_DIRECT_ID)
        );
        assertEquals(
                "pending Nepali subtype",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.pendingProfile().id()
        );
        assertEquals(
                "matching platform observation",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.observePlatformProfile(LanguageRegistry.NEPALI_DIRECT_ID).id()
        );
        assertTrue("matching observation clears pending subtype", preferences.pendingProfile() == null);

        assertTrue(
                "disable non-active English",
                preferences.setEnabled(LanguageRegistry.ENGLISH_ID, false)
        );
        assertTrue("English disabled locally", !preferences.isEnabled(LanguageRegistry.ENGLISH_ID));
        assertEquals(
                "platform selection auto-enables English",
                LanguageRegistry.ENGLISH_ID,
                preferences.observePlatformProfile(LanguageRegistry.ENGLISH_ID).id()
        );
        assertTrue("platform-selected English enabled", preferences.isEnabled(LanguageRegistry.ENGLISH_ID));

        assertTrue(
                "request Nepali over platform English",
                preferences.requestActive(LanguageRegistry.NEPALI_DIRECT_ID)
        );
        assertEquals(
                "stale platform observation cannot replace pending Nepali",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.observePlatformProfile(LanguageRegistry.ENGLISH_ID).id()
        );
        assertEquals(
                "pending Nepali survives stale observation",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.pendingProfile().id()
        );
        preferences.observePlatformProfile(LanguageRegistry.NEPALI_DIRECT_ID);
        assertTrue("converged Nepali clears pending", preferences.pendingProfile() == null);

        assertEquals(
                "unknown platform subtype preserves active profile",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.observePlatformProfile("removed-profile").id()
        );
        assertEquals(
                "unknown platform subtype requests active profile",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.pendingProfile().id()
        );
        preferences.observePlatformProfile(LanguageRegistry.NEPALI_DIRECT_ID);
        assertTrue("reconfirmed active subtype clears pending", preferences.pendingProfile() == null);

        assertTrue(
                "disable active Nepali",
                preferences.setEnabled(LanguageRegistry.NEPALI_DIRECT_ID, false)
        );
        assertEquals(
                "active disable selects deterministic fallback",
                LanguageRegistry.ENGLISH_ID,
                preferences.activeProfile().id()
        );
        assertEquals(
                "active disable requests fallback subtype",
                LanguageRegistry.ENGLISH_ID,
                preferences.pendingProfile().id()
        );
        preferences.clearForTesting();
    }

    private static String expectedSubtypeLabel(KeyboardProfile profile) {
        int methodsForTarget = 0;
        for (KeyboardProfile candidate : LanguageRegistry.available()) {
            if (candidate.languageId().equals(profile.languageId())) {
                methodsForTarget++;
            }
        }
        return methodsForTarget > 1
                ? profile.nativeName() + " · " + profile.detail()
                : profile.nativeName();
    }

    private static void verifySuggestionReadinessContract(
            Context context,
            KeyboardProfile english
    ) throws Exception {
        NkpSuggestionEngine missing = new NkpSuggestionEngine(Collections.emptyList());
        try {
            RecordingTextSink literalSink = new RecordingTextSink();
            ComposingSession literal = new ComposingSession(missing);
            literal.start(english, true, false, literalSink);
            literal.appendText("h", literalSink);
            assertEquals(
                    "missing pack has explicit state",
                    SuggestionSnapshot.Status.MISSING,
                    literal.suggestionSnapshot().status()
            );
            assertEquals("missing pack preserves literal composing", "h", literalSink.text());
            literal.appendText(" ", literalSink);
            assertEquals("missing pack preserves literal commit", "h ", literalSink.text());

            RecordingTextSink privateSink = new RecordingTextSink();
            ComposingSession privateSession = new ComposingSession(missing);
            privateSession.start(english, true, true, privateSink);
            privateSession.appendText("s", privateSink);
            assertEquals("private field keeps literal text", "s", privateSink.text());
            assertEquals(
                    "private field suggestion state",
                    SuggestionSnapshot.Status.INACTIVE,
                    privateSession.suggestionSnapshot().status()
            );
        } finally {
            missing.close();
        }

        File fakePack = File.createTempFile("readiness-", ".nkp", context.getCacheDir());
        try (FileOutputStream output = new FileOutputStream(fakePack, false)) {
            output.write(1);
        }
        CountDownLatch firstEntered = new CountDownLatch(1);
        CountDownLatch firstRelease = new CountDownLatch(1);
        CountDownLatch secondEntered = new CountDownLatch(1);
        CountDownLatch secondRelease = new CountDownLatch(1);
        AtomicInteger opens = new AtomicInteger();
        AtomicReference<SuggestionActivation> callback = new AtomicReference<>();
        ReleasePackSpec spec = new ReleasePackSpec(
                english.id(),
                english.packBinding(),
                fakePack,
                ZERO_SHA256
        );
        NkpSuggestionEngine controlled = new NkpSuggestionEngine(
                Collections.singletonList(spec),
                callback::set,
                (file, expectedSha256) -> {
                    int attempt = opens.incrementAndGet();
                    if (attempt == 1) {
                        firstEntered.countDown();
                        awaitLoaderGate(firstRelease, "first readiness load");
                        throw new IOException("controlled transient failure");
                    }
                    secondEntered.countDown();
                    awaitLoaderGate(secondRelease, "second readiness load");
                    throw new SecurityException("controlled integrity failure");
                }
        );
        try {
            SuggestionQuery query = new SuggestionQuery(english, "h", false);
            SuggestionActivation first = controlled.activate(english);
            assertTrue(
                    "controlled loader entered",
                    firstEntered.await(30, TimeUnit.SECONDS)
            );
            assertEquals(
                    "cold pack loading state",
                    SuggestionSnapshot.Status.LOADING,
                    controlled.suggest(first, query).status()
            );
            controlled.suspend();
            SuggestionActivation second = controlled.activate(english);
            assertEquals(
                    "old same-profile activation is inactive",
                    SuggestionSnapshot.Status.INACTIVE,
                    controlled.suggest(first, query).status()
            );
            firstRelease.countDown();
            awaitSuggestionStatus(
                    controlled,
                    second,
                    query,
                    SuggestionSnapshot.Status.UNAVAILABLE
            );
            awaitExactCallback(callback, second, "same-profile replacement activation");
            assertTrue("stale activation cannot retry", !controlled.retry(first));
            assertTrue("current unavailable activation retries", controlled.retry(second));
            assertTrue(
                    "retry loader entered",
                    secondEntered.await(30, TimeUnit.SECONDS)
            );
            assertEquals(
                    "explicit retry returns to loading",
                    SuggestionSnapshot.Status.LOADING,
                    controlled.suggest(second, query).status()
            );
            secondRelease.countDown();
            awaitSuggestionStatus(
                    controlled,
                    second,
                    query,
                    SuggestionSnapshot.Status.CORRUPT
            );
            assertTrue("corrupt state is not retried in process", !controlled.retry(second));
        } finally {
            firstRelease.countDown();
            secondRelease.countDown();
            controlled.close();
            fakePack.delete();
        }
    }

    private static void awaitLoaderGate(CountDownLatch gate, String label) throws IOException {
        try {
            if (!gate.await(30, TimeUnit.SECONDS)) {
                throw new IOException(label + " timed out");
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IOException(label + " interrupted", interrupted);
        }
    }

    private static void awaitSuggestionStatus(
            NkpSuggestionEngine engine,
            SuggestionActivation activation,
            SuggestionQuery query,
            SuggestionSnapshot.Status expected
    ) {
        long deadline = SystemClock.elapsedRealtime() + TCG_PACK_READY_TIMEOUT_MS;
        do {
            SuggestionSnapshot.Status actual = engine.suggest(activation, query).status();
            if (actual == expected) {
                return;
            }
            if (actual != SuggestionSnapshot.Status.LOADING) {
                throw new AssertionError(
                        "unexpected suggestion state: expected " + expected + ", got " + actual
                );
            }
            SystemClock.sleep(25L);
        } while (SystemClock.elapsedRealtime() < deadline);
        throw new AssertionError("suggestion state timed out: " + expected);
    }

    private static void awaitExactCallback(
            AtomicReference<SuggestionActivation> observed,
            SuggestionActivation expected,
            String label
    ) {
        long deadline = SystemClock.elapsedRealtime() + TCG_PACK_READY_TIMEOUT_MS;
        do {
            SuggestionActivation actual = observed.get();
            if (actual == expected) {
                return;
            }
            if (actual != null && actual != expected) {
                throw new AssertionError(label + " delivered a stale activation");
            }
            SystemClock.sleep(25L);
        } while (SystemClock.elapsedRealtime() < deadline);
        throw new AssertionError(label + " callback timed out");
    }

    private static PackEvidence verifyReleasePacks(
            Context context,
            List<ReleasePackSpec> specs
    ) throws Exception {
        if (specs.isEmpty()) {
            return new PackEvidence("not_staged", 0, false, 0);
        }
        List<PackVector> vectors = readPackVectors(context);
        assertEquals("staged release-pack count", LanguageRegistry.available().size(), specs.size());
        assertEquals("release-pack vector count", specs.size(), vectors.size());
        int noticeSources = 0;
        Set<String> countedNoticeArtifacts = new HashSet<>();
        for (PackVector vector : vectors) {
            ReleasePackSpec spec = findPack(specs, vector.profileId);
            NkpBundle.NoticeDocument notices = verifyPack(spec, vector);
            String artifactKey = vector.packId + ":" + vector.artifactSha256;
            if (countedNoticeArtifacts.add(artifactKey)) {
                noticeSources += notices.sources().size();
            }
        }

        NkpSuggestionEngine engine = new NkpSuggestionEngine(specs);
        try {
            for (PackVector vector : vectors) {
                KeyboardProfile profile = LanguageRegistry.find(vector.profileId);
                assertTrue("release vector profile is available", profile != null && profile.isAvailable());
                SuggestionActivation activation = engine.activate(profile);
                assertEquals(
                        vector.profileId + " release engine",
                        vector.expectedSurface,
                        awaitFirstSuggestion(engine, activation, profile, vector.query)
                );
                assertEquals(
                        vector.profileId + " verified no-match state",
                        SuggestionSnapshot.Status.NO_MATCH,
                        engine.suggest(
                                activation,
                                new SuggestionQuery(profile, "\u0378", false)
                        ).status()
                );
            }
        } finally {
            engine.close();
        }
        return new PackEvidence("staged_release", specs.size(), true, noticeSources);
    }

    private static ReleasePackSpec findPack(List<ReleasePackSpec> specs, String profileId) {
        for (ReleasePackSpec spec : specs) {
            if (profileId.equals(spec.profileId())) {
                return spec;
            }
        }
        throw new AssertionError("missing staged release pack for " + profileId);
    }

    private static NkpBundle.NoticeDocument verifyPack(
            ReleasePackSpec spec,
            PackVector vector
    ) throws Exception {
        String label = vector.profileId;
        assertEquals(label + " binding pack ID", vector.packId, spec.packId());
        assertEquals(label + " binding SHA-256", vector.artifactSha256, spec.artifactSha256());
        if (spec.file().exists()) {
            assertTrue(label + " remove cached extraction", spec.file().delete());
        }
        File materialized = spec.materialize();
        assertTrue(label + " materialized file", materialized.isFile());
        assertEquals(
                label + " idempotent materialization",
                materialized.getCanonicalPath(),
                spec.materialize().getCanonicalPath()
        );
        try (NkpBundle bundle = NkpBundle.open(materialized, vector.artifactSha256)) {
            assertEquals(label + " NKP pack ID", vector.packId, bundle.packId());
            assertEquals(label + " NKP release mode", "release", bundle.releaseMode());
            assertEquals(
                    label + " candidate count",
                    vector.candidateCount,
                    bundle.candidateCount()
            );
            List<NkpBundle.Suggestion> suggestions = "alias_prefix".equals(vector.lookupKind)
                    ? bundle.suggestAliases(vector.query)
                    : bundle.suggestSurface(vector.query);
            assertTrue(label + " reviewed lookup", !suggestions.isEmpty());
            assertEquals(
                    label + " first surface",
                    vector.expectedSurface,
                    suggestions.get(0).surface()
            );
        }
        NkpBundle.NoticeDocument notices = NkpBundle.readNotices(
                materialized,
                vector.artifactSha256
        );
        boolean wrongHashRejected = false;
        try {
            NkpBundle.readNotices(materialized, ZERO_SHA256);
        } catch (SecurityException expectedFailure) {
            wrongHashRejected = true;
        }
        assertTrue(label + " notice SHA gate", wrongHashRejected);
        assertEquals(label + " notice pack ID", vector.packId, notices.packId());
        assertEquals(
                label + " artifact license",
                vector.artifactLicense,
                notices.artifactLicense()
        );
        assertTrue(label + " notice sources", !notices.sources().isEmpty());
        for (NkpBundle.NoticeSource source : notices.sources()) {
            assertTrue(label + " notice source ID", !source.sourceId().isEmpty());
            assertTrue(label + " notice title", !source.title().isEmpty());
            assertTrue(label + " notice license", !source.license().isEmpty());
            assertTrue(label + " source URL", !source.sourceUrl().isEmpty());
            assertTrue(label + " license URL", !source.licenseUrl().isEmpty());
            assertTrue(label + " license notice", !source.licenseNotice().isEmpty());
        }
        return notices;
    }

    private static List<PackVector> readPackVectors(Context context) throws Exception {
        byte[] encoded;
        try (InputStream input = context.getAssets().open(PACK_VECTOR_ASSET);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8 * 1024];
            int total = 0;
            int count;
            while ((count = input.read(buffer)) != -1) {
                total += count;
                if (total > MAX_PACK_VECTOR_BYTES) {
                    throw new IllegalStateException("release-pack vectors exceed size limit");
                }
                output.write(buffer, 0, count);
            }
            encoded = output.toByteArray();
        }
        JSONObject root = new JSONObject(new String(encoded, java.nio.charset.StandardCharsets.UTF_8));
        if (root.length() != 1 || !root.has("bindings")) {
            throw new IllegalStateException("release-pack vector root is invalid");
        }
        JSONArray rows = root.getJSONArray("bindings");
        List<PackVector> result = new ArrayList<>(rows.length());
        Set<String> profiles = new HashSet<>();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.getJSONObject(index);
            if (row.length() != 15 || !"release".equals(row.getString("release_mode"))) {
                throw new IllegalStateException("release-pack vector has unexpected fields");
            }
            String profileId = row.getString("profile_id");
            JSONArray queries = row.getJSONArray("benchmark_queries");
            if (!profiles.add(profileId) || queries.length() < 1 || queries.length() > 64) {
                throw new IllegalStateException("release-pack vector identity is invalid");
            }
            result.add(new PackVector(
                    profileId,
                    row.getString("pack_id"),
                    row.getString("artifact_sha256"),
                    row.getString("artifact_license"),
                    requiredExactInt(row.get("candidate_count"), "candidate_count"),
                    row.getString("lookup_kind"),
                    row.getString("validation_query"),
                    row.getString("validation_expected_surface")
            ));
        }
        return result;
    }

    private static int requiredExactInt(Object value, String label) {
        if (value instanceof Integer) {
            return (Integer) value;
        }
        if (value instanceof Long
                && (Long) value >= Integer.MIN_VALUE
                && (Long) value <= Integer.MAX_VALUE) {
            return ((Long) value).intValue();
        }
        throw new IllegalStateException(label + " must be an exact integer");
    }

    private static int defaultEnabledProfileCount() {
        int count = 0;
        for (KeyboardProfile profile : LanguageRegistry.available()) {
            if (profile.defaultEnabled()) {
                count++;
            }
        }
        return count;
    }

    private static String awaitFirstSuggestion(
            NkpSuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            String prefix
    ) {
        long deadline = SystemClock.elapsedRealtime() + TCG_PACK_READY_TIMEOUT_MS;
        SuggestionQuery query = new SuggestionQuery(profile, prefix, false);
        do {
            SuggestionSnapshot snapshot = engine.suggest(activation, query);
            if (snapshot.status() == SuggestionSnapshot.Status.READY) {
                return snapshot.candidates().get(0);
            }
            if (snapshot.status() == SuggestionSnapshot.Status.MISSING
                    || snapshot.status() == SuggestionSnapshot.Status.CORRUPT
                    || snapshot.status() == SuggestionSnapshot.Status.UNAVAILABLE) {
                throw new AssertionError(
                        "release engine failed for " + profile.id() + ": " + snapshot.status()
                );
            }
            SystemClock.sleep(25L);
        } while (SystemClock.elapsedRealtime() < deadline);
        throw new AssertionError("release engine timed out for " + profile.id());
    }

    private static void assertTrue(String label, boolean value) {
        if (!value) {
            throw new AssertionError(label);
        }
    }

    private static void assertEquals(String label, Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + ", got " + actual);
        }
    }

    private static File render(Context context, View view, String name) {
        int width = 1080;
        int heightLimit = 900;
        layoutForPixel(view, width, heightLimit);
        int height = view.getMeasuredHeight();
        boolean keyboardGeometryValid = view instanceof NepaInputView
                && (((NepaInputView) view).pickerVisibleForTesting()
                        || ((NepaInputView) view).visualGeometryContractForTesting());
        assertTrue(name + " compact render geometry",
                height > 0
                        && height <= heightLimit
                        && keyboardGeometryValid);
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        view.draw(canvas);
        File output = new File(context.getFilesDir(), name);
        try (FileOutputStream stream = new FileOutputStream(output, false)) {
            if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                throw new IllegalStateException("PNG encoder rejected " + name);
            }
        } catch (Exception exception) {
            throw new IllegalStateException("could not write " + name, exception);
        } finally {
            bitmap.recycle();
        }
        return output;
    }

    private static void verifyPixelKeyboardGeometry(NepaInputView view, String label) {
        layoutForPixel(view, 1080, 900);
        assertTrue(label + " base Pixel geometry", view.visualGeometryContractForTesting());
        assertEquals(
                label + " base Backspace character row",
                view.renderedRowCountForTesting() - 2,
                view.actionRowIndexForTesting(KeySpec.Action.DELETE)
        );
        assertEquals(
                label + " base globe bottom row",
                view.renderedRowCountForTesting() - 1,
                view.actionRowIndexForTesting(KeySpec.Action.LANGUAGE)
        );

        view.setShifted(true);
        layoutForPixel(view, 1080, 900);
        assertTrue(label + " shift Pixel geometry", view.visualGeometryContractForTesting());
        view.showSymbols();
        layoutForPixel(view, 1080, 900);
        assertTrue(label + " symbols Pixel geometry", view.visualGeometryContractForTesting());
        view.setNumeric(true);
        layoutForPixel(view, 1080, 1100);
        assertTrue(label + " numeric Pixel geometry", view.visualGeometryContractForTesting());
        view.setNumeric(false);
        view.setShifted(false);
        view.showLetters();
        layoutForPixel(view, 1080, 900);
        assertTrue(label + " restored base Pixel geometry", view.visualGeometryContractForTesting());
    }

    private static void layoutForPixel(View view, int width, int height) {
        view.measure(
                View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.AT_MOST)
        );
        view.layout(0, 0, width, view.getMeasuredHeight());
    }

    private ComposingEvidence verifyComposingSemantics(
            Context context,
            KeyboardProfile english,
            KeyboardProfile nepali,
            KeyboardProfile roman
    ) {
        FixtureSuggestionEngine engine = new FixtureSuggestionEngine();

        RecordingTextSink replacementSink = new RecordingTextSink();
        ComposingSession replacement = new ComposingSession(engine);
        replacement.start(english, true, false, replacementSink);
        replacement.appendText("h", replacementSink);
        replacement.appendText("e", replacementSink);
        replacement.appendText("l", replacementSink);
        assertEquals("incremental editor text", "hel", replacementSink.text());
        assertEquals("incremental composing text", "hel", replacement.composingText());
        assertEquals(
                "incremental composing calls",
                Arrays.asList("h", "he", "hel"),
                replacementSink.composingCalls
        );
        assertEquals("English candidate", "hello", replacement.candidates().get(0));
        assertEquals("query prefix", "hel", engine.lastQuery().composingText());
        assertTrue("candidate selected", replacement.selectCandidate("hello", replacementSink));
        assertEquals("candidate replaces prefix", "hello", replacementSink.text());
        assertTrue("candidate clears composition", !replacement.hasComposingText());
        assertTrue("stale candidate rejected", !replacement.selectCandidate("hello", replacementSink));
        assertEquals("stale candidate leaves text", "hello", replacementSink.text());

        RecordingTextSink separatorSink = new RecordingTextSink();
        ComposingSession separator = new ComposingSession(engine);
        separator.start(english, true, false, separatorSink);
        separator.appendText("h", separatorSink);
        separator.appendText("e", separatorSink);
        separator.appendText("l", separatorSink);
        separator.appendText(" ", separatorSink);
        assertEquals("space commits raw input", "hel ", separatorSink.text());
        assertTrue("space clears composition", !separator.hasComposingText());
        separator.appendText("n", separatorSink);
        separator.appendText("e", separatorSink);
        separator.appendText(",", separatorSink);
        assertEquals("punctuation commits raw input", "hel ne,", separatorSink.text());

        RecordingTextSink asciiConnectorSink = new RecordingTextSink();
        ComposingSession asciiConnector = new ComposingSession(engine);
        asciiConnector.start(english, true, false, asciiConnectorSink);
        asciiConnector.appendText("d", asciiConnectorSink);
        asciiConnector.appendText("o", asciiConnectorSink);
        asciiConnector.appendText("n", asciiConnectorSink);
        asciiConnector.appendText("'", asciiConnectorSink);
        asciiConnector.appendText("t", asciiConnectorSink);
        assertEquals("ASCII apostrophe stays in word", "don't", asciiConnectorSink.text());
        assertEquals("ASCII apostrophe stays composing", "don't", asciiConnector.composingText());

        RecordingTextSink curlyConnectorSink = new RecordingTextSink();
        ComposingSession curlyConnector = new ComposingSession(engine);
        curlyConnector.start(english, true, false, curlyConnectorSink);
        curlyConnector.appendText("d", curlyConnectorSink);
        curlyConnector.appendText("o", curlyConnectorSink);
        curlyConnector.appendText("g", curlyConnectorSink);
        curlyConnector.appendText("s", curlyConnectorSink);
        curlyConnector.appendText("’", curlyConnectorSink);
        assertEquals("curly apostrophe stays in word", "dogs’", curlyConnectorSink.text());
        assertEquals("curly apostrophe stays composing", "dogs’", curlyConnector.composingText());

        RecordingTextSink leadingQuoteSink = new RecordingTextSink();
        ComposingSession leadingQuote = new ComposingSession(engine);
        leadingQuote.start(english, true, false, leadingQuoteSink);
        leadingQuote.appendText("'", leadingQuoteSink);
        assertEquals("leading ASCII quote commits punctuation", "'", leadingQuoteSink.text());
        assertTrue("leading ASCII quote does not compose", !leadingQuote.hasComposingText());
        leadingQuote.appendText("d", leadingQuoteSink);
        assertEquals("word after leading ASCII quote composes", "d", leadingQuote.composingText());

        RecordingTextSink leadingCurlyQuoteSink = new RecordingTextSink();
        ComposingSession leadingCurlyQuote = new ComposingSession(engine);
        leadingCurlyQuote.start(english, true, false, leadingCurlyQuoteSink);
        leadingCurlyQuote.appendText("’", leadingCurlyQuoteSink);
        assertEquals("leading curly quote commits punctuation", "’", leadingCurlyQuoteSink.text());
        assertTrue("leading curly quote does not compose", !leadingCurlyQuote.hasComposingText());

        RecordingTextSink orthographicSink = new RecordingTextSink();
        ComposingSession orthographic = new ComposingSession(engine);
        orthographic.start(english, true, false, orthographicSink);
        orthographic.appendText("a", orthographicSink);
        orthographic.appendText(
                "‘",
                KeySpec.InputPolicy.ORTHOGRAPHIC_WORD,
                orthographicSink
        );
        orthographic.appendText("b", orthographicSink);
        assertEquals(
                "reviewed U+2018 stays inside an active word",
                "a‘b",
                orthographic.composingText()
        );
        orthographic.candidates();
        assertEquals(
                "reviewed U+2018 reaches the suggestion query",
                "a‘b",
                engine.lastQuery().composingText()
        );

        RecordingTextSink leadingOrthographicSink = new RecordingTextSink();
        ComposingSession leadingOrthographic = new ComposingSession(engine);
        leadingOrthographic.start(english, true, false, leadingOrthographicSink);
        leadingOrthographic.appendText(
                "‘",
                KeySpec.InputPolicy.ORTHOGRAPHIC_WORD,
                leadingOrthographicSink
        );
        assertEquals(
                "leading reviewed U+2018 stays in the orthographic token",
                "‘",
                leadingOrthographic.composingText()
        );
        assertTrue(
                "leading reviewed U+2018 composes",
                leadingOrthographic.hasComposingText()
        );
        leadingOrthographic.appendText("आ", leadingOrthographicSink);
        assertEquals(
                "leading reviewed U+2018 accepts following word text",
                "‘आ",
                leadingOrthographic.composingText()
        );

        RecordingTextSink genericLeftQuoteSink = new RecordingTextSink();
        ComposingSession genericLeftQuote = new ComposingSession(engine);
        genericLeftQuote.start(english, true, false, genericLeftQuoteSink);
        genericLeftQuote.appendText("a", genericLeftQuoteSink);
        genericLeftQuote.appendText("‘", genericLeftQuoteSink);
        assertEquals(
                "generic U+2018 remains a boundary",
                "a‘",
                genericLeftQuoteSink.text()
        );
        assertTrue(
                "generic U+2018 clears composition",
                !genericLeftQuote.hasComposingText()
        );

        RecordingTextSink joinerSink = new RecordingTextSink();
        ComposingSession joiner = new ComposingSession(engine);
        joiner.start(nepali, true, false, joinerSink);
        appendDevanagariVirama(joiner, joinerSink);
        int beforeBufferedJoiner = joinerSink.editorCalls.size();
        joiner.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                joinerSink
        );
        assertEquals(
                "buffered ZWJ performs no editor call",
                beforeBufferedJoiner,
                joinerSink.editorCalls.size()
        );
        joiner.appendText("ष", joinerSink);
        assertEquals(
                "ZWJ and following letter use one editor update",
                beforeBufferedJoiner + 1,
                joinerSink.editorCalls.size()
        );
        assertEquals("exact ZWJ conjunct code points", "क्\u200dष", joinerSink.text());
        assertTrue(
                "ZWJ continuation is atomic",
                joinerSink.editorCalls.get(joinerSink.editorCalls.size() - 1)
                        .endsWith("\u200dष")
        );
        assertNoEditorCallEndsInJoiner("ZWJ composing path", joinerSink);

        RecordingTextSink nonJoinerSink = new RecordingTextSink();
        ComposingSession nonJoiner = new ComposingSession(engine);
        nonJoiner.start(nepali, true, false, nonJoinerSink);
        appendDevanagariVirama(nonJoiner, nonJoinerSink);
        int beforeLastTap = nonJoinerSink.editorCalls.size();
        nonJoiner.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                nonJoinerSink
        );
        nonJoiner.appendText(
                "\u200c",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                nonJoinerSink
        );
        assertEquals(
                "repeated joiner taps remain buffered",
                beforeLastTap,
                nonJoinerSink.editorCalls.size()
        );
        nonJoiner.appendText("ष", nonJoinerSink);
        assertEquals("last joiner tap wins", "क्\u200cष", nonJoinerSink.text());
        assertNoEditorCallEndsInJoiner("ZWNJ composing path", nonJoinerSink);

        RecordingTextSink markedBaseSink = new RecordingTextSink();
        ComposingSession markedBase = new ComposingSession(engine);
        markedBase.start(nepali, true, false, markedBaseSink);
        markedBase.appendText("क", markedBaseSink);
        markedBase.appendText("़", markedBaseSink);
        markedBase.appendText("्", markedBaseSink);
        markedBase.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                markedBaseSink
        );
        markedBase.appendText("ष", markedBaseSink);
        assertEquals(
                "Devanagari mark preserves the owned base before virama",
                "क़्\u200dष",
                markedBaseSink.text()
        );
        assertNoEditorCallEndsInJoiner("marked Devanagari base", markedBaseSink);

        RecordingTextSink privateJoinerSink = new RecordingTextSink();
        ComposingSession privateJoiner = new ComposingSession(engine);
        privateJoiner.start(nepali, true, true, privateJoinerSink);
        appendDevanagariVirama(privateJoiner, privateJoinerSink);
        int beforePrivateJoiner = privateJoinerSink.editorCalls.size();
        privateJoiner.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                privateJoinerSink
        );
        assertEquals(
                "private buffered ZWJ performs no editor call",
                beforePrivateJoiner,
                privateJoinerSink.editorCalls.size()
        );
        privateJoiner.appendText("ष", privateJoinerSink);
        assertEquals(
                "private ZWJ and following letter use one commit",
                beforePrivateJoiner + 1,
                privateJoinerSink.editorCalls.size()
        );
        assertEquals(
                "private exact ZWJ conjunct code points",
                "क्\u200dष",
                privateJoinerSink.text()
        );
        assertNoEditorCallEndsInJoiner("ZWJ private path", privateJoinerSink);

        RecordingTextSink invalidJoinerSink = new RecordingTextSink();
        ComposingSession invalidJoiner = new ComposingSession(engine);
        invalidJoiner.start(nepali, true, false, invalidJoinerSink);
        invalidJoiner.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                invalidJoinerSink
        );
        assertTrue("joiner at token start is a no-op", invalidJoinerSink.editorCalls.isEmpty());
        invalidJoiner.appendText("्", invalidJoinerSink);
        int afterLoneVirama = invalidJoinerSink.editorCalls.size();
        invalidJoiner.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                invalidJoinerSink
        );
        assertEquals(
                "joiner after lone virama is a no-op",
                afterLoneVirama,
                invalidJoinerSink.editorCalls.size()
        );
        RecordingTextSink nonDevaHistorySink = new RecordingTextSink();
        ComposingSession nonDevaHistory = new ComposingSession(engine);
        nonDevaHistory.start(nepali, true, false, nonDevaHistorySink);
        nonDevaHistory.appendText("x", nonDevaHistorySink);
        int afterNonDevaHistory = nonDevaHistorySink.editorCalls.size();
        nonDevaHistory.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                nonDevaHistorySink
        );
        assertEquals(
                "joiner after non-Devanagari history is a no-op",
                afterNonDevaHistory,
                nonDevaHistorySink.editorCalls.size()
        );

        assertPendingJoinerDroppedByText(
                "Devanagari mark",
                engine,
                nepali,
                "ि"
        );
        assertPendingJoinerDroppedByText("Latin letter", engine, nepali, "x");
        assertPendingJoinerDroppedByText("punctuation", engine, nepali, ",");
        assertPendingJoinerDroppedByText("space", engine, nepali, " ");
        for (String boundary : Arrays.asList(
                "commitRaw", "finish", "reset", "start", "switchProfile", "candidate"
        )) {
            assertPendingJoinerClearedByBoundary(
                    boundary,
                    engine,
                    english,
                    nepali
            );
        }

        RecordingTextSink pendingDeleteSink = new RecordingTextSink();
        ComposingSession pendingDelete = new ComposingSession(engine);
        pendingDelete.start(nepali, true, false, pendingDeleteSink);
        appendDevanagariVirama(pendingDelete, pendingDeleteSink);
        pendingDelete.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                pendingDeleteSink
        );
        pendingDelete.delete(pendingDeleteSink);
        pendingDelete.appendText("ष", pendingDeleteSink);
        assertEquals(
                "delete clears a pending joiner and still deletes",
                "कष",
                pendingDeleteSink.text()
        );

        RecordingTextSink resolvedDeleteSink = new RecordingTextSink();
        ComposingSession resolvedDelete = new ComposingSession(engine);
        resolvedDelete.start(nepali, true, false, resolvedDeleteSink);
        appendDevanagariVirama(resolvedDelete, resolvedDeleteSink);
        resolvedDelete.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                resolvedDeleteSink
        );
        resolvedDelete.appendText("ष", resolvedDeleteSink);
        resolvedDelete.delete(resolvedDeleteSink);
        assertEquals(
                "delete removes one resolved Devanagari grapheme",
                "",
                resolvedDeleteSink.text()
        );

        RecordingTextSink deleteSink = new RecordingTextSink();
        ComposingSession deletion = new ComposingSession(engine);
        deletion.start(nepali, true, false, deleteSink);
        deletion.appendText("क", deleteSink);
        deletion.appendText("ि", deleteSink);
        deletion.delete(deleteSink);
        assertEquals("delete Nepali grapheme", "", deleteSink.text());
        deletion.delete(deleteSink);
        assertEquals("delete remains safe at empty composing text", "", deleteSink.text());
        deleteSink.commitText("𑰀");
        deletion.delete(deleteSink);
        assertEquals("delete supplementary code point", "", deleteSink.text());

        int callsBeforePrivate = engine.callCount();
        RecordingTextSink privateSink = new RecordingTextSink();
        ComposingSession privateSession = new ComposingSession(engine);
        privateSession.start(english, true, true, privateSink);
        privateSession.appendText("s", privateSink);
        privateSession.appendText("e", privateSink);
        privateSession.appendText("c", privateSink);
        privateSession.appendText("'", privateSink);
        privateSession.appendText("’", privateSink);
        assertEquals("private field direct commits", "sec'’", privateSink.text());
        assertTrue("private field has no composition", !privateSession.hasComposingText());
        assertTrue("private field has no candidates", privateSession.candidates().isEmpty());
        assertEquals("private field avoids engine", callsBeforePrivate, engine.callCount());
        assertTrue(
                "private field rejects candidate",
                !privateSession.selectCandidate("secret", privateSink)
        );

        RecordingTextSink nonComposingSink = new RecordingTextSink();
        ComposingSession nonComposingSession = new ComposingSession(engine);
        nonComposingSession.start(english, false, false, nonComposingSink);
        nonComposingSession.appendText("d", nonComposingSink);
        nonComposingSession.appendText("'", nonComposingSink);
        nonComposingSession.appendText("o", nonComposingSink);
        nonComposingSession.appendText("’", nonComposingSink);
        assertEquals("non-composing field direct commits", "d'o’", nonComposingSink.text());
        assertTrue(
                "non-composing field has no composition",
                !nonComposingSession.hasComposingText()
        );

        RecordingTextSink switchSink = new RecordingTextSink();
        ComposingSession switching = new ComposingSession(engine);
        switching.start(english, true, false, switchSink);
        switching.appendText("h", switchSink);
        switching.appendText("e", switchSink);
        switching.switchProfile(nepali, true, false, switchSink);
        assertEquals("profile switch commits old word", "he", switchSink.text());
        assertTrue("profile switch clears old composition", !switching.hasComposingText());
        assertEquals("profile switched", nepali.id(), switching.profile().id());
        switching.appendText("न", switchSink);
        switching.appendText("े", switchSink);
        assertEquals("new profile starts fresh composition", "heने", switchSink.text());
        assertEquals("Nepali candidate", "नेपाल", switching.candidates().get(0));

        SuggestionActivation romanActivation = engine.activate(roman);
        SuggestionSnapshot romanSuggestions = engine.suggest(
                romanActivation,
                new SuggestionQuery(roman, "nepal", false)
        );
        assertEquals("Roman fixture maps alias", "नेपाल", romanSuggestions.candidates().get(0));
        assertTrue("Roman profile remains unavailable", !roman.isAvailable());

        boolean[] androidReplacement = new boolean[1];
        boolean[] androidJoiner = new boolean[1];
        runOnMainSync(() -> {
            EditText editor = new EditText(context);
            InputConnection connection = editor.onCreateInputConnection(new EditorInfo());
            assertTrue("EditText InputConnection", connection != null);
            ComposingSession platformSession = new ComposingSession(engine);
            InputConnectionTextSink platformSink = new InputConnectionTextSink(connection, true);
            platformSession.start(english, true, false, platformSink);
            platformSession.appendText("h", platformSink);
            platformSession.appendText("e", platformSink);
            platformSession.appendText("l", platformSink);
            assertEquals("Android composing editor text", "hel", editor.getText().toString());
            assertTrue("Android candidate selected", platformSession.selectCandidate("hello", platformSink));
            assertEquals("Android candidate replacement", "hello", editor.getText().toString());
            androidReplacement[0] = true;

            EditText devaEditor = new EditText(context);
            InputConnection devaConnection = devaEditor.onCreateInputConnection(new EditorInfo());
            assertTrue("Devanagari EditText InputConnection", devaConnection != null);
            ComposingSession devaPlatformSession = new ComposingSession(engine);
            InputConnectionTextSink devaPlatformSink = new InputConnectionTextSink(
                    devaConnection,
                    true
            );
            devaPlatformSession.start(nepali, true, false, devaPlatformSink);
            appendDevanagariVirama(devaPlatformSession, devaPlatformSink);
            devaPlatformSession.appendText(
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    devaPlatformSink
            );
            devaPlatformSession.appendText("ष", devaPlatformSink);
            assertEquals(
                    "Android exact Devanagari joiner code points",
                    "क्\u200dष",
                    devaEditor.getText().toString()
            );
            androidJoiner[0] = true;
        });

        return new ComposingEvidence(
                true,
                androidReplacement[0],
                true,
                true,
                androidJoiner[0],
                engine.callCount()
        );
    }

    private static void appendDevanagariVirama(
            ComposingSession session,
            TextSink sink
    ) {
        session.appendText("क", sink);
        session.appendText("्", sink);
    }

    private static void assertNoEditorCallEndsInJoiner(
            String label,
            RecordingTextSink sink
    ) {
        for (String call : sink.editorCalls) {
            assertTrue(
                    label + " never exposes an isolated joiner",
                    !call.endsWith("\u200c") && !call.endsWith("\u200d")
            );
        }
    }

    private static void assertPendingJoinerDroppedByText(
            String label,
            FixtureSuggestionEngine engine,
            KeyboardProfile nepali,
            String continuation
    ) {
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(nepali, true, false, sink);
        appendDevanagariVirama(session, sink);
        session.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                sink
        );
        session.appendText(continuation, sink);
        assertTrue(
                label + " drops pending joiner",
                sink.text().indexOf('\u200c') < 0 && sink.text().indexOf('\u200d') < 0
        );
        assertNoEditorCallEndsInJoiner(label, sink);
    }

    private static void assertPendingJoinerClearedByBoundary(
            String boundary,
            FixtureSuggestionEngine engine,
            KeyboardProfile english,
            KeyboardProfile nepali
    ) {
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(nepali, true, false, sink);
        appendDevanagariVirama(session, sink);
        session.appendText(
                "\u200d",
                KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                sink
        );
        switch (boundary) {
            case "commitRaw":
                session.commitRaw(sink);
                break;
            case "finish":
                session.finish(sink);
                break;
            case "reset":
                session.reset(nepali, true, false);
                break;
            case "start":
                session.start(nepali, true, false, sink);
                break;
            case "switchProfile":
                session.switchProfile(english, true, false, sink);
                break;
            case "candidate":
                assertTrue(
                        "candidate boundary accepted",
                        session.selectCandidate("क्", sink)
                );
                break;
            default:
                throw new IllegalArgumentException("unknown boundary fixture: " + boundary);
        }
        session.appendText("ष", sink);
        assertTrue(
                boundary + " clears pending joiner",
                sink.text().indexOf('\u200c') < 0 && sink.text().indexOf('\u200d') < 0
        );
        assertNoEditorCallEndsInJoiner(boundary, sink);
    }

    private static final class ComposingEvidence {
        final boolean candidateReplacement;
        final boolean androidReplacement;
        final boolean orthographicWord;
        final boolean devaJoiner;
        final boolean androidJoiner;
        final int suggestionCalls;

        ComposingEvidence(
                boolean candidateReplacement,
                boolean androidReplacement,
                boolean orthographicWord,
                boolean devaJoiner,
                boolean androidJoiner,
                int suggestionCalls
        ) {
            this.candidateReplacement = candidateReplacement;
            this.androidReplacement = androidReplacement;
            this.orthographicWord = orthographicWord;
            this.devaJoiner = devaJoiner;
            this.androidJoiner = androidJoiner;
            this.suggestionCalls = suggestionCalls;
        }
    }

    private static final class PackEvidence {
        final String mode;
        final int count;
        final boolean engineSwitching;
        final int noticeSources;

        PackEvidence(String mode, int count, boolean engineSwitching, int noticeSources) {
            this.mode = mode;
            this.count = count;
            this.engineSwitching = engineSwitching;
            this.noticeSources = noticeSources;
        }
    }

    private static final class PackVector {
        final String profileId;
        final String packId;
        final String artifactSha256;
        final String artifactLicense;
        final int candidateCount;
        final String lookupKind;
        final String query;
        final String expectedSurface;

        PackVector(
                String profileId,
                String packId,
                String artifactSha256,
                String artifactLicense,
                int candidateCount,
                String lookupKind,
                String query,
                String expectedSurface
        ) {
            this.profileId = profileId;
            this.packId = packId;
            this.artifactSha256 = artifactSha256;
            this.artifactLicense = artifactLicense;
            this.candidateCount = candidateCount;
            this.lookupKind = lookupKind;
            this.query = query;
            this.expectedSurface = expectedSurface;
        }
    }

    private static final class RecordingTextSink implements TextSink {
        final List<String> composingCalls = new ArrayList<>();
        final List<String> editorCalls = new ArrayList<>();
        private String committed = "";
        private String composing = "";

        @Override
        public boolean setComposingText(String text) {
            composing = text;
            composingCalls.add(text);
            editorCalls.add("set:" + text);
            return true;
        }

        @Override
        public boolean commitText(String text) {
            committed += text;
            composing = "";
            editorCalls.add("commit:" + text);
            return true;
        }

        @Override
        public boolean finishComposingText() {
            committed += composing;
            composing = "";
            editorCalls.add("finish");
            return true;
        }

        @Override
        public boolean deletePreviousGrapheme() {
            editorCalls.add("delete");
            if (committed.isEmpty()) {
                return true;
            }
            int boundary = GraphemeBackspace.previousBoundary(committed);
            committed = committed.substring(0, Math.max(0, boundary));
            return true;
        }

        @Override
        public boolean deleteOneCodePoint() {
            editorCalls.add("delete-code-point");
            if (committed.isEmpty()) {
                return true;
            }
            int end = committed.offsetByCodePoints(committed.length(), -1);
            committed = committed.substring(0, end);
            return true;
        }

        String text() {
            return committed + composing;
        }
    }

    private static final class RecordingListener implements NepaInputView.Listener {
        String lastText;
        KeySpec lastKey;
        int retryCount;

        @Override
        public void onKey(KeySpec key, SpatialKeyStroke stroke) {
            lastKey = key;
            if (key.action() == KeySpec.Action.TEXT) {
                lastText = key.text();
            }
        }

        @Override
        public void onProfileSelected(String profileId) {
        }

        @Override
        public void onCandidateSelected(
                SuggestionQuery owner,
                SuggestionCandidate candidate
        ) {
        }

        @Override
        public void onSuggestionRetry() {
            retryCount++;
        }

        @Override
        public void onManageLanguages() {
        }

        @Override
        public void onOtherKeyboards() {
        }
    }
}
