"""Replay the two authenticated existing Pump outputs; never invoke a compiler."""
import argparse
import base64
import io
import json
import os
import platform
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import traceback
import zipfile
from solders.transaction import Transaction
from recovery import (ROOT, PACKAGE, ORIGINAL_SHA, SOURCE, CORRECTED_SHA, digest, require,
                      load_json, pinned_source)
from verify_runtime import validate

sys.path.insert(0, str(ROOT / "scripts"))
import core_linux_v144_build as pipeline
from compare import compare

BUILD_RUN = 40301208015
BUILD_HEAD = "0710a4c9fe8d7285a6afdc30edbc2fca4c1ee5b5"
ARTIFACT_ID = 12640124116
ARCHIVE_SHA = "fc0125c3c9752ab22b894a9569c92bbe30d12d9a0c90f79d7185d69fedad99cd"
MEMBERS_SHA = "a7f563aa9fb0de347371a2f16a157be18ce3c26ca9f137150ae88c952e05faed"
OUTPUTS = {
    "baseline": {"candidate.so": (1583992, "168eea079c77503ac0a17b4908f1181339c9547b64b4697d7b330db0680ab124"),
                 "unstripped.so": (2165256, "2c707df554965eb0fc58b6eb3620ccfcab90f2c32b429cd1da77426a618a5a95")},
    "corrected": {"candidate.so": (1584520, "1d328c9a78ade28355516f9263ffde5582af8454f201bbe80e4c2699ed9c13f6"),
                  "unstripped.so": (2166112, "f2896e2916a0b9b200a7da1320b069c6b39de7fe8619ab29c88feb6c313f8031")},
}


def authenticated_members(archive, metadata):
    require(len(archive) == 3272692 and digest(archive) == ARCHIVE_SHA, "wrong original artifact ZIP")
    require(metadata["id"] == ARTIFACT_ID and metadata["name"] == "pump-extend-diagnostics-40301208015-1" and
            metadata["size_in_bytes"] == len(archive) and metadata["digest"] == "sha256:" + ARCHIVE_SHA and
            metadata["workflow_run"]["id"] == BUILD_RUN and metadata["workflow_run"]["head_sha"] == BUILD_HEAD,
            "wrong original hosted artifact identity")
    contents = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        for member in source.infolist():
            name = PurePosixPath(member.filename)
            require(not name.is_absolute() and ".." not in name.parts and "\\" not in member.filename and
                    not stat.S_ISLNK(member.external_attr >> 16), "unsafe archive entry")
            if member.is_dir():
                continue
            require(member.filename not in contents, "duplicate archive member")
            contents[member.filename] = source.read(member)
    rows = [{"name": name, "bytes": len(raw), "sha256": digest(raw)} for name, raw in sorted(contents.items())]
    require(len(rows) == 131 and digest(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()) == MEMBERS_SHA,
            "wrong immutable raw artifact member set")
    return contents


def verify_build(contents, repo):
    get = lambda name: json.loads(contents[name])
    state = get("attempt.json")
    require(state["status"] == "failed" and state["build_attempts"] == 2 and state["source_revision"] == BUILD_HEAD,
            "historical failed attempt was relabelled")
    commands = {row["name"]: row for row in state["commands"]}
    require(commands["baseline-build"]["returncode"] == commands["corrected-build"]["returncode"] == 0 and
            commands["baseline-runtime"]["returncode"] == 1, "historical command outcomes changed")
    failed = get("baseline/runtime.json")
    require(failed["status"] == "failed" and failed["problems"] == ["no-growth path changed effects"] and
            len(failed["cases"]) == 12 and len(failed["pre_send_transactions"]) == 24, "historical probe failure changed")
    require("corrected/runtime.json" not in contents and "pair-summary.json" not in contents,
            "invented previously unexecuted acceptance")
    for name, sha in get("tooling-inputs.json").items():
        require(digest(contents["executed-inputs/" + name]) == sha, "executed build helper copy differs")
    recorded = pinned_source(repo)
    builds = {}
    for kind in ("baseline", "corrected"):
        expected = recorded.copy()
        if kind == "corrected":
            expected[SOURCE] = CORRECTED_SHA
        record = get(kind + "/build-record.json")
        require(record["kind"] == kind and record["returncode"] == 0 and record["accepted_build"] is True and
                record["source_unchanged"] is True and record["source_sha256"] == record["source_after_sha256"] == expected,
                "historical source build mismatch")
        prefix = "source/" + kind + "/"
        actual = {name[len(prefix):]: digest(raw) for name, raw in contents.items() if name.startswith(prefix)}
        require(actual == expected, "historical source snapshot mismatch")
        for name, (size, sha) in OUTPUTS[kind].items():
            raw = contents[kind + "/" + name]
            require(len(raw) == size and digest(raw) == sha and record["produced_outputs"][name] == {"bytes": size, "sha256": sha},
                    "historical compiler output changed")
        builds[kind] = record
    return builds


def inherited_acceptance(report, corrected_sha):
    require(report["original_sha256"] == ORIGINAL_SHA and report["candidate_sha256"] == corrected_sha and
            report["mismatches"] == [] and len(report["cases"]) == 308, "inherited extension suite failed")
    prior = load_json(PACKAGE / "inputs/selected-extension.json.gz")
    expected_script = load_json(PACKAGE / "pins.json")["runtime_inputs"]["scripts/pump_extend_differential.py"]
    require(report["script_sha256"] == expected_script == digest((ROOT / "scripts/pump_extend_differential.py").read_bytes()),
            "inherited report uses a different harness")
    require([r["case"] for r in report["cases"]] == [r["case"] for r in prior["cases"]], "inherited cases changed")
    checks = 0
    unique = set()
    for row in report["cases"]:
        require(row["diff"] == [] and all(row["original"][key] == row["candidate"][key] for key in
                ("before", "after", "error", "events", "inner", "return")), "inherited committed effects differ")
        require(row["original"]["transaction_base64"] == row["candidate"]["transaction_base64"], "inherited signed pair differs")
        for side in ("original", "candidate"):
            raw = base64.b64decode(row[side]["transaction_base64"], validate=True)
            tx = Transaction.from_bytes(raw)
            require(bytes(tx) == raw and all(tx.verify_with_results()), "invalid inherited raw signature")
            checks += len(tx.signatures)
            unique.add(raw)
    require(checks == 1208, "inherited signature count differs from unchanged roster")
    return {"cases": 308, "raw_signature_checks": checks, "unique_raw_transactions": len(unique),
            "qualification": "Inherited effect comparison excludes full diagnostic logs; focused receipts check those separately."}


def run(args, attempt):
    evidence = attempt.evidence
    archive = args.archive.read_bytes()
    meta_raw = args.metadata.read_bytes()
    original_dir = evidence / "original-build"
    original_dir.mkdir()
    (original_dir / "artifact.zip").write_bytes(archive)
    (original_dir / "artifact.json").write_bytes(meta_raw)
    require(sys.platform == "linux" and platform.machine() == "x86_64", "Linux x86_64 replay required")
    contents = authenticated_members(archive, json.loads(meta_raw))
    records = verify_build(contents, args.repo)
    pipeline.write_json(evidence / "build-input-provenance.json", {
        "run_id": BUILD_RUN, "head_sha": BUILD_HEAD, "artifact_id": ARTIFACT_ID, "archive_sha256": ARCHIVE_SHA,
        "raw_member_seal": MEMBERS_SHA, "member_count": 131, "historical_conclusion": "failure",
        "historical_builds_succeeded": True, "replay_build_attempts": 0,
        "historical_failure": "baseline-runtime schema expected [] but actual one-instruction CPI groups are [[]]",
        "historical_files_rewritten": False})
    env = {key: os.environ[key] for key in ("HOME", "PATH", "LANG", "LC_ALL") if key in os.environ}
    original = (args.repo / "evidence/original/pump/deployed.so").read_bytes()
    require(digest(original) == ORIGINAL_SHA, "original comparison input changed")
    outputs = {}
    for kind in ("baseline", "corrected"):
        folder = evidence / kind
        folder.mkdir()
        for name in ("candidate.so", "unstripped.so", "build-record.json"):
            (folder / name).write_bytes(contents[kind + "/" + name])
        # New comparison is separate; the historical record remains exact,
        # including corrected's not-yet-measured whole_original_identity field.
        pipeline.write_json(folder / "replay-whole-original-comparison.json", compare(original, contents[kind + "/candidate.so"]))
        attempt.run(kind + "-focused-replay", [sys.executable, "-B", str(PACKAGE / "runtime_probe.py"), "--repo", str(args.repo),
            "--candidate", str(folder / "candidate.so"), "--candidate-sha256", records[kind]["candidate_sha256"],
            "--expect", "rebuilt-baseline" if kind == "baseline" else "corrected", "--build-record", str(folder / "build-record.json"),
            "--output", str(folder / "runtime.json")], args.repo, env)
        outputs[kind] = validate(load_json(folder / "runtime.json"), args.repo, folder / "candidate.so", (folder / "build-record.json").read_bytes())
    inherited = evidence / "corrected/extension.json.gz"
    attempt.run("corrected-inherited-extension", [sys.executable, "-B", str(args.repo / "scripts/pump_extend_differential.py"),
        "--candidate", str(evidence / "corrected/candidate.so"), "--output", str(inherited)], args.repo, env)
    checked = inherited_acceptance(load_json(inherited), records["corrected"]["candidate_sha256"])
    attempt.run("actual-receipt-mutations", [sys.executable, "-B", str(PACKAGE / "test_runtime.py"), "--built", str(evidence)], args.repo, env)
    pipeline.write_json(evidence / "replay-summary.json", {"passed": True, "new_builds": 0, "focused": outputs,
        "inherited": checked, "corrected_vs_baseline": compare(contents["baseline/candidate.so"], contents["corrected/candidate.so"]),
        "scope": "Exact retained source-built files replayed; initial failed raw receipt preserved, no selection or whole-identity promotion."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.repo, args.output = args.repo.resolve(), args.output.resolve()
    require(not args.output.exists(), "output already exists; preserve previous attempt")
    attempt = pipeline.Attempt(args.output)
    attempt.state.update(scope=__doc__, status="preparing", build_attempts=0)
    names = ["replay.py", "runtime_probe.py", "verify_runtime.py", "recovery.py", "verify_evidence.py", "test_runtime.py", "pins.json", "source.patch"]
    paths = [PACKAGE / name for name in names] + list((PACKAGE / "inputs").iterdir())
    paths += [args.repo / name for name in ("scripts/core_linux_v144_build.py", "scripts/core_linux_v144_inputs.json", "scripts/compare.py",
              "scripts/analyze.py", "scripts/pump_extend_differential.py", "evidence/upstream/pump.json")]
    before = {path.relative_to(args.repo).as_posix(): pipeline.digest(path) for path in paths}
    pipeline.write_json(attempt.evidence / "tooling-inputs.json", before)
    for path in paths:
        target = attempt.evidence / "executed-inputs" / path.relative_to(args.repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    try:
        run(args, attempt)
        after = {path.relative_to(args.repo).as_posix(): pipeline.digest(path) for path in paths}
        pipeline.write_json(attempt.evidence / "tooling-inputs-after.json", after)
        require(before == after, "replay tooling changed during execution")
        attempt.state["status"] = "passed"
    except Exception as error:
        attempt.state.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        attempt.save()


if __name__ == "__main__":
    main()
