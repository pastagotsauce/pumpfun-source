"""Read-only verification of complete focused logs, effects and signed payloads."""
import argparse
import base64
import json
import copy
from pathlib import Path
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import Transaction
from recovery import (ROOT, PACKAGE, ORIGINAL_SHA, SOURCE, CORRECTED_SHA, digest, require,
                      load_json, pinned_source, focused_cases, expected_message, full_logs_without_compute, TARGETS)

PROGRAM = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
PAYER = Keypair.from_seed(bytes([227]) * 32).pubkey()
USER = Keypair.from_seed(bytes([228]) * 32).pubkey()
TARGET = Pubkey.from_bytes(bytes([229]) * 32)
EVENT = Pubkey.find_program_address([b"__event_authority"], PROGRAM)[0]
EFFECTS = ("before", "after", "error", "events", "inner", "return")


def fixture_effects(result, spec, discriminator):
    """Exact measured shapes for these normally signed, one-byte-growth fixtures."""
    before = result["before"][str(TARGET)]
    require(before["owner"] == str(PROGRAM) and before["lamports"] == 10**9 and
            bytes.fromhex(before["data"]) == discriminator + bytes(spec["size"] - 8), "wrong fixture state")
    require(result["before"][str(PAYER)]["lamports"] == result["before"][str(USER)]["lamports"] == 10**12,
            "wrong initial fee payer/user funding")
    expected_after = copy.deepcopy(result["before"])
    # Two genuine signatures cost 10,000 lamports in the retained fixed LiteSVM
    # environment. This is a fixture assertion, not a network fee claim.
    expected_after[str(PAYER)]["lamports"] -= 10000
    target_size = TARGETS[spec["kind"]]
    if spec["size"] >= target_size:
        require(result["events"] == [] and result["inner"] == [[]], "no-growth CPI/event shape changed")
    else:
        delta = (target_size - spec["size"]) * 6960
        expected_after[str(USER)]["lamports"] -= delta
        expected_after[str(TARGET)]["lamports"] += delta
        expected_after[str(TARGET)]["data"] += "00" * (target_size - spec["size"])
        require(len(result["events"]) == 1 and len(result["inner"]) == 1 and len(result["inner"][0]) == 2,
                "growth transfer/event CPI shape changed")
    require(result["after"] == expected_after, "unauthorized fixture account change, fee or rent delta")


def signed_payload(encoded, discriminator):
    raw = base64.b64decode(encoded, validate=True)
    tx = Transaction.from_bytes(raw)
    require(bytes(tx) == raw and len(tx.signatures) == tx.message.header.num_required_signatures == 2,
            "wrong transaction encoding or signer count")
    require(set(tx.message.account_keys[:2]) == {PAYER, USER} and tx.message.account_keys[0] == PAYER,
            "unexpected signers")
    for i, signature in enumerate(tx.signatures):
        require(signature.verify(tx.message.account_keys[i], bytes(tx.message)), "invalid transaction signature")
    require(len(tx.message.instructions) == 1, "wrong instruction count")
    ix = tx.message.instructions[0]
    keys = tx.message.account_keys
    require(keys[ix.program_id_index] == PROGRAM and bytes(ix.data) == discriminator, "wrong invoked instruction")
    require([keys[i] for i in ix.accounts] == [TARGET, USER, Pubkey.default(), EVENT, PROGRAM], "wrong account routing")
    require(set(keys) == {PAYER, USER, TARGET, Pubkey.default(), EVENT, PROGRAM}, "unexpected message key")
    header = tx.message.header
    for i, key in enumerate(keys):
        writable = i < header.num_required_signatures - header.num_readonly_signed_accounts or \
            header.num_required_signatures <= i < len(keys) - header.num_readonly_unsigned_accounts
        require(writable == (key in {PAYER, USER, TARGET}), "wrong account privilege")
    return len(tx.signatures)


def validate(report, repo, candidate, build_record):
    require(report["status"] == "passed" and report["problems"] == [], "partial/failed probe")
    require(report["mode"] in ("rebuilt-baseline", "corrected"), "unknown probe mode")
    require(report["cases_spec"] == focused_cases() and len(report["cases"]) == 12, "wrong focused cases")
    require(report["original_sha256"] == digest((repo / "evidence/original/pump/deployed.so").read_bytes()) == ORIGINAL_SHA,
            "wrong original")
    require(report["candidate_sha256"] == digest(candidate.read_bytes()), "wrong candidate")
    expected = pinned_source(repo).copy()
    kind = "baseline" if report["mode"] == "rebuilt-baseline" else "corrected"
    if kind == "corrected":
        expected[SOURCE] = CORRECTED_SHA
    record = json.loads(build_record)
    require(report["build_binding"] == {"sha256": digest(build_record), "record": record}, "build binding changed")
    require(record["kind"] == kind and record["accepted_build"] is True and record["returncode"] == 0 and
            record["source_unchanged"] is True and record["source_sha256"] == record["source_after_sha256"] == expected and
            record["candidate_sha256"] == report["candidate_sha256"], "wrong source build")
    wanted = {"scripts/pump_extend_differential.py", "evidence/upstream/pump.json",
              "repro/pump/extend-diagnostics/runtime_probe.py", "repro/pump/extend-diagnostics/recovery.py",
              "repro/pump/extend-diagnostics/verify_runtime.py"}
    require(set(report["inputs"]) == wanted and all(digest((repo / name).read_bytes()) == value for name, value in report["inputs"].items()), "runtime input changed")
    idl = load_json(repo / "evidence/upstream/pump.json")
    instruction = next(i for i in idl["instructions"] if i["name"] == "extend_account")
    discriminator = bytes(instruction["discriminator"])
    accounts = {a["name"]: bytes(a["discriminator"]) for a in idl["accounts"]}
    signatures = 0
    expected_checkpoints = []
    unique_transactions = set()
    require(report["attempting"] is None, "incomplete runtime side")
    for index, (spec, row) in enumerate(zip(focused_cases(), report["cases"])):
        require(row["case"] == spec, "changed case order or payload")
        first, second = row["original"], row["candidate"]
        require(first["transaction_base64"] == second["transaction_base64"], "original/candidate transaction bytes differ")
        unique_transactions.add(first["transaction_base64"])
        require(all(first[key] == second[key] for key in EFFECTS), "runtime effects differ")
        require(first["error"] is None, "control unexpectedly failed")
        for side, result in (("original", first), ("candidate", second)):
            expected_checkpoints.append({"case_index": index, "side": side, "case": spec,
                                         "transaction_base64": result["transaction_base64"]})
            signatures += signed_payload(result["transaction_base64"], discriminator)
            fixture_effects(result, spec, accounts[spec["kind"]])
        original_logs = full_logs_without_compute(first["logs"])
        candidate_logs = full_logs_without_compute(second["logs"])
        message = expected_message(spec)
        if message:
            require(first["logs"].count(message) == 1, "original message missing/duplicated")
            require(original_logs == [f"Program {PROGRAM} invoke [1]", "Program log: Instruction: ExtendAccount",
                                      message, f"Program {PROGRAM} success"], "original no-growth diagnostic order changed")
            expected_logs = [line for line in original_logs if line != message] if kind == "baseline" else original_logs
            require(second["logs"].count(message) == (0 if kind == "baseline" else 1), "unexpected candidate diagnostic")
        else:
            expected_logs = original_logs
        require(candidate_logs == expected_logs, "full diagnostic log mismatch")
    require(report["pre_send_transactions"] == expected_checkpoints, "missing, changed or reordered pre-send transaction evidence")
    return {"passed": True, "cases": 12, "raw_signature_checks": signatures,
            "unique_raw_transactions": len(unique_transactions), "log_exclusions": "compute-use lines only"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=ROOT)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--build-record", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(validate(load_json(a.report), a.repo, a.candidate, a.build_record.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
