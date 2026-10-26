"""Recheck the original branch/data witness and preserved selected raw receipts."""
import base64
import io
import json
import struct
import gzip
from elftools.elf.elffile import ELFFile
from solders.transaction import Transaction
from solders.pubkey import Pubkey
from recovery import (ROOT, PACKAGE, ORIGINAL_SHA, BASELINE_SHA, SOURCE, digest, require,
                      load_json, pinned_source, patched_source, expected_message, TARGETS)


def original_proof(raw):
    require(digest(raw) == ORIGINAL_SHA, "original capture changed")
    proof = load_json(PACKAGE / "inputs/original-window.json")
    window = proof["window"]
    require(raw[window["start"]:window["end"]].hex() == window["raw_hex"] and
            digest(bytes.fromhex(window["raw_hex"])) == window["sha256"] ==
            "539244734892550dd2e3d6a333ae015141afa9bf163dc2e078d37b5d8e6b2a58", "original window changed")
    for helper in proof["helpers"]:
        body = raw[helper["start"]:helper["end"]]
        require(body.hex() == helper["raw_hex"] and digest(body) == helper["sha256"], "original helper changed")
    wrapper = proof["wrapper"]
    body = raw[wrapper["start"]:wrapper["end"]]
    require(body.hex() == wrapper["raw_hex"] and digest(body) == wrapper["sha256"], "original wrapper changed")
    require(raw[1228440:1228464].hex() == "18010000c27e1b000000000000000000b70200001a000000" and
            raw[1801922:1801948] == b"Instruction: ExtendAccount", "wrong original instruction wrapper")
    require(raw[1228824:1228832].hex() == "85100000171ffeff" and
            1228824 + 8 + struct.unpack_from("<i", raw, 1228828)[0] * 8 == 243928, "wrong wrapper-to-body call")
    for data in proof["data"]:
        require(raw[data["address"]:data["address"] + data["bytes"]].hex() == data["raw_hex"], "original data changed")
    expected = {
        243984: "bf09000000000000", 243992: "7b9aa8fd00000000",
        244752: "bf17000000000000", 244760: "7b7ab0fd00000000",
        244768: "1d791d0000000000", 244776: "2d79010000000000", 244784: "0500560000000000",
        244832: "7b1a58ff00000000", 244848: "07010000a8fdffff", 244856: "7b1a88fe00000000",
        244880: "7b1a90fe00000000", 244888: "7b1a80fe00000000", 244904: "07010000b0fdffff",
        244912: "7b1a78fe00000000", 244928: "7a0a50ff02000000", 244936: "7a0a60ff02000000",
        244976: "85100000aade0200", 244984: "79a1e8fe00000000", 244992: "79a2f0fe00000000",
        245000: "0500030000000000", 245024: "b702000024000000", 245032: "85100000ffffffff",
    }
    require(all(raw[pc:pc + 8].hex() == code for pc, code in expected.items()), "proved register/branch/call changed")
    for pc, target in ((244768, 245008), (244776, 244792), (244784, 245480), (245000, 245032)):
        require(pc + 8 + struct.unpack_from("<h", raw, pc + 2)[0] * 8 == target, "wrong branch target")
    require(raw[245008:245024].hex() == "18010000506d1b000000000000000000", "wrong equality string")
    require(raw[1797456:1797492] == b"Account already has the correct size", "wrong equality payload")
    pieces = []
    for at in (1825608, 1825624):
        pointer, length = struct.unpack_from("<QQ", raw, at)
        require(pointer & 0xffffffff == 0, "unexpected stored pointer")
        pieces.append(raw[pointer >> 32:(pointer >> 32) + length])
    require(pieces == [b"Account already has more than ", b" bytes: "], "wrong format pieces")
    elf = ELFFile(io.BytesIO(raw))
    rel = elf.get_section_by_name(".rel.dyn")
    symbols = elf.get_section(rel["sh_link"])
    relocations = {x["r_offset"]: (x["r_info_type"], symbols.get_symbol(x["r_info_sym"]).name) for x in rel.iter_relocations()}
    require(relocations[245032] == (10, "sol_log_"), "log call not bound to sol_log_")
    require(relocations[1228464] == (10, "sol_log_") and relocations[1228440][0] == 8, "instruction log binding changed")
    require(all(relocations[pc][0] == 8 for pc in (244792, 244864, 245008, 1825608, 1825624)), "data relocation missing")
    return {"instruction_wrapper": [1228408, 1229680], "wrapper_body_call": 1228824,
            "inferred_window": [243928, 249168], "equality_branch": 244768, "greater_branch": 244776,
            "growth_target": 245480, "shared_log_call": 245032,
            "format_argument_order": ["target size at frame-592", "current size at frame-600"],
            "limits": "Full window retained; no historical function-boundary or transitive semantic-equivalence claim."}


def saved_receipts():
    provenance = load_json(PACKAGE / "inputs/receipt-provenance.json")
    for name, row in provenance["selected_build_inputs"].items():
        retained = (PACKAGE / "inputs" / name).read_bytes()
        decoded = gzip.decompress(retained) if name.endswith(".gz") else retained
        require(digest(retained) == row["retained_sha256"] and digest(decoded) == row["raw_sha256"] and len(decoded) == row["raw_bytes"], "selected historical build/gate identity changed")
    layout_raw = gzip.decompress((PACKAGE / "inputs/selected-layout.json.gz").read_bytes())
    members_raw = gzip.decompress((PACKAGE / "inputs/selected-archive-members.json.gz").read_bytes())
    require(digest(layout_raw) == provenance["layout_raw_sha256"] and digest(members_raw) == provenance["archive_members_raw_sha256"], "prior archive manifest binding changed")
    require(json.loads(layout_raw)["files"]["runtime-repository.tar.gz"] == provenance["runtime_archive"], "prior archive identity changed")
    members = json.loads(members_raw)["runtime-repository.tar.gz"]
    for name, row in provenance["copies"].items():
        raw = (PACKAGE / "inputs" / name).read_bytes()
        decoded = gzip.decompress(raw)
        require(digest(raw) == row["retained_gzip_sha256"] and digest(decoded) == row["decoded_sha256"] and len(decoded) == row["decoded_bytes"], "retained raw/gzip identity changed")
        original = raw if row["representation"] == "unchanged original gzip" else decoded
        require(row["original"] == members[row["original_member"]] and digest(original) == row["original"]["sha256"] and len(original) == row["original"]["bytes"], "retained file is not the published raw archive member")
    report = load_json(PACKAGE / "inputs/selected-extension.json.gz")
    require(report["original_sha256"] == ORIGINAL_SHA and report["candidate_sha256"] == BASELINE_SHA and
            len(report["cases"]) == 308 and report["mismatches"] == [], "wrong selected extension receipt")
    signature_count = 0
    changed = []
    for row in report["cases"]:
        require(row["diff"] == [] and all(row["original"][k] == row["candidate"][k] for k in
                ("before", "after", "error", "events", "inner", "return")), "selected extension effects changed")
        for result in (row["original"], row["candidate"]):
            raw = base64.b64decode(result["transaction_base64"], validate=True)
            tx = Transaction.from_bytes(raw)
            require(bytes(tx) == raw and all(tx.verify_with_results()), "invalid selected differential signature")
            signature_count += len(tx.signatures)
        case = row["case"]
        if case["kind"] in TARGETS and row["original"]["error"] is None and case.get("size", 8) >= TARGETS[case["kind"]]:
            message = expected_message(case)
            require(row["original"]["logs"].count(message) == 1 and message not in row["candidate"]["logs"], "selected diagnostic witness changed")
            changed.append(case["name"])
    signed = load_json(PACKAGE / "inputs/selected-signed.json.gz")
    require(set(signed) == {"original", "candidate"} and all(len(rows) == 16 for rows in signed.values()), "wrong selected signed rows")
    signed_count = 0
    program = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    idl = load_json(ROOT / "evidence/upstream/pump.json")
    discriminator = bytes(next(i for i in idl["instructions"] if i["name"] == "extend_account")["discriminator"])
    for rows in signed.values():
        for row in rows:
            raw = base64.b64decode(row["transaction_base64"], validate=True)
            tx = Transaction.from_bytes(raw)
            require(bytes(tx) == raw and all(tx.verify_with_results()) and str(tx.signatures[0]) == row["signature"], "invalid raw selected signature")
            instruction = tx.message.instructions[-1]
            require(str(tx.message.account_keys[instruction.program_id_index]) == program and
                    bytes(instruction.data) == discriminator + bytes.fromhex(row["case"].get("trailing", "")), "signed receipt invokes a different instruction")
            signed_count += len(tx.signatures)
    require(signed_count == 62, "wrong selected signature slots")
    for index in (4, 5):
        first, second = signed["original"][index], signed["candidate"][index]
        require(first["case"] == second["case"] and first["error"] is second["error"] is None, "wrong selected successful witness")
        message = expected_message(first["case"])
        require(first["logs"].count(message) == 1 and message not in second["logs"], "missing selected signed diagnostic witness")
        target = str(Pubkey.from_bytes(bytes([229]) * 32))
        for row in (first, second):
            require(row["before"][target] == row["after"][target], "selected no-growth path changes target")
        for stage in ("before", "after"):
            a, b = json.loads(json.dumps(first[stage])), json.loads(json.dumps(second[stage]))
            for state in (a, b):
                state[program].pop("data_sha256", None)
                state[program].pop("data_length", None)
            require(a == b, "selected signed diagnostic case differs in state")
        require(first["return_data"] == second["return_data"] and
                not any(line.startswith("Program data:") for row in (first, second) for line in row["logs"]), "selected no-growth return/event differs")
    return {"differential_cases": 308, "differential_signatures": signature_count,
            "diagnostic_witness_cases": changed, "surfpool_raw_records": 32, "surfpool_signature_slots": signed_count}


def main():
    pinned_source()
    patched_source((ROOT / SOURCE).read_bytes())
    print(json.dumps({"original": original_proof((ROOT / "evidence/original/pump/deployed.so").read_bytes()),
                      "selected_receipts": saved_receipts(), "new_builds": 0, "new_runtime_executions": 0}, indent=2))


if __name__ == "__main__":
    main()
