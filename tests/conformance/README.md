# WOLS conformance vectors

`test_vectors.py` runs every case in `vectors/` through the public `wols` API.
`MUST` cases must pass. A failing `SHOULD` case is reported as `xfail`.

## Source

The files in `vectors/` are copied unmodified from
[wemush/open-standard](https://github.com/wemush/open-standard/tree/main/conformance):

| Field | Value |
| ----- | ----- |
| Tag | `1.3.0-rc.2` |
| Commit | `9d200c959e78188a6b6a8828b51337f1afc1717a` |
| Path | `conformance/vectors/{embedded,primordia,generation,encrypted,field-encryption}.json` and `SHA256SUMS` |

`vectors/SHA256SUMS` is copied from upstream too. Check the vendored files
with:

```bash
cd tests/conformance/vectors && shasum -a 256 -c SHA256SUMS
```

## How operations map to the API

| Operation | Call |
| --------- | ---- |
| `validate` | `validate_specimen(input)`. `errorField` and `warningField` are matched against `ValidationError.path`. |
| `create` | `create_specimen(**input)`. The warning is a `WolsWarning`. |
| `derive` | `wols.crypto.derive_key(passphrase, salt, iterations)` |
| `decrypt` | `wols.crypto.decrypt_specimen_bytes(url, secret)` (exact plaintext) and `decrypt_specimen(url, secret)`. A failure's `reason` must equal the `WolsEncryptionError.code`, upper-cased with `_` (for example, `id-mismatch` becomes `ID_MISMATCH`). |
| `decryptFields` | `wols.crypto.decrypt_specimen_fields(specimen, secret)`, compared with `expected.specimen`. Failure reasons map to codes as for `decrypt`. |

## Refreshing

```bash
TAG=1.3.0  # or another tag or commit of wemush/open-standard
git clone https://github.com/wemush/open-standard.git /tmp/open-standard
git -C /tmp/open-standard checkout "$TAG"
cp /tmp/open-standard/conformance/vectors/{*.json,SHA256SUMS} tests/conformance/vectors/
git -C /tmp/open-standard rev-parse HEAD   # record in the table above
(cd tests/conformance/vectors && shasum -a 256 -c SHA256SUMS)
uv run pytest tests/conformance -v
```

Then update the tag and commit above. If upstream adds a vector file, add
its name to `VECTOR_FILES` in `test_vectors.py`.
