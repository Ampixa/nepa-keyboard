from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class AndroidDecoderContractSourceTest(unittest.TestCase):
    def test_request_is_generation_bound_cancellable_and_deadlined(self) -> None:
        query = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionQuery.java"
        )
        engine = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionEngine.java"
        )
        cancellation = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionCancellation.java"
        )

        for field in (
            "SuggestionActivation activation",
            "String profileId",
            "String layoutId",
            "int layoutRevision",
            "String layoutSourceSha256",
            "long generation",
            "long createdAtNanos",
            "long deadlineNanos",
            "SuggestionCancellation cancellation",
            "TouchSequence touchSequence",
        ):
            self.assertIn(field, query)
        self.assertIn("DEFAULT_DEADLINE_BUDGET_NANOS = 50_000_000L", query)
        self.assertIn("MAX_DEADLINE_BUDGET_NANOS = 250_000_000L", query)
        self.assertIn("MAX_COMPOSING_UTF16_UNITS = 256", query)
        self.assertIn("MAX_COMPOSING_CODE_POINTS = 64", query)
        self.assertIn("isWithinDecoderInputBound()", query)
        self.assertIn("activation == expectedActivation", query)
        self.assertIn("activation.ownsProfile(profile)", query)
        self.assertIn("private fields cannot create decoder requests", query)
        self.assertIn("nowNanos - deadlineNanos >= 0L", query)
        self.assertIn("!cancellation.isCancelled() && !isExpired(nowNanos)", query)
        self.assertIn("static SuggestionQuery functionalTestRequest(", query)
        self.assertIn("this.deadlineEnforced = deadlineEnforced", query)
        self.assertIn("functional test generation must be positive", query)
        self.assertIn("functional test composing text exceeds decoder bound", query)
        self.assertIn("no wall-clock deadline", query)
        self.assertIn("explicit two-argument engine API", query)
        self.assertIn(
            "default SuggestionSnapshot suggest(SuggestionQuery query)", engine
        )
        self.assertIn("bounded decoder request required", engine)
        self.assertIn(
            "query.privateField() || query.cancellation().isCancelled()", engine
        )
        self.assertIn("default void cancel(SuggestionQuery query)", engine)
        self.assertIn("AtomicBoolean", cancellation)
        self.assertIn("compareAndSet(false, true)", cancellation)

    def test_functional_query_callsites_are_decoder_contract_only(self) -> None:
        source_root = ROOT / "android/ime-app/src"
        callsites = {
            path.relative_to(ROOT).as_posix()
            for path in source_root.rglob("*.java")
            if "SuggestionQuery.functionalTestRequest(" in path.read_text(
                encoding="utf-8"
            )
        }
        self.assertEqual(
            {
                "android/ime-app/src/decoderContract/java/com/ampixa/"
                "nepakeyboard/ime/DecoderContractInstrumentation.java",
                "android/ime-app/src/decoderContract/java/com/ampixa/"
                "nepakeyboard/ime/SpatialDecoderBenchmarkInstrumentation.java",
                "android/ime-app/src/decoderContract/java/com/ampixa/"
                "nepakeyboard/ime/NcmConversionInstrumentation.java",
            },
            callsites,
        )

    def test_result_is_typed_bounded_and_preserves_one_literal(self) -> None:
        candidate = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionCandidate.java"
        )
        snapshot = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionSnapshot.java"
        )

        for category in (
            "LITERAL",
            "EXACT",
            "DICTIONARY",
            "TRANSLITERATION",
            "CORRECTION",
        ):
            self.assertIn(category, candidate)
        self.assertIn("No category authorizes automatic replacement", candidate)
        self.assertIn("Provider-local score", candidate)
        self.assertIn("MAX_CANDIDATES = 3", snapshot)
        self.assertIn("List<SuggestionCandidate> nBestCandidates", snapshot)
        self.assertIn("Collections.unmodifiableList", snapshot)
        self.assertIn("literalCount != 1", snapshot)
        self.assertIn("literal candidate must preserve input", snapshot)
        self.assertIn("typed candidate text must be unique", snapshot)
        self.assertIn("query == expected", snapshot)
        self.assertIn("isLiteralFallback()", snapshot)

    def test_composing_session_cancels_and_rejects_stale_or_expired_results(
        self,
    ) -> None:
        session = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "ComposingSession.java"
        )
        self.assertIn("private SuggestionQuery activeSuggestionQuery", session)
        self.assertIn("long generation = nextSuggestionGeneration()", session)
        self.assertIn("SuggestionQuery.decoderRequest(", session)
        self.assertIn("suggestionEngine.suggest(query)", session)
        self.assertIn("activeSuggestionQuery == query", session)
        self.assertIn("query.generation() == nextSuggestionGeneration", session)
        self.assertIn("query.cancellation().isCancelled()", session)
        self.assertIn("!snapshot.belongsTo(query)", session)
        self.assertIn("query.isExpired(nanoClock.getAsLong())", session)
        self.assertIn("SuggestionSnapshot.literalFallback(query)", session)
        self.assertIn("suggestionEngine.cancel(query)", session)
        self.assertIn("List<SpatialKeyStroke> composingStrokes", session)
        self.assertIn("currentTouchSequence(queryText)", session)
        self.assertIn(
            "TouchSequence.forToken(profile, queryText, composingStrokes)", session
        )

    def test_production_path_is_bounded_async_and_query_owned(self) -> None:
        engine = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionEngine.java"
        )
        nkp = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NkpSuggestionEngine.java"
        )
        service = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputMethodService.java"
        )
        view = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputView.java"
        )

        self.assertIn("SubmitOutcome submit(", engine)
        self.assertIn("new ArrayBlockingQueue<>(1)", nkp)
        self.assertIn('new Thread(runnable, "nepa-prefix-decoder")', nkp)
        self.assertIn("lastDecodeThread = Thread.currentThread()", nkp)
        self.assertIn("query.activation() == activeActivation", nkp)
        self.assertIn("decoder.execute(task)", nkp)
        self.assertIn("decoder.remove(task)", nkp)
        self.assertIn("cancelActiveLoadLocked()", nkp)
        self.assertIn("acquireBundleLease(key)", nkp)
        self.assertIn("releaseBundleLease(bundleLease)", nkp)
        self.assertIn("retireBundleLocked", nkp)
        self.assertIn("suggestionEngine.submit(", service)
        self.assertNotIn("composingSession.suggestionSnapshot()", service)
        self.assertIn("mainHandler.postDelayed", service)
        self.assertIn("query != dispatchedSuggestionQuery", service)
        self.assertIn("currentSuggestions.belongsTo(owner)", service)
        self.assertIn("SuggestionQuery owner", view)
        self.assertIn("SuggestionCandidate candidate", view)

    def test_nkp_exact_and_spatial_prefix_providers_reserve_literal(self) -> None:
        nkp = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NkpSuggestionEngine.java"
        )
        self.assertIn('EXACT_PREFIX_PROVIDER = "nkp-exact-prefix"', nkp)
        self.assertIn('SPATIAL_TAP_PROVIDER = "nkp-spatial-tap-v1"', nkp)
        self.assertIn(
            "MAX_PROVIDER_RESULTS = SuggestionSnapshot.MAX_CANDIDATES - 1",
            nkp,
        )
        self.assertIn("MAX_SPATIAL_ALTERNATIVES_PER_STROKE = 3", nkp)
        self.assertIn("MAX_SPATIAL_BEAMS = 16", nkp)
        self.assertIn("MAX_SPATIAL_IDS_PER_BEAM = 8", nkp)
        self.assertIn("SPATIAL_COST_QUANTUM = 1_024", nkp)
        self.assertIn("SPATIAL_LEXICAL_LOG2_STEP = 512", nkp)
        self.assertIn("normalizedLexicalScore", nkp)
        self.assertIn("beam.exactPath && beam.cost == 0", nkp)
        self.assertIn("!first.cleanExactPath", nkp)
        self.assertIn("spatialJointScore", nkp)
        self.assertIn("Long.compare(second.jointScore, first.jointScore)", nkp)
        self.assertIn("LanguageRegistry.ENGLISH_ID", nkp)
        self.assertIn("LanguageRegistry.NEPALI_DIRECT_ID", nkp)
        self.assertIn("query.touchSequence().hasSpatialEvidence()", nkp)
        self.assertIn("bundle.lookupSurfaceIds(beam.text)", nkp)
        self.assertIn("buildSpatialBeams", nkp)
        self.assertIn("completeCleanExactProviderResults", nkp)
        self.assertIn("isCleanExactTouch", nkp)
        self.assertIn("!stroke.hasSpatialEvidence()", nkp)
        self.assertIn("stroke.alternatives(1).get(0)", nkp)
        self.assertIn("selected.spatialCost() != 0", nkp)
        self.assertIn("publishable.size() < MAX_PROVIDER_RESULTS", nkp)
        self.assertIn("List<SpatialKeyStroke.Alternative> strokeAlternatives", nkp)
        self.assertIn("for (SpatialKeyStroke.Alternative alternative : strokeAlternatives)", nkp)
        self.assertIn("SuggestionCandidate.Category.EXACT", nkp)
        self.assertIn("SuggestionCandidate.Category.TRANSLITERATION", nkp)
        self.assertIn("SuggestionCandidate.Category.CORRECTION", nkp)
        self.assertIn("providerRankScore = MAX_PROVIDER_RESULTS - result.size()", nkp)
        self.assertIn("SuggestionCandidate.literal(query.composingText())", nkp)
        self.assertIn("SuggestionSnapshot.decoded(activation, query, result)", nkp)

    def test_touch_evidence_is_versioned_bounded_and_never_fabricated(self) -> None:
        geometry = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "KeyboardGeometry.java"
        )
        stroke = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SpatialKeyStroke.java"
        )
        sequence = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "TouchSequence.java"
        )
        surface = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "KeyboardSurface.java"
        )

        self.assertIn("COORDINATE_SCALE = 1_000_000", geometry)
        self.assertIn("MAX_TEXT_KEYS = 64", geometry)
        self.assertIn("nearestKeys", geometry)
        self.assertIn("Collections.unmodifiableList", geometry)
        self.assertIn("public static SpatialKeyStroke spatial(", stroke)
        self.assertIn("public static SpatialKeyStroke nonSpatial(", stroke)
        self.assertIn("non-spatial stroke cannot carry coordinates", stroke)
        self.assertIn("stroke and geometry input policy mismatch", stroke)
        self.assertIn("public boolean hasSpatialEvidence()", stroke)
        self.assertIn("touch sequence exceeds decoder bound", sequence)
        self.assertIn("touch sequence is not aligned with composing text", sequence)
        self.assertIn('@SuppressLint("ClickableViewAccessibility")', surface)
        self.assertIn("return false;", surface)
        self.assertIn("nonSpatialStroke(layout, renderGeneration, key)", surface)
        self.assertIn("performTextKeyTouchForTesting", surface)
        self.assertIn("performTextKeyDriftForTesting", surface)
        self.assertIn("float downHorizontalFraction", surface)
        self.assertIn("float upHorizontalFraction", surface)
        self.assertIn("MotionEvent.ACTION_DOWN", surface)
        self.assertIn("MotionEvent.ACTION_UP", surface)
        self.assertIn("selectedLeft + (double) event.getX()", surface)
        self.assertIn("selectedTop + (double) event.getY()", surface)
        self.assertNotIn("selectedLeft + Math.round(event.getX())", surface)
        self.assertNotIn("selectedTop + Math.round(event.getY())", surface)

    def test_spatial_benchmark_times_the_exact_production_decoder(self) -> None:
        benchmark = source(
            "android/ime-app/src/decoderContract/java/com/ampixa/nepakeyboard/ime/"
            "SpatialDecoderBenchmarkInstrumentation.java"
        )
        vectors = source(
            "android/ime-app/src/decoderContract/java/com/ampixa/nepakeyboard/ime/"
            "SpatialDecoderVectors.java"
        )
        contract = source(
            "android/ime-app/src/decoderContract/java/com/ampixa/nepakeyboard/ime/"
            "DecoderContractInstrumentation.java"
        )

        for marker in (
            'BENCHMARK_MODE = "spatial_decoder_v1"',
            "SpatialDecoderVectors.captureEnglish(this, context, english)",
            "SpatialDecoderVectors.captureNepali(this, context, nepali)",
            "SuggestionEngineFactory.createForDecoderTest(",
            "SuggestionQuery.functionalTestRequest(",
            "engine.suggest(activation, query)",
            "query.isBoundedDecoderRequest()",
            "query.acceptsProviderResults(acceptedAtNanos)",
            "NkpSuggestionEngine.spatialBeamCountForTesting(",
            'runtimeStat("art.gc.bytes-allocated")',
            'runtimeStat("art.gc.gc-count")',
            "Debug.getPss()",
            'new File(context.getFilesDir(), "spatial-decoder-benchmark.json")',
            'output.putString("english_exact_verified", "true")',
            'output.putString("english_clean_center_parity_verified", "true")',
            'output.putString("english_boundary_correction_verified", "true")',
            'output.putString("nepali_exact_verified", "true")',
            'output.putString("nepali_clean_center_parity_verified", "true")',
            'output.putString("nepali_boundary_correction_verified", "true")',
            'output.putString("spatial_literal_preservation_verified", "true")',
            'output.putString("spatial_beam_bound_verified", "true")',
            'output.putString("spatial_clean_exact_fast_path_verified", "true")',
            'output.putLong("pack_ready_timeout_ms", PACK_READY_TIMEOUT_MILLIS)',
            'output.putBoolean("functional_query_deadline_enforced", false)',
            '"deadline_outcome_coverage"',
            '"DecoderContractInstrumentation"',
            'label + "_clean_exact_fast_path_eligible"',
            'label + "_boundary_full_path_verified"',
        ):
            self.assertIn(marker, benchmark)
        self.assertNotIn("NkpBundle", benchmark)
        self.assertNotIn("lookupSurfaceIds", benchmark)
        self.assertIn("performTextKeyDriftForTesting", vectors)
        self.assertIn('0.5f, -0.15f', vectors)
        self.assertIn("compiled center tap has nonzero spatial cost", vectors)
        self.assertIn("compiled boundary tap has no spatial displacement", vectors)
        self.assertIn("compiled drift target is not strictly closer", vectors)
        self.assertIn("closerCost >= selectedCost", vectors)
        self.assertIn(
            "expectedTextKeyIds.equals(stroke.geometryKeyIdsForTesting())", vectors
        )
        self.assertIn('"jell"', vectors)
        self.assertIn('"hello"', vectors)
        self.assertIn('"ममस्"', vectors)
        self.assertIn('"नमस्कार"', vectors)
        self.assertIn("SpatialDecoderVectors.captureEnglish", contract)
        self.assertIn("SpatialDecoderVectors.captureNepali", contract)
        self.assertIn("SuggestionQuery.functionalTestRequest", contract)
        self.assertIn("!query.isBoundedDecoderRequest()", contract)
        self.assertIn("requireFunctionalProviderSnapshot", contract)
        self.assertNotIn("FUNCTIONAL_PROVIDER_ATTEMPTS", contract)
        self.assertNotIn("provider-free result is literal fallback", contract)
        self.assertNotIn("in-deadline attempts", contract)
        self.assertIn("functional result has provider candidates", contract)
        self.assertIn("PACK_READY_TIMEOUT_MILLIS = 300_000L", contract)
        self.assertIn("PACK_READY_TIMEOUT_MILLIS = 300_000L", benchmark)
        self.assertIn("snapshot.hasProviderCandidates()", contract)
        self.assertIn("center matrix retains provider-covered rows", contract)
        self.assertIn("center matrix retains exact/spatial parity-covered rows", contract)
        self.assertNotIn("center tap must finish inside provider deadline", contract)
        self.assertIn("center tap correction remains below exact top", contract)
        self.assertIn("center tap exact results precede corrections", contract)
        self.assertIn("verifyMixedTouchAvoidsCleanExactFastPath", contract)
        self.assertIn("isCleanExactTouchForTesting", contract)
        self.assertIn("spatial literal remains last", contract)

    def test_remote_platform_acceptance_is_registered_and_documented(self) -> None:
        manifest = source("android/ime-app/src/debug/AndroidManifest.xml")
        internal_manifest = source("android/ime-app/src/internal/AndroidManifest.xml")
        build = source("android/ime-app/build.gradle.kts")
        runner = source("tools/run_cdjk_internal_catalog_validation.sh")
        instrumentation = source(
            "android/ime-app/src/decoderContract/java/com/ampixa/nepakeyboard/ime/"
            "DecoderContractInstrumentation.java"
        )
        documentation = source("docs/android-decoder-contract-v1.md")

        self.assertIn('.DecoderContractInstrumentation"', manifest)
        self.assertIn('.SpatialDecoderBenchmarkInstrumentation"', manifest)
        self.assertIn("src/decoderContract/java", build)
        self.assertIn("DecoderContractInstrumentation", internal_manifest)
        self.assertIn("SpatialDecoderBenchmarkInstrumentation", internal_manifest)
        for marker in (
            "verifyImmutableTypedSnapshot",
            "verifyPrivateFieldRejectedBeforeProvider",
            "verifyExactProfileObjectBinding",
            "verifyGenerationCancellationAndStaleRejection",
            "verifyCancelledAndExpiredResultRejection",
            "verifyNkpExactPrefixProvider",
            "verifySpatialTouchProvenance",
            "verifySpatialNkpProvider",
            "verifySpatialProfile",
            "verifyCenterTapMatrix",
            "verifyAsyncSpatialSession",
            "verifyAsyncNkpSubmission",
            "verifyLatestWinsAsyncQueue",
            "SuggestionEngineFactory.createForDecoderTest(",
            "BlockingDecodeObserver",
            '"decoder_contract_verified", "true"',
            '"literal_candidate_verified", "true"',
            '"stale_result_rejection_verified", "true"',
            '"expired_result_fallback_verified", "true"',
            '"nkp_exact_prefix_provider_verified", "true"',
            '"functional_query_api_isolation_verified", "true"',
            '"async_decoder_off_main_verified", "true"',
            '"async_decoder_controlled_release_verified", "true"',
            '"async_decoder_deadline_outcome_verified", "true"',
            '"private_field_provider_isolation_verified", "true"',
            '"candidate_query_binding_verified", "true"',
            '"nkp_ordinal_provider_score_verified", "true"',
            '"profile_object_identity_verified", "true"',
            '"async_decoder_latest_wins_verified", "true"',
            '"spatial_touch_provenance_verified", "true"',
            '"spatial_english_prefix_verified", "true"',
            '"spatial_nepali_prefix_verified", "true"',
            '"spatial_bounded_beam_verified", "true"',
            '"spatial_clean_exact_fast_path_verified", "true"',
            '"instrumentation_pack_ready_timeout_ms"',
            '"status", "ok"',
            '"status", "error"',
        ):
            self.assertIn(marker, instrumentation)
        self.assertIn(
            "blocked provider cannot complete before controlled release",
            instrumentation,
        )
        self.assertIn("async provider callback follows controlled release", instrumentation)
        self.assertIn("late async result is expired", instrumentation)
        self.assertIn("late async result is literal-only", instrumentation)
        self.assertIn("late async result excludes provider candidates", instrumentation)
        self.assertIn("real spatial late result is literal fallback", instrumentation)
        self.assertIn("real spatial late result excludes provider candidates", instrumentation)
        self.assertIn("real spatial late result follows deadline expiry", instrumentation)
        self.assertNotIn("async provider completes before deadline", instrumentation)
        exact_provider = instrumentation.split(
            "private void verifyNkpExactPrefixProvider", 1
        )[1].split("private static void verifyFunctionalQueryApiIsolation", 1)[0]
        self.assertIn("SuggestionQuery.functionalTestRequest", exact_provider)
        self.assertIn("engine.suggest(activation, query)", exact_provider)
        self.assertNotIn("SuggestionQuery.decoderRequest", exact_provider)
        readiness = instrumentation.split(
            "private static void awaitReadyProvider", 1
        )[1].split("private static SuggestionQuery newBoundedQuery", 1)[0]
        self.assertIn("SuggestionQuery.functionalTestRequest", readiness)
        self.assertIn("engine.suggest(activation, query)", readiness)
        self.assertNotIn("newBoundedQuery", readiness)
        self.assertIn("verifyFunctionalQueryApiIsolation", instrumentation)
        self.assertIn(
            "functional query cannot enter one-argument production decoder API",
            instrumentation,
        )
        self.assertIn("expired latest callback is literal-only fallback", instrumentation)
        self.assertIn(
            "provider-free latest callback follows deadline expiry",
            instrumentation,
        )
        for marker in (
            "internal-decoder-contract.txt",
            "DecoderContractInstrumentation",
            "decoder_contract_verified=true",
            "literal_candidate_verified=true",
            "stale_result_rejection_verified=true",
            "expired_result_fallback_verified=true",
            "nkp_exact_prefix_provider_verified=true",
            "functional_query_api_isolation_verified=true",
            "async_decoder_off_main_verified=true",
            "async_decoder_controlled_release_verified=true",
            "async_decoder_deadline_outcome_verified=true",
            "async_spatial_deadline_outcome_verified=true",
            "private_field_provider_isolation_verified=true",
            "candidate_query_binding_verified=true",
            "nkp_ordinal_provider_score_verified=true",
            "profile_object_identity_verified=true",
            "async_decoder_latest_wins_verified=true",
            "spatial_touch_provenance_verified=true",
            "spatial_functional_provider_verified=true",
            "spatial_deadline_outcome_separated_verified=true",
            "spatial_english_prefix_verified=true",
            "spatial_nepali_prefix_verified=true",
            "spatial_bounded_beam_verified=true",
            "spatial_clean_exact_fast_path_verified=true",
            "instrumentation_pack_ready_timeout_ms=300000",
            "decoder-contract-run-profile.txt",
            "decoder_contract_timeout_seconds=1800",
            "serial_pack_ready_phase_count=4",
            "internal-spatial-decoder-benchmark.txt",
            "spatial-benchmark-run-profile.txt",
            "SpatialDecoderBenchmarkInstrumentation",
            "benchmark_mode=spatial_decoder_v1",
            "pack_ready_timeout_ms=300000",
            "spatial_benchmark_profile=canonical_tcg_v1",
            "spatial_benchmark_iterations=1000",
            "spatial_benchmark_warmups=100",
            'reference_physical_iterations_per_metric=10000',
            'reference_physical_warmups_per_metric=1000',
            "functional_query_deadline_enforced=false",
            "deadline_outcome_coverage=DecoderContractInstrumentation",
            "english_exact_verified=true",
            "english_clean_center_parity_verified=true",
            "english_boundary_correction_verified=true",
            "nepali_exact_verified=true",
            "nepali_clean_center_parity_verified=true",
            "nepali_boundary_correction_verified=true",
            "spatial_literal_preservation_verified=true",
            "spatial_beam_bound_verified=true",
            "internal-apk-source-inputs-sha256.txt",
            "internal-apk-stale-inputs.txt",
            "benchmark-apk-source-inputs-sha256.txt",
            "benchmark-apk-stale-inputs.txt",
        ):
            self.assertIn(marker, runner)
        self.assertIn(
            'timeout "$decoder_contract_timeout_seconds" \\\n'
            '  "$adb" -s emulator-5556 shell am instrument -w -r \\\n'
            "  com.ampixa.nepakeyboard.ime.internal/\\\n"
            "com.ampixa.nepakeyboard.ime.DecoderContractInstrumentation",
            runner,
        )
        self.assertIn("source and canonical API 34 cdjk emulator evidence passed", documentation)
        self.assertIn(
            "python3 -m unittest tests.test_android_decoder_contract", documentation
        )
        self.assertIn("DecoderContractInstrumentation", documentation)
        self.assertIn("no automatic correction", documentation)
        self.assertIn("Spatial Tap Decoder v1", documentation)

    def test_backspace_v1_is_bounded_private_and_generation_owned(self) -> None:
        grapheme = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "GraphemeBackspace.java"
        )
        sink = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "InputConnectionTextSink.java"
        )
        session = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "ComposingSession.java"
        )
        repeat = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "DeleteRepeatController.java"
        )
        surface = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "KeyboardSurface.java"
        )
        service = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputMethodService.java"
        )
        query = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionQuery.java"
        )
        vectors = source(
            "android/ime-app/src/decoderContract/java/com/ampixa/nepakeyboard/ime/"
            "BackspaceContractVectors.java"
        )
        decoder = source(
            "android/ime-app/src/decoderContract/java/com/ampixa/nepakeyboard/ime/"
            "DecoderContractInstrumentation.java"
        )
        runner = source("tools/run_cdjk_internal_catalog_validation.sh")

        self.assertIn("COMMITTED_CONTEXT_UTF16_LIMIT = 64", grapheme)
        self.assertIn("BreakIterator.getCharacterInstance", grapheme)
        self.assertIn("hasCompleteTrailingGrapheme", grapheme)
        self.assertIn("allowCommittedDeleteContext", sink)
        self.assertIn("getTextBeforeCursor(", sink)
        self.assertIn("deleteSurroundingText(deleteUtf16Units, 0)", sink)
        self.assertIn("return deleteOneCodePoint()", sink)
        self.assertIn('connection.commitText("", 1)', sink)
        self.assertIn("selectionStart", sink)
        self.assertIn("selectionEnd", sink)
        self.assertIn("invalidateSelection();", sink)
        self.assertIn("GraphemeBackspace.previousBoundary(composingText)", session)
        self.assertIn("composingStrokes.subList", session)
        self.assertGreaterEqual(session.count("rebuildDevanagariTail(updated)"), 2)
        self.assertIn("editorSelectionStart", service)
        self.assertIn("editorSelectionEnd", service)
        self.assertIn("private InputConnectionTextSink textSink", service)
        sink_snapshot = service.index("TextSink sink = textSink(connection);")
        selection_consumed = service.index(
            "invalidateEditorSelection();", sink_snapshot
        )
        delete_dispatched = service.index(
            "composingSession.delete(sink);", selection_consumed
        )
        self.assertLess(sink_snapshot, selection_consumed)
        self.assertLess(selection_consumed, delete_dispatched)
        self.assertIn("if (!inputViewActive || connection == null", service)
        self.assertIn("public void onStartInput(EditorInfo attribute, boolean restarting)", service)
        start_input = service.index(
            "public void onStartInput(EditorInfo attribute, boolean restarting)"
        )
        start_input_cancel = service.index("cancelDeleteRepeat();", start_input)
        start_input_super = service.index(
            "super.onStartInput(attribute, restarting);", start_input
        )
        start_input_view = service.index("public void onStartInputView", start_input)
        self.assertLess(start_input, start_input_cancel)
        self.assertLess(start_input_cancel, start_input_super)
        self.assertLess(start_input_super, start_input_view)
        self.assertIn("public void onWindowHidden()", service)
        self.assertGreaterEqual(service.count("cancelDeleteRepeat();"), 6)
        self.assertNotIn("getTextBeforeCursor", query)
        self.assertNotIn("if (before == ZERO_WIDTH_JOINER)", grapheme)

        self.assertIn("INITIAL_DELAY_MILLIS = 400L", repeat)
        self.assertIn("REPEAT_INTERVAL_MILLIS = 60L", repeat)
        self.assertIn("MAX_DISPATCHES_PER_HOLD = 256", repeat)
        self.assertIn("generation != owner", repeat)
        self.assertIn("totalDispatchCount", repeat)
        self.assertIn("totalDispatchCount++", repeat)
        self.assertIn("deleteRepeatController.stop()", surface)
        self.assertIn("protected void onDetachedFromWindow()", surface)
        self.assertIn("MotionEvent.ACTION_CANCEL", surface)
        self.assertIn("MotionEvent.ACTION_POINTER_UP", surface)
        self.assertIn("activeDeletePointerId", surface)
        self.assertIn("testingDeleteDownTime", surface)
        self.assertIn("remainingPointerUp", surface)
        self.assertIn("keyView.setOnClickListener", surface)

        for vector in (
            "e\\u0301",
            "कि",
            "क्\\u200dष",
            "𑰀",
            "👨\\u200d👩\\u200d👧\\u200d👦",
            "👍🏽",
            "🇳🇵",
            "\\r\\n",
            "a\\u200db",
            "👨\\u200da",
            "a\\u200d👩",
            "leading virama does not gain Devanagari conjunct tailoring",
            "truncated cluster context falls back",
            "short editor context falls back",
            "selected text is deleted before surrounding text",
            "private delete never reads context",
            "partial delete rebuilds Devanagari joiner ownership",
            "commit fallback rebuilds Devanagari joiner ownership",
            "Newa joiner continuation preserves base and virama",
            "manual Newa continuation deletes one consonant tap",
            "committed marked Newa fallback preserves base and virama",
            "marked Newa continuation does not orphan its joiner",
            "Newa window without virama remains incomplete",
            "clipped Newa committed delete succeeds",
            "private Newa input drops an undeletable joiner",
            "non-consonant Newa continuation drops the joiner",
            "stale selection is not replaced twice",
            "stale stopped generation cannot delete",
            "rerender cancels held delete",
            "owner pointer-up stops held delete",
            "non-owner pointer-up preserves held delete",
            "service-facing cancellation stops held delete",
            "detach stops held delete",
        ):
            self.assertIn(vector, vectors)
        self.assertNotIn(".repeat(", vectors)

        for marker in (
            "backspace_grapheme_vectors_verified=true",
            "backspace_owned_composition_verified=true",
            "backspace_committed_context_verified=true",
            "backspace_fallback_verified=true",
            "backspace_sink_private_no_read_verified=true",
            "backspace_suggestion_touch_ownership_verified=true",
            "backspace_zwj_tailoring_verified=true",
            "newa_conjunct_joiner_verified=true",
            "backspace_devanagari_state_rebuild_verified=true",
            "backspace_selection_contract_verified=true",
            "backspace_context_completeness_verified=true",
            "delete_repeat_timing_verified=true",
            "delete_touch_pointer_ownership_verified=true",
            "delete_repeat_view_cancellation_verified=true",
        ):
            self.assertIn(marker, runner)
            self.assertIn(marker.replace("=true", '", "true"'), decoder)


if __name__ == "__main__":
    unittest.main()
