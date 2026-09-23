package com.ampixa.nepakeyboard.benchmark;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import android.os.Debug;
import android.os.SystemClock;
import android.util.Log;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/** Platform-only instrumentation harness for v0 prefix lookup. */
public final class PrefixBenchmarkInstrumentation extends Instrumentation {
    private static final String TAG = "NepaPackBenchmark";
    private static final String ASSET_NAME = "benchmark.nkp";
    private static final String DEFAULT_EXPECTED_SHA256 =
            "b219ccce305baf5472f45d639cd452cba8dcbd24dde2602073ce77e985d4c0aa";

    private static final String[] ALIAS_QUERIES = {
            "n", "ne", "nep", "nepa", "nepal", "nam", "namas", "namaste",
            "ghar", "sik", "bika", "sam"
    };
    private static final String[] SURFACE_QUERIES = {
            "न", "ने", "नेपाल", "नम", "प", "भ", "स", "क"
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
            Bundle arguments = benchmarkArguments;
            boolean allowInternal = Boolean.parseBoolean(arguments.getString("allowInternal", "false"));
            if (!allowInternal) {
                throw new SecurityException(
                        "legacy benchmark requires explicit -e allowInternal true; "
                                + "public/export reader remains closed"
                );
            }
            int iterations = boundedInteger(arguments.getString("iterations"), 20_000, 1_000, 200_000);
            int warmups = boundedInteger(arguments.getString("warmups"), 2_000, 100, 20_000);
            String expectedSha256 = arguments.getString("expectedSha256", DEFAULT_EXPECTED_SHA256);

            Context context = getTargetContext();
            File packFile = copyAsset(context, ASSET_NAME);

            boolean productionGateRejectedInternal = false;
            try (NkpBundle ignored = NkpBundle.open(packFile, expectedSha256)) {
                // A successful public/export-mode open of this internal pack is a test failure.
            } catch (SecurityException expected) {
                productionGateRejectedInternal = true;
            }
            if (!productionGateRejectedInternal) {
                throw new AssertionError("public/export reader accepted an internal pack");
            }

            long loadStart = SystemClock.elapsedRealtimeNanos();
            try (NkpBundle pack = NkpBundle.open(packFile, expectedSha256, true)) {
                long verifiedLoadNs = SystemClock.elapsedRealtimeNanos() - loadStart;
                assertEquals("pack ID", "npi-Deva-NP", pack.packId());
                assertEquals("release mode", "internal", pack.releaseMode());
                assertFirstSurface("alias nepal", pack.suggestAliases("nepal"), "नेपाल");
                assertFirstSurface("alias namaste", pack.suggestAliases("namaste"), "नमस्ते");
                assertFirstSurface("surface ने", pack.suggestSurface("ने"), "नेपाल");

                runWarmups(pack, warmups);
                System.gc();
                SystemClock.sleep(100L);

                BenchmarkResult aliasIds = benchmarkIds(pack, true, ALIAS_QUERIES, iterations);
                BenchmarkResult aliasFull = benchmarkSuggestions(pack, ALIAS_QUERIES, iterations);
                BenchmarkResult surfaceIds = benchmarkIds(pack, false, SURFACE_QUERIES, iterations);

                output.putString("status", "ok");
                output.putString("pack_id", pack.packId());
                output.putString("artifact_sha256", pack.artifactSha256());
                output.putString("release_mode", pack.releaseMode());
                output.putInt("candidate_count", pack.candidateCount());
                output.putBoolean("production_gate_rejected_internal", productionGateRejectedInternal);
                output.putInt("iterations", iterations);
                output.putInt("warmups", warmups);
                output.putLong("verified_load_ns", verifiedLoadNs);
                output.putLong("process_pss_kb", Debug.getPss());
                aliasIds.writeTo(output, "alias_ids");
                aliasFull.writeTo(output, "alias_full");
                surfaceIds.writeTo(output, "surface_ids");

                File report = writeReport(context, output);
                output.putString("report_path", report.getAbsolutePath());
                resultCode = Activity.RESULT_OK;
            }
        } catch (Throwable failure) {
            Log.e(TAG, "benchmark failed", failure);
            output.putString("status", "error");
            output.putString("error", failure.toString());
        }
        finish(resultCode, output);
    }

    private static void runWarmups(NkpBundle pack, int warmups) {
        long checksum = 0;
        for (int index = 0; index < warmups; index++) {
            int[] ids = pack.lookupAliasIds(ALIAS_QUERIES[index % ALIAS_QUERIES.length]);
            checksum += ids.length == 0 ? 0 : ids[0] + ids.length;
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
            int[] ids = aliases ? pack.lookupAliasIds(query) : pack.lookupSurfaceIds(query);
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

    private static File copyAsset(Context context, String assetName) throws IOException {
        File output = new File(context.getCacheDir(), assetName);
        try (InputStream input = context.getAssets().open(assetName);
             FileOutputStream stream = new FileOutputStream(output, false)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                stream.write(buffer, 0, read);
            }
        }
        return output;
    }

    private static File writeReport(Context context, Bundle values) throws Exception {
        JSONObject json = new JSONObject();
        for (String key : values.keySet()) {
            json.put(key, values.get(key));
        }
        File output = new File(context.getFilesDir(), "prefix-benchmark.json");
        try (FileWriter writer = new FileWriter(output, false)) {
            writer.write(json.toString(2));
            writer.write('\n');
        }
        return output;
    }

    private static int boundedInteger(String value, int defaultValue, int minimum, int maximum) {
        int parsed = defaultValue;
        if (value != null) {
            try {
                parsed = Integer.parseInt(value);
            } catch (NumberFormatException ignored) {
                parsed = defaultValue;
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

    private static final class BenchmarkResult {
        final long meanNs;
        final long p50Ns;
        final long p95Ns;
        final long p99Ns;
        final long maxNs;
        final long checksum;

        private BenchmarkResult(
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
