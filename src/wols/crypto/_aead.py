"""AES-256-GCM primitives and key handling shared by encrypt and decrypt."""

from __future__ import annotations

import base64
import binascii
import os
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wols.crypto.wire import (
    DEFAULT_ITERATIONS,
    IV_LENGTH,
    KEY_LENGTH,
    MAX_DECODE_ITERATIONS,
    MIN_GENERATE_ITERATIONS,
    SALT_LENGTH,
    EncryptedPayload,
    Kdf,
    RawKey,
    Secret,
    derive_key,
)
from wols.exceptions import WolsEncryptionError, WolsWarning

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _aesgcm(key: bytes) -> AESGCM:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:  # pragma: no cover - exercised without extra
        raise ImportError(
            "Crypto module not installed. Install with: pip install wols\\[crypto]"
        ) from e
    return AESGCM(key)


@dataclass(frozen=True)
class KeyMaterial:
    """A key ready for sealing, with the parameters that produced it."""

    key: bytes
    kdf: Kdf
    salt: bytes | None = None
    iterations: int | None = None


def _check_raw_key(secret: Any) -> bytes:
    if isinstance(secret, RawKey):
        return secret.key
    if not isinstance(secret, bytes | bytearray):
        raise WolsEncryptionError(
            message="kdf=raw requires a 32-byte key as bytes or RawKey",
            code="INVALID_KEY",
        )
    if len(secret) != KEY_LENGTH:
        raise WolsEncryptionError(
            message=f"Key must be {KEY_LENGTH} bytes, got {len(secret)}",
            code="INVALID_KEY",
        )
    return bytes(secret)


def _check_passphrase(secret: Any) -> str:
    if not isinstance(secret, str):
        raise WolsEncryptionError(
            message="kdf=pbkdf2 requires a passphrase as str",
            code="INVALID_KEY",
        )
    if not secret:
        raise WolsEncryptionError(
            message="Passphrase must not be empty", code="INVALID_KEY"
        )
    return secret


def _looks_like_base64_key(secret: str) -> bool:
    """True if secret is standard or URL-safe base64 of exactly 32 bytes."""
    if len(secret) not in (43, 44):
        return False
    for altchars in (None, b"-_"):
        try:
            padded = secret + "=" * (-len(secret) % 4)
            decoded = base64.b64decode(padded, altchars=altchars, validate=True)
        except (binascii.Error, ValueError):
            continue
        if len(decoded) == KEY_LENGTH:
            return True
    return False


_KEY_LIKE_PASSPHRASE = (
    "The secret is a str that looks like a base64-encoded 32-byte key. Since "
    "wols 1.3.0 a str is a passphrase (kdf=pbkdf2). To use it as a raw key "
    "(kdf=raw), pass base64.b64decode(key) or RawKey(key) instead."
)


def prepare_key(
    secret: Secret,
    iterations: int = DEFAULT_ITERATIONS,
    *,
    strict_passphrase: bool = False,
) -> KeyMaterial:
    """Select the KDF from the secret type and produce a fresh key.

    A ``str`` passphrase selects ``pbkdf2`` with a new random salt; a
    32-byte ``bytes`` key or a :class:`~wols.crypto.RawKey` selects ``raw``.

    A ``str`` that looks like a base64-encoded 32-byte key emits a
    ``WolsWarning``, or raises ``INVALID_KEY`` when ``strict_passphrase`` is
    true.
    """
    if isinstance(secret, str):
        passphrase = _check_passphrase(secret)
        if _looks_like_base64_key(passphrase):
            if strict_passphrase:
                raise WolsEncryptionError(
                    message=_KEY_LIKE_PASSPHRASE, code="INVALID_KEY"
                )
            warnings.warn(_KEY_LIKE_PASSPHRASE, WolsWarning, stacklevel=3)
        if (
            isinstance(iterations, bool)
            or not isinstance(iterations, int)
            or not MIN_GENERATE_ITERATIONS <= iterations <= MAX_DECODE_ITERATIONS
        ):
            raise WolsEncryptionError(
                message="PBKDF2 iterations must be an integer from "
                f"{MIN_GENERATE_ITERATIONS} to {MAX_DECODE_ITERATIONS}, "
                f"got {iterations!r}",
                code="INVALID_PARAMETER",
            )
        salt = os.urandom(SALT_LENGTH)
        return KeyMaterial(
            key=derive_key(passphrase, salt, iterations),
            kdf="pbkdf2",
            salt=salt,
            iterations=iterations,
        )
    return KeyMaterial(key=_check_raw_key(secret), kdf="raw")


def key_for_payload(payload: EncryptedPayload, secret: Secret) -> bytes:
    """Recover the key for a parsed payload from the caller's secret."""
    if payload.kdf == "pbkdf2":
        passphrase = _check_passphrase(secret)
        if payload.salt is None or payload.iterations is None:
            raise WolsEncryptionError(
                message="kdf=pbkdf2 requires salt and iterations",
                code="MISSING_PARAMETER",
            )
        return derive_key(passphrase, payload.salt, payload.iterations)
    return _check_raw_key(secret)


def field_aad(label_id: str, field: str) -> bytes:
    """Additional data binding a field-level ciphertext to its label and field.

    The UTF-8 encoding of the label's full ``id``, a line feed, and the
    top-level field name, e.g. ``b"wemush:clx1a2b3c4\\nstrain"``.
    """
    return f"{label_id}\n{field}".encode()


def seal(
    plaintext: bytes, material: KeyMaterial, aad: bytes | None = None
) -> EncryptedPayload:
    """Encrypt with a fresh random IV, authenticating ``aad`` if given."""
    iv = os.urandom(IV_LENGTH)
    try:
        ciphertext = _aesgcm(material.key).encrypt(iv, plaintext, aad)
    except Exception as e:
        raise WolsEncryptionError(
            message=f"Encryption failed: {e}", code="ENCRYPTION_ERROR"
        ) from e
    return EncryptedPayload(
        ciphertext=ciphertext,
        iv=iv,
        kdf=material.kdf,
        salt=material.salt,
        iterations=material.iterations,
    )


def open_payload(
    payload: EncryptedPayload, key: bytes, aad: bytes | None = None
) -> bytes:
    """Decrypt and authenticate a payload (and ``aad``, if given)."""
    from cryptography.exceptions import InvalidTag

    try:
        return _aesgcm(key).decrypt(payload.iv, payload.ciphertext, aad)
    except InvalidTag as e:
        raise WolsEncryptionError(
            message="Authentication failed: wrong key or passphrase, or the "
            "label was modified",
            code="AUTHENTICATION_FAILED",
        ) from e
