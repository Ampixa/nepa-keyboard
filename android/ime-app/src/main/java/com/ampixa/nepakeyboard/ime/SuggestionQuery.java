package com.ampixa.nepakeyboard.ime;

import java.util.Objects;

/** Immutable, current-token-only decoder request snapshot. */
public final class SuggestionQuery {
    public static final long DEFAULT_DEADLINE_BUDGET_NANOS = 50_000_000L;
    public static final long MAX_DEADLINE_BUDGET_NANOS = 250_000_000L;
    public static final int MAX_COMPOSING_UTF16_UNITS = 256;
    public static final int MAX_COMPOSING_CODE_POINTS = 64;

    private final SuggestionActivation activation;
    private final KeyboardProfile profile;
    private final String profileId;
    private final String layoutId;
    private final int layoutRevision;
    private final String layoutSourceSha256;
    private final String composingText;
    private final boolean privateField;
    private final long generation;
    private final long createdAtNanos;
    private final long deadlineNanos;
    private final boolean deadlineEnforced;
    private final SuggestionCancellation cancellation;
    private final TouchSequence touchSequence;

    /**
     * Legacy, unbound request retained for direct v0 engine callers.
     *
     * <p>Production composing sessions use {@link #decoderRequest}; this
     * constructor has no generation or deadline and is not accepted by the
     * one-argument decoder API.</p>
     */
    public SuggestionQuery(
            KeyboardProfile profile,
            String composingText,
            boolean privateField
    ) {
        this.activation = null;
        this.profile = Objects.requireNonNull(profile, "profile");
        this.profileId = profile.id();
        this.layoutId = profile.layoutId();
        this.layoutRevision = profile.layoutRevision();
        this.layoutSourceSha256 = profile.layoutSourceSha256();
        this.composingText = Objects.requireNonNull(composingText, "composingText");
        this.privateField = privateField;
        this.generation = 0L;
        this.createdAtNanos = 0L;
        this.deadlineNanos = 0L;
        this.deadlineEnforced = false;
        this.cancellation = new SuggestionCancellation();
        this.touchSequence = TouchSequence.empty();
    }

    /** Creates a bounded request owned by one exact field/profile activation. */
    public static SuggestionQuery decoderRequest(
            SuggestionActivation activation,
            KeyboardProfile profile,
            String composingText,
            boolean privateField,
            long generation,
            long createdAtNanos,
            long deadlineNanos,
            SuggestionCancellation cancellation
    ) {
        return decoderRequest(
                activation,
                profile,
                composingText,
                privateField,
                generation,
                createdAtNanos,
                deadlineNanos,
                cancellation,
                TouchSequence.empty()
        );
    }

    /** Creates a bounded request with optional, exactly aligned spatial evidence. */
    public static SuggestionQuery decoderRequest(
            SuggestionActivation activation,
            KeyboardProfile profile,
            String composingText,
            boolean privateField,
            long generation,
            long createdAtNanos,
            long deadlineNanos,
            SuggestionCancellation cancellation,
            TouchSequence touchSequence
    ) {
        Objects.requireNonNull(activation, "activation");
        Objects.requireNonNull(profile, "profile");
        Objects.requireNonNull(composingText, "composingText");
        Objects.requireNonNull(cancellation, "cancellation");
        Objects.requireNonNull(touchSequence, "touchSequence");
        if (!activation.ownsProfile(profile)) {
            throw new IllegalArgumentException("activation/profile snapshot mismatch");
        }
        if (composingText.isEmpty()) {
            throw new IllegalArgumentException("decoder composing text must not be empty");
        }
        if (privateField) {
            throw new IllegalArgumentException("private fields cannot create decoder requests");
        }
        if (generation <= 0L) {
            throw new IllegalArgumentException("decoder generation must be positive");
        }
        long budget = deadlineNanos - createdAtNanos;
        if (budget <= 0L || budget > MAX_DEADLINE_BUDGET_NANOS) {
            throw new IllegalArgumentException("decoder deadline budget is outside the bound");
        }
        if (!touchSequence.matches(profile, composingText)) {
            throw new IllegalArgumentException("touch sequence does not own composing text");
        }
        return new SuggestionQuery(
                activation,
                profile,
                composingText,
                privateField,
                generation,
                createdAtNanos,
                deadlineNanos,
                true,
                cancellation,
                touchSequence
        );
    }

    /**
     * Builds an activation-bound request for deterministic provider instrumentation.
     *
     * <p>This package-private path deliberately has no wall-clock deadline. It is
     * accepted only by the explicit two-argument engine API. This keeps provider and
     * ranking coverage separate from controlled production-deadline tests.</p>
     */
    static SuggestionQuery functionalTestRequest(
            SuggestionActivation activation,
            KeyboardProfile profile,
            String composingText,
            long generation,
            TouchSequence touchSequence
    ) {
        Objects.requireNonNull(activation, "activation");
        Objects.requireNonNull(profile, "profile");
        Objects.requireNonNull(composingText, "composingText");
        Objects.requireNonNull(touchSequence, "touchSequence");
        if (!activation.ownsProfile(profile)) {
            throw new IllegalArgumentException("activation/profile snapshot mismatch");
        }
        if (composingText.isEmpty()) {
            throw new IllegalArgumentException("functional test composing text must not be empty");
        }
        if (composingText.length() > MAX_COMPOSING_UTF16_UNITS
                || composingText.codePointCount(0, composingText.length())
                > MAX_COMPOSING_CODE_POINTS) {
            throw new IllegalArgumentException("functional test composing text exceeds decoder bound");
        }
        if (generation <= 0L) {
            throw new IllegalArgumentException("functional test generation must be positive");
        }
        if (!touchSequence.matches(profile, composingText)) {
            throw new IllegalArgumentException("touch sequence does not own composing text");
        }
        return new SuggestionQuery(
                activation,
                profile,
                composingText,
                false,
                generation,
                0L,
                0L,
                false,
                new SuggestionCancellation(),
                touchSequence
        );
    }

    private SuggestionQuery(
            SuggestionActivation activation,
            KeyboardProfile profile,
            String composingText,
            boolean privateField,
            long generation,
            long createdAtNanos,
            long deadlineNanos,
            boolean deadlineEnforced,
            SuggestionCancellation cancellation,
            TouchSequence touchSequence
    ) {
        this.activation = activation;
        this.profile = profile;
        this.profileId = profile.id();
        this.layoutId = profile.layoutId();
        this.layoutRevision = profile.layoutRevision();
        this.layoutSourceSha256 = profile.layoutSourceSha256();
        this.composingText = composingText;
        this.privateField = privateField;
        this.generation = generation;
        this.createdAtNanos = createdAtNanos;
        this.deadlineNanos = deadlineNanos;
        this.deadlineEnforced = deadlineEnforced;
        this.cancellation = cancellation;
        this.touchSequence = touchSequence;
    }

    /** Returns the exact process-local activation, or null for a legacy request. */
    public SuggestionActivation activation() {
        return activation;
    }

    public KeyboardProfile profile() {
        return profile;
    }

    public String profileId() {
        return profileId;
    }

    /** Exact compiled-layout identity captured with the profile snapshot. */
    public String layoutId() {
        return layoutId;
    }

    public int layoutRevision() {
        return layoutRevision;
    }

    public String layoutSourceSha256() {
        return layoutSourceSha256;
    }

    public String composingText() {
        return composingText;
    }

    public boolean privateField() {
        return privateField;
    }

    /** Positive for bounded decoder requests; zero only for the legacy constructor. */
    public long generation() {
        return generation;
    }

    public long createdAtNanos() {
        return createdAtNanos;
    }

    public long deadlineNanos() {
        return deadlineNanos;
    }

    public SuggestionCancellation cancellation() {
        return cancellation;
    }

    public TouchSequence touchSequence() {
        return touchSequence;
    }

    public boolean isBoundedDecoderRequest() {
        return activation != null && deadlineEnforced;
    }

    /** Identity is deliberately exact; equal profile IDs do not imply field ownership. */
    public boolean belongsTo(SuggestionActivation expectedActivation) {
        if (expectedActivation == null) {
            return false;
        }
        if (activation != null) {
            return activation == expectedActivation;
        }
        return expectedActivation.isActive()
                && profileId.equals(expectedActivation.profileId());
    }

    public boolean isExpired(long nowNanos) {
        return deadlineEnforced && nowNanos - deadlineNanos >= 0L;
    }

    public boolean acceptsProviderResults(long nowNanos) {
        return !cancellation.isCancelled() && !isExpired(nowNanos);
    }

    public boolean isWithinDecoderInputBound() {
        return composingText.length() <= MAX_COMPOSING_UTF16_UNITS
                && composingText.codePointCount(0, composingText.length())
                <= MAX_COMPOSING_CODE_POINTS;
    }
}
