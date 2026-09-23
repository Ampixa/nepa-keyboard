package com.ampixa.nepakeyboard.ime;

import java.util.concurrent.atomic.AtomicBoolean;

/** Process-local cancellation ownership for one decoder request. */
public final class SuggestionCancellation {
    private final AtomicBoolean cancelled = new AtomicBoolean();

    /** Cancels the request once and reports whether this call changed its state. */
    public boolean cancel() {
        return cancelled.compareAndSet(false, true);
    }

    public boolean isCancelled() {
        return cancelled.get();
    }
}
