package com.ampixa.nepakeyboard.ime;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import java.io.File;
import java.io.IOException;

/** Play candidate provenance reader for the verified full internal catalog. */
final class NoticeReaderFactory {
    private NoticeReaderFactory() {
    }

    static NkpBundle.NoticeDocument read(File file, String expectedSha256)
            throws IOException {
        return NkpBundle.readNoticesForInternalCatalog(file, expectedSha256);
    }
}
