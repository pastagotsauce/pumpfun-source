#!/usr/bin/env python3
"""Twelve signed offline sweep cases against original, prior and combined builds."""
import argparse
import base64
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

from recovery import (PACKAGE, ROOT, PRIOR, ORIGINAL_SHA, PRIOR_SHA, PRIOR_RECORD_SHA,
                      INPUTS, digest, require, check_build, write_json, roster)
from verify_sweep import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    require(not output.exists(), "output already exists")
    candidate = args.candidate.read_bytes()
    record_bytes = args.build_record.read_bytes()
    record = check_build(repo, candidate, record_bytes)
    binaries = {"original": repo / "evidence/original/pump_amm/deployed.so",
                "liquidity_corrected": PRIOR / "results/build/corrected/candidate.so",
                "combined_corrected": args.candidate.resolve()}
    expected = {"original": ORIGINAL_SHA, "liquidity_corrected": PRIOR_SHA, "combined_corrected": digest(candidate)}
    require({kind: digest(path.read_bytes()) for kind, path in binaries.items()} == expected, "wrong binaries")
    bindings = {path: digest((repo / path).read_bytes()) for path in sorted(INPUTS)}
    os.chdir(repo)
    sys.path.insert(0, str(repo / "scripts"))
    import pump_amm_sweep_differential as harness
    import pump_amm_reusable_harness as reusable
    import solders.solders as native
    transactions = []
    send = reusable._ResettableVM.send_transaction

    def observe(self, transaction):
        transaction.verify()
        transactions.append({"raw_base64": base64.b64encode(bytes(transaction)).decode(),
                             "verified_signature_count": len(transaction.signatures)})
        return send(self, transaction)

    report = {"scope": "Twelve synthetic signed local sweeps; exact effects and full logs except compute cost and 6087 source coordinates. No RPC, deployment, historical replay or whole-program equivalence.",
              "binary_sha256": expected, "input_sha256": bindings,
              "probe_sha256": digest(Path(__file__).read_bytes()),
              "checker_sha256": {name: digest((PACKAGE / name).read_bytes()) for name in ("recovery.py", "verify_sweep.py")},
              "build_binding": {"sha256": digest(record_bytes), "record": record},
              "prior_build_record_sha256": PRIOR_RECORD_SHA,
              "runtime": {"python": sys.version, "platform": platform.platform(),
                          "solders": importlib.metadata.version("solders"), "native_sha256": digest(Path(native.__file__).read_bytes())},
              "planned_case_count": 12, "planned_transaction_count": 36, "cases": []}

    def retain(status, failure=None):
        report.update(status=status, failure=failure,
                      completed_case_count=sum(all(side in row and "error" in row[side] for side in binaries) for row in report["cases"]),
                      transaction_count=sum(len(row.get(side, {}).get("transactions", [])) for row in report["cases"] for side in binaries))
        temporary = output.with_suffix(".tmp")
        write_json(temporary, report)
        temporary.replace(output)

    reusable._ResettableVM.send_transaction = observe
    retain("incomplete")
    try:
        for instruction, mode, amount in roster():
            row = {"instruction": instruction, "mode": mode, "amount": amount}
            report["cases"].append(row)
            kw = {}
            if mode != "ordinary":
                owner = harness.pool if mode == "alias_pool_owner" else harness.OUTSIDER.pubkey()
                kw = {"recipient": harness.pool, "overrides": harness.combine(
                    harness.mutate(harness.CONFIG_KEY, 57, bytes(harness.pool) * 8),
                    harness.mutate(harness.vaultquote, 32, bytes(owner)))}
            for side, binary in binaries.items():
                transactions.clear()
                try:
                    result = harness.sweep(instruction, amount, candidate=binary, **kw)
                except Exception as exc:
                    row[side] = {"transactions": list(transactions), "execution_exception": repr(exc)}
                    raise
                result["transactions"] = list(transactions)
                row[side] = result
                retain("incomplete")
                require(len(transactions) == 1, "one signed transaction required")
        require(bindings == {path: digest((repo / path).read_bytes()) for path in bindings}, "harness inputs changed")
        require(expected == {kind: digest(path.read_bytes()) for kind, path in binaries.items()}, "binary inputs changed")
        require(record_bytes == args.build_record.read_bytes(), "build record changed")
        retain("completed")
        result = validate(report, repo, candidate, record_bytes)
        print(json.dumps(result))
    except Exception as exc:
        retain("failed", type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        reusable._ResettableVM.send_transaction = send


if __name__ == "__main__":
    main()
