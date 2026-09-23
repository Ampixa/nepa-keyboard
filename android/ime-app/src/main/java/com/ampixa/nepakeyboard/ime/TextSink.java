package com.ampixa.nepakeyboard.ime;

/** Minimal editor boundary used by the composing state machine and test fakes. */
public interface TextSink {
    boolean setComposingText(String text);

    boolean commitText(String text);

    boolean finishComposingText();

    /** Deletes one user-perceived character when bounded editor context is available. */
    boolean deletePreviousGrapheme();

    /** Conservative fallback that never requires reading surrounding editor text. */
    boolean deleteOneCodePoint();
}
