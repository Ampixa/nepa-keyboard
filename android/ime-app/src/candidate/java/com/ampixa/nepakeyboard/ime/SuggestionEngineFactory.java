package com.ampixa.nepakeyboard.ime;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import java.util.List;

/** Play candidate boundary for the verified full internal product catalog. */
final class SuggestionEngineFactory {
    private SuggestionEngineFactory() {
    }

    static SuggestionEngine create(
            List<ReleasePackSpec> specs,
            SuggestionEngine.StateListener stateListener
    ) {
        return new NkpSuggestionEngine(
                specs,
                stateListener,
                (file, expectedSha256) -> NkpBundle.open(file, expectedSha256, true)
        );
    }

    static SuggestionEngine create(
            InstalledSuggestionArtifacts artifacts,
            SuggestionEngine.StateListener stateListener
    ) {
        return new RoutingSuggestionEngine(
                new NkpSuggestionEngine(
                        artifacts.packs(),
                        stateListener,
                        (file, expectedSha256) -> NkpBundle.open(
                                file,
                                expectedSha256,
                                true
                        )
                ),
                new NcmConversionEngine(artifacts.conversions(), stateListener)
        );
    }
}
