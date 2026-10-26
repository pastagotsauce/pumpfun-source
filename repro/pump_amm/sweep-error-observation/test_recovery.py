#!/usr/bin/env python3
"""Mutation checks against actual retained observations, plus exact source scope."""
import base64
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from recovery import PACKAGE, ROOT, SWEEP, digest, read_report, prior_source, patched_sweep
from verify_sweep import validate
from verify_evidence import original_window, observed_archive


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(read_report(PACKAGE / "observed/runtime.json.gz"))

    def reject(self, mutate):
        report = copy.deepcopy(self.report)
        mutate(report)
        with self.assertRaises((ValueError, KeyError)):
            validate(report, ROOT, observed=True)

    def test_actual_observation(self):
        result = validate(self.report, ROOT, observed=True)
        self.assertEqual((result["cases"], result["verified_signatures"], result["rejections_per_binary"]), (9, 27, 2))

    def test_removed_zero_log(self):
        self.reject(lambda r: r["cases"][0]["original"]["logs"].remove("Program log: Nothing to sweep for fee bucket 0"))

    def test_unexpected_log_is_not_filtered(self):
        self.reject(lambda r: r["cases"][1]["liquidity_corrected"]["logs"].append("Program log: unexpected"))

    def test_baseline_diagnostic_is_required(self):
        self.reject(lambda r: r["cases"][7]["baseline"]["logs"].remove("Program log: Left:"))

    def test_wrong_error(self):
        self.reject(lambda r: r["cases"][7]["original"].update(error=None))

    def test_changed_state(self):
        self.reject(lambda r: r["cases"][1]["liquidity_corrected"].update(states={}))

    def test_missing_case(self):
        self.reject(lambda r: r["cases"].pop())

    def test_duplicate_case(self):
        self.reject(lambda r: r["cases"].__setitem__(1, copy.deepcopy(r["cases"][0])))

    def test_failed_execution(self):
        self.reject(lambda r: r.update(status="failed", failure="test"))

    def test_corrupt_raw_signature(self):
        def change(r):
            tx = r["cases"][0]["original"]["transactions"][0]
            raw = bytearray(base64.b64decode(tx["raw_base64"]))
            raw[1] ^= 1
            tx["raw_base64"] = base64.b64encode(raw).decode()
        self.reject(change)

    def test_missing_transaction(self):
        self.reject(lambda r: r["cases"][0]["original"].update(transactions=[]))

    def test_wrong_fixture_binding(self):
        self.reject(lambda r: r["input_sha256"].pop(next(iter(r["input_sha256"]))))

    def test_original_instructions_and_provenance(self):
        result = original_window((ROOT / "evidence/original/pump_amm/deployed.so").read_bytes(),
                                 (PACKAGE / "original-zero-branch.asm").read_text())
        self.assertEqual(result["zero_branch"], "0x59c58 -> 0x59e28")
        self.assertEqual(observed_archive()["hosted_members"], 2)

    def test_exact_patch_applies_only_once(self):
        _, source = prior_source(ROOT)
        raw = source[SWEEP].read_bytes()
        with tempfile.TemporaryDirectory(prefix="amm-sweep-patch-") as folder:
            target = Path(folder) / SWEEP
            target.parent.mkdir(parents=True)
            target.write_bytes(raw)
            subprocess.run(["git", "-c", "core.autocrlf=false", "apply", str(PACKAGE / "source.patch")], cwd=folder, check=True, capture_output=True)
            self.assertEqual(target.read_bytes(), patched_sweep(raw))
            result = subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--check", str(PACKAGE / "source.patch")], cwd=folder, capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
