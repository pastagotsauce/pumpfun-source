#!/usr/bin/env python3
"""Verify retained ATA build evidence offline; never compile or run a program."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from prepare_order import BASELINE_BYTES, BASELINE_SHA256, parse_elf, prepare, region, require, verify_linked_order

P = Path(__file__).resolve().parent
REFERENCE_SHA256 = "6804554e69fd3a58caa191dc4a58f4c67223d30ca28ab8987f39fc18d2f7374d"
SOURCE_COMMIT = "f5ce86d43dd31ddefb96d4e8cdd67dd073dc5dca"
BUILD_COMMIT = "031b5b2906475ea30f5c6749df5695795247cec8"
ACTUAL_ARTIFACT_FILES = (
    "baseline-artifacts.json", "baseline-build.log", "baseline.so", "baseline.symbols.so",
    "commands.json", "image-inspect.json", "image-pull.log", "linker-help.txt", "order.json",
    "ordered-build.log", "ordered-strip.log", "ordered.so", "ordered.symbols.so", "result.json",
    "source-manifest.json", "symbol-order.txt", "toolchain.json",
)
# SHA256 of sorted {name,bytes,sha256} rows, canonical JSON (sorted keys, compact
# separators), derived from the actual hosted artifact, independent of package code.
ACTUAL_ARTIFACT_MEMBERS_SHA256 = "1454dc18b7654306263e33233109c511b471f94e09330b17bcf2beb161214f2b"
ACTUAL_ARTIFACT_ZIP_SHA256 = "7c7cf5a3f9bd12ccad227eca42f5d454829c796d1a5a23fd137f520b06284d07"
EXECUTED_INPUTS_SHA256 = "de68f6ecd80aa9c4a4a4558d531fa905c8003c44493dd62bda65079337a759ad"
COMPRESSED_ARTIFACT_FILES = {"source-manifest.json": "source-manifest.json.gz"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def artifact_bytes(directory, name):
    """Read original hosted member bytes from their lossless storage form."""
    data = (directory / COMPRESSED_ARTIFACT_FILES.get(name, name)).read_bytes()
    if name in COMPRESSED_ARTIFACT_FILES:
        try:
            return gzip.decompress(data)
        except (OSError, EOFError) as error:
            raise ValueError("Invalid compressed hosted artifact: " + name) from error
    return data


def allocated_sections(data):
    return {row["name"]: (row["address"], row["size"], row["type"],
                           region(data, row["offset"], row["size"]))
            for row in parse_elf(data) if row["flags"] & 2 and row["type"] != 8}


def verify(package, reference_path):
    package = package.resolve()
    manifest = read_json(package / "manifest.json")
    require(manifest["scope"] == "Retained source-build evidence; no new build or runtime replay", "Wrong manifest scope")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe manifest path")
        path = package / relative
        require(not path.is_symlink() and all(not parent.is_symlink() for parent in
                path.parents if parent != package and package in parent.parents), "Symlinked evidence")
        data = path.read_bytes()
        require(len(data) == expected["bytes"] and digest(data) == expected["sha256"],
                "Changed retained evidence: " + name)
    actual = {path.relative_to(package).as_posix() for path in package.rglob("*") if path.is_file()
              and "__pycache__" not in path.parts and path.name != "manifest.json"}
    require(actual == set(manifest["files"]), "Retained file inventory differs from manifest")

    result_dir = package / "results/run-40287588927"
    reference = reference_path.read_bytes()
    baseline = (result_dir / "baseline.so").read_bytes()
    baseline_symbols = (result_dir / "baseline.symbols.so").read_bytes()
    candidate = (result_dir / "ordered.so").read_bytes()
    candidate_symbols = (result_dir / "ordered.symbols.so").read_bytes()
    require(len(reference) == BASELINE_BYTES and digest(reference) == REFERENCE_SHA256, "Wrong captured reference")
    require(digest(baseline) == BASELINE_SHA256 and len(baseline) == BASELINE_BYTES, "Wrong source-built baseline")
    require(candidate == reference, "Raw source-built output differs from captured reference")
    require(sum(a != b for a, b in zip(reference, baseline)) == 307, "Baseline residual changed")
    require(allocated_sections(baseline_symbols) == allocated_sections(baseline), "Baseline strip binding differs")
    require(allocated_sections(candidate_symbols) == allocated_sections(candidate), "Ordered strip binding differs")

    generated_order, generated_report = prepare(baseline, baseline_symbols)
    require(generated_order == (result_dir / "symbol-order.txt").read_bytes(), "Saved order differs from source-built symbols")
    require(generated_report == read_json(result_dir / "order.json"), "Saved order report differs")
    verify_linked_order(candidate_symbols, generated_report)
    require(generated_report["function_symbols"] == 177, "Wrong function-symbol inventory")

    result = read_json(result_dir / "result.json")
    require(result["status"] == "EXACT_RECONSTRUCTED_RECIPE" and result["full_byte_equality"] is True,
            "Recorded result does not claim the verified raw match")
    require(result["source_commit"] == SOURCE_COMMIT and result["historical_uploader_recipe"] is None,
            "Source/provenance claim changed")
    for key in ("original_program_mounted", "binary_patching", "padding"):
        require(result[key] is False, "Unexpected build method: " + key)
    for key in ("source_unchanged", "exact_requested_placement", "reference_opened"):
        require(result[key] is True, "Missing measured gate: " + key)
    for name in ("baseline-build.log", "ordered-build.log", "ordered-strip.log"):
        require(result[name + "_exit"] == 0, "Saved tool execution failed: " + name)
    require(result["candidate_sha256"] == digest(candidate) == result["reference_sha256"]
            and result["candidate_bytes"] == result["reference_bytes"] == len(candidate)
            and result["differing_shared_positions"] == result["length_difference"] == 0,
            "Recorded equality measurements differ")
    require(result["baseline_sha256"] == digest(baseline)
            and result["baseline_differing_shared_positions"] == 307
            and result["symbol_order_sha256"] == digest(generated_order),
            "Recorded baseline/order measurements differ")
    retained_baseline = read_json(result_dir / "baseline-artifacts.json")
    for name, data in (("baseline.so", baseline), ("baseline.symbols.so", baseline_symbols)):
        measured = {"bytes": len(data), "sha256": digest(data)}
        require(retained_baseline[name] == result["baseline_artifacts"][name] == measured,
                "Baseline artifact receipt differs")

    source_manifest = json.loads(artifact_bytes(result_dir, "source-manifest.json"))
    require(len(source_manifest) == 1229 and source_manifest["Cargo.lock"] ==
            "3c8f402f40488908503e9cc088388c1f95848d79da5141b5cb1a14006d74428b", "Wrong source/lock manifest")
    build_inputs_bytes = (package / "results/build-inputs.json").read_bytes()
    require(digest(build_inputs_bytes) == EXECUTED_INPUTS_SHA256, "Executed-input provenance seal differs")
    build_inputs = json.loads(build_inputs_bytes)
    require(build_inputs["head_sha"] == BUILD_COMMIT, "Wrong executed package commit")
    for name, expected in build_inputs["files"].items():
        data = (package / name).read_bytes()
        require(digest(data) == expected["sha256"] and len(data) == expected["bytes"],
                "Current build input differs from executed revision: " + name)
    hosted = read_json(package / "results/hosted-runs.json")
    require(hosted["successful"]["head_sha"] == BUILD_COMMIT and
            hosted["successful"]["conclusion"] == "success"
            and hosted["successful"]["run_id"] == 40287588927
            and hosted["successful"]["run_attempt"] == 1
            and hosted["successful"]["artifact_id"] == 12634348508
            and hosted["successful"]["artifact_name"] == "ata-source-order-40287588927-1"
            and hosted["successful"]["artifact_digest"] == "sha256:" + ACTUAL_ARTIFACT_ZIP_SHA256,
            "Wrong hosted build receipt")
    require("--symbol-ordering-file" in (result_dir / "linker-help.txt").read_text(), "Missing actual linker support")
    tools = read_json(result_dir / "toolchain.json")
    require("9509bb55a565c64e45ea0b20dfba7fe16fc01fc1" in tools["linker_version"], "Wrong measured linker revision")
    failure = read_json(package / "results/run-40286252822/result.json")
    require(failure["status"] == "FAILED" and failure["reference_opened"] is False
            and "symlink, submodule or unresolved" in failure["error"], "Initial failure receipt changed")
    require(all(command[0] == "git" for command in
                read_json(package / "results/run-40286252822/commands.json")), "Initial attempt unexpectedly built")
    require({path.name for path in result_dir.iterdir()} ==
            {COMPRESSED_ARTIFACT_FILES.get(name, name) for name in ACTUAL_ARTIFACT_FILES},
            "Actual hosted artifact member inventory changed")
    members = []
    for name in ACTUAL_ARTIFACT_FILES:
        data = artifact_bytes(result_dir, name)
        members.append({"name": name, "bytes": len(data), "sha256": digest(data)})
    encoded = json.dumps(members, sort_keys=True, separators=(",", ":")).encode("ascii")
    require(digest(encoded) == ACTUAL_ARTIFACT_MEMBERS_SHA256,
            "Actual hosted artifact provenance seal differs")
    return {"scope": "Saved artifact verification only; no new build or runtime replay",
            "raw_byte_equality": True, "bytes": len(candidate), "sha256": digest(candidate),
            "baseline_differing_positions": 307, "ordered_differing_positions": 0,
            "function_symbols_checked": 177, "historical_uploader_recipe": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path,
                        default=P.parents[2] / "evidence/dependencies/associated_token/deployed.so")
    args = parser.parse_args()
    print(json.dumps(verify(P, args.reference), indent=2))


if __name__ == "__main__":
    main()
