package com.ampixa.nepakeyboard.ime;

/** Cancellable N-best decoder boundary; pack-backed providers plug in here. */
public interface SuggestionEngine {
    enum SubmitOutcome {
        ACCEPTED,
        STALE,
        SATURATED,
        CLOSED,
        UNSUPPORTED
    }

    interface ResultListener {
        /** Called off the IME main thread at most once for an accepted submission. */
        void onResult(SuggestionQuery query, SuggestionSnapshot snapshot);
    }

    interface StateListener {
        /**
         * Reports a load-state transition off the UI thread without carrying typed text.
         * The receiver must reject any activation it no longer owns.
         */
        void onStateChanged(SuggestionActivation activation);
    }

    /** Starts a new field/profile activation, even if the same profile was active before. */
    SuggestionActivation activate(KeyboardProfile profile);

    /** Suspends lookup for a private or non-predictive field without requiring cache eviction. */
    SuggestionActivation suspend();

    /** Returns a query result only when the supplied activation is still exact and current. */
    SuggestionSnapshot suggest(
            SuggestionActivation activation,
            SuggestionQuery query
    );

    /**
     * Decodes a generation-bound request through the backward-compatible v0 method.
     *
     * <p>New callers use this method so activation ownership cannot be omitted
     * or substituted at the call site.</p>
     */
    default SuggestionSnapshot suggest(SuggestionQuery query) {
        if (query == null || !query.isBoundedDecoderRequest()) {
            throw new IllegalArgumentException("bounded decoder request required");
        }
        if (query.privateField() || query.cancellation().isCancelled()) {
            return SuggestionSnapshot.inactive(query.activation());
        }
        return suggest(query.activation(), query);
    }

    /**
     * Queues bounded decoder work without running provider code inline.
     *
     * <p>Legacy/test engines may keep the default unsupported result. Production
     * service code retains the immediate literal candidate in that case.</p>
     */
    default SubmitOutcome submit(
            SuggestionQuery query,
            ResultListener listener
    ) {
        if (query == null || listener == null) {
            throw new IllegalArgumentException("query and listener are required");
        }
        if (!query.isBoundedDecoderRequest()
                || !query.isWithinDecoderInputBound()
                || query.privateField()
                || query.cancellation().isCancelled()) {
            return SubmitOutcome.STALE;
        }
        return SubmitOutcome.UNSUPPORTED;
    }

    /**
     * Cancels one request. Providers with native or queued work may override
     * this method after cancelling the shared token.
     */
    default void cancel(SuggestionQuery query) {
        if (query != null) {
            query.cancellation().cancel();
        }
    }

    /** Retries only a current, recoverable activation. */
    boolean retry(SuggestionActivation activation);

    void close();
}
