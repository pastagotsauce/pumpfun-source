#!/usr/bin/env python3
"""Check the static build hypothesis; this invokes no compiler or program."""
import argparse
import json
from pathlib import Path
import sys
import tarfile

sys.dont_write_bytecode = True
from evidence import Elf, require, sha
from run import P, digest, pins

LOCATIONS_SHA = "cafa749efa65e86c03a6b651f7c30dafd516d51f19ff56b34a5783cb6b003c17"


def verify(repo, archive=None):
    frozen = pins()
    raw = (P / "locations.json").read_bytes()
    require(sha(raw) == LOCATIONS_SHA, "Saved Location pins changed")
    locations = json.loads(raw)
    require(digest(repo / frozen["source_receipt"]["path"]) == frozen["source_receipt"]["sha256"], "Source receipt changed")
    receipt = json.loads((repo / frozen["source_receipt"]["path"]).read_bytes())
    require(receipt["actual_source_sha256"] == frozen["source_sha256"] and receipt["source_unchanged"] is True,
            "Source snapshot is not the actual selected build input")
    require(len(frozen["source_sha256"]) == 14 and all(digest(repo / name) == value for name, value in frozen["source_sha256"].items()),
            "Current14 source inputs changed")
    for key, saved in zip(("original", "selected"), locations):
        data = (repo / frozen[key]["path"]).read_bytes()
        require(sha(data) == frozen[key]["sha256"] and len(data) == frozen[key]["bytes"], "ELF input changed")
        observed = Elf(data).location(saved["reference_pc"])
        require(all(saved[name] == value for name, value in observed.items()), "Location chain changed")
    symbols = (repo / frozen["selected_symbols"]["path"]).read_bytes()
    selected = (repo / frozen["selected"]["path"]).read_bytes()
    require(sha(symbols) == frozen["selected_symbols"]["sha256"], "Selected symbols changed")
    require(Elf(symbols).allocated() == Elf(selected).allocated(), "Selected symbol image binding differs")
    location = Elf(symbols).constructor_locations()
    require(location["location"]["reference_pc"] == locations[1]["reference_pc"], "Wrong selected constructor association")
    result = {"status": "STATIC_INPUTS_VERIFIED", "source_files": 14,
              "original_location": {k: locations[0][k] for k in ("file_display", "line", "column")},
              "selected_location": {k: locations[1][k] for k in ("file_display", "line", "column")},
              "compiler_executed": False, "runtime_executed": False, "linux_archive_checked": False}
    if archive is not None:
        require(archive.stat().st_size == frozen["compiler"]["bytes"] and digest(archive) == frozen["compiler"]["sha256"],
                "Official archive does not match publisher digest")
        expected, found = frozen["compiler"]["selected_members"], {}
        with tarfile.open(archive, "r|bz2") as package:
            for member in package:
                name = member.name.removeprefix("./")
                if name not in expected:
                    continue
                require(member.isfile() and name not in found, "Unexpected selected archive member")
                data = package.extractfile(member).read()
                found[name] = {"bytes": len(data), "sha256": sha(data)}
                if name.endswith("/string.rs"):
                    require(data.decode().splitlines()[2829] == '            .expect("a Display implementation returned an error unexpectedly");',
                            "Bundled alloc expression changed")
                if name.endswith(".rlib"):
                    require(data.count(locations[0]["file_display"].encode()) == 1 and
                            locations[1]["file_display"].encode() not in data, "Wrong alloc metadata path")
        require(found == expected, "Selected official members changed")
        result["linux_archive_checked"] = True
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=P.parents[2])
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.repo.resolve(), args.archive), indent=2))
