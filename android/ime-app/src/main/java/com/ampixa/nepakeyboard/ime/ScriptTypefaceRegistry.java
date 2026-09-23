package com.ampixa.nepakeyboard.ime;

import android.content.Context;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.widget.TextView;

/** Selects bundled script fallbacks only when the displayed text requires one. */
final class ScriptTypefaceRegistry {
    private static final int NEWA_START = 0x11400;
    private static final int NEWA_END = 0x1147f;

    private final Typeface bundledNewa;

    ScriptTypefaceRegistry(Context context) {
        bundledNewa = context.getResources().getFont(R.font.noto_sans_newa_regular);
        if (bundledNewa == null) {
            throw new IllegalStateException("bundled Newa typeface is unavailable");
        }
    }

    void apply(TextView view, CharSequence text, Typeface fallback) {
        view.setTypeface(typefaceFor(text, fallback));
    }

    Typeface typefaceFor(CharSequence text, Typeface fallback) {
        return containsNewa(text) ? bundledNewa : fallback;
    }

    boolean usesBundledNewa(TextView view) {
        return view != null && view.getTypeface() == bundledNewa;
    }

    boolean bundledNewaCovers(CharSequence text) {
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setTypeface(bundledNewa);
        boolean checkedNewa = false;
        for (int offset = 0; text != null && offset < text.length(); ) {
            int codePoint = Character.codePointAt(text, offset);
            if (isNewa(codePoint)) {
                checkedNewa = true;
                if (!paint.hasGlyph(new String(Character.toChars(codePoint)))) {
                    return false;
                }
            }
            offset += Character.charCount(codePoint);
        }
        return checkedNewa;
    }

    static boolean containsNewa(CharSequence text) {
        for (int offset = 0; text != null && offset < text.length(); ) {
            int codePoint = Character.codePointAt(text, offset);
            if (isNewa(codePoint)) {
                return true;
            }
            offset += Character.charCount(codePoint);
        }
        return false;
    }

    private static boolean isNewa(int codePoint) {
        return codePoint >= NEWA_START && codePoint <= NEWA_END;
    }
}
