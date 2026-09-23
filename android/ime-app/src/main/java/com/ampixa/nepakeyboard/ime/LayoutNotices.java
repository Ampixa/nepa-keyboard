package com.ampixa.nepakeyboard.ime;

import android.content.res.AssetManager;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/** Bounded exact-hash reader for APK-bundled declarative-layout notices. */
final class LayoutNotices {
    private static final String MANIFEST_ASSET = "nepa-layout-notices/manifest.json";
    private static final int MAX_MANIFEST_BYTES = 64 * 1024;
    private static final int MAX_NOTICE_BYTES = 64 * 1024;
    private static final int MAX_LAYOUTS = 128;
    private static final Pattern SHA256 = Pattern.compile("^[0-9a-f]{64}$");
    private static final Pattern NOTICE_ASSET = Pattern.compile(
            "^nepa-layout-notices/[A-Za-z0-9._-]+$"
    );
    private static final Set<String> ROOT_KEYS = setOf(
            "format_version", "layout_lock_sha256", "layouts"
    );
    private static final Set<String> ROW_KEYS = setOf(
            "layout_id", "display_name", "license_id", "copyright",
            "license_url", "notice_asset_path", "notice_sha256", "source_url"
    );

    private LayoutNotices() {
    }

    private static Set<String> setOf(String... values) {
        return Collections.unmodifiableSet(new HashSet<>(Arrays.asList(values)));
    }

    static List<Entry> read(AssetManager assets) throws IOException {
        try {
            byte[] manifestBytes = readBounded(
                    assets.open(MANIFEST_ASSET, AssetManager.ACCESS_STREAMING),
                    MAX_MANIFEST_BYTES
            );
            if (!GeneratedLayoutRegistry.NOTICE_MANIFEST_SHA256.equals(
                    sha256(manifestBytes)
            )) {
                throw new SecurityException("layout notice manifest hash mismatch");
            }
            JSONObject manifest = new JSONObject(decodeUtf8(manifestBytes));
            requireExactKeys(manifest, ROOT_KEYS, "layout notice manifest");
            if (manifest.getInt("format_version") != 1) {
                throw new SecurityException("unsupported layout notice format");
            }
            String layoutLockSha256 = requireSha256(
                    manifest.getString("layout_lock_sha256"),
                    "layout notice lock SHA-256"
            );
            if (!GeneratedLayoutRegistry.LAYOUT_LOCK_SHA256.equals(layoutLockSha256)) {
                throw new SecurityException("layout notice manifest lock mismatch");
            }
            JSONArray rows = manifest.getJSONArray("layouts");
            if (rows.length() > MAX_LAYOUTS
                    || rows.length() != GeneratedLayoutRegistry.LAYOUT_NOTICE_COUNT) {
                throw new SecurityException("layout notice count is outside its bound");
            }
            List<Entry> result = new ArrayList<>();
            Set<String> layoutIds = new HashSet<>();
            Set<String> expectedLayoutIds = new HashSet<>(
                    GeneratedLayoutRegistry.layoutNoticeIds()
            );
            if (expectedLayoutIds.size() != GeneratedLayoutRegistry.LAYOUT_NOTICE_COUNT
                    || !new HashSet<>(GeneratedLayoutRegistry.layoutIds())
                    .containsAll(expectedLayoutIds)) {
                throw new SecurityException("generated layout notice subset is invalid");
            }
            Set<String> noticePaths = new HashSet<>();
            for (int index = 0; index < rows.length(); index++) {
                JSONObject row = rows.getJSONObject(index);
                requireExactKeys(row, ROW_KEYS, "layout notice row");
                String layoutId = requireText(row.getString("layout_id"), "layout ID");
                String noticePath = requireText(
                        row.getString("notice_asset_path"),
                        "layout notice asset path"
                );
                if (!layoutIds.add(layoutId)
                        || !expectedLayoutIds.remove(layoutId)
                        || !noticePaths.add(noticePath)
                        || !NOTICE_ASSET.matcher(noticePath).matches()) {
                    throw new SecurityException("duplicate or unsafe layout notice identity");
                }
                String expectedNoticeSha256 = requireSha256(
                        row.getString("notice_sha256"),
                        "layout notice SHA-256"
                );
                byte[] noticeBytes = readBounded(
                        assets.open(noticePath, AssetManager.ACCESS_STREAMING),
                        MAX_NOTICE_BYTES
                );
                if (!expectedNoticeSha256.equals(sha256(noticeBytes))) {
                    throw new SecurityException("layout notice asset hash mismatch");
                }
                String licenseUrl = row.isNull("license_url")
                        ? null
                        : requireHttps(row.getString("license_url"), "layout license URL");
                String sourceUrl = row.isNull("source_url")
                        ? null
                        : requireHttps(row.getString("source_url"), "layout source URL");
                result.add(new Entry(
                        layoutId,
                        requireText(row.getString("display_name"), "layout display name"),
                        requireText(row.getString("license_id"), "layout license ID"),
                        requireText(row.getString("copyright"), "layout copyright"),
                        licenseUrl,
                        sourceUrl,
                        decodeUtf8(noticeBytes)
                ));
            }
            if (!expectedLayoutIds.isEmpty()) {
                throw new SecurityException("layout notice manifest omits a generated notice");
            }
            return Collections.unmodifiableList(result);
        } catch (JSONException invalidJson) {
            throw new SecurityException("invalid layout notice manifest", invalidJson);
        }
    }

    private static byte[] readBounded(InputStream input, int maximumBytes) throws IOException {
        try (InputStream stream = input) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[Math.min(8192, maximumBytes + 1)];
            while (output.size() <= maximumBytes) {
                int count = stream.read(buffer, 0, Math.min(buffer.length, maximumBytes + 1 - output.size()));
                if (count < 0) {
                    break;
                }
                if (count == 0) {
                    int value = stream.read();
                    if (value < 0) {
                        break;
                    }
                    output.write(value);
                    continue;
                }
                output.write(buffer, 0, count);
            }
            byte[] encoded = output.toByteArray();
            if (encoded.length == 0 || encoded.length > maximumBytes) {
                throw new SecurityException("layout notice asset is empty or oversized");
            }
            return encoded;
        }
    }

    private static String decodeUtf8(byte[] encoded) {
        if (encoded.length >= 3
                && encoded[0] == (byte) 0xef
                && encoded[1] == (byte) 0xbb
                && encoded[2] == (byte) 0xbf) {
            throw new SecurityException("layout notice asset must not contain a UTF-8 BOM");
        }
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(encoded))
                    .toString();
        } catch (CharacterCodingException invalidUtf8) {
            throw new SecurityException("layout notice asset is not UTF-8", invalidUtf8);
        }
    }

    private static void requireExactKeys(JSONObject value, Set<String> expected, String label) {
        Set<String> actual = new HashSet<>();
        Iterator<String> keys = value.keys();
        while (keys.hasNext()) {
            actual.add(keys.next());
        }
        if (!actual.equals(expected)) {
            throw new SecurityException(label + " has unexpected fields");
        }
    }

    private static String requireText(String value, String label) {
        if (value == null || value.trim().isEmpty()) {
            throw new SecurityException(label + " must not be empty");
        }
        return value;
    }

    private static String requireHttps(String value, String label) {
        String checked = requireText(value, label);
        if (!checked.startsWith("https://")) {
            throw new SecurityException(label + " must use HTTPS");
        }
        return checked;
    }

    private static String requireSha256(String value, String label) {
        if (!SHA256.matcher(value).matches()) {
            throw new SecurityException(label + " is invalid");
        }
        return value;
    }

    private static String sha256(byte[] encoded) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(encoded);
            StringBuilder result = new StringBuilder(64);
            for (byte value : digest) {
                result.append(String.format(Locale.ROOT, "%02x", value & 0xff));
            }
            return result.toString();
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }

    static final class Entry {
        private final String layoutId;
        private final String displayName;
        private final String licenseId;
        private final String copyright;
        private final String licenseUrl;
        private final String sourceUrl;
        private final String notice;

        Entry(
                String layoutId,
                String displayName,
                String licenseId,
                String copyright,
                String licenseUrl,
                String sourceUrl,
                String notice
        ) {
            this.layoutId = layoutId;
            this.displayName = displayName;
            this.licenseId = licenseId;
            this.copyright = copyright;
            this.licenseUrl = licenseUrl;
            this.sourceUrl = sourceUrl;
            this.notice = notice;
        }

        String layoutId() {
            return layoutId;
        }

        String displayName() {
            return displayName;
        }

        String licenseId() {
            return licenseId;
        }

        String copyright() {
            return copyright;
        }

        String licenseUrl() {
            return licenseUrl;
        }

        String sourceUrl() {
            return sourceUrl;
        }

        String notice() {
            return notice;
        }
    }
}
