"""Compile audited JSONL build tables into deterministic ``.nkp`` bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


COMPILER_VERSION = "0.1.0"
FORMAT_VERSION = 0

TRIE_MAGIC = b"NKTRIE1\0"
CANDIDATE_MAGIC = b"NKCAND1\0"
SCORE_MAGIC = b"NKSCORE1"

TRIE_HEADER = struct.Struct("<8sIIIHH")
TRIE_NODE = struct.Struct("<IHIH")
TRIE_EDGE = struct.Struct("<II")
U32 = struct.Struct("<I")
I32 = struct.Struct("<i")
TABLE_HEADER = struct.Struct("<8sI")

PACK_ID_RE = re.compile(r"^[a-z]{3}-[A-Z][a-z]{3}-[A-Z]{2}(?:[-.][A-Za-z0-9]+)*$")
ISO_639_3_RE = re.compile(r"^[a-z]{3}$")
ISO_15924_RE = re.compile(r"^[A-Z][a-z]{3}$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
CODEPOINT_RE = re.compile(r"^U\+([0-9A-F]{4,6})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

REDISTRIBUTION_VALUES = {
    "allowed",
    "system",
    "prohibited",
    "permission_required",
    "unknown",
}
EVIDENCE_VALUES = {"attested", "induced", "generated", "mixed"}
SURFACE_LOOKUP_NORMALIZATIONS = {"NFC", "NFC+ASCII-lower"}
SHARE_ALIKE_LICENSES = {"CC-BY-SA-4.0"}

# These ranges are validation gates, not transliteration tables. Common
# punctuation, separators, and numbers are accepted separately.
SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "Deva": ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x11B00, 0x11B5F)),
    "Limb": ((0x1900, 0x194F),),
    "Newa": ((0x11400, 0x1147F),),
    "Olck": ((0x1C50, 0x1C7F),),
    "Tirh": ((0x11480, 0x114DF),),
    "Sunu": ((0x11BC0, 0x11BFF),),
    "Lepc": ((0x1C00, 0x1C4F),),
    "Tibt": ((0x0F00, 0x0FFF),),
    "Latn": (
        (0x0041, 0x005A),
        (0x0061, 0x007A),
        (0x00C0, 0x024F),
        (0x1E00, 0x1EFF),
    ),
}


class PackValidationError(ValueError):
    """Raised when build input cannot safely become a language pack."""


@dataclass
class Candidate:
    surface: str
    rank_score: int
    form_ids: set[str] = field(default_factory=set)
    source_ids: set[str] = field(default_factory=set)
    evidence: set[str] = field(default_factory=set)


@dataclass
class TrieNode:
    children: dict[str, int] = field(default_factory=dict)
    terminal_scores: dict[int, int] = field(default_factory=dict)
    top_scores: list[tuple[int, int]] = field(default_factory=list)


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackValidationError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PackValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PackValidationError(f"expected an object in {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise PackValidationError(f"missing required file: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PackValidationError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise PackValidationError(f"expected an object at {path}:{line_number}")
        row["__line__"] = line_number
        rows.append(row)
    return rows


def _require_string(row: dict[str, Any], field_name: str, location: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value:
        raise PackValidationError(f"{location}: {field_name} must be a non-empty string")
    return value


def _require_string_list(row: dict[str, Any], field_name: str, location: str) -> list[str]:
    value = row.get(field_name)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise PackValidationError(
            f"{location}: {field_name} must be a non-empty list of non-empty strings"
        )
    return value


def _parse_metadata(input_dir: Path) -> dict[str, Any]:
    metadata = _read_json(input_dir / "pack.json")
    required = {
        "pack_id",
        "language",
        "display_name",
        "output_script",
        "region",
        "data_version",
        "max_suggestions",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise PackValidationError(f"pack.json: missing fields: {', '.join(missing)}")
    if not PACK_ID_RE.fullmatch(str(metadata["pack_id"])):
        raise PackValidationError("pack.json: invalid pack_id")
    if not ISO_639_3_RE.fullmatch(str(metadata["language"])):
        raise PackValidationError("pack.json: language must be ISO 639-3")
    if not ISO_15924_RE.fullmatch(str(metadata["output_script"])):
        raise PackValidationError("pack.json: output_script must be ISO 15924")
    if metadata["output_script"] not in SCRIPT_RANGES:
        raise PackValidationError(f"pack.json: unsupported output script {metadata['output_script']!r}")
    if not re.fullmatch(r"^[A-Z]{2}$", str(metadata["region"])):
        raise PackValidationError("pack.json: region must be ISO 3166-1 alpha-2")
    if not SEMVER_RE.fullmatch(str(metadata["data_version"])):
        raise PackValidationError("pack.json: data_version must be semantic x.y.z")
    max_suggestions = metadata["max_suggestions"]
    if not isinstance(max_suggestions, int) or not 1 <= max_suggestions <= 32:
        raise PackValidationError("pack.json: max_suggestions must be an integer from 1 to 32")
    artifact_license = metadata.get("artifact_license")
    if artifact_license is not None and (
        not isinstance(artifact_license, str) or not artifact_license.strip()
    ):
        raise PackValidationError("pack.json: artifact_license must be a non-empty string")
    surface_lookup_normalization = metadata.get("surface_lookup_normalization", "NFC")
    if (
        not isinstance(surface_lookup_normalization, str)
        or surface_lookup_normalization not in SURFACE_LOOKUP_NORMALIZATIONS
    ):
        raise PackValidationError(
            "pack.json: surface_lookup_normalization must be NFC or NFC+ASCII-lower"
        )
    metadata["_surface_lookup_normalization"] = surface_lookup_normalization
    allowed: set[int] = set()
    for encoded in metadata.get("allowed_format_characters", []):
        if not isinstance(encoded, str) or not (match := CODEPOINT_RE.fullmatch(encoded)):
            raise PackValidationError(f"pack.json: invalid allowed format character {encoded!r}")
        allowed.add(int(match.group(1), 16))
    metadata["_allowed_format_codepoints"] = allowed
    return metadata


def _parse_sources(input_dir: Path) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(input_dir / "sources.jsonl"):
        line = row.pop("__line__")
        location = f"sources.jsonl:{line}"
        source_id = _require_string(row, "source_id", location)
        _require_string(row, "title", location)
        _require_string(row, "method", location)
        _require_string(row, "license", location)
        redistribution = _require_string(row, "redistribution", location)
        if redistribution not in REDISTRIBUTION_VALUES:
            raise PackValidationError(f"{location}: invalid redistribution state {redistribution!r}")
        sha256 = row.get("sha256")
        if sha256 is not None and (
            not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256)
        ):
            raise PackValidationError(f"{location}: sha256 must be 64 lowercase hexadecimal characters")
        if source_id in sources:
            raise PackValidationError(f"{location}: duplicate source_id {source_id!r}")
        sources[source_id] = row
    return sources


def _validate_release_source(source_id: str, source: dict[str, Any]) -> None:
    if source["redistribution"] == "system":
        return
    location = f"release source {source_id!r}"
    for field_name in ("sha256", "source_url", "license_url", "license_notice"):
        value = source.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise PackValidationError(f"{location}: missing required {field_name}")
    if not SHA256_RE.fullmatch(source["sha256"]):
        raise PackValidationError(
            f"{location}: sha256 must be 64 lowercase hexadecimal characters"
        )


def _validate_source_ids(source_ids: Iterable[str], sources: dict[str, dict[str, Any]], location: str) -> set[str]:
    result = set(source_ids)
    missing = sorted(result - sources.keys())
    if missing:
        raise PackValidationError(f"{location}: unknown source IDs: {', '.join(missing)}")
    return result


def _validate_surface(surface: str, script: str, allowed_format_codepoints: set[int], location: str) -> None:
    if unicodedata.normalize("NFC", surface) != surface:
        raise PackValidationError(f"{location}: surface must already be NFC: {surface!r}")
    ranges = SCRIPT_RANGES[script]
    has_script_letter = False
    for char in surface:
        codepoint = ord(char)
        category = unicodedata.category(char)
        if category == "Cf":
            if codepoint not in allowed_format_codepoints:
                raise PackValidationError(f"{location}: unapproved format character U+{codepoint:04X}")
            continue
        if category == "Cc":
            raise PackValidationError(f"{location}: control character U+{codepoint:04X}")
        if any(start <= codepoint <= end for start, end in ranges):
            if category.startswith("L"):
                has_script_letter = True
            continue
        if category[0] in {"N", "P", "S", "Z"}:
            continue
        raise PackValidationError(
            f"{location}: character U+{codepoint:04X} is outside declared script {script}"
        )
    if not has_script_letter:
        raise PackValidationError(f"{location}: surface has no {script} letter")


def _parse_forms(
    input_dir: Path,
    metadata: dict[str, Any],
    sources: dict[str, dict[str, Any]],
) -> tuple[dict[str, str], dict[str, Candidate], int]:
    form_to_surface: dict[str, str] = {}
    candidates: dict[str, Candidate] = {}
    duplicates_merged = 0
    for row in _read_jsonl(input_dir / "forms.jsonl"):
        line = row.pop("__line__")
        location = f"forms.jsonl:{line}"
        form_id = _require_string(row, "form_id", location)
        surface = _require_string(row, "surface", location)
        if form_id in form_to_surface:
            raise PackValidationError(f"{location}: duplicate form_id {form_id!r}")
        rank_score = row.get("rank_score")
        if not isinstance(rank_score, int) or not -(2**31) <= rank_score < 2**31:
            raise PackValidationError(f"{location}: rank_score must fit signed int32")
        evidence = _require_string(row, "evidence", location)
        if evidence not in EVIDENCE_VALUES:
            raise PackValidationError(f"{location}: invalid evidence {evidence!r}")
        source_ids = _validate_source_ids(
            _require_string_list(row, "source_ids", location), sources, location
        )
        _validate_surface(
            surface,
            metadata["output_script"],
            metadata["_allowed_format_codepoints"],
            location,
        )
        form_to_surface[form_id] = surface
        candidate = candidates.get(surface)
        if candidate is None:
            candidate = Candidate(surface=surface, rank_score=rank_score)
            candidates[surface] = candidate
        else:
            duplicates_merged += 1
            candidate.rank_score = max(candidate.rank_score, rank_score)
        candidate.form_ids.add(form_id)
        candidate.source_ids.update(source_ids)
        candidate.evidence.add(evidence)
    if not candidates:
        raise PackValidationError("forms.jsonl: at least one valid form is required")
    return form_to_surface, candidates, duplicates_merged


def _normalize_alias(alias: str, location: str) -> str:
    for char in alias:
        category = unicodedata.category(char)
        if category in {"Cc", "Cf"}:
            raise PackValidationError(f"{location}: alias contains disallowed U+{ord(char):04X}")
    normalized = unicodedata.normalize("NFC", alias).casefold().strip()
    if not normalized:
        raise PackValidationError(f"{location}: alias is empty after normalization")
    return normalized


def _normalize_surface_lookup_key(surface: str, normalization: str) -> str:
    key = unicodedata.normalize("NFC", surface)
    if normalization == "NFC+ASCII-lower":
        return key.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))
    return key


def _parse_aliases(
    input_dir: Path,
    form_to_surface: dict[str, str],
    candidates: dict[str, Candidate],
    candidate_ids: dict[str, int],
    sources: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[int, int]], int, set[str]]:
    alias_scores: dict[str, dict[int, int]] = {}
    used_source_ids: set[str] = set()
    row_count = 0
    for row in _read_jsonl(input_dir / "aliases.jsonl"):
        line = row.pop("__line__")
        location = f"aliases.jsonl:{line}"
        alias = _normalize_alias(_require_string(row, "alias", location), location)
        form_id = _require_string(row, "form_id", location)
        if form_id not in form_to_surface:
            raise PackValidationError(f"{location}: unknown form_id {form_id!r}")
        rank_delta = row.get("rank_delta", 0)
        if not isinstance(rank_delta, int) or not -(2**31) <= rank_delta < 2**31:
            raise PackValidationError(f"{location}: rank_delta must fit signed int32")
        _require_string(row, "scheme", location)
        evidence = _require_string(row, "evidence", location)
        if evidence not in EVIDENCE_VALUES:
            raise PackValidationError(f"{location}: invalid evidence {evidence!r}")
        source_ids = _validate_source_ids(
            _require_string_list(row, "source_ids", location), sources, location
        )
        used_source_ids.update(source_ids)
        surface = form_to_surface[form_id]
        candidate_id = candidate_ids[surface]
        effective_score = candidates[surface].rank_score + rank_delta
        by_candidate = alias_scores.setdefault(alias, {})
        by_candidate[candidate_id] = max(by_candidate.get(candidate_id, -(2**31)), effective_score)
        row_count += 1
    return alias_scores, row_count, used_source_ids


def _rank_top(scores: dict[int, int], candidate_surfaces: list[str], limit: int) -> list[tuple[int, int]]:
    return sorted(
        scores.items(),
        key=lambda item: (-item[1], candidate_surfaces[item[0]], item[0]),
    )[:limit]


def _build_trie(
    key_scores: dict[str, dict[int, int]],
    candidate_surfaces: list[str],
    max_suggestions: int,
) -> tuple[bytes, dict[str, int]]:
    nodes = [TrieNode()]
    for key in sorted(key_scores):
        node_index = 0
        for char in key:
            child_index = nodes[node_index].children.get(char)
            if child_index is None:
                child_index = len(nodes)
                nodes[node_index].children[char] = child_index
                nodes.append(TrieNode())
            node_index = child_index
        terminal = nodes[node_index].terminal_scores
        for candidate_id, score in key_scores[key].items():
            terminal[candidate_id] = max(terminal.get(candidate_id, -(2**31)), score)

    for node_index in range(len(nodes) - 1, -1, -1):
        node = nodes[node_index]
        merged = dict(node.terminal_scores)
        for child_index in node.children.values():
            for candidate_id, score in nodes[child_index].top_scores:
                merged[candidate_id] = max(merged.get(candidate_id, -(2**31)), score)
        node.top_scores = _rank_top(merged, candidate_surfaces, max_suggestions)

    edge_rows: list[tuple[int, int]] = []
    values: list[int] = []
    node_rows: list[tuple[int, int, int, int]] = []
    for node in nodes:
        first_edge = len(edge_rows)
        for char, child_index in sorted(node.children.items(), key=lambda item: ord(item[0])):
            edge_rows.append((ord(char), child_index))
        first_value = len(values)
        values.extend(candidate_id for candidate_id, _score in node.top_scores)
        if len(node.children) > 0xFFFF or len(node.top_scores) > 0xFFFF:
            raise PackValidationError("trie node exceeds v0 uint16 limits")
        node_rows.append((first_edge, len(node.children), first_value, len(node.top_scores)))

    output = bytearray(
        TRIE_HEADER.pack(
            TRIE_MAGIC,
            len(node_rows),
            len(edge_rows),
            len(values),
            max_suggestions,
            0,
        )
    )
    for row in node_rows:
        output.extend(TRIE_NODE.pack(*row))
    for row in edge_rows:
        output.extend(TRIE_EDGE.pack(*row))
    for candidate_id in values:
        output.extend(U32.pack(candidate_id))
    return bytes(output), {
        "nodes": len(node_rows),
        "edges": len(edge_rows),
        "values": len(values),
        "keys": len(key_scores),
    }


def _serialize_candidates(candidate_surfaces: list[str]) -> bytes:
    encoded = [surface.encode("utf-8") for surface in candidate_surfaces]
    offsets = [0]
    for value in encoded:
        offsets.append(offsets[-1] + len(value))
    output = bytearray(TABLE_HEADER.pack(CANDIDATE_MAGIC, len(encoded)))
    for offset in offsets:
        output.extend(U32.pack(offset))
    for value in encoded:
        output.extend(value)
    return bytes(output)


def _serialize_scores(candidate_surfaces: list[str], candidates: dict[str, Candidate]) -> bytes:
    output = bytearray(TABLE_HEADER.pack(SCORE_MAGIC, len(candidate_surfaces)))
    for surface in candidate_surfaces:
        output.extend(I32.pack(candidates[surface].rank_score))
    return bytes(output)


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def compile_pack(input_dir: Path, output_path: Path, mode: str = "internal") -> dict[str, Any]:
    """Compile one source directory and return its deterministic build report."""
    if mode not in {"internal", "release"}:
        raise PackValidationError("mode must be 'internal' or 'release'")
    metadata = _parse_metadata(input_dir)
    sources = _parse_sources(input_dir)
    form_to_surface, candidates, duplicate_surfaces = _parse_forms(input_dir, metadata, sources)

    candidate_surfaces = sorted(candidates)
    candidate_ids = {surface: index for index, surface in enumerate(candidate_surfaces)}
    aliases, alias_rows, alias_source_ids = _parse_aliases(
        input_dir,
        form_to_surface,
        candidates,
        candidate_ids,
        sources,
    )

    form_source_ids = set().union(*(candidate.source_ids for candidate in candidates.values()))
    used_source_ids = form_source_ids | alias_source_ids
    if mode == "release":
        blocked = {
            source_id: sources[source_id]["redistribution"]
            for source_id in sorted(used_source_ids)
            if sources[source_id]["redistribution"] not in {"allowed", "system"}
        }
        if blocked:
            details = ", ".join(f"{key}={value}" for key, value in blocked.items())
            raise PackValidationError(f"release build blocked by source redistribution: {details}")
        for source_id in sorted(used_source_ids):
            _validate_release_source(source_id, sources[source_id])
        share_alike_sources = [
            source_id
            for source_id in sorted(used_source_ids)
            if sources[source_id]["license"] in SHARE_ALIKE_LICENSES
        ]
        if share_alike_sources and metadata.get("artifact_license") != "CC-BY-SA-4.0":
            raise PackValidationError(
                "release build uses CC-BY-SA-4.0 sources but pack.json does not declare "
                "artifact_license=CC-BY-SA-4.0: " + ", ".join(share_alike_sources)
            )

    surface_scores: dict[str, dict[int, int]] = {}
    for surface in candidate_surfaces:
        key = _normalize_surface_lookup_key(
            surface, metadata["_surface_lookup_normalization"]
        )
        candidate_id = candidate_ids[surface]
        by_candidate = surface_scores.setdefault(key, {})
        by_candidate[candidate_id] = candidates[surface].rank_score
    surface_trie, surface_stats = _build_trie(
        surface_scores, candidate_surfaces, metadata["max_suggestions"]
    )
    aliases_trie, alias_stats = _build_trie(
        aliases, candidate_surfaces, metadata["max_suggestions"]
    )
    candidate_bytes = _serialize_candidates(candidate_surfaces)
    score_bytes = _serialize_scores(candidate_surfaces, candidates)
    notices = {
        "sources": [sources[source_id] for source_id in sorted(used_source_ids)],
        "release_mode": mode,
    }
    notice_bytes = _canonical_json(notices)

    alias_collisions = sum(1 for values in aliases.values() if len(values) > 1)
    members: dict[str, bytes] = {
        "aliases.trie": aliases_trie,
        "candidates.bin": candidate_bytes,
        "notices.json": notice_bytes,
        "scores.bin": score_bytes,
        "surface.trie": surface_trie,
    }
    manifest_metadata = {
        key: value for key, value in metadata.items() if not key.startswith("_")
    }
    manifest = {
        "format_version": FORMAT_VERSION,
        "compiler_version": COMPILER_VERSION,
        "release_mode": mode,
        "pack": manifest_metadata,
        "normalization": {
            "surfaces": "NFC-strict",
            "surface_lookup": metadata["_surface_lookup_normalization"],
            "aliases": "NFC+casefold+trim",
        },
        "counts": {
            "source_forms": len(form_to_surface),
            "candidate_surfaces": len(candidate_surfaces),
            "duplicate_surfaces_merged": duplicate_surfaces,
            "alias_rows": alias_rows,
            "alias_keys": len(aliases),
            "alias_collisions": alias_collisions,
            "sources_used": len(used_source_ids),
        },
        "indexes": {
            "surface": surface_stats,
            "aliases": alias_stats,
        },
        "members": {
            name: {"bytes": len(data), "sha256": _sha256(data)}
            for name, data in sorted(members.items())
        },
    }
    members["manifest.json"] = _canonical_json(manifest)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            archive.writestr(_zip_info(name), members[name])

    artifact_bytes = output_path.read_bytes()
    report = {
        "artifact": str(output_path),
        "artifact_bytes": len(artifact_bytes),
        "artifact_sha256": _sha256(artifact_bytes),
        "manifest": manifest,
    }
    report_path = output_path.with_suffix(output_path.suffix + ".report.json")
    report_path.write_bytes(_canonical_json(report))
    return report


def _build_command(args: argparse.Namespace) -> int:
    try:
        report = compile_pack(args.input, args.output, args.mode)
    except PackValidationError as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _inspect_command(args: argparse.Namespace) -> int:
    from .runtime import KeyboardPack

    with KeyboardPack(args.pack) as pack:
        result = pack.lookup(args.prefix, args.index)
        print(json.dumps({"prefix": args.prefix, "index": args.index, "candidates": result}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nepa-pack")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="compile JSONL source tables into an .nkp bundle")
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--mode", choices=("internal", "release"), default="internal")
    build.set_defaults(func=_build_command)

    inspect = subparsers.add_parser("inspect", help="look up a prefix in a compiled bundle")
    inspect.add_argument("--pack", type=Path, required=True)
    inspect.add_argument("--index", choices=("surface", "aliases"), default="surface")
    inspect.add_argument("--prefix", required=True)
    inspect.set_defaults(func=_inspect_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
