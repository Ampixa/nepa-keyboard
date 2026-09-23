package com.ampixa.nepakeyboard.ime;

import java.util.Objects;

/** One immutable, typed member of a decoder's bounded N-best result. */
public final class SuggestionCandidate {
    /**
     * Candidate semantics, independent from presentation or commit policy.
     *
     * <p>No category authorizes automatic replacement. In particular,
     * {@link Category#CORRECTION} describes an explicit nearby-key hypothesis;
     * it does not grant commit authority.</p>
     */
    public enum Category {
        LITERAL,
        EXACT,
        DICTIONARY,
        TRANSLITERATION,
        CORRECTION,
        CONVERSION
    }

    public static final String LITERAL_PROVIDER = "literal";
    public static final int LITERAL_SCORE = Integer.MIN_VALUE;

    private final String text;
    private final Category category;
    private final String providerId;
    private final int providerScore;

    private SuggestionCandidate(
            String text,
            Category category,
            String providerId,
            int providerScore
    ) {
        this.text = requireText(text, "text");
        this.category = Objects.requireNonNull(category, "category");
        this.providerId = requireText(providerId, "providerId");
        this.providerScore = providerScore;
        if (category == Category.LITERAL
                && (!LITERAL_PROVIDER.equals(providerId)
                || providerScore != LITERAL_SCORE)) {
            throw new IllegalArgumentException("literal candidate metadata is canonical");
        }
        if (category != Category.LITERAL && LITERAL_PROVIDER.equals(providerId)) {
            throw new IllegalArgumentException("literal provider requires literal category");
        }
    }

    public static SuggestionCandidate literal(String text) {
        return new SuggestionCandidate(
                text,
                Category.LITERAL,
                LITERAL_PROVIDER,
                LITERAL_SCORE
        );
    }

    public static SuggestionCandidate provider(
            String text,
            Category category,
            String providerId,
            int providerScore
    ) {
        if (category == Category.LITERAL) {
            throw new IllegalArgumentException("use literal() for literal candidates");
        }
        return new SuggestionCandidate(text, category, providerId, providerScore);
    }

    public String text() {
        return text;
    }

    public Category category() {
        return category;
    }

    /** Identifies the scoring provider, not a language pack artifact. */
    public String providerId() {
        return providerId;
    }

    /**
     * Provider-local score; higher values rank first only within that provider.
     *
     * <p>The v1 contract does not pretend scores from different providers are
     * calibrated or establish correction confidence.</p>
     */
    public int providerScore() {
        return providerScore;
    }

    public boolean isLiteral() {
        return category == Category.LITERAL;
    }

    private static String requireText(String value, String label) {
        Objects.requireNonNull(value, label);
        if (value.isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        return value;
    }
}
