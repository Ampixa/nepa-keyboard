package com.ampixa.nepakeyboard.ime;

import android.content.Context;
import android.content.res.AssetManager;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * The bundled emoji repertoire.
 *
 * <p>Read once from a generated asset so the runtime never guesses at emoji support:
 * every entry declares the Android release that first shipped its glyphs, and entries
 * newer than the running platform are dropped rather than rendered as blank boxes.
 */
public final class EmojiCatalog {
    static final String ASSET_PATH = "nepa-emoji/emoji-v1.json";
    static final int SUPPORTED_CATALOG_VERSION = 1;
    private static final int MAX_ASSET_BYTES = 1024 * 1024;

    private final List<Category> categories;
    private final int totalEmoji;

    private EmojiCatalog(List<Category> categories, int totalEmoji) {
        this.categories = Collections.unmodifiableList(categories);
        this.totalEmoji = totalEmoji;
    }

    public static EmojiCatalog load(Context context) {
        Objects.requireNonNull(context, "context");
        JSONObject root = readAsset(context.getAssets());
        int catalogVersion = root.optInt("catalog_version", -1);
        if (catalogVersion != SUPPORTED_CATALOG_VERSION) {
            throw new IllegalStateException("unsupported emoji catalog version: " + catalogVersion);
        }
        try {
            JSONArray order = root.getJSONArray("category_order");
            JSONArray rawCategories = root.getJSONArray("categories");
            if (order.length() != rawCategories.length()) {
                throw new IllegalStateException("emoji catalog order does not match its categories");
            }
            List<Category> categories = new ArrayList<>();
            int total = 0;
            for (int index = 0; index < rawCategories.length(); index++) {
                JSONObject rawCategory = rawCategories.getJSONObject(index);
                String id = rawCategory.getString("id");
                if (!id.equals(order.getString(index))) {
                    throw new IllegalStateException("emoji catalog category is out of order: " + id);
                }
                JSONArray rawEmoji = rawCategory.getJSONArray("emoji");
                List<String> supported = new ArrayList<>(rawEmoji.length());
                for (int position = 0; position < rawEmoji.length(); position++) {
                    JSONObject entry = rawEmoji.getJSONObject(position);
                    String value = entry.getString("value");
                    if (value.isEmpty()) {
                        throw new IllegalStateException("emoji catalog has an empty value");
                    }
                    if (Build.VERSION.SDK_INT >= entry.getInt("min_api")) {
                        supported.add(value);
                    }
                }
                total += supported.size();
                // A category can legitimately empty out on an old platform; it is hidden
                // rather than shown as an empty grid.
                if (!supported.isEmpty()) {
                    categories.add(new Category(id, Collections.unmodifiableList(supported)));
                }
            }
            if (categories.isEmpty()) {
                throw new IllegalStateException("emoji catalog is empty on this platform");
            }
            return new EmojiCatalog(categories, total);
        } catch (JSONException malformed) {
            throw new IllegalStateException("emoji catalog is malformed", malformed);
        }
    }

    private static JSONObject readAsset(AssetManager assets) {
        try (InputStream stream = assets.open(ASSET_PATH)) {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int read;
            while ((read = stream.read(chunk)) >= 0) {
                buffer.write(chunk, 0, read);
                if (buffer.size() > MAX_ASSET_BYTES) {
                    throw new IllegalStateException("emoji catalog asset is too large");
                }
            }
            return new JSONObject(new String(buffer.toByteArray(), StandardCharsets.UTF_8));
        } catch (IOException | JSONException unreadable) {
            throw new IllegalStateException("emoji catalog asset is unreadable", unreadable);
        }
    }

    public List<Category> categories() {
        return categories;
    }

    public int totalEmoji() {
        return totalEmoji;
    }

    /** One panel tab. */
    public static final class Category {
        private final String id;
        private final List<String> emoji;

        Category(String id, List<String> emoji) {
            this.id = id;
            this.emoji = emoji;
        }

        public String id() {
            return id;
        }

        public List<String> emoji() {
            return emoji;
        }
    }
}
