#!/usr/bin/env python3
"""Mutation-test accepted actual combined-build receipts; never simulate execution."""
import argparse
import copy
import json
from pathlib import Path
import unittest

from recovery import ROOT, read_report
import verify_sweep
import verify_liquidity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=Path, required=True, help="Directory containing candidate.so/build-record.json and both focused reports")
    args = parser.parse_args()
    binary = (args.built / "candidate.so").read_bytes()
    record = (args.built / "build-record.json").read_bytes()
    sweep = json.loads(read_report(args.built / "sweep-runtime.json"))
    liquidity = json.loads(read_report(args.built / "liquidity-runtime.json"))

    class ActualReceiptTests(unittest.TestCase):
        def reject(self, kind, mutate):
            report = copy.deepcopy(sweep if kind == "sweep" else liquidity)
            mutate(report)
            checker = verify_sweep.validate if kind == "sweep" else verify_liquidity.validate
            with self.assertRaises((ValueError, KeyError)):
                checker(report, ROOT, binary, record)

        def test_actual_sweep(self):
            self.assertEqual(verify_sweep.validate(sweep, ROOT, binary, record)["verified_signatures"], 36)

        def test_actual_liquidity(self):
            self.assertEqual(verify_liquidity.validate(liquidity, ROOT, binary, record)["verified_signatures"], 36)

        def test_restored_zero_log_required(self):
            self.reject("sweep", lambda r: r["cases"][0]["combined_corrected"]["logs"].remove("Program log: Nothing to sweep for fee bucket 0"))

        def test_creator_bucket_one_required(self):
            self.reject("sweep", lambda r: r["cases"][9]["combined_corrected"]["logs"].remove("Program log: Nothing to sweep for fee bucket 1"))

        def test_sweep_keys_cannot_return(self):
            self.reject("sweep", lambda r: r["cases"][7]["combined_corrected"]["logs"].append("Program log: Left:"))

        def test_liquidity_logs_remain_checked(self):
            self.reject("liquidity", lambda r: r["cases"][1]["candidate"]["logs"].append("Program log: unexpected"))

        def test_zero_rounding_control_cannot_be_reclassified(self):
            self.reject("liquidity", lambda r: r["cases"][16].update(expected_aliased_transfer_quantity=1))

        def test_build_record_cannot_be_spoofed(self):
            self.reject("liquidity", lambda r: r["build_binding"]["record"].update(kind="corrected"))

        def test_extra_source_change_rejected(self):
            bad = json.loads(record)
            bad["source_sha256"]["programs/pump-amm/Cargo.toml"] = "0" * 64
            with self.assertRaises(ValueError):
                verify_sweep.validate(sweep, ROOT, binary, json.dumps(bad).encode())

        def test_missing_new_case_rejected(self):
            self.reject("sweep", lambda r: r["cases"].pop())

        def test_liquidity_transaction_cannot_be_omitted(self):
            self.reject("liquidity", lambda r: r["cases"][1]["candidate"].update(transactions=[]))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ActualReceiptTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
