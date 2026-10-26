#!/usr/bin/env python3
"""Saved-evidence corruption controls; copies only, no build or target execution."""
import gzip
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import verify_saved as saved

REPO = saved.P.parents[2]
RESULT = "results/run-40293434354/"


class RetainedEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / "relocated"
        shutil.copytree(saved.P, self.package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def rehash(self, rewrite_member_receipt=False):
        if rewrite_member_receipt:
            path = self.package / "results/artifact-members.json"
            path.write_text(json.dumps(saved.members(self.package / "results" / saved.RUN), indent=2) + "\n", encoding="utf-8")
        (self.package / "manifest.json").write_text(json.dumps({"files": saved.members(self.package, exclude_manifest=True)}, indent=2) + "\n", encoding="utf-8")

    def mutate_json(self, name, change):
        path = self.package / name
        value = saved.read_json(path)
        change(value)
        raw = (json.dumps(value, indent=2) + "\n").encode()
        path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)
        self.rehash(rewrite_member_receipt=True)

    def test_relocated_saved_package(self):
        result = saved.verify(self.package, REPO)
        self.assertTrue(result["original_location_raw_payload_equal"])
        self.assertFalse(result["whole_original_comparison"]["full_byte_equality"])

    def test_changed_binary_and_rewritten_manifests_rejected(self):
        path = self.package / RESULT / "candidate.so"
        raw = bytearray(path.read_bytes())
        raw[464840] ^= 1
        path.write_bytes(raw)
        self.rehash(True)
        with self.assertRaisesRegex(ValueError, "artifact provenance seal"):
            saved.verify(self.package, REPO)

    def test_truncated_binary_and_rewritten_manifests_rejected(self):
        path = self.package / RESULT / "candidate.so"
        path.write_bytes(path.read_bytes()[:-1])
        self.rehash(True)
        with self.assertRaisesRegex(ValueError, "artifact provenance seal"):
            saved.verify(self.package, REPO)

    def test_forged_registry_receipt_rejected(self):
        self.mutate_json(RESULT + "registry-before.json.gz", lambda value: next(iter(value.values())).update(archive_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "artifact provenance seal"):
            saved.verify(self.package, REPO)

    def test_forged_command_receipt_rejected(self):
        self.mutate_json(RESULT + "commands.json", lambda value: value.append({"label": "invented"}))
        with self.assertRaisesRegex(ValueError, "artifact provenance seal"):
            saved.verify(self.package, REPO)

    def test_changed_current_helper_rejected(self):
        path = self.package / "run.py"
        path.write_bytes(path.read_bytes() + b"\n# changed helper\n")
        self.rehash()
        with self.assertRaisesRegex(ValueError, "Executing helper differs"):
            saved.verify(self.package, REPO)

    def test_forged_provider_identity_rejected(self):
        self.mutate_json("results/hosted.json", lambda value: value.update(artifact_id=1))
        with self.assertRaisesRegex(ValueError, "hosted identity"):
            saved.verify(self.package, REPO)

    def test_missing_output_rejected(self):
        (self.package / RESULT / "unstripped.so").unlink()
        self.rehash(True)
        with self.assertRaisesRegex(ValueError, "artifact provenance seal"):
            saved.verify(self.package, REPO)


if __name__ == "__main__":
    unittest.main()
