"""Verify a static compiler-source audit; never compile or execute a target."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT_SHA256 = "6a72c9aca71415b6382c1e76dea15dc4ee414783f6b2e6aa33b60f3062ca0cc3"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def checked(raw: bytes, entry: dict) -> bytes:
    require(len(raw) == entry["bytes"], f"size mismatch: {entry['path']}")
    require(hashlib.sha256(raw).hexdigest() == entry["sha256"],
            f"hash mismatch: {entry['path']}")
    return raw


def repo_input(repo: Path, entry: dict) -> bytes:
    path = repo / entry["path"]
    if path.is_file():
        return checked(path.read_bytes(), entry)
    # Sparse checkouts may omit old evidence. Read its pinned Git blob without
    # changing the checkout or trusting the mutable HEAD path.
    result = subprocess.run(["git", "cat-file", "blob", entry["git_blob"]],
                            cwd=repo, check=True, capture_output=True)
    return checked(result.stdout, entry)


def decode_guard(raw: bytes, offset: int, expected: dict) -> dict:
    code, regs, displacement, immediate = struct.unpack_from("<BBhi", raw, offset)
    decoded = dict(opcode=code, dst=regs & 15, src=regs >> 4,
                   target=offset + 8 + 8 * displacement,
                   immediate=immediate)
    require(decoded == expected, "guard opcode/register/destination mismatch")
    return decoded


def verify(repo: Path, compiler_sources: Path | None = None, fetch: bool = False) -> dict:
    raw_audit = (HERE / "audit.json").read_bytes()
    require(hashlib.sha256(raw_audit).hexdigest() == AUDIT_SHA256,
            "audit manifest seal mismatch")
    audit = json.loads(raw_audit)
    require(audit["actual_compiler_source_bound"] is False,
            "current refs cannot establish the historical compiler binding")
    require(not fetch or compiler_sources is not None, "--fetch requires --compiler-sources")
    if compiler_sources is not None:
        compiler_sources = compiler_sources.resolve()
    if fetch and compiler_sources is not None:
        compiler_sources.mkdir(parents=True, exist_ok=True)
    sources = {}
    for item in audit["compiler_sources"] if compiler_sources is not None else []:
        path = compiler_sources / item["path"]
        if fetch and not path.exists():
            # Full revision URLs are sealed in audit.json; downloaded code is
            # only read and hashed. Existing files are never overwritten.
            raw = urllib.request.urlopen(item["url"], timeout=30).read()
            checked(raw, item)
            path.write_bytes(raw)
        sources[item["path"]] = checked(path.read_bytes(), item)
    for item in audit["source_ranges"]:
        retained = checked((HERE / item["excerpt_path"]).read_bytes(),
                           {**item, "path": item["excerpt_path"]})
        if sources:
            lines = sources[item["path"]].splitlines(keepends=True)
            excerpt = b"".join(lines[item["first"] - 1:item["last"]])
            require(excerpt == retained, f"source range mismatch: {item['claim']}")
    observed = {}
    for item in audit["ref_observations"]:
        observed[item["path"]] = json.loads(checked((HERE / item["path"]).read_bytes(), item))
    require(observed["refs/platform-revision.json"]["sha"] == audit["platform_revision"],
            "platform ref receipt mismatch")
    require(observed["refs/rust-revision.json"]["sha"] == audit["rust_revision"],
            "Rust ref receipt mismatch")
    link = observed["refs/llvm-gitlink.json"]
    require(link["sha"] == audit["llvm_revision"] and
            link["submodule_git_url"] == "https://github.com/solana-labs/llvm-project.git",
            "LLVM gitlink receipt mismatch")
    evidence = {item["id"]: repo_input(repo, item) for item in audit["repo_inputs"]}
    require(evidence["candidate11"] == evidence["candidate14"], "11/14 equality changed")
    require(evidence["candidate12"] == evidence["candidate13"], "12/13 equality changed")
    for label, entry in audit["guards"].items():
        decode_guard(evidence[label], audit["guard_file_offset"], entry)
    tools = json.loads(evidence["compiler_receipt"])
    require(tools["selected_rustc_sha256"] == audit["recorded_rustc_sha256"] and
            "commit-hash: unknown" in tools["selected_rustc_version"],
            "historical compiler receipt changed")
    before = evidence["source11"].decode()
    after = evidence["source14"].decode()
    require(before.replace(audit["candidate14_removed"], audit["candidate14_added"], 1) == after,
            "candidate14 was not solely the already-tried checked subtraction change")
    require("metadata_uses.remaining >= number_of_uses" in evidence["positive_guard13"].decode(),
            "prior positive-guard source evidence missing")
    return dict(accepted=True, scope="static source/receipt audit only",
                retained_excerpts=len(audit["source_ranges"]),
                whole_compiler_sources_verified=len(sources), repository_inputs=len(evidence),
                actual_compiler_source_bound=False,
                unchanged_output_pairs=[[11, 14], [12, 13]],
                diagnostic_build_executed=False, new_source_hypothesis=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=HERE.parents[2])
    parser.add_argument("--compiler-sources", type=Path,
                        help="Caller-owned cache of pinned public compiler source files")
    parser.add_argument("--fetch", action="store_true",
                        help="Download missing pinned source files; no code is executed")
    args = parser.parse_args()
    print(json.dumps(verify(args.repo.resolve(), args.compiler_sources, args.fetch), indent=2))


if __name__ == "__main__":
    main()
