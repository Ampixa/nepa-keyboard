package com.ampixa.nepakeyboard.ime;

import android.content.Context;
import android.content.res.AssetManager;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** The bundled Roman-to-script transliteration maps, keyed by profile. */
public final class TransliterationCatalog {
    static final String ASSET_DIRECTORY = "nepa-translit";
    static final int SUPPORTED_ASSET_VERSION = 1;
    private static final int MAX_ASSET_BYTES = 512 * 1024;

    /**
     * Which map serves each selectable profile. A profile is only listed when its
     * output script matches the map, so a profile can never emit a foreign script.
     */
    private static final Map<String, String> PROFILE_MAPS;

    static {
        Map<String, String> maps = new LinkedHashMap<>();
        maps.put("npi-Deva-NP", "npi-Latn-Deva-v1.json");
        maps.put("new-Newa-NP", "new-Latn-Newa-v1.json");
        maps.put("new-Deva-NP", "npi-Latn-Deva-v1.json");
        maps.put("lif-Limb-NP", "lif-Latn-Limb-v1.json");
        // Lepcha has no direct-script layout, so phonetic input is the only way to
        // type it. lep-Latn-Lepc-NP is carried by the reviewed transliteration
        // supplement; the direct profile stays inert until it gains a layout.
        maps.put("lep-Latn-Lepc-NP", "lep-Latn-Lepc-v1.json");
        maps.put("lep-Lepc-NP", "lep-Latn-Lepc-v1.json");
        // Maithili in Tirhuta. There is no Roman-to-Tirhuta profile yet, only the
        // direct one, so this cannot become reachable until such a profile exists.
        maps.put("mai-Tirh-NP", "mai-Latn-Tirh-v1.json");
        PROFILE_MAPS = Collections.unmodifiableMap(maps);
    }

    private final Map<String, TransliterationEngine> byProfile;

    private TransliterationCatalog(Map<String, TransliterationEngine> byProfile) {
        this.byProfile = Collections.unmodifiableMap(byProfile);
    }

    public static TransliterationCatalog load(Context context) {
        Objects.requireNonNull(context, "context");
        AssetManager assets = context.getAssets();
        Map<String, TransliterationEngine> loaded = new LinkedHashMap<>();
        Map<String, TransliterationEngine> byFile = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : PROFILE_MAPS.entrySet()) {
            TransliterationEngine engine = byFile.get(entry.getValue());
            if (engine == null) {
                engine = read(assets, entry.getValue());
                if (engine == null) {
                    // A missing map simply means that profile cannot transliterate.
                    continue;
                }
                byFile.put(entry.getValue(), engine);
            }
            KeyboardProfile profile = LanguageRegistry.find(entry.getKey());
            if (profile == null || !profile.isAvailable()) {
                continue;
            }
            String supplementAsset = LanguageRegistry.transliterationMapAsset(entry.getKey());
            if (supplementAsset != null && !supplementAsset.equals(entry.getValue())) {
                // The reviewed supplement is the authority for these profiles; a
                // disagreeing hardcoded binding must fail rather than silently win.
                throw new IllegalStateException(
                        "transliteration binding disagrees with the reviewed supplement: "
                                + entry.getKey()
                );
            }
            if (!profile.outputScript().equals(engine.outputScript())) {
                throw new IllegalStateException(
                        "transliteration map script does not match profile: " + entry.getKey()
                );
            }
            loaded.put(entry.getKey(), engine);
        }
        for (KeyboardProfile profile : LanguageRegistry.available()) {
            String asset = LanguageRegistry.transliterationMapAsset(profile.id());
            if (asset == null || loaded.containsKey(profile.id())) {
                continue;
            }
            TransliterationEngine engine = byFile.get(asset);
            if (engine == null) {
                engine = read(assets, asset);
                if (engine == null) {
                    throw new IllegalStateException(
                            "reviewed transliteration supplement names a missing map: " + asset
                    );
                }
                byFile.put(asset, engine);
            }
            if (!profile.outputScript().equals(engine.outputScript())) {
                throw new IllegalStateException(
                        "transliteration map script does not match profile: " + profile.id()
                );
            }
            loaded.put(profile.id(), engine);
        }
        return new TransliterationCatalog(loaded);
    }

    private static TransliterationEngine read(AssetManager assets, String fileName) {
        String path = ASSET_DIRECTORY + "/" + fileName;
        try (InputStream stream = assets.open(path)) {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int count;
            while ((count = stream.read(chunk)) >= 0) {
                buffer.write(chunk, 0, count);
                if (buffer.size() > MAX_ASSET_BYTES) {
                    throw new IllegalStateException("transliteration map is too large: " + path);
                }
            }
            JSONObject root = new JSONObject(
                    new String(buffer.toByteArray(), StandardCharsets.UTF_8)
            );
            int version = root.optInt("asset_version", -1);
            if (version != SUPPORTED_ASSET_VERSION) {
                throw new IllegalStateException("unsupported transliteration version: " + version);
            }
            return new TransliterationEngine(
                    root.getString("map_id"),
                    root.getString("output_script"),
                    table(root, "consonants"),
                    table(root, "independent_vowels"),
                    table(root, "vowel_signs"),
                    table(root, "standalone"),
                    table(root, "final_forms"),
                    table(root, "words"),
                    root.optString("virama", ""),
                    root.optString("explicit_virama", ""),
                    policy(root.getString("final_consonant"))
            );
        } catch (IOException missing) {
            return null;
        } catch (org.json.JSONException malformed) {
            throw new IllegalStateException("transliteration map is malformed: " + path, malformed);
        }
    }

    private static TransliterationEngine.FinalConsonant policy(String declared) {
        switch (declared) {
            case "inherent":
                return TransliterationEngine.FinalConsonant.INHERENT;
            case "virama":
                return TransliterationEngine.FinalConsonant.VIRAMA;
            case "final_form":
                return TransliterationEngine.FinalConsonant.FINAL_FORM;
            default:
                throw new IllegalStateException("unknown final_consonant policy: " + declared);
        }
    }

    private static Map<String, String> table(JSONObject root, String field) {
        Map<String, String> values = new LinkedHashMap<>();
        JSONObject raw = root.optJSONObject(field);
        if (raw == null) {
            return values;
        }
        for (Iterator<String> keys = raw.keys(); keys.hasNext(); ) {
            String key = keys.next();
            values.put(key, raw.optString(key, ""));
        }
        return values;
    }

    /** The engine for a profile, or null when that profile cannot transliterate. */
    public TransliterationEngine forProfile(KeyboardProfile profile) {
        return profile == null ? null : byProfile.get(profile.id());
    }

    public boolean supports(KeyboardProfile profile) {
        return forProfile(profile) != null;
    }

    int engineCountForTesting() {
        return byProfile.size();
    }

    /**
     * Loads a bundled map straight from assets, bypassing profile binding.
     *
     * <p>A map whose profiles are still blocked reaches no profile, so this is the
     * only way to hold such a map to the same on-device vectors as the rest.
     */
    static TransliterationEngine engineFileForTesting(Context context, String fileName) {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(fileName, "fileName");
        return read(context.getAssets(), fileName);
    }
}
