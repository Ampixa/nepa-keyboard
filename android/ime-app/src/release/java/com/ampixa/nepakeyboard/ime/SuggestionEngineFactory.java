package com.ampixa.nepakeyboard.ime;

import java.util.List;

/** Public/export builds can open only packs whose release mode is {@code release}. */
final class SuggestionEngineFactory {
    private SuggestionEngineFactory() {
    }

    static SuggestionEngine create(
            List<ReleasePackSpec> specs,
            SuggestionEngine.StateListener stateListener
    ) {
        return new NkpSuggestionEngine(specs, stateListener);
    }

    static SuggestionEngine create(
            InstalledSuggestionArtifacts artifacts,
            SuggestionEngine.StateListener stateListener
    ) {
        return new RoutingSuggestionEngine(
                new NkpSuggestionEngine(artifacts.packs(), stateListener),
                new NcmConversionEngine(artifacts.conversions(), stateListener)
        );
    }
}
