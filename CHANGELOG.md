# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-11-15

Implements WOLS 1.3.0 (`1.3.0-rc.1`). Every `MUST` and `SHOULD` case in the
WOLS conformance vectors passes.

### Breaking

- **Encrypted format**: The library now follows the WOLS 1.3.0 wire
  specification and cannot decrypt 1.2.x output by default.
  - `encrypt_specimen()` returns a
    `wemush://v1/encrypted/{id}?e=&iv=&kdf=pbkdf2|raw[&salt=&i=]` URL instead
    of a base64 blob. It uses AES-256-GCM with a separate random 12-byte `iv`,
    and all values are base64url without padding.
  - A `str` secret is now a passphrase. It selects `kdf=pbkdf2`
    (PBKDF2-HMAC-SHA256, a random 16-byte salt per label, and 100,000
    iterations by default). It is no longer a base64-encoded key. A 32-byte
    `bytes` key selects `kdf=raw`.
  - `decrypt_specimen()` takes the URL. It rejects fewer than 10,000
    iterations, missing or unexpected `salt`/`i`, unknown `kdf` values, and a
    decrypted `id` that doesn't match the URL path.
  - `encrypt_specimen_fields()` returns a JSON-LD `dict` whose fields are
    `{"encrypted": true, "algorithm": "AES-256-GCM", "payload", "iv", "kdf",
    "salt"?, "iterations"?}` objects. It used to return a `Specimen` that
    silently dropped encrypted `strain` and `stage` values.
  - The 1.2.x nonce-prefixed base64 format is never generated. Read it with
    `decrypt_specimen(..., allow_legacy=True)` or
    `decrypt_specimen_fields(..., allow_legacy=True)`.
- **IDs**: `validate_specimen()` and `validate_specimen_id()` accept any
  non-empty suffix after `wemush:` by default, as the spec requires. 1.2.0
  required a 24-character CUID in `validate_specimen()`. Opt in to stricter
  checks with `id_mode=` / `mode=` (`CUID`, `STRICT`, `ULID`, `UUID`).

### Added

- Conformance tests in `tests/conformance/` that run the vendored WOLS vectors
  (`embedded`, `primordia`, `generation`, `encrypted`) from open-standard tag
  `1.3.0-rc.1`.
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
