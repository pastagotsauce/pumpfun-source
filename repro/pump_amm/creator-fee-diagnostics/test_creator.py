"""Preflight tests on authentic evidence, signatures and exact patch scope."""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from migration import (PACKAGE, ROOT, SOURCE, RECEIPT, patched_source, prior_source,
                       migration_transaction, normalized_logs, read_report, sweep)
from verify_creator import verify_saved, verify_original


class CreatorEvidenceTests(unittest.TestCase):
    def test_saved_signed_original_and_candidate(self):
        self.assertEqual(verify_saved(), {"saved_rows": [105, 106], "raw_signatures": 4, "unique_messages": 1})

    def test_original_error_block(self):
        self.assertEqual(verify_original()["original_instruction_bytes"], 464)

    def test_context_patch_applies_once(self):
        _, inputs = prior_source(ROOT)
        raw = inputs[SOURCE].read_bytes()
        with tempfile.TemporaryDirectory(prefix="amm-creator-patch-") as folder:
            target = Path(folder) / SOURCE
            target.parent.mkdir(parents=True)
            target.write_bytes(raw)
            command = ["git", "-c", "core.autocrlf=false", "apply"]
            subprocess.run(command + [str(PACKAGE / "source.patch")], cwd=folder, capture_output=True, check=True)
            self.assertEqual(target.read_bytes(), patched_source(raw))
            self.assertNotEqual(subprocess.run(command + ["--check", str(PACKAGE / "source.patch")], cwd=folder, capture_output=True).returncode, 0)

    def test_admin_guard_unchanged(self):
        _, inputs = prior_source(ROOT)
        raw = inputs[SOURCE].read_bytes()
        changed = patched_source(raw)
        self.assertEqual(raw.split(b"pub fn admin_cto", 1)[1], changed.split(b"pub fn admin_cto", 1)[1])
        self.assertEqual(changed.count(b"require_eq!(pool.creator_fees,0,PumpAmmError::CreatorFeesNotSwept)"), 1)

    def test_missing_migrate_context_rejected(self):
        _, inputs = prior_source(ROOT)
        with self.assertRaises(ValueError):
            patched_source(inputs[SOURCE].read_bytes().replace(b"pub fn migrate(", b"pub fn different("))

    def test_wrong_number_of_duplicate_guards_rejected(self):
        _, inputs = prior_source(ROOT)
        with self.assertRaises(ValueError):
            patched_source(inputs[SOURCE].read_bytes() + b" require_eq!(pool.creator_fees,0,PumpAmmError::CreatorFeesNotSwept);")

    def test_raw_signature_corruption_rejected(self):
        report = json.loads(read_report(ROOT / RECEIPT))
        raw = bytearray(base64.b64decode(report["cases"][105]["original"]["transaction_base64"]))
        raw[1] ^= 1
        fixture, _, idl = sweep.fixture_inputs(ROOT)
        with self.assertRaises(ValueError):
            migration_transaction(bytes(raw), fixture, idl)

    def test_numeric_decoration_is_not_normalized(self):
        self.assertNotEqual(normalized_logs(["Program log: Left: 1"]), normalized_logs([]))

    def test_unrelated_error_source_is_not_normalized(self):
        line = "Program log: AnchorError thrown in src/example.rs:1. Error Code: Overflow. Error Number: 6000. Error Message: overflow."
        self.assertEqual(normalized_logs([line]), [line])

    def test_explicit_holder_coordinate_normalization(self):
        a = "Program log: AnchorError thrown in original.rs:52. Error Code: HolderRewardCreatorImmutable. Error Number: 6074. Error Message: same."
        b = a.replace("original.rs:52", "reconstructed.rs:31")
        self.assertEqual(normalized_logs([a]), normalized_logs([b]))


if __name__ == "__main__":
    unittest.main()
