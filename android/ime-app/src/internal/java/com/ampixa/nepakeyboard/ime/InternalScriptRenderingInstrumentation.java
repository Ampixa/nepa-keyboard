package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Build;
import android.os.Bundle;
import android.view.View;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.Locale;

/** Focused old-Android rendering proof for scripts that need app-bundled fonts. */
public final class InternalScriptRenderingInstrumentation extends Instrumentation {
    private static final String EXPECTED_PACKAGE =
            "com.ampixa.nepakeyboard.ime.internal";
    private static final String NEWA_PROFILE_ID = "new-Newa-NP";
    private static final String NEWA_SAMPLE = "𑐣𑐾𑐥𑐵𑐮𑐮𑐶𑐥𑐶";
    private static final String EXPECTED_FONT_SHA256 =
            "dc8aea050ac05dea01c6a81e6a70d4a7"
                    + "506998a11c6e1ecaaa854b7ff18f9fc6";

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        int resultCode = Activity.RESULT_CANCELED;
        try {
            Context context = getTargetContext();
            assertEquals("internal application ID", EXPECTED_PACKAGE, context.getPackageName());
            assertTrue("supported product API", Build.VERSION.SDK_INT >= 26);
            assertEquals(
                    "bundled Newa font bytes",
                    EXPECTED_FONT_SHA256,
                    resourceSha256(context, R.font.noto_sans_newa_regular)
            );

            KeyboardProfile newa = LanguageRegistry.find(NEWA_PROFILE_ID);
            assertTrue("Newa profile is selectable", newa != null && newa.isAvailable());
            final RenderEvidence[] evidence = new RenderEvidence[1];
            runOnMainSync(() -> evidence[0] = renderAndVerify(context, newa));

            result.putString("status", "ok");
            result.putInt("api_level", Build.VERSION.SDK_INT);
            result.putString("profile_id", NEWA_PROFILE_ID);
            result.putString("newa_font_sha256", EXPECTED_FONT_SHA256);
            result.putBoolean("newa_base_keys_bundled_font_verified", true);
            result.putBoolean("newa_shift_keys_bundled_font_verified", true);
            result.putBoolean("newa_symbol_keys_bundled_font_verified", true);
            result.putBoolean("newa_candidate_bundled_font_verified", true);
            result.putBoolean("newa_sample_glyph_coverage_verified", true);
            result.putBoolean("newa_pixel_width_geometry_verified", true);
            result.putString("render_file", evidence[0].fileName);
            result.putInt("render_width", evidence[0].width);
            result.putInt("render_height", evidence[0].height);
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            result.putString("status", "error");
            result.putString("error", failure.toString());
        }
        finish(resultCode, result);
    }

    private RenderEvidence renderAndVerify(Context context, KeyboardProfile newa) {
        NepaInputView view = new NepaInputView(context, new NoOpListener());
        view.setProfile(newa);
        layoutForPixelWidth(view);
        assertTrue("Newa base geometry", view.visualGeometryContractForTesting());
        assertTrue(
                "all visible Newa base keys use bundled font",
                view.allVisibleNewaKeysUseBundledTypefaceForTesting()
        );
        assertTrue(
                "representative Newa key uses bundled font",
                view.textKeyUsesBundledNewaTypefaceForTesting("𑐣")
        );

        view.setShifted(true);
        layoutForPixelWidth(view);
        assertTrue("Newa shift geometry", view.visualGeometryContractForTesting());
        assertTrue(
                "all visible Newa shift keys use bundled font",
                view.allVisibleNewaKeysUseBundledTypefaceForTesting()
        );

        view.showSymbols();
        layoutForPixelWidth(view);
        assertTrue("Newa symbols geometry", view.visualGeometryContractForTesting());
        assertTrue(
                "all visible Newa symbol keys use bundled font",
                view.allVisibleNewaKeysUseBundledTypefaceForTesting()
        );

        view.setNumeric(false);
        view.setShifted(false);
        view.showLetters();
        view.setSuggestionSnapshot(SuggestionSnapshot.ready(
                new SuggestionActivation(1L, newa.id()),
                Collections.singletonList(NEWA_SAMPLE)
        ));
        layoutForPixelWidth(view);
        assertTrue(
                "Newa candidate uses bundled font",
                view.candidateUsesBundledNewaTypefaceForTesting(NEWA_SAMPLE)
        );
        assertTrue(
                "bundled font covers the attested Newa sample",
                view.bundledNewaTypefaceCoversForTesting(NEWA_SAMPLE)
        );
        assertTrue("restored Newa geometry", view.visualGeometryContractForTesting());

        String fileName = String.format(
                Locale.ROOT,
                "ime-script-rendering-newa-api%d.png",
                Build.VERSION.SDK_INT
        );
        return writeRender(context, view, fileName);
    }

    private static void layoutForPixelWidth(View view) {
        view.measure(
                View.MeasureSpec.makeMeasureSpec(1080, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(1200, View.MeasureSpec.AT_MOST)
        );
        view.layout(0, 0, 1080, view.getMeasuredHeight());
    }

    private static RenderEvidence writeRender(Context context, View view, String fileName) {
        int width = view.getWidth();
        int height = view.getHeight();
        assertTrue("render dimensions are bounded", width == 1080 && height > 0 && height <= 1200);
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        try {
            view.draw(new Canvas(bitmap));
            File output = new File(context.getFilesDir(), fileName);
            try (FileOutputStream stream = new FileOutputStream(output, false)) {
                if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                    throw new IllegalStateException("PNG encoder rejected " + fileName);
                }
            } catch (IOException failure) {
                throw new IllegalStateException("could not write " + fileName, failure);
            }
            assertTrue("render PNG is non-empty", output.isFile() && output.length() > 1024L);
            return new RenderEvidence(fileName, width, height);
        } finally {
            bitmap.recycle();
        }
    }

    private static String resourceSha256(Context context, int resourceId) {
        try (InputStream input = context.getResources().openRawResource(resourceId)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) >= 0) {
                digest.update(buffer, 0, read);
            }
            StringBuilder value = new StringBuilder(64);
            for (byte item : digest.digest()) {
                value.append(String.format(Locale.ROOT, "%02x", item & 0xff));
            }
            return value.toString();
        } catch (Exception failure) {
            throw new IllegalStateException("could not hash bundled Newa font", failure);
        }
    }

    private static void assertTrue(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void assertEquals(String label, Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected + " actual=" + actual);
        }
    }

    private static final class RenderEvidence {
        final String fileName;
        final int width;
        final int height;

        RenderEvidence(String fileName, int width, int height) {
            this.fileName = fileName;
            this.width = width;
            this.height = height;
        }
    }

    private static final class NoOpListener implements NepaInputView.Listener {
        @Override
        public void onKey(KeySpec key, SpatialKeyStroke stroke) {
        }

        @Override
        public void onProfileSelected(String profileId) {
        }

        @Override
        public void onCandidateSelected(
                SuggestionQuery owner,
                SuggestionCandidate candidate
        ) {
        }

        @Override
        public void onSuggestionRetry() {
        }

        @Override
        public void onManageLanguages() {
        }

        @Override
        public void onOtherKeyboards() {
        }
    }
}
