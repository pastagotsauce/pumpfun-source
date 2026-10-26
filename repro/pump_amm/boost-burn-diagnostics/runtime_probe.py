#!/usr/bin/env python3
"""Sixteen boost cases plus all 36 prior focused cases, with retained signed logs."""
import argparse
import base64
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import struct
import sys

from boost import (PACKAGE, ROOT, PRIOR, PRIOR_SHA, PRIOR_RECORD_SHA, ORIGINAL_SHA, INPUTS,
                   digest, require, write_json, check_build, roster, creator, sweep)
from verify_boost import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.repo.resolve(), args.output.resolve()
    require(not output.exists(), "output exists; preserve previous attempt")
    candidate, record_bytes = args.candidate.read_bytes(), args.build_record.read_bytes()
    record = check_build(root, candidate, record_bytes)
    binaries = {"original": root / "evidence/original/pump_amm/deployed.so", "prior_creator": PRIOR / "results/build/combined/candidate.so",
                "candidate": args.candidate.resolve()}
    hashes = {"original": ORIGINAL_SHA, "prior_creator": PRIOR_SHA, "candidate": digest(candidate)}
    require({side: digest(path.read_bytes()) for side, path in binaries.items()} == hashes, "wrong input binaries")
    inputs = {name: digest((root / name).read_bytes()) for name in sorted(INPUTS)}
    fixture, _, _ = sweep.fixture_inputs(root)
    os.chdir(root)
    sys.path.insert(0, str(root / "scripts"))
    import pump_amm_boost_burn_differential as burn
    import pump_amm_creator_reassignment_differential as migrate
    import pump_amm_sweep_differential as sweeps
    import pump_amm_liquidity_differential as pools
    import pump_amm_reusable_harness as reusable
    import solders.solders as native
    transactions = []
    send = reusable._ResettableVM.send_transaction

    def observe(self, transaction):
        transaction.verify()
        transactions.append({"raw_base64": base64.b64encode(bytes(transaction)).decode(), "verified_signature_count": len(transaction.signatures)})
        return send(self, transaction)

    report = {"scope": "Synthetic signed boost guards and previous focused regressions. No RPC, deployment, historical replay or whole-binary equivalence.",
        "binary_sha256": hashes, "prior_build_record_sha256": PRIOR_RECORD_SHA,
        "build_binding": {"sha256": digest(record_bytes), "record": record}, "input_sha256": inputs,
        "tool_sha256": {name: digest((PACKAGE / name).read_bytes()) for name in ("runtime_probe.py", "boost.py", "verify_boost.py")},
        "runtime": {"python": sys.version, "platform": platform.platform(), "solders": importlib.metadata.version("solders"),
                    "native_sha256": digest(Path(native.__file__).read_bytes())},
        "planned_case_count": 52, "planned_transaction_count": 120, "boost": [], "migration": [], "regressions": []}

    def retain(status, failure=None):
        groups = [(report["boost"], tuple(binaries)), (report["migration"], ("original", "candidate")),
                  (report["regressions"], ("original", "candidate"))]
        report.update(status=status, failure=failure,
            completed_case_count=sum(all(side in row and "error" in row[side] for side in sides) for rows, sides in groups for row in rows),
            transaction_count=sum(len(row.get(side, {}).get("transactions", [])) for rows, sides in groups for row in rows for side in sides))
        temporary = output.with_suffix(".tmp")
        write_json(temporary, report)
        temporary.replace(output)

    def execute(row, side, call):
        transactions.clear()
        try:
            result = call()
        except Exception as exc:
            row[side] = {"transactions": list(transactions), "execution_exception": repr(exc)}
            raise
        result["transactions"] = list(transactions)
        row[side] = result
        retain("incomplete")
        require(len(transactions) == 1, "expected one signed observation")

    reusable._ResettableVM.send_transaction = observe
    retain("incomplete")
    try:
        for identity in roster(fixture):
            row = {"case": identity}
            report["boost"].append(row)
            overrides = []
            if "quote_fee" in identity:
                overrides.append(burn.boost_transferfee(burn.quote, *identity["quote_fee"]))
            for key, account in (("vault_amount", burn.BOOST_ATA), ("base_amount", burn.vaultbase), ("quote_amount", burn.vaultquote)):
                if key in identity:
                    overrides.append(burn.mutate(account, 64, struct.pack("<Q", identity[key])))
            if "virtual" in identity:
                overrides.append(burn.mutate(burn.pool, 245, identity["virtual"].to_bytes(16, "little", signed=True)))
            if identity.get("fees_zero"):
                overrides.append(burn.mutate(burn.pool, 271, bytes(16)))
            override = burn.combine(*overrides) if overrides else None
            for side, binary in binaries.items():
                execute(row, side, lambda: burn.run(amount=identity["amount"], limit=identity["minimum"], overrides=override, candidate=binary))
        for holder, amount in creator.migration_roster():
            row = {"holder": holder, "creator_fees": amount}
            report["migration"].append(row)
            case = {"op": "migrate_pool_coin_creator", "patches": {"pool": [
                (279, amount.to_bytes(8, "little").hex()), (270, bytes([holder]).hex())]}}
            for side in ("original", "candidate"):
                execute(row, side, lambda: migrate.run_creator(case, binaries[side]))
        for row in creator.regression_roster():
            report["regressions"].append(row)
            if row["family"] == "sweep":
                kw = {}
                if row["mode"] != "ordinary":
                    owner = sweeps.pool if row["mode"] == "alias_pool_owner" else sweeps.OUTSIDER.pubkey()
                    kw = {"recipient": sweeps.pool, "overrides": sweeps.combine(
                        sweeps.mutate(sweeps.CONFIG_KEY, 57, bytes(sweeps.pool) * 8), sweeps.mutate(sweeps.vaultquote, 32, bytes(owner)))}
                for side in ("original", "candidate"):
                    execute(row, side, lambda: sweeps.sweep(row["instruction"], row["amount"], candidate=binaries[side], **kw))
            else:
                def alias(h, metas):
                    index = row["user_account_index"]
                    metas[index] = pools.AccountMeta(metas[index + 3].pubkey, False, True)
                    if row["wrong_withdraw_owner"]:
                        pools.mutate(metas[index + 3].pubkey, 32, bytes(pools.OUTSIDER.pubkey()))(h, metas)
                limit = 0 if row["instruction"] == "withdraw" else 2**64 - 1
                for side in ("original", "candidate"):
                    execute(row, side, lambda: pools.run(row["instruction"], row["amount"], maxbase=limit, maxquote=limit,
                                                        overrides=alias, candidate=binaries[side]))
        require(inputs == {name: digest((root / name).read_bytes()) for name in inputs}, "harness inputs changed")
        require(hashes == {side: digest(path.read_bytes()) for side, path in binaries.items()}, "binary input changed")
        require(record_bytes == args.build_record.read_bytes(), "build record changed")
        retain("completed")
        print(json.dumps(validate(report, root, candidate, record_bytes)))
    except Exception as exc:
        retain("failed", type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        reusable._ResettableVM.send_transaction = send


if __name__ == "__main__":
    main()
