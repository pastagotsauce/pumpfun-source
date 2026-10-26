#!/usr/bin/env python3
"""Independently check saved sweep execution, signatures and complete logs."""
import argparse
import base64
import json
from pathlib import Path

from recovery import (PACKAGE, ROOT, PRIOR, ORIGINAL_SHA, BASELINE_SHA, PRIOR_SHA,
                      PROBE_SHA, BASE_RECORD_SHA, PRIOR_RECORD_SHA, INPUTS, OUTSIDER,
                      digest, require, liquidity, read_report, check_build,
                      fixture_inputs, roster, check_transaction)

OBSERVED_SHA = "546bf6998ff0c001c993fc9122feab5f1af63a48bad2532bfd23a5bb3ceb5182"


def validate(report, repo, candidate=None, build_record=None, observed=False):
    require(report["status"] == "completed" and report["failure"] is None, "incomplete or failed execution")
    binaries = {"original": ORIGINAL_SHA, "baseline": BASELINE_SHA, "liquidity_corrected": PRIOR_SHA} if observed else {
        "original": ORIGINAL_SHA, "liquidity_corrected": PRIOR_SHA, "combined_corrected": digest(candidate)}
    require(report["binary_sha256"] == binaries, "binary binding mismatch")
    require(digest((repo / "evidence/original/pump_amm/deployed.so").read_bytes()) == ORIGINAL_SHA, "original changed")
    require(set(report["input_sha256"]) == INPUTS and
            all(digest((repo / path).read_bytes()) == sha for path, sha in report["input_sha256"].items()), "probe inputs changed")
    if observed:
        require(report["probe_sha256"] == digest((PACKAGE / "probe.py").read_bytes()) == PROBE_SHA, "executed observer changed")
        require(report["build_record_sha256"] == {"baseline": BASE_RECORD_SHA, "corrected": PRIOR_RECORD_SHA}, "wrong prior build records")
        for kind, expected in (("baseline", BASE_RECORD_SHA), ("corrected", PRIOR_RECORD_SHA)):
            require(digest((PRIOR / "results/build" / kind / "build-record.json").read_bytes()) == expected, "prior record changed")
    else:
        record = check_build(repo, candidate, build_record)
        require(report["build_binding"] == {"sha256": digest(build_record), "record": record}, "combined build binding mismatch")
        require(report["probe_sha256"] == digest((PACKAGE / "runtime_probe.py").read_bytes()), "different probe")
        require(report["checker_sha256"] == {name: digest((PACKAGE / name).read_bytes()) for name in ("recovery.py", "verify_sweep.py")},
                "different acceptance helpers")
        require(report["prior_build_record_sha256"] == PRIOR_RECORD_SHA, "wrong prior binary provenance")
    expected_roster = roster(creator=not observed)
    count = len(expected_roster)
    require(report["planned_case_count"] == report["completed_case_count"] == len(report["cases"]) == count and
            report["planned_transaction_count"] == report["transaction_count"] == count * 3, "incomplete case/transaction counts")
    fixture, config, idl = fixture_inputs(repo)
    transactions, rejected, zero = [], 0, 0
    for index, (row, identity) in enumerate(zip(report["cases"], expected_roster)):
        require((row["instruction"], row["mode"], row["amount"]) == identity, f"case {index}: wrong roster")
        rejected_case = row["mode"] == "alias_wrong_owner" and row["amount"] != 0
        expected_error = liquidity.ERROR if rejected_case else None
        rejected += rejected_case
        zero += row["amount"] == 0
        original = row["original"]
        require(set(original) == {"error", "states", "inner", "logs", "transactions"}, "unexpected result shape")
        zero_log = "Program log: Nothing to sweep for fee bucket " + ("1" if row["instruction"] == "sweep_creator_fee" else "0")
        require(original["logs"].count(zero_log) == (1 if row["amount"] == 0 else 0), "original zero-bucket disposition changed")
        require(not liquidity.compared_keys(original["logs"]), "original compared-key diagnostic appeared")
        if rejected_case:
            require(any(liquidity.ORIGIN in line and "Error Number: 6087." in line for line in original["logs"]), "original 6087 origin changed")
        pair = []
        for side in binaries:
            result = row[side]
            require(set(result) == set(original), "incomplete result shape")
            require(result["error"] == expected_error, f"case {index}/{side}: unexpected error")
            require(all(result[k] == original[k] for k in ("error", "states", "inner")), "committed effects differ")
            logs = list(result["logs"])
            baseline = side in ("baseline", "liquidity_corrected")
            if baseline and rejected_case:
                expected_keys = ["Program log: Left:", f"Program log: {OUTSIDER}", "Program log: Right:", f"Program log: {fixture['pool']}"]
                require(liquidity.compared_keys(logs) == expected_keys, "baseline compared-key mismatch changed")
                start = logs.index("Program log: Left:")
                del logs[start:start + 4]
            expected_logs = list(original["logs"])
            if baseline and row["amount"] == 0:
                require(zero_log not in logs, "baseline missing-zero-log observation changed")
                expected_logs.remove(zero_log)
            require(liquidity.normalized_logs(logs) == liquidity.normalized_logs(expected_logs),
                    f"case {index}/{side}: full log difference beyond expressly recorded prior defects")
            require(len(result["transactions"]) == 1, "wrong transaction count")
            transaction = result["transactions"][0]
            raw = base64.b64decode(transaction["raw_base64"], validate=True)
            require(check_transaction(raw, row, fixture, config, idl[row["instruction"]]) == transaction["verified_signature_count"] == 1,
                    "signature count mismatch")
            transactions.append(raw)
            pair.append(raw)
        require(len(set(pair)) == 1, "binaries received different signed messages")
    require(rejected == 2 and zero == (3 if observed else 4), "wrong rejection/zero-control aggregate")
    return {"cases": count, "rejections_per_binary": rejected, "successful_controls_per_binary": count - rejected,
            "zero_bucket_controls_per_binary": zero, "verified_signatures": len(transactions),
            "unique_transaction_bytes": len(set(transactions)), "combined_correction_checked": not observed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, default=PACKAGE / "observed/runtime.json.gz")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--build-record", type=Path)
    parser.add_argument("--observed", action="store_true")
    args = parser.parse_args()
    raw = read_report(args.report)
    if args.observed:
        require(digest(raw) == OBSERVED_SHA, "original observation receipt changed")
    result = validate(json.loads(raw), args.repo.resolve(), args.candidate.read_bytes() if args.candidate else None,
                      args.build_record.read_bytes() if args.build_record else None, args.observed)
    print(json.dumps({"receipt_sha256": digest(raw), **result}, indent=2))


if __name__ == "__main__":
    main()
