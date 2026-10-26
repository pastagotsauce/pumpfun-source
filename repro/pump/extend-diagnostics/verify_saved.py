"""Verify actual retained build/replay evidence offline; never compile or run a VM."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile
from recovery import ROOT, PACKAGE, ORIGINAL_SHA, digest, require, load_json
from replay import (authenticated_members, verify_build, inherited_acceptance,
                    ARTIFACT_ID, BUILD_RUN, BUILD_HEAD, ARCHIVE_SHA, OUTPUTS)
from verify_runtime import validate
from compare import compare

REPLAY_RUN = 40304336017
REPLAY_HEAD = "4678ffb0fe56c63d46d1851e6fc648fc77695b30"
REPLAY_ARTIFACT = 12641518219
REPLAY_ZIP_SHA = "2733df482c1a02243e8fb65854b29b56041bb21bca8adf0f2fca0bb62f82c511"
REPLAY_MEMBERS_SHA = "fb1b6923199f1f1805c435bcc8e4ae788d6ca83428a706fc274237aa2020aadb"
RESULTS_SHA = "b3d2beed1a7305eca446df56397dfbbd2dd943f5f9bee67de1de1397564e0b8c"
# The raw replay receipt inherited this constant from the shared Attempt helper.
# It is preserved as observed, never interpreted as the replay checkout revision.
SHARED_HELPER_DEFAULT_REVISION = "4ffe8bd88761059693e481ae972443c10204f7af"


def rows_for_files(folder, exclude_manifest=False):
    rows = []
    for path in sorted(folder.rglob("*")):
        require(not path.is_symlink(), "symlinked retained file")
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        name = path.relative_to(folder).as_posix()
        if exclude_manifest and name == "manifest.json":
            continue
        raw = path.read_bytes()
        rows.append({"name": name, "bytes": len(raw), "sha256": digest(raw)})
    return sorted(rows, key=lambda row: row["name"])


def member_rows(contents):
    return [{"name": name, "bytes": len(raw), "sha256": digest(raw)}
            for name, raw in sorted(contents.items())]


def seal(rows):
    return digest(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode())


def replay_contents(raw):
    require(len(raw) == 5277360 and digest(raw) == REPLAY_ZIP_SHA, "actual replay ZIP differs")
    contents = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            require(not path.is_absolute() and ".." not in path.parts and "\\" not in entry.filename
                    and not stat.S_ISLNK(entry.external_attr >> 16), "unsafe retained ZIP entry")
            if entry.is_dir():
                continue
            require(entry.filename not in contents, "duplicate retained ZIP entry")
            contents[entry.filename] = archive.read(entry)
    rows = member_rows(contents)
    require(len(rows) == 45 and seal(rows) == REPLAY_MEMBERS_SHA, "actual replay member seal differs")
    return contents


def provider_identity(folder, run_id, head, artifact_id, archive_sha, archive_bytes, job_id, job_name, conclusion):
    run = load_json(folder / "run.json")
    artifact = load_json(folder / "artifact.json")
    jobs = load_json(folder / "jobs.json")["jobs"]
    matching = [job for job in jobs if job["id"] == job_id]
    require(run["id"] == run_id and run["head_sha"] == head and run["status"] == "completed"
            and run["conclusion"] == conclusion and run["run_attempt"] == 1
            and run["event"] == "workflow_dispatch"
            and run["repository"]["full_name"] == "pastagotsauce/pumpfun-source", "hosted run identity differs")
    require(len(matching) == 1 and matching[0]["name"] == job_name and matching[0]["run_id"] == run_id
            and matching[0]["conclusion"] == conclusion and matching[0]["head_sha"] == head,
            "hosted job identity differs")
    require(artifact["id"] == artifact_id and artifact["digest"] == "sha256:" + archive_sha
            and artifact["size_in_bytes"] == archive_bytes and artifact["workflow_run"]["id"] == run_id
            and artifact["workflow_run"]["head_sha"] == head, "hosted artifact identity differs")


def extract_for_checks(contents, destination):
    """Write already sealed public members only to a caller-owned fresh directory."""
    require(not destination.exists(), "verification extraction destination already exists")
    destination.mkdir(parents=True)
    for name, raw in contents.items():
        target = destination / Path(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)


def verify(package=PACKAGE, repo=ROOT):
    require(rows_for_files(package, exclude_manifest=True) == load_json(package / "manifest.json")["files"],
            "package manifest differs")
    require(seal(rows_for_files(package / "results")) == RESULTS_SHA, "immutable provider/raw evidence seal differs")
    failed = package / "results/attempt-1"
    replay = package / "results/replay-2"
    provider_identity(failed, BUILD_RUN, BUILD_HEAD, ARTIFACT_ID, ARCHIVE_SHA, 3272692,
                      121499267080, "pump-extend-diagnostics", "failure")
    provider_identity(replay, REPLAY_RUN, REPLAY_HEAD, REPLAY_ARTIFACT, REPLAY_ZIP_SHA, 5277360,
                      121509612462, "pump-extend-replay", "success")
    original_build = authenticated_members((failed / "artifact.zip").read_bytes(), load_json(failed / "artifact.json"))
    verify_build(original_build, repo)
    contents = replay_contents((replay / "artifact.zip").read_bytes())
    require(member_rows(original_build) == load_json(failed / "artifact-members.json")
            and member_rows(contents) == load_json(replay / "artifact-members.json"), "member receipt differs")
    require(contents["original-build/artifact.zip"] == (failed / "artifact.zip").read_bytes()
            and contents["original-build/artifact.json"] == (failed / "artifact.json").read_bytes(),
            "replay changed historical failed artifact")
    get = lambda name: json.loads(contents[name])
    before, after = get("tooling-inputs.json"), get("tooling-inputs-after.json")
    require(before == after, "replay inputs changed during execution")
    git_bindings = load_json(package / "results/executed-git-bindings.json")
    require(git_bindings["head_sha"] == REPLAY_HEAD and git_bindings["repository"] == "pastagotsauce/pumpfun-source"
            and set(git_bindings["files"]) == set(before), "actual checkout binding differs")
    require(set(name[len("executed-inputs/"):] for name in contents if name.startswith("executed-inputs/")) == set(before),
            "executed helper copy set differs")
    for name, expected in before.items():
        raw = contents["executed-inputs/" + name]
        require(digest(raw) == expected == digest((repo / name).read_bytes()),
                "actual executed helper/input differs: " + name)
        require(git_bindings["files"][name] == {"bytes": len(raw), "sha256": digest(raw),
                "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()},
                "executed helper Git blob binding differs")
    state = get("attempt.json")
    require(state["status"] == "passed" and state["build_attempts"] == 0 and state["downloads"] == []
            and state["source_revision"] == SHARED_HELPER_DEFAULT_REVISION, "recorded replay outcome/default field differs")
    commands = state["commands"]
    require([row["name"] for row in commands] == ["baseline-focused-replay", "corrected-focused-replay",
            "corrected-inherited-extension", "actual-receipt-mutations"], "replay command roster differs")
    for row in commands:
        require(row["returncode"] == 0 and digest(contents[row["log"]]) == row["log_sha256"], "replay command failed/log differs")
    require(b"Ran 10 tests" in contents["logs/actual-receipt-mutations.log"]
            and b"\nOK\n" in contents["logs/actual-receipt-mutations.log"], "actual receipt mutation checks did not pass")
    provenance = get("build-input-provenance.json")
    require(provenance["run_id"] == BUILD_RUN and provenance["head_sha"] == BUILD_HEAD
            and provenance["artifact_id"] == ARTIFACT_ID and provenance["archive_sha256"] == ARCHIVE_SHA
            and provenance["historical_conclusion"] == "failure" and provenance["historical_builds_succeeded"] is True
            and provenance["replay_build_attempts"] == 0 and provenance["historical_files_rewritten"] is False,
            "replay build provenance differs")
    original = (repo / "evidence/original/pump/deployed.so").read_bytes()
    require(digest(original) == ORIGINAL_SHA, "captured original differs")
    focused, comparisons = {}, {}
    with tempfile.TemporaryDirectory(prefix="pump-retained-check-") as temporary:
        extracted = Path(temporary) / "evidence"
        extract_for_checks(contents, extracted)
        for kind in ("baseline", "corrected"):
            for name in ("candidate.so", "unstripped.so", "build-record.json"):
                require(contents[kind + "/" + name] == original_build[kind + "/" + name], "retained build output/record rewritten")
            folder = extracted / kind
            focused[kind] = validate(get(kind + "/runtime.json"), repo, folder / "candidate.so", contents[kind + "/build-record.json"])
            comparisons[kind] = compare(original, contents[kind + "/candidate.so"])
            require(comparisons[kind] == get(kind + "/replay-whole-original-comparison.json"), "raw original comparison differs")
    inherited = inherited_acceptance(json.loads(gzip.decompress(contents["corrected/extension.json.gz"])), OUTPUTS["corrected"]["candidate.so"][1])
    summary = get("replay-summary.json")
    require(summary["passed"] is True and summary["new_builds"] == 0 and summary["focused"] == focused
            and summary["inherited"] == inherited and summary["corrected_vs_baseline"] == compare(
                contents["baseline/candidate.so"], contents["corrected/candidate.so"]), "replay summary differs")
    return {"scope": "Saved evidence rechecked only; no new build or VM execution", "replay_head_sha": REPLAY_HEAD,
            "raw_attempt_source_revision_is_shared_helper_default": state["source_revision"],
            "source_builds_in_initial_attempt": 2, "replay_new_builds": 0,
            "focused": focused, "corrected_inherited": inherited, "actual_receipt_mutation_tests": 10,
            "whole_original_comparison": comparisons, "production_or_selection_changed": False,
            "qualification": "Two missing no-growth diagnostics recovered; whole byte identity remains false."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(verify(PACKAGE, args.repo.resolve()), indent=2))
