"""WOLS encryption and decryption (WOLS v1.3.0 encrypted format).

Optional module - requires: pip install wols[crypto]

Secrets: a ``str`` passphrase selects ``kdf=pbkdf2`` (PBKDF2-HMAC-SHA256 with
a random per-label salt, the passphrase normalized to Unicode NFC); a 32-byte
``bytes`` key, or a :class:`RawKey` (which also accepts base64 or base64url
text), selects ``kdf=raw``. Field-level ciphertexts are bound to the
label's ``id`` and the field name by AES-GCM additional data.

Signatures (WOLS v1.4.0): :func:`sign_specimen` and
:func:`sign_encrypted_url` add an Ed25519 signature token;
:func:`verify_specimen` checks it against a caller-supplied trust store and
returns a :class:`SignatureStatus`. Decoding and decryption never verify.
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
from wols.crypto.signature import (
    SignatureStatus,
    TrustedKey,
    TrustStore,
    VerificationResult,
    sign_encrypted_url,
    sign_specimen,
    trust_store_from_key_set,
    verify_embedded,
    verify_encrypted_url,
    verify_specimen,
)
from wols.crypto.wire import (
    ALGORITHM,
    DEFAULT_ITERATIONS,
    MIN_DECODE_ITERATIONS,
    EncryptedLabel,
    EncryptedPayload,
    RawKey,
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
    "RawKey",
    "Secret",
    "SignatureStatus",
    "TrustStore",
    "TrustedKey",
    "VerificationResult",
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
    "sign_encrypted_url",
    "sign_specimen",
    "trust_store_from_key_set",
    "verify_embedded",
    "verify_encrypted_url",
    "verify_specimen",
]
