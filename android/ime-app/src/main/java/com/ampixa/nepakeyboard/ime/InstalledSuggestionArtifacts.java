package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Immutable installed-artifact union consumed by the engine factory. */
public final class InstalledSuggestionArtifacts {
    private final List<ReleasePackSpec> packs;
    private final List<ConversionMapSpec> conversions;

    InstalledSuggestionArtifacts(
            List<ReleasePackSpec> packs,
            List<ConversionMapSpec> conversions
    ) {
        this.packs = Collections.unmodifiableList(new ArrayList<>(packs));
        this.conversions = Collections.unmodifiableList(new ArrayList<>(conversions));
    }

    static InstalledSuggestionArtifacts empty() {
        return new InstalledSuggestionArtifacts(
                Collections.emptyList(),
                Collections.emptyList()
        );
    }

    public List<ReleasePackSpec> packs() {
        return packs;
    }

    public List<ConversionMapSpec> conversions() {
        return conversions;
    }
}
