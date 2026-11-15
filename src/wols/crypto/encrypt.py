"""Specimen encryption (WOLS v1.3.0 encrypted format).

Only the v1.3.0 format is generated. The pre-1.3.0 nonce-prefixed base64
format is never produced.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

from wols.constants import ID_PREFIX
from wols.core.validate import validate_specimen_id
from wols.crypto._aead import prepare_key, seal
from wols.crypto.wire import DEFAULT_ITERATIONS, EncryptedLabel, Secret
from wols.exceptions import WolsEncryptionError

if TYPE_CHECKING:
    from wols.models.specimen import Specimen

ENCRYPTABLE_FIELDS: frozenset[str] = frozenset(
    {"strain", "stage", "batch", "organization", "creator", "custom"}
)
"""Fields that :func:`encrypt_specimen_fields` can encrypt."""


def _compact_json(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def encrypt_specimen(
    specimen: Specimen,
    secret: Secret,
    *,
    iterations: int = DEFAULT_ITERATIONS,
) -> str:
    """Encrypt a specimen into an encrypted-format URL.

    The plaintext is the compact UTF-8 JSON-LD serialization of the
    specimen. The IV (and, for a passphrase, the salt) is freshly random for
    every call.

    Args:
        specimen: Specimen to encrypt. Its ID suffix appears in the URL in
            cleartext.
        secret: A passphrase (``str``), which selects ``kdf=pbkdf2``, or a
            32-byte key (``bytes``), which selects ``kdf=raw``.
        iterations: PBKDF2 iterations for a passphrase (at least 100,000).
            Ignored for a raw key.

    Returns:
        ``wemush://v1/encrypted/{id}?e=...&iv=...&kdf=...[&salt=...&i=...]``

    Raises:
        WolsEncryptionError: If the key, passphrase, iterations, or ID is
            invalid, or encryption fails.

    Example:
        >>> url = encrypt_specimen(specimen, "correct horse battery staple")
        >>> url = encrypt_specimen(specimen, os.urandom(32))
    """
    prefix = f"{ID_PREFIX}:"
    if not validate_specimen_id(specimen.id):
        raise WolsEncryptionError(
            message=f"Specimen ID must be '{prefix}' followed by a non-empty "
            f"suffix, got '{specimen.id}'",
            code="INVALID_ID",
        )

    material = prepare_key(secret, iterations)
    payload = seal(_compact_json(specimen.to_dict()), material)
    return EncryptedLabel(id=specimen.id[len(prefix) :], payload=payload).to_url()


def encrypt_specimen_fields(
    specimen: Specimen | dict[str, Any],
    secret: Secret,
    fields: list[str],
    *,
    iterations: int = DEFAULT_ITERATIONS,
) -> dict[str, Any]:
    """Encrypt individual fields of an embedded label.

    Each listed field's value is replaced with a field-level encryption
    object::

        {"encrypted": true, "algorithm": "AES-256-GCM", "payload": ...,
         "iv": ..., "kdf": ..., "salt"?: ..., "iterations"?: ...}

    whose plaintext is the UTF-8 JSON serialization of the field value.
    Every field gets its own random IV. With a passphrase, one random salt
    is generated for the label and shared by its fields.

    Args:
        specimen: Specimen or JSON-LD dictionary.
        secret: A passphrase (``str``) or a 32-byte key (``bytes``).
        fields: Field names to encrypt (e.g. ``["strain", "custom"]``).
            Fields that are absent or ``None`` are left as they are.
        iterations: PBKDF2 iterations for a passphrase (at least 100,000).

    Returns:
        A new JSON-LD dictionary with the fields encrypted. Use
        :func:`~wols.crypto.decrypt_specimen_fields` to restore it.

    Raises:
        ValueError: If a field name cannot be encrypted.
        WolsEncryptionError: If the key or passphrase is invalid, or
            encryption fails.
    """
    for field in fields:
        if field not in ENCRYPTABLE_FIELDS:
            raise ValueError(
                f"Invalid field '{field}'. "
                f"Valid fields: {', '.join(sorted(ENCRYPTABLE_FIELDS))}"
            )

    from wols.models.specimen import Specimen

    data = (
        specimen.to_dict()
        if isinstance(specimen, Specimen)
        else copy.deepcopy(specimen)
    )

    targets = [f for f in dict.fromkeys(fields) if data.get(f) is not None]
    if not targets:
        return data

    material = prepare_key(secret, iterations)
    for field in targets:
        data[field] = seal(_compact_json(data[field]), material).to_field_object()
    return data
