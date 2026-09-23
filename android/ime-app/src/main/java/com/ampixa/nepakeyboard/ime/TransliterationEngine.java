package com.ampixa.nepakeyboard.ime;

import java.text.Normalizer;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;

/**
 * Roman-to-script transliteration for one language.
 *
 * <p>Mirrors the reviewed build-time engine exactly: greedy longest-match syllable
 * assembly with an inherent vowel, attached vowel signs, and a declared policy for a
 * consonant that closes a syllable. The same golden vectors are asserted on device.
 */
public final class TransliterationEngine {
    /** How a consonant with no following vowel is rendered. */
    public enum FinalConsonant {
        INHERENT,
        VIRAMA,
        FINAL_FORM
    }

    private static final int MAX_ROMAN_KEY = 8;

    private final String mapId;
    private final String outputScript;
    private final Map<String, String> consonants;
    private final Map<String, String> independentVowels;
    private final Map<String, String> vowelSigns;
    private final Map<String, String> standalone;
    private final Map<String, String> finalForms;
    private final Map<String, String> words;
    private final String virama;
    private final String explicitVirama;
    private final FinalConsonant finalConsonant;

    TransliterationEngine(
            String mapId,
            String outputScript,
            Map<String, String> consonants,
            Map<String, String> independentVowels,
            Map<String, String> vowelSigns,
            Map<String, String> standalone,
            Map<String, String> finalForms,
            Map<String, String> words,
            String virama,
            String explicitVirama,
            FinalConsonant finalConsonant
    ) {
        this.mapId = Objects.requireNonNull(mapId, "mapId");
        this.outputScript = Objects.requireNonNull(outputScript, "outputScript");
        this.consonants = Collections.unmodifiableMap(consonants);
        this.independentVowels = Collections.unmodifiableMap(independentVowels);
        this.vowelSigns = Collections.unmodifiableMap(vowelSigns);
        this.standalone = Collections.unmodifiableMap(standalone);
        this.finalForms = Collections.unmodifiableMap(finalForms);
        this.words = Collections.unmodifiableMap(words);
        this.virama = Objects.requireNonNull(virama, "virama");
        this.explicitVirama = Objects.requireNonNull(explicitVirama, "explicitVirama");
        this.finalConsonant = Objects.requireNonNull(finalConsonant, "finalConsonant");
        if (finalConsonant == FinalConsonant.FINAL_FORM) {
            if (!virama.isEmpty() || !explicitVirama.isEmpty()) {
                throw new IllegalArgumentException(
                        "a script without a virama must not declare one: " + mapId
                );
            }
            if (finalForms.isEmpty()) {
                throw new IllegalArgumentException("final_form map needs coda letters: " + mapId);
            }
        } else if (virama.isEmpty()) {
            throw new IllegalArgumentException("a virama is required: " + mapId);
        }
    }

    public String mapId() {
        return mapId;
    }

    public String outputScript() {
        return outputScript;
    }

    /** Transliterates a complete Roman token. */
    public String transliterate(String text) {
        Objects.requireNonNull(text, "text");
        if (text.isEmpty()) {
            return "";
        }
        String whole = words.get(text);
        if (whole != null) {
            return whole;
        }
        StringBuilder output = new StringBuilder();
        int position = 0;
        while (position < text.length()) {
            String consonantKey = longest(consonants, text, position);
            if (consonantKey != null) {
                int after = position + consonantKey.length();
                String coda = finalForms.get(consonantKey);
                boolean closing = finalConsonant == FinalConsonant.FINAL_FORM
                        && coda != null
                        && longest(vowelSigns, text, after) == null;
                output.append(closing ? coda : consonants.get(consonantKey));
                position = after;
                if (closing) {
                    continue;
                }
                String vowelKey = longest(vowelSigns, text, position);
                if (vowelKey != null) {
                    output.append(vowelSigns.get(vowelKey));
                    position += vowelKey.length();
                } else if (!explicitVirama.isEmpty() && text.startsWith(explicitVirama, position)) {
                    output.append(virama);
                    position += explicitVirama.length();
                } else if (finalConsonant == FinalConsonant.FINAL_FORM) {
                    // No virama exists in this script; the letter keeps its inherent vowel.
                    continue;
                } else if (position >= text.length()
                        && finalConsonant == FinalConsonant.INHERENT) {
                    // A word-final consonant carries its inherent vowel.
                    continue;
                } else {
                    output.append(virama);
                }
                continue;
            }
            String vowelKey = longest(independentVowels, text, position);
            if (vowelKey != null) {
                output.append(independentVowels.get(vowelKey));
                position += vowelKey.length();
                continue;
            }
            String otherKey = longest(standalone, text, position);
            if (otherKey != null) {
                output.append(standalone.get(otherKey));
                position += otherKey.length();
                continue;
            }
            // Unmapped input passes through so the writer never loses characters.
            output.append(text.charAt(position));
            position++;
        }
        return Normalizer.normalize(output, Normalizer.Form.NFC);
    }

    private static String longest(Map<String, String> table, String text, int position) {
        int limit = Math.min(MAX_ROMAN_KEY, text.length() - position);
        for (int length = limit; length > 0; length--) {
            String candidate = text.substring(position, position + length);
            if (table.containsKey(candidate)) {
                return candidate;
            }
        }
        return null;
    }
}
