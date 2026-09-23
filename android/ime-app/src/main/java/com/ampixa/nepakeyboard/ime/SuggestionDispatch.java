package com.ampixa.nepakeyboard.ime;

import java.util.Objects;

/** Immutable main-thread handoff for one optional asynchronous decoder request. */
public final class SuggestionDispatch {
    private final SuggestionQuery query;
    private final SuggestionSnapshot immediateSnapshot;

    private SuggestionDispatch(
            SuggestionQuery query,
            SuggestionSnapshot immediateSnapshot
    ) {
        this.query = query;
        this.immediateSnapshot = Objects.requireNonNull(
                immediateSnapshot,
                "immediateSnapshot"
        );
        if (query != null && !immediateSnapshot.belongsTo(query)) {
            throw new IllegalArgumentException("dispatch snapshot must own its request");
        }
    }

    static SuggestionDispatch inactive(SuggestionSnapshot snapshot) {
        return new SuggestionDispatch(null, snapshot);
    }

    static SuggestionDispatch active(SuggestionQuery query) {
        return new SuggestionDispatch(query, SuggestionSnapshot.literalFallback(query));
    }

    /** Null when the current field/token must not reach a decoder. */
    public SuggestionQuery query() {
        return query;
    }

    /** Literal-only for an active request, otherwise inactive. */
    public SuggestionSnapshot immediateSnapshot() {
        return immediateSnapshot;
    }
}
