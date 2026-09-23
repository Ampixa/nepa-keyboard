package com.ampixa.nepakeyboard.ime;

import java.util.Objects;

/**
 * Pure transitions for the keyboard shell.
 *
 * <p>The reducer never touches Android state, so every legal transition is directly
 * testable and a stale intent can never silently change what is rendered.
 */
public final class KeyboardUiReducer {
    /** Reviewed double-tap window for caps lock, matched to the reference keyboard. */
    static final long CAPS_LOCK_DOUBLE_TAP_MILLIS = 800L;

    private KeyboardUiReducer() {
    }

    /** The panel an editor opens before any user transition. */
    public static KeyboardUiState.Panel panelForEditor(EditorMode editorMode) {
        Objects.requireNonNull(editorMode, "editorMode");
        switch (editorMode) {
            case NUMBER:
            case NUMBER_PASSWORD:
                return KeyboardUiState.Panel.NUMBER;
            case PHONE:
                return KeyboardUiState.Panel.PHONE;
            case DATE_TIME:
                return KeyboardUiState.Panel.DATE_TIME;
            default:
                return KeyboardUiState.Panel.ALPHABETIC;
        }
    }

    /** A new or restarted editor always discards transient panel, shift, and popup state. */
    public static KeyboardUiState onStartInput(
            KeyboardUiState state,
            String profileId,
            EditorMode editorMode
    ) {
        Objects.requireNonNull(state, "state");
        return state
                .withProfile(profileId)
                .withEditorMode(editorMode)
                .withPanel(panelForEditor(editorMode))
                .withShiftState(KeyboardUiState.ShiftState.OFF, 0L)
                .withPopupVisible(false);
    }

    /** Switching profiles returns to the editor's own panel and clears shift and popups. */
    public static KeyboardUiState onProfileSelected(KeyboardUiState state, String profileId) {
        Objects.requireNonNull(state, "state");
        return state
                .withProfile(profileId)
                .withPanel(panelForEditor(state.editorMode()))
                .withShiftState(KeyboardUiState.ShiftState.OFF, 0L)
                .withPopupVisible(false);
    }

    /**
     * Shift cycles off, one-shot, and locked. A second tap inside the reviewed window
     * locks; a later tap releases instead of locking.
     */
    public static KeyboardUiState onShiftTapped(KeyboardUiState state, long nowMillis) {
        Objects.requireNonNull(state, "state");
        if (nowMillis < 0L) {
            throw new IllegalArgumentException("shift tap time must not be negative");
        }
        if (state.panel() != KeyboardUiState.Panel.ALPHABETIC) {
            return state;
        }
        switch (state.shiftState()) {
            case OFF:
                return state.withShiftState(KeyboardUiState.ShiftState.ONE_SHOT, nowMillis);
            case ONE_SHOT:
                boolean withinWindow =
                        nowMillis >= state.lastShiftTapMillis()
                                && nowMillis - state.lastShiftTapMillis()
                                <= CAPS_LOCK_DOUBLE_TAP_MILLIS;
                return withinWindow
                        ? state.withShiftState(KeyboardUiState.ShiftState.LOCKED, nowMillis)
                        : state.withShiftState(KeyboardUiState.ShiftState.OFF, nowMillis);
            case LOCKED:
                return state.withShiftState(KeyboardUiState.ShiftState.OFF, nowMillis);
            default:
                throw new IllegalStateException("unknown shift state: " + state.shiftState());
        }
    }

    /** Explicit shift assignment, used by generated conformance paths and tests. */
    public static KeyboardUiState onShiftSet(KeyboardUiState state, boolean shifted) {
        Objects.requireNonNull(state, "state");
        if (state.panel() != KeyboardUiState.Panel.ALPHABETIC) {
            return state;
        }
        return state.withShiftState(
                shifted ? KeyboardUiState.ShiftState.ONE_SHOT : KeyboardUiState.ShiftState.OFF,
                0L
        );
    }

    /** Committing text consumes a one-shot shift but never releases caps lock. */
    public static KeyboardUiState onTextCommitted(KeyboardUiState state) {
        Objects.requireNonNull(state, "state");
        if (state.shiftState() != KeyboardUiState.ShiftState.ONE_SHOT) {
            return state;
        }
        return state.withShiftState(KeyboardUiState.ShiftState.OFF, state.lastShiftTapMillis());
    }

    /** The symbol panel is reachable only from an alphabetic editor. */
    public static KeyboardUiState onSymbolsRequested(KeyboardUiState state) {
        Objects.requireNonNull(state, "state");
        if (state.editorMode().numericPanel()) {
            return state;
        }
        return state.withPanel(KeyboardUiState.Panel.SYMBOLS_PRIMARY);
    }

    /**
     * The emoji panel is reachable from any editor that accepts arbitrary text. Numeric,
     * phone, and date editors keep their own panel.
     */
    public static KeyboardUiState onEmojiRequested(KeyboardUiState state) {
        Objects.requireNonNull(state, "state");
        if (state.editorMode().numericPanel()) {
            return state;
        }
        return state.withPanel(KeyboardUiState.Panel.EMOJI);
    }

    /** Returning to letters restores the editor's own panel. */
    public static KeyboardUiState onLettersRequested(KeyboardUiState state) {
        Objects.requireNonNull(state, "state");
        return state.withPanel(panelForEditor(state.editorMode()));
    }

    /**
     * Turns phonetic input on or off. Numeric editors keep their own panel, so the
     * toggle is refused there rather than silently doing nothing visible.
     */
    public static KeyboardUiState onTransliterationToggled(KeyboardUiState state) {
        Objects.requireNonNull(state, "state");
        if (state.editorMode().numericPanel()) {
            return state;
        }
        return state
                .withTransliterating(!state.transliterating())
                .withPanel(KeyboardUiState.Panel.ALPHABETIC);
    }

    public static KeyboardUiState onPopupShown(KeyboardUiState state) {
        Objects.requireNonNull(state, "state");
        return state.withPopupVisible(true);
    }

    public static KeyboardUiState onPopupDismissed(KeyboardUiState state) {
        Objects.requireNonNull(state, "state");
        return state.withPopupVisible(false);
    }
}
