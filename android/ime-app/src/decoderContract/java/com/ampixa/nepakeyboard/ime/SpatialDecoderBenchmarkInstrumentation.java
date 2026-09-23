package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import android.os.Debug;
import android.os.SystemClock;
import android.util.Log;

import org.json.JSONObject;

import java.io.File;
import java.io.FileWriter;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/** Production-path exact, clean-center, and boundary-correction spatial benchmark. */
public final class SpatialDecoderBenchmarkInstrumentation extends Instrumentation {
    private static final String TAG = "NepaSpatialBenchmark";
    private static final String BENCHMARK_MODE = "spatial_decoder_v1";
    private static final int PROFILE_COUNT = 2;
    private static final long PACK_READY_TIMEOUT_MILLIS = 300_000L;
    private static final long REFERENCE_PHYSICAL_P95_BUDGET_NS = 10_000_000L;

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
                    10_000,
                    1_000,
                    200_000
            );
            int warmups = boundedInteger(
                    benchmarkArguments.getString("warmups"),
                    1_000,
                    100,
                    20_000
            );
            long enforcedP95BudgetNs = optionalPositiveLong(
                    benchmarkArguments.getString("maxP95Ns")
            );
            Context context = getTargetContext();
            KeyboardProfile english = requireProfile(LanguageRegistry.ENGLISH_ID);
            KeyboardProfile nepali = requireProfile(LanguageRegistry.NEPALI_DIRECT_ID);
            List<ReleasePackSpec> specs = ReleasePackRegistry.installed(context);
            if (specs.isEmpty()) {
                throw new AssertionError("spatial benchmark requires staged product packs");
            }

            SpatialDecoderVectors.ProfileVectors englishVectors =
                    SpatialDecoderVectors.captureEnglish(this, context, english);
            SpatialDecoderVectors.ProfileVectors nepaliVectors =
                    SpatialDecoderVectors.captureNepali(this, context, nepali);

            output.putString("status", "ok");
            output.putString("benchmark_mode", BENCHMARK_MODE);
            output.putInt("profile_count", PROFILE_COUNT);
            output.putLong("pack_ready_timeout_ms", PACK_READY_TIMEOUT_MILLIS);
            output.putInt("iterations_per_metric", iterations);
            output.putInt("warmups_per_metric", warmups);
            output.putInt(
                    "spatial_beam_limit",
                    NkpSuggestionEngine.maxSpatialBeamsForTesting()
            );
            output.putLong(
                    "latency_budget_ns",
                    enforcedP95BudgetNs == 0L
                            ? REFERENCE_PHYSICAL_P95_BUDGET_NS
                            : enforcedP95BudgetNs
            );
            output.putBoolean("latency_budget_enforced", enforcedP95BudgetNs > 0L);
            output.putBoolean("functional_query_deadline_enforced", false);
            output.putString(
                    "deadline_outcome_coverage",
                    "DecoderContractInstrumentation"
            );

            SuggestionEngine engine = SuggestionEngineFactory.createForDecoderTest(
                    specs,
                    activation -> {
                    },
                    NkpSuggestionEngine.DecodeObserver.NONE
            );
            try {
                benchmarkProfile(
                        engine,
                        specs,
                        english,
                        englishVectors,
                        "english",
                        iterations,
                        warmups,
                        enforcedP95BudgetNs,
                        output
                );
                benchmarkProfile(
                        engine,
                        specs,
                        nepali,
                        nepaliVectors,
                        "nepali",
                        iterations,
                        warmups,
                        enforcedP95BudgetNs,
                        output
                );
            } finally {
                engine.close();
            }

            output.putString("english_exact_verified", "true");
            output.putString("english_clean_center_parity_verified", "true");
            output.putString("english_boundary_correction_verified", "true");
            output.putString("nepali_exact_verified", "true");
            output.putString("nepali_clean_center_parity_verified", "true");
            output.putString("nepali_boundary_correction_verified", "true");
            output.putString("spatial_literal_preservation_verified", "true");
            output.putString("spatial_beam_bound_verified", "true");
            output.putString("spatial_clean_exact_fast_path_verified", "true");

            File report = writeReport(context, output);
            output.putString("report_path", report.getAbsolutePath());
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            Log.e(TAG, "spatial decoder benchmark failed", failure);
            output.putString("status", "error");
            output.putString("failure", failure.toString());
            output.putString("stack", Log.getStackTraceString(failure));
        }
        finish(resultCode, output);
    }

    private static void benchmarkProfile(
            SuggestionEngine engine,
            List<ReleasePackSpec> specs,
            KeyboardProfile profile,
            SpatialDecoderVectors.ProfileVectors vectors,
            String label,
            int iterations,
            int warmups,
            long enforcedP95BudgetNs,
            Bundle output
    ) {
        ReleasePackSpec spec = requireSpec(specs, profile.id());
        SuggestionActivation activation = engine.activate(profile);
        awaitReady(engine, activation, profile, vectors.cleanPrefix());

        PathCase exact = new PathCase(
                "exact",
                vectors.cleanPrefix(),
                TouchSequence.empty(),
                vectors.expectedSurface(),
                SuggestionCandidate.Category.EXACT,
                NkpSuggestionEngine.EXACT_PREFIX_PROVIDER
        );
        int cleanBeamCount = NkpSuggestionEngine.spatialBeamCountForTesting(
                vectors.cleanTouchSequence(),
                vectors.cleanPrefix()
        );
        PathCase clean = new PathCase(
                "clean_center",
                vectors.cleanPrefix(),
                vectors.cleanTouchSequence(),
                vectors.expectedSurface(),
                SuggestionCandidate.Category.EXACT,
                NkpSuggestionEngine.SPATIAL_TAP_PROVIDER
        );
        int boundaryBeamCount = NkpSuggestionEngine.spatialBeamCountForTesting(
                vectors.boundaryTouchSequence(),
                vectors.boundaryRaw()
        );
        boolean cleanExactFastPath = NkpSuggestionEngine.isCleanExactTouchForTesting(
                vectors.cleanTouchSequence()
        );
        boolean boundaryExactFastPath = NkpSuggestionEngine.isCleanExactTouchForTesting(
                vectors.boundaryTouchSequence()
        );
        PathCase boundary = new PathCase(
                "boundary_correction",
                vectors.boundaryRaw(),
                vectors.boundaryTouchSequence(),
                vectors.expectedSurface(),
                SuggestionCandidate.Category.CORRECTION,
                NkpSuggestionEngine.SPATIAL_TAP_PROVIDER
        );

        int beamLimit = NkpSuggestionEngine.maxSpatialBeamsForTesting();
        if (cleanBeamCount < 1 || cleanBeamCount > beamLimit
                || boundaryBeamCount < 1 || boundaryBeamCount > beamLimit) {
            throw new AssertionError("spatial beam count is outside production bound");
        }
        if (!cleanExactFastPath || boundaryExactFastPath) {
            throw new AssertionError("clean/boundary spatial fast-path classification failed");
        }

        validatePath(engine, activation, profile, exact, 1_000_000L);
        validatePath(engine, activation, profile, clean, 1_000_001L);
        validatePath(engine, activation, profile, boundary, 1_000_002L);

        output.putString(label + "_pack_id", spec.packId());
        output.putString(label + "_artifact_sha256", spec.artifactSha256());
        output.putString(label + "_layout_id", profile.layoutId());
        output.putInt(label + "_layout_revision", profile.layoutRevision());
        output.putString(label + "_layout_source_sha256", profile.layoutSourceSha256());
        output.putString(label + "_exact_top_surface", exact.expectedSurface);
        output.putString(label + "_boundary_raw", boundary.rawText);
        output.putInt(label + "_exact_beam_count", 0);
        output.putInt(label + "_clean_center_beam_min", cleanBeamCount);
        output.putInt(label + "_clean_center_beam_max", cleanBeamCount);
        output.putInt(label + "_clean_center_beam_mean", cleanBeamCount);
        output.putInt(label + "_boundary_correction_beam_count", boundaryBeamCount);
        output.putString(label + "_clean_exact_fast_path_eligible", "true");
        output.putString(label + "_boundary_full_path_verified", "true");

        long generation = 2_000_000L;
        for (PathCase path : Arrays.asList(exact, clean, boundary)) {
            generation = warmup(
                    engine,
                    activation,
                    profile,
                    path,
                    warmups,
                    generation
            );
            TimedResult timed = benchmark(
                    engine,
                    activation,
                    profile,
                    path,
                    iterations,
                    generation
            );
            timed.writeTo(output, label + "_" + path.id);
            if (enforcedP95BudgetNs > 0L && timed.p95Ns > enforcedP95BudgetNs) {
                throw new AssertionError(String.format(
                        Locale.ROOT,
                        "%s %s P95 %d ns exceeds enforced budget %d ns",
                        profile.id(),
                        path.id,
                        timed.p95Ns,
                        enforcedP95BudgetNs
                ));
            }
            generation += iterations;
        }
    }

    private static long warmup(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            PathCase path,
            int iterations,
            long generation
    ) {
        long checksum = 1L;
        for (int index = 0; index < iterations; index++) {
            SuggestionQuery query = newQuery(
                    activation,
                    profile,
                    path,
                    generation++
            );
            SuggestionSnapshot snapshot = engine.suggest(activation, query);
            validateSnapshot(snapshot, query, path, System.nanoTime());
            checksum = checksum(snapshot, checksum);
        }
        if (checksum == Long.MIN_VALUE) {
            throw new AssertionError("unreachable spatial warmup checksum");
        }
        return generation;
    }

    private static TimedResult benchmark(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            PathCase path,
            int iterations,
            long firstGeneration
    ) {
        long[] durations = new long[iterations];
        long heapBefore = javaHeapUsed();
        long pssBefore = Debug.getPss();
        // Keep runtime counters last: work caused by the other baseline probes
        // must not be attributed to production decoder operations.
        long gcCountBefore = runtimeStat("art.gc.gc-count");
        long allocatedBefore = runtimeStat("art.gc.bytes-allocated");
        long checksum = 1L;
        long generation = firstGeneration;
        for (int index = 0; index < iterations; index++) {
            long start = System.nanoTime();
            SuggestionQuery query = newQuery(
                    activation,
                    profile,
                    path,
                    generation++
            );
            SuggestionSnapshot snapshot = engine.suggest(activation, query);
            long end = System.nanoTime();
            durations[index] = end - start;
            validateSnapshot(snapshot, query, path, end);
            checksum = checksum(snapshot, checksum);
        }
        long allocatedAfter = runtimeStat("art.gc.bytes-allocated");
        long gcCountAfter = runtimeStat("art.gc.gc-count");
        long heapAfter = javaHeapUsed();
        long pssAfter = Debug.getPss();
        if (allocatedAfter < allocatedBefore || gcCountAfter < gcCountBefore) {
            throw new AssertionError("ART runtime counters moved backwards");
        }
        return TimedResult.calculate(
                durations,
                checksum,
                allocatedAfter - allocatedBefore,
                gcCountAfter - gcCountBefore,
                heapBefore,
                heapAfter,
                pssBefore,
                pssAfter
        );
    }

    private static void validatePath(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            PathCase path,
            long generation
    ) {
        SuggestionQuery query = newQuery(activation, profile, path, generation);
        SuggestionSnapshot snapshot = engine.suggest(activation, query);
        validateSnapshot(snapshot, query, path, System.nanoTime());
    }

    private static void validateSnapshot(
            SuggestionSnapshot snapshot,
            SuggestionQuery query,
            PathCase path,
            long acceptedAtNanos
    ) {
        if (snapshot.status() != SuggestionSnapshot.Status.READY
                || !snapshot.belongsTo(query)
                || query.isBoundedDecoderRequest()
                || !query.acceptsProviderResults(acceptedAtNanos)
                || snapshot.nBestCandidates().size() > SuggestionSnapshot.MAX_CANDIDATES) {
            throw new AssertionError("timed spatial result contract failed: " + path.id);
        }
        List<SuggestionCandidate> candidates = snapshot.nBestCandidates();
        SuggestionCandidate provider = firstProviderCandidate(candidates);
        if (!path.expectedSurface.equals(provider.text())) {
            throw new AssertionError("timed spatial surface mismatch: " + path.id);
        }
        if (provider.category() != path.expectedCategory) {
            throw new AssertionError("timed spatial category mismatch: " + path.id);
        }
        if (!path.expectedProvider.equals(provider.providerId())) {
            throw new AssertionError("timed spatial provider mismatch: " + path.id);
        }
        int literalCount = 0;
        for (int index = 0; index < candidates.size(); index++) {
            SuggestionCandidate candidate = candidates.get(index);
            if (candidate.isLiteral()) {
                literalCount++;
                if (!path.rawText.equals(candidate.text())) {
                    throw new AssertionError("timed spatial literal mismatch: " + path.id);
                }
            }
        }
        if (literalCount != 1) {
            throw new AssertionError("timed spatial literal count mismatch: " + path.id);
        }
    }

    private static SuggestionCandidate firstProviderCandidate(
            List<SuggestionCandidate> candidates
    ) {
        for (int index = 0; index < candidates.size(); index++) {
            SuggestionCandidate candidate = candidates.get(index);
            if (!candidate.isLiteral()) {
                return candidate;
            }
        }
        throw new AssertionError("spatial benchmark result has no provider candidate");
    }

    private static long checksum(SuggestionSnapshot snapshot, long seed) {
        long value = seed * 31L + snapshot.status().ordinal();
        List<SuggestionCandidate> candidates = snapshot.nBestCandidates();
        for (int index = 0; index < candidates.size(); index++) {
            SuggestionCandidate candidate = candidates.get(index);
            value = value * 31L + candidate.text().hashCode();
            value = value * 31L + candidate.category().ordinal();
            value = value * 31L + candidate.providerId().hashCode();
            value = value * 31L + candidate.providerScore();
        }
        return value;
    }

    private static void awaitReady(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            String prefix
    ) {
        long timeout = SystemClock.elapsedRealtime() + PACK_READY_TIMEOUT_MILLIS;
        long generation = 900_000L;
        while (SystemClock.elapsedRealtime() < timeout) {
            PathCase exact = new PathCase(
                    "readiness",
                    prefix,
                    TouchSequence.empty(),
                    "unused",
                    SuggestionCandidate.Category.EXACT,
                    NkpSuggestionEngine.EXACT_PREFIX_PROVIDER
            );
            SuggestionQuery query = newQuery(
                    activation,
                    profile,
                    exact,
                    generation++
            );
            SuggestionSnapshot snapshot = engine.suggest(activation, query);
            if (snapshot.status() == SuggestionSnapshot.Status.LOADING) {
                SystemClock.sleep(25L);
                continue;
            }
            if (snapshot.status() != SuggestionSnapshot.Status.READY
                    || !snapshot.hasProviderCandidates()) {
                throw new AssertionError(
                        "staged provider failed readiness for " + profile.id()
                                + ": " + snapshot.status()
                );
            }
            return;
        }
        throw new AssertionError("staged provider readiness timed out: " + profile.id());
    }

    private static SuggestionQuery newQuery(
            SuggestionActivation activation,
            KeyboardProfile profile,
            PathCase path,
            long generation
    ) {
        return SuggestionQuery.functionalTestRequest(
                activation,
                profile,
                path.rawText,
                generation,
                path.touchSequence
        );
    }

    private static KeyboardProfile requireProfile(String profileId) {
        KeyboardProfile profile = LanguageRegistry.find(profileId);
        if (profile == null || !profile.isAvailable() || !profile.hasVersionedLayout()) {
            throw new AssertionError("required benchmark profile is unavailable: " + profileId);
        }
        return profile;
    }

    private static ReleasePackSpec requireSpec(List<ReleasePackSpec> specs, String profileId) {
        ReleasePackSpec match = null;
        for (ReleasePackSpec spec : specs) {
            if (profileId.equals(spec.profileId())) {
                if (match != null) {
                    throw new AssertionError("duplicate staged pack profile: " + profileId);
                }
                match = spec;
            }
        }
        if (match == null) {
            throw new AssertionError("staged pack profile is missing: " + profileId);
        }
        return match;
    }

    private static long javaHeapUsed() {
        Runtime runtime = Runtime.getRuntime();
        return runtime.totalMemory() - runtime.freeMemory();
    }

    private static long runtimeStat(String key) {
        String encoded = Debug.getRuntimeStat(key);
        if (encoded == null) {
            throw new AssertionError("ART runtime statistic is unavailable: " + key);
        }
        try {
            long value = Long.parseLong(encoded);
            if (value < 0L) {
                throw new NumberFormatException("negative");
            }
            return value;
        } catch (NumberFormatException invalid) {
            throw new AssertionError("ART runtime statistic is invalid: " + key + "=" + encoded);
        }
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

    private static long optionalPositiveLong(String value) {
        if (value == null) {
            return 0L;
        }
        try {
            long parsed = Long.parseLong(value);
            if (parsed <= 0L) {
                throw new NumberFormatException("not positive");
            }
            return parsed;
        } catch (NumberFormatException invalid) {
            throw new IllegalArgumentException("maxP95Ns must be a positive integer", invalid);
        }
    }

    private static File writeReport(Context context, Bundle values) throws Exception {
        JSONObject json = new JSONObject();
        for (String key : values.keySet()) {
            json.put(key, values.get(key));
        }
        File output = new File(context.getFilesDir(), "spatial-decoder-benchmark.json");
        try (FileWriter writer = new FileWriter(output, false)) {
            writer.write(json.toString(2));
            writer.write('\n');
        }
        return output;
    }

    private static final class PathCase {
        final String id;
        final String rawText;
        final TouchSequence touchSequence;
        final String expectedSurface;
        final SuggestionCandidate.Category expectedCategory;
        final String expectedProvider;

        PathCase(
                String id,
                String rawText,
                TouchSequence touchSequence,
                String expectedSurface,
                SuggestionCandidate.Category expectedCategory,
                String expectedProvider
        ) {
            this.id = id;
            this.rawText = rawText;
            this.touchSequence = touchSequence;
            this.expectedSurface = expectedSurface;
            this.expectedCategory = expectedCategory;
            this.expectedProvider = expectedProvider;
        }
    }

    private static final class TimedResult {
        final long meanNs;
        final long p50Ns;
        final long p95Ns;
        final long p99Ns;
        final long maxNs;
        final long checksum;
        final long allocatedBytes;
        final long allocatedBytesPerOp;
        final long gcCountDelta;
        final long javaHeapUsedBeforeBytes;
        final long javaHeapUsedAfterBytes;
        final long processPssBeforeKb;
        final long processPssAfterKb;

        TimedResult(
                long meanNs,
                long p50Ns,
                long p95Ns,
                long p99Ns,
                long maxNs,
                long checksum,
                long allocatedBytes,
                long allocatedBytesPerOp,
                long gcCountDelta,
                long javaHeapUsedBeforeBytes,
                long javaHeapUsedAfterBytes,
                long processPssBeforeKb,
                long processPssAfterKb
        ) {
            this.meanNs = meanNs;
            this.p50Ns = p50Ns;
            this.p95Ns = p95Ns;
            this.p99Ns = p99Ns;
            this.maxNs = maxNs;
            this.checksum = checksum;
            this.allocatedBytes = allocatedBytes;
            this.allocatedBytesPerOp = allocatedBytesPerOp;
            this.gcCountDelta = gcCountDelta;
            this.javaHeapUsedBeforeBytes = javaHeapUsedBeforeBytes;
            this.javaHeapUsedAfterBytes = javaHeapUsedAfterBytes;
            this.processPssBeforeKb = processPssBeforeKb;
            this.processPssAfterKb = processPssAfterKb;
        }

        static TimedResult calculate(
                long[] source,
                long checksum,
                long allocatedBytes,
                long gcCountDelta,
                long javaHeapUsedBeforeBytes,
                long javaHeapUsedAfterBytes,
                long processPssBeforeKb,
                long processPssAfterKb
        ) {
            long[] sorted = source.clone();
            Arrays.sort(sorted);
            long sum = 0L;
            for (long value : source) {
                sum += value;
            }
            return new TimedResult(
                    sum / source.length,
                    percentile(sorted, 50),
                    percentile(sorted, 95),
                    percentile(sorted, 99),
                    sorted[sorted.length - 1],
                    checksum,
                    allocatedBytes,
                    allocatedBytes / source.length,
                    gcCountDelta,
                    javaHeapUsedBeforeBytes,
                    javaHeapUsedAfterBytes,
                    processPssBeforeKb,
                    processPssAfterKb
            );
        }

        void writeTo(Bundle output, String prefix) {
            output.putLong(prefix + "_mean_ns", meanNs);
            output.putLong(prefix + "_p50_ns", p50Ns);
            output.putLong(prefix + "_p95_ns", p95Ns);
            output.putLong(prefix + "_p99_ns", p99Ns);
            output.putLong(prefix + "_max_ns", maxNs);
            output.putLong(prefix + "_checksum", checksum);
            output.putLong(prefix + "_allocated_bytes", allocatedBytes);
            output.putLong(prefix + "_allocated_bytes_per_op", allocatedBytesPerOp);
            output.putLong(prefix + "_gc_count_delta", gcCountDelta);
            output.putLong(prefix + "_java_heap_used_before_bytes", javaHeapUsedBeforeBytes);
            output.putLong(prefix + "_java_heap_used_after_bytes", javaHeapUsedAfterBytes);
            output.putLong(prefix + "_process_pss_before_kb", processPssBeforeKb);
            output.putLong(prefix + "_process_pss_after_kb", processPssAfterKb);
        }

        private static long percentile(long[] sorted, int percentile) {
            int index = (int) Math.ceil((percentile / 100.0) * sorted.length) - 1;
            return sorted[Math.max(0, Math.min(sorted.length - 1, index))];
        }
    }
}
