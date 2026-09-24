import groovy.json.JsonOutput
import groovy.json.JsonGenerator
import groovy.json.JsonSlurper
import java.io.File
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.text.Normalizer
import java.util.Collections
import java.util.Locale
import java.util.Properties
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ListProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.Optional
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault

plugins {
    id("com.android.application")
}

private val candidateSigningPropertiesFile = rootProject.file("keystore.properties")
private val candidateSigningProperties = Properties().apply {
    if (candidateSigningPropertiesFile.isFile) {
        FileInputStream(candidateSigningPropertiesFile).use { input -> load(input) }
    }
}

private fun candidateSigningProperty(name: String): String =
    candidateSigningProperties.getProperty(name)?.takeIf(String::isNotBlank)
        ?: throw GradleException(
            "android/keystore.properties is missing required property $name"
        )

private data class ReleasePackBinding(
    val profileId: String,
    val packId: String,
    val fileName: String,
    val artifactSha256: String,
    val language: String,
    val outputScript: String,
    val artifactLicense: String,
    val candidateCount: Int,
    val surfaceKeyCount: Int,
    val aliasKeyCount: Int,
    val lookupKind: String,
    val validationQuery: String,
    val validationExpectedSurface: String,
    val benchmarkQueries: List<String>,
    val releaseMode: String? = null,
) {
    fun encoded(): String = JsonOutput.toJson(linkedMapOf<String, Any>(
        "profile_id" to profileId,
        "pack_id" to packId,
        "file_name" to fileName,
        "artifact_sha256" to artifactSha256,
        "language" to language,
        "output_script" to outputScript,
        "artifact_license" to artifactLicense,
        "candidate_count" to candidateCount,
        "surface_key_count" to surfaceKeyCount,
        "alias_key_count" to aliasKeyCount,
        "lookup_kind" to lookupKind,
        "validation_query" to validationQuery,
        "validation_expected_surface" to validationExpectedSurface,
        "benchmark_queries" to benchmarkQueries,
    ).also { row ->
        releaseMode?.let { row["release_mode"] = it }
    })
}

private data class ConversionMapVector(
    val input: String,
    val expectedStatus: String,
    val expectedOutput: String?,
)

private data class ConversionMapBinding(
    val profileId: String,
    val converterId: String,
    val fileName: String,
    val artifactSha256: String,
    val language: String,
    val sourceScript: String,
    val outputScript: String,
    val releaseMode: String,
    val ruleCount: Int,
    val vectors: List<ConversionMapVector>,
)

@DisableCachingByDefault(because = "The generated Java source is small and deterministic")
/**
 * Emits the transliteration-profile supplement as a generated Java constant.
 *
 * The profile lock can only make a Roman profile selectable when it has a
 * dictionary pack. Languages with no dictionary -- which is why they have no
 * keyboard -- can still be typed deterministically from a reviewed map. This
 * task carries that separate, hash-pinned claim into the runtime without
 * editing the lock or its generator.
 */
abstract class GenerateTransliterationProfiles : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val catalogFile: RegularFileProperty

    @get:Input
    abstract val expectedCatalogSha256: Property<String>

    @get:Input
    abstract val expectedProfileLockSha256: Property<String>

    /**
     * Whether this variant may use the supplement. The reviewed catalog carries
     * internal authority, so release and debug generate an empty constant rather
     * than silently inheriting an internal-only decision.
     */
    @get:Input
    abstract val includeProfiles: Property<Boolean>

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val file = catalogFile.get().asFile
        val bytes = file.readBytes()
        val actual = MessageDigest.getInstance("SHA-256")
            .digest(bytes)
            .joinToString("") { byte -> "%02x".format(byte) }
        if (actual != expectedCatalogSha256.get()) {
            throw GradleException(
                "transliteration-profile catalog SHA-256 is $actual, " +
                    "expected ${expectedCatalogSha256.get()}"
            )
        }
        val root = groovy.json.JsonSlurper().parseText(
            String(bytes, StandardCharsets.UTF_8)
        ) as Map<*, *>
        val lockSha = root["profile_lock_sha256"] as? String
            ?: throw GradleException("transliteration-profile catalog has no profile_lock_sha256")
        if (lockSha != expectedProfileLockSha256.get()) {
            throw GradleException(
                "transliteration-profile catalog was compiled against lock $lockSha, " +
                    "expected ${expectedProfileLockSha256.get()}"
            )
        }
        @Suppress("UNCHECKED_CAST")
        val profiles = root["profiles"] as? List<Map<*, *>>
            ?: throw GradleException("transliteration-profile catalog has no profiles")
        if (profiles.isEmpty()) {
            throw GradleException("transliteration-profile catalog is empty")
        }
        val included = if (includeProfiles.get()) profiles else emptyList()
        val rows = included.joinToString(",\n") { row ->
            val id = row["profile_id"] as String
            val asset = row["map_asset"] as String
            "            \"$id\", \"$asset\""
        }
        val generated = """
            |package com.ampixa.nepakeyboard.ime;
            |
            |/** Generated from catalog/transliteration-profiles-v0.json. Do not edit. */
            |final class GeneratedTransliterationProfiles {
            |    static final String CATALOG_SHA256 = "$actual";
            |    static final int PROFILE_COUNT = ${included.size};
            |
            |    /** Flattened profile id / map asset pairs. */
            |    static final String[] PROFILE_MAP_PAIRS = {
            |$rows
            |    };
            |
            |    private GeneratedTransliterationProfiles() {}
            |}
            |
        """.trimMargin()
        val packageDirectory = File(outputDirectory.get().asFile, "com/ampixa/nepakeyboard/ime")
        if (packageDirectory.exists() && !packageDirectory.deleteRecursively()) {
            throw GradleException("Could not clear generated transliteration-profile source")
        }
        if (!packageDirectory.mkdirs() && !packageDirectory.isDirectory) {
            throw GradleException("Could not create generated transliteration-profile directory")
        }
        File(packageDirectory, "GeneratedTransliterationProfiles.java").writeText(
            generated,
            StandardCharsets.UTF_8,
        )
    }
}

abstract class GenerateShippingProfileCatalog : DefaultTask() {
    companion object {
        private val FOUNDATION_PROFILES = setOf("eng-Latn-US", "npi-Deva-NP")
        private val COUNT_FIELDS = setOf("targets", "profiles", "scripts", "selectable")
    }

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val lockFile: RegularFileProperty

    @get:Input
    abstract val expectedLockSha256: Property<String>

    @get:Input
    abstract val expectedAuthority: Property<String>

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val compilerFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val catalogSchemaFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val reviewSchemaFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val lockSchemaFile: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @get:OutputDirectory
    abstract val resourceOutputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val source = lockFile.get().asFile
        if (Files.isSymbolicLink(source.toPath())) {
            throw GradleException("Shipping-profile lock must not be a symbolic link")
        }
        val actualLockSha256 = sha256(source)
        val reviewedLockSha256 = expectedLockSha256.get()
        if (actualLockSha256 != reviewedLockSha256) {
            throw GradleException(
                "Shipping-profile lock is not the pinned variant lock: " +
                    "expected $reviewedLockSha256, got $actualLockSha256"
            )
        }
        val parsed = try {
            JsonSlurper().parseText(source.readText(StandardCharsets.UTF_8))
        } catch (failure: RuntimeException) {
            throw GradleException("Shipping-profile lock is invalid JSON", failure)
        }
        val lock = parsed as? Map<*, *>
            ?: throw GradleException("Shipping-profile lock must be an object")
        val lockVersion = requiredExactInt(lock["lock_version"], "lock_version")
        val generatorVersion = requiredExactInt(
            lock["generator_version"],
            "generator_version",
        )
        if (lockVersion !in 1..2 || generatorVersion != lockVersion) {
            throw GradleException("Unsupported shipping-profile lock version")
        }
        if (lock["generator"] != "build_shipping_profile_catalog"
        ) {
            throw GradleException("Shipping-profile lock generator is invalid")
        }
        if (lockVersion == 1) {
            verifyHistoricalPinnedReference(
                lock["compiler"],
                "tools/build_shipping_profile_catalog.py",
                "shipping-profile compiler",
            )
        } else {
            verifyPinnedFile(
                lock["compiler"],
                "tools/build_shipping_profile_catalog.py",
                compilerFile.get().asFile,
                "shipping-profile compiler",
            )
        }
        val schemas = lock["schemas"] as? Map<*, *>
            ?: throw GradleException("Shipping-profile lock schemas must be an object")
        if (schemas.keys.map { it as? String }.toSet() != setOf("catalog", "review", "lock")) {
            throw GradleException("Shipping-profile lock schema references are invalid")
        }
        val schemaInputs = listOf(
            Triple(
                "catalog",
                "schemas/resource-catalog.schema.json",
                catalogSchemaFile.get().asFile,
            ),
            Triple(
                "review",
                "schemas/shipping-profile-review.schema.json",
                reviewSchemaFile.get().asFile,
            ),
            Triple(
                "lock",
                "schemas/shipping-profile-lock.schema.json",
                lockSchemaFile.get().asFile,
            ),
        )
        for ((name, path, file) in schemaInputs) {
            if (lockVersion == 1) {
                verifyHistoricalPinnedReference(
                    schemas[name],
                    path,
                    "shipping-profile $name schema",
                )
            } else {
                verifyPinnedFile(
                    schemas[name],
                    path,
                    file,
                    "shipping-profile $name schema",
                )
            }
        }
        val counts = lock["counts"] as? Map<*, *>
            ?: throw GradleException("Shipping-profile lock has no counts")
        if (counts.keys.map { it as? String }.toSet() != COUNT_FIELDS) {
            throw GradleException("Shipping-profile lock count fields are invalid")
        }
        val reviewedCounts = COUNT_FIELDS.associateWith { name ->
            requiredExactInt(counts[name], "counts.$name").also { value ->
                val minimum = if (name == "selectable") 2 else 1
                if (value < minimum) {
                    throw GradleException("Shipping-profile lock count is invalid: $name")
                }
            }
        }
        val scripts = (lock["scripts"] as? List<*>)?.mapIndexed { index, value ->
            val script = value as? String
                ?: throw GradleException("Shipping-profile lock script $index must be a string")
            if (!script.matches(Regex("[A-Z][a-z]{3}"))) {
                throw GradleException("Shipping-profile script code is invalid")
            }
            script
        } ?: throw GradleException("Shipping-profile lock scripts must be an array")
        if (scripts.size != reviewedCounts.getValue("scripts")
            || scripts.toSet().size != scripts.size
            || scripts != scripts.sorted()
        ) {
            throw GradleException("Shipping-profile script set mismatch")
        }
        val targets = lock["targets"] as? List<*>
            ?: throw GradleException("Shipping-profile targets must be an array")
        val profiles = lock["profiles"] as? List<*>
            ?: throw GradleException("Shipping-profile profiles must be an array")
        if (targets.size != reviewedCounts.getValue("targets")
            || profiles.size != reviewedCounts.getValue("profiles")
        ) {
            throw GradleException("Shipping-profile arrays do not match reviewed counts")
        }
        val targetIds = targets.map { target ->
            val row = target as? Map<*, *>
                ?: throw GradleException("Shipping-profile target must be an object")
            requiredString(row, "target_id")
        }
        if (targetIds.toSet().size != targetIds.size) {
            throw GradleException("Shipping-profile targets are not unique")
        }

        val rows = profiles.map { profile ->
            profile as? Map<*, *>
                ?: throw GradleException("Shipping profile must be an object")
        }
        val profileIds = rows.map { requiredString(it, "profile_id") }
        val methodIds = rows.map { requiredString(it, "input_method_id") }
        if (profileIds.toSet().size != profileIds.size
            || methodIds.toSet().size != methodIds.size
            || rows.any { requiredString(it, "target_id") !in targetIds }
        ) {
            throw GradleException("Shipping profiles have duplicate or unknown identities")
        }
        val selectable = rows.filter { it["selectable"] == true }
            .map { requiredString(it, "profile_id") }
            .toSet()
        if (selectable.size != reviewedCounts.getValue("selectable")
            || !selectable.containsAll(FOUNDATION_PROFILES)
        ) {
            throw GradleException("Shipping-profile selectable set is invalid: $selectable")
        }
        val review = lock["review"] as? Map<*, *>
            ?: throw GradleException("Shipping-profile lock has no review reference")
        if (review["authority"] != expectedAuthority.get()) {
            throw GradleException("Shipping-profile lock authority does not match the variant")
        }
        val catalogId = requiredString(review, "id")

        val generatedRows = rows.joinToString(",\n") { row -> javaProfile(row) }
        val generated = """
            |package com.ampixa.nepakeyboard.ime;
            |
            |import java.util.Arrays;
            |import java.util.Collections;
            |import java.util.List;
            |
            |/** Generated from the reviewed shipping-profile lock. Do not edit. */
            |final class GeneratedProfileCatalog {
            |    static final String CATALOG_ID = ${javaString(catalogId)};
            |    static final String LOCK_SHA256 = ${javaString(actualLockSha256)};
            |    static final int TARGET_COUNT = ${reviewedCounts.getValue("targets")};
            |    static final int PROFILE_COUNT = ${reviewedCounts.getValue("profiles")};
            |    static final int SCRIPT_COUNT = ${reviewedCounts.getValue("scripts")};
            |    static final int SELECTABLE_COUNT = ${reviewedCounts.getValue("selectable")};
            |
            |    private GeneratedProfileCatalog() {}
            |
            |    static List<KeyboardProfile> createProfiles() {
            |        return Collections.unmodifiableList(Arrays.asList(
            |$generatedRows
            |        ));
            |    }
            |}
            |
        """.trimMargin()

        val packageDirectory = File(
            outputDirectory.get().asFile,
            "com/ampixa/nepakeyboard/ime",
        )
        if (packageDirectory.exists() && !packageDirectory.deleteRecursively()) {
            throw GradleException("Could not clear generated shipping-profile source")
        }
        if (!packageDirectory.mkdirs() && !packageDirectory.isDirectory) {
            throw GradleException("Could not create generated shipping-profile source directory")
        }
        File(packageDirectory, "GeneratedProfileCatalog.java").writeText(
            generated,
            StandardCharsets.UTF_8,
        )

        val selectableRows = rows.filter { it["selectable"] == true }
        val selectableTargetCounts = selectableRows
            .groupingBy { requiredString(it, "target_id") }
            .eachCount()
        val subtypeIds = selectableRows.associate { row ->
            val profileId = requiredString(row, "profile_id")
            profileId to stableSubtypeId(profileId)
        }
        if (subtypeIds.values.toSet().size != subtypeIds.size) {
            throw GradleException("Generated Android subtype IDs collide")
        }
        val resourceRoot = resourceOutputDirectory.get().asFile
        if (resourceRoot.exists() && !resourceRoot.deleteRecursively()) {
            throw GradleException("Could not clear generated shipping-profile resources")
        }
        val xmlDirectory = File(resourceRoot, "xml")
        val valuesDirectory = File(resourceRoot, "values")
        if ((!xmlDirectory.mkdirs() && !xmlDirectory.isDirectory)
            || (!valuesDirectory.mkdirs() && !valuesDirectory.isDirectory)
        ) {
            throw GradleException("Could not create generated shipping-profile resources")
        }
        val subtypeRows = selectableRows.joinToString("\n\n") { row ->
            val profileId = requiredString(row, "profile_id")
            val languageTag = requiredString(row, "language_tag")
            val labelName = subtypeLabelName(profileId)
            val asciiCapable = requiredString(row, "source_script") == "Latn"
            """
                |    <subtype
                |        android:icon="@null"
                |        android:imeSubtypeExtraValue="profile=${xmlEscape(profileId)}"
                |        android:imeSubtypeLocale="${xmlEscape(languageTag.replace('-', '_'))}"
                |        android:imeSubtypeMode="keyboard"
                |        android:isAsciiCapable="$asciiCapable"
                |        android:label="@string/$labelName"
                |        android:languageTag="${xmlEscape(languageTag)}"
                |        android:subtypeId="${subtypeIds.getValue(profileId)}" />
            """.trimMargin()
        }
        File(xmlDirectory, "input_method.xml").writeText(
            """
                |<?xml version="1.0" encoding="utf-8"?>
                |<input-method xmlns:android="http://schemas.android.com/apk/res/android"
                |    android:settingsActivity="com.ampixa.nepakeyboard.ime.SettingsActivity"
                |    android:supportsSwitchingToNextInputMethod="true">
                |
                |$subtypeRows
                |</input-method>
                |
            """.trimMargin(),
            StandardCharsets.UTF_8,
        )
        val labelRows = selectableRows.joinToString("\n") { row ->
            val profileId = requiredString(row, "profile_id")
            val targetId = requiredString(row, "target_id")
            val nativeLabel = requiredString(row, "native_label")
            val label = if (selectableTargetCounts.getValue(targetId) > 1) {
                "$nativeLabel · ${requiredString(row, "input_label")}"
            } else {
                nativeLabel
            }
            "    <string name=\"${subtypeLabelName(profileId)}\">${xmlEscape(label)}</string>"
        }
        File(valuesDirectory, "generated_subtypes.xml").writeText(
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" +
                "<resources>\n$labelRows\n</resources>\n",
            StandardCharsets.UTF_8,
        )
    }

    private fun subtypeLabelName(profileId: String): String =
        "subtype_" + profileId.lowercase(Locale.ROOT).replace(Regex("[^a-z0-9_]"), "_")

    private fun stableSubtypeId(profileId: String): Int {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(("nepa-android-subtype-v1\u0000" + profileId).toByteArray(StandardCharsets.UTF_8))
        val positive = ByteBuffer.wrap(digest).int and Int.MAX_VALUE
        return if (positive == 0) 1 else positive
    }

    private fun xmlEscape(value: String): String = value
        .replace("&", "&amp;")
        .replace("\"", "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")

    private fun verifyPinnedFile(
        value: Any?,
        expectedPath: String,
        file: File,
        label: String,
    ) {
        val reference = value as? Map<*, *>
            ?: throw GradleException("$label reference must be an object")
        if (reference.keys.map { it as? String }.toSet() != setOf("path", "sha256")
            || reference["path"] != expectedPath
            || Files.isSymbolicLink(file.toPath())
            || !file.isFile
            || reference["sha256"] != sha256(file)
        ) {
            throw GradleException("$label does not match its reviewed reference")
        }
    }

    /**
     * A v1 lock is still accepted only through its exact task-level SHA pin. Its
     * compiler/schema references describe the historical sources that produced
     * it, so they cannot be compared with the checked v2 compiler and schemas.
     */
    private fun verifyHistoricalPinnedReference(
        value: Any?,
        expectedPath: String,
        label: String,
    ) {
        val reference = value as? Map<*, *>
            ?: throw GradleException("$label reference must be an object")
        val sha256 = reference["sha256"] as? String
        if (reference.keys.map { it as? String }.toSet() != setOf("path", "sha256")
            || reference["path"] != expectedPath
            || sha256?.matches(Regex("^[0-9a-f]{64}$")) != true
        ) {
            throw GradleException("$label historical reference is invalid")
        }
    }

    private fun javaProfile(row: Map<*, *>): String {
        val profileId = requiredString(row, "profile_id")
        val selectable = row["selectable"] as? Boolean
            ?: throw GradleException("Profile $profileId selectable must be boolean")
        val defaultEnabled = row["default_enabled"] as? Boolean
            ?: throw GradleException("Profile $profileId default_enabled must be boolean")
        val packBinding = optionalString(row, "pack_binding")
        val packArtifactValue = row["pack_artifact"]
        val packArtifact = packArtifactValue as? Map<*, *>
        val conversionBinding = optionalString(row, "conversion_binding")
        val conversionArtifactValue = row["conversion_artifact"]
        val conversionArtifact = conversionArtifactValue as? Map<*, *>
        val blockedReason = optionalString(row, "blocked_reason")
        val blockedDetail = optionalString(row, "blocked_detail")
        val evidenceIds = stringList(row, "evidence_ids")
        val evidenceArtifacts = row["evidence_artifacts"] as? List<*>
            ?: throw GradleException("Profile $profileId evidence_artifacts must be an array")
        val layoutRevision = row["layout_revision"]
        val layoutSourceSha256 = row["layout_source_sha256"]
        val checkedLayoutRevision = layoutRevision?.let {
            requiredExactInt(it, "profile $profileId layout_revision").takeIf { value -> value > 0 }
        }
        val lookupKind = when (requiredString(row, "lookup_kind")) {
            "surface_prefix" -> "SURFACE_PREFIX"
            "alias_prefix" -> "ALIAS_PREFIX"
            "conversion" -> "CONVERSION"
            else -> throw GradleException("Profile $profileId has unsupported lookup kind")
        }
        val runtimeBinding = when (lookupKind) {
            "CONVERSION" -> conversionBinding
            else -> packBinding
        }
        if (selectable) {
            val artifactBindingIsValid = if (lookupKind == "CONVERSION") {
                conversionBinding != null
                        && conversionArtifact != null
                        && optionalString(conversionArtifact, "converter_id") == conversionBinding
                        && packBinding == null
                        && packArtifact == null
            } else {
                packBinding != null
                        && packArtifact != null
                        && optionalString(packArtifact, "pack_id") == packBinding
                        && conversionBinding == null
                        && conversionArtifact == null
            }
            if (!artifactBindingIsValid
                || blockedReason != null || blockedDetail != null || evidenceIds.isEmpty()
                || evidenceArtifacts.isEmpty()
                || checkedLayoutRevision == null
                || (layoutSourceSha256 as? String)?.matches(Regex("^[0-9a-f]{64}$")) != true
            ) {
                throw GradleException("Selectable profile $profileId has incomplete evidence")
            }
        } else if (defaultEnabled || packBinding != null || conversionBinding != null
            || blockedReason == null
            || blockedDetail == null || evidenceIds.isNotEmpty()
            || packArtifactValue != null || conversionArtifactValue != null
            || evidenceArtifacts.isNotEmpty()
            || layoutRevision != null || layoutSourceSha256 != null
        ) {
            throw GradleException("Blocked profile $profileId has shipping authority")
        }

        val layoutId = requiredString(row, "layout_id")
        val availability = if (selectable) "AVAILABLE" else "BLOCKED"
        return """
            |            new KeyboardProfile(
            |                    ${javaString(profileId)},
            |                    ${javaString(requiredString(row, "target_id"))},
            |                    ${javaString(requiredString(row, "input_method_id"))},
            |                    ${javaString(requiredString(row, "language_tag"))},
            |                    ${javaString(requiredString(row, "display_label"))},
            |                    ${javaString(requiredString(row, "native_label"))},
            |                    ${javaString(requiredString(row, "source_script"))},
            |                    ${javaString(requiredString(row, "output_script"))},
            |                    ${javaString(requiredString(row, "input_label"))},
            |                    ${javaString(requiredString(row, "method_type"))},
            |                    ${javaString(requiredString(row, "engine_kind"))},
            |                    ${javaString(layoutId)},
            |                    ${checkedLayoutRevision?.toString() ?: "null"},
            |                    ${nullableJavaString(layoutSourceSha256 as? String)},
            |                    KeyboardProfile.LookupKind.$lookupKind,
            |                    ${nullableJavaString(runtimeBinding)},
            |                    ${javaString(requiredString(row, "catalog_readiness"))},
            |                    KeyboardProfile.Availability.$availability,
            |                    ${nullableJavaString(blockedReason)},
            |                    ${nullableJavaString(blockedDetail)},
            |                    $defaultEnabled,
            |                    ${javaString(requiredString(row, "scope"))},
            |                    ${nullableJavaString(optionalString(row, "group"))},
            |                    ${nullableJavaString(optionalString(row, "variety"))},
            |                    ${javaString(requiredString(row, "sort_key"))},
            |                    ${javaStringList(stringList(row, "search_aliases"))},
            |                    ${javaStringList(evidenceIds)}
            |            )
        """.trimMargin()
    }

    private fun requiredString(row: Map<*, *>, field: String): String =
        (row[field] as? String)?.takeIf(String::isNotBlank)
            ?: throw GradleException("Shipping-profile field is missing: $field")

    private fun requiredExactInt(value: Any?, field: String): Int {
        val encoded = (value as? Number)?.toString()
            ?: throw GradleException("Shipping-profile $field must be an integer")
        if (!Regex("^-?(0|[1-9][0-9]*)$").matches(encoded)) {
            throw GradleException("Shipping-profile $field must be an integer")
        }
        return encoded.toIntOrNull()
            ?: throw GradleException("Shipping-profile $field is outside the integer range")
    }

    private fun optionalString(row: Map<*, *>, field: String): String? {
        val value = row[field] ?: return null
        return (value as? String)?.takeIf(String::isNotBlank)
            ?: throw GradleException("Shipping-profile field is invalid: $field")
    }

    private fun stringList(row: Map<*, *>, field: String): List<String> {
        val values = row[field] as? List<*>
            ?: throw GradleException("Shipping-profile field must be an array: $field")
        return values.map { value ->
            (value as? String)?.takeIf(String::isNotBlank)
                ?: throw GradleException("Shipping-profile $field must contain strings")
        }
    }

    private fun javaString(value: String): String = JsonOutput.toJson(value)

    private fun nullableJavaString(value: String?): String =
        value?.let(::javaString) ?: "null"

    private fun javaStringList(values: List<String>): String = when {
        values.isEmpty() -> "Collections.emptyList()"
        else -> values.joinToString(", ", "Arrays.asList(", ")", transform = ::javaString)
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        FileInputStream(file).use { stream ->
            val buffer = ByteArray(8192)
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) {
                    break
                }
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { byte -> "%02x".format(byte) }
    }
}

@DisableCachingByDefault(because = "The generated Java source is small and deterministic")
abstract class GenerateLayoutRegistry : DefaultTask() {
    companion object {
        private val ROOT_KEYS = setOf(
            "layout_lock_version", "generator", "generator_version",
            "unicode_data_version", "transform_semantics", "compiler", "schemas",
            "source_directory", "profile_lock", "profile_bindings", "layout_count", "layouts",
        )
        private val LAYOUT_KEYS = setOf(
            "layout_id", "revision", "display_name", "input_script", "direction",
            "normalization", "unicode_data_version", "device_forms", "authors", "license",
            "provenance", "field_layer_map", "source", "layers", "transforms",
        )
        private val LAYER_IDS = listOf("base", "shift", "symbols", "numeric")
        private val ACTIONS = setOf(
            "shift", "delete", "enter", "space", "language", "symbols", "letters",
        )
        private val TEXT_KEY_KINDS = setOf(
            "text", "orthographic_word", "intra_word_punctuation",
            "deva_conjunct_joiner", "deva_terminal_zwnj", "newa_conjunct_joiner",
        )
        private val EXPECTED_LAYER_ACTIONS = mapOf(
            "base" to listOf("shift", "symbols", "language", "space", "delete", "enter"),
            "shift" to listOf("shift", "symbols", "language", "space", "delete", "enter"),
            "symbols" to listOf("letters", "symbols", "language", "space", "delete", "enter"),
            "numeric" to listOf("space", "delete", "enter"),
        )
        private val KEY_KEYS = setOf(
            "key_id", "kind", "label", "text", "content_description", "action",
            "width_units", "hold_action",
        )
        private val PROFILE_PLACEHOLDERS = listOf(
            "\${profile.native_name}",
            "\${profile.display_name}",
        )
        private val SHA256 = Regex("^[0-9a-f]{64}$")
        private val INTEGER = Regex("^-?[0-9]+$")
        private val ID = Regex("^[a-z0-9][a-z0-9._-]*$")
        private val NOTICE_NAME = Regex("^[A-Za-z0-9._-]+$")
        private val PROFILE_ID = Regex("^[A-Za-z0-9][A-Za-z0-9._-]*$")
        private val SCRIPT = Regex("^[A-Z][a-z]{3}$")
        private const val MAX_LAYOUTS = 128
        private const val MAX_NOTICE_BYTES = 64 * 1024
        private const val MAX_NOTICE_MANIFEST_BYTES = 64 * 1024
        private const val MAX_RUNTIME_CONFORMANCE_BYTES = 256 * 1024
        private const val MAX_RUNTIME_CONFORMANCE_PROFILES = 128
        private const val MAX_TEXT_SCALARS = 16
    }

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val layoutLockFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val profileLockFile: RegularFileProperty

    @get:Input
    abstract val expectedLayoutLockSha256: Property<String>

    @get:Input
    abstract val expectedProfileLockSha256: Property<String>

    @get:Input
    abstract val expectedAuthority: Property<String>

    @get:Input
    abstract val expectedSourceDirectoryPath: Property<String>

    @get:Input
    abstract val expectedNoticeDirectoryPath: Property<String>

    @get:Input
    abstract val expectedProfileLockPath: Property<String>

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceDirectory: DirectoryProperty

    @get:InputDirectory
    @get:Optional
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val noticeDirectory: DirectoryProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val compilerFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceSchemaFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val lockSchemaFile: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @get:OutputDirectory
    abstract val assetOutputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val lockFile = layoutLockFile.get().asFile
        val profileFile = profileLockFile.get().asFile
        val sourceDir = sourceDirectory.get().asFile
        val noticeDir = noticeDirectory.get().asFile
        val compiler = compilerFile.get().asFile
        val sourceSchema = sourceSchemaFile.get().asFile
        val lockSchema = lockSchemaFile.get().asFile
        rejectSymlink(lockFile, "layout lock")
        rejectSymlink(profileFile, "profile lock")
        rejectSymlink(sourceDir, "layout source directory")
        rejectSymlink(noticeDir, "layout notice directory")
        rejectSymlink(compiler, "layout compiler")
        rejectSymlink(sourceSchema, "layout source schema")
        rejectSymlink(lockSchema, "layout lock schema")

        val actualLockSha = sha256(lockFile)
        val pinnedLayoutSha = expectedLayoutLockSha256.get()
        if (actualLockSha != pinnedLayoutSha) {
            throw GradleException(
                "Layout lock is not the pinned variant lock: " +
                    "expected $pinnedLayoutSha, got $actualLockSha"
            )
        }
        val actualProfileSha = sha256(profileFile)
        val pinnedProfileSha = expectedProfileLockSha256.get()
        if (actualProfileSha != pinnedProfileSha) {
            throw GradleException(
                "Profile lock is not the pinned variant lock: " +
                    "expected $pinnedProfileSha, got $actualProfileSha"
            )
        }

        val lock = parseObject(lockFile, "Layout lock")
        val profileLock = parseObject(profileFile, "Shipping-profile lock")
        val profileReview = requireObject(profileLock, "review", "shipping-profile lock")
        requireString(
            profileReview,
            "authority",
            "shipping-profile lock.review",
            expectedAuthority.get(),
        )
        requireExactKeys(lock, ROOT_KEYS, "layout lock")
        requireInt(lock, "layout_lock_version", "layout lock", 1)
        requireString(lock, "generator", "layout lock", "build_keyboard_layouts")
        requireInt(lock, "generator_version", "layout lock", 1)
        requireString(lock, "unicode_data_version", "layout lock", "16.0.0")
        requireString(
            lock,
            "transform_semantics",
            "layout lock",
            "append_then_longest_suffix_once",
        )
        val sourceDirectoryPath = expectedSourceDirectoryPath.get()
        val noticeDirectoryPath = expectedNoticeDirectoryPath.get()
        val noticePathPrefix = "$noticeDirectoryPath/"
        requireString(lock, "source_directory", "layout lock", sourceDirectoryPath)

        validateInputReference(
            requireObject(lock, "compiler", "layout lock"),
            "layout lock.compiler",
            "tools/build_keyboard_layouts.py",
            compiler,
        )
        val schemas = requireObject(lock, "schemas", "layout lock")
        requireExactKeys(schemas, setOf("source", "lock"), "layout lock.schemas")
        validateInputReference(
            requireObject(schemas, "source", "layout lock.schemas"),
            "layout lock.schemas.source",
            "schemas/layout-v1.schema.json",
            sourceSchema,
        )
        validateInputReference(
            requireObject(schemas, "lock", "layout lock.schemas"),
            "layout lock.schemas.lock",
            "schemas/layout-lock-v1.schema.json",
            lockSchema,
        )

        val profileReference = requireObject(lock, "profile_lock", "layout lock")
        requireExactKeys(profileReference, setOf("path", "sha256"), "layout lock.profile_lock")
        requireString(
            profileReference,
            "path",
            "layout lock.profile_lock",
            expectedProfileLockPath.get(),
        )
        val expectedProfileSha = requireSha256(
            profileReference,
            "sha256",
            "layout lock.profile_lock",
        )
        if (actualProfileSha != expectedProfileSha) {
            throw GradleException(
                "Shipping-profile lock hash mismatch: expected $expectedProfileSha, got $actualProfileSha"
            )
        }

        val rawLayouts = requireList(lock, "layouts", "layout lock")
        val layoutCount = requirePositiveInt(lock, "layout_count", "layout lock")
        if (layoutCount > MAX_LAYOUTS || rawLayouts.size != layoutCount) {
            throw GradleException("Layout lock count does not match its layouts array")
        }
        val layouts = rawLayouts.mapIndexed { index, value ->
            validateLayout(
                value as? Map<*, *>
                    ?: throw GradleException("layout lock.layouts[$index] must be an object"),
                index,
                sourceDir,
                noticeDir,
                expectedAuthority.get(),
            )
        }
        val layoutIds = layouts.map { requireString(it, "layout_id", "compiled layout") }
        if (layoutIds.toSet().size != layoutIds.size) {
            throw GradleException("Layout lock contains duplicate layout IDs")
        }

        val expectedSourceNames = layouts.map { layout ->
            val source = requireObject(layout, "source", "compiled layout")
            val sourcePath = requireString(source, "path", "compiled layout.source")
            val prefix = "$sourceDirectoryPath/"
            if (!sourcePath.startsWith(prefix)) {
                throw GradleException("Compiled layout source path is outside $sourceDirectoryPath")
            }
            sourcePath.removePrefix(prefix)
        }.toSet()
        val actualSources = sourceDir.listFiles()?.toList()
            ?: throw GradleException("Could not list declarative layout source directory")
        for (source in actualSources) {
            rejectSymlink(source, "layout source")
            if (!source.isFile || source.extension != "json") {
                throw GradleException("Unexpected layout source entry: ${source.name}")
            }
        }
        if (actualSources.map { source -> source.name }.toSet() != expectedSourceNames) {
            throw GradleException("Layout lock source set does not exactly match $sourceDirectoryPath")
        }
        val expectedNoticeNameRows = layouts.mapNotNull { layout ->
            layoutNoticeName(layout, noticePathPrefix)
        }
        if (expectedNoticeNameRows.toSet().size != expectedNoticeNameRows.size) {
            throw GradleException("Every compiled layout notice must have a distinct asset")
        }
        val expectedNoticeNames = expectedNoticeNameRows.toSet()
        val actualNotices = when {
            !noticeDir.exists() -> emptyList<File>()
            !noticeDir.isDirectory -> {
                throw GradleException("Declarative layout notice path is not a directory")
            }
            else -> noticeDir.listFiles()?.toList()
                ?: throw GradleException("Could not list declarative layout notice directory")
        }
        for (notice in actualNotices) {
            rejectSymlink(notice, "layout notice")
            if (!notice.isFile) {
                throw GradleException("Unexpected layout notice entry: ${notice.name}")
            }
        }
        if (actualNotices.map { it.name }.toSet() != expectedNoticeNames) {
            throw GradleException(
                "Layout lock notice set does not exactly match $noticeDirectoryPath"
            )
        }

        val profileRows = requireList(profileLock, "profiles", "shipping-profile lock")
            .mapIndexed { index, value ->
                value as? Map<*, *>
                    ?: throw GradleException("shipping-profile lock.profiles[$index] must be an object")
            }
        val selectableProfiles = profileRows.filter { it["selectable"] == true }
        val selectableById = selectableProfiles.associateBy {
            requireString(it, "profile_id", "selectable shipping profile")
        }
        if (selectableById.size != selectableProfiles.size) {
            throw GradleException("Shipping-profile lock has duplicate selectable profile IDs")
        }

        val bindingRows = requireList(lock, "profile_bindings", "layout lock")
            .mapIndexed { index, value ->
                val row = value as? Map<*, *>
                    ?: throw GradleException("layout lock.profile_bindings[$index] must be an object")
                requireExactKeys(
                    row,
                    setOf(
                        "profile_id", "layout_id", "source_script", "revision", "source_sha256"
                    ),
                    "layout lock.profile_bindings[$index]",
                )
                row
            }
        val bindingIds = bindingRows.map {
            requirePattern(it, "profile_id", "layout profile binding", PROFILE_ID)
        }
        if (bindingIds.toSet().size != bindingIds.size
            || bindingIds.toSet() != selectableById.keys
        ) {
            throw GradleException(
                "Layout profile bindings must exactly match selectable shipping profiles"
            )
        }
        val layoutsById = layouts.associateBy {
            requireString(it, "layout_id", "compiled layout")
        }
        for (binding in bindingRows) {
            val profileId = requireString(binding, "profile_id", "layout profile binding")
            val layoutId = requirePattern(
                binding,
                "layout_id",
                "layout profile binding $profileId",
                ID,
            )
            val sourceScript = requirePattern(
                binding,
                "source_script",
                "layout profile binding $profileId",
                SCRIPT,
            )
            val revision = requirePositiveInt(binding, "revision", "layout profile binding $profileId")
            val sourceSha256 = requireSha256(
                binding,
                "source_sha256",
                "layout profile binding $profileId",
            )
            val profile = selectableById.getValue(profileId)
            if (requireString(profile, "layout_id", "shipping profile $profileId") != layoutId
                || requireString(profile, "source_script", "shipping profile $profileId") != sourceScript
                || requirePositiveInt(
                    profile,
                    "layout_revision",
                    "shipping profile $profileId",
                ) != revision
                || requireSha256(
                    profile,
                    "layout_source_sha256",
                    "shipping profile $profileId",
                ) != sourceSha256
            ) {
                throw GradleException("Layout binding disagrees with shipping profile $profileId")
            }
            val layout = layoutsById[layoutId]
                ?: throw GradleException("Layout binding references missing layout $layoutId")
            if (requireString(layout, "input_script", "compiled layout $layoutId") != sourceScript) {
                throw GradleException("Layout binding script mismatch for $profileId")
            }
            val layoutSource = requireObject(layout, "source", "compiled layout $layoutId")
            if (requirePositiveInt(layout, "revision", "compiled layout $layoutId") != revision
                || requireSha256(layoutSource, "sha256", "compiled layout $layoutId.source") != sourceSha256
            ) {
                throw GradleException("Layout binding revision/hash mismatch for $profileId")
            }
        }
        if (bindingRows.map { requireString(it, "layout_id", "layout binding") }.toSet()
            != layoutsById.keys
        ) {
            throw GradleException("Compiled layouts must exactly match reviewed profile bindings")
        }

        val conformanceProfiles = selectableProfiles
            .sortedBy { requireString(it, "profile_id", "selectable shipping profile") }
            .map { profile ->
                val profileId = requireString(profile, "profile_id", "selectable shipping profile")
                val layoutId = requireString(profile, "layout_id", "selectable shipping profile")
                runtimeConformanceRow(
                    profile,
                    layoutsById[layoutId]
                        ?: throw GradleException("Selectable profile $profileId has no layout"),
                )
            }
        val runtimeConformance = linkedMapOf<String, Any>(
            "format_version" to 2,
            "profile_lock_sha256" to actualProfileSha,
            "layout_lock_sha256" to actualLockSha,
            "selectable_profile_count" to conformanceProfiles.size,
            "profiles" to conformanceProfiles,
        )
        if (conformanceProfiles.isEmpty()
            || conformanceProfiles.size > MAX_RUNTIME_CONFORMANCE_PROFILES
        ) {
            throw GradleException("Generated runtime conformance profile count is out of bounds")
        }
        val encodedRuntimeConformance = JsonOutput.toJson(runtimeConformance) + "\n"
        val encodedRuntimeConformanceBytes =
            encodedRuntimeConformance.toByteArray(StandardCharsets.UTF_8)
        if (encodedRuntimeConformanceBytes.size > MAX_RUNTIME_CONFORMANCE_BYTES) {
            throw GradleException("Generated runtime conformance asset exceeds its runtime bound")
        }
        val runtimeConformanceSha256 = sha256(encodedRuntimeConformanceBytes)

        val noticeRows = layouts.mapNotNull(::layoutNoticeRow)
        val noticeManifest = linkedMapOf<String, Any>(
            "format_version" to 1,
            "layout_lock_sha256" to actualLockSha,
            "layouts" to noticeRows,
        )
        val encodedNoticeManifest = JsonOutput.toJson(noticeManifest) + "\n"
        val encodedNoticeManifestBytes = encodedNoticeManifest.toByteArray(StandardCharsets.UTF_8)
        if (encodedNoticeManifestBytes.size > MAX_NOTICE_MANIFEST_BYTES) {
            throw GradleException("Generated layout-notice manifest exceeds its runtime bound")
        }
        val noticeManifestSha256 = sha256(encodedNoticeManifestBytes)

        val generatedLayouts = layouts.mapIndexed { index, layout ->
            javaLayout(index, layout)
        }.joinToString("\n\n")
        val generatedLayoutIds = layoutIds.joinToString(", ", transform = ::javaString)
        val noticeLayoutIds = noticeRows.map { row -> row.getValue("layout_id") as String }
        val generatedNoticeLayoutIds = when {
            noticeLayoutIds.isEmpty() -> "Collections.emptyList()"
            else -> noticeLayoutIds.joinToString(
                ", ",
                "Collections.unmodifiableList(Arrays.asList(",
                "))",
                transform = ::javaString,
            )
        }
        val createCalls = layouts.indices.joinToString(",\n") { index ->
            "            createLayout$index()"
        }
        val generated = """
            |package com.ampixa.nepakeyboard.ime;
            |
            |import java.util.Arrays;
            |import java.util.Collections;
            |import java.util.List;
            |
            |/** Generated from the exact-hash declarative layout lock. Do not edit. */
            |final class GeneratedLayoutRegistry {
            |    static final int LAYOUT_COUNT = $layoutCount;
            |    static final int LAYOUT_NOTICE_COUNT = ${noticeRows.size};
            |    static final String LAYOUT_LOCK_SHA256 = ${javaString(actualLockSha)};
            |    static final String PROFILE_LOCK_SHA256 = ${javaString(actualProfileSha)};
            |    static final String NOTICE_MANIFEST_SHA256 = ${javaString(noticeManifestSha256)};
            |    static final String RUNTIME_CONFORMANCE_SHA256 = ${javaString(runtimeConformanceSha256)};
            |    static final String UNICODE_DATA_VERSION = "16.0.0";
            |
            |    private GeneratedLayoutRegistry() {}
            |
            |    static List<KeyboardLayouts.LayoutSet> createLayouts() {
            |        return Collections.unmodifiableList(Arrays.asList(
            |$createCalls
            |        ));
            |    }
            |
            |    static List<String> layoutIds() {
            |        return Collections.unmodifiableList(Arrays.asList($generatedLayoutIds));
            |    }
            |
            |    static List<String> layoutNoticeIds() {
            |        return $generatedNoticeLayoutIds;
            |    }
            |
            |$generatedLayouts
            |}
            |
        """.trimMargin()

        val packageDirectory = File(
            outputDirectory.get().asFile,
            "com/ampixa/nepakeyboard/ime",
        )
        if (packageDirectory.exists() && !packageDirectory.deleteRecursively()) {
            throw GradleException("Could not clear generated layout-registry source")
        }
        if (!packageDirectory.mkdirs() && !packageDirectory.isDirectory) {
            throw GradleException("Could not create generated layout-registry source directory")
        }
        File(packageDirectory, "GeneratedLayoutRegistry.java").writeText(
            generated,
            StandardCharsets.UTF_8,
        )

        val assetRoot = assetOutputDirectory.get().asFile
        if (assetRoot.exists() && !assetRoot.deleteRecursively()) {
            throw GradleException("Could not clear generated layout-notice assets")
        }
        val noticeAssetDirectory = File(assetRoot, "nepa-layout-notices")
        if (!noticeAssetDirectory.mkdirs() && !noticeAssetDirectory.isDirectory) {
            throw GradleException("Could not create generated layout-notice asset directory")
        }
        layouts.forEach { layout ->
            val noticeName = layoutNoticeName(layout, noticePathPrefix)
                ?: return@forEach
            val noticeSource = File(noticeDir, noticeName)
            Files.copy(
                noticeSource.toPath(),
                File(noticeAssetDirectory, noticeName).toPath(),
                StandardCopyOption.REPLACE_EXISTING,
            )
        }
        File(noticeAssetDirectory, "manifest.json").writeText(
            encodedNoticeManifest,
            StandardCharsets.UTF_8,
        )
        val conformanceAssetDirectory = File(assetRoot, "nepa-conformance")
        if (!conformanceAssetDirectory.mkdirs() && !conformanceAssetDirectory.isDirectory) {
            throw GradleException("Could not create generated runtime-conformance asset directory")
        }
        File(conformanceAssetDirectory, "runtime-v2.json").writeText(
            encodedRuntimeConformance,
            StandardCharsets.UTF_8,
        )
    }

    private fun runtimeConformanceRow(
        profile: Map<*, *>,
        layout: Map<*, *>,
    ): Map<String, Any?> {
        val profileId = requireString(profile, "profile_id", "selectable shipping profile")
        val layoutId = requireString(layout, "layout_id", "compiled layout for $profileId")
        val layers = requireObject(layout, "layers", "compiled layout $layoutId")
        val fingerprints = linkedMapOf<String, String>()
        for (layerId in LAYER_IDS) {
            val layer = layers[layerId] as? Map<*, *>
                ?: throw GradleException("Compiled layout $layoutId has no $layerId layer")
            fingerprints[layerId] = renderedLayerFingerprint(profile, layerId, layer)
        }
        val base = layers["base"] as Map<*, *>
        val defaultProbe = requireList(base, "rows", "compiled layout $layoutId base layer")
            .asSequence()
            .flatMap { (it as List<*>).asSequence() }
            .map { it as Map<*, *> }
            .firstOrNull { it["kind"] == "text" }
            ?: throw GradleException("Compiled layout $layoutId has no default base text key")
        val lookupKind = when (requireString(profile, "lookup_kind", "profile $profileId")) {
            "surface_prefix" -> "SURFACE_PREFIX"
            "alias_prefix" -> "ALIAS_PREFIX"
            "conversion" -> "CONVERSION"
            else -> throw GradleException("Profile $profileId has unsupported lookup kind")
        }
        if (profile["selectable"] != true) {
            throw GradleException("Runtime conformance profile must be selectable: $profileId")
        }
        val artifactKind = if (lookupKind == "CONVERSION") "NCM" else "NKP"
        val artifactBinding = if (lookupKind == "CONVERSION") {
            requireString(profile, "conversion_binding", "profile $profileId")
        } else {
            requireString(profile, "pack_binding", "profile $profileId")
        }
        return linkedMapOf(
            "profile_id" to profileId,
            "language_id" to requireString(profile, "target_id", "profile $profileId"),
            "input_method_id" to requireString(profile, "input_method_id", "profile $profileId"),
            "locale_tag" to requireString(profile, "language_tag", "profile $profileId"),
            "display_name" to requireString(profile, "display_label", "profile $profileId"),
            "native_name" to requireString(profile, "native_label", "profile $profileId"),
            "source_script" to requireString(profile, "source_script", "profile $profileId"),
            "output_script" to requireString(profile, "output_script", "profile $profileId"),
            "detail" to requireString(profile, "input_label", "profile $profileId"),
            "method_type" to requireString(profile, "method_type", "profile $profileId"),
            "engine_kind" to requireString(profile, "engine_kind", "profile $profileId"),
            "layout_id" to layoutId,
            "lookup_kind" to lookupKind,
            "artifact_kind" to artifactKind,
            "artifact_binding" to artifactBinding,
            "catalog_readiness" to requireString(
                profile,
                "catalog_readiness",
                "profile $profileId",
            ),
            "availability" to "AVAILABLE",
            "blocked_reason" to nullableProfileString(profile, "blocked_reason", profileId),
            "blocked_detail" to nullableProfileString(profile, "blocked_detail", profileId),
            "default_enabled" to requireProfileBoolean(profile, "default_enabled", profileId),
            "scope" to requireString(profile, "scope", "profile $profileId"),
            "group" to nullableProfileString(profile, "group", profileId),
            "variety" to nullableProfileString(profile, "variety", profileId),
            "sort_key" to requireString(profile, "sort_key", "profile $profileId"),
            "search_aliases" to requireStringList(profile, "search_aliases", "profile $profileId"),
            "evidence_ids" to requireStringList(profile, "evidence_ids", "profile $profileId"),
            "layers" to fingerprints,
            "dispatch_probe" to linkedMapOf(
                "layer_id" to "base",
                "key_id" to requireString(defaultProbe, "key_id", "profile $profileId probe"),
                "text" to requireString(defaultProbe, "text", "profile $profileId probe"),
            ),
        )
    }

    private fun renderedLayerFingerprint(
        profile: Map<*, *>,
        layerId: String,
        layer: Map<*, *>,
    ): String {
        val digest = MessageDigest.getInstance("SHA-256")
        updateFingerprintString(digest, "nepa-runtime-layer-v1")
        updateFingerprintString(digest, layerId)
        val rows = requireList(layer, "rows", "compiled $layerId layer")
        updateFingerprintInt(digest, rows.size)
        for (rowValue in rows) {
            val row = rowValue as List<*>
            updateFingerprintInt(digest, row.size)
            for (keyValue in row) {
                val key = keyValue as Map<*, *>
                val kind = requireString(key, "kind", "compiled $layerId key")
                updateFingerprintString(
                    digest,
                    requireString(key, "key_id", "compiled $layerId key"),
                )
                updateFingerprintString(
                    digest,
                    bindProfileTemplate(
                        requireString(key, "label", "compiled $layerId key"),
                        profile,
                    ),
                )
                updateFingerprintNullableString(digest, key["text"] as? String)
                updateFingerprintString(
                    digest,
                    bindProfileTemplate(
                        requireString(key, "content_description", "compiled $layerId key"),
                        profile,
                    ),
                )
                updateFingerprintString(
                    digest,
                    if (kind in TEXT_KEY_KINDS) {
                        "TEXT"
                    } else {
                        requireString(key, "action", "compiled $layerId key")
                            .uppercase(Locale.ROOT)
                    },
                )
                updateFingerprintNullableString(
                    digest,
                    when (kind) {
                        "text" -> "DEFAULT"
                        "orthographic_word" -> "ORTHOGRAPHIC_WORD"
                        "intra_word_punctuation" -> "INTRA_WORD_PUNCTUATION"
                        "deva_conjunct_joiner" -> "DEVA_CONJUNCT_JOINER"
                        "deva_terminal_zwnj" -> "DEVA_TERMINAL_ZWNJ"
                        "newa_conjunct_joiner" -> "NEWA_CONJUNCT_JOINER"
                        "action" -> null
                        else -> throw GradleException("Unsupported compiled key kind $kind")
                    },
                )
                updateFingerprintInt(
                    digest,
                    requireExactInt(key, "width_units", "compiled $layerId key"),
                )
                updateFingerprintNullableString(
                    digest,
                    when (key["hold_action"]) {
                        null -> null
                        "open_language_picker" -> "OPEN_LANGUAGE_PICKER"
                        else -> throw GradleException("Unsupported compiled hold action")
                    },
                )
            }
        }
        return digest.digest().joinToString("") { byte -> "%02x".format(byte) }
    }

    private fun bindProfileTemplate(value: String, profile: Map<*, *>): String = value
        .replace(
            "\${profile.native_name}",
            requireString(profile, "native_label", "selectable shipping profile"),
        )
        .replace(
            "\${profile.display_name}",
            requireString(profile, "display_label", "selectable shipping profile"),
        )

    private fun nullableProfileString(
        profile: Map<*, *>,
        field: String,
        profileId: String,
    ): String? {
        val value = profile[field] ?: return null
        return (value as? String)?.takeIf(String::isNotEmpty)
            ?: throw GradleException("Profile $profileId field $field is invalid")
    }

    private fun requireProfileBoolean(
        profile: Map<*, *>,
        field: String,
        profileId: String,
    ): Boolean = profile[field] as? Boolean
        ?: throw GradleException("Profile $profileId field $field must be boolean")

    private fun updateFingerprintString(digest: MessageDigest, value: String) {
        updateFingerprintNullableString(digest, value)
    }

    private fun updateFingerprintNullableString(digest: MessageDigest, value: String?) {
        if (value == null) {
            updateFingerprintInt(digest, -1)
            return
        }
        val encoded = value.toByteArray(StandardCharsets.UTF_8)
        updateFingerprintInt(digest, encoded.size)
        digest.update(encoded)
    }

    private fun updateFingerprintInt(digest: MessageDigest, value: Int) {
        digest.update(ByteBuffer.allocate(4).putInt(value).array())
    }

    private fun layoutNoticeName(
        layout: Map<*, *>,
        noticePathPrefix: String,
    ): String? {
        val layoutId = requireString(layout, "layout_id", "compiled layout")
        val license = layout["license"] as? Map<*, *> ?: return null
        val hasNoticePath = license.containsKey("notice_path")
        val hasNoticeSha256 = license.containsKey("notice_sha256")
        if (!hasNoticePath && !hasNoticeSha256) {
            return null
        }
        if (hasNoticePath != hasNoticeSha256) {
            throw GradleException(
                "Compiled layout $layoutId must provide its notice path and SHA-256 together"
            )
        }
        val noticePath = requireString(
            license,
            "notice_path",
            "compiled layout $layoutId.license",
        )
        if (!noticePath.startsWith(noticePathPrefix)) {
            throw GradleException(
                "Compiled layout $layoutId notice is outside the configured notice directory"
            )
        }
        val noticeName = noticePath.removePrefix(noticePathPrefix)
        if (!NOTICE_NAME.matches(noticeName) || noticeName == "manifest.json") {
            throw GradleException("Compiled layout $layoutId has an unsafe notice asset name")
        }
        return noticeName
    }

    private fun layoutNoticeRow(layout: Map<*, *>): Map<String, Any?>? {
        val layoutId = requireString(layout, "layout_id", "compiled layout")
        val license = layout["license"] as? Map<*, *> ?: return null
        val noticeName = layoutNoticeName(
            layout,
            "${expectedNoticeDirectoryPath.get()}/",
        ) ?: return null
        val sourceUrl = requireList(layout, "provenance", "compiled layout $layoutId")
            .map { it as Map<*, *> }
            .mapNotNull { it["source_url"] as? String }
            .firstOrNull()
        return linkedMapOf(
            "layout_id" to layoutId,
            "display_name" to requireString(layout, "display_name", "compiled layout $layoutId"),
            "license_id" to requireString(license, "id", "compiled layout $layoutId.license"),
            "copyright" to requireString(
                license,
                "copyright",
                "compiled layout $layoutId.license",
            ),
            "license_url" to license["license_url"],
            "notice_asset_path" to "nepa-layout-notices/$noticeName",
            "notice_sha256" to requireSha256(
                license,
                "notice_sha256",
                "compiled layout $layoutId.license",
            ),
            "source_url" to sourceUrl,
        )
    }

    private fun validateLayoutLicense(
        value: Any?,
        location: String,
        layoutId: String,
        noticeDir: File,
        authority: String,
    ) {
        if (authority !in setOf("release", "internal")) {
            throw GradleException("$location has unsupported authority $authority")
        }
        if (value == null) {
            if (authority == "release") {
                throw GradleException("$location.license must be an object for release authority")
            }
            return
        }
        val license = value as? Map<*, *>
            ?: throw GradleException("$location.license must be an object or null")
        val requiredFields = setOf("id", "copyright", "redistribution")
        val allowedFields = requiredFields + setOf(
            "notice_path", "notice_sha256", "license_url"
        )
        if (authority == "release") {
            requireExactKeys(license, allowedFields, "$location.license")
        } else {
            requireAllowedKeys(
                license,
                requiredFields,
                allowedFields,
                "$location.license",
            )
        }
        requireNfcString(license, "id", "$location.license")
        requireNfcString(license, "copyright", "$location.license")

        val hasNoticePath = license.containsKey("notice_path")
        val hasNoticeSha256 = license.containsKey("notice_sha256")
        if (hasNoticePath != hasNoticeSha256) {
            throw GradleException(
                "$location.license notice_path and notice_sha256 must be provided together"
            )
        }
        if (hasNoticePath) {
            val noticePath = requireString(license, "notice_path", "$location.license")
            val noticePrefix = "${expectedNoticeDirectoryPath.get()}/"
            val noticeName = noticePath.removePrefix(noticePrefix)
            if (!noticePath.startsWith(noticePrefix)
                || !NOTICE_NAME.matches(noticeName)
                || noticeName == "manifest.json"
            ) {
                throw GradleException("$location.license.notice_path is unsafe or reserved")
            }
            val noticeSha256 = requireSha256(
                license,
                "notice_sha256",
                "$location.license",
            )
            val noticeFile = File(noticeDir, noticeName)
            rejectSymlink(noticeFile, "layout notice for $layoutId")
            if (!noticeFile.isFile
                || noticeFile.length() !in 1L..MAX_NOTICE_BYTES.toLong()
                || sha256(noticeFile) != noticeSha256
            ) {
                throw GradleException(
                    "$location.license notice is missing or has wrong SHA-256"
                )
            }
            validateNoticeUtf8(noticeFile, "$location.license notice")
        }

        if (license.containsKey("license_url")) {
            val licenseUrl = requireString(license, "license_url", "$location.license")
            if (!licenseUrl.startsWith("https://")) {
                throw GradleException("$location.license.license_url must use HTTPS")
            }
        }
        val redistribution = requireString(license, "redistribution", "$location.license")
        if (redistribution !in setOf(
                "allowed", "prohibited", "permission_required", "unknown", "system"
            )
            || (authority == "release" && redistribution != "allowed")
        ) {
            throw GradleException(
                "$location.license.redistribution is not valid for $authority authority"
            )
        }
    }

    private fun validateLayout(
        layout: Map<*, *>,
        index: Int,
        sourceDir: File,
        noticeDir: File,
        authority: String,
    ): Map<*, *> {
        val location = "layout lock.layouts[$index]"
        requireExactKeys(layout, LAYOUT_KEYS, location)
        val layoutId = requirePattern(layout, "layout_id", location, ID)
        requirePositiveInt(layout, "revision", location)
        requireNfcString(layout, "display_name", location)
        val inputScript = requirePattern(layout, "input_script", location, SCRIPT)
        if (inputScript !in setOf(
                "Deva", "Latn", "Lepc", "Limb", "Newa", "Olck", "Sunu", "Tibt", "Tirh"
            )
        ) {
            throw GradleException("Android layout runtime does not support script $inputScript")
        }
        requireString(layout, "direction", location, "ltr")
        requireString(layout, "normalization", location, "NFC")
        requireString(layout, "unicode_data_version", location, "16.0.0")
        val forms = requireStringList(layout, "device_forms", location)
        if (forms != listOf("phone")) {
            throw GradleException("Android layout runtime currently requires exactly the phone form")
        }
        requireNonEmptyUniqueStrings(layout, "authors", location)

        validateLayoutLicense(layout["license"], location, layoutId, noticeDir, authority)

        val provenance = requireList(layout, "provenance", location)
        if (provenance.isEmpty()) {
            throw GradleException("$location.provenance must not be empty")
        }
        provenance.forEachIndexed { provenanceIndex, value ->
            val row = value as? Map<*, *>
                ?: throw GradleException("$location.provenance[$provenanceIndex] must be an object")
            val rowLocation = "$location.provenance[$provenanceIndex]"
            val requiredFields = setOf("kind", "source", "revision", "sha256", "note")
            val allowedFields = requiredFields + "source_url"
            requireAllowedKeys(row, requiredFields, allowedFields, rowLocation)
            val kind = requireString(row, "kind", rowLocation)
            if (kind !in setOf("project_authored", "adapted", "standard_reference")) {
                throw GradleException("$rowLocation.kind is unsupported")
            }
            requireNfcString(row, "source", rowLocation)
            requireNfcString(row, "revision", rowLocation)
            requireSha256(row, "sha256", rowLocation)
            requireNfcString(row, "note", rowLocation)
            if ("source_url" in row) {
                val sourceUrl = requireString(row, "source_url", rowLocation)
                if (!sourceUrl.startsWith("https://")) {
                    throw GradleException("$rowLocation.source_url must use HTTPS")
                }
            }
        }

        val fields = requireObject(layout, "field_layer_map", location)
        requireExactKeys(fields, setOf("text", "number", "phone", "datetime"), "$location.field_layer_map")
        requireString(fields, "text", "$location.field_layer_map", "base")
        for (field in listOf("number", "phone", "datetime")) {
            requireString(fields, field, "$location.field_layer_map", "numeric")
        }

        val source = requireObject(layout, "source", location)
        requireExactKeys(source, setOf("path", "sha256"), "$location.source")
        val sourcePath = requireString(source, "path", "$location.source")
        val expectedPath = "${expectedSourceDirectoryPath.get()}/$layoutId.json"
        if (sourcePath != expectedPath) {
            throw GradleException("$location.source.path must be $expectedPath")
        }
        val expectedSourceSha = requireSha256(source, "sha256", "$location.source")
        val sourceFile = File(sourceDir, "$layoutId.json")
        rejectSymlink(sourceFile, "layout source $layoutId")
        if (!sourceFile.isFile) {
            throw GradleException("Missing declarative layout source: $sourcePath")
        }
        val actualSourceSha = sha256(sourceFile)
        if (actualSourceSha != expectedSourceSha) {
            throw GradleException(
                "Layout source hash mismatch for $layoutId: expected $expectedSourceSha, got $actualSourceSha"
            )
        }

        val transforms = requireList(layout, "transforms", location)
        if (transforms.isNotEmpty()) {
            throw GradleException(
                "Compiled layout $layoutId has transforms, but Android transform runtime is not implemented"
            )
        }

        val layers = requireObject(layout, "layers", location)
        requireExactKeys(layers, LAYER_IDS.toSet(), "$location.layers")
        val keyIds = mutableSetOf<String>()
        for (layerId in LAYER_IDS) {
            val layer = layers[layerId] as? Map<*, *>
                ?: throw GradleException("$location.layers.$layerId must be an object")
            requireExactKeys(layer, setOf("rows"), "$location.layers.$layerId")
            val rows = requireList(layer, "rows", "$location.layers.$layerId")
            if (rows.isEmpty() || rows.size > 8) {
                throw GradleException("$location.layers.$layerId must have 1 to 8 rows")
            }
            val textValues = mutableListOf<String>()
            val actionLocations = mutableListOf<Pair<Int, String>>()
            rows.forEachIndexed { rowIndex, rowValue ->
                val row = rowValue as? List<*>
                    ?: throw GradleException("$location.layers.$layerId.rows[$rowIndex] must be an array")
                if (row.isEmpty() || row.size > 20) {
                    throw GradleException("$location.layers.$layerId.rows[$rowIndex] must have 1 to 20 keys")
                }
                row.forEachIndexed { keyIndex, keyValue ->
                    val key = keyValue as? Map<*, *>
                        ?: throw GradleException(
                            "$location.layers.$layerId.rows[$rowIndex][$keyIndex] must be an object"
                        )
                    validateKey(
                        key,
                        "$location.layers.$layerId.rows[$rowIndex][$keyIndex]",
                        "$layerId.r$rowIndex.k$keyIndex",
                        layerId,
                        inputScript,
                    )
                    val keyId = requireString(key, "key_id", "compiled key")
                    if (!keyIds.add(keyId)) {
                        throw GradleException("Compiled layout $layoutId has duplicate key ID $keyId")
                    }
                    when (requireString(key, "kind", "compiled key $keyId")) {
                        in TEXT_KEY_KINDS ->
                            textValues += requireString(key, "text", "compiled key $keyId")
                        "action" -> actionLocations += rowIndex to
                            requireString(key, "action", "compiled key $keyId")
                    }
                }
            }
            if (textValues.toSet().size != textValues.size) {
                throw GradleException("$location.layers.$layerId contains duplicate text keys")
            }
            if (actionLocations.map { it.second } != EXPECTED_LAYER_ACTIONS.getValue(layerId)) {
                throw GradleException(
                    "$location.layers.$layerId does not match the closed v1 action sequence"
                )
            }
            if (actionLocations.any { it.first != rows.lastIndex }) {
                throw GradleException("$location.layers.$layerId action keys must be in the final row")
            }
            val finalRow = rows.last() as List<*>
            if (finalRow.any { (it as Map<*, *>)["kind"] != "action" }) {
                throw GradleException("$location.layers.$layerId final row must contain only actions")
            }
            if (layerId in setOf("base", "shift")
                && textValues.none { containsDeclaredScript(it, inputScript) }
            ) {
                throw GradleException("$location.layers.$layerId has no key from $inputScript")
            }
        }
        return layout
    }

    private fun validateKey(
        key: Map<*, *>,
        location: String,
        expectedKeyId: String,
        layerId: String,
        inputScript: String,
    ) {
        requireExactKeys(key, KEY_KEYS, location)
        val keyId = requireString(key, "key_id", location)
        if (keyId != expectedKeyId) {
            throw GradleException("$location.key_id must be $expectedKeyId")
        }
        val kind = requireString(key, "kind", location)
        val label = requireNfcString(key, "label", location)
        validatePlaceholders(label, "$location.label")
        val description = requireNfcString(key, "content_description", location)
        validatePlaceholders(description, "$location.content_description")
        val width = requireExactInt(key, "width_units", location)
        if (width !in 25..1000) {
            throw GradleException("$location.width_units must be an integer from 25 to 1000")
        }
        val hold = key["hold_action"]
        if (hold != null && hold != "open_language_picker") {
            throw GradleException("$location.hold_action is unsupported")
        }
        when (kind) {
            in TEXT_KEY_KINDS -> {
                val text = key["text"] as? String
                    ?: throw GradleException(
                        "$location.text must be a string for a text-bearing key"
                    )
                if (text.isEmpty()
                    || text.codePointCount(0, text.length) > MAX_TEXT_SCALARS
                    || !Normalizer.isNormalized(text, Normalizer.Form.NFC)
                ) {
                    throw GradleException("$location.text must be non-empty NFC")
                }
                if (key["action"] != null || hold != null) {
                    throw GradleException(
                        "$location text-bearing key cannot define action or hold_action"
                    )
                }
                if (width != 100) {
                    throw GradleException("$location text-bearing key width_units must be 100")
                }
                if ("\${" in label || "\${" in description) {
                    throw GradleException(
                        "$location text-bearing label and description cannot use placeholders"
                    )
                }
                when (kind) {
                    "text" -> validateText(text, "$location.text", layerId, inputScript)
                    "orthographic_word" -> {
                        if (text != "\u2018") {
                            throw GradleException(
                                "$location orthographic_word text must be exactly U+2018"
                            )
                        }
                        validateText(text, "$location.text", layerId, inputScript)
                    }
                    "intra_word_punctuation" -> {
                        if (text !in setOf("-", "/", "\\", ":")) {
                            throw GradleException(
                                "$location intra_word_punctuation text must be " +
                                    "hyphen, slash, backslash, or colon"
                            )
                        }
                        validateText(text, "$location.text", layerId, inputScript)
                    }
                    "deva_conjunct_joiner" -> {
                        if (inputScript != "Deva") {
                            throw GradleException(
                                "$location deva_conjunct_joiner requires input script Deva"
                            )
                        }
                        if (text != "\u200c" && text != "\u200d") {
                            throw GradleException(
                                "$location deva_conjunct_joiner text must be U+200C or U+200D"
                            )
                        }
                    }
                    "deva_terminal_zwnj" -> {
                        if (inputScript != "Deva") {
                            throw GradleException(
                                "$location deva_terminal_zwnj requires input script Deva"
                            )
                        }
                        if (text != "\u200c") {
                            throw GradleException(
                                "$location deva_terminal_zwnj text must be U+200C"
                            )
                        }
                    }
                    "newa_conjunct_joiner" -> {
                        if (inputScript != "Newa") {
                            throw GradleException(
                                "$location newa_conjunct_joiner requires input script Newa"
                            )
                        }
                        if (text != "\u200c" && text != "\u200d") {
                            throw GradleException(
                                "$location newa_conjunct_joiner text must be U+200C or U+200D"
                            )
                        }
                    }
                }
            }
            "action" -> {
                if (key["text"] != null) {
                    throw GradleException("$location action key text must be null")
                }
                val action = key["action"] as? String
                    ?: throw GradleException("$location.action must be a string for an action key")
                if (action !in ACTIONS) {
                    throw GradleException("$location.action is unsupported")
                }
                if (hold != null && action !in setOf("space", "language")) {
                    throw GradleException(
                        "$location.hold_action is only valid for space or language"
                    )
                }
            }
            else -> throw GradleException("$location.kind is unsupported")
        }
    }

    private fun validateText(
        text: String,
        location: String,
        layerId: String,
        inputScript: String,
    ) {
        var offset = 0
        while (offset < text.length) {
            val codePoint = text.codePointAt(offset)
            val type = Character.getType(codePoint)
            if (type == Character.CONTROL.toInt()
                || type == Character.FORMAT.toInt()
                || type == Character.SURROGATE.toInt()
                || type == Character.PRIVATE_USE.toInt()
                || type == Character.LINE_SEPARATOR.toInt()
                || type == Character.PARAGRAPH_SEPARATOR.toInt()
            ) {
                throw GradleException("$location contains forbidden U+${codePoint.toString(16).uppercase(Locale.ROOT)}")
            }
            val script = Character.UnicodeScript.of(codePoint)
            if (!isDeclaredScriptCodePoint(codePoint, inputScript)
                && script != Character.UnicodeScript.COMMON
                && script != Character.UnicodeScript.INHERITED
            ) {
                throw GradleException("$location in $layerId contains text outside $inputScript")
            }
            offset += Character.charCount(codePoint)
        }
    }

    private fun containsDeclaredScript(text: String, inputScript: String): Boolean {
        var offset = 0
        while (offset < text.length) {
            val codePoint = text.codePointAt(offset)
            if (isDeclaredScriptCodePoint(codePoint, inputScript)) {
                return true
            }
            offset += Character.charCount(codePoint)
        }
        return false
    }

    private fun isDeclaredScriptCodePoint(codePoint: Int, inputScript: String): Boolean =
        when (inputScript) {
            "Deva" -> codePoint in 0x0900..0x097f
                || codePoint in 0xa8e0..0xa8ff
                || codePoint in 0x11b00..0x11b5f
            "Latn" -> codePoint in 0x0041..0x005a
                || codePoint in 0x0061..0x007a
                || codePoint in 0x00c0..0x024f
                || codePoint in 0x1e00..0x1eff
            "Lepc" -> codePoint in 0x1c00..0x1c4f
            "Limb" -> codePoint in 0x1900..0x194f
            "Newa" -> codePoint in 0x11400..0x1147f
            "Olck" -> codePoint in 0x1c50..0x1c7f
            "Sunu" -> codePoint in 0x11bc0..0x11bff
            "Tibt" -> codePoint in 0x0f00..0x0fff
            "Tirh" -> codePoint in 0x11480..0x114df
            else -> throw GradleException("Unsupported input script $inputScript")
        }

    private fun javaLayout(index: Int, layout: Map<*, *>): String {
        val layoutId = requireString(layout, "layout_id", "compiled layout")
        val inputScript = requireString(layout, "input_script", "compiled layout $layoutId")
        val layers = requireObject(layout, "layers", "compiled layout $layoutId")
        val layerValues = LAYER_IDS.joinToString(",\n") { layerId ->
            javaLayer(layerId, layers[layerId] as Map<*, *>)
        }
        return """
            |    private static KeyboardLayouts.LayoutSet createLayout$index() {
            |        return new KeyboardLayouts.LayoutSet(
            |                ${javaString(layoutId)},
            |                ${javaString(inputScript)},
            |$layerValues
            |        );
            |    }
        """.trimMargin()
    }

    private fun javaLayer(layerId: String, layer: Map<*, *>): String {
        val rows = requireList(layer, "rows", "compiled layer $layerId")
        val javaRows = rows.map { it as List<*> }.joinToString(",\n") { row ->
            val keys = row.joinToString(",\n") { value ->
                javaKey(value as Map<*, *>)
            }
            """
                |                        Arrays.asList(
                |$keys
                |                        )
            """.trimMargin()
        }
        return """
            |                new KeyboardLayouts.Layer(
            |                        ${javaString(layerId)},
            |                        Arrays.asList(
            |$javaRows
            |                        )
            |                )
        """.trimMargin()
    }

    private fun javaKey(key: Map<*, *>): String {
        val keyId = requireString(key, "key_id", "compiled key")
        val label = requireString(key, "label", "compiled key $keyId")
        val description = requireString(key, "content_description", "compiled key $keyId")
        val width = (key["width_units"] as Number).toInt()
        val hold = when (key["hold_action"]) {
            null -> "null"
            "open_language_picker" -> "KeySpec.HoldAction.OPEN_LANGUAGE_PICKER"
            else -> throw GradleException("Unsupported compiled hold action")
        }
        val kind = key["kind"] as? String
            ?: throw GradleException("Compiled key $keyId kind must be a string")
        return when {
            kind in TEXT_KEY_KINDS -> {
                val policy = when (kind) {
                    "text" -> "KeySpec.InputPolicy.DEFAULT"
                    "orthographic_word" -> "KeySpec.InputPolicy.ORTHOGRAPHIC_WORD"
                    "intra_word_punctuation" ->
                        "KeySpec.InputPolicy.INTRA_WORD_PUNCTUATION"
                    "deva_conjunct_joiner" -> "KeySpec.InputPolicy.DEVA_CONJUNCT_JOINER"
                    "deva_terminal_zwnj" -> "KeySpec.InputPolicy.DEVA_TERMINAL_ZWNJ"
                    "newa_conjunct_joiner" -> "KeySpec.InputPolicy.NEWA_CONJUNCT_JOINER"
                    else -> throw GradleException("Unsupported compiled text key kind")
                }
                """
                    |                                KeySpec.generatedText(
                    |                                        ${javaString(keyId)},
                    |                                        ${javaString(label)},
                    |                                        ${javaString(key["text"] as String)},
                    |                                        ${javaString(description)},
                    |                                        $policy,
                    |                                        $width,
                    |                                        $hold
                    |                                )
                """.trimMargin()
            }
            kind == "action" -> {
                val action = (key["action"] as String).uppercase(Locale.ROOT)
                """
                    |                                KeySpec.generatedAction(
                    |                                        ${javaString(keyId)},
                    |                                        ${javaString(label)},
                    |                                        ${javaString(description)},
                    |                                        KeySpec.Action.$action,
                    |                                        $width,
                    |                                        $hold
                    |                                )
                """.trimMargin()
            }
            else -> throw GradleException("Unsupported compiled key kind $kind")
        }
    }

    private fun parseObject(file: File, label: String): Map<*, *> {
        val parsed = try {
            JsonSlurper().parseText(file.readText(StandardCharsets.UTF_8))
        } catch (failure: RuntimeException) {
            throw GradleException("$label is invalid JSON", failure)
        }
        return parsed as? Map<*, *>
            ?: throw GradleException("$label must be an object")
    }

    private fun requireObject(row: Map<*, *>, field: String, location: String): Map<*, *> =
        row[field] as? Map<*, *>
            ?: throw GradleException("$location.$field must be an object")

    private fun requireList(row: Map<*, *>, field: String, location: String): List<*> =
        row[field] as? List<*>
            ?: throw GradleException("$location.$field must be an array")

    private fun requireString(row: Map<*, *>, field: String, location: String): String =
        (row[field] as? String)?.takeIf(String::isNotEmpty)
            ?: throw GradleException("$location.$field must be a non-empty string")

    private fun requireString(
        row: Map<*, *>,
        field: String,
        location: String,
        expected: String,
    ): String {
        val value = requireString(row, field, location)
        if (value != expected) {
            throw GradleException("$location.$field must be $expected")
        }
        return value
    }

    private fun requireNfcString(row: Map<*, *>, field: String, location: String): String {
        val value = requireString(row, field, location)
        if (!Normalizer.isNormalized(value, Normalizer.Form.NFC)) {
            throw GradleException("$location.$field must be NFC")
        }
        return value
    }

    private fun requirePattern(
        row: Map<*, *>,
        field: String,
        location: String,
        pattern: Regex,
    ): String {
        val value = requireString(row, field, location)
        if (!pattern.matches(value)) {
            throw GradleException("$location.$field has invalid syntax")
        }
        return value
    }

    private fun requireSha256(row: Map<*, *>, field: String, location: String): String =
        requirePattern(row, field, location, SHA256)

    private fun requireInt(
        row: Map<*, *>,
        field: String,
        location: String,
        expected: Int,
    ) {
        if (requireExactInt(row, field, location) != expected) {
            throw GradleException("$location.$field must be $expected")
        }
    }

    private fun requirePositiveInt(row: Map<*, *>, field: String, location: String): Int {
        val value = requireExactInt(row, field, location)
        if (value < 1) {
            throw GradleException("$location.$field must be a positive integer")
        }
        return value
    }

    private fun requireExactInt(row: Map<*, *>, field: String, location: String): Int {
        val encoded = (row[field] as? Number)?.toString()
            ?: throw GradleException("$location.$field must be an integer")
        if (!INTEGER.matches(encoded)) {
            throw GradleException("$location.$field must be an integer")
        }
        return encoded.toIntOrNull()
            ?: throw GradleException("$location.$field is outside the integer range")
    }

    private fun requireStringList(row: Map<*, *>, field: String, location: String): List<String> {
        val values = requireList(row, field, location)
        return values.mapIndexed { index, value ->
            (value as? String)?.takeIf(String::isNotEmpty)
                ?: throw GradleException("$location.$field[$index] must be a non-empty string")
        }
    }

    private fun requireNonEmptyUniqueStrings(
        row: Map<*, *>,
        field: String,
        location: String,
    ): List<String> {
        val values = requireStringList(row, field, location)
        if (values.isEmpty() || values.toSet().size != values.size) {
            throw GradleException("$location.$field must be a non-empty unique string array")
        }
        values.forEachIndexed { index, value ->
            if (!Normalizer.isNormalized(value, Normalizer.Form.NFC)) {
                throw GradleException("$location.$field[$index] must be NFC")
            }
        }
        return values
    }

    private fun requireExactKeys(row: Map<*, *>, expected: Set<String>, location: String) {
        val keys = row.keys.map { key ->
            key as? String ?: throw GradleException("$location contains a non-string field name")
        }.toSet()
        if (keys != expected) {
            val missing = (expected - keys).sorted()
            val extra = (keys - expected).sorted()
            throw GradleException("$location fields mismatch: missing=$missing extra=$extra")
        }
    }

    private fun requireAllowedKeys(
        row: Map<*, *>,
        required: Set<String>,
        allowed: Set<String>,
        location: String,
    ) {
        val keys = row.keys.map { key ->
            key as? String ?: throw GradleException("$location contains a non-string field name")
        }.toSet()
        if (!keys.containsAll(required) || !allowed.containsAll(keys)) {
            val missing = (required - keys).sorted()
            val extra = (keys - allowed).sorted()
            throw GradleException("$location fields mismatch: missing=$missing extra=$extra")
        }
    }

    private fun validateInputReference(
        reference: Map<*, *>,
        location: String,
        expectedPath: String,
        file: File,
    ) {
        requireExactKeys(reference, setOf("path", "sha256"), location)
        requireString(reference, "path", location, expectedPath)
        val expectedSha256 = requireSha256(reference, "sha256", location)
        val actualSha256 = sha256(file)
        if (actualSha256 != expectedSha256) {
            throw GradleException("$location SHA-256 mismatch")
        }
    }

    private fun validatePlaceholders(value: String, location: String) {
        var stripped = value
        for (placeholder in PROFILE_PLACEHOLDERS) {
            stripped = stripped.replace(placeholder, "")
        }
        if ("\${" in stripped) {
            throw GradleException("$location contains an unsupported profile placeholder")
        }
    }

    private fun validateNoticeUtf8(file: File, location: String) {
        val encoded = Files.readAllBytes(file.toPath())
        if (encoded.size >= 3
            && encoded[0] == 0xef.toByte()
            && encoded[1] == 0xbb.toByte()
            && encoded[2] == 0xbf.toByte()
        ) {
            throw GradleException("$location must be UTF-8 without BOM")
        }
        try {
            StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(encoded))
        } catch (invalidUtf8: CharacterCodingException) {
            throw GradleException("$location must be strict UTF-8", invalidUtf8)
        }
    }

    private fun rejectSymlink(file: File, label: String) {
        if (Files.isSymbolicLink(file.toPath())) {
            throw GradleException("$label must not be a symbolic link: $file")
        }
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        FileInputStream(file).use { stream ->
            val buffer = ByteArray(8192)
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) {
                    break
                }
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { byte -> "%02x".format(byte) }
    }

    private fun sha256(encoded: ByteArray): String =
        MessageDigest.getInstance("SHA-256")
            .digest(encoded)
            .joinToString("") { byte -> "%02x".format(byte) }

    private fun javaString(value: String): String = JsonOutput.toJson(value)
}

@DisableCachingByDefault(
    because = "Catalog assets must be verified from the explicitly supplied external files"
)
abstract class StageExternalPackStager : DefaultTask() {
    companion object {
        private const val MAX_PACK_BYTES = 256L * 1024L * 1024L
        private const val MAX_NKP_MANIFEST_BYTES = 1024 * 1024
        private const val MAX_NKP_MEMBER_BYTES = 128 * 1024 * 1024
        private val REQUIRED_NKP_MEMBERS = setOf(
            "aliases.trie",
            "candidates.bin",
            "notices.json",
            "scores.bin",
            "surface.trie",
        )
        private val REQUIRED_ARCHIVE_ENTRIES = REQUIRED_NKP_MEMBERS + "manifest.json"
    }

    @get:Input
    abstract val sourceDirectoryPath: Property<String>

    @get:Input
    abstract val bindingRows: ListProperty<String>

    @get:Optional
    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val profileLockFile: RegularFileProperty

    @get:Optional
    @get:Input
    abstract val expectedProfileLockSha256: Property<String>

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun stage() {
        val configuredDirectory = sourceDirectoryPath.orNull?.takeIf(String::isNotBlank)
            ?: throw GradleException(
                "External catalog packs are required; pass the variant's nepa pack directory property"
            )
        val sourceDirectory = File(configuredDirectory)
        if (Files.isSymbolicLink(sourceDirectory.toPath()) || !sourceDirectory.isDirectory) {
            throw GradleException("External pack directory does not exist or is not a directory")
        }

        val encodedBindings = bindingRows.getOrElse(emptyList())
        val hasProfileLock = profileLockFile.isPresent
        if (hasProfileLock == encodedBindings.isNotEmpty()) {
            throw GradleException(
                "Pack staging needs exactly one reviewed profile lock or explicit binding set"
            )
        }
        val bindings = if (hasProfileLock) {
            readReviewedBindings(profileLockFile.get().asFile)
        } else {
            encodedBindings.map(::decodeBinding)
        }
        if (bindings.isEmpty() || bindings.map { it.profileId }.toSet().size != bindings.size) {
            throw GradleException("Pack bindings must be non-empty and profile-unique")
        }
        for (field in listOf("pack ID", "file name")) {
            val groups = if (field == "pack ID") {
                bindings.groupBy { it.packId }
            } else {
                bindings.groupBy { it.fileName }
            }
            if (groups.values.any { rows ->
                    rows.map(::artifactIdentity).toSet().size != 1
                }
            ) {
                throw GradleException("Pack bindings contain conflicting $field reuse")
            }
        }
        val sources = bindings.associateWith { binding ->
            File(sourceDirectory, binding.fileName)
        }
        for ((binding, source) in sources) {
            if (!Files.isRegularFile(source.toPath(), LinkOption.NOFOLLOW_LINKS)) {
                throw GradleException("Missing regular pack: ${binding.fileName}")
            }
            if (source.length() <= 0L || source.length() > MAX_PACK_BYTES) {
                throw GradleException("Pack size is outside the 256 MiB limit: ${binding.fileName}")
            }
        }

        val outputRoot = outputDirectory.get().asFile
        if (outputRoot.exists() && !outputRoot.deleteRecursively()) {
            throw GradleException("Could not clear generated pack assets")
        }
        val assetDirectory = File(outputRoot, "nepa-packs")
        if (!assetDirectory.mkdirs() && !assetDirectory.isDirectory) {
            throw GradleException("Could not create generated pack asset directory")
        }

        try {
            for (binding in bindings.distinctBy(::artifactIdentity)) {
                val staged = File(assetDirectory, binding.fileName)
                Files.copy(
                    sources.getValue(binding).toPath(),
                    staged.toPath(),
                    StandardCopyOption.REPLACE_EXISTING,
                )
                val actualSha256 = sha256(staged)
                if (actualSha256 != binding.artifactSha256) {
                    throw GradleException("Pack SHA-256 mismatch: ${binding.fileName}")
                }
                verifyNkpManifest(
                    staged,
                    binding,
                    acceptedReleaseMode(binding.releaseMode),
                    enforceRedistributionApproval(),
                )
            }
            val manifestRows = bindings.map { binding ->
                linkedMapOf<String, Any>(
                    "profile_id" to binding.profileId,
                    "pack_id" to binding.packId,
                    "asset_path" to "nepa-packs/${binding.fileName}",
                    "artifact_sha256" to binding.artifactSha256,
                )
            }
            val generatedManifest = linkedMapOf<String, Any>("packs" to manifestRows)
            File(assetDirectory, "manifest.json").writeText(
                JsonOutput.toJson(generatedManifest) + "\n",
                StandardCharsets.UTF_8,
            )
            val vectors = linkedMapOf<String, Any>(
                "bindings" to bindings.map { binding ->
                    linkedMapOf<String, Any>(
                        "profile_id" to binding.profileId,
                        "pack_id" to binding.packId,
                        "asset_path" to "nepa-packs/${binding.fileName}",
                        "artifact_sha256" to binding.artifactSha256,
                        "language" to binding.language,
                        "output_script" to binding.outputScript,
                        "artifact_license" to binding.artifactLicense,
                        "release_mode" to acceptedReleaseMode(binding.releaseMode),
                        "candidate_count" to binding.candidateCount,
                        "surface_key_count" to binding.surfaceKeyCount,
                        "alias_key_count" to binding.aliasKeyCount,
                        "lookup_kind" to binding.lookupKind,
                        "validation_query" to binding.validationQuery,
                        "validation_expected_surface" to binding.validationExpectedSurface,
                        "benchmark_queries" to binding.benchmarkQueries,
                    )
                },
            )
            File(assetDirectory, "benchmark-vectors.json").writeText(
                JsonOutput.toJson(vectors) + "\n",
                StandardCharsets.UTF_8,
            )
        } catch (failure: Exception) {
            outputRoot.deleteRecursively()
            throw failure
        }
    }

    private fun decodeBinding(encoded: String): ReleasePackBinding {
        val value = try {
            JsonSlurper().parseText(encoded)
        } catch (failure: RuntimeException) {
            throw GradleException("Invalid configured pack binding", failure)
        }
        val row = value as? Map<*, *>
            ?: throw GradleException("Configured pack binding must be an object")
        return decodeBindingObject(row, "configured pack binding")
    }

    private fun readReviewedBindings(lockFile: File): List<ReleasePackBinding> {
        if (Files.isSymbolicLink(lockFile.toPath())) {
            throw GradleException("Shipping-profile lock must not be a symbolic link")
        }
        val actualSha256 = sha256(lockFile)
        val expectedSha256 = expectedProfileLockSha256.orNull
            ?: throw GradleException("No reviewed profile-lock SHA-256 is configured")
        if (actualSha256 != expectedSha256) {
            throw GradleException(
                "Pack-staging profile lock is not reviewed: " +
                    "expected $expectedSha256, got $actualSha256"
            )
        }
        val root = try {
            JsonSlurper().parseText(
                lockFile.readText(StandardCharsets.UTF_8)
            ) as? Map<*, *>
        } catch (failure: RuntimeException) {
            throw GradleException("Shipping-profile lock is invalid JSON", failure)
        } ?: throw GradleException("Shipping-profile lock must be an object")
        val profiles = root["profiles"] as? List<*>
            ?: throw GradleException("Shipping-profile lock has no profiles")
        val bindings = profiles.mapIndexedNotNull { index, value ->
            val profile = value as? Map<*, *>
                ?: throw GradleException("Shipping profile $index must be an object")
            val isSelectable = profile["selectable"] as? Boolean
                ?: throw GradleException("Shipping profile $index selectable must be boolean")
            val lookupKind = requiredNonBlankString(
                profile["lookup_kind"], "shipping profile $index.lookup_kind"
            )
            if (!isSelectable) {
                if (profile["pack_binding"] != null
                    || profile["pack_artifact"] != null
                    || profile["conversion_binding"] != null
                    || profile["conversion_artifact"] != null
                ) {
                    throw GradleException("Blocked profile carries a runtime artifact")
                }
                null
            } else if (lookupKind == "conversion") {
                if (profile["pack_binding"] != null || profile["pack_artifact"] != null) {
                    throw GradleException("Conversion profile carries an NKP artifact")
                }
                null
            } else {
                val profileId = requiredNonBlankString(
                    profile["profile_id"], "shipping profile $index.profile_id"
                )
                val packBinding = requiredNonBlankString(
                    profile["pack_binding"], "shipping profile $profileId.pack_binding"
                )
                if (profile["conversion_binding"] != null
                    || profile["conversion_artifact"] != null
                ) {
                    throw GradleException("NKP profile carries a conversion artifact")
                }
                val artifact = profile["pack_artifact"] as? Map<*, *>
                    ?: throw GradleException(
                        "Selectable profile $profileId has no exact pack artifact"
                    )
                val merged = LinkedHashMap<Any?, Any?>(artifact)
                merged["profile_id"] = profileId
                merged["lookup_kind"] = lookupKind
                val validation = artifact["validation"] as? Map<*, *>
                    ?: throw GradleException("Pack artifact validation must be an object")
                merged["validation_query"] = validation["query"]
                merged["validation_expected_surface"] = validation["expected_surface"]
                merged["benchmark_queries"] = validation["benchmark_queries"]
                val binding = decodeBindingObject(
                    merged, "shipping profile $profileId pack artifact"
                )
                if (binding.packId != packBinding
                    || binding.outputScript != profile["output_script"]
                ) {
                    throw GradleException("Pack artifact does not match profile $profileId")
                }
                binding
            }
        }
        val expectedPackProfiles = profiles.count { value ->
            val profile = value as Map<*, *>
            profile["selectable"] == true && profile["lookup_kind"] != "conversion"
        }
        if (bindings.size != expectedPackProfiles) {
            throw GradleException("Shipping-profile pack binding count is inconsistent")
        }
        return bindings
    }

    private fun decodeBindingObject(row: Map<*, *>, location: String): ReleasePackBinding {
        val validationQueries = row["benchmark_queries"] as? List<*>
            ?: throw GradleException("$location benchmark_queries must be an array")
        val binding = ReleasePackBinding(
            requiredNonBlankString(row["profile_id"], "$location.profile_id"),
            requiredNonBlankString(row["pack_id"], "$location.pack_id"),
            requiredNonBlankString(row["file_name"], "$location.file_name"),
            requiredNonBlankString(row["artifact_sha256"], "$location.artifact_sha256"),
            requiredNonBlankString(row["language"], "$location.language"),
            requiredNonBlankString(row["output_script"], "$location.output_script"),
            requiredNonBlankString(row["artifact_license"], "$location.artifact_license"),
            requiredExactInt(row["candidate_count"], "$location.candidate_count"),
            requiredExactInt(row["surface_key_count"], "$location.surface_key_count"),
            requiredExactInt(row["alias_key_count"], "$location.alias_key_count"),
            requiredNonBlankString(row["lookup_kind"], "$location.lookup_kind"),
            requiredNonBlankString(row["validation_query"], "$location.validation_query"),
            requiredNonBlankString(
                row["validation_expected_surface"], "$location.validation_expected_surface"
            ),
            validationQueries.mapIndexed { index, value ->
                requiredNonBlankString(value, "$location.benchmark_queries[$index]")
            },
            (row["release_mode"] as? String)?.takeIf(String::isNotBlank),
        )
        validateBinding(binding)
        return binding
    }

    private fun validateBinding(binding: ReleasePackBinding) {
        val safeId = Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
        if (!binding.profileId.matches(safeId)
            || !binding.packId.matches(safeId)
            || !binding.language.matches(Regex("[a-z]{3}"))
            || !binding.outputScript.matches(Regex("[A-Z][a-z]{3}"))
            || !binding.fileName.matches(Regex("[A-Za-z0-9._-]+\\.nkp"))
            || !binding.artifactSha256.matches(Regex("[0-9a-f]{64}"))
            || !binding.artifactLicense.matches(Regex("[A-Za-z0-9][A-Za-z0-9.+-]{0,63}"))
            || binding.candidateCount < 1
            || binding.surfaceKeyCount < 0
            || binding.aliasKeyCount < 0
            || binding.lookupKind !in setOf("surface_prefix", "alias_prefix")
            || (binding.lookupKind == "surface_prefix" && binding.surfaceKeyCount < 1)
            || (binding.lookupKind == "alias_prefix" && binding.aliasKeyCount < 1)
            || binding.validationQuery.isBlank()
            || binding.validationExpectedSurface.isBlank()
            || binding.benchmarkQueries.isEmpty()
            || binding.benchmarkQueries.size > 64
            || (binding.releaseMode != null
                && binding.releaseMode !in setOf("release", "internal"))
        ) {
            throw GradleException("Invalid configured pack binding metadata")
        }
    }

    private fun artifactIdentity(binding: ReleasePackBinding): String = listOf(
        binding.packId,
        binding.fileName,
        binding.artifactSha256,
        binding.language,
        binding.outputScript,
        binding.artifactLicense,
        binding.candidateCount,
        binding.surfaceKeyCount,
        binding.aliasKeyCount,
        binding.releaseMode ?: "release",
    ).joinToString("|")

    private fun requiredNonBlankString(value: Any?, location: String): String {
        val string = value as? String
        if (string.isNullOrBlank()) {
            throw GradleException("$location must be a non-empty string")
        }
        return string
    }

    private fun requiredExactInt(value: Any?, location: String): Int {
        val exact = when (value) {
            is Byte -> value.toInt()
            is Short -> value.toInt()
            is Int -> value
            is Long -> value.takeIf { it in Int.MIN_VALUE..Int.MAX_VALUE }?.toInt()
            is java.math.BigInteger -> try {
                value.intValueExact()
            } catch (_: ArithmeticException) {
                null
            }
            else -> null
        }
        return exact ?: throw GradleException("$location must be an exact 32-bit integer")
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        FileInputStream(file).use { input ->
            val buffer = ByteArray(16 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read == -1) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { byte ->
            String.format(Locale.ROOT, "%02x", byte.toInt() and 0xff)
        }
    }

    private fun verifyNkpManifest(
        file: File,
        binding: ReleasePackBinding,
        acceptedReleaseMode: String,
        enforceRedistributionApproval: Boolean,
    ) {
        ZipFile(file).use { archive ->
            val entries = Collections.list(archive.entries())
            val entryNames = entries.map(ZipEntry::getName)
            if (entryNames.size != entryNames.toSet().size
                || entryNames.toSet() != REQUIRED_ARCHIVE_ENTRIES
                || entries.any { it.isDirectory || it.method != ZipEntry.STORED }
            ) {
                throw GradleException(
                    "NKP archive entries must be the exact ZIP-STORE v0 allowlist: ${binding.fileName}"
                )
            }

            val entry = archive.getEntry("manifest.json")
                ?: throw GradleException("NKP is missing manifest.json: ${binding.fileName}")
            if (entry.isDirectory
                || entry.size <= 0L
                || entry.size > MAX_NKP_MANIFEST_BYTES.toLong()
            ) {
                throw GradleException("NKP manifest size is invalid: ${binding.fileName}")
            }
            val encoded = readBoundedEntry(archive, entry, MAX_NKP_MANIFEST_BYTES)
            if (encoded.size > MAX_NKP_MANIFEST_BYTES) {
                throw GradleException("NKP manifest exceeds size limit: ${binding.fileName}")
            }
            val manifest = parseJsonObject(encoded, "manifest.json", binding)
            val pack = requiredObject(manifest, "pack", "manifest.json", binding)
            val counts = requiredObject(manifest, "counts", "manifest.json", binding)
            val indexes = requiredObject(manifest, "indexes", "manifest.json", binding)
            val members = requiredObject(manifest, "members", "manifest.json", binding)
            if (requiredExactInt(manifest["format_version"], "manifest.format_version") != 0
                || manifest["release_mode"] != acceptedReleaseMode
            ) {
                throw GradleException(
                    "NKP release mode does not match the staging lane: ${binding.fileName}"
                )
            }
            if (pack["pack_id"] != binding.packId
                || pack["language"] != binding.language
                || pack["output_script"] != binding.outputScript
                || pack["artifact_license"] != binding.artifactLicense
                || requiredExactInt(
                    counts["candidate_surfaces"], "manifest.counts.candidate_surfaces"
                ) != binding.candidateCount
            ) {
                throw GradleException("NKP pack/profile metadata mismatch: ${binding.fileName}")
            }
            val surfaceIndex = requiredObject(indexes, "surface", "manifest.indexes", binding)
            val aliasIndex = requiredObject(indexes, "aliases", "manifest.indexes", binding)
            if (requiredExactInt(surfaceIndex["keys"], "manifest.indexes.surface.keys")
                    != binding.surfaceKeyCount
                || requiredExactInt(aliasIndex["keys"], "manifest.indexes.aliases.keys")
                    != binding.aliasKeyCount
            ) {
                throw GradleException("NKP lookup-index counts mismatch: ${binding.fileName}")
            }
            if (members.keys.map { it as? String }.toSet() != REQUIRED_NKP_MEMBERS) {
                throw GradleException("NKP member manifest is not the exact v0 allowlist")
            }
            for (memberName in REQUIRED_NKP_MEMBERS) {
                val metadata = requiredObject(
                    members,
                    memberName,
                    "manifest.members",
                    binding,
                )
                val expectedBytes = requiredExactInt(
                    metadata["bytes"],
                    "manifest.members.$memberName.bytes",
                ).toLong()
                val expectedSha256 = metadata["sha256"] as? String
                    ?: throw GradleException("NKP member has no SHA-256: $memberName")
                val memberEntry = archive.getEntry(memberName)
                    ?: throw GradleException("NKP member is missing: $memberName")
                if (expectedBytes < 0L
                    || expectedBytes > MAX_NKP_MEMBER_BYTES.toLong()
                    || memberEntry.size != expectedBytes
                    || !expectedSha256.matches(Regex("[0-9a-f]{64}"))
                ) {
                    throw GradleException("NKP member metadata is invalid: $memberName")
                }
                val memberBytes = readBoundedEntry(
                    archive,
                    memberEntry,
                    MAX_NKP_MEMBER_BYTES,
                )
                if (memberBytes.size.toLong() != expectedBytes
                    || sha256(memberBytes) != expectedSha256
                ) {
                    throw GradleException("NKP member verification failed: $memberName")
                }
            }

            val notices = parseJsonObject(
                readBoundedEntry(
                    archive,
                    archive.getEntry("notices.json"),
                    MAX_NKP_MEMBER_BYTES,
                ),
                "notices.json",
                binding,
            )
            val sources = notices["sources"] as? List<*>
            if (notices["release_mode"] != acceptedReleaseMode || sources.isNullOrEmpty()) {
                throw GradleException("NKP notices do not match the staging lane")
            }
            for (sourceValue in sources) {
                val source = sourceValue as? Map<*, *>
                    ?: throw GradleException("NKP notice source is not an object")
                for (field in listOf(
                    "source_id",
                    "title",
                    "method",
                    "license",
                    "redistribution",
                )) {
                    val value = source[field] as? String
                    if (value.isNullOrBlank()) {
                        throw GradleException(
                            "NKP source is missing required provenance field: $field"
                        )
                    }
                }
                if (enforceRedistributionApproval) {
                    if (source["redistribution"] != "allowed") {
                        throw GradleException("NKP source is not approved for redistribution")
                    }
                    for (field in listOf(
                        "source_id",
                        "license",
                        "source_url",
                        "license_url",
                        "license_notice",
                    )) {
                        val value = source[field] as? String
                        if (value.isNullOrBlank()) {
                            throw GradleException(
                                "NKP source is missing required notice field: $field"
                            )
                        }
                    }
                }
            }
        }
    }

    private fun parseJsonObject(
        encoded: ByteArray,
        name: String,
        binding: ReleasePackBinding,
    ): Map<*, *> {
        val parsed = try {
            JsonSlurper().parseText(String(encoded, StandardCharsets.UTF_8))
        } catch (failure: RuntimeException) {
            throw GradleException("NKP $name is invalid JSON: ${binding.fileName}", failure)
        }
        return parsed as? Map<*, *>
            ?: throw GradleException("NKP $name is not an object: ${binding.fileName}")
    }

    private fun requiredObject(
        parent: Map<*, *>,
        field: String,
        location: String,
        binding: ReleasePackBinding,
    ): Map<*, *> = parent[field] as? Map<*, *>
        ?: throw GradleException(
            "NKP $location.$field is not an object: ${binding.fileName}"
        )

    private fun readBoundedEntry(
        archive: ZipFile,
        entry: ZipEntry?,
        maximumBytes: Int,
    ): ByteArray {
        if (entry == null
            || entry.isDirectory
            || entry.size < 0L
            || entry.size > maximumBytes.toLong()
        ) {
            throw GradleException("NKP archive entry is missing or outside its size limit")
        }
        val encoded = archive.getInputStream(entry).use { input ->
            input.readNBytes(maximumBytes + 1)
        }
        if (encoded.size > maximumBytes) {
            throw GradleException("NKP archive entry exceeds its size limit")
        }
        return encoded
    }

    private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { byte ->
            String.format(Locale.ROOT, "%02x", byte.toInt() and 0xff)
        }

    protected abstract fun acceptedReleaseMode(releaseMode: String?): String

    protected abstract fun enforceRedistributionApproval(): Boolean
}

/** Public/export staging authority; its release mode cannot be configured. */
abstract class StageExternalReleasePacks : StageExternalPackStager() {
    final override fun acceptedReleaseMode(releaseMode: String?): String {
        if (releaseMode != null && releaseMode != "release") {
            throw GradleException("Public/export staging accepts only release-mode bindings")
        }
        return "release"
    }

    final override fun enforceRedistributionApproval(): Boolean = true
}

/** Internal staging authority; this task can never emit public/export assets. */
abstract class StageExternalInternalPacks : StageExternalPackStager() {
    final override fun acceptedReleaseMode(releaseMode: String?): String =
        releaseMode
            ?: throw GradleException("Internal pack bindings must declare release_mode")

    final override fun enforceRedistributionApproval(): Boolean = false
}

@DisableCachingByDefault(
    because = "Canonical conversion maps must be verified from exact external files"
)
abstract class StageExternalConversionMaps : DefaultTask() {
    companion object {
        private const val MAX_MAP_BYTES = 256L * 1024L
        private const val MAX_RULES = 1024
        private val ROOT_FIELDS = listOf(
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
            "unmapped_policy",
        )
        private val ARTIFACT_FIELDS = setOf(
            "converter_id",
            "file_name",
            "artifact_sha256",
            "language",
            "source_script",
            "output_script",
            "release_mode",
            "rule_count",
            "validation",
        )
    }

    @get:Input
    abstract val sourceDirectoryPath: Property<String>

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val profileLockFile: RegularFileProperty

    @get:Input
    abstract val profileLockSha256: Property<String>

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun stage() {
        val lockFile = profileLockFile.get().asFile
        if (Files.isSymbolicLink(lockFile.toPath())
            || sha256(lockFile) != profileLockSha256.get()
        ) {
            throw GradleException("Conversion staging profile lock is not reviewed")
        }
        val lock = try {
            JsonSlurper().parseText(
                lockFile.readText(StandardCharsets.UTF_8)
            ) as? Map<*, *>
        } catch (failure: RuntimeException) {
            throw GradleException("Conversion staging profile lock is invalid JSON", failure)
        } ?: throw GradleException("Conversion staging profile lock must be an object")
        val lockVersion = requiredExactInt(
            lock["lock_version"],
            "conversion staging lock version",
        )
        val generatorVersion = requiredExactInt(
            lock["generator_version"],
            "conversion staging generator version",
        )
        if (lockVersion !in 1..2
            || generatorVersion != lockVersion
            || lock["generator"] != "build_shipping_profile_catalog"
        ) {
            throw GradleException("Conversion staging profile lock version is unsupported")
        }
        val review = lock["review"] as? Map<*, *>
            ?: throw GradleException("Conversion staging profile lock has no review")
        val authority = requiredString(
            review["authority"],
            "conversion staging review authority",
        )
        if (authority != "release" && authority != "internal") {
            throw GradleException("Conversion staging review authority is invalid")
        }
        val profiles = lock["profiles"] as? List<*>
            ?: throw GradleException("Conversion staging profile lock has no profiles")
        val bindings = profiles.mapIndexedNotNull { index, value ->
            val profile = value as? Map<*, *>
                ?: throw GradleException("Shipping profile $index must be an object")
            val selectable = profile["selectable"] as? Boolean
                ?: throw GradleException("Shipping profile $index selectable must be boolean")
            val conversionArtifact = profile["conversion_artifact"]
            val conversionProfile = profile["lookup_kind"] == "conversion"
                    || profile["engine_kind"] == "converter"
            if (!selectable) {
                if (conversionArtifact != null || profile["conversion_binding"] != null) {
                    throw GradleException("Blocked profile carries a conversion artifact")
                }
                null
            } else if (!conversionProfile) {
                if (conversionArtifact != null || profile["conversion_binding"] != null) {
                    throw GradleException("Non-conversion profile carries a conversion artifact")
                }
                null
            } else {
                if (profile["pack_binding"] != null || profile["pack_artifact"] != null) {
                    throw GradleException("Conversion profile carries an NKP artifact")
                }
                decodeBinding(profile, authority)
            }
        }

        if (bindings.map { it.profileId }.toSet().size != bindings.size) {
            throw GradleException("Conversion bindings repeat a profile")
        }
        for (groups in listOf(
            bindings.groupBy { it.converterId },
            bindings.groupBy { it.fileName },
        )) {
            if (groups.values.any { rows ->
                    rows.map(::artifactIdentity).toSet().size != 1
                }
            ) {
                throw GradleException("Conversion bindings contain conflicting artifact reuse")
            }
        }

        val outputRoot = outputDirectory.get().asFile
        if (outputRoot.exists() && !outputRoot.deleteRecursively()) {
            throw GradleException("Could not clear generated conversion-map assets")
        }
        if (!outputRoot.mkdirs() && !outputRoot.isDirectory) {
            throw GradleException("Could not create generated conversion-map root")
        }
        if (bindings.isEmpty()) {
            return
        }

        val configuredDirectory = sourceDirectoryPath.orNull?.takeIf(String::isNotBlank)
            ?: throw GradleException("Selectable conversions require an external map directory")
        val sourceDirectory = File(configuredDirectory)
        if (Files.isSymbolicLink(sourceDirectory.toPath()) || !sourceDirectory.isDirectory) {
            throw GradleException("External conversion-map directory is invalid")
        }
        val assetDirectory = File(outputRoot, "nepa-conversions")
        if (!assetDirectory.mkdirs() && !assetDirectory.isDirectory) {
            throw GradleException("Could not create conversion-map asset directory")
        }

        try {
            val unique = bindings.distinctBy(::artifactIdentity)
            for (binding in unique) {
                val source = File(sourceDirectory, binding.fileName)
                if (!Files.isRegularFile(source.toPath(), LinkOption.NOFOLLOW_LINKS)
                    || source.length() <= 0L
                    || source.length() > MAX_MAP_BYTES
                ) {
                    throw GradleException("Missing or oversized conversion map: ${binding.fileName}")
                }
                val staged = File(assetDirectory, binding.fileName)
                Files.copy(
                    source.toPath(),
                    staged.toPath(),
                    StandardCopyOption.REPLACE_EXISTING,
                )
                if (sha256(staged) != binding.artifactSha256) {
                    throw GradleException("Conversion-map SHA-256 mismatch: ${binding.fileName}")
                }
                verifyCanonicalNcm(staged, binding)
            }

            File(assetDirectory, "manifest.json").writeText(
                JsonOutput.toJson(linkedMapOf<String, Any>(
                    "conversions" to bindings.map { binding ->
                        linkedMapOf<String, String>(
                            "profile_id" to binding.profileId,
                            "converter_id" to binding.converterId,
                            "asset_path" to "nepa-conversions/${binding.fileName}",
                            "artifact_sha256" to binding.artifactSha256,
                        )
                    },
                )) + "\n",
                StandardCharsets.UTF_8,
            )
            File(assetDirectory, "benchmark-vectors.json").writeText(
                JsonOutput.toJson(linkedMapOf<String, Any>(
                    "bindings" to bindings.map { binding ->
                        linkedMapOf<String, Any>(
                            "profile_id" to binding.profileId,
                            "converter_id" to binding.converterId,
                            "asset_path" to "nepa-conversions/${binding.fileName}",
                            "artifact_sha256" to binding.artifactSha256,
                            "language" to binding.language,
                            "source_script" to binding.sourceScript,
                            "output_script" to binding.outputScript,
                            "release_mode" to binding.releaseMode,
                            "rule_count" to binding.ruleCount,
                            "vectors" to binding.vectors.map { vector ->
                                linkedMapOf<String, Any?>(
                                    "input" to vector.input,
                                    "expected_status" to vector.expectedStatus,
                                    "expected_output" to vector.expectedOutput,
                                )
                            },
                        )
                    },
                )) + "\n",
                StandardCharsets.UTF_8,
            )
        } catch (failure: Exception) {
            outputRoot.deleteRecursively()
            throw failure
        }
    }

    private fun decodeBinding(
        profile: Map<*, *>,
        authority: String,
    ): ConversionMapBinding {
        val profileId = requiredString(profile["profile_id"], "conversion profile ID")
        val bindingId = requiredString(
            profile["conversion_binding"],
            "profile $profileId conversion binding",
        )
        val artifact = profile["conversion_artifact"] as? Map<*, *>
            ?: throw GradleException("Selectable conversion $profileId has no artifact")
        if (artifact.keys.map { it as? String }.toSet() != ARTIFACT_FIELDS) {
            throw GradleException("Conversion artifact $profileId has unexpected fields")
        }
        val converterId = requiredString(
            artifact["converter_id"],
            "profile $profileId converter ID",
        )
        val fileName = requiredString(artifact["file_name"], "profile $profileId file name")
        val language = requiredString(artifact["language"], "profile $profileId language")
        val sourceScript = requiredString(
            artifact["source_script"],
            "profile $profileId source script",
        )
        val outputScript = requiredString(
            artifact["output_script"],
            "profile $profileId output script",
        )
        val releaseMode = requiredString(
            artifact["release_mode"],
            "profile $profileId conversion release mode",
        )
        val validation = artifact["validation"] as? Map<*, *>
            ?: throw GradleException("Conversion artifact $profileId has no validation")
        if (validation.keys.map { it as? String }.toSet() != setOf("vectors")) {
            throw GradleException("Conversion validation $profileId has unexpected fields")
        }
        val rows = validation["vectors"] as? List<*>
            ?: throw GradleException("Conversion validation $profileId vectors must be an array")
        if (rows.size !in 2..64) {
            throw GradleException("Conversion validation $profileId needs 2..64 vectors")
        }
        val vectors = rows.mapIndexed { index, value ->
            val row = value as? Map<*, *>
                ?: throw GradleException("Conversion vector $profileId[$index] must be an object")
            if (row.keys.map { it as? String }.toSet()
                != setOf("input", "expected_status", "expected_output")
            ) {
                throw GradleException("Conversion vector $profileId[$index] has unexpected fields")
            }
            val expectedStatus = requiredString(
                row["expected_status"],
                "conversion vector $profileId[$index] status",
            )
            val expected = row["expected_output"]
            if (expectedStatus == "MATCH"
                && (expected !is String || expected.isEmpty())
            ) {
                throw GradleException("Conversion vector $profileId[$index] output is invalid")
            }
            if (expectedStatus == "NO_MATCH" && expected != null) {
                throw GradleException("Conversion vector $profileId[$index] must not have output")
            }
            if (expectedStatus != "MATCH" && expectedStatus != "NO_MATCH") {
                throw GradleException("Conversion vector $profileId[$index] status is invalid")
            }
            ConversionMapVector(
                requiredString(row["input"], "conversion vector $profileId[$index] input"),
                expectedStatus,
                expected as? String,
            )
        }
        val ruleCount = requiredExactInt(artifact["rule_count"], "profile $profileId rule count")
        val sha = requiredString(artifact["artifact_sha256"], "profile $profileId SHA-256")
        if (converterId != bindingId
            || profile["source_script"] != sourceScript
            || profile["output_script"] != outputScript
            || !converterId.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}"))
            || !fileName.matches(Regex("[A-Za-z0-9._-]+\\.ncm"))
            || !sha.matches(Regex("[0-9a-f]{64}"))
            || !language.matches(Regex("[a-z]{3}"))
            || sourceScript != "Deva"
            || outputScript != "Newa"
            || releaseMode !in setOf("release", "internal")
            || (authority == "release" && releaseMode != "release")
            || ruleCount !in 1..MAX_RULES
            || vectors.none { it.expectedStatus == "MATCH" }
            || vectors.none { it.expectedStatus == "NO_MATCH" }
        ) {
            throw GradleException("Conversion artifact $profileId metadata is invalid")
        }
        return ConversionMapBinding(
            profileId,
            converterId,
            fileName,
            sha,
            language,
            sourceScript,
            outputScript,
            releaseMode,
            ruleCount,
            vectors,
        )
    }

    private fun verifyCanonicalNcm(file: File, binding: ConversionMapBinding) {
        val encoded = file.readBytes()
        if (encoded.size > MAX_MAP_BYTES
            || encoded.take(3) == listOf(0xef.toByte(), 0xbb.toByte(), 0xbf.toByte())
        ) {
            throw GradleException("NCM must be bounded UTF-8 without BOM")
        }
        val text = try {
            StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(encoded))
                .toString()
        } catch (failure: CharacterCodingException) {
            throw GradleException("NCM must be strict UTF-8", failure)
        }
        val root = try {
            JsonSlurper().parseText(text) as? Map<*, *>
        } catch (failure: RuntimeException) {
            throw GradleException("NCM is invalid JSON", failure)
        } ?: throw GradleException("NCM must be a JSON object")
        if (root.keys.map { it as? String } != ROOT_FIELDS
            || root["format"] != "nepa-conversion-map"
            || requiredExactInt(root["format_version"], "NCM format version") != 1
            || root["converter_id"] != binding.converterId
            || root["language"] != binding.language
            || root["source_script"] != binding.sourceScript
            || root["output_script"] != binding.outputScript
            || root["normalization"] != "NFC"
            || root["algorithm"] != "leftmost-longest-codepoint-v1"
            || root["unmapped_policy"] != "no-match"
            || root["joiner_policy"] != "virama-context-only-v1"
            || requiredExactInt(root["rule_count"], "NCM rule count") != binding.ruleCount
        ) {
            throw GradleException("NCM metadata does not match its exact binding")
        }
        val rules = root["rules"] as? List<*>
            ?: throw GradleException("NCM rules must be an array")
        if (rules.size != binding.ruleCount || rules.any { value ->
                val row = value as? Map<*, *> ?: return@any true
                row.keys.map { it as? String } != listOf("from", "to")
                        || (row["from"] as? String).isNullOrEmpty()
                        || (row["to"] as? String).isNullOrEmpty()
                        || !Normalizer.isNormalized(row["from"] as String, Normalizer.Form.NFC)
                        || !Normalizer.isNormalized(row["to"] as String, Normalizer.Form.NFC)
            }
        ) {
            throw GradleException("NCM rules are invalid")
        }
        val canonicalJson = JsonGenerator.Options()
            .disableUnicodeEscaping()
            .build()
            .toJson(root) + "\n"
        if (!encoded.contentEquals(canonicalJson.toByteArray(StandardCharsets.UTF_8))) {
            throw GradleException("NCM is not canonical JSON")
        }
    }

    private fun artifactIdentity(binding: ConversionMapBinding): String = listOf(
        binding.converterId,
        binding.fileName,
        binding.artifactSha256,
        binding.language,
        binding.sourceScript,
        binding.outputScript,
        binding.releaseMode,
        binding.ruleCount,
    ).joinToString("|")

    private fun requiredString(value: Any?, location: String): String =
        (value as? String)?.takeIf(String::isNotBlank)
            ?: throw GradleException("$location must be a non-empty string")

    private fun requiredExactInt(value: Any?, location: String): Int {
        val exact = when (value) {
            is Byte -> value.toInt()
            is Short -> value.toInt()
            is Int -> value
            is Long -> value.takeIf { it in Int.MIN_VALUE..Int.MAX_VALUE }?.toInt()
            is java.math.BigInteger -> try {
                value.intValueExact()
            } catch (_: ArithmeticException) {
                null
            }
            else -> null
        }
        return exact ?: throw GradleException("$location must be an exact integer")
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        FileInputStream(file).use { input ->
            val buffer = ByteArray(8 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { byte ->
            String.format(Locale.ROOT, "%02x", byte.toInt() and 0xff)
        }
    }
}

android {
    namespace = "com.ampixa.nepakeyboard.ime"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.ampixa.nepakeyboard.ime"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
    }

    signingConfigs {
        if (candidateSigningPropertiesFile.isFile) {
            create("candidate") {
                storeFile = rootProject.file(candidateSigningProperty("storeFile"))
                storePassword = candidateSigningProperty("storePassword")
                keyAlias = candidateSigningProperty("keyAlias")
                keyPassword = candidateSigningProperty("keyPassword")
            }
        }
    }

    buildTypes {
        create("internal") {
            initWith(getByName("debug"))
            applicationIdSuffix = ".internal"
            versionNameSuffix = "-internal"
            isDebuggable = true
            matchingFallbacks += listOf("debug")
        }
        create("candidate") {
            initWith(getByName("release"))
            isDebuggable = false
            matchingFallbacks += listOf("release")
            if (candidateSigningPropertiesFile.isFile) {
                signingConfig = signingConfigs.getByName("candidate")
            }
        }
    }

    sourceSets {
        getByName("debug").java.srcDir("src/decoderContract/java")
        getByName("internal").java.srcDir("src/decoderContract/java")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        abortOnError = true
        checkReleaseBuilds = true
    }
}

dependencies {
    implementation(project(":pack-runtime"))
    implementation(project(":conversion-runtime"))
}

private val verifyCandidateSigningConfiguration = tasks.register(
    "verifyCandidateSigningConfiguration"
) {
    doLast {
        if (!candidateSigningPropertiesFile.isFile) {
            throw GradleException(
                "Create ignored android/keystore.properties from " +
                    "android/keystore.properties.example before building a candidate"
            )
        }
        val configuredStore = rootProject.file(candidateSigningProperty("storeFile"))
        if (!configuredStore.isFile) {
            throw GradleException("Candidate upload keystore does not exist: $configuredStore")
        }
    }
}

tasks.matching { it.name == "assembleCandidate" || it.name == "bundleCandidate" }
    .configureEach {
        dependsOn(verifyCandidateSigningConfiguration)
    }

private val internalProfileLockFile = rootProject.file(
    "../catalog/internal-profiles.lock.json"
)

val generateShippingProfileCatalog = tasks.register<GenerateShippingProfileCatalog>(
    "generateShippingProfileCatalog"
) {
    lockFile.set(rootProject.file("../catalog/shipping-profiles.lock.json"))
    expectedLockSha256.set(
        "0f1b467c102450026a71db3ea639aa840deec050edc6a58382ff73789e4882c7"
    )
    expectedAuthority.set("release")
    compilerFile.set(rootProject.file("../tools/build_shipping_profile_catalog.py"))
    catalogSchemaFile.set(rootProject.file("../schemas/resource-catalog.schema.json"))
    reviewSchemaFile.set(rootProject.file("../schemas/shipping-profile-review.schema.json"))
    lockSchemaFile.set(rootProject.file("../schemas/shipping-profile-lock.schema.json"))
    outputDirectory.set(layout.buildDirectory.dir("generated/shippingProfiles/java"))
    resourceOutputDirectory.set(layout.buildDirectory.dir("generated/shippingProfiles/res"))
}

val generateInternalProfileCatalog = tasks.register<GenerateShippingProfileCatalog>(
    "generateInternalProfileCatalog"
) {
    lockFile.set(internalProfileLockFile)
    expectedLockSha256.set(
        "d3f2a85fea6018f74b81d7374db537faeb9fd7b94f917003291e1db0d1c73a01"
    )
    expectedAuthority.set("internal")
    compilerFile.set(rootProject.file("../tools/build_shipping_profile_catalog.py"))
    catalogSchemaFile.set(rootProject.file("../schemas/resource-catalog.schema.json"))
    reviewSchemaFile.set(rootProject.file("../schemas/shipping-profile-review.schema.json"))
    lockSchemaFile.set(rootProject.file("../schemas/shipping-profile-lock.schema.json"))
    outputDirectory.set(layout.buildDirectory.dir("generated/internalProfiles/java"))
    resourceOutputDirectory.set(layout.buildDirectory.dir("generated/internalProfiles/res"))
}

val generateTransliterationProfiles = tasks.register<GenerateTransliterationProfiles>(
    "generateTransliterationProfiles"
) {
    catalogFile.set(file("src/main/assets/nepa-translit/profiles-v1.json"))
    expectedCatalogSha256.set(
        "a407b687f67bd03d5bbc885395096f89d16ad6a68f1308aca28fdc24aaa2d462"
    )
    expectedProfileLockSha256.set(
        "d3f2a85fea6018f74b81d7374db537faeb9fd7b94f917003291e1db0d1c73a01"
    )
    includeProfiles.set(true)
    outputDirectory.set(layout.buildDirectory.dir("generated/transliterationProfiles/java"))
}

val generateEmptyTransliterationProfiles = tasks.register<GenerateTransliterationProfiles>(
    "generateEmptyTransliterationProfiles"
) {
    catalogFile.set(file("src/main/assets/nepa-translit/profiles-v1.json"))
    expectedCatalogSha256.set(
        "a407b687f67bd03d5bbc885395096f89d16ad6a68f1308aca28fdc24aaa2d462"
    )
    expectedProfileLockSha256.set(
        "d3f2a85fea6018f74b81d7374db537faeb9fd7b94f917003291e1db0d1c73a01"
    )
    includeProfiles.set(false)
    outputDirectory.set(layout.buildDirectory.dir("generated/emptyTransliterationProfiles/java"))
}

val generateLayoutRegistry = tasks.register<GenerateLayoutRegistry>(
    "generateLayoutRegistry"
) {
    layoutLockFile.set(rootProject.file("../layouts/layouts-v1.lock.json"))
    profileLockFile.set(rootProject.file("../catalog/shipping-profiles.lock.json"))
    expectedLayoutLockSha256.set(
        "a076a24314ff64eafe00e32df33fa499ff5ef5d4b0ffdf87c89b3960d453b159"
    )
    expectedProfileLockSha256.set(
        "0f1b467c102450026a71db3ea639aa840deec050edc6a58382ff73789e4882c7"
    )
    expectedAuthority.set("release")
    expectedSourceDirectoryPath.set("layouts/src")
    expectedNoticeDirectoryPath.set("layouts/notices")
    expectedProfileLockPath.set("catalog/shipping-profiles.lock.json")
    sourceDirectory.set(rootProject.layout.projectDirectory.dir("../layouts/src"))
    noticeDirectory.set(rootProject.layout.projectDirectory.dir("../layouts/notices"))
    compilerFile.set(rootProject.file("../tools/build_keyboard_layouts.py"))
    sourceSchemaFile.set(rootProject.file("../schemas/layout-v1.schema.json"))
    lockSchemaFile.set(rootProject.file("../schemas/layout-lock-v1.schema.json"))
    outputDirectory.set(layout.buildDirectory.dir("generated/layoutRegistry/java"))
    assetOutputDirectory.set(layout.buildDirectory.dir("generated/layoutRegistry/assets"))
}

val generateInternalLayoutRegistry = tasks.register<GenerateLayoutRegistry>(
    "generateInternalLayoutRegistry"
) {
    layoutLockFile.set(rootProject.file("../layouts/internal/layouts-v1.lock.json"))
    profileLockFile.set(internalProfileLockFile)
    expectedLayoutLockSha256.set(
        "1bc236e1b71dfc8b29bdcef4a7f8aa8c627fd5a5f6a899f062955338b509d85f"
    )
    expectedProfileLockSha256.set(
        "d3f2a85fea6018f74b81d7374db537faeb9fd7b94f917003291e1db0d1c73a01"
    )
    expectedAuthority.set("internal")
    expectedSourceDirectoryPath.set("layouts/internal/src")
    expectedNoticeDirectoryPath.set("layouts/internal/notices")
    expectedProfileLockPath.set("catalog/internal-profiles.lock.json")
    sourceDirectory.set(rootProject.layout.projectDirectory.dir("../layouts/internal/src"))
    noticeDirectory.set(rootProject.layout.projectDirectory.dir("../layouts/internal/notices"))
    compilerFile.set(rootProject.file("../tools/build_keyboard_layouts.py"))
    sourceSchemaFile.set(rootProject.file("../schemas/layout-v1.schema.json"))
    lockSchemaFile.set(rootProject.file("../schemas/layout-lock-v1.schema.json"))
    outputDirectory.set(layout.buildDirectory.dir("generated/internalLayoutRegistry/java"))
    assetOutputDirectory.set(layout.buildDirectory.dir("generated/internalLayoutRegistry/assets"))
}

private val reviewedProfileLockFile = rootProject.file(
    "../catalog/shipping-profiles.lock.json"
)

// Quality-gated Romanized Nepali is benchmarked through the same release-pack
// verifier, but this binding is never attached to an IME variant. The pack ID
// describes its Devanagari candidate bundle; the profile ID describes the
// distinct Latin-to-Devanagari input method that remains blocked in the lock.
private val romanCandidatePackBindings = listOf(
    ReleasePackBinding(
        profileId = "npi-Latn-Deva-NP",
        packId = "npi-Deva-NP",
        fileName = "npi-Deva-NP.nkp",
        artifactSha256 = "09eb5b7496855c94593dc3b71c47e44221d62c4def2f57b4aa0507e7d6edf05f",
        language = "npi",
        outputScript = "Deva",
        artifactLicense = "CC-BY-SA-4.0",
        candidateCount = 80_969,
        surfaceKeyCount = 80_969,
        aliasKeyCount = 368_164,
        lookupKind = "alias_prefix",
        validationQuery = "nepal",
        validationExpectedSurface = "नेपाल",
        benchmarkQueries = listOf(
            "ne", "nep", "nepal", "nam", "namaste", "ghar", "sik",
            "bika", "sam", "bhasha", "dhanyabad", "swasthya", "keybo",
        ),
    ),
)
val encodedRomanCandidatePackBindings =
    romanCandidatePackBindings.map(ReleasePackBinding::encoded)

val releasePackDirectory = providers.gradleProperty("nepaReleasePackDir").map { configured ->
    rootProject.file(configured).absolutePath
}
val stageReleaseExternalPacks = tasks.register<StageExternalReleasePacks>(
    "stageReleaseExternalPacks"
) {
    sourceDirectoryPath.set(releasePackDirectory.orElse(""))
    bindingRows.set(emptyList())
    expectedProfileLockSha256.set(
        "0f1b467c102450026a71db3ea639aa840deec050edc6a58382ff73789e4882c7"
    )
    profileLockFile.set(reviewedProfileLockFile)
    outputDirectory.set(layout.buildDirectory.dir("generated/nepaReleasePacks/release/assets"))
    outputs.upToDateWhen { false }
}

val debugPackDirectory = providers.gradleProperty("nepaDebugPackDir").map { configured ->
    rootProject.file(configured).absolutePath
}
val stageDebugExternalPacks = tasks.register<StageExternalReleasePacks>(
    "stageDebugExternalPacks"
) {
    sourceDirectoryPath.set(debugPackDirectory.orElse(""))
    bindingRows.set(emptyList())
    expectedProfileLockSha256.set(
        "0f1b467c102450026a71db3ea639aa840deec050edc6a58382ff73789e4882c7"
    )
    profileLockFile.set(reviewedProfileLockFile)
    outputDirectory.set(layout.buildDirectory.dir("generated/nepaReleasePacks/debug/assets"))
    outputs.upToDateWhen { false }
}

val romanCandidatePackDirectory = providers.gradleProperty(
    "nepaRomanCandidatePackDir"
).map { configured ->
    rootProject.file(configured).absolutePath
}
val stageRomanCandidateExternalPack = tasks.register<StageExternalReleasePacks>(
    "stageRomanCandidateExternalPack"
) {
    sourceDirectoryPath.set(romanCandidatePackDirectory.orElse(""))
    bindingRows.set(encodedRomanCandidatePackBindings)
    outputDirectory.set(
        layout.buildDirectory.dir("generated/nepaRomanCandidatePacks/debug/assets")
    )
    outputs.upToDateWhen { false }
}

val internalPackDirectory = providers.gradleProperty("nepaInternalPackDir").map { configured ->
    rootProject.file(configured).absolutePath
}
val stageInternalExternalPacks = tasks.register<StageExternalInternalPacks>(
    "stageInternalExternalPacks"
) {
    sourceDirectoryPath.set(internalPackDirectory.orElse(""))
    bindingRows.set(emptyList())
    expectedProfileLockSha256.set(
        "d3f2a85fea6018f74b81d7374db537faeb9fd7b94f917003291e1db0d1c73a01"
    )
    profileLockFile.set(internalProfileLockFile)
    outputDirectory.set(layout.buildDirectory.dir("generated/nepaInternalPacks/internal/assets"))
    outputs.upToDateWhen { false }
}

val stageReleaseExternalConversionMaps = tasks.register<StageExternalConversionMaps>(
    "stageReleaseExternalConversionMaps"
) {
    sourceDirectoryPath.set(releasePackDirectory.orElse(""))
    profileLockFile.set(reviewedProfileLockFile)
    profileLockSha256.set(
        generateShippingProfileCatalog.flatMap { it.expectedLockSha256 }
    )
    outputDirectory.set(
        layout.buildDirectory.dir("generated/nepaReleaseConversions/release/assets")
    )
    outputs.upToDateWhen { false }
}

val stageDebugExternalConversionMaps = tasks.register<StageExternalConversionMaps>(
    "stageDebugExternalConversionMaps"
) {
    sourceDirectoryPath.set(debugPackDirectory.orElse(""))
    profileLockFile.set(reviewedProfileLockFile)
    profileLockSha256.set(
        generateShippingProfileCatalog.flatMap { it.expectedLockSha256 }
    )
    outputDirectory.set(
        layout.buildDirectory.dir("generated/nepaReleaseConversions/debug/assets")
    )
    outputs.upToDateWhen { false }
}

val stageInternalExternalConversionMaps = tasks.register<StageExternalConversionMaps>(
    "stageInternalExternalConversionMaps"
) {
    sourceDirectoryPath.set(internalPackDirectory.orElse(""))
    profileLockFile.set(internalProfileLockFile)
    profileLockSha256.set(
        generateInternalProfileCatalog.flatMap { it.expectedLockSha256 }
    )
    outputDirectory.set(
        layout.buildDirectory.dir("generated/nepaInternalConversions/internal/assets")
    )
    outputs.upToDateWhen { false }
}

androidComponents {
    onVariants(selector().withBuildType("release")) { variant ->
        variant.sources.java?.addGeneratedSourceDirectory(
            generateEmptyTransliterationProfiles,
            GenerateTransliterationProfiles::outputDirectory,
        )
        variant.sources.java?.addGeneratedSourceDirectory(
            generateShippingProfileCatalog,
            GenerateShippingProfileCatalog::outputDirectory,
        )
        variant.sources.res?.addGeneratedSourceDirectory(
            generateShippingProfileCatalog,
            GenerateShippingProfileCatalog::resourceOutputDirectory,
        )
        variant.sources.java?.addGeneratedSourceDirectory(
            generateLayoutRegistry,
            GenerateLayoutRegistry::outputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            generateLayoutRegistry,
            GenerateLayoutRegistry::assetOutputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            stageReleaseExternalPacks,
            StageExternalReleasePacks::outputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            stageReleaseExternalConversionMaps,
            StageExternalConversionMaps::outputDirectory,
        )
    }
    onVariants(selector().withBuildType("debug")) { variant ->
        variant.sources.java?.addGeneratedSourceDirectory(
            generateEmptyTransliterationProfiles,
            GenerateTransliterationProfiles::outputDirectory,
        )
        variant.sources.java?.addGeneratedSourceDirectory(
            generateShippingProfileCatalog,
            GenerateShippingProfileCatalog::outputDirectory,
        )
        variant.sources.res?.addGeneratedSourceDirectory(
            generateShippingProfileCatalog,
            GenerateShippingProfileCatalog::resourceOutputDirectory,
        )
        variant.sources.java?.addGeneratedSourceDirectory(
            generateLayoutRegistry,
            GenerateLayoutRegistry::outputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            generateLayoutRegistry,
            GenerateLayoutRegistry::assetOutputDirectory,
        )
        if (debugPackDirectory.isPresent) {
            variant.sources.assets?.addGeneratedSourceDirectory(
                stageDebugExternalPacks,
                StageExternalReleasePacks::outputDirectory,
            )
        }
        variant.sources.assets?.addGeneratedSourceDirectory(
            stageDebugExternalConversionMaps,
            StageExternalConversionMaps::outputDirectory,
        )
    }
    onVariants(selector().withBuildType("internal")) { variant ->
        variant.sources.java?.addGeneratedSourceDirectory(
            generateInternalProfileCatalog,
            GenerateShippingProfileCatalog::outputDirectory,
        )
        variant.sources.res?.addGeneratedSourceDirectory(
            generateInternalProfileCatalog,
            GenerateShippingProfileCatalog::resourceOutputDirectory,
        )
        variant.sources.java?.addGeneratedSourceDirectory(
            generateInternalLayoutRegistry,
            GenerateLayoutRegistry::outputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            generateInternalLayoutRegistry,
            GenerateLayoutRegistry::assetOutputDirectory,
        )
        variant.sources.java?.addGeneratedSourceDirectory(
            generateTransliterationProfiles,
            GenerateTransliterationProfiles::outputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            stageInternalExternalPacks,
            StageExternalInternalPacks::outputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            stageInternalExternalConversionMaps,
            StageExternalConversionMaps::outputDirectory,
        )
    }
    // A non-debuggable Play candidate for the full internal product. It keeps
    // the base package ID and uses the same internal catalogs exercised by the
    // emulator validation lane, while the public/export release lane remains
    // independently isolated above.
    onVariants(selector().withBuildType("candidate")) { variant ->
        variant.sources.java?.addGeneratedSourceDirectory(
            generateInternalProfileCatalog,
            GenerateShippingProfileCatalog::outputDirectory,
        )
        variant.sources.res?.addGeneratedSourceDirectory(
            generateInternalProfileCatalog,
            GenerateShippingProfileCatalog::resourceOutputDirectory,
        )
        variant.sources.java?.addGeneratedSourceDirectory(
            generateInternalLayoutRegistry,
            GenerateLayoutRegistry::outputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            generateInternalLayoutRegistry,
            GenerateLayoutRegistry::assetOutputDirectory,
        )
        variant.sources.java?.addGeneratedSourceDirectory(
            generateTransliterationProfiles,
            GenerateTransliterationProfiles::outputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            stageInternalExternalPacks,
            StageExternalInternalPacks::outputDirectory,
        )
        variant.sources.assets?.addGeneratedSourceDirectory(
            stageInternalExternalConversionMaps,
            StageExternalConversionMaps::outputDirectory,
        )
    }
}
