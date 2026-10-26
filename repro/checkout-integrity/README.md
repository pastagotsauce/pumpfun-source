# Clone without changing evidence bytes

Clone this repository with line-ending conversion disabled in its local Git configuration:

```sh
git clone --config core.autocrlf=false https://github.com/lalalune/pumpfun-source.git
cd pumpfun-source
python scripts/verify_evidence.py
```

The clone option applies before checkout and persists in this clone's `.git/config`.
It overrides a Windows/global `core.autocrlf=true` setting without changing other
repositories. Both LF and authentic CRLF receipts stay byte-identical to their
Git blobs. Do not force `eol=lf`, which can rewrite authentic CRLF receipts.

For an existing clone, `git config --local core.autocrlf false` prevents future
conversion, but does **not** repair files already converted in the working tree.
Preserve local edits before refreshing tracked files, or use a fresh clone with
the command above. Do not rewrite evidence manifests to accept converted bytes.

## Reproduced failure and check

A fresh Windows checkout using `core.autocrlf=true` converted the three upstream
JSON receipts to CRLF. `scripts/verify_evidence.py` then failed before checking
any captured program, although the Git blobs still matched their recorded hashes.
Restoring exact Git bytes made all nine capture checks pass.

```sh
python -B repro/checkout-integrity/test_checkout_bytes.py
python scripts/verify_evidence.py
python scripts/test_tooling.py
```

The standard-library regression creates temporary Git repositories and uses real
checkout and staging. It verifies the local `false` setting against inherited
`true`, `input` and `false` settings, with LF, CRLF, mixed-ending and binary
fixtures. It also reproduces the conversion failure and the forced-LF limitation.

The repository's root `.gitattributes` is sealed by the current integrity proof.
It remains unchanged, as do all historical evidence, program source, selected
artifacts, manifests and root script/workflow sets. This package documents and
tests clone setup; it does not automatically configure other clones or add a
compiled candidate or byte-identity claim.
