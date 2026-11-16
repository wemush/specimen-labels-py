"""JSON parsing and RFC 8785 canonicalization for WOLS signatures.

WOLS 1.4.0 signs an embedded label as the JSON Canonicalization Scheme
(JCS, RFC 8785) of the label as parsed from its text. Python's :mod:`json`
module differs from the I-JSON model JCS assumes in a few ways, and this
module handles each one explicitly:

- **Numbers**: JCS treats every number as an IEEE 754 double and writes it
  with the ECMAScript ``Number.prototype.toString`` rules. Python parses
  integers exactly, so integers are converted to the nearest double before
  they are written (``9007199254740993`` becomes ``9007199254740992``).
- **Non-finite numbers**: :func:`json.loads` accepts ``NaN`` and
  ``Infinity``, and very large literals parse to infinity. JCS can't write
  them, so they are rejected.
- **Lone surrogates**: :func:`json.loads` accepts ``"\\ud800"``. Such a
  string isn't I-JSON, so it is rejected.
- **Duplicate member names**: :func:`json.loads` silently keeps the last
  one. :func:`parse_json` reports them instead.

This module only needs the standard library.
"""

from __future__ import annotations

import json
import math
from typing import Any

__all__ = ["CanonicalizationError", "ParsedJson", "canonicalize", "parse_json"]

# Integer literals longer than this are parsed straight to a float, so a
# crafted label can't hit Python's int-conversion digit limit. Any integer
# with this many digits is beyond the largest double and becomes infinity.
_MAX_INT_DIGITS = 400


class CanonicalizationError(ValueError):
    """The value can't be canonicalized with RFC 8785 (JCS)."""


class ParsedJson:
    """The result of :func:`parse_json`.

    Attributes:
        value: The parsed JSON value. Integers are ``int``, other numbers
            are ``float``. When a member name is duplicated, the last value
            is kept.
        duplicate_names: True if any object in the text repeats a member
            name.
    """

    __slots__ = ("duplicate_names", "value")

    def __init__(self, value: Any, duplicate_names: bool) -> None:
        self.value = value
        self.duplicate_names = duplicate_names


def parse_json(text: str) -> ParsedJson:
    """Parse JSON text, recording duplicate member names.

    Args:
        text: JSON text.

    Returns:
        The parsed value and whether any member name was duplicated.

    Raises:
        ValueError: If the text isn't JSON (including excessive nesting).
    """
    duplicates = False

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal duplicates
        obj: dict[str, Any] = {}
        for key, value in items:
            if key in obj:
                duplicates = True
            obj[key] = value
        return obj

    def parse_int(literal: str) -> int | float:
        if len(literal) > _MAX_INT_DIGITS:
            return float(literal)
        return int(literal)

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_int=parse_int)
    except RecursionError as e:
        raise ValueError("JSON is nested too deeply") from e
    return ParsedJson(value, duplicates)


def canonicalize(value: Any) -> str:
    """Return the RFC 8785 (JCS) canonical form of a JSON value.

    Args:
        value: A JSON value built from ``dict`` (with ``str`` keys),
            ``list``, ``str``, ``int``, ``float``, ``bool``, and ``None``.

    Returns:
        The canonical JSON text. Encode it as UTF-8 to get the canonical
        bytes.

    Raises:
        CanonicalizationError: For a lone surrogate, a non-finite number,
            a value that isn't JSON, or nesting too deep to process.
    """
    out: list[str] = []
    try:
        _write(value, out)
    except RecursionError as e:
        raise CanonicalizationError("value is nested too deeply") from e
    return "".join(out)


_SHORT_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _write_string(s: str, out: list[str]) -> None:
    out.append('"')
    for ch in s:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            raise CanonicalizationError("string contains a lone surrogate")
        escaped = _SHORT_ESCAPES.get(ch)
        if escaped is not None:
            out.append(escaped)
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')


def _number(x: float) -> str:
    """ECMAScript ``Number::toString`` (RFC 8785 section 3.2.2.3)."""
    if not math.isfinite(x):
        raise CanonicalizationError("number is not finite")
    if x == 0:
        return "0"  # also -0
    sign = "-" if x < 0 else ""
    # repr() gives the shortest digit string that round-trips, as
    # ECMAScript does. Rewrite it into the ECMAScript layout.
    mantissa, _, exp = repr(abs(x)).partition("e")
    int_part, _, frac_part = mantissa.partition(".")
    digits = int_part + frac_part
    n = len(int_part) + (int(exp) if exp else 0)
    stripped = digits.lstrip("0")
    n -= len(digits) - len(stripped)
    digits = stripped.rstrip("0")
    k = len(digits)
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mant = digits if k == 1 else digits[0] + "." + digits[1:]
        body = f"{mant}e{'+' if e >= 0 else '-'}{abs(e)}"
    return sign + body


def _utf16_key(name: str) -> bytes:
    return name.encode("utf-16-be")


def _write(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, int):
        try:
            out.append(_number(float(value)))
        except OverflowError as e:
            raise CanonicalizationError("number is not finite") from e
    elif isinstance(value, float):
        out.append(_number(value))
    elif isinstance(value, str):
        _write_string(value, out)
    elif isinstance(value, list):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _write(item, out)
        out.append("]")
    elif isinstance(value, dict):
        for name in value:
            if not isinstance(name, str):
                raise CanonicalizationError(f"member name {name!r} is not a string")
            # Checked before sorting: encoding a lone surrogate would fail.
            _write_string(name, [])
        out.append("{")
        for i, name in enumerate(sorted(value, key=_utf16_key)):
            if i:
                out.append(",")
            _write_string(name, out)
            out.append(":")
            _write(value[name], out)
        out.append("}")
    else:
        raise CanonicalizationError(f"{type(value).__name__} is not a JSON value")
