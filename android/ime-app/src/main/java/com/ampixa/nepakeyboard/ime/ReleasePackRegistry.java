package com.ampixa.nepakeyboard.ime;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Fail-closed reader for the generated, SHA-pinned product-pack asset manifest.
 *
 * <p>Builds without validated staged assets expose an empty registry. Variant
 * staging decides whether the manifest represents the internal product catalog
 * or the isolated public/export catalog; pack opening remains the responsibility
 * of that variant's reader authority.</p>
 */
public final class ReleasePackRegistry {
    private static final String MANIFEST_ASSET = "nepa-packs/manifest.json";
    private static final int MAX_MANIFEST_BYTES = 256 * 1024;
    private static final int MAX_PACKS = 128;
    private static final Set<String> ROW_FIELDS = Collections.unmodifiableSet(
            new HashSet<>(java.util.Arrays.asList(
                    "profile_id",
                    "pack_id",
                    "asset_path",
                    "artifact_sha256"
            ))
    );
    private static final Pattern SAFE_ID = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
    );

    private ReleasePackRegistry() {
    }

    public static List<ReleasePackSpec> installed(Context context) {
        if (context == null) {
            return Collections.emptyList();
        }
        try {
            byte[] encoded = readBoundedManifest(context);
            JSONObject root = new JSONObject(new String(encoded, StandardCharsets.UTF_8));
            if (root.length() != 1 || !root.has("packs")) {
                return Collections.emptyList();
            }
            JSONArray rows = root.optJSONArray("packs");
            if (rows == null || rows.length() < 1 || rows.length() > MAX_PACKS) {
                return Collections.emptyList();
            }

            List<ReleasePackSpec> result = new ArrayList<>(rows.length());
            Set<String> profileIds = new HashSet<>();
            Map<String, String> bindingByPackId = new HashMap<>();
            Map<String, String> bindingByAssetPath = new HashMap<>();
            for (int index = 0; index < rows.length(); index++) {
                JSONObject row = rows.optJSONObject(index);
                if (row == null || !hasExactFields(row, ROW_FIELDS)) {
                    return Collections.emptyList();
                }
                String profileId = requiredString(row, "profile_id");
                String packId = requiredString(row, "pack_id");
                String assetPath = requiredString(row, "asset_path");
                String artifactSha256 = requiredString(row, "artifact_sha256")
                        .toLowerCase(java.util.Locale.ROOT);
                KeyboardProfile profile = LanguageRegistry.find(profileId);
                if (!isSafeId(profileId)
                        || !isSafeId(packId)
                        || profile == null
                        || !profile.isAvailable()
                        || !packId.equals(profile.packBinding())
                        || !ReleasePackSpec.isSafeAssetPath(assetPath)
                        || !artifactSha256.matches("[0-9a-f]{64}")
                        || !profileIds.add(profileId)) {
                    return Collections.emptyList();
                }

                String artifactBinding = assetPath + "\u0000" + artifactSha256;
                String priorPackBinding = bindingByPackId.putIfAbsent(packId, artifactBinding);
                if (priorPackBinding != null && !priorPackBinding.equals(artifactBinding)) {
                    return Collections.emptyList();
                }
                String packBinding = packId + "\u0000" + artifactSha256;
                String priorAssetBinding = bindingByAssetPath.putIfAbsent(assetPath, packBinding);
                if (priorAssetBinding != null && !priorAssetBinding.equals(packBinding)) {
                    return Collections.emptyList();
                }
                result.add(ReleasePackSpec.fromAsset(
                        context,
                        profileId,
                        packId,
                        assetPath,
                        artifactSha256
                ));
            }
            Set<String> availableProfileIds = new HashSet<>();
            for (KeyboardProfile profile : LanguageRegistry.available()) {
                // A transliteration-only profile is served by a reviewed map, not by a
                // dictionary pack, so it must not be expected in the pack manifest.
                if (profile.artifactKind() == KeyboardProfile.ArtifactKind.NKP
                        && !LanguageRegistry.isTransliterationOnly(profile.id())) {
                    availableProfileIds.add(profile.id());
                }
            }
            if (!profileIds.equals(availableProfileIds)) {
                return Collections.emptyList();
            }
            return Collections.unmodifiableList(result);
        } catch (IOException | JSONException | RuntimeException invalidManifest) {
            // Fail closed without logging asset names, paths, or pack metadata.
            return Collections.emptyList();
        }
    }

    private static byte[] readBoundedManifest(Context context) throws IOException {
        try (InputStream input = context.getAssets().open(MANIFEST_ASSET);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8 * 1024];
            int total = 0;
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > MAX_MANIFEST_BYTES) {
                    throw new IOException("product-pack manifest exceeds size limit");
                }
                output.write(buffer, 0, read);
            }
            if (total == 0) {
                throw new IOException("product-pack manifest is empty");
            }
            return output.toByteArray();
        }
    }

    private static boolean hasExactFields(JSONObject row, Set<String> expected) {
        if (row.length() != expected.size()) {
            return false;
        }
        for (String field : expected) {
            if (!row.has(field)) {
                return false;
            }
        }
        return true;
    }

    private static String requiredString(JSONObject row, String name) throws JSONException {
        Object value = row.get(name);
        if (!(value instanceof String) || ((String) value).isEmpty()) {
            throw new JSONException(name + " must be a non-empty string");
        }
        return (String) value;
    }

    private static boolean isSafeId(String value) {
        return SAFE_ID.matcher(value).matches();
    }
}
