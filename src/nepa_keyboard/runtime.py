"""Small reference reader for the v0 pack format.

The Android implementation should match this behavior, not embed this Python
reader. Keeping a reference reader makes binary compatibility testable.
"""

from __future__ import annotations

import bisect
import json
import struct
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from .compiler import (
    CANDIDATE_MAGIC,
    SCORE_MAGIC,
    TABLE_HEADER,
    TRIE_EDGE,
    TRIE_HEADER,
    TRIE_MAGIC,
    TRIE_NODE,
)


class KeyboardPack:
    """Read candidates and prefix indexes from one `.nkp` artifact."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._archive = zipfile.ZipFile(self.path, "r")
        self.manifest: dict[str, Any] = json.loads(self._archive.read("manifest.json"))
        normalization = self.manifest.get("normalization", {})
        if not isinstance(normalization, dict):
            raise ValueError("manifest normalization must be an object")
        self._surface_lookup_normalization = normalization.get("surface_lookup", "NFC")
        if self._surface_lookup_normalization not in {"NFC", "NFC+ASCII-lower"}:
            raise ValueError("unsupported surface lookup normalization")
        self._candidates = self._decode_candidates(self._archive.read("candidates.bin"))
        self._scores = self._decode_scores(self._archive.read("scores.bin"))
        if len(self._candidates) != len(self._scores):
            raise ValueError("candidate/score table count mismatch")
        self._trie_data: dict[str, bytes] = {}

    def __enter__(self) -> "KeyboardPack":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._archive.close()

    @staticmethod
    def _decode_candidates(data: bytes) -> list[str]:
        magic, count = TABLE_HEADER.unpack_from(data, 0)
        if magic != CANDIDATE_MAGIC:
            raise ValueError("invalid candidate table magic")
        table_start = TABLE_HEADER.size
        offsets = struct.unpack_from(f"<{count + 1}I", data, table_start)
        blob_start = table_start + (count + 1) * 4
        blob = data[blob_start:]
        if offsets[0] != 0 or offsets[-1] != len(blob):
            raise ValueError("invalid candidate offsets")
        return [blob[offsets[i] : offsets[i + 1]].decode("utf-8") for i in range(count)]

    @staticmethod
    def _decode_scores(data: bytes) -> list[int]:
        magic, count = TABLE_HEADER.unpack_from(data, 0)
        if magic != SCORE_MAGIC:
            raise ValueError("invalid score table magic")
        return list(struct.unpack_from(f"<{count}i", data, TABLE_HEADER.size))

    def _candidate_ids(self, prefix: str, index: str) -> list[int]:
        if index not in {"surface", "aliases"}:
            raise ValueError("index must be surface or aliases")
        if index == "aliases":
            prefix = unicodedata.normalize("NFC", prefix).casefold().strip()
        else:
            prefix = unicodedata.normalize("NFC", prefix)
            if self._surface_lookup_normalization == "NFC+ASCII-lower":
                prefix = prefix.translate(
                    str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
                )
        data = self._trie_data.get(index)
        if data is None:
            data = self._archive.read(f"{index}.trie")
            self._trie_data[index] = data
        magic, node_count, edge_count, value_count, _max_suggestions, _reserved = TRIE_HEADER.unpack_from(data, 0)
        if magic != TRIE_MAGIC:
            raise ValueError("invalid trie magic")
        nodes_start = TRIE_HEADER.size
        edges_start = nodes_start + node_count * TRIE_NODE.size
        values_start = edges_start + edge_count * TRIE_EDGE.size
        if len(data) != values_start + value_count * 4:
            raise ValueError("invalid trie length")

        node_index = 0
        for char in prefix:
            first_edge, edge_count_at_node, _first_value, _value_count_at_node = TRIE_NODE.unpack_from(
                data, nodes_start + node_index * TRIE_NODE.size
            )
            codepoints: list[int] = []
            targets: list[int] = []
            for offset in range(edge_count_at_node):
                codepoint, target = TRIE_EDGE.unpack_from(
                    data, edges_start + (first_edge + offset) * TRIE_EDGE.size
                )
                codepoints.append(codepoint)
                targets.append(target)
            position = bisect.bisect_left(codepoints, ord(char))
            if position == len(codepoints) or codepoints[position] != ord(char):
                return []
            node_index = targets[position]

        _first_edge, _edge_count, first_value, values_at_node = TRIE_NODE.unpack_from(
            data, nodes_start + node_index * TRIE_NODE.size
        )
        return list(struct.unpack_from(f"<{values_at_node}I", data, values_start + first_value * 4))

    def lookup(self, prefix: str, index: str = "surface") -> list[dict[str, Any]]:
        return [
            {"candidate_id": candidate_id, "surface": self._candidates[candidate_id], "score": self._scores[candidate_id]}
            for candidate_id in self._candidate_ids(prefix, index)
        ]
