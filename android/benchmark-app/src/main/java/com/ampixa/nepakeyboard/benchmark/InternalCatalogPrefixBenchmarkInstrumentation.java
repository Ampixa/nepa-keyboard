package com.ampixa.nepakeyboard.benchmark;

/** Internal-product entry point for the shared exact-catalog prefix benchmark. */
public final class InternalCatalogPrefixBenchmarkInstrumentation
        extends ReleasePrefixBenchmarkInstrumentation {
    @Override
    protected boolean allowInternalPacks() {
        return true;
    }

    @Override
    protected String benchmarkMode() {
        return "internal_catalog_prefix";
    }
}
