"""Compact URL rules shared by parsing and signing (WOLS 1.5.0-rc.2).

The decoding rules live here so that :func:`wols.parse_compact_url` and the
compact URL signature checks in :mod:`wols.crypto.signature` read a URL the
same way.
"""

from __future__ import annotations

import re

__all__ = [
    "COMPACT_URL_PREFIX",
    "REGISTERED_PARAMETERS",
    "InvalidEncoding",
    "is_compact_shape",
    "percent_decode",
    "unwrap_wols_url",
]

COMPACT_URL_PREFIX = "wemush://v1/"
"""The only prefix a signed compact URL may have."""

ENCRYPTED_URL_PREFIX = "wemush://v1/encrypted/"

REGISTERED_PARAMETERS: tuple[str, ...] = (
    "s",
    "ty",
    "st",
    "t",
    "b",
    "sn",
    "sg",
    "td",
    "sig",
)
"""The compact URL parameter registry, in registry order (WOLS 1.5.0-rc.2).

A name is never reassigned. Parameters defined outside the specification
use an ``x-`` prefix.
"""

_HEX = frozenset("0123456789abcdefABCDEF")
_HANDLER_RE = re.compile(r"https://[^/?#]+/wols/(.+)", re.DOTALL)


class InvalidEncoding(ValueError):
    """A malformed percent escape, or an escape that isn't valid UTF-8."""


def percent_decode(text: str, *, plus_as_space: bool = False) -> str:
    """Percent-decode ``text`` as UTF-8, strictly.

    Unlike :func:`urllib.parse.unquote`, a malformed escape (``%zz``, a
    trailing ``%2``) or bytes that aren't valid UTF-8 raise
    :class:`InvalidEncoding` instead of passing through.

    Args:
        text: The encoded text.
        plus_as_space: Decode ``+`` as a space, as compact URL parameter
            values do. In the ID path segment ``+`` is a literal character.
    """
    if plus_as_space:
        text = text.replace("+", " ")
    if "%" not in text:
        return text
    out = bytearray()
    i = 0
    while i < len(text):
        char = text[i]
        if char == "%":
            pair = text[i + 1 : i + 3]
            if len(pair) != 2 or not set(pair) <= _HEX:
                raise InvalidEncoding(f"malformed percent escape at position {i}")
            out.append(int(pair, 16))
            i += 3
        else:
            try:
                out += char.encode("utf-8")
            except UnicodeEncodeError as e:  # a lone surrogate
                raise InvalidEncoding(str(e)) from e
            i += 1
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError as e:
        raise InvalidEncoding(f"escape is not valid UTF-8: {e}") from e


def is_compact_shape(url: str) -> bool:
    """True when ``url`` has the shape of a signable compact URL.

    That is exactly ``wemush://v1/`` followed by one non-empty path segment
    with no ``/``, and not an encrypted URL (``wemush://v1/encrypted/...``).
    A compact ID that is literally ``encrypted`` (``wemush://v1/encrypted?...``)
    has the compact shape.
    """
    if not url.startswith(COMPACT_URL_PREFIX) or url.startswith(ENCRYPTED_URL_PREFIX):
        return False
    rest = url[len(COMPACT_URL_PREFIX) :]
    segment = rest.split("?", 1)[0]
    return segment != "" and "/" not in segment


def unwrap_wols_url(text: str) -> str | None:
    """Unwrap a scanned URL to the ``wemush://v1/`` URL it carries, or None.

    The optional step before compact URL verification (WOLS 1.5.0-rc.2). It
    applies exactly two transforms, in this order:

    1. ``https://{host}/wols/{x}``: ``{x}`` is percent-decoded exactly once.
    2. A leading ``web+`` is removed from ``web+wemush://v1/...``.

    The result is returned only if it starts with ``wemush://v1/``. Nothing
    else is rewritten: an outer query is never merged in, and ``{x}`` is
    never decoded twice. An unwrap can make a signature fail as ``invalid``
    but never make it ``valid``.

    Example:
        >>> unwrap_wols_url("web+wemush://v1/abc?s=POSTR&sig=w1.AAAA")
        'wemush://v1/abc?s=POSTR&sig=w1.AAAA'
        >>> unwrap_wols_url("https://example.com/v1/abc?s=POSTR") is None
        True
    """
    if not isinstance(text, str):
        return None
    match = _HANDLER_RE.fullmatch(text)
    if match is not None:
        try:
            text = percent_decode(match.group(1))
        except InvalidEncoding:
            return None
    if text.startswith("web+" + COMPACT_URL_PREFIX):
        text = text[len("web+") :]
    return text if text.startswith(COMPACT_URL_PREFIX) else None
