package com.ampixa.nepakeyboard.ime;

import android.app.Activity;
import android.app.Instrumentation;
import android.os.Bundle;

import com.ampixa.nepakeyboard.conversion.NcmBundle;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Collections;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Focused reader, category, routing, and asynchronous NCM substrate contract. */
public final class NcmConversionInstrumentation extends Instrumentation {
    private static final String CONVERTER_ID = "fixture-Deva-Newa-NP";
    private static final String DEVA_KA = "\u0915";
    private static final String DEVA_SSA = "\u0937";
    private static final String DEVA_VIRAMA = "\u094d";
    private static final String NEWA_KA = "\ud805\udc0e";
    private static final String NEWA_SSA = "\ud805\udc31";
    private static final String NEWA_VIRAMA = "\ud805\udc42";
    private static final String CONJUNCT = DEVA_KA + DEVA_VIRAMA + DEVA_SSA;

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle output = new Bundle();
        int result = Activity.RESULT_CANCELED;
        NcmConversionEngine engine = null;
        try {
            byte[] artifact = canonicalArtifact();
            File file = new File(getTargetContext().getCacheDir(), "fixture-conversion.ncm");
            write(file, artifact);
            String sha256 = sha256(artifact);

            try (NcmBundle bundle = NcmBundle.open(file, sha256)) {
                assertEquals("converter ID", CONVERTER_ID, bundle.converterId());
                assertEquals("mapping version", "1.0.0", bundle.mappingVersion());
                assertEquals("leftmost-longest", NEWA_KA, bundle.convert(CONJUNCT));
                assertEquals(
                        "scalar sequence",
                        NEWA_KA + NEWA_SSA,
                        bundle.convert(DEVA_KA + DEVA_SSA)
                );
                if (bundle.convert(DEVA_KA + "a") != null || bundle.convert("") != null) {
                    throw new AssertionError("unmapped or empty input did not fail closed");
                }
            }

            byte[] nonCanonical = (new String(artifact, StandardCharsets.UTF_8).trim() + " \n")
                    .getBytes(StandardCharsets.UTF_8);
            File drifted = new File(getTargetContext().getCacheDir(), "drifted-conversion.ncm");
            write(drifted, nonCanonical);
            boolean rejected = false;
            try (NcmBundle ignored = NcmBundle.open(drifted, sha256(nonCanonical))) {
                // Canonical drift must not open even when the caller pins its exact hash.
            } catch (IOException expected) {
                rejected = true;
            }
            if (!rejected) {
                throw new AssertionError("non-canonical NCM was accepted");
            }

            KeyboardProfile profile = conversionProfile();
            ConversionMapSpec spec = new ConversionMapSpec(
                    profile.id(),
                    CONVERTER_ID,
                    file,
                    sha256
            );
            CountDownLatch ready = new CountDownLatch(1);
            engine = new NcmConversionEngine(
                    Collections.singletonList(spec),
                    activation -> ready.countDown()
            );
            SuggestionActivation activation = engine.activate(profile);
            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("conversion map did not become ready");
            }
            SuggestionQuery functional = SuggestionQuery.functionalTestRequest(
                    activation,
                    profile,
                    CONJUNCT,
                    1L,
                    TouchSequence.empty()
            );
            SuggestionSnapshot snapshot = engine.suggest(activation, functional);
            assertConversionSnapshot(snapshot, functional);

            long now = System.nanoTime();
            SuggestionQuery asynchronous = SuggestionQuery.decoderRequest(
                    activation,
                    profile,
                    DEVA_KA,
                    false,
                    2L,
                    now,
                    now + SuggestionQuery.MAX_DEADLINE_BUDGET_NANOS,
                    new SuggestionCancellation()
            );
            CountDownLatch completed = new CountDownLatch(1);
            AtomicReference<SuggestionSnapshot> asynchronousResult = new AtomicReference<>();
            AtomicReference<Thread> callbackThread = new AtomicReference<>();
            Thread submittingThread = Thread.currentThread();
            if (engine.submit(asynchronous, (query, value) -> {
                callbackThread.set(Thread.currentThread());
                asynchronousResult.set(value);
                completed.countDown();
            }) != SuggestionEngine.SubmitOutcome.ACCEPTED
                    || !completed.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("asynchronous conversion did not complete");
            }
            if (callbackThread.get() == submittingThread
                    || callbackThread.get() != engine.lastDecodeThreadForTesting()) {
                throw new AssertionError("conversion callback ran on the submitting thread");
            }
            assertConversionSnapshot(asynchronousResult.get(), asynchronous);

            RoutingSuggestionEngine router = new RoutingSuggestionEngine(
                    new NoOpSuggestionEngine(),
                    engine
            );
            SuggestionActivation routed = router.activate(profile);
            if (!routed.ownsProfile(profile)) {
                throw new AssertionError("router did not retain the exact conversion profile");
            }
            router.close();
            engine = null;

            output.putString("status", "ok");
            output.putString("ncm_canonical_reader_verified", "true");
            output.putString("ncm_leftmost_longest_verified", "true");
            output.putString("ncm_no_match_verified", "true");
            output.putString("ncm_conversion_category_verified", "true");
            output.putString("ncm_async_off_main_verified", "true");
            output.putString("ncm_router_activation_verified", "true");
            result = Activity.RESULT_OK;
        } catch (Throwable failure) {
            output.putString("status", "error");
            output.putString("error", failure.toString());
        } finally {
            if (engine != null) {
                engine.close();
            }
        }
        finish(result, output);
    }

    private static void assertConversionSnapshot(
            SuggestionSnapshot snapshot,
            SuggestionQuery query
    ) {
        if (snapshot == null
                || !snapshot.belongsTo(query)
                || snapshot.status() != SuggestionSnapshot.Status.READY
                || snapshot.nBestCandidates().size() != 2) {
            throw new AssertionError("conversion snapshot shape is invalid");
        }
        SuggestionCandidate converted = snapshot.nBestCandidates().get(0);
        SuggestionCandidate literal = snapshot.nBestCandidates().get(1);
        if (converted.category() != SuggestionCandidate.Category.CONVERSION
                || !NcmConversionEngine.CONVERSION_PROVIDER.equals(converted.providerId())
                || converted.providerScore() != 1
                || !literal.isLiteral()
                || !query.composingText().equals(literal.text())) {
            throw new AssertionError("conversion snapshot semantics are invalid");
        }
    }

    private static KeyboardProfile conversionProfile() {
        return new KeyboardProfile(
                "new-Deva-Newa-NP",
                "new",
                "fixture-new-deva-newa",
                "new-NP",
                "Nepal Bhasa",
                "Nepal Bhasa",
                "Deva",
                "Newa",
                "Devanagari to Newa fixture",
                "script_conversion",
                "converter",
                "deva-nepal-bhasa-v1",
                KeyboardProfile.LookupKind.CONVERSION,
                CONVERTER_ID,
                "research",
                KeyboardProfile.Availability.AVAILABLE,
                null,
                null,
                false,
                "language",
                null,
                null,
                "fixture",
                Arrays.asList("new", "Newa", "conversion"),
                Collections.singletonList("fixture-evidence")
        );
    }

    private static byte[] canonicalArtifact() {
        String json = "{"
                + "\"algorithm\":\"leftmost-longest-codepoint-v1\","
                + "\"converter_id\":\"" + CONVERTER_ID + "\","
                + "\"format\":\"nepa-conversion-map\","
                + "\"format_version\":1,"
                + "\"joiner_policy\":\"virama-context-only-v1\","
                + "\"language\":\"new\","
                + "\"mapping_version\":\"1.0.0\","
                + "\"normalization\":\"NFC\","
                + "\"output_script\":\"Newa\","
                + "\"rule_count\":4,"
                + "\"rules\":["
                + "{\"from\":\"" + DEVA_KA + "\",\"to\":\"" + NEWA_KA + "\"},"
                + "{\"from\":\"" + CONJUNCT + "\",\"to\":\"" + NEWA_KA + "\"},"
                + "{\"from\":\"" + DEVA_SSA + "\",\"to\":\"" + NEWA_SSA + "\"},"
                + "{\"from\":\"" + DEVA_VIRAMA + "\",\"to\":\"" + NEWA_VIRAMA + "\"}"
                + "],"
                + "\"source_script\":\"Deva\","
                + "\"unmapped_policy\":\"no-match\""
                + "}\n";
        return json.getBytes(StandardCharsets.UTF_8);
    }

    private static void write(File file, byte[] value) throws Exception {
        try (FileOutputStream output = new FileOutputStream(file, false)) {
            output.write(value);
            output.flush();
            output.getFD().sync();
        }
    }

    private static String sha256(byte[] value) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(value);
        StringBuilder result = new StringBuilder(64);
        for (byte item : digest) {
            result.append(String.format(java.util.Locale.ROOT, "%02x", item & 0xff));
        }
        return result.toString();
    }

    private static void assertEquals(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + ", got " + actual);
        }
    }
}
