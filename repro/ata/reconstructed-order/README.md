# ATA reconstruction through a supported linker order

This is a **proposed reconstructed build recipe**, not recovery of the release
uploader's historical invocation. No byte-identity result is claimed before an
actual run of `run.py` succeeds and its retained output is reviewed.

The existing [ATA monomorph proof](../monomorph-order-proof/REPORT.md) and
[complete correspondence proof](../../parallel-work/2026-10-24/results/ata_recipe/evidence/REPORT.md)
isolate the selected candidate's 307 differing positions to the placement of two
adjacent `RawVec::reserve_for_push` specializations and affected calls/relocations.
Candidate2 places the 352-byte `u8` function before the 440-byte `AccountMeta`
function; the capture has the reverse order. Their combined extent is unchanged.

This experiment asks whether ordinary source compilation plus the pinned
linker's supported symbol-order option can reproduce that placement. It does
not patch an ELF, replace compiler-generated code, supply original bytes to a
build, change the compiler, or search flags/metadata values.

## Reproduction

Use a Linux host with Python 3 and Docker. Start with a clean checkout of
`solana-labs/solana-program-library` at
`f5ce86d43dd31ddefb96d4e8cdd67dd073dc5dca` in `work/ata-source`.

```sh
python -B repro/ata/reconstructed-order/test_prepare_order.py
python -B repro/ata/reconstructed-order/test_driver.py
python -B repro/ata/reconstructed-order/run.py \
  --source work/ata-source \
  --output work/ata-order-run \
  --reference evidence/dependencies/associated_token/deployed.so
```

The output directory must not already exist. The driver:

1. Builds the unchanged source and lock in the existing digest-pinned image.
   The stripped baseline must reproduce candidate2's full SHA256
   `ba8dd8a42ca7bff4b668c72e1b5614e9363b271924d520253f5724760ba2d65b`.
2. Reads that fresh build's symbol table. It emits symbol names only, retaining
   every function's order except the evidenced adjacent pair. Missing,
   ambiguous, overlapping or unexpected symbols stop the experiment.
3. Checks the actual pinned `rust-lld` help for `--symbol-ordering-file`, then
   compiles the final crate with that one linker argument. It requires all
   symbols to retain their sizes and addresses apart from the specified pair.
4. Uses the same SDK's `llvm-objcopy --strip-all`. Only then does the host read
   the captured reference and compare the entire raw output, including length.

The Docker container mounts only the official source checkout. The order file
is copied into the container separately; no captured executable is mounted.
Before mounting, every tracked regular file must equal its Git blob; missing
files, submodules and untracked or ignored inputs are rejected. The exact twelve
tracked symlinks in the pinned source tree are accepted only with their original
Git blob and relative target, resolving directly to their pinned, regular,
tracked in-tree destinations. Unknown, replaced, escaping, missing or chained
links are rejected. `source-symlinks.json` records that complete tree shape.
After compilation, new files are allowed only beneath the generated `target/`
directory. The optional reference must resolve outside the mounted source tree.
`result.json`, commands, logs, input hashes, actual tool hashes/help and both
builds' raw/unstripped outputs are retained. Available baseline outputs and their
measured hashes are saved before a failed build or unequal baseline is rejected.
Upload only the output directory,
which excludes generated keypairs. A failed baseline or unsupported ordering
stops without selecting a different recipe.

## Why the option is applicable

The retained v1.27 Rust revision's BPF target uses `sbf_base`, whose linker is
`rust-lld` and whose `.text` output collects function input sections. Its pinned
LLVM submodule implements `--symbol-ordering-file` for local and global symbols.
The implementation assigns priorities to input sections and sorts their existing
contents; the linker still resolves calls and relocations. [Pinned target](https://github.com/anza-xyz/rust/blob/e2df8fa5aff81929ef8e5f5cf8b177e5cec0fe87/compiler/rustc_target/src/spec/sbf_base.rs),
[pinned LLD option](https://github.com/solana-labs/llvm-project/blob/9509bb55a565c64e45ea0b20dfba7fe16fc01fc1/lld/ELF/Options.td),
[pinned LLD ordering implementation](https://github.com/solana-labs/llvm-project/blob/9509bb55a565c64e45ea0b20dfba7fe16fc01fc1/lld/ELF/Writer.cpp).

These source observations select one testable recipe; they do not substitute
for the driver's checks against the actual linker and emitted symbols.
`source-receipts.json` records the immutable files inspected for this proposal.

Fifteen local tests exercise synthetic ELF parsing and failure cases, including
a wrong baseline, altered text, ambiguous functions, changed sizes, duplicate
names, overlaps, truncated input, wrong architecture, injected order lines,
ignored ordering and unrelated placement changes. These are tooling checks,
not runtime comparisons or evidence of a successful rebuild.
Fourteen additional filesystem/topology tests verify source-input rejection,
reference separation, retention of an unequal control artifact, and the actual
twelve-link source-tree shape. The real filesystem symlink case skips where the
host lacks symlink privileges; it must pass on the Linux build runner.

The first hosted attempt, [40286252822](https://github.com/pastagotsauce/pumpfun-source/actions/runs/40286252822),
stopped before Docker because its initial gate rejected all symlinks. No build
or equality result came from that attempt. The exception above admits only the
twelve legitimate links observed in the immutable source tree; the original
failure remains separate evidence.
