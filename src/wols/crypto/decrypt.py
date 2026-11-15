"""Specimen decryption (WOLS v1.3.0 encrypted format).

The pre-1.3.0 format produced by ``wols`` 1.x (a standard-base64 blob of
``nonce || ciphertext``, with no URL or ``kdf``) can be read only when the
caller passes ``allow_legacy=True``. It is never generated.
"""

from __future__ import annotations

import base64
import binascii
import copy
import json
from typing import TYPE_CHECKING, Any

from wols.crypto._aead import key_for_payload, open_payload
from wols.crypto.wire import (
    IV_LENGTH,
    KEY_LENGTH,
    Secret,
    parse_encrypted_field,
    parse_encrypted_url,
)
from wols.exceptions import WolsEncryptionError

if TYPE_CHECKING:
    from wols.models.specimen import Specimen

_LEGACY_FIELD_PREFIX = "encrypted:"


def decrypt_specimen_bytes(url: str, secret: Secret) -> bytes:
    """Decrypt an encrypted-format URL and return the exact plaintext bytes.

    The plaintext must be a JSON object whose ``id`` equals ``wemush:{id}``
    from the URL path.

    Args:
        url: ``wemush://v1/encrypted/{id}?...`` (``web+wemush://`` is also
            accepted).
        secret: The passphrase (``str``) for ``kdf=pbkdf2`` or the 32-byte
            key (``bytes``) for ``kdf=raw``.

    Returns:
        The decrypted UTF-8 JSON-LD bytes.

    Raises:
        WolsEncryptionError: With one of these codes:
            ``AUTHENTICATION_FAILED`` (wrong secret or tampered label),
            ``ID_MISMATCH``, ``INSUFFICIENT_ITERATIONS``,
            ``MISSING_PARAMETER``, ``UNEXPECTED_PARAMETER``,
            ``UNSUPPORTED_KDF``, ``INVALID_PARAMETER``, ``INVALID_KEY``,
            ``INVALID_URL``, ``LEGACY_FORMAT``, or ``INVALID_PAYLOAD``.
    """
    label = parse_encrypted_url(url)
    plaintext = open_payload(label.payload, key_for_payload(label.payload, secret))

    try:
        data = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise WolsEncryptionError(
            message=f"Decrypted payload is not UTF-8 JSON: {e}",
            code="INVALID_PAYLOAD",
        ) from e
    if not isinstance(data, dict):
        raise WolsEncryptionError(
            message="Decrypted payload is not a JSON object",
            code="INVALID_PAYLOAD",
        )
    if data.get("id") != label.specimen_id:
        raise WolsEncryptionError(
            message=f"Decrypted specimen ID {data.get('id')!r} does not match "
            f"'{label.specimen_id}' from the URL",
            code="ID_MISMATCH",
        )
    return plaintext


def decrypt_specimen(
    url: str,
    secret: Secret,
    *,
    allow_legacy: bool = False,
) -> Specimen:
    """Decrypt an encrypted-format URL into a Specimen.

    Args:
        url: ``wemush://v1/encrypted/{id}?...`` URL. With
            ``allow_legacy=True``, a pre-1.3.0 base64 payload is also
            accepted.
        secret: The passphrase (``str``) for ``kdf=pbkdf2`` or the 32-byte
            key (``bytes``) for ``kdf=raw``. For a legacy payload, a 32-byte
            key or a standard-base64 encoding of one.
        allow_legacy: Accept the pre-1.3.0 nonce-prefixed base64 format.

    Returns:
        The decrypted Specimen.

    Raises:
        WolsEncryptionError: If decryption or validation fails (see
            :func:`decrypt_specimen_bytes` for codes). A legacy payload
            without ``allow_legacy=True`` raises ``LEGACY_FORMAT``.
        WolsParseError: If the plaintext is not a valid specimen.

    Example:
        >>> specimen = decrypt_specimen(url, "correct horse battery staple")
    """
    from wols.core.parse import parse_specimen

    text = url.strip()
    if "://" in text:
        # Any URL goes through the v1.3.0 parser, which reports what is wrong.
        plaintext = decrypt_specimen_bytes(text, secret)
    elif allow_legacy:
        plaintext = _decrypt_legacy(text, secret)
    else:
        raise WolsEncryptionError(
            message="Not an encrypted WOLS URL. If this is a payload from wols "
            "1.x, pass allow_legacy=True",
            code="LEGACY_FORMAT",
        )
    return parse_specimen(plaintext.decode("utf-8"))


def decrypt_specimen_fields(
    data: dict[str, Any],
    secret: Secret,
    *,
    allow_legacy: bool = False,
) -> dict[str, Any]:
    """Decrypt field-level encryption objects in an embedded label.

    Args:
        data: JSON-LD dictionary, as returned by
            :func:`~wols.crypto.encrypt_specimen_fields`.
        secret: The passphrase (``str``) or 32-byte key (``bytes``).
        allow_legacy: Also decrypt pre-1.3.0 ``"encrypted:<base64>"`` string
            values.

    Returns:
        A new dictionary with every encrypted field restored. Pass it to
        :meth:`wols.Specimen.from_dict` for a Specimen.

    Raises:
        WolsEncryptionError: If any field fails to decrypt.
    """
    result = copy.deepcopy(data)
    keys: dict[tuple[str, bytes | None, int | None], bytes] = {}

    for field, value in data.items():
        if isinstance(value, dict) and value.get("encrypted") is True:
            payload = parse_encrypted_field(value, field=field)
            cache_key = (payload.kdf, payload.salt, payload.iterations)
            if cache_key not in keys:
                keys[cache_key] = key_for_payload(payload, secret)
            plaintext = open_payload(payload, keys[cache_key])
        elif (
            allow_legacy
            and isinstance(value, str)
            and value.startswith(_LEGACY_FIELD_PREFIX)
        ):
            plaintext = _decrypt_legacy(value[len(_LEGACY_FIELD_PREFIX) :], secret)
        else:
            continue

        try:
            result[field] = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise WolsEncryptionError(
                message=f"Field '{field}' did not decrypt to UTF-8 JSON: {e}",
                code="INVALID_PAYLOAD",
            ) from e
    return result


def _legacy_key(key: Secret) -> bytes:
    """Interpret a key the way wols 1.x did: raw bytes or standard base64."""
    if isinstance(key, bytes | bytearray):
        key_bytes = bytes(key)
    else:
        try:
            key_bytes = base64.b64decode(key, validate=True)
        except (binascii.Error, ValueError) as e:
            raise WolsEncryptionError(
                message=f"Failed to decode key: {e}", code="INVALID_KEY"
            ) from e
    if len(key_bytes) != KEY_LENGTH:
        raise WolsEncryptionError(
            message=f"Key must be {KEY_LENGTH} bytes, got {len(key_bytes)}",
            code="INVALID_KEY",
        )
    return key_bytes


def _decrypt_legacy(payload: str, key: Secret) -> bytes:
    """Decrypt the wols 1.x format: base64(nonce[12] || ciphertext || tag)."""
    from cryptography.exceptions import InvalidTag

    from wols.crypto._aead import _aesgcm

    key_bytes = _legacy_key(key)
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as e:
        raise WolsEncryptionError(
            message=f"Failed to decode legacy payload: {e}", code="INVALID_PAYLOAD"
        ) from e
    if len(raw) < IV_LENGTH + 16:
        raise WolsEncryptionError(
            message="Legacy payload too short", code="INVALID_PAYLOAD"
        )
    try:
        return _aesgcm(key_bytes).decrypt(raw[:IV_LENGTH], raw[IV_LENGTH:], None)
    except InvalidTag as e:
        raise WolsEncryptionError(
            message="Authentication failed: wrong key or corrupted payload",
            code="AUTHENTICATION_FAILED",
        ) from e
