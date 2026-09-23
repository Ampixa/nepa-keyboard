package com.ampixa.nepakeyboard.ime;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

/** Tiny deterministic test data; debug-only and never packaged in release builds. */
final class FixtureSuggestionEngine implements SuggestionEngine {
    private int callCount;
    private SuggestionQuery lastQuery;
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
        callCount++;
        lastQuery = query;
        if (activation == null
                || activation != activeActivation
                || !activation.isActive()
                || query == null
                || !query.belongsTo(activation)
                || query.privateField()
                || query.composingText().isEmpty()
                || !activation.profileId().equals(query.profileId())) {
            if (activation == null) {
                throw new IllegalArgumentException("activation must not be null");
            }
            return SuggestionSnapshot.inactive(activation);
        }
        List<String> candidates = candidates(query);
        if (candidates.isEmpty()) {
            return SuggestionSnapshot.state(
                    activation,
                    query,
                    SuggestionSnapshot.Status.NO_MATCH
            );
        }
        List<SuggestionCandidate> typed = new java.util.ArrayList<>();
        SuggestionCandidate.Category category;
        if (query.profile().lookupKind() == KeyboardProfile.LookupKind.ALIAS_PREFIX) {
            category = SuggestionCandidate.Category.TRANSLITERATION;
        } else if (query.profile().lookupKind() == KeyboardProfile.LookupKind.CONVERSION) {
            category = SuggestionCandidate.Category.CONVERSION;
        } else {
            category = SuggestionCandidate.Category.EXACT;
        }
        for (int index = 0; index < candidates.size(); index++) {
            String candidate = candidates.get(index);
            if (!candidate.equals(query.composingText())) {
                typed.add(SuggestionCandidate.provider(
                        candidate,
                        category,
                        "debug-fixture-prefix",
                        -index
                ));
                if (typed.size() == SuggestionSnapshot.MAX_CANDIDATES - 1) {
                    break;
                }
            }
        }
        typed.add(SuggestionCandidate.literal(query.composingText()));
        return SuggestionSnapshot.decoded(activation, query, typed);
    }

    private static List<String> candidates(SuggestionQuery query) {
        String profileId = query.profile().id();
        String input = query.composingText();
        if (LanguageRegistry.ENGLISH_ID.equals(profileId)) {
            String key = input.toLowerCase(Locale.ROOT);
            if ("hello".startsWith(key)) {
                return Arrays.asList("hello", "help", "held");
            }
            if ("nepal".startsWith(key)) {
                return Arrays.asList("nepal", "new", "next");
            }
        } else if (LanguageRegistry.NEPALI_DIRECT_ID.equals(profileId)) {
            if ("नेपाल".startsWith(input)) {
                return Arrays.asList("नेपाल", "नेपाली");
            }
            if ("नमस्ते".startsWith(input)) {
                return Collections.singletonList("नमस्ते");
            }
        } else if (LanguageRegistry.NEPALI_ROMAN_ID.equals(profileId)) {
            String key = input.toLowerCase(Locale.ROOT);
            if ("nepal".startsWith(key)) {
                return Arrays.asList("नेपाल", "नेपाली");
            }
        }
        return Collections.emptyList();
    }

    @Override
    public boolean retry(SuggestionActivation activation) {
        return false;
    }

    @Override
    public void close() {
        activeActivation = null;
    }

    int callCount() {
        return callCount;
    }

    SuggestionQuery lastQuery() {
        return lastQuery;
    }

    private long nextActivationId() {
        nextActivationId++;
        return nextActivationId;
    }
}
