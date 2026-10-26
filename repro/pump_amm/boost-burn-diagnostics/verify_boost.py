"""Validate actual boost and prior focused receipts without executing SBF."""
import base64
import json

from boost import (PACKAGE, ORIGINAL_SHA, PRIOR_SHA, PRIOR_RECORD_SHA, INPUTS, SITES, ORIGIN,
                   digest, require, check_build, roster, expected_case, check_transaction,
                   normalized_logs, creator, sweep, liquidity, liquidity_runtime)
from verify_creator import effects, signed


def validate_inherited(report, repo, candidate):
    require(report["case_count"] == len(report["cases"]) == 506 and report["mismatches"] == [] and
            report["original_sha256"] == ORIGINAL_SHA and report["candidate_sha256"] == digest(candidate) and
            report["script_sha256"] == digest((repo / "scripts/pump_amm_boost_burn_differential.py").read_bytes()),
            "inherited boost input/count mismatch")
    schema = {"error", "logs", "events", "inner", "return_data", "before", "after", "transaction_base64"}
    signatures, transactions = 0, []
    for row in report["cases"]:
        require(row["diff"] == [] and set(row["original"]) == set(row["candidate"]) == schema,
                "inherited boost incomplete/mismatched effects")
        require(all(row["original"][key] == row["candidate"][key] for key in schema - {"logs"}),
                "inherited boost effects/raw transactions differ")
        for side in ("original", "candidate"):
            raw = base64.b64decode(row[side]["transaction_base64"], validate=True)
            tx = sweep.Transaction.from_bytes(raw)
            require(bytes(tx) == raw and len(tx.signatures) == tx.message.header.num_required_signatures and
                    all(tx.verify_with_results()), "invalid inherited raw signature")
            signatures += len(tx.signatures)
            transactions.append(raw)
    require(signatures == 1018 and len(transactions) == 1012, "inherited signature coverage changed")
    return {"cases": 506, "mismatches": [], "verified_signature_fields": signatures,
            "unique_transaction_bytes": len(set(transactions)),
            "scope": "Complete saved errors/account states/events/CPI/return data/raw transactions compared; full logs excluded here."}


def validate_regressions(report, repo, fixture, config, idl):
    transactions = []
    for row, (holder, amount) in zip(report["migration"], creator.migration_roster()):
        require(type(row["holder"]) is bool and type(row["creator_fees"]) is int and
                (row["holder"], row["creator_fees"]) == (holder, amount), "migration roster changed")
        expected = creator.HOLDER_ERROR if holder else creator.ERROR if amount else None
        original = row["original"]
        pool_before = original["before"][fixture["pool"]]
        pool_bytes = bytes.fromhex(pool_before["data"])
        require(pool_before["owner"] == sweep.PROGRAM and len(pool_bytes) >= 287 and pool_bytes[270] == int(holder) and
                int.from_bytes(pool_bytes[279:287], "little") == amount, "migration labelled state changed")
        pair = []
        for side in ("original", "candidate"):
            result = row[side]
            require(set(result) == {"error", "before", "after", "events", "logs", "inner", "return", "transaction_base64", "transactions"},
                    "incomplete migration effects")
            require(result["error"] == expected and effects(result) == effects(original), "migration effects changed")
            require(not any(line.startswith(("Program log: Left:", "Program log: Right:")) for line in result["logs"]),
                    "migration numeric decoration returned")
            require(creator.normalized_logs(result["logs"]) == creator.normalized_logs(original["logs"]), "migration full logs changed")
            if expected:
                require(sum(" invoke [" in line for line in result["logs"]) == 1, "rejected migration invoked dependency")
            pair.append(signed(result, lambda raw: creator.migration_transaction(raw, fixture, idl)))
        if expected:
            line = 52 if holder else 59
            require(any(creator.ORIGIN + f":{line}." in log for log in original["logs"]), "original migration origin changed")
        require(pair[0] == pair[1], "migration signed inputs differ")
        transactions.extend(pair)
    economics = liquidity.fixture_economics((repo / liquidity.FIXTURE_PATH).read_bytes())
    for row, identity in zip(report["regressions"], creator.regression_roster()):
        require({key: row[key] for key in identity} == identity, "regression roster changed")
        original, rebuilt = row["original"], row["candidate"]
        fields = ({"error", "states", "logs", "inner", "transactions"} if row["family"] == "sweep" else
                  {"accounts", "pool_data", "inner_instructions", "error", "logs", "amounts", "pool_supply", "lp_supply", "transactions"})
        require(set(original) == set(rebuilt) == fields, "incomplete prior focused effects")
        require(effects(original) == effects(rebuilt), "prior focused effects changed")
        require(creator.normalized_logs(original["logs"]) == creator.normalized_logs(rebuilt["logs"]), "prior focused full logs changed")
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
        require(pair[0] == pair[1], "regression signed inputs differ")
        transactions.extend(pair)
    require(len(transactions) == 72, "missing prior focused signed observations")
    return transactions


def validate(report, repo, candidate, record_bytes):
    record = check_build(repo, candidate, record_bytes)
    require(report["status"] == "completed" and report["failure"] is None, "incomplete/failed execution")
    require(report["build_binding"] == {"sha256": digest(record_bytes), "record": record}, "changed build binding")
    require(report["binary_sha256"] == {"original": ORIGINAL_SHA, "prior_creator": PRIOR_SHA, "candidate": digest(candidate)} and
            report["prior_build_record_sha256"] == PRIOR_RECORD_SHA, "wrong binary/prior binding")
    require(digest((repo / "evidence/original/pump_amm/deployed.so").read_bytes()) == ORIGINAL_SHA, "original input changed")
    require(set(report["input_sha256"]) == INPUTS and
            all(digest((repo / path).read_bytes()) == sha for path, sha in report["input_sha256"].items()), "harness inputs changed")
    require(report["tool_sha256"] == {name: digest((PACKAGE / name).read_bytes()) for name in
                                      ("runtime_probe.py", "boost.py", "verify_boost.py")}, "probe/checker changed")
    require(report["planned_case_count"] == report["completed_case_count"] == 52 and
            report["planned_transaction_count"] == report["transaction_count"] == 120 and
            len(report["boost"]) == 16 and len(report["migration"]) == 6 and len(report["regressions"]) == 30,
            "incomplete focused roster")
    fixture, config, idl = sweep.fixture_inputs(repo)
    transactions, sites = [], {line: 0 for line in SITES}
    for row, identity in zip(report["boost"], roster(fixture)):
        require(json.dumps(row["case"], sort_keys=True) == json.dumps(identity, sort_keys=True), "boost roster changed")
        original = row["original"]
        site, values = expected_case(identity, original["before"], fixture, config)
        expected = None if site is None else f"TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom({SITES[site][0]}))))"
        if site is not None:
            sites[site] += 1
        pair = []
        for side in ("original", "prior_creator", "candidate"):
            result = row[side]
            require(set(result) == {"error", "before", "after", "events", "logs", "inner", "return_data", "transaction_base64", "transactions"},
                    "incomplete boost effects")
            require(result["error"] == expected and effects(result) == effects(original), "boost error/effects differ")
            logs = list(result["logs"])
            observed = [line for line in logs if line.startswith(("Program log: Left:", "Program log: Right:"))]
            decoration = [] if site is None else [f"Program log: Left: {values[0]}", f"Program log: Right: {values[1]}"]
            if side == "prior_creator":
                require(observed == [], "prior source-built numeric omission absent/changed")
                reference = list(original["logs"])
                for line in decoration:
                    require(line in reference, "original numeric decoration missing")
                    reference.remove(line)
            else:
                require(observed == decoration, "wrong numeric values or value ordering")
                reference = original["logs"]
            require(normalized_logs(logs) == normalized_logs(reference), "boost full logs/site differ")
            if site is not None:
                require(sum(f"<boost-source:{site}>" in line for line in normalized_logs(logs)) == 1,
                        "wrong guard/error precedence")
                require(sum(" invoke [" in line for line in logs) == 1, "boost rejection invoked dependency")
            pair.append(signed(result, lambda raw: check_transaction(raw, identity, fixture, config, idl["boost_buy_and_burn"])))
        if site is not None:
            require(any(f"{ORIGIN}:{site}." in line for line in original["logs"]), "original boost origin missing")
        require(len(set(pair)) == 1, "boost binaries received different signed inputs")
        transactions.extend(pair)
    require(sites == {250: 3, 255: 2, 273: 3, 274: 2, 280: 1}, "focused guard coverage changed")
    transactions.extend(validate_regressions(report, repo, fixture, config, idl))
    require(len(transactions) == 120, "missing signed observations")
    return {"boost_cases": 16, "boost_rejections_per_binary": 11, "boost_success_controls_per_binary": 5,
            "original_guard_counts": sites, "prior_focused_cases": 36, "verified_signatures": 120,
            "unique_transaction_bytes": len(set(transactions)), "full_logs_compared": True,
            "scope": "Only compute lines and the explicitly identified source coordinates are normalized."}
