# Metaplex Utilize: branch-selection frontier (static only)

No additional ordinary source rewrite is justified by the saved trials. The new discriminator is a specific compiler-stage boundary: the referenced SBF backend cannot use the generic machine-block-placement conditional reversal path, whereas SelectionDAG branch lowering can complement a condition according to its successor order. This is a source-supported mechanism, not proof of the historical compiler invocation or the actual cause of candidate11's residual.

No new source candidate, compilation, VM execution, flag experiment, binary rewrite, diagnostic-coordinate adjustment, or selection change was performed. Repository publication, if reviewed, is limited to a static audit.

## Existing negative experiments govern the next step

Candidate11 uses a unified ordered guard for zero use, use above total, and use above remaining, followed by checked subtraction. Candidate12 removes only the last explicit condition and retains checked subtraction. Candidate13 uses an explicit positive remaining >= requested expression after the first two guards; its complete output equals candidate12. Candidate14 keeps candidate11's unified guard and replaces the redundant checked subtraction with ordinary subtraction; its complete output equals candidate11.

The saved binary hashes are 11=14: `3bbaf27ff0c10ff68d8a195a82f39eadee266f324067bd0a66081710be30b4ec`, and 12=13: `4f039033a3cde9d47aa8ee0f68c13c2c4d55a9d6ee0ab50df9d4ef93a4a02edf`. Both raw outputs are 707,448 bytes. These are measured negative experiments, so neither positive comparison spelling nor dropping the redundant checked subtraction is a fresh hypothesis.

At file offset 238832 the original bytes are `3d97070000000000`: unsigned r7 >= r9 jumps to success at 238896 and falls through to error construction at 238840. Candidate11 has `2d79120000000000`: unsigned r9 > r7 jumps to error at 238984 and falls through to success at 238840. Candidate12/13 instead adds one unconditional branch after its complementary conditional. The existing complete-body and prior function-order audits remain the authority for all other instruction mapping; this investigation does not repeat those analyses or infer historical source from token multisets.

## New compiler-source evidence and its binding limit

The platform-tools v1.37 Git ref currently resolves to `390112a3f6d25e17662e83bf73d73f3d483b556e`. Its build.sh lines 34-35 clones Rust ref solana-tools-v1.37 and writes the resolved revision to version.md; line 69 copies that receipt into the release archive. That Rust ref currently resolves to `764ce69bd00903f5c59f44b6aa72649b173f568c`; the exact commit's src/llvm-project Gitlink is `7b8db05b564faffb522434b73b7082662171f94a`.

All downloaded files, immutable URLs, exact raw sizes and SHA-256 hashes are in audit.json. Raw API responses refs/rust-revision.json, refs/llvm-gitlink.json, and refs/platform-revision.json preserve the observed ref resolution. The following ranges refer to that exact LLVM Gitlink:

* SBFInstrInfo.cpp 164-217: analyzeBranch handles unconditional JMP but rejects conditional branches at 213-214. SBFInstrInfo.h 23-65 does not override reverseBranchCondition.
* MachineBlockPlacement.cpp 2684-2715: unanalysable fallthrough blocks are merged into a chain to retain their adjacency. Lines 2832-2842 skip terminator updates when branch analysis fails; lines 2862-2868 gate the generic conditional reversal behind successful analysis.
* SelectionDAGBuilder.cpp 2359-2454 routes ordinary conditional branches through visitSwitchCase. Lines 2527-2532 swap true/false successors and complement the condition when the true successor is the next block. Lines 2535-2543 emit the conditional and explicit false branches for subsequent DAG optimization.
* SBFISelLowering.cpp 776-803 swaps operands for unsigned < and <= (also signed forms), conditional on !getHasJmpExt(). SBFInstrInfo.td 236-243 maps the resulting unsigned > and >= conditions to JUGT/JUGE. This can explain the observed complementary opcode plus register reversal; it does not establish the actual subtarget or trace.
* SBFTargetMachine.cpp 178-182 still installs a target pre-emit peephole. Whole-chain placement also remains possible. Therefore this audit rules out the shown generic conditional-reversal path, not every later transformation.

Candidate11's retained tool receipt identifies rustc SHA-256 `7194df9c12e893cfa88fff5dd821d02d45910b4d375e13677b4723f45769a384`, selected path `/root/.cache/solana/v1.37/platform-tools/rust/bin/rustc`, rustc 1.68.0-dev and LLVM 15.0.7. It explicitly reports unknown compiler commit. It does not retain archive version.md, the loaded LLVM library hash, selected target CPU/features, or optimized IR / machine IR. Current public ref resolution alone does not bind the downloaded source to that historical binary. The original deployment compiler identity is additionally unknown.

## Smallest next evidence check - proposed, not executed

1. In the exact existing image `solanafoundation/solana-verifiable-build@sha256:43206149a565ec35da95b1a909f4714f5d5f0d8241c31df24189e517acd18467`, read and retain the actual platform archive version.md, selected rustc hash, loaded LLVM library hash, cargo-build-sbf command/version, and resulting rustc target CPU/features. Resolve the recorded Rust commit's LLVM Gitlink. If these disagree with the source map here, stop this attribution and inspect the recorded revision; do not change toolchain.
2. Reproduce unchanged candidate11 source/lockfile and exact image/tool inputs once with diagnostic capture only. Capture optimized Utilize LLVM IR with block order/branch metadata, post-instruction-selection machine IR, and post-block-placement machine IR; retain actual commands, all logs and exits. Determine supported trace switches from that compiler before preparing the reviewed command. No optimizing flag, source, path, dependency, or version variants. A trace switch is an observation request, not a proposed recovery input.
3. Require raw stripped output SHA-256 `3bbaf27ff0c10ff68d8a195a82f39eadee266f324067bd0a66081710be30b4ec` and length 707,448 before calling the trace candidate11 evidence. Do not compare with rebuilt.deployed.so, whose extra 86,543 zeros represent allocation padding. A mismatch is a failed diagnostic reproduction; retain it unchanged and do not interpret its IR as the accepted candidate's trace.
4. Locate the remaining/requested comparison and error/success successors. Check whether the JGT orientation exists immediately after selection and is preserved through placement; inspect earlier IR order only if the trace supports that boundary. If orientation changes later, identify the first actual pass before proposing source changes. Stop after that one causal discriminator. No source trial follows automatically, and this observation cannot itself recover historical source.

Even a successful diagnostic reproduction leaves 30 diagnostic-coordinate bytes and two relocation bytes, plus the original allocation distinction, in the existing identity accounting. It is not a recovered executable or byte-identity improvement.

## Verify this audit

From the repository root, using Python 3.12 or later:

```sh
python repro/metaplex/branch-selection-audit/verify.py
python -m unittest discover -s repro/metaplex/branch-selection-audit -p test_verify.py
```

The default offline checker validates retained excerpts and their seals, saved raw guards, prior 11=14 / 12=13 output pairs, candidate14's sole source substitution, and the historical compiler receipt's explicit unknown commit. Sparse checkouts can read missing historical inputs by their pinned Git blob IDs. Offline verification of the retained excerpts does not independently authenticate their full upstream files or establish compiler behavior.

Optionally verify full upstream source bytes and reproduce the excerpt ranges:

```sh
python repro/metaplex/branch-selection-audit/verify.py --compiler-sources /tmp/metaplex-compiler-sources --fetch
```

This downloads only immutable public source text into the caller's cache and validates its full hashes and cited line ranges. It never executes downloaded code or runs a compiler/VM. Omit --fetch to validate an existing full-source cache offline. Hashing compiler source does not prove its semantics or bind the deployed compiler; the source interpretation requires review.

## Upstream excerpt attribution

Files under excerpts/ preserve exact contiguous upstream source bytes. Their original file paths, immutable URLs, full-file hashes/sizes, and excerpt bounds/hashes are in audit.json. LLVM source is from the Solana LLVM fork of the LLVM Project, under the [Apache License 2.0 with LLVM exceptions](https://github.com/solana-labs/llvm-project/blob/7b8db05b564faffb522434b73b7082662171f94a/llvm/LICENSE.TXT). The two build-script excerpts come from [Solana platform-tools](https://github.com/solana-labs/platform-tools/blob/390112a3f6d25e17662e83bf73d73f3d483b556e/build.sh). These source excerpts serve this static review; they are not executable build inputs or recovered Metaplex source.

Source URLs are revision-pinned in audit.json. The main mechanisms can be read directly in [SBFInstrInfo.cpp](https://github.com/solana-labs/llvm-project/blob/7b8db05b564faffb522434b73b7082662171f94a/llvm/lib/Target/SBF/SBFInstrInfo.cpp#L164-L217), [MachineBlockPlacement.cpp](https://github.com/solana-labs/llvm-project/blob/7b8db05b564faffb522434b73b7082662171f94a/llvm/lib/CodeGen/MachineBlockPlacement.cpp#L2684-L2715), [SelectionDAGBuilder.cpp](https://github.com/solana-labs/llvm-project/blob/7b8db05b564faffb522434b73b7082662171f94a/llvm/lib/CodeGen/SelectionDAG/SelectionDAGBuilder.cpp#L2527-L2543), and [SBFISelLowering.cpp](https://github.com/solana-labs/llvm-project/blob/7b8db05b564faffb522434b73b7082662171f94a/llvm/lib/Target/SBF/SBFISelLowering.cpp#L776-L803).
