package com.ampixa.nepakeyboard.ime;

import android.app.Instrumentation;
import android.content.Context;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputConnectionWrapper;
import android.widget.EditText;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

/** Shared debug/internal vectors for Backspace v1 source and platform acceptance. */
final class BackspaceContractVectors {
    private static final String NEWA_A = "\ud805\udc00";
    private static final String NEWA_KA = "\ud805\udc0e";
    private static final String NEWA_VIRAMA = "\ud805\udc42";
    private static final String NEWA_AVAGRAHA = "\ud805\udc47";
    private static final String NEWA_VOWEL_SIGN_AA = "\ud805\udc35";
    private static final String NEWA_VOWEL_SIGN_U = "\ud805\udc38";

    private BackspaceContractVectors() {
    }

    static Evidence verify(
            Instrumentation instrumentation,
            Context context,
            KeyboardProfile english,
            KeyboardProfile nepali
    ) {
        if (instrumentation == null || context == null || english == null || nepali == null) {
            throw new IllegalArgumentException("backspace vectors require instrumentation and profiles");
        }
        KeyboardProfile newa = newaFixtureProfile();
        verifyBoundaryVectors();
        verifyOwnedComposingDeletion(english, nepali, newa);
        verifyCommittedDeletion(instrumentation, context);
        verifyRepeatController();
        verifyRenderedDeleteWiring(instrumentation, context, english);
        return new Evidence();
    }

    private static void verifyBoundaryVectors() {
        assertWholeCluster("Latin combining", "e\u0301");
        assertWholeCluster("Nepali matra", "कि");
        assertWholeCluster("Nepali conjunct joiner", "क्\u200dष");
        assertNewaActionBoundaries();
        assertWholeCluster("supplementary scalar", "𑰀");
        assertWholeCluster("emoji ZWJ family", "👨\u200d👩\u200d👧\u200d👦");
        assertWholeCluster("emoji modifier", "👍🏽");
        assertWholeCluster("regional-indicator flag", "🇳🇵");
        assertWholeCluster("CRLF", "\r\n");
        assertEquals(
                "unrelated ZWJ does not absorb following Latin letter",
                2,
                GraphemeBackspace.previousBoundary("a\u200db")
        );
        assertEquals(
                "emoji ZWJ does not absorb unrelated Latin suffix",
                3,
                GraphemeBackspace.previousBoundary("👨\u200da")
        );
        assertEquals(
                "Latin ZWJ prefix does not absorb pictograph",
                2,
                GraphemeBackspace.previousBoundary("a\u200d👩")
        );
        assertEquals(
                "leading virama does not gain Devanagari conjunct tailoring",
                2,
                GraphemeBackspace.previousBoundary("्\u200dष")
        );
    }

    private static void assertNewaActionBoundaries() {
        int ownedPrefixLength = NEWA_KA.length() + NEWA_VIRAMA.length();
        for (String joiner : new String[]{"\u200c", "\u200d"}) {
            String continuation = NEWA_KA + NEWA_VIRAMA + joiner + NEWA_KA;
            assertEquals(
                    "Newa joiner continuation preserves base and virama",
                    ownedPrefixLength,
                    GraphemeBackspace.previousBoundary(continuation)
            );
            assertEquals(
                    "prefixed Newa continuation preserves base and virama",
                    1 + ownedPrefixLength,
                    GraphemeBackspace.previousBoundary("x" + continuation)
            );
            assertEquals(
                    "clipped Newa suffix deletes only joiner and continuation",
                    NEWA_VIRAMA.length(),
                    GraphemeBackspace.previousBoundary(
                            NEWA_VIRAMA + joiner + NEWA_KA
                    )
            );
            assertEquals(
                    "marked Newa continuation does not orphan its joiner",
                    ownedPrefixLength,
                    GraphemeBackspace.previousBoundary(
                            continuation + NEWA_VOWEL_SIGN_AA
                    )
            );
        }
        assertTrue(
                "Newa window without virama remains incomplete",
                !GraphemeBackspace.hasCompleteTrailingGrapheme(
                        "\u200d" + NEWA_KA,
                        GraphemeBackspace.COMMITTED_CONTEXT_UTF16_LIMIT,
                        GraphemeBackspace.COMMITTED_CONTEXT_UTF16_LIMIT + 1
                )
        );
        String manual = NEWA_KA + NEWA_VIRAMA + NEWA_KA;
        assertEquals(
                "manual Newa continuation deletes one consonant tap",
                ownedPrefixLength,
                GraphemeBackspace.previousBoundary(manual)
        );
        assertEquals(
                "manual Newa virama deletes one virama tap",
                NEWA_KA.length(),
                GraphemeBackspace.previousBoundary(NEWA_KA + NEWA_VIRAMA)
        );
    }

    private static void verifyNewaJoinerDeletion(
            KeyboardProfile newa,
            KeyboardProfile nepali,
            NoOpSuggestionEngine engine
    ) {
        String ownedPrefix = NEWA_KA + NEWA_VIRAMA;
        for (String joiner : new String[]{"\u200c", "\u200d"}) {
            RecordingTextSink sink = new RecordingTextSink();
            ComposingSession session = new ComposingSession(engine);
            session.start(newa, true, false, sink);
            appendNewaBaseAndVirama(session, sink);
            int beforeJoiner = sink.editorCalls.size();
            session.appendText(
                    joiner,
                    KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER,
                    sink
            );
            assertEquals(
                    "Newa joiner remains buffered",
                    beforeJoiner,
                    sink.editorCalls.size()
            );
            session.appendText(NEWA_KA, sink);
            assertEquals(
                    "Newa joiner continuation materializes atomically",
                    ownedPrefix + joiner + NEWA_KA,
                    sink.text()
            );
            session.appendText(NEWA_VOWEL_SIGN_AA, sink);
            assertEquals(
                    "Newa continuation accepts a trailing vowel-sign tap",
                    ownedPrefix + joiner + NEWA_KA + NEWA_VOWEL_SIGN_AA,
                    sink.text()
            );
            assertNoEditorCallEndsInJoiner("Newa atomic continuation", sink.editorCalls);
            session.delete(sink);
            assertEquals(
                    "Newa delete preserves the user-owned base and virama",
                    ownedPrefix,
                    sink.text()
            );
            session.delete(sink);
            assertEquals(
                    "Newa second delete removes only the virama tap",
                    NEWA_KA,
                    sink.text()
            );
            session.delete(sink);
            assertEquals("Newa third delete removes the base tap", "", sink.text());
        }

        for (String joiner : new String[]{"\u200c", "\u200d"}) {
            RecordingTextSink pendingSink = new RecordingTextSink();
            ComposingSession pending = new ComposingSession(engine);
            pending.start(newa, true, false, pendingSink);
            appendNewaBaseAndVirama(pending, pendingSink);
            pending.appendText(
                    joiner,
                    KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER,
                    pendingSink
            );
            int beforePendingDelete = pendingSink.editorCalls.size();
            pending.delete(pendingSink);
            assertEquals(
                    "pending Newa joiner delete makes no editor call",
                    beforePendingDelete,
                    pendingSink.editorCalls.size()
            );
            assertEquals(
                    "pending Newa delete preserves typed text",
                    ownedPrefix,
                    pendingSink.text()
            );
            assertNoEditorCallEndsInJoiner(
                    "pending Newa delete",
                    pendingSink.editorCalls
            );
        }

        for (String joiner : new String[]{"\u200c", "\u200d"}) {
            RecordingTextSink fallbackSink = new RecordingTextSink();
            ComposingSession fallback = new ComposingSession(engine);
            fallback.start(newa, true, false, fallbackSink);
            appendNewaBaseAndVirama(fallback, fallbackSink);
            fallback.appendText(
                    joiner,
                    KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER,
                    fallbackSink
            );
            fallback.appendText(NEWA_KA, fallbackSink);
            fallbackSink.rejectNextSetComposingText = true;
            fallback.appendText(NEWA_VOWEL_SIGN_AA, fallbackSink);
            assertTrue(
                    "marked Newa fallback loses composing ownership",
                    !fallback.hasComposingText()
            );
            fallback.delete(fallbackSink);
            assertEquals(
                    "committed marked Newa fallback preserves base and virama",
                    ownedPrefix,
                    fallbackSink.text()
            );
            assertNoEditorCallEndsInJoiner(
                    "committed marked Newa fallback",
                    fallbackSink.editorCalls
            );
        }

        for (String invalidContinuation : new String[]{NEWA_A, NEWA_AVAGRAHA}) {
            RecordingTextSink invalidSink = new RecordingTextSink();
            ComposingSession invalid = new ComposingSession(engine);
            invalid.start(newa, true, false, invalidSink);
            appendNewaBaseAndVirama(invalid, invalidSink);
            invalid.appendText(
                    "\u200d",
                    KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER,
                    invalidSink
            );
            invalid.appendText(invalidContinuation, invalidSink);
            assertEquals(
                    "non-consonant Newa continuation drops the joiner",
                    ownedPrefix + invalidContinuation,
                    invalidSink.text()
            );
            assertNoEditorCallEndsInJoiner(
                    "non-consonant Newa continuation",
                    invalidSink.editorCalls
            );
        }

        RecordingTextSink wrongScriptSink = new RecordingTextSink();
        ComposingSession wrongScript = new ComposingSession(engine);
        wrongScript.start(nepali, true, false, wrongScriptSink);
        wrongScript.appendText("क", wrongScriptSink);
        wrongScript.appendText("्", wrongScriptSink);
        wrongScript.appendText(
                "\u200d",
                KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER,
                wrongScriptSink
        );
        wrongScript.appendText("ष", wrongScriptSink);
        assertTrue(
                "Newa joiner policy fails closed outside a Newa profile",
                wrongScriptSink.text().indexOf('\u200d') < 0
        );

        RecordingTextSink wrongViramaSink = new RecordingTextSink();
        ComposingSession wrongVirama = new ComposingSession(engine);
        wrongVirama.start(newa, true, false, wrongViramaSink);
        wrongVirama.appendText(NEWA_KA, wrongViramaSink);
        wrongVirama.appendText("्", wrongViramaSink);
        wrongVirama.appendText(
                "\u200d",
                KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER,
                wrongViramaSink
        );
        wrongVirama.appendText(NEWA_KA, wrongViramaSink);
        assertTrue(
                "Newa joiner requires exact U+11442",
                wrongViramaSink.text().indexOf('\u200d') < 0
        );

        RecordingTextSink privateSink = new RecordingTextSink();
        ComposingSession privateSession = new ComposingSession(engine);
        privateSession.start(newa, true, true, privateSink);
        appendNewaBaseAndVirama(privateSession, privateSink);
        privateSession.appendText(
                "\u200d",
                KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER,
                privateSink
        );
        privateSession.appendText(NEWA_KA, privateSink);
        assertEquals(
                "private Newa input drops an undeletable joiner",
                ownedPrefix + NEWA_KA,
                privateSink.text()
        );
        privateSession.delete(privateSink);
        assertEquals(
                "private Newa delete remains context-free and tap-aware",
                ownedPrefix,
                privateSink.text()
        );
        assertNoEditorCallEndsInJoiner("private Newa path", privateSink.editorCalls);
    }

    private static void appendNewaBaseAndVirama(
            ComposingSession session,
            TextSink sink
    ) {
        session.appendText(NEWA_KA, sink);
        session.appendText(NEWA_VIRAMA, sink);
    }

    private static KeyboardProfile newaFixtureProfile() {
        return new KeyboardProfile(
                "fixture-Newa-NP",
                "new",
                "fixture-newa-direct",
                "new-NP",
                "Nepal Bhasa fixture",
                "Nepal Bhasa fixture",
                "Newa",
                "Newa",
                "Newa direct fixture",
                "direct",
                "layout",
                "fixture-newa-layout",
                KeyboardProfile.LookupKind.SURFACE_PREFIX,
                null,
                "research",
                KeyboardProfile.Availability.BLOCKED,
                "FIXTURE_ONLY",
                "Synthetic Newa runtime fixture.",
                false,
                "language",
                null,
                null,
                "nepal bhasa fixture|newa",
                Collections.emptyList(),
                Collections.emptyList()
        );
    }

    private static void assertWholeCluster(String label, String cluster) {
        assertEquals(label + " full boundary", 0, GraphemeBackspace.previousBoundary(cluster));
        String prefixed = "x" + cluster;
        assertEquals(
                label + " prefixed boundary",
                1,
                GraphemeBackspace.previousBoundary(prefixed)
        );
    }

    private static void verifyOwnedComposingDeletion(
            KeyboardProfile english,
            KeyboardProfile nepali,
            KeyboardProfile newa
    ) {
        NoOpSuggestionEngine engine = new NoOpSuggestionEngine();
        try {
            RecordingTextSink nepaliSink = new RecordingTextSink();
            ComposingSession nepaliSession = new ComposingSession(engine);
            nepaliSession.start(nepali, true, false, nepaliSink);
            nepaliSession.appendText("क", nepaliSink);
            nepaliSession.appendText("ि", nepaliSink);
            SuggestionQuery matraOwner = nepaliSession.beginSuggestionDispatch().query();
            assertTrue("Nepali matra owns a suggestion request", matraOwner != null);
            nepaliSession.delete(nepaliSink);
            assertEquals("Nepali matra deletes atomically", "", nepaliSink.text());
            assertTrue(
                    "grapheme delete cancels the prior suggestion",
                    matraOwner.cancellation().isCancelled()
            );
            assertTrue(
                    "grapheme delete clears suggestion ownership",
                    nepaliSession.activeSuggestionQueryForTesting() == null
            );

            RecordingTextSink conjunctSink = new RecordingTextSink();
            ComposingSession conjunct = new ComposingSession(engine);
            conjunct.start(nepali, true, false, conjunctSink);
            conjunct.appendText("क", conjunctSink);
            conjunct.appendText("्", conjunctSink);
            conjunct.appendText(
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    conjunctSink
            );
            conjunct.appendText("ष", conjunctSink);
            assertEquals("resolved conjunct fixture", "क्\u200dष", conjunctSink.text());
            conjunct.delete(conjunctSink);
            assertEquals("resolved conjunct deletes atomically", "", conjunctSink.text());
            assertNoEditorCallEndsInJoiner("resolved conjunct delete", conjunctSink.editorCalls);

            RecordingTextSink pendingSink = new RecordingTextSink();
            ComposingSession pending = new ComposingSession(engine);
            pending.start(nepali, true, false, pendingSink);
            pending.appendText("क", pendingSink);
            pending.appendText("्", pendingSink);
            pending.appendText(
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    pendingSink
            );
            int beforePendingDelete = pendingSink.editorCalls.size();
            pending.delete(pendingSink);
            assertEquals(
                    "pending joiner delete makes no editor call",
                    beforePendingDelete,
                    pendingSink.editorCalls.size()
            );
            assertNoEditorCallEndsInJoiner("pending joiner delete", pendingSink.editorCalls);

            verifyNewaJoinerDeletion(newa, nepali, engine);

            RecordingTextSink touchSink = new RecordingTextSink();
            ComposingSession touchSession = new ComposingSession(engine);
            touchSession.start(english, true, false, touchSink);
            appendWithStroke(touchSession, english, "x", "fixture.x", touchSink);
            appendWithStroke(touchSession, english, "e", "fixture.e", touchSink);
            appendWithStroke(touchSession, english, "\u0301", "fixture.acute", touchSink);
            touchSession.delete(touchSink);
            assertEquals("touch-aligned grapheme suffix deletes", "x", touchSink.text());
            SuggestionQuery remaining = touchSession.beginSuggestionDispatch().query();
            assertTrue("remaining prefix owns a suggestion request", remaining != null);
            assertEquals(
                    "all strokes belonging to deleted grapheme are removed",
                    1,
                    remaining.touchSequence().strokes().size()
            );
            assertEquals(
                    "remaining touch stroke stays exact",
                    "x",
                    remaining.touchSequence().strokes().get(0).emittedText()
            );

            RecordingTextSink retainedTailSink = new RecordingTextSink();
            ComposingSession retainedTail = new ComposingSession(engine);
            retainedTail.start(nepali, true, false, retainedTailSink);
            retainedTail.appendText("क", retainedTailSink);
            retainedTail.appendText("क", retainedTailSink);
            retainedTail.appendText("्", retainedTailSink);
            retainedTail.delete(retainedTailSink);
            assertEquals("partial delete retains first Devanagari base", "क", retainedTailSink.text());
            retainedTail.appendText("्", retainedTailSink);
            retainedTail.appendText(
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    retainedTailSink
            );
            retainedTail.appendText("ष", retainedTailSink);
            assertEquals(
                    "partial delete rebuilds Devanagari joiner ownership",
                    "क्\u200dष",
                    retainedTailSink.text()
            );
            assertNoEditorCallEndsInJoiner(
                    "rebuilt Devanagari tail",
                    retainedTailSink.editorCalls
            );

            RecordingTextSink committedTailSink = new RecordingTextSink();
            ComposingSession committedTail = new ComposingSession(engine);
            committedTail.start(nepali, true, false, committedTailSink);
            committedTail.appendText("क", committedTailSink);
            committedTail.appendText("क", committedTailSink);
            committedTail.appendText("्", committedTailSink);
            committedTailSink.rejectNextSetComposingText = true;
            committedTail.delete(committedTailSink);
            assertEquals(
                    "commit fallback retains first Devanagari base",
                    "क",
                    committedTailSink.text()
            );
            committedTail.appendText("्", committedTailSink);
            committedTail.appendText(
                    "\u200d",
                    KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER,
                    committedTailSink
            );
            committedTail.appendText("ष", committedTailSink);
            assertEquals(
                    "commit fallback rebuilds Devanagari joiner ownership",
                    "क्\u200dष",
                    committedTailSink.text()
            );
            assertNoEditorCallEndsInJoiner(
                    "commit-fallback Devanagari tail",
                    committedTailSink.editorCalls
            );
        } finally {
            engine.close();
        }
    }

    private static void appendWithStroke(
            ComposingSession session,
            KeyboardProfile profile,
            String text,
            String keyId,
            TextSink sink
    ) {
        session.appendText(
                text,
                KeySpec.InputPolicy.DEFAULT,
                SpatialKeyStroke.nonSpatial(
                        profile.layoutId(),
                        profile.layoutRevision(),
                        profile.layoutSourceSha256(),
                        1L,
                        keyId,
                        text,
                        KeySpec.InputPolicy.DEFAULT
                ),
                sink
        );
    }

    private static void verifyCommittedDeletion(
            Instrumentation instrumentation,
            Context context
    ) {
        instrumentation.runOnMainSync(() -> {
            for (String cluster : new String[]{
                    "e\u0301",
                    "कि",
                    "क्\u200dष",
                    "𑰀",
                    "👨\u200d👩\u200d👧\u200d👦",
                    "👍🏽",
                    "🇳🇵",
                    "\r\n"
            }) {
                EditorFixture fixture = editorFixture(context, "x" + cluster);
                assertTrue(
                        "committed cluster delete succeeds",
                        fixture.sink(true).deletePreviousGrapheme()
                );
                assertEquals("committed cluster deletes atomically", "x", fixture.text());
                assertEquals("committed delete reads once", 1, fixture.connection.contextReads);
                assertEquals("committed delete uses UTF-16 boundary", 1, fixture.connection.utf16Deletes);
                assertEquals("committed delete avoids fallback", 0, fixture.connection.codePointDeletes);
            }

            for (String joiner : new String[]{"\u200c", "\u200d"}) {
                String ownedPrefix = "x" + NEWA_KA + NEWA_VIRAMA;
                EditorFixture markedNewa = editorFixture(
                        context,
                        ownedPrefix + joiner + NEWA_KA + NEWA_VOWEL_SIGN_AA
                );
                assertTrue(
                        "committed marked Newa delete succeeds",
                        markedNewa.sink(true).deletePreviousGrapheme()
                );
                assertEquals(
                        "committed marked Newa delete preserves base and virama",
                        ownedPrefix,
                        markedNewa.text()
                );
                assertEquals(
                        "committed marked Newa delete avoids fallback",
                        0,
                        markedNewa.connection.codePointDeletes
                );
            }

            EditorFixture privateFixture = editorFixture(context, "e\u0301");
            assertTrue(
                    "private delete fallback succeeds",
                    privateFixture.sink(false).deletePreviousGrapheme()
            );
            assertEquals("private delete never reads context", 0, privateFixture.connection.contextReads);
            assertEquals("private delete uses code-point fallback", 1, privateFixture.connection.codePointDeletes);
            assertEquals("private fallback deletes only final code point", "e", privateFixture.text());

            EditorFixture missingContext = editorFixture(context, "e\u0301");
            missingContext.connection.returnNullContext = true;
            assertTrue(
                    "missing context falls back",
                    missingContext.sink(true).deletePreviousGrapheme()
            );
            assertEquals("missing-context fallback result", "e", missingContext.text());
            assertEquals("missing-context code-point fallback", 1, missingContext.connection.codePointDeletes);

            EditorFixture rejectedMutation = editorFixture(context, "e\u0301");
            rejectedMutation.connection.rejectUtf16Delete = true;
            assertTrue(
                    "rejected grapheme mutation falls back",
                    rejectedMutation.sink(true).deletePreviousGrapheme()
            );
            assertEquals("rejected mutation fallback result", "e", rejectedMutation.text());
            assertEquals("rejected mutation attempted once", 1, rejectedMutation.connection.utf16Deletes);
            assertEquals("rejected mutation used fallback", 1, rejectedMutation.connection.codePointDeletes);

            EditorFixture truncated = editorFixture(
                    context,
                    "x" + repeatForTesting(
                            "\u0301",
                            GraphemeBackspace.COMMITTED_CONTEXT_UTF16_LIMIT
                    )
            );
            assertTrue(
                    "truncated cluster context falls back",
                    truncated.sink(true).deletePreviousGrapheme()
            );
            assertEquals(
                    "truncated-context fallback deletes one code point",
                    "x" + repeatForTesting(
                            "\u0301",
                            GraphemeBackspace.COMMITTED_CONTEXT_UTF16_LIMIT - 1
                    ),
                    truncated.text()
            );
            assertEquals("truncated context does not bulk-delete", 0, truncated.connection.utf16Deletes);
            assertEquals("truncated context uses fallback", 1, truncated.connection.codePointDeletes);

            EditorFixture clippedShort = editorFixture(context, "xe\u0301");
            clippedShort.connection.forcedContext = "e\u0301";
            assertTrue(
                    "short editor context falls back",
                    clippedShort.sink(true).deletePreviousGrapheme()
            );
            assertEquals("short-context fallback result", "xe", clippedShort.text());
            assertEquals("short context does not bulk-delete", 0, clippedShort.connection.utf16Deletes);
            assertEquals("short context uses fallback", 1, clippedShort.connection.codePointDeletes);

            String clippedNewaOwned = "x"
                    + NEWA_KA
                    + repeatForTesting(NEWA_VOWEL_SIGN_U, 32)
                    + NEWA_VIRAMA;
            for (String joiner : new String[]{"\u200c", "\u200d"}) {
                EditorFixture clippedNewa = editorFixture(
                        context,
                        clippedNewaOwned + joiner + NEWA_KA
                );
                assertTrue(
                        "clipped Newa committed delete succeeds",
                        clippedNewa.sink(true).deletePreviousGrapheme()
                );
                assertEquals(
                        "clipped Newa delete preserves the virama",
                        clippedNewaOwned,
                        clippedNewa.text()
                );
                assertEquals(
                        "clipped Newa delete reads once",
                        1,
                        clippedNewa.connection.contextReads
                );
                assertEquals(
                        "clipped Newa delete uses bounded UTF-16 deletion",
                        1,
                        clippedNewa.connection.utf16Deletes
                );
                assertEquals(
                        "clipped Newa delete avoids code-point fallback",
                        0,
                        clippedNewa.connection.codePointDeletes
                );
            }

            EditorFixture selected = editorFixture(context, "abc");
            selected.editor.setSelection(1, 2);
            InputConnectionTextSink selectedSink = selected.sink(true);
            assertTrue("selected text delete succeeds", selectedSink.deletePreviousGrapheme());
            assertEquals("selected text is deleted before surrounding text", "ac", selected.text());
            assertEquals("selected text delete does not read context", 0, selected.connection.contextReads);
            assertEquals("selected text delete does not bulk-delete", 0, selected.connection.utf16Deletes);
            assertEquals("selected text delete does not use code-point path", 0, selected.connection.codePointDeletes);
            assertTrue("second quick delete is dispatched", selectedSink.deletePreviousGrapheme());
            assertEquals("stale selection is not replaced twice", 1, selected.connection.commits);
            assertEquals("second quick delete uses key-event fallback", 2, selected.connection.keyEvents);

            EditorFixture privateSelected = editorFixture(context, "abc");
            privateSelected.editor.setSelection(1, 2);
            assertTrue(
                    "private selected text delete succeeds",
                    privateSelected.sink(false).deletePreviousGrapheme()
            );
            assertEquals("private selected text is deleted", "ac", privateSelected.text());
            assertEquals("private selected text never reads context", 0, privateSelected.connection.contextReads);

            EditorFixture unknownSelection = editorFixture(context, "abc");
            new InputConnectionTextSink(
                    unknownSelection.connection,
                    true,
                    -1,
                    -1
            ).deletePreviousGrapheme();
            assertEquals("unknown selection never reads context", 0, unknownSelection.connection.contextReads);
        });
        instrumentation.waitForIdleSync();
    }

    private static EditorFixture editorFixture(Context context, String text) {
        EditText editor = new EditText(context);
        editor.setText(text);
        editor.setSelection(editor.length());
        InputConnection base = editor.onCreateInputConnection(new EditorInfo());
        assertTrue("EditText InputConnection exists", base != null);
        return new EditorFixture(editor, new TrackingInputConnection(base));
    }

    private static String repeatForTesting(String value, int count) {
        StringBuilder repeated = new StringBuilder(value.length() * count);
        for (int index = 0; index < count; index++) {
            repeated.append(value);
        }
        return repeated.toString();
    }

    private static void verifyRepeatController() {
        FakeScheduler scheduler = new FakeScheduler();
        AtomicInteger deletes = new AtomicInteger();
        DeleteRepeatController controller = new DeleteRepeatController(scheduler);
        controller.start(deletes::incrementAndGet);
        assertEquals("delete dispatches immediately on down", 1, deletes.get());
        assertEquals("total dispatch count records immediate delete", 1L, controller.totalDispatchCount());
        assertEquals(
                "delete repeat uses initial delay",
                DeleteRepeatController.INITIAL_DELAY_MILLIS,
                scheduler.delayMillis
        );
        scheduler.runPending();
        assertEquals("first held repeat dispatches", 2, deletes.get());
        assertEquals(
                "held delete uses bounded cadence",
                DeleteRepeatController.REPEAT_INTERVAL_MILLIS,
                scheduler.delayMillis
        );
        Runnable stale = scheduler.pending;
        controller.stop();
        long dispatchesAtStop = controller.totalDispatchCount();
        assertTrue("delete repeat stops", !controller.isActive());
        stale.run();
        assertEquals("stale stopped generation cannot delete", 2, deletes.get());
        assertEquals(
                "stale stopped generation cannot advance total dispatch count",
                dispatchesAtStop,
                controller.totalDispatchCount()
        );

        controller.start(deletes::incrementAndGet);
        Runnable superseded = scheduler.pending;
        controller.start(deletes::incrementAndGet);
        int afterRestart = deletes.get();
        superseded.run();
        assertEquals("superseded generation cannot delete", afterRestart, deletes.get());
        controller.stop();

        AtomicInteger boundedDeletes = new AtomicInteger();
        controller.start(boundedDeletes::incrementAndGet);
        while (controller.isActive()) {
            scheduler.runPending();
        }
        assertEquals(
                "one hold has a hard dispatch bound",
                DeleteRepeatController.MAX_DISPATCHES_PER_HOLD,
                boundedDeletes.get()
        );
        assertTrue("bounded hold leaves no callback", scheduler.pending == null);
    }

    private static void verifyRenderedDeleteWiring(
            Instrumentation instrumentation,
            Context context,
            KeyboardProfile english
    ) {
        AtomicInteger deletes = new AtomicInteger();
        instrumentation.runOnMainSync(() -> {
            KeyboardSurface surface = new KeyboardSurface(context);
            surface.setListener(new KeyboardSurface.Listener() {
                @Override
                public void onKey(KeySpec key, SpatialKeyStroke stroke) {
                    if (key.action() == KeySpec.Action.DELETE) {
                        deletes.incrementAndGet();
                    }
                }

                @Override
                public void onLanguagePickerRequested(android.view.View source) {
                }
            });
            KeyboardLayouts.Layout layout = KeyboardLayouts.forProfile(
                    english,
                    false,
                    false,
                    false
            );
            surface.render(layout);
            assertTrue(
                    "short delete touch is handled",
                    surface.performActionKeyTouchForTesting(KeySpec.Action.DELETE)
            );
            assertEquals("short delete touch is one-shot", 1, deletes.get());
            assertTrue("short delete touch stops repeat", !surface.deleteRepeatActiveForTesting());
            assertTrue("programmatic delete click is handled", surface.performKeyIdForTesting("base.r3.k4"));
            assertEquals("programmatic delete click is one-shot", 2, deletes.get());
            assertTrue("programmatic delete does not arm repeat", !surface.deleteRepeatActiveForTesting());
            assertTrue(
                    "held delete down is handled",
                    surface.beginActionKeyTouchForTesting(KeySpec.Action.DELETE)
            );
            assertEquals("held delete down dispatches once", 3, deletes.get());
            assertTrue("held delete arms repeat", surface.deleteRepeatActiveForTesting());
            surface.render(layout);
            assertTrue("rerender cancels held delete", !surface.deleteRepeatActiveForTesting());
            assertTrue(
                    "cancelled delete touch is handled",
                    surface.beginActionKeyTouchForTesting(KeySpec.Action.DELETE)
                            && surface.finishActionKeyTouchForTesting(
                            KeySpec.Action.DELETE,
                            true
                    )
            );
            assertEquals("cancelled touch only dispatched down", 4, deletes.get());
            assertTrue("ACTION_CANCEL stops held delete", !surface.deleteRepeatActiveForTesting());
            assertTrue(
                    "pointer-owned delete down is handled",
                    surface.beginActionKeyTouchForTesting(KeySpec.Action.DELETE)
            );
            assertTrue(
                    "owner pointer-up is handled while another pointer remains",
                    surface.releaseDeleteOwnerWithSecondaryPointerForTesting()
            );
            assertTrue(
                    "owner pointer-up stops held delete",
                    !surface.deleteRepeatActiveForTesting()
            );
            assertTrue(
                    "non-owner pointer fixture arms delete",
                    surface.beginActionKeyTouchForTesting(KeySpec.Action.DELETE)
            );
            assertTrue(
                    "non-owner pointer-up is handled",
                    surface.releaseDeleteNonOwnerWithSecondaryPointerForTesting()
            );
            assertTrue(
                    "non-owner pointer-up preserves held delete",
                    surface.deleteRepeatActiveForTesting()
            );
            assertEquals("non-owner pointer-up does not dispatch delete", 6, deletes.get());
            assertTrue(
                    "owner release after non-owner is handled",
                    surface.finishActionKeyTouchForTesting(KeySpec.Action.DELETE, false)
            );
            assertTrue(
                    "owner release after non-owner stops held delete",
                    !surface.deleteRepeatActiveForTesting()
            );
            assertTrue(
                    "service-facing cancellation fixture arms delete",
                    surface.beginActionKeyTouchForTesting(KeySpec.Action.DELETE)
            );
            surface.cancelDeleteRepeat();
            assertTrue(
                    "service-facing cancellation stops held delete",
                    !surface.deleteRepeatActiveForTesting()
            );
            assertTrue(
                    "detach fixture arms delete",
                    surface.beginActionKeyTouchForTesting(KeySpec.Action.DELETE)
            );
            surface.onDetachedFromWindow();
            assertTrue("detach stops held delete", !surface.deleteRepeatActiveForTesting());
        });
        instrumentation.waitForIdleSync();
    }

    private static void assertNoEditorCallEndsInJoiner(String label, List<String> calls) {
        for (String call : calls) {
            assertTrue(
                    label + " does not expose an isolated joiner",
                    !call.endsWith("\u200c") && !call.endsWith("\u200d")
            );
        }
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

    static final class Evidence {
        private Evidence() {
        }
    }

    private static final class FakeScheduler implements DeleteRepeatController.Scheduler {
        Runnable pending;
        long delayMillis;

        @Override
        public void postDelayed(Runnable runnable, long delayMillis) {
            if (pending != null) {
                throw new AssertionError("delete repeat queued more than one callback");
            }
            pending = runnable;
            this.delayMillis = delayMillis;
        }

        @Override
        public void remove(Runnable runnable) {
            if (pending == runnable) {
                pending = null;
            }
        }

        void runPending() {
            Runnable runnable = pending;
            if (runnable == null) {
                throw new AssertionError("delete repeat callback is missing");
            }
            pending = null;
            runnable.run();
        }
    }

    private static final class EditorFixture {
        final EditText editor;
        final TrackingInputConnection connection;

        EditorFixture(EditText editor, TrackingInputConnection connection) {
            this.editor = editor;
            this.connection = connection;
        }

        String text() {
            return editor.getText().toString();
        }

        InputConnectionTextSink sink(boolean allowCommittedDeleteContext) {
            return new InputConnectionTextSink(
                    connection,
                    allowCommittedDeleteContext,
                    editor.getSelectionStart(),
                    editor.getSelectionEnd()
            );
        }
    }

    private static final class TrackingInputConnection extends InputConnectionWrapper {
        int contextReads;
        int utf16Deletes;
        int codePointDeletes;
        int commits;
        int keyEvents;
        boolean returnNullContext;
        boolean rejectUtf16Delete;
        String forcedContext;

        TrackingInputConnection(InputConnection target) {
            super(target, false);
        }

        @Override
        public boolean commitText(CharSequence text, int newCursorPosition) {
            commits++;
            return super.commitText(text, newCursorPosition);
        }

        @Override
        public boolean sendKeyEvent(android.view.KeyEvent event) {
            keyEvents++;
            return true;
        }

        @Override
        public CharSequence getTextBeforeCursor(int length, int flags) {
            contextReads++;
            if (returnNullContext) {
                return null;
            }
            if (forcedContext != null) {
                return forcedContext;
            }
            return super.getTextBeforeCursor(length, flags);
        }

        @Override
        public boolean deleteSurroundingText(int beforeLength, int afterLength) {
            utf16Deletes++;
            return !rejectUtf16Delete
                    && super.deleteSurroundingText(beforeLength, afterLength);
        }

        @Override
        public boolean deleteSurroundingTextInCodePoints(
                int beforeLength,
                int afterLength
        ) {
            codePointDeletes++;
            return super.deleteSurroundingTextInCodePoints(beforeLength, afterLength);
        }
    }

    private static final class RecordingTextSink implements TextSink {
        final List<String> editorCalls = new ArrayList<>();
        private String committed = "";
        private String composing = "";
        boolean rejectNextSetComposingText;

        @Override
        public boolean setComposingText(String text) {
            if (rejectNextSetComposingText) {
                rejectNextSetComposingText = false;
                editorCalls.add("reject-set:" + text);
                return false;
            }
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
            editorCalls.add("delete-grapheme");
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
            if (!committed.isEmpty()) {
                int boundary = committed.offsetByCodePoints(committed.length(), -1);
                committed = committed.substring(0, boundary);
            }
            return true;
        }

        String text() {
            return committed + composing;
        }
    }
}
