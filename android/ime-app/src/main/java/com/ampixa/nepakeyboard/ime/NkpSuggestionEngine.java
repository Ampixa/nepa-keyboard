package com.ampixa.nepakeyboard.ime;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.FutureTask;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/**
 * Asynchronous adapter from verified NKP bundles to the IME.
 *
 * <p>The default constructors use only the fail-closed two-argument reader.
 * An internal Android source set may inject a different opener; that opt-in is
 * absent from release and ordinary debug APKs.</p>
 *
 * <p>Pack readiness is reusable profile data, but every field/profile activation
 * receives a fresh identity. Completion callbacks therefore refresh only the
 * current field, including when two successive fields use the same pack.</p>
 */
public final class NkpSuggestionEngine implements SuggestionEngine {
    interface DecodeObserver {
        DecodeObserver NONE = query -> {
        };

        /** Runs on the decoder worker immediately before provider lookup. */
        void beforeLookup(SuggestionQuery query);
    }

    static final String EXACT_PREFIX_PROVIDER = "nkp-exact-prefix";
    static final String SPATIAL_TAP_PROVIDER = "nkp-spatial-tap-v1";
    private static final int MAX_PROVIDER_RESULTS = SuggestionSnapshot.MAX_CANDIDATES - 1;
    private static final int MAX_SPATIAL_ALTERNATIVES_PER_STROKE = 3;
    private static final int MAX_SPATIAL_BEAMS = 16;
    private static final int MAX_SPATIAL_IDS_PER_BEAM = 8;
    private static final int SPATIAL_COST_QUANTUM = 1_024;
    private static final int SPATIAL_TRIE_RANK_PENALTY = 1;
    private static final int SPATIAL_LEXICAL_LOG2_STEP = 512;
    private static final java.util.Set<String> SPATIAL_PROFILE_IDS =
            Collections.unmodifiableSet(new java.util.HashSet<>(Arrays.asList(
                    LanguageRegistry.ENGLISH_ID,
                    LanguageRegistry.NEPALI_DIRECT_ID
            )));

    private final Map<String, ReleasePackSpec> specsByProfile;
    private final Map<String, NkpBundle> bundlesByArtifact = new ConcurrentHashMap<>();
    private final Map<NkpBundle, Integer> bundleLeaseCounts = new IdentityHashMap<>();
    private final java.util.Set<NkpBundle> retiredBundles =
            Collections.newSetFromMap(new IdentityHashMap<>());
    private final Map<String, SuggestionSnapshot.Status> statesByArtifact =
            new ConcurrentHashMap<>();
    private final Map<String, LoadJob> loadingJobsByArtifact = new ConcurrentHashMap<>();
    private final ThreadPoolExecutor loader;
    private final ThreadPoolExecutor decoder;
    private final PackBundleOpener bundleOpener;
    private final StateListener stateListener;
    private final DecodeObserver decodeObserver;
    private final Object bundleLock = new Object();
    private final Object loaderLock = new Object();
    private final Object decoderLock = new Object();
    private LoadJob activeLoadJob;
    private FutureTask<Void> activeLoadTask;
    private SuggestionQuery activeDecodeQuery;
    private FutureTask<Void> activeDecodeTask;
    private volatile Thread lastDecodeThread;
    private volatile SuggestionActivation activeActivation;
    private volatile String activeArtifact;
    private volatile String retainedArtifact;
    private volatile boolean closed;
    private long nextActivationId;

    public NkpSuggestionEngine(List<ReleasePackSpec> specs) {
        this(specs, activation -> {
        }, PackBundleOpener.RELEASE_ONLY);
    }

    public NkpSuggestionEngine(List<ReleasePackSpec> specs, StateListener stateListener) {
        this(specs, stateListener, PackBundleOpener.RELEASE_ONLY);
    }

    NkpSuggestionEngine(
            List<ReleasePackSpec> specs,
            StateListener stateListener,
            PackBundleOpener bundleOpener
    ) {
        this(specs, stateListener, bundleOpener, DecodeObserver.NONE);
    }

    NkpSuggestionEngine(
            List<ReleasePackSpec> specs,
            StateListener stateListener,
            PackBundleOpener bundleOpener,
            DecodeObserver decodeObserver
    ) {
        Map<String, ReleasePackSpec> indexed = new HashMap<>();
        for (ReleasePackSpec spec : specs == null
                ? Collections.<ReleasePackSpec>emptyList()
                : specs) {
            if (indexed.put(spec.profileId(), spec) != null) {
                throw new IllegalArgumentException("duplicate staged pack profile: " + spec.profileId());
            }
        }
        specsByProfile = Collections.unmodifiableMap(indexed);
        this.stateListener = stateListener == null ? activation -> {
        } : stateListener;
        if (bundleOpener == null) {
            throw new IllegalArgumentException("bundleOpener must not be null");
        }
        this.bundleOpener = bundleOpener;
        this.decodeObserver = decodeObserver == null
                ? DecodeObserver.NONE
                : decodeObserver;
        loader = new ThreadPoolExecutor(
                1,
                1,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                runnable -> {
                    Thread thread = new Thread(runnable, "nepa-pack-loader");
                    thread.setDaemon(true);
                    thread.setPriority(Thread.MIN_PRIORITY);
                    return thread;
                },
                new ThreadPoolExecutor.AbortPolicy()
        );
        decoder = new ThreadPoolExecutor(
                1,
                1,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                runnable -> {
                    Thread thread = new Thread(runnable, "nepa-prefix-decoder");
                    thread.setDaemon(true);
                    thread.setPriority(Thread.NORM_PRIORITY - 1);
                    return thread;
                },
                new ThreadPoolExecutor.AbortPolicy()
        );
    }

    @Override
    public SuggestionActivation activate(KeyboardProfile profile) {
        Objects.requireNonNull(profile, "profile");
        ReleasePackSpec spec = exactSpec(profile);
        String nextArtifact = spec == null ? null : spec.cacheKey();
        SuggestionActivation activation;
        synchronized (decoderLock) {
            cancelActiveDecodeLocked();
            if (closed) {
                return newSuspendedActivation();
            }
            activation = newActiveActivation(profile);
            synchronized (bundleLock) {
                // Publish activation/artifact while decoder submission is excluded,
                // so an old request cannot be enqueued across this transition.
                activeActivation = activation;
                activeArtifact = nextArtifact;
                if (nextArtifact == null) {
                    retainedArtifact = null;
                    for (NkpBundle bundle : bundlesByArtifact.values()) {
                        retireBundleLocked(bundle);
                    }
                    bundlesByArtifact.clear();
                    statesByArtifact.clear();
                    return activation;
                }
                retainedArtifact = nextArtifact;
                List<String> staleArtifacts = new ArrayList<>();
                for (Map.Entry<String, NkpBundle> entry : bundlesByArtifact.entrySet()) {
                    if (!entry.getKey().equals(nextArtifact)) {
                        retireBundleLocked(entry.getValue());
                        staleArtifacts.add(entry.getKey());
                    }
                }
                for (String staleArtifact : staleArtifacts) {
                    bundlesByArtifact.remove(staleArtifact);
                    statesByArtifact.remove(staleArtifact);
                }
                for (String stateArtifact : new ArrayList<>(statesByArtifact.keySet())) {
                    if (!stateArtifact.equals(nextArtifact)) {
                        statesByArtifact.remove(stateArtifact);
                    }
                }
            }
        }
        if (!bundlesByArtifact.containsKey(nextArtifact)
                && statesByArtifact.get(nextArtifact) == null) {
            scheduleLoad(spec);
        }
        return activation;
    }

    @Override
    public SuggestionActivation suspend() {
        synchronized (decoderLock) {
            cancelActiveDecodeLocked();
            SuggestionActivation activation = newSuspendedActivation();
            if (closed) {
                return activation;
            }
            synchronized (bundleLock) {
                activeActivation = activation;
                activeArtifact = null;
            }
            return activation;
        }
    }

    @Override
    public SuggestionSnapshot suggest(
            SuggestionActivation activation,
            SuggestionQuery query
    ) {
        Objects.requireNonNull(activation, "activation");
        if (closed
                || activation != activeActivation
                || !activation.isActive()
                || query == null
                || !query.belongsTo(activation)
                || query.privateField()
                || query.composingText().isEmpty()
                || !activation.profileId().equals(query.profileId())
                || !query.profileId().equals(query.profile().id())
                || !query.layoutId().equals(query.profile().layoutId())
                || query.layoutRevision() != query.profile().layoutRevision()
                || !Objects.equals(
                        query.layoutSourceSha256(),
                        query.profile().layoutSourceSha256()
                )
                || !query.profile().isAvailable()) {
            return SuggestionSnapshot.inactive(activation);
        }
        if (query.isBoundedDecoderRequest()) {
            if (!query.isWithinDecoderInputBound()) {
                return SuggestionSnapshot.literalFallback(query);
            }
            if (!query.acceptsProviderResults(System.nanoTime())) {
                return query.cancellation().isCancelled()
                        ? SuggestionSnapshot.inactive(activation)
                        : SuggestionSnapshot.literalFallback(query);
            }
        }

        ReleasePackSpec spec = exactSpec(query.profile());
        if (spec == null) {
            return SuggestionSnapshot.state(
                    activation,
                    query,
                    SuggestionSnapshot.Status.MISSING
            );
        }
        String key = spec.cacheKey();
        if (!key.equals(activeArtifact)) {
            return SuggestionSnapshot.inactive(activation);
        }

        BundleLease bundleLease = acquireBundleLease(key);
        if (bundleLease == null) {
            SuggestionSnapshot.Status status = statesByArtifact.get(key);
            if (status == SuggestionSnapshot.Status.MISSING
                    || status == SuggestionSnapshot.Status.CORRUPT
                    || status == SuggestionSnapshot.Status.UNAVAILABLE) {
                return SuggestionSnapshot.state(activation, query, status);
            }
            return SuggestionSnapshot.state(
                    activation,
                    query,
                    SuggestionSnapshot.Status.LOADING
            );
        }

        List<ProviderResult> providerResults;
        try {
            if (query.profile().lookupKind() == KeyboardProfile.LookupKind.SURFACE_PREFIX) {
                if (SPATIAL_PROFILE_IDS.contains(query.profileId())
                        && query.touchSequence().hasSpatialEvidence()) {
                    providerResults = spatialProviderResults(bundleLease.bundle, query);
                } else {
                    providerResults = exactProviderResults(
                            bundleLease.bundle.suggestSurface(query.composingText()),
                            SuggestionCandidate.Category.EXACT,
                            EXACT_PREFIX_PROVIDER
                    );
                }
            } else if (query.profile().lookupKind() == KeyboardProfile.LookupKind.ALIAS_PREFIX) {
                providerResults = exactProviderResults(
                        bundleLease.bundle.suggestAliases(query.composingText()),
                        SuggestionCandidate.Category.TRANSLITERATION,
                        EXACT_PREFIX_PROVIDER
                );
            } else {
                return SuggestionSnapshot.state(
                        activation,
                        query,
                        SuggestionSnapshot.Status.NO_MATCH
                );
            }
        } finally {
            releaseBundleLease(bundleLease);
        }
        if (query.isBoundedDecoderRequest()) {
            if (!query.acceptsProviderResults(System.nanoTime())) {
                return query.cancellation().isCancelled()
                        ? SuggestionSnapshot.inactive(activation)
                        : SuggestionSnapshot.literalFallback(query);
            }
        }
        if (providerResults.isEmpty()) {
            return SuggestionSnapshot.state(
                    activation,
                    query,
                    SuggestionSnapshot.Status.NO_MATCH
            );
        }
        List<SuggestionCandidate> result = new ArrayList<>(SuggestionSnapshot.MAX_CANDIDATES);
        for (ProviderResult providerResult : providerResults) {
            String surface = providerResult.surface;
            if (surface != null
                    && !surface.isEmpty()
                    && !surface.equals(query.composingText())
                    && !containsText(result, surface)) {
                // Trie order is authoritative. Alias rank deltas participate
                // in that order but are not stored in NKP v0, so publishing
                // the base dictionary score here would be misleading.
                int providerRankScore = MAX_PROVIDER_RESULTS - result.size();
                result.add(SuggestionCandidate.provider(
                        surface,
                        providerResult.category,
                        providerResult.providerId,
                        providerRankScore
                ));
                if (result.size() == MAX_PROVIDER_RESULTS) {
                    break;
                }
            }
        }
        result.add(SuggestionCandidate.literal(query.composingText()));
        return SuggestionSnapshot.decoded(activation, query, result);
    }

    private static List<ProviderResult> exactProviderResults(
            List<NkpBundle.Suggestion> packed,
            SuggestionCandidate.Category category,
            String providerId
    ) {
        if (packed.isEmpty()) {
            return Collections.emptyList();
        }
        List<ProviderResult> result = new ArrayList<>(packed.size());
        for (NkpBundle.Suggestion suggestion : packed) {
            result.add(new ProviderResult(suggestion.surface(), category, providerId));
        }
        return result;
    }

    private static List<ProviderResult> spatialProviderResults(
            NkpBundle bundle,
            SuggestionQuery query
    ) {
        if (isCleanExactTouch(query.touchSequence())) {
            List<ProviderResult> exact = completeCleanExactProviderResults(bundle, query);
            if (exact != null) {
                return exact;
            }
        }
        Map<String, SpatialHit> bestBySurface = new HashMap<>();
        for (SpatialBeam beam : buildSpatialBeams(query.touchSequence(), query.composingText())) {
            int[] candidateIds = bundle.lookupSurfaceIds(beam.text);
            int limit = Math.min(candidateIds.length, MAX_SPATIAL_IDS_PER_BEAM);
            for (int rank = 0; rank < limit; rank++) {
                int candidateId = candidateIds[rank];
                String surface = bundle.candidateSurface(candidateId);
                SpatialHit hit = new SpatialHit(
                        surface,
                        beam.cost,
                        rank,
                        bundle.candidateScore(candidateId),
                        !beam.text.equals(query.composingText()),
                        beam.exactPath && beam.cost == 0
                );
                SpatialHit previous = bestBySurface.get(surface);
                if (previous == null || SpatialHit.ORDER.compare(hit, previous) < 0) {
                    bestBySurface.put(surface, hit);
                }
            }
        }
        if (bestBySurface.isEmpty()) {
            return Collections.emptyList();
        }
        List<SpatialHit> ranked = new ArrayList<>(bestBySurface.values());
        ranked.sort(SpatialHit.ORDER);
        List<ProviderResult> result = new ArrayList<>(ranked.size());
        for (SpatialHit hit : ranked) {
            result.add(new ProviderResult(
                    hit.surface,
                    hit.corrected
                            ? SuggestionCandidate.Category.CORRECTION
                            : SuggestionCandidate.Category.EXACT,
                    SPATIAL_TAP_PROVIDER
            ));
        }
        return result;
    }

    private static List<ProviderResult> completeCleanExactProviderResults(
            NkpBundle bundle,
            SuggestionQuery query
    ) {
        int[] candidateIds = bundle.lookupSurfaceIds(query.composingText());
        int limit = Math.min(candidateIds.length, MAX_SPATIAL_IDS_PER_BEAM);
        List<SpatialHit> ranked = new ArrayList<>(limit);
        java.util.Set<String> publishable = new java.util.HashSet<>();
        for (int rank = 0; rank < limit; rank++) {
            int candidateId = candidateIds[rank];
            String surface = bundle.candidateSurface(candidateId);
            ranked.add(new SpatialHit(
                    surface,
                    0,
                    rank,
                    bundle.candidateScore(candidateId),
                    false,
                    true
            ));
            if (!surface.equals(query.composingText())) {
                publishable.add(surface);
            }
        }
        if (publishable.size() < MAX_PROVIDER_RESULTS) {
            return null;
        }
        ranked.sort(SpatialHit.ORDER);
        List<ProviderResult> result = new ArrayList<>(ranked.size());
        for (SpatialHit hit : ranked) {
            result.add(new ProviderResult(
                    hit.surface,
                    SuggestionCandidate.Category.EXACT,
                    SPATIAL_TAP_PROVIDER
            ));
        }
        return result;
    }

    private static boolean isCleanExactTouch(TouchSequence touchSequence) {
        if (touchSequence.isEmpty()) {
            return false;
        }
        for (SpatialKeyStroke stroke : touchSequence.strokes()) {
            if (!stroke.hasSpatialEvidence()) {
                return false;
            }
            SpatialKeyStroke.Alternative selected = stroke.alternatives(1).get(0);
            if (!selected.exactKey() || selected.spatialCost() != 0) {
                return false;
            }
        }
        return true;
    }

    private static List<SpatialBeam> buildSpatialBeams(
            TouchSequence touchSequence,
            String exactText
    ) {
        List<SpatialBeam> beams = Collections.singletonList(new SpatialBeam("", 0, true));
        for (SpatialKeyStroke stroke : touchSequence.strokes()) {
            List<SpatialKeyStroke.Alternative> strokeAlternatives = stroke.alternatives(
                    MAX_SPATIAL_ALTERNATIVES_PER_STROKE
            );
            Map<String, SpatialBeam> bestByText = new HashMap<>();
            for (SpatialBeam beam : beams) {
                for (SpatialKeyStroke.Alternative alternative : strokeAlternatives) {
                    SpatialBeam expanded = new SpatialBeam(
                            beam.text + alternative.text(),
                            saturatedCost(beam.cost, alternative.spatialCost()),
                            beam.exactPath && alternative.exactKey()
                    );
                    SpatialBeam previous = bestByText.get(expanded.text);
                    if (previous == null || SpatialBeam.ORDER.compare(expanded, previous) < 0) {
                        bestByText.put(expanded.text, expanded);
                    }
                }
            }
            List<SpatialBeam> ranked = new ArrayList<>(bestByText.values());
            ranked.sort(SpatialBeam.ORDER);
            SpatialBeam exactBeam = null;
            for (SpatialBeam beam : ranked) {
                if (beam.exactPath) {
                    exactBeam = beam;
                    break;
                }
            }
            if (ranked.size() > MAX_SPATIAL_BEAMS) {
                ranked = new ArrayList<>(ranked.subList(0, MAX_SPATIAL_BEAMS));
                if (exactBeam != null && !ranked.contains(exactBeam)) {
                    ranked.set(ranked.size() - 1, exactBeam);
                    ranked.sort(SpatialBeam.ORDER);
                }
            }
            beams = ranked;
        }
        boolean foundExact = false;
        for (SpatialBeam beam : beams) {
            if (beam.text.equals(exactText)) {
                foundExact = true;
                break;
            }
        }
        if (!foundExact) {
            throw new IllegalStateException("spatial beam lost the literal key path");
        }
        return Collections.unmodifiableList(beams);
    }

    static int spatialBeamCountForTesting(
            TouchSequence touchSequence,
            String exactText
    ) {
        return buildSpatialBeams(touchSequence, exactText).size();
    }

    static boolean isCleanExactTouchForTesting(TouchSequence touchSequence) {
        return isCleanExactTouch(touchSequence);
    }

    static int maxSpatialBeamsForTesting() {
        return MAX_SPATIAL_BEAMS;
    }

    static long spatialJointScoreForTesting(
            int candidateScore,
            int spatialCost,
            int trieRank
    ) {
        return spatialJointScore(candidateScore, spatialCost, trieRank);
    }

    private static long spatialJointScore(
            int candidateScore,
            int spatialCost,
            int trieRank
    ) {
        if (spatialCost < 0 || trieRank < 0) {
            throw new IllegalArgumentException("spatial cost and trie rank must be non-negative");
        }
        long spatialPenalty = ((long) spatialCost + SPATIAL_COST_QUANTUM / 2L)
                / SPATIAL_COST_QUANTUM;
        return normalizedLexicalScore(candidateScore)
                - spatialPenalty
                - (long) trieRank * SPATIAL_TRIE_RANK_PENALTY;
    }

    private static long normalizedLexicalScore(int candidateScore) {
        if (candidateScore == 0) {
            return 0L;
        }
        long magnitude = Math.abs((long) candidateScore);
        int log2Bucket = Long.SIZE - Long.numberOfLeadingZeros(magnitude);
        long normalized = (long) log2Bucket * SPATIAL_LEXICAL_LOG2_STEP;
        return candidateScore > 0 ? normalized : -normalized;
    }

    private static int saturatedCost(int first, int second) {
        long total = (long) first + second;
        return total >= Integer.MAX_VALUE ? Integer.MAX_VALUE : (int) total;
    }

    private static final class ProviderResult {
        final String surface;
        final SuggestionCandidate.Category category;
        final String providerId;

        ProviderResult(
                String surface,
                SuggestionCandidate.Category category,
                String providerId
        ) {
            this.surface = surface;
            this.category = category;
            this.providerId = providerId;
        }
    }

    private static final class SpatialBeam {
        static final Comparator<SpatialBeam> ORDER = (first, second) -> {
            int byCost = Integer.compare(first.cost, second.cost);
            if (byCost != 0) {
                return byCost;
            }
            int byExact = Boolean.compare(!first.exactPath, !second.exactPath);
            if (byExact != 0) {
                return byExact;
            }
            return first.text.compareTo(second.text);
        };

        final String text;
        final int cost;
        final boolean exactPath;

        SpatialBeam(String text, int cost, boolean exactPath) {
            this.text = text;
            this.cost = cost;
            this.exactPath = exactPath;
        }
    }

    private static final class SpatialHit {
        static final Comparator<SpatialHit> ORDER = (first, second) -> {
            int byCleanExact = Boolean.compare(
                    !first.cleanExactPath,
                    !second.cleanExactPath
            );
            if (byCleanExact != 0) {
                return byCleanExact;
            }
            int byJointScore = Long.compare(second.jointScore, first.jointScore);
            if (byJointScore != 0) {
                return byJointScore;
            }
            int byCorrection = Boolean.compare(first.corrected, second.corrected);
            if (byCorrection != 0) {
                return byCorrection;
            }
            int byCost = Integer.compare(first.spatialCost, second.spatialCost);
            if (byCost != 0) {
                return byCost;
            }
            int byTrieRank = Integer.compare(first.trieRank, second.trieRank);
            if (byTrieRank != 0) {
                return byTrieRank;
            }
            int byCandidateScore = Integer.compare(
                    second.candidateScore,
                    first.candidateScore
            );
            if (byCandidateScore != 0) {
                return byCandidateScore;
            }
            return first.surface.compareTo(second.surface);
        };

        final String surface;
        final int spatialCost;
        final int trieRank;
        final int candidateScore;
        final boolean corrected;
        final boolean cleanExactPath;
        final long jointScore;

        SpatialHit(
                String surface,
                int spatialCost,
                int trieRank,
                int candidateScore,
                boolean corrected,
                boolean cleanExactPath
        ) {
            this.surface = surface;
            this.spatialCost = spatialCost;
            this.trieRank = trieRank;
            this.candidateScore = candidateScore;
            this.corrected = corrected;
            this.cleanExactPath = cleanExactPath;
            this.jointScore = spatialJointScore(candidateScore, spatialCost, trieRank);
        }
    }

    @Override
    public SubmitOutcome submit(
            SuggestionQuery query,
            ResultListener listener
    ) {
        if (query == null || listener == null) {
            throw new IllegalArgumentException("query and listener are required");
        }
        if (!query.isBoundedDecoderRequest()
                || !query.isWithinDecoderInputBound()
                || query.privateField()
                || query.cancellation().isCancelled()
                || query.isExpired(System.nanoTime())) {
            return SubmitOutcome.STALE;
        }
        synchronized (decoderLock) {
            if (closed || decoder.isShutdown()) {
                return SubmitOutcome.CLOSED;
            }
            if (query.activation() != activeActivation) {
                return SubmitOutcome.STALE;
            }
            cancelActiveDecodeLocked();
            FutureTask<Void> task = new FutureTask<>(() -> {
                runDecode(query, listener);
                return null;
            });
            activeDecodeQuery = query;
            activeDecodeTask = task;
            try {
                decoder.execute(task);
                return SubmitOutcome.ACCEPTED;
            } catch (RejectedExecutionException saturatedOrClosed) {
                if (activeDecodeTask == task) {
                    activeDecodeTask = null;
                    activeDecodeQuery = null;
                }
                task.cancel(true);
                return decoder.isShutdown()
                        ? SubmitOutcome.CLOSED
                        : SubmitOutcome.SATURATED;
            }
        }
    }

    @Override
    public void cancel(SuggestionQuery query) {
        SuggestionEngine.super.cancel(query);
        synchronized (decoderLock) {
            if (query != null && activeDecodeQuery == query) {
                cancelActiveDecodeLocked();
            }
        }
    }

    @Override
    public boolean retry(SuggestionActivation activation) {
        if (closed
                || activation == null
                || activation != activeActivation
                || !activation.isActive()) {
            return false;
        }
        KeyboardProfile profile = LanguageRegistry.find(activation.profileId());
        ReleasePackSpec spec = profile == null ? null : exactSpec(profile);
        if (spec == null
                || !spec.cacheKey().equals(activeArtifact)
                || statesByArtifact.get(spec.cacheKey())
                != SuggestionSnapshot.Status.UNAVAILABLE) {
            return false;
        }
        statesByArtifact.remove(spec.cacheKey(), SuggestionSnapshot.Status.UNAVAILABLE);
        if (!scheduleLoad(spec)) {
            statesByArtifact.put(spec.cacheKey(), SuggestionSnapshot.Status.UNAVAILABLE);
            return false;
        }
        return true;
    }

    @Override
    public void close() {
        closed = true;
        synchronized (decoderLock) {
            cancelActiveDecodeLocked();
        }
        decoder.shutdownNow();
        synchronized (loaderLock) {
            cancelActiveLoadLocked();
        }
        loader.shutdownNow();
        synchronized (bundleLock) {
            activeArtifact = null;
            activeActivation = null;
            retainedArtifact = null;
            for (NkpBundle bundle : bundlesByArtifact.values()) {
                retireBundleLocked(bundle);
            }
            bundlesByArtifact.clear();
            statesByArtifact.clear();
        }
        loadingJobsByArtifact.clear();
    }

    int queuedDecodeCountForTesting() {
        return decoder.getQueue().size();
    }

    Thread lastDecodeThreadForTesting() {
        return lastDecodeThread;
    }

    private void runDecode(
            SuggestionQuery query,
            ResultListener listener
    ) {
        lastDecodeThread = Thread.currentThread();
        SuggestionSnapshot snapshot;
        try {
            decodeObserver.beforeLookup(query);
            snapshot = suggest(query);
        } catch (RuntimeException providerFailure) {
            snapshot = SuggestionSnapshot.literalFallback(query);
        }
        boolean deliver;
        synchronized (decoderLock) {
            deliver = !closed
                    && activeDecodeQuery == query
                    && query.activation() == activeActivation
                    && !query.cancellation().isCancelled();
            if (activeDecodeQuery == query) {
                activeDecodeQuery = null;
                activeDecodeTask = null;
            }
        }
        if (deliver) {
            listener.onResult(query, snapshot);
        }
    }

    private void cancelActiveDecodeLocked() {
        SuggestionQuery query = activeDecodeQuery;
        FutureTask<Void> task = activeDecodeTask;
        activeDecodeQuery = null;
        activeDecodeTask = null;
        if (query != null) {
            query.cancellation().cancel();
        }
        if (task != null) {
            task.cancel(true);
            decoder.remove(task);
            decoder.purge();
        }
    }

    private BundleLease acquireBundleLease(String artifact) {
        synchronized (bundleLock) {
            if (closed || !artifact.equals(activeArtifact)) {
                return null;
            }
            NkpBundle bundle = bundlesByArtifact.get(artifact);
            if (bundle == null || retiredBundles.contains(bundle)) {
                return null;
            }
            bundleLeaseCounts.put(bundle, bundleLeaseCounts.getOrDefault(bundle, 0) + 1);
            return new BundleLease(bundle);
        }
    }

    private void releaseBundleLease(BundleLease lease) {
        synchronized (bundleLock) {
            Integer count = bundleLeaseCounts.get(lease.bundle);
            if (count == null || count <= 0) {
                throw new IllegalStateException("bundle lease accounting is inconsistent");
            }
            if (count == 1) {
                bundleLeaseCounts.remove(lease.bundle);
                if (retiredBundles.remove(lease.bundle)) {
                    lease.bundle.close();
                }
            } else {
                bundleLeaseCounts.put(lease.bundle, count - 1);
            }
        }
    }

    private void retireBundleLocked(NkpBundle bundle) {
        if (bundleLeaseCounts.containsKey(bundle)) {
            retiredBundles.add(bundle);
        } else {
            bundle.close();
        }
    }

    private static final class BundleLease {
        final NkpBundle bundle;

        BundleLease(NkpBundle bundle) {
            this.bundle = bundle;
        }
    }

    private ReleasePackSpec exactSpec(KeyboardProfile profile) {
        if (!profile.isAvailable()) {
            return null;
        }
        ReleasePackSpec spec = specsByProfile.get(profile.id());
        return spec != null && spec.packId().equals(profile.packBinding()) ? spec : null;
    }

    private static boolean containsText(
            List<SuggestionCandidate> candidates,
            String text
    ) {
        for (SuggestionCandidate candidate : candidates) {
            if (candidate.text().equals(text)) {
                return true;
            }
        }
        return false;
    }

    private synchronized long nextActivationId() {
        if (nextActivationId == Long.MAX_VALUE) {
            throw new IllegalStateException("suggestion activation space exhausted");
        }
        nextActivationId++;
        return nextActivationId;
    }

    private SuggestionActivation newActiveActivation(KeyboardProfile profile) {
        return SuggestionActivation.active(nextActivationId(), profile);
    }

    private SuggestionActivation newSuspendedActivation() {
        return SuggestionActivation.suspended(nextActivationId());
    }

    private boolean scheduleLoad(ReleasePackSpec spec) {
        String key = spec.cacheKey();
        synchronized (loaderLock) {
            if (closed
                    || loader.isShutdown()
                    || bundlesByArtifact.containsKey(key)
                    || loadingJobsByArtifact.containsKey(key)) {
                return false;
            }
            cancelActiveLoadLocked();
            LoadJob job = new LoadJob(key);
            if (loadingJobsByArtifact.putIfAbsent(key, job) != null) {
                return false;
            }
            statesByArtifact.put(key, SuggestionSnapshot.Status.LOADING);
            FutureTask<Void> task = new FutureTask<>(() -> {
                runLoad(spec, job);
                return null;
            });
            activeLoadJob = job;
            activeLoadTask = task;
            try {
                loader.execute(task);
                return true;
            } catch (RejectedExecutionException closedDuringSchedule) {
                if (activeLoadJob == job && activeLoadTask == task) {
                    activeLoadJob = null;
                    activeLoadTask = null;
                }
                task.cancel(true);
                if (loadingJobsByArtifact.remove(key, job)) {
                    statesByArtifact.remove(key, SuggestionSnapshot.Status.LOADING);
                }
                return false;
            }
        }
    }

    private void runLoad(ReleasePackSpec spec, LoadJob job) {
        try {
            load(spec, job);
        } finally {
            synchronized (loaderLock) {
                completeLoadOwnershipLocked(job);
            }
        }
    }

    private void cancelActiveLoadLocked() {
        LoadJob job = activeLoadJob;
        FutureTask<Void> task = activeLoadTask;
        activeLoadJob = null;
        activeLoadTask = null;
        if (job != null && loadingJobsByArtifact.remove(job.key, job)) {
            statesByArtifact.remove(job.key, SuggestionSnapshot.Status.LOADING);
        }
        if (task != null) {
            task.cancel(true);
            loader.remove(task);
            loader.purge();
        }
    }

    private void load(ReleasePackSpec spec, LoadJob job) {
        String key = spec.cacheKey();
        NkpBundle opened = null;
        SuggestionSnapshot.Status outcome;
        try {
            File materialized = spec.materialize();
            if (!materialized.isFile()) {
                outcome = SuggestionSnapshot.Status.MISSING;
            } else {
                opened = bundleOpener.open(materialized, spec.artifactSha256());
                if (opened == null) {
                    throw new IOException("bundle opener returned no bundle");
                }
                if (!spec.packId().equals(opened.packId())) {
                    opened.close();
                    opened = null;
                    throw new SecurityException("pack ID mismatch");
                }
                outcome = SuggestionSnapshot.Status.READY;
            }
        } catch (SecurityException failure) {
            if (opened != null) {
                opened.close();
                opened = null;
            }
            outcome = SuggestionSnapshot.Status.CORRUPT;
        } catch (IOException failure) {
            if (opened != null) {
                opened.close();
                opened = null;
            }
            outcome = SuggestionSnapshot.Status.UNAVAILABLE;
        } catch (RuntimeException failure) {
            if (opened != null) {
                opened.close();
                opened = null;
            }
            outcome = SuggestionSnapshot.Status.UNAVAILABLE;
        }

        SuggestionActivation callbackActivation = null;
        synchronized (loaderLock) {
            boolean ownsLoad = loadingJobsByArtifact.get(key) == job;
            if (ownsLoad) {
                // Release exact job ownership before terminal readiness becomes
                // observable, so an immediate retry cannot be rejected as busy.
                completeLoadOwnershipLocked(job);
            }
            synchronized (bundleLock) {
                if (!ownsLoad || closed || !key.equals(retainedArtifact)) {
                    if (opened != null) {
                        opened.close();
                    }
                    if (!loadingJobsByArtifact.containsKey(key)) {
                        statesByArtifact.remove(key);
                    }
                } else {
                    if (opened != null) {
                        NkpBundle previous = bundlesByArtifact.put(key, opened);
                        if (previous != null && previous != opened) {
                            retireBundleLocked(previous);
                        }
                    }
                    statesByArtifact.put(key, outcome);
                    SuggestionActivation current = activeActivation;
                    if (key.equals(activeArtifact)
                            && current != null
                            && current.isActive()) {
                        callbackActivation = current;
                    }
                }
            }
        }
        if (callbackActivation != null && !closed) {
            stateListener.onStateChanged(callbackActivation);
        }
    }

    private void completeLoadOwnershipLocked(LoadJob job) {
        loadingJobsByArtifact.remove(job.key, job);
        if (activeLoadJob == job) {
            activeLoadJob = null;
            activeLoadTask = null;
        }
    }

    /** Identity token prevents a cancelled A load from owning a later A load. */
    private static final class LoadJob {
        final String key;

        LoadJob(String key) {
            this.key = key;
        }
    }
}
