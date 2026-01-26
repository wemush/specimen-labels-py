"""Generation Format System for WOLS v1.2.0.

Handles normalization and validation of generation strings.
"""

from __future__ import annotations

import re
from enum import Enum

# Pattern for parsing generation strings
# Accepts: P, P1, F1, F2, G1, G2, or plain numbers (1, 2, 3)
GENERATION_PARSE_PATTERN = re.compile(r"^(P|P1|F(\d+)|G(\d+)|(\d+))$", re.IGNORECASE)


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
        return "0" if generation_format == GenerationFormat.NUMERIC else "P"

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
