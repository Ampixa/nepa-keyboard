package com.ampixa.nepakeyboard.ime;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import java.io.File;
import java.io.IOException;

/** Public/export variants read provenance only from release packs. */
final class NoticeReaderFactory {
    private NoticeReaderFactory() {
    }

    static NkpBundle.NoticeDocument read(File file, String expectedSha256)
            throws IOException {
        return NkpBundle.readNotices(file, expectedSha256);
    }
}
