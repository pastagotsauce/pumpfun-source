# Planned compiler-image observation

This prerequisite to the branch-selection audit inspects the exact recorded
Linux image without mounting source or captured binaries. It first requires
candidate 11's recorded rustc hash, then retains the archive revision receipt,
dynamic-library paths and hashes, and the tool's own capability/help output.
Available target CPUs and target-spec defaults do not identify the arguments
used for the earlier build. A missing or different compiler stops attribution.

The container has no network, host mounts or persistent writes. No compilation,
program replay, source change or optimization experiment occurs. Failure logs
and all command exits remain evidence. Optional inspection failures remain
explicit and cannot establish a missing revision or library binding.

Run on Linux x86_64 with Docker:

```sh
python3 repro/metaplex/compiler-image-observation/observe.py --output /tmp/metaplex-compiler-observation
```

The output must be new. Retain its `evidence` directory even if inspection fails.
No observation has been executed for this package yet.
