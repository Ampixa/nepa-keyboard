package com.ampixa.nepakeyboard.conversion;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.Closeable;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Strict reader for canonical Nepa conversion-map v1 JSON artifacts.
 *
 * <p>The matching contract is the same as {@code tools/build_conversion_map.py}:
 * NFC Devanagari input, deterministic leftmost-longest code-point matching,
 * Newa-only output, and complete no-match on an unmapped position. The reader
 * accepts no executable rules, regexes, heuristic fallback, or mixed-script
 * passthrough.</p>
 */
public final class NcmBundle implements Closeable {
    private static final int FORMAT_VERSION = 1;
    private static final int MAX_ARTIFACT_BYTES = 256 * 1024;
    private static final int MAX_RULES = 1024;
    private static final int MAX_SOURCE_CODE_POINTS = 8;
    private static final int MAX_TARGET_CODE_POINTS = 16;
    private static final int MAX_INPUT_CODE_POINTS = 64;
    private static final int MAX_OUTPUT_CODE_POINTS =
            MAX_INPUT_CODE_POINTS * MAX_TARGET_CODE_POINTS;

    private static final String FORMAT = "nepa-conversion-map";
    private static final String NORMALIZATION = "NFC";
    private static final String ALGORITHM = "leftmost-longest-codepoint-v1";
    private static final String UNMAPPED_POLICY = "no-match";
    private static final String JOINER_POLICY = "virama-context-only-v1";
    private static final int DEVA_VIRAMA = 0x094D;
    private static final int NEWA_VIRAMA = 0x11442;
    private static final int ZWNJ = 0x200C;
    private static final int ZWJ = 0x200D;

    private static final Pattern SAFE_ID = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
    );
    private static final Pattern SEMANTIC_VERSION = Pattern.compile(
            "[0-9]+\\.[0-9]+\\.[0-9]+"
    );
    private static final Pattern LANGUAGE = Pattern.compile("[a-z]{3}");
    private static final Set<String> ROOT_FIELDS = Collections.unmodifiableSet(
            new HashSet<>(Arrays.asList(
                    "algorithm",
                    "converter_id",
                    "format",
                    "format_version",
                    "joiner_policy",
                    "language",
                    "mapping_version",
                    "normalization",
                    "output_script",
                    "rule_count",
                    "rules",
                    "source_script",
                    "unmapped_policy"
            ))
    );
    private static final Set<String> RULE_FIELDS = Collections.unmodifiableSet(
            new HashSet<>(Arrays.asList("from", "to"))
    );

    private final String artifactSha256;
    private final String converterId;
    private final String mappingVersion;
    private final String language;
    private final List<Rule> rules;
    private final Map<Integer, List<Rule>> rulesByFirstCodePoint;
    private volatile boolean closed;

    private NcmBundle(
            String artifactSha256,
            String converterId,
            String mappingVersion,
            String language,
            List<Rule> rules
    ) {
        this.artifactSha256 = artifactSha256;
        this.converterId = converterId;
        this.mappingVersion = mappingVersion;
        this.language = language;
        this.rules = Collections.unmodifiableList(new ArrayList<>(rules));
        Map<Integer, List<Rule>> indexed = new HashMap<>();
        for (Rule rule : rules) {
            indexed.computeIfAbsent(rule.sourceCodePoints[0], ignored -> new ArrayList<>())
                    .add(rule);
        }
        Comparator<Rule> matchingOrder = (first, second) -> {
            int byLength = Integer.compare(
                    second.sourceCodePoints.length,
                    first.sourceCodePoints.length
            );
            return byLength != 0
                    ? byLength
                    : compareCodePoints(first.sourceCodePoints, second.sourceCodePoints);
        };
        for (Map.Entry<Integer, List<Rule>> entry : indexed.entrySet()) {
            entry.getValue().sort(matchingOrder);
            entry.setValue(Collections.unmodifiableList(entry.getValue()));
        }
        this.rulesByFirstCodePoint = Collections.unmodifiableMap(indexed);
    }

    /** Opens and fully verifies one canonical JSON {@code .ncm} artifact. */
    public static NcmBundle open(File file, String expectedArtifactSha256) throws IOException {
        Objects.requireNonNull(file, "file");
        if (Files.isSymbolicLink(file.toPath())) {
            throw new IOException("conversion map must not be a symbolic link");
        }
        if (!file.isFile()) {
            throw new IOException("conversion map is not a regular file");
        }
        if (!file.getName().endsWith(".ncm")
                || file.length() <= 0L
                || file.length() > MAX_ARTIFACT_BYTES) {
            throw new IOException("conversion map file is outside the v1 bounds");
        }

        byte[] encoded = readBounded(file);
        String actualSha256 = sha256(encoded);
        String normalizedExpected = requireSha256(expectedArtifactSha256);
        if (!MessageDigest.isEqual(
                decodeSha256(actualSha256),
                decodeSha256(normalizedExpected)
        )) {
            throw new SecurityException("conversion map artifact SHA-256 mismatch");
        }
        if (encoded.length >= 3
                && (encoded[0] & 0xff) == 0xef
                && (encoded[1] & 0xff) == 0xbb
                && (encoded[2] & 0xff) == 0xbf) {
            throw new IOException("conversion map must not contain a UTF-8 BOM");
        }

        String text = decodeStrictUtf8(encoded);
        JSONObject root;
        try {
            root = new JSONObject(text);
        } catch (JSONException invalidJson) {
            throw new IOException("conversion map is invalid JSON", invalidJson);
        }
        Parsed parsed;
        try {
            parsed = parse(root);
        } catch (JSONException invalidShape) {
            throw new IOException("conversion map JSON shape is invalid", invalidShape);
        }
        byte[] canonical = canonicalBytes(parsed);
        if (!MessageDigest.isEqual(encoded, canonical)) {
            throw new IOException("conversion map is not canonical JSON");
        }
        return new NcmBundle(
                actualSha256,
                parsed.converterId,
                parsed.mappingVersion,
                parsed.language,
                parsed.rules
        );
    }

    /** Returns the deterministic conversion, or null when the complete token cannot map. */
    public String convert(String input) {
        if (closed) {
            throw new IllegalStateException("conversion map is closed");
        }
        if (!isValidScriptText(
                input,
                true,
                MAX_INPUT_CODE_POINTS,
                true
        )) {
            return null;
        }
        int[] source = input.codePoints().toArray();
        StringBuilder converted = new StringBuilder();
        int outputCodePoints = 0;
        int index = 0;
        while (index < source.length) {
            Rule match = null;
            List<Rule> candidates = rulesByFirstCodePoint.get(source[index]);
            if (candidates != null) {
                for (Rule candidate : candidates) {
                    if (matches(source, index, candidate.sourceCodePoints)) {
                        match = candidate;
                        break;
                    }
                }
            }
            if (match == null) {
                return null;
            }
            outputCodePoints += match.targetCodePoints.length;
            if (outputCodePoints > MAX_OUTPUT_CODE_POINTS) {
                return null;
            }
            converted.append(match.target);
            index += match.sourceCodePoints.length;
        }
        String output = converted.toString();
        return isValidScriptText(
                output,
                false,
                MAX_OUTPUT_CODE_POINTS,
                true
        ) ? output : null;
    }

    public String artifactSha256() {
        return artifactSha256;
    }

    public String converterId() {
        return converterId;
    }

    public String mappingVersion() {
        return mappingVersion;
    }

    public String language() {
        return language;
    }

    public String sourceScript() {
        return "Deva";
    }

    public String outputScript() {
        return "Newa";
    }

    public int ruleCount() {
        return rules.size();
    }

    @Override
    public void close() {
        closed = true;
    }

    private static Parsed parse(JSONObject root) throws JSONException, IOException {
        requireExactFields(root, ROOT_FIELDS, "conversion map");
        if (!FORMAT.equals(requiredString(root, "format"))
                || requiredExactInt(root, "format_version") != FORMAT_VERSION
                || !NORMALIZATION.equals(requiredString(root, "normalization"))
                || !ALGORITHM.equals(requiredString(root, "algorithm"))
                || !UNMAPPED_POLICY.equals(requiredString(root, "unmapped_policy"))
                || !JOINER_POLICY.equals(requiredString(root, "joiner_policy"))
                || !"Deva".equals(requiredString(root, "source_script"))
                || !"Newa".equals(requiredString(root, "output_script"))) {
            throw new IOException("conversion map metadata is unsupported");
        }
        String converterId = requiredString(root, "converter_id");
        String mappingVersion = requiredString(root, "mapping_version");
        String language = requiredString(root, "language");
        if (!SAFE_ID.matcher(converterId).matches()
                || !SEMANTIC_VERSION.matcher(mappingVersion).matches()
                || !LANGUAGE.matcher(language).matches()) {
            throw new IOException("conversion map identity is invalid");
        }

        JSONArray rows = root.getJSONArray("rules");
        int ruleCount = requiredExactInt(root, "rule_count");
        if (rows.length() < 1 || rows.length() > MAX_RULES || ruleCount != rows.length()) {
            throw new IOException("conversion map rule count is invalid");
        }
        List<Rule> rules = new ArrayList<>(rows.length());
        Set<String> sources = new HashSet<>();
        Rule previous = null;
        for (int index = 0; index < rows.length(); index++) {
            JSONObject row = rows.getJSONObject(index);
            requireExactFields(row, RULE_FIELDS, "conversion rule");
            String source = requiredString(row, "from");
            String target = requiredString(row, "to");
            if (!isValidScriptText(source, true, MAX_SOURCE_CODE_POINTS, false)
                    || !isValidScriptText(target, false, MAX_TARGET_CODE_POINTS, false)
                    || !sources.add(source)) {
                throw new IOException("conversion rule is invalid");
            }
            Rule rule = new Rule(source, target);
            if (previous != null
                    && compareCodePoints(previous.sourceCodePoints, rule.sourceCodePoints) >= 0) {
                throw new IOException("conversion rules are not in canonical order");
            }
            rules.add(rule);
            previous = rule;
        }
        return new Parsed(converterId, mappingVersion, language, rules);
    }

    private static boolean isValidScriptText(
            String value,
            boolean devanagari,
            int maximumCodePoints,
            boolean requireCompleteJoiners
    ) {
        if (value == null
                || value.isEmpty()
                || !Normalizer.isNormalized(value, Normalizer.Form.NFC)) {
            return false;
        }
        int[] codePoints = value.codePoints().toArray();
        if (codePoints.length > maximumCodePoints) {
            return false;
        }
        boolean hasScriptCharacter = false;
        int virama = devanagari ? DEVA_VIRAMA : NEWA_VIRAMA;
        for (int index = 0; index < codePoints.length; index++) {
            int codePoint = codePoints[index];
            if (codePoint == ZWNJ || codePoint == ZWJ) {
                if (index < 1
                        || index + 1 >= codePoints.length
                        || codePoints[index - 1] != virama
                        || !isScriptLetter(codePoints[index + 1], devanagari)
                        || (requireCompleteJoiners
                        && !hasBaseBeforeVirama(codePoints, index, devanagari))) {
                    return false;
                }
                continue;
            }
            if (!isScriptCharacter(codePoint, devanagari)) {
                return false;
            }
            hasScriptCharacter = true;
        }
        return hasScriptCharacter;
    }

    private static boolean hasBaseBeforeVirama(
            int[] codePoints,
            int joinerIndex,
            boolean devanagari
    ) {
        int index = joinerIndex - 2;
        while (index >= 0
                && isInScriptRange(codePoints[index], devanagari)
                && categoryPrefix(codePoints[index]) == 'M') {
            index--;
        }
        return index >= 0 && isScriptLetter(codePoints[index], devanagari);
    }

    private static boolean isScriptCharacter(int codePoint, boolean devanagari) {
        if (!isInScriptRange(codePoint, devanagari)
                || Character.getType(codePoint) == Character.UNASSIGNED) {
            return false;
        }
        char prefix = categoryPrefix(codePoint);
        return prefix == 'L' || prefix == 'M' || prefix == 'N' || prefix == 'P';
    }

    private static boolean isScriptLetter(int codePoint, boolean devanagari) {
        return isInScriptRange(codePoint, devanagari) && categoryPrefix(codePoint) == 'L';
    }

    private static boolean isInScriptRange(int codePoint, boolean devanagari) {
        if (!devanagari) {
            return codePoint >= 0x11400 && codePoint <= 0x1147F;
        }
        return (codePoint >= 0x0900 && codePoint <= 0x097F)
                || (codePoint >= 0xA8E0 && codePoint <= 0xA8FF)
                || (codePoint >= 0x11B00 && codePoint <= 0x11B5F);
    }

    private static char categoryPrefix(int codePoint) {
        switch (Character.getType(codePoint)) {
            case Character.UPPERCASE_LETTER:
            case Character.LOWERCASE_LETTER:
            case Character.TITLECASE_LETTER:
            case Character.MODIFIER_LETTER:
            case Character.OTHER_LETTER:
                return 'L';
            case Character.NON_SPACING_MARK:
            case Character.COMBINING_SPACING_MARK:
            case Character.ENCLOSING_MARK:
                return 'M';
            case Character.DECIMAL_DIGIT_NUMBER:
            case Character.LETTER_NUMBER:
            case Character.OTHER_NUMBER:
                return 'N';
            case Character.CONNECTOR_PUNCTUATION:
            case Character.DASH_PUNCTUATION:
            case Character.START_PUNCTUATION:
            case Character.END_PUNCTUATION:
            case Character.INITIAL_QUOTE_PUNCTUATION:
            case Character.FINAL_QUOTE_PUNCTUATION:
            case Character.OTHER_PUNCTUATION:
                return 'P';
            default:
                return '?';
        }
    }

    private static boolean matches(int[] input, int offset, int[] candidate) {
        if (offset + candidate.length > input.length) {
            return false;
        }
        for (int index = 0; index < candidate.length; index++) {
            if (input[offset + index] != candidate[index]) {
                return false;
            }
        }
        return true;
    }

    private static int compareCodePoints(int[] first, int[] second) {
        int limit = Math.min(first.length, second.length);
        for (int index = 0; index < limit; index++) {
            int compared = Integer.compare(first[index], second[index]);
            if (compared != 0) {
                return compared;
            }
        }
        return Integer.compare(first.length, second.length);
    }

    private static void requireExactFields(
            JSONObject value,
            Set<String> fields,
            String label
    ) throws IOException {
        Set<String> actual = new HashSet<>();
        java.util.Iterator<String> keys = value.keys();
        while (keys.hasNext()) {
            actual.add(keys.next());
        }
        if (!actual.equals(fields)) {
            throw new IOException(label + " has unexpected fields");
        }
    }

    private static String requiredString(JSONObject value, String field) throws JSONException {
        Object item = value.get(field);
        if (!(item instanceof String) || ((String) item).isEmpty()) {
            throw new JSONException(field + " must be a non-empty string");
        }
        return (String) item;
    }

    private static int requiredExactInt(JSONObject value, String field) throws JSONException {
        Object item = value.get(field);
        if (item instanceof Integer) {
            return (Integer) item;
        }
        if (item instanceof Long
                && (Long) item >= Integer.MIN_VALUE
                && (Long) item <= Integer.MAX_VALUE) {
            return ((Long) item).intValue();
        }
        throw new JSONException(field + " must be an exact integer");
    }

    private static byte[] canonicalBytes(Parsed parsed) {
        StringBuilder output = new StringBuilder();
        output.append('{');
        field(output, "algorithm", ALGORITHM).append(',');
        field(output, "converter_id", parsed.converterId).append(',');
        field(output, "format", FORMAT).append(',');
        output.append("\"format_version\":").append(FORMAT_VERSION).append(',');
        field(output, "joiner_policy", JOINER_POLICY).append(',');
        field(output, "language", parsed.language).append(',');
        field(output, "mapping_version", parsed.mappingVersion).append(',');
        field(output, "normalization", NORMALIZATION).append(',');
        field(output, "output_script", "Newa").append(',');
        output.append("\"rule_count\":").append(parsed.rules.size()).append(',');
        output.append("\"rules\":[");
        for (int index = 0; index < parsed.rules.size(); index++) {
            if (index > 0) {
                output.append(',');
            }
            Rule rule = parsed.rules.get(index);
            output.append('{');
            field(output, "from", rule.source).append(',');
            field(output, "to", rule.target);
            output.append('}');
        }
        output.append("],");
        field(output, "source_script", "Deva").append(',');
        field(output, "unmapped_policy", UNMAPPED_POLICY);
        output.append("}\n");
        return output.toString().getBytes(StandardCharsets.UTF_8);
    }

    private static StringBuilder field(StringBuilder output, String name, String value) {
        return quoted(output, name).append(':').append(quoted(new StringBuilder(), value));
    }

    private static StringBuilder quoted(StringBuilder output, String value) {
        output.append('"');
        for (int offset = 0; offset < value.length(); ) {
            int codePoint = value.codePointAt(offset);
            switch (codePoint) {
                case '"':
                    output.append("\\\"");
                    break;
                case '\\':
                    output.append("\\\\");
                    break;
                case '\b':
                    output.append("\\b");
                    break;
                case '\t':
                    output.append("\\t");
                    break;
                case '\n':
                    output.append("\\n");
                    break;
                case '\f':
                    output.append("\\f");
                    break;
                case '\r':
                    output.append("\\r");
                    break;
                default:
                    if (codePoint < 0x20) {
                        output.append(String.format(Locale.ROOT, "\\u%04x", codePoint));
                    } else {
                        output.appendCodePoint(codePoint);
                    }
                    break;
            }
            offset += Character.charCount(codePoint);
        }
        return output.append('"');
    }

    private static byte[] readBounded(File file) throws IOException {
        try (InputStream input = new FileInputStream(file);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8 * 1024];
            int total = 0;
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > MAX_ARTIFACT_BYTES) {
                    throw new IOException("conversion map exceeds the v1 size bound");
                }
                output.write(buffer, 0, read);
            }
            return output.toByteArray();
        }
    }

    private static String decodeStrictUtf8(byte[] encoded) throws IOException {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(encoded))
                    .toString();
        } catch (CharacterCodingException invalidUtf8) {
            throw new IOException("conversion map must be strict UTF-8", invalidUtf8);
        }
    }

    private static String sha256(byte[] value) throws IOException {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value);
            StringBuilder output = new StringBuilder(64);
            for (byte item : digest) {
                output.append(String.format(Locale.ROOT, "%02x", item & 0xff));
            }
            return output.toString();
        } catch (NoSuchAlgorithmException impossible) {
            throw new IOException("SHA-256 is unavailable", impossible);
        }
    }

    private static String requireSha256(String value) {
        if (value == null || !value.matches("[0-9a-fA-F]{64}")) {
            throw new IllegalArgumentException("expected artifact SHA-256 is required");
        }
        return value.toLowerCase(Locale.ROOT);
    }

    private static byte[] decodeSha256(String value) {
        byte[] result = new byte[32];
        for (int index = 0; index < result.length; index++) {
            result[index] = (byte) Integer.parseInt(
                    value.substring(index * 2, index * 2 + 2),
                    16
            );
        }
        return result;
    }

    private static final class Rule {
        final String source;
        final String target;
        final int[] sourceCodePoints;
        final int[] targetCodePoints;

        Rule(String source, String target) {
            this.source = source;
            this.target = target;
            this.sourceCodePoints = source.codePoints().toArray();
            this.targetCodePoints = target.codePoints().toArray();
        }
    }

    private static final class Parsed {
        final String converterId;
        final String mappingVersion;
        final String language;
        final List<Rule> rules;

        Parsed(
                String converterId,
                String mappingVersion,
                String language,
                List<Rule> rules
        ) {
            this.converterId = converterId;
            this.mappingVersion = mappingVersion;
            this.language = language;
            this.rules = rules;
        }
    }
}
