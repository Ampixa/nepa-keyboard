package com.ampixa.nepakeyboard.ime;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import java.io.File;
import java.io.IOException;

/** Internal variant reads verified provenance from every internal-catalog pack. */
final class NoticeReaderFactory {
    private NoticeReaderFactory() {
    }

    static NkpBundle.NoticeDocument read(File file, String expectedSha256)
            throws IOException {
        return NkpBundle.readNoticesForInternalCatalog(file, expectedSha256);
    }
}
