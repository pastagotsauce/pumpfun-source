#!/usr/bin/env python3
"""Independently accept permanently retained combined-build artifacts and receipts."""
import json
import sys

from recovery import (PACKAGE, ROOT, PRIOR, ORIGINAL_SHA, PRIOR_SHA, SWEEP, OMITTED,
                      digest, require, read_report, check_build, expected_source)
import verify_sweep
import verify_liquidity

sys.path.insert(0, str(ROOT / "scripts"))
from compare import compare

RESULTS = PACKAGE / "results"
MANIFEST_SHA = "0ba49bbebbe894e3a0792234c4653d20ee8230f17f836d16e39f11b8095a0b8e"


def inherited(report, suite, candidate_sha):
    count = 254 if suite == "sweep" else 680
    require(report["case_count"] == len(report["cases"]) == count and report["mismatches"] == [], "incomplete/failed inherited suite")
    require(report["candidate_sha256"] == candidate_sha and report["original_sha256"] == ORIGINAL_SHA, "wrong inherited binary binding")
    require(report["script_sha256"] == digest((ROOT / f"scripts/pump_amm_{suite}_differential.py").read_bytes()), "different inherited harness")
    for row in report["cases"]:
        if suite == "sweep":
            require(row["diff"] == [] and row["original"] == row["candidate"], "sweep effects differ")
        else:
            require(row["match"] is True and row["mismatched_fields"] == [], "liquidity case failed")
            effects = lambda side: {key: value for key, value in side.items() if key != "logs"}
            require(effects(row["original"]) == effects(row["candidate"]), "liquidity effects differ")
            for side in (row["original"], row["candidate"]):
                require(side["events"] == [line for line in side["logs"] if line.startswith("Program data: ")], "liquidity event extraction changed")
    return {"cases": count, "mismatches": 0, "scope": "All retained account/error/CPI/event effects; full logs are excluded by the inherited suites."}


def main():
    raw = (RESULTS / "manifest.json").read_bytes()
    require(digest(raw) == MANIFEST_SHA, "publication manifest changed")
    manifest = json.loads(raw)
    files = {path.relative_to(RESULTS).as_posix() for path in RESULTS.rglob("*") if path.is_file()}
    require(files == set(manifest["files"]) | {"manifest.json"}, "publication file set changed")
    members = {}
    for name, entry in manifest["files"].items():
        path = RESULTS / name
        require(not path.is_symlink(), "linked publication member")
        stored = path.read_bytes()
        require(digest(stored) == entry["sha256"] and len(stored) == entry["bytes"], "stored artifact changed: " + name)
        raw = read_report(path)
        if entry.get("compression"):
            require(digest(raw) == entry["raw_sha256"] and len(raw) == entry["raw_bytes"], "gzip payload changed: " + name)
        if "artifact_id" in entry["origin"]:
            origin = entry["origin"]
            require(origin["artifact_id"] == manifest["archive"]["artifact_id"] and origin["member"] not in members, "unknown/duplicated origin")
            members[origin["member"]] = {"bytes": len(raw), "sha256": digest(raw)}
    archive = manifest["archive"]
    require(members == archive["members"], "retained member set changed")
    run = json.loads((RESULTS / "provenance/run.json").read_bytes())
    artifact = json.loads((RESULTS / "provenance/artifact.json").read_bytes())
    require(run["id"] == archive["run_id"] == 40294311933 and run["head_sha"] == archive["head_sha"] and
            run["conclusion"] == archive["conclusion"] == "success", "successful run binding changed")
    require(artifact["id"] == archive["artifact_id"] and artifact["digest"] == "sha256:" + archive["sha256"] and
            artifact["size_in_bytes"] == archive["bytes"] and artifact["workflow_run"]["id"] == run["id"], "artifact provider binding changed")
    build = RESULTS / "build"
    attempt = json.loads((build / "attempt.json").read_bytes())
    require(attempt["status"] == "passed" and attempt["build_attempts"] == 1 and attempt["source_revision"] == run["head_sha"],
            "actual attempt failed or different source/run")
    commands = {row["name"]: row for row in attempt["commands"]}
    required = {"combined-build", "focused-sweep", "focused-liquidity", "verify-focused-liquidity", "test-actual-focused-receipts",
                "inherited-sweep", "inherited-liquidity"}
    require(required <= set(commands) and all(row["returncode"] == 0 for row in commands.values()), "required commands did not pass")
    for row in commands.values():
        require(digest((build / row["log"]).read_bytes()) == row["log_sha256"], "command log hash changed")
    tooling = json.loads((build / "tooling-inputs.json").read_bytes())
    require(all(digest((ROOT / name).read_bytes()) == sha for name, sha in tooling.items()), "executed tool source changed")
    prior_tools = json.loads((PRIOR / "results/build/tool-bindings.json").read_bytes())
    tools = json.loads((build / "tool-bindings.json").read_bytes())
    require(all(prior_tools[name] == sha for name, sha in tools.items()), "prior toolchain input changed")
    folder = build / "combined"
    candidate, record_raw = (folder / "candidate.so").read_bytes(), (folder / "build-record.json").read_bytes()
    record = check_build(ROOT, candidate, record_raw)
    require(len(candidate) == record["candidate_bytes"] and digest((folder / "unstripped.so").read_bytes()) == record["unstripped_sha256"],
            "compiler output changed")
    source = build / "source"
    actual_source = {path.relative_to(source).as_posix(): digest(path.read_bytes()) for path in source.rglob("*") if path.is_file()}
    require(actual_source == expected_source(ROOT) and len(actual_source) == 30, "new source snapshot incomplete or changed")
    inputs = json.loads((build / "source-inputs.json").read_bytes())
    require(inputs["prior_artifact_omitted"] == [OMITTED] and inputs["new_authenticated_repository_input"] == {OMITTED: actual_source[OMITTED]},
            "omitted prior metadata qualification changed")
    require([name for name in actual_source if actual_source[name] != inputs["input_sha256"][name]] == [SWEEP], "unrelated source change")
    focused = {
        "sweep": verify_sweep.validate(json.loads(read_report(folder / "sweep-runtime.json.gz")), ROOT, candidate, record_raw),
        "liquidity": verify_liquidity.validate(json.loads(read_report(folder / "liquidity-runtime.json.gz")), ROOT, candidate, record_raw)}
    regressions = {suite: inherited(json.loads(read_report(folder / (suite + ".json.gz"))), suite, digest(candidate)) for suite in ("sweep", "liquidity")}
    original = (ROOT / "evidence/original/pump_amm/deployed.so").read_bytes()
    require(digest(original) == ORIGINAL_SHA, "original changed")
    prior = (PRIOR / "results/build/corrected/candidate.so").read_bytes()
    require(digest(prior) == PRIOR_SHA, "prior compiler output changed")
    comparison = compare(original, candidate)
    require(comparison == json.loads((folder / "whole-original-comparison.json").read_bytes()), "original byte comparison changed")
    require(compare(prior, candidate) == json.loads((folder / "prior-liquidity-comparison.json").read_bytes()), "prior byte comparison changed")
    print(json.dumps({"retained_files": len(manifest["files"]), "hosted_members": len(members), "run_id": run["id"],
                      "candidate_sha256": digest(candidate), "candidate_bytes": len(candidate), "full_original_identity": comparison["full_byte_equality"],
                      "retained_source_files": len(actual_source), "focused": focused, "inherited": regressions}, indent=2))


if __name__ == "__main__":
    main()
