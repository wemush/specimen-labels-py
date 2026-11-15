# WOLS - WeMush Open Labeling Standard

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-yellow.svg)](https://opensource.org/licenses/Apache-2.0)

The official Python implementation of the WeMush Open Labeling Standard (WOLS) v1.3.0 for specimen tracking in mushroom cultivation. It passes every case in the [WOLS conformance vectors](https://github.com/wemush/open-standard/tree/main/conformance) (see [`tests/conformance/`](tests/conformance/README.md)).

> **Upgrading from 1.2?** The encrypted format changed in 1.3.0 and is not compatible with 1.2.x output. See [Upgrading from 1.2](#upgrading-from-12).

![WOLS CLI Demo](demo/demo.gif)

## Features

- **Core Module**: Create, parse, validate, and serialize specimen labels
- **QR Codes**: Generate and scan QR codes (PNG, SVG, base64)
- **Encryption**: WOLS 1.3.0 encrypted labels (AES-256-GCM, passphrase or raw key)
- **CLI**: Command-line interface for all operations
- **Type Safe**: Full type annotations with PEP 561 support

## Installation

### Basic Installation (Core Only)

```bash
# Using UV (recommended)
uv add wols

# Using pip
pip install wols
```

### With Optional Features

```bash
# QR code support
uv add "wols[qr]"

# CLI support
uv add "wols[cli]"

# Encryption support
uv add "wols[crypto]"

# Everything
uv add "wols[all]"
```

### Requirements

- Python 3.12 or later
- No required dependencies for core module

### Container Image

The WOLS CLI is also available as a container image:

```bash
# Pull the latest image
docker pull ghcr.io/wemush/specimen-labels-py:latest

# Run the CLI
docker run --rm ghcr.io/wemush/specimen-labels-py --version

# Create a specimen
docker run --rm ghcr.io/wemush/specimen-labels-py create \
  --species "Pleurotus ostreatus" \
  --type SUBSTRATE \
  --json

# Validate a specimen (mount local file)
docker run --rm -v $(pwd):/data ghcr.io/wemush/specimen-labels-py \
  validate /data/specimen.json

# Generate QR code
docker run --rm -v $(pwd):/data ghcr.io/wemush/specimen-labels-py \
  qr /data/specimen.json --output /data/label.png
```

## Quick Examples

### Create a Specimen (Library)

```python
from wols import create_specimen, SpecimenType, GrowthStage, to_json

# Create a specimen
specimen = create_specimen(
    type=SpecimenType.SUBSTRATE,
    species="Pleurotus ostreatus",
    strain="Blue Oyster",
    stage=GrowthStage.COLONIZATION,
    batch="BATCH-2026-001",
)

# Print the ID
print(f"Created: {specimen.id}")
# Output: Created: wemush:clx1abc123def456

# Serialize to JSON-LD
json_str = to_json(specimen, indent=2)
print(json_str)
```

### Create a Specimen (CLI)

```bash
wols create \
  --species "Pleurotus ostreatus" \
  --type SUBSTRATE \
  --strain "Blue Oyster" \
  --stage COLONIZATION \
  --output specimen.json
```

### Generate QR Code (Library)

```python
from wols import create_specimen, SpecimenType
from wols.qr import generate_qr_png

specimen = create_specimen(
    type=SpecimenType.SUBSTRATE,
    species="Pleurotus ostreatus",
)

# Generate QR code
qr_bytes = generate_qr_png(specimen)

# Save to file
with open("label.png", "wb") as f:
    f.write(qr_bytes)
```

### Validate Specimen (Library)

```python
from wols import validate_specimen, parse_specimen

json_str = '{"@context": "...", "@type": "Specimen", ...}'
specimen = parse_specimen(json_str)

result = validate_specimen(specimen)
if result.valid:
    print("Valid specimen!")
else:
    for error in result.errors:
        print(f"{error.path}: {error.message}")
```

### Validate Specimen (CLI)

```bash
wols validate specimen.json
```

### Encrypt a Specimen (Library)

```python
import os
from wols.crypto import decrypt_specimen, encrypt_specimen

# A passphrase (str) uses kdf=pbkdf2 with a random salt for every label
url = encrypt_specimen(specimen, "correct horse battery staple")
# wemush://v1/encrypted/{id}?e=...&iv=...&kdf=pbkdf2&salt=...&i=600000

# A 32-byte key (bytes) uses kdf=raw
key = os.urandom(32)
url = encrypt_specimen(specimen, key)

recovered = decrypt_specimen(url, key)
```

The specimen ID stays visible in the URL, percent-encoded as one path segment
(so IDs containing `/`, `+`, `%`, spaces, or non-ASCII characters round-trip).
Decryption checks that the decrypted `id` matches it. Errors raise
`WolsEncryptionError` with a `code` such as `AUTHENTICATION_FAILED`,
`ID_MISMATCH`, `EXCESSIVE_ITERATIONS`, `INVALID_ENCODING`, or
`INVALID_PLAINTEXT`. The codes match the conformance vectors' suggested
reasons.

To encrypt individual fields inside an embedded label, use
`encrypt_specimen_fields(specimen, secret, ["strain", "custom"])` and
`decrypt_specimen_fields`. Each field's value is replaced with an
`{"encrypted": true, "algorithm": "AES-256-GCM", ...}` object. Identifying
fields (`@context`, `@type`, `id`, `version`, `type`, `species`) are never
encrypted, and a label that has any of them encrypted is refused with
`IDENTIFYING_FIELD`.

Security notes:

- **Iterations and scan speed**: Passphrase labels default to 600,000
  PBKDF2 iterations, in line with OWASP guidance for PBKDF2-HMAC-SHA256.
  Every scan pays that cost once: about 0.1 s on a desktop, and more on
  phones or in browsers. If scan speed matters more than resistance to
  offline guessing, pass `iterations=100_000`, the spec minimum. Generation
  refuses more than 10,000,000. The count is stored in each label, so
  decoders read either. Raw-key labels (`bytes`) skip key derivation
  entirely.

- **Passphrases**: Labels are printed and their ciphertext is public, so a
  weak passphrase can be guessed offline. Use a long, random passphrase, or a
  raw 32-byte key. Passphrases are normalized to Unicode NFC and then encoded
  as UTF-8 before key derivation, both when encrypting and when decrypting,
  so `ü` typed as one code point or as `u` plus a combining mark gives the
  same key on every platform.
- **Field-level integrity**: Each field's ciphertext is authenticated
  together with AES-GCM additional data: the label's full `id`, a line feed,
  and the field name (for example `wemush:clx1a2b3c4\nstrain`). An encrypted
  value swapped into another field, or copied from another label, fails with
  `AUTHENTICATION_FAILED`, and so does a label whose `id` was changed. Each
  field gets its own random IV. Unencrypted fields are not authenticated;
  use the whole-label URL form when every field must be tamper-evident.
- **Raw keys**: Every label gets a fresh random 96-bit IV. Rotate a long-lived
  raw key well before it has encrypted about 2^32 labels.
- **Untrusted input**: Decoders cap PBKDF2 work at 10,000,000 iterations per
  URL, and in total across the distinct salts of a field-level label, so a
  crafted label can't stall a scanner. `i` must be plain decimal digits.
  Every parameter, the percent-encoded ID, and the total cost are checked
  before any key is derived. A decrypted plaintext that starts with a UTF-8
  byte order mark is refused.

## WOLS 1.3.0 Behavior

- **IDs**: Any non-empty suffix after `wemush:` is accepted, including
  `wemush:clx1a2b3c4`, ULIDs, UUIDs, and `wemush:WM-LC-250114-000001`. For a
  stricter check, opt in with
  `validate_specimen(data, id_mode=IdValidationMode.CUID)` (or `STRICT`,
  `ULID`, `UUID`).
- **Type aliases**: `create_specimen(type=...)` and `wols create --type`
  resolve the spec alias table case-insensitively. For example, `"lc"` becomes
  `CULTURE`, `"BLOCK"` becomes `SUBSTRATE`, and `"PINNING"` becomes
  `FRUITING`.
- **Warnings**: Two channels exist. `create_specimen()` and
  `encrypt_specimen()` report accepted-but-questionable input through
  `warnings.warn(..., WolsWarning)`. Run
  `warnings.simplefilter("error", WolsWarning)` to turn those into errors.
  `validate_specimen()` returns its findings in `ValidationResult.warnings`
  and never calls `warnings.warn`.
- **`PRIMORDIA`**: This is a growth stage, not a type. Passing it as the type
  gives `type=FRUITING` and sets `stage=PRIMORDIA` when no stage was supplied
  (a supplied stage is kept). It also emits a `wols.WolsWarning`. `PRIMORDIA`
  is never serialized as a `type`.
- **Transfer depth**: `Strain(transfer_depth=5)` is serialized as
  `strain.transferDepth`. It must be a non-negative integer. Validation warns
  when it is less than `clonalGeneration`. `generation` is the filial
  generation (`"F1"`, `"P"`, `"G2"`, `"3"`), `clonal_generation` counts
  culture-to-culture subcultures, and `transfer_depth` counts every transfer.
- **Compact URLs**: `parse_compact_url` accepts `wemush://`, `web+wemush://`,
  and `https://`. The compact URL output is unchanged in 1.3.0.

## Upgrading from 1.2

The encrypted format follows the WOLS 1.3.0 wire specification. It is
**not compatible** with 1.2.x output:

| | 1.2.x | 1.3.0 |
| --- | --- | --- |
| `encrypt_specimen` returns | standard base64 of `nonce‖ciphertext` | `wemush://v1/encrypted/{id}?e=&iv=&kdf=...` URL |
| A `str` secret means | a base64-encoded 32-byte key | a passphrase (PBKDF2-HMAC-SHA256) |
| A `bytes` secret means | a 32-byte key | a 32-byte key (`kdf=raw`) |
| IV | prefixed to the ciphertext | separate `iv` parameter |
| Encoding | standard base64 with padding | base64url, no padding |
| `encrypt_specimen_fields` returns | a `Specimen` (dropped `strain`/`stage`) | a JSON-LD `dict` with encryption objects |

**If you passed a base64 key string in 1.2**, decode it to bytes to keep
using it as a raw key. Passing the string itself now treats it as a
passphrase, and `encrypt_specimen` emits a `WolsWarning` when a string looks
like a base64-encoded key.

```python
import base64

key_b64 = "..."  # your 1.2 key string

# 1.2: encrypt_specimen(specimen, key_b64)
url = encrypt_specimen(specimen, base64.b64decode(key_b64))  # kdf=raw
specimen = decrypt_specimen(url, base64.b64decode(key_b64))

# Reading 1.2 payloads: the legacy path still accepts the base64 string
old = decrypt_specimen(old_payload, key_b64, allow_legacy=True)
```

To read labels written by 1.2.x, pass `allow_legacy=True`, for example
`decrypt_specimen(old_payload, key, allow_legacy=True)` or
`decrypt_specimen_fields(data, key, allow_legacy=True)`. The old format is
never generated.

`wols` versions follow the WOLS specification version, so 1.3.0 carries
breaking changes despite being a minor release. If you pin `wols~=1.2` or
`wols>=1.2,<2`, check this section before upgrading.

Other changes that may affect callers:

- `validate_specimen` and `validate_specimen_id` accept any non-empty ID
  suffix by default. Pass `id_mode=` or `mode=` to restore a stricter check.
- `validate_specimen` reports an error when `@context` or `@type` has the
  wrong value. A missing value is a warning.
- `strain.generation` accepts filial notation strings (`"F1"`) as well as
  integers.

## Verification

After installation, verify the library works:

```bash
# Check version
python -c "import wols; print(wols.__version__)"

# Check CLI (if installed)
wols --version

# Run a quick test
python -c "
from wols import create_specimen, SpecimenType, to_json
s = create_specimen(type=SpecimenType.CULTURE, species='Test')
print('Success:', s.id)
"
```

## Documentation

- [Full API Documentation](./specs/001-wols-python-library/contracts/python-api.md)
- [CLI Reference](./specs/001-wols-python-library/contracts/cli-api.md)
- [Data Model](./specs/001-wols-python-library/data-model.md)
- [Quickstart Guide](./specs/001-wols-python-library/quickstart.md)

## Development

```bash
# Clone the repository
git clone https://github.com/wemush/specimen-labels-py.git
cd specimen-labels-py

# Install with development dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run only the WOLS conformance vectors
uv run pytest tests/conformance -v

# Run linting
uv run ruff check src tests
uv run ruff format --check src tests

# Run type checking
uv run mypy src
```

### Regenerating the Demo GIF

The demo GIF is generated using [VHS](https://github.com/charmbracelet/vhs):

```bash
# Install VHS (macOS)
brew install vhs

# Regenerate the demo
cd demo
vhs demo.tape
```

## License

Apache 2.0 License - see [LICENSE](LICENSE) for details.
