#!/usr/bin/env python3
"""One isolated Linux baseline/corrected Pump extension build pair and signed local probes."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tomllib
import traceback

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import core_linux_v144_build as pipeline
from compare import compare
from recovery import BASELINE_SHA, ORIGINAL_SHA, SOURCE_SHA, SOURCE, digest, require, pinned_source, patched_source, load_json


def source_hashes(directory, names):
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    require(actual == set(names), "source path set changed")
    require(not any(p.is_symlink() for p in directory.rglob("*")), "source contains symlink")
    return {name: pipeline.digest(directory / name) for name in names}


def registry_views(cargo_home, source, evidence):
    """Authenticate locked public crates, then copy their genuine Cargo views."""
    lock = tomllib.loads((source / "programs/pump/Cargo.lock").read_text())
    locked = [p for p in lock["package"] if p.get("source")]
    require(all(p["source"] == "registry+https://github.com/rust-lang/crates.io-index" for p in locked),
            "unexpected non-registry dependency")
    fetched = pipeline.registry_namespace_sets(cargo_home)
    for namespace in fetched:
        pipeline.inventory_registry_view(cargo_home, locked, namespace)
    origin = sorted(fetched)[0]
    copied = []
    for namespace in pipeline.REGISTRY_NAMESPACES:
        if namespace in fetched:
            continue
        for kind in ("cache", "src", "index"):
            first = cargo_home / "registry" / kind / origin
            second = cargo_home / "registry" / kind / namespace
            before = pipeline.tree_hashes(first)
            require(not any("symlink" in row for row in before.values()), "registry input symlink")
            shutil.copytree(first, second)
            require(pipeline.tree_hashes(first) == pipeline.tree_hashes(second) == before,
                    "registry copy changed bytes")
            copied.append({"kind": kind, "from": origin, "to": namespace,
                           "files": len(before), "tree_sha256": digest(json.dumps(before, sort_keys=True).encode())})
    inventories = {}
    for namespace in pipeline.REGISTRY_NAMESPACES:
        inventories[namespace], metadata = pipeline.inventory_registry_view(cargo_home, locked, namespace)
        pipeline.write_json(evidence / f"cargo-metadata-{namespace}.json", metadata)
    pipeline.write_json(evidence / "registry-preparation.json", {
        "fetched_namespaces": sorted(fetched), "copies": copied,
        "locked_registry_packages": len(locked), "archives_and_source": inventories,
        "metadata_markers_fabricated": False,
        "note": "Authentic Cargo fetch bytes copied into two real namespace directories; no native-extraction claim for copied view."})
    return locked


def run(args, attempt):
    repo, output, evidence = args.repo.resolve(), args.output.resolve(), attempt.evidence
    require(sys.platform == "linux" and platform.machine() == "x86_64", "Linux x86_64 required")
    pins = json.loads((repo / "scripts/core_linux_v144_inputs.json").read_text())
    experiment_pins = load_json(PACKAGE / "pins.json")
    require(all(pipeline.digest(repo / name) == expected for name, expected in experiment_pins["shared_build_inputs"].items()), "shared build helper changed")
    phases = pins["pipeline_tools"]
    selected = repo / "repro/pump_amm/owner6048-v144/main/build-01"
    recorded = pinned_source(repo)
    require(load_json(PACKAGE / "inputs/selected-gate-before.json.gz")["external"]["sdk"] == pins["recorded_sdk_source_sha256"], "Pump selected SDK differs from recorded SDK")
    require(all(pipeline.digest(repo / name) == sha for name, sha in recorded.items()),
            "current source differs from selected baseline")
    sdk_source = selected / "sdk"
    sdk_hashes = pipeline.tree_hashes(sdk_source)
    require(len(sdk_hashes) == 53 and {n: v.get("sha256") for n, v in sdk_hashes.items()} == pins["recorded_sdk_source_sha256"],
            "recorded SDK bytes changed")
    sources = {}
    for kind in ("baseline", "corrected"):
        source = output / "sources" / kind
        for name in recorded:
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / name, destination)
        sources[kind] = source
    minimal_env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL") if k in os.environ}
    isolated_home = output / "home"
    isolated_home.mkdir()
    minimal_env.update(HOME=str(isolated_home), LANG="C.UTF-8", LC_ALL="C.UTF-8")
    for source in sources.values():
        for parent in (source, *source.parents):
            require(not any((parent / ".cargo" / n).exists() for n in ("config", "config.toml")), "ambient Cargo ancestor config")
    patch = PACKAGE / "source.patch"
    attempt.run("check-source-patch", ["git", "apply", "--check", str(patch)], sources["corrected"], minimal_env)
    attempt.run("apply-source-patch", ["git", "apply", str(patch)], sources["corrected"], minimal_env)
    before_source = {kind: source_hashes(path, recorded) for kind, path in sources.items()}
    changed = [name for name in recorded if before_source["baseline"][name] != before_source["corrected"][name]]
    require(changed == [SOURCE], "patch changed unrelated source")
    require((sources["corrected"] / SOURCE).read_bytes() == patched_source((sources["baseline"] / SOURCE).read_bytes()), "patch is not exactly the proved message restoration")
    pipeline.write_json(evidence / "source-before.json", before_source)
    for kind, source in sources.items():
        shutil.copytree(source, evidence / "source" / kind)
    shutil.copy2(patch, evidence / "source.patch")

    # Keep compiler inputs apart from captured binaries; only source/registry/SDK
    # paths are passed to cargo. Original comparison occurs after both builds.
    tools = output / "platform-v144"
    strip = output / "platform-v152"
    cli_root = output / "agave"
    criterion = output / "criterion-v233"
    pipeline.unpack(attempt.download("platform-v144.tar.bz2", pipeline.PLATFORM_URL, pipeline.PLATFORM_SHA, pipeline.PLATFORM_SIZE), tools)
    pipeline.unpack(attempt.download("platform-v152.tar.bz2", phases["strip_url"], phases["strip_sha256"], phases["strip_bytes"]), strip)
    pipeline.unpack(attempt.download("agave-v2.1.21.tar.bz2", pipeline.CLI_URL, pipeline.CLI_SHA, pipeline.CLI_SIZE), cli_root)
    pipeline.unpack_criterion(attempt.download("criterion-v2.3.3.tar.bz2", phases["criterion_url"], phases["criterion_sha256"], phases["criterion_bytes"]), criterion)
    for base, expected in ((tools, pins["platform_selected_sha256"]), (strip, phases["strip_selected_sha256"])):
        require(all(pipeline.digest(base / name) == sha for name, sha in expected.items()), "selected tool member hash mismatch")
    cli_bin = cli_root / "solana-release/bin"
    require((cli_bin / "cargo-build-sbf").is_file(), "CLI layout mismatch")
    caches = {}
    for version, name, target in (("v1.44", "platform-tools", tools), ("v1.52", "platform-tools", strip), ("v2.3.3", "criterion", criterion)):
        cache = isolated_home / ".cache/solana" / version / name
        require(not os.path.lexists(cache), f"owned task cache already exists: {cache}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.symlink_to(target, target_is_directory=True)
        caches[str(cache)] = str(target)
    pipeline.write_json(evidence / "pipeline-caches.json", {"links": caches, "completion_markers_fabricated": False})
    host_rustc = Path(subprocess.check_output(["rustup", "which", "--toolchain", "1.94.0", "rustc"], text=True).strip()).resolve()
    host_toolchain = host_rustc.parents[1]
    cargo_home = output / "cargo-home"
    cargo_home.mkdir()
    base_env = dict(minimal_env, CARGO_HOME=str(cargo_home))
    base_env["PATH"] = str(cli_bin) + ":" + base_env["PATH"]
    envs, sdks = {}, {}
    for kind in sources:
        task = output / kind
        task.mkdir()
        rustup = task / "rustup"
        rustup.mkdir()
        env = dict(base_env, RUSTUP_HOME=str(rustup), CARGO_TARGET_DIR=str(task / "target"))
        attempt.run(kind + "-link-host", ["rustup", "toolchain", "link", "host194", str(host_toolchain)], task, env)
        attempt.run(kind + "-select-host", ["rustup", "default", "host194"], task, env)
        sdk = task / "sdk"
        shutil.copytree(sdk_source, sdk)
        modes = {}
        for name in ("dump", "install", "objcopy", "package", "strip"):
            path = sdk / "scripts" / (name + ".sh")
            modes[name] = {"before": oct(stat.S_IMODE(path.stat().st_mode)), "after": "0o755"}
            path.chmod(0o755)
        require(pipeline.tree_hashes(sdk) == sdk_hashes, "SDK text changed while preparing executable modes")
        pipeline.write_json(evidence / f"sdk-modes-{kind}.json", {"scripts": modes,
            "scope": "Explicit Linux experiment executable-mode preparation; historical Git modes are not claimed."})
        envs[kind], sdks[kind] = env, sdk
    attempt.run("host-rustc-version", [str(host_rustc), "--version", "--verbose"], output, base_env)
    require("rustc 1.94.0 " in (evidence / "logs/host-rustc-version.log").read_text(), "wrong host Rust")
    for name, command in (("cli-version", [str(cli_bin / "cargo-build-sbf"), "--version"]),
                          ("compiler-version", [str(tools / "rust/bin/rustc"), "--version", "--verbose"]),
                          ("strip-version", [str(strip / "llvm/bin/llvm-objcopy"), "--version"])):
        attempt.run(name, command, output, base_env)
    pipeline.write_json(evidence / "tool-bindings.json", {
        "host_rustc_sha256": pipeline.digest(host_rustc), "host_cargo_sha256": pipeline.digest(host_toolchain / "bin/cargo"),
        "compiler_rustc_sha256": pipeline.digest(tools / "rust/bin/rustc"),
        "compiler_cargo_sha256": pipeline.digest(tools / "rust/bin/cargo"),
        "strip_objcopy_sha256": pipeline.digest(strip / "llvm/bin/llvm-objcopy"),
        "cli_sha256": pipeline.digest(cli_bin / "cargo-build-sbf"),
        "recorded_sdk": sdk_hashes, "pipeline": phases})
    fetch_env = dict(envs["baseline"], CARGO_TARGET_DIR=str(output / "fetch-target"))
    attempt.run("locked-public-fetch", ["cargo", "fetch", "--manifest-path", str(sources["baseline"] / "programs/pump/Cargo.toml"), "--locked"], sources["baseline"], fetch_env)
    locked = registry_views(cargo_home, sources["baseline"], evidence)
    require(source_hashes(sources["baseline"], recorded) == before_source["baseline"], "fetch changed source/lock")
    results = {}
    for kind, source in sources.items():
        task = output / kind
        artifact_dir = task / "artifacts"
        command = ["cargo", "build-sbf", "--manifest-path", str(source / "programs/pump/Cargo.toml"),
                   "--tools-version", "v1.44", "--offline", "--sbf-sdk", str(sdks[kind]),
                   "--sbf-out-dir", str(artifact_dir), "--", "--locked", "--offline"]
        attempt.state["build_attempts"] += 1
        result = attempt.run(kind + "-build", command, source, envs[kind], check=False)
        after, source_error = None, None
        try:
            after = source_hashes(source, recorded)
        except Exception as error:
            source_error = str(error)
        record = {"kind": kind, "returncode": result, "source_sha256": before_source[kind],
                  "source_after_sha256": after, "source_unchanged": None if after is None else after == before_source[kind],
                  "source_validation_error": source_error,
                  "pipeline": "Linux v1.44 compilation / recorded SDK / v1.52 strip, prepared executable script modes",
                  "whole_original_identity": None, "accepted_build": False}
        retained = evidence / kind
        retained.mkdir()
        binary = artifact_dir / "pump_recovered.so"
        unstripped = task / "target/sbf-solana-solana/release/pump_recovered.so"
        produced = {}
        for src, dst in ((binary, retained / "candidate.so"), (unstripped, retained / "unstripped.so")):
            if src.is_file():
                shutil.copy2(src, dst)
                produced[dst.name] = {"sha256": pipeline.digest(dst), "bytes": dst.stat().st_size}
        record["produced_outputs"] = produced
        pipeline.write_json(retained / "build-record.json", record)
        # Preserve known partial compiler outputs even when a later frontend or
        # stripping step fails. They are explicitly unaccepted until all gates pass.
        require(result == 0 and record["source_unchanged"], f"{kind} build failed or changed source")
        require(set(produced) == {"candidate.so", "unstripped.so"}, f"{kind} missing compiler outputs")
        record.update(candidate_sha256=pipeline.digest(binary), candidate_bytes=binary.stat().st_size,
                      unstripped_sha256=pipeline.digest(unstripped), selected_darwin_sha256=BASELINE_SHA,
                      equals_selected_darwin_output=pipeline.digest(binary) == BASELINE_SHA)
        pipeline.write_json(retained / "build-record.json", record)
        # No keypair file is opened, hashed or copied into evidence.
        pipeline.write_json(retained / "excluded-keypair-paths.json", pipeline.excluded_keypair_paths(task))
        sdk_after = pipeline.tree_hashes(sdks[kind], exclude=lambda p: "dependencies" in p.parts)
        require(sdk_after == sdk_hashes, "SDK source bytes changed during build")
        for namespace in pipeline.REGISTRY_NAMESPACES:
            pipeline.inventory_registry_view(cargo_home, locked, namespace)
        record["accepted_build"] = True
        pipeline.write_json(retained / "build-record.json", record)
        results[kind] = record
    original = (repo / "evidence/original/pump/deployed.so").read_bytes()
    require(digest(original) == ORIGINAL_SHA, "original comparison input changed")
    for kind, record in results.items():
        retained = evidence / kind
        comparison = compare(original, (retained / "candidate.so").read_bytes())
        pipeline.write_json(retained / "whole-original-comparison.json", comparison)
        record["whole_original_identity"] = comparison["full_byte_equality"]
        pipeline.write_json(retained / "build-record.json", record)
        command = [sys.executable, "-B", str(PACKAGE / "runtime_probe.py"), "--repo", str(repo),
                   "--candidate", str(retained / "candidate.so"), "--candidate-sha256", record["candidate_sha256"],
                   "--expect", "rebuilt-baseline" if kind == "baseline" else "corrected",
                   "--build-record", str(retained / "build-record.json"), "--output", str(retained / "runtime.json")]
        attempt.run(kind + "-runtime", command, repo, minimal_env)
    inherited = evidence / "corrected/extension.json.gz"
    attempt.run("corrected-inherited-extension", [sys.executable, "-B", str(repo / "scripts/pump_extend_differential.py"),
                "--candidate", str(evidence / "corrected/candidate.so"), "--output", str(inherited)], repo, minimal_env)
    inherited_report = load_json(inherited)
    require(len(inherited_report["cases"]) == 308 and inherited_report["mismatches"] == [], "inherited extension regression did not pass")
    require(all(row["diff"] == [] and all(row["original"][key] == row["candidate"][key] for key in ("before", "after", "error", "events", "inner", "return")) for row in inherited_report["cases"]), "inherited saved effects differ")
    pipeline.write_json(evidence / "pair-summary.json", {
        "builds": results, "source_changed_only": changed,
        "inherited_extension": {"cases": 308, "mismatches": 0, "report_sha256": pipeline.digest(inherited),
            "qualification": "Existing suite excludes full logs; focused probe separately enforces recovered diagnostics."},
        "scope": "Two clean Linux source builds and bounded signed diagnostic checks; no selected-artifact promotion or historical compiler-identity claim."})
    attempt.run("test-actual-focused-receipts", [sys.executable, "-B", str(PACKAGE / "test_runtime.py"), "--built", str(evidence)], repo, minimal_env)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    require(not args.output.exists(), "output already exists; keep previous attempts intact")
    attempt = pipeline.Attempt(args.output)
    attempt.state.update(source_revision=subprocess.check_output(["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True).strip(),
                         scope=__doc__, status="preparing")
    attempt.save()
    tool_paths = [PACKAGE / name for name in ("linux_build.py", "runtime_probe.py", "recovery.py", "verify_evidence.py", "verify_runtime.py", "test_runtime.py", "source.patch", "pins.json")]
    tool_paths += [ROOT / "scripts/core_linux_v144_build.py", ROOT / "scripts/core_linux_v144_inputs.json",
                   ROOT / "scripts/compare.py", ROOT / "scripts/pump_extend_differential.py"]
    tool_paths += list((PACKAGE / "inputs").iterdir())
    for path in tool_paths:
        dest = attempt.evidence / "executed-inputs" / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    pipeline.write_json(attempt.evidence / "tooling-inputs.json", {
        path.relative_to(ROOT).as_posix(): pipeline.digest(path) for path in tool_paths})
    try:
        attempt.run("verify-original-and-selected-evidence", [sys.executable, "-B", str(PACKAGE / "verify_evidence.py")], args.repo, {k: os.environ[k] for k in ("HOME", "PATH", "LANG", "LC_ALL") if k in os.environ})
        run(args, attempt)
        original_tooling = load_json(attempt.evidence / "tooling-inputs.json")
        current_tooling = {path.relative_to(ROOT).as_posix(): pipeline.digest(path) for path in tool_paths}
        pipeline.write_json(attempt.evidence / "tooling-inputs-after.json", current_tooling)
        require(current_tooling == original_tooling, "executed tooling changed during build/runtime")
        attempt.state["status"] = "passed"
    except Exception as error:
        attempt.state.update(status="failed", error=str(error), traceback=traceback.format_exc())
        attempt.save()
        raise
    finally:
        attempt.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
