#!/usr/bin/env python3
"""Accept the exact published creator-fee build, source and actual signed receipts."""
import json
import sys

from migration import (PACKAGE, ROOT, PRIOR, PRIOR_SHA, PRIOR_RECORD_SHA, SOURCE,
                       ORIGINAL_SHA, digest, require, read_report, check_build,
                       expected_source, prior_source)
from verify_creator import validate

sys.path.insert(0, str(ROOT / "scripts"))
from compare import compare

RESULTS = PACKAGE / "results"
MANIFEST_SHA = "e10f8d972502535406be4f9a1b1137b98f5ea4d699fc71cc33848c6d5b96422e"


def main():
    raw_manifest = (RESULTS / "manifest.json").read_bytes()
    require(digest(raw_manifest) == MANIFEST_SHA, "publication manifest changed")
    manifest = json.loads(raw_manifest)
    actual_files = {path.relative_to(RESULTS).as_posix() for path in RESULTS.rglob("*") if path.is_file()}
    require(actual_files == set(manifest["files"]) | {"manifest.json"}, "publication membership changed")
    members = {}
    for name, entry in manifest["files"].items():
        path = RESULTS / name
        require(not path.is_symlink(), "linked artifact member")
        stored = path.read_bytes()
        require(digest(stored) == entry["sha256"] and len(stored) == entry["bytes"], "stored member changed: " + name)
        raw = read_report(path)
        if entry.get("compression"):
            require(digest(raw) == entry["raw_sha256"] and len(raw) == entry["raw_bytes"], "gzip payload changed: " + name)
        if "artifact_id" in entry["origin"]:
            origin = entry["origin"]
            require(origin["artifact_id"] == manifest["archive"]["artifact_id"] and origin["member"] not in members, "unknown/duplicate member origin")
            members[origin["member"]] = {"bytes": len(raw), "sha256": digest(raw)}
    archive = manifest["archive"]
    require(members == archive["members"], "raw member set changed")
    run = json.loads((RESULTS / "provenance/run.json").read_bytes())
    artifact = json.loads((RESULTS / "provenance/artifact.json").read_bytes())
    require(run["id"] == archive["run_id"] == 40297988318 and run["head_sha"] == archive["head_sha"] and
            run["conclusion"] == archive["conclusion"] == "success", "run provenance mismatch")
    require(artifact["id"] == archive["artifact_id"] and artifact["digest"] == "sha256:" + archive["sha256"] and
            artifact["size_in_bytes"] == archive["bytes"] and artifact["workflow_run"]["id"] == run["id"], "provider artifact binding mismatch")
    build = RESULTS / "build"
    attempt = json.loads((build / "attempt.json").read_bytes())
    require(attempt["status"] == "passed" and attempt["build_attempts"] == 1 and attempt["source_revision"] == run["head_sha"], "attempt not accepted")
    commands = {row["name"]: row for row in attempt["commands"]}
    require({"combined-build", "focused-migration-and-regressions", "test-actual-focused-receipts", "inherited-creator-reassignment"} <= set(commands)
            and all(row["returncode"] == 0 for row in commands.values()), "required command did not pass")
    for row in commands.values():
        require(digest((build / row["log"]).read_bytes()) == row["log_sha256"], "command log changed")
    tooling = json.loads((build / "tooling-inputs.json").read_bytes())
    require(all(digest((ROOT / name).read_bytes()) == sha for name, sha in tooling.items()), "executed tool source changed")
    tools = json.loads((build / "tool-bindings.json").read_bytes())
    require(tools == json.loads((PRIOR / "results/build/tool-bindings.json").read_bytes()), "prior toolchain input changed")
    folder = build / "combined"
    candidate, record_raw = (folder / "candidate.so").read_bytes(), (folder / "build-record.json").read_bytes()
    record = check_build(ROOT, candidate, record_raw)
    require(record["candidate_bytes"] == len(candidate) and digest((folder / "unstripped.so").read_bytes()) == record["unstripped_sha256"],
            "compiler output changed")
    source = build / "source"
    source_files = {path.relative_to(source).as_posix(): digest(path.read_bytes()) for path in source.rglob("*") if path.is_file()}
    require(source_files == expected_source(ROOT) and len(source_files) == 30, "source snapshot incomplete/changed")
    before_source, before_paths = prior_source(ROOT)
    require([name for name in source_files if source_files[name] != before_source[name]] == [SOURCE], "source changes exceed migrate file")
    before = before_paths[SOURCE].read_bytes()
    after = (source / SOURCE).read_bytes()
    require(before.split(b"pub fn admin_cto", 1)[1] == after.split(b"pub fn admin_cto", 1)[1], "admin_cto source changed")
    inputs = json.loads((build / "source-inputs.json").read_bytes())
    require(inputs["source_files"] == 30 and inputs["input_sha256"] == before_source and
            inputs["prior_candidate_sha256"] == PRIOR_SHA and inputs["prior_build_record_sha256"] == PRIOR_RECORD_SHA, "prior input manifest changed")
    focused = validate(json.loads(read_report(folder / "runtime.json.gz")), ROOT, candidate, record_raw)
    inherited = json.loads(read_report(folder / "creator-reassignment.json.gz"))
    require(inherited["case_count"] == len(inherited["cases"]) == 327 and inherited["mismatches"] == [] and
            inherited["candidate_sha256"] == digest(candidate) and inherited["original_sha256"] == ORIGINAL_SHA, "inherited creator suite incomplete/failed")
    require(inherited["script_sha256"] == digest((ROOT / "scripts/pump_amm_creator_reassignment_differential.py").read_bytes()), "inherited script changed")
    for row in inherited["cases"]:
        require(row["match"] is True and row["mismatched_fields"] == [] and
                all(row["original"][key] == row["candidate"][key] for key in ("error", "before", "after", "events", "inner", "return")),
                "inherited effects differ")
    original = (ROOT / "evidence/original/pump_amm/deployed.so").read_bytes()
    require(digest(original) == ORIGINAL_SHA, "original changed")
    prior = (PRIOR / "results/build/combined/candidate.so").read_bytes()
    require(digest(prior) == PRIOR_SHA, "prior candidate changed")
    comparison = compare(original, candidate)
    require(comparison == json.loads((folder / "whole-original-comparison.json").read_bytes()), "original byte comparison changed")
    require(compare(prior, candidate) == json.loads((folder / "prior-sweep-comparison.json").read_bytes()), "prior byte comparison changed")
    print(json.dumps({"retained_files": len(manifest["files"]), "hosted_members": len(members), "run_id": run["id"],
        "candidate_sha256": digest(candidate), "candidate_bytes": len(candidate), "whole_original_identity": comparison["full_byte_equality"],
        "source_files": len(source_files), "focused": focused, "inherited_creator_cases": 327,
        "inherited_scope": "Exact errors/account/event/CPI/return effects; inherited suite excludes full logs."}, indent=2))


if __name__ == "__main__":
    main()
