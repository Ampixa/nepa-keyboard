package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/** Immutable text-key event with explicit spatial or non-spatial provenance. */
public final class SpatialKeyStroke {
    private final String layoutId;
    private final int layoutRevision;
    private final String layoutSourceSha256;
    private final long renderGeneration;
    private final String keyId;
    private final String emittedText;
    private final KeySpec.InputPolicy inputPolicy;
    private final KeyboardGeometry geometry;
    private final int x;
    private final int y;

    private SpatialKeyStroke(
            String layoutId,
            int layoutRevision,
            String layoutSourceSha256,
            long renderGeneration,
            String keyId,
            String emittedText,
            KeySpec.InputPolicy inputPolicy,
            KeyboardGeometry geometry,
            int x,
            int y
    ) {
        this.layoutId = require(layoutId, "layoutId");
        if (layoutRevision < 1) {
            throw new IllegalArgumentException("layoutRevision must be positive");
        }
        this.layoutRevision = layoutRevision;
        this.layoutSourceSha256 = require(layoutSourceSha256, "layoutSourceSha256");
        if (!layoutSourceSha256.matches("^[0-9a-f]{64}$")) {
            throw new IllegalArgumentException("layout source hash must be lowercase SHA-256");
        }
        if (renderGeneration < 1L) {
            throw new IllegalArgumentException("renderGeneration must be positive");
        }
        this.renderGeneration = renderGeneration;
        this.keyId = require(keyId, "keyId");
        this.emittedText = require(emittedText, "emittedText");
        this.inputPolicy = Objects.requireNonNull(inputPolicy, "inputPolicy");
        this.geometry = geometry;
        this.x = x;
        this.y = y;
        if (geometry != null) {
            if (!layoutId.equals(geometry.layoutId())
                    || layoutRevision != geometry.layoutRevision()
                    || !layoutSourceSha256.equals(geometry.layoutSourceSha256())
                    || renderGeneration != geometry.renderGeneration()) {
                throw new IllegalArgumentException("stroke and geometry identity mismatch");
            }
            KeyboardGeometry.KeyBounds selected = geometry.requireKey(keyId, emittedText);
            if (inputPolicy != selected.inputPolicy()) {
                throw new IllegalArgumentException("stroke and geometry input policy mismatch");
            }
            KeyboardGeometry.requireCoordinate(x, "x");
            KeyboardGeometry.requireCoordinate(y, "y");
        } else if (x != -1 || y != -1) {
            throw new IllegalArgumentException("non-spatial stroke cannot carry coordinates");
        }
    }

    public static SpatialKeyStroke spatial(
            KeyboardGeometry geometry,
            String keyId,
            String emittedText,
            KeySpec.InputPolicy inputPolicy,
            int x,
            int y
    ) {
        Objects.requireNonNull(geometry, "geometry");
        return new SpatialKeyStroke(
                geometry.layoutId(),
                geometry.layoutRevision(),
                geometry.layoutSourceSha256(),
                geometry.renderGeneration(),
                keyId,
                emittedText,
                inputPolicy,
                geometry,
                x,
                y
        );
    }

    public static SpatialKeyStroke nonSpatial(
            String layoutId,
            int layoutRevision,
            String layoutSourceSha256,
            long renderGeneration,
            String keyId,
            String emittedText,
            KeySpec.InputPolicy inputPolicy
    ) {
        return new SpatialKeyStroke(
                layoutId,
                layoutRevision,
                layoutSourceSha256,
                renderGeneration,
                keyId,
                emittedText,
                inputPolicy,
                null,
                -1,
                -1
        );
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

    public String keyId() {
        return keyId;
    }

    public String emittedText() {
        return emittedText;
    }

    public KeySpec.InputPolicy inputPolicy() {
        return inputPolicy;
    }

    public boolean hasSpatialEvidence() {
        return geometry != null;
    }

    Set<String> geometryKeyIdsForTesting() {
        if (geometry == null) {
            return Collections.emptySet();
        }
        Set<String> keyIds = new LinkedHashSet<>();
        for (KeyboardGeometry.KeyBounds bounds : geometry.textKeys()) {
            keyIds.add(bounds.keyId());
        }
        return Collections.unmodifiableSet(keyIds);
    }

    List<Alternative> alternatives(int limit) {
        if (geometry == null) {
            return Collections.singletonList(new Alternative(emittedText, 0, true));
        }
        KeyboardGeometry.KeyBounds selected = geometry.requireKey(keyId, emittedText);
        List<Alternative> result = new ArrayList<>();
        for (KeyboardGeometry.ScoredKey value : geometry.nearestKeys(selected, x, y, limit)) {
            result.add(new Alternative(
                    value.bounds().emittedText(),
                    value.cost(),
                    value.bounds() == selected
            ));
        }
        return Collections.unmodifiableList(result);
    }

    boolean matchesProfile(KeyboardProfile profile) {
        return profile != null
                && layoutId.equals(profile.layoutId())
                && layoutRevision == profile.layoutRevision()
                && layoutSourceSha256.equals(profile.layoutSourceSha256());
    }

    private static String require(String value, String label) {
        Objects.requireNonNull(value, label);
        if (value.isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        return value;
    }

    static final class Alternative {
        private final String text;
        private final int spatialCost;
        private final boolean exactKey;

        Alternative(String text, int spatialCost, boolean exactKey) {
            this.text = text;
            this.spatialCost = spatialCost;
            this.exactKey = exactKey;
        }

        String text() {
            return text;
        }

        int spatialCost() {
            return spatialCost;
        }

        boolean exactKey() {
            return exactKey;
        }
    }
}
