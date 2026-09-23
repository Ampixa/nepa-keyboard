package com.ampixa.nepakeyboard.pack;

import org.json.JSONException;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.Closeable;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * Verified reader for Nepa Keyboard v0 language packs.
 *
 * <p>The default {@link #open(File, String)} entry point is the isolated
 * public/export boundary and rejects internal packs. The internal product uses
 * {@link #open(File, String, boolean)} with explicit internal-catalog authority
 * while retaining the same artifact, archive, member, and metadata integrity
 * checks.</p>
 */
public final class NkpBundle implements Closeable {
    private static final int FORMAT_VERSION = 0;
    private static final int MAX_PACK_BYTES = 256 * 1024 * 1024;
    private static final int MAX_MEMBER_BYTES = 128 * 1024 * 1024;
    private static final int MAX_NOTICE_BYTES = 2 * 1024 * 1024;
    private static final int MAX_NOTICE_SOURCES = 64;
    private static final int MAX_CANDIDATES = 2_000_000;
    private static final int MAX_TRIE_NODES = 16_000_000;
    private static final String SURFACE_NORMALIZATION_NFC = "NFC";
    private static final String SURFACE_NORMALIZATION_ASCII_LOWER = "NFC+ASCII-lower";

    private static final byte[] CANDIDATE_MAGIC = ascii("NKCAND1\0");
    private static final byte[] SCORE_MAGIC = ascii("NKSCORE1");
    private static final byte[] TRIE_MAGIC = ascii("NKTRIE1\0");

    private static final Set<String> REQUIRED_MEMBERS = Collections.unmodifiableSet(
            new HashSet<>(Arrays.asList(
                    "aliases.trie",
                    "candidates.bin",
                    "notices.json",
                    "scores.bin",
                    "surface.trie"
            ))
    );
    private static final Set<String> ALLOWED_MEMBERS;

    static {
        Set<String> allowed = new HashSet<>(REQUIRED_MEMBERS);
        allowed.add("manifest.json");
        ALLOWED_MEMBERS = Collections.unmodifiableSet(allowed);
    }

    private final String artifactSha256;
    private final JSONObject manifest;
    private final String releaseMode;
    private final String surfaceLookupNormalization;
    private final CandidateTable candidates;
    private final int[] scores;
    private final PrefixTrie surfaceTrie;
    private final PrefixTrie aliasesTrie;

    private NkpBundle(
            String artifactSha256,
            JSONObject manifest,
            String releaseMode,
            String surfaceLookupNormalization,
            CandidateTable candidates,
            int[] scores,
            PrefixTrie surfaceTrie,
            PrefixTrie aliasesTrie
    ) {
        this.artifactSha256 = artifactSha256;
        this.manifest = manifest;
        this.releaseMode = releaseMode;
        this.surfaceLookupNormalization = surfaceLookupNormalization;
        this.candidates = candidates;
        this.scores = scores;
        this.surfaceTrie = surfaceTrie;
        this.aliasesTrie = aliasesTrie;
    }

    /** Opens only a release pack. */
    public static NkpBundle open(File file, String expectedArtifactSha256) throws IOException {
        return open(file, expectedArtifactSha256, false);
    }

    /**
     * Opens and verifies one pack.
     *
     * @param allowInternal internal-product authority; public/export callers must pass false
     */
    public static NkpBundle open(
            File file,
            String expectedArtifactSha256,
            boolean allowInternal
    ) throws IOException {
        Objects.requireNonNull(file, "file");
        if (Files.isSymbolicLink(file.toPath())) {
            throw new IOException("pack must not be a symbolic link: " + file);
        }
        if (!file.isFile()) {
            throw new IOException("pack is not a regular file: " + file);
        }
        if (file.length() <= 0 || file.length() > MAX_PACK_BYTES) {
            throw new IOException("pack size is outside the v0 safety limit: " + file.length());
        }

        String artifactHash = sha256(file);
        if (expectedArtifactSha256 != null
                && !expectedArtifactSha256.trim().isEmpty()
                && !constantTimeEquals(artifactHash, expectedArtifactSha256.toLowerCase(Locale.ROOT))) {
            throw new SecurityException("artifact SHA-256 mismatch");
        }

        try (ZipFile zipFile = new ZipFile(file)) {
            verifyArchiveMembers(zipFile);
            byte[] manifestBytes = readStoredEntry(zipFile, "manifest.json", 1024 * 1024);
            JSONObject manifest = parseJson(manifestBytes, "manifest.json");
            if (requiredExactInt(manifest, "format_version", "manifest.json") != FORMAT_VERSION) {
                throw new IOException("unsupported pack format version");
            }
            String releaseMode = requiredString(manifest, "release_mode", "manifest.json");
            if (!releaseMode.equals("release") && !releaseMode.equals("internal")) {
                throw new IOException("invalid release_mode: " + releaseMode);
            }
            if (releaseMode.equals("internal") && !allowInternal) {
                throw new SecurityException("internal pack rejected by public/export reader gate");
            }
            String surfaceLookupNormalization = SURFACE_NORMALIZATION_NFC;
            JSONObject normalization = manifest.optJSONObject("normalization");
            if (manifest.has("normalization") && normalization == null) {
                throw new IOException("manifest normalization must be an object");
            }
            if (normalization != null) {
                surfaceLookupNormalization = normalization.optString(
                        "surface_lookup", SURFACE_NORMALIZATION_NFC
                );
            }
            if (!surfaceLookupNormalization.equals(SURFACE_NORMALIZATION_NFC)
                    && !surfaceLookupNormalization.equals(SURFACE_NORMALIZATION_ASCII_LOWER)) {
                throw new IOException(
                        "unsupported surface lookup normalization: " + surfaceLookupNormalization
                );
            }

            JSONObject memberManifest = requiredObject(manifest, "members", "manifest.json");
            verifyMemberManifest(memberManifest);

            byte[] candidateBytes = verifiedMember(zipFile, memberManifest, "candidates.bin");
            byte[] scoreBytes = verifiedMember(zipFile, memberManifest, "scores.bin");
            byte[] surfaceBytes = verifiedMember(zipFile, memberManifest, "surface.trie");
            byte[] aliasBytes = verifiedMember(zipFile, memberManifest, "aliases.trie");
            byte[] noticeBytes = verifiedMember(zipFile, memberManifest, "notices.json");

            JSONObject notices = parseJson(noticeBytes, "notices.json");
            String noticeMode = requiredString(notices, "release_mode", "notices.json");
            if (!releaseMode.equals(noticeMode)) {
                throw new SecurityException("manifest/notices release mode mismatch");
            }

            CandidateTable candidates = CandidateTable.parse(candidateBytes);
            int[] scores = parseScores(scoreBytes, candidates.size());
            PrefixTrie surfaceTrie = PrefixTrie.parse(surfaceBytes, candidates.size());
            PrefixTrie aliasesTrie = PrefixTrie.parse(aliasBytes, candidates.size());

            return new NkpBundle(
                    artifactHash,
                    manifest,
                    releaseMode,
                    surfaceLookupNormalization,
                    candidates,
                    scores,
                    surfaceTrie,
                    aliasesTrie
            );
        } catch (JSONException exception) {
            throw new IOException("invalid JSON metadata", exception);
        }
    }

    /** Reads verified release notices without loading candidates or tries. */
    public static NoticeDocument readNotices(
            File file,
            String expectedArtifactSha256
    ) throws IOException {
        return readNotices(file, expectedArtifactSha256, false);
    }

    /** Reads verified provenance for the internal product catalog. */
    public static NoticeDocument readNoticesForInternalCatalog(
            File file,
            String expectedArtifactSha256
    ) throws IOException {
        return readNotices(file, expectedArtifactSha256, true);
    }

    private static NoticeDocument readNotices(
            File file,
            String expectedArtifactSha256,
            boolean allowInternal
    ) throws IOException {
        Objects.requireNonNull(file, "file");
        if (Files.isSymbolicLink(file.toPath())) {
            throw new IOException("pack must not be a symbolic link: " + file);
        }
        if (!file.isFile()) {
            throw new IOException("pack is not a regular file: " + file);
        }
        if (file.length() <= 0 || file.length() > MAX_PACK_BYTES) {
            throw new IOException("pack size is outside the v0 safety limit: " + file.length());
        }
        String artifactHash = sha256(file);
        if (expectedArtifactSha256 == null
                || expectedArtifactSha256.trim().isEmpty()
                || !constantTimeEquals(
                        artifactHash,
                        expectedArtifactSha256.toLowerCase(Locale.ROOT)
                )) {
            throw new SecurityException("artifact SHA-256 mismatch");
        }

        try (ZipFile zipFile = new ZipFile(file)) {
            verifyArchiveMembers(zipFile);
            JSONObject manifest = parseJson(
                    readStoredEntry(zipFile, "manifest.json", 1024 * 1024),
                    "manifest.json"
            );
            if (requiredExactInt(manifest, "format_version", "manifest.json") != FORMAT_VERSION) {
                throw new IOException("unsupported pack format version");
            }
            String releaseMode = requiredString(manifest, "release_mode", "manifest.json");
            if (!("release".equals(releaseMode)
                    || (allowInternal && "internal".equals(releaseMode)))) {
                throw new SecurityException("notice reader accepts only release packs");
            }
            JSONObject pack = requiredObject(manifest, "pack", "manifest.json");
            String packId = requiredString(pack, "pack_id", "manifest.pack");
            String artifactLicense = requiredString(
                    pack,
                    "artifact_license",
                    "manifest.pack"
            );
            JSONObject members = requiredObject(manifest, "members", "manifest.json");
            verifyMemberManifest(members);
            byte[] noticeBytes = verifiedMember(
                    zipFile,
                    members,
                    "notices.json",
                    MAX_NOTICE_BYTES
            );
            JSONObject notices = parseJson(noticeBytes, "notices.json");
            if (!releaseMode.equals(requiredString(
                    notices,
                    "release_mode",
                    "notices.json"
            ))) {
                throw new SecurityException("manifest/notices release mode mismatch");
            }
            JSONArray sources = notices.optJSONArray("sources");
            if (sources == null
                    || sources.length() < 1
                    || sources.length() > MAX_NOTICE_SOURCES) {
                throw new IOException("notice source count is outside v0 safety limit");
            }
            List<NoticeSource> parsed = new ArrayList<>(sources.length());
            for (int index = 0; index < sources.length(); index++) {
                JSONObject source = sources.optJSONObject(index);
                if (source == null) {
                    throw new IOException("notice source must be an object: " + index);
                }
                String location = "notices.sources[" + index + "]";
                String redistribution = requiredString(
                        source,
                        "redistribution",
                        location
                );
                if (!allowInternal && !"allowed".equals(redistribution)) {
                    throw new SecurityException("notice source is not release-approved");
                }
                requiredString(source, "method", location);
                String sourceUrl = optionalString(source, "source_url", location);
                String licenseUrl = optionalString(source, "license_url", location);
                String licenseNotice = optionalString(source, "license_notice", location);
                if (!allowInternal
                        && (sourceUrl == null || licenseUrl == null || licenseNotice == null)) {
                    throw new JSONException(
                            location + " must contain complete release notice fields"
                    );
                }
                parsed.add(new NoticeSource(
                        requiredString(source, "source_id", location),
                        requiredString(source, "title", location),
                        requiredString(source, "license", location),
                        sourceUrl,
                        licenseUrl,
                        licenseNotice == null ? "" : licenseNotice,
                        source.optString("changes", "")
                ));
            }
            return new NoticeDocument(
                    packId,
                    artifactLicense,
                    Collections.unmodifiableList(parsed)
            );
        } catch (JSONException exception) {
            throw new IOException("invalid JSON metadata", exception);
        }
    }

    public String artifactSha256() {
        return artifactSha256;
    }

    public String releaseMode() {
        return releaseMode;
    }

    public String packId() throws IOException {
        try {
            return requiredString(requiredObject(manifest, "pack", "manifest.json"), "pack_id", "manifest.pack");
        } catch (JSONException exception) {
            throw new IOException("manifest pack metadata is invalid", exception);
        }
    }

    public int candidateCount() {
        return candidates.size();
    }

    public int[] lookupSurfaceIds(String prefix) {
        return surfaceTrie.lookup(normalizeSurface(prefix, surfaceLookupNormalization));
    }

    public int[] lookupAliasIds(String prefix) {
        return aliasesTrie.lookup(normalizeAlias(prefix));
    }

    public List<Suggestion> suggestSurface(String prefix) {
        return resolve(lookupSurfaceIds(prefix));
    }

    public List<Suggestion> suggestAliases(String prefix) {
        return resolve(lookupAliasIds(prefix));
    }

    public String candidateSurface(int candidateId) {
        return candidates.get(candidateId);
    }

    public int candidateScore(int candidateId) {
        if (candidateId < 0 || candidateId >= scores.length) {
            throw new IndexOutOfBoundsException("candidate ID: " + candidateId);
        }
        return scores[candidateId];
    }

    private List<Suggestion> resolve(int[] candidateIds) {
        if (candidateIds.length == 0) {
            return Collections.emptyList();
        }
        List<Suggestion> result = new ArrayList<>(candidateIds.length);
        for (int candidateId : candidateIds) {
            result.add(new Suggestion(candidateId, candidates.get(candidateId), scores[candidateId]));
        }
        return Collections.unmodifiableList(result);
    }

    @Override
    public void close() {
        // v0 members are bounded byte buffers. No open descriptor survives open().
    }

    private static String normalizeAlias(String value) {
        return Normalizer.normalize(value, Normalizer.Form.NFC)
                .toLowerCase(Locale.ROOT)
                .trim();
    }

    private static String normalizeSurface(String value, String mode) {
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFC);
        if (!mode.equals(SURFACE_NORMALIZATION_ASCII_LOWER)) {
            return normalized;
        }
        StringBuilder output = new StringBuilder(normalized.length());
        for (int index = 0; index < normalized.length(); index++) {
            char character = normalized.charAt(index);
            output.append(character >= 'A' && character <= 'Z'
                    ? (char) (character + ('a' - 'A'))
                    : character);
        }
        return output.toString();
    }

    private static byte[] verifiedMember(
            ZipFile zipFile,
            JSONObject memberManifest,
            String name
    ) throws IOException, JSONException {
        return verifiedMember(zipFile, memberManifest, name, MAX_MEMBER_BYTES);
    }

    private static byte[] verifiedMember(
            ZipFile zipFile,
            JSONObject memberManifest,
            String name,
            int maximumBytes
    ) throws IOException, JSONException {
        JSONObject metadata = requiredObject(memberManifest, name, "manifest.members");
        long expectedBytes = requiredExactInt(
                metadata,
                "bytes",
                "manifest.members." + name
        );
        if (expectedBytes < 0 || expectedBytes > maximumBytes) {
            throw new IOException("member size is outside v0 safety limit: " + name);
        }
        byte[] data = readStoredEntry(zipFile, name, (int) expectedBytes);
        if (data.length != expectedBytes) {
            throw new SecurityException("member size mismatch: " + name);
        }
        String expectedHash = requiredString(metadata, "sha256", "manifest.members." + name);
        if (!constantTimeEquals(sha256(data), expectedHash.toLowerCase(Locale.ROOT))) {
            throw new SecurityException("member SHA-256 mismatch: " + name);
        }
        return data;
    }

    private static void verifyArchiveMembers(ZipFile zipFile) throws IOException {
        Set<String> observed = new HashSet<>();
        java.util.Enumeration<? extends ZipEntry> entries = zipFile.entries();
        while (entries.hasMoreElements()) {
            ZipEntry entry = entries.nextElement();
            String name = entry.getName();
            if (entry.isDirectory() || !ALLOWED_MEMBERS.contains(name)) {
                throw new IOException("unexpected pack member: " + name);
            }
            if (!observed.add(name)) {
                throw new IOException("duplicate pack member: " + name);
            }
        }
        for (String name : ALLOWED_MEMBERS) {
            if (!observed.contains(name)) {
                throw new IOException("missing pack member: " + name);
            }
        }
    }

    private static void verifyMemberManifest(JSONObject memberManifest)
            throws IOException, JSONException {
        Set<String> observed = new HashSet<>();
        java.util.Iterator<String> keys = memberManifest.keys();
        while (keys.hasNext()) {
            String name = keys.next();
            if (!REQUIRED_MEMBERS.contains(name)) {
                throw new IOException("unexpected manifest member: " + name);
            }
            observed.add(name);
        }
        for (String name : REQUIRED_MEMBERS) {
            if (!observed.contains(name)) {
                throw new IOException("manifest is missing required member: " + name);
            }
            requiredObject(memberManifest, name, "manifest.members");
        }
    }

    private static byte[] readStoredEntry(ZipFile zipFile, String name, int maximumBytes) throws IOException {
        ZipEntry entry = zipFile.getEntry(name);
        if (entry == null || entry.isDirectory()) {
            throw new IOException("missing pack member: " + name);
        }
        if (entry.getMethod() != ZipEntry.STORED) {
            throw new IOException("v0 pack member must use ZIP-STORE: " + name);
        }
        long entrySize = entry.getSize();
        if (entrySize < 0 || entrySize > maximumBytes || entrySize > MAX_MEMBER_BYTES) {
            throw new IOException("invalid pack member size: " + name);
        }
        try (InputStream input = zipFile.getInputStream(entry);
             ByteArrayOutputStream output = new ByteArrayOutputStream((int) entrySize)) {
            byte[] buffer = new byte[16 * 1024];
            int total = 0;
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > maximumBytes) {
                    throw new IOException("pack member exceeded declared size: " + name);
                }
                output.write(buffer, 0, read);
            }
            return output.toByteArray();
        }
    }

    private static int[] parseScores(byte[] data, int expectedCount) throws IOException {
        ByteBuffer buffer = littleEndian(data);
        requireMagic(buffer, SCORE_MAGIC, "scores.bin");
        if (buffer.remaining() < 4) {
            throw new IOException("truncated score header");
        }
        int count = checkedCount(buffer.getInt(), MAX_CANDIDATES, "score count");
        if (count != expectedCount || data.length != 12L + count * 4L) {
            throw new IOException("score/candidate count mismatch");
        }
        int[] scores = new int[count];
        for (int index = 0; index < count; index++) {
            scores[index] = buffer.getInt();
        }
        return scores;
    }

    private static ByteBuffer littleEndian(byte[] data) {
        return ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN);
    }

    private static void requireMagic(ByteBuffer buffer, byte[] expected, String member) throws IOException {
        if (buffer.remaining() < expected.length) {
            throw new IOException("truncated magic: " + member);
        }
        byte[] actual = new byte[expected.length];
        buffer.get(actual);
        if (!Arrays.equals(actual, expected)) {
            throw new IOException("invalid magic: " + member);
        }
    }

    private static int checkedCount(int value, int maximum, String label) throws IOException {
        if (value < 0 || value > maximum) {
            throw new IOException(label + " is outside v0 safety limit: " + value);
        }
        return value;
    }

    private static JSONObject parseJson(byte[] data, String member) throws IOException {
        try {
            return new JSONObject(new String(data, StandardCharsets.UTF_8));
        } catch (JSONException exception) {
            throw new IOException("invalid JSON in " + member, exception);
        }
    }

    private static JSONObject requiredObject(JSONObject value, String key, String location) throws JSONException {
        Object child = value.get(key);
        if (!(child instanceof JSONObject)) {
            throw new JSONException(location + "." + key + " must be an object");
        }
        return (JSONObject) child;
    }

    private static String requiredString(JSONObject value, String key, String location) throws JSONException {
        Object child = value.get(key);
        if (!(child instanceof String) || ((String) child).isEmpty()) {
            throw new JSONException(location + "." + key + " must be a non-empty string");
        }
        return (String) child;
    }

    private static String optionalString(
            JSONObject value,
            String key,
            String location
    ) throws JSONException {
        if (!value.has(key)) {
            return null;
        }
        Object child = value.get(key);
        if (!(child instanceof String) || ((String) child).isEmpty()) {
            throw new JSONException(location + "." + key + " must be a non-empty string");
        }
        return (String) child;
    }

    private static int requiredExactInt(
            JSONObject value,
            String key,
            String location
    ) throws JSONException {
        Object child = value.get(key);
        if (child instanceof Integer) {
            return (Integer) child;
        }
        if (child instanceof Long
                && (Long) child >= Integer.MIN_VALUE
                && (Long) child <= Integer.MAX_VALUE) {
            return ((Long) child).intValue();
        }
        throw new JSONException(location + "." + key + " must be an exact 32-bit integer");
    }

    private static String sha256(File file) throws IOException {
        MessageDigest digest = newDigest();
        try (InputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }
        return hex(digest.digest());
    }

    private static String sha256(byte[] data) {
        MessageDigest digest = newDigest();
        return hex(digest.digest(data));
    }

    private static MessageDigest newDigest() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new AssertionError("Android runtime has no SHA-256", exception);
        }
    }

    private static String hex(byte[] data) {
        StringBuilder output = new StringBuilder(data.length * 2);
        for (byte value : data) {
            output.append(Character.forDigit((value >>> 4) & 0xF, 16));
            output.append(Character.forDigit(value & 0xF, 16));
        }
        return output.toString();
    }

    private static boolean constantTimeEquals(String first, String second) {
        return MessageDigest.isEqual(
                first.getBytes(StandardCharsets.US_ASCII),
                second.getBytes(StandardCharsets.US_ASCII)
        );
    }

    private static byte[] ascii(String value) {
        return value.getBytes(StandardCharsets.US_ASCII);
    }

    /** Immutable suggestion returned to the keyboard. */
    public static final class Suggestion {
        private final int candidateId;
        private final String surface;
        private final int score;

        Suggestion(int candidateId, String surface, int score) {
            this.candidateId = candidateId;
            this.surface = surface;
            this.score = score;
        }

        public int candidateId() {
            return candidateId;
        }

        public String surface() {
            return surface;
        }

        public int score() {
            return score;
        }
    }

    /** Immutable verified pack notice document. */
    public static final class NoticeDocument {
        private final String packId;
        private final String artifactLicense;
        private final List<NoticeSource> sources;

        NoticeDocument(
                String packId,
                String artifactLicense,
                List<NoticeSource> sources
        ) {
            this.packId = packId;
            this.artifactLicense = artifactLicense;
            this.sources = sources;
        }

        public String packId() {
            return packId;
        }

        public String artifactLicense() {
            return artifactLicense;
        }

        public List<NoticeSource> sources() {
            return sources;
        }
    }

    /** One immutable source row from verified pack provenance. */
    public static final class NoticeSource {
        private final String sourceId;
        private final String title;
        private final String license;
        private final String sourceUrl;
        private final String licenseUrl;
        private final String licenseNotice;
        private final String changes;

        NoticeSource(
                String sourceId,
                String title,
                String license,
                String sourceUrl,
                String licenseUrl,
                String licenseNotice,
                String changes
        ) {
            this.sourceId = sourceId;
            this.title = title;
            this.license = license;
            this.sourceUrl = sourceUrl;
            this.licenseUrl = licenseUrl;
            this.licenseNotice = licenseNotice;
            this.changes = changes;
        }

        public String sourceId() {
            return sourceId;
        }

        public String title() {
            return title;
        }

        public String license() {
            return license;
        }

        public String sourceUrl() {
            return sourceUrl;
        }

        public String licenseUrl() {
            return licenseUrl;
        }

        public String licenseNotice() {
            return licenseNotice;
        }

        public String changes() {
            return changes;
        }
    }

    private static final class CandidateTable {
        private final byte[] blob;
        private final int[] offsets;
        private final String[] cache;

        private CandidateTable(byte[] blob, int[] offsets) {
            this.blob = blob;
            this.offsets = offsets;
            this.cache = new String[offsets.length - 1];
        }

        static CandidateTable parse(byte[] data) throws IOException {
            ByteBuffer buffer = littleEndian(data);
            requireMagic(buffer, CANDIDATE_MAGIC, "candidates.bin");
            if (buffer.remaining() < 4) {
                throw new IOException("truncated candidate header");
            }
            int count = checkedCount(buffer.getInt(), MAX_CANDIDATES, "candidate count");
            long tableBytes = 12L + (count + 1L) * 4L;
            if (tableBytes > data.length) {
                throw new IOException("truncated candidate offset table");
            }
            int[] offsets = new int[count + 1];
            int previous = -1;
            for (int index = 0; index <= count; index++) {
                int offset = buffer.getInt();
                if (offset < 0 || offset < previous) {
                    throw new IOException("candidate offsets are not monotonic");
                }
                offsets[index] = offset;
                previous = offset;
            }
            int blobStart = (int) tableBytes;
            int blobLength = data.length - blobStart;
            if (offsets[0] != 0 || offsets[count] != blobLength) {
                throw new IOException("candidate offset boundary mismatch");
            }
            return new CandidateTable(Arrays.copyOfRange(data, blobStart, data.length), offsets);
        }

        int size() {
            return cache.length;
        }

        String get(int candidateId) {
            if (candidateId < 0 || candidateId >= cache.length) {
                throw new IndexOutOfBoundsException("candidate ID: " + candidateId);
            }
            String value = cache[candidateId];
            if (value == null) {
                value = new String(
                        blob,
                        offsets[candidateId],
                        offsets[candidateId + 1] - offsets[candidateId],
                        StandardCharsets.UTF_8
                );
                cache[candidateId] = value;
            }
            return value;
        }
    }

    private static final class PrefixTrie {
        private static final int HEADER_BYTES = 24;
        private static final int NODE_BYTES = 12;
        private static final int EDGE_BYTES = 8;

        private final ByteBuffer data;
        private final int nodeCount;
        private final int edgeCount;
        private final int valuesOffset;
        private final int nodesOffset;
        private final int edgesOffset;

        private PrefixTrie(
                ByteBuffer data,
                int nodeCount,
                int edgeCount,
                int nodesOffset,
                int edgesOffset,
                int valuesOffset
        ) {
            this.data = data;
            this.nodeCount = nodeCount;
            this.edgeCount = edgeCount;
            this.nodesOffset = nodesOffset;
            this.edgesOffset = edgesOffset;
            this.valuesOffset = valuesOffset;
        }

        static PrefixTrie parse(byte[] bytes, int candidateCount) throws IOException {
            ByteBuffer buffer = littleEndian(bytes);
            requireMagic(buffer, TRIE_MAGIC, "prefix trie");
            if (bytes.length < HEADER_BYTES) {
                throw new IOException("truncated trie header");
            }
            int nodeCount = checkedCount(buffer.getInt(), MAX_TRIE_NODES, "trie node count");
            int edgeCount = checkedCount(buffer.getInt(), MAX_TRIE_NODES, "trie edge count");
            int valueCount = checkedCount(buffer.getInt(), MAX_TRIE_NODES * 32, "trie value count");
            int maxSuggestions = Short.toUnsignedInt(buffer.getShort());
            int reserved = Short.toUnsignedInt(buffer.getShort());
            if (nodeCount == 0 || maxSuggestions == 0 || maxSuggestions > 32 || reserved != 0) {
                throw new IOException("invalid trie header");
            }
            long edgesOffset = HEADER_BYTES + (long) nodeCount * NODE_BYTES;
            long valuesOffset = edgesOffset + (long) edgeCount * EDGE_BYTES;
            long expectedLength = valuesOffset + (long) valueCount * 4L;
            if (expectedLength != bytes.length || valuesOffset > Integer.MAX_VALUE) {
                throw new IOException("trie length/count mismatch");
            }

            PrefixTrie trie = new PrefixTrie(
                    buffer,
                    nodeCount,
                    edgeCount,
                    HEADER_BYTES,
                    (int) edgesOffset,
                    (int) valuesOffset
            );
            trie.validate(valueCount, candidateCount, maxSuggestions);
            return trie;
        }

        private void validate(int valueCount, int candidateCount, int maxSuggestions) throws IOException {
            for (int node = 0; node < nodeCount; node++) {
                int nodeOffset = nodeOffset(node);
                int firstEdge = data.getInt(nodeOffset);
                int edgesAtNode = Short.toUnsignedInt(data.getShort(nodeOffset + 4));
                int firstValue = data.getInt(nodeOffset + 6);
                int valuesAtNode = Short.toUnsignedInt(data.getShort(nodeOffset + 10));
                if (firstEdge < 0 || edgesAtNode > edgeCount - firstEdge) {
                    throw new IOException("trie node edge range is invalid");
                }
                if (firstValue < 0 || valuesAtNode > valueCount - firstValue || valuesAtNode > maxSuggestions) {
                    throw new IOException("trie node value range is invalid");
                }

                int previousCodePoint = -1;
                for (int offset = 0; offset < edgesAtNode; offset++) {
                    int edgeOffset = edgeOffset(firstEdge + offset);
                    int codePoint = data.getInt(edgeOffset);
                    int targetNode = data.getInt(edgeOffset + 4);
                    if (!Character.isValidCodePoint(codePoint)
                            || codePoint <= previousCodePoint
                            || targetNode < 0
                            || targetNode >= nodeCount) {
                        throw new IOException("trie edge is invalid or unsorted");
                    }
                    previousCodePoint = codePoint;
                }
                for (int offset = 0; offset < valuesAtNode; offset++) {
                    int candidateId = data.getInt(valuesOffset + (firstValue + offset) * 4);
                    if (candidateId < 0 || candidateId >= candidateCount) {
                        throw new IOException("trie references an invalid candidate ID");
                    }
                }
            }
        }

        int[] lookup(String prefix) {
            int node = 0;
            for (int offset = 0; offset < prefix.length(); ) {
                int codePoint = prefix.codePointAt(offset);
                node = child(node, codePoint);
                if (node < 0) {
                    return new int[0];
                }
                offset += Character.charCount(codePoint);
            }

            int nodeOffset = nodeOffset(node);
            int firstValue = data.getInt(nodeOffset + 6);
            int valuesAtNode = Short.toUnsignedInt(data.getShort(nodeOffset + 10));
            int[] result = new int[valuesAtNode];
            for (int index = 0; index < valuesAtNode; index++) {
                result[index] = data.getInt(valuesOffset + (firstValue + index) * 4);
            }
            return result;
        }

        private int child(int node, int codePoint) {
            int nodeOffset = nodeOffset(node);
            int firstEdge = data.getInt(nodeOffset);
            int edgesAtNode = Short.toUnsignedInt(data.getShort(nodeOffset + 4));
            int low = 0;
            int high = edgesAtNode - 1;
            while (low <= high) {
                int middle = (low + high) >>> 1;
                int edgeOffset = edgeOffset(firstEdge + middle);
                int candidate = data.getInt(edgeOffset);
                if (candidate < codePoint) {
                    low = middle + 1;
                } else if (candidate > codePoint) {
                    high = middle - 1;
                } else {
                    return data.getInt(edgeOffset + 4);
                }
            }
            return -1;
        }

        private int nodeOffset(int node) {
            return nodesOffset + node * NODE_BYTES;
        }

        private int edgeOffset(int edge) {
            return edgesOffset + edge * EDGE_BYTES;
        }
    }
}
