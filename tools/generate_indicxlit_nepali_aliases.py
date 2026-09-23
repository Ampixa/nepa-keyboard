#!/usr/bin/env python3
"""Generate deterministic Nepali Roman aliases with pinned IndicXlit v1.0.

This is a build-host tool, not an Android dependency.  It verifies the exact
MIT-licensed native-to-Roman model and the pinned direct Nepali vocabulary,
runs Fairseq on CPU with fixed decoding settings, and emits a small auditable
JSONL artifact consumed by the release-source adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path


GENERATOR_VERSION = 1
PACK_ID = "npi-Deva-NP"
DIRECT_FORMS_SHA256 = (
    "1ea9db6637c1332e57cb2c5a437cdf3da13c6a166723196e1680902eb7bcf7c2"
)
DIRECT_FORM_COUNT = 80_969
INDICXLIT_REPO_COMMIT = "042cda8cf6f07450adbd0d00ff74cd40a759154a"
INDICXLIT_MODEL_ARCHIVE_SHA256 = (
    "420d23a13cfa953edfb47644bc805de06e97134f25e6d182303a29f55b5a3322"
)
INDICXLIT_CHECKPOINT_SHA256 = (
    "45ffecef88d990ae12f915939b91267a3fc8f69f26331baa59f7932005976f28"
)
INDICXLIT_NE_DICT_SHA256 = (
    "0fe786202f4418cec9d8fcd8413c715a2be7fabb5b58fdc47671e6227dde384f"
)
INDICXLIT_EN_DICT_SHA256 = (
    "5ed7b43557095f70f20bad9fb0484ea9f2099001467bc8c732c8a9e6b3d7c34a"
)
INDICXLIT_LANG_LIST_SHA256 = (
    "9f5f2ae3c3eab13746f0874612940a37d0a1603966e35d88d8d7a2aa805c14c2"
)
INDICXLIT_LICENSE_SHA256 = (
    "763144522d0515acd475f496d0e0df4e44030688a432e7a21fe46e8a4501188b"
)
MODEL_ARCHIVE_URL = (
    "https://github.com/AI4Bharat/IndicXlit/releases/download/v1.0/"
    "indicxlit-indic-en-v1.0.zip"
)
MODEL_PROJECT_URL = "https://github.com/AI4Bharat/IndicXlit"
MODEL_LICENSE_URL = (
    "https://github.com/AI4Bharat/IndicXlit/blob/"
    f"{INDICXLIT_REPO_COMMIT}/LICENSE"
)

LANG_PAIRS = (
    "as-en,bn-en,brx-en,gom-en,gu-en,hi-en,kn-en,ks-en,mai-en,ml-en,"
    "mni-en,mr-en,ne-en,or-en,pa-en,sa-en,sd-en,si-en,ta-en,te-en,ur-en"
)
ASCII_ALIAS_RE = re.compile(r"^[a-z]+$")
HYPOTHESIS_RE = re.compile(r"^H-([0-9]+)\t([^\t]+)\t(.+)$")


class IndicXlitGenerationError(ValueError):
    """Raised when model inputs or generated aliases violate the pinned contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except FileNotFoundError as exc:
        raise IndicXlitGenerationError(f"missing required input: {path}") from exc
    return digest.hexdigest()


def _verify_file(path: Path, expected: str, label: str) -> str:
    actual = _sha256_file(path)
    if actual != expected:
        raise IndicXlitGenerationError(
            f"{label} SHA-256 mismatch: expected {expected}, got {actual}"
        )
    return actual


def _load_forms(path: Path) -> list[dict[str, str]]:
    _verify_file(path, DIRECT_FORMS_SHA256, "direct Nepali forms")
    forms: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_surfaces: set[str] = set()
    try:
        handle = path.open(encoding="utf-8")
    except FileNotFoundError as exc:
        raise IndicXlitGenerationError(f"missing direct forms: {path}") from exc
    with handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IndicXlitGenerationError(
                    f"invalid direct form JSON at line {line_number}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise IndicXlitGenerationError(
                    f"direct forms line {line_number} is not an object"
                )
            form_id = row.get("form_id")
            surface = row.get("surface")
            if not isinstance(form_id, str) or not isinstance(surface, str):
                raise IndicXlitGenerationError(
                    f"direct forms line {line_number} lacks form_id or surface"
                )
            if form_id in seen_ids or surface in seen_surfaces:
                raise IndicXlitGenerationError(
                    f"direct forms line {line_number} duplicates form_id or surface"
                )
            seen_ids.add(form_id)
            seen_surfaces.add(surface)
            forms.append({"form_id": form_id, "surface": surface})
    if len(forms) != DIRECT_FORM_COUNT:
        raise IndicXlitGenerationError(
            f"direct form count mismatch: expected {DIRECT_FORM_COUNT}, got {len(forms)}"
        )
    return forms


def _verify_toolchain() -> dict[str, str]:
    try:
        import fairseq
        import numpy
        import torch
    except ImportError as exc:
        raise IndicXlitGenerationError(
            "generation requires the pinned remote Fairseq toolchain"
        ) from exc
    fairseq_version = str(getattr(fairseq, "__version__", ""))
    torch_version = str(getattr(torch, "__version__", ""))
    numpy_version = str(getattr(numpy, "__version__", ""))
    if fairseq_version != "0.12.2":
        raise IndicXlitGenerationError(
            f"Fairseq version must be 0.12.2, got {fairseq_version}"
        )
    if not torch_version.startswith("1.13.1"):
        raise IndicXlitGenerationError(
            f"PyTorch version must be 1.13.1, got {torch_version}"
        )
    if numpy_version != "1.26.4":
        raise IndicXlitGenerationError(
            f"NumPy version must be 1.26.4, got {numpy_version}"
        )
    if torch.cuda.is_available():
        raise IndicXlitGenerationError(
            "pinned alias generation must run on CPU for reproducibility"
        )
    return {
        "python": sys.version.split()[0],
        "fairseq": fairseq_version,
        "torch": torch_version,
        "numpy": numpy_version,
    }


def _write_model_input(forms: list[dict[str, str]], path: Path) -> str:
    path.write_text(
        "".join(" ".join(form["surface"]) + "\n" for form in forms),
        encoding="utf-8",
    )
    return _sha256_file(path)


def _command(args: argparse.Namespace) -> list[str]:
    checkpoint = args.model_root / "transformer" / "indicxlit.pt"
    data = args.model_root / "corpus-bin"
    return [
        sys.executable,
        "-m",
        "fairseq_cli.interactive",
        str(data),
        "--path",
        str(checkpoint),
        "--task",
        "translation_multi_simple_epoch",
        "--source-lang",
        "ne",
        "--target-lang",
        "en",
        "--beam",
        str(args.topk),
        "--nbest",
        str(args.topk),
        "--batch-size",
        str(args.batch_size),
        "--buffer-size",
        str(args.batch_size),
        "--cpu",
        "--encoder-langtok",
        "src",
        "--lang-dict",
        str(args.lang_list),
        "--lang-pairs",
        LANG_PAIRS,
        "--num-workers",
        "0",
        "--seed",
        "1",
    ]


def _run_fairseq(
    command: list[str],
    model_input: Path,
    raw_output: Path,
    raw_stderr: Path,
    threads: int,
) -> None:
    environment = dict(os.environ)
    environment["CUDA_VISIBLE_DEVICES"] = ""
    environment["OMP_NUM_THREADS"] = str(threads)
    environment["MKL_NUM_THREADS"] = str(threads)
    with (
        model_input.open("rb") as stdin,
        raw_output.open("wb") as stdout,
        raw_stderr.open("wb") as stderr,
    ):
        completed = subprocess.run(
            command,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            env=environment,
            check=False,
        )
    if completed.returncode != 0:
        raise IndicXlitGenerationError(
            f"Fairseq inference failed with exit status {completed.returncode}; "
            f"see {raw_stderr}"
        )


def _parse_hypotheses(
    raw_output: Path,
    forms: list[dict[str, str]],
    topk: int,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    hypotheses: dict[int, list[str]] = defaultdict(list)
    stats = Counter()
    try:
        handle = raw_output.open(encoding="utf-8")
    except FileNotFoundError as exc:
        raise IndicXlitGenerationError(f"missing Fairseq output: {raw_output}") from exc
    with handle:
        for line_number, line in enumerate(handle, 1):
            match = HYPOTHESIS_RE.match(line.rstrip("\n"))
            if not match:
                continue
            index = int(match.group(1))
            if index >= len(forms):
                raise IndicXlitGenerationError(
                    f"Fairseq output line {line_number} has out-of-range index {index}"
                )
            alias = "".join(match.group(3).split()).lower()
            if not ASCII_ALIAS_RE.fullmatch(alias):
                raise IndicXlitGenerationError(
                    f"Fairseq output line {line_number} has invalid alias {alias!r}"
                )
            if alias in hypotheses[index]:
                stats["duplicate_hypotheses"] += 1
                continue
            hypotheses[index].append(alias)

    missing = [index for index in range(len(forms)) if not hypotheses.get(index)]
    if missing:
        raise IndicXlitGenerationError(
            f"Fairseq produced no aliases for {len(missing)} forms; first index {missing[0]}"
        )
    rows: list[dict[str, object]] = []
    short_beams = 0
    for index, form in enumerate(forms):
        values = hypotheses[index]
        if len(values) > topk:
            raise IndicXlitGenerationError(
                f"Fairseq produced {len(values)} unique aliases for form index {index}; "
                f"topk is {topk}"
            )
        if len(values) < topk:
            short_beams += 1
        for beam_rank, alias in enumerate(values, 1):
            rows.append(
                {
                    "alias": alias,
                    "beam_rank": beam_rank,
                    "form_id": form["form_id"],
                    "surface": form["surface"],
                }
            )
    stats["forms"] = len(forms)
    stats["alias_rows"] = len(rows)
    stats["forms_with_short_beam"] = short_beams
    stats["unique_aliases"] = len({str(row["alias"]) for row in rows})
    return rows, dict(sorted(stats.items()))


def _write_aliases(path: Path, rows: list[dict[str, object]]) -> str:
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return _sha256_file(path)


def generate(args: argparse.Namespace) -> dict[str, object]:
    if not isinstance(args.topk, int) or not 1 <= args.topk <= 8:
        raise IndicXlitGenerationError("topk must be an integer from 1 to 8")
    if not isinstance(args.batch_size, int) or not 1 <= args.batch_size <= 1024:
        raise IndicXlitGenerationError("batch size must be an integer from 1 to 1024")
    if not isinstance(args.threads, int) or not 1 <= args.threads <= 8:
        raise IndicXlitGenerationError("threads must be an integer from 1 to 8")

    forms = _load_forms(args.forms)
    toolchain = _verify_toolchain()
    model_archive_sha256 = _verify_file(
        args.model_archive,
        INDICXLIT_MODEL_ARCHIVE_SHA256,
        "IndicXlit native-to-Roman model archive",
    )
    checkpoint_sha256 = _verify_file(
        args.model_root / "transformer" / "indicxlit.pt",
        INDICXLIT_CHECKPOINT_SHA256,
        "IndicXlit checkpoint",
    )
    ne_dict_sha256 = _verify_file(
        args.model_root / "corpus-bin" / "dict.ne.txt",
        INDICXLIT_NE_DICT_SHA256,
        "IndicXlit Nepali dictionary",
    )
    en_dict_sha256 = _verify_file(
        args.model_root / "corpus-bin" / "dict.en.txt",
        INDICXLIT_EN_DICT_SHA256,
        "IndicXlit Roman dictionary",
    )
    lang_list_sha256 = _verify_file(
        args.lang_list,
        INDICXLIT_LANG_LIST_SHA256,
        "IndicXlit language list",
    )
    license_sha256 = _verify_file(
        args.license,
        INDICXLIT_LICENSE_SHA256,
        "IndicXlit MIT license",
    )
    license_text = args.license.read_text(encoding="utf-8")
    if "MIT License" not in license_text or "Copyright (c) 2022 AI4Bhārat" not in license_text:
        raise IndicXlitGenerationError("IndicXlit license lacks the audited MIT notice")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_input = args.output_dir / "model-input.txt"
    raw_output = args.output_dir / "fairseq-output.txt"
    raw_stderr = args.output_dir / "fairseq-stderr.txt"
    aliases_path = args.output_dir / "aliases.jsonl"
    manifest_path = args.output_dir / "manifest.json"
    model_input_sha256 = _write_model_input(forms, model_input)
    command = _command(args)
    _run_fairseq(
        command,
        model_input,
        raw_output,
        raw_stderr,
        args.threads,
    )
    rows, stats = _parse_hypotheses(raw_output, forms, args.topk)
    aliases_sha256 = _write_aliases(aliases_path, rows)

    manifest: dict[str, object] = {
        "generator": "generate_indicxlit_nepali_aliases",
        "generator_version": GENERATOR_VERSION,
        "pack_id": PACK_ID,
        "model_direction": "Nepali Devanagari to Roman",
        "decoding": {
            "beam": args.topk,
            "nbest": args.topk,
            "batch_size": args.batch_size,
            "cpu": True,
            "seed": 1,
            "threads": args.threads,
            "fairseq_task": "translation_multi_simple_epoch",
            "source_language": "ne",
            "target_language": "en",
            "encoder_langtok": "src",
        },
        "inputs": {
            "direct_forms": {
                "sha256": DIRECT_FORMS_SHA256,
                "rows": len(forms),
            },
            "model_archive": {
                "sha256": model_archive_sha256,
                "source_url": MODEL_ARCHIVE_URL,
                "checkpoint_sha256": checkpoint_sha256,
                "ne_dictionary_sha256": ne_dict_sha256,
                "en_dictionary_sha256": en_dict_sha256,
            },
            "indicxlit": {
                "repository": MODEL_PROJECT_URL,
                "commit": INDICXLIT_REPO_COMMIT,
                "license": "MIT",
                "license_url": MODEL_LICENSE_URL,
                "license_sha256": license_sha256,
                "lang_list_sha256": lang_list_sha256,
            },
        },
        "toolchain": toolchain,
        "outputs": {
            "model_input_sha256": model_input_sha256,
            "aliases_sha256": aliases_sha256,
            "fairseq_output_sha256": _sha256_file(raw_output),
            "counts": stats,
        },
        "evaluation_data_consumed": False,
    }
    manifest_path.write_text(_canonical_json(manifest) + "\n", encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate pinned IndicXlit native-to-Roman aliases on a build host."
    )
    parser.add_argument("--forms", type=Path, required=True)
    parser.add_argument("--model-archive", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--lang-list", type=Path, required=True)
    parser.add_argument("--license", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--topk", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--threads", type=int, default=2)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        manifest = generate(args)
    except IndicXlitGenerationError as exc:
        parser.error(str(exc))
    print(_canonical_json(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
