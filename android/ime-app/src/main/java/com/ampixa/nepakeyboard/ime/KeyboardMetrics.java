package com.ampixa.nepakeyboard.ime;

import android.content.res.Configuration;
import android.content.res.Resources;
import android.util.DisplayMetrics;
import android.util.TypedValue;

import java.util.Objects;

/**
 * Width- and configuration-aware key geometry.
 *
 * <p>Key height follows the reviewed reference metric per configuration and is scaled by
 * the user's height preference. An accessible floor is enforced in every configuration,
 * which is an intentional deviation from the reference on short landscape screens.
 */
public final class KeyboardMetrics {
    /** Reviewed height-preference bounds, matched to the reference keyboard. */
    static final int MIN_HEIGHT_PERCENT = 70;
    static final int MAX_HEIGHT_PERCENT = 160;
    static final int DEFAULT_HEIGHT_PERCENT = 100;
    static final int HEIGHT_STEP_PERCENT = 2;

    /** Reviewed reference key heights in density-independent pixels. */
    static final int BASE_KEY_HEIGHT_DP = 48;
    static final int LANDSCAPE_KEY_HEIGHT_DP = 36;
    static final int LARGE_KEY_HEIGHT_DP = 72;
    static final int LARGE_LANDSCAPE_KEY_HEIGHT_DP = 60;

    /** Accessible floors. Landscape is deliberately lower so five rows still fit. */
    static final int MIN_KEY_HEIGHT_DP = 48;
    static final int MIN_LANDSCAPE_KEY_HEIGHT_DP = 40;

    private static final int LARGE_SCREEN_WIDTH_DP = 600;
    private static final int KEY_GAP_DP = 2;

    private final int keyHeightPx;
    private final int keyGapPx;
    private final int rowHeightPx;
    private final int minimumKeyHeightPx;
    private final int heightPercent;
    private final boolean landscape;

    private KeyboardMetrics(
            int keyHeightPx,
            int keyGapPx,
            int minimumKeyHeightPx,
            int heightPercent,
            boolean landscape
    ) {
        this.keyHeightPx = keyHeightPx;
        this.keyGapPx = keyGapPx;
        this.rowHeightPx = keyHeightPx + (2 * keyGapPx);
        this.minimumKeyHeightPx = minimumKeyHeightPx;
        this.heightPercent = heightPercent;
        this.landscape = landscape;
    }

    public static KeyboardMetrics forResources(Resources resources, int heightPercent) {
        Objects.requireNonNull(resources, "resources");
        Configuration configuration = resources.getConfiguration();
        DisplayMetrics display = resources.getDisplayMetrics();
        boolean landscape = configuration.orientation == Configuration.ORIENTATION_LANDSCAPE;
        boolean large = configuration.smallestScreenWidthDp >= LARGE_SCREEN_WIDTH_DP;
        int referenceDp;
        if (large) {
            referenceDp = landscape ? LARGE_LANDSCAPE_KEY_HEIGHT_DP : LARGE_KEY_HEIGHT_DP;
        } else {
            referenceDp = landscape ? LANDSCAPE_KEY_HEIGHT_DP : BASE_KEY_HEIGHT_DP;
        }
        int clampedPercent = clampHeightPercent(heightPercent);
        int floorDp = landscape ? MIN_LANDSCAPE_KEY_HEIGHT_DP : MIN_KEY_HEIGHT_DP;
        int floorPx = px(display, floorDp);
        int scaledPx = Math.round(px(display, referenceDp) * (clampedPercent / 100f));
        return new KeyboardMetrics(
                Math.max(scaledPx, floorPx),
                px(display, KEY_GAP_DP),
                floorPx,
                clampedPercent,
                landscape
        );
    }

    /** Clamps to the reviewed range and snaps to the reviewed step. */
    static int clampHeightPercent(int heightPercent) {
        int bounded = Math.max(MIN_HEIGHT_PERCENT, Math.min(MAX_HEIGHT_PERCENT, heightPercent));
        int steps = Math.round((bounded - MIN_HEIGHT_PERCENT) / (float) HEIGHT_STEP_PERCENT);
        return MIN_HEIGHT_PERCENT + (steps * HEIGHT_STEP_PERCENT);
    }

    public int keyHeightPx() {
        return keyHeightPx;
    }

    public int keyGapPx() {
        return keyGapPx;
    }

    public int rowHeightPx() {
        return rowHeightPx;
    }

    public int minimumKeyHeightPx() {
        return minimumKeyHeightPx;
    }

    public int heightPercent() {
        return heightPercent;
    }

    public boolean landscape() {
        return landscape;
    }

    /** Total height of a rendered keyboard body, excluding surface padding. */
    public int keyboardHeightPx(int rowCount) {
        if (rowCount <= 0) {
            throw new IllegalArgumentException("row count must be positive");
        }
        return rowHeightPx * rowCount;
    }

    private static int px(DisplayMetrics display, int dp) {
        return Math.round(TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP,
                dp,
                display
        ));
    }
}
