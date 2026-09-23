package com.ampixa.nepakeyboard.benchmark;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;

import com.ampixa.nepakeyboard.pack.NkpBundle;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

/** Internal-catalog integrity negatives using the staged Limbu v0 bundle. */
public final class NkpBundleCorruptionInstrumentation extends Instrumentation {
    private static final String TAG = "NepaPackCorruption";
    private static final String PACK_ASSET = "nepa-packs/lif-Limb-NP.nkp";
    private static final int MAX_MEMBER_BYTES = 128 * 1024 * 1024;
    private static final String WRONG_SHA256 =
            "0000000000000000000000000000000000000000000000000000000000000000";
    private static final Set<String> EXPECTED_MEMBERS = new HashSet<>(Arrays.asList(
            "aliases.trie",
            "candidates.bin",
            "manifest.json",
            "notices.json",
            "scores.bin",
            "surface.trie"
    ));

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle output = new Bundle();
        int resultCode = Activity.RESULT_CANCELED;
        File workDirectory = null;
        try {
            Context context = getTargetContext();
            workDirectory = new File(
                    context.getCacheDir(),
                    "nkp-corruption-" + SystemClock.elapsedRealtimeNanos()
            );
            if (!workDirectory.mkdir()) {
                throw new IOException("cannot create isolated corruption fixture directory");
            }

            File baseline = new File(workDirectory, "baseline.nkp");
            copyAsset(context, baseline);
            String baselineSha256 = sha256(baseline);
            try (NkpBundle pack = NkpBundle.open(baseline, baselineSha256, true)) {
                assertEquals("baseline pack ID", "lif-Limb-NP", pack.packId());
            }
            output.putBoolean("valid_catalog_baseline", true);
            output.putString("baseline_artifact_sha256", baselineSha256);
            Map<String, byte[]> baselineMembers = readMembers(baseline);

            int passed = 0;
            File truncatedAliases = new File(workDirectory, "truncated-aliases-trie.nkp");
            Map<String, byte[]> truncatedAliasMembers = copyMembers(baselineMembers);
            byte[] aliasMagicOnly = Arrays.copyOf(
                    truncatedAliasMembers.get("aliases.trie"),
                    8
            );
            truncatedAliasMembers.put("aliases.trie", aliasMagicOnly);
            JSONObject truncatedAliasManifest = json(
                    truncatedAliasMembers.get("manifest.json")
            );
            updateMemberMetadata(truncatedAliasManifest, "aliases.trie", aliasMagicOnly);
            truncatedAliasMembers.put("manifest.json", jsonBytes(truncatedAliasManifest));
            writeArchive(truncatedAliases, truncatedAliasMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "truncated_alias_trie_header",
                    () -> openWithActualHash(truncatedAliases),
                    "truncated trie header"
            );
            passed += recordExpectedFailure(
                    output,
                    "outer_sha_mismatch",
                    () -> openAndClose(baseline, WRONG_SHA256),
                    "artifact SHA-256 mismatch"
            );

            File invalidMode = new File(workDirectory, "invalid-release-mode.nkp");
            Map<String, byte[]> invalidModeMembers = copyMembers(baselineMembers);
            JSONObject invalidModeManifest = json(invalidModeMembers.get("manifest.json"));
            invalidModeManifest.put("release_mode", "invalid");
            invalidModeMembers.put("manifest.json", jsonBytes(invalidModeManifest));
            writeArchive(invalidMode, invalidModeMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "invalid_release_mode",
                    () -> openWithActualHash(invalidMode),
                    "invalid release_mode"
            );

            File modeMismatch = new File(workDirectory, "mode-mismatch.nkp");
            Map<String, byte[]> modeMismatchMembers = copyMembers(baselineMembers);
            JSONObject modeMismatchNotices = json(modeMismatchMembers.get("notices.json"));
            modeMismatchNotices.put("release_mode", "release");
            byte[] changedNotices = jsonBytes(modeMismatchNotices);
            modeMismatchMembers.put("notices.json", changedNotices);
            JSONObject modeMismatchManifest = json(modeMismatchMembers.get("manifest.json"));
            updateMemberMetadata(modeMismatchManifest, "notices.json", changedNotices);
            modeMismatchMembers.put("manifest.json", jsonBytes(modeMismatchManifest));
            writeArchive(modeMismatch, modeMismatchMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "manifest_notices_mode_mismatch",
                    () -> openWithActualHash(modeMismatch),
                    "manifest/notices release mode mismatch"
            );

            File memberHash = new File(workDirectory, "member-hash.nkp");
            Map<String, byte[]> memberHashMembers = copyMembers(baselineMembers);
            byte[] changedCandidates = memberHashMembers.get("candidates.bin").clone();
            if (changedCandidates.length == 0) {
                throw new AssertionError("baseline candidates.bin is empty");
            }
            changedCandidates[changedCandidates.length - 1] ^= 0x01;
            memberHashMembers.put("candidates.bin", changedCandidates);
            writeArchive(memberHash, memberHashMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "member_hash_mismatch",
                    () -> openWithActualHash(memberHash),
                    "member SHA-256 mismatch: candidates.bin"
            );

            File memberSize = new File(workDirectory, "member-size.nkp");
            Map<String, byte[]> memberSizeMembers = copyMembers(baselineMembers);
            JSONObject memberSizeManifest = json(memberSizeMembers.get("manifest.json"));
            JSONObject sizeMetadata = memberSizeManifest
                    .getJSONObject("members")
                    .getJSONObject("candidates.bin");
            sizeMetadata.put("bytes", sizeMetadata.getInt("bytes") + 1);
            memberSizeMembers.put("manifest.json", jsonBytes(memberSizeManifest));
            writeArchive(memberSize, memberSizeMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "member_size_mismatch",
                    () -> openWithActualHash(memberSize),
                    "member size mismatch: candidates.bin"
            );

            File fractionalFormat = new File(workDirectory, "fractional-format.nkp");
            Map<String, byte[]> fractionalFormatMembers = copyMembers(baselineMembers);
            JSONObject fractionalFormatManifest = json(
                    fractionalFormatMembers.get("manifest.json")
            );
            fractionalFormatManifest.put("format_version", 0.5d);
            fractionalFormatMembers.put("manifest.json", jsonBytes(fractionalFormatManifest));
            writeArchive(fractionalFormat, fractionalFormatMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "fractional_format_version",
                    () -> openWithActualHash(fractionalFormat),
                    "must be an exact 32-bit integer"
            );

            File fractionalBytes = new File(workDirectory, "fractional-member-bytes.nkp");
            Map<String, byte[]> fractionalBytesMembers = copyMembers(baselineMembers);
            JSONObject fractionalBytesManifest = json(
                    fractionalBytesMembers.get("manifest.json")
            );
            JSONObject fractionalMetadata = fractionalBytesManifest
                    .getJSONObject("members")
                    .getJSONObject("candidates.bin");
            fractionalMetadata.put("bytes", fractionalMetadata.getInt("bytes") + 0.5d);
            fractionalBytesMembers.put("manifest.json", jsonBytes(fractionalBytesManifest));
            writeArchive(fractionalBytes, fractionalBytesMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "fractional_member_bytes",
                    () -> openWithActualHash(fractionalBytes),
                    "must be an exact 32-bit integer"
            );

            File unexpectedManifestMember = new File(
                    workDirectory,
                    "unexpected-manifest-member.nkp"
            );
            Map<String, byte[]> unexpectedManifestMembers = copyMembers(baselineMembers);
            JSONObject unexpectedManifest = json(unexpectedManifestMembers.get("manifest.json"));
            JSONObject unexpectedMetadata = new JSONObject();
            unexpectedMetadata.put("bytes", 0);
            unexpectedMetadata.put("sha256", WRONG_SHA256);
            unexpectedManifest.getJSONObject("members").put("extra.bin", unexpectedMetadata);
            unexpectedManifestMembers.put("manifest.json", jsonBytes(unexpectedManifest));
            writeArchive(unexpectedManifestMember, unexpectedManifestMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "unexpected_manifest_member",
                    () -> openWithActualHash(unexpectedManifestMember),
                    "unexpected manifest member: extra.bin"
            );

            File missingMember = new File(workDirectory, "missing-member.nkp");
            Map<String, byte[]> missingMemberMembers = copyMembers(baselineMembers);
            missingMemberMembers.remove("aliases.trie");
            writeArchive(missingMember, missingMemberMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "missing_member",
                    () -> openWithActualHash(missingMember),
                    "missing pack member: aliases.trie"
            );

            File compressedMember = new File(workDirectory, "compressed-member.nkp");
            writeArchive(compressedMember, baselineMembers, "candidates.bin");
            passed += recordExpectedFailure(
                    output,
                    "compressed_member",
                    () -> openWithActualHash(compressedMember),
                    "v0 pack member must use ZIP-STORE: candidates.bin"
            );

            File extraMember = new File(workDirectory, "extra-member.nkp");
            Map<String, byte[]> extraMemberMembers = copyMembers(baselineMembers);
            extraMemberMembers.put("extra.bin", new byte[] {0x00});
            writeArchive(extraMember, extraMemberMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "extra_member",
                    () -> openWithActualHash(extraMember),
                    "unexpected pack member: extra.bin"
            );

            File truncatedCandidates = new File(workDirectory, "truncated-candidates.nkp");
            Map<String, byte[]> truncatedCandidateMembers = copyMembers(baselineMembers);
            byte[] candidateMagicOnly = Arrays.copyOf(
                    truncatedCandidateMembers.get("candidates.bin"),
                    8
            );
            truncatedCandidateMembers.put("candidates.bin", candidateMagicOnly);
            JSONObject truncatedCandidateManifest = json(
                    truncatedCandidateMembers.get("manifest.json")
            );
            updateMemberMetadata(
                    truncatedCandidateManifest,
                    "candidates.bin",
                    candidateMagicOnly
            );
            truncatedCandidateMembers.put(
                    "manifest.json",
                    jsonBytes(truncatedCandidateManifest)
            );
            writeArchive(truncatedCandidates, truncatedCandidateMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "truncated_candidate_header",
                    () -> openWithActualHash(truncatedCandidates),
                    "truncated candidate header"
            );

            File truncatedScores = new File(workDirectory, "truncated-scores.nkp");
            Map<String, byte[]> truncatedScoreMembers = copyMembers(baselineMembers);
            byte[] scoreMagicOnly = Arrays.copyOf(truncatedScoreMembers.get("scores.bin"), 8);
            truncatedScoreMembers.put("scores.bin", scoreMagicOnly);
            JSONObject truncatedScoreManifest = json(truncatedScoreMembers.get("manifest.json"));
            updateMemberMetadata(truncatedScoreManifest, "scores.bin", scoreMagicOnly);
            truncatedScoreMembers.put("manifest.json", jsonBytes(truncatedScoreManifest));
            writeArchive(truncatedScores, truncatedScoreMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "truncated_score_header",
                    () -> openWithActualHash(truncatedScores),
                    "truncated score header"
            );

            File truncatedTrie = new File(workDirectory, "truncated-trie.nkp");
            Map<String, byte[]> truncatedTrieMembers = copyMembers(baselineMembers);
            byte[] trieMagicOnly = Arrays.copyOf(truncatedTrieMembers.get("surface.trie"), 8);
            truncatedTrieMembers.put("surface.trie", trieMagicOnly);
            JSONObject truncatedTrieManifest = json(truncatedTrieMembers.get("manifest.json"));
            updateMemberMetadata(truncatedTrieManifest, "surface.trie", trieMagicOnly);
            truncatedTrieMembers.put("manifest.json", jsonBytes(truncatedTrieManifest));
            writeArchive(truncatedTrie, truncatedTrieMembers, null);
            passed += recordExpectedFailure(
                    output,
                    "truncated_trie_header",
                    () -> openWithActualHash(truncatedTrie),
                    "truncated trie header"
            );

            File missingFile = new File(workDirectory, "does-not-exist.nkp");
            passed += recordExpectedFailure(
                    output,
                    "missing_file",
                    () -> openAndClose(missingFile, null),
                    "not a regular file"
            );

            File symbolicLink = new File(workDirectory, "symbolic-link.nkp");
            Files.createSymbolicLink(symbolicLink.toPath(), baseline.toPath());
            passed += recordExpectedFailure(
                    output,
                    "symbolic_link",
                    () -> openAndClose(symbolicLink, baselineSha256),
                    "symbolic link"
            );

            final int expectedNegativeCases = 17;
            if (passed != expectedNegativeCases) {
                throw new AssertionError(
                        "corruption case count mismatch: " + passed + " != "
                                + expectedNegativeCases
                );
            }
            output.putInt("negative_case_count", expectedNegativeCases);
            output.putInt("negative_case_pass_count", passed);
            output.putBoolean("internal_catalog_reader_verified", true);
            output.putString("status", "ok");
            resultCode = Activity.RESULT_OK;
        } catch (Throwable failure) {
            Log.e(TAG, "bundle corruption harness failed", failure);
            output.putString("status", "error");
            output.putString("error", failure.toString());
        } finally {
            if (workDirectory != null) {
                deleteTree(workDirectory);
            }
        }
        finish(resultCode, output);
    }

    private static int recordExpectedFailure(
            Bundle output,
            String label,
            ThrowingAction action,
            String expectedMessage
    ) throws Exception {
        try {
            action.run();
        } catch (Throwable failure) {
            if (!(failure instanceof IOException)
                    && !(failure instanceof SecurityException)) {
                throw new AssertionError(
                        label + " escaped as a non-contract exception",
                        failure
                );
            }
            if (!causeChainContains(failure, expectedMessage)) {
                throw new AssertionError(
                        label + " failed for the wrong reason; expected message containing "
                                + expectedMessage,
                        failure
                );
            }
            output.putBoolean(label, true);
            return 1;
        }
        throw new AssertionError(label + " was accepted");
    }

    private static boolean causeChainContains(Throwable failure, String expected) {
        Set<Throwable> visited = new HashSet<>();
        Throwable current = failure;
        while (current != null && visited.add(current)) {
            if (current.getMessage() != null && current.getMessage().contains(expected)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static void openWithActualHash(File file) throws Exception {
        openAndClose(file, sha256(file));
    }

    private static void openAndClose(
            File file,
            String expectedSha256
    ) throws Exception {
        try (NkpBundle ignored = NkpBundle.open(file, expectedSha256, true)) {
            // A successful open is an expected-failure assertion failure at the caller.
        }
    }

    private static Map<String, byte[]> readMembers(File file) throws IOException {
        Map<String, byte[]> result = new TreeMap<>();
        try (ZipFile archive = new ZipFile(file)) {
            Enumeration<? extends ZipEntry> entries = archive.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (entry.isDirectory() || result.containsKey(entry.getName())) {
                    throw new IOException("baseline archive member identity is invalid");
                }
                result.put(entry.getName(), readBounded(archive.getInputStream(entry)));
            }
        }
        if (!result.keySet().equals(EXPECTED_MEMBERS)) {
            throw new IOException("baseline archive member set is invalid: " + result.keySet());
        }
        return result;
    }

    private static Map<String, byte[]> copyMembers(Map<String, byte[]> source) {
        Map<String, byte[]> copy = new TreeMap<>();
        for (Map.Entry<String, byte[]> entry : source.entrySet()) {
            copy.put(entry.getKey(), entry.getValue().clone());
        }
        return copy;
    }

    private static void writeArchive(
            File output,
            Map<String, byte[]> members,
            String deflatedMember
    ) throws IOException {
        try (ZipOutputStream archive = new ZipOutputStream(new FileOutputStream(output, false))) {
            for (Map.Entry<String, byte[]> member : new TreeMap<>(members).entrySet()) {
                byte[] data = member.getValue();
                ZipEntry entry = new ZipEntry(member.getKey());
                entry.setTime(0L);
                if (member.getKey().equals(deflatedMember)) {
                    entry.setMethod(ZipEntry.DEFLATED);
                } else {
                    CRC32 crc = new CRC32();
                    crc.update(data);
                    entry.setMethod(ZipEntry.STORED);
                    entry.setSize(data.length);
                    entry.setCompressedSize(data.length);
                    entry.setCrc(crc.getValue());
                }
                archive.putNextEntry(entry);
                archive.write(data);
                archive.closeEntry();
            }
        }
    }

    private static JSONObject json(byte[] data) throws Exception {
        return new JSONObject(new String(data, StandardCharsets.UTF_8));
    }

    private static byte[] jsonBytes(JSONObject value) {
        return (value.toString() + "\n").getBytes(StandardCharsets.UTF_8);
    }

    private static void updateMemberMetadata(
            JSONObject manifest,
            String member,
            byte[] data
    ) throws Exception {
        JSONObject metadata = manifest.getJSONObject("members").getJSONObject(member);
        metadata.put("bytes", data.length);
        metadata.put("sha256", sha256(data));
    }

    private static void copyAsset(Context context, File output) throws IOException {
        try (InputStream input = context.getAssets().open(PACK_ASSET);
             FileOutputStream stream = new FileOutputStream(output, false)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            long total = 0;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > 256L * 1024L * 1024L) {
                    throw new IOException("baseline NKP exceeds v0 size limit");
                }
                stream.write(buffer, 0, read);
            }
            stream.getFD().sync();
            if (total == 0) {
                throw new IOException("baseline NKP asset is empty");
            }
        }
    }

    private static byte[] readBounded(InputStream input) throws IOException {
        try (InputStream source = input;
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[16 * 1024];
            int total = 0;
            int read;
            while ((read = source.read(buffer)) != -1) {
                total += read;
                if (total > MAX_MEMBER_BYTES) {
                    throw new IOException("baseline NKP member exceeds v0 size limit");
                }
                output.write(buffer, 0, read);
            }
            return output.toByteArray();
        }
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
        return hex(newDigest().digest(data));
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
            output.append(Character.forDigit((value >>> 4) & 0x0f, 16));
            output.append(Character.forDigit(value & 0x0f, 16));
        }
        return output.toString();
    }

    private static void assertEquals(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + ", got " + actual);
        }
    }

    private static void deleteTree(File path) {
        if (Files.isSymbolicLink(path.toPath())) {
            path.delete();
            return;
        }
        File[] children = path.listFiles();
        if (children != null) {
            for (File child : children) {
                deleteTree(child);
            }
        }
        path.delete();
    }

    private interface ThrowingAction {
        void run() throws Exception;
    }
}
