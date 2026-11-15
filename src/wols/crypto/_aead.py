"""AES-256-GCM primitives and key handling shared by encrypt and decrypt."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wols.crypto.wire import (
    DEFAULT_ITERATIONS,
    IV_LENGTH,
    KEY_LENGTH,
    MIN_GENERATE_ITERATIONS,
    SALT_LENGTH,
    EncryptedPayload,
    Kdf,
    Secret,
    derive_key,
)
from wols.exceptions import WolsEncryptionError

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
    if not isinstance(secret, bytes | bytearray):
        raise WolsEncryptionError(
            message="kdf=raw requires a 32-byte key as bytes",
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


def prepare_key(secret: Secret, iterations: int = DEFAULT_ITERATIONS) -> KeyMaterial:
    """Select the KDF from the secret type and produce a fresh key.

    A ``str`` passphrase selects ``pbkdf2`` with a new random salt; a
    32-byte ``bytes`` key selects ``raw``.
    """
    if isinstance(secret, str):
        passphrase = _check_passphrase(secret)
        if (
            isinstance(iterations, bool)
            or not isinstance(iterations, int)
            or iterations < MIN_GENERATE_ITERATIONS
        ):
            raise WolsEncryptionError(
                message="PBKDF2 iterations must be an integer of at least "
                f"{MIN_GENERATE_ITERATIONS}, got {iterations!r}",
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


def seal(plaintext: bytes, material: KeyMaterial) -> EncryptedPayload:
    """Encrypt with a fresh random IV."""
    iv = os.urandom(IV_LENGTH)
    try:
        ciphertext = _aesgcm(material.key).encrypt(iv, plaintext, None)
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


def open_payload(payload: EncryptedPayload, key: bytes) -> bytes:
    """Decrypt and authenticate a payload."""
    from cryptography.exceptions import InvalidTag

    try:
        return _aesgcm(key).decrypt(payload.iv, payload.ciphertext, None)
    except InvalidTag as e:
        raise WolsEncryptionError(
            message="Authentication failed: wrong key or passphrase, or the "
            "label was modified",
            code="AUTHENTICATION_FAILED",
        ) from e
