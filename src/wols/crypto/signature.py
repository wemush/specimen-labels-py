"""Ed25519 label signatures (WOLS v1.4.0).

Optional module - requires: pip install wols[crypto]

A signature lets a verifier check that a label's bytes were signed with a
private key the verifier already trusts, and that they haven't changed
since. Two forms can be signed:

- **Embedded labels** (JSON-LD) carry the token in the top-level
  ``signature`` member. The signed body is the RFC 8785 (JCS) canonical form
  of the label as parsed, without that member.
- **Encrypted URLs** carry the token in a final ``sig`` parameter. The
  signed body is the exact URL text before ``&sig=``.

The token is ``{kid}.{signature}``: a key identifier and the 64-byte Ed25519
signature in unpadded base64url. Ed25519 signs::

    "WOLS-SIG-v1" LF form LF kid LF body

Keys come only from a trust store the caller supplies, never from the label.
Verification returns one of five statuses and never raises for a bad
signature. Decoding never verifies, and verifying never decodes.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from wols.crypto.jcs import CanonicalizationError, canonicalize, parse_json
from wols.exceptions import WolsSignatureError, WolsTrustStoreError

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    from wols.models.specimen import Specimen

__all__ = [
    "ED25519",
    "FORM_EMBEDDED",
    "FORM_ENCRYPTED_URL",
    "SIGNING_DOMAIN",
    "SignatureStatus",
    "TrustStore",
    "TrustedKey",
    "VerificationResult",
    "sign_encrypted_url",
    "sign_specimen",
    "trust_store_from_key_set",
    "verify_embedded",
    "verify_encrypted_url",
    "verify_specimen",
]

SIGNING_DOMAIN = "WOLS-SIG-v1"
"""The first line of every signing input."""

FORM_EMBEDDED = "embedded"
FORM_ENCRYPTED_URL = "encrypted-url"
ED25519 = "Ed25519"
"""The only signature algorithm in WOLS 1.4.0."""

ENCRYPTED_URL_PREFIX = "wemush://v1/encrypted/"
"""Only URLs that start with this prefix can be signed or verified."""

PUBLIC_KEY_LENGTH = 32
PRIVATE_KEY_LENGTH = 32
SIGNATURE_LENGTH = 64

# RFC 8032 group order. A signature's S value must be less than this.
_ED25519_L = 2**252 + 27742317777372353535851937790883648493

# Matched with fullmatch, so a trailing newline doesn't slip through.
_KID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_TOKEN_RE = re.compile(r"([A-Za-z0-9_-]{1,64})\.([A-Za-z0-9_-]{86})")
_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


class SignatureStatus(StrEnum):
    """The outcome of verifying a label.

    Only ``VALID`` means the label is signed, authentic, and unmodified.
    """

    UNSIGNED = "unsigned"
    """No top-level ``signature`` member, or no ``sig`` parameter."""

    MALFORMED = "malformed"
    """The label text isn't an I-JSON object (signed or not), or a signature
    is present but the token or URL breaks a rule."""

    UNKNOWN_KID = "unknown-kid"
    """The token is well-formed, but its kid isn't in the trust store.
    "Signed by an unknown key", never valid."""

    INVALID = "invalid"
    """The kid is in the trust store, but the signature doesn't verify under
    its entry (including an unusable entry that reached verification)."""

    VALID = "valid"
    """The signature verifies under the trust store's key for the kid."""


@dataclass(frozen=True)
class VerificationResult:
    """The result of :func:`verify_specimen`.

    Attributes:
        status: The verification status.
        kid: The token's key identifier. Always set for ``VALID``; also set
            for ``UNKNOWN_KID`` and ``INVALID`` for diagnostics. ``None`` for
            ``UNSIGNED`` and ``MALFORMED``.
        reason: Human-readable detail for every status except ``VALID``.
    """

    status: SignatureStatus
    kid: str | None = None
    reason: str | None = None

    @property
    def valid(self) -> bool:
        """True only for ``SignatureStatus.VALID``."""
        return self.status is SignatureStatus.VALID


@dataclass(frozen=True)
class TrustedKey:
    """A public key in a trust store.

    The key is checked when it is built: an algorithm other than
    ``"Ed25519"``, a key that isn't exactly 32 bytes, or 32 bytes that don't
    decode to a curve point (RFC 8032 section 5.1.3) is a configuration
    error and raises :class:`~wols.WolsTrustStoreError`. An unusable entry
    that reaches verification anyway (for example a trust store holding
    something other than a ``TrustedKey``) verifies as ``INVALID``.

    Attributes:
        public_key: The 32-byte Ed25519 public key (the encoded point).
        alg: The algorithm. Only ``"Ed25519"`` is defined.
    """

    public_key: bytes
    alg: str = ED25519

    def __post_init__(self) -> None:
        problem = _key_problem(self.alg, self.public_key)
        if problem is not None:
            raise WolsTrustStoreError(message=problem)
        object.__setattr__(self, "public_key", bytes(self.public_key))


type TrustStore = Mapping[str, TrustedKey]
"""Maps each kid to its public key. Built by the caller, never from a label."""


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------


# Edwards25519 (RFC 8032 section 5.1): field prime and curve constant.
_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _is_curve_point(encoded: bytes) -> bool:
    """Decode a 32-byte point as RFC 8032 section 5.1.3 specifies.

    ``cryptography`` accepts any 32 bytes as a public key, so off-curve
    entries are caught here.
    """
    n = int.from_bytes(encoded, "little")
    x_sign = n >> 255
    y = n & ((1 << 255) - 1)
    if y >= _P:
        return False
    u = (y * y - 1) % _P
    v = (_D * y * y + 1) % _P
    x2 = u * pow(v, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
        if (x * x - x2) % _P != 0:
            return False
    return not (x == 0 and x_sign == 1)


def _key_problem(alg: object, public_key: object) -> str | None:
    """Why a trust store entry is unusable, or None if it is usable."""
    if alg != ED25519:
        return f"trust store algorithm must be {ED25519!r}, got {alg!r}"
    if not isinstance(public_key, bytes | bytearray):
        return "trust store public key must be bytes"
    if len(public_key) != PUBLIC_KEY_LENGTH:
        return (
            f"Ed25519 public key must be {PUBLIC_KEY_LENGTH} bytes, "
            f"got {len(public_key)}"
        )
    if not _is_curve_point(bytes(public_key)):
        return "Ed25519 public key is not a point on the curve"
    return None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _signing_input(form: str, kid: str, body: bytes) -> bytes:
    return f"{SIGNING_DOMAIN}\n{form}\n{kid}\n".encode("ascii") + body


class _Malformed(Exception):
    """Internal: the label is malformed for verification."""


def _parse_token(token: object) -> tuple[str, bytes]:
    if not isinstance(token, str):
        raise _Malformed("signature token is not a string")
    match = _TOKEN_RE.fullmatch(token)
    if match is None:
        raise _Malformed(
            "signature token must be {kid}.{signature}: a kid of 1-64 "
            "characters [A-Za-z0-9_-] and 86 base64url characters"
        )
    kid, encoded = match.groups()
    try:
        raw = base64.urlsafe_b64decode(encoded + "==")
    except (binascii.Error, ValueError) as e:  # pragma: no cover - regex guards
        raise _Malformed(f"signature is not base64url: {e}") from e
    if len(raw) != SIGNATURE_LENGTH or _b64url(raw) != encoded:
        raise _Malformed("signature is not canonical base64url (unused bits set)")
    return kid, raw


# ---------------------------------------------------------------------------
# Embedded labels
# ---------------------------------------------------------------------------


def _embedded_body(label: Mapping[str, Any]) -> bytes:
    """JCS of the label without its top-level ``signature``."""
    unsigned = {k: v for k, v in label.items() if k != "signature"}
    return canonicalize(unsigned).encode("utf-8")


def _label_text(label: str | bytes) -> str:
    if isinstance(label, bytes):
        return label.decode("utf-8")  # strict: invalid UTF-8 raises
    return label


# ---------------------------------------------------------------------------
# Encrypted URLs
# ---------------------------------------------------------------------------


def _url_params(url: str) -> list[str]:
    q = url.find("?")
    return url[q + 1 :].split("&") if q != -1 else []


def _param_name(param: str) -> str:
    return param.split("=", 1)[0]


def _check_url_text(url: str) -> None:
    """The rules a signed URL and an unsigned URL to be signed share."""
    if any(not 0x21 <= ord(c) <= 0x7E for c in url):
        raise _Malformed(
            "URL contains a character outside U+0021..U+007E; spaces and "
            "non-ASCII characters must be percent-encoded"
        )
    if "#" in url:
        raise _Malformed("URL has a fragment")
    if not url.startswith(ENCRYPTED_URL_PREFIX):
        raise _Malformed(f"URL doesn't start with {ENCRYPTED_URL_PREFIX}")


def _split_signed_url(url: str) -> tuple[str, str] | None:
    """Return ``(body, token)``, or None when the URL has no ``sig``.

    Raises:
        _Malformed: When the URL breaks a rule.
    """
    params = _url_params(url)
    names = [_param_name(p) for p in params]
    if "sig" not in names:
        return None
    _check_url_text(url)
    if names.count("sig") != 1:
        raise _Malformed("URL has more than one 'sig' parameter")
    if names[-1] != "sig":
        raise _Malformed("'sig' must be the last parameter")
    if len(params) < 2:
        raise _Malformed("'sig' must not be the only parameter")
    last = params[-1]
    if not last.startswith("sig="):
        raise _Malformed("'sig' parameter has no value")
    token = last[len("sig=") :]
    return url[: len(url) - len("&sig=") - len(token)], token


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


def _private_key(private_key: bytes | Ed25519PrivateKey) -> Ed25519PrivateKey:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
    except ImportError as e:  # pragma: no cover - exercised without extra
        raise ImportError(
            "Crypto module not installed. Install with: pip install wols\\[crypto]"
        ) from e
    if isinstance(private_key, Ed25519PrivateKey):
        return private_key
    if not isinstance(private_key, bytes | bytearray):
        raise WolsSignatureError(
            message="private_key must be a 32-byte Ed25519 seed or an "
            "Ed25519PrivateKey",
            code="INVALID_KEY",
        )
    if len(private_key) != PRIVATE_KEY_LENGTH:
        raise WolsSignatureError(
            message=f"Ed25519 private key must be {PRIVATE_KEY_LENGTH} bytes, "
            f"got {len(private_key)}",
            code="INVALID_KEY",
        )
    return Ed25519PrivateKey.from_private_bytes(bytes(private_key))


def _check_kid(kid: object) -> str:
    if not isinstance(kid, str) or not _KID_RE.fullmatch(kid):
        raise WolsSignatureError(
            message=f"kid must be 1-64 characters [A-Za-z0-9_-], got {kid!r}",
            code="INVALID_KID",
        )
    return kid


def _verify_signature(
    kid: str, signature: bytes, message: bytes, trust_store: TrustStore
) -> VerificationResult:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not isinstance(trust_store, Mapping) or kid not in trust_store:
        return VerificationResult(
            SignatureStatus.UNKNOWN_KID,
            kid=kid,
            reason=f"kid {kid!r} is not in the trust store",
        )
    entry = trust_store[kid]
    # A TrustedKey was checked when built; anything else is checked here.
    # An unusable entry is a configuration error and verifies as invalid.
    problem = (
        _key_problem(entry.alg, entry.public_key)
        if isinstance(entry, TrustedKey)
        else "trust store entry is not a TrustedKey"
    )
    if problem is not None:
        return VerificationResult(
            SignatureStatus.INVALID,
            kid=kid,
            reason=f"unusable trust store entry for {kid!r} "
            f"(configuration error): {problem}",
        )
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes(entry.public_key))
    except ValueError:  # pragma: no cover - _key_problem checks the length
        return VerificationResult(
            SignatureStatus.INVALID,
            kid=kid,
            reason=f"unusable trust store entry for {kid!r} (configuration error)",
        )
    # RFC 8032 section 5.1.7: reject S >= L. Checked here as well as by the
    # backend, so a malleated signature is invalid whatever OpenSSL does.
    if int.from_bytes(signature[32:], "little") >= _ED25519_L:
        return VerificationResult(
            SignatureStatus.INVALID,
            kid=kid,
            reason="signature S value is not less than the group order L",
        )
    try:
        public_key.verify(signature, message)
    except InvalidSignature:
        return VerificationResult(
            SignatureStatus.INVALID,
            kid=kid,
            reason="signature does not verify under the trust store's key",
        )
    return VerificationResult(SignatureStatus.VALID, kid=kid)


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def sign_specimen(
    label: str | bytes | Mapping[str, Any] | Specimen,
    private_key: bytes | Ed25519PrivateKey,
    kid: str,
) -> str:
    """Sign an embedded label and return the signed label text.

    Any existing top-level ``signature`` is removed first, so re-signing
    replaces it. The body is the RFC 8785 (JCS) canonical form of the label
    without ``signature``; the token is then stored in ``signature``. The
    result is compact JSON in the label's member order with ``signature``
    last. It is exactly the object that was signed, so it verifies after
    any whitespace or member-order change.

    Args:
        label: Embedded label text (``str`` or UTF-8 ``bytes``), a parsed
            JSON object, or a :class:`~wols.Specimen` (signed as
            :func:`wols.to_json` serializes it).
        private_key: The 32-byte Ed25519 seed, or an ``Ed25519PrivateKey``.
        kid: The key identifier verifiers will look up, 1-64 characters
            from ``[A-Za-z0-9_-]``.

    Returns:
        The signed label as JSON text.

    Raises:
        WolsSignatureError: ``INVALID_KID`` or ``INVALID_KEY`` for a bad
            kid or key; ``INVALID_LABEL`` when the label isn't a JSON object,
            repeats a member name, or holds a lone surrogate, a non-finite
            number, or a non-JSON value.
    """
    import json

    from wols.models.specimen import Specimen

    kid = _check_kid(kid)
    key = _private_key(private_key)

    obj: Any
    if isinstance(label, Specimen):
        from wols.core.serialize import to_json

        label = to_json(label)
    if isinstance(label, str | bytes):
        try:
            parsed = parse_json(_label_text(label))
        except ValueError as e:  # includes UnicodeDecodeError
            raise WolsSignatureError(
                message=f"Label is not valid JSON: {e}", code="INVALID_LABEL"
            ) from e
        if parsed.duplicate_names:
            raise WolsSignatureError(
                message="Label repeats a member name; signers must not "
                "produce duplicate names",
                code="INVALID_LABEL",
            )
        obj = parsed.value
    else:
        obj = label
    if not isinstance(obj, Mapping):
        raise WolsSignatureError(
            message="An embedded label must be a JSON object", code="INVALID_LABEL"
        )

    unsigned = {k: v for k, v in obj.items() if k != "signature"}
    try:
        body = canonicalize(unsigned).encode("utf-8")
    except CanonicalizationError as e:
        raise WolsSignatureError(
            message=f"Label can't be signed: {e}", code="INVALID_LABEL"
        ) from e

    signature = key.sign(_signing_input(FORM_EMBEDDED, kid, body))
    signed = {**unsigned, "signature": f"{kid}.{_b64url(signature)}"}
    # The values passed canonicalize(), so they are finite JSON values that
    # json.dumps writes back exactly (floats as their shortest repr).
    return json.dumps(
        signed, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def sign_encrypted_url(
    url: str,
    private_key: bytes | Ed25519PrivateKey,
    kid: str,
) -> str:
    """Sign an encrypted URL and return it with ``&sig={token}`` appended.

    The URL is signed byte for byte, exactly as it will be printed. Nothing
    is decoded or re-encoded. Re-serializing the result (reordering or
    re-encoding parameters) breaks the signature.

    Args:
        url: An unsigned ``wemush://v1/encrypted/...`` URL, as produced by
            :func:`wols.crypto.encrypt_specimen`.
        private_key: The 32-byte Ed25519 seed, or an ``Ed25519PrivateKey``.
        kid: The key identifier, 1-64 characters from ``[A-Za-z0-9_-]``.

    Returns:
        The signed URL.

    Raises:
        WolsSignatureError: ``INVALID_KID`` or ``INVALID_KEY`` for a bad kid
            or key; ``ALREADY_SIGNED`` if the URL has a ``sig`` parameter
            (remove it to re-sign); ``INVALID_URL`` if the URL isn't
            printable ASCII, has a fragment, has no query, or doesn't start
            with ``wemush://v1/encrypted/``.
    """
    kid = _check_kid(kid)
    key = _private_key(private_key)
    if not isinstance(url, str):
        raise WolsSignatureError(message="url must be a str", code="INVALID_URL")
    if "sig" in (_param_name(p) for p in _url_params(url)):
        raise WolsSignatureError(
            message="URL already has a 'sig' parameter; remove it to re-sign",
            code="ALREADY_SIGNED",
        )
    try:
        _check_url_text(url)
    except _Malformed as e:
        raise WolsSignatureError(message=str(e), code="INVALID_URL") from e
    q = url.find("?")
    if q == -1 or q == len(url) - 1:
        # Without a query, "&sig=" would land in the path (or follow an
        # empty query) and the result wouldn't verify as signed.
        raise WolsSignatureError(
            message="Encrypted URL has no query parameters", code="INVALID_URL"
        )

    signature = key.sign(_signing_input(FORM_ENCRYPTED_URL, kid, url.encode("ascii")))
    return f"{url}&sig={kid}.{_b64url(signature)}"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _malformed(reason: str) -> VerificationResult:
    return VerificationResult(SignatureStatus.MALFORMED, reason=reason)


def verify_embedded(
    label: str | bytes | Mapping[str, Any], trust_store: TrustStore
) -> VerificationResult:
    """Verify the signature of an embedded label.

    Pass the label text exactly as scanned. A parsed object is accepted too,
    but it must be the raw JSON value, never a value rebuilt from
    :class:`~wols.Specimen`: the body is canonicalized from what was
    received, including members this library doesn't know.

    Checks run in the order the specification fixes. First the label must
    be an I-JSON object: text that isn't JSON, a non-object, a duplicate
    member name at any depth (compared after unescaping), a lone surrogate,
    or a non-finite or overflowing number is ``malformed`` whether or not
    the label is signed. Then ``unsigned``, then the token rules
    (``malformed``), then the trust store (``unknown-kid``), then the
    signature (``invalid`` or ``valid``).

    Args:
        label: Embedded label text (``str`` or UTF-8 ``bytes``), or the raw
            parsed JSON object.
        trust_store: Maps each trusted kid to its key.

    Returns:
        The verification result. Never raises for a bad signature.
    """
    duplicate_names = False
    obj: Any
    if isinstance(label, str | bytes):
        try:
            parsed = parse_json(_label_text(label))
        except ValueError as e:  # includes UnicodeDecodeError
            return _malformed(f"label is not valid JSON: {e}")
        obj = parsed.value
        duplicate_names = parsed.duplicate_names
    else:
        obj = label
    if not isinstance(obj, Mapping):
        return _malformed("label is not a JSON object")
    if duplicate_names:
        return _malformed("label repeats a member name")
    try:
        # The whole label, signature included, must be I-JSON.
        canonicalize(dict(obj))
        body = _embedded_body(obj)
    except CanonicalizationError as e:
        return _malformed(f"label is not I-JSON: {e}")
    if "signature" not in obj:
        return VerificationResult(
            SignatureStatus.UNSIGNED, reason="label has no top-level 'signature'"
        )
    try:
        kid, signature = _parse_token(obj["signature"])
    except _Malformed as e:
        return _malformed(str(e))
    message = _signing_input(FORM_EMBEDDED, kid, body)
    return _verify_signature(kid, signature, message, trust_store)


def verify_encrypted_url(url: str, trust_store: TrustStore) -> VerificationResult:
    """Verify the signature of an encrypted URL.

    The body is the URL exactly as received, up to its final ``&sig=``
    parameter. Nothing is percent-decoded or normalized, so pass the URL as
    scanned, not one rebuilt by a decoder.

    Args:
        url: The encrypted URL, as scanned.
        trust_store: Maps each trusted kid to its key.

    Returns:
        The verification result. Never raises for a bad signature.
    """
    if not isinstance(url, str):
        return _malformed("URL is not a str")
    try:
        split = _split_signed_url(url)
        if split is None:
            return VerificationResult(
                SignatureStatus.UNSIGNED, reason="URL has no 'sig' parameter"
            )
        body, token = split
        kid, signature = _parse_token(token)
    except _Malformed as e:
        return _malformed(str(e))
    message = _signing_input(FORM_ENCRYPTED_URL, kid, body.encode("ascii"))
    return _verify_signature(kid, signature, message, trust_store)


def verify_specimen(
    label: str | bytes | Mapping[str, Any], trust_store: TrustStore
) -> VerificationResult:
    """Verify a label's signature against a trust store.

    Accepts embedded label text, the raw parsed JSON object, or an encrypted
    URL. Text that starts with a URL scheme (such as ``wemush:``) is
    verified as an encrypted URL with :func:`verify_encrypted_url`;
    anything else is verified as an embedded label with
    :func:`verify_embedded`.

    Only ``SignatureStatus.VALID`` means the label is signed, authentic, and
    unmodified. ``UNSIGNED`` is not a failure of verification but a missing
    signature: an application that requires signatures must reject it under
    its own policy. Verification makes no network requests.

    Args:
        label: Embedded label text, a raw parsed JSON object, or an
            encrypted URL, exactly as scanned.
        trust_store: Maps each trusted kid to its key. Build it from sources
            you trust, never from the label.

    Returns:
        The verification result. Never raises for a bad signature.

    Raises:
        TypeError: If given a :class:`~wols.Specimen`. A model rebuilt by
            the library can't be verified; pass the label text instead.

    Example:
        >>> result = verify_specimen(scanned_text, trust_store)
        >>> if result.status is SignatureStatus.VALID:
        ...     print("signed by", result.kid)
    """
    from wols.models.specimen import Specimen

    if isinstance(label, Specimen):
        raise TypeError(
            "verify_specimen() needs the label text or raw JSON object, not a "
            "Specimen: the model doesn't keep every member that was signed"
        )
    if isinstance(label, str | bytes):
        try:
            text = _label_text(label)
        except UnicodeDecodeError as e:
            return _malformed(f"label is not valid UTF-8: {e}")
        if _SCHEME_RE.match(text):
            return verify_encrypted_url(text, trust_store)
        return verify_embedded(text, trust_store)
    return verify_embedded(label, trust_store)


# ---------------------------------------------------------------------------
# Key set documents
# ---------------------------------------------------------------------------


def trust_store_from_key_set(
    document: str | bytes | Mapping[str, Any],
    *,
    on_skip: Callable[[Mapping[str, Any]], None] | None = None,
) -> TrustStore:
    """Build a trust store from a WOLS key set document.

    The document has the shape an issuer MAY publish at
    ``https://{issuer-host}/.well-known/wols-keys.json``::

        {
            "keys": [
                {
                    "kid": "mushoh-2026",
                    "alg": "Ed25519",
                    "publicKey": "<32 bytes, base64url, no padding>",
                }
            ]
        }

    An entry whose ``alg`` isn't ``"Ed25519"`` (compared exactly, so
    ``"ed25519"`` too) is skipped without checking its other members. That
    keeps the format forward-compatible: an issuer can add keys for a later
    algorithm without breaking this verifier. A label signed under a skipped
    entry's kid verifies as ``UNKNOWN_KID``. Members the specification
    doesn't define are ignored.

    This function doesn't fetch anything. Choose the host independently of
    any label, fetch the document over HTTPS yourself, and pass it here.
    Merge stores from several issuers only if their kids don't collide.

    Args:
        document: The key set document, as text or parsed JSON.
        on_skip: Called with each entry skipped for an unsupported
            algorithm, in document order, for example to log it.

    Returns:
        A trust store with one entry per Ed25519 key.

    Raises:
        WolsTrustStoreError: (a ``ValueError``) If the document isn't an
            object with a ``keys`` array, an entry isn't an object with a
            string ``alg``, two Ed25519 entries share a kid, or an Ed25519
            entry is unusable: an invalid kid, or a ``publicKey`` that isn't
            the canonical unpadded base64url of 32 bytes encoding a curve
            point. A damaged Ed25519 entry signals corruption or tampering,
            so the whole document is rejected rather than the key dropped.

    Example:
        >>> store = trust_store_from_key_set(fetched_text, on_skip=log.info)
    """
    import json

    try:
        doc: Any = (
            json.loads(document) if isinstance(document, str | bytes) else document
        )
    except ValueError as e:
        raise WolsTrustStoreError(message=f"key set is not valid JSON: {e}") from e
    keys = doc.get("keys") if isinstance(doc, Mapping) else None
    if not isinstance(keys, list):
        raise WolsTrustStoreError(
            message="key set document must be an object with a 'keys' array"
        )
    store: dict[str, TrustedKey] = {}
    for index, entry in enumerate(keys):
        if not isinstance(entry, Mapping):
            raise WolsTrustStoreError(message=f"keys[{index}] must be an object")
        alg = entry.get("alg")
        if not isinstance(alg, str):
            raise WolsTrustStoreError(message=f"keys[{index}] needs a string 'alg'")
        if alg != ED25519:
            # Unsupported algorithm: skipped, other members unchecked.
            if on_skip is not None:
                on_skip(entry)
            continue
        kid, encoded = entry.get("kid"), entry.get("publicKey")
        if not isinstance(kid, str) or not _KID_RE.fullmatch(kid):
            raise WolsTrustStoreError(message=f"keys[{index}]: invalid kid {kid!r}")
        if not isinstance(encoded, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{43}", encoded
        ):
            raise WolsTrustStoreError(
                message=f"publicKey for {kid!r} is not 32 bytes of base64url"
            )
        public_key = base64.urlsafe_b64decode(encoded + "=")
        if _b64url(public_key) != encoded:
            raise WolsTrustStoreError(
                message=f"publicKey for {kid!r} is not canonical base64url"
            )
        if kid in store:
            raise WolsTrustStoreError(message=f"kid {kid!r} appears more than once")
        try:
            store[kid] = TrustedKey(public_key=public_key, alg=alg)
        except WolsTrustStoreError as e:
            raise WolsTrustStoreError(message=f"key {kid!r}: {e.message}") from e
    return store
