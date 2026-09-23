package com.ampixa.nepakeyboard.ime;

/**
 * Process-local identity for one field/profile suggestion activation.
 *
 * <p>Activations are deliberately compared by object identity. Their numeric ID is
 * diagnostic test metadata only and must not be persisted or treated as a user or
 * editor identity.</p>
 */
public final class SuggestionActivation {
    private final long id;
    private final String profileId;
    private final KeyboardProfile profile;

    /** Legacy/test activation without an exact profile-object binding. */
    SuggestionActivation(long id, String profileId) {
        if (id <= 0) {
            throw new IllegalArgumentException("activation ID must be positive");
        }
        if (profileId != null && profileId.trim().isEmpty()) {
            throw new IllegalArgumentException("profile ID must not be empty");
        }
        this.id = id;
        this.profileId = profileId;
        this.profile = null;
    }

    private SuggestionActivation(long id, KeyboardProfile profile) {
        if (id <= 0) {
            throw new IllegalArgumentException("activation ID must be positive");
        }
        this.id = id;
        this.profile = java.util.Objects.requireNonNull(profile, "profile");
        this.profileId = profile.id();
    }

    static SuggestionActivation active(long id, KeyboardProfile profile) {
        return new SuggestionActivation(id, profile);
    }

    static SuggestionActivation suspended(long id) {
        return new SuggestionActivation(id, (String) null);
    }

    public long id() {
        return id;
    }

    /** Returns the active profile ID, or null for a suspended activation. */
    public String profileId() {
        return profileId;
    }

    public boolean isActive() {
        return profileId != null;
    }

    /** Production activations bind the exact immutable profile object by identity. */
    boolean ownsProfile(KeyboardProfile expected) {
        if (expected == null || !isActive()) {
            return false;
        }
        return profile == null
                ? profileId.equals(expected.id())
                : profile == expected;
    }
}
