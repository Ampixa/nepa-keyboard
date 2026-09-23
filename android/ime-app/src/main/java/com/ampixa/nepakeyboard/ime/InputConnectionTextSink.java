package com.ampixa.nepakeyboard.ime;

import android.view.KeyEvent;
import android.view.inputmethod.InputConnection;

import java.util.Objects;

/** Android editor adapter for {@link ComposingSession}. */
public final class InputConnectionTextSink implements TextSink {
    private final InputConnection connection;
    private final boolean allowCommittedDeleteContext;
    private int selectionStart;
    private int selectionEnd;

    public InputConnectionTextSink(
            InputConnection connection,
            boolean allowCommittedDeleteContext
    ) {
        this(connection, allowCommittedDeleteContext, -1, -1);
    }

    public InputConnectionTextSink(
            InputConnection connection,
            boolean allowCommittedDeleteContext,
            int selectionStart,
            int selectionEnd
    ) {
        this.connection = Objects.requireNonNull(connection, "connection");
        this.allowCommittedDeleteContext = allowCommittedDeleteContext;
        if ((selectionStart < 0) != (selectionEnd < 0)) {
            throw new IllegalArgumentException("selection endpoints must both be known or unknown");
        }
        this.selectionStart = selectionStart;
        this.selectionEnd = selectionEnd;
    }

    @Override
    public boolean setComposingText(String text) {
        return connection.setComposingText(text, 1);
    }

    @Override
    public boolean commitText(String text) {
        return connection.commitText(text, 1);
    }

    @Override
    public boolean finishComposingText() {
        return connection.finishComposingText();
    }

    @Override
    public boolean deletePreviousGrapheme() {
        if (!selectionKnown()) {
            return sendDeleteKeyEvent();
        }
        if (selectionStart != selectionEnd) {
            return deleteSelection();
        }
        if (!allowCommittedDeleteContext) {
            return deleteOneCodePoint();
        }
        CharSequence preceding;
        try {
            preceding = connection.getTextBeforeCursor(
                    GraphemeBackspace.COMMITTED_CONTEXT_UTF16_LIMIT,
                    0
            );
        } catch (RuntimeException unavailable) {
            return deleteOneCodePoint();
        }
        if (preceding == null || preceding.length() == 0) {
            return deleteOneCodePoint();
        }
        // Keep the editor-owned text in this stack frame only. It is never
        // retained by ComposingSession or exposed to SuggestionQuery.
        String context = preceding.toString();
        if (!GraphemeBackspace.hasCompleteTrailingGrapheme(
                context,
                GraphemeBackspace.COMMITTED_CONTEXT_UTF16_LIMIT,
                selectionStart
        )) {
            return deleteOneCodePoint();
        }
        int boundary = GraphemeBackspace.previousBoundary(context);
        int deleteUtf16Units = context.length() - boundary;
        if (deleteUtf16Units <= 0) {
            return deleteOneCodePoint();
        }
        try {
            if (connection.deleteSurroundingText(deleteUtf16Units, 0)) {
                return true;
            }
        } catch (RuntimeException unavailable) {
            // Fall through to the no-read, one-code-point compatibility path.
        }
        return deleteOneCodePoint();
    }

    @Override
    public boolean deleteOneCodePoint() {
        if (!selectionKnown()) {
            return sendDeleteKeyEvent();
        }
        if (selectionStart != selectionEnd) {
            return deleteSelection();
        }
        try {
            if (connection.deleteSurroundingTextInCodePoints(1, 0)) {
                return true;
            }
        } catch (RuntimeException unavailable) {
            // Fall through to the legacy key-event path.
        }
        return sendDeleteKeyEvent();
    }

    private boolean selectionKnown() {
        return selectionStart >= 0 && selectionEnd >= 0;
    }

    private boolean deleteSelection() {
        try {
            if (connection.commitText("", 1)) {
                invalidateSelection();
                return true;
            }
        } catch (RuntimeException unavailable) {
            // Fall through to the editor's delete-key compatibility path.
        }
        boolean deleted = sendDeleteKeyEvent();
        if (deleted) {
            invalidateSelection();
        }
        return deleted;
    }

    private void invalidateSelection() {
        selectionStart = -1;
        selectionEnd = -1;
    }

    private boolean sendDeleteKeyEvent() {
        try {
            boolean down = connection.sendKeyEvent(
                    new KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_DEL)
            );
            boolean up = connection.sendKeyEvent(
                    new KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_DEL)
            );
            return down && up;
        } catch (RuntimeException unavailable) {
            return false;
        }
    }
}
