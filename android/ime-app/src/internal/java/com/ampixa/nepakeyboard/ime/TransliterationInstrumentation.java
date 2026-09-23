package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import android.view.View;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Proves phonetic typing works on device.
 *
 * <p>The vectors are the same ones the build-time compiler asserts, so the Java engine
 * and the Python engine are held to one shared contract rather than drifting apart.
 */
public final class TransliterationInstrumentation extends Instrumentation {
    private static final String EXPECTED_PACKAGE = "com.ampixa.nepakeyboard.ime.internal";

    /** Golden vectors, mirrored from the reviewed transliteration sources. */
    private static final Map<String, String[][]> VECTORS = new LinkedHashMap<>();

    static {
        VECTORS.put("npi-Deva-NP", new String[][]{
                {"nepaal", "नेपाल"},
                {"namaste", "नमस्ते"},
                {"kaam", "काम"},
                {"ma", "म"},
                {"k_", "क्"},
                {"gharmaa", "घर्मा"},
                {"raamro", "राम्रो"},
                {"chha", "छ"},
                {"himaal", "हिमाल"},
                {"5", "५"},
        });
        VECTORS.put("new-Newa-NP", new String[][]{
                {"nepaal", "𑐣𑐾𑐥𑐵𑐮"},
                {"ka", "𑐎"},
                {"k_", "𑐎𑑂"},
                {"khaa", "𑐏𑐵"},
                {"mhaa", "𑐪𑐵"},
                {"5", "𑑕"},
        });
        VECTORS.put("lif-Limb-NP", new String[][]{
                {"ka", "ᤁ"},
                {"kaa", "ᤁᤠ"},
                {"kan", "ᤁᤴ"},
                {"sik", "ᤛᤡᤰ"},
                {"a", "ᤀ"},
                {"i", "ᤀᤡ"},
                {"5", "᥋"},
        });
    }

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
            assertEquals("internal application ID", EXPECTED_PACKAGE, context.getPackageName());

            TransliterationCatalog catalog = TransliterationCatalog.load(context);
            assertTrue("catalog loaded engines", catalog.engineCountForTesting() > 0);

            int checked = verifyVectors(catalog, result);
            checked += verifyUnboundMaps(context, result);
            verifySupplementProfiles(catalog, result);
            verifyPhonemicContrasts(catalog, result);
            verifySession(catalog, result);
            verifySessionLifecycle(catalog, result);
            runOnMainSync(() -> verifyLiveTyping(context, catalog, result));

            result.putInt("transliteration_vectors_checked", checked);
            result.putInt("transliteration_engines", catalog.engineCountForTesting());
            result.putString("status", "ok");
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            result.putString("status", "error");
            result.putString("error", failure.toString());
        }
        finish(resultCode, result);
    }

    private int verifyVectors(TransliterationCatalog catalog, Bundle result) {
        int checked = 0;
        for (Map.Entry<String, String[][]> entry : VECTORS.entrySet()) {
            KeyboardProfile profile = LanguageRegistry.find(entry.getKey());
            assertTrue("profile exists: " + entry.getKey(), profile != null);
            TransliterationEngine engine = catalog.forProfile(profile);
            assertTrue("engine bound: " + entry.getKey(), engine != null);
            assertEquals(
                    "engine script matches profile: " + entry.getKey(),
                    profile.outputScript(),
                    engine.outputScript()
            );
            for (String[] vector : entry.getValue()) {
                assertEquals(
                        entry.getKey() + " " + vector[0],
                        vector[1],
                        engine.transliterate(vector[0])
                );
                checked++;
            }
        }
        result.putBoolean("transliteration_vectors_verified", true);
        return checked;
    }

    /** The buffer must build up, delete back down, and commit exactly once. */
    private void verifySession(TransliterationCatalog catalog, Bundle result) {
        KeyboardProfile nepali = LanguageRegistry.find("npi-Deva-NP");
        TransliterationEngine engine = catalog.forProfile(nepali);
        RecordingSink sink = new RecordingSink();
        TransliterationSession session = new TransliterationSession();
        session.start(engine, false);
        assertTrue("session is active", session.isActive());

        for (String letter : new String[]{"n", "e", "p", "a", "a", "l"}) {
            session.append(letter, sink);
        }
        assertEquals("buffer accumulates", "nepaal", session.romanBuffer());
        assertEquals("composing text is the script form", "नेपाल", sink.composing);

        session.deleteLast(sink);
        assertEquals("delete removes one Roman character", "nepaa", session.romanBuffer());
        assertEquals("composing text re-renders", "नेपा", sink.composing);

        session.commit(sink);
        assertEquals("commit emits the rendered text", "नेपा", sink.committed);
        assertTrue("buffer clears after commit", !session.hasComposingText());

        // Deleting with an empty buffer must defer to the editor, not swallow the key.
        assertTrue("empty delete defers to the editor", !session.deleteLast(sink));
        result.putBoolean("transliteration_session_verified", true);
    }

    /**
     * Phonemic contrasts must survive the round trip to the device.
     *
     * <p>A map can pass every golden vector and still be unable to write a
     * distinction the language depends on, which silently merges different words.
     * The build-time compiler refuses such a map; this proves the shipped asset
     * still carries the distinction once parsed by the Java engine.
     */
    private void verifyPhonemicContrasts(TransliterationCatalog catalog, Bundle result) {
        KeyboardProfile limbu = LanguageRegistry.find("lif-Limb-NP");
        TransliterationEngine engine = catalog.forProfile(limbu);
        assertTrue("Limbu engine is bound", engine != null);
        String[][] contrasts = {
                {"hap", "\u191C\u1935", "haq", "\u191C\u1939", "glottal stop against final /p/"},
                {"lat", "\u1917\u1933", "laq", "\u1917\u1939", "glottal stop against final /t/"},
                {"hek", "\u191C\u1927\u1930", "heq", "\u191C\u1927\u1939", "glottal stop against final /k/"},
                {"laang", "\u1917\u1920\u1931", "laa:ng", "\u1917\u1920\u193A\u1931", "vowel length"},
                {"maang", "\u1914\u1920\u1931", "maa:ng", "\u1914\u1920\u193A\u1931", "vowel length"},
        };
        for (String[] row : contrasts) {
            String left = engine.transliterate(row[0]);
            String right = engine.transliterate(row[2]);
            assertEquals("contrast left " + row[0], row[1], left);
            assertEquals("contrast right " + row[2], row[3], right);
            assertTrue(
                    "contrast survives on device: " + row[4]
                            + " (" + row[0] + " vs " + row[2] + ")",
                    !left.equals(right)
            );
        }
        result.putInt("transliteration_contrasts_checked", contrasts.length);
        result.putBoolean("transliteration_contrasts_verified", true);
    }

    /**
     * The reviewed transliteration supplement must actually make a language typable.
     *
     * <p>This is the whole point of the supplement: a language with no dictionary
     * cannot pass the lock's pack gate, so without this it stays unreachable.
     */
    private void verifySupplementProfiles(TransliterationCatalog catalog, Bundle result) {
        KeyboardProfile lepcha = LanguageRegistry.find("lep-Latn-Lepc-NP");
        assertTrue("Lepcha roman profile exists", lepcha != null);
        assertTrue("Lepcha is selectable", lepcha.isAvailable());
        assertTrue(
                "Lepcha is transliteration-only",
                LanguageRegistry.isTransliterationOnly("lep-Latn-Lepc-NP")
        );
        assertTrue("Lepcha appears in the picker", LanguageRegistry.available().contains(lepcha));

        TransliterationEngine engine = catalog.forProfile(lepcha);
        assertTrue("Lepcha has a bound engine", engine != null);
        assertEquals("Lepcha engine script", "Lepc", engine.outputScript());
        assertEquals("Lepcha types", "\u1C00\u1C33", engine.transliterate("kat"));

        // The direct Lepcha profile still has no layout, so it must stay unreachable.
        KeyboardProfile direct = LanguageRegistry.find("lep-Lepc-NP");
        assertTrue("direct Lepcha still blocked", direct != null && !direct.isAvailable());

        // Typing through a real session must commit Lepcha, not Latin.
        RecordingSink sink = new RecordingSink();
        TransliterationSession session = new TransliterationSession();
        session.start(engine, false);
        for (String letter : new String[]{"k", "a", "t"}) {
            session.append(letter, sink);
        }
        assertEquals("Lepcha composing text", "\u1C00\u1C33", sink.composing);
        session.commit(sink);
        assertEquals("Lepcha commits script", "\u1C00\u1C33", sink.committed);

        result.putBoolean("transliteration_supplement_verified", true);
        result.putInt("transliteration_supplement_profiles", GeneratedTransliterationProfiles.PROFILE_COUNT);
    }

    /**
     * Maps that ship but whose profiles are still blocked in the profile locks.
     *
     * <p>They reach no profile, so they are held to their vectors directly rather
     * than being left unverified on device until the locks are reopened.
     */
    private int verifyUnboundMaps(Context context, Bundle result) {
        int checked = 0;
        checked += verifyUnboundMap(
                context,
                "lep-Latn-Lepc-v1.json",
                "Lepc",
                new String[][]{
                        {"ka", "\u1C00"},
                        {"kaa", "\u1C00\u1C26"},
                        {"kat", "\u1C00\u1C33"},
                        {"lam", "\u1C1C\u1C2E"},
                        {"tshu", "\u1C18\u1C2A"},
                        {"a", "\u1C23"},
                        {"i", "\u1C23\u1C27"},
                        {"5", "\u1C45"},
                },
                new String[]{"lep-Lepc-NP"}
        );
        checked += verifyUnboundMap(
                context,
                "mai-Latn-Tirh-v1.json",
                "Tirh",
                new String[][]{
                        {"ka", "\uD805\uDC8F"},
                        {"kaa", "\uD805\uDC8F\uD805\uDCB0"},
                        {"ki", "\uD805\uDC8F\uD805\uDCB1"},
                        {"k_", "\uD805\uDC8F\uD805\uDCC2"},
                        {"kaam", "\uD805\uDC8F\uD805\uDCB0\uD805\uDCA7"},
                        {"a", "\uD805\uDC81"},
                        {"i", "\uD805\uDC83"},
                        {"5", "\uD805\uDCD5"},
                },
                new String[]{"mai-Tirh-NP"}
        );
        result.putBoolean("transliteration_unbound_maps_verified", true);
        return checked;
    }

    private int verifyUnboundMap(
            Context context,
            String fileName,
            String expectedScript,
            String[][] vectors,
            String[] profileIds
    ) {
        TransliterationEngine engine =
                TransliterationCatalog.engineFileForTesting(context, fileName);
        assertTrue("map is bundled: " + fileName, engine != null);
        assertEquals("map script: " + fileName, expectedScript, engine.outputScript());
        int checked = 0;
        for (String[] vector : vectors) {
            assertEquals(
                    fileName + " " + vector[0],
                    vector[1],
                    engine.transliterate(vector[0])
            );
            checked++;
        }
        // The profiles exist but must stay unavailable until the locks are reopened,
        // so a premature release cannot be mistaken for a passing test.
        for (String profileId : profileIds) {
            KeyboardProfile profile = LanguageRegistry.find(profileId);
            assertTrue("profile is declared: " + profileId, profile != null);
            assertTrue("profile stays blocked: " + profileId, !profile.isAvailable());
        }
        return checked;
    }

    /**
     * The lifecycle edges the service drives: leaving a field, switching profile mid-word,
     * and typing into a password field must never lose or mis-script the buffer.
     */
    private void verifySessionLifecycle(TransliterationCatalog catalog, Bundle result) {
        KeyboardProfile nepali = LanguageRegistry.find("npi-Deva-NP");
        KeyboardProfile limbu = LanguageRegistry.find("lif-Limb-NP");
        TransliterationEngine deva = catalog.forProfile(nepali);
        TransliterationEngine limb = catalog.forProfile(limbu);

        // Leaving the field commits what the editor is already showing.
        RecordingSink leaving = new RecordingSink();
        TransliterationSession session = new TransliterationSession();
        session.start(deva, false);
        session.append("ma", leaving);
        session.finish(leaving);
        assertEquals("finish commits the pending buffer", "म", leaving.committed);
        assertTrue("finish clears the buffer", !session.hasComposingText());

        // Unbinding must make the session inert, not merely empty.
        session.start(null, false);
        assertTrue("unbound session is inactive", !session.isActive());
        RecordingSink unbound = new RecordingSink();
        assertTrue("unbound session ignores keys", !session.append("k", unbound));
        assertEquals("unbound session emits nothing", "", unbound.composing);

        // Switching profile mid-word must render under the engine that owned the buffer,
        // then continue in the new script.
        RecordingSink switching = new RecordingSink();
        session.start(deva, false);
        session.append("ka", switching);
        session.finish(switching);
        assertEquals("buffer commits in the outgoing script", "क", switching.committed);
        session.start(limb, false);
        session.append("ka", switching);
        assertEquals("typing continues in the incoming script", "ᤁ", switching.composing);
        session.finish(switching);

        // A password field commits literally and never accumulates a buffer.
        RecordingSink privateSink = new RecordingSink();
        session.start(deva, true);
        session.append("k", privateSink);
        assertEquals("private field commits immediately", "क", privateSink.committed);
        assertTrue("private field keeps no buffer", !session.hasComposingText());
        assertEquals("private field publishes no composing text", "", privateSink.composing);

        result.putBoolean("transliteration_lifecycle_verified", true);
    }

    /** The mode must be reachable from the keyboard and must switch the input surface. */
    private void verifyLiveTyping(
            Context context,
            TransliterationCatalog catalog,
            Bundle result
    ) {
        KeyboardProfile nepali = LanguageRegistry.find("npi-Deva-NP");
        boolean[] modeChanges = new boolean[]{false};
        NepaInputView view = new NepaInputView(context, new ModeListener(modeChanges));
        view.setProfile(nepali);
        view.setTransliterationAvailable(catalog.supports(nepali));
        layoutForPixelWidth(view);

        assertTrue("new keyboard view starts with a complete theme",
                view.activeThemeForTesting() != null);
        assertTrue("phonetic mode starts off", !view.isTransliterating());
        assertTrue(
                "phonetic toggle uses a script-neutral symbol",
                view.transliterationToggleUsesNeutralSymbolForTesting()
        );
        assertTrue("phonetic toggle announces off",
                view.transliterationToggleStateForTesting(false));
        KeyboardLayouts.Layout direct = KeyboardLayouts.forProfile(nepali, view.uiState());
        assertTrue("direct surface is Devanagari", direct.containsText("क"));

        view.toggleTransliteration();
        layoutForPixelWidth(view);
        assertTrue("phonetic mode turns on", view.isTransliterating());
        assertTrue("phonetic toggle visibly announces on",
                view.transliterationToggleStateForTesting(true));
        assertTrue("the service was told", modeChanges[0]);
        assertTrue("geometry stays valid", view.visualGeometryContractForTesting());

        KeyboardLayouts.Layout roman = KeyboardLayouts.forTransliteration(nepali, view.uiState());
        assertTrue("phonetic surface is Latin", roman.containsText("k"));
        assertTrue("phonetic surface drops the script keys", !roman.containsText("क"));

        view.toggleTransliteration();
        layoutForPixelWidth(view);
        assertTrue("phonetic mode turns back off", !view.isTransliterating());
        assertTrue("phonetic toggle visibly returns off",
                view.transliterationToggleStateForTesting(false));
        assertTrue("geometry stays valid after returning", view.visualGeometryContractForTesting());

        // A profile with no map must not offer the mode at all.
        KeyboardProfile english = LanguageRegistry.find(LanguageRegistry.ENGLISH_ID);
        assertTrue("English has no map", !catalog.supports(english));
        view.setProfile(english);
        view.setTransliterationAvailable(catalog.supports(english));
        layoutForPixelWidth(view);
        view.toggleTransliteration();
        assertTrue("unsupported profile refuses the mode", !view.isTransliterating());
        result.putBoolean("transliteration_live_typing_verified", true);
    }

    private static void layoutForPixelWidth(View view) {
        view.measure(
                View.MeasureSpec.makeMeasureSpec(1080, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(1600, View.MeasureSpec.AT_MOST)
        );
        view.layout(0, 0, 1080, view.getMeasuredHeight());
    }

    private static void assertTrue(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void assertEquals(String label, Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + ", got " + actual);
        }
    }

    private static final class RecordingSink implements TextSink {
        private String composing = "";
        private String committed = "";

        @Override
        public boolean setComposingText(String text) {
            composing = text;
            return true;
        }

        @Override
        public boolean commitText(String text) {
            committed = text;
            composing = "";
            return true;
        }

        @Override
        public boolean finishComposingText() {
            return true;
        }

        @Override
        public boolean deletePreviousGrapheme() {
            return true;
        }

        @Override
        public boolean deleteOneCodePoint() {
            return true;
        }
    }

    private static final class ModeListener implements NepaInputView.Listener {
        private final boolean[] changes;

        ModeListener(boolean[] changes) {
            this.changes = changes;
        }

        @Override
        public void onKey(KeySpec key, SpatialKeyStroke stroke) {
        }

        @Override
        public void onProfileSelected(String profileId) {
        }

        @Override
        public void onCandidateSelected(SuggestionQuery owner, SuggestionCandidate candidate) {
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

        @Override
        public void onTransliterationModeChanged(boolean transliterating) {
            if (transliterating) {
                changes[0] = true;
            }
        }
    }
}
