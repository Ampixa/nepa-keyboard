package com.ampixa.nepakeyboard.ime;

import java.util.Objects;

/** One-outstanding-callback, generation-guarded delete hold-repeat state. */
final class DeleteRepeatController {
    static final long INITIAL_DELAY_MILLIS = 400L;
    static final long REPEAT_INTERVAL_MILLIS = 60L;
    static final int MAX_DISPATCHES_PER_HOLD = 256;

    interface Scheduler {
        void postDelayed(Runnable runnable, long delayMillis);

        void remove(Runnable runnable);
    }

    interface DeleteCallback {
        void delete();
    }

    private final Scheduler scheduler;
    private long generation;
    private long totalDispatchCount;
    private boolean active;
    private int dispatchCount;
    private Runnable pending;
    private DeleteCallback callback;

    DeleteRepeatController(Scheduler scheduler) {
        this.scheduler = Objects.requireNonNull(scheduler, "scheduler");
    }

    void start(DeleteCallback callback) {
        stop();
        long owner = nextGeneration();
        this.callback = Objects.requireNonNull(callback, "callback");
        active = true;
        dispatchCount = 0;
        dispatch(owner);
        if (active && generation == owner && dispatchCount < MAX_DISPATCHES_PER_HOLD) {
            schedule(owner, INITIAL_DELAY_MILLIS);
        }
    }

    void stop() {
        nextGeneration();
        active = false;
        dispatchCount = 0;
        callback = null;
        Runnable stale = pending;
        pending = null;
        if (stale != null) {
            scheduler.remove(stale);
        }
    }

    boolean isActive() {
        return active;
    }

    int dispatchCount() {
        return dispatchCount;
    }

    long totalDispatchCount() {
        return totalDispatchCount;
    }

    private void schedule(long owner, long delayMillis) {
        Runnable task = new Runnable() {
            @Override
            public void run() {
                if (pending != this || !active || generation != owner) {
                    return;
                }
                pending = null;
                dispatch(owner);
                if (active
                        && generation == owner
                        && dispatchCount < MAX_DISPATCHES_PER_HOLD) {
                    schedule(owner, REPEAT_INTERVAL_MILLIS);
                } else if (generation == owner) {
                    active = false;
                    callback = null;
                }
            }
        };
        pending = task;
        scheduler.postDelayed(task, delayMillis);
    }

    private void dispatch(long owner) {
        if (!active || generation != owner || callback == null) {
            return;
        }
        dispatchCount++;
        totalDispatchCount++;
        try {
            callback.delete();
        } catch (RuntimeException failure) {
            stop();
            throw failure;
        }
    }

    private long nextGeneration() {
        generation = generation == Long.MAX_VALUE ? 1L : generation + 1L;
        return generation;
    }
}
