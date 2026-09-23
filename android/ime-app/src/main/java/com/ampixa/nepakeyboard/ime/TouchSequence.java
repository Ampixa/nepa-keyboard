package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/** Bounded immutable spatial evidence aligned exactly with one composing token. */
public final class TouchSequence {
    private static final TouchSequence EMPTY = new TouchSequence(Collections.emptyList());

    private final List<SpatialKeyStroke> strokes;

    private TouchSequence(List<SpatialKeyStroke> strokes) {
        this.strokes = Collections.unmodifiableList(strokes);
    }

    public static TouchSequence empty() {
        return EMPTY;
    }

    public static TouchSequence forToken(
            KeyboardProfile profile,
            String composingText,
            List<SpatialKeyStroke> strokes
    ) {
        Objects.requireNonNull(profile, "profile");
        Objects.requireNonNull(composingText, "composingText");
        List<SpatialKeyStroke> copy = new ArrayList<>(Objects.requireNonNull(strokes, "strokes"));
        if (copy.isEmpty()) {
            return EMPTY;
        }
        if (copy.size() > SuggestionQuery.MAX_COMPOSING_CODE_POINTS) {
            throw new IllegalArgumentException("touch sequence exceeds decoder bound");
        }
        StringBuilder emitted = new StringBuilder();
        for (SpatialKeyStroke stroke : copy) {
            Objects.requireNonNull(stroke, "stroke");
            if (!stroke.matchesProfile(profile)) {
                throw new IllegalArgumentException("touch sequence layout identity mismatch");
            }
            emitted.append(stroke.emittedText());
        }
        if (!emitted.toString().equals(composingText)) {
            throw new IllegalArgumentException("touch sequence is not aligned with composing text");
        }
        return new TouchSequence(copy);
    }

    public List<SpatialKeyStroke> strokes() {
        return strokes;
    }

    public boolean isEmpty() {
        return strokes.isEmpty();
    }

    public boolean hasSpatialEvidence() {
        for (SpatialKeyStroke stroke : strokes) {
            if (stroke.hasSpatialEvidence()) {
                return true;
            }
        }
        return false;
    }

    boolean matches(KeyboardProfile profile, String composingText) {
        if (isEmpty()) {
            return true;
        }
        try {
            return forToken(profile, composingText, strokes).strokes.equals(strokes);
        } catch (IllegalArgumentException invalid) {
            return false;
        }
    }
}
