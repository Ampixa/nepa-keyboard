package com.ampixa.nepakeyboard.ime;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.Objects;

/**
 * Durable keyboard shell preferences.
 *
 * <p>Stored separately from language selection so a settings migration can never disturb
 * the reviewed profile state. Every read is clamped, so a hand-edited or stale value
 * degrades to the reviewed default instead of rendering an unusable keyboard.
 */
public final class KeyboardPreferences {
    private static final String DEFAULT_PREFERENCES = "keyboard_shell";
    private static final String KEY_SCHEMA_VERSION = "schema_version";
    private static final String KEY_HEIGHT_PERCENT = "height_percent";
    private static final String KEY_SOUND_ENABLED = "sound_enabled";
    private static final String KEY_HAPTICS_ENABLED = "haptics_enabled";
    private static final String KEY_KEY_PREVIEW_ENABLED = "key_preview_enabled";
    private static final String KEY_SUGGESTIONS_ENABLED = "suggestions_enabled";
    private static final String KEY_THEME_ID = "theme_id";
    private static final String KEY_RECENT_EMOJI = "recent_emoji";
    private static final String RECENT_EMOJI_SEPARATOR = "\n";

    /** Reviewed recents depth. */
    static final int MAX_RECENT_EMOJI = 15;

    /** Current schema. Bump only alongside an explicit migration step. */
    static final int SCHEMA_VERSION = 1;

    static final boolean DEFAULT_SOUND_ENABLED = false;
    static final boolean DEFAULT_HAPTICS_ENABLED = false;
    static final boolean DEFAULT_KEY_PREVIEW_ENABLED = true;
    static final boolean DEFAULT_SUGGESTIONS_ENABLED = true;

    private final SharedPreferences preferences;

    public KeyboardPreferences(Context context) {
        this(context, DEFAULT_PREFERENCES);
    }

    KeyboardPreferences(Context context, String preferenceName) {
        Objects.requireNonNull(context, "context");
        preferences = context.getSharedPreferences(
                Objects.requireNonNull(preferenceName, "preferenceName"),
                Context.MODE_PRIVATE
        );
        migrate();
    }

    /**
     * Applies any pending schema migration. A store written by a newer build is left
     * untouched and read through the same clamping accessors.
     */
    private void migrate() {
        int stored = readInt(KEY_SCHEMA_VERSION, 0);
        if (stored == SCHEMA_VERSION) {
            return;
        }
        if (stored > SCHEMA_VERSION) {
            return;
        }
        preferences.edit().putInt(KEY_SCHEMA_VERSION, SCHEMA_VERSION).apply();
    }

    public int heightPercent() {
        return KeyboardMetrics.clampHeightPercent(
                readInt(KEY_HEIGHT_PERCENT, KeyboardMetrics.DEFAULT_HEIGHT_PERCENT)
        );
    }

    public void setHeightPercent(int heightPercent) {
        preferences.edit()
                .putInt(KEY_HEIGHT_PERCENT, KeyboardMetrics.clampHeightPercent(heightPercent))
                .apply();
    }

    public boolean soundEnabled() {
        return readBoolean(KEY_SOUND_ENABLED, DEFAULT_SOUND_ENABLED);
    }

    public void setSoundEnabled(boolean enabled) {
        preferences.edit().putBoolean(KEY_SOUND_ENABLED, enabled).apply();
    }

    public boolean hapticsEnabled() {
        return readBoolean(KEY_HAPTICS_ENABLED, DEFAULT_HAPTICS_ENABLED);
    }

    public void setHapticsEnabled(boolean enabled) {
        preferences.edit().putBoolean(KEY_HAPTICS_ENABLED, enabled).apply();
    }

    public boolean keyPreviewEnabled() {
        return readBoolean(KEY_KEY_PREVIEW_ENABLED, DEFAULT_KEY_PREVIEW_ENABLED);
    }

    public void setKeyPreviewEnabled(boolean enabled) {
        preferences.edit().putBoolean(KEY_KEY_PREVIEW_ENABLED, enabled).apply();
    }

    public boolean suggestionsEnabled() {
        return readBoolean(KEY_SUGGESTIONS_ENABLED, DEFAULT_SUGGESTIONS_ENABLED);
    }

    public void setSuggestionsEnabled(boolean enabled) {
        preferences.edit().putBoolean(KEY_SUGGESTIONS_ENABLED, enabled).apply();
    }

    public String themeId() {
        String stored = readString(KEY_THEME_ID, KeyboardUiState.DEFAULT_THEME_ID);
        return stored.isEmpty() ? KeyboardUiState.DEFAULT_THEME_ID : stored;
    }

    public void setThemeId(String themeId) {
        Objects.requireNonNull(themeId, "themeId");
        if (themeId.isEmpty()) {
            throw new IllegalArgumentException("theme id must not be empty");
        }
        preferences.edit().putString(KEY_THEME_ID, themeId).apply();
    }

    /** Most recent first, bounded to the reviewed depth. */
    public java.util.List<String> recentEmoji() {
        String stored = readString(KEY_RECENT_EMOJI, "");
        if (stored.isEmpty()) {
            return java.util.Collections.emptyList();
        }
        java.util.List<String> recents = new java.util.ArrayList<>();
        for (String value : stored.split(RECENT_EMOJI_SEPARATOR, -1)) {
            if (!value.isEmpty() && !recents.contains(value) && recents.size() < MAX_RECENT_EMOJI) {
                recents.add(value);
            }
        }
        return java.util.Collections.unmodifiableList(recents);
    }

    /** Records a use, moving an existing entry to the front rather than duplicating it. */
    public void recordRecentEmoji(String emoji) {
        Objects.requireNonNull(emoji, "emoji");
        if (emoji.isEmpty() || emoji.contains(RECENT_EMOJI_SEPARATOR)) {
            throw new IllegalArgumentException("emoji must be non-empty and single-line");
        }
        java.util.List<String> next = new java.util.ArrayList<>();
        next.add(emoji);
        for (String existing : recentEmoji()) {
            if (!existing.equals(emoji) && next.size() < MAX_RECENT_EMOJI) {
                next.add(existing);
            }
        }
        preferences.edit()
                .putString(KEY_RECENT_EMOJI, String.join(RECENT_EMOJI_SEPARATOR, next))
                .apply();
    }

    void registerStateListener(SharedPreferences.OnSharedPreferenceChangeListener listener) {
        preferences.registerOnSharedPreferenceChangeListener(listener);
    }

    void unregisterStateListener(SharedPreferences.OnSharedPreferenceChangeListener listener) {
        preferences.unregisterOnSharedPreferenceChangeListener(listener);
    }

    void clearForTesting() {
        preferences.edit().clear().apply();
        migrate();
    }

    int schemaVersionForTesting() {
        return readInt(KEY_SCHEMA_VERSION, 0);
    }

    /** A stale entry of the wrong type must degrade to the default, never crash the IME. */
    private int readInt(String key, int fallback) {
        try {
            return preferences.getInt(key, fallback);
        } catch (ClassCastException staleEntry) {
            return fallback;
        }
    }

    private boolean readBoolean(String key, boolean fallback) {
        try {
            return preferences.getBoolean(key, fallback);
        } catch (ClassCastException staleEntry) {
            return fallback;
        }
    }

    private String readString(String key, String fallback) {
        try {
            String value = preferences.getString(key, fallback);
            return value == null ? fallback : value;
        } catch (ClassCastException staleEntry) {
            return fallback;
        }
    }
}
