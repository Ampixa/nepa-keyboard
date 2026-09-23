package com.ampixa.nepakeyboard.ime;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/** One rendered key; actions remain distinct from text payloads. */
public final class KeySpec {
    public enum Action {
        TEXT,
        SHIFT,
        DELETE,
        ENTER,
        SPACE,
        LANGUAGE,
        SYMBOLS,
        LETTERS
    }

    public enum HoldAction {
        OPEN_LANGUAGE_PICKER
    }

    /** Runtime handling policy for a reviewed text-bearing layout key. */
    public enum InputPolicy {
        DEFAULT,
        ORTHOGRAPHIC_WORD,
        INTRA_WORD_PUNCTUATION,
        DEVA_CONJUNCT_JOINER,
        DEVA_TERMINAL_ZWNJ,
        NEWA_CONJUNCT_JOINER
    }

    private static final String PROFILE_NATIVE_NAME = "${profile.native_name}";
    private static final String PROFILE_DISPLAY_NAME = "${profile.display_name}";

    private final String keyId;
    private final String label;
    private final String text;
    private final String contentDescription;
    private final Action action;
    private final InputPolicy inputPolicy;
    private final int widthUnits;
    private final HoldAction holdAction;
    private final List<String> alternates;

    private KeySpec(
            String keyId,
            String label,
            String text,
            String contentDescription,
            Action action,
            InputPolicy inputPolicy,
            int widthUnits,
            HoldAction holdAction,
            List<String> alternates
    ) {
        this.keyId = require(keyId, "keyId");
        this.label = Objects.requireNonNull(label, "label");
        this.text = text;
        this.contentDescription = Objects.requireNonNull(contentDescription, "contentDescription");
        this.action = Objects.requireNonNull(action, "action");
        this.inputPolicy = inputPolicy;
        validateInputPolicy(action, text, inputPolicy);
        if (widthUnits <= 0) {
            throw new IllegalArgumentException("key width must be positive");
        }
        this.widthUnits = widthUnits;
        this.holdAction = holdAction;
        if (alternates == null || alternates.isEmpty()) {
            this.alternates = Collections.emptyList();
        } else {
            if (action != Action.TEXT) {
                throw new IllegalArgumentException("only a text key can carry alternates");
            }
            List<String> frozen = new ArrayList<>(alternates.size());
            for (String value : alternates) {
                if (value == null || value.isEmpty()) {
                    throw new IllegalArgumentException("alternate must not be empty");
                }
                if (value.equals(text) || frozen.contains(value)) {
                    throw new IllegalArgumentException("alternate must be distinct: " + value);
                }
                frozen.add(value);
            }
            this.alternates = Collections.unmodifiableList(frozen);
        }
    }

    static KeySpec generatedText(
            String keyId,
            String label,
            String text,
            String contentDescription,
            InputPolicy inputPolicy,
            int widthUnits,
            HoldAction holdAction
    ) {
        return generatedText(
                keyId,
                label,
                text,
                contentDescription,
                inputPolicy,
                widthUnits,
                holdAction,
                null
        );
    }

    static KeySpec generatedText(
            String keyId,
            String label,
            String text,
            String contentDescription,
            InputPolicy inputPolicy,
            int widthUnits,
            HoldAction holdAction,
            String[] alternates
    ) {
        return new KeySpec(
                keyId,
                label,
                require(text, "text"),
                contentDescription,
                Action.TEXT,
                Objects.requireNonNull(inputPolicy, "inputPolicy"),
                widthUnits,
                holdAction,
                alternates == null ? null : java.util.Arrays.asList(alternates)
        );
    }

    static KeySpec generatedAction(
            String keyId,
            String label,
            String contentDescription,
            Action action,
            int widthUnits,
            HoldAction holdAction
    ) {
        if (action == Action.TEXT) {
            throw new IllegalArgumentException("generated action key cannot use TEXT");
        }
        return new KeySpec(
                keyId,
                label,
                null,
                contentDescription,
                action,
                null,
                widthUnits,
                holdAction,
                null
        );
    }

    /** Attaches reviewed long-press variants to a text key. */
    KeySpec withAlternates(List<String> values) {
        if (action != Action.TEXT) {
            throw new IllegalStateException("only a text key can carry alternates");
        }
        return new KeySpec(
                keyId,
                label,
                text,
                contentDescription,
                action,
                inputPolicy,
                widthUnits,
                holdAction,
                values
        );
    }

    KeySpec bindProfile(KeyboardProfile profile) {
        Objects.requireNonNull(profile, "profile");
        String boundLabel = bind(label, profile);
        String boundDescription = bind(contentDescription, profile);
        if (boundLabel.equals(label) && boundDescription.equals(contentDescription)) {
            return this;
        }
        return new KeySpec(
                keyId,
                boundLabel,
                text,
                boundDescription,
                action,
                inputPolicy,
                widthUnits,
                holdAction,
                alternates
        );
    }

    public String keyId() {
        return keyId;
    }

    public String label() {
        return label;
    }

    public String text() {
        return text;
    }

    public String contentDescription() {
        return contentDescription;
    }

    public Action action() {
        return action;
    }

    public InputPolicy inputPolicy() {
        return inputPolicy;
    }

    public int widthUnits() {
        return widthUnits;
    }

    public HoldAction holdAction() {
        return holdAction;
    }

    /** Long-press variants in display order; empty when the key has none. */
    public List<String> alternates() {
        return alternates;
    }

    public boolean hasAlternates() {
        return !alternates.isEmpty();
    }

    private static String bind(String value, KeyboardProfile profile) {
        return value
                .replace(PROFILE_NATIVE_NAME, profile.nativeName())
                .replace(PROFILE_DISPLAY_NAME, profile.displayName());
    }

    private static void validateInputPolicy(
            Action action,
            String text,
            InputPolicy inputPolicy
    ) {
        if (action != Action.TEXT) {
            if (text != null || inputPolicy != null) {
                throw new IllegalArgumentException("action key cannot carry text input policy");
            }
            return;
        }
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(inputPolicy, "inputPolicy");
        switch (inputPolicy) {
            case DEFAULT:
                if (text.indexOf('\u200c') >= 0 || text.indexOf('\u200d') >= 0) {
                    throw new IllegalArgumentException(
                            "default text key cannot carry a conjunct joiner"
                    );
                }
                return;
            case ORTHOGRAPHIC_WORD:
                if (!"\u2018".equals(text)) {
                    throw new IllegalArgumentException(
                            "orthographic word key must carry U+2018"
                    );
                }
                return;
            case INTRA_WORD_PUNCTUATION:
                if (!isIntraWordPunctuation(text)) {
                    throw new IllegalArgumentException(
                            "intra-word punctuation key must carry hyphen, slash, backslash, or colon"
                    );
                }
                return;
            case DEVA_CONJUNCT_JOINER:
                if (!"\u200c".equals(text) && !"\u200d".equals(text)) {
                    throw new IllegalArgumentException(
                            "Devanagari conjunct joiner key must carry U+200C or U+200D"
                    );
                }
                return;
            case DEVA_TERMINAL_ZWNJ:
                if (!"\u200c".equals(text)) {
                    throw new IllegalArgumentException(
                            "Devanagari terminal ZWNJ key must carry U+200C"
                    );
                }
                return;
            case NEWA_CONJUNCT_JOINER:
                if (!"\u200c".equals(text) && !"\u200d".equals(text)) {
                    throw new IllegalArgumentException(
                            "Newa conjunct joiner key must carry U+200C or U+200D"
                    );
                }
                return;
            default:
                throw new IllegalStateException("unknown input policy: " + inputPolicy);
        }
    }

    private static boolean isIntraWordPunctuation(String text) {
        return "-".equals(text)
                || "/".equals(text)
                || "\\".equals(text)
                || ":".equals(text);
    }

    private static String require(String value, String label) {
        Objects.requireNonNull(value, label);
        if (value.isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        return value;
    }
}
