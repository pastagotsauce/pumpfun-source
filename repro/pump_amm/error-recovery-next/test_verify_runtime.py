#!/usr/bin/env python3
"""Negative acceptance tests against an actual successful retained probe receipt."""
import argparse
import base64
import copy
import json
from pathlib import Path
import sys
import unittest

import verify_runtime


class RuntimeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.report = copy.deepcopy(REPORT)

    def accept(self):
        return verify_runtime.validate(self.report, REPO, CANDIDATE, BUILD)

    def test_actual_receipt(self):
        result = self.accept()
        self.assertEqual((result["cases"], result["rejections"], result["verified_signatures"]), (18, 7, 36))

    def test_failed_run_cannot_be_relabelled_by_checker(self):
        self.report["problems"] = ["recorded failure"]
        with self.assertRaisesRegex(ValueError, "failed run"):
            self.accept()

    def test_missing_case(self):
        self.report["cases"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete focused"):
            self.accept()

    def test_duplicate_case(self):
        self.report["cases"][1] = self.report["cases"][0]
        with self.assertRaisesRegex(ValueError, "omitted, duplicated or wrong"):
            self.accept()

    def test_raw_signature_mutation(self):
        record = self.report["cases"][0]["candidate"]["transactions"][0]
        raw = bytearray(base64.b64decode(record["raw_base64"]))
        raw[1] ^= 1
        record["raw_base64"] = base64.b64encode(raw).decode()
        with self.assertRaisesRegex(ValueError, "invalid raw transaction signature"):
            self.accept()

    def test_claimed_count_cannot_replace_raw_signature(self):
        self.report["cases"][0]["candidate"]["transactions"] = []
        with self.assertRaisesRegex(ValueError, "missing/extra transaction"):
            self.accept()

    def test_effect_change(self):
        self.report["cases"][0]["candidate"]["pool_supply"] += 1
        with self.assertRaisesRegex(ValueError, "effects differ"):
            self.accept()

    def test_extra_log_not_normalized_away(self):
        self.report["cases"][0]["candidate"]["logs"].append("Program log: unexpected diagnostic")
        with self.assertRaisesRegex(ValueError, "log equality|logs differ"):
            self.accept()

    def test_zero_quantity_case_is_not_a_blanket_error_waiver(self):
        self.report["cases"][16]["expected_aliased_transfer_quantity"] = 1
        with self.assertRaisesRegex(ValueError, "wrong transfer classification"):
            self.accept()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=verify_runtime.ROOT)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-record", type=Path)
    args = parser.parse_args()
    REPO, REPORT, CANDIDATE = args.repo.resolve(), json.loads(args.report.read_text()), args.candidate.read_bytes()
    BUILD = args.build_record.read_bytes() if args.build_record else None
    unittest.main(argv=[sys.argv[0]])
