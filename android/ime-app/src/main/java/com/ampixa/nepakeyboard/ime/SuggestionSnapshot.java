package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/** Immutable UI-facing result for one exact suggestion activation and query. */
public final class SuggestionSnapshot {
    public enum Status {
        INACTIVE,
        LOADING,
        READY,
        NO_MATCH,
        MISSING,
        CORRUPT,
        UNAVAILABLE
    }

    public static final int MAX_CANDIDATES = 3;

    private final SuggestionActivation activation;
    private final SuggestionQuery query;
    private final Status status;
    private final List<SuggestionCandidate> nBestCandidates;
    private final List<String> candidates;

    private SuggestionSnapshot(
            SuggestionActivation activation,
            SuggestionQuery query,
            Status status,
            List<SuggestionCandidate> nBestCandidates,
            List<String> candidates
    ) {
        this.activation = Objects.requireNonNull(activation, "activation");
        this.query = query;
        this.status = Objects.requireNonNull(status, "status");
        this.nBestCandidates = freezeTypedCandidates(nBestCandidates);
        this.candidates = freezeVisibleCandidates(candidates, status);
        validateContract();
    }

    static SuggestionSnapshot inactive(SuggestionActivation activation) {
        return state(activation, Status.INACTIVE);
    }

    static SuggestionSnapshot state(
            SuggestionActivation activation,
            Status status
    ) {
        if (status == Status.READY) {
            throw new IllegalArgumentException("ready snapshots require candidates");
        }
        return new SuggestionSnapshot(
                activation,
                null,
                status,
                Collections.emptyList(),
                Collections.emptyList()
        );
    }

    /** State for a real request; the typed result retains its literal path. */
    static SuggestionSnapshot state(
            SuggestionActivation activation,
            SuggestionQuery query,
            Status status
    ) {
        requireQueryOwnership(activation, query);
        if (status == Status.READY || status == Status.INACTIVE) {
            throw new IllegalArgumentException("request state must be non-ready and active");
        }
        return new SuggestionSnapshot(
                activation,
                query,
                status,
                Collections.singletonList(
                        SuggestionCandidate.literal(query.composingText())
                ),
                Collections.emptyList()
        );
    }

    /**
     * Presentation-only compatibility factory used by view tests.
     *
     * <p>Decoder providers must use the typed {@code decoded} factory; this has no
     * request identity or literal guarantee.</p>
     */
    static SuggestionSnapshot ready(
            SuggestionActivation activation,
            List<String> candidates
    ) {
        List<SuggestionCandidate> typed = new ArrayList<>();
        List<String> values = candidates == null
                ? Collections.emptyList()
                : candidates;
        for (int index = 0; index < values.size(); index++) {
            typed.add(SuggestionCandidate.provider(
                    values.get(index),
                    SuggestionCandidate.Category.DICTIONARY,
                    "legacy-presentation",
                    -index
            ));
        }
        return new SuggestionSnapshot(activation, null, Status.READY, typed, values);
    }

    /** Builds one query-owned, typed N-best decoder result. */
    static SuggestionSnapshot decoded(
            SuggestionActivation activation,
            SuggestionQuery query,
            List<SuggestionCandidate> candidates
    ) {
        requireQueryOwnership(activation, query);
        List<String> visible = new ArrayList<>();
        for (SuggestionCandidate candidate : candidates == null
                ? Collections.<SuggestionCandidate>emptyList()
                : candidates) {
            visible.add(candidate == null ? null : candidate.text());
        }
        return new SuggestionSnapshot(
                activation,
                query,
                Status.READY,
                candidates,
                visible
        );
    }

    static SuggestionSnapshot literalFallback(SuggestionQuery query) {
        if (query == null || query.activation() == null) {
            throw new IllegalArgumentException("bound request required");
        }
        return decoded(
                query.activation(),
                query,
                Collections.singletonList(
                        SuggestionCandidate.literal(query.composingText())
                )
        );
    }

    public SuggestionActivation activation() {
        return activation;
    }

    /** Returns the exact request object, or null for a compatibility snapshot. */
    public SuggestionQuery query() {
        return query;
    }

    public Status status() {
        return status;
    }

    /** Backward-compatible text projection used by the current candidate strip. */
    public List<String> candidates() {
        return candidates;
    }

    public List<SuggestionCandidate> nBestCandidates() {
        return nBestCandidates;
    }

    public boolean belongsTo(SuggestionQuery expected) {
        return expected != null
                && query == expected
                && activation == expected.activation();
    }

    public boolean hasProviderCandidates() {
        for (SuggestionCandidate candidate : nBestCandidates) {
            if (!candidate.isLiteral()) {
                return true;
            }
        }
        return false;
    }

    public boolean hasExplicitLiteral() {
        for (SuggestionCandidate candidate : nBestCandidates) {
            if (candidate.isLiteral()) {
                return true;
            }
        }
        return false;
    }

    public boolean isLiteralFallback() {
        return status == Status.READY
                && nBestCandidates.size() == 1
                && nBestCandidates.get(0).isLiteral();
    }

    /** Only transient/unclassified I/O failure has an in-process retry path in v0. */
    public boolean retryable() {
        return status == Status.UNAVAILABLE;
    }

    private void validateContract() {
        if (status == Status.READY) {
            if (candidates.isEmpty() || candidates.size() != nBestCandidates.size()) {
                throw new IllegalArgumentException("ready snapshot projections must agree");
            }
        } else if (!candidates.isEmpty()) {
            throw new IllegalArgumentException("non-ready snapshots cannot expose UI candidates");
        }
        if (query == null) {
            return;
        }
        if (!query.belongsTo(activation)) {
            throw new IllegalArgumentException("snapshot request activation mismatch");
        }
        int literalCount = 0;
        for (SuggestionCandidate candidate : nBestCandidates) {
            if (candidate.isLiteral()) {
                literalCount++;
                if (!query.composingText().equals(candidate.text())) {
                    throw new IllegalArgumentException("literal candidate must preserve input");
                }
            }
        }
        if (literalCount != 1) {
            throw new IllegalArgumentException("request snapshots require one literal candidate");
        }
    }

    private static List<SuggestionCandidate> freezeTypedCandidates(
            List<SuggestionCandidate> values
    ) {
        List<SuggestionCandidate> copy = new ArrayList<>(
                Objects.requireNonNull(values, "nBestCandidates")
        );
        if (copy.size() > MAX_CANDIDATES) {
            throw new IllegalArgumentException("N-best result exceeds candidate bound");
        }
        Set<String> texts = new HashSet<>();
        for (SuggestionCandidate candidate : copy) {
            if (candidate == null) {
                throw new IllegalArgumentException("typed candidates must not be null");
            }
            if (!texts.add(candidate.text())) {
                throw new IllegalArgumentException("typed candidate text must be unique");
            }
        }
        return Collections.unmodifiableList(copy);
    }

    private static List<String> freezeVisibleCandidates(
            List<String> values,
            Status status
    ) {
        List<String> copy = new ArrayList<>(Objects.requireNonNull(values, "candidates"));
        if (status == Status.READY
                && (copy.isEmpty() || copy.size() > MAX_CANDIDATES)) {
            throw new IllegalArgumentException("ready snapshots require one to three candidates");
        }
        for (String value : copy) {
            if (value == null || value.isEmpty()) {
                throw new IllegalArgumentException("ready candidates must not be empty");
            }
        }
        return Collections.unmodifiableList(copy);
    }

    private static void requireQueryOwnership(
            SuggestionActivation activation,
            SuggestionQuery query
    ) {
        Objects.requireNonNull(activation, "activation");
        Objects.requireNonNull(query, "query");
        if (!query.belongsTo(activation)) {
            throw new IllegalArgumentException("query activation mismatch");
        }
        if (query.privateField() || query.composingText().isEmpty()) {
            throw new IllegalArgumentException("decoder query is not suggestible");
        }
    }
}
