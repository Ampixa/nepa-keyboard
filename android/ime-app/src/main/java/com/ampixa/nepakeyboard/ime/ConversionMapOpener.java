package com.ampixa.nepakeyboard.ime;

import com.ampixa.nepakeyboard.conversion.NcmBundle;

import java.io.File;
import java.io.IOException;

/** Injectable verified NCM opener used by the asynchronous conversion engine. */
interface ConversionMapOpener {
    ConversionMapOpener STRICT = NcmBundle::open;

    NcmBundle open(File file, String expectedSha256) throws IOException;
}
