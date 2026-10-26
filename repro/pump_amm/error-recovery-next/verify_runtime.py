#!/usr/bin/env python3
"""Accept complete saved focused receipts and independently verify raw signatures."""
import argparse
import base64
import gzip
import json
from pathlib import Path
import struct

from solders.pubkey import Pubkey
from solders.transaction import Transaction
from verify import (PACKAGE, ROOT, ORIGINAL_SHA, BASELINE_SHA, ORIGIN, SOURCE_SHA,
                    FIXTURE_PATH, digest, require, normalized_logs, compared_keys,
                    fixture_economics, expected_transfer)

PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
PAYER = "DXyM8yAHqpMzDtvwz5DXoEUQmPxjJPMKCASCPhLMKpEx"
OUTSIDER = "5jotNjSnm9ZJRefVfqHato9FC4d9t6CHb2xS1726MTyY"
CORRECTED_SOURCE_SHA = "85e95b9e9e677368236eef2292b82e82352108c63c5acf15ab488e1ebb673f90"
BUILD_INPUT = "repro/pump_amm/owner6048-v144/main/build-01/build-attempt.json"
BUILD_INPUT_SHA = "d08e845f95f2f922658f6b464cb5b9d47e701902324ae55186c39004faec4607"
INPUTS = {
    "scripts/pump_amm_liquidity_differential.py", "scripts/pump_amm_admin_differential.py",
    "scripts/pump_amm_reusable_harness.py", FIXTURE_PATH,
    "research/imported-lab/analysis/pump_fun/config-snapshot.json", "evidence/upstream/pump_amm.json",
    "evidence/dependencies/spl_token/deployed.so", "evidence/dependencies/spl_token_2022/deployed.so",
}


def read_report(path):
    raw = path.read_bytes()
    return gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw


def check_transaction(raw, row, fixture, config_key, discriminator):
    transaction = Transaction.from_bytes(raw)
    require(bytes(transaction) == raw, "transaction bytes do not round-trip")
    message = transaction.message
    require(message.header.num_required_signatures == len(transaction.signatures) == 1, "expected exactly one signer")
    require(str(message.account_keys[0]) == PAYER, "unexpected payer/signer")
    # Recompute Ed25519 verification from raw message/signature bytes, ignoring
    # the producer's claimed verified_signature_count.
    require(transaction.signatures[0].verify(message.account_keys[0], bytes(message)), "invalid raw transaction signature")
    require(len(message.instructions) == 1, "unexpected instruction count")
    instruction = message.instructions[0]
    require(str(message.account_keys[instruction.program_id_index]) == PROGRAM, "wrong invoked program")
    limit = 0 if row["instruction"] == "withdraw" else 2**64 - 1
    require(bytes(instruction.data) == discriminator + struct.pack("<QQQ", row["amount"], limit, limit), "wrong signed instruction payload")
    pool_bytes = base64.b64decode(fixture["accounts"]["pool"]["data_base64"], validate=True)
    expected = [fixture["pool"], config_key, PAYER, fixture["keys"]["base_mint"], fixture["keys"]["quote_mint"],
                str(Pubkey.from_bytes(pool_bytes[107:139])), str(Pubkey.from_bytes(bytes([70]) * 32)),
                str(Pubkey.from_bytes(bytes([71]) * 32)), str(Pubkey.from_bytes(bytes([72]) * 32)),
                fixture["keys"]["pool_base_token_account"], fixture["keys"]["pool_quote_token_account"],
                "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
                str(Pubkey.find_program_address([b"__event_authority"], Pubkey.from_string(PROGRAM))[0]), PROGRAM]
    expected[row["user_account_index"]] = expected[row["user_account_index"] + 3]
    actual = [str(message.account_keys[index]) for index in instruction.accounts]
    require(actual == expected, "wrong signed account routing")
    require(set(map(str, message.account_keys)) == set(expected), "unexpected unused message account")
    writable = {expected[index] for index in (0, 2, 5, 6, 7, 8, 9, 10)}
    header = message.header
    for index, key in enumerate(message.account_keys):
        is_writable = (index < header.num_required_signatures - header.num_readonly_signed_accounts or
                       header.num_required_signatures <= index < len(message.account_keys) - header.num_readonly_unsigned_accounts)
        require(is_writable == (str(key) in writable), "wrong signed account privileges")
    return 1


def validate(report, repo, candidate, build_record_bytes):
    require(report["problems"] == [], "producer reported a failed run; preserve it as failed")
    require(report["case_count"] == len(report["cases"]) == 18, "incomplete focused case set")
    require(report["mode"] in ("baseline", "rebuilt-baseline", "corrected"), "unknown validation mode")
    require(report["original_sha256"] == ORIGINAL_SHA and digest((repo / "evidence/original/pump_amm/deployed.so").read_bytes()) == ORIGINAL_SHA,
            "original binding mismatch")
    require(report["candidate_sha256"] == digest(candidate), "candidate bytes do not match receipt")
    require(set(report["input_sha256"]) == INPUTS, "missing or added harness input binding")
    require(all(digest((repo / path).read_bytes()) == sha for path, sha in report["input_sha256"].items()), "harness input changed")
    require(report["probe_sha256"] == digest((PACKAGE / "runtime_probe.py").read_bytes()), "receipt uses a different probe")
    require(report["comparison_helper_sha256"] == digest((PACKAGE / "verify.py").read_bytes()), "receipt uses a different comparison helper")
    if report["mode"] == "baseline":
        require(report["candidate_sha256"] == BASELINE_SHA, "selected baseline hash mismatch")
    else:
        require(build_record_bytes is not None, "rebuilt receipts need their retained build record")
        record = json.loads(build_record_bytes)
        require(report["build_binding"] == {"sha256": digest(build_record_bytes), "record": record}, "build binding mismatch")
        kind = "corrected" if report["mode"] == "corrected" else "baseline"
        require(record["kind"] == kind and record["accepted_build"] and record["returncode"] == 0 and record["source_unchanged"], "build did not pass its gates")
        require(record["candidate_sha256"] == report["candidate_sha256"], "build references different binary")
        baseline_bytes = (repo / BUILD_INPUT).read_bytes()
        require(digest(baseline_bytes) == BUILD_INPUT_SHA, "historical source manifest changed")
        expected_source = json.loads(baseline_bytes)["source_sha256"]
        require(expected_source["programs/pump-amm/src/lib.rs"] == SOURCE_SHA, "baseline source changed")
        if kind == "corrected":
            expected_source["programs/pump-amm/src/lib.rs"] = CORRECTED_SOURCE_SHA
        require(record["source_sha256"] == record["source_after_sha256"] == expected_source, "unexpected built source change")
    fixture_raw = (repo / FIXTURE_PATH).read_bytes()
    fixture = json.loads(fixture_raw)
    economics = fixture_economics(fixture_raw)
    require(report["fixture_economics"] == economics, "fixture classification inputs changed")
    config = json.loads((repo / "research/imported-lab/analysis/pump_fun/config-snapshot.json").read_text())
    config_key = next(row["address"] for row in config["accounts"] if row["program_name"] == "pump_amm")
    idl = json.loads((repo / "evidence/upstream/pump_amm.json").read_text())
    discriminators = {row["name"]: bytes(row["discriminator"]) for row in idl["instructions"] if row["name"] in ("deposit", "withdraw")}
    roster = [(instruction, account, amount, wrong)
              for instruction, wrong in (("deposit", False), ("withdraw", False), ("withdraw", True))
              for account in (6, 7) for amount in (0, 1, 1000000)]
    raw_transactions, signatures, rejected = [], 0, 0
    for index, (row, identity) in enumerate(zip(report["cases"], roster)):
        require(type(row["wrong_withdraw_owner"]) is bool and
                (row["instruction"], row["user_account_index"], row["amount"], row["wrong_withdraw_owner"]) == identity,
                f"case {index}: omitted, duplicated or wrong case")
        quantity, expected_error = expected_transfer(row, economics)
        require(row["expected_aliased_transfer_quantity"] == quantity, "wrong transfer classification")
        rejected += expected_error is not None
        original, rebuilt = row["original"], row["candidate"]
        require(original["error"] == rebuilt["error"] == expected_error, "unexpected error disposition")
        effects = lambda data: {key: value for key, value in data.items() if key not in ("logs", "transactions")}
        require(effects(original) == effects(rebuilt) and row["effect_differences"] == [], "effects differ")
        logs_equal = normalized_logs(original["logs"]) == normalized_logs(rebuilt["logs"])
        require(row["normalized_logs_equal"] is logs_equal, "incorrect log equality claim")
        if expected_error is not None:
            require(any(ORIGIN in line and "Error Number: 6087." in line for line in original["logs"]), "original error origin missing")
            require(not compared_keys(original["logs"]), "original has unexpected compared keys")
        if report["mode"] == "corrected" or expected_error is None:
            require(logs_equal, "normalized logs differ")
        else:
            decoration = compared_keys(rebuilt["logs"])
            left, right = (fixture["pool"], PAYER) if row["instruction"] == "deposit" else (OUTSIDER, fixture["pool"])
            require(decoration == ["Program log: Left:", f"Program log: {left}", "Program log: Right:", f"Program log: {right}"], "baseline diagnostic mismatch changed")
            clean = list(rebuilt["logs"])
            start = clean.index("Program log: Left:")
            del clean[start:start + 4]
            require(normalized_logs(original["logs"]) == normalized_logs(clean), "additional baseline diagnostic mismatch")
        pair = []
        for side in (original, rebuilt):
            require(len(side["transactions"]) == 1, "missing/extra transaction record")
            raw = base64.b64decode(side["transactions"][0]["raw_base64"], validate=True)
            verified = check_transaction(raw, row, fixture, config_key, discriminators[row["instruction"]])
            require(side["transactions"][0]["verified_signature_count"] == verified, "wrong signature-count claim")
            signatures += verified
            pair.append(raw)
            raw_transactions.append(raw)
        require(pair[0] == pair[1], "original and candidate were sent different signed transactions")
    require(rejected == 7 and report["transaction_count"] == len(raw_transactions) == 36 and report["signature_count"] == signatures == 36,
            "incomplete aggregate acceptance")
    return {"mode": report["mode"], "cases": 18, "rejections": 7, "successful_controls": 11,
            "raw_transaction_records": 36, "verified_signatures": signatures,
            "unique_transaction_bytes": len(set(raw_transactions)),
            "scope": "Saved synthetic execution evidence and raw signature verification; repeated messages and separate fixture states are not unique coverage."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-record", type=Path)
    args = parser.parse_args()
    report_bytes = read_report(args.report)
    result = validate(json.loads(report_bytes), args.repo.resolve(), args.candidate.read_bytes(),
                      args.build_record.read_bytes() if args.build_record else None)
    print(json.dumps({"receipt_sha256": digest(report_bytes), **result}, indent=2))


if __name__ == "__main__":
    main()
