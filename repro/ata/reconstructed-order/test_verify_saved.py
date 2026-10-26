#!/usr/bin/env python3
"""Corrupt saved evidence in temporary copies; never modify retained originals."""
import hashlib
import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import verify_saved

P = Path(__file__).resolve().parent
REFERENCE = P.parents[2] / "evidence/dependencies/associated_token/deployed.so"
RESULTS = "results/run-40287588927/"


class SavedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / "relocated-package"
        shutil.copytree(P, self.package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def replace(self, name, data, rehash=False):
        (self.package / name).write_bytes(data)
        if rehash:
            path = self.package / "manifest.json"
            manifest = json.loads(path.read_bytes())
            manifest["files"][name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def replace_json(self, name, change):
        stored_name = name + ".gz" if name == RESULTS + "source-manifest.json" else name
        raw = (self.package / stored_name).read_bytes()
        data = json.loads(gzip.decompress(raw) if stored_name != name else raw)
        change(data)
        raw = (json.dumps(data, indent=2) + "\n").encode()
        self.replace(stored_name, gzip.compress(raw, mtime=0) if stored_name != name else raw, rehash=True)

    def test_relocated_saved_verification(self):
        result = verify_saved.verify(self.package, REFERENCE)
        self.assertTrue(result["raw_byte_equality"])
        self.assertEqual(result["ordered_differing_positions"], 0)

    def test_compression_container_does_not_change_raw_member_seal(self):
        name = RESULTS + "source-manifest.json.gz"
        raw = gzip.decompress((self.package / name).read_bytes())
        self.replace(name, gzip.compress(raw, compresslevel=1, mtime=1), rehash=True)
        self.assertTrue(verify_saved.verify(self.package, REFERENCE)["raw_byte_equality"])

    def test_invalid_compressed_member_rejected_after_manifest_rehash(self):
        self.replace(RESULTS + "source-manifest.json.gz", b"not gzip", rehash=True)
        with self.assertRaisesRegex(ValueError, "Invalid compressed hosted artifact"):
            verify_saved.verify(self.package, REFERENCE)

    def test_changed_binary_rejects_even_with_rewritten_file_hash(self):
        name = RESULTS + "ordered.so"
        data = bytearray((self.package / name).read_bytes())
        data[28592] ^= 1
        self.replace(name, bytes(data), rehash=True)
        with self.assertRaisesRegex(ValueError, "Raw source-built output differs"):
            verify_saved.verify(self.package, REFERENCE)

    def test_truncated_binary_rejects_even_with_rewritten_file_hash(self):
        name = RESULTS + "ordered.so"
        self.replace(name, (self.package / name).read_bytes()[:-1], rehash=True)
        with self.assertRaisesRegex(ValueError, "Raw source-built output differs"):
            verify_saved.verify(self.package, REFERENCE)

    def test_unsupported_historical_claim_rejected(self):
        self.replace_json(RESULTS + "result.json", lambda data: data.update(historical_uploader_recipe="recovered"))
        with self.assertRaisesRegex(ValueError, "provenance claim changed"):
            verify_saved.verify(self.package, REFERENCE)

    def test_changed_source_lock_rejected(self):
        self.replace_json(RESULTS + "source-manifest.json", lambda data: data.update({"Cargo.lock": "0" * 64}))
        with self.assertRaisesRegex(ValueError, "source/lock"):
            verify_saved.verify(self.package, REFERENCE)

    def test_changed_order_rejected(self):
        name = RESULTS + "symbol-order.txt"
        lines = (self.package / name).read_bytes().splitlines(keepends=True)
        lines[38], lines[39] = lines[39], lines[38]
        self.replace(name, b"".join(lines), rehash=True)
        with self.assertRaisesRegex(ValueError, "Saved order differs"):
            verify_saved.verify(self.package, REFERENCE)

    def test_rehashed_source_provenance_rejected(self):
        self.replace_json(RESULTS + "source-manifest.json", lambda data: data.update({"Cargo.toml": "0" * 64}))
        with self.assertRaisesRegex(ValueError, "provenance seal differs"):
            verify_saved.verify(self.package, REFERENCE)

    def test_rehashed_command_provenance_rejected(self):
        self.replace_json(RESULTS + "commands.json", lambda data: data.append(["fabricated-build"]))
        with self.assertRaisesRegex(ValueError, "provenance seal differs"):
            verify_saved.verify(self.package, REFERENCE)

    def test_rehashed_hosted_artifact_identity_rejected(self):
        self.replace_json("results/hosted-runs.json", lambda data: data["successful"].update(artifact_id=1))
        with self.assertRaisesRegex(ValueError, "Wrong hosted build receipt"):
            verify_saved.verify(self.package, REFERENCE)

    def test_helper_and_rewritten_executed_hashes_rejected(self):
        name = "run.py"
        changed = (self.package / name).read_bytes() + b"\n# substituted helper\n"
        self.replace(name, changed, rehash=True)
        self.replace_json("results/build-inputs.json", lambda data:
                          data["files"][name].update(bytes=len(changed), sha256=hashlib.sha256(changed).hexdigest()))
        with self.assertRaisesRegex(ValueError, "Executed-input provenance seal differs"):
            verify_saved.verify(self.package, REFERENCE)

    def test_omitted_failed_attempt_rejected(self):
        (self.package / "results/run-40286252822/result.json").unlink()
        with self.assertRaises(FileNotFoundError):
            verify_saved.verify(self.package, REFERENCE)

    def test_manifest_path_escape_rejected(self):
        path = self.package / "manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["files"] = {"../outside": {"bytes": 0, "sha256": "0" * 64}}
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unsafe manifest path"):
            verify_saved.verify(self.package, REFERENCE)


if __name__ == "__main__":
    unittest.main()
