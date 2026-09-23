package com.ampixa.nepakeyboard.ime;

import android.content.Context;
import android.content.res.AssetManager;
import android.system.ErrnoException;
import android.system.Os;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

/** SHA-pinned binding between one conversion profile and one canonical NCM map. */
public final class ConversionMapSpec {
    private static final long MAX_MAP_BYTES = 256L * 1024L;
    private static final Pattern SAFE_ID = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
    );
    private static final Pattern SAFE_ASSET_SEGMENT = Pattern.compile("[A-Za-z0-9._-]+");

    private final String profileId;
    private final String converterId;
    private final File file;
    private final String artifactSha256;
    private final AssetManager assetManager;
    private final String assetPath;

    public ConversionMapSpec(
            String profileId,
            String converterId,
            File file,
            String artifactSha256
    ) {
        this(profileId, converterId, file, artifactSha256, null, null);
    }

    private ConversionMapSpec(
            String profileId,
            String converterId,
            File file,
            String artifactSha256,
            AssetManager assetManager,
            String assetPath
    ) {
        this.profileId = requireSafeId(profileId, "profileId");
        this.converterId = requireSafeId(converterId, "converterId");
        this.file = Objects.requireNonNull(file, "file");
        String normalizedSha = require(artifactSha256, "artifactSha256")
                .toLowerCase(Locale.ROOT);
        if (!normalizedSha.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("artifactSha256 must be lowercase SHA-256");
        }
        this.artifactSha256 = normalizedSha;
        this.assetManager = assetManager;
        this.assetPath = assetPath;
    }

    static ConversionMapSpec fromAsset(
            Context context,
            String profileId,
            String converterId,
            String assetPath,
            String artifactSha256
    ) {
        Objects.requireNonNull(context, "context");
        if (!isSafeId(profileId)
                || !isSafeId(converterId)
                || !isSafeAssetPath(assetPath)) {
            throw new IllegalArgumentException("asset-backed conversion identifiers are invalid");
        }
        String normalizedSha = require(artifactSha256, "artifactSha256")
                .toLowerCase(Locale.ROOT);
        if (!normalizedSha.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("artifactSha256 must be lowercase SHA-256");
        }
        Context applicationContext = context.getApplicationContext();
        Context stableContext = applicationContext == null ? context : applicationContext;
        File directory = new File(stableContext.getNoBackupFilesDir(), "conversion-maps");
        File destination = new File(
                directory,
                converterId + "-" + normalizedSha + ".ncm"
        );
        return new ConversionMapSpec(
                profileId,
                converterId,
                destination,
                normalizedSha,
                stableContext.getAssets(),
                assetPath
        );
    }

    public String profileId() {
        return profileId;
    }

    public String converterId() {
        return converterId;
    }

    public File file() {
        return file;
    }

    public String artifactSha256() {
        return artifactSha256;
    }

    /** Materializes an asset atomically; a file-backed test spec is already materialized. */
    public synchronized File materialize() throws IOException {
        if (assetManager == null) {
            return file;
        }
        File directory = file.getParentFile();
        if (directory == null
                || (!directory.isDirectory() && !directory.mkdirs())
                || !directory.isDirectory()) {
            throw new IOException("could not create conversion-map directory");
        }
        if (isVerifiedFile(file)) {
            return file;
        }
        if (file.exists() && !file.delete()) {
            throw new IOException("could not remove invalid conversion map");
        }
        File temporary = File.createTempFile("." + converterId + "-", ".tmp", directory);
        boolean renamed = false;
        try {
            MessageDigest digest = sha256Digest();
            long total = 0L;
            try (InputStream input = assetManager.open(assetPath, AssetManager.ACCESS_STREAMING);
                 FileOutputStream output = new FileOutputStream(temporary, false)) {
                byte[] buffer = new byte[8 * 1024];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    total += read;
                    if (total > MAX_MAP_BYTES) {
                        throw new IOException("conversion-map asset exceeds size limit");
                    }
                    digest.update(buffer, 0, read);
                    output.write(buffer, 0, read);
                }
                if (total == 0L) {
                    throw new IOException("conversion-map asset is empty");
                }
                output.flush();
                output.getFD().sync();
            }
            if (!MessageDigest.isEqual(digest.digest(), decodeSha256(artifactSha256))) {
                throw new SecurityException("conversion-map asset SHA-256 mismatch");
            }
            try {
                Os.rename(temporary.getAbsolutePath(), file.getAbsolutePath());
            } catch (ErrnoException failure) {
                throw new IOException("could not atomically install conversion map", failure);
            }
            renamed = true;
            return file;
        } finally {
            if (!renamed && temporary.exists()) {
                temporary.delete();
            }
        }
    }

    String cacheKey() {
        return converterId + ":" + artifactSha256 + ":" + file.getAbsolutePath();
    }

    static boolean isSafeAssetPath(String value) {
        if (value == null
                || value.length() > 255
                || value.startsWith("/")
                || value.contains("\\")
                || !value.startsWith("nepa-conversions/")
                || !value.endsWith(".ncm")) {
            return false;
        }
        String[] segments = value.split("/", -1);
        if (segments.length < 2) {
            return false;
        }
        for (String segment : segments) {
            if (segment.isEmpty()
                    || segment.equals(".")
                    || segment.equals("..")
                    || !SAFE_ASSET_SEGMENT.matcher(segment).matches()) {
                return false;
            }
        }
        return true;
    }

    private boolean isVerifiedFile(File candidate) throws IOException {
        if (!candidate.isFile()
                || candidate.length() <= 0L
                || candidate.length() > MAX_MAP_BYTES) {
            return false;
        }
        MessageDigest digest = sha256Digest();
        try (InputStream input = new FileInputStream(candidate)) {
            byte[] buffer = new byte[8 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }
        return MessageDigest.isEqual(digest.digest(), decodeSha256(artifactSha256));
    }

    private static boolean isSafeId(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }

    private static String require(String value, String label) {
        Objects.requireNonNull(value, label);
        if (value.isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        return value;
    }

    private static String requireSafeId(String value, String label) {
        String checked = require(value, label);
        if (!isSafeId(checked)) {
            throw new IllegalArgumentException(label + " is unsafe");
        }
        return checked;
    }

    private static MessageDigest sha256Digest() throws IOException {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException impossible) {
            throw new IOException("SHA-256 is unavailable", impossible);
        }
    }

    private static byte[] decodeSha256(String value) {
        byte[] result = new byte[32];
        for (int index = 0; index < result.length; index++) {
            result[index] = (byte) Integer.parseInt(
                    value.substring(index * 2, index * 2 + 2),
                    16
            );
        }
        return result;
    }
}
