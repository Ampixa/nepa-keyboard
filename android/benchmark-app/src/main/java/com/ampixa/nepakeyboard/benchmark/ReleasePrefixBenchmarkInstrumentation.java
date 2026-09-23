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
import java.text.Normalizer;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/** Catalog correctness and prefix benchmark for exact staged pack bindings. */
public class ReleasePrefixBenchmarkInstrumentation extends Instrumentation {
    private static final String TAG = "NepaCatalogBenchmark";
    private static final String MANIFEST_ASSET = "nepa-packs/manifest.json";
    private static final String VECTOR_ASSET = "nepa-packs/benchmark-vectors.json";
    private static final int MAX_MANIFEST_BYTES = 256 * 1024;
    private static final long MAX_PACK_BYTES = 256L * 1024L * 1024L;

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
            PackCase[] packs = readPackCases(context);
            boolean allowInternal = allowInternalPacks();
            validateCatalogAuthority(packs, allowInternal);
            JSONObject manifest = readManifest(context);
            validateManifest(manifest, packs);

            output.putString("status", "ok");
            output.putString("benchmark_mode", benchmarkMode());
            output.putInt("pack_count", packs.length);
            output.putInt("iterations_per_metric", iterations);
            output.putInt("warmups_per_pack", warmups);

            for (PackCase packCase : packs) {
                benchmarkPack(
                        context,
                        packCase,
                        iterations,
                        warmups,
                        allowInternal,
                        output
                );
                System.gc();
                SystemClock.sleep(100L);
            }
            output.putLong("process_pss_kb_after_benchmarks", Debug.getPss());
            File report = writeReport(context, output);
            output.putString("report_path", report.getAbsolutePath());
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            Log.e(TAG, "catalog benchmark failed", failure);
            output.putString("status", "error");
            output.putString("error", failure.toString());
        }
        finish(resultCode, output);
    }

    protected boolean allowInternalPacks() {
        return false;
    }

    protected String benchmarkMode() {
        return "release_catalog_prefix";
    }

    private static void validateCatalogAuthority(PackCase[] packs, boolean allowInternal) {
        if (allowInternal) {
            return;
        }
        for (PackCase packCase : packs) {
            if (!"release".equals(packCase.releaseMode)) {
                throw new SecurityException(
                        "release catalog contains a non-release pack: " + packCase.packId
                );
            }
        }
    }

    private static void benchmarkPack(
            Context context,
            PackCase packCase,
            int iterations,
            int warmups,
            boolean allowInternal,
            Bundle output
    ) throws Exception {
        long copyStart = SystemClock.elapsedRealtimeNanos();
        File packFile = copyAsset(context, packCase);
        long verifiedCopyNs = SystemClock.elapsedRealtimeNanos() - copyStart;

        long loadStart = SystemClock.elapsedRealtimeNanos();
        try (NkpBundle pack = NkpBundle.open(
                packFile,
                packCase.sha256,
                allowInternal
        )) {
            long verifiedLoadNs = SystemClock.elapsedRealtimeNanos() - loadStart;
            assertEquals(packCase.packId + " pack ID", packCase.packId, pack.packId());
            assertEquals(
                    packCase.packId + " release mode",
                    packCase.releaseMode,
                    pack.releaseMode()
            );
            String normalizedSmokeQuery = Normalizer.normalize(
                    packCase.smokeQuery,
                    Normalizer.Form.NFC
            );
            String diagnosticPrefix = packCase.label + "_smoke_";
            output.putString(diagnosticPrefix + "query", packCase.smokeQuery);
            output.putString(
                    diagnosticPrefix + "query_code_points",
                    codePoints(packCase.smokeQuery)
            );
            output.putString(diagnosticPrefix + "normalized_query", normalizedSmokeQuery);
            output.putString(
                    diagnosticPrefix + "normalized_code_points",
                    codePoints(normalizedSmokeQuery)
            );
            output.putBoolean(
                    diagnosticPrefix + "nfc_stable",
                    packCase.smokeQuery.equals(normalizedSmokeQuery)
            );
            output.putInt(
                    diagnosticPrefix + "candidate_id_count",
                    lookupIds(pack, packCase, packCase.smokeQuery).length
            );
            assertFirstSurface(
                    packCase.packId + " smoke lookup",
                    suggestions(pack, packCase, packCase.smokeQuery),
                    packCase.smokeExpected
            );
            if ("eng-Latn-US".equals(packCase.profileId)) {
                assertContainsSurface("English case normalization", pack.suggestSurface("HEL"), "hello", 3);
                assertEmpty("English negative lookup", pack.suggestSurface("zzqx"));
            }

            runWarmups(pack, packCase, warmups);
            BenchmarkResult ids = benchmarkIds(pack, packCase, iterations);
            BenchmarkResult full = benchmarkSuggestions(pack, packCase, iterations);

            String prefix = packCase.label;
            output.putString(prefix + "_pack_id", pack.packId());
            output.putString(prefix + "_artifact_sha256", pack.artifactSha256());
            output.putString(prefix + "_release_mode", pack.releaseMode());
            output.putInt(prefix + "_candidate_count", pack.candidateCount());
            output.putLong(prefix + "_asset_copy_and_sha_ns", verifiedCopyNs);
            output.putLong(prefix + "_verified_load_ns", verifiedLoadNs);
            output.putLong(prefix + "_process_pss_kb", Debug.getPss());
            String metricKind = "alias_prefix".equals(packCase.lookupKind)
                    ? "alias" : "surface";
            ids.writeTo(output, prefix + "_" + metricKind + "_ids");
            full.writeTo(output, prefix + "_" + metricKind + "_full");
        }
    }

    private static JSONObject readManifest(Context context) throws Exception {
        return new JSONObject(new String(
                readBoundedAsset(context, MANIFEST_ASSET),
                StandardCharsets.UTF_8
        ));
    }

    private static byte[] readBoundedAsset(Context context, String assetPath) throws Exception {
        try (InputStream input = context.getAssets().open(assetPath);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8 * 1024];
            int total = 0;
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > MAX_MANIFEST_BYTES) {
                    throw new IllegalStateException("catalog manifest exceeds size limit");
                }
                output.write(buffer, 0, read);
            }
            if (total == 0) {
                throw new IllegalStateException("catalog manifest is empty");
            }
            return output.toByteArray();
        }
    }

    private static String codePoints(String value) {
        StringBuilder result = new StringBuilder();
        value.codePoints().forEach(codePoint -> {
            if (result.length() > 0) {
                result.append(',');
            }
            result.append(String.format(Locale.ROOT, "U+%04X", codePoint));
        });
        return result.toString();
    }

    private static PackCase[] readPackCases(Context context) throws Exception {
        JSONObject root = new JSONObject(new String(
                readBoundedAsset(context, VECTOR_ASSET),
                StandardCharsets.UTF_8
        ));
        if (root.length() != 1 || !root.has("bindings")) {
            throw new IllegalStateException("catalog vector root is invalid");
        }
        JSONArray rows = root.getJSONArray("bindings");
        if (rows.length() < 1 || rows.length() > 64) {
            throw new IllegalStateException("catalog vector count is invalid");
        }
        PackCase[] result = new PackCase[rows.length()];
        java.util.HashSet<String> profileIds = new java.util.HashSet<>();
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.getJSONObject(index);
            if (row.length() != 15) {
                throw new IllegalStateException("catalog vector has unexpected fields");
            }
            String profileId = row.getString("profile_id");
            String lookupKind = row.getString("lookup_kind");
            String releaseMode = row.getString("release_mode");
            JSONArray queryRows = row.getJSONArray("benchmark_queries");
            if (!profileIds.add(profileId)
                    || !("surface_prefix".equals(lookupKind) || "alias_prefix".equals(lookupKind))
                    || !("release".equals(releaseMode) || "internal".equals(releaseMode))
                    || queryRows.length() < 1
                    || queryRows.length() > 64) {
                throw new IllegalStateException("catalog vector identity is invalid");
            }
            String[] queries = new String[queryRows.length()];
            for (int queryIndex = 0; queryIndex < queryRows.length(); queryIndex++) {
                queries[queryIndex] = queryRows.getString(queryIndex);
                if (queries[queryIndex].isEmpty()) {
                    throw new IllegalStateException("catalog benchmark query is empty");
                }
            }
            result[index] = new PackCase(
                    profileId.replace('-', '_'),
                    profileId,
                    row.getString("pack_id"),
                    row.getString("asset_path"),
                    row.getString("artifact_sha256"),
                    releaseMode,
                    lookupKind,
                    row.getString("validation_query"),
                    row.getString("validation_expected_surface"),
                    queries
            );
        }
        return result;
    }

    private static void validateManifest(JSONObject root, PackCase[] packs) throws Exception {
        if (root.length() != 1 || !root.has("packs")) {
            throw new IllegalStateException("catalog manifest root is invalid");
        }
        JSONArray rows = root.getJSONArray("packs");
        if (rows.length() != packs.length) {
            throw new IllegalStateException("catalog manifest/vector count mismatch");
        }
        for (PackCase packCase : packs) {
            JSONObject match = null;
            for (int index = 0; index < rows.length(); index++) {
                JSONObject row = rows.getJSONObject(index);
                if (packCase.profileId.equals(row.optString("profile_id", null))) {
                    match = row;
                    break;
                }
            }
            if (match == null
                    || match.length() != 4
                    || !packCase.profileId.equals(match.getString("profile_id"))
                    || !packCase.packId.equals(match.getString("pack_id"))
                    || !packCase.assetPath.equals(match.getString("asset_path"))
                    || !packCase.sha256.equals(match.getString("artifact_sha256"))) {
                throw new IllegalStateException("catalog manifest binding mismatch");
            }
        }
    }

    private static File copyAsset(Context context, PackCase packCase) throws Exception {
        File output = new File(context.getCacheDir(), packCase.packId + "-catalog.nkp");
        long total = 0;
        try (InputStream input = context.getAssets().open(packCase.assetPath);
             FileOutputStream stream = new FileOutputStream(output, false)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > MAX_PACK_BYTES) {
                    throw new IllegalStateException("catalog pack exceeds size limit");
                }
                stream.write(buffer, 0, read);
            }
            if (total == 0) {
                throw new IllegalStateException("catalog pack is empty");
            }
            stream.flush();
            stream.getFD().sync();
        }
        return output;
    }

    private static void runWarmups(NkpBundle pack, PackCase packCase, int warmups) {
        long checksum = 0;
        for (int index = 0; index < warmups; index++) {
            String query = packCase.queries[index % packCase.queries.length];
            int[] ids = lookupIds(pack, packCase, query);
            checksum += ids.length == 0 ? 0 : ids[0] + ids.length;
            List<NkpBundle.Suggestion> rows = suggestions(pack, packCase, query);
            checksum += rows.isEmpty() ? 0 : rows.get(0).candidateId();
        }
        if (checksum == Long.MIN_VALUE) {
            throw new AssertionError("unreachable warmup checksum");
        }
    }

    private static BenchmarkResult benchmarkIds(
            NkpBundle pack,
            PackCase packCase,
            int iterations
    ) {
        long[] durations = new long[iterations];
        long checksum = 1;
        for (int index = 0; index < iterations; index++) {
            String query = packCase.queries[index % packCase.queries.length];
            long start = System.nanoTime();
            int[] ids = lookupIds(pack, packCase, query);
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
            PackCase packCase,
            int iterations
    ) {
        long[] durations = new long[iterations];
        long checksum = 1;
        for (int index = 0; index < iterations; index++) {
            String query = packCase.queries[index % packCase.queries.length];
            long start = System.nanoTime();
            List<NkpBundle.Suggestion> suggestions = suggestions(pack, packCase, query);
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

    private static int[] lookupIds(NkpBundle pack, PackCase packCase, String query) {
        return "alias_prefix".equals(packCase.lookupKind)
                ? pack.lookupAliasIds(query)
                : pack.lookupSurfaceIds(query);
    }

    private static List<NkpBundle.Suggestion> suggestions(
            NkpBundle pack,
            PackCase packCase,
            String query
    ) {
        return "alias_prefix".equals(packCase.lookupKind)
                ? pack.suggestAliases(query)
                : pack.suggestSurface(query);
    }

    private static int boundedInteger(String value, int fallback, int minimum, int maximum) {
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
        throw new AssertionError(label + " did not contain " + expected + " in top " + maximumRank);
    }

    private static void assertEmpty(String label, List<NkpBundle.Suggestion> suggestions) {
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
        File output = new File(context.getFilesDir(), "catalog-prefix-benchmark.json");
        try (FileWriter writer = new FileWriter(output, false)) {
            writer.write(json.toString(2));
            writer.write('\n');
        }
        return output;
    }

    private static final class PackCase {
        final String label;
        final String profileId;
        final String packId;
        final String assetPath;
        final String sha256;
        final String releaseMode;
        final String lookupKind;
        final String smokeQuery;
        final String smokeExpected;
        final String[] queries;

        PackCase(
                String label,
                String profileId,
                String packId,
                String assetPath,
                String sha256,
                String releaseMode,
                String lookupKind,
                String smokeQuery,
                String smokeExpected,
                String[] queries
        ) {
            this.label = label;
            this.profileId = profileId;
            this.packId = packId;
            this.assetPath = assetPath;
            this.sha256 = sha256;
            this.releaseMode = releaseMode;
            this.lookupKind = lookupKind;
            this.smokeQuery = smokeQuery;
            this.smokeExpected = smokeExpected;
            this.queries = queries;
        }
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
