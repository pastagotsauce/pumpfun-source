# Recorded image failure and compiler-archive revision

The exact recorded image did not resolve candidate 11's cached compiler path.
[Run 40304340175](https://github.com/pastagotsauce/pumpfun-source/actions/runs/40304340175)
therefore stopped before executing rustc or querying its capabilities. The image
pull and inspection succeeded, the raw failed readlink status is retained, and
the container stopped successfully. This does not establish whether another
compiler path exists in the image. All seven provider artifact members remain
unchanged under `results/image-attempt/`.

Separately, a read-only inspection of the official Linux v1.37 release archive
found its 17,264-byte rustc entrypoint exactly matches the historical receipt's
SHA256 `7194df9c12e893cfa88fff5dd821d02d45910b4d375e13677b4723f45769a384`.
Its retained 249-byte `version.md` names Rust revision
`764ce69bd00903f5c59f44b6aa72649b173f568c`, matching the source examined in
[the branch-selection audit](../branch-selection-audit/README.md).
The archive is asset 101838771, 362,756,282 bytes, measured SHA256
`8d5153589dbe19635affe937663cf4555a7e69a62d91ab4a1df064aaa8d5f066`.
The publisher API supplies no digest; this is a locally measured archive hash.

The bundled 197,537,432-byte `librustc_driver-f767167903553d17.so` has observed
SHA256 `e7d221509c0d5f5430175547b6d972e300892258bfa6e1b0cf1c4058a73ad9f2`.
The historical receipt did not hash that loaded library, so matching the small
entrypoint does not establish the entire historical compiler. The prior target
CPU/features, actual compilation trace, and original deployment recipe also
remain unknown. No source build, VM replay, executable recovery or byte-identity
improvement was performed by this package.

Check the retained provider/log/source observations without execution:

```sh
python3 repro/metaplex/compiler-image-observation/verify.py
```

Optionally rehash the complete [official archive](https://github.com/anza-xyz/platform-tools/releases/download/v1.37/platform-tools-linux-x86_64.tar.bz2)
and stream its three selected members, without extracting or executing files:

```sh
python3 repro/metaplex/compiler-image-observation/verify.py --archive /path/to/platform-tools-linux-x86_64.tar.bz2
```

The original `observe.py` remains unchanged to preserve the failed attempt. It
requires Linux x86_64 and Docker; it uses a network-disabled, read-only container
without host mounts. Repeating that failed assumption is not the next experiment.
Any future diagnostic reproduction must first establish the installed archive,
loaded compiler and actual build arguments, then reproduce candidate 11's exact
707,448-byte compiler output before treating its traces as candidate evidence.
