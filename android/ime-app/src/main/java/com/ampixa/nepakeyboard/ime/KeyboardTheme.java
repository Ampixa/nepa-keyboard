package com.ampixa.nepakeyboard.ime;

import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Color;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * A bundled keyboard theme.
 *
 * <p>Themes are code-defined rather than downloadable: the keyboard stays offline and a
 * theme can never arrive from a server or carry executable content.
 */
public final class KeyboardTheme {
    /** Follows the system light/dark setting; the default for a fresh install. */
    public static final String SYSTEM_ID = KeyboardUiState.DEFAULT_THEME_ID;

    private final String id;
    private final int surfaceColor;
    private final int keyColor;
    private final int actionKeyColor;
    private final int keyTextColor;
    private final int pressedColor;
    private final int textColor;
    private final int secondaryTextColor;
    private final boolean keyBorders;

    private KeyboardTheme(
            String id,
            int surfaceColor,
            int keyColor,
            int actionKeyColor,
            int keyTextColor,
            int pressedColor,
            int textColor,
            int secondaryTextColor,
            boolean keyBorders
    ) {
        this.id = id;
        this.surfaceColor = surfaceColor;
        this.keyColor = keyColor;
        this.actionKeyColor = actionKeyColor;
        this.keyTextColor = keyTextColor;
        this.pressedColor = pressedColor;
        this.textColor = textColor;
        this.secondaryTextColor = secondaryTextColor;
        this.keyBorders = keyBorders;
    }

    public String id() {
        return id;
    }

    public int surfaceColor() {
        return surfaceColor;
    }

    public int keyColor() {
        return keyColor;
    }

    public int actionKeyColor() {
        return actionKeyColor;
    }

    public int keyTextColor() {
        return keyTextColor;
    }

    public int pressedColor() {
        return pressedColor;
    }

    public int textColor() {
        return textColor;
    }

    public int secondaryTextColor() {
        return secondaryTextColor;
    }

    public boolean keyBorders() {
        return keyBorders;
    }

    /** Display name resource for the settings chooser. */
    public int displayNameResource() {
        switch (id) {
            case SYSTEM_ID:
                return R.string.theme_system;
            case "classic":
                return R.string.theme_classic;
            case "black":
                return R.string.theme_black;
            case "bright":
                return R.string.theme_bright;
            case "white":
                return R.string.theme_white;
            default:
                throw new IllegalStateException("unknown theme: " + id);
        }
    }

    private static final KeyboardTheme DARK_SYSTEM = new KeyboardTheme(
            SYSTEM_ID,
            Color.rgb(30, 29, 34),
            Color.rgb(53, 51, 58),
            Color.rgb(42, 40, 47),
            Color.rgb(244, 242, 248),
            Color.rgb(91, 87, 103),
            Color.rgb(245, 243, 248),
            Color.rgb(196, 191, 203),
            true
    );
    private static final KeyboardTheme LIGHT_SYSTEM = new KeyboardTheme(
            SYSTEM_ID,
            Color.rgb(240, 238, 244),
            Color.rgb(255, 255, 255),
            Color.rgb(226, 224, 232),
            Color.rgb(34, 32, 38),
            Color.rgb(198, 194, 211),
            Color.rgb(34, 32, 38),
            Color.rgb(91, 87, 99),
            true
    );

    private static final Map<String, KeyboardTheme> BUNDLED;

    static {
        Map<String, KeyboardTheme> themes = new LinkedHashMap<>();
        themes.put(SYSTEM_ID, LIGHT_SYSTEM);
        themes.put("classic", new KeyboardTheme(
                "classic",
                Color.rgb(38, 50, 56),
                Color.rgb(55, 71, 79),
                Color.rgb(45, 59, 66),
                Color.rgb(219, 219, 219),
                Color.rgb(84, 110, 122),
                Color.rgb(219, 219, 219),
                Color.rgb(176, 190, 197),
                true
        ));
        themes.put("black", new KeyboardTheme(
                "black",
                Color.rgb(18, 18, 18),
                Color.rgb(18, 18, 18),
                Color.rgb(28, 28, 28),
                Color.rgb(219, 219, 219),
                Color.rgb(60, 60, 60),
                Color.rgb(219, 219, 219),
                Color.rgb(158, 158, 158),
                false
        ));
        themes.put("bright", new KeyboardTheme(
                "bright",
                Color.rgb(236, 239, 241),
                Color.rgb(236, 239, 241),
                Color.rgb(207, 216, 220),
                Color.rgb(34, 34, 34),
                Color.rgb(176, 190, 197),
                Color.rgb(34, 34, 34),
                Color.rgb(96, 106, 112),
                false
        ));
        themes.put("white", new KeyboardTheme(
                "white",
                Color.rgb(236, 239, 241),
                Color.rgb(255, 255, 255),
                Color.rgb(215, 222, 226),
                Color.rgb(34, 34, 34),
                Color.rgb(176, 190, 197),
                Color.rgb(34, 34, 34),
                Color.rgb(96, 106, 112),
                true
        ));
        BUNDLED = Collections.unmodifiableMap(themes);
    }

    /** Stable chooser order; the system theme is always first. */
    public static java.util.List<String> bundledIds() {
        return Collections.unmodifiableList(new java.util.ArrayList<>(BUNDLED.keySet()));
    }

    /**
     * Resolves a stored identifier. An unknown or stale value degrades to the system
     * theme rather than leaving the keyboard unstyled.
     */
    public static KeyboardTheme resolve(Context context, String themeId) {
        Objects.requireNonNull(context, "context");
        if (themeId == null || SYSTEM_ID.equals(themeId) || !BUNDLED.containsKey(themeId)) {
            return systemTheme(context);
        }
        return BUNDLED.get(themeId);
    }

    private static KeyboardTheme systemTheme(Context context) {
        boolean dark = (context.getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        return dark ? DARK_SYSTEM : LIGHT_SYSTEM;
    }
}
