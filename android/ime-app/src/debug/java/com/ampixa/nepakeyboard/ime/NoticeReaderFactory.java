package com.ampixa.nepakeyboard.ime;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import java.io.File;
import java.io.IOException;

/** Ordinary debug variants retain the public/export notice-reader authority. */
final class NoticeReaderFactory {
    private NoticeReaderFactory() {
    }

    static NkpBundle.NoticeDocument read(File file, String expectedSha256)
            throws IOException {
        return NkpBundle.readNotices(file, expectedSha256);
    }
}
