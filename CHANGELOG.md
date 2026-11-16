# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Implements the WOLS `1.4.0-rc.1` signature scheme
([open-standard#24](https://github.com/wemush/open-standard/pull/24)). The
specification is a release candidate, so this must not be released until it
is accepted.

### Added

- **Signatures** (`wols[crypto]`): `wols.crypto.sign_specimen`,
  `sign_encrypted_url`, and `verify_specimen` (plus the form-specific
  `verify_embedded` and `verify_encrypted_url`). Ed25519 (RFC 8032), with
  `S ≥ L` rejected explicitly as well as by the backend. Embedded labels are
  signed as the RFC 8785 (JCS) canonical form of the label as parsed, without
  its top-level `signature`; encrypted URLs are signed byte for byte before
  `&sig=`.
- `VerificationResult` with a `SignatureStatus` (`unsigned`, `malformed`,
  `unknown-kid`, `invalid`, `valid`, checked in that order), `kid`, and
  `reason`. Verification never raises for a bad signature.
- `TrustedKey`, `TrustStore`, and `trust_store_from_key_set()` for the
  optional `/.well-known/wols-keys.json` key set document. Keys are never read
  from a label.
- `wols.crypto.jcs`: RFC 8785 canonicalization and a JSON parser that reports
  duplicate member names. It handles where Python's `json` differs from
  I-JSON: integers are rounded to doubles, and `NaN`, `Infinity`, overflowing
  numbers, and lone surrogates are refused.
- `WolsSignatureError`, raised only when a label can't be signed.
- `SUPPORTED_VERSIONS`: the label versions validation accepts without a
  warning.
- Conformance: vendored the vectors from open-standard commit `dead46a`
  (`1.4.0-rc.1`), including `signatures.json` and the new
  `decrypt-with-sig`, `decrypt-signed-url`, and `signed-label-valid` cases.
  Every case passes. The decrypt cases now also check that `sig` is kept
  unchanged.

### Changed

- `validate_specimen` no longer warns `INVALID_VERSION` for `"version":
  "1.3.1"` or `"1.4.0"`. Those versions change no wire format, and 1.4.0's
  only addition, signatures, is now supported. Other versions still warn, and
  new labels are still written as `1.3.0`.

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

[Unreleased]: https://github.com/wemush/specimen-labels-py/compare/1.3.0...HEAD
[1.3.0]: https://github.com/wemush/specimen-labels-py/compare/1.2.0...1.3.0
[0.1.1]: https://github.com/wemush/specimen-labels-py/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/wemush/specimen-labels-py/releases/tag/v0.1.0
