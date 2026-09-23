package com.ampixa.nepakeyboard.ime;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import java.io.File;
import java.io.IOException;

/** Build-variant boundary for opening a verified on-device language pack. */
@FunctionalInterface
interface PackBundleOpener {
    PackBundleOpener RELEASE_ONLY = NkpBundle::open;

    NkpBundle open(File file, String expectedArtifactSha256) throws IOException;
}
