package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/** Shared debug/internal platform acceptance for the cancellable typed decoder contract. */
public final class DecoderContractInstrumentation extends Instrumentation {
    private static final long TEST_DEADLINE_BUDGET_NANOS = 1_000L;
    private static final long PACK_READY_TIMEOUT_MILLIS = 300_000L;

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
            KeyboardProfile english = requireProfile(LanguageRegistry.ENGLISH_ID);
            KeyboardProfile nepali = requireProfile(LanguageRegistry.NEPALI_DIRECT_ID);
            BackspaceContractVectors.verify(this, context, english, nepali);
            verifyImmutableTypedSnapshot(english);
            verifyPrivateFieldRejectedBeforeProvider(english);
            verifyExactProfileObjectBinding(english);
            verifyGenerationCancellationAndStaleRejection(english);
            verifyCancelledAndExpiredResultRejection(english);
            SpatialKeyStroke capturedEnglishStroke = verifySpatialTouchProvenance(
                    context,
                    english
            );
            verifyNkpExactPrefixProvider(context, english, capturedEnglishStroke);
            verifySpatialNkpProvider(context, english, nepali);
            verifyLatestWinsAsyncQueue(context, english);
            result.putString("decoder_contract_verified", "true");
            result.putString("literal_candidate_verified", "true");
            result.putString("stale_result_rejection_verified", "true");
            result.putString("expired_result_fallback_verified", "true");
            result.putString("nkp_exact_prefix_provider_verified", "true");
            result.putString("functional_query_api_isolation_verified", "true");
            result.putString("async_decoder_off_main_verified", "true");
            result.putString("async_decoder_controlled_release_verified", "true");
            result.putString("async_decoder_deadline_outcome_verified", "true");
            result.putString("async_spatial_deadline_outcome_verified", "true");
            result.putString("private_field_provider_isolation_verified", "true");
            result.putString("candidate_query_binding_verified", "true");
            result.putString("nkp_ordinal_provider_score_verified", "true");
            result.putString("profile_object_identity_verified", "true");
            result.putString("async_decoder_latest_wins_verified", "true");
            result.putString("spatial_touch_provenance_verified", "true");
            result.putString("spatial_functional_provider_verified", "true");
            result.putString("spatial_deadline_outcome_separated_verified", "true");
            result.putString("spatial_english_prefix_verified", "true");
            result.putString("spatial_nepali_prefix_verified", "true");
            result.putString("spatial_bounded_beam_verified", "true");
            result.putString("spatial_clean_exact_fast_path_verified", "true");
            result.putLong(
                    "instrumentation_pack_ready_timeout_ms",
                    PACK_READY_TIMEOUT_MILLIS
            );
            result.putString("backspace_grapheme_vectors_verified", "true");
            result.putString("backspace_owned_composition_verified", "true");
            result.putString("backspace_committed_context_verified", "true");
            result.putString("backspace_fallback_verified", "true");
            result.putString("backspace_sink_private_no_read_verified", "true");
            result.putString("backspace_suggestion_touch_ownership_verified", "true");
            result.putString("backspace_zwj_tailoring_verified", "true");
            result.putString("newa_conjunct_joiner_verified", "true");
            result.putString("backspace_devanagari_state_rebuild_verified", "true");
            result.putString("backspace_selection_contract_verified", "true");
            result.putString("backspace_context_completeness_verified", "true");
            result.putString("delete_repeat_timing_verified", "true");
            result.putString("delete_touch_pointer_ownership_verified", "true");
            result.putString("delete_repeat_view_cancellation_verified", "true");
            result.putString("status", "ok");
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            result.putString("status", "error");
            result.putString("failure", failure.toString());
            result.putString("stack", android.util.Log.getStackTraceString(failure));
        }
        finish(resultCode, result);
    }

    private static void verifyImmutableTypedSnapshot(KeyboardProfile profile) {
        ContractEngine engine = new ContractEngine(new AtomicLong(10_000L));
        SuggestionActivation activation = engine.activate(profile);
        SuggestionCancellation cancellation = new SuggestionCancellation();
        SuggestionQuery query = SuggestionQuery.decoderRequest(
                activation,
                profile,
                "h",
                false,
                7L,
                10_000L,
                11_000L,
                cancellation
        );
        SuggestionSnapshot snapshot = engine.suggest(query);

        assertSame("request activation snapshot", activation, query.activation());
        assertEquals("request profile snapshot", profile.id(), query.profileId());
        assertEquals("request layout snapshot", profile.layoutId(), query.layoutId());
        assertEquals("request generation snapshot", 7L, query.generation());
        assertEquals("request creation snapshot", 10_000L, query.createdAtNanos());
        assertEquals("request deadline snapshot", 11_000L, query.deadlineNanos());
        assertTrue("request result identity", snapshot.belongsTo(query));
        assertEquals("bounded N-best size", 2, snapshot.nBestCandidates().size());
        assertEquals(
                "exact provider category",
                SuggestionCandidate.Category.EXACT,
                snapshot.nBestCandidates().get(0).category()
        );
        assertEquals(
                "exact provider identity",
                ContractEngine.PROVIDER_ID,
                snapshot.nBestCandidates().get(0).providerId()
        );
        assertEquals("provider-local score", 100, snapshot.nBestCandidates().get(0).providerScore());
        SuggestionCandidate literal = snapshot.nBestCandidates().get(1);
        assertEquals("literal text is exact input", "h", literal.text());
        assertEquals("literal category", SuggestionCandidate.Category.LITERAL, literal.category());
        assertTrue("explicit literal marker", snapshot.hasExplicitLiteral());
        assertEquals("legacy text projection first result", "hello", snapshot.candidates().get(0));
        assertEquals("legacy text projection literal", "h", snapshot.candidates().get(1));

        boolean immutable = false;
        try {
            snapshot.nBestCandidates().add(SuggestionCandidate.literal("changed"));
        } catch (UnsupportedOperationException expected) {
            immutable = true;
        }
        assertTrue("typed result list is immutable", immutable);
        assertTrue("request starts uncancelled", !query.cancellation().isCancelled());

        boolean oversizedDeadlineRejected = false;
        try {
            SuggestionQuery.decoderRequest(
                    activation,
                    profile,
                    "h",
                    false,
                    8L,
                    10_000L,
                    10_000L + SuggestionQuery.MAX_DEADLINE_BUDGET_NANOS + 1L,
                    new SuggestionCancellation()
            );
        } catch (IllegalArgumentException expected) {
            oversizedDeadlineRejected = true;
        }
        assertTrue("oversized decoder deadline is rejected", oversizedDeadlineRejected);

        boolean missingLiteralRejected = false;
        try {
            SuggestionSnapshot.decoded(
                    activation,
                    query,
                    Collections.singletonList(SuggestionCandidate.provider(
                            "hello",
                            SuggestionCandidate.Category.EXACT,
                            ContractEngine.PROVIDER_ID,
                            100
                    ))
            );
        } catch (IllegalArgumentException expected) {
            missingLiteralRejected = true;
        }
        assertTrue("typed result without literal is rejected", missingLiteralRejected);

        engine.cancel(query);
        assertTrue("engine cancellation reaches request token", query.cancellation().isCancelled());
        engine.close();
    }

    private static void verifyPrivateFieldRejectedBeforeProvider(
            KeyboardProfile profile
    ) {
        ContractEngine engine = new ContractEngine(new AtomicLong(System.nanoTime()));
        SuggestionActivation activation = engine.activate(profile);
        long createdAtNanos = System.nanoTime();
        boolean rejected = false;
        try {
            SuggestionQuery.decoderRequest(
                    activation,
                    profile,
                    "secret",
                    true,
                    1L,
                    createdAtNanos,
                    createdAtNanos + SuggestionQuery.MAX_DEADLINE_BUDGET_NANOS,
                    new SuggestionCancellation()
            );
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        assertTrue("private field cannot create bounded request", rejected);
        assertEquals("private request never reaches provider", 0, engine.providerCallCount);
        engine.close();
    }

    private static void verifyExactProfileObjectBinding(KeyboardProfile profile) {
        ContractEngine engine = new ContractEngine(new AtomicLong(System.nanoTime()));
        SuggestionActivation activation = engine.activate(profile);
        KeyboardProfile forged = new KeyboardProfile(
                profile.id(),
                profile.languageId(),
                profile.inputMethodId(),
                profile.localeTag(),
                profile.displayName(),
                profile.nativeName(),
                profile.sourceScript(),
                profile.outputScript(),
                profile.detail(),
                profile.methodType(),
                profile.engineKind(),
                profile.layoutId(),
                profile.layoutRevision(),
                profile.layoutSourceSha256(),
                profile.lookupKind(),
                profile.packBinding(),
                profile.catalogReadiness(),
                profile.availability(),
                profile.blockedReason(),
                profile.blockedDetail(),
                profile.defaultEnabled(),
                profile.scope(),
                profile.group(),
                profile.variety(),
                profile.sortKey(),
                profile.searchAliases(),
                profile.evidenceIds()
        );
        boolean rejected = false;
        long createdAtNanos = System.nanoTime();
        try {
            SuggestionQuery.decoderRequest(
                    activation,
                    forged,
                    "h",
                    false,
                    1L,
                    createdAtNanos,
                    createdAtNanos + SuggestionQuery.MAX_DEADLINE_BUDGET_NANOS,
                    new SuggestionCancellation()
            );
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        assertTrue("equal-ID forged profile is rejected by identity", rejected);
        assertEquals("forged profile never reaches provider", 0, engine.providerCallCount);
        engine.close();
    }

    private static void verifyGenerationCancellationAndStaleRejection(
            KeyboardProfile profile
    ) {
        AtomicLong clock = new AtomicLong(20_000L);
        ContractEngine engine = new ContractEngine(clock);
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(
                engine,
                clock::get,
                TEST_DEADLINE_BUDGET_NANOS
        );
        session.start(profile, true, false, sink);
        session.appendText("h", sink);
        SuggestionSnapshot first = session.suggestionSnapshot();
        SuggestionQuery firstQuery = session.activeSuggestionQueryForTesting();
        assertEquals("first request is ready", SuggestionSnapshot.Status.READY, first.status());
        assertEquals("first request generation", 1L, firstQuery.generation());

        session.appendText("e", sink);
        assertTrue("typing cancels prior generation", firstQuery.cancellation().isCancelled());
        assertTrue(
                "stale candidate owner cannot commit",
                !session.selectCandidate(
                        firstQuery,
                        first.nBestCandidates().get(0),
                        sink
                )
        );
        assertEquals("stale candidate leaves editor unchanged", "he", sink.text);
        engine.mode = ContractEngine.Mode.RETURN_PREVIOUS;
        SuggestionSnapshot stale = session.suggestionSnapshot();
        SuggestionQuery secondQuery = engine.lastQuery;
        assertEquals("second request generation", 2L, secondQuery.generation());
        assertEquals(
                "old generation result leaves current literal ready",
                SuggestionSnapshot.Status.READY,
                stale.status()
        );
        assertTrue("stale result preserves only current literal", stale.isLiteralFallback());
        assertEquals("stale fallback owns current token", "he", stale.candidates().get(0));
        engine.close();
    }

    private static void verifyCancelledAndExpiredResultRejection(
            KeyboardProfile profile
    ) {
        AtomicLong cancelledClock = new AtomicLong(30_000L);
        ContractEngine cancelledEngine = new ContractEngine(cancelledClock);
        cancelledEngine.mode = ContractEngine.Mode.CANCEL_CURRENT;
        RecordingTextSink cancelledSink = new RecordingTextSink();
        ComposingSession cancelledSession = new ComposingSession(
                cancelledEngine,
                cancelledClock::get,
                TEST_DEADLINE_BUDGET_NANOS
        );
        cancelledSession.start(profile, true, false, cancelledSink);
        cancelledSession.appendText("h", cancelledSink);
        SuggestionSnapshot cancelled = cancelledSession.suggestionSnapshot();
        assertEquals(
                "cancelled current result leaves literal ready",
                SuggestionSnapshot.Status.READY,
                cancelled.status()
        );
        assertTrue("cancelled current result is literal-only", cancelled.isLiteralFallback());
        cancelledEngine.close();

        AtomicLong expiredClock = new AtomicLong(40_000L);
        ContractEngine expiredEngine = new ContractEngine(expiredClock);
        expiredEngine.mode = ContractEngine.Mode.EXPIRE_CURRENT;
        RecordingTextSink expiredSink = new RecordingTextSink();
        ComposingSession expiredSession = new ComposingSession(
                expiredEngine,
                expiredClock::get,
                TEST_DEADLINE_BUDGET_NANOS
        );
        expiredSession.start(profile, true, false, expiredSink);
        expiredSession.appendText("h", expiredSink);
        SuggestionSnapshot expired = expiredSession.suggestionSnapshot();
        assertEquals("expired provider result falls back", SuggestionSnapshot.Status.READY, expired.status());
        assertTrue("expired result is literal-only", expired.isLiteralFallback());
        assertEquals("expired fallback preserves exact input", "h", expired.candidates().get(0));
        assertEquals(
                "expired fallback has literal category",
                SuggestionCandidate.Category.LITERAL,
                expired.nBestCandidates().get(0).category()
        );
        assertEquals("expired fallback does not change editor text", "h", expiredSink.text);
        expiredEngine.close();
    }

    private void verifyNkpExactPrefixProvider(
            Context context,
            KeyboardProfile profile,
            SpatialKeyStroke capturedStroke
    ) throws InterruptedException {
        List<ReleasePackSpec> specs = ReleasePackRegistry.installed(context);
        assertTrue("focused decoder acceptance requires staged packs", !specs.isEmpty());
        BlockingDecodeObserver decodeGate = new BlockingDecodeObserver();
        SuggestionEngine engine = SuggestionEngineFactory.createForDecoderTest(
                specs,
                activation -> {
                },
                decodeGate
        );
        try {
            SuggestionActivation activation = engine.activate(profile);
            long timeout = SystemClock.elapsedRealtime() + PACK_READY_TIMEOUT_MILLIS;
            long generation = 0L;
            while (SystemClock.elapsedRealtime() < timeout) {
                SuggestionQuery query = SuggestionQuery.functionalTestRequest(
                        activation,
                        profile,
                        "h",
                        ++generation,
                        TouchSequence.empty()
                );
                SuggestionSnapshot snapshot = engine.suggest(activation, query);
                if (snapshot.status() == SuggestionSnapshot.Status.LOADING) {
                    SystemClock.sleep(25L);
                    continue;
                }
                assertEquals(
                        "staged NKP prefix is ready",
                        SuggestionSnapshot.Status.READY,
                        snapshot.status()
                );
                assertTrue("staged NKP result owns request", snapshot.belongsTo(query));
                assertTrue(
                        "staged NKP functional query has no wall-clock deadline",
                        !query.isBoundedDecoderRequest()
                );
                assertTrue("staged NKP result keeps literal", snapshot.hasExplicitLiteral());
                assertTrue(
                        "staged NKP N-best remains bounded",
                        snapshot.nBestCandidates().size() <= SuggestionSnapshot.MAX_CANDIDATES
                );
                boolean exactProvider = false;
                boolean literalProvider = false;
                int precedingProviderScore = Integer.MAX_VALUE;
                for (SuggestionCandidate candidate : snapshot.nBestCandidates()) {
                    if (candidate.isLiteral()) {
                        literalProvider = true;
                        assertEquals("staged literal preserves prefix", "h", candidate.text());
                    } else {
                        exactProvider = true;
                        assertTrue(
                                "staged provider ordinals descend",
                                candidate.providerScore() < precedingProviderScore
                        );
                        precedingProviderScore = candidate.providerScore();
                        assertEquals(
                                "staged surface category",
                                SuggestionCandidate.Category.EXACT,
                                candidate.category()
                        );
                        assertEquals(
                                "staged NKP provider identity",
                                NkpSuggestionEngine.EXACT_PREFIX_PROVIDER,
                                candidate.providerId()
                        );
                    }
                }
                assertTrue("staged NKP contributes an exact-prefix candidate", exactProvider);
                assertTrue("staged NKP contributes one literal candidate", literalProvider);
                verifyFunctionalQueryApiIsolation(engine, query);
                verifyAsyncNkpSubmission(
                        engine,
                        activation,
                        profile,
                        decodeGate,
                        TouchSequence.forToken(
                                profile,
                                capturedStroke.emittedText(),
                                Collections.singletonList(capturedStroke)
                        )
                );
                return;
            }
            throw new AssertionError("staged NKP provider readiness timed out");
        } finally {
            engine.close();
        }
    }

    private static void verifyFunctionalQueryApiIsolation(
            SuggestionEngine engine,
            SuggestionQuery functionalQuery
    ) {
        boolean synchronousProductionEntryRejected = false;
        try {
            engine.suggest(functionalQuery);
        } catch (IllegalArgumentException expected) {
            synchronousProductionEntryRejected = true;
        }
        assertTrue(
                "functional query cannot enter one-argument production decoder API",
                synchronousProductionEntryRejected
        );

        AtomicBoolean callbackInvoked = new AtomicBoolean(false);
        assertEquals(
                "functional query cannot enter production async queue",
                SuggestionEngine.SubmitOutcome.STALE,
                engine.submit(
                        functionalQuery,
                        (ignoredQuery, ignoredSnapshot) -> callbackInvoked.set(true)
                )
        );
        assertTrue("rejected functional query has no async callback", !callbackInvoked.get());
    }

    private SpatialKeyStroke verifySpatialTouchProvenance(
            Context context,
            KeyboardProfile profile
    ) {
        assertTrue("spatial touch profile has versioned layout", profile.hasVersionedLayout());
        KeyboardGeometry invariantGeometry = new KeyboardGeometry(
                profile.layoutId(),
                profile.layoutRevision(),
                profile.layoutSourceSha256(),
                99L,
                Collections.singletonList(new KeyboardGeometry.KeyBounds(
                        "policy-vector",
                        "h",
                        KeySpec.InputPolicy.DEFAULT,
                        0,
                        0,
                        100_000,
                        100_000
                ))
        );
        boolean policyMismatchRejected = false;
        try {
            SpatialKeyStroke.spatial(
                    invariantGeometry,
                    "policy-vector",
                    "h",
                    KeySpec.InputPolicy.ORTHOGRAPHIC_WORD,
                    50_000,
                    50_000
            );
        } catch (IllegalArgumentException expected) {
            policyMismatchRejected = true;
        }
        assertTrue("spatial factory rejects input-policy forgery", policyMismatchRejected);

        Intent hostIntent = new Intent(context, SettingsActivity.class);
        hostIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity host = startActivitySync(hostIntent);
        AtomicReference<SpatialKeyStroke> observed = new AtomicReference<>();
        AtomicReference<KeyboardSurface> surfaceReference = new AtomicReference<>();
        try {
            runOnMainSync(() -> {
                KeyboardSurface surface = new KeyboardSurface(host);
                surface.setListener(recordingSurfaceListener(observed));
                surface.render(KeyboardLayouts.forProfile(profile, false, false, false));
                host.setContentView(surface);
                surfaceReference.set(surface);
            });
            waitForIdleSync();
            runOnMainSync(() -> assertTrue(
                    "programmatic text key dispatch",
                    surfaceReference.get().performTextKeyForTesting("h")
            ));
            SpatialKeyStroke nonSpatial = observed.getAndSet(null);
            assertTrue("programmatic key records provenance", nonSpatial != null);
            assertTrue(
                    "programmatic/accessibility click never fabricates coordinates",
                    !nonSpatial.hasSpatialEvidence()
            );
            assertEquals("non-spatial layout identity", profile.layoutId(), nonSpatial.layoutId());
            assertEquals(
                    "non-spatial alternative is exact only",
                    1,
                    nonSpatial.alternatives(3).size()
            );

            runOnMainSync(() -> assertTrue(
                    "real MotionEvent text key dispatch",
                    surfaceReference.get().performTextKeyTouchForTesting("h", 0.5f, 0.5f)
            ));
            waitForIdleSync();
            SpatialKeyStroke spatial = observed.get();
            assertTrue("real MotionEvent records a stroke", spatial != null);
            assertTrue("real MotionEvent records coordinates", spatial.hasSpatialEvidence());
            assertEquals("spatial layout identity", profile.layoutId(), spatial.layoutId());
            assertTrue(
                    "captured alternatives remain bounded",
                    spatial.alternatives(3).size() <= 3
            );
        } finally {
            runOnMainSync(host::finish);
            waitForIdleSync();
        }
        SpatialKeyStroke captured = observed.get();
        assertTrue("captured spatial stroke survives UI handoff", captured != null);

        ContractEngine alignmentEngine = new ContractEngine(new AtomicLong(System.nanoTime()));
        RecordingTextSink sink = new RecordingTextSink();
        ComposingSession session = new ComposingSession(alignmentEngine);
        session.start(profile, true, false, sink);
        session.appendText(
                captured.emittedText(),
                captured.inputPolicy(),
                captured,
                sink
        );
        SuggestionDispatch dispatch = session.beginSuggestionDispatch();
        SuggestionQuery query = dispatch.query();
        assertTrue("captured stroke creates a decoder request", query != null);
        assertTrue("captured stroke reaches composing query", query.touchSequence().hasSpatialEvidence());
        assertEquals("captured query owns one stroke", 1, query.touchSequence().strokes().size());
        assertSame(
                "captured query retains exact immutable stroke",
                captured,
                query.touchSequence().strokes().get(0)
        );
        session.finish(sink);
        alignmentEngine.close();
        return captured;
    }

    private static KeyboardSurface.Listener recordingSurfaceListener(
            AtomicReference<SpatialKeyStroke> observed
    ) {
        return new KeyboardSurface.Listener() {
            @Override
            public void onKey(KeySpec key, SpatialKeyStroke stroke) {
                if (key.action() == KeySpec.Action.TEXT) {
                    observed.set(stroke);
                }
            }

            @Override
            public void onLanguagePickerRequested(View source) {
            }
        };
    }

    private void verifySpatialNkpProvider(
            Context context,
            KeyboardProfile english,
            KeyboardProfile nepali
    ) throws InterruptedException {
        List<ReleasePackSpec> specs = ReleasePackRegistry.installed(context);
        assertTrue("spatial decoder acceptance requires staged packs", !specs.isEmpty());
        SuggestionEngine engine = SuggestionEngineFactory.createForDecoderTest(
                specs,
                activation -> {
                },
                NkpSuggestionEngine.DecodeObserver.NONE
        );
        try {
            assertTrue("focused spatial provider is NKP", engine instanceof NkpSuggestionEngine);

            SpatialDecoderVectors.ProfileVectors englishVectors =
                    SpatialDecoderVectors.captureEnglish(this, context, english);
            Map<String, SpatialKeyStroke> englishStrokes = englishVectors.strokes();
            verifyMixedTouchAvoidsCleanExactFastPath(english, englishStrokes);
            SuggestionActivation englishActivation = engine.activate(english);
            awaitReadyProvider(
                    engine,
                    englishActivation,
                    english,
                    englishVectors.cleanPrefix()
            );
            verifyCenterTapMatrix(
                    engine,
                    englishActivation,
                    english,
                    englishStrokes,
                    englishVectors.centerPrefixes(),
                    310_000L
            );
            String englishSurface = verifySpatialProfile(
                    engine,
                    englishActivation,
                    english,
                    englishVectors.cleanPrefix(),
                    englishVectors.expectedSurface(),
                    englishVectors.cleanTouchSequence(),
                    englishVectors.boundaryRaw(),
                    englishVectors.boundaryTouchSequence(),
                    300_000L
            );
            verifyAsyncSpatialSession(
                    engine,
                    english,
                    englishVectors.boundaryRaw(),
                    englishVectors.boundaryTouchSequence(),
                    englishSurface
            );

            SpatialDecoderVectors.ProfileVectors nepaliVectors =
                    SpatialDecoderVectors.captureNepali(this, context, nepali);
            Map<String, SpatialKeyStroke> nepaliStrokes = nepaliVectors.strokes();
            SuggestionActivation nepaliActivation = engine.activate(nepali);
            awaitReadyProvider(
                    engine,
                    nepaliActivation,
                    nepali,
                    nepaliVectors.cleanPrefix()
            );
            verifyCenterTapMatrix(
                    engine,
                    nepaliActivation,
                    nepali,
                    nepaliStrokes,
                    nepaliVectors.centerPrefixes(),
                    410_000L
            );
            String nepaliSurface = verifySpatialProfile(
                    engine,
                    nepaliActivation,
                    nepali,
                    nepaliVectors.cleanPrefix(),
                    nepaliVectors.expectedSurface(),
                    nepaliVectors.cleanTouchSequence(),
                    nepaliVectors.boundaryRaw(),
                    nepaliVectors.boundaryTouchSequence(),
                    400_000L
            );
            verifyAsyncSpatialSession(
                    engine,
                    nepali,
                    nepaliVectors.boundaryRaw(),
                    nepaliVectors.boundaryTouchSequence(),
                    nepaliSurface
            );
        } finally {
            engine.close();
        }
    }

    private static void verifyCenterTapMatrix(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            Map<String, SpatialKeyStroke> strokesByText,
            List<String> prefixes,
            long firstGeneration
    ) {
        long generation = firstGeneration;
        int spatialProviderRows = 0;
        int parityRows = 0;
        for (String prefix : prefixes) {
            List<SpatialKeyStroke> strokes = new ArrayList<>();
            for (int offset = 0; offset < prefix.length(); ) {
                int next = offset + Character.charCount(prefix.codePointAt(offset));
                String text = prefix.substring(offset, next);
                SpatialKeyStroke stroke = strokesByText.get(text);
                assertTrue("center matrix has compiled key " + text, stroke != null);
                strokes.add(stroke);
                offset = next;
            }
            TouchSequence touchSequence = TouchSequence.forToken(profile, prefix, strokes);
            assertTrue(
                    "center tap is eligible for exact spatial fast path " + prefix,
                    NkpSuggestionEngine.isCleanExactTouchForTesting(touchSequence)
            );
            SuggestionSnapshot exact = validatedFunctionalSnapshot(
                    engine,
                    activation,
                    profile,
                    prefix,
                    generation,
                    TouchSequence.empty(),
                    "center exact " + profile.id() + " " + prefix
            );
            generation++;
            SuggestionSnapshot spatial = validatedFunctionalSnapshot(
                    engine,
                    activation,
                    profile,
                    prefix,
                    generation,
                    touchSequence,
                    "center spatial " + profile.id() + " " + prefix
            );
            generation++;
            spatialProviderRows++;
            SuggestionCandidate spatialCandidate = firstProviderCandidate(spatial);
            if (exact.hasProviderCandidates()) {
                SuggestionCandidate exactCandidate = firstProviderCandidate(exact);
                assertEquals(
                        "center tap preserves exact-prefix top result " + prefix,
                        exactCandidate.text(),
                        spatialCandidate.text()
                );
                parityRows++;
            }
            int providerIndex = 0;
            boolean correctionSeen = false;
            for (SuggestionCandidate candidate : spatial.nBestCandidates()) {
                if (!candidate.isLiteral()) {
                    assertTrue(
                            "center tap provider category remains spatial exact/correction "
                                    + prefix,
                            candidate.category() == SuggestionCandidate.Category.EXACT
                                    || candidate.category()
                                    == SuggestionCandidate.Category.CORRECTION
                    );
                    if (candidate.category() == SuggestionCandidate.Category.CORRECTION) {
                        assertTrue(
                                "center tap correction remains below exact top " + prefix,
                                providerIndex > 0
                        );
                        correctionSeen = true;
                    } else {
                        assertTrue(
                                "center tap exact results precede corrections " + prefix,
                                !correctionSeen
                        );
                    }
                    assertEquals(
                            "center tap provider identity remains spatial " + prefix,
                            NkpSuggestionEngine.SPATIAL_TAP_PROVIDER,
                            candidate.providerId()
                    );
                    providerIndex++;
                }
            }
            assertEquals(
                    "center tap remains exact " + prefix,
                    SuggestionCandidate.Category.EXACT,
                    spatialCandidate.category()
            );
            assertEquals(
                    "center tap uses spatial provider " + prefix,
                    NkpSuggestionEngine.SPATIAL_TAP_PROVIDER,
                    spatialCandidate.providerId()
            );
            assertLiteralCandidate(spatial, prefix);
        }
        assertTrue(
                "center matrix retains provider-covered rows " + profile.id(),
                spatialProviderRows > 0
        );
        assertTrue(
                "center matrix retains exact/spatial parity-covered rows " + profile.id(),
                parityRows > 0
        );
    }

    private static void verifyMixedTouchAvoidsCleanExactFastPath(
            KeyboardProfile profile,
            Map<String, SpatialKeyStroke> strokesByText
    ) {
        SpatialKeyStroke spatial = strokesByText.get("h");
        SpatialKeyStroke capturedNonSpatial = strokesByText.get("e");
        assertTrue("mixed-touch vector has captured strokes", spatial != null
                && capturedNonSpatial != null);
        SpatialKeyStroke nonSpatial = SpatialKeyStroke.nonSpatial(
                capturedNonSpatial.layoutId(),
                capturedNonSpatial.layoutRevision(),
                capturedNonSpatial.layoutSourceSha256(),
                capturedNonSpatial.renderGeneration(),
                capturedNonSpatial.keyId(),
                capturedNonSpatial.emittedText(),
                capturedNonSpatial.inputPolicy()
        );
        TouchSequence mixed = TouchSequence.forToken(
                profile,
                "he",
                Arrays.asList(spatial, nonSpatial)
        );
        assertTrue(
                "mixed provenance retains correction-beam lookup",
                !NkpSuggestionEngine.isCleanExactTouchForTesting(mixed)
        );
    }

    private static String verifySpatialProfile(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            String cleanPrefix,
            String expectedSurface,
            TouchSequence cleanTouch,
            String correctedRaw,
            TouchSequence correctedTouch,
            long generation
    ) {
        SuggestionSnapshot exact = requireFunctionalProviderSnapshot(
                engine,
                activation,
                profile,
                cleanPrefix,
                generation,
                TouchSequence.empty(),
                "spatial exact " + profile.id() + " " + cleanPrefix
        );
        SuggestionCandidate exactCandidate = firstProviderCandidate(exact);
        if (expectedSurface != null) {
            assertEquals("exact-prefix baseline surface", expectedSurface, exactCandidate.text());
        }
        String authoritativeSurface = exactCandidate.text();
        assertEquals(
                "exact-prefix baseline provider",
                NkpSuggestionEngine.EXACT_PREFIX_PROVIDER,
                exactCandidate.providerId()
        );

        SuggestionSnapshot clean = requireFunctionalProviderSnapshot(
                engine,
                activation,
                profile,
                cleanPrefix,
                generation + 1L,
                cleanTouch,
                "spatial clean " + profile.id() + " " + cleanPrefix
        );
        SuggestionCandidate cleanCandidate = firstProviderCandidate(clean);
        assertEquals("clean tap preserves exact prefix ranking", authoritativeSurface, cleanCandidate.text());
        assertEquals(
                "clean tap category",
                SuggestionCandidate.Category.EXACT,
                cleanCandidate.category()
        );
        assertEquals(
                "clean tap provider",
                NkpSuggestionEngine.SPATIAL_TAP_PROVIDER,
                cleanCandidate.providerId()
        );
        assertLiteralCandidate(clean, cleanPrefix);

        SuggestionSnapshot corrected = requireFunctionalProviderSnapshot(
                engine,
                activation,
                profile,
                correctedRaw,
                generation + 2L,
                correctedTouch,
                "spatial corrected " + profile.id() + " " + correctedRaw
        );
        SuggestionCandidate correctedCandidate = firstProviderCandidate(corrected);
        assertEquals("near-key tap recovers expected prefix", authoritativeSurface, correctedCandidate.text());
        assertEquals(
                "near-key tap category",
                SuggestionCandidate.Category.CORRECTION,
                correctedCandidate.category()
        );
        assertEquals(
                "near-key tap provider",
                NkpSuggestionEngine.SPATIAL_TAP_PROVIDER,
                correctedCandidate.providerId()
        );
        assertLiteralCandidate(corrected, correctedRaw);

        assertTrue(
                "clean center is eligible for exact spatial fast path",
                NkpSuggestionEngine.isCleanExactTouchForTesting(cleanTouch)
        );
        assertTrue(
                "boundary correction retains the full spatial path",
                !NkpSuggestionEngine.isCleanExactTouchForTesting(correctedTouch)
        );

        assertTrue(
                "clean spatial beam count is bounded",
                NkpSuggestionEngine.spatialBeamCountForTesting(cleanTouch, cleanPrefix)
                        <= NkpSuggestionEngine.maxSpatialBeamsForTesting()
        );
        assertTrue(
                "corrected spatial beam count is bounded",
                NkpSuggestionEngine.spatialBeamCountForTesting(correctedTouch, correctedRaw)
                        <= NkpSuggestionEngine.maxSpatialBeamsForTesting()
        );
        assertTrue(
                "joint score can prefer much stronger dictionary evidence",
                NkpSuggestionEngine.spatialJointScoreForTesting(10_000, 1_400_000, 0)
                        > NkpSuggestionEngine.spatialJointScoreForTesting(
                        2_000,
                        1_000_000,
                        0
                )
        );
        assertTrue(
                "one-key center separation bounds current lexical spread",
                NkpSuggestionEngine.spatialJointScoreForTesting(1_000, 0, 0)
                        > NkpSuggestionEngine.spatialJointScoreForTesting(
                        32_000,
                        4_194_304,
                        0
                )
        );
        return authoritativeSurface;
    }

    private void verifyAsyncSpatialSession(
            SuggestionEngine engine,
            KeyboardProfile profile,
            String rawText,
            TouchSequence touchSequence,
            String expectedSurface
    ) throws InterruptedException {
        ComposingSession session = new ComposingSession(
                engine,
                System::nanoTime,
                SuggestionQuery.MAX_DEADLINE_BUDGET_NANOS
        );
        RecordingTextSink sink = new RecordingTextSink();
        AtomicReference<SuggestionQuery> submittedQuery = new AtomicReference<>();
        AtomicReference<SuggestionQuery> callbackQuery = new AtomicReference<>();
        AtomicReference<SuggestionSnapshot> callbackSnapshot = new AtomicReference<>();
        AtomicReference<Thread> callbackThread = new AtomicReference<>();
        AtomicLong callbackCompletedAtNanos = new AtomicLong(-1L);
        AtomicReference<SuggestionEngine.SubmitOutcome> outcome = new AtomicReference<>();
        CountDownLatch completion = new CountDownLatch(1);

        runOnMainSync(() -> {
            session.start(profile, true, false, sink);
            for (SpatialKeyStroke stroke : touchSequence.strokes()) {
                session.appendText(
                        stroke.emittedText(),
                        stroke.inputPolicy(),
                        stroke,
                        sink
                );
            }
            assertEquals("real spatial session preserves raw text", rawText, sink.text);
            SuggestionDispatch dispatch = session.beginSuggestionDispatch();
            SuggestionQuery query = dispatch.query();
            assertTrue("real spatial session creates query", query != null);
            assertTrue("real spatial session owns touch evidence", query.touchSequence().hasSpatialEvidence());
            assertEquals(
                    "real spatial session keeps every stroke",
                    touchSequence.strokes().size(),
                    query.touchSequence().strokes().size()
            );
            submittedQuery.set(query);
            outcome.set(engine.submit(query, (completedQuery, snapshot) -> {
                callbackCompletedAtNanos.set(System.nanoTime());
                callbackThread.set(Thread.currentThread());
                callbackQuery.set(completedQuery);
                callbackSnapshot.set(snapshot);
                completion.countDown();
            }));
        });

        assertEquals(
                "real spatial async submit accepted",
                SuggestionEngine.SubmitOutcome.ACCEPTED,
                outcome.get()
        );
        assertTrue("real spatial async callback completes", completion.await(5L, TimeUnit.SECONDS));
        SuggestionQuery query = submittedQuery.get();
        assertSame("real spatial callback owns exact query", query, callbackQuery.get());
        assertTrue(
                "real spatial callback is off Android main",
                callbackThread.get() != Looper.getMainLooper().getThread()
        );
        SuggestionSnapshot snapshot = callbackSnapshot.get();
        assertTrue("real spatial callback snapshot owns query", snapshot.belongsTo(query));
        assertLiteralCandidate(snapshot, rawText);
        if (snapshot.hasProviderCandidates()) {
            SuggestionCandidate candidate = firstProviderCandidate(snapshot);
            assertEquals("real spatial async correction", expectedSurface, candidate.text());
            assertEquals(
                    "real spatial async category",
                    SuggestionCandidate.Category.CORRECTION,
                    candidate.category()
            );
            assertEquals(
                    "real spatial async provider",
                    NkpSuggestionEngine.SPATIAL_TAP_PROVIDER,
                    candidate.providerId()
            );
        } else {
            assertTrue("real spatial late result is literal fallback", snapshot.isLiteralFallback());
            assertTrue(
                    "real spatial late result excludes provider candidates",
                    !snapshot.hasProviderCandidates()
            );
            assertTrue(
                    "real spatial late result follows deadline expiry",
                    query.isExpired(callbackCompletedAtNanos.get())
            );
        }
        runOnMainSync(() -> session.finish(sink));
    }

    private static SuggestionCandidate firstProviderCandidate(SuggestionSnapshot snapshot) {
        assertEquals("spatial provider is ready", SuggestionSnapshot.Status.READY, snapshot.status());
        assertTrue("spatial result owns exact request", snapshot.query() != null);
        assertTrue("spatial N-best remains bounded", snapshot.nBestCandidates().size()
                <= SuggestionSnapshot.MAX_CANDIDATES);
        for (SuggestionCandidate candidate : snapshot.nBestCandidates()) {
            if (!candidate.isLiteral()) {
                return candidate;
            }
        }
        throw new AssertionError("spatial provider returned no provider candidate");
    }

    private static SuggestionSnapshot requireFunctionalProviderSnapshot(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            String composingText,
            long generation,
            TouchSequence touchSequence,
            String assertionLabel
    ) {
        return validatedFunctionalSnapshot(
                engine,
                activation,
                profile,
                composingText,
                generation,
                touchSequence,
                assertionLabel
        );
    }

    private static SuggestionSnapshot validatedFunctionalSnapshot(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            String composingText,
            long generation,
            TouchSequence touchSequence,
            String assertionLabel
    ) {
        SuggestionQuery query = SuggestionQuery.functionalTestRequest(
                activation,
                profile,
                composingText,
                generation,
                touchSequence
        );
        SuggestionSnapshot snapshot = engine.suggest(activation, query);
        assertTrue(
                assertionLabel + " functional request has no wall-clock deadline",
                !query.isBoundedDecoderRequest()
        );
        assertTrue(assertionLabel + " result owns request", snapshot.belongsTo(query));
        assertEquals(
                assertionLabel + " result is ready",
                SuggestionSnapshot.Status.READY,
                snapshot.status()
        );
        assertTrue(
                assertionLabel + " N-best remains bounded",
                snapshot.nBestCandidates().size() <= SuggestionSnapshot.MAX_CANDIDATES
        );
        assertLiteralCandidate(snapshot, composingText);
        assertTrue(
                assertionLabel + " functional result has provider candidates",
                snapshot.hasProviderCandidates()
        );
        assertTrue(
                assertionLabel + " functional result is not literal fallback",
                !snapshot.isLiteralFallback()
        );
        return snapshot;
    }

    private static void assertLiteralCandidate(
            SuggestionSnapshot snapshot,
            String expectedText
    ) {
        int literalCount = 0;
        for (SuggestionCandidate candidate : snapshot.nBestCandidates()) {
            if (candidate.isLiteral()) {
                literalCount++;
                assertEquals("spatial literal preserves raw input", expectedText, candidate.text());
            }
        }
        assertEquals("spatial result has one literal", 1, literalCount);
        assertTrue(
                "spatial literal remains last",
                snapshot.nBestCandidates().get(
                        snapshot.nBestCandidates().size() - 1
                ).isLiteral()
        );
    }

    private void verifyAsyncNkpSubmission(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            BlockingDecodeObserver decodeGate,
            TouchSequence touchSequence
    ) throws InterruptedException {
        CountDownLatch heartbeat = new CountDownLatch(1);
        CountDownLatch completion = new CountDownLatch(1);
        AtomicReference<SuggestionQuery> queryReference = new AtomicReference<>();
        AtomicReference<SuggestionEngine.SubmitOutcome> outcome = new AtomicReference<>();
        AtomicReference<Thread> callbackThread = new AtomicReference<>();
        AtomicReference<SuggestionSnapshot> callbackSnapshot = new AtomicReference<>();
        AtomicLong callbackNanos = new AtomicLong(Long.MAX_VALUE);
        AtomicLong releaseNanos = new AtomicLong(Long.MAX_VALUE);
        Handler main = new Handler(Looper.getMainLooper());

        runOnMainSync(() -> {
            assertSame("async submit runs on Android main", Looper.getMainLooper().getThread(), Thread.currentThread());
            long createdAtNanos = System.nanoTime();
            SuggestionQuery query = SuggestionQuery.decoderRequest(
                    activation,
                    profile,
                    "h",
                    false,
                    100_000L,
                    createdAtNanos,
                    createdAtNanos + SuggestionQuery.MAX_DEADLINE_BUDGET_NANOS,
                    new SuggestionCancellation(),
                    touchSequence
            );
            queryReference.set(query);
            outcome.set(engine.submit(query, (completedQuery, snapshot) -> {
                assertSame("async callback owns exact request", query, completedQuery);
                callbackThread.set(Thread.currentThread());
                callbackSnapshot.set(snapshot);
                callbackNanos.set(System.nanoTime());
                completion.countDown();
            }));
            main.post(heartbeat::countDown);
        });

        assertEquals(
                "real NKP async submit is accepted",
                SuggestionEngine.SubmitOutcome.ACCEPTED,
                outcome.get()
        );
        assertTrue("decode worker reaches controlled gate", decodeGate.awaitEntered());
        assertSame(
                "decode worker observes exact spatial request",
                queryReference.get(),
                decodeGate.observedQuery()
        );
        assertTrue(
                "decode worker observes MotionEvent-derived evidence",
                decodeGate.observedQuery().touchSequence().hasSpatialEvidence()
        );
        try {
            assertTrue(
                    "main looper heartbeat runs while provider is blocked",
                    heartbeat.await(2L, TimeUnit.SECONDS)
            );
            assertTrue(
                    "blocked provider cannot complete before controlled release",
                    completion.getCount() == 1L
            );
        } finally {
            releaseNanos.set(System.nanoTime());
            decodeGate.release();
        }
        assertTrue("async NKP callback completes", completion.await(5L, TimeUnit.SECONDS));
        SuggestionQuery query = queryReference.get();
        assertTrue(
                "NKP callback never runs on Android main",
                callbackThread.get() != Looper.getMainLooper().getThread()
        );
        SuggestionSnapshot snapshot = callbackSnapshot.get();
        assertTrue("async result owns exact request", snapshot != null && snapshot.belongsTo(query));
        assertTrue("async result keeps exact literal", snapshot.hasExplicitLiteral());
        assertTrue(
                "async provider callback follows controlled release",
                callbackNanos.get() >= releaseNanos.get()
        );
        assertTrue("focused provider is NKP", engine instanceof NkpSuggestionEngine);
        assertSame(
                "recorded decode thread is callback worker",
                callbackThread.get(),
                ((NkpSuggestionEngine) engine).lastDecodeThreadForTesting()
        );
        long completedAtNanos = callbackNanos.get();
        if (completedAtNanos < query.deadlineNanos()) {
            assertTrue("on-time async result includes provider candidates", snapshot.hasProviderCandidates());
            int precedingScore = Integer.MAX_VALUE;
            for (SuggestionCandidate candidate : snapshot.nBestCandidates()) {
                if (!candidate.isLiteral()) {
                    assertEquals(
                            "async provider category",
                            SuggestionCandidate.Category.EXACT,
                            candidate.category()
                    );
                    assertEquals(
                            "async provider identity",
                            NkpSuggestionEngine.SPATIAL_TAP_PROVIDER,
                            candidate.providerId()
                    );
                    assertTrue(
                            "provider ordinal is monotonically descending",
                            candidate.providerScore() < precedingScore
                    );
                    precedingScore = candidate.providerScore();
                }
            }
        } else {
            assertTrue("late async result is expired", query.isExpired(completedAtNanos));
            assertTrue("late async result is literal-only", snapshot.isLiteralFallback());
            assertTrue(
                    "late async result excludes provider candidates",
                    !snapshot.hasProviderCandidates()
            );
        }
    }

    private void verifyLatestWinsAsyncQueue(
            Context context,
            KeyboardProfile profile
    ) throws InterruptedException {
        NonCooperativeFirstDecodeObserver decodeGate =
                new NonCooperativeFirstDecodeObserver();
        SuggestionEngine engine = SuggestionEngineFactory.createForDecoderTest(
                ReleasePackRegistry.installed(context),
                activation -> {
                },
                decodeGate
        );
        try {
            SuggestionActivation activation = engine.activate(profile);
            awaitReadyProvider(engine, activation, profile);
            AtomicReference<SuggestionQuery> finalQuery = new AtomicReference<>();
            AtomicReference<SuggestionQuery> callbackQuery = new AtomicReference<>();
            AtomicReference<SuggestionSnapshot> callbackSnapshot = new AtomicReference<>();
            AtomicInteger callbackCount = new AtomicInteger();
            AtomicLong callbackAtNanos = new AtomicLong();
            CountDownLatch completion = new CountDownLatch(1);
            SuggestionEngine.ResultListener listener = (query, snapshot) -> {
                callbackQuery.set(query);
                callbackSnapshot.set(snapshot);
                callbackAtNanos.set(System.nanoTime());
                callbackCount.incrementAndGet();
                completion.countDown();
            };

            runOnMainSync(() -> {
                SuggestionQuery first = newBoundedQuery(activation, profile, "h", 200_000L);
                assertEquals(
                        "blocked first async query accepted",
                        SuggestionEngine.SubmitOutcome.ACCEPTED,
                        engine.submit(first, listener)
                );
            });
            assertTrue("first async query reaches non-cooperative gate", decodeGate.awaitEntered());

            runOnMainSync(() -> {
                for (int index = 1; index <= 20; index++) {
                    SuggestionQuery latest = newBoundedQuery(
                            activation,
                            profile,
                            "h",
                            200_000L + index
                    );
                    assertEquals(
                            "superseding async query accepted",
                            SuggestionEngine.SubmitOutcome.ACCEPTED,
                            engine.submit(latest, listener)
                    );
                    assertTrue("decoder queue remains bounded", engine instanceof NkpSuggestionEngine);
                    assertTrue(
                            "decoder queue contains at most latest query",
                            ((NkpSuggestionEngine) engine).queuedDecodeCountForTesting() <= 1
                    );
                    finalQuery.set(latest);
                }
            });
            decodeGate.release();
            assertTrue("latest async query completes", completion.await(5L, TimeUnit.SECONDS));
            SystemClock.sleep(50L);
            assertEquals("only one async callback survives", 1, callbackCount.get());
            assertSame("latest query owns callback", finalQuery.get(), callbackQuery.get());
            SuggestionSnapshot snapshot = callbackSnapshot.get();
            assertTrue("latest callback owns exact request", snapshot.belongsTo(finalQuery.get()));
            assertEquals(
                    "latest callback is a terminal ready result",
                    SuggestionSnapshot.Status.READY,
                    snapshot.status()
            );
            assertTrue("latest callback preserves literal", snapshot.hasExplicitLiteral());
            if (snapshot.hasProviderCandidates()) {
                assertTrue(
                        "on-time latest callback is not literal fallback",
                        !snapshot.isLiteralFallback()
                );
            } else {
                assertTrue(
                        "expired latest callback is literal-only fallback",
                        snapshot.isLiteralFallback()
                );
                assertTrue(
                        "provider-free latest callback follows deadline expiry",
                        finalQuery.get().isExpired(callbackAtNanos.get())
                );
                assertEquals(
                        "expired latest callback preserves exact input",
                        "h",
                        snapshot.candidates().get(0)
                );
            }
        } finally {
            decodeGate.release();
            engine.close();
        }
    }

    private static void awaitReadyProvider(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile
    ) {
        awaitReadyProvider(engine, activation, profile, "h");
    }

    private static void awaitReadyProvider(
            SuggestionEngine engine,
            SuggestionActivation activation,
            KeyboardProfile profile,
            String prefix
    ) {
        long timeout = SystemClock.elapsedRealtime() + PACK_READY_TIMEOUT_MILLIS;
        long generation = 150_000L;
        while (SystemClock.elapsedRealtime() < timeout) {
            SuggestionQuery query = SuggestionQuery.functionalTestRequest(
                    activation,
                    profile,
                    prefix,
                    ++generation,
                    TouchSequence.empty()
            );
            SuggestionSnapshot snapshot = engine.suggest(activation, query);
            if (snapshot.status() == SuggestionSnapshot.Status.LOADING) {
                SystemClock.sleep(25L);
                continue;
            }
            assertEquals(
                    "latest-wins staged provider is ready",
                    SuggestionSnapshot.Status.READY,
                    snapshot.status()
            );
            assertTrue("functional readiness result owns request", snapshot.belongsTo(query));
            assertTrue(
                    "functional readiness query has no wall-clock deadline",
                    !query.isBoundedDecoderRequest()
            );
            assertTrue("latest-wins staged provider has candidates", snapshot.hasProviderCandidates());
            return;
        }
        throw new AssertionError("latest-wins staged provider readiness timed out");
    }

    private static SuggestionQuery newBoundedQuery(
            SuggestionActivation activation,
            KeyboardProfile profile,
            String composingText,
            long generation
    ) {
        return newBoundedQuery(
                activation,
                profile,
                composingText,
                generation,
                TouchSequence.empty()
        );
    }

    private static SuggestionQuery newBoundedQuery(
            SuggestionActivation activation,
            KeyboardProfile profile,
            String composingText,
            long generation,
            TouchSequence touchSequence
    ) {
        long createdAtNanos = System.nanoTime();
        return SuggestionQuery.decoderRequest(
                activation,
                profile,
                composingText,
                false,
                generation,
                createdAtNanos,
                createdAtNanos + SuggestionQuery.MAX_DEADLINE_BUDGET_NANOS,
                new SuggestionCancellation(),
                touchSequence
        );
    }

    private static KeyboardProfile requireProfile(String profileId) {
        KeyboardProfile profile = LanguageRegistry.find(profileId);
        if (profile == null || !profile.isAvailable()) {
            throw new AssertionError("required profile is unavailable: " + profileId);
        }
        return profile;
    }

    private static final class BlockingDecodeObserver
            implements NkpSuggestionEngine.DecodeObserver {
        private final CountDownLatch entered = new CountDownLatch(1);
        private final CountDownLatch released = new CountDownLatch(1);
        private final AtomicReference<SuggestionQuery> observedQuery = new AtomicReference<>();

        @Override
        public void beforeLookup(SuggestionQuery query) {
            observedQuery.set(query);
            entered.countDown();
            try {
                if (!released.await(5L, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("controlled decode gate timed out");
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("controlled decode gate interrupted", interrupted);
            }
        }

        boolean awaitEntered() throws InterruptedException {
            return entered.await(2L, TimeUnit.SECONDS);
        }

        SuggestionQuery observedQuery() {
            return observedQuery.get();
        }

        void release() {
            released.countDown();
        }
    }

    private static final class NonCooperativeFirstDecodeObserver
            implements NkpSuggestionEngine.DecodeObserver {
        private final AtomicBoolean first = new AtomicBoolean(true);
        private final CountDownLatch entered = new CountDownLatch(1);
        private final CountDownLatch released = new CountDownLatch(1);

        @Override
        public void beforeLookup(SuggestionQuery query) {
            if (!first.compareAndSet(true, false)) {
                return;
            }
            entered.countDown();
            while (released.getCount() != 0L) {
                try {
                    if (!released.await(5L, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("non-cooperative decode gate timed out");
                    }
                } catch (InterruptedException intentionallyIgnored) {
                    // This case deliberately proves correctness when cancellation
                    // cannot stop already-running provider work.
                }
            }
        }

        boolean awaitEntered() throws InterruptedException {
            return entered.await(2L, TimeUnit.SECONDS);
        }

        void release() {
            released.countDown();
        }
    }

    private static void assertTrue(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void assertSame(String label, Object expected, Object actual) {
        if (expected != actual) {
            throw new AssertionError(label + ": expected exact identity");
        }
    }

    private static void assertEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected " + expected + ", got " + actual);
        }
    }

    private static final class ContractEngine implements SuggestionEngine {
        static final String PROVIDER_ID = "instrumentation-exact-prefix";

        enum Mode {
            NORMAL,
            RETURN_PREVIOUS,
            CANCEL_CURRENT,
            EXPIRE_CURRENT
        }

        private final AtomicLong clock;
        private SuggestionActivation activation;
        private SuggestionSnapshot previous;
        private SuggestionQuery lastQuery;
        private long nextActivationId;
        private int providerCallCount;
        Mode mode = Mode.NORMAL;

        ContractEngine(AtomicLong clock) {
            this.clock = clock;
        }

        @Override
        public SuggestionActivation activate(KeyboardProfile profile) {
            activation = SuggestionActivation.active(++nextActivationId, profile);
            return activation;
        }

        @Override
        public SuggestionActivation suspend() {
            activation = SuggestionActivation.suspended(++nextActivationId);
            return activation;
        }

        @Override
        public SuggestionSnapshot suggest(
                SuggestionActivation expectedActivation,
                SuggestionQuery query
        ) {
            providerCallCount++;
            lastQuery = query;
            if (expectedActivation != activation || !query.belongsTo(expectedActivation)) {
                return SuggestionSnapshot.inactive(expectedActivation);
            }
            if (mode == Mode.RETURN_PREVIOUS && previous != null) {
                return previous;
            }
            List<SuggestionCandidate> candidates = new ArrayList<>(Arrays.asList(
                    SuggestionCandidate.provider(
                            "hello",
                            SuggestionCandidate.Category.EXACT,
                            PROVIDER_ID,
                            100
                    ),
                    SuggestionCandidate.literal(query.composingText())
            ));
            SuggestionSnapshot result = SuggestionSnapshot.decoded(
                    expectedActivation,
                    query,
                    candidates
            );
            previous = result;
            if (mode == Mode.CANCEL_CURRENT) {
                cancel(query);
            } else if (mode == Mode.EXPIRE_CURRENT) {
                clock.set(query.deadlineNanos());
            }
            return result;
        }

        @Override
        public boolean retry(SuggestionActivation expectedActivation) {
            return false;
        }

        @Override
        public void close() {
            activation = null;
            previous = null;
            lastQuery = null;
        }
    }

    private static final class RecordingTextSink implements TextSink {
        String text = "";

        @Override
        public boolean setComposingText(String value) {
            text = value;
            return true;
        }

        @Override
        public boolean commitText(String value) {
            text = value;
            return true;
        }

        @Override
        public boolean finishComposingText() {
            return true;
        }

        @Override
        public boolean deletePreviousGrapheme() {
            if (!text.isEmpty()) {
                int boundary = GraphemeBackspace.previousBoundary(text);
                text = text.substring(0, Math.max(0, boundary));
            }
            return true;
        }

        @Override
        public boolean deleteOneCodePoint() {
            if (!text.isEmpty()) {
                text = text.substring(0, text.offsetByCodePoints(text.length(), -1));
            }
            return true;
        }
    }
}
