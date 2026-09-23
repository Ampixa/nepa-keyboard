package com.ampixa.nepakeyboard.ime;

import android.content.Context;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Atomically validates the union of installed NKP and NCM profile bindings. */
public final class SuggestionArtifactRegistry {
    private SuggestionArtifactRegistry() {
    }

    public static InstalledSuggestionArtifacts installed(Context context) {
        List<ReleasePackSpec> packs = ReleasePackRegistry.installed(context);
        List<ConversionMapSpec> conversions = ConversionMapRegistry.installed(context);
        Set<String> actual = new HashSet<>();
        for (ReleasePackSpec pack : packs) {
            if (!actual.add(pack.profileId())) {
                return InstalledSuggestionArtifacts.empty();
            }
        }
        for (ConversionMapSpec conversion : conversions) {
            if (!actual.add(conversion.profileId())) {
                return InstalledSuggestionArtifacts.empty();
            }
        }
        Set<String> expected = new HashSet<>();
        for (KeyboardProfile profile : LanguageRegistry.available()) {
            // A transliteration-only profile is served by a reviewed map, so it has
            // no suggestion artifact and must not be expected among them.
            if (!LanguageRegistry.isTransliterationOnly(profile.id())) {
                expected.add(profile.id());
            }
        }
        return actual.equals(expected)
                ? new InstalledSuggestionArtifacts(packs, conversions)
                : InstalledSuggestionArtifacts.empty();
    }
}
