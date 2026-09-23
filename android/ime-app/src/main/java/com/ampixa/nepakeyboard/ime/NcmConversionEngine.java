package com.ampixa.nepakeyboard.ime;

import com.ampixa.nepakeyboard.conversion.NcmBundle;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.FutureTask;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** Asynchronous, activation-safe adapter from verified NCM maps to the IME. */
public final class NcmConversionEngine implements SuggestionEngine {
    interface DecodeObserver {
        DecodeObserver NONE = query -> {
        };

        void beforeConversion(SuggestionQuery query);
    }

    static final String CONVERSION_PROVIDER = "ncm-script-conversion-v1";

    private final Map<String, ConversionMapSpec> specsByProfile;
    private final Map<String, NcmBundle> bundlesByArtifact = new ConcurrentHashMap<>();
    private final Map<NcmBundle, Integer> leaseCounts = new IdentityHashMap<>();
    private final java.util.Set<NcmBundle> retiredBundles =
            Collections.newSetFromMap(new IdentityHashMap<>());
    private final Map<String, SuggestionSnapshot.Status> statesByArtifact =
            new ConcurrentHashMap<>();
    private final Map<String, LoadJob> loadingJobsByArtifact = new ConcurrentHashMap<>();
    private final ThreadPoolExecutor loader;
    private final ThreadPoolExecutor decoder;
    private final StateListener stateListener;
    private final ConversionMapOpener opener;
    private final DecodeObserver decodeObserver;
    private final Object loaderLock = new Object();
    private final Object decoderLock = new Object();
    private final Object bundleLock = new Object();
    private LoadJob activeLoadJob;
    private FutureTask<Void> activeLoadTask;
    private SuggestionQuery activeDecodeQuery;
    private FutureTask<Void> activeDecodeTask;
    private volatile SuggestionActivation activeActivation;
    private volatile String activeArtifact;
    private volatile String retainedArtifact;
    private volatile Thread lastDecodeThread;
    private volatile boolean closed;
    private long nextActivationId;

    public NcmConversionEngine(List<ConversionMapSpec> specs) {
        this(specs, activation -> {
        });
    }

    public NcmConversionEngine(
            List<ConversionMapSpec> specs,
            StateListener stateListener
    ) {
        this(specs, stateListener, ConversionMapOpener.STRICT, DecodeObserver.NONE);
    }

    NcmConversionEngine(
            List<ConversionMapSpec> specs,
            StateListener stateListener,
            ConversionMapOpener opener,
            DecodeObserver decodeObserver
    ) {
        Map<String, ConversionMapSpec> indexed = new HashMap<>();
        for (ConversionMapSpec spec : specs == null
                ? Collections.<ConversionMapSpec>emptyList()
                : specs) {
            if (indexed.put(spec.profileId(), spec) != null) {
                throw new IllegalArgumentException(
                        "duplicate staged conversion profile: " + spec.profileId()
                );
            }
        }
        specsByProfile = Collections.unmodifiableMap(indexed);
        this.stateListener = stateListener == null ? activation -> {
        } : stateListener;
        this.opener = Objects.requireNonNull(opener, "opener");
        this.decodeObserver = decodeObserver == null ? DecodeObserver.NONE : decodeObserver;
        loader = executor("nepa-conversion-loader", Thread.MIN_PRIORITY);
        decoder = executor("nepa-conversion-decoder", Thread.NORM_PRIORITY - 1);
    }

    private static ThreadPoolExecutor executor(String name, int priority) {
        return new ThreadPoolExecutor(
                1,
                1,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                runnable -> {
                    Thread thread = new Thread(runnable, name);
                    thread.setDaemon(true);
                    thread.setPriority(priority);
                    return thread;
                },
                new ThreadPoolExecutor.AbortPolicy()
        );
    }

    @Override
    public SuggestionActivation activate(KeyboardProfile profile) {
        Objects.requireNonNull(profile, "profile");
        ConversionMapSpec spec = exactSpec(profile);
        String nextArtifact = spec == null ? null : spec.cacheKey();
        SuggestionActivation activation;
        synchronized (decoderLock) {
            cancelActiveDecodeLocked();
            if (closed) {
                return newSuspendedActivation();
            }
            activation = SuggestionActivation.active(nextActivationId(), profile);
            synchronized (bundleLock) {
                activeActivation = activation;
                activeArtifact = nextArtifact;
                retainedArtifact = nextArtifact;
                List<String> stale = new ArrayList<>();
                for (Map.Entry<String, NcmBundle> entry : bundlesByArtifact.entrySet()) {
                    if (!entry.getKey().equals(nextArtifact)) {
                        retireBundleLocked(entry.getValue());
                        stale.add(entry.getKey());
                    }
                }
                for (String key : stale) {
                    bundlesByArtifact.remove(key);
                    statesByArtifact.remove(key);
                }
                for (String key : new ArrayList<>(statesByArtifact.keySet())) {
                    if (!key.equals(nextArtifact)) {
                        statesByArtifact.remove(key);
                    }
                }
            }
        }
        if (nextArtifact != null
                && !bundlesByArtifact.containsKey(nextArtifact)
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
            if (!closed) {
                synchronized (bundleLock) {
                    activeActivation = activation;
                    activeArtifact = null;
                }
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
                || query.profile() == null
                || !query.profile().isAvailable()
                || query.profile().artifactKind() != KeyboardProfile.ArtifactKind.NCM
                || query.profile().lookupKind() != KeyboardProfile.LookupKind.CONVERSION
                || !"converter".equals(query.profile().engineKind())) {
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
        ConversionMapSpec spec = exactSpec(query.profile());
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
        BundleLease lease = acquireLease(key);
        if (lease == null) {
            SuggestionSnapshot.Status state = statesByArtifact.get(key);
            if (state == SuggestionSnapshot.Status.MISSING
                    || state == SuggestionSnapshot.Status.CORRUPT
                    || state == SuggestionSnapshot.Status.UNAVAILABLE) {
                return SuggestionSnapshot.state(activation, query, state);
            }
            return SuggestionSnapshot.state(
                    activation,
                    query,
                    SuggestionSnapshot.Status.LOADING
            );
        }
        String converted;
        try {
            converted = lease.bundle.convert(query.composingText());
        } finally {
            releaseLease(lease);
        }
        if (query.isBoundedDecoderRequest()
                && !query.acceptsProviderResults(System.nanoTime())) {
            return query.cancellation().isCancelled()
                    ? SuggestionSnapshot.inactive(activation)
                    : SuggestionSnapshot.literalFallback(query);
        }
        if (converted == null || converted.equals(query.composingText())) {
            return SuggestionSnapshot.state(
                    activation,
                    query,
                    SuggestionSnapshot.Status.NO_MATCH
            );
        }
        List<SuggestionCandidate> candidates = new ArrayList<>(2);
        candidates.add(SuggestionCandidate.provider(
                converted,
                SuggestionCandidate.Category.CONVERSION,
                CONVERSION_PROVIDER,
                1
        ));
        candidates.add(SuggestionCandidate.literal(query.composingText()));
        return SuggestionSnapshot.decoded(activation, query, candidates);
    }

    @Override
    public SubmitOutcome submit(SuggestionQuery query, ResultListener listener) {
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
                return decoder.isShutdown() ? SubmitOutcome.CLOSED : SubmitOutcome.SATURATED;
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
        ConversionMapSpec spec = profile == null ? null : exactSpec(profile);
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
            for (NcmBundle bundle : bundlesByArtifact.values()) {
                retireBundleLocked(bundle);
            }
            bundlesByArtifact.clear();
            statesByArtifact.clear();
        }
        loadingJobsByArtifact.clear();
    }

    Thread lastDecodeThreadForTesting() {
        return lastDecodeThread;
    }

    private void runDecode(SuggestionQuery query, ResultListener listener) {
        lastDecodeThread = Thread.currentThread();
        SuggestionSnapshot snapshot;
        try {
            decodeObserver.beforeConversion(query);
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

    private ConversionMapSpec exactSpec(KeyboardProfile profile) {
        if (!profile.isAvailable()
                || profile.artifactKind() != KeyboardProfile.ArtifactKind.NCM
                || profile.lookupKind() != KeyboardProfile.LookupKind.CONVERSION
                || !"converter".equals(profile.engineKind())) {
            return null;
        }
        ConversionMapSpec spec = specsByProfile.get(profile.id());
        return spec != null && spec.converterId().equals(profile.conversionBinding())
                ? spec
                : null;
    }

    private BundleLease acquireLease(String key) {
        synchronized (bundleLock) {
            if (closed || !key.equals(activeArtifact)) {
                return null;
            }
            NcmBundle bundle = bundlesByArtifact.get(key);
            if (bundle == null || retiredBundles.contains(bundle)) {
                return null;
            }
            leaseCounts.put(bundle, leaseCounts.getOrDefault(bundle, 0) + 1);
            return new BundleLease(bundle);
        }
    }

    private void releaseLease(BundleLease lease) {
        synchronized (bundleLock) {
            Integer count = leaseCounts.get(lease.bundle);
            if (count == null || count <= 0) {
                throw new IllegalStateException("conversion bundle lease is inconsistent");
            }
            if (count == 1) {
                leaseCounts.remove(lease.bundle);
                if (retiredBundles.remove(lease.bundle)) {
                    lease.bundle.close();
                }
            } else {
                leaseCounts.put(lease.bundle, count - 1);
            }
        }
    }

    private void retireBundleLocked(NcmBundle bundle) {
        if (leaseCounts.containsKey(bundle)) {
            retiredBundles.add(bundle);
        } else {
            bundle.close();
        }
    }

    private boolean scheduleLoad(ConversionMapSpec spec) {
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
            loadingJobsByArtifact.put(key, job);
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
                activeLoadJob = null;
                activeLoadTask = null;
                loadingJobsByArtifact.remove(key, job);
                statesByArtifact.remove(key, SuggestionSnapshot.Status.LOADING);
                task.cancel(true);
                return false;
            }
        }
    }

    private void runLoad(ConversionMapSpec spec, LoadJob job) {
        try {
            load(spec, job);
        } finally {
            synchronized (loaderLock) {
                completeLoadOwnershipLocked(job);
            }
        }
    }

    private void load(ConversionMapSpec spec, LoadJob job) {
        String key = spec.cacheKey();
        NcmBundle opened = null;
        SuggestionSnapshot.Status outcome;
        try {
            File materialized = spec.materialize();
            if (!materialized.isFile()) {
                outcome = SuggestionSnapshot.Status.MISSING;
            } else {
                opened = opener.open(materialized, spec.artifactSha256());
                if (opened == null) {
                    throw new IOException("conversion opener returned no map");
                }
                if (!spec.converterId().equals(opened.converterId())) {
                    opened.close();
                    opened = null;
                    throw new SecurityException("conversion ID mismatch");
                }
                outcome = SuggestionSnapshot.Status.READY;
            }
        } catch (SecurityException invalidHashOrIdentity) {
            if (opened != null) {
                opened.close();
                opened = null;
            }
            outcome = SuggestionSnapshot.Status.CORRUPT;
        } catch (IOException | RuntimeException unavailable) {
            if (opened != null) {
                opened.close();
                opened = null;
            }
            outcome = SuggestionSnapshot.Status.UNAVAILABLE;
        }

        SuggestionActivation callback = null;
        synchronized (loaderLock) {
            boolean owns = loadingJobsByArtifact.get(key) == job;
            if (owns) {
                completeLoadOwnershipLocked(job);
            }
            synchronized (bundleLock) {
                if (!owns || closed || !key.equals(retainedArtifact)) {
                    if (opened != null) {
                        opened.close();
                    }
                    if (!loadingJobsByArtifact.containsKey(key)) {
                        statesByArtifact.remove(key);
                    }
                } else {
                    if (opened != null) {
                        NcmBundle previous = bundlesByArtifact.put(key, opened);
                        if (previous != null && previous != opened) {
                            retireBundleLocked(previous);
                        }
                    }
                    statesByArtifact.put(key, outcome);
                    if (key.equals(activeArtifact)
                            && activeActivation != null
                            && activeActivation.isActive()) {
                        callback = activeActivation;
                    }
                }
            }
        }
        if (callback != null && !closed) {
            stateListener.onStateChanged(callback);
        }
    }

    private void cancelActiveLoadLocked() {
        LoadJob job = activeLoadJob;
        FutureTask<Void> task = activeLoadTask;
        activeLoadJob = null;
        activeLoadTask = null;
        if (job != null) {
            loadingJobsByArtifact.remove(job.key, job);
            statesByArtifact.remove(job.key, SuggestionSnapshot.Status.LOADING);
        }
        if (task != null) {
            task.cancel(true);
            loader.remove(task);
            loader.purge();
        }
    }

    private void completeLoadOwnershipLocked(LoadJob job) {
        loadingJobsByArtifact.remove(job.key, job);
        if (activeLoadJob == job) {
            activeLoadJob = null;
            activeLoadTask = null;
        }
    }

    private synchronized long nextActivationId() {
        if (nextActivationId == Long.MAX_VALUE) {
            throw new IllegalStateException("conversion activation space exhausted");
        }
        return ++nextActivationId;
    }

    private SuggestionActivation newSuspendedActivation() {
        return SuggestionActivation.suspended(nextActivationId());
    }

    private static final class BundleLease {
        final NcmBundle bundle;

        BundleLease(NcmBundle bundle) {
            this.bundle = bundle;
        }
    }

    private static final class LoadJob {
        final String key;

        LoadJob(String key) {
            this.key = key;
        }
    }
}
