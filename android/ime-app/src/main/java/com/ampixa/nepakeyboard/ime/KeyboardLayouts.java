package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Runtime view of the fail-closed generated declarative layout registry. */
public final class KeyboardLayouts {
    private static final Map<String, LayoutSet> LAYOUTS;

    static {
        Map<String, LayoutSet> layouts = new LinkedHashMap<>();
        for (LayoutSet layout : GeneratedLayoutRegistry.createLayouts()) {
            if (layouts.put(layout.id(), layout) != null) {
                throw new IllegalStateException("duplicate generated layout: " + layout.id());
            }
        }
        if (layouts.size() != GeneratedLayoutRegistry.LAYOUT_COUNT) {
            throw new IllegalStateException("generated layout registry count mismatch");
        }
        LAYOUTS = Collections.unmodifiableMap(layouts);
    }

    private KeyboardLayouts() {
    }

    /** The Latin surface used to type phonetically into a non-Latin script. */
    static final String TRANSLITERATION_LAYOUT_ID = "latn-qwerty-us-v1";

    /**
     * Renders the Roman input surface for phonetic typing.
     *
     * <p>The script check applied to a profile's own layout is intentionally not
     * applied here: in this mode the input surface is Latin by design while the
     * profile's output script stays whatever the profile declares.
     */
    public static Layout forTransliteration(KeyboardProfile profile, KeyboardUiState state) {
        Objects.requireNonNull(profile, "profile");
        Objects.requireNonNull(state, "state");
        if (!profile.isAvailable()) {
            throw new IllegalStateException("unavailable profile has no layout: " + profile.id());
        }
        LayoutSet layout = LAYOUTS.get(TRANSLITERATION_LAYOUT_ID);
        if (layout == null) {
            throw new IllegalStateException("the Roman input surface is not compiled in");
        }
        String layerId = state.layoutLayerId();
        return layout.render(layerId, TRANSLITERATION_LAYOUT_ID + ":" + layerId, profile);
    }

    public static Layout forProfile(KeyboardProfile profile, KeyboardUiState state) {
        Objects.requireNonNull(state, "state");
        String layerId = state.layoutLayerId();
        return render(profile, layerId, renderedId(profile, layerId));
    }

    public static Layout forProfile(
            KeyboardProfile profile,
            boolean shifted,
            boolean symbols,
            boolean numeric
    ) {
        String layerId;
        if (numeric) {
            layerId = "numeric";
        } else if (symbols) {
            layerId = "symbols";
        } else if (shifted) {
            layerId = "shift";
        } else {
            layerId = "base";
        }
        return render(profile, layerId, renderedId(profile, layerId));
    }

    private static String renderedId(KeyboardProfile profile, String layerId) {
        Objects.requireNonNull(profile, "profile");
        switch (layerId) {
            case "numeric":
            case "symbols":
                return layerId;
            case "shift":
                return profile.id() + ":shift";
            case "base":
                return profile.id();
            default:
                throw new IllegalStateException("unknown generated layer: " + layerId);
        }
    }

    private static Layout render(KeyboardProfile profile, String layerId, String renderedId) {
        Objects.requireNonNull(profile, "profile");
        // A reusable layout binding must never make a gated profile renderable.
        if (!profile.isAvailable()) {
            throw new IllegalStateException("unavailable profile has no production layout: " + profile.id());
        }
        LayoutSet layout = LAYOUTS.get(profile.layoutId());
        if (layout == null) {
            throw new IllegalStateException("available profile has no generated layout: " + profile.id());
        }
        if (!profile.sourceScript().equals(layout.inputScript())) {
            throw new IllegalStateException("profile and generated layout script mismatch: " + profile.id());
        }
        return layout.render(layerId, renderedId, profile);
    }

    static boolean hasLayoutForTesting(String layoutId) {
        return LAYOUTS.containsKey(layoutId);
    }

    static String inputScriptForTesting(String layoutId) {
        LayoutSet layout = LAYOUTS.get(layoutId);
        return layout == null ? null : layout.inputScript();
    }

    static final class LayoutSet {
        private final String id;
        private final String inputScript;
        private final Map<String, Layer> layers;

        LayoutSet(
                String id,
                String inputScript,
                Layer base,
                Layer shift,
                Layer symbols,
                Layer numeric
        ) {
            this.id = require(id, "layout id");
            this.inputScript = require(inputScript, "input script");
            Map<String, Layer> byId = new LinkedHashMap<>();
            for (Layer layer : new Layer[]{base, shift, symbols, numeric}) {
                Objects.requireNonNull(layer, "layer");
                if (byId.put(layer.id(), layer) != null) {
                    throw new IllegalArgumentException("duplicate generated layer: " + layer.id());
                }
            }
            if (byId.size() != 4
                    || !byId.containsKey("base")
                    || !byId.containsKey("shift")
                    || !byId.containsKey("symbols")
                    || !byId.containsKey("numeric")) {
                throw new IllegalArgumentException("generated layout has unsupported layer set");
            }
            layers = Collections.unmodifiableMap(byId);
        }

        String id() {
            return id;
        }

        String inputScript() {
            return inputScript;
        }

        Layout render(String layerId, String renderedId, KeyboardProfile profile) {
            Layer layer = layers.get(layerId);
            if (layer == null) {
                throw new IllegalStateException("generated layout has no layer: " + id + ":" + layerId);
            }
            return layer.bind(renderedId, id, profile);
        }
    }

    static final class Layer {
        private final String id;
        private final List<List<KeySpec>> rows;

        Layer(String id, List<List<KeySpec>> rows) {
            this.id = require(id, "layer id");
            Objects.requireNonNull(rows, "rows");
            List<List<KeySpec>> frozen = new ArrayList<>();
            for (List<KeySpec> row : rows) {
                if (row == null || row.isEmpty()) {
                    throw new IllegalArgumentException("generated layout row must not be empty");
                }
                frozen.add(Collections.unmodifiableList(new ArrayList<>(row)));
            }
            if (frozen.isEmpty()) {
                throw new IllegalArgumentException("generated layout layer must not be empty");
            }
            this.rows = Collections.unmodifiableList(frozen);
        }

        String id() {
            return id;
        }

        Layout bind(
                String renderedId,
                String sourceLayoutId,
                KeyboardProfile profile
        ) {
            List<List<KeySpec>> bound = new ArrayList<>();
            for (List<KeySpec> row : rows) {
                List<KeySpec> boundRow = new ArrayList<>();
                for (KeySpec key : row) {
                    boundRow.add(key.bindProfile(profile));
                }
                bound.add(boundRow);
            }
            return new Layout(
                    renderedId,
                    sourceLayoutId,
                    profile.layoutRevision(),
                    profile.layoutSourceSha256(),
                    bound
            );
        }
    }

    public static final class Layout {
        private final String id;
        private final String sourceLayoutId;
        private final int layoutRevision;
        private final String layoutSourceSha256;
        private final List<List<KeySpec>> rows;

        private Layout(
                String id,
                String sourceLayoutId,
                int layoutRevision,
                String layoutSourceSha256,
                List<List<KeySpec>> rows
        ) {
            this.id = require(id, "rendered layout id");
            this.sourceLayoutId = require(sourceLayoutId, "source layout id");
            this.layoutRevision = layoutRevision;
            this.layoutSourceSha256 = layoutSourceSha256;
            List<List<KeySpec>> frozen = new ArrayList<>();
            for (List<KeySpec> row : rows) {
                frozen.add(Collections.unmodifiableList(new ArrayList<>(row)));
            }
            this.rows = Collections.unmodifiableList(frozen);
        }

        public String id() {
            return id;
        }

        public String sourceLayoutId() {
            return sourceLayoutId;
        }

        public int layoutRevision() {
            return layoutRevision;
        }

        public String layoutSourceSha256() {
            return layoutSourceSha256;
        }

        public List<List<KeySpec>> rows() {
            return rows;
        }

        /**
         * Returns a copy with reviewed long-press variants attached. A variant set only
         * applies when the key is still a text key carrying the expected payload.
         */
        Layout withKeyAlternates(java.util.Map<String, List<String>> alternatesByKeyId) {
            List<List<KeySpec>> next = new ArrayList<>();
            boolean changed = false;
            for (List<KeySpec> row : rows) {
                List<KeySpec> nextRow = new ArrayList<>(row.size());
                for (KeySpec key : row) {
                    List<String> alternates = alternatesByKeyId.get(key.keyId());
                    if (alternates == null || key.action() != KeySpec.Action.TEXT) {
                        nextRow.add(key);
                        continue;
                    }
                    nextRow.add(key.withAlternates(alternates));
                    changed = true;
                }
                next.add(nextRow);
            }
            if (!changed) {
                return this;
            }
            return new Layout(id, sourceLayoutId, layoutRevision, layoutSourceSha256, next);
        }

        public boolean containsText(String text) {
            for (List<KeySpec> row : rows) {
                for (KeySpec key : row) {
                    if (text.equals(key.text())) {
                        return true;
                    }
                }
            }
            return false;
        }

        KeySpec keyForTesting(String keyId) {
            for (List<KeySpec> row : rows) {
                for (KeySpec key : row) {
                    if (keyId.equals(key.keyId())) {
                        return key;
                    }
                }
            }
            return null;
        }
    }

    private static String require(String value, String label) {
        Objects.requireNonNull(value, label);
        if (value.isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        return value;
    }
}
