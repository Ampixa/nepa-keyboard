plugins {
    id("com.android.application")
}

android {
    namespace = "com.ampixa.nepakeyboard.benchmark"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.ampixa.nepakeyboard.benchmark"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    androidResources {
        noCompress += "nkp"
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

fun registerBenchmarkAssetVerification(
    taskName: String,
    stagedAssetRoot: File,
    stagingTaskPath: String,
) = tasks.register(taskName) {
    dependsOn(stagingTaskPath)
    inputs.dir(stagedAssetRoot)
    doLast {
        val packRoot = stagedAssetRoot.resolve("nepa-packs")
        val manifest = packRoot.resolve("manifest.json")
        val vectors = packRoot.resolve("benchmark-vectors.json")
        val packs = packRoot.listFiles { file ->
            file.isFile && file.extension == "nkp"
        }?.sortedBy(File::getName).orEmpty()
        if (!manifest.isFile || !vectors.isFile || packs.isEmpty()) {
            throw GradleException(
                "Verified benchmark pack assets are missing from $packRoot"
            )
        }
    }
}

fun registerConversionAssetVerification(
    taskName: String,
    stagedAssetRoot: File,
    stagingTaskPath: String,
) = tasks.register(taskName) {
    dependsOn(stagingTaskPath)
    inputs.dir(stagedAssetRoot)
    doLast {
        val conversionRoot = stagedAssetRoot.resolve("nepa-conversions")
        if (!conversionRoot.exists()) {
            return@doLast
        }
        val manifest = conversionRoot.resolve("manifest.json")
        val vectors = conversionRoot.resolve("benchmark-vectors.json")
        val maps = conversionRoot.listFiles { file ->
            file.isFile && file.extension == "ncm"
        }?.sortedBy(File::getName).orEmpty()
        if (!manifest.isFile || !vectors.isFile || maps.isEmpty()) {
            throw GradleException(
                "Verified conversion-map assets are incomplete in $conversionRoot"
            )
        }
    }
}

val hasReleasePacks = providers.gradleProperty("nepaDebugPackDir").isPresent
val hasRomanCandidate = providers.gradleProperty(
    "nepaRomanCandidatePackDir"
).isPresent
val hasInternalPacks = providers.gradleProperty("nepaInternalPackDir").isPresent
if (listOf(hasReleasePacks, hasRomanCandidate, hasInternalPacks).count { it } > 1) {
    throw GradleException(
        "Choose exactly one staged pack lane for one benchmark APK"
    )
}

// The internal catalog can mix proven release foundations with internal packs.
// It reuses the same exact-hash stager and vectors as the internal IME variant.
if (hasInternalPacks) {
    // Consume the explicit output directories declared by the IME staging
    // tasks. These paths are stable across AGP generated-source relocation.
    val stagedInternalPackAssets = project(":ime-app")
        .layout
        .buildDirectory
        .get()
        .dir("generated/nepaInternalPacks/internal/assets")
        .asFile
    val verifyInternalBenchmarkPackAssets = registerBenchmarkAssetVerification(
        "verifyInternalBenchmarkPackAssets",
        stagedInternalPackAssets,
        ":ime-app:stageInternalExternalPacks",
    )
    val stagedInternalConversionAssets = project(":ime-app")
        .layout
        .buildDirectory
        .get()
        .dir("generated/nepaInternalConversions/internal/assets")
        .asFile
    val verifyInternalConversionAssets = registerConversionAssetVerification(
        "verifyInternalConversionAssets",
        stagedInternalConversionAssets,
        ":ime-app:stageInternalExternalConversionMaps",
    )
    android.sourceSets.getByName("main").assets.setSrcDirs(
        listOf(stagedInternalPackAssets, stagedInternalConversionAssets)
    )
    tasks.named("preBuild").configure {
        dependsOn(verifyInternalBenchmarkPackAssets)
        dependsOn(verifyInternalConversionAssets)
    }
}

// Reuse the IME's SHA-pinned staging task so benchmark builds cannot introduce
// a second, less strict artifact-integrity path.
if (hasReleasePacks) {
    val stagedReleasePackAssets = project(":ime-app")
        .layout
        .buildDirectory
        .get()
        .dir("generated/nepaReleasePacks/debug/assets")
        .asFile
    val verifyReleaseBenchmarkPackAssets = registerBenchmarkAssetVerification(
        "verifyReleaseBenchmarkPackAssets",
        stagedReleasePackAssets,
        ":ime-app:stageDebugExternalPacks",
    )
    val stagedReleaseConversionAssets = project(":ime-app")
        .layout
        .buildDirectory
        .get()
        .dir("generated/nepaReleaseConversions/debug/assets")
        .asFile
    val verifyReleaseConversionAssets = registerConversionAssetVerification(
        "verifyReleaseConversionAssets",
        stagedReleaseConversionAssets,
        ":ime-app:stageDebugExternalConversionMaps",
    )
    // A release-pack benchmark replaces the normal asset root, so it cannot
    // carry the separately gated internal pilot used by the legacy harness.
    android.sourceSets.getByName("main").assets.setSrcDirs(
        listOf(stagedReleasePackAssets, stagedReleaseConversionAssets)
    )
    tasks.named("preBuild").configure {
        dependsOn(verifyReleaseBenchmarkPackAssets)
        dependsOn(verifyReleaseConversionAssets)
    }
}


// The quality-gated Roman pack is staged by the same verifier but is never
// included in an IME variant or exposed through the shipping registry.
if (hasRomanCandidate) {
    val stagedRomanCandidateAssets = project(":ime-app")
        .layout
        .buildDirectory
        .get()
        .dir("generated/nepaRomanCandidatePacks/debug/assets")
        .asFile
    val verifyRomanBenchmarkPackAssets = registerBenchmarkAssetVerification(
        "verifyRomanBenchmarkPackAssets",
        stagedRomanCandidateAssets,
        ":ime-app:stageRomanCandidateExternalPack",
    )
    android.sourceSets.getByName("main").assets.setSrcDirs(
        listOf(stagedRomanCandidateAssets)
    )
    tasks.named("preBuild").configure {
        dependsOn(verifyRomanBenchmarkPackAssets)
    }
}
