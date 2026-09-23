package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Runtime view of the reviewed generated shipping-profile lock. */
public final class LanguageRegistry {
    public static final String ENGLISH_ID = "eng-Latn-US";
    public static final String NEPALI_DIRECT_ID = "npi-Deva-NP";
    public static final String NEPALI_ROMAN_ID = "npi-Latn-Deva-NP";
    public static final String LIMBU_DIRECT_ID = "lif-Limb-NP";

    private static final List<KeyboardProfile> ALL;
    private static final List<KeyboardProfile> AVAILABLE;
    private static final Map<String, KeyboardProfile> BY_ID;

    /** Profiles selectable only through a reviewed transliteration map. */
    private static final Map<String, String> TRANSLITERATION_ONLY;

    static {
        List<KeyboardProfile> generated = GeneratedProfileCatalog.createProfiles();
        List<KeyboardProfile> available = new ArrayList<>();
        Map<String, KeyboardProfile> byId = new LinkedHashMap<>();
        for (KeyboardProfile profile : generated) {
            if (byId.put(profile.id(), profile) != null) {
                throw new IllegalStateException("duplicate generated profile: " + profile.id());
            }
            if (profile.isAvailable()) {
                available.add(profile);
            }
        }
        if (generated.size() != GeneratedProfileCatalog.PROFILE_COUNT
                || available.size() != GeneratedProfileCatalog.SELECTABLE_COUNT
                || !byId.containsKey(ENGLISH_ID)
                || !byId.containsKey(NEPALI_DIRECT_ID)
                || !byId.containsKey(NEPALI_ROMAN_ID)) {
            throw new IllegalStateException("generated profile catalog invariants failed");
        }

        // A language with no dictionary cannot satisfy the lock's pack gate, which is
        // exactly why it has no keyboard. The reviewed transliteration supplement
        // grants such a profile deterministic phonetic input without editing the lock,
        // so these are appended to the selectable set rather than changing it.
        String[] pairs = GeneratedTransliterationProfiles.PROFILE_MAP_PAIRS;
        if (pairs.length != GeneratedTransliterationProfiles.PROFILE_COUNT * 2) {
            throw new IllegalStateException("transliteration profile supplement is malformed");
        }
        Map<String, String> transliterationOnly = new LinkedHashMap<>();
        for (int index = 0; index < pairs.length; index += 2) {
            String profileId = pairs[index];
            KeyboardProfile profile = byId.get(profileId);
            if (profile == null) {
                throw new IllegalStateException(
                        "transliteration supplement names unknown profile: " + profileId
                );
            }
            if (profile.isAvailable()) {
                throw new IllegalStateException(
                        "transliteration supplement duplicates a selectable profile: " + profileId
                );
            }
            if (transliterationOnly.put(profileId, pairs[index + 1]) != null) {
                throw new IllegalStateException(
                        "transliteration supplement repeats profile: " + profileId
                );
            }
            // Replace the entry everywhere, not just in the selectable list: layout
            // and subtype lookups gate on the profile's own availability.
            KeyboardProfile promoted = profile.promotedForTransliteration(pairs[index + 1]);
            byId.put(profileId, promoted);
            available.add(promoted);
        }

        // Rebuild the full list from the promoted map so every consumer sees one
        // view. Settings sections a profile by its own availability, so leaving the
        // original blocked object here would file a supplement profile under "Later"
        // and leave the user no way to enable it.
        List<KeyboardProfile> all = new ArrayList<>(generated.size());
        for (KeyboardProfile profile : generated) {
            all.add(byId.get(profile.id()));
        }

        TRANSLITERATION_ONLY = Collections.unmodifiableMap(transliterationOnly);
        ALL = Collections.unmodifiableList(all);
        AVAILABLE = Collections.unmodifiableList(available);
        BY_ID = Collections.unmodifiableMap(byId);
    }

    /** The map asset serving a transliteration-only profile, or null. */
    static String transliterationMapAsset(String profileId) {
        return profileId == null ? null : TRANSLITERATION_ONLY.get(profileId);
    }

    /**
     * Profiles that have an installed Android subtype.
     *
     * <p>The subtype resource is generated from the reviewed profile catalog, which
     * this build does not modify, so a transliteration-only profile is selectable in
     * the keyboard's own picker but is not offered by the system language switcher.
     */
    public static List<KeyboardProfile> subtypeBacked() {
        List<KeyboardProfile> backed = new ArrayList<>();
        for (KeyboardProfile profile : AVAILABLE) {
            if (!isTransliterationOnly(profile.id())) {
                backed.add(profile);
            }
        }
        return Collections.unmodifiableList(backed);
    }

    /** Whether this profile can only be typed phonetically. */
    public static boolean isTransliterationOnly(String profileId) {
        return profileId != null && TRANSLITERATION_ONLY.containsKey(profileId);
    }

    private LanguageRegistry() {
    }

    public static List<KeyboardProfile> all() {
        return ALL;
    }

    public static List<KeyboardProfile> available() {
        return AVAILABLE;
    }

    public static KeyboardProfile find(String id) {
        return id == null ? null : BY_ID.get(id);
    }

    static String catalogId() {
        return GeneratedProfileCatalog.CATALOG_ID;
    }

    static int targetCountForTesting() {
        return GeneratedProfileCatalog.TARGET_COUNT;
    }

    static int scriptCountForTesting() {
        return GeneratedProfileCatalog.SCRIPT_COUNT;
    }
}
