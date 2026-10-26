# AMM migration creator-fee diagnostics

The recovered `migrate_pool_coin_creator` guard returns the correct error 6081
but adds numeric `Left:` and `Right:` values that the original does not log.
`source.patch` changes only that guard from `require_eq!(pool.creator_fees,0,...)`
to `require!(pool.creator_fees==0,...)`. The same predicate and error remain.
The identical-looking `admin_cto` guard is explicitly outside this correction.

This package builds on the authenticated liquidity/sweep output
`64d909213b9fe0fe9447e9204e470129c0eff8fcab1a50ae628fb6ec9256a069`, from
[run 40294311933](https://github.com/pastagotsauce/pumpfun-source/actions/runs/40294311933),
artifact `12637738214`, documented in `../sweep-error-observation/`. Its full
30-file source snapshot and build record (SHA-256
`cad21b8fd0e9ab05fc7e0664883eff40154632216cd54a2f3a10b22b09eab245`) are immutable
inputs. Production source, selected artifacts and earlier evidence are unchanged.
**The new compiled correction and runtime gates are pending.**

## Existing source evidence

Saved receipt `../owner6048-v144/runtime/runtime-01/creator_reassignment.json.gz`
has SHA-256 `ad5ca42a325cd366f7213db431a463629c687976ea2f1b21b9c95e15e069632d`;
its decompressed bytes have SHA-256
`c4d203a1e11a95b3f53dbcca186e61052e3cc1e932b0289e9dc4e79a77a50fdb`.
It contains 327 cases against original `6a7ad345…` and the selected Darwin
candidate `09bee0df…`. Rows 105 and 106 set the serialized pool creator-fee field
at bytes 279–286 to 1 and 2. Both return `CreatorFeesNotSwept` (6081), with equal
before/after accounts, events, CPIs and return data. Only the reconstructed
candidate adds `Left: 1` (or `2`) and `Right: 0` after the error.

Four raw signature fields verify independently; all four contain the same
signed message. They represent two fixture-state variations, not four distinct
transactions. The original error comes from the AMM itself, with no dependent
program invocation. The inherited comparator excludes logs, so its zero reported
mismatches did not detect this difference. The initial scan also found an
unrelated fee-config key difference caused by `Pubkey.new_unique()` creating
different signed inputs; that was excluded as an input difference, not patched.

Current `programs/pump-amm/src/creator_reassignment.rs:32` contains the relevant
`require_eq!`. Its source SHA-256 is
`59449c2174c08bc4d093488788c8921c0594303e9a79d74d2da91d99325e5965`.
The patch is anchored inside `migrate`, and `patched_source()` requires the
entire `admin_cto` suffix to remain byte-identical. The resulting file SHA-256 is
`1d9dd70a389a046d325a45a2523ae7637451262c4570d32f4f516da4d7de691a`.

`original-migrate-guard.asm` retains 464 checked original instruction bytes:

- `0x23e50` checks the holder-reward flag first. `0x23e60` loads the creator fee;
  its zero branch at `0x23e68` targets `0x24208` and bypasses the error block.
- `0x24188` loads the source-path literal at `0x11c875`:
  `programs/pump-amm/src/instructions/coin_creator/migrate_pool_coin_creator.rs`.
  `0x241a0` writes error 6081 and `0x241b0` writes original source line 59.
- Saved holder precedence control row 154 returns 6074 at original line 52.
  The new focused run separately checks this order before the fee guard.

## Reproduction and acceptance

Use a fresh Linux x86_64 host with Rust 1.94.0 and repository Python requirements:

```sh
.venv/bin/python -B repro/pump_amm/creator-fee-diagnostics/verify_evidence.py
.venv/bin/python -B -m unittest discover \
  -s repro/pump_amm/creator-fee-diagnostics -p 'test_*.py'
.venv/bin/python -B repro/pump_amm/creator-fee-diagnostics/linux_build.py \
  --repo . --output /absolute/new/attempt-directory
```

The driver performs one clean source build, using the same authenticated v1.44
compiler, recorded SDK, Agave 2.1.21 CLI, Criterion 2.3.3 and v1.52 strip tools.
The unchanged lockfile's public dependencies are authenticated before offline
compilation; authentic cache/source/index trees populate both Cargo namespaces.
No markers or source files are fabricated. Five SDK shell files receive the same
explicit executable-mode preparation as the earlier Linux experiment, with SDK
text checked before and after. Original binaries are comparison inputs after
compilation, never compiler inputs.

Required execution gates are:

1. Six signed migration cases against original, prior sweep output and new
   candidate: creator fees 0/1/2/u64::MAX with holder flag false, then fees 0/1
   with holder flag true. Expected results are one successful zero control,
   three 6081 rejections and two holder-precedence 6074 controls per binary.
   The actual before-account fee and holder bytes must match each case label.
2. The prior twelve sweep and eighteen liquidity focused cases run again against
   original and new output. The complete three-file cumulative source manifest
   is checked explicitly; no old receipt, build record or sealed validator is
   relabelled or changed to accept a different build.
3. All 327 inherited creator-reassignment cases retain equal errors, account
   state, CPIs, events and return data. This suite's full-log exclusion is explicit;
   the focused cases separately enforce the recovered diagnostics.
4. Twelve mutation/positive checks run against the actual new focused receipt.
   They reject missing effects, mislabeled account states, lost earlier fixes,
   returned numeric diagnostics, invalid signatures and incorrect build bindings.

The focused checker retains all raw logs. Its only exclusions are compute-use
lines and source coordinates for errors 6081, 6074 and the earlier 6087 recovery.
Error names/numbers/messages, numeric diagnostics, other logs and committed
effects remain strict. Expected total: 78 raw signature fields across six
migration comparisons and thirty previous focused comparisons. Unique signed
message count is reported from actual bytes, not inferred from case count.

Ten static evidence/signature/patch-scope tests currently pass. Fresh Linux
execution remains required. The driver retains source/input/tool manifests,
archive hashes, exact command logs/exits, both compiler outputs and failed
partial receipts. Generated keypair files are never read, hashed or copied.
This is bounded synthetic offline recovery, not historical replay, live
deployment, full path coverage or whole-binary identity.
