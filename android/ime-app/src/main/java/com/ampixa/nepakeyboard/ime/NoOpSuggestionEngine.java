package com.ampixa.nepakeyboard.ime;

import java.util.Objects;

/** Deliberately empty engine used by composing-policy tests and packless callers. */
public final class NoOpSuggestionEngine implements SuggestionEngine {
    private SuggestionActivation activeActivation;
    private long nextActivationId;

    @Override
    public SuggestionActivation activate(KeyboardProfile profile) {
        Objects.requireNonNull(profile, "profile");
        activeActivation = SuggestionActivation.active(nextActivationId(), profile);
        return activeActivation;
    }

    @Override
    public SuggestionActivation suspend() {
        activeActivation = SuggestionActivation.suspended(nextActivationId());
        return activeActivation;
    }

    @Override
    public SuggestionSnapshot suggest(
            SuggestionActivation activation,
            SuggestionQuery query
    ) {
        Objects.requireNonNull(activation, "activation");
        if (activation != activeActivation
                || !activation.isActive()
                || query == null
                || !query.belongsTo(activation)
                || query.privateField()
                || query.composingText().isEmpty()
                || !activation.profileId().equals(query.profileId())) {
            return SuggestionSnapshot.inactive(activation);
        }
        return SuggestionSnapshot.state(
                activation,
                query,
                SuggestionSnapshot.Status.NO_MATCH
        );
    }

    @Override
    public boolean retry(SuggestionActivation activation) {
        return false;
    }

    @Override
    public void close() {
        activeActivation = null;
    }

    private long nextActivationId() {
        nextActivationId++;
        return nextActivationId;
    }
}
