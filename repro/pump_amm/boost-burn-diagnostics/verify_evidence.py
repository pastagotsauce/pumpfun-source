#!/usr/bin/env python3
"""Validate historical signed boost receipts and original guard/operand bytes."""
import base64
import json
import re
import struct

from boost import (PACKAGE, ROOT, ORIGINAL_SHA, RECEIPT, RECEIPT_SHA, RAW_SHA, ORIGIN,
                   SITES, digest, require, read_report, normalized_logs, liquidity, sweep)


def verify_saved():
    compressed = (ROOT / RECEIPT).read_bytes()
    require(digest(compressed) == RECEIPT_SHA, "saved compressed receipt changed")
    raw = read_report(ROOT / RECEIPT)
    require(digest(raw) == RAW_SHA, "saved raw receipt changed")
    report = json.loads(raw)
    require(report["case_count"] == len(report["cases"]) == 506 and report["mismatches"] == [] and
            report["original_sha256"] == ORIGINAL_SHA and report["candidate_sha256"] == liquidity.BASELINE_SHA,
            "saved receipt binding changed")
    sites, transactions, signatures = {line: [] for line in SITES}, [], 0
    schema = {"error", "logs", "events", "inner", "return_data", "before", "after", "transaction_base64"}
    for index, row in enumerate(report["cases"]):
        original, candidate = row["original"], row["candidate"]
        require(set(original) == set(candidate) == schema, "incomplete saved effects")
        require(all(original[key] == candidate[key] for key in schema - {"logs"}), "saved signed inputs/effects differ")
        for result in (original, candidate):
            raw_tx = base64.b64decode(result["transaction_base64"], validate=True)
            tx = sweep.Transaction.from_bytes(raw_tx)
            require(bytes(tx) == raw_tx and len(tx.signatures) == tx.message.header.num_required_signatures and
                    all(tx.verify_with_results()), "invalid saved raw signature")
            transactions.append(raw_tx)
            signatures += len(tx.signatures)
        values = [line for line in original["logs"] if line.startswith(("Program log: Left:", "Program log: Right:"))]
        observed = [line for line in candidate["logs"] if line.startswith(("Program log: Left:", "Program log: Right:"))]
        if values == observed:
            continue
        require(len(values) == 2 and not observed, "unexpected saved diagnostic shape")
        matches = [line for line in SITES if any(f"{ORIGIN}:{line}." in log for log in original["logs"])]
        require(len(matches) == 1, "unaccounted decoration site")
        line = matches[0]
        code = SITES[line][0]
        require(original["error"] == f"TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom({code}))))",
                "wrong original program error")
        stripped = list(original["logs"])
        for value in values:
            stripped.remove(value)
        require(normalized_logs(stripped) == normalized_logs(candidate["logs"]), "additional saved log difference")
        require(sum(" invoke [" in entry for entry in original["logs"]) == 1, "error came after a dependency invocation")
        sites[line].append(index)
    require({line: len(indices) for line, indices in sites.items()} == {250: 4, 255: 16, 273: 38, 274: 16, 280: 3},
            "saved diagnostic coverage changed")
    require(signatures == 1018 and len(transactions) == 1012 and len(set(transactions)) == 125,
            "saved signed observation coverage changed")
    return {"historical_cases": 506, "same_signed_inputs_and_effects": 506, "signature_fields": signatures,
            "unique_transaction_bytes": len(set(transactions)), "numeric_diagnostic_rows": 77,
            "original_sites": {str(line): indices for line, indices in sites.items()}}


def verify_original():
    original = (ROOT / "evidence/original/pump_amm/deployed.so").read_bytes()
    require(digest(original) == ORIGINAL_SHA, "original binary changed")
    ranges = [(0x340, 0x378), (0x1840, 0x1878), (0x1fed8, 0x1fef8), (0x1fff0, 0x20030),
              (0x20590, 0x20658), (0x20858, 0x20960), (0x20a58, 0x20ba8), (0x20ba8, 0x20f08), (0x21600, 0x21708)]
    covered = set()
    for line in (PACKAGE / "original-boost-guards.asm").read_text().splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s*((?:[0-9a-f]{2} )+)\s", line)
        if match:
            pc, raw = int(match[1], 16), bytes.fromhex(match[2])
            require(original[pc:pc+len(raw)] == raw, "original instruction bytes differ")
            covered.update(range(pc, pc+len(raw)))
    require(covered == {pc for start, end in ranges for pc in range(start, end)}, "incomplete original excerpt")
    require(original[0x11c7c9:0x11c7c9 + 43] == ORIGIN.encode(), "original source-path literal changed")

    def instruction(pc, code, dst, src, immediate=None):
        actual, regs, displacement, value = struct.unpack_from("<BBhi", original, pc)
        require((actual, regs & 15, regs >> 4) == (code, dst, src) and
                (immediate is None or immediate == value), f"instruction field mismatch at {pc:#x}")
        return displacement, value

    branches = [(0x20018, 0x15, 1, 0, 0x20590), (0x20648, 0x15, 0, 0, 0x20858),
                (0x20a60, 0x15, 8, 0, 0x20ab0), (0x20cb0, 0x15, 8, 0, 0x20df0),
                (0x20cc0, 0xad, 8, 3, 0x20cd0), (0x20cc8, 0x05, 0, 0, 0x20ee8),
                (0x20ef0, 0x2d, 1, 8, 0x20f00), (0x20ef8, 0x05, 0, 0, 0x21600)]
    for pc, opcode, dst, src, target in branches:
        displacement, _ = instruction(pc, opcode, dst, src, 0)
        require(pc + 8 * (displacement + 1) == target, "wrong original branch destination")
    for pc, line in ((0x208e0, 250), (0x20b20, 255), (0x20e60, 273), (0x20d48, 274), (0x21670, 280)):
        instruction(pc, 0x62, 10, 0, line)
    for pc, code in ((0x208d0, 6002), (0x20b38, 6002), (0x20e78, 6001), (0x20d60, 6004), (0x21688, 6003)):
        instruction(pc, 0x62, 10, 0, code)
    calls = [(0x20940, 0x340), (0x20b88, 0x340), (0x20ec8, 0x340), (0x20dc0, 0x1840), (0x216e8, 0x1840)]
    for pc, target in calls:
        _, immediate = instruction(pc, 0x85, 0, 1)
        require(pc + 8 * (1 + immediate) == target, "wrong numeric-value helper")
    # The two variable-value call sites pass left in r4 and right in r5.
    instruction(0x20db0, 0xbf, 4, 8, 0)
    instruction(0x20db8, 0xbf, 5, 7, 0)
    instruction(0x20cf0, 0xbf, 7, 3, 0)
    require(instruction(0x20cb8, 0x79, 3, 10, 0)[0] == -0x7b8 and
            instruction(0x1fed8, 0x7b, 10, 4, 0)[0] == -0x7b8, "minimum operand chain changed")
    require(instruction(0x20ca0, 0x7b, 10, 8, 0)[0] == -0x7f0 and
            instruction(0x20ee8, 0x79, 1, 10, 0)[0] == -0x7f0 and
            instruction(0x216d8, 0x79, 4, 10, 0)[0] == -0x7f0, "old-base operand chain changed")
    instruction(0x216e0, 0xbf, 5, 8, 0)
    require(instruction(0x1858, 0x7b, 10, 5, 0)[0] == -0x120 and
            instruction(0x1860, 0x7b, 10, 4, 0)[0] == -0x128, "generic value ordering changed")
    instruction(0x368, 0x62, 10, 0, 0)
    instruction(0x370, 0x7a, 10, 0, 0)
    return {"original_instruction_bytes": len(covered), "used_zero_guard": "0x20018 -> 0x20590",
            "later_error_format_branch": "0x20648 -> 0x20858", "numeric_helper_calls": 5,
            "scope": "Absolute byte addresses; .text-relative labels retain their 0x120 section base. No compiler or VM execution."}


if __name__ == "__main__":
    print(json.dumps({**verify_saved(), **verify_original()}, indent=2))
