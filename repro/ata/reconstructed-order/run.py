#!/usr/bin/env python3
"""One source-only ATA control build and one supported linker-order experiment.

Run on Linux with Docker. No captured program is mounted into the container.
The optional reference is opened only after both compiler/linker outputs exist.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import shutil
import subprocess
import sys
import uuid

from prepare_order import BASELINE_BYTES, BASELINE_SHA256, prepare, require, verify_linked_order

SOURCE_COMMIT = "f5ce86d43dd31ddefb96d4e8cdd67dd073dc5dca"
IMAGE = "solanafoundation/solana-verifiable-build@sha256:ee9ad7809009a99a70f659f7cba959e0c3c124e10f771b524914fd42f2b605a8"
REFERENCE_SHA256 = "6804554e69fd3a58caa191dc4a58f4c67223d30ca28ab8987f39fc18d2f7374d"
LOCK_SHA256 = "3c8f402f40488908503e9cc088388c1f95848d79da5141b5cb1a14006d74428b"
MANIFEST = "associated-token-account/program/Cargo.toml"
LIBRARY = "spl_associated_token_account.so"
PINNED_SYMLINKS = json.loads((Path(__file__).parent / "source-symlinks.json").read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def symlink_destination(name, blob, target, indexed):
    """Accept only the twelve exact, direct in-tree links in the pinned source tree."""
    expected = PINNED_SYMLINKS["links"].get(name)
    require(expected is not None and blob == expected["blob"] and target == expected["target"],
            "Unknown or modified source symlink: " + name)
    destination = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
    require(not posixpath.isabs(target) and destination != ".." and not destination.startswith("../"),
            "Source symlink escapes checkout")
    expected_destination = PINNED_SYMLINKS["destinations"].get(destination)
    actual_destination = indexed.get(destination)
    require(expected_destination is not None and actual_destination ==
            (expected_destination["mode"], expected_destination["blob"]),
            "Source symlink target is missing, changed or chained: " + name)
    return destination


def source_manifest(source, allow_target=False):
    """Bind tracked bytes/link text and reject extra build inputs, including ignored ones."""
    entries = subprocess.check_output(["git", "-C", str(source), "ls-files", "--stage", "-z"])
    indexed = {}
    for entry in entries.split(b"\0"):
        if entry:
            metadata, name = entry.split(b"\t", 1)
            mode, blob, stage = metadata.decode().split()
            require(mode in ("100644", "100755", "120000") and stage == "0",
                    "Source index contains a submodule or unresolved entry")
            require(name.decode() not in indexed, "Duplicate source index entry")
            indexed[name.decode()] = (mode, blob)
    manifest = {}
    for name, (mode, blob) in indexed.items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Invalid source path")
        path = source / relative
        require(all(not p.is_symlink() for p in
                path.parents if p != source and source in p.parents),
                "Source parent directory is symlinked")
        if mode == "120000":
            require(path.is_symlink(), "Tracked source symlink is missing or replaced: " + name)
            target = os.readlink(path)
            destination = symlink_destination(name, blob, target, indexed)
            resolved = path.resolve(strict=True)
            require(source in resolved.parents and resolved == source / destination,
                    "Source symlink resolves outside its pinned target: " + name)
            require(resolved.is_file() and not resolved.is_symlink(), "Source symlink has no regular target")
            data = os.fsencode(target)
        else:
            require(not path.is_symlink(), "Tracked regular source file is symlinked")
            require(path.is_file(), "Tracked source file is missing: " + str(relative))
            data = path.read_bytes()
        actual_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(actual_blob == blob, "Tracked source bytes differ from Git: " + str(relative))
        manifest[name] = sha(data)
    for switches in (["--others", "--exclude-standard"],
                     ["--others", "--ignored", "--exclude-standard"]):
        extras = subprocess.check_output(["git", "-C", str(source), "ls-files", *switches, "-z"])
        for name in extras.split(b"\0"):
            if name:
                relative = Path(name.decode())
                require(allow_target and relative.parts[0] == "target",
                        "Unexpected untracked or ignored build input: " + str(relative))
    return manifest


def resolve_reference(source, reference):
    if reference is None:
        return None
    reference = reference.resolve()
    require(source != reference and source not in reference.parents,
            "Captured reference must be outside the source mount")
    return reference


def retain_baseline(source, output):
    """Preserve available compiler results before accepting or rejecting the control build."""
    records = {}
    for relative, name in (("target/deploy/" + LIBRARY, "baseline.so"),
                           ("target/bpfel-unknown-unknown/release/" + LIBRARY, "baseline.symbols.so")):
        path = source / relative
        if path.is_file():
            data = path.read_bytes()
            (output / name).write_bytes(data)
            records[name] = {"bytes": len(data), "sha256": sha(data)}
        else:
            records[name] = {"available": False}
    write_json(output / "baseline-artifacts.json", records)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    require(sys.platform.startswith("linux"), "This driver requires Linux and Docker")
    source, output = args.source.resolve(), args.output.resolve()
    reference_path = resolve_reference(source, args.reference)
    require(source not in output.parents and source != output, "Output must be outside source checkout")
    require(not output.exists(), "Output already exists; use a fresh directory")
    output.mkdir(parents=True)
    commands = []
    container = None
    result = {"status": "STARTED", "historical_uploader_recipe": None,
              "recipe": "independent source compilation with reconstructed symbol order",
              "source_commit": SOURCE_COMMIT, "image": IMAGE,
              "original_program_mounted": False, "reference_opened": False,
              "binary_patching": False, "padding": False}

    def read(command):
        commands.append(command)
        return subprocess.check_output(command, text=True).strip()

    def run_logged(command, filename, check=True):
        commands.append(command)
        with (output / filename).open("wb") as stream:
            execution = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        result[filename + "_exit"] = execution.returncode
        if check:
            execution.check_returncode()
        return execution

    try:
        require(read(["git", "-C", str(source), "rev-parse", "HEAD"]) == SOURCE_COMMIT,
                "Wrong source revision")
        require(not read(["git", "-C", str(source), "status", "--porcelain"]),
                "Source checkout must start clean")
        require(not (source / "target").exists(), "Source checkout has a prior target directory")
        require(sha((source / "Cargo.lock").read_bytes()) == LOCK_SHA256, "Wrong source lockfile")
        before = source_manifest(source)
        write_json(output / "source-manifest.json", before)
        run_logged(["docker", "pull", "--platform", "linux/amd64", IMAGE], "image-pull.log")
        write_json(output / "image-inspect.json", json.loads(read(["docker", "image", "inspect", IMAGE])))
        workdir = read(["docker", "run", "--rm", "--platform", "linux/amd64", IMAGE, "pwd"])
        require(workdir.startswith("/") and workdir != "/" and "\n" not in workdir,
                "Unexpected build-image workdir")
        container = read(["docker", "run", "--rm", "--platform", "linux/amd64",
                          "--name", "ata-reconstructed-order-" + uuid.uuid4().hex[:12],
                          "--mount", f"type=bind,source={source},target={workdir}",
                          "-d", IMAGE, "sleep", "infinity"])
        active = read(["docker", "exec", "-w", "/", container, "rustup", "show", "active-toolchain"]).split()[0]
        manifest = workdir.rstrip("/") + "/" + MANIFEST
        baseline_execution = run_logged(["docker", "exec", "-e", "RUSTUP_TOOLCHAIN=" + active,
                    "-e", "RUSTFLAGS=-D warnings", "-w", workdir, container,
                    "cargo", "build-bpf", "--manifest-path", manifest, "--", "--locked"],
                    "baseline-build.log", check=False)
        result["baseline_artifacts"] = retain_baseline(source, output)
        baseline_execution.check_returncode()
        baseline_path = source / "target/deploy" / LIBRARY
        symbols_path = source / "target/bpfel-unknown-unknown/release" / LIBRARY
        baseline = baseline_path.read_bytes()
        require(len(baseline) == BASELINE_BYTES and sha(baseline) == BASELINE_SHA256,
                "Baseline did not reproduce selected candidate2; ordered build is not run")
        order, order_report = prepare(baseline, symbols_path.read_bytes())
        (output / "symbol-order.txt").write_bytes(order)
        write_json(output / "order.json", order_report)
        require(before == source_manifest(source, allow_target=True), "Baseline changed source or lockfile")

        rustc = read(["docker", "exec", container, "rustup", "which", "--toolchain", "bpf", "rustc"])
        sysroot = read(["docker", "exec", container, rustc, "--print", "sysroot"])
        sysroot = read(["docker", "exec", container, "readlink", "-f", sysroot])
        rustc_version = read(["docker", "exec", container, rustc, "--version", "--verbose"])
        host = next(line.split(": ", 1)[1] for line in rustc_version.splitlines() if line.startswith("host: "))
        linker = sysroot + "/lib/rustlib/" + host + "/bin/rust-lld"
        help_text = read(["docker", "exec", container, linker, "-flavor", "gnu", "--help"])
        (output / "linker-help.txt").write_text(help_text + "\n", encoding="utf-8", newline="\n")
        require("--symbol-ordering-file" in help_text, "Pinned linker does not support symbol ordering")
        linker_version = read(["docker", "exec", container, linker, "-flavor", "gnu", "--version"])
        llvm = sysroot.rsplit("/", 1)[0] + "/llvm/bin"
        tools = {"rustc": rustc, "cargo": sysroot + "/bin/cargo", "rust-lld": linker,
                 "llvm-objcopy": llvm + "/llvm-objcopy"}
        tool_hashes = {name: read(["docker", "exec", container, "sha256sum", path]).split()[0]
                       for name, path in tools.items()}
        write_json(output / "toolchain.json", {"active_host_toolchain": active,
                   "rustc_version": rustc_version, "linker_version": linker_version,
                   "paths": tools, "sha256": tool_hashes})
        subprocess.run(["docker", "cp", str(output / "symbol-order.txt"),
                        container + ":/tmp/ata-symbol-order.txt"], check=True)
        environment = ["RUSTUP_TOOLCHAIN=" + active, "RUSTFLAGS=-D warnings -Zremap-cwd-prefix=",
                       "CC=" + llvm + "/clang", "AR=" + llvm + "/llvm-ar",
                       "OBJDUMP=" + llvm + "/llvm-objdump", "OBJCOPY=" + llvm + "/llvm-objcopy"]
        command = ["docker", "exec", "-w", workdir + "/associated-token-account/program", container,
                   "env", "-u", "RUSTC", *environment, "cargo", "+bpf", "rustc",
                   "--manifest-path", manifest, "--target", "bpfel-unknown-unknown", "--release",
                   "--locked", "--lib", "--", "-C", "link-arg=--symbol-ordering-file=/tmp/ata-symbol-order.txt"]
        run_logged(command, "ordered-build.log")
        ordered_log = (output / "ordered-build.log").read_text(errors="replace")
        require("symbol ordering file:" not in ordered_log and "unable to order" not in ordered_log,
                "Linker reported an ordering warning")
        require(before == source_manifest(source, allow_target=True), "Ordered build changed source or lockfile")
        shutil.copyfile(symbols_path, output / "ordered.symbols.so")
        verify_linked_order(symbols_path.read_bytes(), order_report)
        result["exact_requested_placement"] = True
        container_symbols = workdir + "/target/bpfel-unknown-unknown/release/" + LIBRARY
        container_stripped = workdir + "/target/ata-ordered.so"
        run_logged(["docker", "exec", container, tools["llvm-objcopy"], "--strip-all",
                    container_symbols, container_stripped], "ordered-strip.log")
        shutil.copyfile(source / "target/ata-ordered.so", output / "ordered.so")
        candidate = (output / "ordered.so").read_bytes()
        result.update(status="BUILT_UNCOMPARED", baseline_sha256=sha(baseline),
                      candidate_sha256=sha(candidate), candidate_bytes=len(candidate),
                      source_unchanged=True, symbol_order_sha256=sha(order))
        if reference_path is not None:
            # The captured reference first enters the process here, after independent linking/stripping.
            reference = reference_path.read_bytes()
            result["reference_opened"] = True
            require(sha(reference) == REFERENCE_SHA256, "Wrong captured ATA reference")
            differences = sum(a != b for a, b in zip(reference, candidate))
            result.update(reference_sha256=sha(reference), reference_bytes=len(reference),
                          differing_shared_positions=differences,
                          length_difference=len(candidate) - len(reference),
                          baseline_differing_shared_positions=sum(a != b for a, b in zip(reference, baseline)),
                          full_byte_equality=reference == candidate,
                          status="EXACT_RECONSTRUCTED_RECIPE" if reference == candidate else "DIFFERS")
        print(json.dumps(result, indent=2))
        return 0 if result["status"] in ("EXACT_RECONSTRUCTED_RECIPE", "BUILT_UNCOMPARED") else 1
    except Exception as error:
        result.update(status="FAILED", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        write_json(output / "commands.json", commands)
        write_json(output / "result.json", result)
        if container:
            subprocess.run(["docker", "stop", container], check=False, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())
