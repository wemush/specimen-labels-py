"""Specimen parsing functionality."""

from __future__ import annotations

import contextlib
import json
import warnings
from urllib.parse import parse_qs, urlparse

from wols.constants import (
    LEGACY_SPECIES_CODES,
    SPECIES_CODES,
    STAGE_CODES,
    VALID_URL_SCHEMES,
)
from wols.exceptions import WolsParseError, WolsWarning
from wols.models.enums import GrowthStage
from wols.models.specimen import Specimen, SpecimenRef


def parse_specimen(json_str: str) -> Specimen:
    """Parse a JSON-LD string into a Specimen object.

    Args:
        json_str: JSON-LD formatted specimen string.

    Returns:
        Parsed Specimen instance.

    Raises:
        WolsParseError: If JSON is invalid or missing required fields.

    Example:
        >>> json_str = '{"@context": "https://wemush.com/wols/v1", ...}'
        >>> specimen = parse_specimen(json_str)
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise WolsParseError(
            message=f"Invalid JSON: {e.msg} at line {e.lineno}, column {e.colno}",
            code="INVALID_JSON",
            input=json_str,
        ) from e

    if not isinstance(data, dict):
        raise WolsParseError(
            message="Expected JSON object, got " + type(data).__name__,
            code="INVALID_TYPE",
            input=json_str,
        )

    # Check required fields
    required_fields = ["id", "type", "species"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise WolsParseError(
            message=f"Missing required field(s): {', '.join(missing)}",
            code="REQUIRED_FIELD",
            input=json_str,
        )

    try:
        return Specimen.from_dict(data)
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        # Untrusted input must only ever surface as WolsParseError.
        raise WolsParseError(
            message=f"Failed to parse specimen: {e}",
            code="PARSE_ERROR",
            input=json_str,
        ) from e


def parse_compact_url(url: str) -> SpecimenRef:
    """Parse a compact WOLS URL into a SpecimenRef.

    Decoders accept every supported scheme, regardless of which one
    :func:`~wols.to_compact_url` emits by default:
        - wemush://v1/{id}?s={species}&st={stage} (native app, spec form)
        - web+wemush://v1/{id}?s={species}&st={stage} (PWA)
        - https://domain/path/v1/{id}?s={species}&st={stage} (web)

    Args:
        url: Compact URL in any supported scheme.

    Returns:
        SpecimenRef with extracted parameters.

    Raises:
        WolsParseError: If URL format is invalid.

    Example:
        >>> ref = parse_compact_url("web+wemush://v1/abc123?s=POSTR&st=COL")
        >>> print(ref.id)
        'abc123'
        >>> print(ref.species_code)
        'POSTR'
        >>> print(ref.species)
        'Pleurotus ostreatus'

        >>> ref = parse_compact_url("https://wemush.com/s/v1/abc123?s=POSTR")
        >>> print(ref.id)
        'abc123'
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise WolsParseError(
            message=f"Invalid URL format: {e}",
            code="INVALID_URL",
            input=url,
        ) from e

    # Validate scheme
    if parsed.scheme not in VALID_URL_SCHEMES:
        valid_schemes = ", ".join(sorted(VALID_URL_SCHEMES))
        raise WolsParseError(
            message=f"Invalid URL scheme: expected one of "
            f"[{valid_schemes}], got '{parsed.scheme}'",
            code="INVALID_SCHEME",
            input=url,
        )

    # Parse path based on scheme type
    # HTTPS: path is like /s/v1/{id} or /specimen/v1/{id}
    # Custom schemes: netloc contains the path start (v1/...)
    path = parsed.path if parsed.scheme == "https" else parsed.netloc + parsed.path

    path_parts = [p for p in path.split("/") if p]

    # Find the version marker (v1) in the path
    try:
        v1_index = path_parts.index("v1")
    except ValueError:
        raise WolsParseError(
            message=f"Invalid URL path: missing 'v1' version marker in '{path}'",
            code="INVALID_PATH",
            input=url,
        ) from None

    # Specimen ID should follow v1
    if len(path_parts) <= v1_index + 1:
        raise WolsParseError(
            message=f"Invalid URL path: missing specimen ID after 'v1' in '{path}'",
            code="INVALID_PATH",
            input=url,
        )

    specimen_id = path_parts[v1_index + 1]

    # wemush://v1/encrypted/{id} is the encrypted format, not a compact URL
    if specimen_id == "encrypted" and len(path_parts) > v1_index + 2:
        raise WolsParseError(
            message="This is an encrypted WOLS URL; decrypt it with "
            "wols.crypto.decrypt_specimen()",
            code="ENCRYPTED_URL",
            input=url,
        )

    # Parse query parameters
    query_params: dict[str, str] = {}
    if parsed.query:
        raw_params = parse_qs(parsed.query)
        # Flatten single-value lists (always take first value)
        query_params = {k: v[0] for k, v in raw_params.items()}

    # Extract species code, and resolve it as WOLS 1.5 decodes `s`: a
    # registered code, then a legacy two-letter code, then the name as written.
    species_code = query_params.get("s")
    species = resolve_species(species_code, stacklevel=3) if species_code else None

    # Extract and convert stage: a three-letter code or a full stage name
    stage: GrowthStage | None = None
    stage_code = query_params.get("st")
    if stage_code:
        stage_value = STAGE_CODES.get(stage_code.upper(), stage_code.upper())
        with contextlib.suppress(ValueError):
            stage = GrowthStage(stage_value)

    return SpecimenRef(
        id=specimen_id,
        species_code=species_code,
        stage=stage,
        params=query_params,
        species=species,
    )


def resolve_species(value: str, *, stacklevel: int = 2) -> str:
    """Resolve a compact URL ``s`` value to a scientific name.

    Follows the WOLS 1.5 Species Code Registry: a registered code gives its
    species; a legacy two-letter code (written by wols before 1.5) gives its
    species with a :class:`~wols.exceptions.WolsWarning`; anything else is
    taken as the species name as written.

    Example:
        >>> resolve_species("POSTR")
        'Pleurotus ostreatus'
        >>> resolve_species("Morchella importuna")
        'Morchella importuna'
    """
    if value in SPECIES_CODES:
        return SPECIES_CODES[value]
    if value in LEGACY_SPECIES_CODES:
        warnings.warn(
            f"Species code {value!r} is a legacy code; read as "
            f"{LEGACY_SPECIES_CODES[value]!r}. WOLS 1.5 generators write the "
            "registered five-letter code instead.",
            WolsWarning,
            stacklevel=stacklevel + 1,
        )
        return LEGACY_SPECIES_CODES[value]
    return value


def parse_compact_url_or_throw(url: str) -> SpecimenRef:
    """Parse a compact URL, raising WolsParseError on failure.

    This is an alias for parse_compact_url that makes the throwing
    behavior explicit in the function name.

    Args:
        url: The compact URL to parse.

    Returns:
        Parsed SpecimenRef.

    Raises:
        WolsParseError: If parsing fails.

    Example:
        >>> ref = parse_compact_url_or_throw("web+wemush://v1/abc123?s=POSTR")
        >>> print(ref.id)
        'abc123'
    """
    return parse_compact_url(url)


def parse_compact_url_or_none(url: str) -> SpecimenRef | None:
    """Parse a compact URL, returning None on failure.

    Args:
        url: The compact URL to parse.

    Returns:
        Parsed SpecimenRef or None if parsing failed.

    Example:
        >>> ref = parse_compact_url_or_none("web+wemush://v1/abc123?s=POSTR")
        >>> print(ref.id if ref else "Failed")
        'abc123'
        >>> ref = parse_compact_url_or_none("invalid://url")
        >>> print(ref)
        None
    """
    try:
        return parse_compact_url(url)
    except WolsParseError:
        return None
