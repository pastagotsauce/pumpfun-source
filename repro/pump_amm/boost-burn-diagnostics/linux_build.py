#!/usr/bin/env python3
"""One pinned Linux boost diagnostic build on accepted liquidity/sweep/migration corrections."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import traceback

from boost import (PACKAGE, ROOT, PRIOR, PRIOR_SHA, PRIOR_RECORD_SHA, ORIGINAL_SHA,
                       SOURCE, digest, require, write_json, prior_source,
                       expected_source, patched_source, load_prior_builder, creator, sweep)

previous = load_prior_builder()
pipeline = previous.pipeline
from analyze import elf_layout


def run(args, attempt):
    repo, output, evidence = args.repo.resolve(), args.output.resolve(), attempt.evidence
    require(sys.platform == "linux" and platform.machine() == "x86_64", "Linux x86_64 required")
    prior_inputs = json.loads((PRIOR / "results/build/tooling-inputs.json").read_bytes())
    for name in ("scripts/core_linux_v144_build.py", "scripts/core_linux_v144_inputs.json"):
        require(pipeline.digest(repo / name) == prior_inputs[name], "prior pipeline input changed")
    pins = json.loads((repo / "scripts/core_linux_v144_inputs.json").read_bytes())
    phases = pins["pipeline_tools"]
    prior_tools = json.loads((PRIOR / "results/build/tool-bindings.json").read_bytes())
    recorded, inputs = prior_source(repo)
    source = output / "source"
    for name, path in inputs.items():
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    require(previous.source_hashes(source, recorded) == recorded, "source copy changed")
    write_json(evidence / "source-inputs.json", {"prior_build_record_sha256": PRIOR_RECORD_SHA,
        "prior_candidate_sha256": PRIOR_SHA, "input_sha256": recorded,
        "source_files": 30, "note": "All30 authentic source files copied from the accepted creator build; no synthesized or omitted source."})
    env = {key: os.environ[key] for key in ("HOME", "PATH", "LANG", "LC_ALL") if key in os.environ}
    env.update(LANG="C.UTF-8", LC_ALL="C.UTF-8")
    patch = PACKAGE / "source.patch"
    attempt.run("check-source-patch", ["git", "-c", "core.autocrlf=false", "apply", "--check", str(patch)], source, env)
    attempt.run("apply-source-patch", ["git", "-c", "core.autocrlf=false", "apply", str(patch)], source, env)
    before_source = previous.source_hashes(source, recorded)
    require(before_source == expected_source(repo), "unexpected source patch")
    require((source / SOURCE).read_bytes() == patched_source(inputs[SOURCE].read_bytes()), "patch is not exact")
    write_json(evidence / "source-before.json", before_source)
    shutil.copytree(source, evidence / "source")
    shutil.copy2(patch, evidence / "source.patch")

    tools, strip, cli_root, criterion = (output / name for name in ("platform-v144", "platform-v152", "agave", "criterion-v233"))
    pipeline.unpack(attempt.download("platform-v144.tar.bz2", pipeline.PLATFORM_URL, pipeline.PLATFORM_SHA, pipeline.PLATFORM_SIZE), tools)
    pipeline.unpack(attempt.download("platform-v152.tar.bz2", phases["strip_url"], phases["strip_sha256"], phases["strip_bytes"]), strip)
    pipeline.unpack(attempt.download("agave-v2.1.21.tar.bz2", pipeline.CLI_URL, pipeline.CLI_SHA, pipeline.CLI_SIZE), cli_root)
    pipeline.unpack_criterion(attempt.download("criterion-v2.3.3.tar.bz2", phases["criterion_url"], phases["criterion_sha256"], phases["criterion_bytes"]), criterion)
    for base, expected in ((tools, pins["platform_selected_sha256"]), (strip, phases["strip_selected_sha256"])):
        require(all(pipeline.digest(base / name) == sha for name, sha in expected.items()), "tool archive member mismatch")
    cli_bin = cli_root / "solana-release/bin"
    caches = {}
    for version, name, target in (("v1.44", "platform-tools", tools), ("v1.52", "platform-tools", strip), ("v2.3.3", "criterion", criterion)):
        cache = Path(os.environ["HOME"]) / ".cache/solana" / version / name
        require(not os.path.lexists(cache), "task cache already exists")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.symlink_to(target, target_is_directory=True)
        caches[str(cache)] = str(target)
    write_json(evidence / "pipeline-caches.json", {"links": caches, "completion_markers_fabricated": False})
    host_rustc = Path(subprocess.check_output(["rustup", "which", "--toolchain", "1.94.0", "rustc"], text=True).strip()).resolve()
    host = host_rustc.parents[1]
    bindings = {"host_rustc_sha256": pipeline.digest(host_rustc), "host_cargo_sha256": pipeline.digest(host / "bin/cargo"),
        "compiler_rustc_sha256": pipeline.digest(tools / "rust/bin/rustc"), "compiler_cargo_sha256": pipeline.digest(tools / "rust/bin/cargo"),
        "strip_objcopy_sha256": pipeline.digest(strip / "llvm/bin/llvm-objcopy"), "cli_sha256": pipeline.digest(cli_bin / "cargo-build-sbf")}
    require(all(prior_tools[name] == sha for name, sha in bindings.items()), "toolchain differs from accepted prior build")
    write_json(evidence / "tool-bindings.json", bindings)
    cargo_home, rustup, target = (output / name for name in ("cargo-home", "rustup", "target"))
    cargo_home.mkdir()
    rustup.mkdir()
    build_env = dict(env, CARGO_HOME=str(cargo_home), RUSTUP_HOME=str(rustup), CARGO_TARGET_DIR=str(target))
    build_env["PATH"] = str(cli_bin) + ":" + env["PATH"]
    attempt.run("link-host", ["rustup", "toolchain", "link", "host194", str(host)], output, build_env)
    attempt.run("select-host", ["rustup", "default", "host194"], output, build_env)
    sdk_source = repo / "repro/pump_amm/owner6048-v144/main/build-01/sdk"
    sdk_hashes = pipeline.tree_hashes(sdk_source)
    require(len(sdk_hashes) == 53 and {name: value.get("sha256") for name, value in sdk_hashes.items()} == pins["recorded_sdk_source_sha256"],
            "SDK bytes changed")
    sdk = output / "sdk"
    shutil.copytree(sdk_source, sdk)
    modes = {}
    for name in ("dump", "install", "objcopy", "package", "strip"):
        path = sdk / "scripts" / (name + ".sh")
        modes[name] = {"before": oct(stat.S_IMODE(path.stat().st_mode)), "after": "0o755"}
        path.chmod(0o755)
    require(pipeline.tree_hashes(sdk) == sdk_hashes, "SDK text changed")
    write_json(evidence / "sdk-inputs.json", {"sha256": sdk_hashes, "prepared_modes": modes,
        "scope": "Same explicit Linux executable-mode preparation as prior experiment; no historical Git mode claim."})
    for name, command in (("host-rustc-version", [str(host_rustc), "--version", "--verbose"]),
                          ("compiler-version", [str(tools / "rust/bin/rustc"), "--version", "--verbose"]),
                          ("cli-version", [str(cli_bin / "cargo-build-sbf"), "--version"]),
                          ("strip-version", [str(strip / "llvm/bin/llvm-objcopy"), "--version"])):
        attempt.run(name, command, output, build_env)
    fetch_env = dict(build_env, CARGO_TARGET_DIR=str(output / "fetch-target"))
    attempt.run("locked-public-fetch", ["cargo", "fetch", "--manifest-path", str(source / "programs/pump-amm/Cargo.toml"), "--locked"], source, fetch_env)
    locked = previous.registry_views(cargo_home, source, evidence)
    require(previous.source_hashes(source, recorded) == before_source, "fetch changed source/lock")
    artifact_dir = output / "artifacts"
    command = ["cargo", "build-sbf", "--manifest-path", str(source / "programs/pump-amm/Cargo.toml"), "--tools-version", "v1.44",
               "--offline", "--sbf-sdk", str(sdk), "--sbf-out-dir", str(artifact_dir), "--", "--locked", "--offline"]
    attempt.state["build_attempts"] += 1
    result = attempt.run("combined-build", command, source, build_env, check=False)
    after, source_error = None, None
    try:
        after = previous.source_hashes(source, recorded)
    except Exception as error:
        source_error = type(error).__name__ + ": " + str(error)
    record = {"kind": "liquidity-sweep-migration-boost-corrected", "accepted_build": False, "returncode": result,
        "source_sha256": before_source, "source_after_sha256": after, "source_unchanged": after == before_source,
        "source_validation_error": source_error,
        "source_patch_sha256": pipeline.digest(patch), "prior_candidate_sha256": PRIOR_SHA,
        "prior_build_record_sha256": PRIOR_RECORD_SHA, "pipeline": "Linux v1.44 compile / recorded SDK with explicit executable modes / v1.52 strip"}
    retained = evidence / "combined"
    retained.mkdir()
    produced = {}
    for src, name in ((artifact_dir / "pump_amm_recovered.so", "candidate.so"), (target / "sbf-solana-solana/release/pump_amm_recovered.so", "unstripped.so")):
        if src.is_file():
            shutil.copy2(src, retained / name)
            produced[name] = {"sha256": pipeline.digest(retained / name), "bytes": src.stat().st_size}
    record["produced_outputs"] = produced
    record_path = retained / "build-record.json"
    write_json(record_path, record)
    write_json(evidence / "excluded-keypair-paths.json", pipeline.excluded_keypair_paths(output))
    require(result == 0 and record["source_unchanged"] and set(produced) == {"candidate.so", "unstripped.so"}, "build failed")
    require(pipeline.tree_hashes(sdk, exclude=lambda p: "dependencies" in p.parts) == sdk_hashes, "SDK changed during compile")
    for namespace in pipeline.REGISTRY_NAMESPACES:
        pipeline.inventory_registry_view(cargo_home, locked, namespace)
    record.update(accepted_build=True, candidate_sha256=produced["candidate.so"]["sha256"], candidate_bytes=produced["candidate.so"]["bytes"],
                  unstripped_sha256=produced["unstripped.so"]["sha256"])
    write_json(record_path, record)
    candidate = retained / "candidate.so"
    original = (repo / "evidence/original/pump_amm/deployed.so").read_bytes()
    require(digest(original) == ORIGINAL_SHA, "original comparison input changed")
    for label, comparison in (("whole-original", original), ("prior-creator", (PRIOR / "results/build/combined/candidate.so").read_bytes())):
        write_json(retained / (label + "-comparison.json"), previous.compare(comparison, candidate.read_bytes()))
    raw_candidate = candidate.read_bytes()
    original_layout, candidate_layout = elf_layout(original), elf_layout(raw_candidate)
    require(original_layout["trailing_all_zero"], "captured unused allocation is not zero")
    require(len(raw_candidate) == candidate_layout["elf_extent"], "candidate has a suffix outside its complete ELF extent")
    extent = original_layout["elf_extent"]
    write_json(retained / "executable-comparison.json", {
        "executable": previous.compare(original[:extent], raw_candidate),
        "original_complete_elf_extent": extent, "candidate_complete_elf_extent": candidate_layout["elf_extent"],
        "original_captured_allocation_bytes": len(original), "original_captured_allocation_sha256": digest(original),
        "unused_original_allocation": {"offset": extent, "bytes": len(original) - extent,
            "sha256": digest(original[extent:]), "all_zero": True},
        "candidate_suffix_bytes": 0,
        "scope": "Complete ELF bytes compared; unused original allocation checked separately. No trimming by byte value, manufactured padding or byte rewriting."})
    attempt.run("focused-boost-and-regressions", [sys.executable, "-B", str(PACKAGE / "runtime_probe.py"), "--repo", str(repo),
                "--candidate", str(candidate), "--build-record", str(record_path), "--output", str(retained / "runtime.json")], repo, env)
    attempt.run("test-actual-focused-receipts", [sys.executable, "-B", str(PACKAGE / "test_runtime_boost.py"), "--built", str(retained)], repo, env)
    report_path = retained / "boost-burn.json"
    attempt.run("inherited-boost-burn", [sys.executable, "-B", str(repo / "scripts/pump_amm_boost_burn_differential.py"),
                "--candidate", str(candidate), "--output", str(report_path)], repo, env)
    from verify_boost import validate_inherited
    inherited = validate_inherited(json.loads(report_path.read_bytes()), repo, candidate.read_bytes())
    write_json(evidence / "summary.json", {"build": record, "source_changed_from_prior": [SOURCE],
        "inherited_boost_burn": {**inherited, "report_sha256": pipeline.digest(report_path)},
        "scope": "One five-guard source build preserving prior corrections;16boost and36prior cases enforce full diagnostics separately. No selection or byte-identity claim."})



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    require(not args.output.exists(), "output exists; retain previous attempts")
    attempt = pipeline.Attempt(args.output)
    attempt.state.update(source_revision=subprocess.check_output(["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True).strip(), scope=__doc__)
    tool_paths = list(PACKAGE.glob("*.py")) + [PACKAGE / "source.patch", PRIOR / "migration.py",
        PRIOR / "verify_creator.py", creator.PRIOR / "recovery.py"]
    tool_paths += [sweep.PRIOR / name for name in ("linux_build.py", "verify.py", "verify_runtime.py")]
    tool_paths += [ROOT / name for name in ("scripts/core_linux_v144_build.py", "scripts/core_linux_v144_inputs.json", "scripts/compare.py", "scripts/analyze.py",
                                          "scripts/pump_amm_creator_reassignment_differential.py", "scripts/pump_amm_sweep_differential.py",
                                          "scripts/pump_amm_boost_burn_differential.py", "scripts/pump_amm_legacy_sell_differential.py",
                                          "scripts/pump_amm_trade_v2_differential.py",
                                          "scripts/pump_amm_liquidity_differential.py")]
    write_json(attempt.evidence / "tooling-inputs.json", {path.relative_to(ROOT).as_posix(): pipeline.digest(path) for path in tool_paths})
    try:
        run(args, attempt)
        attempt.state["status"] = "passed"
    except Exception as error:
        attempt.state.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        attempt.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
