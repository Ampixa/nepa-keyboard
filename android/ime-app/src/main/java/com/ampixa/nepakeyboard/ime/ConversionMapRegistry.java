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

/** Fail-closed registry for exact staged conversion-map profile bindings. */
public final class ConversionMapRegistry {
    private static final String MANIFEST_ASSET = "nepa-conversions/manifest.json";
    private static final int MAX_MANIFEST_BYTES = 128 * 1024;
    private static final int MAX_MAPS = 64;
    private static final Set<String> ROW_FIELDS = Collections.unmodifiableSet(
            new HashSet<>(java.util.Arrays.asList(
                    "profile_id",
                    "converter_id",
                    "asset_path",
                    "artifact_sha256"
            ))
    );
    private static final Pattern SAFE_ID = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
    );

    private ConversionMapRegistry() {
    }

    public static List<ConversionMapSpec> installed(Context context) {
        Set<String> expectedProfileIds = new HashSet<>();
        for (KeyboardProfile profile : LanguageRegistry.available()) {
            if (profile.artifactKind() == KeyboardProfile.ArtifactKind.NCM) {
                expectedProfileIds.add(profile.id());
            }
        }
        if (expectedProfileIds.isEmpty()) {
            return Collections.emptyList();
        }
        if (context == null) {
            return Collections.emptyList();
        }
        try {
            JSONObject root = new JSONObject(new String(
                    readBoundedManifest(context),
                    StandardCharsets.UTF_8
            ));
            if (root.length() != 1 || !root.has("conversions")) {
                return Collections.emptyList();
            }
            JSONArray rows = root.optJSONArray("conversions");
            if (rows == null || rows.length() < 1 || rows.length() > MAX_MAPS) {
                return Collections.emptyList();
            }
            List<ConversionMapSpec> result = new ArrayList<>(rows.length());
            Set<String> profileIds = new HashSet<>();
            Map<String, String> bindingByConverterId = new HashMap<>();
            Map<String, String> bindingByAssetPath = new HashMap<>();
            for (int index = 0; index < rows.length(); index++) {
                JSONObject row = rows.optJSONObject(index);
                if (row == null || !hasExactFields(row, ROW_FIELDS)) {
                    return Collections.emptyList();
                }
                String profileId = requiredString(row, "profile_id");
                String converterId = requiredString(row, "converter_id");
                String assetPath = requiredString(row, "asset_path");
                String sha256 = requiredString(row, "artifact_sha256")
                        .toLowerCase(java.util.Locale.ROOT);
                KeyboardProfile profile = LanguageRegistry.find(profileId);
                if (!isSafeId(profileId)
                        || !isSafeId(converterId)
                        || profile == null
                        || !profile.isAvailable()
                        || profile.artifactKind() != KeyboardProfile.ArtifactKind.NCM
                        || profile.lookupKind() != KeyboardProfile.LookupKind.CONVERSION
                        || !"converter".equals(profile.engineKind())
                        || !converterId.equals(profile.conversionBinding())
                        || !ConversionMapSpec.isSafeAssetPath(assetPath)
                        || !sha256.matches("[0-9a-f]{64}")
                        || !profileIds.add(profileId)) {
                    return Collections.emptyList();
                }
                String artifactBinding = assetPath + "\u0000" + sha256;
                String priorId = bindingByConverterId.putIfAbsent(
                        converterId,
                        artifactBinding
                );
                if (priorId != null && !priorId.equals(artifactBinding)) {
                    return Collections.emptyList();
                }
                String assetBinding = converterId + "\u0000" + sha256;
                String priorPath = bindingByAssetPath.putIfAbsent(assetPath, assetBinding);
                if (priorPath != null && !priorPath.equals(assetBinding)) {
                    return Collections.emptyList();
                }
                result.add(ConversionMapSpec.fromAsset(
                        context,
                        profileId,
                        converterId,
                        assetPath,
                        sha256
                ));
            }
            if (!profileIds.equals(expectedProfileIds)) {
                return Collections.emptyList();
            }
            return Collections.unmodifiableList(result);
        } catch (IOException | JSONException | RuntimeException invalidManifest) {
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
                    throw new IOException("conversion manifest exceeds size limit");
                }
                output.write(buffer, 0, read);
            }
            if (total == 0) {
                throw new IOException("conversion manifest is empty");
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
