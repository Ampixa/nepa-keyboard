#!/usr/bin/env python3
"""Finalize deterministic Limbu pack evidence and its internal profile review.

Run this only after two independent adapter and compiler runs. The finalizer
compares the complete adapter outputs and NKPs, verifies every stored member,
executes the chosen surface-prefix queries, writes the evidence report, and
derives the internal review from those exact bytes. It never accepts artifact
hashes, counts, or expected candidates as command-line claims.
"""

from __future__ import annotations

import argparse
import copy
import filecmp
import hashlib
import inspect
import json
import os
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from nepa_keyboard.compiler import PackValidationError, compile_pack
from nepa_keyboard.runtime import KeyboardPack
from tools import build_limbu_internal_source as adapter


PACK_ID = "lif-Limb-NP"
LANGUAGE = "lif"
OUTPUT_SCRIPT = "Limb"
ARTIFACT_LICENSE = "LicenseRef-Internal"
LAYOUT_ID = "limb-nepal-phonetic-v1"
INPUT_METHOD_ID = "lif-limb-direct"
SOURCE_FILES = frozenset({
    "adapter-report.json",
    "aliases.jsonl",
    "forms.jsonl",
    "pack.json",
    "rejected-rows.jsonl",
    "sources.jsonl",
})
PACK_MEMBERS = frozenset({
    "aliases.trie",
    "candidates.bin",
    "manifest.json",
    "notices.json",
    "scores.bin",
    "surface.trie",
})
VERIFIED_MEMBERS = PACK_MEMBERS - {"manifest.json"}
INTERNAL_GATES = frozenset({
    "deterministic_build",
    "internal_pack",
    "layout_implemented",
})
FOUNDATION_PROFILE_IDS = frozenset({"eng-Latn-US", "npi-Deva-NP"})
EXPECTED_FOUNDATION_COUNTS = {
    "targets": 33,
    "profiles": 74,
    "scripts": 9,
    "selectable": 2,
}
REMAINING_GATES = (
    "accessibility_review",
    "glyph_rendering",
    "native_speaker_review",
    "physical_device_runtime",
    "quality_evaluation",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class FinalizeError(ValueError):
    """Raised when milestone evidence is incomplete or inconsistent."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise FinalizeError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise FinalizeError(f"{label} is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FinalizeError(f"{label} must be a JSON object: {path}")
    return value


def _required_object(value: dict[str, Any], key: str, location: str) -> dict[str, Any]:
    child = value.get(key)
    if not isinstance(child, dict):
        raise FinalizeError(f"{location}.{key} must be an object")
    return child


def _required_string(value: dict[str, Any], key: str, location: str) -> str:
    child = value.get(key)
    if not isinstance(child, str) or not child:
        raise FinalizeError(f"{location}.{key} must be a non-empty string")
    return child


def _required_exact_int(value: dict[str, Any], key: str, location: str) -> int:
    child = value.get(key)
    if isinstance(child, bool) or not isinstance(child, int):
        raise FinalizeError(f"{location}.{key} must be an exact integer")
    return child


def _regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise FinalizeError(f"{label} is not a regular file: {path}")


def _require_distinct_paths(first: Path, second: Path, label: str) -> None:
    if first.resolve() == second.resolve():
        raise FinalizeError(f"the two {label} paths must be distinct")
    try:
        same_file = os.path.samefile(first, second)
    except OSError as exc:
        raise FinalizeError(f"cannot compare {label} identities: {exc}") from exc
    if same_file:
        raise FinalizeError(f"the two {label} inputs must not be the same file identity")


def _loaded_compiler_source() -> Path:
    source = inspect.getsourcefile(compile_pack)
    if source is None:
        raise FinalizeError("cannot identify the loaded pack compiler source")
    loaded = Path(source).resolve()
    expected = (REPOSITORY_ROOT / "src/nepa_keyboard/compiler.py").resolve()
    if loaded != expected:
        raise FinalizeError(
            f"loaded pack compiler is not the repository source: {loaded} != {expected}"
        )
    return loaded


def _tree_inventory(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise FinalizeError(f"adapter source is not a regular directory: {root}")
    entries = sorted(root.iterdir(), key=lambda path: path.name)
    names = {path.name for path in entries}
    if names != SOURCE_FILES:
        raise FinalizeError(
            f"adapter source file set mismatch: expected {sorted(SOURCE_FILES)}, "
            f"got {sorted(names)}"
        )
    files: list[dict[str, object]] = []
    for path in entries:
        _regular_file(path, "adapter source member")
        files.append({
            "bytes": path.stat().st_size,
            "path": path.name,
            "sha256": _sha256_file(path),
        })
    tree_payload = {"files": files}
    return {
        "algorithm": "sha256(canonical-json({files:[{bytes,path,sha256},...]}))",
        "files": files,
        "tree_sha256": _sha256_bytes(_canonical_bytes(tree_payload)),
    }


def _verified_pack(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    _regular_file(path, "NKP")
    if path.name != "lif-Limb-NP.nkp":
        raise FinalizeError(f"Limbu NKP has an unexpected file name: {path.name}")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise FinalizeError(f"NKP contains duplicate members: {path}")
            if set(names) != PACK_MEMBERS:
                raise FinalizeError(
                    f"NKP member set mismatch: expected {sorted(PACK_MEMBERS)}, "
                    f"got {sorted(names)}"
                )
            if any(info.is_dir() or info.compress_type != zipfile.ZIP_STORED for info in infos):
                raise FinalizeError(f"NKP members must all be regular ZIP-STORE entries: {path}")
            members = {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise FinalizeError(f"cannot verify NKP {path}: {exc}") from exc

    try:
        manifest = json.loads(members["manifest.json"].decode("utf-8"))
        notices = json.loads(members["notices.json"].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"NKP metadata is not strict UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(notices, dict):
        raise FinalizeError(f"NKP metadata roots must be objects: {path}")
    if _required_exact_int(manifest, "format_version", "manifest") != 0:
        raise FinalizeError("Limbu NKP does not use pack format v0")
    if _required_string(manifest, "release_mode", "manifest") != "internal":
        raise FinalizeError("Limbu NKP is not release_mode=internal")
    if _required_string(notices, "release_mode", "notices") != "internal":
        raise FinalizeError("Limbu notices are not release_mode=internal")

    pack = _required_object(manifest, "pack", "manifest")
    expected_pack = {
        "artifact_license": ARTIFACT_LICENSE,
        "language": LANGUAGE,
        "output_script": OUTPUT_SCRIPT,
        "pack_id": PACK_ID,
    }
    for key, expected in expected_pack.items():
        if _required_string(pack, key, "manifest.pack") != expected:
            raise FinalizeError(f"manifest.pack.{key} does not match {expected!r}")

    declared_members = _required_object(manifest, "members", "manifest")
    if set(declared_members) != VERIFIED_MEMBERS:
        raise FinalizeError("manifest member allowlist does not match pack format v0")
    for name in sorted(VERIFIED_MEMBERS):
        metadata = _required_object(declared_members, name, "manifest.members")
        expected_bytes = _required_exact_int(metadata, "bytes", f"manifest.members.{name}")
        expected_sha256 = _required_string(metadata, "sha256", f"manifest.members.{name}")
        if expected_bytes != len(members[name]):
            raise FinalizeError(f"member byte count mismatch: {name}")
        if not SHA256_RE.fullmatch(expected_sha256):
            raise FinalizeError(f"member SHA-256 is malformed: {name}")
        if expected_sha256 != _sha256_bytes(members[name]):
            raise FinalizeError(f"member SHA-256 mismatch: {name}")

    counts = _required_object(manifest, "counts", "manifest")
    indexes = _required_object(manifest, "indexes", "manifest")
    surface = _required_object(indexes, "surface", "manifest.indexes")
    aliases = _required_object(indexes, "aliases", "manifest.indexes")
    candidate_count = _required_exact_int(counts, "candidate_surfaces", "manifest.counts")
    surface_key_count = _required_exact_int(surface, "keys", "manifest.indexes.surface")
    alias_key_count = _required_exact_int(aliases, "keys", "manifest.indexes.aliases")
    if candidate_count < 1 or surface_key_count < 1 or alias_key_count != 0:
        raise FinalizeError("Limbu direct pack counts are not a non-empty surface-only pack")

    artifact = {
        "artifact_bytes": path.stat().st_size,
        "artifact_sha256": _sha256_file(path),
        "file_name": "lif-Limb-NP.nkp",
    }
    return manifest, artifact


def _normalized_compiler_report(pack_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    report_path = pack_path.with_suffix(pack_path.suffix + ".report.json")
    report = _read_json_object(report_path, "compiler report")
    if report.get("manifest") != manifest:
        raise FinalizeError(f"compiler report manifest does not match NKP: {report_path}")
    if report.get("artifact_sha256") != _sha256_file(pack_path):
        raise FinalizeError(f"compiler report artifact hash does not match NKP: {report_path}")
    if report.get("artifact_bytes") != pack_path.stat().st_size:
        raise FinalizeError(f"compiler report artifact size does not match NKP: {report_path}")
    normalized = copy.deepcopy(report)
    normalized.pop("artifact", None)
    return normalized


def _recompile_and_bind(
    source_a: Path,
    source_b: Path,
    pack_a: Path,
    pack_b: Path,
    compiler_a: dict[str, Any],
    compiler_b: dict[str, Any],
) -> None:
    with tempfile.TemporaryDirectory(prefix="nepa-limbu-finalize-") as temporary:
        root = Path(temporary)
        for label, source, provided_pack, provided_report in (
            ("a", source_a, pack_a, compiler_a),
            ("b", source_b, pack_b, compiler_b),
        ):
            output = root / label / "lif-Limb-NP.nkp"
            try:
                rebuilt_report = compile_pack(source, output, "internal")
            except (OSError, PackValidationError, ValueError) as exc:
                raise FinalizeError(
                    f"current compiler could not rebuild Limbu run {label}: {exc}"
                ) from exc
            if not filecmp.cmp(output, provided_pack, shallow=False):
                raise FinalizeError(
                    f"Limbu run {label} NKP is not derived from its source tree "
                    "by the current compiler"
                )
            normalized = copy.deepcopy(rebuilt_report)
            normalized.pop("artifact", None)
            if normalized != provided_report:
                raise FinalizeError(
                    f"Limbu run {label} compiler report is not derived from its "
                    "source tree by the current compiler"
                )


def _query_selection(path: Path) -> tuple[str, list[str], str]:
    value = _read_json_object(path, "query selection")
    if set(value) != {"benchmark_queries", "validation_query"}:
        raise FinalizeError(
            "query selection must contain exactly validation_query and benchmark_queries"
        )
    validation_query = value["validation_query"]
    benchmark_queries = value["benchmark_queries"]
    if not isinstance(validation_query, str) or not validation_query:
        raise FinalizeError("validation_query must be a non-empty string")
    if not isinstance(benchmark_queries, list) or not 8 <= len(benchmark_queries) <= 12:
        raise FinalizeError("benchmark_queries must contain 8 to 12 strings")
    if any(not isinstance(query, str) or not query for query in benchmark_queries):
        raise FinalizeError("every benchmark query must be a non-empty string")
    if len(set(benchmark_queries)) != len(benchmark_queries):
        raise FinalizeError("benchmark queries must be unique")
    all_queries = [validation_query, *benchmark_queries]
    if any(unicodedata.normalize("NFC", query) != query for query in all_queries):
        raise FinalizeError("all Limbu queries must already be NFC")
    canonical = {
        "benchmark_queries": benchmark_queries,
        "validation_query": validation_query,
    }
    return validation_query, benchmark_queries, _sha256_bytes(_canonical_bytes(canonical))


def _run_queries(
    pack_path: Path,
    validation_query: str,
    benchmark_queries: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    def query(pack: KeyboardPack, prefix: str) -> dict[str, Any]:
        candidates = pack.lookup(prefix, "surface")
        if not candidates:
            raise FinalizeError(f"Limbu query has no candidates: {prefix!r}")
        return {
            "candidates": candidates,
            "expected_first_surface": candidates[0]["surface"],
            "query": prefix,
        }

    with KeyboardPack(pack_path) as pack:
        validation = query(pack, validation_query)
        benchmark = [query(pack, prefix) for prefix in benchmark_queries]
    return validation, benchmark


def _adapter_report(source: Path) -> dict[str, Any]:
    report = _read_json_object(source / "adapter-report.json", "adapter report")
    if report.get("adapter") != "build_limbu_internal_source":
        raise FinalizeError("unexpected Limbu adapter identity")
    if report.get("adapter_version") != 2:
        raise FinalizeError("Limbu adapter report is not version 2")
    adapter_sha256 = _sha256_file(Path(adapter.__file__))
    if report.get("adapter_sha256") != adapter_sha256:
        raise FinalizeError("Limbu adapter report does not pin the current adapter bytes")
    input_row = _required_object(report, "input", "adapter report")
    if input_row.get("sha256") != adapter.LIMDIC_SHA256:
        raise FinalizeError("adapter report input SHA does not match the pinned LimDic")
    if input_row.get("expected_data_rows") != adapter.EXPECTED_DATA_ROWS:
        raise FinalizeError("adapter report row pin does not match the Limbu adapter")
    if report.get("pack_id") != PACK_ID:
        raise FinalizeError("adapter report pack ID does not match Limbu")
    return report


def _build_evidence(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    compiler_source = _loaded_compiler_source()
    tree_a = _tree_inventory(args.source_a)
    tree_b = _tree_inventory(args.source_b)
    if tree_a != tree_b:
        raise FinalizeError("the two Limbu adapter source trees are not byte-identical")
    adapter_a = _adapter_report(args.source_a)
    adapter_b = _adapter_report(args.source_b)
    if adapter_a != adapter_b:
        raise FinalizeError("the two Limbu adapter reports are not identical")

    manifest_a, artifact_a = _verified_pack(args.pack_a)
    manifest_b, artifact_b = _verified_pack(args.pack_b)
    if not filecmp.cmp(args.pack_a, args.pack_b, shallow=False):
        raise FinalizeError("the two Limbu NKPs are not byte-identical")
    if manifest_a != manifest_b or artifact_a != artifact_b:
        raise FinalizeError("the two Limbu NKP identities are inconsistent")

    compiler_a = _normalized_compiler_report(args.pack_a, manifest_a)
    compiler_b = _normalized_compiler_report(args.pack_b, manifest_b)
    if compiler_a != compiler_b:
        raise FinalizeError("normalized Limbu compiler reports are not identical")
    _recompile_and_bind(
        args.source_a,
        args.source_b,
        args.pack_a,
        args.pack_b,
        compiler_a,
        compiler_b,
    )

    validation_query, benchmark_queries, query_sha256 = _query_selection(args.queries)
    validation, benchmark = _run_queries(
        args.pack_a, validation_query, benchmark_queries
    )
    counts = _required_object(manifest_a, "counts", "manifest")
    indexes = _required_object(manifest_a, "indexes", "manifest")
    pack = _required_object(manifest_a, "pack", "manifest")
    evidence = {
        "adapter": adapter_a,
        "compiler": {
            "normalized_report_sha256": _sha256_bytes(_canonical_bytes(compiler_a)),
            "provided_packs_recompiled_from_source": True,
            "source_path": "src/nepa_keyboard/compiler.py",
            "source_sha256": _sha256_file(compiler_source),
        },
        "determinism": {
            "normalized_compiler_reports_identical": True,
            "pack_bytes_identical": True,
            "run_a": {"pack": artifact_a, "source_tree": tree_a},
            "run_b": {"pack": artifact_b, "source_tree": tree_b},
            "source_trees_identical": True,
        },
        "finalizer": {
            "path": "tools/finalize_limbu_internal_milestone.py",
            "sha256": _sha256_file(Path(__file__)),
        },
        "pack": {
            "artifact_license": pack["artifact_license"],
            "artifact_sha256": artifact_a["artifact_sha256"],
            "candidate_count": counts["candidate_surfaces"],
            "file_name": "lif-Limb-NP.nkp",
            "indexes": indexes,
            "language": pack["language"],
            "manifest_members": manifest_a["members"],
            "output_script": pack["output_script"],
            "pack_id": pack["pack_id"],
            "release_mode": manifest_a["release_mode"],
            "source_form_count": counts["source_forms"],
        },
        "queries": {
            "benchmark": benchmark,
            "selection_sha256": query_sha256,
            "validation": validation,
        },
        "remaining_production_gates": list(REMAINING_GATES),
        "report_id": "limbu-internal-pack-v0",
        "report_version": 1,
    }
    return evidence, manifest_a


def _repository_relative(path: Path, repository_root: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(repository_root).as_posix()
    except ValueError as exc:
        raise FinalizeError(f"{label} must be inside the repository: {path}") from exc


def _build_review(
    args: argparse.Namespace,
    evidence: dict[str, Any],
    evidence_bytes: bytes,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    foundation = _read_json_object(args.shipping_review, "shipping review")
    if foundation.get("authority") != "release":
        raise FinalizeError("foundation review is not release authority")
    if foundation.get("expected_counts") != EXPECTED_FOUNDATION_COUNTS:
        raise FinalizeError("foundation review counts drifted from the three-profile milestone")
    foundation_evidence = foundation.get("evidence")
    if not isinstance(foundation_evidence, list) or {
        row.get("profile_id") for row in foundation_evidence if isinstance(row, dict)
    } != FOUNDATION_PROFILE_IDS:
        raise FinalizeError("foundation review does not contain exactly English and Nepali evidence")

    layout = _read_json_object(args.layout_source, "Limbu layout source")
    if layout.get("layout_id") != LAYOUT_ID or layout.get("revision") != 1:
        raise FinalizeError("Limbu layout identity is not the reviewed revision 1 source")
    layout_sha256 = _sha256_file(args.layout_source)
    evidence_path = _repository_relative(
        args.evidence_output, REPOSITORY_ROOT, "evidence output"
    )

    review = copy.deepcopy(foundation)
    review["authority"] = "internal"
    review["review_id"] = f"internal-profiles-{args.reviewed_at}"
    review["reviewed_at"] = args.reviewed_at
    review["expected_counts"]["selectable"] = 3
    review["blocked_reason_by_method"] = {
        "direct": "DIRECT_PROFILE_NOT_INTERNAL_READY",
        "roman_phonetic": "ROMAN_ALIAS_NOT_INTERNAL_READY",
        "script_conversion": "SCRIPT_CONVERTER_NOT_INTERNAL_READY",
    }
    for row in review["evidence"]:
        row["gates"] = sorted(set(row["gates"]) | INTERNAL_GATES)
        binding = _required_object(row, "layout_binding", "foundation evidence")
        layout_id = _required_string(binding, "layout_id", "foundation layout binding")
        internal_layout_source = args.layout_source.parent / f"{layout_id}.json"
        internal_layout = _read_json_object(
            internal_layout_source,
            f"internal foundation layout {layout_id}",
        )
        if internal_layout.get("layout_id") != layout_id:
            raise FinalizeError(f"internal foundation layout ID mismatch: {layout_id}")
        revision = internal_layout.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise FinalizeError(f"internal foundation layout revision is invalid: {layout_id}")
        row["layout_binding"] = {
            "layout_id": layout_id,
            "revision": revision,
            "source_sha256": _sha256_file(internal_layout_source),
        }

    evidence_id = f"lif-direct-internal-{args.reviewed_at}"
    review["profile_overrides"][INPUT_METHOD_ID] = {
        "default_enabled": False,
        "evidence_ids": [evidence_id],
        "layout_id": LAYOUT_ID,
        "pack_binding": PACK_ID,
        "profile_id": PACK_ID,
        "selectable": True,
    }
    counts = _required_object(manifest, "counts", "manifest")
    indexes = _required_object(manifest, "indexes", "manifest")
    surface = _required_object(indexes, "surface", "manifest.indexes")
    aliases = _required_object(indexes, "aliases", "manifest.indexes")
    validation = _required_object(
        _required_object(evidence, "queries", "evidence"),
        "validation",
        "evidence.queries",
    )
    benchmark = evidence["queries"]["benchmark"]
    pack = _required_object(manifest, "pack", "manifest")
    review["evidence"].append({
        "artifacts": [{
            "path": evidence_path,
            "sha256": _sha256_bytes(evidence_bytes),
        }],
        "evidence_id": evidence_id,
        "gates": sorted(INTERNAL_GATES),
        "layout_binding": {
            "layout_id": LAYOUT_ID,
            "revision": 1,
            "source_sha256": layout_sha256,
        },
        "pack_artifact": {
            "alias_key_count": _required_exact_int(
                aliases, "keys", "manifest.indexes.aliases"
            ),
            "artifact_license": _required_string(
                pack, "artifact_license", "manifest.pack"
            ),
            "artifact_sha256": evidence["pack"]["artifact_sha256"],
            "candidate_count": _required_exact_int(
                counts, "candidate_surfaces", "manifest.counts"
            ),
            "file_name": "lif-Limb-NP.nkp",
            "language": LANGUAGE,
            "output_script": OUTPUT_SCRIPT,
            "pack_id": PACK_ID,
            "release_mode": "internal",
            "surface_key_count": _required_exact_int(
                surface, "keys", "manifest.indexes.surface"
            ),
            "validation": {
                "benchmark_queries": [row["query"] for row in benchmark],
                "expected_surface": validation["expected_first_surface"],
                "query": validation["query"],
            },
        },
        "profile_id": PACK_ID,
        "status": "passed",
    })
    return review


def _write_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _write_or_check(path: Path, encoded: bytes, check: bool) -> None:
    if path.is_symlink():
        raise FinalizeError(f"output must not be a symbolic link: {path}")
    if check:
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise FinalizeError(f"cannot check output {path}: {exc}") from exc
        if current != encoded:
            raise FinalizeError(f"generated output is stale: {path}")
        return
    _write_atomic(path, encoded)


def finalize(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    if not DATE_RE.fullmatch(args.reviewed_at):
        raise FinalizeError("reviewed-at must be YYYY-MM-DD")
    expected_paths = {
        "query selection": (
            REPOSITORY_ROOT / "catalog/limbu-internal-prefixes-v0.json"
        ),
        "shipping review": REPOSITORY_ROOT / "catalog/shipping-profile-review.json",
        "Limbu layout source": (
            REPOSITORY_ROOT / "layouts/internal/src/limb-nepal-phonetic-v1.json"
        ),
        "evidence output": REPOSITORY_ROOT / "reports/limbu-internal-pack-v0.json",
        "review output": REPOSITORY_ROOT / "catalog/internal-profile-review.json",
    }
    actual_paths = {
        "query selection": args.queries,
        "shipping review": args.shipping_review,
        "Limbu layout source": args.layout_source,
        "evidence output": args.evidence_output,
        "review output": args.review_output,
    }
    for label, expected in expected_paths.items():
        if actual_paths[label].resolve() != expected.resolve():
            raise FinalizeError(f"{label} must use canonical path {expected}")
    if args.evidence_output.resolve() == args.review_output.resolve():
        raise FinalizeError("evidence and review outputs must be distinct")
    _require_distinct_paths(args.source_a, args.source_b, "source directory")
    _require_distinct_paths(args.pack_a, args.pack_b, "NKP")
    evidence, manifest = _build_evidence(args)
    evidence_bytes = _canonical_bytes(evidence)
    review = _build_review(args, evidence, evidence_bytes, manifest)
    review_bytes = _canonical_bytes(review)
    _write_or_check(args.evidence_output, evidence_bytes, args.check)
    _write_or_check(args.review_output, review_bytes, args.check)
    return evidence, review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-a", type=Path, required=True)
    parser.add_argument("--source-b", type=Path, required=True)
    parser.add_argument("--pack-a", type=Path, required=True)
    parser.add_argument("--pack-b", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--shipping-review", type=Path, required=True)
    parser.add_argument("--layout-source", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--review-output", type=Path, required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        evidence, review = finalize(args)
    except FinalizeError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "evidence_output": str(args.evidence_output),
        "evidence_sha256": _sha256_bytes(_canonical_bytes(evidence)),
        "review_output": str(args.review_output),
        "review_sha256": _sha256_bytes(_canonical_bytes(review)),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
