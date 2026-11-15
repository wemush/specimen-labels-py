"""WOLS encryption and decryption (WOLS v1.3.0 encrypted format).

Optional module - requires: pip install wols[crypto]

Secrets: a ``str`` passphrase selects ``kdf=pbkdf2`` (PBKDF2-HMAC-SHA256 with
a random per-label salt); a 32-byte ``bytes`` key selects ``kdf=raw``.
"""

from wols.crypto.decrypt import (
    decrypt_specimen,
    decrypt_specimen_bytes,
    decrypt_specimen_fields,
)
from wols.crypto.encrypt import (
    ENCRYPTABLE_FIELDS,
    encrypt_specimen,
    encrypt_specimen_fields,
)
from wols.crypto.wire import (
    ALGORITHM,
    DEFAULT_ITERATIONS,
    MIN_DECODE_ITERATIONS,
    EncryptedLabel,
    EncryptedPayload,
    Secret,
    b64url_decode,
    b64url_encode,
    derive_key,
    is_encrypted_url,
    parse_encrypted_url,
)

__all__ = [
    "ALGORITHM",
    "DEFAULT_ITERATIONS",
    "ENCRYPTABLE_FIELDS",
    "MIN_DECODE_ITERATIONS",
    "EncryptedLabel",
    "EncryptedPayload",
    "Secret",
    "b64url_decode",
    "b64url_encode",
    "decrypt_specimen",
    "decrypt_specimen_bytes",
    "decrypt_specimen_fields",
    "derive_key",
    "encrypt_specimen",
    "encrypt_specimen_fields",
    "is_encrypted_url",
    "parse_encrypted_url",
]
