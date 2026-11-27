# WOLS conformance vectors

`test_vectors.py` runs every case in `vectors/` through the public `wols` API.
`MUST` cases must pass. A failing `SHOULD` case is reported as `xfail`.

## Source

The files in `vectors/` are copied unmodified from
[wemush/open-standard](https://github.com/wemush/open-standard/tree/main/conformance):

| Field | Value |
| ----- | ----- |
| Version | `1.4.0` (final, [open-standard#29](https://github.com/wemush/open-standard/pull/29)), plus the sign-then-encrypt cases |
| Commit | `4b9235e3f3371b424718dcfe506bad2abe2f9241` (`main`, open-standard PR #30) |
| Path | `conformance/vectors/{embedded,primordia,generation,encrypted,field-encryption,signatures}.json` and `SHA256SUMS` |

`1.4.0` leaves the 1.3.0 cases unchanged and adds `signatures.json`,
plus `decrypt-with-sig` and `decrypt-signed-url` in `encrypted.json` and
`signed-label-valid` in `embedded.json`. `signatures.json` includes the
`loadKeySet` cases from open-standard#26. open-standard#27 adds three `SHOULD`
cases for an integer `strain.generation` (`generation-numeric`,
`decrypt-numeric-generation`, `decrypt-fields-numeric-generation`), which this
library passes. The final `1.4.0` specification leaves every vector file
byte-identical to the `1.4.0-rc.1` copies from `a44dd3a`.

`signatures.json` is vendored from open-standard `main` at `4b9235e`
(PR #30), which adds the sign-then-encrypt cases on top of `02079df`: six
`verifyNested` cases and `sign-nested-encrypted-url`, for 119 cases. The other
vector files are byte-identical to the `02079df` copies.

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
| `verifyNested` | Sign-then-encrypt. `verify_specimen(url, trust_store)` (and `verify_encrypted_url`) for `outer`; `decrypt_specimen_bytes(url, secret)` for the exact `plaintext`, and `decrypt_specimen`; then `verify_specimen` (and `verify_embedded`) on the decrypted text as received for `inner`. Each layer's status, and for `valid` its kid and signing input, must match. A failed decryption's `reason` maps to a code as for `decrypt`, and has no `inner`. |
| `loadKeySet` | `wols.crypto.trust_store_from_key_set(document, on_skip=...)`, with the document both parsed and as JSON text. A `configError` case must raise `WolsTrustStoreError`. Otherwise the sorted kids must equal `kids`, `on_skip` must be called `skipped` times, and `verify_specimen(label, store)` must give `status` (and `kid` for `valid`). |

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
