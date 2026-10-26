#!/usr/bin/env python3
"""Recheck retained Mayhem output and build receipts; never build or execute it."""
import argparse
import gzip
import json
from pathlib import Path
import sys
import tomllib

sys.dont_write_bytecode = True
from evidence import Elf, compare, require, same_location_payload, sha

P = Path(__file__).resolve().parent
RUN = "run-40293434354"
ARTIFACT_MEMBERS_SHA = "cc4955c318755e383cc979ad1cb5b57b7b59b29866582dd0e1980796838c3ab6"
ARTIFACT_ZIP_SHA = "f4c6b08f2e38f3a9447b0dbc35b39b60f2836bcca851b57a969f6ca63c3bb397"
BUILD_HEAD = "cff253dc6d84874d95a74805a631c7d3096b8c7a"
INPUTS_SHA = "f7a141ef09a60c773db988ebe5b07eb7a51d6d9c0da9c807cd901550a9ced20d"
CANDIDATE_SHA = "e59f9f970813102e04327ce0502f8359dd217cfaebec942172614ab84dd6ac88"
SYMBOLS_SHA = "9a3d7ed93fd47670ef48c36cb3540fa6847906c9292fc138f302ca1a1aedf2bd"


def read_json(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def members(directory, exclude_manifest=False):
    rows = []
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Symlinked retained evidence")
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        name = path.relative_to(directory).as_posix()
        if exclude_manifest and name == "manifest.json":
            continue
        data = path.read_bytes()
        rows.append({"name": name, "bytes": len(data), "sha256": sha(data)})
    return sorted(rows, key=lambda row: row["name"])


def verify(package, repo):
    expected_package = read_json(package / "manifest.json")
    require(members(package, exclude_manifest=True) == expected_package["files"], "Package manifest differs")
    result_dir = package / "results" / RUN
    actual = members(result_dir)
    encoded = json.dumps(actual, sort_keys=True, separators=(",", ":")).encode("ascii")
    require(len(actual) == 47 and sha(encoded) == ARTIFACT_MEMBERS_SHA, "Actual hosted artifact provenance seal differs")
    require(actual == read_json(package / "results/artifact-members.json"), "Published member receipt differs")
    raw_manifest = read_json(result_dir / "manifest.json")
    require(raw_manifest == {row["name"]: {"bytes": row["bytes"], "sha256": row["sha256"]}
                             for row in actual if row["name"] != "manifest.json"}, "Original artifact manifest differs")
    provider = read_json(package / "results/hosted.json")
    require(provider["repository"] == "pastagotsauce/pumpfun-source" and provider["run_id"] == 40293434354
            and provider["run_attempt"] == 1 and provider["job_id"] == 121473647776
            and provider["head_sha"] == BUILD_HEAD and provider["conclusion"] == "success"
            and provider["event"] == "workflow_dispatch" and provider["artifact_id"] == 12636926978
            and provider["artifact_name"] == "mayhem-linux-v154-40293434354-1"
            and provider["artifact_bytes"] == 1555883 and provider["artifact_digest"] == "sha256:" + ARTIFACT_ZIP_SHA,
            "Wrong immutable hosted identity")
    raw_inputs = (package / "inputs.json").read_bytes()
    require(sha(raw_inputs) == INPUTS_SHA and raw_inputs == (result_dir / "input-pins.json").read_bytes(), "Input provenance changed")
    frozen = json.loads(raw_inputs)
    for name, row in read_json(result_dir / "driver-bindings.json").items():
        source = (package / name).read_bytes()
        require(source == (result_dir / "driver" / name).read_bytes()
                and row == {"bytes": len(source), "sha256": sha(source)}, "Executing helper differs: " + name)
    source = result_dir / "source"
    observed_source = {row["name"]: row["sha256"] for row in members(source)}
    require(observed_source == frozen["source_sha256"] == read_json(result_dir / "source-before.json"), "Source inputs differ")
    for name in ("source-after-compile.json", "source-after.json"):
        after = read_json(result_dir / name)
        require(after == {row["name"]: {"bytes": row["bytes"], "sha256": row["sha256"]} for row in members(source)}, "Source after-receipt differs")
    tools = read_json(result_dir / "tools-before.json.gz")
    require(tools == read_json(result_dir / "tools-after.json.gz"), "Tool distribution changed")
    for name, metadata in frozen["compiler"]["selected_members"].items():
        require(tools["compiler"][name] == metadata, "Pinned compiler member differs")
    require(tools["stripper"]["llvm/bin/llvm-objcopy"]["sha256"] == frozen["stripper"]["objcopy_sha256"], "Stripper differs")
    for phase in ("compiler", "stripper"):
        receipt = read_json(result_dir / (phase + ".tar.bz2.receipt.json"))
        require(receipt["complete"] is True and receipt["url"] == frozen[phase]["url"]
                and receipt["observed_sha256"] == receipt["expected_sha256"] == frozen[phase]["sha256"]
                and receipt["observed_bytes"] == receipt["expected_bytes"] == frozen[phase]["bytes"], "Tool archive receipt differs")
    registry = read_json(result_dir / "registry-before.json.gz")
    require(registry == read_json(result_dir / "registry-after.json.gz"), "Dependency inputs changed")
    lock = tomllib.loads((source / "programs/mayhem/Cargo.lock").read_text())
    locked = {row["name"] + "-" + row["version"]: row["checksum"] for row in lock["package"] if "source" in row}
    require(len(locked) == 215 and {name: row["archive_sha256"] for name, row in registry.items()} == locked, "Locked registry receipt differs")
    commands = read_json(result_dir / "commands.json")
    require(all(row["exit"] == 0 for row in commands), "A retained command failed")
    require(sum(row["label"] == "compile" for row in commands) == 1 and sum(row["label"] == "strip" for row in commands) == 1,
            "Wrong build/strip attempt count")
    for row in commands:
        log = (result_dir / (row["label"] + ".log")).read_bytes()
        require(row["log_sha256"] == sha(log) and row["log_bytes"] == len(log), "Command log changed")
    compile_command = next(row for row in commands if row["label"] == "compile")
    require(compile_command["argv"][4:] == ["--release", "--target", "sbpf-solana-solana", "--locked", "--offline", "--verbose"]
            and compile_command["environment"]["CARGO_TARGET_SBPF_SOLANA_SOLANA_RUSTFLAGS"] == "-Zremap-cwd-prefix=",
            "Recipe flags differ")
    candidate = (result_dir / "candidate.so").read_bytes()
    symbols = (result_dir / "unstripped.so").read_bytes()
    require(sha(candidate) == CANDIDATE_SHA and len(candidate) == 599776 and sha(symbols) == SYMBOLS_SHA, "Compiler output identity differs")
    require(Elf(candidate).allocated() == Elf(symbols).allocated(), "Stripped image is not bound to symbols")
    original = (repo / frozen["original"]["path"]).read_bytes()
    selected = (repo / frozen["selected"]["path"]).read_bytes()
    require(sha(original) == frozen["original"]["sha256"] and sha(selected) == frozen["selected"]["sha256"], "External captured/selected input differs")
    original_comparison, selected_comparison = compare(original, candidate), compare(selected, candidate)
    require(original_comparison == read_json(result_dir / "whole-original-comparison.json")
            and selected_comparison == read_json(result_dir / "selected-darwin-comparison.json"), "Raw comparison receipt differs")
    original_location = Elf(original).location(632832)
    compiled = Elf(symbols).constructor_locations()
    require(original_location == read_json(result_dir / "original-location.json")
            and compiled == read_json(result_dir / "compiled-location.json"), "Location derivation differs")
    require(same_location_payload(original_location, compiled["location"]), "Full raw Location payload differs")
    state = read_json(result_dir / "result.json")
    require(state["status"] == "MEASURED" and state["build_attempts"] == 1 and state["compile_exit"] == state["strip_exit"] == 0
            and state["source_unchanged"] is True and state["source_changed"] is False
            and state["distribution_location_matches_original"] is True
            and state["full_byte_equality"] is False and state["historical_uploader_recipe"] is None
            and all(state[key] is False for key in ("runtime_executed", "binary_patching", "padding")), "Recorded scope/result changed")
    for filename, data in (("candidate.so", candidate), ("unstripped.so", symbols)):
        require(state["produced_outputs"][filename] == {"bytes": len(data), "sha256": sha(data)}, "Output receipt differs")
    linux, darwin = Elf(candidate), Elf(selected)
    section_differences = {}
    for name, row in linux.sections.items():
        if name and row[1] != 8:
            other = darwin.sections[name]
            section_differences[name] = compare(darwin.read(other[4], other[5]), linux.read(row[4], row[5]))["differing_shared_positions"]
    return {"scope": "Retained artifact verification only; no new build or runtime execution",
            "candidate_sha256": sha(candidate), "candidate_bytes": len(candidate),
            "source_files": len(observed_source), "locked_registry_packages": len(registry),
            "original_location_raw_payload_equal": True, "location_path_bytes": compiled["location"]["file_length"],
            "whole_original_comparison": original_comparison, "selected_darwin_comparison": selected_comparison,
            "section_differences_vs_darwin": section_differences, "historical_uploader_recipe": None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=P.parents[2])
    args = parser.parse_args()
    print(json.dumps(verify(P, args.repo.resolve()), indent=2))
