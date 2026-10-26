# AMM sweep diagnostics recovery

The original AMM binary emits two diagnostics that the reconstructed sweep
source does not reproduce: a plain `SelfTransferNotAllowed` error without key
values, and `Nothing to sweep for fee bucket 0` on an empty protocol fee bucket.
This package proposes exactly those two source corrections, layered onto the
previously validated liquidity correction. **The combined source build and all
bounded runtime gates passed in run 40294311933.** Production source and selected
artifacts remain unchanged; byte identity has not been achieved.

## Verified combined output

[Run 40294311933](https://github.com/pastagotsauce/pumpfun-source/actions/runs/40294311933)
at `ae32224a28824fbe2380af47b589b25077c6fa60` completed one source build and every
required check. Artifact `12637738214` (`amm-sweep-correction-40294311933-1`)
is 2,219,013 bytes with provider and independently downloaded ZIP SHA-256
`8bf5e369c06ba2c0438571a33a306a3e73fc2a815cdac38a7316cc7dca8c0428`.
All 68 archive members are retained exactly under `results/build/`, with large
JSON losslessly gzipped, plus three raw provider provenance records. The fixed
publication manifest SHA-256 is
`0ba49bbebbe894e3a0792234c4653d20ee8230f17f836d16e39f11b8095a0b8e`.

The combined stripped output is 1,200,560 bytes, SHA-256
`64d909213b9fe0fe9447e9204e470129c0eff8fcab1a50ae628fb6ec9256a069`.
Unstripped output SHA-256 is
`381ed5ee2a7ebcafdced903ed39f1d82439e830fa21321144e2849949f3e7f9a`.
The new snapshot retains all 30 source inputs. Only `sweep.rs` changed from the
prior liquidity-corrected source; Cargo.lock and the earlier `lib.rs` correction
are unchanged.

- Twelve focused sweep cases compare the original, prior liquidity output and
  combined output: two rejections and ten successful controls per binary. The combined
  output removes the extra key diagnostics and restores all four empty-bucket
  logs, including creator bucket 1. Every other full log and committed effect
  matches under the stated compute/source-coordinate exclusions.
- The unchanged 18-case liquidity probe passes: seven rejections, eleven
  successful controls, and the original full-log behavior preserved.
- Independent raw verification accepts 36 sweep signature fields (three unique
  signed messages) and 36 liquidity signature fields (twelve unique messages).
  These include repeated messages over separately prepared fixture states.
- All 254 inherited sweep cases and all 680 inherited liquidity cases pass their
  account/error/CPI/event comparisons. Their full-log exclusion remains explicit.
- All 11 actual-receipt mutation/positive tests passed on the runner and again
  against the downloaded receipts. The 14 observation/source/evidence tests pass.

The new output is 528 bytes larger than the prior liquidity output. Its original
comparison has 672,361 differing shared positions and a 9,285,155-byte allocation
gap; the sum of differing/missing positions is 427 larger than before. Thus this
is a demonstrated diagnostic recovery, **not a claim of improved positional
byte similarity**. Source/compiler reconstruction and allocation matching remain
unfinished. `verify_results.py` recomputes the exact byte comparisons and all
saved-receipt acceptance checks without compiling or executing SBF:

```sh
.venv/bin/python -B repro/pump_amm/sweep-error-observation/verify_results.py
```

## Observed evidence

[Run 40291256769](https://github.com/pastagotsauce/pumpfun-source/actions/runs/40291256769)
executed the unchanged `probe.py` at
`fb92040071948ef610e60542d784e5c2d7a15e64`. Artifact `12636451641`
(`amm-sweep-observation-40291256769-1`) has provider and downloaded ZIP SHA-256
`81aa55b595b44b4bda2ba237a2cb4c3ba8004cd643e4033cd41f1188c4da9460`.
Its two members are preserved under `observed/`; the large runtime JSON is
losslessly gzipped. `observed/manifest.json` binds raw and stored bytes, provider
run/job/artifact responses and the full source revision. Raw runtime SHA-256:
`546bf6998ff0c001c993fc9122feab5f1af63a48bad2532bfd23a5bb3ceb5182`.

All nine protocol sweep cases have equal errors, committed account states and
CPIs across the original, Linux baseline and liquidity-corrected Linux outputs:

- Ordinary recipient, pool alias with pool authority, pool alias with outsider
  authority; each with fee amount 0, 1 and 1000.
- Only outsider-authority aliases with amount 1 or 1000 reject with 6087. Both
  source-built outputs add four `Left:`/key/`Right:`/key lines; the original does
  not.
- All seven other cases succeed. The three zero-amount cases have the exact
  empty-bucket log only in the original. Other logs agree after excluding compute
  consumption and the intentional 6087 source-coordinate difference.
- Independent raw-message Ed25519 checks validate 27 signature fields, representing
  two unique signed messages. Amount/authority are fixture-state variations, not
  additional distinct signed payloads. All three binaries receive identical
  signed bytes per case; account routes and privileges are checked independently.

The previous compiler outputs came from
[build run 40286252822](https://github.com/pastagotsauce/pumpfun-source/actions/runs/40286252822),
artifact `12634605630`; their accepted runtime replay is
[run 40288855065](https://github.com/pastagotsauce/pumpfun-source/actions/runs/40288855065),
artifact `12634894210`. Exact evidence remains in `../error-recovery-next/`.
Linux baseline `cc2326ba…` and liquidity-corrected output `ec8aa1df…` differ from
the selected Darwin output `09bee0df…`; none equals original `6a7ad345…`.

## Original instruction correlation

`original-zero-branch.asm` retains exact bytes from the captured original:

- Entry `0x59408` saves fee-bucket argument r3 into r9. The amount helper at
  `0x6d128` chooses bucket offset `0x100` for zero or `0x108` for nonzero and
  returns the selected amount. The caller passes r9 at `0x59c28`.
- `0x59c58` branches on returned amount zero to `0x59e28`. That branch loads the
  formatting slice at `0x122580`, which relocates to the 32-byte literal at
  `0x11bdd0`, and stores the bucket as a byte at `0x59e88`.
- `0x59ee0` has an ELF relocation to `sol_log_`; the branch then returns success.
  This supports formatting a `u8` bucket in the existing zero-amount return.
  Creator bucket 1 additionally matches in the new actual execution.
- Rejected sweep logs identify `programs/pump-amm/src/utils/token.rs:21`, the
  shared original token-owner guard already retained in
  `../error-recovery-next/original-guard.asm`. The new source patch keeps the
  existing owner-equality predicate/error and changes only its macro decoration.

`verify_evidence.py` checks the excerpt bytes, exact branch target, literal/slice,
log relocation and hosted members. `source.patch` replaces only the sweep guard
macro and adds `msg!("Nothing to sweep for fee bucket {}", u8::from(creator))`
immediately before its existing zero-amount success return.

## One reproducible combined build

On a fresh Linux x86_64 host with Rust 1.94.0 and repository Python requirements:

```sh
.venv/bin/python -B repro/pump_amm/sweep-error-observation/test_recovery.py
.venv/bin/python -B repro/pump_amm/sweep-error-observation/linux_build.py \
  --repo . --output /absolute/new/attempt-directory
```

The driver copies the prior liquidity-corrected source, applies only
`source.patch`, and builds once with the same authenticated v1.44 compiler,
recorded SDK, Agave 2.1.21 CLI, Criterion 2.3.3 and v1.52 strip tools. It reuses
the existing generic registry helper to authenticate the unchanged lockfile's
public dependencies and copy their exact Cargo views into both registry
namespaces. No completion markers are fabricated. The five SDK shell scripts
get the same explicitly recorded executable-mode preparation as the previous
Linux experiment; SDK text is unchanged.

The old artifact omitted one hidden public `.cargo_vcs_info.json` (29/30 source
files). Only the new compile workspace adds that existing repository file after
checking its hash against the prior 30-file build record. This does not alter or
fill in the old artifact. The new complete source manifest, old/new source hashes,
tools, archives, command exits and logs are retained. Known partial stripped and
unstripped outputs survive failed builds with `accepted_build: false`; generated
keypair files are never read, hashed or copied. Original binaries are comparison
inputs after compilation, never compiler inputs.

The successful run enforces these acceptance gates:

1. Twelve focused sweeps against original, prior liquidity output and combined
   output: the observed nine protocol cases plus ordinary creator amounts 0/1/1000.
   Full corrected logs, signed bytes, errors, states and CPIs must match.
2. The unchanged prior 18-case liquidity probe must pass. `verify_liquidity.py`
   explicitly accepts the combined two-file source manifest and independently
   verifies all raw signatures and full logs; it never alters the new build
   record or the old sealed validator to impersonate an earlier build.
3. Actual-receipt mutation checks, all 254 inherited sweep cases and all 680
   inherited liquidity cases must pass. The inherited suites exclude full logs;
   that limitation remains explicit and is covered only by the focused cases.

`test_recovery.py` passes 14 observation/source/evidence checks; `test_runtime.py`
passes 11 checks against actual focused receipts. To rerun those mutation tests,
pass `--built /absolute/extracted-artifact/combined` to `test_runtime.py`. All
failed or partial attempts must remain intact. These are bounded synthetic local checks,
not historical transaction replay, full path coverage, live deployment or proof
of whole-binary identity.
