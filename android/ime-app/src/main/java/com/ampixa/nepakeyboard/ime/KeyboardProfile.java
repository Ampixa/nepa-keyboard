package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * One selectable language + output script + input-method combination.
 *
 * <p>Keeping this identity explicit prevents umbrella labels and generated
 * script conversions from being mistaken for interchangeable dictionaries.</p>
 */
public final class KeyboardProfile {
    public enum Availability {
        AVAILABLE,
        BLOCKED
    }

    /** Pack index used by this input method; independent from its visual layout. */
    public enum LookupKind {
        SURFACE_PREFIX,
        ALIAS_PREFIX,
        CONVERSION
    }

    /** Runtime artifact family; conversion maps never enter the NKP reader. */
    public enum ArtifactKind {
        NKP,
        NCM
    }

    private final String id;
    private final String languageId;
    private final String inputMethodId;
    private final String localeTag;
    private final String displayName;
    private final String nativeName;
    private final String sourceScript;
    private final String outputScript;
    private final String detail;
    private final String methodType;
    private final String engineKind;
    private final String layoutId;
    private final Integer layoutRevision;
    private final String layoutSourceSha256;
    private final LookupKind lookupKind;
    private final String artifactBinding;
    private final String catalogReadiness;
    private final Availability availability;
    private final String blockedReason;
    private final String blockedDetail;
    private final boolean defaultEnabled;
    private final String scope;
    private final String group;
    private final String variety;
    private final String sortKey;
    private final List<String> searchAliases;
    private final List<String> evidenceIds;

    public KeyboardProfile(
            String id,
            String languageId,
            String inputMethodId,
            String localeTag,
            String displayName,
            String nativeName,
            String sourceScript,
            String outputScript,
            String detail,
            String methodType,
            String engineKind,
            String layoutId,
            LookupKind lookupKind,
            String artifactBinding,
            String catalogReadiness,
            Availability availability,
            String blockedReason,
            String blockedDetail,
            boolean defaultEnabled,
            String scope,
            String group,
            String variety,
            String sortKey,
            List<String> searchAliases,
            List<String> evidenceIds
    ) {
        this(
                id,
                languageId,
                inputMethodId,
                localeTag,
                displayName,
                nativeName,
                sourceScript,
                outputScript,
                detail,
                methodType,
                engineKind,
                layoutId,
                null,
                null,
                lookupKind,
                artifactBinding,
                catalogReadiness,
                availability,
                blockedReason,
                blockedDetail,
                defaultEnabled,
                scope,
                group,
                variety,
                sortKey,
                searchAliases,
                evidenceIds
        );
    }

    /** Full generated profile identity, including the reviewed layout artifact. */
    public KeyboardProfile(
            String id,
            String languageId,
            String inputMethodId,
            String localeTag,
            String displayName,
            String nativeName,
            String sourceScript,
            String outputScript,
            String detail,
            String methodType,
            String engineKind,
            String layoutId,
            Integer layoutRevision,
            String layoutSourceSha256,
            LookupKind lookupKind,
            String artifactBinding,
            String catalogReadiness,
            Availability availability,
            String blockedReason,
            String blockedDetail,
            boolean defaultEnabled,
            String scope,
            String group,
            String variety,
            String sortKey,
            List<String> searchAliases,
            List<String> evidenceIds
    ) {
        this.id = require(id, "id");
        this.languageId = require(languageId, "languageId");
        this.inputMethodId = require(inputMethodId, "inputMethodId");
        this.localeTag = require(localeTag, "localeTag");
        this.displayName = require(displayName, "displayName");
        this.nativeName = require(nativeName, "nativeName");
        this.sourceScript = require(sourceScript, "sourceScript");
        this.outputScript = require(outputScript, "outputScript");
        this.detail = require(detail, "detail");
        this.methodType = require(methodType, "methodType");
        this.engineKind = require(engineKind, "engineKind");
        this.layoutId = require(layoutId, "layoutId");
        this.layoutRevision = layoutRevision;
        this.layoutSourceSha256 = optional(layoutSourceSha256);
        this.lookupKind = Objects.requireNonNull(lookupKind, "lookupKind");
        this.artifactBinding = optional(artifactBinding);
        this.catalogReadiness = require(catalogReadiness, "catalogReadiness");
        this.availability = Objects.requireNonNull(availability, "availability");
        this.blockedReason = optional(blockedReason);
        this.blockedDetail = optional(blockedDetail);
        this.defaultEnabled = defaultEnabled;
        this.scope = require(scope, "scope");
        this.group = optional(group);
        this.variety = optional(variety);
        this.sortKey = require(sortKey, "sortKey");
        this.searchAliases = frozenStrings(searchAliases, "searchAliases");
        this.evidenceIds = frozenStrings(evidenceIds, "evidenceIds");
        if ((layoutRevision == null) != (this.layoutSourceSha256 == null)) {
            throw new IllegalArgumentException("layout revision and source hash must be paired");
        }
        if (layoutRevision != null && layoutRevision < 1) {
            throw new IllegalArgumentException("layout revision must be positive");
        }
        if (this.layoutSourceSha256 != null
                && !this.layoutSourceSha256.matches("^[0-9a-f]{64}$")) {
            throw new IllegalArgumentException("layout source hash must be lowercase SHA-256");
        }
        if (availability == Availability.AVAILABLE) {
            if (this.artifactBinding == null
                    || this.blockedReason != null
                    || this.blockedDetail != null) {
                throw new IllegalArgumentException("available profile has inconsistent shipping metadata");
            }
        } else if (this.artifactBinding != null
                || this.blockedReason == null
                || this.blockedDetail == null) {
            throw new IllegalArgumentException("blocked profile has inconsistent shipping metadata");
        }
        if (defaultEnabled && availability != Availability.AVAILABLE) {
            throw new IllegalArgumentException("blocked profile cannot be enabled by default");
        }
    }

    public String id() {
        return id;
    }

    public String languageId() {
        return languageId;
    }

    public String inputMethodId() {
        return inputMethodId;
    }

    public String localeTag() {
        return localeTag;
    }

    public String displayName() {
        return displayName;
    }

    public String nativeName() {
        return nativeName;
    }

    public String sourceScript() {
        return sourceScript;
    }

    public String outputScript() {
        return outputScript;
    }

    public String detail() {
        return detail;
    }

    public String methodType() {
        return methodType;
    }

    public String engineKind() {
        return engineKind;
    }

    public String layoutId() {
        return layoutId;
    }

    /** Positive for generated selectable profiles; zero for legacy direct callers. */
    public int layoutRevision() {
        return layoutRevision == null ? 0 : layoutRevision;
    }

    public String layoutSourceSha256() {
        return layoutSourceSha256;
    }

    public boolean hasVersionedLayout() {
        return layoutRevision != null && layoutSourceSha256 != null;
    }

    public LookupKind lookupKind() {
        return lookupKind;
    }

    public ArtifactKind artifactKind() {
        return lookupKind == LookupKind.CONVERSION
                ? ArtifactKind.NCM
                : ArtifactKind.NKP;
    }

    /** Typed runtime binding independent from the artifact's file format. */
    public String artifactBinding() {
        return artifactBinding;
    }

    /** NKP compatibility accessor; null for conversion-map profiles. */
    public String packBinding() {
        return artifactKind() == ArtifactKind.NKP ? artifactBinding : null;
    }

    /** Conversion-map binding; null for direct and alias profiles. */
    public String conversionBinding() {
        return artifactKind() == ArtifactKind.NCM ? artifactBinding : null;
    }

    public String catalogReadiness() {
        return catalogReadiness;
    }

    public Availability availability() {
        return availability;
    }

    /**
     * A copy that is selectable because a reviewed transliteration map serves it.
     *
     * <p>The profile lock withholds this profile for want of a dictionary pack,
     * which is the correct gate for alias-decoder input and the wrong one for
     * deterministic transliteration. The original blocked reason is kept so the
     * lock's finding stays visible rather than being erased.
     */
    KeyboardProfile promotedForTransliteration(String mapId) {
        if (availability == Availability.AVAILABLE) {
            throw new IllegalStateException("profile is already selectable: " + id);
        }
        if (mapId == null || mapId.isEmpty()) {
            throw new IllegalStateException("transliteration promotion needs a map id: " + id);
        }
        return new KeyboardProfile(
                id,
                languageId,
                inputMethodId,
                localeTag,
                displayName,
                nativeName,
                sourceScript,
                outputScript,
                detail,
                methodType,
                engineKind,
                layoutId,
                layoutRevision,
                layoutSourceSha256,
                lookupKind,
                // The serving artifact is the reviewed map, not a dictionary pack.
                // Pack lookups simply find nothing, which is correct here: a
                // dictionary-free profile has no candidates to offer.
                mapId,
                catalogReadiness,
                Availability.AVAILABLE,
                null,
                null,
                defaultEnabled,
                scope,
                group,
                variety,
                sortKey,
                searchAliases,
                evidenceIds
        );
    }

    public boolean isAvailable() {
        return availability == Availability.AVAILABLE;
    }

    public String blockedReason() {
        return blockedReason;
    }

    public String blockedDetail() {
        return blockedDetail;
    }

    public boolean defaultEnabled() {
        return defaultEnabled;
    }

    public String scope() {
        return scope;
    }

    public String group() {
        return group;
    }

    public String variety() {
        return variety;
    }

    public String sortKey() {
        return sortKey;
    }

    public List<String> searchAliases() {
        return searchAliases;
    }

    public List<String> evidenceIds() {
        return evidenceIds;
    }

    private static String require(String value, String label) {
        Objects.requireNonNull(value, label);
        if (value.trim().isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        return value;
    }

    private static String optional(String value) {
        return value == null || value.trim().isEmpty() ? null : value;
    }

    private static List<String> frozenStrings(List<String> values, String label) {
        Objects.requireNonNull(values, label);
        List<String> copy = new ArrayList<>();
        for (String value : values) {
            copy.add(require(value, label + " item"));
        }
        return Collections.unmodifiableList(copy);
    }
}
