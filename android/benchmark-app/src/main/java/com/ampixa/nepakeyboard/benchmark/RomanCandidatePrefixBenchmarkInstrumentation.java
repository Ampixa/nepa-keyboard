package com.ampixa.nepakeyboard.benchmark;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import android.os.Debug;
import android.os.SystemClock;
import android.util.Log;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/**
 * Production-reader benchmark for the quality-gated Romanized Nepali pack.
 *
 * <p>The exact release artifact passes the normal Gradle redistribution gate,
 * but this benchmark APK does not make the blocked Roman input profile
 * selectable and the pack is never attached to an IME build variant.</p>
 */
public final class RomanCandidatePrefixBenchmarkInstrumentation extends Instrumentation {
    private static final String TAG = "NepaRomanBenchmark";
    private static final String PROFILE_ID = "npi-Latn-Deva-NP";
    private static final String PACK_ID = "npi-Deva-NP";
    private static final String ASSET_PATH = "nepa-packs/npi-Deva-NP.nkp";
    private static final String MANIFEST_ASSET = "nepa-packs/manifest.json";
    private static final String ARTIFACT_SHA256 =
            "09eb5b7496855c94593dc3b71c47e44221d62c4def2f57b4aa0507e7d6edf05f";
    private static final int CANDIDATE_COUNT = 80_969;
    private static final int MAX_MANIFEST_BYTES = 256 * 1024;
    private static final long MAX_PACK_BYTES = 256L * 1024L * 1024L;

    private static final String[] ALIAS_QUERIES = {
            "ne", "nep", "nepal", "nam", "namaste", "ghar", "sik",
            "bika", "sam", "bhasha", "dhanyabad", "swasthya", "keybo"
    };
    private static final String[] SURFACE_QUERIES = {
            "न", "ने", "नेपाल", "नम", "भ", "भा", "भाष", "स्वास्"
    };

    private Bundle benchmarkArguments = Bundle.EMPTY;

    @Override
    public void onCreate(Bundle arguments) {
        benchmarkArguments = arguments == null ? Bundle.EMPTY : new Bundle(arguments);
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle output = new Bundle();
        int resultCode = Activity.RESULT_CANCELED;
        try {
            int iterations = boundedInteger(
                    benchmarkArguments.getString("iterations"),
                    20_000,
                    1_000,
                    200_000
            );
            int warmups = boundedInteger(
                    benchmarkArguments.getString("warmups"),
                    2_000,
                    100,
                    20_000
            );
            Context context = getTargetContext();
            validateManifest(readManifest(context));

            output.putString("status", "ok");
            output.putString("benchmark_mode", "gated_nepali_roman_alias_prefix");
            output.putString("profile_id", PROFILE_ID);
            output.putBoolean("profile_selectable", false);
            output.putInt("iterations_per_metric", iterations);
            output.putInt("warmups", warmups);
            output.putLong("process_pss_kb_before_load", Debug.getPss());

            long copyStart = SystemClock.elapsedRealtimeNanos();
            File packFile = copyAsset(context);
            long copyNs = SystemClock.elapsedRealtimeNanos() - copyStart;

            long loadStart = SystemClock.elapsedRealtimeNanos();
            try (NkpBundle pack = NkpBundle.open(packFile, ARTIFACT_SHA256)) {
                long verifiedLoadNs = SystemClock.elapsedRealtimeNanos() - loadStart;
                assertEquals("pack ID", PACK_ID, pack.packId());
                assertEquals("release mode", "release", pack.releaseMode());
                if (pack.candidateCount() != CANDIDATE_COUNT) {
                    throw new AssertionError("candidate count mismatch");
                }
                assertFirstSurface("alias namaste", pack.suggestAliases("namaste"), "नमस्ते");
                assertFirstSurface(
                        "trimmed uppercase alias normalization",
                        pack.suggestAliases(" NAMASTE "),
                        "नमस्ते"
                );
                assertContainsSurface(
                        "alias nepal",
                        pack.suggestAliases("nepal"),
                        "नेपाल",
                        3
                );
                assertFirstSurface("surface भाषा", pack.suggestSurface("भाष"), "भाषा");
                assertEmpty("negative alias", pack.suggestAliases("zzqx"));
                output.putLong("process_pss_kb_after_open", Debug.getPss());

                runWarmups(pack, warmups);
                System.gc();
                SystemClock.sleep(100L);

                BenchmarkResult aliasIds = benchmarkIds(
                        pack,
                        true,
                        ALIAS_QUERIES,
                        iterations
                );
                BenchmarkResult aliasFull = benchmarkSuggestions(
                        pack,
                        ALIAS_QUERIES,
                        iterations
                );
                BenchmarkResult surfaceIds = benchmarkIds(
                        pack,
                        false,
                        SURFACE_QUERIES,
                        iterations
                );

                output.putString("pack_id", pack.packId());
                output.putString("artifact_sha256", pack.artifactSha256());
                output.putString("release_mode", pack.releaseMode());
                output.putInt("candidate_count", pack.candidateCount());
                output.putLong("asset_copy_fsync_ns", copyNs);
                output.putLong("verified_load_ns", verifiedLoadNs);
                output.putLong("process_pss_kb_after_benchmarks", Debug.getPss());
                aliasIds.writeTo(output, "alias_ids");
                aliasFull.writeTo(output, "alias_full");
                surfaceIds.writeTo(output, "surface_ids");
            }

            File report = writeReport(context, output);
            output.putString("report_path", report.getAbsolutePath());
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            Log.e(TAG, "Roman candidate benchmark failed", failure);
            output.putString("status", "error");
            output.putString("error", failure.toString());
        }
        finish(resultCode, output);
    }

    private static JSONObject readManifest(Context context) throws Exception {
        byte[] encoded;
        try (InputStream input = context.getAssets().open(MANIFEST_ASSET);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8 * 1024];
            int total = 0;
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > MAX_MANIFEST_BYTES) {
                    throw new IllegalStateException("candidate manifest exceeds size limit");
                }
                output.write(buffer, 0, read);
            }
            if (total == 0) {
                throw new IllegalStateException("candidate manifest is empty");
            }
            encoded = output.toByteArray();
        }
        return new JSONObject(new String(encoded, StandardCharsets.UTF_8));
    }

    private static void validateManifest(JSONObject root) throws Exception {
        if (root.length() != 1 || !root.has("packs")) {
            throw new IllegalStateException("candidate manifest root is invalid");
        }
        JSONArray rows = root.getJSONArray("packs");
        if (rows.length() != 1) {
            throw new IllegalStateException("candidate manifest must bind exactly one pack");
        }
        JSONObject row = rows.getJSONObject(0);
        if (row.length() != 4
                || !PROFILE_ID.equals(row.getString("profile_id"))
                || !PACK_ID.equals(row.getString("pack_id"))
                || !ASSET_PATH.equals(row.getString("asset_path"))
                || !ARTIFACT_SHA256.equals(row.getString("artifact_sha256"))) {
            throw new IllegalStateException("candidate manifest binding mismatch");
        }
    }

    private static File copyAsset(Context context) throws Exception {
        File output = new File(context.getCacheDir(), "npi-roman-candidate.nkp");
        long total = 0;
        try (InputStream input = context.getAssets().open(ASSET_PATH);
             FileOutputStream stream = new FileOutputStream(output, false)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > MAX_PACK_BYTES) {
                    throw new IllegalStateException("candidate pack exceeds size limit");
                }
                stream.write(buffer, 0, read);
            }
            if (total == 0) {
                throw new IllegalStateException("candidate pack is empty");
            }
            stream.flush();
            stream.getFD().sync();
        }
        return output;
    }

    private static void runWarmups(NkpBundle pack, int warmups) {
        long checksum = 0;
        for (int index = 0; index < warmups; index++) {
            String alias = ALIAS_QUERIES[index % ALIAS_QUERIES.length];
            int[] ids = pack.lookupAliasIds(alias);
            checksum += ids.length == 0 ? 0 : ids[0] + ids.length;
            List<NkpBundle.Suggestion> suggestions = pack.suggestAliases(alias);
            checksum += suggestions.isEmpty() ? 0 : suggestions.get(0).candidateId();
            ids = pack.lookupSurfaceIds(SURFACE_QUERIES[index % SURFACE_QUERIES.length]);
            checksum += ids.length == 0 ? 0 : ids[0] + ids.length;
        }
        if (checksum == Long.MIN_VALUE) {
            throw new AssertionError("unreachable warmup checksum");
        }
    }

    private static BenchmarkResult benchmarkIds(
            NkpBundle pack,
            boolean aliases,
            String[] queries,
            int iterations
    ) {
        long[] durations = new long[iterations];
        long checksum = 1;
        for (int index = 0; index < iterations; index++) {
            String query = queries[index % queries.length];
            long start = System.nanoTime();
            int[] ids = aliases
                    ? pack.lookupAliasIds(query)
                    : pack.lookupSurfaceIds(query);
            durations[index] = System.nanoTime() - start;
            checksum = checksum * 31 + ids.length;
            if (ids.length > 0) {
                checksum = checksum * 31 + ids[0];
            }
        }
        return BenchmarkResult.calculate(durations, checksum);
    }

    private static BenchmarkResult benchmarkSuggestions(
            NkpBundle pack,
            String[] queries,
            int iterations
    ) {
        long[] durations = new long[iterations];
        long checksum = 1;
        for (int index = 0; index < iterations; index++) {
            String query = queries[index % queries.length];
            long start = System.nanoTime();
            List<NkpBundle.Suggestion> suggestions = pack.suggestAliases(query);
            durations[index] = System.nanoTime() - start;
            checksum = checksum * 31 + suggestions.size();
            if (!suggestions.isEmpty()) {
                NkpBundle.Suggestion first = suggestions.get(0);
                checksum = checksum * 31 + first.candidateId();
                checksum = checksum * 31 + first.surface().length();
                checksum = checksum * 31 + first.score();
            }
        }
        return BenchmarkResult.calculate(durations, checksum);
    }

    private static int boundedInteger(
            String value,
            int fallback,
            int minimum,
            int maximum
    ) {
        int parsed = fallback;
        if (value != null) {
            try {
                parsed = Integer.parseInt(value);
            } catch (NumberFormatException ignored) {
                parsed = fallback;
            }
        }
        return Math.max(minimum, Math.min(maximum, parsed));
    }

    private static void assertFirstSurface(
            String label,
            List<NkpBundle.Suggestion> suggestions,
            String expected
    ) {
        if (suggestions.isEmpty()) {
            throw new AssertionError(label + " returned no suggestions");
        }
        assertEquals(label, expected, suggestions.get(0).surface());
    }

    private static void assertContainsSurface(
            String label,
            List<NkpBundle.Suggestion> suggestions,
            String expected,
            int maximumRank
    ) {
        int limit = Math.min(maximumRank, suggestions.size());
        for (int index = 0; index < limit; index++) {
            if (expected.equals(suggestions.get(index).surface())) {
                return;
            }
        }
        throw new AssertionError(label + " did not contain " + expected);
    }

    private static void assertEmpty(
            String label,
            List<NkpBundle.Suggestion> suggestions
    ) {
        if (!suggestions.isEmpty()) {
            throw new AssertionError(label + " returned unexpected suggestions");
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

    private static File writeReport(Context context, Bundle values) throws Exception {
        JSONObject json = new JSONObject();
        for (String key : values.keySet()) {
            json.put(key, values.get(key));
        }
        File output = new File(context.getFilesDir(), "roman-candidate-prefix-benchmark.json");
        try (FileWriter writer = new FileWriter(output, false)) {
            writer.write(json.toString(2));
            writer.write('\n');
        }
        return output;
    }

    private static final class BenchmarkResult {
        final long meanNs;
        final long p50Ns;
        final long p95Ns;
        final long p99Ns;
        final long maxNs;
        final long checksum;

        BenchmarkResult(
                long meanNs,
                long p50Ns,
                long p95Ns,
                long p99Ns,
                long maxNs,
                long checksum
        ) {
            this.meanNs = meanNs;
            this.p50Ns = p50Ns;
            this.p95Ns = p95Ns;
            this.p99Ns = p99Ns;
            this.maxNs = maxNs;
            this.checksum = checksum;
        }

        static BenchmarkResult calculate(long[] source, long checksum) {
            long[] sorted = source.clone();
            Arrays.sort(sorted);
            long sum = 0;
            for (long value : source) {
                sum += value;
            }
            return new BenchmarkResult(
                    sum / source.length,
                    percentile(sorted, 50),
                    percentile(sorted, 95),
                    percentile(sorted, 99),
                    sorted[sorted.length - 1],
                    checksum
            );
        }

        void writeTo(Bundle output, String prefix) {
            output.putLong(prefix + "_mean_ns", meanNs);
            output.putLong(prefix + "_p50_ns", p50Ns);
            output.putLong(prefix + "_p95_ns", p95Ns);
            output.putLong(prefix + "_p99_ns", p99Ns);
            output.putLong(prefix + "_max_ns", maxNs);
            output.putLong(prefix + "_checksum", checksum);
        }

        private static long percentile(long[] sorted, int percentile) {
            int index = (int) Math.ceil((percentile / 100.0) * sorted.length) - 1;
            return sorted[Math.max(0, Math.min(sorted.length - 1, index))];
        }
    }
}
