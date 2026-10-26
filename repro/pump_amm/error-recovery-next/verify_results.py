#!/usr/bin/env python3
"""Verify the permanent build/replay publication without compiling or running SBF."""
import json
from pathlib import Path
import sys

from verify import PACKAGE, ROOT, BASELINE_SHA, ORIGINAL_SHA, digest, require
from verify_runtime import read_report, validate

sys.path.insert(0, str(ROOT / "scripts"))
from compare import compare

RESULTS = PACKAGE / "results"
MANIFEST_SHA = "0cc88a4146cddec8b57309c5b99ad8b840925a155c765faed30fdeb9bd7a4b34"
MISSING_SOURCE = "programs/pump-amm/vendor/solana-pubkey/.cargo_vcs_info.json"


def main():
    manifest_raw = (RESULTS / "manifest.json").read_bytes()
    require(digest(manifest_raw) == MANIFEST_SHA, "publication manifest changed")
    manifest = json.loads(manifest_raw)
    actual = {path.relative_to(RESULTS).as_posix() for path in RESULTS.rglob("*") if path.is_file()}
    require(actual == set(manifest["files"]) | {"manifest.json"}, "publication file set changed")
    members = {"build": {}, "replay": {}}
    for name, expected in manifest["files"].items():
        path = RESULTS / name
        require(not path.is_symlink(), "publication file is a link")
        raw = path.read_bytes()
        require(len(raw) == expected["bytes"] and digest(raw) == expected["sha256"], "publication bytes changed: " + name)
        if expected.get("compression"):
            raw = read_report(path)
            require(len(raw) == expected["raw_bytes"] and digest(raw) == expected["raw_sha256"], "gzip payload changed: " + name)
        origin = expected.get("origin", {})
        if "artifact_id" in origin:
            kind = "build" if origin["artifact_id"] == 12634605630 else "replay"
            require(origin["artifact_id"] == manifest["archives"][kind]["artifact_id"], "unknown artifact origin")
            require(origin["member"] not in members[kind], "duplicate artifact member")
            members[kind][origin["member"]] = {"bytes": len(raw), "sha256": digest(raw)}
    for kind, expected_conclusion in (("build", "failure"), ("replay", "success")):
        archive = manifest["archives"][kind]
        require(members[kind] == archive["members"], "retained artifact member set changed")
        metadata = json.loads((RESULTS / f"provenance/{kind}-artifact.json").read_text())
        run = json.loads((RESULTS / f"provenance/{kind}-run.json").read_text())
        require(metadata["id"] == archive["artifact_id"] and metadata["digest"] == "sha256:" + archive["sha256"]
                and metadata["size_in_bytes"] == archive["bytes"], "artifact provenance changed")
        require(run["id"] == archive["run_id"] and run["head_sha"] == archive["head_sha"]
                and run["conclusion"] == archive["conclusion"] == expected_conclusion, "run provenance changed")

    attempt = json.loads((RESULTS / "build/attempt.json").read_text())
    require(attempt["status"] == "failed" and attempt["build_attempts"] == 2, "initial failure was relabelled")
    commands = {row["name"]: row for row in attempt["commands"]}
    require(commands["baseline-build"]["returncode"] == commands["corrected-build"]["returncode"] == 0,
            "source builds did not succeed")
    require(commands["baseline-runtime"]["returncode"] == 1, "initial probe failure not retained")
    failed = json.loads(read_report(RESULTS / "failed/initial-baseline-runtime.json.gz"))
    require(failed["problems"] == ["case 16: unexpected original error", "case 16: unexpected candidate error",
                                    "case 16: baseline mismatch absent or changed"], "initial diagnostic changed")

    omissions = json.loads((RESULTS / "source-omissions.json").read_text())
    require(len(omissions) == 2, "missing source omission qualification")
    original = (ROOT / "evidence/original/pump_amm/deployed.so").read_bytes()
    require(digest(original) == ORIGINAL_SHA, "original bytes changed")
    results = {}
    for kind in ("baseline", "corrected"):
        folder = RESULTS / "build" / kind
        record_bytes = (folder / "build-record.json").read_bytes()
        record = json.loads(record_bytes)
        candidate = (folder / "candidate.so").read_bytes()
        require(digest(candidate) == record["candidate_sha256"] and len(candidate) == record["candidate_bytes"], "compiler output changed")
        require(digest((folder / "unstripped.so").read_bytes()) == record["unstripped_sha256"], "unstripped output changed")
        source = RESULTS / "build/source" / kind
        paths = {path.relative_to(source).as_posix(): path for path in source.rglob("*") if path.is_file()}
        require(set(record["source_sha256"]) - set(paths) == {MISSING_SOURCE} and len(paths) == 29,
                "source subset differs from the observed hidden-file omission")
        require(all(digest(path.read_bytes()) == record["source_sha256"][name] for name, path in paths.items()), "retained source changed")
        require(digest((ROOT / MISSING_SOURCE).read_bytes()) == record["source_sha256"][MISSING_SOURCE],
                "existing repository metadata differs from recorded thirtieth input")
        require(any(row["build"] == kind and row["missing_path"] == MISSING_SOURCE and
                    row["retained_source_files"] == 29 and row["recorded_source_files"] == 30 for row in omissions),
                "omitted source was not disclosed")
        report = json.loads(read_report(RESULTS / f"replay/{kind}-runtime.json.gz"))
        focused = validate(report, ROOT, candidate, record_bytes)
        comparison = compare(original, candidate)
        results[kind] = {"candidate_sha256": digest(candidate), "candidate_bytes": len(candidate),
                         "equals_selected_darwin": digest(candidate) == BASELINE_SHA,
                         "whole_original_equality": comparison["full_byte_equality"],
                         "different_shared_positions": comparison["different_positions_in_shared_length"],
                         "missing_allocation_bytes": max(0, -comparison["length_difference"]), "focused": focused}
    inherited = json.loads(read_report(RESULTS / "replay/corrected-liquidity.json.gz"))
    require(inherited["case_count"] == len(inherited["cases"]) == 680 and inherited["mismatches"] == [], "inherited regression failed")
    require(inherited["candidate_sha256"] == results["corrected"]["candidate_sha256"]
            and inherited["original_sha256"] == ORIGINAL_SHA, "inherited binary binding changed")
    for row in inherited["cases"]:
        require(row["match"] and row["mismatched_fields"] == [], "inherited case failed")
        effects = lambda side: {key: value for key, value in side.items() if key != "logs"}
        require(effects(row["original"]) == effects(row["candidate"]), "inherited non-log effects differ")
        for side in (row["original"], row["candidate"]):
            require(side["events"] == [line for line in side["logs"] if line.startswith("Program data: ")], "inherited event observation changed")
    print(json.dumps({"retained_files": len(manifest["files"]), "source_retention": "29/30 files per build; one public hidden metadata input explicitly absent",
                      "initial_run": "failed after both successful builds", "replay_run": "success",
                      "builds": results, "inherited_liquidity_cases": 680,
                      "inherited_scope": "non-log effects; focused receipts separately gate recovered diagnostics"}, indent=2))


if __name__ == "__main__":
    main()
