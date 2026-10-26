# Pump extension diagnostics: source proposal and controlled experiment

**Planned, not yet built or executed.** Selected Pump `71ec4d8a…` silently returns
when an account already meets its target size. The captured original logs
`Account already has the correct size` on equality and
`Account already has more than {target} bytes: {current}` on excess.
`source.patch` restores those two messages in `extend.rs`, preserving the
existing growth path, target sizes, account requirements and error behavior.
Production source, selected artifacts and historical receipts are unchanged.

The original 1,272-byte instruction wrapper begins with a relocated
`Instruction: ExtendAccount` log and calls the retained 5,240-byte body at
1228824 -> 243928. In that body, current length is saved at frame-600 and target
length at frame-592. Equality at244768 selects the literal; unsigned greater-than
at244776 selects formatting; smaller accounts continue at245480. The oversized
format record contains the exact two string fragments and orders its arguments
target then current. Both messages reach the relocated `sol_log_` call at245032.
Complete body/helper/window bytes and data are retained as analysis inputs.
Their boundaries are inferred call windows, not claimed historical debug data.

The selected immutable extension suite has 308 original/candidate pairs. Its
saved state/error/event/CPI/return comparisons agree and all 1,208 raw signature
slots verify. Full logs expose the omitted messages. The separately retained
Surfpool receipt has 16 rows per binary and 62 valid raw signature slots; its
BondingCurve 166 and 200 cases directly show both missing diagnostics. Those
two cases retain unchanged target states; the saved state comparison excludes
only the different loaded Pump executable hash/length. No source-coordinate
normalization was used to identify this difference.

`inputs/receipt-provenance.json` connects every retained receipt to its exact
published `runtime-repository.tar.gz` member. The complete prior layout/member
manifests are losslessly compressed. The original archive SHA256 is
`bd21f6f02605481390a1f912f26e1397ecffca4eeeb1b2e705675f83404ee9b7`.
Both retained gzip and decompressed raw identities are recorded. A fixed input
seal prevents rewriting the receipts and their expected hashes together.
The same provenance record identifies the exact selected main build-attempt
and gate-before paths, raw lengths and raw/retained hashes.

The proposed hosted experiment builds unchanged and corrected source separately.
Both use the selected 37 source/lock inputs and release profile, official Linux
platform-tools v1.44, the selected 53 SDK bytes, Agave 2.1.21 frontend and recorded
v1.52 stripping phase. The SDK is stored under the AMM evidence directory, but
its complete hash map equals the selected Pump gate; no AMM source is compiled.
The shared authenticated download/registry helpers are pinned. Fresh source,
HOME, Cargo, rustup and target directories reject unrecorded source additions
and ancestor Cargo configurations. Genuine fetched registry views are copied
only as explicitly recorded by the existing helper. No source remapping,
compiler patch, metadata fabrication or flag search is proposed.

The Linux unchanged-source output is a new baseline: it need not equal the
selected Darwin executable. Both actual output hashes and full raw comparisons
will be measured. Original binaries never enter compiler source trees. Actual
compiler failure records and any produced output are retained before acceptance
gates. Runtime happens only after both builds pass. Twelve focused cases cover
growth, equality and excess for each of four account types. The full-log check
excludes only compute-use lines; the original's eight no-growth messages must
be absent in Linux baseline and present in corrected output. Complete raw
transactions, privileges, payloads, committed effects, CPIs and events are
checked. Each pair must contain identical raw transaction bytes; the unique
transaction count is reported separately from repeated fixture executions.
Signed bytes, case and side are checkpointed before the target send, including
when that send raises. The unchanged 308-case inherited extension suite then runs
on corrected output. Partial probe results survive failure. Ten mutation tests
run against the actual successful receipts; pre-build discovery explicitly
skips that class. These are finite diagnostic
checks, not whole-byte identity, exhaustive equivalence or historical uploader
recipe recovery.

Parallel upstream [PR43](https://github.com/lalalune/pumpfun-source/pull/43)
reports a Linux build using a different wrapper/host recipe. This proposal
does not claim the first Linux Pump build or adopt that reported output hash;
its paired outputs will be measured independently with the selected recipe.

Offline prerequisite checks (Python 3.12, `solders==0.27.1`, `pyelftools==0.32`):

```sh
python3 -B repro/pump/extend-diagnostics/verify_evidence.py
python3 -B -m unittest discover -s repro/pump/extend-diagnostics -p 'test_*.py'
```

Only after independent review, on isolated Linux x86_64 with Rust 1.94.0 installed:

```sh
python3 -B repro/pump/extend-diagnostics/linux_build.py --repo "$PWD" --output /tmp/pump-extend
```

Retain `/tmp/pump-extend/evidence` even on failure. The driver records actual
commands, tools, source snapshots and executed helper/input copies. Tooling
inputs are rehashed at final acceptance. Existing
selected evidence is checked read-only; the verifier performs no VM or build.
No successful source-build or runtime result is claimed by this proposal.
