package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.view.View;

import java.util.ArrayList;
import java.util.List;

/** Proves the bundled emoji panel loads, filters, commits, and remembers recents. */
public final class EmojiPanelInstrumentation extends Instrumentation {
    private static final String EXPECTED_PACKAGE = "com.ampixa.nepakeyboard.ime.internal";
    private static final String PREFERENCES = "emoji_panel_instrumentation";
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

            EmojiCatalog catalog = EmojiCatalog.load(context);
            verifyCatalog(catalog, result);

            KeyboardPreferences preferences = new KeyboardPreferences(context, PREFERENCES);
            preferences.clearForTesting();
            verifyRecents(preferences, result);
            preferences.clearForTesting();
            runOnMainSync(() -> verifyPanel(context, profile, preferences, result));
            preferences.clearForTesting();

            result.putString("status", "ok");
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            result.putString("status", "error");
            result.putString("error", failure.toString());
        }
        finish(resultCode, result);
    }

    private void verifyCatalog(EmojiCatalog catalog, Bundle result) {
        assertTrue("catalog has categories", !catalog.categories().isEmpty());
        int counted = 0;
        for (EmojiCatalog.Category category : catalog.categories()) {
            assertTrue("category is populated: " + category.id(), !category.emoji().isEmpty());
            for (String emoji : category.emoji()) {
                assertTrue("emoji is not empty", !emoji.isEmpty());
                counted++;
            }
        }
        assertEquals("counted emoji match the catalog total", catalog.totalEmoji(), counted);
        // The catalog gates on platform support, so a modern device sees the full set.
        assertTrue("catalog is substantial", counted > 1000);
        result.putInt("emoji_total", counted);
        result.putInt("emoji_categories", catalog.categories().size());
        result.putInt("emoji_api_level", Build.VERSION.SDK_INT);
        result.putBoolean("emoji_catalog_verified", true);
    }

    private void verifyRecents(KeyboardPreferences preferences, Bundle result) {
        assertTrue("recents start empty", preferences.recentEmoji().isEmpty());
        preferences.recordRecentEmoji("😀");
        preferences.recordRecentEmoji("🎉");
        assertEquals("most recent is first", "🎉", preferences.recentEmoji().get(0));
        assertEquals("recents size", 2, preferences.recentEmoji().size());

        // Re-using an emoji moves it to the front instead of duplicating it.
        preferences.recordRecentEmoji("😀");
        assertEquals("reuse promotes", "😀", preferences.recentEmoji().get(0));
        assertEquals("reuse does not duplicate", 2, preferences.recentEmoji().size());

        List<String> pushed = new ArrayList<>();
        for (int index = 0; index < KeyboardPreferences.MAX_RECENT_EMOJI + 8; index++) {
            String emoji = new String(Character.toChars(0x1F300 + index));
            pushed.add(emoji);
            preferences.recordRecentEmoji(emoji);
        }
        List<String> recents = preferences.recentEmoji();
        assertEquals(
                "recents stay bounded",
                KeyboardPreferences.MAX_RECENT_EMOJI,
                recents.size()
        );
        assertEquals(
                "newest push is first",
                pushed.get(pushed.size() - 1),
                recents.get(0)
        );
        result.putBoolean("emoji_recents_verified", true);
    }

    private void verifyPanel(
            Context context,
            KeyboardProfile profile,
            KeyboardPreferences preferences,
            Bundle result
    ) {
        List<String> committed = new ArrayList<>();
        boolean[] backspaced = new boolean[1];
        NepaInputView view = new NepaInputView(context, new PanelListener(committed, backspaced));
        view.setProfile(profile);
        view.applyPreferences(preferences);

        assertTrue("panel starts hidden", !view.emojiPanelVisible());
        assertTrue("emoji toggle announces closed", view.emojiToggleStateForTesting(false));
        view.toggleEmojiPanel();
        layoutForPixelWidth(view);
        assertTrue("panel opens", view.emojiPanelVisible());
        assertTrue("emoji toggle visibly announces open", view.emojiToggleStateForTesting(true));

        EmojiPanel panel = view.emojiPanelForTesting();
        // Recents plus every supported category.
        assertTrue("panel has pages", panel.pageCountForTesting() > 1);
        assertTrue(
                "a first run does not open on the empty recents page",
                !EmojiPanel.RECENTS_CATEGORY_ID.equals(panel.activeCategoryForTesting())
        );
        assertTrue("grid is populated", panel.visibleEmojiCountForTesting() > 0);
        assertTrue("emoji controls keep 48 dp touch targets",
                panel.touchTargetsMeetMinimumForTesting());

        assertTrue("smileys page is selectable", panel.selectPageForTesting("smileys-people"));
        assertEquals(
                "selected page is active",
                "smileys-people",
                panel.activeCategoryForTesting()
        );
        int smileys = panel.visibleEmojiCountForTesting();
        assertTrue("smileys page is populated", smileys > 0);

        assertTrue("flags page is selectable", panel.selectPageForTesting("flags"));
        assertTrue("flags page is populated", panel.visibleEmojiCountForTesting() > 0);

        assertTrue("an emoji can be chosen", panel.selectEmojiForTesting(0));
        assertEquals("one emoji was committed", 1, committed.size());
        String chosen = committed.get(0);
        assertTrue("committed emoji is not empty", !chosen.isEmpty());
        assertTrue("emoji backspace control is clickable", panel.performBackspaceForTesting());
        assertTrue("emoji backspace reaches the listener", backspaced[0]);

        view.recordEmojiUse(chosen);
        assertEquals(
                "the choice is remembered",
                chosen,
                preferences.recentEmoji().get(0)
        );
        assertTrue("recents page is selectable", panel.selectPageForTesting(
                EmojiPanel.RECENTS_CATEGORY_ID
        ));
        assertEquals(
                "recents page shows the choice",
                1,
                panel.visibleEmojiCountForTesting()
        );

        view.toggleEmojiPanel();
        layoutForPixelWidth(view);
        assertTrue("panel closes", !view.emojiPanelVisible());
        assertTrue("emoji toggle visibly returns closed", view.emojiToggleStateForTesting(false));
        assertTrue("keys return", view.renderedRowCountForTesting() > 0);
        assertTrue("key geometry is valid again", view.visualGeometryContractForTesting());

        // A numeric editor keeps its own panel; emoji must not override it.
        view.setEditorMode(EditorMode.NUMBER);
        view.toggleEmojiPanel();
        layoutForPixelWidth(view);
        assertTrue("numeric editor refuses the emoji panel", !view.emojiPanelVisible());

        view.setEditorMode(EditorMode.TEXT);
        view.toggleEmojiPanel();
        layoutForPixelWidth(view);
        assertTrue("panel reopens for text", view.emojiPanelVisible());
        // Switching profile while the panel is open must return to keys.
        view.setProfile(profile);
        layoutForPixelWidth(view);
        assertTrue("profile change closes the panel", !view.emojiPanelVisible());

        result.putInt("emoji_smileys_visible", smileys);
        result.putString("emoji_committed", chosen);
        result.putBoolean("emoji_panel_verified", true);
        result.putBoolean("emoji_backspace_wired", backspaced[0]);
        result.putBoolean("emoji_touch_targets_verified", true);
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

    private static final class PanelListener implements NepaInputView.Listener {
        private final List<String> committed;
        private final boolean[] backspaced;

        PanelListener(List<String> committed, boolean[] backspaced) {
            this.committed = committed;
            this.backspaced = backspaced;
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
        public void onEmojiSelected(String emoji) {
            committed.add(emoji);
        }

        @Override
        public void onEmojiBackspace() {
            backspaced[0] = true;
        }
    }
}
