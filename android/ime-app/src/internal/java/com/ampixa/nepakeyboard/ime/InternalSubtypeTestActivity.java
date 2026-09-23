package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.content.Context;
import android.os.Bundle;
import android.text.InputType;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputConnectionWrapper;
import android.view.inputmethod.InputMethodManager;
import android.widget.EditText;

import java.util.concurrent.atomic.AtomicInteger;

/** Internal-only editor host for service-bound subtype compatibility evidence. */
public final class InternalSubtypeTestActivity extends Activity {
    private TrackingEditText editor;
    private boolean destroyed;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        editor = new TrackingEditText(this);
        editor.setSingleLine(false);
        editor.setInputType(
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        );
        editor.setContentDescription("Internal subtype compatibility editor");
        setContentView(editor);
        getWindow().setSoftInputMode(
                WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE
        );
    }

    @Override
    protected void onResume() {
        super.onResume();
        editor.requestFocus();
    }

    @Override
    protected void onDestroy() {
        destroyed = true;
        super.onDestroy();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            editor.post(this::showImeForTesting);
        }
    }

    boolean editorIsServedForTesting() {
        InputMethodManager manager = getSystemService(InputMethodManager.class);
        return editor != null
                && editor.hasWindowFocus()
                && editor.hasFocus()
                && manager != null
                && manager.isActive(editor);
    }

    boolean editorHasInputFocusForTesting() {
        return editorHasWindowFocusForTesting() && editorHasViewFocusForTesting();
    }

    boolean editorHasWindowFocusForTesting() {
        return editor != null && editor.hasWindowFocus();
    }

    boolean editorHasViewFocusForTesting() {
        return editor != null && editor.hasFocus();
    }

    boolean destroyedForTesting() {
        return destroyed;
    }

    void setEditorTextForTesting(String text) {
        editor.setText(text);
        editor.setSelection(text.length());
    }

    String editorTextForTesting() {
        return editor.getText().toString();
    }

    void setEditorSelectionForTesting(int start, int end) {
        editor.setSelection(start, end);
    }

    int editorSelectionStartForTesting() {
        return editor.getSelectionStart();
    }

    int editorSelectionEndForTesting() {
        return editor.getSelectionEnd();
    }

    void restartAsNormalForTesting() {
        restartWithInputTypeForTesting(
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        );
    }

    void restartAsPasswordForTesting() {
        restartWithInputTypeForTesting(
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
        );
    }

    boolean showImeForTesting() {
        editor.requestFocus();
        InputMethodManager manager = getSystemService(InputMethodManager.class);
        return manager != null
                && manager.showSoftInput(editor, InputMethodManager.SHOW_IMPLICIT);
    }

    boolean hideImeForTesting() {
        InputMethodManager manager = getSystemService(InputMethodManager.class);
        return manager != null
                && manager.hideSoftInputFromWindow(editor.getWindowToken(), 0);
    }

    int normalContextReadCountForTesting() {
        return editor.normalContextReadCount();
    }

    int privateContextReadCountForTesting() {
        return editor.privateContextReadCount();
    }

    void resetContextReadCountsForTesting() {
        editor.resetContextReadCounts();
    }

    private void restartWithInputTypeForTesting(int inputType) {
        int selectionStart = editor.getSelectionStart();
        int selectionEnd = editor.getSelectionEnd();
        editor.setInputType(inputType);
        int length = editor.length();
        if (selectionStart >= 0 && selectionEnd >= 0) {
            editor.setSelection(
                    Math.min(selectionStart, length),
                    Math.min(selectionEnd, length)
            );
        }
        InputMethodManager manager = getSystemService(InputMethodManager.class);
        if (manager != null) {
            manager.restartInput(editor);
        }
    }

    private static final class TrackingEditText extends EditText {
        private final AtomicInteger normalContextReads = new AtomicInteger();
        private final AtomicInteger privateContextReads = new AtomicInteger();

        TrackingEditText(Context context) {
            super(context);
        }

        @Override
        public InputConnection onCreateInputConnection(EditorInfo outAttrs) {
            InputConnection target = super.onCreateInputConnection(outAttrs);
            if (target == null) {
                return null;
            }
            final boolean privateConnection = isPrivateInputType(outAttrs.inputType);
            return new InputConnectionWrapper(target, false) {
                @Override
                public CharSequence getTextBeforeCursor(int length, int flags) {
                    if (privateConnection) {
                        privateContextReads.incrementAndGet();
                    } else {
                        normalContextReads.incrementAndGet();
                    }
                    return super.getTextBeforeCursor(length, flags);
                }
            };
        }

        int normalContextReadCount() {
            return normalContextReads.get();
        }

        int privateContextReadCount() {
            return privateContextReads.get();
        }

        void resetContextReadCounts() {
            normalContextReads.set(0);
            privateContextReads.set(0);
        }

        private static boolean isPrivateInputType(int inputType) {
            int inputClass = inputType & InputType.TYPE_MASK_CLASS;
            int variation = inputType & InputType.TYPE_MASK_VARIATION;
            if (inputClass == InputType.TYPE_CLASS_NUMBER) {
                return variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD;
            }
            return inputClass == InputType.TYPE_CLASS_TEXT
                    && (variation == InputType.TYPE_TEXT_VARIATION_PASSWORD
                    || variation == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                    || variation == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD);
        }
    }
}
