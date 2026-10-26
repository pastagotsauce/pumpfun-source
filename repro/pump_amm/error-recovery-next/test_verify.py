#!/usr/bin/env python3
"""Mutation tests for the retained-log evidence and narrowly scoped comparison."""
import copy
import gzip
import json
from pathlib import Path
import unittest

import verify


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compressed = (verify.ROOT / verify.RECEIPT).read_bytes()
        cls.saved = json.loads(gzip.decompress(cls.compressed))
        cls.image = (verify.ROOT / "evidence/original/pump_amm/deployed.so").read_bytes()
        cls.assembly = (verify.PACKAGE / "original-guard.asm").read_text()

    def test_authentic_retained_receipt_and_guard(self):
        self.assertEqual(len(verify.verify_receipt_bytes(self.compressed)), 4)
        self.assertEqual(verify.verify_original_window(self.image, self.assembly)["bytes"], 656)

    def test_changed_receipt_rejected_before_parsing(self):
        altered = bytearray(self.compressed)
        altered[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "compressed receipt changed"):
            verify.verify_receipt_bytes(altered)

    def test_missing_case_rejected(self):
        data = copy.deepcopy(self.saved)
        data["cases"][223]["original"]["error"] = None
        with self.assertRaisesRegex(ValueError, "missing or duplicate"):
            verify.inspect_saved(data)

    def test_original_compared_keys_rejected(self):
        data = copy.deepcopy(self.saved)
        data["cases"][223]["original"]["logs"].extend([
            "Program log: Left:", "Program log: A", "Program log: Right:", "Program log: B"])
        with self.assertRaisesRegex(ValueError, "original contains"):
            verify.inspect_saved(data)

    def test_missing_candidate_diagnostic_rejected(self):
        data = copy.deepcopy(self.saved)
        logs = data["cases"][223]["candidate"]["logs"]
        start = logs.index("Program log: Left:")
        del logs[start:start + 4]
        with self.assertRaisesRegex(ValueError, "unexpected baseline compared keys"):
            verify.inspect_saved(data)

    def test_effect_regression_not_hidden_by_log_analysis(self):
        data = copy.deepcopy(self.saved)
        data["cases"][223]["candidate"]["pool_supply"] += 1
        with self.assertRaisesRegex(ValueError, "non-log output differs"):
            verify.inspect_saved(data)

    def test_additional_candidate_log_not_ignored(self):
        data = copy.deepcopy(self.saved)
        data["cases"][223]["candidate"]["logs"].append("Program log: unexpected CPI effect")
        with self.assertRaisesRegex(ValueError, "difference extends beyond"):
            verify.inspect_saved(data)

    def test_wrong_original_program_binding_rejected(self):
        data = copy.deepcopy(self.saved)
        data["original_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "wrong original binding"):
            verify.inspect_saved(data)

    def test_disassembly_omission_rejected(self):
        lines = self.assembly.splitlines()
        del lines[5]
        with self.assertRaisesRegex(ValueError, "incomplete/overlapping"):
            verify.verify_original_window(self.image, "\n".join(lines))

    def test_disassembly_byte_corruption_rejected(self):
        altered = self.assembly.replace("bf 57 00 00", "bf 56 00 00", 1)
        with self.assertRaisesRegex(ValueError, "do not match original"):
            verify.verify_original_window(self.image, altered)

    def test_normalization_preserves_meaningful_logs(self):
        logs = ["Program log: Left:", "Program log: Right:", "Program data: abc",
                "Program log: consumed 1 of 2 compute units", "Program X consumed 1 of 2 compute units",
                "Program log: AnchorError thrown in src/x.rs:1. Error Code: Other. Error Number: 2006. Error Message: Other"]
        result = verify.normalized_logs(logs)
        self.assertEqual(result, logs[:4] + logs[5:])

    def test_withdrawal_quote_rounds_to_zero_before_guard(self):
        economics = verify.fixture_economics((verify.ROOT / verify.FIXTURE_PATH).read_bytes())
        quote = {"instruction": "withdraw", "user_account_index": 7, "amount": 1, "wrong_withdraw_owner": True}
        self.assertEqual(verify.expected_transfer(quote, economics), (0, None))
        self.assertEqual(verify.expected_transfer(quote | {"instruction": "deposit"}, economics), (1, verify.ERROR))
        self.assertEqual(verify.expected_transfer(quote | {"user_account_index": 6}, economics), (160, verify.ERROR))
        self.assertEqual(verify.expected_transfer(quote | {"amount": 1000000}, economics), (29312, verify.ERROR))

    def test_quantity_rounding_does_not_waive_other_wrong_owners(self):
        economics = verify.fixture_economics((verify.ROOT / verify.FIXTURE_PATH).read_bytes())
        outcomes = []
        for instruction, wrong in (("deposit", False), ("withdraw", False), ("withdraw", True)):
            for account in (6, 7):
                for amount in (0, 1, 1000000):
                    row = {"instruction": instruction, "user_account_index": account, "amount": amount, "wrong_withdraw_owner": wrong}
                    outcomes.append(verify.expected_transfer(row, economics)[1])
        self.assertEqual([i for i, error in enumerate(outcomes) if error], [1, 2, 4, 5, 13, 14, 17])


if __name__ == "__main__":
    unittest.main()
