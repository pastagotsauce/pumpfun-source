#!/usr/bin/env python3
"""One unchanged-source Mayhem build with official Linux v1.54 and v1.52 strip."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tomllib
import traceback
import urllib.request

sys.dont_write_bytecode = True
from evidence import Elf, compare, require, same_location_payload, sha

P = Path(__file__).resolve().parent
INPUTS_SHA = "f7a141ef09a60c773db988ebe5b07eb7a51d6d9c0da9c807cd901550a9ced20d"
TARGET = "sbpf-solana-solana"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value, compressed=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(gzip.compress(data, mtime=0) if compressed else data)


def pins():
    raw = (P / "inputs.json").read_bytes()
    require(sha(raw) == INPUTS_SHA, "Input pins changed")
    return json.loads(raw)


def inventory(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            key = path.relative_to(root).as_posix()
            require(not name.endswith("-keypair.json"), "Unexpected generated keypair path")
            if path.is_symlink():
                result[key] = {"symlink": os.readlink(path)}
            elif path.is_file():
                result[key] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    return result


def check_source(root, expected):
    rows = inventory(root)
    require(set(rows) == set(expected) and all("sha256" in row for row in rows.values()),
            "Source path inventory differs")
    observed = {name: row["sha256"] for name, row in rows.items()}
    require(observed == expected, "Frozen source bytes changed")
    return observed


def reject_parent_config(directory):
    for parent in (directory, *directory.parents):
        for filename in ("config", "config.toml"):
            require(not os.path.lexists(parent / ".cargo" / filename), "Ambient Cargo configuration present")


def measure_source(attempt, source, expected, label):
    after = inventory(source)
    write_json(attempt.evidence / (label + ".json"), after)
    equal = {name: row.get("sha256") for name, row in after.items()} == expected
    attempt.state.update(source_changed=not equal, source_unchanged=equal)
    attempt.save()
    return equal


def registry_inventory(cargo_home, lock):
    locked = [row for row in lock["package"] if "source" in row]
    require(len(locked) == 215 and all(row["source"] == "registry+https://github.com/rust-lang/crates.io-index"
                                      for row in locked), "Unexpected locked dependency graph")
    cache_root, source_root = cargo_home / "registry/cache", cargo_home / "registry/src"
    require(cache_root.is_dir() and source_root.is_dir(), "Missing fetched registry")
    namespaces = {p.name for p in cache_root.iterdir()}
    require(len(namespaces) == 1 and namespaces == {p.name for p in source_root.iterdir()},
            "Unexpected registry namespaces")
    namespace = next(iter(namespaces))
    stems = {r["name"] + "-" + r["version"] for r in locked}
    require({p.name for p in (cache_root / namespace).iterdir()} == {s + ".crate" for s in stems},
            "Registry archive set differs from lock")
    require({p.name for p in (source_root / namespace).iterdir()} == stems, "Registry source set differs from lock")
    result = {}
    for row in locked:
        stem = row["name"] + "-" + row["version"]
        archive, source = cache_root / namespace / (stem + ".crate"), source_root / namespace / stem
        require(not archive.is_symlink() and not source.is_symlink(), "Symlinked registry input")
        require(digest(archive) == row["checksum"], "Registry archive checksum mismatch: " + stem)
        actual = inventory(source)
        require(all("sha256" in value for value in actual.values()), "Registry source symlink")
        expected = {}
        with tarfile.open(archive, "r:gz") as crate:
            for member in crate:
                if member.isdir():
                    continue
                path = Path(member.name)
                require(member.isfile() and not path.is_absolute() and ".." not in path.parts
                        and path.parts[0] == stem, "Unsafe crate member")
                relative = Path(*path.parts[1:]).as_posix()
                require(relative not in expected, "Duplicate crate member")
                expected[relative] = {"bytes": member.size, "sha256": sha(crate.extractfile(member).read())}
        require(set(actual) - set(expected) <= {".cargo-ok"}, "Unexpected extracted dependency files")
        require(all(actual.get(name) == value for name, value in expected.items()), "Extracted crate bytes differ")
        result[stem] = {"archive_sha256": row["checksum"], "files": actual}
    return result


class Attempt:
    def __init__(self, output):
        self.output = output
        output.mkdir(parents=True, exist_ok=False)
        self.evidence = output / "evidence"
        self.evidence.mkdir()
        self.state = {"status": "PREPARING", "build_attempts": 0, "reference_opened": False,
                      "runtime_executed": False, "source_changed": None,
                      "historical_uploader_recipe": None, "binary_patching": False, "padding": False}
        self.commands = []
        self.save()

    def save(self):
        write_json(self.evidence / "result.json", self.state)
        write_json(self.evidence / "commands.json", self.commands)

    def command(self, label, command, cwd, env, check=True):
        record = {"label": label, "argv": command, "cwd": str(cwd), "environment": env, "exit": None}
        self.commands.append(record)
        self.save()
        log = self.evidence / (label + ".log")
        with log.open("xb") as stream:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
        record.update(exit=result.returncode, log_sha256=digest(log), log_bytes=log.stat().st_size)
        self.save()
        if check:
            require(result.returncode == 0, label + " failed")
        return result.returncode

    def download(self, name, metadata):
        directory = self.output / "downloads"
        directory.mkdir(exist_ok=True)
        path = directory / name
        receipt = {"url": metadata["url"], "expected_sha256": metadata["sha256"],
                   "expected_bytes": metadata["bytes"], "complete": False}
        try:
            with urllib.request.urlopen(metadata["url"], timeout=90) as response, path.open("xb") as stream:
                shutil.copyfileobj(response, stream)
            receipt.update(observed_bytes=path.stat().st_size, observed_sha256=digest(path))
            require(receipt["observed_bytes"] == metadata["bytes"] and
                    receipt["observed_sha256"] == metadata["sha256"], "Tool archive checksum mismatch")
            receipt["complete"] = True
        finally:
            if path.is_file():
                receipt.update(observed_bytes=path.stat().st_size, observed_sha256=digest(path))
            write_json(self.evidence / (name + ".receipt.json"), receipt)
        return path

    def retain(self, unstripped, stripped):
        files = {}
        for source, name in ((unstripped, "unstripped.so"), (stripped, "candidate.so")):
            if source.is_file():
                shutil.copy2(source, self.evidence / name)
                files[name] = {"bytes": source.stat().st_size, "sha256": digest(source)}
        write_json(self.evidence / "produced-outputs.json", files)
        self.state["produced_outputs"] = files
        self.save()


def run(repo, attempt):
    require(sys.platform == "linux" and platform.machine() == "x86_64", "Linux x86_64 required")
    frozen = pins()
    root, evidence = attempt.output, attempt.evidence
    driver = {}
    for name in ("run.py", "evidence.py", "inputs.json"):
        original = P / name
        destination = evidence / "driver" / name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(original, destination)
        driver[name] = {"bytes": destination.stat().st_size, "sha256": digest(destination)}
    write_json(evidence / "driver-bindings.json", driver)
    require(root != repo and repo not in root.parents, "Output must be outside repository")
    require(digest(repo / frozen["source_receipt"]["path"]) == frozen["source_receipt"]["sha256"],
            "Prior source-build receipt changed")
    source = root / "source"
    for name, expected in frozen["source_sha256"].items():
        current = repo / name
        require(not current.is_symlink() and digest(current) == expected, "Current source differs: " + name)
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, destination)
    check_source(source, frozen["source_sha256"])
    reject_parent_config(source)
    shutil.copytree(source, evidence / "source")
    write_json(evidence / "source-before.json", frozen["source_sha256"])
    shutil.copy2(P / "inputs.json", evidence / "input-pins.json")
    tool_roots = {}
    for name in ("compiler", "stripper"):
        archive = attempt.download(name + ".tar.bz2", frozen[name])
        destination = root / name
        destination.mkdir()
        with tarfile.open(archive, "r:bz2") as package:
            package.extractall(destination, filter="data")
        tool_roots[name] = destination
    compiler, stripper = tool_roots["compiler"], tool_roots["stripper"]
    for name, expected in frozen["compiler"]["selected_members"].items():
        path = compiler / name
        require(digest(path) == expected["sha256"] and path.stat().st_size == expected["bytes"], "Compiler member mismatch")
    require(digest(stripper / "llvm/bin/llvm-objcopy") == frozen["stripper"]["objcopy_sha256"], "Stripper mismatch")
    tools_before = {name: inventory(path) for name, path in tool_roots.items()}
    write_json(evidence / "tools-before.json.gz", tools_before, compressed=True)
    home, cargo_home, rustup_home = root / "home", root / "cargo-home", root / "rustup-home"
    for directory in (home, cargo_home, rustup_home):
        directory.mkdir()
    env = {"HOME": str(home), "PATH": str(compiler / "rust/bin") + ":/usr/bin:/bin",
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "CARGO_HOME": str(cargo_home),
           "RUSTUP_HOME": str(rustup_home), "RUSTC": str(compiler / "rust/bin/rustc"),
           "RUSTDOC": str(compiler / "rust/bin/rustdoc"),
           "CC": str(compiler / "llvm/bin/clang"), "AR": str(compiler / "llvm/bin/llvm-ar"),
           "OBJDUMP": str(compiler / "llvm/bin/llvm-objdump"), "OBJCOPY": str(compiler / "llvm/bin/llvm-objcopy"),
           "CARGO_TARGET_SBPF_SOLANA_SOLANA_RUSTFLAGS": "-Zremap-cwd-prefix="}
    cargo = str(compiler / "rust/bin/cargo")
    manifest = source / "programs/mayhem/Cargo.toml"
    for label, command in (("compiler-version", [env["RUSTC"], "--version", "--verbose"]),
                           ("cargo-version", [cargo, "--version", "--verbose"]),
                           ("target-cfg", [env["RUSTC"], "--print", "cfg", "--target", TARGET]),
                           ("stripper-version", [str(stripper / "llvm/bin/llvm-objcopy"), "--version"]),
                           ("host-linker-version", ["/usr/bin/cc", "--version"])):
        attempt.command(label, command, source, env)
    write_json(evidence / "host.json", {"uname": list(platform.uname()), "python": sys.version,
                                        "host_cc_sha256": digest(Path("/usr/bin/cc").resolve()),
                                        "filesystem_hermeticity": "not claimed; clean explicit input paths and environment",
                                        "network_hermeticity": "Cargo offline compilation; OS network denial not claimed"})
    fetch_env = dict(env, CARGO_TARGET_DIR=str(root / "fetch-target"))
    attempt.command("locked-fetch", [cargo, "fetch", "--locked", "--manifest-path", str(manifest)], source, fetch_env)
    check_source(source, frozen["source_sha256"])
    lock = tomllib.loads(manifest.with_name("Cargo.lock").read_text())
    registry_before = registry_inventory(cargo_home, lock)
    write_json(evidence / "registry-before.json.gz", registry_before, compressed=True)
    require(not (cargo_home / "config").exists() and not (cargo_home / "config.toml").exists(), "Injected Cargo home configuration")
    target = root / "target"
    require(not target.exists(), "Compile target was populated before the single build")
    build_env = dict(env, CARGO_TARGET_DIR=str(target), CARGO_NET_OFFLINE="true")
    command = [cargo, "build", "--manifest-path", str(manifest), "--release", "--target", TARGET,
               "--locked", "--offline", "--verbose"]
    unstripped = target / TARGET / "release/mayhem_recovered.so"
    stripped = root / "candidate.so"
    attempt.state.update(status="BUILDING", build_attempts=1, source_changed=None)
    try:
        exit_code = attempt.command("compile", command, source, build_env, check=False)
        attempt.state["compile_exit"] = exit_code
    finally:
        attempt.retain(unstripped, stripped)
        measure_source(attempt, source, frozen["source_sha256"], "source-after-compile")
    check_source(source, frozen["source_sha256"])
    require(exit_code == 0, "Compilation failed")
    require(unstripped.is_file(), "Compiler produced no expected ELF")
    try:
        exit_code = attempt.command("strip", [str(stripper / "llvm/bin/llvm-objcopy"), "--strip-all",
                                               str(unstripped), str(stripped)], source, env, check=False)
        attempt.state["strip_exit"] = exit_code
    finally:
        attempt.retain(unstripped, stripped)
    require(exit_code == 0 and stripped.is_file(), "Stripping failed")
    registry_after = registry_inventory(cargo_home, lock)
    tools_after = {name: inventory(path) for name, path in tool_roots.items()}
    write_json(evidence / "registry-after.json.gz", registry_after, compressed=True)
    write_json(evidence / "tools-after.json.gz", tools_after, compressed=True)
    require(registry_after == registry_before, "Dependency bytes changed during compilation")
    require(tools_after == tools_before, "Compiler distribution changed during compilation")
    require(all(digest(P / name) == row["sha256"] for name, row in driver.items()), "Executing driver files changed")
    require(measure_source(attempt, source, frozen["source_sha256"], "source-after"), "Frozen source bytes changed")
    candidate, symbols = stripped.read_bytes(), unstripped.read_bytes()
    require(Elf(candidate).allocated() == Elf(symbols).allocated(), "Strip changed allocated sections")
    # Original and selected images are first opened after the single source build.
    original = (repo / frozen["original"]["path"]).read_bytes()
    selected = (repo / frozen["selected"]["path"]).read_bytes()
    attempt.state["reference_opened"] = True
    require(sha(original) == frozen["original"]["sha256"] and sha(selected) == frozen["selected"]["sha256"],
            "Comparison input changed")
    write_json(evidence / "whole-original-comparison.json", compare(original, candidate))
    write_json(evidence / "selected-darwin-comparison.json", compare(selected, candidate))
    location = Elf(symbols).constructor_locations()
    write_json(evidence / "compiled-location.json", location)
    original_location = Elf(original).location(632832)
    write_json(evidence / "original-location.json", original_location)
    matched = same_location_payload(location["location"], original_location)
    attempt.state.update(status="MEASURED", source_unchanged=True,
                         distribution_location_matches_original=matched, full_byte_equality=candidate == original)
    attempt.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    attempt = Attempt(args.output.resolve())
    try:
        run(args.repo.resolve(), attempt)
    except Exception as error:
        attempt.state.update(status="FAILED", error=str(error), exception_type=type(error).__name__)
        (attempt.evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        attempt.save()
        raise
    finally:
        write_json(attempt.evidence / "manifest.json", inventory(attempt.evidence))


if __name__ == "__main__":
    main()
