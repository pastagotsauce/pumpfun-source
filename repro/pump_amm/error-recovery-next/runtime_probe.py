#!/usr/bin/env python3
"""Signed offline self-transfer probe preserving full logs and transaction bytes.

Requires a Linux solders wheel with LiteSVM. No RPC or deployment is performed.
"""
import argparse
import base64
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

from verify import (BASELINE_SHA, ORIGINAL_SHA, SOURCE_SHA, digest, normalized_logs,
                    require, compared_keys, fixture_economics, expected_transfer, FIXTURE_PATH)

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--expect", choices=("baseline", "rebuilt-baseline", "corrected"), required=True)
    parser.add_argument("--build-record", type=Path, help="Required for rebuilt-baseline; binds a successful unchanged-source build")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repo.resolve()
    candidate = args.candidate.resolve()
    output = args.output.resolve()
    require(not output.exists(), "output already exists")
    original = root / "evidence/original/pump_amm/deployed.so"
    require(digest(original.read_bytes()) == ORIGINAL_SHA, "original binary changed")
    require(digest(candidate.read_bytes()) == args.candidate_sha256, "candidate hash mismatch")
    if args.expect == "baseline":
        require(args.candidate_sha256 == BASELINE_SHA, "baseline must be selected 09be candidate")
    build_binding = None
    if args.build_record:
        record_bytes = args.build_record.read_bytes()
        record = json.loads(record_bytes)
        require(record["candidate_sha256"] == args.candidate_sha256 and record["returncode"] == 0,
                "build record does not bind successful candidate")
        require(record["source_unchanged"] is True, "build inputs changed")
        if args.expect == "rebuilt-baseline":
            require(record["kind"] == "baseline" and
                    record["source_sha256"]["programs/pump-amm/src/lib.rs"] == SOURCE_SHA,
                    "rebuilt baseline source binding mismatch")
        build_binding = {"sha256": digest(record_bytes), "record": record}
    require(args.expect != "rebuilt-baseline" or build_binding is not None,
            "rebuilt-baseline requires --build-record")
    inputs = [
        "scripts/pump_amm_liquidity_differential.py",
        "scripts/pump_amm_admin_differential.py", "scripts/pump_amm_reusable_harness.py",
        "research/imported-lab/analysis/pump_fun/config-snapshot.json",
        "research/imported-lab/analysis/pump_fun/amm-v2-trade-fixture.json",
        "evidence/upstream/pump_amm.json",
        "evidence/dependencies/spl_token/deployed.so",
        "evidence/dependencies/spl_token_2022/deployed.so",
    ]
    input_hashes = {path: digest((root / path).read_bytes()) for path in inputs}
    economics = fixture_economics((root / FIXTURE_PATH).read_bytes())
    os.chdir(root)  # The existing fixture loader uses repo-relative paths.
    sys.path.insert(0, str(root / "scripts"))
    import pump_amm_liquidity_differential as harness
    import pump_amm_reusable_harness as reusable
    import solders.solders as native

    transactions = []
    send_transaction = reusable._ResettableVM.send_transaction

    def observe(self, transaction):
        transaction.verify()
        transactions.append({"raw_base64": base64.b64encode(bytes(transaction)).decode(),
                             "verified_signature_count": len(transaction.signatures)})
        return send_transaction(self, transaction)

    reusable._ResettableVM.send_transaction = observe
    rows = []
    try:
        for instruction, wrong_withdraw_owner in (("deposit", False), ("withdraw", False), ("withdraw", True)):
            for user_index, vault_index in ((6, 9), (7, 10)):
                for amount in (0, 1, 1000000):
                    def alias(h, metas, ui=user_index, vi=vault_index, wrong=wrong_withdraw_owner):
                        metas[ui] = harness.AccountMeta(metas[vi].pubkey, False, True)
                        if wrong:
                            harness.mutate(metas[vi].pubkey, 32, bytes(harness.OUTSIDER.pubkey()))(h, metas)
                    row = {"instruction": instruction, "user_account_index": user_index,
                           "amount": amount, "wrong_withdraw_owner": wrong_withdraw_owner}
                    for side, binary in (("original", original), ("candidate", candidate)):
                        transactions.clear()
                        result = harness.run(instruction, amount, maxbase=0 if instruction == "withdraw" else 2**64 - 1,
                                             maxquote=0 if instruction == "withdraw" else 2**64 - 1,
                                             overrides=alias, candidate=binary)
                        result["transactions"] = list(transactions)
                        row[side] = result
                    excluded = {"logs", "transactions"}
                    row["effect_differences"] = [key for key in row["original"] if key not in excluded
                                                 and row["original"][key] != row["candidate"][key]]
                    row["normalized_logs_equal"] = normalized_logs(row["original"]["logs"]) == normalized_logs(row["candidate"]["logs"])
                    rows.append(row)
    finally:
        reusable._ResettableVM.send_transaction = send_transaction

    require(digest(original.read_bytes()) == ORIGINAL_SHA, "original changed during execution")
    require(digest(candidate.read_bytes()) == args.candidate_sha256, "candidate changed during execution")
    require(input_hashes == {path: digest((root / path).read_bytes()) for path in inputs}, "harness inputs changed")
    problems = []
    for index, row in enumerate(rows):
        quantity, expected_error = expected_transfer(row, economics)
        reject = expected_error is not None
        row["expected_aliased_transfer_quantity"] = quantity
        for side in ("original", "candidate"):
            result = row[side]
            if result["error"] != expected_error:
                problems.append(f"case {index}: unexpected {side} error")
            if len(result["transactions"]) != 1 or result["transactions"][0]["verified_signature_count"] != 1:
                problems.append(f"case {index}: expected one signed transaction per side")
        if row["effect_differences"]:
            problems.append(f"case {index}: effects differ: {row['effect_differences']}")
        if args.expect == "corrected" or not reject:
            if not row["normalized_logs_equal"]:
                problems.append(f"case {index}: normalized logs differ")
        else:
            old, rebuilt = row["original"]["logs"], row["candidate"]["logs"]
            decoration = compared_keys(rebuilt)
            if compared_keys(old) or len(decoration) != 4:
                problems.append(f"case {index}: baseline mismatch absent or changed")
            else:
                clean = list(rebuilt)
                start = clean.index("Program log: Left:")
                del clean[start:start + 4]
                if normalized_logs(old) != normalized_logs(clean):
                    problems.append(f"case {index}: baseline has additional log difference")
    report = {
        "scope": "18 synthetic signed local self-transfer cases; existing history-disabled fixture harness; no network, historical replay or exhaustive equivalence claim",
        "normalization": "Exclude compute-use lines and normalize only SelfTransferNotAllowed source coordinates; retain full raw logs",
        "mode": args.expect, "original_sha256": ORIGINAL_SHA,
        "candidate_sha256": args.candidate_sha256, "input_sha256": input_hashes,
        "build_binding": build_binding,
        "fixture_economics": economics,
        "probe_sha256": digest(Path(__file__).read_bytes()),
        "comparison_helper_sha256": digest(Path(__file__).with_name("verify.py").read_bytes()),
        "runtime": {"python": sys.version, "platform": platform.platform(),
                    "solders": importlib.metadata.version("solders"),
                    "native_sha256": digest(Path(native.__file__).read_bytes())},
        "case_count": len(rows), "transaction_count": sum(len(row[side]["transactions"]) for row in rows for side in ("original", "candidate")),
        "signature_count": sum(tx["verified_signature_count"] for row in rows for side in ("original", "candidate") for tx in row[side]["transactions"]),
        "problems": problems, "cases": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("mode", "case_count", "transaction_count", "signature_count", "problems")}))
    return bool(problems)


if __name__ == "__main__":
    sys.exit(main())
