#!/usr/bin/env python3
"""Mutation tests of actual accepted migration and previous-focused receipts."""
import argparse
import base64
import copy
import json
from pathlib import Path
import unittest

from migration import ROOT, read_report, sweep
from verify_creator import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(read_report(args.built / "runtime.json"))
    candidate = (args.built / "candidate.so").read_bytes()
    record = (args.built / "build-record.json").read_bytes()

    class ActualCreatorTests(unittest.TestCase):
        def reject(self, mutation):
            changed = copy.deepcopy(report)
            mutation(changed)
            with self.assertRaises((ValueError, KeyError)):
                validate(changed, ROOT, candidate, record)

        def test_actual_receipt(self):
            self.assertEqual(validate(report, ROOT, candidate, record)["verified_signatures"], 78)

        def test_candidate_numeric_logs_rejected(self):
            self.reject(lambda r: r["migration"][1]["candidate"]["logs"].append("Program log: Left: 1"))

        def test_prior_defect_must_be_observed(self):
            self.reject(lambda r: r["migration"][1]["prior_sweep"]["logs"].remove("Program log: Left: 1"))

        def test_6081_rejection_cannot_be_waived(self):
            self.reject(lambda r: r["migration"][1]["candidate"].update(error=None))

        def test_holder_precedence_required(self):
            self.reject(lambda r: r["migration"][5]["candidate"].update(error=None))

        def test_fixture_fee_binds_case_label(self):
            def mutate(r):
                fixture, _, _ = sweep.fixture_inputs(ROOT)
                for side in ("original", "prior_sweep", "candidate"):
                    state = r["migration"][3][side]["before"][fixture["pool"]]
                    data = bytearray.fromhex(state["data"])
                    data[279:287] = (1).to_bytes(8, "little")
                    state["data"] = data.hex()
            self.reject(mutate)

        def test_effect_field_cannot_be_deleted_from_all_sides(self):
            self.reject(lambda r: [r["migration"][1][side].pop("inner") for side in ("original", "prior_sweep", "candidate")])

        def test_old_sweep_log_fix_preserved(self):
            self.reject(lambda r: r["regressions"][0]["candidate"]["logs"].remove("Program log: Nothing to sweep for fee bucket 0"))

        def test_old_liquidity_log_fix_preserved(self):
            self.reject(lambda r: r["regressions"][13]["candidate"]["logs"].append("Program log: Left:"))

        def test_invalid_raw_signature_rejected(self):
            def mutate(r):
                tx = r["migration"][1]["candidate"]["transactions"][0]
                raw = bytearray(base64.b64decode(tx["raw_base64"]))
                raw[1] ^= 1
                tx["raw_base64"] = base64.b64encode(raw).decode()
            self.reject(mutate)

        def test_build_record_cannot_impersonate_prior(self):
            self.reject(lambda r: r["build_binding"]["record"].update(kind="liquidity-and-sweep-corrected"))

        def test_missing_case_rejected(self):
            self.reject(lambda r: r["regressions"].pop())

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActualCreatorTests))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
