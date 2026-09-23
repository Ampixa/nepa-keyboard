package com.ampixa.nepakeyboard.ime;

import android.icu.text.BreakIterator;

import java.util.Locale;
import java.util.Objects;

/** Bounded previous-grapheme boundary used only by explicit backspace handling. */
final class GraphemeBackspace {
    static final int COMMITTED_CONTEXT_UTF16_LIMIT = 64;

    private static final int ZERO_WIDTH_JOINER = 0x200d;
    private static final int DEVANAGARI_VIRAMA = 0x094d;
    private static final int NEWA_VIRAMA = 0x11442;

    private GraphemeBackspace() {
    }

    /**
     * Returns the UTF-16 boundary before the final user-perceived character.
     *
     * <p>Android ICU supplies the extended-grapheme baseline. The small
     * coalescing pass keeps Devanagari virama conjuncts and older-ICU emoji
     * ZWJ/flag boundaries stable across the supported API range.</p>
     */
    static int previousBoundary(String text) {
        Objects.requireNonNull(text, "text");
        if (text.isEmpty()) {
            return BreakIterator.DONE;
        }
        int newaActionBoundary = previousNewaActionBoundary(text);
        if (newaActionBoundary >= 0) {
            return newaActionBoundary;
        }
        BreakIterator iterator = BreakIterator.getCharacterInstance(Locale.ROOT);
        iterator.setText(text);
        int boundary = iterator.preceding(text.length());
        if (boundary == BreakIterator.DONE) {
            return fallbackCodePointBoundary(text);
        }

        while (boundary > 0 && shouldCoalesce(text, boundary)) {
            int previous = iterator.preceding(boundary);
            boundary = previous == BreakIterator.DONE ? 0 : previous;
        }
        return boundary;
    }

    /**
     * A full-window result beginning inside the final grapheme is ambiguous.
     * The caller must fall back to a single-code-point delete in that case.
     */
    static boolean hasCompleteTrailingGrapheme(
            String text,
            int requestedUtf16Units,
            int knownTextBeforeCursorUtf16Units
    ) {
        Objects.requireNonNull(text, "text");
        if (text.isEmpty() || requestedUtf16Units <= 0) {
            return false;
        }
        if (knownTextBeforeCursorUtf16Units < 0) {
            return false;
        }
        int expectedWindow = Math.min(
                requestedUtf16Units,
                knownTextBeforeCursorUtf16Units
        );
        if (text.length() != expectedWindow) {
            return false;
        }
        int boundary = previousBoundary(text);
        return boundary != BreakIterator.DONE
                && !(knownTextBeforeCursorUtf16Units > requestedUtf16Units
                && boundary == 0);
    }

    private static boolean shouldCoalesce(String text, int boundary) {
        int next = text.codePointAt(boundary);
        int before = text.codePointBefore(boundary);
        if (before == '\r' && next == '\n') {
            return true;
        }
        if (next == 0x200c || next == ZERO_WIDTH_JOINER) {
            if (before == NEWA_VIRAMA) {
                return false;
            }
            return true;
        }
        if (isGraphemeExtension(next)) {
            return true;
        }
        if (isRegionalIndicator(before) && isRegionalIndicator(next)) {
            return regionalIndicatorCountBefore(text, boundary) % 2 == 1;
        }
        if (isDevanagariLetter(next)) {
            int cursor = boundary;
            int preceding = text.codePointBefore(cursor);
            if (preceding == 0x200c || preceding == ZERO_WIDTH_JOINER) {
                cursor -= Character.charCount(preceding);
                if (cursor == 0) {
                    return false;
                }
                preceding = text.codePointBefore(cursor);
            }
            return preceding == DEVANAGARI_VIRAMA
                    && hasDevanagariBaseBeforeVirama(text, cursor);
        }
        return false;
    }

    private static int previousNewaActionBoundary(String text) {
        int end = text.length();
        int trailing = text.codePointBefore(end);
        if (trailing == NEWA_VIRAMA) {
            int viramaStart = end - Character.charCount(trailing);
            return hasNewaBaseBeforeVirama(text, end) ? viramaStart : -1;
        }
        int continuationEnd = end;
        while (isNewaMark(trailing) && trailing != NEWA_VIRAMA) {
            continuationEnd -= Character.charCount(trailing);
            if (continuationEnd == 0) {
                return -1;
            }
            trailing = text.codePointBefore(continuationEnd);
        }
        if (!isNewaConjunctConsonant(trailing)) {
            return -1;
        }
        int continuationStart = continuationEnd - Character.charCount(trailing);
        if (continuationStart == 0) {
            return -1;
        }
        int preceding = text.codePointBefore(continuationStart);
        if (preceding == NEWA_VIRAMA) {
            return hasNewaBaseBeforeVirama(text, continuationStart)
                    ? continuationStart
                    : -1;
        }
        if (preceding != 0x200c && preceding != ZERO_WIDTH_JOINER) {
            return -1;
        }
        int joinerStart = continuationStart - Character.charCount(preceding);
        if (joinerStart == 0
                || text.codePointBefore(joinerStart) != NEWA_VIRAMA) {
            return -1;
        }
        // The bounded editor window may begin at the virama after a long mark
        // sequence. The exact virama+joiner+consonant suffix is sufficient to
        // delete the continuation and its marks without orphaning the joiner.
        // This is the grapheme-safe fallback when mark-tap ownership is gone.
        return joinerStart;
    }

    private static int regionalIndicatorCountBefore(String text, int boundary) {
        int count = 0;
        int cursor = boundary;
        while (cursor > 0) {
            int codePoint = text.codePointBefore(cursor);
            if (!isRegionalIndicator(codePoint)) {
                break;
            }
            count++;
            cursor -= Character.charCount(codePoint);
        }
        return count;
    }

    private static boolean isRegionalIndicator(int codePoint) {
        return codePoint >= 0x1f1e6 && codePoint <= 0x1f1ff;
    }

    private static boolean isGraphemeExtension(int codePoint) {
        int type = Character.getType(codePoint);
        return type == Character.NON_SPACING_MARK
                || type == Character.COMBINING_SPACING_MARK
                || type == Character.ENCLOSING_MARK
                || (codePoint >= 0xfe00 && codePoint <= 0xfe0f)
                || (codePoint >= 0xe0100 && codePoint <= 0xe01ef)
                || (codePoint >= 0x1f3fb && codePoint <= 0x1f3ff);
    }

    private static boolean isDevanagariLetter(int codePoint) {
        return ((codePoint >= 0x0900 && codePoint <= 0x097f)
                || (codePoint >= 0xa8e0 && codePoint <= 0xa8ff)
                || (codePoint >= 0x11b00 && codePoint <= 0x11b5f))
                && Character.isLetter(codePoint);
    }

    private static boolean hasDevanagariBaseBeforeVirama(String text, int cursor) {
        int viramaStart = cursor - Character.charCount(DEVANAGARI_VIRAMA);
        int scan = viramaStart;
        while (scan > 0) {
            int codePoint = text.codePointBefore(scan);
            if (isDevanagariLetter(codePoint)) {
                return true;
            }
            if (!isDevanagariMark(codePoint)) {
                return false;
            }
            scan -= Character.charCount(codePoint);
        }
        return false;
    }

    private static boolean isDevanagariMark(int codePoint) {
        if (!((codePoint >= 0x0900 && codePoint <= 0x097f)
                || (codePoint >= 0xa8e0 && codePoint <= 0xa8ff)
                || (codePoint >= 0x11b00 && codePoint <= 0x11b5f))) {
            return false;
        }
        int type = Character.getType(codePoint);
        return type == Character.NON_SPACING_MARK
                || type == Character.COMBINING_SPACING_MARK
                || type == Character.ENCLOSING_MARK;
    }

    private static boolean isNewaConjunctConsonant(int codePoint) {
        return codePoint >= 0x1140e && codePoint <= 0x11434;
    }

    private static boolean hasNewaBaseBeforeVirama(String text, int cursor) {
        int viramaStart = cursor - Character.charCount(NEWA_VIRAMA);
        int scan = viramaStart;
        while (scan > 0) {
            int codePoint = text.codePointBefore(scan);
            if (isNewaConjunctConsonant(codePoint)) {
                return true;
            }
            if (!isNewaMark(codePoint)) {
                return false;
            }
            scan -= Character.charCount(codePoint);
        }
        return false;
    }

    private static boolean isNewaMark(int codePoint) {
        if (codePoint < 0x11400 || codePoint > 0x1147f) {
            return false;
        }
        int type = Character.getType(codePoint);
        return type == Character.NON_SPACING_MARK
                || type == Character.COMBINING_SPACING_MARK
                || type == Character.ENCLOSING_MARK;
    }

    private static int fallbackCodePointBoundary(String text) {
        return text.offsetByCodePoints(text.length(), -1);
    }
}
