package com.ampixa.nepakeyboard.ime;

import java.util.Objects;

/**
 * Composing state for phonetic typing.
 *
 * <p>Deliberately separate from {@link ComposingSession}: that session owns reviewed
 * joiner and conjunct semantics for direct script input, while this one owns a Roman
 * buffer whose rendering is recomputed from scratch on every keystroke. Exactly one of
 * the two is active at a time, so a token can never be half-owned by both.
 */
public final class TransliterationSession {
    private final StringBuilder roman = new StringBuilder();
    private TransliterationEngine engine;
    private boolean privateField;

    /** Binds the engine for the active profile. A null engine disables phonetic input. */
    public void start(TransliterationEngine engine, boolean privateField) {
        this.engine = engine;
        this.privateField = privateField;
        roman.setLength(0);
    }

    public boolean isActive() {
        return engine != null;
    }

    public boolean hasComposingText() {
        return roman.length() > 0;
    }

    public String romanBuffer() {
        return roman.toString();
    }

    /** The script text the current Roman buffer renders to. */
    public String rendered() {
        return engine == null ? "" : engine.transliterate(roman.toString());
    }

    /** Appends Roman input and republishes the rendered script text. */
    public boolean append(String text, TextSink sink) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(sink, "sink");
        if (engine == null || text.isEmpty()) {
            return false;
        }
        if (privateField) {
            // A password field never accumulates a buffer; input is committed literally.
            return sink.commitText(engine.transliterate(text));
        }
        roman.append(text);
        return publish(sink);
    }

    /** Removes one Roman character. Returns false when there was nothing to remove. */
    public boolean deleteLast(TextSink sink) {
        Objects.requireNonNull(sink, "sink");
        if (engine == null || roman.length() == 0) {
            return false;
        }
        roman.deleteCharAt(roman.length() - 1);
        if (roman.length() == 0) {
            // Clearing through the sink keeps the editor's composing span consistent.
            if (!sink.setComposingText("")) {
                sink.commitText("");
            }
            sink.finishComposingText();
            return true;
        }
        return publish(sink);
    }

    /** Commits the rendered text and clears the buffer. */
    public boolean commit(TextSink sink) {
        Objects.requireNonNull(sink, "sink");
        if (engine == null || roman.length() == 0) {
            return false;
        }
        String rendered = rendered();
        roman.setLength(0);
        boolean committed = sink.commitText(rendered);
        sink.finishComposingText();
        return committed;
    }

    /** Drops the buffer without emitting anything further. */
    public void reset() {
        roman.setLength(0);
    }

    public void finish(TextSink sink) {
        if (roman.length() > 0) {
            commit(sink);
        } else if (engine != null) {
            sink.finishComposingText();
        }
    }

    private boolean publish(TextSink sink) {
        String rendered = rendered();
        if (sink.setComposingText(rendered)) {
            return true;
        }
        // An editor that refuses composing text still receives the rendered form.
        boolean committed = sink.commitText(rendered);
        roman.setLength(0);
        return committed;
    }
}
