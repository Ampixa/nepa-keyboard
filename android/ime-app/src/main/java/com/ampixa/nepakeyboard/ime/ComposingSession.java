package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.LongSupplier;

/**
 * Owns one active word and its editor composing span.
 *
 * <p>The session never reads surrounding editor text. This makes candidate
 * replacement deterministic and keeps private fields outside the prediction
 * boundary.</p>
 */
public final class ComposingSession {
    private static final int DEVANAGARI_VIRAMA = 0x094d;
    private static final int NEWA_VIRAMA = 0x11442;
    private static final String ZERO_WIDTH_NON_JOINER = "\u200c";
    private static final String ZERO_WIDTH_JOINER = "\u200d";

    private enum ScriptTail {
        NONE,
        BASE,
        AFTER_VIRAMA
    }

    private final SuggestionEngine suggestionEngine;
    private final LongSupplier nanoClock;
    private final long suggestionDeadlineBudgetNanos;
    private SuggestionActivation suggestionActivation;
    private SuggestionQuery activeSuggestionQuery;
    private SuggestionSnapshot currentSuggestionSnapshot;
    private long nextSuggestionGeneration;
    private KeyboardProfile profile;
    private String composingText = "";
    private boolean composingAllowed;
    private boolean privateField;
    private ScriptTail devanagariTail = ScriptTail.NONE;
    private ScriptTail newaTail = ScriptTail.NONE;
    private String pendingJoiner;
    private String pendingJoinerScript;
    private boolean pendingJoinerMayTerminate;
    private final List<SpatialKeyStroke> composingStrokes = new ArrayList<>();
    private boolean touchAlignmentValid = true;

    public ComposingSession(SuggestionEngine suggestionEngine) {
        this(
                suggestionEngine,
                System::nanoTime,
                SuggestionQuery.DEFAULT_DEADLINE_BUDGET_NANOS
        );
    }

    ComposingSession(
            SuggestionEngine suggestionEngine,
            LongSupplier nanoClock,
            long suggestionDeadlineBudgetNanos
    ) {
        this.suggestionEngine = Objects.requireNonNull(suggestionEngine, "suggestionEngine");
        this.nanoClock = Objects.requireNonNull(nanoClock, "nanoClock");
        if (suggestionDeadlineBudgetNanos <= 0L
                || suggestionDeadlineBudgetNanos
                > SuggestionQuery.MAX_DEADLINE_BUDGET_NANOS) {
            throw new IllegalArgumentException("suggestion deadline budget is outside the bound");
        }
        this.suggestionDeadlineBudgetNanos = suggestionDeadlineBudgetNanos;
        suggestionActivation = suggestionEngine.suspend();
    }

    public void start(
            KeyboardProfile profile,
            boolean composingAllowed,
            boolean privateField,
            TextSink sink
    ) {
        Objects.requireNonNull(profile, "profile");
        Objects.requireNonNull(sink, "sink");
        finish(sink);
        this.profile = profile;
        this.privateField = privateField;
        this.composingAllowed = composingAllowed && !privateField;
        clearKeyboardContext();
        clearTouchSequence();
        suggestionActivation = this.composingAllowed
                ? suggestionEngine.activate(profile)
                : suggestionEngine.suspend();
    }

    public void reset(
            KeyboardProfile profile,
            boolean composingAllowed,
            boolean privateField
    ) {
        cancelSuggestionQuery();
        this.profile = Objects.requireNonNull(profile, "profile");
        this.privateField = privateField;
        this.composingAllowed = composingAllowed && !privateField;
        composingText = "";
        clearKeyboardContext();
        clearTouchSequence();
        suggestionActivation = this.composingAllowed
                ? suggestionEngine.activate(profile)
                : suggestionEngine.suspend();
    }

    public void switchProfile(
            KeyboardProfile profile,
            boolean composingAllowed,
            boolean privateField,
            TextSink sink
    ) {
        Objects.requireNonNull(profile, "profile");
        Objects.requireNonNull(sink, "sink");
        cancelSuggestionQuery();
        clearPendingJoiner();
        commitRaw(sink);
        this.profile = profile;
        this.privateField = privateField;
        this.composingAllowed = composingAllowed && !privateField;
        clearKeyboardContext();
        clearTouchSequence();
        suggestionActivation = this.composingAllowed
                ? suggestionEngine.activate(profile)
                : suggestionEngine.suspend();
    }

    public void appendText(String text, TextSink sink) {
        appendText(text, KeySpec.InputPolicy.DEFAULT, null, sink);
    }

    public void appendText(
            String text,
            KeySpec.InputPolicy inputPolicy,
            TextSink sink
    ) {
        appendText(text, inputPolicy, null, sink);
    }

    public void appendText(
            String text,
            KeySpec.InputPolicy inputPolicy,
            SpatialKeyStroke stroke,
            TextSink sink
    ) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(inputPolicy, "inputPolicy");
        Objects.requireNonNull(sink, "sink");
        if (text.isEmpty()) {
            return;
        }
        validatePolicyPayload(text, inputPolicy);
        if (stroke != null && (profile == null
                || !stroke.matchesProfile(profile)
                || !text.equals(stroke.emittedText())
                || inputPolicy != stroke.inputPolicy())) {
            throw new IllegalArgumentException("text key stroke does not match active input");
        }
        cancelSuggestionQuery();
        if (inputPolicy == KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER
                || inputPolicy == KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ
                || inputPolicy == KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER) {
            invalidateTouchAlignment();
            bufferConjunctJoiner(
                    text,
                    inputPolicy == KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER
                            ? "Newa"
                            : "Deva",
                    inputPolicy == KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ
            );
            return;
        }

        String emittedText = text;
        boolean conjunctContinuation = false;
        if (pendingJoiner != null) {
            String bufferedJoiner = pendingJoiner;
            if (inputPolicy == KeySpec.InputPolicy.DEFAULT
                    && startsWithPendingJoinerLetter(text)
                    && canMaterializePendingJoiner()) {
                clearPendingJoiner();
                emittedText = bufferedJoiner + text;
                conjunctContinuation = true;
            } else if (!pendingJoinerMayTerminate
                    || !composingAllowed
                    || canAppendToComposingToken(text, inputPolicy)) {
                // Non-letter word continuations cannot materialize a terminal
                // joiner. Boundaries leave it pending for commitRaw below.
                clearPendingJoiner();
            }
        }

        if (!composingAllowed) {
            clearTouchSequence();
            if (sink.commitText(emittedText)) {
                updateDevanagariTail(emittedText);
            } else {
                clearKeyboardContext();
            }
            return;
        }
        if (!conjunctContinuation && !canAppendToComposingToken(text, inputPolicy)) {
            commitRaw(sink);
            if (sink.commitText(emittedText)) {
                updateDevanagariTail(emittedText);
            }
            return;
        }
        if (conjunctContinuation && composingText.isEmpty()) {
            clearTouchSequence();
            if (sink.commitText(emittedText)) {
                updateDevanagariTail(emittedText);
            } else {
                clearKeyboardContext();
            }
            return;
        }

        String updated = composingText + emittedText;
        String previous = composingText;
        if (sink.setComposingText(updated)) {
            composingText = updated;
            recordTouchStroke(previous, emittedText, stroke);
            updateDevanagariTail(emittedText);
        } else {
            // commitText replaces an existing composing span, avoiding duplicate text.
            if (sink.commitText(updated)) {
                updateDevanagariTail(emittedText);
            } else {
                clearKeyboardContext();
            }
            composingText = "";
            clearTouchSequence();
        }
    }

    public void delete(TextSink sink) {
        Objects.requireNonNull(sink, "sink");
        cancelSuggestionQuery();
        if (pendingJoiner != null) {
            clearPendingJoiner();
            return;
        }
        clearKeyboardContext();
        if (composingText.isEmpty()) {
            clearTouchSequence();
            sink.deletePreviousGrapheme();
            return;
        }

        int end = GraphemeBackspace.previousBoundary(composingText);
        if (end < 0 || end >= composingText.length()) {
            end = composingText.offsetByCodePoints(composingText.length(), -1);
        }
        String updated = composingText.substring(0, end);
        if (updated.isEmpty()) {
            if (!sink.setComposingText("") && !sink.commitText("")) {
                rebuildDevanagariTail(composingText);
                return;
            }
            sink.finishComposingText();
            composingText = "";
            clearTouchSequence();
        } else if (sink.setComposingText(updated)) {
            updateTouchAfterDelete(composingText, updated);
            composingText = updated;
            rebuildDevanagariTail(updated);
        } else if (sink.commitText(updated)) {
            composingText = "";
            clearTouchSequence();
            rebuildDevanagariTail(updated);
        } else {
            rebuildDevanagariTail(composingText);
        }
    }

    public boolean selectCandidate(String candidate, TextSink sink) {
        Objects.requireNonNull(candidate, "candidate");
        Objects.requireNonNull(sink, "sink");
        if (candidate.isEmpty() || privateField || composingText.isEmpty()) {
            return false;
        }
        cancelSuggestionQuery();
        if (!sink.commitText(candidate)) {
            clearKeyboardContext();
            return false;
        }
        composingText = "";
        clearTouchSequence();
        clearKeyboardContext();
        return true;
    }

    public boolean selectCandidate(
            SuggestionQuery owner,
            SuggestionCandidate candidate,
            TextSink sink
    ) {
        Objects.requireNonNull(candidate, "candidate");
        if (!ownsCurrentSuggestionQuery(owner)
                || currentSuggestionSnapshot == null
                || !currentSuggestionSnapshot.belongsTo(owner)
                || currentSuggestionSnapshot.status() != SuggestionSnapshot.Status.READY
                || !currentSuggestionSnapshot.nBestCandidates().contains(candidate)) {
            return false;
        }
        return selectCandidate(candidate.text(), sink);
    }

    public void commitRaw(TextSink sink) {
        Objects.requireNonNull(sink, "sink");
        cancelSuggestionQuery();
        if (!composingText.isEmpty()) {
            String terminalJoiner = pendingJoinerMayTerminate
                    && pendingJoiner != null
                    ? pendingJoiner
                    : "";
            sink.commitText(composingText + terminalJoiner);
            composingText = "";
        }
        clearTouchSequence();
        clearKeyboardContext();
    }

    public void finish(TextSink sink) {
        Objects.requireNonNull(sink, "sink");
        cancelSuggestionQuery();
        if (!composingText.isEmpty()) {
            if (pendingJoinerMayTerminate && pendingJoiner != null) {
                sink.commitText(composingText + pendingJoiner);
            } else {
                sink.finishComposingText();
            }
            composingText = "";
        }
        clearTouchSequence();
        clearKeyboardContext();
    }

    public List<String> candidates() {
        return suggestionSnapshot().candidates();
    }

    /** Starts the latest-wins production request without running provider code. */
    public SuggestionDispatch beginSuggestionDispatch() {
        if (profile == null || privateField || !composingAllowed || composingText.isEmpty()) {
            cancelSuggestionQuery();
            currentSuggestionSnapshot = SuggestionSnapshot.inactive(suggestionActivation);
            return SuggestionDispatch.inactive(currentSuggestionSnapshot);
        }
        String queryText = composingText;
        if (pendingJoinerMayTerminate && pendingJoiner != null) {
            queryText += pendingJoiner;
        }
        cancelSuggestionQuery();
        long generation = nextSuggestionGeneration();
        long createdAtNanos = nanoClock.getAsLong();
        SuggestionQuery query = SuggestionQuery.decoderRequest(
                suggestionActivation,
                profile,
                queryText,
                false,
                generation,
                createdAtNanos,
                createdAtNanos + suggestionDeadlineBudgetNanos,
                new SuggestionCancellation(),
                currentTouchSequence(queryText)
        );
        activeSuggestionQuery = query;
        currentSuggestionSnapshot = SuggestionSnapshot.literalFallback(query);
        return SuggestionDispatch.active(query);
    }

    /** Main-thread acceptance; stale callbacks leave the newer snapshot unchanged. */
    public boolean acceptSuggestionResult(
            SuggestionQuery query,
            SuggestionSnapshot snapshot
    ) {
        if (!ownsCurrentSuggestionQuery(query)
                || query.cancellation().isCancelled()) {
            return false;
        }
        if (query.isExpired(nanoClock.getAsLong())
                || snapshot == null
                || !snapshot.belongsTo(query)) {
            expireSuggestionQuery(query);
            return false;
        }
        currentSuggestionSnapshot = snapshot;
        return true;
    }

    /** Main-thread timeout/failure path; it preserves exact literal input. */
    public boolean expireSuggestionQuery(SuggestionQuery query) {
        if (!ownsCurrentSuggestionQuery(query)) {
            return false;
        }
        currentSuggestionSnapshot = SuggestionSnapshot.literalFallback(query);
        suggestionEngine.cancel(query);
        return true;
    }

    public SuggestionSnapshot currentSuggestionSnapshot() {
        return currentSuggestionSnapshot;
    }

    public boolean ownsCurrentSuggestionQuery(SuggestionQuery query) {
        return query != null
                && activeSuggestionQuery == query
                && query.generation() == nextSuggestionGeneration
                && query.belongsTo(suggestionActivation);
    }

    public SuggestionSnapshot suggestionSnapshot() {
        SuggestionDispatch dispatch = beginSuggestionDispatch();
        SuggestionQuery query = dispatch.query();
        if (query == null) {
            return dispatch.immediateSnapshot();
        }
        SuggestionSnapshot snapshot;
        try {
            snapshot = suggestionEngine.suggest(query);
        } catch (RuntimeException providerFailure) {
            expireSuggestionQuery(query);
            return currentSuggestionSnapshot;
        }
        acceptSuggestionResult(query, snapshot);
        return currentSuggestionSnapshot;
    }

    /** Exact identity check; profile equality is insufficient across fields. */
    public boolean ownsActivation(SuggestionActivation activation) {
        return activation != null && activation == suggestionActivation;
    }

    public boolean retrySuggestions() {
        cancelSuggestionQuery();
        return suggestionEngine.retry(suggestionActivation);
    }

    public void cancelSuggestions() {
        cancelSuggestionQuery();
        currentSuggestionSnapshot = SuggestionSnapshot.inactive(suggestionActivation);
    }

    public String composingText() {
        return composingText;
    }

    public boolean hasComposingText() {
        return !composingText.isEmpty();
    }

    public KeyboardProfile profile() {
        return profile;
    }

    SuggestionQuery activeSuggestionQueryForTesting() {
        return activeSuggestionQuery;
    }

    private long nextSuggestionGeneration() {
        if (nextSuggestionGeneration == Long.MAX_VALUE) {
            throw new IllegalStateException("suggestion generation space exhausted");
        }
        nextSuggestionGeneration++;
        return nextSuggestionGeneration;
    }

    private void cancelSuggestionQuery() {
        SuggestionQuery query = activeSuggestionQuery;
        activeSuggestionQuery = null;
        if (query != null) {
            suggestionEngine.cancel(query);
        }
    }

    private TouchSequence currentTouchSequence(String queryText) {
        if (!touchAlignmentValid || pendingJoiner != null || composingStrokes.isEmpty()) {
            return TouchSequence.empty();
        }
        try {
            return TouchSequence.forToken(profile, queryText, composingStrokes);
        } catch (IllegalArgumentException misaligned) {
            invalidateTouchAlignment();
            return TouchSequence.empty();
        }
    }

    private void recordTouchStroke(
            String previous,
            String emittedText,
            SpatialKeyStroke stroke
    ) {
        if (!touchAlignmentValid) {
            return;
        }
        if (stroke == null
                || !emittedText.equals(stroke.emittedText())
                || !composingText.equals(previous + stroke.emittedText())) {
            invalidateTouchAlignment();
            return;
        }
        composingStrokes.add(stroke);
        if (composingStrokes.size() > SuggestionQuery.MAX_COMPOSING_CODE_POINTS) {
            invalidateTouchAlignment();
        }
    }

    private void updateTouchAfterDelete(String previous, String updated) {
        if (!touchAlignmentValid || composingStrokes.isEmpty()) {
            invalidateTouchAlignment();
            return;
        }
        if (!previous.startsWith(updated)) {
            invalidateTouchAlignment();
            return;
        }
        String removed = previous.substring(updated.length());
        StringBuilder alignedSuffix = new StringBuilder();
        int firstRemovedStroke = composingStrokes.size();
        while (firstRemovedStroke > 0 && alignedSuffix.length() < removed.length()) {
            SpatialKeyStroke stroke = composingStrokes.get(--firstRemovedStroke);
            alignedSuffix.insert(0, stroke.emittedText());
        }
        if (!removed.contentEquals(alignedSuffix)) {
            invalidateTouchAlignment();
            return;
        }
        composingStrokes.subList(firstRemovedStroke, composingStrokes.size()).clear();
    }

    private void invalidateTouchAlignment() {
        composingStrokes.clear();
        touchAlignmentValid = false;
    }

    private void clearTouchSequence() {
        composingStrokes.clear();
        touchAlignmentValid = true;
    }

    private boolean canAppendToComposingToken(
            String text,
            KeySpec.InputPolicy inputPolicy
    ) {
        if (inputPolicy == KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION) {
            return isIntraWordPunctuation(text) && endsWithWordContent(composingText);
        }
        boolean hasWordCharacter = containsWordCharacter(composingText);
        for (int offset = 0; offset < text.length(); ) {
            int codePoint = text.codePointAt(offset);
            if (Character.isLetterOrDigit(codePoint)) {
                hasWordCharacter = true;
            } else if (!isWordMark(codePoint)
                    && !(isWordConnector(codePoint) && hasWordCharacter)
                    && !(inputPolicy == KeySpec.InputPolicy.ORTHOGRAPHIC_WORD
                    && codePoint == 0x2018)) {
                return false;
            }
            offset += Character.charCount(codePoint);
        }
        return true;
    }

    private static boolean endsWithWordContent(String text) {
        if (text.isEmpty()) {
            return false;
        }
        int codePoint = text.codePointBefore(text.length());
        return Character.isLetterOrDigit(codePoint) || isWordMark(codePoint);
    }

    private static boolean isIntraWordPunctuation(String text) {
        return "-".equals(text)
                || "/".equals(text)
                || "\\".equals(text)
                || ":".equals(text);
    }

    private static boolean containsWordCharacter(String text) {
        for (int offset = 0; offset < text.length(); ) {
            int codePoint = text.codePointAt(offset);
            if (Character.isLetterOrDigit(codePoint)) {
                return true;
            }
            offset += Character.charCount(codePoint);
        }
        return false;
    }

    private static boolean isWordMark(int codePoint) {
        int type = Character.getType(codePoint);
        return type == Character.NON_SPACING_MARK
                || type == Character.COMBINING_SPACING_MARK
                || type == Character.ENCLOSING_MARK;
    }

    private static boolean isWordConnector(int codePoint) {
        return codePoint == '\'' || codePoint == 0x2019;
    }

    private void bufferConjunctJoiner(
            String joiner,
            String inputScript,
            boolean mayTerminate
    ) {
        boolean afterOwnedVirama = "Deva".equals(inputScript)
                ? devanagariTail == ScriptTail.AFTER_VIRAMA
                : "Newa".equals(inputScript) && newaTail == ScriptTail.AFTER_VIRAMA;
        if (profile != null
                && inputScript.equals(profile.sourceScript())
                && afterOwnedVirama) {
            pendingJoiner = joiner;
            pendingJoinerScript = inputScript;
            pendingJoinerMayTerminate = mayTerminate;
        } else {
            clearPendingJoiner();
        }
    }

    private void updateDevanagariTail(String emittedText) {
        if (profile == null || !"Deva".equals(profile.sourceScript())) {
            devanagariTail = ScriptTail.NONE;
        } else {
            devanagariTail = updateScriptTail(
                    emittedText,
                    devanagariTail,
                    DEVANAGARI_VIRAMA,
                    ComposingSession::isDevanagariLetter,
                    ComposingSession::isDevanagariMark
            );
        }
        if (profile == null || !"Newa".equals(profile.sourceScript())) {
            newaTail = ScriptTail.NONE;
        } else {
            newaTail = updateScriptTail(
                    emittedText,
                    newaTail,
                    NEWA_VIRAMA,
                    ComposingSession::isNewaConjunctConsonant,
                    ComposingSession::isNewaMark
            );
        }
    }

    private static ScriptTail updateScriptTail(
            String emittedText,
            ScriptTail initial,
            int virama,
            CodePointPredicate isLetter,
            CodePointPredicate isMark
    ) {
        ScriptTail tail = initial;
        for (int offset = 0; offset < emittedText.length(); ) {
            int codePoint = emittedText.codePointAt(offset);
            if (isLetter.test(codePoint)) {
                tail = ScriptTail.BASE;
            } else if (codePoint == virama && tail == ScriptTail.BASE) {
                tail = ScriptTail.AFTER_VIRAMA;
            } else if (isMark.test(codePoint) && tail == ScriptTail.BASE) {
                // Preserve ownership across consonant marks such as nukta.
                tail = ScriptTail.BASE;
            } else {
                tail = ScriptTail.NONE;
            }
            offset += Character.charCount(codePoint);
        }
        return tail;
    }

    private void rebuildDevanagariTail(String text) {
        devanagariTail = ScriptTail.NONE;
        newaTail = ScriptTail.NONE;
        updateDevanagariTail(text);
    }

    private void clearKeyboardContext() {
        devanagariTail = ScriptTail.NONE;
        newaTail = ScriptTail.NONE;
        clearPendingJoiner();
    }

    private void clearPendingJoiner() {
        pendingJoiner = null;
        pendingJoinerScript = null;
        pendingJoinerMayTerminate = false;
    }

    private boolean startsWithPendingJoinerLetter(String text) {
        if (text.isEmpty()) {
            return false;
        }
        int codePoint = text.codePointAt(0);
        if ("Deva".equals(pendingJoinerScript)) {
            return isDevanagariLetter(codePoint);
        }
        return "Newa".equals(pendingJoinerScript)
                && isNewaConjunctConsonant(codePoint);
    }

    private boolean canMaterializePendingJoiner() {
        // A committed private/non-composing Newa control could not be deleted
        // safely without reading editor context. Drop it before it reaches the
        // editor; the following consonant is still committed literally.
        return !"Newa".equals(pendingJoinerScript) || composingAllowed;
    }

    private static boolean isDevanagariLetter(int codePoint) {
        return ((codePoint >= 0x0900 && codePoint <= 0x097f)
                || (codePoint >= 0xa8e0 && codePoint <= 0xa8ff)
                || (codePoint >= 0x11b00 && codePoint <= 0x11b5f))
                && Character.isLetter(codePoint);
    }

    private static boolean isDevanagariMark(int codePoint) {
        if (!((codePoint >= 0x0900 && codePoint <= 0x097f)
                || (codePoint >= 0xa8e0 && codePoint <= 0xa8ff)
                || (codePoint >= 0x11b00 && codePoint <= 0x11b5f))) {
            return false;
        }
        int type = Character.getType(codePoint);
        return type == Character.NON_SPACING_MARK
                || type == Character.COMBINING_SPACING_MARK
                || type == Character.ENCLOSING_MARK;
    }

    private static boolean isNewaConjunctConsonant(int codePoint) {
        return codePoint >= 0x1140e && codePoint <= 0x11434;
    }

    private static boolean isNewaMark(int codePoint) {
        if (codePoint < 0x11400 || codePoint > 0x1147f) {
            return false;
        }
        int type = Character.getType(codePoint);
        return type == Character.NON_SPACING_MARK
                || type == Character.COMBINING_SPACING_MARK
                || type == Character.ENCLOSING_MARK;
    }

    @FunctionalInterface
    private interface CodePointPredicate {
        boolean test(int codePoint);
    }

    private static void validatePolicyPayload(
            String text,
            KeySpec.InputPolicy inputPolicy
    ) {
        switch (inputPolicy) {
            case DEFAULT:
                if (text.indexOf('\u200c') >= 0 || text.indexOf('\u200d') >= 0) {
                    throw new IllegalArgumentException(
                            "default input cannot carry a conjunct joiner"
                    );
                }
                return;
            case ORTHOGRAPHIC_WORD:
                if (!"\u2018".equals(text)) {
                    throw new IllegalArgumentException(
                            "orthographic word input must carry U+2018"
                    );
                }
                return;
            case INTRA_WORD_PUNCTUATION:
                if (!isIntraWordPunctuation(text)) {
                    throw new IllegalArgumentException(
                            "intra-word punctuation input must carry hyphen, slash, backslash, or colon"
                    );
                }
                return;
            case DEVA_CONJUNCT_JOINER:
                if (!ZERO_WIDTH_NON_JOINER.equals(text)
                        && !ZERO_WIDTH_JOINER.equals(text)) {
                    throw new IllegalArgumentException(
                            "Devanagari conjunct joiner input must carry U+200C or U+200D"
                    );
                }
                return;
            case DEVA_TERMINAL_ZWNJ:
                if (!ZERO_WIDTH_NON_JOINER.equals(text)) {
                    throw new IllegalArgumentException(
                            "Devanagari terminal ZWNJ input must carry U+200C"
                    );
                }
                return;
            case NEWA_CONJUNCT_JOINER:
                if (!ZERO_WIDTH_NON_JOINER.equals(text)
                        && !ZERO_WIDTH_JOINER.equals(text)) {
                    throw new IllegalArgumentException(
                            "Newa conjunct joiner input must carry U+200C or U+200D"
                    );
                }
                return;
            default:
                throw new IllegalStateException("unknown input policy: " + inputPolicy);
        }
    }
}
