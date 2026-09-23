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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Reviewed long-press variants, held outside the layout lock.
 *
 * <p>The generated artifact is validated at build time against the compiled layout, so a
 * variant can only attach to a key the layout renders and can only emit scalars that
 * layout already produces. This class re-checks the key binding at attach time, so a
 * layout change can never silently re-point a variant set at a different letter.
 */
public final class KeyAlternatesCatalog {
    static final String ASSET_PATH = "nepa-layouts/key-alternates-v1.json";
    static final int SUPPORTED_ASSET_VERSION = 1;
    private static final int MAX_ASSET_BYTES = 256 * 1024;

    private final Map<String, Map<String, List<String>>> byLayout;

    private KeyAlternatesCatalog(Map<String, Map<String, List<String>>> byLayout) {
        this.byLayout = Collections.unmodifiableMap(byLayout);
    }

    public static KeyAlternatesCatalog load(Context context) {
        Objects.requireNonNull(context, "context");
        JSONObject root;
        try (InputStream stream = context.getAssets().open(ASSET_PATH)) {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int read;
            while ((read = stream.read(chunk)) >= 0) {
                buffer.write(chunk, 0, read);
                if (buffer.size() > MAX_ASSET_BYTES) {
                    throw new IllegalStateException("key alternates asset is too large");
                }
            }
            root = new JSONObject(new String(buffer.toByteArray(), StandardCharsets.UTF_8));
        } catch (IOException missing) {
            // Long-press variants are an enhancement; their absence must not break typing.
            return new KeyAlternatesCatalog(new LinkedHashMap<>());
        } catch (JSONException malformed) {
            throw new IllegalStateException("key alternates asset is malformed", malformed);
        }
        try {
            int version = root.optInt("asset_version", -1);
            if (version != SUPPORTED_ASSET_VERSION) {
                throw new IllegalStateException("unsupported key alternates version: " + version);
            }
            Map<String, Map<String, List<String>>> layouts = new LinkedHashMap<>();
            JSONArray rawLayouts = root.getJSONArray("layouts");
            for (int index = 0; index < rawLayouts.length(); index++) {
                JSONObject rawLayout = rawLayouts.getJSONObject(index);
                String layoutId = rawLayout.getString("layout_id");
                Map<String, List<String>> keys = new LinkedHashMap<>();
                JSONArray rawKeys = rawLayout.getJSONArray("keys");
                for (int position = 0; position < rawKeys.length(); position++) {
                    JSONObject rawKey = rawKeys.getJSONObject(position);
                    JSONArray rawAlternates = rawKey.getJSONArray("alternates");
                    List<String> alternates = new ArrayList<>(rawAlternates.length());
                    for (int slot = 0; slot < rawAlternates.length(); slot++) {
                        String value = rawAlternates.getString(slot);
                        if (value.isEmpty()) {
                            throw new IllegalStateException("empty alternate");
                        }
                        alternates.add(value);
                    }
                    if (alternates.isEmpty()) {
                        throw new IllegalStateException("key declares no alternates");
                    }
                    keys.put(rawKey.getString("key_id"), Collections.unmodifiableList(alternates));
                }
                layouts.put(layoutId, Collections.unmodifiableMap(keys));
            }
            return new KeyAlternatesCatalog(layouts);
        } catch (JSONException malformed) {
            throw new IllegalStateException("key alternates asset is malformed", malformed);
        }
    }

    /**
     * Returns the layout's keys with reviewed variants attached. Keys without variants,
     * and keys whose text no longer matches, are returned unchanged.
     */
    public KeyboardLayouts.Layout attach(KeyboardLayouts.Layout layout) {
        Objects.requireNonNull(layout, "layout");
        Map<String, List<String>> keys = byLayout.get(layout.sourceLayoutId());
        if (keys == null || keys.isEmpty()) {
            return layout;
        }
        return layout.withKeyAlternates(keys);
    }

    int layoutCountForTesting() {
        return byLayout.size();
    }

    int keyCountForTesting() {
        int total = 0;
        for (Map<String, List<String>> keys : byLayout.values()) {
            total += keys.size();
        }
        return total;
    }
}
