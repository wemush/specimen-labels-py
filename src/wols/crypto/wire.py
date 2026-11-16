"""Encrypted format wire encoding (WOLS v1.3.0).

URL form::

    wemush://v1/encrypted/{id}?e=&iv=&kdf=pbkdf2|raw[&salt=&i=][&sig=]

Field-level form (replaces a field's value inside an embedded label)::

    {"encrypted": true, "algorithm": "AES-256-GCM", "payload": e, "iv": iv,
     "kdf": kdf, "salt"?: salt, "iterations"?: i}

Field-level ciphertexts authenticate the additional data
``f"{label_id}\\n{field}"`` (see :func:`wols.crypto._aead.field_aad`); the URL
form uses none and instead checks the decrypted ``id``.

All binary values are base64url without padding. Padded input is accepted
when decoding. This module only parses and builds the format; it does not
need the ``cryptography`` package except for :func:`derive_key`.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qsl, quote, unquote_to_bytes, urlsplit

from wols.constants import ID_PREFIX
from wols.exceptions import WolsEncryptionError

ALGORITHM = "AES-256-GCM"
"""The only algorithm defined by the encrypted format."""

KEY_LENGTH = 32
IV_LENGTH = 12
TAG_LENGTH = 16
SALT_LENGTH = 16
"""Salt length used when generating. The spec minimum is 16 bytes."""

DEFAULT_ITERATIONS = 600_000
"""PBKDF2 iterations used when generating (OWASP guidance for
PBKDF2-HMAC-SHA256). Labels are printed with public ciphertext, so the default
favors resistance to offline guessing. Each passphrase scan costs roughly
0.1 s on a desktop and more on phones. Pass ``iterations=100_000`` (the spec
minimum, ``MIN_GENERATE_ITERATIONS``) when scan speed matters more."""

MIN_GENERATE_ITERATIONS = 100_000
MIN_DECODE_ITERATIONS = 10_000
"""Decoders MUST reject PBKDF2 iteration counts below this value."""

MAX_DECODE_ITERATIONS = 10_000_000
"""Decoders MUST reject more PBKDF2 iterations than this, per derivation and
in total for one field-level label, so a crafted label cannot stall the
decoder. Generators never exceed it either."""

_MAX_ITERATION_DIGITS = len(str(MAX_DECODE_ITERATIONS))

ENCRYPTED_URL_SCHEMES = frozenset({"wemush", "web+wemush"})
SUPPORTED_KDFS: tuple[str, ...] = ("pbkdf2", "raw")

type Kdf = Literal["pbkdf2", "raw"]
type Secret = str | bytes | RawKey
"""A passphrase (``str``, selects ``kdf=pbkdf2``), or a 32-byte key as
``bytes`` or :class:`RawKey` (selects ``kdf=raw``)."""

# Matched with fullmatch: "$" alone would also accept a trailing newline.
_B64URL_RE = re.compile(r"[A-Za-z0-9_-]*={0,2}")
_B64STD_RE = re.compile(r"[A-Za-z0-9+/]*={0,2}")


class RawKey:
    """An explicit 32-byte AES-256 key, which selects ``kdf=raw``.

    Since wols 1.3.0 a ``str`` secret is always a passphrase. Wrap a key in
    ``RawKey`` to say unambiguously that it is a raw key, including a key
    stored as base64 text (the wols 1.2 convention). A ``RawKey`` is
    accepted wherever a secret is: :func:`~wols.crypto.encrypt_specimen`,
    :func:`~wols.crypto.encrypt_specimen_fields`,
    :func:`~wols.crypto.decrypt_specimen`,
    :func:`~wols.crypto.decrypt_specimen_fields`, and
    :func:`~wols.crypto.decrypt_specimen_bytes`, including with
    ``allow_legacy=True``. It behaves exactly like passing the 32 key bytes.

    Args:
        key: The key as 32 bytes (``bytes``, ``bytearray``, or
            ``memoryview``), or as standard base64 or base64url text that
            decodes to 32 bytes. Padding is optional and surrounding
            whitespace is ignored. A string mixing the two alphabets is
            refused.

    Raises:
        WolsEncryptionError: ``INVALID_KEY`` if the value is not 32 bytes,
            is not valid base64 or base64url, or has an unsupported type.

    Example:
        >>> key = RawKey(os.urandom(32))
        >>> key = RawKey("q83vEjRWeJCrze8SNFZ4kKvN7xI0VniQq83vEjRWeJA=")
        >>> url = encrypt_specimen(specimen, key)  # kdf=raw
    """

    __slots__ = ("_key",)

    def __init__(self, key: bytes | bytearray | memoryview | str) -> None:
        if isinstance(key, str):
            key_bytes = _decode_key_text(key)
        elif isinstance(key, bytes | bytearray | memoryview):
            key_bytes = bytes(key)
        else:
            raise WolsEncryptionError(
                message="RawKey takes 32 bytes or base64/base64url text, got "
                f"{type(key).__name__}",
                code="INVALID_KEY",
            )
        if len(key_bytes) != KEY_LENGTH:
            raise WolsEncryptionError(
                message=f"Key must be {KEY_LENGTH} bytes, got {len(key_bytes)}",
                code="INVALID_KEY",
            )
        self._key = key_bytes

    @property
    def key(self) -> bytes:
        """The 32 key bytes."""
        return self._key

    def __bytes__(self) -> bytes:
        return self._key

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RawKey):
            return NotImplemented
        return hmac.compare_digest(self._key, other._key)

    def __hash__(self) -> int:
        return hash((RawKey, self._key))

    def __repr__(self) -> str:
        # Never show key material.
        return f"RawKey(<{KEY_LENGTH} bytes>)"


def _decode_key_text(text: str) -> bytes:
    """Decode standard base64 or base64url key text, padding optional."""
    stripped = text.strip()
    if _B64STD_RE.fullmatch(stripped):
        altchars = None
    elif _B64URL_RE.fullmatch(stripped):
        altchars = b"-_"
    else:
        raise WolsEncryptionError(
            message="RawKey text is not valid base64 or base64url",
            code="INVALID_KEY",
        )
    unpadded = stripped.rstrip("=")
    try:
        return base64.b64decode(
            unpadded + "=" * (-len(unpadded) % 4), altchars=altchars, validate=True
        )
    except (binascii.Error, ValueError) as e:
        raise WolsEncryptionError(
            message=f"RawKey text is not valid base64 or base64url: {e}",
            code="INVALID_KEY",
        ) from e


_DECIMAL_RE = re.compile(r"[0-9]+")
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def b64url_encode(data: bytes) -> str:
    """Encode bytes as base64url without padding (RFC 4648 section 5)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str, *, name: str = "value") -> bytes:
    """Decode base64url, with or without padding.

    Raises:
        WolsEncryptionError: ``INVALID_PARAMETER`` if the value is not
            base64url.
    """
    if not isinstance(value, str) or not _B64URL_RE.fullmatch(value):
        raise WolsEncryptionError(
            message=f"'{name}' is not valid base64url",
            code="INVALID_PARAMETER",
        )
    unpadded = value.rstrip("=")
    try:
        return base64.urlsafe_b64decode(unpadded + "=" * (-len(unpadded) % 4))
    except (binascii.Error, ValueError) as e:
        raise WolsEncryptionError(
            message=f"'{name}' is not valid base64url: {e}",
            code="INVALID_PARAMETER",
        ) from e


def derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    """Derive a 256-bit key with PBKDF2-HMAC-SHA256.

    The passphrase is normalized to Unicode NFC and then encoded as UTF-8,
    so the same passphrase typed on different platforms (for example ``ü``
    as one code point or as ``u`` plus a combining diaeresis) derives the
    same key.

    Args:
        passphrase: Passphrase.
        salt: Per-label random salt.
        iterations: PBKDF2 iteration count.

    Returns:
        32-byte key.
    """
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except ImportError as e:  # pragma: no cover - exercised without extra
        raise ImportError(
            "Crypto module not installed. Install with: pip install wols\\[crypto]"
        ) from e

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(unicodedata.normalize("NFC", passphrase).encode("utf-8"))


@dataclass(frozen=True)
class EncryptedPayload:
    """Decoded AES-256-GCM payload and key-derivation parameters.

    Attributes:
        ciphertext: Ciphertext with the 16-byte GCM tag appended.
        iv: 12-byte IV.
        kdf: ``"pbkdf2"`` or ``"raw"``.
        salt: PBKDF2 salt (``kdf="pbkdf2"`` only).
        iterations: PBKDF2 iteration count (``kdf="pbkdf2"`` only).
    """

    ciphertext: bytes
    iv: bytes
    kdf: Kdf
    salt: bytes | None = None
    iterations: int | None = None

    def to_field_object(self) -> dict[str, Any]:
        """Build a field-level encryption object."""
        obj: dict[str, Any] = {
            "encrypted": True,
            "algorithm": ALGORITHM,
            "payload": b64url_encode(self.ciphertext),
            "iv": b64url_encode(self.iv),
            "kdf": self.kdf,
        }
        if self.salt is not None:
            obj["salt"] = b64url_encode(self.salt)
        if self.iterations is not None:
            obj["iterations"] = self.iterations
        return obj


@dataclass(frozen=True)
class EncryptedLabel:
    """A parsed encrypted-format URL.

    Attributes:
        id: Specimen ID suffix from the URL path (without ``wemush:``).
        payload: Ciphertext and key-derivation parameters.
        signature: Detached signature (``sig``), if present. It is not
            verified and is not part of decryption.
    """

    id: str
    payload: EncryptedPayload
    signature: str | None = None

    @property
    def specimen_id(self) -> str:
        """The full specimen ID the plaintext must carry."""
        return f"{ID_PREFIX}:{self.id}"

    def to_url(self) -> str:
        """Build the ``wemush://v1/encrypted/...`` URL.

        The ID suffix is percent-encoded as UTF-8 in a single path segment
        (every character except unreserved ASCII is escaped).
        """
        p = self.payload
        query = f"e={b64url_encode(p.ciphertext)}&iv={b64url_encode(p.iv)}&kdf={p.kdf}"
        if p.salt is not None:
            query += f"&salt={b64url_encode(p.salt)}"
        if p.iterations is not None:
            query += f"&i={p.iterations}"
        if self.signature is not None:
            query += f"&sig={quote(self.signature, safe='')}"
        return f"wemush://v1/encrypted/{quote(self.id, safe='')}?{query}"


def _parse_iterations(value: object, *, name: str) -> int:
    if isinstance(value, str) and _DECIMAL_RE.fullmatch(value):
        # Bound the length before int(): very long digit strings would hit
        # Python's int conversion limit and raise a bare ValueError.
        if len(value.lstrip("0")) > _MAX_ITERATION_DIGITS:
            raise WolsEncryptionError(
                message=f"PBKDF2 iteration count in '{name}' exceeds the decoder "
                f"limit of {MAX_DECODE_ITERATIONS}",
                code="EXCESSIVE_ITERATIONS",
            )
        iterations = int(value)
    elif isinstance(value, int) and not isinstance(value, bool):
        iterations = value
    else:
        raise WolsEncryptionError(
            message=f"'{name}' must be a decimal integer, got {value!r}",
            code="INVALID_PARAMETER",
        )
    if iterations < MIN_DECODE_ITERATIONS:
        raise WolsEncryptionError(
            message=f"PBKDF2 iteration count {iterations} is below the minimum "
            f"of {MIN_DECODE_ITERATIONS}",
            code="INSUFFICIENT_ITERATIONS",
        )
    if iterations > MAX_DECODE_ITERATIONS:
        raise WolsEncryptionError(
            message=f"PBKDF2 iteration count {iterations} exceeds the decoder "
            f"limit of {MAX_DECODE_ITERATIONS}",
            code="EXCESSIVE_ITERATIONS",
        )
    return iterations


def build_payload(
    *,
    kdf: object,
    ciphertext: object,
    iv: object,
    salt: object,
    iterations: object,
    names: dict[str, str],
) -> EncryptedPayload:
    """Validate raw wire values and decode them into an EncryptedPayload.

    Shared by the URL and field-level forms. ``names`` maps the logical
    names (``ciphertext``, ``iv``, ``salt``, ``iterations``) to the
    parameter names used by the form, for error messages.

    Raises:
        WolsEncryptionError: With code ``UNSUPPORTED_KDF``,
            ``MISSING_PARAMETER``, ``UNEXPECTED_PARAMETER``,
            ``INSUFFICIENT_ITERATIONS``, ``EXCESSIVE_ITERATIONS``, or
            ``INVALID_PARAMETER``.
    """
    if kdf not in SUPPORTED_KDFS:
        raise WolsEncryptionError(
            message=f"Unsupported kdf {kdf!r}. Supported: {', '.join(SUPPORTED_KDFS)}",
            code="UNSUPPORTED_KDF",
        )
    for logical, value in (("ciphertext", ciphertext), ("iv", iv)):
        if value is None:
            raise WolsEncryptionError(
                message=f"Missing required parameter '{names[logical]}'",
                code="MISSING_PARAMETER",
            )

    salt_bytes: bytes | None = None
    iteration_count: int | None = None
    if kdf == "pbkdf2":
        for logical, value in (("salt", salt), ("iterations", iterations)):
            if value is None:
                raise WolsEncryptionError(
                    message=f"Missing required parameter '{names[logical]}' "
                    "for kdf=pbkdf2",
                    code="MISSING_PARAMETER",
                )
        iteration_count = _parse_iterations(iterations, name=names["iterations"])
        salt_bytes = b64url_decode(salt, name=names["salt"])  # type: ignore[arg-type]
        if not salt_bytes:
            raise WolsEncryptionError(
                message=f"'{names['salt']}' must not be empty",
                code="INVALID_PARAMETER",
            )
    else:
        for logical, value in (("salt", salt), ("iterations", iterations)):
            if value is not None:
                raise WolsEncryptionError(
                    message=f"Parameter '{names[logical]}' must be omitted "
                    "when kdf=raw",
                    code="UNEXPECTED_PARAMETER",
                )

    iv_bytes = b64url_decode(iv, name=names["iv"])  # type: ignore[arg-type]
    if len(iv_bytes) != IV_LENGTH:
        raise WolsEncryptionError(
            message=f"'{names['iv']}' must be {IV_LENGTH} bytes, got {len(iv_bytes)}",
            code="INVALID_PARAMETER",
        )
    ct_bytes = b64url_decode(ciphertext, name=names["ciphertext"])  # type: ignore[arg-type]
    if len(ct_bytes) < TAG_LENGTH:
        raise WolsEncryptionError(
            message=f"'{names['ciphertext']}' is shorter than the "
            f"{TAG_LENGTH}-byte authentication tag",
            code="INVALID_PARAMETER",
        )

    return EncryptedPayload(
        ciphertext=ct_bytes,
        iv=iv_bytes,
        kdf=kdf,  # type: ignore[arg-type]
        salt=salt_bytes,
        iterations=iteration_count,
    )


_URL_NAMES = {"ciphertext": "e", "iv": "iv", "salt": "salt", "iterations": "i"}
_FIELD_NAMES = {
    "ciphertext": "payload",
    "iv": "iv",
    "salt": "salt",
    "iterations": "iterations",
}


def is_encrypted_url(text: str) -> bool:
    """Return True if text looks like an encrypted-format URL."""
    try:
        parts = urlsplit(text.strip())
    except ValueError:
        return False
    path = [p for p in (parts.netloc + parts.path).split("/") if p]
    return (
        parts.scheme in ENCRYPTED_URL_SCHEMES
        and len(path) >= 2
        and path[:2] == ["v1", "encrypted"]
    )


def _decode_id_segment(segment: str) -> str:
    """Percent-decode the ID path segment as UTF-8, strictly.

    ``+`` is a literal character (this is a path, not a form). A ``%`` not
    followed by two hex digits, or escapes that decode to invalid UTF-8, are
    rejected rather than passed through or replaced.
    """
    if _BAD_PERCENT_RE.search(segment):
        raise WolsEncryptionError(
            message="Encrypted URL ID has a malformed percent-escape",
            code="INVALID_ENCODING",
        )
    try:
        return unquote_to_bytes(segment).decode("utf-8")
    except UnicodeDecodeError as e:
        raise WolsEncryptionError(
            message=f"Encrypted URL ID is not valid UTF-8: {e}",
            code="INVALID_ENCODING",
        ) from e


def parse_encrypted_url(url: str) -> EncryptedLabel:
    """Parse and validate an encrypted-format URL without decrypting it.

    Accepts the ``wemush://`` and ``web+wemush://`` schemes.

    Args:
        url: ``wemush://v1/encrypted/{id}?e=&iv=&kdf=...``

    Returns:
        The parsed label.

    Raises:
        WolsEncryptionError: ``INVALID_URL`` for a malformed URL,
            ``INVALID_ENCODING`` for a malformed percent-escape or invalid
            UTF-8 in the ID, ``LEGACY_FORMAT`` when ``kdf`` is absent (pre-1.3.0 label), or
            any code raised by :func:`build_payload`.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError as e:
        raise WolsEncryptionError(
            message=f"Invalid encrypted URL: {e}", code="INVALID_URL"
        ) from e

    if parts.scheme not in ENCRYPTED_URL_SCHEMES:
        raise WolsEncryptionError(
            message=f"Invalid encrypted URL scheme '{parts.scheme}'. Expected "
            "wemush:// or web+wemush://",
            code="INVALID_URL",
        )
    path = [p for p in (parts.netloc + parts.path).split("/") if p]
    if len(path) != 3 or path[:2] != ["v1", "encrypted"]:
        raise WolsEncryptionError(
            message="Invalid encrypted URL path. Expected v1/encrypted/{id}",
            code="INVALID_URL",
        )
    id_suffix = _decode_id_segment(path[2])
    if not id_suffix:
        raise WolsEncryptionError(
            message="Encrypted URL is missing the specimen ID", code="INVALID_URL"
        )

    try:
        pairs = parse_qsl(parts.query, keep_blank_values=True, errors="strict")
    except UnicodeDecodeError as e:
        raise WolsEncryptionError(
            message=f"Encrypted URL query is not valid UTF-8: {e}",
            code="INVALID_ENCODING",
        ) from e
    params: dict[str, str] = {}
    for key, value in pairs:
        if key in params:
            raise WolsEncryptionError(
                message=f"Duplicate parameter '{key}'", code="INVALID_PARAMETER"
            )
        params[key] = value

    if "kdf" not in params:
        raise WolsEncryptionError(
            message="Encrypted URL has no 'kdf' parameter. Labels without kdf "
            "predate WOLS 1.3.0 and are not supported",
            code="LEGACY_FORMAT",
        )

    payload = build_payload(
        kdf=params["kdf"],
        ciphertext=params.get("e"),
        iv=params.get("iv"),
        salt=params.get("salt"),
        iterations=params.get("i"),
        names=_URL_NAMES,
    )
    return EncryptedLabel(id=id_suffix, payload=payload, signature=params.get("sig"))


def parse_encrypted_field(obj: dict[str, Any], *, field: str) -> EncryptedPayload:
    """Parse and validate a field-level encryption object.

    Raises:
        WolsEncryptionError: ``UNSUPPORTED_ALGORITHM`` for an algorithm other
            than AES-256-GCM, ``LEGACY_FORMAT`` when ``kdf`` is absent, or any
            code raised by :func:`build_payload`.
    """
    if obj.get("algorithm") != ALGORITHM:
        raise WolsEncryptionError(
            message=f"Field '{field}': unsupported algorithm "
            f"{obj.get('algorithm')!r}, expected {ALGORITHM}",
            code="UNSUPPORTED_ALGORITHM",
        )
    names = {k: f"{field}.{v}" for k, v in _FIELD_NAMES.items()}
    if "kdf" not in obj:
        raise WolsEncryptionError(
            message=f"Field '{field}' has no 'kdf'. Field objects without kdf "
            "predate WOLS 1.3.0 and are not supported",
            code="LEGACY_FORMAT",
        )
    return build_payload(
        kdf=obj["kdf"],
        ciphertext=obj.get("payload"),
        iv=obj.get("iv"),
        salt=obj.get("salt"),
        iterations=obj.get("iterations"),
        names=names,
    )
