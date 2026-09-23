package com.ampixa.nepakeyboard.ime;

import android.text.InputType;
import android.view.inputmethod.EditorInfo;

import java.util.Objects;

/** Closed editor classification shared by the keyboard UI state and the composing session. */
public enum EditorMode {
    TEXT(true, false, false),
    NON_PREDICTIVE_TEXT(false, false, false),
    EMAIL(false, false, false),
    URL(false, false, false),
    PASSWORD(false, true, false),
    NUMBER(false, false, true),
    NUMBER_PASSWORD(false, true, true),
    PHONE(false, false, true),
    DATE_TIME(false, false, true),
    OTHER(false, false, false);

    private final boolean composingAllowed;
    private final boolean privateField;
    private final boolean numericPanel;

    EditorMode(boolean composingAllowed, boolean privateField, boolean numericPanel) {
        this.composingAllowed = composingAllowed;
        this.privateField = privateField;
        this.numericPanel = numericPanel;
    }

    /** Whether the reviewed composing pipeline may run for this editor. */
    public boolean composingAllowed() {
        return composingAllowed;
    }

    /** Whether the editor must never receive candidates or retain typed context. */
    public boolean privateField() {
        return privateField;
    }

    /** Whether the editor opens a digit-first panel instead of the alphabetic layers. */
    public boolean numericPanel() {
        return numericPanel;
    }

    public static EditorMode from(EditorInfo info) {
        Objects.requireNonNull(info, "info");
        int inputClass = info.inputType & InputType.TYPE_MASK_CLASS;
        int variation = info.inputType & InputType.TYPE_MASK_VARIATION;
        switch (inputClass) {
            case InputType.TYPE_CLASS_NUMBER:
                return variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD
                        ? NUMBER_PASSWORD
                        : NUMBER;
            case InputType.TYPE_CLASS_PHONE:
                return PHONE;
            case InputType.TYPE_CLASS_DATETIME:
                return DATE_TIME;
            case InputType.TYPE_CLASS_TEXT:
                return classifyText(info.inputType, variation);
            default:
                return OTHER;
        }
    }

    private static EditorMode classifyText(int inputType, int variation) {
        if (variation == InputType.TYPE_TEXT_VARIATION_PASSWORD
                || variation == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                || variation == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD) {
            return PASSWORD;
        }
        if (variation == InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
                || variation == InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS) {
            return EMAIL;
        }
        if (variation == InputType.TYPE_TEXT_VARIATION_URI) {
            return URL;
        }
        if ((inputType & InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS) != 0
                || (inputType & InputType.TYPE_TEXT_FLAG_AUTO_COMPLETE) != 0) {
            return NON_PREDICTIVE_TEXT;
        }
        return TEXT;
    }
}
