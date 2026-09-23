package com.ampixa.nepakeyboard.ime;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/** Persistent enabled-profile and active-profile state with safe fallbacks. */
public final class LanguagePreferences {
    private static final String DEFAULT_PREFERENCES = "keyboard_profiles";
    private static final String KEY_ENABLED = "enabled";
    private static final String KEY_ACTIVE = "active";
    private static final String KEY_PENDING_SUBTYPE = "pending_subtype";
    private static final String KEY_CATALOG_ID = "catalog_id";
    private static final Object STATE_LOCK = new Object();

    private final SharedPreferences preferences;

    public LanguagePreferences(Context context) {
        this(context, DEFAULT_PREFERENCES);
    }

    LanguagePreferences(Context context, String preferenceName) {
        preferences = context.getSharedPreferences(preferenceName, Context.MODE_PRIVATE);
    }

    public List<KeyboardProfile> enabledProfiles() {
        synchronized (STATE_LOCK) {
            State state = readState();
            List<KeyboardProfile> result = new ArrayList<>();
            for (KeyboardProfile profile : LanguageRegistry.available()) {
                if (state.enabledIds.contains(profile.id())) {
                    result.add(profile);
                }
            }
            return result;
        }
    }

    public boolean isEnabled(String profileId) {
        synchronized (STATE_LOCK) {
            return readState().enabledIds.contains(profileId);
        }
    }

    public boolean setEnabled(String profileId, boolean enabled) {
        synchronized (STATE_LOCK) {
            KeyboardProfile profile = LanguageRegistry.find(profileId);
            if (profile == null || !profile.isAvailable()) {
                return false;
            }
            State state = readState();
            if (enabled) {
                state.enabledIds.add(profileId);
            } else {
                if (!state.enabledIds.contains(profileId) || state.enabledIds.size() == 1) {
                    return false;
                }
                state.enabledIds.remove(profileId);
                if (profileId.equals(state.active.id())) {
                    state.active = firstEnabled(state.enabledIds);
                    state.pending = state.active;
                }
            }
            writeState(state);
            return true;
        }
    }

    public KeyboardProfile activeProfile() {
        synchronized (STATE_LOCK) {
            return readState().active;
        }
    }

    /** Backward-compatible active selection; new callers should use {@link #requestActive}. */
    public boolean setActive(String profileId) {
        return requestActive(profileId);
    }

    /** Records the latest in-product selection until Android reports the same subtype. */
    public boolean requestActive(String profileId) {
        synchronized (STATE_LOCK) {
            KeyboardProfile profile = LanguageRegistry.find(profileId);
            State state = readState();
            if (profile == null
                    || !profile.isAvailable()
                    || !state.enabledIds.contains(profileId)) {
                return false;
            }
            state.active = profile;
            state.pending = profile;
            writeState(state);
            return true;
        }
    }

    /**
     * Reconciles one exact generated Android subtype observation.
     *
     * <p>A matching pending profile acknowledges an in-product request. With no pending
     * request, an explicit Android selection wins and is added to the quick-switch set. A
     * different observation cannot overwrite a newer pending in-product request.</p>
     */
    public KeyboardProfile observePlatformProfile(String profileId) {
        synchronized (STATE_LOCK) {
            State state = readState();
            KeyboardProfile observed = LanguageRegistry.find(profileId);
            if (observed == null || !observed.isAvailable()) {
                // Unknown, removed, or malformed platform state must not silently
                // replace the user's active profile. Mark that exact profile for
                // re-publication to Android so the service can converge again.
                state.pending = state.active;
                writeState(state);
                return state.active;
            }
            if (state.pending != null && !state.pending.id().equals(observed.id())) {
                return state.pending;
            }
            state.enabledIds.add(observed.id());
            state.active = observed;
            state.pending = null;
            writeState(state);
            return observed;
        }
    }

    /** Returns the exact subtype still requested from Android, or null after convergence. */
    public KeyboardProfile pendingProfile() {
        synchronized (STATE_LOCK) {
            return readState().pending;
        }
    }

    /** Registers a process-local observer for settings changes made by any app surface. */
    void registerStateListener(SharedPreferences.OnSharedPreferenceChangeListener listener) {
        preferences.registerOnSharedPreferenceChangeListener(listener);
    }

    void unregisterStateListener(SharedPreferences.OnSharedPreferenceChangeListener listener) {
        preferences.unregisterOnSharedPreferenceChangeListener(listener);
    }

    public KeyboardProfile cycle() {
        synchronized (STATE_LOCK) {
            State state = readState();
            List<KeyboardProfile> enabled = new ArrayList<>();
            int index = 0;
            for (KeyboardProfile profile : LanguageRegistry.available()) {
                if (state.enabledIds.contains(profile.id())) {
                    if (profile.id().equals(state.active.id())) {
                        index = enabled.size();
                    }
                    enabled.add(profile);
                }
            }
            KeyboardProfile next = enabled.get((index + 1) % enabled.size());
            state.active = next;
            state.pending = next;
            writeState(state);
            return next;
        }
    }

    void clearForTesting() {
        synchronized (STATE_LOCK) {
            preferences.edit().clear().apply();
        }
    }

    private State readState() {
        Set<String> stored = preferences.getStringSet(KEY_ENABLED, null);
        Set<String> enabled = new LinkedHashSet<>();
        if (stored == null) {
            for (KeyboardProfile profile : LanguageRegistry.available()) {
                if (profile.defaultEnabled()) {
                    enabled.add(profile.id());
                }
            }
        } else {
            for (KeyboardProfile profile : LanguageRegistry.available()) {
                if (stored.contains(profile.id())) {
                    enabled.add(profile.id());
                }
            }
        }
        if (enabled.isEmpty()) {
            enabled.add(LanguageRegistry.available().get(0).id());
        }

        String savedActiveId = preferences.getString(KEY_ACTIVE, null);
        KeyboardProfile savedActive = LanguageRegistry.find(savedActiveId);
        KeyboardProfile active = savedActive != null
                && savedActive.isAvailable()
                && enabled.contains(savedActive.id())
                ? savedActive
                : firstEnabled(enabled);

        String savedPendingId = preferences.getString(KEY_PENDING_SUBTYPE, null);
        KeyboardProfile savedPending = LanguageRegistry.find(savedPendingId);
        KeyboardProfile pending = savedPending != null
                && savedPending.isAvailable()
                && enabled.contains(savedPending.id())
                && savedPending.id().equals(active.id())
                ? savedPending
                : null;

        State state = new State(enabled, active, pending);
        if (!LanguageRegistry.catalogId().equals(preferences.getString(KEY_CATALOG_ID, null))
                || stored == null
                || !enabled.equals(stored)
                || !active.id().equals(savedActiveId)
                || (pending == null ? savedPendingId != null : !pending.id().equals(savedPendingId))) {
            writeState(state);
        }
        return state;
    }

    private KeyboardProfile firstEnabled(Set<String> enabledIds) {
        for (KeyboardProfile profile : LanguageRegistry.available()) {
            if (enabledIds.contains(profile.id())) {
                return profile;
            }
        }
        throw new IllegalStateException("profile state has no enabled fallback");
    }

    private void writeState(State state) {
        SharedPreferences.Editor editor = preferences.edit()
                .putStringSet(KEY_ENABLED, new HashSet<>(state.enabledIds))
                .putString(KEY_ACTIVE, state.active.id())
                .putString(KEY_CATALOG_ID, LanguageRegistry.catalogId());
        if (state.pending == null) {
            editor.remove(KEY_PENDING_SUBTYPE);
        } else {
            editor.putString(KEY_PENDING_SUBTYPE, state.pending.id());
        }
        editor.apply();
    }

    private static final class State {
        private final Set<String> enabledIds;
        private KeyboardProfile active;
        private KeyboardProfile pending;

        State(
                Set<String> enabledIds,
                KeyboardProfile active,
                KeyboardProfile pending
        ) {
            this.enabledIds = new LinkedHashSet<>(enabledIds);
            this.active = active;
            this.pending = pending;
        }
    }
}
