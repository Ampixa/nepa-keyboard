package com.ampixa.nepakeyboard.ime;

import java.util.Objects;

/**
 * Immutable keyboard shell state.
 *
 * <p>Every visible mode is derived from this value, so a rendered keyboard can never
 * disagree with the state that produced it.
 */
public final class KeyboardUiState {
    /** Visible key panels. Panels beyond the reviewed layout-v1 layers are declared but gated. */
    public enum Panel {
        ALPHABETIC("base"),
        SYMBOLS_PRIMARY("symbols"),
        SYMBOLS_SECONDARY(null),
        EMOJI(null),
        NUMBER("numeric"),
        PHONE("numeric"),
        DATE_TIME("numeric"),
        EMAIL(null),
        URL(null);

        private final String layoutV1Layer;

        Panel(String layoutV1Layer) {
            this.layoutV1Layer = layoutV1Layer;
        }

        /** The reviewed layout-v1 layer, or null when the panel needs the layout-v2 contract. */
        String layoutV1Layer() {
            return layoutV1Layer;
        }

        boolean rendersWithLayoutV1() {
            return layoutV1Layer != null;
        }
    }

    public enum ShiftState {
        OFF,
        ONE_SHOT,
        LOCKED;

        boolean rendersShiftLayer() {
            return this != OFF;
        }
    }

    static final String DEFAULT_THEME_ID = "nepa-default";

    private final String profileId;
    private final EditorMode editorMode;
    private final Panel panel;
    private final ShiftState shiftState;
    private final int emojiCategory;
    private final String themeId;
    private final boolean popupVisible;
    private final boolean transliterating;
    private final long lastShiftTapMillis;

    private KeyboardUiState(
            String profileId,
            EditorMode editorMode,
            Panel panel,
            ShiftState shiftState,
            int emojiCategory,
            String themeId,
            boolean popupVisible,
            boolean transliterating,
            long lastShiftTapMillis
    ) {
        this.profileId = require(profileId, "profileId");
        this.editorMode = Objects.requireNonNull(editorMode, "editorMode");
        this.panel = Objects.requireNonNull(panel, "panel");
        this.shiftState = Objects.requireNonNull(shiftState, "shiftState");
        if (emojiCategory < 0) {
            throw new IllegalArgumentException("emoji category must not be negative");
        }
        this.emojiCategory = emojiCategory;
        this.themeId = require(themeId, "themeId");
        this.popupVisible = popupVisible;
        this.transliterating = transliterating;
        if (lastShiftTapMillis < 0L) {
            throw new IllegalArgumentException("last shift tap must not be negative");
        }
        this.lastShiftTapMillis = lastShiftTapMillis;
        if (panel != Panel.ALPHABETIC && shiftState == ShiftState.LOCKED) {
            throw new IllegalArgumentException("caps lock is only valid on the alphabetic panel");
        }
    }

    public static KeyboardUiState initial(String profileId) {
        return new KeyboardUiState(
                profileId,
                EditorMode.TEXT,
                Panel.ALPHABETIC,
                ShiftState.OFF,
                0,
                DEFAULT_THEME_ID,
                false,
                false,
                0L
        );
    }

    public String profileId() {
        return profileId;
    }

    public EditorMode editorMode() {
        return editorMode;
    }

    public Panel panel() {
        return panel;
    }

    public ShiftState shiftState() {
        return shiftState;
    }

    public int emojiCategory() {
        return emojiCategory;
    }

    public String themeId() {
        return themeId;
    }

    public boolean popupVisible() {
        return popupVisible;
    }

    /** Whether Roman input is being transliterated into the profile's script. */
    public boolean transliterating() {
        return transliterating;
    }

    long lastShiftTapMillis() {
        return lastShiftTapMillis;
    }

    /** Whether the reviewed shift layer is rendered for the current panel. */
    public boolean rendersShiftLayer() {
        return panel == Panel.ALPHABETIC && shiftState.rendersShiftLayer();
    }

    /** The reviewed layout-v1 layer for the current panel. */
    public String layoutLayerId() {
        String layer = panel.layoutV1Layer();
        if (layer == null) {
            throw new IllegalStateException(
                    "panel requires the layout-v2 contract: " + panel
            );
        }
        if (Panel.ALPHABETIC.equals(panel) && shiftState.rendersShiftLayer()) {
            return "shift";
        }
        return layer;
    }

    KeyboardUiState withProfile(String nextProfileId) {
        if (profileId.equals(nextProfileId)) {
            return this;
        }
        return new KeyboardUiState(
                nextProfileId,
                editorMode,
                panel,
                shiftState,
                emojiCategory,
                themeId,
                false,
                transliterating,
                0L
        );
    }

    KeyboardUiState withEditorMode(EditorMode nextEditorMode) {
        return new KeyboardUiState(
                profileId,
                nextEditorMode,
                panel,
                shiftState,
                emojiCategory,
                themeId,
                popupVisible,
                transliterating,
                lastShiftTapMillis
        );
    }

    KeyboardUiState withPanel(Panel nextPanel) {
        ShiftState nextShiftState = nextPanel == Panel.ALPHABETIC
                ? shiftState
                : ShiftState.OFF;
        return new KeyboardUiState(
                profileId,
                editorMode,
                nextPanel,
                nextShiftState,
                emojiCategory,
                themeId,
                false,
                transliterating,
                lastShiftTapMillis
        );
    }

    KeyboardUiState withShiftState(ShiftState nextShiftState, long tapMillis) {
        return new KeyboardUiState(
                profileId,
                editorMode,
                panel,
                nextShiftState,
                emojiCategory,
                themeId,
                popupVisible,
                transliterating,
                tapMillis
        );
    }

    KeyboardUiState withEmojiCategory(int nextEmojiCategory) {
        return new KeyboardUiState(
                profileId,
                editorMode,
                panel,
                shiftState,
                nextEmojiCategory,
                themeId,
                popupVisible,
                transliterating,
                lastShiftTapMillis
        );
    }

    KeyboardUiState withTheme(String nextThemeId) {
        return new KeyboardUiState(
                profileId,
                editorMode,
                panel,
                shiftState,
                emojiCategory,
                nextThemeId,
                popupVisible,
                transliterating,
                lastShiftTapMillis
        );
    }

    KeyboardUiState withTransliterating(boolean next) {
        if (transliterating == next) {
            return this;
        }
        return new KeyboardUiState(
                profileId,
                editorMode,
                panel,
                ShiftState.OFF,
                emojiCategory,
                themeId,
                false,
                next,
                0L
        );
    }

    KeyboardUiState withPopupVisible(boolean nextPopupVisible) {
        if (popupVisible == nextPopupVisible) {
            return this;
        }
        return new KeyboardUiState(
                profileId,
                editorMode,
                panel,
                shiftState,
                emojiCategory,
                themeId,
                nextPopupVisible,
                transliterating,
                lastShiftTapMillis
        );
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof KeyboardUiState)) {
            return false;
        }
        KeyboardUiState value = (KeyboardUiState) other;
        return emojiCategory == value.emojiCategory
                && popupVisible == value.popupVisible
                && transliterating == value.transliterating
                && lastShiftTapMillis == value.lastShiftTapMillis
                && profileId.equals(value.profileId)
                && editorMode == value.editorMode
                && panel == value.panel
                && shiftState == value.shiftState
                && themeId.equals(value.themeId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
                profileId,
                editorMode,
                panel,
                shiftState,
                emojiCategory,
                themeId,
                popupVisible,
                transliterating,
                lastShiftTapMillis
        );
    }

    @Override
    public String toString() {
        return "KeyboardUiState{profile=" + profileId
                + ", editor=" + editorMode
                + ", panel=" + panel
                + ", shift=" + shiftState
                + ", emojiCategory=" + emojiCategory
                + ", theme=" + themeId
                + ", popup=" + popupVisible
                + ", transliterating=" + transliterating
                + "}";
    }

    private static String require(String value, String label) {
        Objects.requireNonNull(value, label);
        if (value.isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        return value;
    }
}
