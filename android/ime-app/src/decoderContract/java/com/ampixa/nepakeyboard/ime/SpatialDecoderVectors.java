package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.view.View;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

/** Shared MotionEvent-derived English and Nepali vectors for spatial acceptance and timing. */
final class SpatialDecoderVectors {
    private static final List<Tap> ENGLISH_TAPS = Collections.unmodifiableList(Arrays.asList(
            new Tap("h", "base.r1.k5", 0.5f),
            new Tap("e", "base.r0.k2", 0.5f),
            new Tap("l", "base.r1.k8", 0.5f),
            new Tap("j-boundary", "j", "base.r1.k6", 0.5f, -0.15f, "h"),
            new Tap("a", "base.r1.k0", 0.5f),
            new Tap("b", "base.r2.k4", 0.5f),
            new Tap("c", "base.r2.k2", 0.5f),
            new Tap("f", "base.r1.k3", 0.5f),
            new Tap("g", "base.r1.k4", 0.5f),
            new Tap("i", "base.r0.k7", 0.5f),
            new Tap("k", "base.r1.k7", 0.5f),
            new Tap("m", "base.r2.k6", 0.5f),
            new Tap("n", "base.r2.k5", 0.5f),
            new Tap("o", "base.r0.k8", 0.5f),
            new Tap("r", "base.r0.k3", 0.5f),
            new Tap("u", "base.r0.k6", 0.5f),
            new Tap("v", "base.r2.k3", 0.5f),
            new Tap("y", "base.r0.k5", 0.5f)
    ));
    private static final List<Tap> NEPALI_TAPS = Collections.unmodifiableList(Arrays.asList(
            new Tap("न", "base.r2.k5", 0.5f),
            new Tap("े", "base.r0.k2", 0.5f),
            new Tap("प", "base.r0.k9", 0.5f),
            new Tap("ा", "base.r1.k0", 0.5f),
            new Tap("म-boundary", "म", "base.r2.k6", 0.5f, -0.15f, "न"),
            new Tap("म", "base.r2.k6", 0.5f),
            new Tap("स", "base.r1.k1", 0.5f),
            new Tap("्", "base.r2.k9", 0.5f),
            new Tap("र", "base.r0.k3", 0.5f),
            new Tap("व", "base.r2.k3", 0.5f)
    ));

    private SpatialDecoderVectors() {
    }

    static ProfileVectors captureEnglish(
            Instrumentation instrumentation,
            Context context,
            KeyboardProfile profile
    ) {
        return capture(
                instrumentation,
                context,
                profile,
                ENGLISH_TAPS,
                Arrays.asList(
                        "h", "he", "hel", "hell", "becau",
                        "governm", "informa", "keybo", "langu"
                ),
                "hell",
                "hello",
                Arrays.asList("h", "e", "l", "l"),
                "jell",
                Arrays.asList("j-boundary", "e", "l", "l")
        );
    }

    static ProfileVectors captureNepali(
            Instrumentation instrumentation,
            Context context,
            KeyboardProfile profile
    ) {
        return capture(
                instrumentation,
                context,
                profile,
                NEPALI_TAPS,
                Arrays.asList("न", "ने", "नेपा", "नमस्", "राम्", "स्वास्"),
                "नमस्",
                "नमस्कार",
                Arrays.asList("न", "म", "स", "्"),
                "ममस्",
                Arrays.asList("म-boundary", "म", "स", "्")
        );
    }

    private static ProfileVectors capture(
            Instrumentation instrumentation,
            Context context,
            KeyboardProfile profile,
            List<Tap> taps,
            List<String> centerPrefixes,
            String cleanPrefix,
            String expectedSurface,
            List<String> cleanVectorIds,
            String boundaryRaw,
            List<String> boundaryVectorIds
    ) {
        if (instrumentation == null || context == null || profile == null) {
            throw new IllegalArgumentException("instrumentation, context, and profile are required");
        }
        if (!profile.hasVersionedLayout()) {
            throw new AssertionError("spatial vector profile has no versioned layout: " + profile.id());
        }
        KeyboardLayouts.Layout boundLayout = KeyboardLayouts.forProfile(
                profile,
                false,
                false,
                false
        );
        Set<String> expectedTextKeyIds = new HashSet<>();
        for (List<KeySpec> row : boundLayout.rows()) {
            for (KeySpec key : row) {
                if (key.action() == KeySpec.Action.TEXT
                        && !expectedTextKeyIds.add(key.keyId())) {
                    throw new AssertionError("compiled layout repeats text key: " + key.keyId());
                }
            }
        }
        if (expectedTextKeyIds.isEmpty()) {
            throw new AssertionError("compiled layout has no text keys: " + profile.id());
        }
        Intent hostIntent = new Intent(context, SettingsActivity.class);
        hostIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity host = instrumentation.startActivitySync(hostIntent);
        AtomicReference<SpatialKeyStroke> observed = new AtomicReference<>();
        AtomicReference<KeyboardSurface> surfaceReference = new AtomicReference<>();
        Map<String, SpatialKeyStroke> captured = new HashMap<>();
        try {
            instrumentation.runOnMainSync(() -> {
                KeyboardSurface surface = new KeyboardSurface(host);
                surface.setListener(new KeyboardSurface.Listener() {
                    @Override
                    public void onKey(KeySpec key, SpatialKeyStroke stroke) {
                        if (key.action() == KeySpec.Action.TEXT) {
                            observed.set(stroke);
                        }
                    }

                    @Override
                    public void onLanguagePickerRequested(View source) {
                    }
                });
                surface.render(boundLayout);
                host.setContentView(surface);
                surfaceReference.set(surface);
            });
            instrumentation.waitForIdleSync();
            for (Tap tap : taps) {
                observed.set(null);
                instrumentation.runOnMainSync(() -> {
                    if (!surfaceReference.get().performTextKeyDriftForTesting(
                            tap.text,
                            tap.downHorizontalFraction,
                            tap.upHorizontalFraction,
                            0.5f
                    )) {
                        throw new AssertionError(
                                "compiled-layout MotionEvent dispatch failed: " + tap.vectorId
                        );
                    }
                });
                instrumentation.waitForIdleSync();
                SpatialKeyStroke stroke = observed.get();
                if (stroke == null || !stroke.hasSpatialEvidence()) {
                    throw new AssertionError("compiled-layout spatial stroke missing: " + tap.vectorId);
                }
                if (!tap.keyId.equals(stroke.keyId())) {
                    throw new AssertionError(
                            "compiled physical key mismatch for " + tap.vectorId
                                    + ": expected " + tap.keyId + ", got " + stroke.keyId()
                    );
                }
                SpatialKeyStroke.Alternative selected = stroke.alternatives(1).get(0);
                if (!selected.exactKey()) {
                    throw new AssertionError(
                            "compiled selected key is not the exact alternative: " + tap.vectorId
                    );
                }
                if (tap.downHorizontalFraction == 0.5f
                        && tap.upHorizontalFraction == 0.5f
                        && selected.spatialCost() != 0) {
                    throw new AssertionError(
                            "compiled center tap has nonzero spatial cost: " + tap.vectorId
                                    + " cost=" + selected.spatialCost()
                    );
                }
                if (tap.downHorizontalFraction != tap.upHorizontalFraction
                        && selected.spatialCost() <= 0) {
                    throw new AssertionError(
                            "compiled boundary tap has no spatial displacement: " + tap.vectorId
                    );
                }
                if (tap.expectedCloserAlternative != null) {
                    int selectedCost = Integer.MAX_VALUE;
                    int closerCost = Integer.MAX_VALUE;
                    for (SpatialKeyStroke.Alternative alternative : stroke.alternatives(3)) {
                        if (alternative.exactKey()) {
                            selectedCost = alternative.spatialCost();
                        }
                        if (tap.expectedCloserAlternative.equals(alternative.text())) {
                            closerCost = alternative.spatialCost();
                        }
                    }
                    if (closerCost >= selectedCost) {
                        throw new AssertionError(
                                "compiled drift target is not strictly closer: " + tap.vectorId
                                        + " target=" + closerCost
                                        + " selected=" + selectedCost
                        );
                    }
                }
                if (!expectedTextKeyIds.equals(stroke.geometryKeyIdsForTesting())) {
                    throw new AssertionError(
                            "compiled full-layout geometry key set mismatch: " + tap.vectorId
                    );
                }
                if (captured.put(tap.vectorId, stroke) != null) {
                    throw new AssertionError("duplicate spatial tap vector: " + tap.vectorId);
                }
            }
        } finally {
            instrumentation.runOnMainSync(host::finish);
            instrumentation.waitForIdleSync();
        }
        if (captured.size() != taps.size()) {
            throw new AssertionError("spatial vector capture count mismatch");
        }
        Map<String, SpatialKeyStroke> frozen = Collections.unmodifiableMap(captured);
        return new ProfileVectors(
                frozen,
                Collections.unmodifiableList(new ArrayList<>(centerPrefixes)),
                cleanPrefix,
                expectedSurface,
                sequence(profile, cleanPrefix, cleanVectorIds, frozen),
                boundaryRaw,
                sequence(profile, boundaryRaw, boundaryVectorIds, frozen)
        );
    }

    private static TouchSequence sequence(
            KeyboardProfile profile,
            String text,
            List<String> vectorIds,
            Map<String, SpatialKeyStroke> strokes
    ) {
        List<SpatialKeyStroke> ordered = new ArrayList<>();
        for (String vectorId : vectorIds) {
            SpatialKeyStroke stroke = strokes.get(vectorId);
            if (stroke == null) {
                throw new AssertionError("spatial sequence vector is missing: " + vectorId);
            }
            ordered.add(stroke);
        }
        return TouchSequence.forToken(profile, text, ordered);
    }

    static final class ProfileVectors {
        private final Map<String, SpatialKeyStroke> strokes;
        private final List<String> centerPrefixes;
        private final String cleanPrefix;
        private final String expectedSurface;
        private final TouchSequence cleanTouchSequence;
        private final String boundaryRaw;
        private final TouchSequence boundaryTouchSequence;

        ProfileVectors(
                Map<String, SpatialKeyStroke> strokes,
                List<String> centerPrefixes,
                String cleanPrefix,
                String expectedSurface,
                TouchSequence cleanTouchSequence,
                String boundaryRaw,
                TouchSequence boundaryTouchSequence
        ) {
            this.strokes = strokes;
            this.centerPrefixes = centerPrefixes;
            this.cleanPrefix = cleanPrefix;
            this.expectedSurface = expectedSurface;
            this.cleanTouchSequence = cleanTouchSequence;
            this.boundaryRaw = boundaryRaw;
            this.boundaryTouchSequence = boundaryTouchSequence;
        }

        Map<String, SpatialKeyStroke> strokes() {
            return strokes;
        }

        List<String> centerPrefixes() {
            return centerPrefixes;
        }

        String cleanPrefix() {
            return cleanPrefix;
        }

        String expectedSurface() {
            return expectedSurface;
        }

        TouchSequence cleanTouchSequence() {
            return cleanTouchSequence;
        }

        String boundaryRaw() {
            return boundaryRaw;
        }

        TouchSequence boundaryTouchSequence() {
            return boundaryTouchSequence;
        }
    }

    private static final class Tap {
        final String vectorId;
        final String text;
        final String keyId;
        final float downHorizontalFraction;
        final float upHorizontalFraction;
        final String expectedCloserAlternative;

        Tap(String text, String keyId, float horizontalFraction) {
            this(text, text, keyId, horizontalFraction);
        }

        Tap(String vectorId, String text, String keyId, float horizontalFraction) {
            this(vectorId, text, keyId, horizontalFraction, horizontalFraction, null);
        }

        Tap(
                String vectorId,
                String text,
                String keyId,
                float downHorizontalFraction,
                float upHorizontalFraction,
                String expectedCloserAlternative
        ) {
            this.vectorId = vectorId;
            this.text = text;
            this.keyId = keyId;
            this.downHorizontalFraction = downHorizontalFraction;
            this.upHorizontalFraction = upHorizontalFraction;
            this.expectedCloserAlternative = expectedCloserAlternative;
        }
    }
}
