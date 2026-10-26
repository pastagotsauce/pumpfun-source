#!/usr/bin/env python3
"""Authenticate original zero-bucket instructions and hosted observation members."""
import io
import json
import re
import struct

from elftools.elf.elffile import ELFFile
from recovery import PACKAGE, ROOT, ORIGINAL_SHA, digest, require, read_report


def original_window(original, assembly):
    require(digest(original) == ORIGINAL_SHA, "wrong original")
    rows = []
    for line in assembly.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s*((?:[0-9a-f]{2} )+)\s", line)
        if match:
            offset, raw = int(match[1], 16), bytes.fromhex(match[2])
            require(original[offset:offset + len(raw)] == raw, "assembly bytes differ from original")
            rows.append((offset, len(raw)))
    ranges = [(0x59408, 0x59428), (0x59c08, 0x59c60), (0x59e08, 0x59ef8), (0x6d128, 0x6d208)]
    require({offset + n for offset, size in rows for n in range(size)} == {n for start, end in ranges for n in range(start, end)},
            "incomplete or expanded instruction excerpt")
    require(original[0x11bdd0:0x11bdd0 + 32] == b"Nothing to sweep for fee bucket ", "wrong literal")
    require(struct.unpack_from("<IIQ", original, 0x122580) == (0, 0x11bdd0, 32), "wrong relocated format slice")
    branch = original[0x59c58:0x59c60]
    require(branch == bytes.fromhex("15 06 39 00 00 00 00 00") and
            0x59c58 + 8 * (1 + struct.unpack_from("<h", branch, 2)[0]) == 0x59e28, "wrong zero branch target")
    elf = ELFFile(io.BytesIO(original))
    symbols = elf.get_section_by_name(".dynsym")
    logs = [r for r in elf.get_section_by_name(".rel.dyn").iter_relocations() if r["r_offset"] == 0x59ee0]
    require(len(logs) == 1 and logs[0]["r_info_type"] == 10 and symbols.get_symbol(logs[0]["r_info_sym"]).name == "sol_log_",
            "log call relocation mismatch")
    return {"instruction_bytes": sum(size for _, size in rows), "zero_branch": "0x59c58 -> 0x59e28", "log_call": "0x59ee0 sol_log_"}


def observed_archive():
    base = PACKAGE / "observed"
    raw_manifest = (base / "manifest.json").read_bytes()
    require(digest(raw_manifest) == "d53d3a825b72baba567cedc6552a3d74dce495cc8c643644c0b4cbdc54496924", "observation manifest changed")
    manifest = json.loads(raw_manifest)
    require(manifest["run_id"] == 40291256769 and manifest["artifact_id"] == 12636451641 and
            manifest["archive_sha256"] == "81aa55b595b44b4bda2ba237a2cb4c3ba8004cd643e4033cd41f1188c4da9460", "wrong archive identity")
    require(set(manifest["members"]) == {"build-artifact.json", "runtime.json"}, "wrong artifact membership")
    for name, row in manifest["members"].items():
        stored = base / row["stored"]
        require(digest(stored.read_bytes()) == row["stored_sha256"], "stored member changed")
        raw = read_report(stored)
        require(digest(raw) == row["raw_sha256"] and len(raw) == row["raw_bytes"], "raw member changed")
    for name, sha in manifest["provenance_sha256"].items():
        require(digest((base / name).read_bytes()) == sha, "provenance changed")
    run = json.loads((base / "run.json").read_bytes())
    artifact = json.loads((base / "artifact.json").read_bytes())
    require(run["id"] == manifest["run_id"] and run["conclusion"] == "success" and run["head_sha"] == manifest["head_sha"], "run mismatch")
    require(artifact["id"] == manifest["artifact_id"] and artifact["digest"] == "sha256:" + manifest["archive_sha256"] and
            artifact["size_in_bytes"] == manifest["archive_bytes"] == 10736 and artifact["workflow_run"]["id"] == run["id"], "artifact mismatch")
    return {"hosted_members": len(manifest["members"]), "run_id": run["id"]}


if __name__ == "__main__":
    result = original_window((ROOT / "evidence/original/pump_amm/deployed.so").read_bytes(),
                             (PACKAGE / "original-zero-branch.asm").read_text())
    print(json.dumps({**result, **observed_archive()}, indent=2))
