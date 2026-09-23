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

/** SHA-pinned binding between one keyboard profile and one staged product pack. */
public final class ReleasePackSpec {
    private static final long MAX_PACK_BYTES = 256L * 1024L * 1024L;
    private static final Pattern SAFE_ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");
    private static final Pattern SAFE_ASSET_SEGMENT = Pattern.compile("[A-Za-z0-9._-]+");

    private final String profileId;
    private final String packId;
    private final File file;
    private final String artifactSha256;
    private final AssetManager assetManager;
    private final String assetPath;

    public ReleasePackSpec(
            String profileId,
            String packId,
            File file,
            String artifactSha256
    ) {
        this(profileId, packId, file, artifactSha256, null, null);
    }

    private ReleasePackSpec(
            String profileId,
            String packId,
            File file,
            String artifactSha256,
            AssetManager assetManager,
            String assetPath
    ) {
        this.profileId = require(profileId, "profileId");
        this.packId = require(packId, "packId");
        this.file = Objects.requireNonNull(file, "file");
        String normalizedSha = require(artifactSha256, "artifactSha256")
                .toLowerCase(Locale.ROOT);
        if (!normalizedSha.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("artifactSha256 must be 64 hexadecimal characters");
        }
        this.artifactSha256 = normalizedSha;
        this.assetManager = assetManager;
        this.assetPath = assetPath;
    }

    public static ReleasePackSpec fromAsset(
            Context context,
            String profileId,
            String packId,
            String assetPath,
            String artifactSha256
    ) {
        Objects.requireNonNull(context, "context");
        if (!isSafeId(profileId) || !isSafeId(packId) || !isSafeAssetPath(assetPath)) {
            throw new IllegalArgumentException("asset-backed pack identifiers are invalid");
        }
        String normalizedSha = require(artifactSha256, "artifactSha256")
                .toLowerCase(Locale.ROOT);
        if (!normalizedSha.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("artifactSha256 must be 64 hexadecimal characters");
        }
        Context applicationContext = context.getApplicationContext();
        Context stableContext = applicationContext == null ? context : applicationContext;
        File directory = new File(stableContext.getNoBackupFilesDir(), "language-packs");
        File destination = new File(directory, require(packId, "packId")
                + "-" + normalizedSha + ".nkp");
        return new ReleasePackSpec(
                profileId,
                packId,
                destination,
                normalizedSha,
                stableContext.getAssets(),
                assetPath
        );
    }

    public String profileId() {
        return profileId;
    }

    public String packId() {
        return packId;
    }

    public File file() {
        return file;
    }

    public String artifactSha256() {
        return artifactSha256;
    }

    /** Materializes an asset-backed pack atomically; file-backed specs are already materialized. */
    public synchronized File materialize() throws IOException {
        if (assetManager == null) {
            return file;
        }
        File directory = file.getParentFile();
        if (directory == null
                || (!directory.isDirectory() && !directory.mkdirs())
                || !directory.isDirectory()) {
            throw new IOException("could not create no-backup pack directory");
        }
        if (isVerifiedFile(file)) {
            return file;
        }
        if (file.exists() && !file.delete()) {
            throw new IOException("could not remove invalid materialized pack");
        }

        File temporary = File.createTempFile("." + packId + "-", ".tmp", directory);
        boolean renamed = false;
        try {
            MessageDigest digest = sha256Digest();
            long total = 0;
            try (InputStream input = assetManager.open(assetPath, AssetManager.ACCESS_STREAMING);
                 FileOutputStream output = new FileOutputStream(temporary, false)) {
                byte[] buffer = new byte[16 * 1024];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    total += read;
                    if (total > MAX_PACK_BYTES) {
                        throw new IOException("pack asset exceeds size limit");
                    }
                    digest.update(buffer, 0, read);
                    output.write(buffer, 0, read);
                }
                if (total == 0) {
                    throw new IOException("pack asset is empty");
                }
                output.flush();
                output.getFD().sync();
            }
            if (!MessageDigest.isEqual(digest.digest(), decodeSha256(artifactSha256))) {
                throw new SecurityException("pack asset SHA-256 mismatch");
            }
            try {
                Os.rename(temporary.getAbsolutePath(), file.getAbsolutePath());
            } catch (ErrnoException exception) {
                throw new IOException("could not atomically install pack asset", exception);
            }
            renamed = true;
            return file;
        } finally {
            if (!renamed && temporary.exists()) {
                // Best effort only; the content-addressed destination is never exposed partially.
                temporary.delete();
            }
        }
    }

    String cacheKey() {
        return packId + ":" + artifactSha256 + ":" + file.getAbsolutePath();
    }

    static boolean isSafeAssetPath(String value) {
        if (value == null
                || value.length() > 255
                || value.startsWith("/")
                || value.contains("\\")
                || !value.startsWith("nepa-packs/")
                || !value.endsWith(".nkp")) {
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

    private static boolean isSafeId(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }

    private boolean isVerifiedFile(File candidate) throws IOException {
        if (!candidate.isFile()
                || candidate.length() <= 0
                || candidate.length() > MAX_PACK_BYTES) {
            return false;
        }
        MessageDigest digest = sha256Digest();
        try (InputStream input = new FileInputStream(candidate)) {
            byte[] buffer = new byte[16 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }
        return MessageDigest.isEqual(digest.digest(), decodeSha256(artifactSha256));
    }

    private static MessageDigest sha256Digest() throws IOException {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IOException("SHA-256 is unavailable", exception);
        }
    }

    private static byte[] decodeSha256(String encoded) {
        byte[] output = new byte[32];
        for (int index = 0; index < output.length; index++) {
            output[index] = (byte) Integer.parseInt(
                    encoded.substring(index * 2, index * 2 + 2),
                    16
            );
        }
        return output;
    }

    private static String require(String value, String label) {
        Objects.requireNonNull(value, label);
        if (value.trim().isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        return value;
    }
}
