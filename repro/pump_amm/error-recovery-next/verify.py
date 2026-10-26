#!/usr/bin/env python3
"""Verify saved AMM liquidity error evidence; never compile or execute a program."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[2]
RECEIPT = "repro/pump_amm/owner6048-v144/runtime/runtime-01/liquidity.json.gz"
RECEIPT_SHA = "8e8e68d6005cb6c0ccfdef830579b5daa603177df576d9f7ac44f992660b4fe1"
RAW_SHA = "3a0735d3ca936528aadd95136441e92815b1fc8b2efc83f05d6b3aeb56c96906"
ORIGINAL_SHA = "6a7ad34596d83b4c435b32f458a56e718e9f82eb4ad38e4316616d15d24d8ff7"
BASELINE_SHA = "09bee0dfd751dc6ae0240bbac262933c6bda6e0c94aa643f82c57f2956c3a117"
SOURCE_SHA = "ba0be4636bd22d63b9d3e18907d00e15316386f8f1507ad01ebe31d8134349b1"
ERROR = "TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom(6087))))"
ORIGIN = "programs/pump-amm/src/utils/token.rs:21"
BAD_CASES = {
    ("deposit", f"self-transfer=({index}, {amount})")
    for index in (6, 7) for amount in (1, 1000000)
}
COMPUTE = re.compile(r"^Program [1-9A-HJ-NP-Za-km-z]+ consumed \d+ of \d+ compute units$")
ERROR_LOCATION = re.compile(
    r"^(Program log: AnchorError thrown in )[^\r\n]+:\d+"
    r"(\. Error Code: SelfTransferNotAllowed\. Error Number: 6087\. Error Message: .*)$"
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalized_logs(logs):
    """Ignore compute costs and only the 6087 source coordinate, nothing else."""
    return [ERROR_LOCATION.sub(r"\1<source>\2", line) for line in logs if not COMPUTE.fullmatch(line)]


def compared_keys(logs):
    for index, line in enumerate(logs):
        if line == "Program log: Left:":
            require(index + 3 < len(logs), "incomplete compared-key diagnostic")
            require(logs[index + 2] == "Program log: Right:", "malformed compared-key diagnostic")
            return logs[index:index + 4]
    return []


def inspect_saved(receipt):
    require(receipt["original_sha256"] == ORIGINAL_SHA, "wrong original binding")
    require(receipt["candidate_sha256"] == BASELINE_SHA, "wrong baseline binding")
    require(receipt["case_count"] == len(receipt["cases"]) == 680, "incomplete saved corpus")
    require(receipt["mismatches"] == [], "changed legacy non-log acceptance")
    observed = []
    for index, row in enumerate(receipt["cases"]):
        original, candidate = row["original"], row["candidate"]
        if original["error"] != ERROR:
            continue
        identity = (row["instruction"], row["case"])
        require(identity in BAD_CASES, "unexpected 6087 case")
        require(candidate["error"] == ERROR, "different candidate error")
        require(row["match"] and row["mismatched_fields"] == [], "legacy case did not pass")
        require({k: v for k, v in original.items() if k != "logs"} ==
                {k: v for k, v in candidate.items() if k != "logs"}, "non-log output differs")
        require(any(ORIGIN in line and "Error Number: 6087." in line for line in original["logs"]),
                "missing original 6087 origin")
        require(not compared_keys(original["logs"]), "original contains compared keys")
        decoration = compared_keys(candidate["logs"])
        require(decoration == ["Program log: Left:",
                "Program log: GseMAnNDvntR5uFePZ51yZBXzNSn7GdFPkfHwfr6d77J",
                "Program log: Right:",
                "Program log: DXyM8yAHqpMzDtvwz5DXoEUQmPxjJPMKCASCPhLMKpEx"],
                "unexpected baseline compared keys")
        clean = list(candidate["logs"])
        start = clean.index("Program log: Left:")
        del clean[start:start + 4]
        require(normalized_logs(original["logs"]) == normalized_logs(clean),
                "difference extends beyond compared keys and source/compute")
        observed.append({"index": index, "instruction": identity[0], "case": identity[1],
                         "error": ERROR, "extra_candidate_log_lines": decoration})
    require({(r["instruction"], r["case"]) for r in observed} == BAD_CASES and len(observed) == 4,
            "missing or duplicate rejected self-transfer cases")
    return observed


def verify_receipt_bytes(compressed):
    require(digest(compressed) == RECEIPT_SHA, "saved compressed receipt changed")
    raw = gzip.decompress(compressed)
    require(digest(raw) == RAW_SHA, "saved receipt payload changed")
    return inspect_saved(json.loads(raw))


def verify_original_window(original, assembly):
    require(digest(original) == ORIGINAL_SHA, "original image changed")
    pattern = re.compile(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} ){7,15}[0-9a-f]{2})\s+(.+)$")
    cursor = 456200
    for line in assembly.splitlines():
        match = pattern.match(line)
        require(match is not None, "unrecognized retained disassembly record")
        address = int(match[1], 16)
        raw = bytes.fromhex(match[2])
        require(address == cursor and len(raw) in (8, 16), "incomplete/overlapping original window")
        require(original[address:address + len(raw)] == raw, "disassembly bytes do not match original")
        cursor += len(raw)
    require(cursor == 456856, "incomplete original guard window")
    require(original[456736:456744].hex() == "620a88ffc7170000", "6087 store changed")
    require(original[456752:456760].hex() == "620a08ff15000000", "line-21 store changed")
    require(original[1167392:1167428] == b"programs/pump-amm/src/utils/token.rs", "origin path changed")
    # These are numeric direct-call targets, not claims about unknown callees.
    calls = [456248, 456312]
    require(all(p + 8 + struct.unpack_from("<i", original, p + 4)[0] * 8 == 1153248 for p in calls),
            "shared 32-byte comparison target changed")
    require(all(p + 8 + struct.unpack_from("<h", original, p + 2)[0] * 8 == 456832
                for p in (456280, 456336)), "guard return branches changed")
    return {"start": 456200, "end_exclusive": 456856, "bytes": 656,
            "sha256": digest(original[456200:456856])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    rows = verify_receipt_bytes((args.repo / RECEIPT).read_bytes())
    window = verify_original_window((args.repo / "evidence/original/pump_amm/deployed.so").read_bytes(),
                                    (PACKAGE / "original-guard.asm").read_text())
    print(json.dumps({"saved_receipt_verified": True, "hidden_log_mismatches": rows,
                      "original_window": window, "new_program_execution": False,
                      "new_compilation": False, "whole_binary_identity": False}, indent=2))


if __name__ == "__main__":
    main()
