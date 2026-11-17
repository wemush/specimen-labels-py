# WOLS conformance vectors

`test_vectors.py` runs every case in `vectors/` through the public `wols` API.
`MUST` cases must pass. A failing `SHOULD` case is reported as `xfail`.

## Source

The files in `vectors/` are copied unmodified from
[wemush/open-standard](https://github.com/wemush/open-standard/tree/main/conformance):

| Field | Value |
| ----- | ----- |
| Version | `1.4.0-rc.1` (release candidate, [open-standard#24](https://github.com/wemush/open-standard/pull/24), stacked on `1.3.1-rc.1`) |
| Commit | `8e02ecaa9a0552d444b14d061dc5998b275f9188` |
| Path | `conformance/vectors/{embedded,primordia,generation,encrypted,field-encryption,signatures}.json` and `SHA256SUMS` |

`1.4.0-rc.1` leaves the earlier cases unchanged and adds `signatures.json`,
plus `decrypt-with-sig` and `decrypt-signed-url` in `encrypted.json` and
`signed-label-valid` in `embedded.json`. Replace the commit with the `1.4.0`
tag once the specification is accepted.

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
| `sign` | `wols.crypto.sign_specimen(label, seed, kid)` or `sign_encrypted_url(url, seed, kid)`, with the seed from `testKeys`. The token must match exactly. `signingInput` is checked with `wols.crypto.jcs.canonicalize`. A `refused` case must raise `WolsSignatureError`. |
| `verify` | `wols.crypto.verify_specimen(label_or_url, trust_store)`, and also `verify_embedded` or `verify_encrypted_url`, against `input.trustStore` or else the file's `trustStore`. The status must match; for `valid`, so must the kid. For a `configError` case, building the `TrustedKey` must raise `WolsTrustStoreError`, and verifying with the unchecked entry must give `invalid`. |

For `decrypt` cases with `sig`, the test also checks that
`parse_encrypted_url(url).signature` keeps the token unchanged and that
`to_url()` rebuilds the URL byte for byte.

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
