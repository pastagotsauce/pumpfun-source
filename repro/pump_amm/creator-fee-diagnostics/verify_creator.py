"""Verify actual migration/previous-focused receipts without executing SBF."""
import base64
import json
import re
import struct

from migration import (PACKAGE, ROOT, PRIOR, PRIOR_SHA, PRIOR_RECORD_SHA, ORIGINAL_SHA,
                       RECEIPT, RECEIPT_SHA, RAW_SHA, INPUTS, ERROR, HOLDER_ERROR, ORIGIN,
                       digest, require, read_report, normalized_logs, migration_transaction,
                       migration_roster, regression_roster, check_build, sweep, liquidity,
                       liquidity_runtime)


def verify_saved():
    compressed = (ROOT / RECEIPT).read_bytes()
    require(digest(compressed) == RECEIPT_SHA, "saved receipt changed")
    raw = read_report(ROOT / RECEIPT)
    require(digest(raw) == RAW_SHA, "saved raw receipt changed")
    report = json.loads(raw)
    require(report["case_count"] == len(report["cases"]) == 327 and report["mismatches"] == [] and
            report["original_sha256"] == ORIGINAL_SHA and report["candidate_sha256"] == liquidity.BASELINE_SHA,
            "saved receipt binding changed")
    fixture, _, idl = sweep.fixture_inputs(ROOT)
    indices = [i for i, row in enumerate(report["cases"]) if row["original"]["error"] == ERROR]
    require(indices == [105, 106], "saved 6081 case set changed")
    transactions = []
    for index, amount in ((105, 1), (106, 2)):
        row = report["cases"][index]
        require(row["case"]["op"] == "migrate_pool_coin_creator" and row["case"]["patches"] == {
            "pool": [[279, amount.to_bytes(8, "little").hex()]]}, "saved case changed")
        original, candidate = row["original"], row["candidate"]
        require(candidate["error"] == ERROR and all(original[key] == candidate[key] for key in
                ("error", "before", "after", "events", "inner", "return", "transaction_base64")), "saved effects differ")
        expected = [f"Program log: Left: {amount}", "Program log: Right: 0"]
        require([line for line in candidate["logs"] if line.startswith(("Program log: Left:", "Program log: Right:"))] == expected,
                "saved numeric decoration changed")
        require(normalized_logs(original["logs"]) == normalized_logs([line for line in candidate["logs"] if line not in expected]),
                "additional saved diagnostic difference")
        for result in (original, candidate):
            raw_tx = base64.b64decode(result["transaction_base64"], validate=True)
            migration_transaction(raw_tx, fixture, idl)
            transactions.append(raw_tx)
    return {"saved_rows": indices, "raw_signatures": len(transactions), "unique_messages": len(set(transactions))}


def verify_original():
    original = (ROOT / "evidence/original/pump_amm/deployed.so").read_bytes()
    require(digest(original) == ORIGINAL_SHA, "original binary changed")
    covered = set()
    for line in (PACKAGE / "original-migrate-guard.asm").read_text().splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s*((?:[0-9a-f]{2} )+)\s", line)
        if match:
            offset, raw = int(match[1], 16), bytes.fromhex(match[2])
            require(original[offset:offset + len(raw)] == raw, "original instruction bytes differ")
            covered.update(range(offset, offset + len(raw)))
    require(covered == set(range(0x23e40, 0x23f30)) | set(range(0x24128, 0x24208)), "incomplete original excerpt")
    require(original[0x11c875:0x11c875 + 76] == ORIGIN.encode(), "original source-path literal changed")
    require(original[0x23e68:0x23e70] == bytes.fromhex("15 01 73 00 00 00 00 00") and
            0x23e68 + 8 * (1 + struct.unpack_from("<h", original, 0x23e6a)[0]) == 0x24208, "zero-fee target changed")
    require(struct.unpack_from("<I", original, 0x241a4)[0] == 6081 and struct.unpack_from("<I", original, 0x241b4)[0] == 59,
            "error/source-line construction changed")
    return {"original_instruction_bytes": len(covered), "zero_branch": "0x23e68 -> 0x24208", "original_error_origin": ORIGIN + ":59"}


def effects(result):
    return {key: value for key, value in result.items() if key not in ("logs", "transactions", "transaction_base64")}


def signed(result, checker):
    require(len(result["transactions"]) == 1, "missing/extra transaction")
    transaction = result["transactions"][0]
    raw = base64.b64decode(transaction["raw_base64"], validate=True)
    require(transaction["verified_signature_count"] == checker(raw) == 1, "wrong signature count")
    if "transaction_base64" in result:
        require(base64.b64decode(result["transaction_base64"], validate=True) == raw, "harness transaction differs from observation")
    return raw


def validate(report, repo, candidate, record_bytes):
    record = check_build(repo, candidate, record_bytes)
    require(report["status"] == "completed" and report["failure"] is None, "incomplete/failed execution")
    require(report["build_binding"] == {"sha256": digest(record_bytes), "record": record}, "build binding changed")
    require(report["binary_sha256"] == {"original": ORIGINAL_SHA, "prior_sweep": PRIOR_SHA, "candidate": digest(candidate)}, "wrong binary binding")
    require(report["prior_build_record_sha256"] == PRIOR_RECORD_SHA and
            digest((repo / "evidence/original/pump_amm/deployed.so").read_bytes()) == ORIGINAL_SHA, "original/prior binding changed")
    require(set(report["input_sha256"]) == INPUTS and
            all(digest((repo / name).read_bytes()) == sha for name, sha in report["input_sha256"].items()), "probe inputs changed")
    require(report["tool_sha256"] == {name: digest((PACKAGE / name).read_bytes()) for name in
                                      ("runtime_probe.py", "migration.py", "verify_creator.py")}, "probe/checker changed")
    require(report["planned_case_count"] == report["completed_case_count"] == 36 and
            report["planned_transaction_count"] == report["transaction_count"] == 78, "incomplete aggregate")
    require(len(report["migration"]) == 6 and len(report["regressions"]) == 30, "wrong focused case counts")
    fixture, config, idl = sweep.fixture_inputs(repo)
    transactions = []
    for row, (holder, amount) in zip(report["migration"], migration_roster()):
        require(type(row["holder"]) is bool and type(row["creator_fees"]) is int and
                (row["holder"], row["creator_fees"]) == (holder, amount), "migration roster changed")
        expected = HOLDER_ERROR if holder else ERROR if amount else None
        original = row["original"]
        pool_before = original["before"][fixture["pool"]]
        pool_bytes = bytes.fromhex(pool_before["data"])
        require(pool_before["owner"] == sweep.PROGRAM and len(pool_bytes) >= 287 and pool_bytes[270] == int(holder) and
                int.from_bytes(pool_bytes[279:287], "little") == amount, "labelled migration fixture state differs")
        pair = []
        for side in ("original", "prior_sweep", "candidate"):
            result = row[side]
            require(set(result) == {"error", "before", "after", "events", "logs", "inner", "return", "transaction_base64", "transactions"},
                    "incomplete migration result fields")
            require(result["error"] == expected and effects(result) == effects(original), "migration effects/error differ")
            logs = list(result["logs"])
            if side == "prior_sweep" and expected == ERROR:
                decoration = [f"Program log: Left: {amount}", "Program log: Right: 0"]
                require([line for line in logs if line.startswith(("Program log: Left:", "Program log: Right:"))] == decoration,
                        "prior Linux 6081 defect absent/changed")
                for line in decoration:
                    logs.remove(line)
            else:
                require(not any(line.startswith(("Program log: Left:", "Program log: Right:")) for line in logs), "unexpected numeric decoration")
            require(normalized_logs(logs) == normalized_logs(original["logs"]), "migration full logs differ")
            if expected:
                require(sum(" invoke [" in line for line in result["logs"]) == 1, "rejected migration invoked a dependency")
            pair.append(signed(result, lambda raw: migration_transaction(raw, fixture, idl)))
        if expected:
            line = 52 if holder else 59
            require(any(ORIGIN + f":{line}." in log for log in original["logs"]), "original error origin missing")
        require(len(set(pair)) == 1, "migration binaries received different signed messages")
        transactions.extend(pair)
    economics = liquidity.fixture_economics((repo / liquidity.FIXTURE_PATH).read_bytes())
    for row, identity in zip(report["regressions"], regression_roster()):
        require({key: row[key] for key in identity} == identity, "regression roster changed")
        original, rebuilt = row["original"], row["candidate"]
        fields = ({"error", "states", "logs", "inner", "transactions"} if row["family"] == "sweep" else
                  {"accounts", "pool_data", "inner_instructions", "error", "logs", "amounts", "pool_supply", "lp_supply", "transactions"})
        require(set(original) == set(rebuilt) == fields, "incomplete prior-focused result fields")
        require(effects(original) == effects(rebuilt), "prior focused effects changed")
        require(normalized_logs(original["logs"]) == normalized_logs(rebuilt["logs"]), "prior focused full logs changed")
        if row["family"] == "sweep":
            expected = liquidity.ERROR if row["mode"] == "alias_wrong_owner" and row["amount"] else None
            checker = lambda raw: sweep.check_transaction(raw, row, fixture, config, idl[row["instruction"]])
            zero_log = "Program log: Nothing to sweep for fee bucket " + ("1" if row["instruction"] == "sweep_creator_fee" else "0")
            require(original["logs"].count(zero_log) == (1 if row["amount"] == 0 else 0), "empty-bucket log regression")
        else:
            _, expected = liquidity.expected_transfer(row, economics)
            checker = lambda raw: liquidity_runtime.check_transaction(raw, row, fixture, config["address"], bytes(idl[row["instruction"]]["discriminator"]))
        require(original["error"] == rebuilt["error"] == expected, "prior focused classification changed")
        require(not liquidity.compared_keys(original["logs"]) and not liquidity.compared_keys(rebuilt["logs"]), "6087 compared keys returned")
        pair = [signed(result, checker) for result in (original, rebuilt)]
        require(pair[0] == pair[1], "regression binaries received different signed messages")
        transactions.extend(pair)
    require(len(transactions) == 78, "missing signed observations")
    return {"migration_cases": 6, "migration_6081_rejections_per_binary": 3, "holder_precedence_controls_per_binary": 2,
            "successful_zero_controls_per_binary": 1, "prior_focused_regression_cases": 30, "verified_signatures": 78,
            "unique_transaction_bytes": len(set(transactions))}
