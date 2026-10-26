#!/usr/bin/env python3
"""Mutation tests of an actual completed boost/previous-focused receipt."""
import argparse
import base64
import copy
import json
from pathlib import Path
import unittest

from boost import ROOT, read_report, sweep
from verify_boost import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(read_report(args.built / "runtime.json"))
    candidate = (args.built / "candidate.so").read_bytes()
    record = (args.built / "build-record.json").read_bytes()

    class ActualBoostTests(unittest.TestCase):
        def reject(self, mutation):
            changed = copy.deepcopy(report)
            mutation(changed)
            with self.assertRaises((ValueError, KeyError)):
                validate(changed, ROOT, candidate, record)

        def test_actual_receipt(self):
            self.assertEqual(validate(report, ROOT, candidate, record)["verified_signatures"], 120)

        def test_missing_numeric_value_rejected(self):
            self.reject(lambda r: r["boost"][0]["candidate"]["logs"].remove("Program log: Left: 0"))

        def test_spurious_success_numeric_value_rejected(self):
            self.reject(lambda r: r["boost"][10]["candidate"]["logs"].append("Program log: Left: 5435"))

        def test_variable_operand_order_is_preserved(self):
            def mutate(r):
                logs = r["boost"][9]["candidate"]["logs"]
                logs[logs.index("Program log: Left: 5435")] = "Program log: Left: 5436"
                logs[logs.index("Program log: Right: 5436")] = "Program log: Right: 5435"
            self.reject(mutate)

        def test_used_zero_cannot_be_relabeled_as_net_zero(self):
            self.reject(lambda r: r["boost"][0]["candidate"].update(logs=[line.replace("src/boost_burn.rs:41.", "src/boost_burn.rs:50.")
                                                                          for line in r["boost"][0]["candidate"]["logs"]]))

        def test_prior_numeric_omission_must_be_observed(self):
            self.reject(lambda r: r["boost"][0]["prior_creator"]["logs"].append("Program log: Left: 0"))

        def test_equality_success_cannot_be_waived(self):
            self.reject(lambda r: r["boost"][10]["candidate"].update(error="slippage"))

        def test_zero_gate_rejection_cannot_be_waived(self):
            self.reject(lambda r: r["boost"][0]["candidate"].update(error=None))

        def test_before_state_binds_label_on_all_sides(self):
            def mutate(r):
                fixture, _, _ = sweep.fixture_inputs(ROOT)
                for side in ("original", "prior_creator", "candidate"):
                    state = r["boost"][0][side]["before"][fixture["pool"]]
                    raw = bytearray.fromhex(state["data_hex"])
                    raw[245] ^= 1
                    state["data_hex"] = raw.hex()
            self.reject(mutate)

        def test_effect_field_cannot_be_deleted_from_all_sides(self):
            self.reject(lambda r: [r["boost"][0][side].pop("inner") for side in ("original", "prior_creator", "candidate")])

        def test_raw_signature_rejected_when_corrupted(self):
            def mutate(r):
                tx = r["boost"][0]["candidate"]["transactions"][0]
                raw = bytearray(base64.b64decode(tx["raw_base64"]))
                raw[1] ^= 1
                tx["raw_base64"] = base64.b64encode(raw).decode()
            self.reject(mutate)

        def test_build_record_cannot_impersonate_prior(self):
            self.reject(lambda r: r["build_binding"]["record"].update(kind="liquidity-sweep-migration-corrected"))

        def test_migration_fix_preserved(self):
            self.reject(lambda r: r["migration"][1]["candidate"]["logs"].append("Program log: Left: 1"))

        def test_sweep_fix_preserved(self):
            self.reject(lambda r: r["regressions"][0]["candidate"]["logs"].remove("Program log: Nothing to sweep for fee bucket 0"))

        def test_liquidity_fix_preserved(self):
            self.reject(lambda r: r["regressions"][13]["candidate"]["logs"].append("Program log: Left:"))

        def test_missing_case_rejected(self):
            self.reject(lambda r: r["boost"].pop())

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActualBoostTests))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
