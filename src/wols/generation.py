"""Generation Format System for WOLS v1.2.0.

Handles normalization and validation of generation strings.
"""

from __future__ import annotations

import re
import warnings
from enum import Enum
from typing import Any, TypeGuard

from wols.exceptions import WolsWarning

# Pattern for parsing generation strings
# Accepts: P, P{n}, F{n}, G{n} or plain numbers (1, 2, 3), letters in either
# case (WOLS 1.5.0-rc.2).
GENERATION_PARSE_PATTERN = re.compile(r"^(P\d*|F(\d+)|G(\d+)|(\d+))$", re.IGNORECASE)


class GenerationFormat(str, Enum):
    """Output format for generation normalization."""

    PRESERVE = "preserve"
    """Keep the original format."""

    FILIAL = "filial"
    """Convert to filial format (F1, F2, etc.)."""

    NUMERIC = "numeric"
    """Convert to plain numeric format (0, 1, 2, etc.)."""


def normalize_generation(
    generation: str,
    generation_format: GenerationFormat = GenerationFormat.PRESERVE,
) -> str:
    """Normalize a generation string to the specified format.

    Accepts: F1, F2, G1, G2, P, P1, or plain numbers (1, 2, 3)

    Args:
        generation: The generation string to normalize.
        generation_format: Target format (preserve, filial, or numeric).

    Returns:
        Normalized generation string, or original if not parseable.

    Example:
        >>> normalize_generation("F1", GenerationFormat.NUMERIC)
        '1'
        >>> normalize_generation("G3", GenerationFormat.FILIAL)
        'F3'
        >>> normalize_generation("P", GenerationFormat.NUMERIC)
        '0'
    """
    trimmed = generation.strip().upper()

    # Handle parental generation specially
    if trimmed in ("P", "P1"):
        if generation_format == GenerationFormat.NUMERIC:
            return "0"
        if generation_format == GenerationFormat.PRESERVE:
            # Preserve the original string (return stripped but not normalized)
            return generation.strip()
        # For FILIAL format, canonicalize to "P"
        return "P"

    match = GENERATION_PARSE_PATTERN.match(trimmed)
    if not match:
        return generation  # Return original if not parseable

    # Extract the numeric value
    if match.group(2) is not None:  # F{n} format
        numeric_value = int(match.group(2))
    elif match.group(3) is not None:  # G{n} format
        numeric_value = int(match.group(3))
    elif match.group(4) is not None:  # Plain number
        numeric_value = int(match.group(4))
    else:
        return generation

    if generation_format == GenerationFormat.PRESERVE:
        return generation
    elif generation_format == GenerationFormat.FILIAL:
        return f"F{numeric_value}"
    elif generation_format == GenerationFormat.NUMERIC:
        return str(numeric_value)

    return generation


def is_valid_generation(generation: str) -> bool:
    """Check if a generation string is valid.

    Args:
        generation: The generation string to validate.

    Returns:
        True if valid, False otherwise.

    Example:
        >>> is_valid_generation("F1")
        True
        >>> is_valid_generation("G2")
        True
        >>> is_valid_generation("P")
        True
        >>> is_valid_generation("invalid")
        False
    """
    trimmed = generation.strip().upper()
    return bool(GENERATION_PARSE_PATTERN.match(trimmed))


# =============================================================================
# Numeric strain.generation (WOLS 1.4.0)
# =============================================================================

NUMERIC_GENERATION = "NUMERIC_GENERATION"
"""Warning code for a ``strain.generation`` given as a JSON integer (WOLS 1.4.0)."""


def is_integer_generation(value: object) -> TypeGuard[int]:
    """Return True for a non-negative ``int`` generation (``bool`` is rejected).

    ``strain.generation`` is a string. wols 1.3.0 accepted and wrote a JSON
    integer, so decoders read one as its decimal string (WOLS 1.4.0).
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def numeric_generation_message(value: int) -> str:
    """Describe a numeric ``strain.generation`` read as its decimal string."""
    return (
        f"strain.generation is the number {value}; read as the string {str(value)!r}. "
        f"Write it as a string: {str(value)!r}"
    )


def warn_numeric_generation(value: int, *, stacklevel: int) -> None:
    """Emit a :class:`~wols.exceptions.WolsWarning` for a numeric generation."""
    warnings.warn(
        numeric_generation_message(value), WolsWarning, stacklevel=stacklevel + 1
    )


def with_string_generation(strain: Any, *, stacklevel: int) -> Any:
    """Return ``strain`` with an integer ``generation`` as its decimal string.

    ``strain`` is a JSON-LD strain object (a ``dict``). Anything else, and a
    strain whose generation is not a non-negative integer, is returned
    unchanged. Converting warns. The input is never mutated.
    """
    if not isinstance(strain, dict):
        return strain
    generation = strain.get("generation")
    if not is_integer_generation(generation):
        return strain
    warn_numeric_generation(generation, stacklevel=stacklevel + 1)
    return {**strain, "generation": str(generation)}
