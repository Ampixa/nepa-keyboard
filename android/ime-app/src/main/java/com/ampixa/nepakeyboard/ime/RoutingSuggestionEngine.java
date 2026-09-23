package com.ampixa.nepakeyboard.ime;

import java.util.Objects;

/** Routes an exact activation to either the unchanged NKP engine or the NCM engine. */
public final class RoutingSuggestionEngine implements SuggestionEngine {
    private final SuggestionEngine nkpEngine;
    private final SuggestionEngine ncmEngine;
    private SuggestionEngine activeEngine;
    private SuggestionActivation activeActivation;
    private boolean closed;

    RoutingSuggestionEngine(
            SuggestionEngine nkpEngine,
            SuggestionEngine ncmEngine
    ) {
        this.nkpEngine = Objects.requireNonNull(nkpEngine, "nkpEngine");
        this.ncmEngine = Objects.requireNonNull(ncmEngine, "ncmEngine");
    }

    @Override
    public synchronized SuggestionActivation activate(KeyboardProfile profile) {
        Objects.requireNonNull(profile, "profile");
        if (closed) {
            return activeActivation == null
                    ? nkpEngine.suspend()
                    : activeActivation;
        }
        nkpEngine.suspend();
        ncmEngine.suspend();
        activeEngine = profile.artifactKind() == KeyboardProfile.ArtifactKind.NCM
                ? ncmEngine
                : nkpEngine;
        activeActivation = activeEngine.activate(profile);
        return activeActivation;
    }

    @Override
    public synchronized SuggestionActivation suspend() {
        SuggestionActivation nkpSuspended = nkpEngine.suspend();
        ncmEngine.suspend();
        activeEngine = null;
        activeActivation = nkpSuspended;
        return activeActivation;
    }

    @Override
    public SuggestionSnapshot suggest(
            SuggestionActivation activation,
            SuggestionQuery query
    ) {
        SuggestionEngine provider = exactProvider(activation, query);
        return provider == null
                ? SuggestionSnapshot.inactive(activation)
                : provider.suggest(activation, query);
    }

    @Override
    public SubmitOutcome submit(SuggestionQuery query, ResultListener listener) {
        if (query == null || listener == null) {
            throw new IllegalArgumentException("query and listener are required");
        }
        SuggestionEngine provider = exactProvider(query.activation(), query);
        return provider == null
                ? SubmitOutcome.STALE
                : provider.submit(query, listener);
    }

    @Override
    public void cancel(SuggestionQuery query) {
        SuggestionEngine provider;
        synchronized (this) {
            provider = query != null
                    && query.activation() == activeActivation
                    ? activeEngine
                    : null;
        }
        if (provider != null) {
            provider.cancel(query);
        } else if (query != null) {
            query.cancellation().cancel();
        }
    }

    @Override
    public synchronized boolean retry(SuggestionActivation activation) {
        return !closed
                && activation != null
                && activation == activeActivation
                && activeEngine != null
                && activeEngine.retry(activation);
    }

    @Override
    public synchronized void close() {
        if (closed) {
            return;
        }
        closed = true;
        activeEngine = null;
        activeActivation = null;
        nkpEngine.close();
        ncmEngine.close();
    }

    private synchronized SuggestionEngine exactProvider(
            SuggestionActivation activation,
            SuggestionQuery query
    ) {
        if (closed
                || activation == null
                || activation != activeActivation
                || activeEngine == null
                || query == null
                || !query.belongsTo(activation)) {
            return null;
        }
        KeyboardProfile.ArtifactKind expected = query.profile().artifactKind();
        if ((expected == KeyboardProfile.ArtifactKind.NCM) != (activeEngine == ncmEngine)) {
            return null;
        }
        return activeEngine;
    }
}
