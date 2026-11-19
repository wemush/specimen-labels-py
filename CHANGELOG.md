# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The conformance runner supports the `verifyNested` operation
  (sign-then-encrypt): it verifies an encrypted URL's `sig`, decrypts the URL
  to its exact plaintext, and verifies the plaintext's own `signature`.
  `signatures.json` is vendored from open-standard `a211697` (branch
  `conformance/sign-then-encrypt-vector`, not yet on `main`), which adds six
  `verifyNested` cases and `sign-nested-encrypted-url`; all 119 `MUST` cases
  pass. No library code changed.

## [1.4.0] - 2026-11-17

Implements the final WOLS 1.4.0 specification
([open-standard#29](https://github.com/wemush/open-standard/pull/29), commit
`02079df`). Every `MUST` and `SHOULD` case in the WOLS conformance vectors
passes, including all 112 `MUST` cases in `signatures.json`. Summary:

- **Signatures**: `sign_specimen`, `sign_encrypted_url`, and
  `verify_specimen` (Ed25519 over RFC 8785 JCS for embedded labels, over the
  exact URL bytes for encrypted URLs), with five verification statuses and
  keys taken only from a caller-supplied trust store.
- **Key sets**: `trust_store_from_key_set()` loads
  `/.well-known/wols-keys.json` documents and skips entries for algorithms it
  doesn't support.
- **Numeric `strain.generation`**: an integer is read as its decimal string,
  with a warning, and only the string is written.
- **`RawKey`**: an explicit 32-byte raw key type, so a base64 key string is
  no longer mistaken for a passphrase.
- **Migration guide**: a "Migrating from 1.2" README section, with its
  examples run as tests against real `wols` 1.2.0 output.
- **Interop**: CI round-trips encrypted labels with `@wemush/wols` across the
  shared 51-case matrix, in both directions.

WOLS 1.3.1 was not released separately. Its release candidate's
clarifications (a reserved, never-verified `sig`) ship as part of 1.4.0, and
1.3.0 already behaved that way, so there is no `wols` 1.3.1.

### Added

- `wols.crypto.RawKey(key)`: an explicit 32-byte raw key (`kdf=raw`). It
  takes 32 bytes, or standard base64 or base64url text (padding optional),
  and raises `WolsEncryptionError` (`INVALID_KEY`) for anything else. Every
  function that takes a secret accepts it, including with
  `allow_legacy=True`, and it behaves exactly like the 32 key bytes. Its
  `repr` hides the key. `Secret` is now `str | bytes | RawKey`.
- `strict_passphrase=False` keyword on `encrypt_specimen()` and
  `encrypt_specimen_fields()`. When true, a `str` secret that looks like a
  base64-encoded 32-byte key raises `INVALID_KEY` instead of emitting a
  `WolsWarning`. The default is unchanged.
- README: a "Migrating from 1.2" section (rollout order, recognizing and
  re-encrypting legacy labels, raw keys, and restoring strict ID checks),
  with its examples run as tests against real `wols` 1.2.0 output.
- **Signatures** (`wols[crypto]`): `wols.crypto.sign_specimen`,
  `sign_encrypted_url`, and `verify_specimen` (plus the form-specific
  `verify_embedded` and `verify_encrypted_url`). Ed25519 (RFC 8032), with
  `S ≥ L` rejected explicitly as well as by the backend. Embedded labels are
  signed as the RFC 8785 (JCS) canonical form of the label as parsed, without
  its top-level `signature`; encrypted URLs are signed byte for byte before
  `&sig=`.
- `VerificationResult` with a `SignatureStatus`, `kid`, and `reason`.
  Verification never raises for a bad signature. Checks run in the
  specification's order: the label text must be an I-JSON object, so it is
  `malformed`, signed or not, if it isn't JSON, isn't an object, repeats a
  member name at any depth (compared after unescaping), or holds a lone
  surrogate, `NaN`, `Infinity`, or an overflowing number; then `unsigned`;
  then the token and URL rules (`malformed`); then `unknown-kid`; then
  `invalid` or `valid`.
- `TrustedKey`, `TrustStore`, and `trust_store_from_key_set()` for the
  optional `/.well-known/wols-keys.json` key set document. Keys are never read
  from a label. An unusable entry (not Ed25519, not 32 bytes, or not a curve
  point) raises `WolsTrustStoreError` when it is built, and verifies as
  `invalid` if one reaches verification anyway.
- `trust_store_from_key_set()` follows the key set rules from
  [open-standard#26](https://github.com/wemush/open-standard/pull/26): an
  entry whose `alg` isn't `Ed25519` (compared exactly) is skipped without
  checking its other members, so an issuer can publish keys for a future
  algorithm without breaking this verifier. The new `on_skip` keyword is
  called with each skipped entry. A damaged `Ed25519` entry (bad kid, or a
  key that isn't canonical base64url of 32 bytes on the curve), a duplicate
  kid among `Ed25519` entries, and a document that isn't an object with a
  `keys` array, or holds an entry without a string `alg`, still reject the
  whole document. `TrustedKey` still rejects other algorithms.
- Signing refuses label text that isn't I-JSON, and encrypted URLs with no
  query, an empty query, or an existing `sig`.
- `wols.crypto.jcs`: RFC 8785 canonicalization and a JSON parser that reports
  duplicate member names. It handles where Python's `json` differs from
  I-JSON: integers are rounded to doubles, and `NaN`, `Infinity`, overflowing
  numbers, and lone surrogates are refused.
- `WolsSignatureError`, raised only when a label can't be signed, and
  `WolsTrustStoreError` (also a `ValueError`) for unusable trust store
  entries.
- `SUPPORTED_VERSIONS`: the label versions validation accepts without a
  warning, `{"1.3.0", "1.4.0"}`.
- Conformance: vendored the vectors from the final 1.4.0 specification
  (open-standard `02079df`; the files are byte-identical to the
  `1.4.0-rc.1` copies from `a44dd3a`), including `signatures.json` (with its
  `loadKeySet` cases) and the new `decrypt-with-sig`, `decrypt-signed-url`,
  and `signed-label-valid` cases. Every `MUST` and `SHOULD` case passes. The
  decrypt cases now also check that `sig` is kept unchanged.

### Changed

- The base64-key `WolsWarning` message now also suggests `RawKey(key)`.
- **`WOLS_VERSION` and `__version__` are `"1.4.0"`**, so new labels say
  `"version": "1.4.0"`. The wire format is unchanged: 1.3.0 labels decode
  the same way, and `wols` 1.3.0 reads 1.4.0 labels (with an
  `INVALID_VERSION` warning, since it expects exactly `1.3.0`).
- `validate_specimen` no longer warns `INVALID_VERSION` for `"version":
  "1.4.0"`. `"1.3.0"` still validates without a warning. Other versions still
  warn, including `"1.3.1"`, which was never released.
- `is_outdated("1.3.0")` is now `True`, and `migrate()` or `can_migrate()` on
  a 1.3.0 label needs a registered `1.3.0` to `1.4.0` handler. Setting
  `version` is enough:
  `register_migration("1.3.0", "1.4.0", lambda d: {**d, "version": "1.4.0"})`.
- **`strain.generation` is always written as a string** (WOLS 1.4.0,
  [open-standard#27](https://github.com/wemush/open-standard/pull/27)). wols
  1.3.0 accepted an `int` and wrote it as a JSON integer (`"generation": 1`),
  which the specification doesn't allow and `@wemush/wols` rejected. Now:
  - `Strain(generation=1)` and `Strain.from_dict({"generation": 1})` store
    `"1"` and emit a `WolsWarning`. Every generator (`to_json`,
    `encrypt_specimen`, `encrypt_specimen_fields`) writes the string. A
    negative, `bool`, or `float` generation is still rejected.
  - Labels that already carry an integer keep decoding. `parse_specimen` and
    `decrypt_specimen` read it as the decimal string (through `Strain`), and
    `decrypt_specimen_fields` does the same in the dictionary it returns,
    each with a `WolsWarning`. `decrypt_specimen_bytes` still returns the
    exact plaintext.
  - `validate_specimen` reports a `NUMERIC_GENERATION` warning on
    `strain.generation` for an integer, instead of accepting it silently.
  - Conformance: the `SHOULD` cases `generation-numeric`,
    `decrypt-numeric-generation`, and `decrypt-fields-numeric-generation`
    (open-standard `a44dd3a`) now pass. The `decrypt` check compares the
    decoded plaintext with `expected.specimen`, as the vector README now
    specifies.

## [1.3.0] - 2026-11-15

Implements WOLS 1.3.0 (`1.3.0-rc.2`). Every `MUST` and `SHOULD` case in the
WOLS conformance vectors passes, including `field-encryption.json`.

Field-level ciphertexts made by pre-release 1.3.0 builds (before `rc.2`
added NFC normalization and field AAD) do not decrypt with this release.
No such build was published, so no migration is needed.

### Breaking

`wols` versions follow the WOLS specification version, so this minor release
contains breaking changes. Read these entries before upgrading a `~=1.2` pin.

- **If you passed a base64 key string to `encrypt_specimen`/`decrypt_specimen`**,
  pass `base64.b64decode(key)` instead. A `str` is now a passphrase, so the
  old string would be used as a passphrase rather than a key.
  `encrypt_specimen` emits a `WolsWarning` when a string looks like a base64
  32-byte key.
- **Encrypted format**: The library now follows the WOLS 1.3.0 wire
  specification and cannot decrypt 1.2.x output by default.
  - `encrypt_specimen()` returns a
    `wemush://v1/encrypted/{id}?e=&iv=&kdf=pbkdf2|raw[&salt=&i=]` URL instead
    of a base64 blob. It uses AES-256-GCM with a separate random 12-byte `iv`,
    and all values are base64url without padding.
  - A `str` secret is now a passphrase. It selects `kdf=pbkdf2`
    (PBKDF2-HMAC-SHA256, a random 16-byte salt per label, and 600,000
    iterations by default, following OWASP guidance; pass
    `iterations=100_000`, the spec minimum, for faster scans). It is no longer a base64-encoded key. A 32-byte
    `bytes` key selects `kdf=raw`.
  - `decrypt_specimen()` takes the URL. It rejects fewer than 10,000
    iterations, missing or unexpected `salt`/`i`, unknown `kdf` values, and a
    decrypted `id` that doesn't match the URL path.
  - Passphrases are normalized to Unicode NFC before UTF-8 encoding and
    PBKDF2, when encrypting and decrypting.
  - `encrypt_specimen_fields()` returns a JSON-LD `dict` whose fields are
    `{"encrypted": true, "algorithm": "AES-256-GCM", "payload", "iv", "kdf",
    "salt"?, "iterations"?}` objects. It used to return a `Specimen` that
    silently dropped encrypted `strain` and `stage` values. Each ciphertext
    is bound by AES-GCM additional data to the label's `id` and the field
    name (`"{id}\n{field}"`), so swapped or copied fields fail to decrypt.
    The label must have a valid `id`.
  - The 1.2.x nonce-prefixed base64 format is never generated. Read it with
    `decrypt_specimen(..., allow_legacy=True)` or
    `decrypt_specimen_fields(..., allow_legacy=True)`.
- **IDs**: `validate_specimen()` and `validate_specimen_id()` accept any
  non-empty suffix after `wemush:` by default, as the spec requires. 1.2.0
  required a 24-character CUID in `validate_specimen()`. Opt in to stricter
  checks with `id_mode=` / `mode=` (`CUID`, `STRICT`, `ULID`, `UUID`).

### Added

- Conformance tests in `tests/conformance/` that run the vendored WOLS vectors
  (`embedded`, `primordia`, `generation`, `encrypted`, `field-encryption`)
  from open-standard tag `1.3.0-rc.2`, checked against its `SHA256SUMS`.
- `strain.transferDepth` (`Strain.transfer_depth`). It must be a non-negative
  integer, and validation warns when it is less than `clonalGeneration`. It
  round-trips through `to_json()` and `parse_specimen()`.
- `PRIMORDIA` supplied as a type resolves to `FRUITING`, sets `stage` to
  `PRIMORDIA` when no stage was given (never overriding one), and emits a
  `WolsWarning`. It is never serialized as a type, and it is reserved in
  `register_type_alias()`.
- `create_specimen()` resolves the spec alias table case-insensitively, and so
  does `wols create --type`.
- `create_specimen(type=...)`, matching the documented examples.
  `input_type=` still works.
- `WolsWarning` warning category.
- `wols.crypto`: `decrypt_specimen_bytes()`, `decrypt_specimen_fields()`,
  `parse_encrypted_url()`, `is_encrypted_url()`, `derive_key()`,
  `EncryptedLabel`, `EncryptedPayload`, and the base64url helpers.
- `IdValidationMode.CUID` and `validate_specimen(id_mode=...)`.

### Changed

- `validate_specimen()` reports an error for a wrong `@context` or `@type`
  value and a warning when either is missing.
- `strain.generation` accepts filial notation strings (`P`, `F1`, `G2`, `3`)
  as well as non-negative integers.
- `validate_specimen()` accepts field-level encryption objects in place of
  encryptable fields.
- The unknown-field warning recommends `custom`.
- `parse_compact_url()` raises `ENCRYPTED_URL` for a `wemush://v1/encrypted/...`
  URL instead of reading `encrypted` as the ID. It still accepts `wemush://`,
  `web+wemush://`, and `https://`. Compact URL output is unchanged.
- `WOLS_VERSION` and the package version are `1.3.0`.
- `Strain` rejects invalid `clonal_generation` and `generation` values (as it
  does `transfer_depth`), and `parse_specimen` reports any malformed field as
  `WolsParseError` instead of leaking `TypeError` or `AttributeError`.
- ID and base64url checks match the whole string. A trailing newline is
  rejected.
- `decrypt_specimen_fields` bounds total PBKDF2 work per label (10,000,000
  iterations across distinct salts), checking it before deriving any key. It
  refuses encrypted objects on identifying fields (`@context`, `@type`, `id`,
  `version`, `type`, `species`) with `IDENTIFYING_FIELD`.
- Encrypted URLs percent-encode the ID as one UTF-8 path segment. Decoding
  is strict: a malformed escape or invalid UTF-8 raises `INVALID_ENCODING`,
  and `+` is a literal character.
- Decoders reject more than 10,000,000 iterations (`EXCESSIVE_ITERATIONS`),
  a non-decimal `i` (`INVALID_PARAMETER`), and a plaintext with a UTF-8 byte
  order mark or invalid JSON (`INVALID_PLAINTEXT`). A field object without
  `kdf` raises `LEGACY_FORMAT`. Generation refuses more than 10,000,000
  iterations.
- `create_specimen` has typed overloads, so type checkers require exactly one
  of `type` or `input_type`.

## [0.1.1] - 2026-01-05

### Added

- Container image published to GitHub Container Registry (ghcr.io)
- Containerfile for running WOLS CLI in containerized environments
- Multi-architecture support (linux/amd64, linux/arm64)

### Changed

- Release workflow now builds and publishes container images alongside PyPI packages

## [0.1.0] - 2026-01-04

### Added

- Initial release of WOLS Python library
- Core module with specimen creation, parsing, validation, and serialization
- Support for WOLS v1.1.0 specification
- Specimen types: CULTURE, SPAWN, SUBSTRATE, FRUITING, HARVEST
- Growth stages: INOCULATION, COLONIZATION, FRUITING, HARVEST
- JSON-LD serialization with `@context` and `@type` fields
- Compact URL format for small QR codes
- Optional QR code generation (PNG, SVG, base64)
- Optional QR code scanning
- Optional AES-256-GCM encryption for sensitive data
- CLI interface with create, validate, qr, and scan commands
- Full type annotations with PEP 561 support
- 80%+ test coverage

[Unreleased]: https://github.com/wemush/specimen-labels-py/compare/1.4.0...HEAD
[1.4.0]: https://github.com/wemush/specimen-labels-py/compare/1.3.0...1.4.0
[1.3.0]: https://github.com/wemush/specimen-labels-py/compare/1.2.0...1.3.0
[0.1.1]: https://github.com/wemush/specimen-labels-py/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/wemush/specimen-labels-py/releases/tag/v0.1.0
