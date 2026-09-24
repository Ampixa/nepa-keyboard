from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import build_central_gurung_candidate_source as candidate
from tools import build_central_gurung_internal_source as internal


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "reports/evidence/central-gurung-candidate-v0/gvr_nep_lexicon.tsv"


class CentralGurungInternalSourceTest(unittest.TestCase):
    def test_internal_pack_preserves_pinned_candidate_curation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_dir = root / "candidate"
            internal_dir = root / "internal"
            common = {"toolkit_tsv": RAW, "data_version": "1.0.0", "max_suggestions": 8}
            candidate.build_candidate_source(
                argparse.Namespace(**common, output=candidate_dir)
            )
            report = internal.build_internal_source(
                argparse.Namespace(**common, output=internal_dir)
            )

            for member in ("forms.jsonl", "rejected-rows.jsonl", "sources.jsonl", "aliases.jsonl"):
                self.assertEqual(
                    (candidate_dir / member).read_bytes(),
                    (internal_dir / member).read_bytes(),
                    member,
                )
            pack = json.loads((internal_dir / "pack.json").read_text(encoding="utf-8"))
            self.assertEqual(pack["display_name"], "Central Gurung")
            self.assertEqual(pack["variety"], "Central Gurung source review pending")
            self.assertEqual(report["stats"]["accepted_rows"], 294)
            self.assertEqual(report["stats"]["distinct_accepted_surfaces"], 286)
            self.assertEqual(report["adapter"], "build_central_gurung_internal_source")
            self.assertEqual(
                report["adapter_sha256"],
                hashlib.sha256(Path(internal.__file__).read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
