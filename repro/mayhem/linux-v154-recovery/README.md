# Mayhem: one official Linux v1.54 distribution measurement

**Planned source build; no Linux candidate or runtime result is claimed yet.**
The selected Mayhem `ca5d4f54…` remains unchanged. This tests one observed
standard-library data discrepancy while preserving all fourteen source/lock
inputs, the supported `sbpf-solana-solana` target, release profile, ordinary
`-Zremap-cwd-prefix=` setting, and separate v1.52 strip phase.

## Concrete discriminator

The original ELF `a87fa9f8…` has a relocated LDDW at 632832 pointing to the
24-byte Location at 728816. That record points to 85 bytes at 707880, containing
`/home/runner/work/platform-tools/platform-tools/out/rust/library/alloc/src/string.rs`
and its retained terminal NUL, at line 2830, column 14.

The selected `ca5d4f54…` ErrorCode conversion has the corresponding relocated
instruction at 464840, Location at 558880, and 86-byte path at 540000. It names
`/Users/runner/…/alloc/src/string.rs` at the same coordinate. Both code and
Location pointers carry type-8 relocations. `locations.json` retains the raw
records. The data-pointer interpretation is the documented stored V0 high-word
representation; this static observation does not recover the historical loader
configuration or prove a runtime dereference.

The [official v1.54 Linux archive](https://github.com/anza-xyz/platform-tools/releases/tag/v1.54),
asset 368583779, was downloaded and checked against its publisher SHA256
`fcc41631c7f77561bf5412218bf297501dccf0305ea280f338f0ace2aab9f31e`
(520,154,357 bytes). Its `liballoc-91c82d13bc4939af.rlib` has SHA256
`781c60a5d9e28a72bca31f6b811591ef0ad1446fc4afab649534e6fe97de7c76`.
The original Linux path occurs once in its `lib.rmeta` member; the Darwin path
does not occur. Bundled `alloc/src/string.rs` contains the `Display::fmt`
`.expect(...)` at 2830:14. This is source/metadata evidence, not yet an emitted
Linux program Location match. The whole archive and selected member pins are
in `inputs.json`.

The falsifiable prediction is that compiling the unchanged source with this
official distribution emits the original **raw path bytes, length, line and
column** at this conversion site. The comparison includes the terminal NUL.
It does not predict complete Mayhem byte identity or recover a unique historical
compiler recipe. The seven unmatched admitted handlers and other source gaps
remain separate. No path replacement, invented source coordinate, ELF editing,
padding, compiler patch or flag search is used.

## Checks and execution

```sh
python3 -B repro/mayhem/linux-v154-recovery/verify_inputs.py
python3 -B -m unittest discover -s repro/mayhem/linux-v154-recovery -p 'test_*.py'
# Optional complete official archive/member recheck, without execution:
python3 -B repro/mayhem/linux-v154-recovery/verify_inputs.py --archive /path/to/platform-tools-linux-x86_64.tar.bz2
# One native Linux x86_64 build, with a fresh output outside the repository:
python3 -B repro/mayhem/linux-v154-recovery/run.py --repo "$PWD" --output /tmp/mayhem-linux-v154
```

Python 3.12 or later, a Linux x86_64 host with `/usr/bin/cc`, and public download
access are required. No host Rust installation is needed. The driver downloads
the pinned compiler and v1.52 stripper archives, copies only the fourteen
authenticated inputs, and gives Cargo a fresh home, fetch target and build
target. It rejects ambient ancestor Cargo configuration and altered source.
Every locked crate archive and extracted member is authenticated before and
after the single offline build. Tool distributions are also inventoried before
and after; exact commands, environment, versions and executing helper bytes are
retained. Clean explicit inputs and Cargo offline mode are measured; full
filesystem or OS network isolation is not claimed.

Upload only `OUTPUT/evidence/`, including on failure. Available compiler/strip
outputs are retained before checking exits or accepting the Location result.
Failed downloads retain partial-file measurements, and a failed compiler
retains its log and any emitted output. Source change status starts unknown and
is populated from actual measurements. Download archives, Cargo caches and
targets remain outside this evidence directory. No generated keypairs are
opened or included. The capture is first opened by the build driver after
compilation and is never copied into its source snapshot or passed as a compiler
input. The static preflight separately reads it to verify the stated hypothesis.

The final report compares complete raw output against the captured original and
selected Darwin output, binds stripped allocated sections to the unstripped ELF,
and locates the constructor through its fresh symbol table. A successful compile
with a negative Location prediction is retained as a measured negative. A
whole-file mismatch remains a mismatch; Mayhem's 1,992 zero allocation-tail bytes
are never added to the compiler output. No target program or VM is executed.

Thirteen compiler-free tests cover the actual source/pointer chain, malformed
ELF input, missing relocation, changed source/pins, extra/ancestor configuration,
truthful failed-output/source-change retention, existing-output refusal, raw
length mismatch and NUL-sensitive Location equality. These tests pass locally.

## Existing-work check

`upstream-check.json` records a bounded check of upstream main at `0b29240…`,
its Mayhem directory, recent commits and Mayhem/Linux search. The repository has
a separate older v1.52 Linux plan and several Darwin v1.54 experiments; no exact
fourteen-input Linux v1.54 execution was found in those checked records. This is
not a claim to have searched every private or unindexed branch. New upstream
restructure maps infer module placement and do not provide this measured build.
Fees Linux PR38 and Metaplex registry PR37 are separate work and are not repeated.
