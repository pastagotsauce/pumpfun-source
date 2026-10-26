"""Static receipt/source regressions; no SBF execution or synthetic acceptance."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from boost import (PACKAGE, ROOT, SOURCE, SOURCE_SHA, CHANGES, RECEIPT, read_report, digest, prior_source,
                   expected_source, patched_source, normalized_logs, roster, expected_case, check_transaction, sweep)

spec = importlib.util.spec_from_file_location("boost_original_evidence", PACKAGE / "verify_evidence.py")
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class StaticBoostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.config, cls.idl = sweep.fixture_inputs(ROOT)
        cls.report = json.loads(read_report(ROOT / RECEIPT))
        cls.cases = roster(cls.fixture)

    def test_authentic_source_has_only_five_local_substitutions(self):
        before, files = prior_source(ROOT)
        after = expected_source(ROOT)
        self.assertEqual([name for name in before if before[name] != after[name]], [SOURCE])
        raw = files[SOURCE].read_bytes()
        self.assertEqual(digest(raw), SOURCE_SHA)
        changed = patched_source(raw)
        self.assertEqual(digest(changed), "fd74007543769bc7dd27a23f018cc756f20056db6acb7e5cec29cc2df054b148")
        self.assertEqual(len(CHANGES), 5)

    def test_source_patch_applies_once_and_matches_exact_proposal(self):
        _, files = prior_source(ROOT)
        raw = files[SOURCE].read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / SOURCE
            destination.parent.mkdir(parents=True)
            destination.write_bytes(raw)
            subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--check", str(PACKAGE / "source.patch")], cwd=temporary, check=True, capture_output=True)
            subprocess.run(["git", "-c", "core.autocrlf=false", "apply", str(PACKAGE / "source.patch")], cwd=temporary, check=True, capture_output=True)
            self.assertEqual(destination.read_bytes(), patched_source(raw))
            duplicate = subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--check", str(PACKAGE / "source.patch")], cwd=temporary, capture_output=True)
            self.assertNotEqual(duplicate.returncode, 0)

    def test_original_guard_operand_evidence(self):
        self.assertEqual(evidence.verify_original()["original_instruction_bytes"], 2136)

    def test_saved_signatures_and_effects(self):
        verified = evidence.verify_saved()
        self.assertEqual((verified["signature_fields"], verified["numeric_diagnostic_rows"]), (1018, 77))

    def test_same_code_different_zero_gate_is_not_normalized_away(self):
        original = self.report["cases"][0]["original"]["logs"]
        changed = [line.replace("boost.rs:250.", "boost.rs:255.") for line in original]
        self.assertNotEqual(normalized_logs(original), normalized_logs(changed))

    def test_historical_before_state_supports_fifteen_focused_classifications(self):
        indices = [0, 2, 146, 318, 375, 299, 3, 4, 118, 467, 466, 465, 8, 418, None, 39]
        expected = [250, 250, 250, 255, 255, None, 273, 273, 273, 274, None, None, 274, 280, None, None]
        for case, index, site in zip(self.cases, indices, expected):
            if index is not None:
                self.assertEqual(expected_case(case, self.report["cases"][index]["original"]["before"], self.fixture, self.config)[0], site)

    def test_labelled_vault_state_cannot_change(self):
        before = copy.deepcopy(self.report["cases"][0]["original"]["before"])
        pool = before[self.fixture["pool"]]
        raw = bytearray.fromhex(pool["data_hex"])
        raw[245] ^= 1
        pool["data_hex"] = raw.hex()
        with self.assertRaisesRegex(ValueError, "before-state differs"):
            expected_case(self.cases[0], before, self.fixture, self.config)

    def test_exact_slippage_equality_succeeds(self):
        before = self.report["cases"][466]["original"]["before"]
        self.assertEqual(expected_case(self.cases[10], before, self.fixture, self.config), (None, None))
        self.assertEqual(expected_case(self.cases[9], before, self.fixture, self.config), (274, (5435, 5436)))

    def test_signed_amount_is_bound(self):
        raw = base64.b64decode(self.report["cases"][8]["original"]["transaction_base64"])
        self.assertEqual(check_transaction(raw, self.cases[12], self.fixture, self.config, self.idl["boost_buy_and_burn"]), 1)
        wrong = dict(self.cases[12], amount=3)
        with self.assertRaisesRegex(ValueError, "signed instruction"):
            check_transaction(raw, wrong, self.fixture, self.config, self.idl["boost_buy_and_burn"])

    def test_invalid_signature_rejected(self):
        raw = bytearray(base64.b64decode(self.report["cases"][8]["original"]["transaction_base64"]))
        raw[1] ^= 1
        with self.assertRaisesRegex(ValueError, "signature"):
            check_transaction(bytes(raw), self.cases[12], self.fixture, self.config, self.idl["boost_buy_and_burn"])


if __name__ == "__main__":
    unittest.main()
