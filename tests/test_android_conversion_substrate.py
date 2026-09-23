from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class AndroidConversionSubstrateSourceTest(unittest.TestCase):
    def test_conversion_runtime_matches_the_canonical_json_v1_contract(self) -> None:
        runtime = source(
            "android/conversion-runtime/src/main/java/com/ampixa/nepakeyboard/"
            "conversion/NcmBundle.java"
        )
        for marker in (
            'FORMAT = "nepa-conversion-map"',
            "FORMAT_VERSION = 1",
            'NORMALIZATION = "NFC"',
            'ALGORITHM = "leftmost-longest-codepoint-v1"',
            'UNMAPPED_POLICY = "no-match"',
            'JOINER_POLICY = "virama-context-only-v1"',
            "MAX_ARTIFACT_BYTES = 256 * 1024",
            "MAX_RULES = 1024",
            "MAX_SOURCE_CODE_POINTS = 8",
            "MAX_TARGET_CODE_POINTS = 16",
            "Normalizer.isNormalized",
            "conversion map is not canonical JSON",
            "rulesByFirstCodePoint",
            "sourceCodePoints.length",
            "if (match == null)",
            "return null;",
        ):
            self.assertIn(marker, runtime)
        self.assertNotIn("Pattern.compile(rule", runtime)
        self.assertNotIn("ScriptEngine", runtime)

        settings = source("android/settings.gradle.kts")
        ime_build = source("android/ime-app/build.gradle.kts")
        benchmark_build = source("android/benchmark-app/build.gradle.kts")
        self.assertIn('include(":conversion-runtime")', settings)
        self.assertIn('implementation(project(":conversion-runtime"))', ime_build)
        self.assertIn('implementation(project(":conversion-runtime"))', benchmark_build)

    def test_profile_artifact_union_and_registries_are_fail_closed(self) -> None:
        profile = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "KeyboardProfile.java"
        )
        pack_registry = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "ReleasePackRegistry.java"
        )
        conversion_registry = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "ConversionMapRegistry.java"
        )
        union = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionArtifactRegistry.java"
        )
        service = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NepaInputMethodService.java"
        )
        for marker in (
            "enum ArtifactKind",
            "NKP",
            "NCM",
            "public String artifactBinding()",
            "public String conversionBinding()",
        ):
            self.assertIn(marker, profile)
        self.assertIn("profile.artifactKind() == KeyboardProfile.ArtifactKind.NKP", pack_registry)
        self.assertIn('MANIFEST_ASSET = "nepa-conversions/manifest.json"', conversion_registry)
        self.assertIn("profile.artifactKind() != KeyboardProfile.ArtifactKind.NCM", conversion_registry)
        self.assertIn("profileIds.equals(expectedProfileIds)", conversion_registry)
        self.assertIn("if (!actual.add", union)
        self.assertIn("actual.equals(expected)", union)
        self.assertIn("SuggestionArtifactRegistry.installed(this)", service)

    def test_conversion_engine_is_separate_async_and_typed(self) -> None:
        nkp = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NkpSuggestionEngine.java"
        )
        ncm = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "NcmConversionEngine.java"
        )
        router = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "RoutingSuggestionEngine.java"
        )
        candidate = source(
            "android/ime-app/src/main/java/com/ampixa/nepakeyboard/ime/"
            "SuggestionCandidate.java"
        )
        self.assertNotIn("NcmBundle", nkp)
        self.assertNotIn("CONVERSION_PROVIDER", nkp)
        for marker in (
            'CONVERSION_PROVIDER = "ncm-script-conversion-v1"',
            'executor("nepa-conversion-loader"',
            'executor("nepa-conversion-decoder"',
            "new ArrayBlockingQueue<>(1)",
            "query.acceptsProviderResults(System.nanoTime())",
            "SuggestionCandidate.Category.CONVERSION",
            "SuggestionCandidate.literal(query.composingText())",
            "query.activation() == activeActivation",
        ):
            self.assertIn(marker, ncm)
        self.assertIn("profile.artifactKind() == KeyboardProfile.ArtifactKind.NCM", router)
        self.assertIn("activation == activeActivation", router)
        self.assertIn("nkpEngine.close()", router)
        self.assertIn("ncmEngine.close()", router)

        categories = candidate.split("public enum Category {", 1)[1].split("}", 1)[0]
        self.assertLess(categories.index("CORRECTION"), categories.index("CONVERSION"))

    def test_staging_is_separate_and_nkp_vectors_keep_their_shape(self) -> None:
        build = source("android/ime-app/build.gradle.kts")
        self.assertIn("abstract class StageExternalConversionMaps", build)
        self.assertIn('File(outputRoot, "nepa-conversions")', build)
        self.assertIn('"conversions" to bindings.map', build)
        self.assertIn('"vectors" to binding.vectors.map', build)
        self.assertIn("bindings.distinctBy(::artifactIdentity)", build)
        self.assertIn("verifyCanonicalNcm(staged, binding)", build)
        self.assertIn("stageInternalExternalConversionMaps", build)

        benchmark = source(
            "android/benchmark-app/src/main/java/com/ampixa/nepakeyboard/benchmark/"
            "ReleasePrefixBenchmarkInstrumentation.java"
        )
        self.assertIn('VECTOR_ASSET = "nepa-packs/benchmark-vectors.json"', benchmark)
        self.assertNotIn("nepa-conversions", benchmark)

        conversion_benchmark = source(
            "android/benchmark-app/src/main/java/com/ampixa/nepakeyboard/benchmark/"
            "ConversionCatalogBenchmarkInstrumentation.java"
        )
        for marker in (
            'MANIFEST_ASSET = "nepa-conversions/manifest.json"',
            'VECTOR_ASSET = "nepa-conversions/benchmark-vectors.json"',
            "NcmBundle.open(file, vectorCase.sha256)",
            "conversion vectors need success and no-match cases",
            'output.putLong(prefix + "_p95_ns"',
        ):
            self.assertIn(marker, conversion_benchmark)
        self.assertIn(
            "ConversionCatalogBenchmarkInstrumentation",
            source("android/benchmark-app/src/main/AndroidManifest.xml"),
        )

    def test_stager_consumes_the_exact_catalog_v2_conversion_shape(self) -> None:
        build = source("android/ime-app/build.gradle.kts")
        artifact_fields = build.split(
            "private val ARTIFACT_FIELDS = setOf(",
            1,
        )[1].split(")", 1)[0]
        self.assertIn('"converter_id"', artifact_fields)
        self.assertIn('"release_mode"', artifact_fields)
        self.assertNotIn('"conversion_id"', artifact_fields)
        self.assertIn('artifact["converter_id"]', build)
        self.assertNotIn('artifact["conversion_id"]', build)
        self.assertIn(
            'setOf("input", "expected_status", "expected_output")',
            build,
        )
        self.assertIn('row["expected_status"]', build)
        self.assertIn('artifact["release_mode"]', build)

    def test_focused_instrumentation_is_registered_for_debug_and_internal(self) -> None:
        instrumentation = source(
            "android/ime-app/src/decoderContract/java/com/ampixa/nepakeyboard/ime/"
            "NcmConversionInstrumentation.java"
        )
        for marker in (
            "NcmBundle.open(file, sha256)",
            "non-canonical NCM was accepted",
            "leftmost-longest",
            "SuggestionCandidate.Category.CONVERSION",
            "engine.submit(asynchronous",
            "callback ran on the submitting thread",
            "RoutingSuggestionEngine",
            'output.putString("status", "ok")',
            '"\\ud805\\udc0e"',
            '"\\ud805\\udc31"',
            '"\\ud805\\udc42"',
        ):
            self.assertIn(marker, instrumentation)
        self.assertNotIn('"\\ud804\\udc0e"', instrumentation)
        for manifest in (
            "android/ime-app/src/debug/AndroidManifest.xml",
            "android/ime-app/src/internal/AndroidManifest.xml",
        ):
            self.assertIn("NcmConversionInstrumentation", source(manifest))


if __name__ == "__main__":
    unittest.main()
