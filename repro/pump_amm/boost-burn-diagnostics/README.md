# Draft: restore five boost/burn numeric error diagnostics

**Unbuilt and unexecuted proposal.** This package changes five source guards to restore numeric values present in the captured original program's errors. Static evidence and preflight checks pass. No new compiler output, runtime receipt, runtime acceptance or selected-artifact change exists. The commands below describe pending validation, not completed work.

The source proposal builds on the authenticated liquidity/sweep/migration candidate `7f6c301e7d39ced26a6280ae1053db6cff76a01c67dd9c4627e6022cb8384d52` from [the creator correction](../creator-fee-diagnostics/README.md). Its retained build-record SHA-256 is `ac14e9f4477466fce3705aa6d621a965bef9a8fc6f957bab26a902b0947e65e3`. All 30 source files and the prior three changed source files are authenticated before copying them into an isolated build directory.

Only `programs/pump-amm/src/boost_burn.rs` changes. Its prior hash is `92310c452df7fa7352dde64f64aaf616a6857af61732aee017c5149affbe40d4`; the proposed hash is `fd74007543769bc7dd27a23f018cc756f20056db6acb7e5cec29cc2df054b148`. The patch preserves each predicate, error and operand order. It replaces `require!` with `require_gt!` for `used > 0`, `net > 0`, `burned > 0`, and `old_base > burned`, and with `require_gte!` for `burned >= minimum`. It adds no line padding, invented coordinates, arithmetic changes or binary edits.

## Existing evidence

The original ELF is SHA-256 `6a7ad34596d83b4c435b32f458a56e718e9f82eb4ad38e4316616d15d24d8ff7`. The existing selected-candidate receipt at `repro/pump_amm/owner6048-v144/runtime/runtime-01/boost_burn.json.gz` has compressed SHA-256 `03aa0b2865bd81ba3d51d5d0e7296bb682d898725b2f0406e47d18b840ef1e9c` and raw SHA-256 `1d703b5cbc445448f3b92e4e16aaa9cf57bcdfb3155f604cbe7752c8f80e6a69`. It compares the original with selected Darwin candidate `09bee0dfd751dc6ae0240bbac262933c6bda6e0c94aa643f82c57f2956c3a117`, not the proposed new build.

Independent re-verification covers all 506 historical pairs: identical signed input bytes and non-log effects, 1,018 valid signature fields, and 125 unique signed transactions. Exactly 77 rows contain numeric Left/Right lines in the original that are absent in that historical candidate. For those 77 rows, full logs otherwise agree after excluding compute lines and mapping each exact original/reconstructed source-coordinate pair. The two zero-quote sites retain distinct identities; normalization cannot turn an error at the first gate into one at the second. No dependency was invoked on those rejected paths.

| Original site | Predicate | Witness rows | Absolute guard and destination |
|---|---|---:|---|
| `boost.rs:250` | `used > 0` | 4 | `0x20018 -> 0x20590` on zero |
| `boost.rs:255` | `net > 0` | 16 | `0x20a60 -> 0x20ab0` on zero |
| `boost.rs:273` | `burned > 0` | 38 | `0x20cb0 -> 0x20df0` on zero |
| `boost.rs:274` | `burned >= minimum` | 16 | `0x20cc0 -> 0x20cd0` on unsigned less-than |
| `boost.rs:280` | `old_base > burned` | 3 | `0x20ef0 -> 0x20f00` on success; otherwise `0x20ef8 -> 0x21600` |

The 2,136 retained instruction bytes in `original-boost-guards.asm` are checked against the original ELF. Calls at `0x20940`, `0x20b88`, and `0x20ec8` reach the zero-value helper at `0x340`. The two variable-value calls at `0x20dc0` and `0x216e8` reach `0x1840`, with left/right passed in `r4`/`r5`: burned/minimum and old-base/burned respectively. Original source-line and error-number construction are separately checked. The branch at `0x20648 -> 0x20858` is later error formatting, not the used-amount predicate.

Listed addresses are absolute ELF addresses/file offsets. The imported disassembly's angle-bracket `.text+...` labels are section-relative, with `.text` starting at `0x120`. Branch destinations are recomputed from signed instruction offsets; comments are not mistaken for absolute addresses.

## Checks completed

```sh
python repro/pump_amm/boost-burn-diagnostics/verify_evidence.py
python -m unittest discover -s repro/pump_amm/boost-burn-diagnostics -p 'test_*.py' -v
```

Ten static tests pass. They cover the five-only source change, actual patch application exactly once, original operands/branches, historical signatures/effects, preservation of zero-gate identity, fixture-state binding, signed arguments/signatures and the exact slippage equality boundary. Fifteen planned classifications can be checked using existing historical before-state snapshots; that is a static check, not a new execution of those cases. The newly specified greater-than-liquidity success control still requires actual execution.

`test_runtime_boost.py` contains sixteen tests for a future real receipt. They are deliberately not run by preflight discovery, and none has passed against a new boost candidate yet.

## Pending single-build experiment

The unexecuted `linux_build.py` preserves the prior pinned Linux recipe: platform-tools v1.44 compilation, v1.52 stripping, Agave 2.1.21 CLI, Criterion 2.3.3, host Rust 1.94.0, the recorded 53-file SDK, authenticated locked registry inputs and explicit Linux script executable modes. Patches apply with `core.autocrlf=false`, preserving exact source bytes independently of host Git defaults. Source/lock hashes, archive/member hashes, before/after input manifests, command logs, actual exits, current Git revision and executed helper hashes are retained. Partial stripped/unstripped ELF outputs are retained before enforcing acceptance; generated keypair contents are never read or copied. The original is a comparison input after compilation, never a compiler input.

The pending focused roster has 16 boost cases across original/prior-creator/new binaries: 11 rejected paths covering all five gates and five successes. Controls cover zero/clamped amounts, rounded/full transfer fees, exact slippage equality and its neighbors, gate precedence, full vault drain and base-reserve equality. The 36 previously established migration/sweep/liquidity cases run against original/new binaries. All 120 planned signed observations retain complete effects and full logs; the checker verifies raw signatures and signed account routes independently, exact result schemas, labelled before-state, original/prior/new outcomes, and the prior numeric omission. Only compute lines and the explicitly documented source-coordinate differences are excluded. Previous 6081/6074/6087 checks remain explicit; prior receipts and build records are not rewritten to impersonate the new four-file source manifest.

The inherited 506-case boost suite follows the focused run. Its complete account states, errors, event/CPI bytes, return data and raw transactions are compared, and all signature fields are re-verified. That inherited suite excludes full-log comparison; the focused cases enforce the diagnostic correction separately. The driver runs the sixteen real-receipt mutation tests only after the actual focused probe succeeds.

Executable identity follows the clarified finish line: compare the complete original ELF extent with the raw candidate's complete ELF bytes, and verify unused original allocation padding separately. `scripts/analyze.py` determines extent from the ELF header, program/section tables, program file extents and non-NOBITS sections. The driver requires the original suffix to be zero and the raw candidate to end exactly at its own complete ELF extent. `executable-comparison.json` retains separate executable and padding hashes/counts. Existing strict raw whole-file comparison records remain separate and unchanged. No `rstrip`, invented padding or candidate trimming is used.

After reviewing the exact hosted command and workflow, a future Linux x86_64 runner can resume with:

```sh
python repro/pump_amm/boost-burn-diagnostics/linux_build.py --repo "$PWD" --output "$RUNNER_TEMP/amm-boost-diagnostics"
```

The output directory must be new. Preserve any failed or partial attempt; do not relabel it as accepted. Resume with one build and the existing planned tests, then independently review actual outputs and receipts before claiming recovery or publishing a completed-results PR. This draft is not an executable-byte match or a completed diagnostic repair.
