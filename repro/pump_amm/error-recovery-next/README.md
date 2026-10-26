# AMM liquidity self-transfer error recovery

The selected AMM candidate adds compared-public-key diagnostics that the original
does not emit when a nonzero deposit aliases its base or quote token account to
the corresponding pool vault. Both return `SelfTransferNotAllowed` (6087).

The existing 680-case liquidity receipt contains four affected cases (rows 223,
224, 226 and 227). Its comparator deliberately excludes all logs. The old zero
mismatch count therefore does not establish error-diagnostic equality. This
package authenticates that receipt and checks the previously untested difference;
it does not rewrite the historical result.

`source.patch` proposes replacing **only** the liquidity helper's
`require_keys_eq!` with the equivalent `require!(owner == expected_authority, ...)`.
The predicate, error code and real current source location remain intact. No
historical source coordinate is fabricated. Other transfer helpers and sweep
instructions are outside this patch.

## Original-byte evidence

`original-guard.asm` retains the complete 656-byte window `[456200, 456856)` from
the imported AMM disassembly. The verifier checks every byte against the pinned
original, including all 16-byte immediate instructions. The two 32-byte comparison
calls have the same numeric target; their success exits bypass error construction.
The error path stores 6087 at `456736`, the observed source line 21 at `456752`,
and references the exact `programs/pump-amm/src/utils/token.rs` string.

This supports the narrow guard/error attribution together with the retained
runtime logs. It does not prove the unknown callees, allocator/drop behavior,
historical Rust source, or all possible inputs.

## Verification

From the repository root:

```sh
python -B repro/pump_amm/error-recovery-next/verify.py
python -B repro/pump_amm/error-recovery-next/test_verify.py
```

These are saved-evidence checks, requiring no compiler or VM. The original
receipt is read from its existing publication path; it is not duplicated here.

`runtime_probe.py` accepts `--candidate`, `--candidate-sha256`, `--expect baseline`,
`--expect rebuilt-baseline` or `--expect corrected`, and a new `--output` path.
The selected-baseline mode requires the published `09be` hash; rebuilt-baseline
requires a successful unchanged-source `--build-record` binding instead. It runs 18 synthetic cases
using the existing signed local harness: base/quote aliases, zero/nonzero amounts,
deposit rejection, successful withdrawal, and a withdrawal with an incorrect
token authority. It retains full raw logs and every signed transaction, and
checks all existing account, CPI and error observations. Only compute-use lines
and the 6087 source coordinate are normalized for log comparison. The underlying
fixture disables transaction history; this is neither historical-bank replay
nor a production transaction.

The probe needs a Linux `solders` wheel with LiteSVM. The Windows 0.27.1 wheel
installed during investigation lacks the required `FeatureSet` binding, so the
Windows attempt executed no program.

The first Linux pair built successfully, then its baseline probe failed its own
expectation for the one-LP quote withdrawal with a wrong token authority. The
original and baseline both succeeded: the pinned fixture has quote reserve
122,946,690,720 and LP supply 4,194,352,106,721, so that withdrawal rounds the quote
transfer down to zero. The guard is skipped for zero transfer quantity. Its
original receipt contains a 160-unit base transfer, a one-LP burn and no quote
transfer. The failed attempt remains failed; it is not rewritten as a pass.

The corrected probe derives each aliased transfer quantity from the pinned
fixture, using deposit ceiling and withdrawal floor before checking the guard.
It requires seven rejections and eleven successful controls, including the zero
quote transfer. Regression tests distinguish that case from base withdrawal,
larger quote withdrawal and the corresponding deposit.

After an actual successful replay, `verify_runtime.py` and
`test_verify_runtime.py` accept `--report`, `--candidate`, `--build-record` and
optional `--repo`. The standalone checker recomputes all 18 case dispositions,
effect and log comparisons, artifact/source bindings and Ed25519 verification
from raw signed transaction bytes. It checks the complete signed instruction
payload and account routing, distinguishes repeated messages, and rejects any
receipt whose producer recorded a failure. It does not execute the VM or turn
saved signatures into proof of exhaustive state coverage.

## Isolated Linux experiment

`linux_build.py --repo . --output <new-directory>` requires Linux x86_64,
Python 3.12 with the repository requirements, and an installed Rust 1.94.0 host
toolchain. It downloads the hash-pinned official v1.44 compiler, v1.52 stripping
tools, Agave 2.1.21 CLI and Criterion 2.3.3 archives already recorded by the
repository. After a locked public dependency fetch it authenticates the archives
and extracted sources, then copies those same bytes into both observed Cargo
registry namespaces. It fabricates no dependency files or installation markers.

The baseline and one-line proposal build in distinct source, target, SDK and
Rustup directories. The 53 recorded SDK files retain their bytes; five scripts
receive explicit executable-mode preparation, which is recorded as part of this
Linux experiment rather than claimed as historical mode recovery. The driver
retains actual command exits/logs, source manifests, stripped/unstripped outputs,
whole-original comparisons and candidate-bound focused runtime receipts. Known
partial compiler outputs are preserved on failure, without acceptance or copying
generated keypairs. The corrected build also runs the inherited 680-case liquidity
suite; that suite's full-log exclusion remains explicit.

Linux baseline identity with the selected Darwin output is measured, never
assumed. A passing Linux pair demonstrates the bounded source correction under
that recipe; it does not promote the selected artifact or recover the original
historical compiler recipe. Large downloaded public archives live under
`evidence/downloads`; their URLs, hashes, lengths and verification results are also
retained in `attempt.json` if a CI artifact excludes the archives themselves.

## Status

Saved-evidence verification and mutation tests are local checks. The patch is a
proposal until a source build and candidate-bound runtime validation are retained.
The selected source/artifact, global counts and historical packages are unchanged.
No raw binary byte reduction or whole-file equality is claimed by this finding.
