package com.ampixa.nepakeyboard.ime;

import java.util.List;

/** Ordinary debug builds exercise the same fail-closed pack reader as release. */
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

    static SuggestionEngine createForDecoderTest(
            List<ReleasePackSpec> specs,
            SuggestionEngine.StateListener stateListener,
            NkpSuggestionEngine.DecodeObserver decodeObserver
    ) {
        return new NkpSuggestionEngine(
                specs,
                stateListener,
                PackBundleOpener.RELEASE_ONLY,
                decodeObserver
        );
    }
}
