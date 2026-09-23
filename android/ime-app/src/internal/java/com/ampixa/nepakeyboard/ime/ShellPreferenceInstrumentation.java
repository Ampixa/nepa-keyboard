package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import android.view.View;
import android.widget.LinearLayout;

/** Proves the reviewed shell preferences reach the rendered keyboard, not just storage. */
public final class ShellPreferenceInstrumentation extends Instrumentation {
    private static final String EXPECTED_PACKAGE = "com.ampixa.nepakeyboard.ime.internal";
    private static final String PREFERENCES = "shell_preference_instrumentation";
    private static final String PROFILE_ID = "npi-Deva-NP";

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        int resultCode = Activity.RESULT_CANCELED;
        try {
            Context context = getTargetContext();
            assertEquals("internal application ID", EXPECTED_PACKAGE, context.getPackageName());
            KeyboardProfile profile = LanguageRegistry.find(PROFILE_ID);
            assertTrue("profile is selectable", profile != null && profile.isAvailable());

            KeyboardPreferences preferences = new KeyboardPreferences(context, PREFERENCES);
            preferences.clearForTesting();
            verifyDefaults(preferences, result);
            runOnMainSync(() -> verifyRendering(context, profile, preferences, result));
            verifyPersistence(context, preferences, result);
            preferences.clearForTesting();

            result.putString("status", "ok");
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            result.putString("status", "error");
            result.putString("error", failure.toString());
        }
        finish(resultCode, result);
    }

    /** The reference ships sound and vibration off; suggestions and preview stay on. */
    private void verifyDefaults(KeyboardPreferences preferences, Bundle result) {
        assertEquals("schema version", KeyboardPreferences.SCHEMA_VERSION,
                preferences.schemaVersionForTesting());
        assertEquals("default height", KeyboardMetrics.DEFAULT_HEIGHT_PERCENT,
                preferences.heightPercent());
        assertTrue("sound defaults off", !preferences.soundEnabled());
        assertTrue("haptics default off", !preferences.hapticsEnabled());
        assertTrue("key preview defaults on", preferences.keyPreviewEnabled());
        assertTrue("suggestions default on", preferences.suggestionsEnabled());
        result.putBoolean("shell_preference_defaults_verified", true);
    }

    private void verifyRendering(
            Context context,
            KeyboardProfile profile,
            KeyboardPreferences preferences,
            Bundle result
    ) {
        NepaInputView view = new NepaInputView(context, new NoOpListener());
        view.setProfile(profile);

        preferences.setHeightPercent(KeyboardMetrics.MIN_HEIGHT_PERCENT);
        view.applyPreferences(preferences);
        layoutForPixelWidth(view);
        int shortRowHeight = view.keyboardMetricsForTesting().rowHeightPx();
        int shortKeyHeight = view.keyboardMetricsForTesting().keyHeightPx();
        int shortRendered = renderedRowHeight(view);
        assertTrue("short geometry is valid", view.visualGeometryContractForTesting());

        preferences.setHeightPercent(KeyboardMetrics.MAX_HEIGHT_PERCENT);
        view.applyPreferences(preferences);
        layoutForPixelWidth(view);
        int tallRowHeight = view.keyboardMetricsForTesting().rowHeightPx();
        int tallKeyHeight = view.keyboardMetricsForTesting().keyHeightPx();
        int tallRendered = renderedRowHeight(view);
        assertTrue("tall geometry is valid", view.visualGeometryContractForTesting());

        assertTrue("row metrics grow with the preference", tallRowHeight > shortRowHeight);
        assertTrue("key metrics grow with the preference", tallKeyHeight > shortKeyHeight);
        assertTrue("rendered rows grow with the preference", tallRendered > shortRendered);
        assertEquals("rendered short row matches its metric", shortRowHeight, shortRendered);
        assertEquals("rendered tall row matches its metric", tallRowHeight, tallRendered);
        // 160/70 is well over 2x; require a clearly proportional, non-cosmetic change.
        assertTrue(
                "the height change is proportional",
                tallRendered >= (shortRendered * 3) / 2
        );
        result.putInt("row_height_at_min_percent", shortRendered);
        result.putInt("row_height_at_max_percent", tallRendered);
        result.putBoolean("shell_preference_height_render_verified", true);

        // The floor keeps keys reachable even at the smallest reviewed height.
        preferences.setHeightPercent(KeyboardMetrics.MIN_HEIGHT_PERCENT);
        view.applyPreferences(preferences);
        layoutForPixelWidth(view);
        assertTrue(
                "keys stay at or above the accessible floor",
                view.keyboardMetricsForTesting().keyHeightPx()
                        >= view.keyboardMetricsForTesting().minimumKeyHeightPx()
        );
        result.putBoolean("shell_preference_touch_floor_verified", true);

        preferences.setKeyPreviewEnabled(false);
        view.applyPreferences(preferences);
        assertTrue("preview disabled", !view.keyPreviewEnabledForTesting());
        assertTrue("no preview is showing", !view.keyPreviewShowingForTesting());
        preferences.setKeyPreviewEnabled(true);
        view.applyPreferences(preferences);
        assertTrue("preview re-enabled", view.keyPreviewEnabledForTesting());
        result.putBoolean("shell_preference_key_preview_verified", true);

        preferences.setSoundEnabled(true);
        preferences.setHapticsEnabled(true);
        view.applyPreferences(preferences);
        assertTrue("sound applied", view.keyboardSurfaceForTesting().soundEnabledForTesting());
        assertTrue("haptics applied", view.keyboardSurfaceForTesting().hapticsEnabledForTesting());
        preferences.setSoundEnabled(false);
        preferences.setHapticsEnabled(false);
        view.applyPreferences(preferences);
        assertTrue(
                "sound cleared",
                !view.keyboardSurfaceForTesting().soundEnabledForTesting()
        );
        assertTrue(
                "haptics cleared",
                !view.keyboardSurfaceForTesting().hapticsEnabledForTesting()
        );
        result.putBoolean("shell_preference_feedback_verified", true);

        verifyThemes(context, view, preferences, result);
        verifyAlternates(context, profile, result);
    }

    /** The reviewed long-press variants must reach the key surface and commit correctly. */
    private void verifyAlternates(Context context, KeyboardProfile profile, Bundle result) {
        java.util.List<String> committed = new java.util.ArrayList<>();
        NepaInputView view = new NepaInputView(context, new AlternateListener(committed));
        view.setProfile(profile);
        layoutForPixelWidth(view);

        KeyAlternatesCatalog catalog = KeyAlternatesCatalog.load(context);
        assertTrue("the alternates catalog is populated", catalog.keyCountForTesting() > 0);
        KeyboardLayouts.Layout layout = catalog.attach(
                KeyboardLayouts.forProfile(profile, false, false, false)
        );
        int withAlternates = 0;
        for (java.util.List<KeySpec> row : layout.rows()) {
            for (KeySpec key : row) {
                if (key.hasAlternates()) {
                    withAlternates++;
                    assertTrue(
                            "only text keys carry alternates",
                            key.action() == KeySpec.Action.TEXT
                    );
                    for (String alternate : key.alternates()) {
                        assertTrue("alternate is not empty", !alternate.isEmpty());
                        assertTrue(
                                "alternate differs from the key",
                                !alternate.equals(key.text())
                        );
                    }
                }
            }
        }
        assertTrue("the layout declares alternates", withAlternates > 0);

        KeySpec target = null;
        for (java.util.List<KeySpec> row : layout.rows()) {
            for (KeySpec key : row) {
                if (key.hasAlternates() && target == null) {
                    target = key;
                }
            }
        }
        assertTrue("a key with alternates was found", target != null);

        KeyboardSurface surface = view.keyboardSurfaceForTesting();
        KeyPreviewOverlay overlay = view.keyPreviewOverlayForTesting();
        assertTrue(
                "long press opens the variant strip",
                surface.performLongPressForTesting(target.keyId())
        );
        assertTrue("the strip is showing", overlay.alternatesShowing());
        assertEquals(
                "the strip holds every declared variant",
                target.alternates().size(),
                overlay.alternateCountForTesting()
        );
        assertEquals(
                "the first variant is highlighted",
                target.alternates().get(0),
                overlay.highlightedAlternateForTesting()
        );
        assertTrue("the variant commits", overlay.commitHighlightedAlternate());
        assertEquals("exactly one variant committed", 1, committed.size());
        assertEquals(
                "the highlighted variant was committed",
                target.alternates().get(0),
                committed.get(0)
        );
        assertTrue("the strip closes after committing", !overlay.alternatesShowing());

        // A variant may only reach scalars the layout itself can already emit.
        java.util.Set<String> layoutScalars = new java.util.HashSet<>();
        for (String layerId : new String[]{"base", "shift", "symbols", "numeric"}) {
            KeyboardLayouts.Layout layer = KeyboardLayouts.forProfile(
                    profile,
                    "shift".equals(layerId),
                    "symbols".equals(layerId),
                    "numeric".equals(layerId)
            );
            for (java.util.List<KeySpec> row : layer.rows()) {
                for (KeySpec key : row) {
                    if (key.text() != null) {
                        for (int offset = 0; offset < key.text().length(); offset++) {
                            layoutScalars.add(String.valueOf(key.text().charAt(offset)));
                        }
                    }
                }
            }
        }
        for (java.util.List<KeySpec> row : layout.rows()) {
            for (KeySpec key : row) {
                for (String alternate : key.alternates()) {
                    for (int offset = 0; offset < alternate.length(); offset++) {
                        assertTrue(
                                "alternate stays within the layout repertoire: " + alternate,
                                layoutScalars.contains(String.valueOf(alternate.charAt(offset)))
                        );
                    }
                }
            }
        }

        result.putInt("keys_with_alternates", withAlternates);
        result.putInt("alternate_catalog_keys", catalog.keyCountForTesting());
        result.putString("alternate_committed", committed.get(0));
        result.putBoolean("shell_preference_alternates_verified", true);
    }

    private static final class AlternateListener implements NepaInputView.Listener {
        private final java.util.List<String> committed;

        AlternateListener(java.util.List<String> committed) {
            this.committed = committed;
        }

        @Override
        public void onKey(KeySpec key, SpatialKeyStroke stroke) {
        }

        @Override
        public void onProfileSelected(String profileId) {
        }

        @Override
        public void onCandidateSelected(SuggestionQuery owner, SuggestionCandidate candidate) {
        }

        @Override
        public void onSuggestionRetry() {
        }

        @Override
        public void onManageLanguages() {
        }

        @Override
        public void onOtherKeyboards() {
        }

        @Override
        public void onKeyAlternate(KeySpec key, String alternate) {
            committed.add(alternate);
        }
    }

    /** Every bundled theme must resolve, restyle the surface, and survive a bad value. */
    private void verifyThemes(
            Context context,
            NepaInputView view,
            KeyboardPreferences preferences,
            Bundle result
    ) {
        java.util.List<String> ids = KeyboardTheme.bundledIds();
        assertTrue("bundled themes exist", ids.size() >= 4);
        assertEquals("system theme is first", KeyboardTheme.SYSTEM_ID, ids.get(0));

        java.util.Set<Integer> surfaces = new java.util.HashSet<>();
        for (String id : ids) {
            preferences.setThemeId(id);
            view.applyPreferences(preferences);
            layoutForPixelWidth(view);
            KeyboardTheme active = view.activeThemeForTesting();
            assertEquals("theme applied: " + id, id, active.id());
            assertEquals(
                    "key surface adopts the theme colour: " + id,
                    active.keyColor(),
                    view.keyboardSurfaceForTesting().keyColorForTesting()
            );
            assertEquals(
                    "key borders follow the theme: " + id,
                    active.keyBorders(),
                    view.keyboardSurfaceForTesting().keyBordersForTesting()
            );
            assertTrue(
                    "toolbar and emoji chrome adopt the theme: " + id,
                    view.chromeThemeMatchesForTesting(active)
            );
            view.showLanguagePicker();
            layoutForPixelWidth(view);
            assertTrue(
                    "language picker adopts the theme: " + id,
                    view.pickerThemeMatchesForTesting(active)
            );
            assertTrue("language picker closes after theme check", view.hidePicker());
            // Visibility changes request a new layout pass in a real window. The
            // detached harness must perform that pass before inspecting bounds.
            layoutForPixelWidth(view);
            assertTrue("theme geometry stays valid: " + id,
                    view.visualGeometryContractForTesting());
            surfaces.add(active.surfaceColor());
        }
        assertTrue("themes are visually distinct", surfaces.size() >= 3);

        // A stale or hand-edited identifier must not leave the keyboard unstyled.
        preferences.setThemeId("no-such-theme");
        view.applyPreferences(preferences);
        assertEquals(
                "unknown theme falls back to the system theme",
                KeyboardTheme.SYSTEM_ID,
                view.activeThemeForTesting().id()
        );
        preferences.setThemeId(KeyboardTheme.SYSTEM_ID);
        view.applyPreferences(preferences);
        result.putInt("bundled_theme_count", ids.size());
        result.putBoolean("shell_preference_theme_verified", true);
    }

    /** A fresh reader must observe the stored value, and a stale entry must not crash. */
    private void verifyPersistence(
            Context context,
            KeyboardPreferences preferences,
            Bundle result
    ) {
        preferences.setHeightPercent(128);
        preferences.setSuggestionsEnabled(false);
        KeyboardPreferences reopened = new KeyboardPreferences(context, PREFERENCES);
        assertEquals("height persists", 128, reopened.heightPercent());
        assertTrue("suggestions persist", !reopened.suggestionsEnabled());

        // Values outside the reviewed range degrade to the bounds instead of rendering
        // an unusable keyboard.
        preferences.setHeightPercent(5);
        assertEquals(
                "below-range height clamps",
                KeyboardMetrics.MIN_HEIGHT_PERCENT,
                new KeyboardPreferences(context, PREFERENCES).heightPercent()
        );
        preferences.setHeightPercent(9000);
        assertEquals(
                "above-range height clamps",
                KeyboardMetrics.MAX_HEIGHT_PERCENT,
                new KeyboardPreferences(context, PREFERENCES).heightPercent()
        );
        result.putBoolean("shell_preference_persistence_verified", true);
    }

    private static int renderedRowHeight(NepaInputView view) {
        KeyboardSurface surface = view.keyboardSurfaceForTesting();
        assertTrue("keyboard rendered rows", surface.getChildCount() > 0);
        View row = surface.getChildAt(0);
        assertTrue("row is a layout", row instanceof LinearLayout);
        return row.getHeight();
    }

    private static void layoutForPixelWidth(View view) {
        view.measure(
                View.MeasureSpec.makeMeasureSpec(1080, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(1600, View.MeasureSpec.AT_MOST)
        );
        view.layout(0, 0, 1080, view.getMeasuredHeight());
    }

    private static void assertTrue(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void assertEquals(String label, Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + ", got " + actual);
        }
    }

    private static final class NoOpListener implements NepaInputView.Listener {
        @Override
        public void onKey(KeySpec key, SpatialKeyStroke stroke) {
        }

        @Override
        public void onProfileSelected(String profileId) {
        }

        @Override
        public void onCandidateSelected(SuggestionQuery owner, SuggestionCandidate candidate) {
        }

        @Override
        public void onSuggestionRetry() {
        }

        @Override
        public void onManageLanguages() {
        }

        @Override
        public void onOtherKeyboards() {
        }
    }
}
