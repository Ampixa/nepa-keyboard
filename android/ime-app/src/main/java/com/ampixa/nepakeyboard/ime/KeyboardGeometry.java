package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/** Immutable, view-free geometry for one rendered keyboard generation. */
public final class KeyboardGeometry {
    public static final int COORDINATE_SCALE = 1_000_000;
    public static final int MAX_TEXT_KEYS = 64;

    private final String layoutId;
    private final int layoutRevision;
    private final String layoutSourceSha256;
    private final long renderGeneration;
    private final List<KeyBounds> textKeys;

    public KeyboardGeometry(
            String layoutId,
            int layoutRevision,
            String layoutSourceSha256,
            long renderGeneration,
            List<KeyBounds> textKeys
    ) {
        this.layoutId = require(layoutId, "layoutId");
        if (layoutRevision < 1) {
            throw new IllegalArgumentException("layoutRevision must be positive");
        }
        this.layoutRevision = layoutRevision;
        this.layoutSourceSha256 = requireSha256(layoutSourceSha256);
        if (renderGeneration < 1L) {
            throw new IllegalArgumentException("renderGeneration must be positive");
        }
        this.renderGeneration = renderGeneration;
        List<KeyBounds> copy = new ArrayList<>(Objects.requireNonNull(textKeys, "textKeys"));
        if (copy.isEmpty() || copy.size() > MAX_TEXT_KEYS) {
            throw new IllegalArgumentException("geometry must contain one to 64 text keys");
        }
        Set<String> keyIds = new HashSet<>();
        for (KeyBounds bounds : copy) {
            Objects.requireNonNull(bounds, "text key bounds");
            if (!keyIds.add(bounds.keyId())) {
                throw new IllegalArgumentException("geometry repeats text key ID");
            }
        }
        this.textKeys = Collections.unmodifiableList(copy);
    }

    public String layoutId() {
        return layoutId;
    }

    public int layoutRevision() {
        return layoutRevision;
    }

    public String layoutSourceSha256() {
        return layoutSourceSha256;
    }

    public long renderGeneration() {
        return renderGeneration;
    }

    public List<KeyBounds> textKeys() {
        return textKeys;
    }

    KeyBounds requireKey(String keyId, String emittedText) {
        for (KeyBounds bounds : textKeys) {
            if (bounds.keyId().equals(keyId) && bounds.emittedText().equals(emittedText)) {
                return bounds;
            }
        }
        throw new IllegalArgumentException("stroke key is absent from its geometry");
    }

    List<ScoredKey> nearestKeys(
            KeyBounds selected,
            int x,
            int y,
            int limit
    ) {
        requireCoordinate(x, "x");
        requireCoordinate(y, "y");
        if (limit < 1 || limit > 3) {
            throw new IllegalArgumentException("spatial alternatives must be bounded to 1..3");
        }
        List<ScoredKey> ranked = new ArrayList<>();
        for (KeyBounds bounds : textKeys) {
            if (bounds == selected || selected.isSpatiallyCompatible(bounds)) {
                ranked.add(new ScoredKey(bounds, bounds.normalizedSquaredDistance(x, y)));
            }
        }
        ranked.sort(Comparator
                .comparingInt(ScoredKey::cost)
                .thenComparing(value -> value.bounds().keyId()));
        List<ScoredKey> result = new ArrayList<>();
        ScoredKey selectedScore = null;
        for (ScoredKey value : ranked) {
            if (value.bounds() == selected) {
                selectedScore = value;
            }
            if (result.size() < limit) {
                result.add(value);
            }
        }
        if (selectedScore == null) {
            throw new IllegalStateException("selected key vanished from geometry");
        }
        if (!result.contains(selectedScore)) {
            result.set(result.size() - 1, selectedScore);
            result.sort(Comparator
                    .comparingInt(ScoredKey::cost)
                    .thenComparing(value -> value.bounds().keyId()));
        }
        return Collections.unmodifiableList(result);
    }

    static void requireCoordinate(int value, String label) {
        if (value < 0 || value > COORDINATE_SCALE) {
            throw new IllegalArgumentException(label + " is outside normalized keyboard bounds");
        }
    }

    private static String require(String value, String label) {
        Objects.requireNonNull(value, label);
        if (value.isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        return value;
    }

    private static String requireSha256(String value) {
        String checked = require(value, "layoutSourceSha256");
        if (!checked.matches("^[0-9a-f]{64}$")) {
            throw new IllegalArgumentException("layoutSourceSha256 must be lowercase SHA-256");
        }
        return checked;
    }

    /** Fixed-point bounds relative to the keyboard surface, independent of pixels. */
    public static final class KeyBounds {
        private final String keyId;
        private final String emittedText;
        private final KeySpec.InputPolicy inputPolicy;
        private final int left;
        private final int top;
        private final int right;
        private final int bottom;
        private final boolean wordKey;

        public KeyBounds(
                String keyId,
                String emittedText,
                KeySpec.InputPolicy inputPolicy,
                int left,
                int top,
                int right,
                int bottom
        ) {
            this.keyId = require(keyId, "keyId");
            this.emittedText = require(emittedText, "emittedText");
            this.inputPolicy = Objects.requireNonNull(inputPolicy, "inputPolicy");
            requireCoordinate(left, "left");
            requireCoordinate(top, "top");
            requireCoordinate(right, "right");
            requireCoordinate(bottom, "bottom");
            if (right <= left || bottom <= top) {
                throw new IllegalArgumentException("text key bounds must have positive area");
            }
            this.left = left;
            this.top = top;
            this.right = right;
            this.bottom = bottom;
            this.wordKey = isWordKey(emittedText, inputPolicy);
        }

        public String keyId() {
            return keyId;
        }

        public String emittedText() {
            return emittedText;
        }

        public KeySpec.InputPolicy inputPolicy() {
            return inputPolicy;
        }

        public int left() {
            return left;
        }

        public int top() {
            return top;
        }

        public int right() {
            return right;
        }

        public int bottom() {
            return bottom;
        }

        boolean isSpatiallyCompatible(KeyBounds other) {
            return wordKey
                    && other.wordKey
                    && inputPolicy == KeySpec.InputPolicy.DEFAULT
                    && other.inputPolicy == KeySpec.InputPolicy.DEFAULT;
        }

        int normalizedSquaredDistance(int x, int y) {
            long centerX = ((long) left + right) / 2L;
            long centerY = ((long) top + bottom) / 2L;
            long halfWidth = Math.max(1L, ((long) right - left) / 2L);
            long halfHeight = Math.max(1L, ((long) bottom - top) / 2L);
            long dx = ((x - centerX) * 1024L) / halfWidth;
            long dy = ((y - centerY) * 1024L) / halfHeight;
            long squared = dx * dx + dy * dy;
            return squared >= Integer.MAX_VALUE ? Integer.MAX_VALUE : (int) squared;
        }

        private static boolean isWordKey(String text, KeySpec.InputPolicy policy) {
            if (policy != KeySpec.InputPolicy.DEFAULT) {
                return false;
            }
            for (int offset = 0; offset < text.length(); ) {
                int codePoint = text.codePointAt(offset);
                int type = Character.getType(codePoint);
                if (!Character.isLetter(codePoint)
                        && type != Character.NON_SPACING_MARK
                        && type != Character.COMBINING_SPACING_MARK) {
                    return false;
                }
                offset += Character.charCount(codePoint);
            }
            return true;
        }
    }

    static final class ScoredKey {
        private final KeyBounds bounds;
        private final int cost;

        ScoredKey(KeyBounds bounds, int cost) {
            this.bounds = bounds;
            this.cost = cost;
        }

        KeyBounds bounds() {
            return bounds;
        }

        int cost() {
            return cost;
        }
    }
}
