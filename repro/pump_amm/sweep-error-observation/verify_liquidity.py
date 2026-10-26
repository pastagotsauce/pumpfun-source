#!/usr/bin/env python3
"""Accept the unchanged 18-case probe against the explicit combined source build.

The original package's sealed validator deliberately allows only its historical
one-file change. This wrapper preserves the new record and checks the two-file
source manifest, then independently repeats its receipt and signature gates.
"""
import argparse
import base64
import json
from pathlib import Path

from recovery import (ROOT, PRIOR, ORIGINAL_SHA, digest, require, liquidity,
                      liquidity_runtime as old, read_report, check_build, fixture_inputs)


def validate(report, repo, candidate, record_bytes):
    record = check_build(repo, candidate, record_bytes)
    require(report["build_binding"] == {"sha256": digest(record_bytes), "record": record}, "changed build binding")
    require(report["problems"] == [] and report["mode"] == "corrected" and report["case_count"] == len(report["cases"]) == 18,
            "failed or incomplete liquidity run")
    require(report["candidate_sha256"] == digest(candidate) and report["original_sha256"] == ORIGINAL_SHA and
            digest((repo / "evidence/original/pump_amm/deployed.so").read_bytes()) == ORIGINAL_SHA, "wrong binaries")
    require(report["probe_sha256"] == digest((PRIOR / "runtime_probe.py").read_bytes()) and
            report["comparison_helper_sha256"] == digest((PRIOR / "verify.py").read_bytes()), "prior probe/helper changed")
    require(set(report["input_sha256"]) == old.INPUTS and
            all(digest((repo / path).read_bytes()) == sha for path, sha in report["input_sha256"].items()), "harness binding mismatch")
    fixture, config, idl = fixture_inputs(repo)
    economics = liquidity.fixture_economics((repo / liquidity.FIXTURE_PATH).read_bytes())
    require(report["fixture_economics"] == economics, "different fixture economics")
    roster = [(instruction, account, amount, wrong)
              for instruction, wrong in (("deposit", False), ("withdraw", False), ("withdraw", True))
              for account in (6, 7) for amount in (0, 1, 1000000)]
    transactions, rejected = [], 0
    for row, identity in zip(report["cases"], roster):
        require(type(row["wrong_withdraw_owner"]) is bool and
                (row["instruction"], row["user_account_index"], row["amount"], row["wrong_withdraw_owner"]) == identity,
                "wrong liquidity case roster")
        quantity, expected_error = liquidity.expected_transfer(row, economics)
        require(row["expected_aliased_transfer_quantity"] == quantity, "wrong rounding classification")
        rejected += expected_error is not None
        original, corrected = row["original"], row["candidate"]
        effects = lambda data: {key: value for key, value in data.items() if key not in ("logs", "transactions")}
        require(original["error"] == corrected["error"] == expected_error and effects(original) == effects(corrected) and
                row["effect_differences"] == [], "liquidity effects differ")
        require(liquidity.normalized_logs(original["logs"]) == liquidity.normalized_logs(corrected["logs"]) and
                row["normalized_logs_equal"] is True, "liquidity full logs differ")
        require(not liquidity.compared_keys(original["logs"]) and not liquidity.compared_keys(corrected["logs"]), "compared keys returned")
        if expected_error:
            require(any(liquidity.ORIGIN in line and "Error Number: 6087." in line for line in original["logs"]), "missing original origin")
        pair = []
        for result in (original, corrected):
            require(len(result["transactions"]) == 1, "wrong transaction count")
            tx = result["transactions"][0]
            raw = base64.b64decode(tx["raw_base64"], validate=True)
            require(old.check_transaction(raw, row, fixture, config["address"], bytes(idl[row["instruction"]]["discriminator"])) ==
                    tx["verified_signature_count"] == 1, "wrong signature count")
            transactions.append(raw)
            pair.append(raw)
        require(pair[0] == pair[1], "different signed inputs")
    require(rejected == 7 and report["transaction_count"] == report["signature_count"] == len(transactions) == 36,
            "incomplete liquidity aggregate")
    return {"cases": 18, "rejections": 7, "successful_controls": 11, "verified_signatures": 36,
            "unique_transaction_bytes": len(set(transactions)), "combined_source_explicitly_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-record", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(json.loads(read_report(args.report)), args.repo.resolve(), args.candidate.read_bytes(),
                              args.build_record.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
