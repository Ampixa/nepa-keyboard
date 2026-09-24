package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Application;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Bundle;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.InputMethodInfo;
import android.view.inputmethod.InputMethodManager;
import android.view.inputmethod.InputMethodSubtype;

import com.ampixa.nepakeyboard.pack.NkpBundle;
import com.ampixa.nepakeyboard.conversion.NcmBundle;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Internal-only API 34 smoke checks for the generated internal product catalog. */
public final class InternalImeSmokeInstrumentation extends Instrumentation {
    private static final String EXPECTED_PACKAGE = "com.ampixa.nepakeyboard.ime.internal";
    private static final String DHIMAL_DIRECT_ID = "dhi-Deva-NP";
    private static final String DHIMAL_LAYOUT_ID = "deva-nepal-dhimal-v1";
    private static final String SUNUWAR_DIRECT_ID = "suz-Deva-NP";
    private static final String SUNUWAR_LAYOUT_ID = "deva-nepal-extended-v1";
    private static final String WESTERN_TAMANG_DIRECT_ID = "tdg-Deva-NP";
    private static final String WESTERN_TAMANG_LAYOUT_ID = "deva-nepal-western-tamang-v1";
    private static final String LOHORUNG_DIRECT_ID = "lbr-Deva-NP";
    private static final String LOHORUNG_LAYOUT_ID = "deva-nepal-lohorung-v1";
    private static final String YAKKHA_DIRECT_ID = "ybh-Deva-NP";
    private static final String YAKKHA_LAYOUT_ID = "deva-nepal-yakkha-v1";
    private static final String KHALING_DIRECT_ID = "klr-Deva-NP";
    private static final String KHALING_LAYOUT_ID = "deva-nepal-khaling-v1";
    private static final String DUMI_DIRECT_ID = "dus-Deva-NP";
    private static final String DUMI_LAYOUT_ID = "deva-nepal-dumi-v1";
    private static final String BANTAWA_DIRECT_ID = "bap-Deva-NP";
    private static final String BANTAWA_LAYOUT_ID = "deva-nepal-bantawa-v1";
    private static final String WESTERN_MAGAR_DIRECT_ID = "mrd-Deva-NP";
    private static final String WESTERN_MAGAR_LAYOUT_ID = "deva-nepal-western-magar-v1";
    private static final String MID_EASTERN_THARU_DIRECT_ID = "thq-Deva-NP";
    private static final String MID_EASTERN_THARU_LAYOUT_ID = "deva-nepal-mid-eastern-tharu-v1";
    private static final String NEPAL_BHASA_DEVA_DIRECT_ID = "new-Deva-NP";
    private static final String NEPAL_BHASA_ROMAN_ID = "new-Latn-Deva-NP";
    private static final String LATIN_QWERTY_LAYOUT_ID = "latn-qwerty-us-v1";
    private static final String NEWA_DIRECT_ID = "new-Newa-NP";
    private static final String NEPAL_BHASA_CONVERSION_ID = "new-Deva-Newa-NP";
    private static final String NEWA_LAYOUT_ID = "newa-nepal-prachalit-v1";
    private static final String PACK_VECTOR_ASSET = "nepa-packs/benchmark-vectors.json";
    private static final String ZERO_SHA256 =
            "00000000000000000000000000000000"
                    + "00000000000000000000000000000000";
    private static final String RUNTIME_CONFORMANCE_ASSET =
            "nepa-conformance/runtime-v2.json";
    private static final int MAX_PACK_VECTOR_BYTES = 256 * 1024;
    private static final int MAX_RUNTIME_CONFORMANCE_BYTES = 256 * 1024;
    private static final int MAX_RUNTIME_CONFORMANCE_PROFILES = 128;
    private static final long TCG_PACK_READY_TIMEOUT_MS = 120_000L;
    private static final long PICKER_LAYOUT_TIMEOUT_MS = 5_000L;

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        int resultCode = Activity.RESULT_CANCELED;
        LanguagePreferences preferences = null;
        SuggestionEngine engine = null;
        try {
            Context context = getTargetContext();
            assertEquals("internal application ID", EXPECTED_PACKAGE, context.getPackageName());
            // The generated catalog's selectable count describes lock-selectable
            // profiles. Transliteration-only profiles are selectable through the
            // reviewed map supplement instead, so they are counted separately rather
            // than allowed to loosen this assertion.
            int availableProfileCount = LanguageRegistry.subtypeBacked().size();
            assertEquals(
                    "available profile count matches generated catalog",
                    GeneratedProfileCatalog.SELECTABLE_COUNT,
                    availableProfileCount
            );
            assertEquals(
                    "supplement adds exactly the reviewed transliteration profiles",
                    GeneratedProfileCatalog.SELECTABLE_COUNT
                            + GeneratedTransliterationProfiles.PROFILE_COUNT,
                    LanguageRegistry.available().size()
            );
            RuntimeConformance conformance = readRuntimeConformance(context);
            assertEquals(
                    "runtime conformance selectable count",
                    availableProfileCount,
                    conformance.profiles.size()
            );
            assertEquals(
                    "runtime conformance exact profile set",
                    availableProfileIds(),
                    conformance.profileIds()
            );
            int keyboardRenderCount = verifyRuntimeProfilesAndLayouts(context, conformance);
            assertEquals(
                    "every selectable profile has keyboard render evidence",
                    LanguageRegistry.available().size(),
                    keyboardRenderCount
            );
            verifyGeneratedSubtypeRegistry(context);
            verifyPreferencePlatformReconciliation(context);
            verifySetupStateModel();
            reportProgress("runtime_catalog_verified");

            KeyboardProfile english = available(LanguageRegistry.ENGLISH_ID);
            KeyboardProfile nepali = available(LanguageRegistry.NEPALI_DIRECT_ID);
            KeyboardProfile limbu = available(LanguageRegistry.LIMBU_DIRECT_ID);
            KeyboardProfile dhimal = available(DHIMAL_DIRECT_ID);
            KeyboardProfile sunuwar = available(SUNUWAR_DIRECT_ID);
            KeyboardProfile westernTamang = available(WESTERN_TAMANG_DIRECT_ID);
            KeyboardProfile lohorung = available(LOHORUNG_DIRECT_ID);
            KeyboardProfile yakkha = available(YAKKHA_DIRECT_ID);
            KeyboardProfile khaling = available(KHALING_DIRECT_ID);
            KeyboardProfile dumi = available(DUMI_DIRECT_ID);
            KeyboardProfile bantawa = available(BANTAWA_DIRECT_ID);
            KeyboardProfile westernMagar = available(WESTERN_MAGAR_DIRECT_ID);
            KeyboardProfile midEasternTharu = available(MID_EASTERN_THARU_DIRECT_ID);
            KeyboardProfile nepalBhasaDeva = available(NEPAL_BHASA_DEVA_DIRECT_ID);
            KeyboardProfile nepalBhasaRoman = available(NEPAL_BHASA_ROMAN_ID);
            KeyboardProfile newa = available(NEWA_DIRECT_ID);
            KeyboardProfile nepalBhasaConversion = available(NEPAL_BHASA_CONVERSION_ID);
            BackspaceContractVectors.verify(this, context, english, nepali);
            verifySuggestionReadinessContract(context, english);
            verifyCandidateAccessibilityContract(context, english);
            assertEquals("Limbu input script", "Limb", limbu.sourceScript());
            assertEquals("Limbu output script", "Limb", limbu.outputScript());
            assertEquals("Limbu layout", "limb-nepal-phonetic-v1", limbu.layoutId());
            verifyLimbuLayout(limbu);
            verifyLimbuKeyDispatch(context, limbu);
            verifyDhimalProfileAndLayout(nepali, dhimal);
            verifyDhimalKeyDispatch(context, dhimal);
            verifyDhimalGeneratedInputPolicies(dhimal);
            verifySunuwarProfileAndLayout(nepali, sunuwar);
            verifySunuwarKeyDispatch(context, sunuwar);
            verifySunuwarGeneratedInputPolicies(sunuwar);
            verifyWesternTamangProfileAndLayout(nepali, westernTamang);
            verifyWesternTamangKeyDispatch(context, westernTamang);
            verifyWesternTamangGeneratedInputPolicies(westernTamang);
            verifyLohorungProfileAndLayout(nepali, lohorung);
            verifyLohorungKeyDispatch(context, lohorung);
            verifyLohorungGeneratedInputPolicies(lohorung, nepali);
            verifyYakkhaProfileAndLayout(nepali, yakkha);
            verifyYakkhaKeyDispatch(context, yakkha);
            verifyYakkhaGeneratedInputPolicies(yakkha);
            verifyKhalingProfileAndLayout(nepali, khaling);
            verifyKhalingKeyDispatch(context, khaling);
            verifyKhalingGeneratedInputPolicies(khaling);
            verifyDumiProfileAndLayout(nepali, dumi);
            verifyDumiKeyDispatch(context, dumi);
            verifyDumiGeneratedInputPolicies(dumi);
            verifyNewDirectProfileAndLayout(bantawa, BANTAWA_DIRECT_ID,
                    "bap-deva-direct", BANTAWA_LAYOUT_ID, 4);
            verifyNewDirectProfileAndLayout(westernMagar, WESTERN_MAGAR_DIRECT_ID,
                    "mrd-deva-direct", WESTERN_MAGAR_LAYOUT_ID, 5);
            verifyNewDirectProfileAndLayout(midEasternTharu, MID_EASTERN_THARU_DIRECT_ID,
                    "thq-deva-direct", MID_EASTERN_THARU_LAYOUT_ID, 5);
            verifyBantawaLayoutAndDispatch(context, nepali, bantawa);
            verifyWesternMagarLayoutAndDispatch(context, nepali, westernMagar);
            verifyMidEasternTharuLayoutAndDispatch(context, nepali, midEasternTharu);
            verifyRomanizedNewaProfileAndLayout(nepalBhasaDeva, nepalBhasaRoman);
            verifyNewaProfileAndLayout(newa);
            verifyNewaKeyDispatch(context, newa);
            verifyNepalBhasaConversionProfile(nepalBhasaConversion);
            reportProgress("language_layouts_verified");

            preferences = new LanguagePreferences(context);
            preferences.clearForTesting();
            assertEquals(
                    "generated default profile count",
                    defaultEnabledProfileCount(),
                    preferences.enabledProfiles().size()
            );
            for (KeyboardProfile profile : LanguageRegistry.available()) {
                assertTrue(
                        "enable generated profile " + profile.id(),
                        preferences.setEnabled(profile.id(), true)
                );
            }
            assertEquals(
                    "all generated profiles enabled",
                    LanguageRegistry.available().size(),
                    preferences.enabledProfiles().size()
            );
            verifyLanguageManager(context);
            PickerRecyclingEvidence pickerRecyclingEvidence = verifyPicker(
                    context,
                    conformance,
                    preferences,
                    // The picker lists every enabled selectable profile, which
                    // includes the transliteration supplement.
                    LanguageRegistry.available().size(),
                    english,
                    nepali
            );
            reportProgress("picker_verified");

            List<ReleasePackSpec> specs = ReleasePackRegistry.installed(context);
            List<ConversionMapSpec> conversionSpecs = ConversionMapRegistry.installed(context);
            assertEquals(
                    "staged internal pack bindings",
                    availablePackProfileIds().size(),
                    specs.size()
            );
            assertEquals(
                    "staged internal conversion bindings",
                    availableConversionProfileIds().size(),
                    conversionSpecs.size()
            );
            List<PackVector> vectors = readPackVectors(context);
            assertEquals("internal pack vectors", specs.size(), vectors.size());
            assertEquals(
                    "pack-vector/runtime-conformance profile set",
                    availablePackProfileIds(),
                    packVectorProfileIds(vectors)
            );
            Map<String, ReleasePackSpec> specsByProfile = new HashMap<>();
            for (ReleasePackSpec spec : specs) {
                assertTrue("unique staged profile", specsByProfile.put(spec.profileId(), spec) == null);
            }
            assertEquals(
                    "staged profile set",
                    availablePackProfileIds(),
                    specsByProfile.keySet()
            );
            verifyStagedNepalBhasaConversion(
                    nepalBhasaConversion,
                    conversionSpecs
            );

            int provenanceSourceCount = 0;
            Set<String> provenanceArtifacts = new HashSet<>();
            for (PackVector vector : vectors) {
                ReleasePackSpec spec = specsByProfile.get(vector.profileId);
                assertTrue("vector has staged pack", spec != null);
                assertEquals(vector.profileId + " staged pack ID", vector.packId, spec.packId());
                assertEquals(
                        vector.profileId + " staged artifact SHA-256",
                        vector.artifactSha256,
                        spec.artifactSha256()
                );
                File cached = spec.file();
                assertTrue(
                        vector.profileId + " remove verified cache before extraction",
                        !cached.exists() || cached.delete()
                );
                File materialized = spec.materialize();
                try (NkpBundle bundle = NkpBundle.open(
                        materialized,
                        vector.artifactSha256,
                        true
                )) {
                    assertEquals(vector.profileId + " pack ID", vector.packId, bundle.packId());
                    assertEquals(vector.profileId + " release mode", vector.releaseMode, bundle.releaseMode());
                    assertEquals(
                            vector.profileId + " candidate count",
                            vector.candidateCount,
                            bundle.candidateCount()
                    );
                    List<NkpBundle.Suggestion> suggestions = suggest(bundle, vector);
                    assertTrue(vector.profileId + " lookup result", !suggestions.isEmpty());
                    assertEquals(
                            vector.profileId + " lookup surface",
                            vector.expectedSurface,
                            suggestions.get(0).surface()
                    );
                }
                NkpBundle.NoticeDocument notices = NoticeReaderFactory.read(
                        materialized,
                        vector.artifactSha256
                );
                assertEquals(vector.profileId + " notice pack ID", vector.packId, notices.packId());
                assertTrue(
                        vector.profileId + " artifact provenance",
                        !notices.artifactLicense().isEmpty()
                );
                assertTrue(vector.profileId + " source provenance", !notices.sources().isEmpty());
                boolean firstArtifactNotice = provenanceArtifacts.add(
                        vector.packId + ":" + vector.artifactSha256
                );
                for (NkpBundle.NoticeSource source : notices.sources()) {
                    assertTrue(vector.profileId + " source ID", !source.sourceId().isEmpty());
                    assertTrue(vector.profileId + " source title", !source.title().isEmpty());
                    assertTrue(vector.profileId + " source license", !source.license().isEmpty());
                    if (firstArtifactNotice) {
                        provenanceSourceCount++;
                    }
                }
                reportProgress("direct_pack_verified:" + vector.profileId);
            }

            Intent noticesIntent = new Intent(context, NoticesActivity.class);
            noticesIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            NoticesActivity noticesActivity = (NoticesActivity) startActivitySync(noticesIntent);
            long noticeDeadline = SystemClock.elapsedRealtime() + TCG_PACK_READY_TIMEOUT_MS;
            while ((!noticesActivity.noticesReadyForTesting()
                    || !noticesActivity.systemBarInsetsAppliedForTesting())
                    && SystemClock.elapsedRealtime() < noticeDeadline) {
                SystemClock.sleep(25L);
            }
            assertTrue("internal provenance UI loads", noticesActivity.noticesReadyForTesting());
            assertTrue(
                    "internal provenance UI avoids system bars",
                    noticesActivity.systemBarInsetsAppliedForTesting()
            );
            assertEquals(
                    "internal provenance UI source count",
                    provenanceSourceCount,
                    noticesActivity.visibleNoticeSourcesForTesting()
            );
            int layoutNoticeCount = noticesActivity.visibleLayoutNoticesForTesting();
            assertEquals(
                    "internal layout provenance count",
                    GeneratedLayoutRegistry.LAYOUT_NOTICE_COUNT,
                    layoutNoticeCount
            );
            runOnMainSync(() -> {
                assertTrue(
                        "internal provenance UI uses a virtualized list",
                        noticesActivity.noticeListIsVirtualizedForTesting()
                );
                noticesActivity.finish();
            });
            reportProgress("notices_verified");
            PackVector sunuwarVector = findVector(vectors, SUNUWAR_DIRECT_ID);
            assertEquals("Sunuwar leading orthographic validation query", "‘आ", sunuwarVector.query);
            PackVector dhimalVector = findVector(vectors, DHIMAL_DIRECT_ID);
            assertEquals("Dhimal reviewed validation query", "इअ्‌थ", dhimalVector.query);
            PackVector westernTamangVector = findVector(vectors, WESTERN_TAMANG_DIRECT_ID);
            assertEquals(
                    "Western Tamang reviewed validation query",
                    "वा़",
                    westernTamangVector.query
            );
            PackVector lohorungVector = findVector(vectors, LOHORUNG_DIRECT_ID);
            assertEquals("Lohorung reviewed validation query", "अ", lohorungVector.query);
            assertEquals("Lohorung reviewed validation surface", "अःग्‍मा", lohorungVector.expectedSurface);
            PackVector yakkhaVector = findVector(vectors, YAKKHA_DIRECT_ID);
            assertEquals("Yakkha reviewed validation query", "अ", yakkhaVector.query);
            assertEquals("Yakkha reviewed validation surface", "अनन्त", yakkhaVector.expectedSurface);
            PackVector khalingVector = findVector(vectors, KHALING_DIRECT_ID);
            assertEquals("Khaling reviewed validation query", "क", khalingVector.query);
            assertEquals(
                    "Khaling reviewed validation surface",
                    "कइना़",
                    khalingVector.expectedSurface
            );
            PackVector dumiVector = findVector(vectors, DUMI_DIRECT_ID);
            assertEquals("Dumi reviewed validation query", "क", dumiVector.query);
            assertEquals(
                    "Dumi reviewed validation surface",
                    "क:फु",
                    dumiVector.expectedSurface
            );
            PackVector bantawaVector = findVector(vectors, BANTAWA_DIRECT_ID);
            assertEquals("Bantawa reviewed validation query", "अ", bantawaVector.query);
            assertEquals("Bantawa reviewed validation surface", "अ", bantawaVector.expectedSurface);
            PackVector westernMagarVector = findVector(vectors, WESTERN_MAGAR_DIRECT_ID);
            assertEquals("Western Magar reviewed pack query", "-ऐ", westernMagarVector.query);
            assertEquals("Western Magar reviewed pack surface", "-ऐ",
                    westernMagarVector.expectedSurface);
            PackVector midEasternTharuVector = findVector(vectors, MID_EASTERN_THARU_DIRECT_ID);
            assertEquals("Mid-Eastern Tharu reviewed validation query", "अइठ",
                    midEasternTharuVector.query);
            assertEquals("Mid-Eastern Tharu reviewed validation surface", "अइठल",
                    midEasternTharuVector.expectedSurface);
            PackVector nepalBhasaRomanVector = findVector(vectors, NEPAL_BHASA_ROMAN_ID);
            assertEquals(
                    "Romanized Newa measured validation query",
                    "madu",
                    nepalBhasaRomanVector.query
            );
            assertEquals(
                    "Romanized Newa measured validation surface",
                    "मदु",
                    nepalBhasaRomanVector.expectedSurface
            );
            PackVector newaVector = findVector(vectors, NEWA_DIRECT_ID);
            assertEquals("Newa attested validation query", "𑐣𑐾", newaVector.query);
            assertEquals(
                    "Newa attested validation surface",
                    "𑐣𑐾𑐥𑐵𑐮𑐮𑐶𑐥𑐶",
                    newaVector.expectedSurface
            );

            InstalledSuggestionArtifacts installedArtifacts =
                    SuggestionArtifactRegistry.installed(context);
            assertEquals("atomic installed packs", specs.size(), installedArtifacts.packs().size());
            assertEquals(
                    "atomic installed conversions",
                    conversionSpecs.size(),
                    installedArtifacts.conversions().size()
            );
            engine = SuggestionEngineFactory.create(installedArtifacts, activation -> {
            });
            for (PackVector vector : vectors) {
                KeyboardProfile profile = available(vector.profileId);
                SuggestionActivation activation = engine.activate(profile);
                List<String> engineSuggestions = awaitSuggestions(
                        engine,
                        activation,
                        profile,
                        vector.query
                );
                if (vector.expectedSurface.equals(vector.query)) {
                    assertEquals(
                            vector.profileId + " exact validation literal is preserved at tail",
                            vector.expectedSurface,
                            engineSuggestions.get(engineSuggestions.size() - 1)
                    );
                } else {
                    assertEquals(
                            vector.profileId + " variant engine",
                            vector.expectedSurface,
                            engineSuggestions.get(0)
                    );
                }
                assertEquals(
                        vector.profileId + " verified no-match state",
                        SuggestionSnapshot.Status.NO_MATCH,
                        engine.suggest(
                                activation,
                                new SuggestionQuery(profile, "\u0378", false)
                        ).status()
                );
                reportProgress("engine_vector_verified:" + vector.profileId);
            }
            verifyDhimalPackInput(dhimal, dhimalVector, engine);
            verifySunuwarPackInput(sunuwar, sunuwarVector, engine);
            verifyWesternTamangPackInput(westernTamang, westernTamangVector, engine);
            verifyLohorungPackInput(lohorung, lohorungVector, engine);
            verifyYakkhaPackInput(yakkha, yakkhaVector, engine);
            verifyKhalingPackInput(khaling, khalingVector, engine);
            verifyDumiPackInput(dumi, dumiVector, engine);
            verifyBantawaPackInput(bantawa, bantawaVector, engine);
            verifyWesternMagarPackInput(westernMagar, engine);
            verifyMidEasternTharuPackInput(midEasternTharu, midEasternTharuVector, engine);
            verifyRomanizedNewaPackInput(
                    nepalBhasaRoman,
                    nepalBhasaRomanVector,
                    engine
            );
            verifyNewaPackInput(newa, newaVector, engine);
            verifyNepalBhasaConversionInput(nepalBhasaConversion, engine);
            reportProgress("language_inputs_verified");

            result.putString("status", "ok");
            result.putInt("available_profiles", LanguageRegistry.available().size());
            result.putInt("staged_packs", specs.size());
            result.putInt("staged_conversions", conversionSpecs.size());
            result.putBoolean("runtime_conformance_asset_verified", true);
            result.putBoolean("runtime_conformance_profile_set_verified", true);
            result.putBoolean("runtime_conformance_profile_fields_verified", true);
            result.putBoolean("runtime_conformance_layer_fingerprints_verified", true);
            result.putBoolean("runtime_conformance_stable_key_dispatch_verified", true);
            result.putBoolean("pixel_width_keyboard_geometry_matrix_verified", true);
            result.putBoolean("language_delete_separate_rows_verified", true);
            result.putBoolean("compact_language_control_verified", true);
            result.putInt("keyboard_render_count", keyboardRenderCount);
            result.putBoolean("all_selectable_keyboard_renders_verified", true);
            result.putString("english_keyboard_render", "ime-internal-eng-Latn-US.png");
            result.putString("newa_keyboard_render", "ime-internal-new-Newa-NP.png");
            result.putBoolean("runtime_conformance_picker_verified", true);
            result.putBoolean("runtime_conformance_pack_vector_profile_set_verified", true);
            result.putBoolean("nepal_bhasa_conversion_profile_verified", true);
            result.putBoolean("nepal_bhasa_conversion_artifact_verified", true);
            result.putBoolean("nepal_bhasa_conversion_engine_verified", true);
            result.putBoolean("limbu_layout_registry_verified", true);
            result.putBoolean("limbu_key_dispatch_verified", true);
            result.putBoolean("dhimal_profile_binding_verified", true);
            result.putBoolean("dhimal_layout_registry_verified", true);
            result.putBoolean("dhimal_generated_key_policies_verified", true);
            result.putBoolean("dhimal_atomic_zwnj_verified", true);
            result.putBoolean("dhimal_key_dispatch_verified", true);
            result.putBoolean("dhimal_picker_row_selection_verified", true);
            result.putBoolean("dhimal_pack_input_verified", true);
            result.putBoolean("sunuwar_profile_binding_verified", true);
            result.putBoolean("sunuwar_layout_registry_verified", true);
            result.putBoolean("sunuwar_generated_key_policies_verified", true);
            result.putBoolean("sunuwar_leading_orthographic_word_verified", true);
            result.putBoolean("sunuwar_atomic_zwj_verified", true);
            result.putBoolean("sunuwar_key_dispatch_verified", true);
            result.putBoolean("sunuwar_picker_row_selection_verified", true);
            result.putBoolean("sunuwar_pack_input_verified", true);
            result.putBoolean("tdg_profile_binding_verified", true);
            result.putBoolean("tdg_layout_registry_verified", true);
            result.putBoolean("tdg_generated_key_policies_verified", true);
            result.putBoolean("tdg_atomic_zwj_verified", true);
            result.putBoolean("tdg_atomic_zwnj_verified", true);
            result.putBoolean("tdg_stable_key_dispatch_verified", true);
            result.putBoolean("tdg_key_dispatch_verified", true);
            result.putBoolean("tdg_nepali_layout_isolation_verified", true);
            result.putBoolean("tdg_picker_row_selection_verified", true);
            result.putBoolean("tdg_pack_input_verified", true);
            result.putBoolean("lbr_profile_binding_verified", true);
            result.putBoolean("lbr_layout_registry_verified", true);
            result.putBoolean("lbr_generated_key_policies_verified", true);
            result.putBoolean("lbr_internal_zwj_verified", true);
            result.putBoolean("lbr_internal_zwnj_verified", true);
            result.putBoolean("lbr_terminal_zwnj_query_verified", true);
            result.putBoolean("lbr_terminal_zwnj_boundary_verified", true);
            result.putBoolean("lbr_terminal_zwnj_candidate_replacement_verified", true);
            result.putBoolean("lbr_terminal_zwnj_delete_verified", true);
            result.putBoolean("lbr_terminal_zwnj_invalid_continuation_verified", true);
            result.putBoolean("lbr_terminal_zwnj_private_field_verified", true);
            result.putBoolean("lbr_terminal_zwnj_profile_switch_verified", true);
            result.putBoolean("lbr_terminal_zwj_rejected_verified", true);
            result.putBoolean("lbr_key_dispatch_verified", true);
            result.putBoolean("lbr_nepali_layout_isolation_verified", true);
            result.putBoolean("lbr_picker_row_selection_verified", true);
            result.putBoolean("lbr_pack_input_verified", true);
            result.putBoolean("ybh_profile_binding_verified", true);
            result.putBoolean("ybh_layout_registry_verified", true);
            result.putBoolean("ybh_generated_key_policies_verified", true);
            result.putBoolean("ybh_intra_word_punctuation_verified", true);
            result.putBoolean("ybh_terminal_zwnj_query_verified", true);
            result.putBoolean("ybh_key_dispatch_verified", true);
            result.putBoolean("ybh_nepali_layout_isolation_verified", true);
            result.putBoolean("ybh_picker_row_selection_verified", true);
            result.putBoolean("ybh_pack_input_verified", true);
            result.putBoolean("klr_profile_binding_verified", true);
            result.putBoolean("klr_layout_registry_verified", true);
            result.putBoolean("klr_generated_key_policies_verified", true);
            result.putBoolean("klr_atomic_zwj_verified", true);
            result.putBoolean("klr_atomic_zwnj_verified", true);
            result.putBoolean("klr_intra_word_hyphen_verified", true);
            result.putBoolean("klr_key_dispatch_verified", true);
            result.putBoolean("klr_nepali_layout_isolation_verified", true);
            result.putBoolean("klr_picker_row_selection_verified", true);
            result.putBoolean("klr_pack_input_verified", true);
            result.putBoolean("dus_profile_binding_verified", true);
            result.putBoolean("dus_layout_registry_verified", true);
            result.putBoolean("dus_generated_key_policies_verified", true);
            result.putBoolean("dus_atomic_zwj_verified", true);
            result.putBoolean("dus_atomic_zwnj_verified", true);
            result.putBoolean("dus_intra_word_hyphen_verified", true);
            result.putBoolean("dus_intra_word_colon_verified", true);
            result.putBoolean("dus_key_dispatch_verified", true);
            result.putBoolean("dus_nepali_layout_isolation_verified", true);
            result.putBoolean("dus_picker_row_selection_verified", true);
            result.putBoolean("dus_pack_input_verified", true);
            result.putBoolean("bap_profile_layout_dispatch_verified", true);
            result.putBoolean("bap_pack_input_verified", true);
            result.putBoolean("mrd_profile_layout_dispatch_verified", true);
            result.putBoolean("mrd_typable_pack_input_verified", true);
            result.putBoolean("thq_profile_layout_dispatch_verified", true);
            result.putBoolean("thq_pack_input_verified", true);
            result.putBoolean("nepal_bhasa_roman_profile_binding_verified", true);
            result.putBoolean("nepal_bhasa_roman_pack_input_verified", true);
            result.putBoolean("newa_profile_binding_verified", true);
            result.putBoolean("newa_layout_registry_verified", true);
            result.putBoolean("newa_extended_letters_verified", true);
            result.putBoolean("newa_key_dispatch_verified", true);
            result.putBoolean("newa_picker_row_selection_verified", true);
            result.putBoolean("newa_pack_input_verified", true);
            result.putBoolean("internal_catalog_reader_verified", true);
            result.putBoolean("internal_catalog_notices_verified", true);
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
            result.putBoolean("picker_attached_max_enabled_recycling_verified", true);
            result.putInt(
                    "picker_attached_max_enabled_profiles",
                    pickerRecyclingEvidence.enabledProfileCount
            );
            result.putInt(
                    "picker_attached_window_rows",
                    pickerRecyclingEvidence.attachedWindowRowCount
            );
            result.putInt(
                    "picker_attached_rebound_rows",
                    pickerRecyclingEvidence.reboundRowCount
            );
            result.putBoolean("language_manager_recycling_saved_state_verified", true);
            result.putBoolean("language_manager_sections_verified", true);
            result.putBoolean("language_picker_enabled_only_verified", true);
            result.putBoolean("last_enabled_switch_rejection_verified", true);
            result.putBoolean("observable_setup_state_model_verified", true);
            result.putBoolean("activity_system_bar_insets_verified", true);
            result.putInt("internal_catalog_notice_sources", provenanceSourceCount);
            result.putInt(
                    "layout_notice_count",
                    layoutNoticeCount
            );
            result.putString("profile_lock_sha256", GeneratedProfileCatalog.LOCK_SHA256);
            result.putString("layout_lock_sha256", GeneratedLayoutRegistry.LAYOUT_LOCK_SHA256);
            result.putString(
                    "runtime_conformance_sha256",
                    GeneratedLayoutRegistry.RUNTIME_CONFORMANCE_SHA256
            );
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            result.putString("status", "error");
            result.putString("error", failure.toString());
        } finally {
            if (engine != null) {
                engine.close();
            }
            if (preferences != null) {
                preferences.clearForTesting();
            }
        }
        finish(resultCode, result);
    }

    private static void verifySuggestionReadinessContract(
            Context context,
            KeyboardProfile english
    ) throws Exception {
        NkpSuggestionEngine missing = new NkpSuggestionEngine(Collections.emptyList());
        try {
            SuggestionActivation activation = missing.activate(english);
            SuggestionSnapshot missingSnapshot = missing.suggest(
                    activation,
                    new SuggestionQuery(english, "h", false)
            );
            assertEquals(
                    "internal missing pack state",
                    SuggestionSnapshot.Status.MISSING,
                    missingSnapshot.status()
            );
            assertTrue("internal missing pack is not retryable", !missing.retry(activation));

            RecordingTextSink sink = new RecordingTextSink();
            ComposingSession session = new ComposingSession(missing);
            session.start(english, true, false, sink);
            session.appendText("h", sink);
            session.appendText(" ", sink);
            assertEquals("internal missing pack preserves literal text", "h ", sink.text());
        } finally {
            missing.close();
        }

        File fakePack = File.createTempFile("readiness-", ".nkp", context.getCacheDir());
        try (FileOutputStream output = new FileOutputStream(fakePack, false)) {
            output.write(1);
        }
        ReleasePackSpec spec = new ReleasePackSpec(
                english.id(),
                english.packBinding(),
                fakePack,
                ZERO_SHA256
        );
        SuggestionQuery query = new SuggestionQuery(english, "h", false);
        NkpSuggestionEngine corrupt = new NkpSuggestionEngine(
                Collections.singletonList(spec),
                activation -> {
                },
                (file, expectedSha256) -> {
                    throw new SecurityException("controlled integrity failure");
                }
        );
        try {
            SuggestionActivation activation = corrupt.activate(english);
            awaitReadinessStatus(
                    corrupt,
                    activation,
                    query,
                    SuggestionSnapshot.Status.CORRUPT
            );
            assertTrue("internal corrupt state is not retryable", !corrupt.retry(activation));
        } finally {
            corrupt.close();
        }

        NkpSuggestionEngine unavailable = new NkpSuggestionEngine(
                Collections.singletonList(spec),
                activation -> {
                },
                (file, expectedSha256) -> {
                    throw new IOException("controlled transient failure");
                }
        );
        try {
            SuggestionActivation activation = unavailable.activate(english);
            awaitReadinessStatus(
                    unavailable,
                    activation,
                    query,
                    SuggestionSnapshot.Status.UNAVAILABLE
            );
            assertTrue("internal unavailable state retries", unavailable.retry(activation));
            awaitReadinessStatus(
                    unavailable,
                    activation,
                    query,
                    SuggestionSnapshot.Status.UNAVAILABLE
            );
        } finally {
            unavailable.close();
            fakePack.delete();
        }
    }

    private void verifyCandidateAccessibilityContract(
            Context context,
            KeyboardProfile english
    ) {
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, new RecordingInputListener(null));
            view.setProfile(english);
            view.setSuggestionSnapshot(SuggestionSnapshot.ready(
                    new SuggestionActivation(1, english.id()),
                    Arrays.asList("hello", "help", "held")
            ));
            assertTrue(
                    "candidate results stay individually accessible without auto-announcement",
                    view.candidateAccessibilityContractForTesting()
            );
            view.setSuggestionSnapshot(SuggestionSnapshot.ready(
                    new SuggestionActivation(2, english.id()),
                    Collections.singletonList("hello")
            ));
            assertEquals("single internal ready candidate", 1, view.visibleCandidateCountForTesting());
            assertTrue(
                    "hidden candidate slots clear stale accessibility labels",
                    view.candidateAccessibilityContractForTesting()
            );
            view.setSuggestionSnapshot(SuggestionSnapshot.state(
                    new SuggestionActivation(3, english.id()),
                    SuggestionSnapshot.Status.NO_MATCH
            ));
            assertTrue(
                    "candidate accessibility state clears before a status row",
                    view.candidateAccessibilityContractForTesting()
            );
            view.clearSuggestions();
            assertTrue(
                    "candidate accessibility state stays clear when inactive",
                    view.candidateAccessibilityContractForTesting()
            );
        });
    }

    private static void awaitReadinessStatus(
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
                        "unexpected internal readiness state: expected "
                                + expected
                                + ", got "
                                + actual
                );
            }
            SystemClock.sleep(25L);
        } while (SystemClock.elapsedRealtime() < deadline);
        throw new AssertionError("internal readiness state timed out: " + expected);
    }

    private int verifyRuntimeProfilesAndLayouts(
            Context context,
            RuntimeConformance conformance
    ) {
        for (RuntimeProfileVector vector : conformance.profiles) {
            KeyboardProfile profile = available(vector.profileId);
            assertEquals(vector.profileId + " language ID", vector.languageId, profile.languageId());
            assertEquals(
                    vector.profileId + " input method ID",
                    vector.inputMethodId,
                    profile.inputMethodId()
            );
            assertEquals(vector.profileId + " locale tag", vector.localeTag, profile.localeTag());
            assertEquals(vector.profileId + " display name", vector.displayName, profile.displayName());
            assertEquals(vector.profileId + " native name", vector.nativeName, profile.nativeName());
            assertEquals(
                    vector.profileId + " source script",
                    vector.sourceScript,
                    profile.sourceScript()
            );
            assertEquals(
                    vector.profileId + " output script",
                    vector.outputScript,
                    profile.outputScript()
            );
            assertEquals(vector.profileId + " detail", vector.detail, profile.detail());
            assertEquals(vector.profileId + " method type", vector.methodType, profile.methodType());
            assertEquals(vector.profileId + " engine kind", vector.engineKind, profile.engineKind());
            assertEquals(vector.profileId + " layout ID", vector.layoutId, profile.layoutId());
            assertEquals(
                    vector.profileId + " lookup kind",
                    vector.lookupKind,
                    profile.lookupKind().name()
            );
            assertEquals(
                    vector.profileId + " artifact kind",
                    vector.artifactKind,
                    profile.artifactKind().name()
            );
            assertEquals(
                    vector.profileId + " artifact binding",
                    vector.artifactBinding,
                    profile.artifactBinding()
            );
            assertEquals(
                    vector.profileId + " catalog readiness",
                    vector.catalogReadiness,
                    profile.catalogReadiness()
            );
            assertEquals(
                    vector.profileId + " availability",
                    vector.availability,
                    profile.availability().name()
            );
            assertEquals(
                    vector.profileId + " blocked reason",
                    vector.blockedReason,
                    profile.blockedReason()
            );
            assertEquals(
                    vector.profileId + " blocked detail",
                    vector.blockedDetail,
                    profile.blockedDetail()
            );
            assertEquals(
                    vector.profileId + " default enabled",
                    vector.defaultEnabled,
                    profile.defaultEnabled()
            );
            assertEquals(vector.profileId + " scope", vector.scope, profile.scope());
            assertEquals(vector.profileId + " group", vector.group, profile.group());
            assertEquals(vector.profileId + " variety", vector.variety, profile.variety());
            assertEquals(vector.profileId + " sort key", vector.sortKey, profile.sortKey());
            assertEquals(
                    vector.profileId + " search aliases",
                    vector.searchAliases,
                    profile.searchAliases()
            );
            assertEquals(
                    vector.profileId + " evidence IDs",
                    vector.evidenceIds,
                    profile.evidenceIds()
            );

            for (String layerId : RuntimeProfileVector.LAYER_IDS) {
                KeyboardLayouts.Layout layout = renderedLayer(profile, layerId);
                assertEquals(
                        vector.profileId + " " + layerId + " complete layer fingerprint",
                        vector.layerFingerprints.get(layerId),
                        renderedLayerFingerprint(layerId, layout)
                );
            }

            RecordingInputListener listener = new RecordingInputListener(null);
            runOnMainSync(() -> {
                NepaInputView view = new NepaInputView(context, listener);
                view.setProfile(profile);
                assertTrue(
                        vector.profileId + " stable key dispatch " + vector.dispatchKeyId,
                        view.performKeyIdForTesting(vector.dispatchKeyId)
                );
                assertTrue(vector.profileId + " stable dispatch callback", listener.keySpec != null);
                assertEquals(
                        vector.profileId + " stable dispatch key ID",
                        vector.dispatchKeyId,
                        listener.keySpec.keyId()
                );
                assertEquals(
                        vector.profileId + " stable dispatch text",
                        vector.dispatchText,
                        listener.keySpec.text()
                );
                assertEquals(
                        vector.profileId + " stable dispatch action",
                        KeySpec.Action.TEXT,
                        listener.keySpec.action()
                );
                assertEquals(
                        vector.profileId + " stable dispatch input policy",
                        KeySpec.InputPolicy.DEFAULT,
                        listener.keySpec.inputPolicy()
                );
                verifyPixelWidthGeometry(view, vector.profileId);
            });
        }
        return renderAllSelectableProfiles(context);
    }

    /**
     * Renders the installed product surface, including profiles promoted by the
     * reviewed transliteration supplement rather than present in lock conformance.
     */
    private int renderAllSelectableProfiles(Context context) {
        TransliterationCatalog transliterationCatalog = TransliterationCatalog.load(context);
        Set<String> rendered = new HashSet<>();
        for (KeyboardProfile profile : LanguageRegistry.available()) {
            assertTrue("unique keyboard render " + profile.id(), rendered.add(profile.id()));
            RecordingInputListener listener = new RecordingInputListener(null);
            runOnMainSync(() -> {
                NepaInputView view = new NepaInputView(context, listener);
                view.setProfile(profile);
                boolean transliterationAvailable = transliterationCatalog.supports(profile);
                view.setTransliterationAvailable(transliterationAvailable);
                if (LanguageRegistry.isTransliterationOnly(profile.id())) {
                    assertTrue(
                            profile.id() + " has a reviewed transliteration engine",
                            transliterationAvailable
                    );
                    view.toggleTransliteration();
                    assertTrue(
                            profile.id() + " renders its required phonetic surface",
                            view.isTransliterating()
                    );
                }
                verifyPixelWidthGeometry(view, profile.id());
                renderKeyboardEvidence(
                        context,
                        view,
                        "ime-internal-" + profile.id() + ".png"
                );
            });
        }
        return rendered.size();
    }

    private static void verifyPixelWidthGeometry(NepaInputView view, String label) {
        layoutForPixelWidth(view);
        assertTrue(label + " base Pixel-width geometry", view.visualGeometryContractForTesting());
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
        layoutForPixelWidth(view);
        assertTrue(label + " shift Pixel-width geometry", view.visualGeometryContractForTesting());
        view.showSymbols();
        layoutForPixelWidth(view);
        assertTrue(label + " symbols Pixel-width geometry", view.visualGeometryContractForTesting());
        view.setNumeric(true);
        layoutForPixelWidth(view);
        assertTrue(label + " numeric Pixel-width geometry", view.visualGeometryContractForTesting());
        view.setNumeric(false);
        view.setShifted(false);
        view.showLetters();
        layoutForPixelWidth(view);
        assertTrue(label + " restored base Pixel-width geometry", view.visualGeometryContractForTesting());
    }

    private static void layoutForPixelWidth(View view) {
        view.measure(
                View.MeasureSpec.makeMeasureSpec(1080, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(1400, View.MeasureSpec.AT_MOST)
        );
        view.layout(0, 0, 1080, view.getMeasuredHeight());
    }

    private static void renderKeyboardEvidence(Context context, View view, String name) {
        int width = 1080;
        int heightLimit = 1200;
        view.measure(
                View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(heightLimit, View.MeasureSpec.AT_MOST)
        );
        int height = view.getMeasuredHeight();
        view.layout(0, 0, width, height);
        assertTrue(name + " uses compact visible chrome",
                view instanceof NepaInputView
                        && height > 0
                        && height <= heightLimit
                        && ((NepaInputView) view).visualGeometryContractForTesting());
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        try {
            Canvas canvas = new Canvas(bitmap);
            view.draw(canvas);
            File output = new File(context.getFilesDir(), name);
            try (FileOutputStream stream = new FileOutputStream(output, false)) {
                if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                    throw new IllegalStateException("PNG encoder rejected " + name);
                }
            } catch (IOException failure) {
                throw new IllegalStateException("could not write " + name, failure);
            }
            assertTrue(name + " render is non-empty", output.isFile() && output.length() > 1024L);
        } finally {
            bitmap.recycle();
        }
    }

    private static KeyboardLayouts.Layout renderedLayer(
            KeyboardProfile profile,
            String layerId
    ) {
        switch (layerId) {
            case "base":
                return KeyboardLayouts.forProfile(profile, false, false, false);
            case "shift":
                return KeyboardLayouts.forProfile(profile, true, false, false);
            case "symbols":
                return KeyboardLayouts.forProfile(profile, false, true, false);
            case "numeric":
                return KeyboardLayouts.forProfile(profile, false, false, true);
            default:
                throw new AssertionError("unsupported conformance layer: " + layerId);
        }
    }

    private static String renderedLayerFingerprint(
            String layerId,
            KeyboardLayouts.Layout layout
    ) {
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (Exception failure) {
            throw new IllegalStateException("SHA-256 is unavailable", failure);
        }
        updateFingerprintString(digest, "nepa-runtime-layer-v1");
        updateFingerprintString(digest, layerId);
        updateFingerprintInt(digest, layout.rows().size());
        for (List<KeySpec> row : layout.rows()) {
            updateFingerprintInt(digest, row.size());
            for (KeySpec key : row) {
                updateFingerprintString(digest, key.keyId());
                updateFingerprintString(digest, key.label());
                updateFingerprintNullableString(digest, key.text());
                updateFingerprintString(digest, key.contentDescription());
                updateFingerprintString(digest, key.action().name());
                updateFingerprintNullableString(
                        digest,
                        key.inputPolicy() == null ? null : key.inputPolicy().name()
                );
                updateFingerprintInt(digest, key.widthUnits());
                updateFingerprintNullableString(
                        digest,
                        key.holdAction() == null ? null : key.holdAction().name()
                );
            }
        }
        return hex(digest.digest());
    }

    private static void updateFingerprintString(MessageDigest digest, String value) {
        updateFingerprintNullableString(digest, value);
    }

    private static void updateFingerprintNullableString(
            MessageDigest digest,
            String value
    ) {
        if (value == null) {
            updateFingerprintInt(digest, -1);
            return;
        }
        byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
        updateFingerprintInt(digest, encoded.length);
        digest.update(encoded);
    }

    private static void updateFingerprintInt(MessageDigest digest, int value) {
        digest.update((byte) (value >>> 24));
        digest.update((byte) (value >>> 16));
        digest.update((byte) (value >>> 8));
        digest.update((byte) value);
    }

    private PickerRecyclingEvidence verifyPicker(
            Context context,
            RuntimeConformance conformance,
            LanguagePreferences preferences,
            int expectedProfileCount,
            KeyboardProfile english,
            KeyboardProfile nepali
    ) {
        assertEquals(
                "picker verification uses the maximum enabled selectable set",
                expectedProfileCount,
                preferences.enabledProfiles().size()
        );
        String firstPickerProfileId = preferences.enabledProfiles().get(0).id();
        Intent hostIntent = new Intent(context, SettingsActivity.class);
        hostIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        SettingsActivity pickerHost = (SettingsActivity) startActivitySync(hostIntent);
        NepaInputView[] holder = new NepaInputView[1];
        RecordingInputListener listener = new RecordingInputListener(preferences);
        Map<View, String> attachedBindingsBeforeScroll = new IdentityHashMap<>();
        int[] attachedWindowRowCount = new int[1];
        int[] reboundRowCount = new int[1];
        runOnMainSync(() -> {
            holder[0] = new NepaInputView(pickerHost, listener);
            int constrainedPickerHeight = Math.round(
                    320 * context.getResources().getDisplayMetrics().density
            );
            pickerHost.setContentView(
                    holder[0],
                    new ViewGroup.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            constrainedPickerHeight
                    )
            );
            listener.attach(holder[0]);
            verifyPickerHoldAccessibilityContract(
                    context,
                    holder[0],
                    listener,
                    english,
                    nepali
            );
            holder[0].setProfile(english);
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            assertTrue(
                    "picker hold source accepts input focus",
                    holder[0].requestKeyInputFocusForTesting("base.r3.k2")
            );
            assertTrue(
                    "picker hold source owns input focus before dispatch",
                    holder[0].keyHasInputFocusForTesting("base.r3.k2")
            );
            assertTrue(
                    "focused picker hold accessibility dispatch",
                    holder[0].performPickerHoldAccessibilityActionForTesting("base.r3.k2")
            );
            assertTrue(
                    "focused picker hold opens actual picker",
                    holder[0].pickerVisibleForTesting()
            );
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            assertTrue(
                    "picker hold source loses input focus while picker is open",
                    !holder[0].keyHasInputFocusForTesting("base.r3.k2")
            );
            assertTrue("focused picker hold closes", holder[0].hidePicker());
            assertTrue(
                    "focused picker hold resets modal state",
                    holder[0].pickerAccessibilityRestoredForTesting()
            );
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            assertTrue(
                    "picker returns input focus to accessibility hold source",
                    holder[0].keyHasInputFocusForTesting("base.r3.k2")
            );
            assertTrue(
                    "picker hold return focus can be cleared",
                    holder[0].clearKeyInputFocusForTesting("base.r3.k2")
            );
            holder[0].setProfile(available(conformance.profiles.get(0).profileId));
            holder[0].showLanguagePicker();
            assertTrue("internal picker visible", holder[0].pickerVisibleForTesting());
            assertTrue("internal picker scrolls", holder[0].pickerUsesScrollingContainerForTesting());
            assertTrue(
                    "internal picker recycles rebound rows",
                    holder[0].pickerRecyclesRowsForTesting()
            );
            assertTrue(
                    "internal picker is accessibility-modal",
                    holder[0].pickerIsAccessibilityModalForTesting()
            );
            assertTrue(
                    "internal picker blocks underlying keyboard interaction",
                    holder[0].pickerBlocksUnderlyingKeyboardForTesting()
            );
            assertEquals(
                    "internal picker rows",
                    expectedProfileCount,
                    holder[0].pickerProfileCountForTesting()
            );
            String currentProfileId = holder[0].profile().id();
            assertTrue(
                    "current picker profile exposes selected state",
                    holder[0].pickerProfileSelectedForTesting(currentProfileId)
            );
            CharSequence selectedDescription =
                    holder[0].pickerProfileDescriptionForTesting(currentProfileId);
            assertTrue(
                    "current picker profile has localized selected description",
                    selectedDescription != null
                            && selectedDescription.toString().contains(
                            context.getString(R.string.selected_state)
                    )
            );
            if (conformance.profiles.size() > 1) {
                String otherProfileId = conformance.profiles.get(1).profileId;
                assertTrue(
                        "non-current picker profile is not selected",
                        !holder[0].pickerProfileSelectedForTesting(otherProfileId)
                );
            }
            for (RuntimeProfileVector vector : conformance.profiles) {
                assertTrue(
                        "internal picker contains " + vector.profileId,
                        holder[0].pickerHasProfileForTesting(vector.profileId)
                );
            }
            for (RuntimeProfileVector vector : conformance.profiles) {
                holder[0].showLanguagePicker();
                assertTrue(
                        "internal picker visible for " + vector.profileId,
                        holder[0].pickerVisibleForTesting()
                );
                assertTrue(
                        "internal picker modal for " + vector.profileId,
                        holder[0].pickerIsAccessibilityModalForTesting()
                );
                assertTrue(
                        "select generated picker row " + vector.profileId,
                        holder[0].performPickerProfileForTesting(vector.profileId)
                );
                assertEquals(
                        "picker callback profile " + vector.profileId,
                        vector.profileId,
                        listener.selectedProfileId
                );
                assertEquals(
                        "picker persisted active profile " + vector.profileId,
                        vector.profileId,
                        preferences.activeProfile().id()
                );
                assertEquals(
                        "picker switches visible profile " + vector.profileId,
                        vector.profileId,
                        holder[0].profile().id()
                );
                assertTrue(
                        "picker closes after selection " + vector.profileId,
                        !holder[0].pickerVisibleForTesting()
                );
                assertTrue(
                        "picker restores accessibility state after selection " + vector.profileId,
                        holder[0].pickerAccessibilityRestoredForTesting()
                );
            }
            holder[0].showLanguagePicker();
            assertTrue("hide picker action closes", holder[0].hidePicker());
            assertTrue(
                    "hide picker action restores accessibility state",
                    holder[0].pickerAccessibilityRestoredForTesting()
            );
            holder[0].showLanguagePicker();
            assertTrue("immediate picker close", holder[0].hidePicker());
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            assertTrue(
                    "stale posted focus cannot reopen picker modal state",
                    !holder[0].pickerVisibleForTesting()
                            && holder[0].pickerAccessibilityRestoredForTesting()
            );
            holder[0].showLanguagePicker();
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            String attachedProfileId = holder[0].profile().id();
            int attachedCount = holder[0].pickerAttachedProfileCountForTesting();
            attachedWindowRowCount[0] = attachedCount;
            assertTrue("maximum enabled picker attaches rows", attachedCount > 0);
            assertTrue(
                    "maximum enabled picker virtualizes rows",
                    attachedCount < expectedProfileCount
            );
            assertTrue(
                    "maximum enabled picker starts in its active tail window",
                    holder[0].pickerFirstVisiblePositionForTesting() > 0
            );
            assertTrue(
                    "attached active picker row keeps accessibility selected state",
                    holder[0].pickerAttachedProfileSelectedForTesting(attachedProfileId)
            );
            assertTrue(
                    "attached bottom rows have exact selection state",
                    holder[0].pickerAttachedRowsHaveExactSelectionStateForTesting(
                            attachedProfileId
                    )
            );
            for (View row : holder[0].pickerAttachedRowsForTesting()) {
                String boundProfileId = holder[0].pickerBoundProfileIdForTesting(row);
                assertTrue("attached bottom row has a profile binding", boundProfileId != null);
                assertTrue(
                        "attached bottom row identity is unique",
                        attachedBindingsBeforeScroll.put(row, boundProfileId) == null
                );
            }
            assertTrue(
                    "maximum enabled picker spans distinct scroll targets",
                    !firstPickerProfileId.equals(attachedProfileId)
            );
            assertTrue(
                    "scroll maximum enabled picker to first profile",
                    holder[0].pickerScrollToProfileForTesting(firstPickerProfileId)
            );
        });
        awaitPickerFirstVisiblePosition(
                holder[0],
                0,
                "maximum enabled picker reaches first position"
        );
        runOnMainSync(() -> {
            String activeProfileId = holder[0].profile().id();
            boolean firstProfileAttached = false;
            int attachedViewReboundCount = 0;
            for (View row : holder[0].pickerAttachedRowsForTesting()) {
                String boundProfileId = holder[0].pickerBoundProfileIdForTesting(row);
                assertTrue("attached top row has a profile binding", boundProfileId != null);
                if (firstPickerProfileId.equals(boundProfileId)) {
                    firstProfileAttached = true;
                }
                String previousProfileId = attachedBindingsBeforeScroll.get(row);
                if (previousProfileId != null && !previousProfileId.equals(boundProfileId)) {
                    attachedViewReboundCount++;
                }
            }
            assertTrue("first picker profile is attached after scroll", firstProfileAttached);
            assertTrue("ListView reuses an attached picker row", attachedViewReboundCount > 0);
            reboundRowCount[0] = attachedViewReboundCount;
            assertTrue(
                    "recycled top rows never inherit active selection state",
                    holder[0].pickerAttachedRowsHaveExactSelectionStateForTesting(activeProfileId)
            );
            assertTrue(
                    "scroll maximum enabled picker back to active profile",
                    holder[0].pickerScrollToProfileForTesting(activeProfileId)
            );
        });
        awaitPickerAttachedProfileSelected(
                holder[0],
                conformance.profiles.get(conformance.profiles.size() - 1).profileId,
                "active picker row is attached after return scroll"
        );
        runOnMainSync(() -> {
            String attachedProfileId = holder[0].profile().id();
            assertEquals(
                    "scrolling does not change the persisted active profile",
                    attachedProfileId,
                    preferences.activeProfile().id()
            );
            assertTrue(
                    "active picker row is attached after return scroll",
                    holder[0].pickerAttachedProfileSelectedForTesting(attachedProfileId)
            );
            assertTrue(
                    "active selection persists after attached row recycling",
                    holder[0].pickerAttachedRowsHaveExactSelectionStateForTesting(
                            attachedProfileId
                    )
            );
            assertTrue("attached-state picker closes", holder[0].hidePicker());
            assertTrue(
                    "attached-state picker restores accessibility state",
                    holder[0].pickerAccessibilityRestoredForTesting()
            );
            pickerHost.finish();
        });
        return new PickerRecyclingEvidence(
                expectedProfileCount,
                attachedWindowRowCount[0],
                reboundRowCount[0]
        );
    }

    private void awaitPickerFirstVisiblePosition(
            NepaInputView picker,
            int expectedPosition,
            String label
    ) {
        long deadline = SystemClock.elapsedRealtime() + PICKER_LAYOUT_TIMEOUT_MS;
        int[] actualPosition = {-1};
        do {
            waitForIdleSync();
            runOnMainSync(() ->
                    actualPosition[0] = picker.pickerFirstVisiblePositionForTesting()
            );
            if (actualPosition[0] == expectedPosition) {
                return;
            }
            SystemClock.sleep(25L);
        } while (SystemClock.elapsedRealtime() < deadline);
        assertEquals(label, expectedPosition, actualPosition[0]);
    }

    private void awaitPickerAttachedProfileSelected(
            NepaInputView picker,
            String profileId,
            String label
    ) {
        long deadline = SystemClock.elapsedRealtime() + PICKER_LAYOUT_TIMEOUT_MS;
        boolean[] selected = {false};
        do {
            waitForIdleSync();
            runOnMainSync(() ->
                    selected[0] = picker.pickerAttachedProfileSelectedForTesting(profileId)
            );
            if (selected[0]) {
                return;
            }
            SystemClock.sleep(25L);
        } while (SystemClock.elapsedRealtime() < deadline);
        assertTrue(label, selected[0]);
    }

    private static void verifyPickerHoldAccessibilityContract(
            Context context,
            NepaInputView inputView,
            RecordingInputListener listener,
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
                    listener.keySpec.action()
            );
            assertTrue(
                    profile.id() + " ordinary space tap dispatches",
                    inputView.performKeyIdForTesting("base.r3.k3")
            );
            assertEquals(
                    profile.id() + " ordinary space tap action",
                    KeySpec.Action.SPACE,
                    listener.keySpec.action()
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

    private static void verifySetupStateModel() {
        assertSetupStep(
                "disabled keyboard",
                false,
                false,
                0,
                false,
                SettingsActivity.SetupStep.ENABLE_KEYBOARD,
                false
        );
        assertSetupStep(
                "enabled unselected keyboard",
                true,
                false,
                1,
                true,
                SettingsActivity.SetupStep.SELECT_KEYBOARD,
                false
        );
        assertSetupStep(
                "selected keyboard without a language",
                true,
                true,
                0,
                true,
                SettingsActivity.SetupStep.CHOOSE_LANGUAGES,
                false
        );
        assertSetupStep(
                "selected keyboard ready to test",
                true,
                true,
                2,
                false,
                SettingsActivity.SetupStep.TEST_TYPING,
                false
        );
        assertSetupStep(
                "observed typing completes current setup",
                true,
                true,
                2,
                true,
                SettingsActivity.SetupStep.COMPLETE,
                true
        );
    }

    private static void assertSetupStep(
            String label,
            boolean imeEnabled,
            boolean imeSelected,
            int enabledLanguageCount,
            boolean typingObserved,
            SettingsActivity.SetupStep expectedStep,
            boolean expectedComplete
    ) {
        SettingsActivity.SetupState state = SettingsActivity.deriveSetupStateForTesting(
                imeEnabled,
                imeSelected,
                enabledLanguageCount,
                typingObserved
        );
        assertEquals(label + " step", expectedStep, state.currentStep());
        assertEquals(label + " complete", expectedComplete, state.complete());
        assertEquals(
                label + " typing evidence",
                expectedComplete,
                state.typingTested()
        );
    }

    private static SetupPlatformObservation observeSetupPlatform(Context context) {
        InputMethodManager manager = (InputMethodManager) context.getSystemService(
                Context.INPUT_METHOD_SERVICE
        );
        InputMethodInfo own = null;
        for (InputMethodInfo info : manager.getInputMethodList()) {
            if (context.getPackageName().equals(info.getPackageName())
                    && NepaInputMethodService.class.getName().equals(info.getServiceName())) {
                own = info;
                break;
            }
        }
        if (own == null) {
            return new SetupPlatformObservation(false, false);
        }
        boolean enabled = false;
        for (InputMethodInfo info : manager.getEnabledInputMethodList()) {
            if (own.getId().equals(info.getId())) {
                enabled = true;
                break;
            }
        }
        String selected = Settings.Secure.getString(
                context.getContentResolver(),
                Settings.Secure.DEFAULT_INPUT_METHOD
        );
        return new SetupPlatformObservation(enabled, own.getId().equals(selected));
    }

    private void verifyLanguageManager(Context context) throws InterruptedException {
        Intent settingsIntent = new Intent(context, SettingsActivity.class);
        settingsIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        SettingsActivity original = (SettingsActivity) startActivitySync(settingsIntent);
        long insetDeadline = SystemClock.elapsedRealtime() + PICKER_LAYOUT_TIMEOUT_MS;
        while (!original.systemBarInsetsAppliedForTesting()
                && SystemClock.elapsedRealtime() < insetDeadline) {
            SystemClock.sleep(25L);
        }
        assertTrue(
                "settings activity avoids system bars",
                original.systemBarInsetsAppliedForTesting()
        );
        SetupPlatformObservation setupPlatform = observeSetupPlatform(context);
        int setupLanguageCount = new LanguagePreferences(context).enabledProfiles().size();
        boolean expectedSetupComplete = setupPlatform.enabled
                && setupPlatform.selected
                && setupLanguageCount > 0;
        LanguagePreferences managerPreferences = new LanguagePreferences(context);
        KeyboardProfile temporarilyDisabled = firstNonActiveAvailable(
                managerPreferences.activeProfile().id()
        );
        int availableCount = LanguageRegistry.available().size();
        int laterCount = LanguageRegistry.all().size() - availableCount;
        int[] before = new int[3];
        runOnMainSync(() -> {
            SettingsActivity.SetupState observedSetup = original.setupStateForTesting();
            assertEquals(
                    "setup reflects Android enabled state",
                    setupPlatform.enabled,
                    observedSetup.imeEnabled()
            );
            assertEquals(
                    "setup reflects Android selected state",
                    setupPlatform.selected,
                    observedSetup.imeSelected()
            );
            assertEquals(
                    "setup reflects enabled language state",
                    setupLanguageCount,
                    observedSetup.enabledLanguageCount()
            );
            assertTrue(
                    "setup typing text persistence is disabled",
                    original.setupTypingTextPersistenceDisabledForTesting()
            );
            original.setSetupTypingTextForTesting("setup-test");
            assertEquals(
                    "setup test edit is visible only in the current instance",
                    "setup-test",
                    original.setupTypingTextForTesting()
            );
            SettingsActivity.SetupState typedSetup = original.setupStateForTesting();
            assertEquals(
                    "typing completes only an actually enabled and selected keyboard",
                    expectedSetupComplete,
                    typedSetup.complete()
            );
            assertTrue(
                    "internal language manager uses stable IDs",
                    original.languageManagerHasStableIdsForTesting()
            );
            assertEquals(
                    "internal language manager view types",
                    2,
                    original.languageManagerViewTypeCountForTesting()
            );
            assertEquals(
                    "all selectable profiles start in enabled section",
                    availableCount,
                    original.languageManagerSectionCountForTesting(
                            SettingsActivity.LanguageSection.ENABLED
                    )
            );
            assertEquals(
                    "no selectable profile starts available to enable",
                    0,
                    original.languageManagerSectionCountForTesting(
                            SettingsActivity.LanguageSection.AVAILABLE_TO_ENABLE
                    )
            );
            assertEquals(
                    "blocked profiles start in later section",
                    laterCount,
                    original.languageManagerSectionCountForTesting(
                            SettingsActivity.LanguageSection.LATER
                    )
            );
            assertTrue(
                    "language manager sections are ordered",
                    original.languageManagerSectionsOrderedForTesting()
            );
            assertTrue(
                    "language manager section headings are bound and accessible",
                    original.languageManagerSectionHeadingsForTesting()
            );
            assertTrue(
                    "temporarily disable one non-active selectable profile",
                    managerPreferences.setEnabled(temporarilyDisabled.id(), false)
            );
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            assertEquals(
                    "preference listener moves disabled profile out of enabled section",
                    availableCount - 1,
                    original.languageManagerSectionCountForTesting(
                            SettingsActivity.LanguageSection.ENABLED
                    )
            );
            assertEquals(
                    "disabled selectable profile enters available-to-enable section",
                    1,
                    original.languageManagerSectionCountForTesting(
                            SettingsActivity.LanguageSection.AVAILABLE_TO_ENABLE
                    )
            );
            assertEquals(
                    "later count stays stable after selectable disable",
                    laterCount,
                    original.languageManagerSectionCountForTesting(
                            SettingsActivity.LanguageSection.LATER
                    )
            );
            assertTrue(
                    "three-section manager remains ordered after disable",
                    original.languageManagerSectionsOrderedForTesting()
            );
            assertTrue(
                    "three-section headings bind after disable",
                    original.languageManagerSectionHeadingsForTesting()
            );
            List<KeyboardProfile> expectedPickerProfiles =
                    managerPreferences.enabledProfiles();
            NepaInputView enabledOnlyPicker = new NepaInputView(
                    context,
                    new RecordingInputListener(managerPreferences)
            );
            enabledOnlyPicker.setProfile(managerPreferences.activeProfile());
            enabledOnlyPicker.showLanguagePicker();
            assertEquals(
                    "in-keyboard picker has exactly the enabled-profile count",
                    expectedPickerProfiles.size(),
                    enabledOnlyPicker.pickerProfileCountForTesting()
            );
            for (KeyboardProfile expected : expectedPickerProfiles) {
                assertTrue(
                        "in-keyboard picker contains enabled profile " + expected.id(),
                        enabledOnlyPicker.pickerHasProfileForTesting(expected.id())
                );
            }
            assertTrue(
                    "in-keyboard picker excludes disabled selectable profile",
                    !enabledOnlyPicker.pickerHasProfileForTesting(temporarilyDisabled.id())
            );
            for (KeyboardProfile profile : LanguageRegistry.all()) {
                if (!profile.isAvailable()) {
                    assertTrue(
                            "in-keyboard picker excludes Later profile " + profile.id(),
                            !enabledOnlyPicker.pickerHasProfileForTesting(profile.id())
                    );
                }
            }
            assertTrue(
                    "enabled-only picker closes after partition verification",
                    enabledOnlyPicker.hidePicker()
            );
            assertTrue(
                    "restore temporarily disabled selectable profile",
                    managerPreferences.setEnabled(temporarilyDisabled.id(), true)
            );
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            assertEquals(
                    "preference listener restores enabled section count",
                    availableCount,
                    original.languageManagerSectionCountForTesting(
                            SettingsActivity.LanguageSection.ENABLED
                    )
            );
            assertEquals(
                    "preference listener clears available-to-enable section",
                    0,
                    original.languageManagerSectionCountForTesting(
                            SettingsActivity.LanguageSection.AVAILABLE_TO_ENABLE
                    )
            );
            assertTrue(
                    "internal language manager recycles and rebinds rows",
                    original.languageManagerRecyclesRowsForTesting()
            );
            original.setLanguageQueryForTesting("deva");
            before[0] = original.visibleLanguageProfilesForTesting();
            assertTrue("Devanagari query remains scrollable", before[0] > 12);
            assertTrue(
                    "filtered language sections retain stable ordering",
                    original.languageManagerSectionsOrderedForTesting()
            );
            assertTrue(
                    "filtered language section headings stay bound and accessible",
                    original.languageManagerSectionHeadingsForTesting()
            );
            original.setLanguageManagerSelectionFromTopForTesting(10, -13);
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            before[1] = original.languageManagerFirstVisiblePositionForTesting();
            before[2] = original.languageManagerFirstVisibleOffsetForTesting();
            assertTrue("language manager moved away from top", before[1] > 0);
        });

        Application application = (Application) context.getApplicationContext();
        AtomicReference<SettingsActivity> recreatedReference = new AtomicReference<>();
        CountDownLatch recreatedLatch = new CountDownLatch(1);
        Application.ActivityLifecycleCallbacks callbacks =
                new Application.ActivityLifecycleCallbacks() {
                    @Override
                    public void onActivityCreated(Activity activity, Bundle state) {
                        if (activity instanceof SettingsActivity && activity != original) {
                            recreatedReference.set((SettingsActivity) activity);
                            recreatedLatch.countDown();
                        }
                    }

                    @Override
                    public void onActivityStarted(Activity activity) {
                    }

                    @Override
                    public void onActivityResumed(Activity activity) {
                    }

                    @Override
                    public void onActivityPaused(Activity activity) {
                    }

                    @Override
                    public void onActivityStopped(Activity activity) {
                    }

                    @Override
                    public void onActivitySaveInstanceState(Activity activity, Bundle state) {
                    }

                    @Override
                    public void onActivityDestroyed(Activity activity) {
                    }
                };
        application.registerActivityLifecycleCallbacks(callbacks);
        try {
            runOnMainSync(original::recreate);
            assertTrue(
                    "language manager recreated after saved-state request",
                    recreatedLatch.await(30, TimeUnit.SECONDS)
            );
        } finally {
            application.unregisterActivityLifecycleCallbacks(callbacks);
        }
        SettingsActivity recreated = recreatedReference.get();
        assertTrue("recreated language manager instance captured", recreated != null);
        String soleProfileId = managerPreferences.activeProfile().id();
        waitForIdleSync();
        runOnMainSync(() -> {
            assertEquals(
                    "observable setup state survives instance recreation",
                    expectedSetupComplete,
                    recreated.setupStateForTesting().complete()
            );
            assertEquals(
                    "setup test text is not restored after instance recreation",
                    "",
                    recreated.setupTypingTextForTesting()
            );
            assertEquals(
                    "language manager query survives recreation",
                    "deva",
                    recreated.languageQueryForTesting()
            );
            assertEquals(
                    "language manager filtered count survives recreation",
                    before[0],
                    recreated.visibleLanguageProfilesForTesting()
            );
            assertEquals(
                    "language manager position survives recreation",
                    before[1],
                    recreated.languageManagerFirstVisiblePositionForTesting()
            );
            assertEquals(
                    "language manager pixel offset survives recreation",
                    before[2],
                    recreated.languageManagerFirstVisibleOffsetForTesting()
            );
            recreated.setLanguageQueryForTesting("");
            for (KeyboardProfile profile : LanguageRegistry.available()) {
                if (!profile.id().equals(soleProfileId)) {
                    assertTrue(
                            "prepare sole enabled profile " + soleProfileId,
                            managerPreferences.setEnabled(profile.id(), false)
                    );
                }
            }
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            assertEquals(
                    "repeated final-disable case has exactly one enabled profile",
                    1,
                    managerPreferences.enabledProfiles().size()
            );
            assertTrue(
                    "same switch rejects repeated attempts to disable final profile",
                    recreated.languageManagerRejectsRepeatedLastDisableForTesting(
                            soleProfileId
                    )
            );
            for (KeyboardProfile profile : LanguageRegistry.available()) {
                if (!profile.id().equals(soleProfileId)) {
                    assertTrue(
                            "restore selectable profile after final-disable case "
                                    + profile.id(),
                            managerPreferences.setEnabled(profile.id(), true)
                    );
                }
            }
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            assertEquals(
                    "final-disable case restores all selectable profiles",
                    availableCount,
                    managerPreferences.enabledProfiles().size()
            );
            assertEquals(
                    "restored manager returns every selectable profile to Enabled",
                    availableCount,
                    recreated.languageManagerSectionCountForTesting(
                            SettingsActivity.LanguageSection.ENABLED
                    )
            );
            recreated.finish();
        });
    }

    private static KeyboardProfile firstNonActiveAvailable(String activeProfileId) {
        for (KeyboardProfile profile : LanguageRegistry.available()) {
            if (!profile.id().equals(activeProfileId)) {
                return profile;
            }
        }
        throw new AssertionError("language-section test needs two selectable profiles");
    }

    private void verifyDhimalKeyDispatch(Context context, KeyboardProfile dhimal) {
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(dhimal);
            assertDispatchedTextKey(view, listener, "इ", KeySpec.InputPolicy.DEFAULT);
            assertDispatchedTextKey(view, listener, "ए", KeySpec.InputPolicy.DEFAULT);
            assertDispatchedTextKey(view, listener, "ः", KeySpec.InputPolicy.DEFAULT);
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200c",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertDispatchedTextKey(view, listener, "[", KeySpec.InputPolicy.DEFAULT);
            assertDispatchedTextKey(view, listener, "]", KeySpec.InputPolicy.DEFAULT);
        });
    }

    private void verifyLimbuKeyDispatch(Context context, KeyboardProfile limbu) {
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(limbu);
            assertTrue("dispatch Limbu key", view.performTextKeyForTesting("ᤀ"));
            assertEquals("Limbu key callback", "ᤀ", listener.keyText);
        });
    }

    private void verifySunuwarKeyDispatch(Context context, KeyboardProfile sunuwar) {
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(sunuwar);
            assertDispatchedTextKey(
                    view,
                    listener,
                    "ॆ",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "़",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "ॽ",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "‘",
                    KeySpec.InputPolicy.ORTHOGRAPHIC_WORD
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200c",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
        });
    }

    private void verifyWesternTamangKeyDispatch(
            Context context,
            KeyboardProfile westernTamang
    ) {
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(westernTamang);
            listener.keySpec = null;
            assertTrue(
                    "dispatch Western Tamang Devanagari eight by stable key ID",
                    view.performKeyIdForTesting("base.r3.k4")
            );
            assertTrue("Western Tamang stable dispatch callback", listener.keySpec != null);
            assertEquals("Western Tamang stable dispatch key ID", "base.r3.k4", listener.keySpec.keyId());
            assertEquals("Western Tamang stable dispatch text", "८", listener.keySpec.text());
            assertEquals(
                    "Western Tamang stable dispatch policy",
                    KeySpec.InputPolicy.DEFAULT,
                    listener.keySpec.inputPolicy()
            );
        });
    }

    private void verifyLohorungKeyDispatch(Context context, KeyboardProfile lohorung) {
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(lohorung);
            for (String text : new String[]{"इ", "ई", "ऎ", "ए", "ः", "ॆ", "़", "ॽ"}) {
                assertDispatchedTextKey(view, listener, text, KeySpec.InputPolicy.DEFAULT);
            }
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200c",
                    KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ
            );
            listener.keySpec = null;
            assertTrue(
                    "dispatch Lohorung terminal ZWNJ by stable key ID",
                    view.performKeyIdForTesting("base.r3.k9")
            );
            assertTrue("Lohorung stable dispatch callback", listener.keySpec != null);
            assertEquals("Lohorung stable dispatch key ID", "base.r3.k9", listener.keySpec.keyId());
            assertEquals("Lohorung stable dispatch text", "\u200c", listener.keySpec.text());
            assertEquals(
                    "Lohorung stable dispatch policy",
                    KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ,
                    listener.keySpec.inputPolicy()
            );
        });
    }

    private void verifyYakkhaKeyDispatch(Context context, KeyboardProfile yakkha) {
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(yakkha);
            for (String text : new String[]{"इ", "ए", "ॽ"}) {
                assertDispatchedTextKey(view, listener, text, KeySpec.InputPolicy.DEFAULT);
            }
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200c",
                    KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ
            );

            view.showSymbols();
            String[] keyIds = {"symbols.r1.k5", "symbols.r2.k7", "symbols.r2.k9"};
            String[] text = {"-", "/", "\\"};
            for (int index = 0; index < keyIds.length; index++) {
                listener.keySpec = null;
                assertTrue(
                        "dispatch Yakkha symbol by stable key ID " + keyIds[index],
                        view.performKeyIdForTesting(keyIds[index])
                );
                assertTrue("Yakkha symbol dispatch callback", listener.keySpec != null);
                assertEquals("Yakkha symbol stable key ID", keyIds[index], listener.keySpec.keyId());
                assertEquals("Yakkha symbol text", text[index], listener.keySpec.text());
                assertEquals(
                        "Yakkha symbol input policy",
                        KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION,
                        listener.keySpec.inputPolicy()
                );
            }
        });
    }

    private void verifyKhalingKeyDispatch(Context context, KeyboardProfile khaling) {
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(khaling);
            for (String text : new String[]{"इ", "ई", "ए", "़"}) {
                assertDispatchedTextKey(view, listener, text, KeySpec.InputPolicy.DEFAULT);
            }
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200c",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );

            view.showSymbols();
            listener.keySpec = null;
            assertTrue(
                    "dispatch Khaling hyphen by stable key ID",
                    view.performKeyIdForTesting("symbols.r1.k5")
            );
            assertTrue("Khaling hyphen dispatch callback", listener.keySpec != null);
            assertEquals(
                    "Khaling hyphen stable key ID",
                    "symbols.r1.k5",
                    listener.keySpec.keyId()
            );
            assertEquals("Khaling hyphen text", "-", listener.keySpec.text());
            assertEquals(
                    "Khaling hyphen input policy",
                    KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION,
                    listener.keySpec.inputPolicy()
            );
        });
    }

    private void verifyDumiKeyDispatch(Context context, KeyboardProfile dumi) {
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(dumi);
            for (String text : new String[]{"इ", "ई", "ए", "़", "ः", "ॽ"}) {
                assertDispatchedTextKey(view, listener, text, KeySpec.InputPolicy.DEFAULT);
            }
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200c",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );

            view.showSymbols();
            String[] keyIds = {"symbols.r1.k5", "symbols.r2.k3"};
            String[] text = {"-", ":"};
            for (int index = 0; index < keyIds.length; index++) {
                listener.keySpec = null;
                assertTrue(
                        "dispatch Dumi punctuation by stable key ID " + keyIds[index],
                        view.performKeyIdForTesting(keyIds[index])
                );
                assertTrue("Dumi punctuation dispatch callback", listener.keySpec != null);
                assertEquals("Dumi punctuation stable key ID", keyIds[index], listener.keySpec.keyId());
                assertEquals("Dumi punctuation text", text[index], listener.keySpec.text());
                assertEquals(
                        "Dumi punctuation input policy",
                        KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION,
                        listener.keySpec.inputPolicy()
                );
            }
        });
    }

    private static void verifyNewDirectProfileAndLayout(
            KeyboardProfile profile,
            String profileId,
            String methodId,
            String layoutId,
            int letterRows
    ) {
        assertEquals(profileId + " profile ID", profileId, profile.id());
        assertEquals(profileId + " input method", methodId, profile.inputMethodId());
        assertEquals(profileId + " input script", "Deva", profile.sourceScript());
        assertEquals(profileId + " output script", "Deva", profile.outputScript());
        assertEquals(profileId + " layout binding", layoutId, profile.layoutId());
        assertEquals(profileId + " pack binding", profileId, profile.packBinding());
        assertTrue(profileId + " generated layout", KeyboardLayouts.hasLayoutForTesting(layoutId));
        assertEquals(profileId + " generated layout script", "Deva",
                KeyboardLayouts.inputScriptForTesting(layoutId));
        assertEquals(profileId + " base rows", letterRows,
                KeyboardLayouts.forProfile(profile, false, false, false).rows().size());
        assertEquals(profileId + " shift rows", letterRows,
                KeyboardLayouts.forProfile(profile, true, false, false).rows().size());
        assertEquals(profileId + " symbol rows", 4,
                KeyboardLayouts.forProfile(profile, false, true, false).rows().size());
    }

    private void verifyBantawaLayoutAndDispatch(
            Context context,
            KeyboardProfile nepali,
            KeyboardProfile bantawa
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(bantawa, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(bantawa, true, false, false);
        KeyboardLayouts.Layout nepaliShift = KeyboardLayouts.forProfile(nepali, true, false, false);
        assertGeneratedTextKey(shift, "shift.r0.k1", "ए", "ए", "ए",
                KeySpec.InputPolicy.DEFAULT);
        assertGeneratedTextKey(shift, "shift.r2.k0", "इ", "इ", "इ",
                KeySpec.InputPolicy.DEFAULT);
        assertEquals("Bantawa retained base vowel sign", "ौ",
                requiredKey(base, "base.r0.k1").text());
        assertEquals("Nepali independent vowel stays isolated", "औ",
                requiredKey(nepaliShift, "shift.r0.k1").text());
        assertEquals("Nepali independent i stays isolated", "ऋ",
                requiredKey(nepaliShift, "shift.r2.k0").text());
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(bantawa);
            view.setShifted(true);
            assertDispatchedKey(view, listener, "shift.r0.k1", "ए",
                    KeySpec.InputPolicy.DEFAULT);
            assertDispatchedKey(view, listener, "shift.r2.k0", "इ",
                    KeySpec.InputPolicy.DEFAULT);
        });
    }

    private void verifyWesternMagarLayoutAndDispatch(
            Context context,
            KeyboardProfile nepali,
            KeyboardProfile westernMagar
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(westernMagar, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(westernMagar, true, false, false);
        for (KeyboardLayouts.Layout layout : new KeyboardLayouts.Layout[]{base, shift}) {
            String layer = layout == base ? "base" : "shift";
            assertGeneratedTextKey(layout, layer + ".r3.k2", "ऐ", "ऐ", "ऐ",
                    KeySpec.InputPolicy.DEFAULT);
            assertGeneratedTextKey(layout, layer + ".r3.k3", "\u200d", "ZWJ",
                    "Western Magar conjunct zero width joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER);
            assertGeneratedTextKey(layout, layer + ".r3.k4", "\u200c", "ZWNJ",
                    "Western Magar conjunct or terminal zero width non-joiner",
                    KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ);
        }
        verifyNewDirectPunctuation(westernMagar, nepali);
        verifyNewDirectInputPolicies(westernMagar, "base.r3.k3", "base.r3.k4");
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(westernMagar);
            assertDispatchedKey(view, listener, "base.r3.k2", "ऐ",
                    KeySpec.InputPolicy.DEFAULT);
            assertDispatchedKey(view, listener, "base.r3.k3", "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER);
            assertDispatchedKey(view, listener, "base.r3.k4", "\u200c",
                    KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ);
            verifyNewDirectPunctuationDispatch(view, listener);
        });
    }

    private void verifyMidEasternTharuLayoutAndDispatch(
            Context context,
            KeyboardProfile nepali,
            KeyboardProfile tharu
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(tharu, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(tharu, true, false, false);
        for (KeyboardLayouts.Layout layout : new KeyboardLayouts.Layout[]{base, shift}) {
            String layer = layout == base ? "base" : "shift";
            assertGeneratedTextKey(layout, layer + ".r3.k4", "़", "◌़",
                    "Devanagari sign nukta", KeySpec.InputPolicy.DEFAULT);
            assertGeneratedTextKey(layout, layer + ".r3.k5", "\u200d", "ZWJ",
                    "Tharu conjunct zero width joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER);
            assertGeneratedTextKey(layout, layer + ".r3.k6", "\u200c", "ZWNJ",
                    "Tharu conjunct zero width non-joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER);
        }
        verifyNewDirectPunctuation(tharu, nepali);
        verifyNewDirectInputPolicies(tharu, "base.r3.k5", "base.r3.k6");
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(tharu);
            assertDispatchedKey(view, listener, "base.r3.k0", "इ",
                    KeySpec.InputPolicy.DEFAULT);
            assertDispatchedKey(view, listener, "base.r3.k4", "़",
                    KeySpec.InputPolicy.DEFAULT);
            assertDispatchedKey(view, listener, "base.r3.k5", "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER);
            assertDispatchedKey(view, listener, "base.r3.k6", "\u200c",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER);
            verifyNewDirectPunctuationDispatch(view, listener);
        });
    }

    private static void verifyNewDirectPunctuation(
            KeyboardProfile profile,
            KeyboardProfile nepali
    ) {
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(profile, false, true, false);
        KeyboardLayouts.Layout nepaliSymbols = KeyboardLayouts.forProfile(nepali, false, true, false);
        for (String keyId : new String[]{"symbols.r1.k5", "symbols.r2.k7"}) {
            assertEquals(profile.id() + " intra-word " + keyId,
                    KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION,
                    requiredKey(symbols, keyId).inputPolicy());
            assertEquals("Nepali punctuation isolation " + keyId,
                    KeySpec.InputPolicy.DEFAULT,
                    requiredKey(nepaliSymbols, keyId).inputPolicy());
        }
    }

    private static void verifyNewDirectInputPolicies(
            KeyboardProfile profile,
            String zwjKeyId,
            String zwnjKeyId
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(profile, false, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(profile, false, true, false);
        NoOpSuggestionEngine engine = new NoOpSuggestionEngine();
        try {
            String[] joinerIds = {zwjKeyId, zwnjKeyId};
            String[] joiners = {"\u200d", "\u200c"};
            for (int index = 0; index < joinerIds.length; index++) {
                RecordingTextSink sink = new RecordingTextSink();
                ComposingSession session = new ComposingSession(engine);
                session.start(profile, true, false, sink);
                appendKey(session, requiredKey(base, "base.r1.k7"), sink);
                appendKey(session, requiredKey(base, "base.r2.k9"), sink);
                int beforeJoiner = sink.editorCalls.size();
                appendKey(session, requiredKey(base, joinerIds[index]), sink);
                assertEquals(profile.id() + " joiner remains buffered", beforeJoiner,
                        sink.editorCalls.size());
                appendKey(session, requiredKey(base, "base.r0.k5"), sink);
                assertEquals(profile.id() + " joined editor text", "क्" + joiners[index] + "य",
                        sink.text());
                assertNoEditorCallEndsInJoiner(profile.id() + " joined editor update", sink);
            }
            String[] punctuationIds = {"symbols.r1.k5", "symbols.r2.k7"};
            String[] punctuation = {"-", "/"};
            for (int index = 0; index < punctuationIds.length; index++) {
                RecordingTextSink sink = new RecordingTextSink();
                ComposingSession session = new ComposingSession(engine);
                session.start(profile, true, false, sink);
                appendKey(session, requiredKey(base, "base.r1.k7"), sink);
                appendKey(session, requiredKey(symbols, punctuationIds[index]), sink);
                appendKey(session, requiredKey(base, "base.r0.k5"), sink);
                assertEquals(profile.id() + " intra-word punctuation composes",
                        "क" + punctuation[index] + "य", session.composingText());

                RecordingTextSink leadingSink = new RecordingTextSink();
                ComposingSession leading = new ComposingSession(engine);
                leading.start(profile, true, false, leadingSink);
                appendKey(leading, requiredKey(symbols, punctuationIds[index]), leadingSink);
                assertEquals(profile.id() + " leading punctuation stays outside composition",
                        "", leading.composingText());
                assertEquals(profile.id() + " leading punctuation remains typeable",
                        punctuation[index], leadingSink.text());
            }
        } finally {
            engine.close();
        }
    }

    private static void verifyNewDirectPunctuationDispatch(
            NepaInputView view,
            RecordingInputListener listener
    ) {
        view.showSymbols();
        assertDispatchedKey(view, listener, "symbols.r1.k5", "-",
                KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION);
        assertDispatchedKey(view, listener, "symbols.r2.k7", "/",
                KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION);
    }

    private static void assertDispatchedKey(
            NepaInputView view,
            RecordingInputListener listener,
            String keyId,
            String text,
            KeySpec.InputPolicy policy
    ) {
        listener.keySpec = null;
        assertTrue("dispatch stable key " + keyId, view.performKeyIdForTesting(keyId));
        assertTrue("stable key dispatch callback " + keyId, listener.keySpec != null);
        assertEquals("stable key ID " + keyId, keyId, listener.keySpec.keyId());
        assertEquals("stable key text " + keyId, text, listener.keySpec.text());
        assertEquals("stable key policy " + keyId, policy, listener.keySpec.inputPolicy());
    }

    private static void assertDispatchedTextKey(
            NepaInputView view,
            RecordingInputListener listener,
            String text,
            KeySpec.InputPolicy inputPolicy
    ) {
        listener.keySpec = null;
        assertTrue("dispatch generated text key " + printable(text), view.performTextKeyForTesting(text));
        assertTrue("generated dispatch returns KeySpec " + printable(text), listener.keySpec != null);
        assertEquals("generated dispatch text " + printable(text), text, listener.keySpec.text());
        assertEquals(
                "generated dispatch policy " + printable(text),
                inputPolicy,
                listener.keySpec.inputPolicy()
        );
    }

    private static void verifyRomanizedNewaProfileAndLayout(
            KeyboardProfile directDevanagari,
            KeyboardProfile romanizedNewa
    ) {
        assertEquals("Romanized Newa profile ID", NEPAL_BHASA_ROMAN_ID, romanizedNewa.id());
        assertEquals("Romanized Newa input method", "new-latn-deva", romanizedNewa.inputMethodId());
        assertEquals("Romanized Newa input script", "Latn", romanizedNewa.sourceScript());
        assertEquals("Romanized Newa output script", "Deva", romanizedNewa.outputScript());
        assertEquals("Romanized Newa method type", "roman_phonetic", romanizedNewa.methodType());
        assertEquals("Romanized Newa engine", "alias_decoder", romanizedNewa.engineKind());
        assertEquals(
                "Romanized Newa lookup kind",
                KeyboardProfile.LookupKind.ALIAS_PREFIX,
                romanizedNewa.lookupKind()
        );
        assertEquals("Romanized Newa layout", LATIN_QWERTY_LAYOUT_ID, romanizedNewa.layoutId());
        assertEquals(
                "Romanized Newa shared Devanagari pack",
                NEPAL_BHASA_DEVA_DIRECT_ID,
                romanizedNewa.packBinding()
        );
        assertEquals(
                "direct and Romanized Newa share one exact pack identity",
                directDevanagari.packBinding(),
                romanizedNewa.packBinding()
        );
        assertTrue(
                "Romanized Newa Latin layout generated",
                KeyboardLayouts.hasLayoutForTesting(LATIN_QWERTY_LAYOUT_ID)
        );
        assertEquals(
                "Romanized Newa generated layout script",
                "Latn",
                KeyboardLayouts.inputScriptForTesting(LATIN_QWERTY_LAYOUT_ID)
        );
    }

    private static void verifyNewaProfileAndLayout(KeyboardProfile newa) {
        assertEquals("Newa profile ID", NEWA_DIRECT_ID, newa.id());
        assertEquals("Newa input method", "new-newa-direct", newa.inputMethodId());
        assertEquals("Newa input script", "Newa", newa.sourceScript());
        assertEquals("Newa output script", "Newa", newa.outputScript());
        assertEquals("Newa layout binding", NEWA_LAYOUT_ID, newa.layoutId());
        assertEquals("Newa pack binding", NEWA_DIRECT_ID, newa.packBinding());
        assertTrue("Newa layout generated", KeyboardLayouts.hasLayoutForTesting(NEWA_LAYOUT_ID));
        assertEquals(
                "Newa generated layout script",
                "Newa",
                KeyboardLayouts.inputScriptForTesting(NEWA_LAYOUT_ID)
        );

        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(newa, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(newa, true, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(newa, false, true, false);
        KeyboardLayouts.Layout numeric = KeyboardLayouts.forProfile(newa, false, false, true);
        assertEquals("Newa base rows", 4, base.rows().size());
        assertEquals("Newa shift rows", 4, shift.rows().size());
        assertEquals("Newa symbols rows", 6, symbols.rows().size());
        assertEquals("Newa numeric rows", 5, numeric.rows().size());

        assertGeneratedTextKey(
                base,
                "base.r2.k8",
                "𑑂",
                "𑑂",
                "𑑂",
                KeySpec.InputPolicy.DEFAULT
        );
        assertGeneratedTextKey(
                base,
                "base.r2.k9",
                "\u200d",
                "ZWJ",
                "Newa zero width joiner",
                KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER
        );
        assertGeneratedTextKey(
                base,
                "base.r2.k10",
                "\u200c",
                "ZWNJ",
                "Newa zero width non-joiner",
                KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER
        );

        String[] letters = {"𑐓", "𑐙", "𑐤", "𑐪", "𑐭"};
        String[] names = {
                "Newa letter NGHA",
                "Newa letter NYHA",
                "Newa letter NHA",
                "Newa letter MHA",
                "Newa letter RHA"
        };
        for (int index = 0; index < letters.length; index++) {
            assertGeneratedTextKey(
                    symbols,
                    "symbols.r4.k" + index,
                    letters[index],
                    letters[index],
                    names[index],
                    KeySpec.InputPolicy.DEFAULT
            );
        }
        KeySpec language = requiredKey(symbols, "symbols.r5.k2");
        assertEquals("Newa symbols action row", KeySpec.Action.LANGUAGE, language.action());
        assertEquals(
                "Newa language hold action",
                KeySpec.HoldAction.OPEN_LANGUAGE_PICKER,
                language.holdAction()
        );
    }

    private void verifyNewaKeyDispatch(Context context, KeyboardProfile newa) {
        RecordingInputListener listener = new RecordingInputListener(null);
        runOnMainSync(() -> {
            NepaInputView view = new NepaInputView(context, listener);
            view.setProfile(newa);
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200d",
                    KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER
            );
            assertDispatchedTextKey(
                    view,
                    listener,
                    "\u200c",
                    KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER
            );
            view.showSymbols();
            for (String letter : new String[]{"𑐓", "𑐙", "𑐤", "𑐪", "𑐭"}) {
                assertDispatchedTextKey(
                        view,
                        listener,
                        letter,
                        KeySpec.InputPolicy.DEFAULT
                );
            }
            listener.keySpec = null;
            assertTrue(
                    "dispatch Newa RHA by stable key ID",
                    view.performKeyIdForTesting("symbols.r4.k4")
            );
            assertTrue("Newa stable dispatch callback", listener.keySpec != null);
            assertEquals("Newa stable dispatch key ID", "symbols.r4.k4", listener.keySpec.keyId());
            assertEquals("Newa stable dispatch text", "𑐭", listener.keySpec.text());
        });
    }

    private static void verifyNepalBhasaConversionProfile(KeyboardProfile profile) {
        assertEquals("conversion profile ID", NEPAL_BHASA_CONVERSION_ID, profile.id());
        assertEquals("conversion input method", "new-deva-newa", profile.inputMethodId());
        assertEquals("conversion source script", "Deva", profile.sourceScript());
        assertEquals("conversion output script", "Newa", profile.outputScript());
        assertEquals("conversion method type", "script_conversion", profile.methodType());
        assertEquals("conversion engine", "converter", profile.engineKind());
        assertEquals(
                "conversion lookup kind",
                KeyboardProfile.LookupKind.CONVERSION,
                profile.lookupKind()
        );
        assertEquals(
                "conversion artifact kind",
                KeyboardProfile.ArtifactKind.NCM,
                profile.artifactKind()
        );
        assertTrue("conversion profile has no NKP binding", profile.packBinding() == null);
        assertEquals(
                "conversion map binding",
                NEPAL_BHASA_CONVERSION_ID,
                profile.conversionBinding()
        );
    }

    private static void verifyStagedNepalBhasaConversion(
            KeyboardProfile profile,
            List<ConversionMapSpec> specs
    ) throws Exception {
        ConversionMapSpec found = null;
        for (ConversionMapSpec spec : specs) {
            if (profile.id().equals(spec.profileId())) {
                if (found != null) {
                    throw new AssertionError("duplicate staged Nepal Bhasa conversion");
                }
                found = spec;
            }
        }
        assertTrue("staged Nepal Bhasa conversion exists", found != null);
        assertEquals(
                "staged Nepal Bhasa converter ID",
                profile.conversionBinding(),
                found.converterId()
        );
        try (NcmBundle bundle = NcmBundle.open(found.materialize(), found.artifactSha256())) {
            assertEquals("opened Nepal Bhasa converter ID", found.converterId(), bundle.converterId());
            assertEquals("opened Nepal Bhasa conversion language", "new", bundle.language());
            assertEquals("opened Nepal Bhasa conversion rules", 165, bundle.ruleCount());
            assertEquals("Nepal Bhasa positive conversion", "𑐩𑐡𑐸", bundle.convert("मदु"));
            assertTrue("Nepal Bhasa mixed-script no-match", bundle.convert("कa") == null);
        }
    }

    private static void verifyDhimalProfileAndLayout(
            KeyboardProfile nepali,
            KeyboardProfile dhimal
    ) {
        assertEquals("Dhimal profile ID", DHIMAL_DIRECT_ID, dhimal.id());
        assertEquals("Dhimal input method", "dhi-deva-direct", dhimal.inputMethodId());
        assertEquals("Dhimal input script", "Deva", dhimal.sourceScript());
        assertEquals("Dhimal output script", "Deva", dhimal.outputScript());
        assertEquals("Dhimal layout binding", DHIMAL_LAYOUT_ID, dhimal.layoutId());
        assertEquals("Dhimal pack binding", DHIMAL_DIRECT_ID, dhimal.packBinding());
        assertTrue("Dhimal layout generated", KeyboardLayouts.hasLayoutForTesting(DHIMAL_LAYOUT_ID));
        assertEquals(
                "Dhimal generated layout script",
                "Deva",
                KeyboardLayouts.inputScriptForTesting(DHIMAL_LAYOUT_ID)
        );

        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                dhimal,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                dhimal,
                true,
                false,
                false
        );
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(
                dhimal,
                false,
                true,
                false
        );
        KeyboardLayouts.Layout numeric = KeyboardLayouts.forProfile(
                dhimal,
                false,
                false,
                true
        );
        assertEquals("Dhimal base rows", 5, base.rows().size());
        assertEquals("Dhimal shift rows", 5, shift.rows().size());
        assertEquals("Dhimal symbols rows", 4, symbols.rows().size());
        assertEquals("Dhimal numeric rows", 5, numeric.rows().size());

        for (KeyboardLayouts.Layout layout : new KeyboardLayouts.Layout[]{base, shift}) {
            String prefix = layout == base ? "base" : "shift";
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k0",
                    "इ",
                    "इ",
                    "इ",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k1",
                    "ए",
                    "ए",
                    "ए",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k2",
                    "ः",
                    "◌ः",
                    "Devanagari sign visarga",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k3",
                    "\u200d",
                    "ZWJ",
                    "Devanagari zero width joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k4",
                    "\u200c",
                    "ZWNJ",
                    "Devanagari zero width non-joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k5",
                    "[",
                    "[",
                    "[",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k6",
                    "]",
                    "]",
                    "]",
                    KeySpec.InputPolicy.DEFAULT
            );
            KeySpec language = requiredKey(layout, prefix + ".r4.k2");
            assertEquals(prefix + " Dhimal shifted action row", KeySpec.Action.LANGUAGE, language.action());
            assertEquals(
                    prefix + " Dhimal language hold action",
                    KeySpec.HoldAction.OPEN_LANGUAGE_PICKER,
                    language.holdAction()
            );
        }

        KeyboardLayouts.Layout nepaliBase = KeyboardLayouts.forProfile(
                nepali,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout nepaliShift = KeyboardLayouts.forProfile(
                nepali,
                true,
                false,
                false
        );
        for (String text : new String[]{"इ", "ए", "ः", "\u200d", "\u200c", "[", "]"}) {
            assertTrue(
                    "Nepali basic excludes Dhimal extension key " + printable(text),
                    !nepaliBase.containsText(text) && !nepaliShift.containsText(text)
            );
        }
    }

    private static void verifySunuwarProfileAndLayout(
            KeyboardProfile nepali,
            KeyboardProfile sunuwar
    ) {
        assertEquals("Sunuwar profile ID", SUNUWAR_DIRECT_ID, sunuwar.id());
        assertEquals("Sunuwar input method", "suz-deva-direct", sunuwar.inputMethodId());
        assertEquals("Sunuwar input script", "Deva", sunuwar.sourceScript());
        assertEquals("Sunuwar output script", "Deva", sunuwar.outputScript());
        assertEquals("Sunuwar layout binding", SUNUWAR_LAYOUT_ID, sunuwar.layoutId());
        assertEquals("Sunuwar pack binding", SUNUWAR_DIRECT_ID, sunuwar.packBinding());
        assertTrue("Sunuwar extended layout generated", KeyboardLayouts.hasLayoutForTesting(SUNUWAR_LAYOUT_ID));
        assertEquals(
                "Sunuwar generated layout script",
                "Deva",
                KeyboardLayouts.inputScriptForTesting(SUNUWAR_LAYOUT_ID)
        );

        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                sunuwar,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                sunuwar,
                true,
                false,
                false
        );
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(
                sunuwar,
                false,
                true,
                false
        );
        KeyboardLayouts.Layout numeric = KeyboardLayouts.forProfile(
                sunuwar,
                false,
                false,
                true
        );
        assertEquals("Sunuwar base rows", 5, base.rows().size());
        assertEquals("Sunuwar shift rows", 5, shift.rows().size());
        assertEquals("Sunuwar symbols rows", 4, symbols.rows().size());
        assertEquals("Sunuwar numeric rows", 5, numeric.rows().size());

        for (KeyboardLayouts.Layout layout : new KeyboardLayouts.Layout[]{base, shift}) {
            String prefix = layout == base ? "base" : "shift";
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k0",
                    "ॆ",
                    "◌ॆ",
                    "Devanagari vowel sign short E",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k1",
                    "़",
                    "◌़",
                    "Devanagari sign nukta",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k2",
                    "ॽ",
                    "ॽ",
                    "Devanagari glottal stop",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k3",
                    "‘",
                    "‘",
                    "Orthographic word mark",
                    KeySpec.InputPolicy.ORTHOGRAPHIC_WORD
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k4",
                    "\u200d",
                    "ZWJ",
                    "Devanagari zero width joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k5",
                    "\u200c",
                    "ZWNJ",
                    "Devanagari zero width non-joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            KeySpec language = requiredKey(layout, prefix + ".r4.k2");
            assertEquals(prefix + " shifted action row", KeySpec.Action.LANGUAGE, language.action());
            assertEquals(
                    prefix + " language hold action",
                    KeySpec.HoldAction.OPEN_LANGUAGE_PICKER,
                    language.holdAction()
            );
        }

        KeyboardLayouts.Layout nepaliBase = KeyboardLayouts.forProfile(
                nepali,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout nepaliShift = KeyboardLayouts.forProfile(
                nepali,
                true,
                false,
                false
        );
        assertEquals("internal Nepali basic base rows unchanged", 4, nepaliBase.rows().size());
        assertEquals("internal Nepali basic shift rows unchanged", 4, nepaliShift.rows().size());
        for (String text : new String[]{"ॆ", "़", "ॽ", "‘", "\u200d", "\u200c"}) {
            assertTrue(
                    "Nepali basic excludes extension key " + printable(text),
                    !nepaliBase.containsText(text) && !nepaliShift.containsText(text)
            );
        }
    }

    private static void verifyWesternTamangProfileAndLayout(
            KeyboardProfile nepali,
            KeyboardProfile westernTamang
    ) {
        assertEquals("Western Tamang profile ID", WESTERN_TAMANG_DIRECT_ID, westernTamang.id());
        assertEquals(
                "Western Tamang input method",
                "tdg-deva-direct",
                westernTamang.inputMethodId()
        );
        assertEquals("Western Tamang input script", "Deva", westernTamang.sourceScript());
        assertEquals("Western Tamang output script", "Deva", westernTamang.outputScript());
        assertEquals(
                "Western Tamang layout binding",
                WESTERN_TAMANG_LAYOUT_ID,
                westernTamang.layoutId()
        );
        assertEquals(
                "Western Tamang pack binding",
                WESTERN_TAMANG_DIRECT_ID,
                westernTamang.packBinding()
        );
        assertTrue(
                "Western Tamang layout generated",
                KeyboardLayouts.hasLayoutForTesting(WESTERN_TAMANG_LAYOUT_ID)
        );
        assertEquals(
                "Western Tamang generated layout script",
                "Deva",
                KeyboardLayouts.inputScriptForTesting(WESTERN_TAMANG_LAYOUT_ID)
        );

        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                westernTamang,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                westernTamang,
                true,
                false,
                false
        );
        assertEquals("Western Tamang base rows", 5, base.rows().size());
        assertEquals("Western Tamang shift rows", 5, shift.rows().size());
        for (KeyboardLayouts.Layout layout : new KeyboardLayouts.Layout[]{base, shift}) {
            String prefix = layout == base ? "base" : "shift";
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k0",
                    "इ",
                    "इ",
                    "इ",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k1",
                    "ए",
                    "ए",
                    "ए",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k2",
                    "ः",
                    "◌ः",
                    "Devanagari sign visarga",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k3",
                    "़",
                    "◌़",
                    "Devanagari sign nukta",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k4",
                    "८",
                    "८",
                    "८",
                    KeySpec.InputPolicy.DEFAULT
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k5",
                    "\u200d",
                    "ZWJ",
                    "Devanagari zero width joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
            assertGeneratedTextKey(
                    layout,
                    prefix + ".r3.k6",
                    "\u200c",
                    "ZWNJ",
                    "Devanagari zero width non-joiner",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            );
        }

        KeyboardLayouts.Layout nepaliBase = KeyboardLayouts.forProfile(
                nepali,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout nepaliShift = KeyboardLayouts.forProfile(
                nepali,
                true,
                false,
                false
        );
        for (String text : new String[]{"इ", "ए", "ः", "़", "८", "\u200d", "\u200c"}) {
            assertTrue(
                    "Nepali basic excludes Western Tamang extension key " + printable(text),
                    !nepaliBase.containsText(text) && !nepaliShift.containsText(text)
            );
        }
    }

    private static void verifyLohorungProfileAndLayout(
            KeyboardProfile nepali,
            KeyboardProfile lohorung
    ) {
        assertEquals("Lohorung profile ID", LOHORUNG_DIRECT_ID, lohorung.id());
        assertEquals("Lohorung input method", "lbr-deva-direct", lohorung.inputMethodId());
        assertEquals("Lohorung input script", "Deva", lohorung.sourceScript());
        assertEquals("Lohorung output script", "Deva", lohorung.outputScript());
        assertEquals("Lohorung layout binding", LOHORUNG_LAYOUT_ID, lohorung.layoutId());
        assertEquals("Lohorung pack binding", LOHORUNG_DIRECT_ID, lohorung.packBinding());
        assertTrue(
                "Lohorung layout generated",
                KeyboardLayouts.hasLayoutForTesting(LOHORUNG_LAYOUT_ID)
        );
        assertEquals(
                "Lohorung generated layout script",
                "Deva",
                KeyboardLayouts.inputScriptForTesting(LOHORUNG_LAYOUT_ID)
        );

        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                lohorung,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                lohorung,
                true,
                false,
                false
        );
        assertEquals("Lohorung base rows", 5, base.rows().size());
        assertEquals("Lohorung shift rows", 5, shift.rows().size());
        for (KeyboardLayouts.Layout layout : new KeyboardLayouts.Layout[]{base, shift}) {
            String prefix = layout == base ? "base" : "shift";
            String[] text = {"इ", "ई", "ऎ", "ए", "ः", "ॆ", "़", "ॽ", "\u200d", "\u200c"};
            String[] labels = {"इ", "ई", "ऎ", "ए", "◌ः", "◌ॆ", "◌़", "ॽ", "ZWJ", "ZWNJ"};
            String[] descriptions = {
                    "इ",
                    "ई",
                    "ऎ",
                    "ए",
                    "Devanagari sign visarga",
                    "Devanagari vowel sign short E",
                    "Devanagari sign nukta",
                    "Devanagari glottal stop",
                    "Devanagari zero width joiner",
                    "Lohorung conjunct or terminal zero width non-joiner"
            };
            for (int index = 0; index < text.length; index++) {
                KeySpec.InputPolicy policy = KeySpec.InputPolicy.DEFAULT;
                if (index == 8) {
                    policy = KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER;
                } else if (index == 9) {
                    policy = KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ;
                }
                assertGeneratedTextKey(
                        layout,
                        prefix + ".r3.k" + index,
                        text[index],
                        labels[index],
                        descriptions[index],
                        policy
                );
            }
            KeySpec language = requiredKey(layout, prefix + ".r4.k2");
            assertEquals(prefix + " Lohorung language action", KeySpec.Action.LANGUAGE, language.action());
            assertEquals(
                    prefix + " Lohorung language hold action",
                    KeySpec.HoldAction.OPEN_LANGUAGE_PICKER,
                    language.holdAction()
            );
        }

        KeyboardLayouts.Layout nepaliBase = KeyboardLayouts.forProfile(
                nepali,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout nepaliShift = KeyboardLayouts.forProfile(
                nepali,
                true,
                false,
                false
        );
        for (String text : new String[]{"इ", "ई", "ऎ", "ए", "ः", "ॆ", "़", "ॽ", "\u200d", "\u200c"}) {
            assertTrue(
                    "Nepali basic excludes Lohorung extension key " + printable(text),
                    !nepaliBase.containsText(text) && !nepaliShift.containsText(text)
            );
        }
    }

    private static void verifyYakkhaProfileAndLayout(
            KeyboardProfile nepali,
            KeyboardProfile yakkha
    ) {
        assertEquals("Yakkha profile ID", YAKKHA_DIRECT_ID, yakkha.id());
        assertEquals("Yakkha input method", "ybh-deva-direct", yakkha.inputMethodId());
        assertEquals("Yakkha input script", "Deva", yakkha.sourceScript());
        assertEquals("Yakkha output script", "Deva", yakkha.outputScript());
        assertEquals("Yakkha layout binding", YAKKHA_LAYOUT_ID, yakkha.layoutId());
        assertEquals("Yakkha pack binding", YAKKHA_DIRECT_ID, yakkha.packBinding());
        assertTrue("Yakkha layout generated", KeyboardLayouts.hasLayoutForTesting(YAKKHA_LAYOUT_ID));
        assertEquals(
                "Yakkha generated layout script",
                "Deva",
                KeyboardLayouts.inputScriptForTesting(YAKKHA_LAYOUT_ID)
        );

        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(yakkha, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(yakkha, true, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(yakkha, false, true, false);
        assertEquals("Yakkha base rows", 5, base.rows().size());
        assertEquals("Yakkha shift rows", 5, shift.rows().size());
        assertEquals("Yakkha symbols rows", 4, symbols.rows().size());

        for (KeyboardLayouts.Layout layout : new KeyboardLayouts.Layout[]{base, shift}) {
            String prefix = layout == base ? "base" : "shift";
            String[] text = {"इ", "ए", "ॽ", "\u200d", "\u200c"};
            String[] labels = {"इ", "ए", "ॽ", "ZWJ", "ZWNJ"};
            String[] descriptions = {
                    "इ",
                    "ए",
                    "Devanagari glottal stop",
                    "Devanagari zero width joiner",
                    "Yakkha conjunct or terminal zero width non-joiner"
            };
            KeySpec.InputPolicy[] policies = {
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ
            };
            for (int index = 0; index < text.length; index++) {
                assertGeneratedTextKey(
                        layout,
                        prefix + ".r3.k" + index,
                        text[index],
                        labels[index],
                        descriptions[index],
                        policies[index]
                );
            }
        }

        assertGeneratedTextKey(
                symbols,
                "symbols.r1.k5",
                "-",
                "-",
                "Hyphen within Yakkha word",
                KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION
        );
        assertGeneratedTextKey(
                symbols,
                "symbols.r2.k7",
                "/",
                "/",
                "Slash within Yakkha word",
                KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION
        );
        assertGeneratedTextKey(
                symbols,
                "symbols.r2.k9",
                "\\",
                "\\",
                "Backslash within Yakkha word",
                KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION
        );

        KeyboardLayouts.Layout nepaliBase = KeyboardLayouts.forProfile(nepali, false, false, false);
        KeyboardLayouts.Layout nepaliShift = KeyboardLayouts.forProfile(nepali, true, false, false);
        KeyboardLayouts.Layout nepaliSymbols = KeyboardLayouts.forProfile(nepali, false, true, false);
        for (String text : new String[]{"इ", "ए", "ॽ", "\u200d", "\u200c"}) {
            assertTrue(
                    "Nepali basic excludes Yakkha extension key " + printable(text),
                    !nepaliBase.containsText(text) && !nepaliShift.containsText(text)
            );
        }
        assertEquals(
                "Nepali hyphen remains ordinary punctuation",
                KeySpec.InputPolicy.DEFAULT,
                requiredKey(nepaliSymbols, "symbols.r1.k5").inputPolicy()
        );
        assertEquals(
                "Nepali slash remains ordinary punctuation",
                KeySpec.InputPolicy.DEFAULT,
                requiredKey(nepaliSymbols, "symbols.r2.k7").inputPolicy()
        );
        assertTrue("Nepali symbols exclude backslash", !nepaliSymbols.containsText("\\"));
    }

    private static void verifyKhalingProfileAndLayout(
            KeyboardProfile nepali,
            KeyboardProfile khaling
    ) {
        assertEquals("Khaling profile ID", KHALING_DIRECT_ID, khaling.id());
        assertEquals("Khaling input method", "klr-deva-direct", khaling.inputMethodId());
        assertEquals("Khaling input script", "Deva", khaling.sourceScript());
        assertEquals("Khaling output script", "Deva", khaling.outputScript());
        assertEquals("Khaling layout binding", KHALING_LAYOUT_ID, khaling.layoutId());
        assertEquals("Khaling pack binding", KHALING_DIRECT_ID, khaling.packBinding());
        assertTrue(
                "Khaling layout generated",
                KeyboardLayouts.hasLayoutForTesting(KHALING_LAYOUT_ID)
        );
        assertEquals(
                "Khaling generated layout script",
                "Deva",
                KeyboardLayouts.inputScriptForTesting(KHALING_LAYOUT_ID)
        );

        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(khaling, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(khaling, true, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(khaling, false, true, false);
        assertEquals("Khaling base rows", 5, base.rows().size());
        assertEquals("Khaling shift rows", 5, shift.rows().size());
        assertEquals("Khaling symbols rows", 4, symbols.rows().size());

        for (KeyboardLayouts.Layout layout : new KeyboardLayouts.Layout[]{base, shift}) {
            String prefix = layout == base ? "base" : "shift";
            String[] text = {"इ", "ई", "ए", "़", "\u200d", "\u200c"};
            String[] labels = {"इ", "ई", "ए", "◌़", "ZWJ", "ZWNJ"};
            String[] descriptions = {
                    "इ",
                    "ई",
                    "ए",
                    "Devanagari sign nukta",
                    "Khaling conjunct zero width joiner",
                    "Khaling conjunct zero width non-joiner"
            };
            KeySpec.InputPolicy[] policies = {
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
            };
            for (int index = 0; index < text.length; index++) {
                assertGeneratedTextKey(
                        layout,
                        prefix + ".r3.k" + index,
                        text[index],
                        labels[index],
                        descriptions[index],
                        policies[index]
                );
            }
        }

        assertGeneratedTextKey(
                symbols,
                "symbols.r1.k5",
                "-",
                "-",
                "Hyphen within Khaling word",
                KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION
        );

        KeyboardLayouts.Layout nepaliBase = KeyboardLayouts.forProfile(nepali, false, false, false);
        KeyboardLayouts.Layout nepaliShift = KeyboardLayouts.forProfile(nepali, true, false, false);
        KeyboardLayouts.Layout nepaliSymbols = KeyboardLayouts.forProfile(nepali, false, true, false);
        for (String text : new String[]{"इ", "ई", "ए", "़", "\u200d", "\u200c"}) {
            assertTrue(
                    "Nepali basic excludes Khaling extension key " + printable(text),
                    !nepaliBase.containsText(text) && !nepaliShift.containsText(text)
            );
        }
        assertEquals(
                "Nepali hyphen remains ordinary punctuation for Khaling isolation",
                KeySpec.InputPolicy.DEFAULT,
                requiredKey(nepaliSymbols, "symbols.r1.k5").inputPolicy()
        );
    }

    private static void verifyDumiProfileAndLayout(
            KeyboardProfile nepali,
            KeyboardProfile dumi
    ) {
        assertEquals("Dumi profile ID", DUMI_DIRECT_ID, dumi.id());
        assertEquals("Dumi input method", "dus-deva-direct", dumi.inputMethodId());
        assertEquals("Dumi input script", "Deva", dumi.sourceScript());
        assertEquals("Dumi output script", "Deva", dumi.outputScript());
        assertEquals("Dumi layout binding", DUMI_LAYOUT_ID, dumi.layoutId());
        assertEquals("Dumi pack binding", DUMI_DIRECT_ID, dumi.packBinding());
        assertTrue(
                "Dumi layout generated",
                KeyboardLayouts.hasLayoutForTesting(DUMI_LAYOUT_ID)
        );
        assertEquals(
                "Dumi generated layout script",
                "Deva",
                KeyboardLayouts.inputScriptForTesting(DUMI_LAYOUT_ID)
        );

        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(dumi, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(dumi, true, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(dumi, false, true, false);
        assertEquals("Dumi base rows", 5, base.rows().size());
        assertEquals("Dumi shift rows", 5, shift.rows().size());
        assertEquals("Dumi symbols rows", 4, symbols.rows().size());

        for (KeyboardLayouts.Layout layout : new KeyboardLayouts.Layout[]{base, shift}) {
            String prefix = layout == base ? "base" : "shift";
            String[] text = {"इ", "ई", "ए", "़", "\u200d", "\u200c", "ः", "ॽ"};
            String[] labels = {"इ", "ई", "ए", "◌़", "ZWJ", "ZWNJ", "◌ः", "ॽ"};
            String[] descriptions = {
                    "इ",
                    "ई",
                    "ए",
                    "Devanagari sign nukta",
                    "Dumi conjunct zero width joiner",
                    "Dumi conjunct zero width non-joiner",
                    "Devanagari sign visarga",
                    "Devanagari letter glottal stop"
            };
            KeySpec.InputPolicy[] policies = {
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    KeySpec.InputPolicy.DEFAULT,
                    KeySpec.InputPolicy.DEFAULT
            };
            for (int index = 0; index < text.length; index++) {
                assertGeneratedTextKey(
                        layout,
                        prefix + ".r3.k" + index,
                        text[index],
                        labels[index],
                        descriptions[index],
                        policies[index]
                );
            }
        }

        assertGeneratedTextKey(
                symbols,
                "symbols.r1.k5",
                "-",
                "-",
                "Hyphen within Dumi word",
                KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION
        );
        assertGeneratedTextKey(
                symbols,
                "symbols.r2.k3",
                ":",
                ":",
                "Colon within Dumi word",
                KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION
        );

        KeyboardLayouts.Layout nepaliBase = KeyboardLayouts.forProfile(nepali, false, false, false);
        KeyboardLayouts.Layout nepaliShift = KeyboardLayouts.forProfile(nepali, true, false, false);
        KeyboardLayouts.Layout nepaliSymbols = KeyboardLayouts.forProfile(nepali, false, true, false);
        for (String text : new String[]{"इ", "ई", "ए", "़", "\u200d", "\u200c", "ः", "ॽ"}) {
            assertTrue(
                    "Nepali basic excludes Dumi extension key " + printable(text),
                    !nepaliBase.containsText(text) && !nepaliShift.containsText(text)
            );
        }
        assertEquals(
                "Nepali hyphen remains ordinary punctuation for Dumi isolation",
                KeySpec.InputPolicy.DEFAULT,
                requiredKey(nepaliSymbols, "symbols.r1.k5").inputPolicy()
        );
        assertEquals(
                "Nepali colon remains ordinary punctuation for Dumi isolation",
                KeySpec.InputPolicy.DEFAULT,
                requiredKey(nepaliSymbols, "symbols.r2.k3").inputPolicy()
        );
    }

    private static void assertGeneratedTextKey(
            KeyboardLayouts.Layout layout,
            String keyId,
            String text,
            String label,
            String contentDescription,
            KeySpec.InputPolicy inputPolicy
    ) {
        KeySpec key = requiredKey(layout, keyId);
        assertEquals(keyId + " stable ID", keyId, key.keyId());
        assertEquals(keyId + " action", KeySpec.Action.TEXT, key.action());
        assertEquals(keyId + " text", text, key.text());
        assertEquals(keyId + " visible label", label, key.label());
        assertEquals(keyId + " content description", contentDescription, key.contentDescription());
        assertEquals(keyId + " input policy", inputPolicy, key.inputPolicy());
        assertEquals(keyId + " width", 100, key.widthUnits());
        assertEquals(keyId + " hold action", null, key.holdAction());
    }

    private static void verifySunuwarGeneratedInputPolicies(KeyboardProfile sunuwar) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                sunuwar,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                sunuwar,
                true,
                false,
                false
        );
        KeySpec orthographicWord = requiredKey(base, "base.r3.k3");
        KeySpec zwj = requiredKey(base, "base.r3.k4");
        NoOpSuggestionEngine engine = new NoOpSuggestionEngine();
        try {
            RecordingTextSink orthographicSink = new RecordingTextSink();
            ComposingSession orthographic = new ComposingSession(engine);
            orthographic.start(sunuwar, true, false, orthographicSink);
            appendKey(orthographic, orthographicWord, orthographicSink);
            assertEquals("leading Sunuwar U+2018 composes", "‘", orthographic.composingText());
            appendKey(orthographic, requiredKey(shift, "shift.r1.k0"), orthographicSink);
            assertEquals("Sunuwar U+2018 word prefix", "‘आ", orthographic.composingText());

            RecordingTextSink joinerSink = new RecordingTextSink();
            ComposingSession conjunct = new ComposingSession(engine);
            conjunct.start(sunuwar, true, false, joinerSink);
            appendKey(conjunct, requiredKey(base, "base.r1.k7"), joinerSink);
            appendKey(conjunct, requiredKey(base, "base.r2.k9"), joinerSink);
            int beforeJoiner = joinerSink.editorCalls.size();
            appendKey(conjunct, zwj, joinerSink);
            assertEquals(
                    "generated Sunuwar ZWJ remains buffered",
                    beforeJoiner,
                    joinerSink.editorCalls.size()
            );
            appendKey(conjunct, requiredKey(base, "base.r2.k0"), joinerSink);
            assertEquals(
                    "generated Sunuwar ZWJ continuation is one editor update",
                    beforeJoiner + 1,
                    joinerSink.editorCalls.size()
            );
            assertEquals("generated Sunuwar exact ZWJ conjunct", "क्\u200dष", joinerSink.text());
            assertTrue(
                    "generated Sunuwar ZWJ continuation is atomic",
                    joinerSink.editorCalls.get(joinerSink.editorCalls.size() - 1)
                            .endsWith("\u200dष")
            );
            assertNoEditorCallEndsInJoiner("generated Sunuwar ZWJ", joinerSink);
        } finally {
            engine.close();
        }
    }

    private static void verifyDhimalGeneratedInputPolicies(KeyboardProfile dhimal) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                dhimal,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                dhimal,
                true,
                false,
                false
        );
        KeySpec zwnj = requiredKey(base, "base.r3.k4");
        NoOpSuggestionEngine engine = new NoOpSuggestionEngine();
        try {
            RecordingTextSink sink = new RecordingTextSink();
            ComposingSession session = new ComposingSession(engine);
            session.start(dhimal, true, false, sink);
            appendKey(session, requiredKey(base, "base.r3.k0"), sink);
            appendKey(session, requiredKey(shift, "shift.r1.k5"), sink);
            appendKey(session, requiredKey(base, "base.r2.k9"), sink);
            int beforeJoiner = sink.editorCalls.size();
            appendKey(session, zwnj, sink);
            assertEquals(
                    "generated Dhimal ZWNJ remains buffered",
                    beforeJoiner,
                    sink.editorCalls.size()
            );
            appendKey(session, requiredKey(shift, "shift.r0.k4"), sink);
            assertEquals(
                    "generated Dhimal ZWNJ continuation is one editor update",
                    beforeJoiner + 1,
                    sink.editorCalls.size()
            );
            assertEquals("generated Dhimal exact ZWNJ query", "इअ्‌थ", sink.text());
            assertTrue(
                    "generated Dhimal ZWNJ continuation is atomic",
                    sink.editorCalls.get(sink.editorCalls.size() - 1).endsWith("\u200cथ")
            );
            assertNoEditorCallEndsInJoiner("generated Dhimal ZWNJ", sink);
        } finally {
            engine.close();
        }
    }

    private static void verifyWesternTamangGeneratedInputPolicies(
            KeyboardProfile westernTamang
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                westernTamang,
                false,
                false,
                false
        );
        NoOpSuggestionEngine engine = new NoOpSuggestionEngine();
        try {
            assertAtomicWesternTamangJoiner(
                    westernTamang,
                    base,
                    requiredKey(base, "base.r3.k5"),
                    "\u200d",
                    "ZWJ",
                    engine
            );
            assertAtomicWesternTamangJoiner(
                    westernTamang,
                    base,
                    requiredKey(base, "base.r3.k6"),
                    "\u200c",
                    "ZWNJ",
                    engine
            );
        } finally {
            engine.close();
        }
    }

    private static void assertAtomicWesternTamangJoiner(
            KeyboardProfile westernTamang,
            KeyboardLayouts.Layout base,
            KeySpec joiner,
            String joinerText,
            String label,
            SuggestionEngine engine
    ) {
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(westernTamang, true, false, sink);
        appendKey(session, requiredKey(base, "base.r1.k7"), sink);
        appendKey(session, requiredKey(base, "base.r2.k9"), sink);
        int beforeJoiner = sink.editorCalls.size();
        appendKey(session, joiner, sink);
        assertEquals(
                "generated Western Tamang " + label + " remains buffered",
                beforeJoiner,
                sink.editorCalls.size()
        );
        appendKey(session, requiredKey(base, "base.r0.k5"), sink);
        assertEquals(
                "generated Western Tamang " + label + " continuation is one editor update",
                beforeJoiner + 1,
                sink.editorCalls.size()
        );
        assertEquals(
                "generated Western Tamang exact " + label + " sequence",
                "क्" + joinerText + "य",
                sink.text()
        );
        assertTrue(
                "generated Western Tamang " + label + " continuation is atomic",
                sink.editorCalls.get(sink.editorCalls.size() - 1).endsWith(joinerText + "य")
        );
        assertNoEditorCallEndsInJoiner("generated Western Tamang " + label, sink);
    }

    private static void verifyLohorungGeneratedInputPolicies(
            KeyboardProfile lohorung,
            KeyboardProfile nepali
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                lohorung,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                lohorung,
                true,
                false,
                false
        );
        KeySpec zwj = requiredKey(base, "base.r3.k8");
        KeySpec terminalZwnj = requiredKey(base, "base.r3.k9");
        NoOpSuggestionEngine engine = new NoOpSuggestionEngine();
        try {
            RecordingTextSink zwjSink = new RecordingTextSink();
            ComposingSession zwjSession = new ComposingSession(engine);
            zwjSession.start(lohorung, true, false, zwjSink);
            appendKey(zwjSession, requiredKey(base, "base.r1.k7"), zwjSink);
            appendKey(zwjSession, requiredKey(base, "base.r2.k9"), zwjSink);
            int beforeZwj = zwjSink.editorCalls.size();
            appendKey(zwjSession, zwj, zwjSink);
            assertEquals("Lohorung ZWJ remains buffered", beforeZwj, zwjSink.editorCalls.size());
            appendKey(zwjSession, requiredKey(base, "base.r0.k5"), zwjSink);
            assertEquals("Lohorung ZWJ conjunct", "क्\u200dय", zwjSink.text());
            assertNoEditorCallEndsInJoiner("Lohorung internal ZWJ", zwjSink);

            RecordingTextSink conjunctSink = new RecordingTextSink();
            ComposingSession conjunct = new ComposingSession(engine);
            conjunct.start(lohorung, true, false, conjunctSink);
            appendLohorungTerminalStem(conjunct, base, shift, conjunctSink);
            int beforeZwnj = conjunctSink.editorCalls.size();
            appendKey(conjunct, terminalZwnj, conjunctSink);
            assertEquals(
                    "Lohorung terminal-capable ZWNJ remains buffered",
                    beforeZwnj,
                    conjunctSink.editorCalls.size()
            );
            appendKey(conjunct, requiredKey(base, "base.r1.k7"), conjunctSink);
            assertEquals("Lohorung internal ZWNJ continuation", "एकङ्\u200cक", conjunctSink.text());
            assertTrue(
                    "Lohorung internal ZWNJ is atomic with its letter",
                    conjunctSink.editorCalls.get(conjunctSink.editorCalls.size() - 1)
                            .endsWith("\u200cक")
            );

            RecordingTextSink boundarySink = new RecordingTextSink();
            ComposingSession boundary = new ComposingSession(engine);
            boundary.start(lohorung, true, false, boundarySink);
            appendLohorungTerminalStem(boundary, base, shift, boundarySink);
            int beforeTerminal = boundarySink.editorCalls.size();
            appendKey(boundary, terminalZwnj, boundarySink);
            assertEquals(
                    "Lohorung terminal ZWNJ has no isolated editor call",
                    beforeTerminal,
                    boundarySink.editorCalls.size()
            );
            boundary.appendText(" ", KeySpec.InputPolicy.DEFAULT, boundarySink);
            assertEquals("Lohorung terminal ZWNJ boundary text", "एकङ्\u200c ", boundarySink.text());
            assertTrue(
                    "Lohorung terminal ZWNJ commits with the whole token",
                    boundarySink.editorCalls.contains("commit:एकङ्\u200c")
            );
            assertNoIsolatedJoinerCall("Lohorung terminal ZWNJ boundary", boundarySink);

            RecordingTextSink deleteSink = new RecordingTextSink();
            ComposingSession deleting = new ComposingSession(engine);
            deleting.start(lohorung, true, false, deleteSink);
            appendLohorungTerminalStem(deleting, base, shift, deleteSink);
            int beforeDelete = deleteSink.editorCalls.size();
            appendKey(deleting, terminalZwnj, deleteSink);
            deleting.delete(deleteSink);
            assertEquals("delete clears pending Lohorung ZWNJ", beforeDelete, deleteSink.editorCalls.size());
            assertEquals("delete preserves the visible Lohorung stem", "एकङ्", deleteSink.text());

            RecordingTextSink invalidSink = new RecordingTextSink();
            ComposingSession invalid = new ComposingSession(engine);
            invalid.start(lohorung, true, false, invalidSink);
            appendLohorungTerminalStem(invalid, base, shift, invalidSink);
            appendKey(invalid, terminalZwnj, invalidSink);
            appendKey(invalid, requiredKey(base, "base.r3.k5"), invalidSink);
            assertEquals("invalid mark continuation clears terminal ZWNJ", "एकङ्ॆ", invalidSink.text());

            RecordingTextSink privateSink = new RecordingTextSink();
            ComposingSession privateSession = new ComposingSession(engine);
            privateSession.start(lohorung, true, true, privateSink);
            appendLohorungTerminalStem(privateSession, base, shift, privateSink);
            appendKey(privateSession, terminalZwnj, privateSink);
            privateSession.appendText(" ", KeySpec.InputPolicy.DEFAULT, privateSink);
            assertEquals("private field drops terminal ZWNJ", "एकङ् ", privateSink.text());

            RecordingTextSink switchSink = new RecordingTextSink();
            ComposingSession switching = new ComposingSession(engine);
            switching.start(lohorung, true, false, switchSink);
            appendLohorungTerminalStem(switching, base, shift, switchSink);
            appendKey(switching, terminalZwnj, switchSink);
            switching.switchProfile(nepali, true, false, switchSink);
            assertEquals("profile switch clears terminal ZWNJ", "एकङ्", switchSink.text());

            RecordingTextSink terminalZwjSink = new RecordingTextSink();
            ComposingSession terminalZwj = new ComposingSession(engine);
            terminalZwj.start(lohorung, true, false, terminalZwjSink);
            appendLohorungTerminalStem(terminalZwj, base, shift, terminalZwjSink);
            appendKey(terminalZwj, zwj, terminalZwjSink);
            terminalZwj.appendText(" ", KeySpec.InputPolicy.DEFAULT, terminalZwjSink);
            assertEquals("terminal ZWJ is not emitted", "एकङ् ", terminalZwjSink.text());
            assertNoIsolatedJoinerCall("Lohorung terminal ZWJ", terminalZwjSink);
        } finally {
            engine.close();
        }
    }

    private static void appendLohorungTerminalStem(
            ComposingSession session,
            KeyboardLayouts.Layout base,
            KeyboardLayouts.Layout shift,
            TextSink sink
    ) {
        appendKey(session, requiredKey(base, "base.r3.k3"), sink);
        appendKey(session, requiredKey(base, "base.r1.k7"), sink);
        appendKey(session, requiredKey(shift, "shift.r2.k7"), sink);
        appendKey(session, requiredKey(base, "base.r2.k9"), sink);
    }

    private static void verifyYakkhaGeneratedInputPolicies(KeyboardProfile yakkha) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(yakkha, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(yakkha, true, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(yakkha, false, true, false);
        KeySpec[] punctuation = {
                requiredKey(symbols, "symbols.r1.k5"),
                requiredKey(symbols, "symbols.r2.k7"),
                requiredKey(symbols, "symbols.r2.k9")
        };
        NoOpSuggestionEngine engine = new NoOpSuggestionEngine();
        try {
            for (KeySpec key : punctuation) {
                RecordingTextSink joinedSink = new RecordingTextSink();
                ComposingSession joined = new ComposingSession(engine);
                joined.start(yakkha, true, false, joinedSink);
                appendKey(joined, requiredKey(base, "base.r0.k9"), joinedSink);
                appendKey(joined, key, joinedSink);
                appendKey(joined, requiredKey(base, "base.r1.k7"), joinedSink);
                assertEquals(
                        "Yakkha intra-word punctuation composes " + key.text(),
                        "प" + key.text() + "क",
                        joined.composingText()
                );

                RecordingTextSink leadingSink = new RecordingTextSink();
                ComposingSession leading = new ComposingSession(engine);
                leading.start(yakkha, true, false, leadingSink);
                appendKey(leading, key, leadingSink);
                assertEquals(
                        "Yakkha punctuation does not start composition " + key.text(),
                        "",
                        leading.composingText()
                );
                assertEquals(
                        "Yakkha leading punctuation remains typeable " + key.text(),
                        key.text(),
                        leadingSink.text()
                );
            }

            RecordingTextSink repeatedSink = new RecordingTextSink();
            ComposingSession repeated = new ComposingSession(engine);
            repeated.start(yakkha, true, false, repeatedSink);
            appendKey(repeated, requiredKey(base, "base.r0.k9"), repeatedSink);
            appendKey(repeated, punctuation[0], repeatedSink);
            appendKey(repeated, punctuation[1], repeatedSink);
            assertEquals("second Yakkha punctuation closes the word", "", repeated.composingText());
            assertEquals("repeated Yakkha punctuation is literal", "प-/", repeatedSink.text());

            RecordingTextSink terminalSink = new RecordingTextSink();
            ComposingSession terminal = new ComposingSession(engine);
            terminal.start(yakkha, true, false, terminalSink);
            appendYakkhaTerminalStem(terminal, base, shift, terminalSink);
            int beforeJoiner = terminalSink.editorCalls.size();
            appendKey(terminal, requiredKey(base, "base.r3.k4"), terminalSink);
            assertEquals(
                    "Yakkha terminal ZWNJ remains buffered",
                    beforeJoiner,
                    terminalSink.editorCalls.size()
            );
            terminal.appendText(" ", KeySpec.InputPolicy.DEFAULT, terminalSink);
            assertEquals("Yakkha terminal ZWNJ boundary", "टाङ्\u200c ", terminalSink.text());
            assertNoIsolatedJoinerCall("Yakkha terminal ZWNJ boundary", terminalSink);
        } finally {
            engine.close();
        }
    }

    private static void verifyKhalingGeneratedInputPolicies(KeyboardProfile khaling) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(khaling, false, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(khaling, false, true, false);
        NoOpSuggestionEngine engine = new NoOpSuggestionEngine();
        try {
            String[] joinerIds = {"base.r3.k4", "base.r3.k5"};
            String[] joiners = {"\u200d", "\u200c"};
            String[] labels = {"ZWJ", "ZWNJ"};
            for (int index = 0; index < joinerIds.length; index++) {
                RecordingTextSink sink = new RecordingTextSink();
                ComposingSession session = new ComposingSession(engine);
                session.start(khaling, true, false, sink);
                appendKey(session, requiredKey(base, "base.r1.k7"), sink);
                appendKey(session, requiredKey(base, "base.r2.k9"), sink);
                int beforeJoiner = sink.editorCalls.size();
                appendKey(session, requiredKey(base, joinerIds[index]), sink);
                assertEquals(
                        "generated Khaling " + labels[index] + " remains buffered",
                        beforeJoiner,
                        sink.editorCalls.size()
                );
                appendKey(session, requiredKey(base, "base.r0.k5"), sink);
                assertEquals(
                        "generated Khaling exact " + labels[index] + " sequence",
                        "क्" + joiners[index] + "य",
                        sink.text()
                );
                assertTrue(
                        "generated Khaling " + labels[index] + " continuation is atomic",
                        sink.editorCalls.get(sink.editorCalls.size() - 1)
                                .endsWith(joiners[index] + "य")
                );
                assertNoEditorCallEndsInJoiner("generated Khaling " + labels[index], sink);
            }

            RecordingTextSink hyphenSink = new RecordingTextSink();
            ComposingSession hyphen = new ComposingSession(engine);
            hyphen.start(khaling, true, false, hyphenSink);
            appendKey(hyphen, requiredKey(base, "base.r0.k9"), hyphenSink);
            appendKey(hyphen, requiredKey(symbols, "symbols.r1.k5"), hyphenSink);
            appendKey(hyphen, requiredKey(base, "base.r1.k7"), hyphenSink);
            assertEquals("Khaling intra-word hyphen composes", "प-क", hyphen.composingText());

            RecordingTextSink leadingSink = new RecordingTextSink();
            ComposingSession leading = new ComposingSession(engine);
            leading.start(khaling, true, false, leadingSink);
            appendKey(leading, requiredKey(symbols, "symbols.r1.k5"), leadingSink);
            assertEquals("Khaling leading hyphen does not compose", "", leading.composingText());
            assertEquals("Khaling leading hyphen remains typeable", "-", leadingSink.text());
        } finally {
            engine.close();
        }
    }

    private static void verifyDumiGeneratedInputPolicies(KeyboardProfile dumi) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(dumi, false, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(dumi, false, true, false);
        NoOpSuggestionEngine engine = new NoOpSuggestionEngine();
        try {
            String[] joinerIds = {"base.r3.k4", "base.r3.k5"};
            String[] joiners = {"\u200d", "\u200c"};
            String[] labels = {"ZWJ", "ZWNJ"};
            for (int index = 0; index < joinerIds.length; index++) {
                RecordingTextSink sink = new RecordingTextSink();
                ComposingSession session = new ComposingSession(engine);
                session.start(dumi, true, false, sink);
                appendKey(session, requiredKey(base, "base.r1.k7"), sink);
                appendKey(session, requiredKey(base, "base.r2.k9"), sink);
                int beforeJoiner = sink.editorCalls.size();
                appendKey(session, requiredKey(base, joinerIds[index]), sink);
                assertEquals(
                        "generated Dumi " + labels[index] + " remains buffered",
                        beforeJoiner,
                        sink.editorCalls.size()
                );
                appendKey(session, requiredKey(base, "base.r0.k5"), sink);
                assertEquals(
                        "generated Dumi exact " + labels[index] + " sequence",
                        "क्" + joiners[index] + "य",
                        sink.text()
                );
                assertTrue(
                        "generated Dumi " + labels[index] + " continuation is atomic",
                        sink.editorCalls.get(sink.editorCalls.size() - 1)
                                .endsWith(joiners[index] + "य")
                );
                assertNoEditorCallEndsInJoiner("generated Dumi " + labels[index], sink);
            }

            String[] punctuationIds = {"symbols.r1.k5", "symbols.r2.k3"};
            String[] punctuation = {"-", ":"};
            String[] punctuationLabels = {"hyphen", "colon"};
            for (int index = 0; index < punctuationIds.length; index++) {
                RecordingTextSink sink = new RecordingTextSink();
                ComposingSession session = new ComposingSession(engine);
                session.start(dumi, true, false, sink);
                appendKey(session, requiredKey(base, "base.r0.k9"), sink);
                appendKey(session, requiredKey(symbols, punctuationIds[index]), sink);
                appendKey(session, requiredKey(base, "base.r1.k7"), sink);
                assertEquals(
                        "Dumi intra-word " + punctuationLabels[index] + " composes",
                        "प" + punctuation[index] + "क",
                        session.composingText()
                );

                RecordingTextSink leadingSink = new RecordingTextSink();
                ComposingSession leading = new ComposingSession(engine);
                leading.start(dumi, true, false, leadingSink);
                appendKey(leading, requiredKey(symbols, punctuationIds[index]), leadingSink);
                assertEquals(
                        "Dumi leading " + punctuationLabels[index] + " does not compose",
                        "",
                        leading.composingText()
                );
                assertEquals(
                        "Dumi leading " + punctuationLabels[index] + " remains typeable",
                        punctuation[index],
                        leadingSink.text()
                );
            }
        } finally {
            engine.close();
        }
    }

    private static void appendYakkhaTerminalStem(
            ComposingSession session,
            KeyboardLayouts.Layout base,
            KeyboardLayouts.Layout shift,
            TextSink sink
    ) {
        appendKey(session, requiredKey(base, "base.r0.k0"), sink);
        appendKey(session, requiredKey(base, "base.r1.k0"), sink);
        appendKey(session, requiredKey(shift, "shift.r2.k7"), sink);
        appendKey(session, requiredKey(base, "base.r2.k9"), sink);
    }

    private static void verifyNewaPackInput(
            KeyboardProfile newa,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                newa,
                false,
                false,
                false
        );
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(newa, true, false, sink);
        appendKey(session, requiredKey(base, "base.r2.k5"), sink);
        appendKey(session, requiredKey(base, "base.r0.k2"), sink);
        assertSessionQuery(
                "Newa",
                session,
                vector.query,
                vector.expectedSurface
        );
    }

    private static void verifyNepalBhasaConversionInput(
            KeyboardProfile profile,
            SuggestionEngine engine
    ) {
        SuggestionActivation activation = engine.activate(profile);
        List<String> suggestions = awaitSuggestions(engine, activation, profile, "मदु");
        assertEquals("Nepal Bhasa converted candidate", "𑐩𑐡𑐸", suggestions.get(0));
        assertEquals(
                "Nepal Bhasa conversion literal tail",
                "मदु",
                suggestions.get(suggestions.size() - 1)
        );
        assertEquals(
                "Nepal Bhasa conversion no-match",
                SuggestionSnapshot.Status.NO_MATCH,
                engine.suggest(
                        activation,
                        new SuggestionQuery(profile, "कa", false)
                ).status()
        );
    }

    private static void verifyRomanizedNewaPackInput(
            KeyboardProfile romanizedNewa,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                romanizedNewa,
                false,
                false,
                false
        );
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(romanizedNewa, true, false, sink);
        appendKey(session, requiredKey(base, "base.r2.k6"), sink);
        appendKey(session, requiredKey(base, "base.r1.k0"), sink);
        appendKey(session, requiredKey(base, "base.r1.k2"), sink);
        appendKey(session, requiredKey(base, "base.r0.k6"), sink);
        assertSessionQuery(
                "Romanized Newa",
                session,
                vector.query,
                vector.expectedSurface
        );
    }

    private static void verifyDhimalPackInput(
            KeyboardProfile dhimal,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                dhimal,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                dhimal,
                true,
                false,
                false
        );
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(dhimal, true, false, sink);
        appendKey(session, requiredKey(base, "base.r3.k0"), sink);
        appendKey(session, requiredKey(shift, "shift.r1.k5"), sink);
        appendKey(session, requiredKey(base, "base.r2.k9"), sink);
        appendKey(session, requiredKey(base, "base.r3.k4"), sink);
        appendKey(session, requiredKey(shift, "shift.r0.k4"), sink);
        assertSessionQuery(
                "Dhimal",
                session,
                vector.query,
                vector.expectedSurface
        );
    }

    private static void verifySunuwarPackInput(
            KeyboardProfile sunuwar,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                sunuwar,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                sunuwar,
                true,
                false,
                false
        );
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(sunuwar, true, false, sink);
        appendKey(session, requiredKey(base, "base.r3.k3"), sink);
        appendKey(session, requiredKey(shift, "shift.r1.k0"), sink);
        assertSessionQuery(
                "Sunuwar",
                session,
                vector.query,
                vector.expectedSurface
        );
    }

    private static void verifyWesternTamangPackInput(
            KeyboardProfile westernTamang,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                westernTamang,
                false,
                false,
                false
        );
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(westernTamang, true, false, sink);
        appendKey(session, requiredKey(base, "base.r2.k3"), sink);
        appendKey(session, requiredKey(base, "base.r1.k0"), sink);
        appendKey(session, requiredKey(base, "base.r3.k3"), sink);
        assertSessionQuery(
                "Western Tamang",
                session,
                vector.query,
                "वा़से"
        );
        assertEquals(
                "Western Tamang pack vector surface",
                "वा़से",
                vector.expectedSurface
        );
    }

    private static void verifyLohorungPackInput(
            KeyboardProfile lohorung,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(
                lohorung,
                false,
                false,
                false
        );
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(
                lohorung,
                true,
                false,
                false
        );

        RecordingTextSink validationSink = new RecordingTextSink();
        ComposingSession validation = new ComposingSession(engine);
        validation.start(lohorung, true, false, validationSink);
        appendKey(validation, requiredKey(shift, "shift.r1.k5"), validationSink);
        assertSessionQuery(
                "Lohorung validation",
                validation,
                vector.query,
                vector.expectedSurface
        );

        RecordingTextSink terminalSink = new RecordingTextSink();
        ComposingSession terminal = new ComposingSession(engine);
        terminal.start(lohorung, true, false, terminalSink);
        appendLohorungTerminalStem(terminal, base, shift, terminalSink);
        int beforeJoiner = terminalSink.editorCalls.size();
        appendKey(terminal, requiredKey(base, "base.r3.k9"), terminalSink);
        assertEquals(
                "Lohorung pack query buffers terminal ZWNJ",
                beforeJoiner,
                terminalSink.editorCalls.size()
        );
        assertEquals(
                "Lohorung visible composing stem excludes pending terminal ZWNJ",
                "एकङ्",
                terminal.composingText()
        );
        String candidate = awaitSessionCandidate(terminal, "एकङ्\u200c");
        assertEquals("Lohorung terminal-ZWNJ literal candidate", "एकङ्\u200c", candidate);
        assertTrue(
                "Lohorung terminal-ZWNJ candidate replacement succeeds",
                terminal.selectCandidate(candidate, terminalSink)
        );
        assertEquals("Lohorung terminal-ZWNJ candidate text", "एकङ्\u200c", terminalSink.text());
        assertTrue(
                "Lohorung terminal-ZWNJ candidate commits atomically",
                terminalSink.editorCalls.contains("commit:एकङ्\u200c")
        );
        assertNoIsolatedJoinerCall("Lohorung candidate replacement", terminalSink);
    }

    private static void verifyYakkhaPackInput(
            KeyboardProfile yakkha,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(yakkha, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(yakkha, true, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(yakkha, false, true, false);

        RecordingTextSink validationSink = new RecordingTextSink();
        ComposingSession validation = new ComposingSession(engine);
        validation.start(yakkha, true, false, validationSink);
        appendKey(validation, requiredKey(shift, "shift.r1.k5"), validationSink);
        assertSessionQuery(
                "Yakkha validation",
                validation,
                vector.query,
                vector.expectedSurface
        );

        RecordingTextSink hyphenSink = new RecordingTextSink();
        ComposingSession hyphen = new ComposingSession(engine);
        hyphen.start(yakkha, true, false, hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r0.k9"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r0.k2"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r3.k2"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r1.k8"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r0.k2"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r2.k6"), hyphenSink);
        appendKey(hyphen, requiredKey(symbols, "symbols.r1.k5"), hyphenSink);
        assertSessionQuery(
                "Yakkha hyphen",
                hyphen,
                "पेॽलेम-",
                "पेॽलेम-पेॽलेम"
        );

        RecordingTextSink slashSink = new RecordingTextSink();
        ComposingSession slash = new ComposingSession(engine);
        slash.start(yakkha, true, false, slashSink);
        appendKey(slash, requiredKey(shift, "shift.r1.k7"), slashSink);
        appendKey(slash, requiredKey(base, "base.r0.k8"), slashSink);
        appendKey(slash, requiredKey(base, "base.r1.k7"), slashSink);
        appendKey(slash, requiredKey(base, "base.r2.k9"), slashSink);
        appendKey(slash, requiredKey(base, "base.r3.k3"), slashSink);
        appendKey(slash, requiredKey(base, "base.r2.k5"), slashSink);
        appendKey(slash, requiredKey(base, "base.r0.k7"), slashSink);
        appendKey(slash, requiredKey(base, "base.r2.k6"), slashSink);
        appendKey(slash, requiredKey(base, "base.r1.k0"), slashSink);
        appendKey(slash, requiredKey(symbols, "symbols.r2.k7"), slashSink);
        assertSessionQuery(
                "Yakkha slash",
                slash,
                "खोक्‍निमा/",
                "खोक्‍निमा/खोक्‍निबा"
        );

        RecordingTextSink backslashSink = new RecordingTextSink();
        ComposingSession backslash = new ComposingSession(engine);
        backslash.start(yakkha, true, false, backslashSink);
        appendKey(backslash, requiredKey(base, "base.r2.k4"), backslashSink);
        appendKey(backslash, requiredKey(base, "base.r0.k2"), backslashSink);
        appendKey(backslash, requiredKey(symbols, "symbols.r2.k9"), backslashSink);
        assertSessionQuery("Yakkha backslash", backslash, "बे\\", "बे\\पे");

        RecordingTextSink terminalSink = new RecordingTextSink();
        ComposingSession terminal = new ComposingSession(engine);
        terminal.start(yakkha, true, false, terminalSink);
        appendYakkhaTerminalStem(terminal, base, shift, terminalSink);
        int beforeJoiner = terminalSink.editorCalls.size();
        appendKey(terminal, requiredKey(base, "base.r3.k4"), terminalSink);
        assertEquals(
                "Yakkha pack query buffers terminal ZWNJ",
                beforeJoiner,
                terminalSink.editorCalls.size()
        );
        assertEquals(
                "Yakkha visible composing stem excludes pending terminal ZWNJ",
                "टाङ्",
                terminal.composingText()
        );
        String candidate = awaitSessionCandidate(terminal, "टाङ्\u200c");
        assertEquals("Yakkha terminal-ZWNJ literal candidate", "टाङ्\u200c", candidate);
        assertTrue(
                "Yakkha terminal-ZWNJ candidate replacement succeeds",
                terminal.selectCandidate(candidate, terminalSink)
        );
        assertEquals("Yakkha terminal-ZWNJ candidate text", "टाङ्\u200c", terminalSink.text());
        assertTrue(
                "Yakkha terminal-ZWNJ candidate commits atomically",
                terminalSink.editorCalls.contains("commit:टाङ्\u200c")
        );
        assertNoIsolatedJoinerCall("Yakkha candidate replacement", terminalSink);
    }

    private static void verifyKhalingPackInput(
            KeyboardProfile khaling,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(khaling, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(khaling, true, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(khaling, false, true, false);

        RecordingTextSink validationSink = new RecordingTextSink();
        ComposingSession validation = new ComposingSession(engine);
        validation.start(khaling, true, false, validationSink);
        appendKey(validation, requiredKey(base, "base.r1.k7"), validationSink);
        assertSessionQuery(
                "Khaling validation",
                validation,
                vector.query,
                vector.expectedSurface
        );

        RecordingTextSink zwjSink = new RecordingTextSink();
        ComposingSession zwj = new ComposingSession(engine);
        zwj.start(khaling, true, false, zwjSink);
        appendKey(zwj, requiredKey(shift, "shift.r1.k0"), zwjSink);
        appendKey(zwj, requiredKey(shift, "shift.r2.k7"), zwjSink);
        appendKey(zwj, requiredKey(base, "base.r2.k9"), zwjSink);
        appendKey(zwj, requiredKey(base, "base.r3.k4"), zwjSink);
        appendKey(zwj, requiredKey(shift, "shift.r1.k7"), zwjSink);
        assertSessionQuery(
                "Khaling conjunct ZWJ",
                zwj,
                "आङ्\u200dख",
                "आङ्\u200dखङा"
        );
        assertNoEditorCallEndsInJoiner("Khaling pack-backed ZWJ", zwjSink);

        RecordingTextSink hyphenSink = new RecordingTextSink();
        ComposingSession hyphen = new ComposingSession(engine);
        hyphen.start(khaling, true, false, hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r1.k6"), hyphenSink);
        appendKey(hyphen, requiredKey(shift, "shift.r0.k7"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r2.k3"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r2.k5"), hyphenSink);
        appendKey(hyphen, requiredKey(symbols, "symbols.r1.k5"), hyphenSink);
        assertSessionQuery(
                "Khaling intra-word hyphen",
                hyphen,
                "जीवन-",
                "जीवन-काल"
        );
    }

    private static void verifyDumiPackInput(
            KeyboardProfile dumi,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(dumi, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(dumi, true, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(dumi, false, true, false);

        RecordingTextSink validationSink = new RecordingTextSink();
        ComposingSession validation = new ComposingSession(engine);
        validation.start(dumi, true, false, validationSink);
        appendKey(validation, requiredKey(base, "base.r1.k7"), validationSink);
        assertSessionQuery("Dumi validation", validation, vector.query, vector.expectedSurface);

        RecordingTextSink zwjSink = new RecordingTextSink();
        ComposingSession zwj = new ComposingSession(engine);
        zwj.start(dumi, true, false, zwjSink);
        appendKey(zwj, requiredKey(shift, "shift.r1.k5"), zwjSink);
        appendKey(zwj, requiredKey(base, "base.r2.k6"), zwjSink);
        appendKey(zwj, requiredKey(base, "base.r2.k9"), zwjSink);
        appendKey(zwj, requiredKey(base, "base.r3.k4"), zwjSink);
        appendKey(zwj, requiredKey(base, "base.r1.k8"), zwjSink);
        assertSessionQuery("Dumi conjunct ZWJ", zwj, "अम्‍ल", "अम्‍ल");
        assertNoEditorCallEndsInJoiner("Dumi pack-backed ZWJ", zwjSink);

        RecordingTextSink zwnjSink = new RecordingTextSink();
        ComposingSession zwnj = new ComposingSession(engine);
        zwnj.start(dumi, true, false, zwnjSink);
        appendKey(zwnj, requiredKey(shift, "shift.r1.k0"), zwnjSink);
        appendKey(zwnj, requiredKey(base, "base.r0.k3"), zwnjSink);
        appendKey(zwnj, requiredKey(base, "base.r2.k9"), zwnjSink);
        appendKey(zwnj, requiredKey(base, "base.r3.k5"), zwnjSink);
        appendKey(zwnj, requiredKey(shift, "shift.r1.k7"), zwnjSink);
        appendKey(zwnj, requiredKey(base, "base.r0.k6"), zwnjSink);
        assertSessionQuery("Dumi conjunct ZWNJ", zwnj, "आर्‌खु", "आर्‌खु");
        assertNoEditorCallEndsInJoiner("Dumi pack-backed ZWNJ", zwnjSink);

        RecordingTextSink colonSink = new RecordingTextSink();
        ComposingSession colon = new ComposingSession(engine);
        colon.start(dumi, true, false, colonSink);
        appendKey(colon, requiredKey(base, "base.r1.k7"), colonSink);
        appendKey(colon, requiredKey(base, "base.r0.k6"), colonSink);
        appendKey(colon, requiredKey(symbols, "symbols.r2.k3"), colonSink);
        assertSessionQuery("Dumi intra-word colon", colon, "कु:", "कु:ना");

        RecordingTextSink hyphenSink = new RecordingTextSink();
        ComposingSession hyphen = new ComposingSession(engine);
        hyphen.start(dumi, true, false, hyphenSink);
        appendKey(hyphen, requiredKey(shift, "shift.r1.k0"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r2.k6"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r2.k9"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r3.k4"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r2.k5"), hyphenSink);
        appendKey(hyphen, requiredKey(base, "base.r1.k0"), hyphenSink);
        appendKey(hyphen, requiredKey(symbols, "symbols.r1.k5"), hyphenSink);
        assertSessionQuery(
                "Dumi intra-word hyphen",
                hyphen,
                "आम्‍ना-",
                "आम्‍ना-आसाला"
        );

        RecordingTextSink visargaSink = new RecordingTextSink();
        ComposingSession visarga = new ComposingSession(engine);
        visarga.start(dumi, true, false, visargaSink);
        appendKey(visarga, requiredKey(base, "base.r0.k4"), visargaSink);
        appendKey(visarga, requiredKey(base, "base.r3.k6"), visargaSink);
        assertSessionQuery("Dumi visarga", visarga, "तः", "तःले");

        RecordingTextSink nuktaSink = new RecordingTextSink();
        ComposingSession nukta = new ComposingSession(engine);
        nukta.start(dumi, true, false, nuktaSink);
        appendKey(nukta, requiredKey(base, "base.r2.k4"), nuktaSink);
        appendKey(nukta, requiredKey(base, "base.r3.k3"), nuktaSink);
        assertSessionQuery("Dumi nukta", nukta, "ब़", "ब़ह़");

        RecordingTextSink glottalSink = new RecordingTextSink();
        ComposingSession glottal = new ComposingSession(engine);
        glottal.start(dumi, true, false, glottalSink);
        appendKey(glottal, requiredKey(base, "base.r3.k7"), glottalSink);
        assertSessionQuery("Dumi glottal stop", glottal, "ॽ", "ॽवाक्ना");
    }

    private static void verifyBantawaPackInput(
            KeyboardProfile bantawa,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(bantawa, true, false, false);
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(bantawa, true, false, sink);
        appendKey(session, requiredKey(shift, "shift.r1.k5"), sink);
        assertSessionQuery("Bantawa validation", session, vector.query, vector.expectedSurface);
    }

    private static void verifyWesternMagarPackInput(
            KeyboardProfile westernMagar,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(westernMagar, true, false, false);
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(westernMagar, true, false, sink);
        appendKey(session, requiredKey(shift, "shift.r1.k5"), sink);
        appendKey(session, requiredKey(shift, "shift.r1.k4"), sink);
        assertSessionQuery("Western Magar typeable prefix", session, "अघ", "अघाडी");
    }

    private static void verifyMidEasternTharuPackInput(
            KeyboardProfile tharu,
            PackVector vector,
            SuggestionEngine engine
    ) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(tharu, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(tharu, true, false, false);
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(engine);
        session.start(tharu, true, false, sink);
        appendKey(session, requiredKey(shift, "shift.r1.k5"), sink);
        appendKey(session, requiredKey(base, "base.r3.k0"), sink);
        appendKey(session, requiredKey(shift, "shift.r0.k0"), sink);
        assertSessionQuery("Mid-Eastern Tharu validation", session, vector.query,
                vector.expectedSurface);
    }

    private static void assertSessionQuery(
            String label,
            ComposingSession session,
            String expectedQuery,
            String expectedSurface
    ) {
        assertEquals(label + " generated-key query", expectedQuery, session.composingText());
        if (expectedSurface.equals(expectedQuery)) {
            assertEquals(
                    label + " generated-key literal candidate",
                    expectedSurface,
                    awaitSessionCandidate(session, expectedSurface)
            );
            return;
        }
        assertEquals(
                label + " generated-key suggestion",
                expectedSurface,
                awaitFirstSessionCandidate(session)
        );
    }

    private static void appendKey(
            ComposingSession session,
            KeySpec key,
            TextSink sink
    ) {
        assertEquals("generated composing key action", KeySpec.Action.TEXT, key.action());
        session.appendText(key.text(), key.inputPolicy(), sink);
    }

    private static KeySpec requiredKey(KeyboardLayouts.Layout layout, String keyId) {
        KeySpec key = layout.keyForTesting(keyId);
        assertTrue("generated key exists " + keyId, key != null);
        return key;
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

    private static void assertNoIsolatedJoinerCall(
            String label,
            RecordingTextSink sink
    ) {
        for (String call : sink.editorCalls) {
            assertTrue(
                    label + " never emits a standalone joiner",
                    !"set:\u200c".equals(call)
                            && !"set:\u200d".equals(call)
                            && !"commit:\u200c".equals(call)
                            && !"commit:\u200d".equals(call)
            );
        }
    }

    private static String printable(String text) {
        if ("\u200c".equals(text)) {
            return "U+200C";
        }
        if ("\u200d".equals(text)) {
            return "U+200D";
        }
        return text;
    }

    private static void verifyLimbuLayout(KeyboardProfile limbu) {
        KeyboardLayouts.Layout base = KeyboardLayouts.forProfile(limbu, false, false, false);
        KeyboardLayouts.Layout shift = KeyboardLayouts.forProfile(limbu, true, false, false);
        KeyboardLayouts.Layout symbols = KeyboardLayouts.forProfile(limbu, false, true, false);
        KeyboardLayouts.Layout numeric = KeyboardLayouts.forProfile(limbu, false, false, true);
        assertEquals("Limbu base rows", 4, base.rows().size());
        assertEquals("Limbu shift rows", 4, shift.rows().size());
        assertEquals("Limbu symbols rows", 4, symbols.rows().size());
        assertEquals("Limbu numeric rows", 5, numeric.rows().size());
        Set<Integer> scalars = new HashSet<>();
        collectLimbuScalars(base, scalars);
        collectLimbuScalars(shift, scalars);
        collectLimbuScalars(symbols, scalars);
        assertEquals("assigned Limbu scalar coverage", assignedLimbuScalars(), scalars);
        assertTrue("Limbu GYAN key", shift.containsText("ᤝ"));
        assertTrue("Limbu TRA key", shift.containsText("ᤞ"));
        assertTrue("Limbu native digit key", symbols.containsText("᥇"));
        assertTrue("ASCII numeric fallback", numeric.containsText("0"));
    }

    private static Set<Integer> assignedLimbuScalars() {
        Set<Integer> expected = new HashSet<>();
        addRange(expected, 0x1900, 0x191E);
        addRange(expected, 0x1920, 0x192B);
        addRange(expected, 0x1930, 0x193B);
        addRange(expected, 0x1940, 0x1940);
        addRange(expected, 0x1944, 0x194F);
        assertEquals("assigned Limbu scalar reference size", 68, expected.size());
        return expected;
    }

    private static void addRange(Set<Integer> destination, int start, int end) {
        for (int codePoint = start; codePoint <= end; codePoint++) {
            destination.add(codePoint);
        }
    }

    private static List<NkpBundle.Suggestion> suggest(
            NkpBundle bundle,
            PackVector vector
    ) {
        if ("surface_prefix".equals(vector.lookupKind)) {
            return bundle.suggestSurface(vector.query);
        }
        if ("alias_prefix".equals(vector.lookupKind)) {
            return bundle.suggestAliases(vector.query);
        }
        throw new AssertionError("unsupported lookup kind: " + vector.lookupKind);
    }

    private static void collectLimbuScalars(
            KeyboardLayouts.Layout layout,
            Set<Integer> destination
    ) {
        for (List<KeySpec> row : layout.rows()) {
            for (KeySpec key : row) {
                String text = key.text();
                if (text == null) {
                    continue;
                }
                text.codePoints()
                        .filter(codePoint -> codePoint >= 0x1900 && codePoint <= 0x194F)
                        .forEach(codePoint -> {
                            if (!destination.add(codePoint)) {
                                throw new AssertionError(
                                        String.format("duplicate Limbu scalar U+%04X", codePoint)
                                );
                            }
                        });
            }
        }
    }

    private static KeyboardProfile available(String profileId) {
        KeyboardProfile profile = LanguageRegistry.find(profileId);
        assertTrue("available profile " + profileId, profile != null && profile.isAvailable());
        return profile;
    }

    private static int defaultEnabledProfileCount() {
        int count = 0;
        for (KeyboardProfile profile : LanguageRegistry.available()) {
            if (profile.defaultEnabled()) {
                count++;
            }
        }
        assertTrue("generated catalog has a default profile", count > 0);
        return count;
    }

    private static void verifyGeneratedSubtypeRegistry(Context context) {
        AndroidSubtypeRegistry registry = AndroidSubtypeRegistry.load(context);
        InputMethodInfo inputMethod = registry.inputMethodInfoForTesting();
        // Only lock-selectable profiles get an installed Android subtype; the
        // transliteration supplement adds in-keyboard profiles, not system ones.
        assertEquals(
                "generated subtype registry count",
                LanguageRegistry.subtypeBacked().size(),
                inputMethod.getSubtypeCount()
        );
        Set<String> profileIds = new HashSet<>();
        Set<Integer> subtypeIds = new HashSet<>();
        for (int index = 0; index < inputMethod.getSubtypeCount(); index++) {
            InputMethodSubtype subtype = inputMethod.getSubtypeAt(index);
            KeyboardProfile profile = registry.profileForSubtype(subtype);
            assertTrue("internal generated subtype resolves", profile != null);
            assertTrue("internal subtype profile is unique", profileIds.add(profile.id()));
            assertTrue("internal subtype ID is positive", subtype.hashCode() > 0);
            assertTrue("internal subtype ID is unique", subtypeIds.add(subtype.hashCode()));
            assertTrue(
                    "internal profile resolves to exact subtype",
                    subtype.equals(registry.subtypeForProfile(profile.id()))
            );
            assertEquals(
                    "internal subtype language tag",
                    profile.localeTag(),
                    subtype.getLanguageTag()
            );
            assertEquals(
                    "internal subtype display label",
                    expectedSubtypeLabel(profile),
                    subtype.getDisplayName(
                            context,
                            inputMethod.getPackageName(),
                            inputMethod.getServiceInfo().applicationInfo
                    ).toString()
            );
        }
        assertEquals("internal subtype exact profile set", availableProfileIds(), profileIds);
    }

    private static void verifyPreferencePlatformReconciliation(Context context) {
        LanguagePreferences preferences = new LanguagePreferences(
                context,
                "internal_ime_smoke_profile_reconciliation"
        );
        preferences.clearForTesting();
        assertTrue(
                "internal request active Nepali",
                preferences.requestActive(LanguageRegistry.NEPALI_DIRECT_ID)
        );
        assertEquals(
                "internal pending Nepali",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.pendingProfile().id()
        );
        preferences.observePlatformProfile(LanguageRegistry.NEPALI_DIRECT_ID);
        assertTrue("internal matching observation clears pending", preferences.pendingProfile() == null);

        assertTrue(
                "internal disable English",
                preferences.setEnabled(LanguageRegistry.ENGLISH_ID, false)
        );
        assertTrue("internal English disabled", !preferences.isEnabled(LanguageRegistry.ENGLISH_ID));
        assertEquals(
                "internal platform English auto-enable",
                LanguageRegistry.ENGLISH_ID,
                preferences.observePlatformProfile(LanguageRegistry.ENGLISH_ID).id()
        );
        assertTrue("internal platform English enabled", preferences.isEnabled(LanguageRegistry.ENGLISH_ID));

        assertTrue(
                "internal request Nepali over English",
                preferences.requestActive(LanguageRegistry.NEPALI_DIRECT_ID)
        );
        assertEquals(
                "internal stale observation preserves pending",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.observePlatformProfile(LanguageRegistry.ENGLISH_ID).id()
        );
        assertEquals(
                "internal pending survives stale observation",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.pendingProfile().id()
        );
        preferences.observePlatformProfile(LanguageRegistry.NEPALI_DIRECT_ID);
        assertTrue("internal converged observation clears pending", preferences.pendingProfile() == null);

        assertEquals(
                "internal unknown subtype preserves active",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.observePlatformProfile("removed-profile").id()
        );
        assertEquals(
                "internal unknown subtype requests active",
                LanguageRegistry.NEPALI_DIRECT_ID,
                preferences.pendingProfile().id()
        );
        preferences.observePlatformProfile(LanguageRegistry.NEPALI_DIRECT_ID);
        assertTrue("internal active subtype reconfirms", preferences.pendingProfile() == null);

        assertTrue(
                "internal disable active Nepali",
                preferences.setEnabled(LanguageRegistry.NEPALI_DIRECT_ID, false)
        );
        assertEquals(
                "internal active disable fallback",
                LanguageRegistry.ENGLISH_ID,
                preferences.activeProfile().id()
        );
        assertEquals(
                "internal active disable pending fallback",
                LanguageRegistry.ENGLISH_ID,
                preferences.pendingProfile().id()
        );
        preferences.clearForTesting();
    }

    private static String expectedSubtypeLabel(KeyboardProfile profile) {
        int methodsForTarget = 0;
        // Counts installed subtypes only: a supplement profile has none, so it must
        // not change how an existing subtype's label is rendered.
        for (KeyboardProfile candidate : LanguageRegistry.subtypeBacked()) {
            if (candidate.languageId().equals(profile.languageId())) {
                methodsForTarget++;
            }
        }
        return methodsForTarget > 1
                ? profile.nativeName() + " · " + profile.detail()
                : profile.nativeName();
    }

    /** Lock-selectable profiles only: these are compared against lock-derived assets. */
    private static Set<String> availableProfileIds() {
        Set<String> ids = new HashSet<>();
        for (KeyboardProfile profile : LanguageRegistry.subtypeBacked()) {
            assertTrue("unique available profile " + profile.id(), ids.add(profile.id()));
        }
        return ids;
    }

    private static Set<String> availablePackProfileIds() {
        return availableProfileIds(KeyboardProfile.ArtifactKind.NKP);
    }

    private static Set<String> availableConversionProfileIds() {
        return availableProfileIds(KeyboardProfile.ArtifactKind.NCM);
    }

    private static Set<String> availableProfileIds(KeyboardProfile.ArtifactKind artifactKind) {
        Set<String> ids = new HashSet<>();
        for (KeyboardProfile profile : LanguageRegistry.subtypeBacked()) {
            if (profile.artifactKind() == artifactKind) {
                assertTrue("unique available artifact profile " + profile.id(), ids.add(profile.id()));
            }
        }
        return ids;
    }

    private static PackVector findVector(List<PackVector> vectors, String profileId) {
        for (PackVector vector : vectors) {
            if (profileId.equals(vector.profileId)) {
                return vector;
            }
        }
        throw new AssertionError("missing vector for " + profileId);
    }

    private static Set<String> packVectorProfileIds(List<PackVector> vectors) {
        Set<String> result = new HashSet<>();
        for (PackVector vector : vectors) {
            assertTrue("unique pack-vector profile " + vector.profileId, result.add(vector.profileId));
        }
        return result;
    }

    private static RuntimeConformance readRuntimeConformance(Context context) throws Exception {
        byte[] encoded = readBoundedAsset(
                context,
                RUNTIME_CONFORMANCE_ASSET,
                MAX_RUNTIME_CONFORMANCE_BYTES,
                "runtime conformance"
        );
        assertEquals(
                "runtime conformance asset SHA-256",
                GeneratedLayoutRegistry.RUNTIME_CONFORMANCE_SHA256,
                hex(MessageDigest.getInstance("SHA-256").digest(encoded))
        );
        JSONObject root = new JSONObject(new String(encoded, StandardCharsets.UTF_8));
        assertExactJsonFields(
                root,
                "runtime conformance root",
                "format_version",
                "profile_lock_sha256",
                "layout_lock_sha256",
                "selectable_profile_count",
                "profiles"
        );
        if (requiredExactInt(root.get("format_version"), "format_version") != 2) {
            throw new IllegalStateException("unsupported runtime conformance format");
        }
        assertEquals(
                "runtime conformance profile lock",
                GeneratedProfileCatalog.LOCK_SHA256,
                requiredJsonString(root, "profile_lock_sha256", "runtime conformance root")
        );
        assertEquals(
                "runtime conformance layout lock",
                GeneratedLayoutRegistry.LAYOUT_LOCK_SHA256,
                requiredJsonString(root, "layout_lock_sha256", "runtime conformance root")
        );
        int profileCount = requiredExactInt(
                root.get("selectable_profile_count"),
                "selectable_profile_count"
        );
        if (profileCount < 1 || profileCount > MAX_RUNTIME_CONFORMANCE_PROFILES
                || profileCount != GeneratedProfileCatalog.SELECTABLE_COUNT) {
            throw new IllegalStateException("runtime conformance profile count is invalid");
        }
        JSONArray rows = root.getJSONArray("profiles");
        if (rows.length() != profileCount) {
            throw new IllegalStateException("runtime conformance profile array count mismatch");
        }

        List<RuntimeProfileVector> profiles = new ArrayList<>(profileCount);
        Set<String> seen = new HashSet<>();
        String previousProfileId = null;
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.getJSONObject(index);
            assertExactJsonFields(
                    row,
                    "runtime conformance profile " + index,
                    "profile_id",
                    "language_id",
                    "input_method_id",
                    "locale_tag",
                    "display_name",
                    "native_name",
                    "source_script",
                    "output_script",
                    "detail",
                    "method_type",
                    "engine_kind",
                    "layout_id",
                    "lookup_kind",
                    "artifact_kind",
                    "artifact_binding",
                    "catalog_readiness",
                    "availability",
                    "blocked_reason",
                    "blocked_detail",
                    "default_enabled",
                    "scope",
                    "group",
                    "variety",
                    "sort_key",
                    "search_aliases",
                    "evidence_ids",
                    "layers",
                    "dispatch_probe"
            );
            String label = "runtime conformance profile " + index;
            String profileId = requiredJsonString(row, "profile_id", label);
            if (!profileId.matches("[A-Za-z0-9][A-Za-z0-9._-]*")
                    || !seen.add(profileId)
                    || (previousProfileId != null && previousProfileId.compareTo(profileId) >= 0)) {
                throw new IllegalStateException("runtime conformance profile order/set is invalid");
            }
            previousProfileId = profileId;

            JSONObject layers = row.getJSONObject("layers");
            assertExactJsonFields(layers, label + " layers", "base", "shift", "symbols", "numeric");
            Map<String, String> layerFingerprints = new HashMap<>();
            for (String layerId : RuntimeProfileVector.LAYER_IDS) {
                String fingerprint = requiredJsonString(layers, layerId, label + " layers");
                if (!fingerprint.matches("[0-9a-f]{64}")) {
                    throw new IllegalStateException(label + " has invalid layer fingerprint");
                }
                layerFingerprints.put(layerId, fingerprint);
            }

            JSONObject probe = row.getJSONObject("dispatch_probe");
            assertExactJsonFields(probe, label + " dispatch probe", "layer_id", "key_id", "text");
            if (!"base".equals(requiredJsonString(probe, "layer_id", label + " dispatch probe"))) {
                throw new IllegalStateException(label + " dispatch probe must use the base layer");
            }
            String dispatchKeyId = requiredJsonString(probe, "key_id", label + " dispatch probe");
            String dispatchText = requiredJsonString(probe, "text", label + " dispatch probe");
            if (!dispatchKeyId.matches("base\\.r[0-7]\\.k(?:[0-9]|1[0-9])")
                    || dispatchText.codePointCount(0, dispatchText.length()) > 16
                    || dispatchText.indexOf('\u200c') >= 0
                    || dispatchText.indexOf('\u200d') >= 0) {
                throw new IllegalStateException(label + " dispatch probe is invalid");
            }

            profiles.add(new RuntimeProfileVector(
                    profileId,
                    requiredJsonString(row, "language_id", label),
                    requiredJsonString(row, "input_method_id", label),
                    requiredJsonString(row, "locale_tag", label),
                    requiredJsonString(row, "display_name", label),
                    requiredJsonString(row, "native_name", label),
                    requiredJsonString(row, "source_script", label),
                    requiredJsonString(row, "output_script", label),
                    requiredJsonString(row, "detail", label),
                    requiredJsonString(row, "method_type", label),
                    requiredJsonString(row, "engine_kind", label),
                    requiredJsonString(row, "layout_id", label),
                    requiredJsonString(row, "lookup_kind", label),
                    requiredJsonString(row, "artifact_kind", label),
                    requiredJsonString(row, "artifact_binding", label),
                    requiredJsonString(row, "catalog_readiness", label),
                    requiredJsonString(row, "availability", label),
                    nullableJsonString(row, "blocked_reason", label),
                    nullableJsonString(row, "blocked_detail", label),
                    requiredJsonBoolean(row, "default_enabled", label),
                    requiredJsonString(row, "scope", label),
                    nullableJsonString(row, "group", label),
                    nullableJsonString(row, "variety", label),
                    requiredJsonString(row, "sort_key", label),
                    requiredJsonStringList(row, "search_aliases", label, 1, 64),
                    requiredJsonStringList(row, "evidence_ids", label, 1, 64),
                    layerFingerprints,
                    dispatchKeyId,
                    dispatchText
            ));
        }
        return new RuntimeConformance(profiles);
    }

    private static byte[] readBoundedAsset(
            Context context,
            String assetPath,
            int maximumBytes,
            String label
    ) throws Exception {
        try (InputStream input = context.getAssets().open(assetPath);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8 * 1024];
            int total = 0;
            int count;
            while ((count = input.read(buffer)) != -1) {
                total += count;
                if (total > maximumBytes) {
                    throw new IllegalStateException(label + " exceeds size limit");
                }
                output.write(buffer, 0, count);
            }
            if (total == 0) {
                throw new IllegalStateException(label + " is empty");
            }
            return output.toByteArray();
        }
    }

    private static void assertExactJsonFields(
            JSONObject value,
            String label,
            String... expectedFields
    ) {
        Set<String> actual = new HashSet<>();
        Iterator<String> keys = value.keys();
        while (keys.hasNext()) {
            actual.add(keys.next());
        }
        Set<String> expected = new HashSet<>(Arrays.asList(expectedFields));
        if (!actual.equals(expected)) {
            throw new IllegalStateException(
                    label + " fields mismatch: expected " + expected + ", got " + actual
            );
        }
    }

    private static String requiredJsonString(
            JSONObject row,
            String field,
            String label
    ) throws JSONException {
        if (!row.has(field) || row.isNull(field)) {
            throw new IllegalStateException(label + "." + field + " must be a string");
        }
        Object value = row.get(field);
        if (!(value instanceof String) || ((String) value).isEmpty()) {
            throw new IllegalStateException(label + "." + field + " must be a non-empty string");
        }
        return (String) value;
    }

    private static String nullableJsonString(
            JSONObject row,
            String field,
            String label
    ) throws JSONException {
        if (!row.has(field)) {
            throw new IllegalStateException(label + "." + field + " is missing");
        }
        if (row.isNull(field)) {
            return null;
        }
        return requiredJsonString(row, field, label);
    }

    private static boolean requiredJsonBoolean(
            JSONObject row,
            String field,
            String label
    ) throws JSONException {
        if (!row.has(field) || row.isNull(field) || !(row.get(field) instanceof Boolean)) {
            throw new IllegalStateException(label + "." + field + " must be boolean");
        }
        return (Boolean) row.get(field);
    }

    private static List<String> requiredJsonStringList(
            JSONObject row,
            String field,
            String label,
            int minimumSize,
            int maximumSize
    ) throws JSONException {
        JSONArray values = row.getJSONArray(field);
        if (values.length() < minimumSize || values.length() > maximumSize) {
            throw new IllegalStateException(label + "." + field + " has invalid size");
        }
        List<String> result = new ArrayList<>(values.length());
        for (int index = 0; index < values.length(); index++) {
            Object value = values.get(index);
            if (!(value instanceof String) || ((String) value).isEmpty()) {
                throw new IllegalStateException(label + "." + field + " contains invalid text");
            }
            result.add((String) value);
        }
        return result;
    }

    private static String hex(byte[] encoded) {
        char[] result = new char[encoded.length * 2];
        for (int index = 0; index < encoded.length; index++) {
            int value = encoded[index] & 0xff;
            result[index * 2] = Character.forDigit(value >>> 4, 16);
            result[index * 2 + 1] = Character.forDigit(value & 0xf, 16);
        }
        return new String(result);
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
                    throw new IllegalStateException("internal pack vectors exceed size limit");
                }
                output.write(buffer, 0, count);
            }
            encoded = output.toByteArray();
        }
        JSONObject root = new JSONObject(new String(encoded, StandardCharsets.UTF_8));
        if (root.length() != 1 || !root.has("bindings")) {
            throw new IllegalStateException("internal pack vector root is invalid");
        }
        JSONArray rows = root.getJSONArray("bindings");
        List<PackVector> result = new ArrayList<>(rows.length());
        Set<String> profiles = new HashSet<>();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.getJSONObject(index);
            if (row.length() != 15) {
                throw new IllegalStateException("internal pack vector has unexpected fields");
            }
            String profileId = row.getString("profile_id");
            if (!profiles.add(profileId)) {
                throw new IllegalStateException("internal pack vector repeats a profile");
            }
            String assetPath = row.getString("asset_path");
            String language = row.getString("language");
            String outputScript = row.getString("output_script");
            String artifactLicense = row.getString("artifact_license");
            int candidateCount = requiredExactInt(row.get("candidate_count"), "candidate_count");
            int surfaceKeyCount = requiredExactInt(
                    row.get("surface_key_count"),
                    "surface_key_count"
            );
            int aliasKeyCount = requiredExactInt(row.get("alias_key_count"), "alias_key_count");
            String lookupKind = row.getString("lookup_kind");
            String validationQuery = row.getString("validation_query");
            String validationExpectedSurface = row.getString("validation_expected_surface");
            JSONArray benchmarkQueries = row.getJSONArray("benchmark_queries");
            if (!assetPath.matches("nepa-packs/[A-Za-z0-9._-]+\\.nkp")
                    || !language.matches("[a-z]{3}")
                    || !outputScript.matches("[A-Z][a-z]{3}")
                    || artifactLicense.isEmpty()
                    || candidateCount < 1
                    || surfaceKeyCount < 0
                    || aliasKeyCount < 0
                    || !("surface_prefix".equals(lookupKind)
                        || "alias_prefix".equals(lookupKind))
                    || ("surface_prefix".equals(lookupKind) && surfaceKeyCount < 1)
                    || ("alias_prefix".equals(lookupKind) && aliasKeyCount < 1)
                    || validationQuery.isEmpty()
                    || validationExpectedSurface.isEmpty()
                    || benchmarkQueries.length() < 1
                    || benchmarkQueries.length() > 64
            ) {
                throw new IllegalStateException("internal pack vector metadata is invalid");
            }
            for (int queryIndex = 0; queryIndex < benchmarkQueries.length(); queryIndex++) {
                if (benchmarkQueries.getString(queryIndex).isEmpty()) {
                    throw new IllegalStateException("internal benchmark query is empty");
                }
            }
            result.add(new PackVector(
                    profileId,
                    row.getString("pack_id"),
                    row.getString("artifact_sha256"),
                    row.getString("release_mode"),
                    candidateCount,
                    lookupKind,
                    validationQuery,
                    validationExpectedSurface
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

    private static List<String> awaitSuggestions(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            String prefix
    ) {
        long deadline = SystemClock.elapsedRealtime() + TCG_PACK_READY_TIMEOUT_MS;
        SuggestionQuery query = new SuggestionQuery(profile, prefix, false);
        do {
            SuggestionSnapshot snapshot = engine.suggest(activation, query);
            if (snapshot.status() == SuggestionSnapshot.Status.READY) {
                return snapshot.candidates();
            }
            if (snapshot.status() == SuggestionSnapshot.Status.MISSING
                    || snapshot.status() == SuggestionSnapshot.Status.CORRUPT
                    || snapshot.status() == SuggestionSnapshot.Status.UNAVAILABLE) {
                throw new AssertionError(
                        "internal engine failed for " + profile.id() + ": " + snapshot.status()
                );
            }
            SystemClock.sleep(25L);
        } while (SystemClock.elapsedRealtime() < deadline);
        throw new AssertionError("internal engine timed out for " + profile.id());
    }

    private static String awaitFirstSessionCandidate(ComposingSession session) {
        long deadline = SystemClock.elapsedRealtime() + TCG_PACK_READY_TIMEOUT_MS;
        do {
            SuggestionSnapshot snapshot = session.suggestionSnapshot();
            if (snapshot.status() == SuggestionSnapshot.Status.READY
                    && snapshot.hasProviderCandidates()) {
                return snapshot.candidates().get(0);
            }
            if (snapshot.status() == SuggestionSnapshot.Status.MISSING
                    || snapshot.status() == SuggestionSnapshot.Status.CORRUPT
                    || snapshot.status() == SuggestionSnapshot.Status.UNAVAILABLE) {
                throw new AssertionError(
                        "internal composing engine failed for "
                                + session.profile().id()
                                + ": "
                                + snapshot.status()
                );
            }
            SystemClock.sleep(25L);
        } while (SystemClock.elapsedRealtime() < deadline);
        throw new AssertionError(
                "internal composing engine timed out for " + session.profile().id()
        );
    }

    private static String awaitSessionCandidate(
            ComposingSession session,
            String expectedCandidate
    ) {
        long deadline = SystemClock.elapsedRealtime() + TCG_PACK_READY_TIMEOUT_MS;
        do {
            SuggestionSnapshot snapshot = session.suggestionSnapshot();
            if (snapshot.status() == SuggestionSnapshot.Status.READY) {
                assertTrue(
                        "internal composing candidate is present for " + session.profile().id(),
                        snapshot.candidates().contains(expectedCandidate)
                );
                return expectedCandidate;
            }
            if (snapshot.status() == SuggestionSnapshot.Status.MISSING
                    || snapshot.status() == SuggestionSnapshot.Status.CORRUPT
                    || snapshot.status() == SuggestionSnapshot.Status.UNAVAILABLE) {
                throw new AssertionError(
                        "internal composing engine failed for "
                                + session.profile().id()
                                + ": "
                                + snapshot.status()
                );
            }
            SystemClock.sleep(25L);
        } while (SystemClock.elapsedRealtime() < deadline);
        throw new AssertionError(
                "internal composing engine timed out for " + session.profile().id()
        );
    }

    private static void assertTrue(String label, boolean value) {
        if (!value) {
            throw new AssertionError(label);
        }
    }

    private void reportProgress(String stage) {
        Bundle progress = new Bundle();
        progress.putString("progress", stage);
        sendStatus(0, progress);
    }

    private static void assertEquals(String label, Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + ", got " + actual);
        }
    }

    private static final class SetupPlatformObservation {
        final boolean enabled;
        final boolean selected;

        SetupPlatformObservation(boolean enabled, boolean selected) {
            this.enabled = enabled;
            this.selected = selected;
        }
    }

    private static final class PickerRecyclingEvidence {
        final int enabledProfileCount;
        final int attachedWindowRowCount;
        final int reboundRowCount;

        PickerRecyclingEvidence(
                int enabledProfileCount,
                int attachedWindowRowCount,
                int reboundRowCount
        ) {
            this.enabledProfileCount = enabledProfileCount;
            this.attachedWindowRowCount = attachedWindowRowCount;
            this.reboundRowCount = reboundRowCount;
        }
    }

    private static final class RuntimeConformance {
        final List<RuntimeProfileVector> profiles;

        RuntimeConformance(List<RuntimeProfileVector> profiles) {
            this.profiles = profiles;
        }

        Set<String> profileIds() {
            Set<String> result = new HashSet<>();
            for (RuntimeProfileVector profile : profiles) {
                assertTrue("unique runtime profile " + profile.profileId, result.add(profile.profileId));
            }
            return result;
        }
    }

    private static final class RuntimeProfileVector {
        static final List<String> LAYER_IDS =
                Arrays.asList("base", "shift", "symbols", "numeric");

        final String profileId;
        final String languageId;
        final String inputMethodId;
        final String localeTag;
        final String displayName;
        final String nativeName;
        final String sourceScript;
        final String outputScript;
        final String detail;
        final String methodType;
        final String engineKind;
        final String layoutId;
        final String lookupKind;
        final String artifactKind;
        final String artifactBinding;
        final String catalogReadiness;
        final String availability;
        final String blockedReason;
        final String blockedDetail;
        final boolean defaultEnabled;
        final String scope;
        final String group;
        final String variety;
        final String sortKey;
        final List<String> searchAliases;
        final List<String> evidenceIds;
        final Map<String, String> layerFingerprints;
        final String dispatchKeyId;
        final String dispatchText;

        RuntimeProfileVector(
                String profileId,
                String languageId,
                String inputMethodId,
                String localeTag,
                String displayName,
                String nativeName,
                String sourceScript,
                String outputScript,
                String detail,
                String methodType,
                String engineKind,
                String layoutId,
                String lookupKind,
                String artifactKind,
                String artifactBinding,
                String catalogReadiness,
                String availability,
                String blockedReason,
                String blockedDetail,
                boolean defaultEnabled,
                String scope,
                String group,
                String variety,
                String sortKey,
                List<String> searchAliases,
                List<String> evidenceIds,
                Map<String, String> layerFingerprints,
                String dispatchKeyId,
                String dispatchText
        ) {
            this.profileId = profileId;
            this.languageId = languageId;
            this.inputMethodId = inputMethodId;
            this.localeTag = localeTag;
            this.displayName = displayName;
            this.nativeName = nativeName;
            this.sourceScript = sourceScript;
            this.outputScript = outputScript;
            this.detail = detail;
            this.methodType = methodType;
            this.engineKind = engineKind;
            this.layoutId = layoutId;
            this.lookupKind = lookupKind;
            this.artifactKind = artifactKind;
            this.artifactBinding = artifactBinding;
            this.catalogReadiness = catalogReadiness;
            this.availability = availability;
            this.blockedReason = blockedReason;
            this.blockedDetail = blockedDetail;
            this.defaultEnabled = defaultEnabled;
            this.scope = scope;
            this.group = group;
            this.variety = variety;
            this.sortKey = sortKey;
            this.searchAliases = searchAliases;
            this.evidenceIds = evidenceIds;
            this.layerFingerprints = layerFingerprints;
            this.dispatchKeyId = dispatchKeyId;
            this.dispatchText = dispatchText;
        }
    }

    private static final class PackVector {
        final String profileId;
        final String packId;
        final String artifactSha256;
        final String releaseMode;
        final int candidateCount;
        final String lookupKind;
        final String query;
        final String expectedSurface;

        PackVector(
                String profileId,
                String packId,
                String artifactSha256,
                String releaseMode,
                int candidateCount,
                String lookupKind,
                String query,
                String expectedSurface
        ) {
            this.profileId = profileId;
            this.packId = packId;
            this.artifactSha256 = artifactSha256;
            this.releaseMode = releaseMode;
            this.candidateCount = candidateCount;
            this.lookupKind = lookupKind;
            this.query = query;
            this.expectedSurface = expectedSurface;
        }
    }

    private static final class RecordingInputListener implements NepaInputView.Listener {
        private final LanguagePreferences preferences;
        private NepaInputView inputView;
        String selectedProfileId;
        String keyText;
        KeySpec keySpec;

        RecordingInputListener(LanguagePreferences preferences) {
            this.preferences = preferences;
        }

        void attach(NepaInputView inputView) {
            this.inputView = inputView;
        }

        @Override
        public void onKey(KeySpec key, SpatialKeyStroke stroke) {
            keySpec = key;
            keyText = key.text();
        }

        @Override
        public void onProfileSelected(String profileId) {
            selectedProfileId = profileId;
            if (preferences != null && !preferences.setActive(profileId)) {
                throw new AssertionError("could not persist selected profile: " + profileId);
            }
            if (preferences != null && inputView != null) {
                inputView.setProfile(preferences.activeProfile());
            }
        }

        @Override
        public void onCandidateSelected(
                SuggestionQuery owner,
                SuggestionCandidate candidate
        ) {
        }

        @Override
        public void onSuggestionRetry() {
        }

        @Override
        public void onManageLanguages() {
        }

        @Override
        public void onOtherKeyboards() {
        }
    }

    private static final class RecordingTextSink implements TextSink {
        final List<String> editorCalls = new ArrayList<>();
        private String committed = "";
        private String composing = "";

        @Override
        public boolean setComposingText(String text) {
            composing = text;
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
}
