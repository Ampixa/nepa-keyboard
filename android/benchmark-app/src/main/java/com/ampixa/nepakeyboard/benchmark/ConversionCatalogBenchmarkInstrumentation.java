package com.ampixa.nepakeyboard.benchmark;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import android.os.Debug;
import android.os.SystemClock;
import android.util.Log;

import com.ampixa.nepakeyboard.conversion.NcmBundle;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/** Correctness-first benchmark for the separately staged NCM catalog. */
public final class ConversionCatalogBenchmarkInstrumentation extends Instrumentation {
    private static final String TAG = "NepaConversionBenchmark";
    private static final String MANIFEST_ASSET = "nepa-conversions/manifest.json";
    private static final String VECTOR_ASSET = "nepa-conversions/benchmark-vectors.json";
    private static final int MAX_METADATA_BYTES = 128 * 1024;
    private static final int MAX_MAP_BYTES = 256 * 1024;
    private Bundle arguments = Bundle.EMPTY;

    @Override
    public void onCreate(Bundle supplied) {
        arguments = supplied == null ? Bundle.EMPTY : new Bundle(supplied);
        super.onCreate(supplied);
        start();
    }

    @Override
    public void onStart() {
        Bundle output = new Bundle();
        int result = Activity.RESULT_CANCELED;
        try {
            int iterations = boundedInteger(arguments.getString("iterations"), 10_000, 100, 200_000);
            int warmups = boundedInteger(arguments.getString("warmups"), 1_000, 10, 20_000);
            Context context = getTargetContext();
            VectorCase[] cases = readCases(context);
            validateManifest(context, cases);
            output.putString("status", "ok");
            output.putString("benchmark_mode", "conversion_catalog_v1");
            output.putInt("conversion_profile_count", cases.length);
            output.putInt("iterations_per_profile", iterations);
            output.putInt("warmups_per_profile", warmups);
            for (VectorCase vectorCase : cases) {
                benchmark(context, vectorCase, iterations, warmups, output);
                System.gc();
                SystemClock.sleep(100L);
            }
            output.putLong("process_pss_kb_after_benchmarks", Debug.getPss());
            File report = new File(context.getFilesDir(), "conversion-catalog-benchmark.json");
            JSONObject json = new JSONObject();
            for (String key : output.keySet()) {
                json.put(key, output.get(key));
            }
            try (FileWriter writer = new FileWriter(report, false)) {
                writer.write(json.toString(2));
                writer.write('\n');
            }
            output.putString("report_path", report.getAbsolutePath());
            result = Activity.RESULT_OK;
        } catch (Throwable failure) {
            Log.e(TAG, "conversion catalog benchmark failed", failure);
            output.putString("status", "error");
            output.putString("error", failure.toString());
        }
        finish(result, output);
    }

    private static void benchmark(
            Context context,
            VectorCase vectorCase,
            int iterations,
            int warmups,
            Bundle output
    ) throws Exception {
        long copyStart = SystemClock.elapsedRealtimeNanos();
        File file = copyAsset(context, vectorCase);
        long copyNanos = SystemClock.elapsedRealtimeNanos() - copyStart;
        long loadStart = SystemClock.elapsedRealtimeNanos();
        try (NcmBundle bundle = NcmBundle.open(file, vectorCase.sha256)) {
            long loadNanos = SystemClock.elapsedRealtimeNanos() - loadStart;
            assertEquals("converter ID", vectorCase.converterId, bundle.converterId());
            assertEquals("language", vectorCase.language, bundle.language());
            assertEquals("source script", vectorCase.sourceScript, bundle.sourceScript());
            assertEquals("output script", vectorCase.outputScript, bundle.outputScript());
            if (bundle.ruleCount() != vectorCase.ruleCount) {
                throw new AssertionError("conversion rule count mismatch");
            }
            for (ConversionVector vector : vectorCase.vectors) {
                String actual = bundle.convert(vector.input);
                if (vector.expectedOutput == null ? actual != null
                        : !vector.expectedOutput.equals(actual)) {
                    throw new AssertionError(
                            "conversion vector mismatch for " + vectorCase.profileId
                    );
                }
            }
            long checksum = 1L;
            for (int index = 0; index < warmups; index++) {
                ConversionVector vector = vectorCase.vectors[index % vectorCase.vectors.length];
                String converted = bundle.convert(vector.input);
                checksum = checksum * 31L + (converted == null ? 0 : converted.length());
            }
            long[] durations = new long[iterations];
            for (int index = 0; index < iterations; index++) {
                ConversionVector vector = vectorCase.vectors[index % vectorCase.vectors.length];
                long start = System.nanoTime();
                String converted = bundle.convert(vector.input);
                durations[index] = System.nanoTime() - start;
                checksum = checksum * 31L + (converted == null ? 0 : converted.hashCode());
            }
            Arrays.sort(durations);
            long sum = 0L;
            for (long duration : durations) {
                sum += duration;
            }
            String prefix = vectorCase.profileId.replace('-', '_');
            output.putString(prefix + "_converter_id", bundle.converterId());
            output.putString(prefix + "_artifact_sha256", bundle.artifactSha256());
            output.putInt(prefix + "_rule_count", bundle.ruleCount());
            output.putInt(prefix + "_verified_vector_count", vectorCase.vectors.length);
            output.putLong(prefix + "_asset_copy_and_sha_ns", copyNanos);
            output.putLong(prefix + "_verified_load_ns", loadNanos);
            output.putLong(prefix + "_mean_ns", sum / durations.length);
            output.putLong(prefix + "_p50_ns", percentile(durations, 50));
            output.putLong(prefix + "_p95_ns", percentile(durations, 95));
            output.putLong(prefix + "_p99_ns", percentile(durations, 99));
            output.putLong(prefix + "_max_ns", durations[durations.length - 1]);
            output.putLong(prefix + "_checksum", checksum);
            output.putLong(prefix + "_process_pss_kb", Debug.getPss());
        }
    }

    private static VectorCase[] readCases(Context context) throws Exception {
        JSONObject root = new JSONObject(new String(
                readBoundedAsset(context, VECTOR_ASSET),
                StandardCharsets.UTF_8
        ));
        if (root.length() != 1 || !root.has("bindings")) {
            throw new IllegalStateException("conversion vector root is invalid");
        }
        JSONArray rows = root.getJSONArray("bindings");
        if (rows.length() < 1 || rows.length() > 64) {
            throw new IllegalStateException("conversion vector count is invalid");
        }
        VectorCase[] result = new VectorCase[rows.length()];
        Set<String> profiles = new HashSet<>();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.getJSONObject(index);
            if (row.length() != 10) {
                throw new IllegalStateException("conversion vector row has unexpected fields");
            }
            String profileId = row.getString("profile_id");
            String converterId = row.getString("converter_id");
            String assetPath = row.getString("asset_path");
            String sha256 = row.getString("artifact_sha256");
            String releaseMode = row.getString("release_mode");
            String language = row.getString("language");
            String sourceScript = row.getString("source_script");
            String outputScript = row.getString("output_script");
            int ruleCount = row.getInt("rule_count");
            JSONArray vectors = row.getJSONArray("vectors");
            if (!profiles.add(profileId)
                    || !profileId.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
                    || !converterId.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
                    || !assetPath.matches("nepa-conversions/[A-Za-z0-9._-]+\\.ncm")
                    || !sha256.matches("[0-9a-f]{64}")
                    || !language.matches("[a-z]{3}")
                    || !"Deva".equals(sourceScript)
                    || !"Newa".equals(outputScript)
                    || !("release".equals(releaseMode) || "internal".equals(releaseMode))
                    || ruleCount < 1
                    || ruleCount > 1024
                    || vectors.length() < 2
                    || vectors.length() > 64) {
                throw new IllegalStateException("conversion vector identity is invalid");
            }
            ConversionVector[] parsedVectors = new ConversionVector[vectors.length()];
            boolean positive = false;
            boolean negative = false;
            for (int vectorIndex = 0; vectorIndex < vectors.length(); vectorIndex++) {
                JSONObject vector = vectors.getJSONObject(vectorIndex);
                if (vector.length() != 3
                        || !vector.has("input")
                        || !vector.has("expected_status")
                        || !vector.has("expected_output")) {
                    throw new IllegalStateException("conversion test vector shape is invalid");
                }
                String input = vector.getString("input");
                String expectedStatus = vector.getString("expected_status");
                String expected = vector.isNull("expected_output")
                        ? null
                        : vector.getString("expected_output");
                if (input.isEmpty()
                        || ("MATCH".equals(expectedStatus)
                        && (expected == null || expected.isEmpty()))
                        || ("NO_MATCH".equals(expectedStatus) && expected != null)
                        || !("MATCH".equals(expectedStatus)
                        || "NO_MATCH".equals(expectedStatus))) {
                    throw new IllegalStateException("conversion test vector is empty");
                }
                positive |= "MATCH".equals(expectedStatus);
                negative |= "NO_MATCH".equals(expectedStatus);
                parsedVectors[vectorIndex] = new ConversionVector(
                        input,
                        expectedStatus,
                        expected
                );
            }
            if (!positive || !negative) {
                throw new IllegalStateException("conversion vectors need success and no-match cases");
            }
            result[index] = new VectorCase(
                    profileId,
                    converterId,
                    assetPath,
                    sha256,
                    language,
                    sourceScript,
                    outputScript,
                    releaseMode,
                    ruleCount,
                    parsedVectors
            );
        }
        return result;
    }

    private static void validateManifest(Context context, VectorCase[] cases) throws Exception {
        JSONObject root = new JSONObject(new String(
                readBoundedAsset(context, MANIFEST_ASSET),
                StandardCharsets.UTF_8
        ));
        if (root.length() != 1 || !root.has("conversions")) {
            throw new IllegalStateException("conversion manifest root is invalid");
        }
        JSONArray rows = root.getJSONArray("conversions");
        if (rows.length() != cases.length) {
            throw new IllegalStateException("conversion manifest/vector count mismatch");
        }
        for (VectorCase vectorCase : cases) {
            JSONObject found = null;
            for (int index = 0; index < rows.length(); index++) {
                JSONObject row = rows.getJSONObject(index);
                if (vectorCase.profileId.equals(row.optString("profile_id", null))) {
                    found = row;
                    break;
                }
            }
            if (found == null
                    || found.length() != 4
                    || !vectorCase.converterId.equals(found.getString("converter_id"))
                    || !vectorCase.assetPath.equals(found.getString("asset_path"))
                    || !vectorCase.sha256.equals(found.getString("artifact_sha256"))) {
                throw new IllegalStateException("conversion manifest binding mismatch");
            }
        }
    }

    private static File copyAsset(Context context, VectorCase vectorCase) throws Exception {
        File output = new File(
                context.getCacheDir(),
                vectorCase.converterId + "-benchmark.ncm"
        );
        int total = 0;
        try (InputStream input = context.getAssets().open(vectorCase.assetPath);
             FileOutputStream stream = new FileOutputStream(output, false)) {
            byte[] buffer = new byte[8 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > MAX_MAP_BYTES) {
                    throw new IllegalStateException("conversion map exceeds size limit");
                }
                stream.write(buffer, 0, read);
            }
            if (total == 0) {
                throw new IllegalStateException("conversion map is empty");
            }
            stream.flush();
            stream.getFD().sync();
        }
        return output;
    }

    private static byte[] readBoundedAsset(Context context, String path) throws Exception {
        try (InputStream input = context.getAssets().open(path);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8 * 1024];
            int total = 0;
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > MAX_METADATA_BYTES) {
                    throw new IllegalStateException("conversion metadata exceeds size limit");
                }
                output.write(buffer, 0, read);
            }
            if (total == 0) {
                throw new IllegalStateException("conversion metadata is empty");
            }
            return output.toByteArray();
        }
    }

    private static long percentile(long[] sorted, int percentile) {
        int index = (int) Math.ceil((percentile / 100.0) * sorted.length) - 1;
        return sorted[Math.max(0, Math.min(sorted.length - 1, index))];
    }

    private static int boundedInteger(String value, int fallback, int minimum, int maximum) {
        try {
            int parsed = value == null ? fallback : Integer.parseInt(value);
            return Math.max(minimum, Math.min(maximum, parsed));
        } catch (NumberFormatException ignored) {
            return fallback;
        }
    }

    private static void assertEquals(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(String.format(
                    Locale.ROOT,
                    "%s: expected %s, got %s",
                    label,
                    expected,
                    actual
            ));
        }
    }

    private static final class VectorCase {
        final String profileId;
        final String converterId;
        final String assetPath;
        final String sha256;
        final String language;
        final String sourceScript;
        final String outputScript;
        final String releaseMode;
        final int ruleCount;
        final ConversionVector[] vectors;

        VectorCase(
                String profileId,
                String converterId,
                String assetPath,
                String sha256,
                String language,
                String sourceScript,
                String outputScript,
                String releaseMode,
                int ruleCount,
                ConversionVector[] vectors
        ) {
            this.profileId = profileId;
            this.converterId = converterId;
            this.assetPath = assetPath;
            this.sha256 = sha256;
            this.language = language;
            this.sourceScript = sourceScript;
            this.outputScript = outputScript;
            this.releaseMode = releaseMode;
            this.ruleCount = ruleCount;
            this.vectors = vectors;
        }
    }

    private static final class ConversionVector {
        final String input;
        final String expectedStatus;
        final String expectedOutput;

        ConversionVector(String input, String expectedStatus, String expectedOutput) {
            this.input = input;
            this.expectedStatus = expectedStatus;
            this.expectedOutput = expectedOutput;
        }
    }
}
