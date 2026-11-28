"""Specimen parsing functionality."""

from __future__ import annotations

import json
import re
import warnings
from collections.abc import Callable
from datetime import UTC, datetime

from wols.constants import (
    LEGACY_SPECIES_CODES,
    SPECIES_CODES,
    STAGE_CODES,
)
from wols.core.compact import REGISTERED_PARAMETERS, InvalidEncoding, percent_decode
from wols.exceptions import WolsParseError, WolsWarning
from wols.generation import is_valid_generation
from wols.models.enums import GrowthStage, SpecimenType
from wols.models.specimen import Specimen, SpecimenRef, Strain


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

    Follows the WOLS 1.5 compact URL rules. Accepted forms:
        - ``wemush://v1/{id}?s={species}&...`` (native app, spec form)
        - ``web+wemush://v1/{id}?s={species}&...`` (PWA)
        - ``https://{host}/{path}/v1/{id}?s={species}&...`` (web; the
          specification lets decoders accept other forms like this one)

    The ID is the single path segment after ``v1/``, percent-decoded as
    UTF-8 with ``+`` as a literal character. Parameter values are
    percent-decoded with ``+`` as a space. ``s`` is required. The registered
    parameters are ``s``, ``ty``, ``st``, ``t``, ``b``, ``sn``, ``sg``,
    ``td`` and ``sig``; any other parameter is kept in
    ``unrecognized_params`` and never rejects the URL. ``sig`` is kept as
    written and never verified.

    Warnings (:class:`~wols.exceptions.WolsWarning`): a legacy two-letter
    species code, and a ``td`` that isn't plain digits (which is ignored).

    Args:
        url: Compact URL in any supported scheme.

    Returns:
        SpecimenRef with the decoded parameters.

    Raises:
        WolsParseError: With ``code`` set to one of:

            - ``INVALID_URL``: not a compact URL (scheme, missing or extra
              path segments, fragment).
            - ``UNSUPPORTED_VERSION``: a version segment other than ``v1``.
            - ``ENCRYPTED_URL``: a ``wemush://v1/encrypted/{id}`` URL;
              decrypt it with :func:`wols.crypto.decrypt_specimen`.
            - ``INVALID_ENCODING``: a malformed percent escape, or one that
              isn't valid UTF-8, in the ID or any value.
            - ``DUPLICATE_PARAMETER``: a registered parameter appears twice.
            - ``MISSING_PARAMETER``: no ``s``, or an empty one.
            - ``INVALID_PARAMETER``: a ``ty``, ``st``, ``t`` or ``sg`` value
              outside its syntax.

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

    def refuse(code: str, message: str) -> WolsParseError:
        return WolsParseError(message=message, code=code, input=url)

    if not isinstance(url, str):
        raise WolsParseError(
            message=f"Expected a URL string, got {type(url).__name__}",
            code="INVALID_URL",
        )
    if "#" in url:
        raise refuse("INVALID_URL", "Compact URL must not have a fragment")

    path, _, query = url.partition("?")
    segment = _compact_id_segment(path, refuse)

    try:
        specimen_id = percent_decode(segment)
    except InvalidEncoding as e:
        raise refuse("INVALID_ENCODING", f"Compact URL ID: {e}") from None

    registered: dict[str, str] = {}
    params: dict[str, str] = {}
    unrecognized: dict[str, str] = {}
    raw_sig: str | None = None
    for pair in query.split("&") if query else ():
        if pair == "":
            continue
        name, has_value, raw_value = pair.partition("=")
        try:
            value = percent_decode(raw_value, plus_as_space=True)
        except InvalidEncoding as e:
            raise refuse(
                "INVALID_ENCODING", f"Compact URL parameter {name!r}: {e}"
            ) from None
        if name in _REGISTERED:
            if name in registered:
                raise refuse(
                    "DUPLICATE_PARAMETER",
                    f"Compact URL parameter {name!r} appears more than once",
                )
            registered[name] = value
            if name == "sig":
                raw_sig = raw_value if has_value else ""
        else:
            unrecognized.setdefault(name, value)
        params.setdefault(name, value)

    species_code = registered.get("s")
    if not species_code:
        raise refuse("MISSING_PARAMETER", "Compact URL has no species parameter 's'")
    # A registered code, then a legacy two-letter code, then the name itself.
    species = resolve_species(species_code, stacklevel=3)

    specimen_type: SpecimenType | None = None
    if "ty" in registered:
        try:
            specimen_type = SpecimenType(registered["ty"])
        except ValueError:
            raise refuse(
                "INVALID_PARAMETER",
                f"Compact URL 'ty' must be a canonical specimen type, got "
                f"{registered['ty']!r}",
            ) from None

    stage: GrowthStage | None = None
    if "st" in registered:
        stage_value = STAGE_CODES.get(registered["st"], registered["st"])
        try:
            stage = GrowthStage(stage_value)
        except ValueError:
            raise refuse(
                "INVALID_PARAMETER",
                "Compact URL 'st' must be a growth stage or its 3-letter code, "
                f"got {registered['st']!r}",
            ) from None

    created: datetime | None = None
    if "t" in registered:
        created = _unix_time(registered["t"], refuse)

    generation = registered.get("sg")
    if generation is not None and not (
        generation == generation.strip() and is_valid_generation(generation)
    ):
        raise refuse(
            "INVALID_PARAMETER",
            f"Compact URL 'sg' is not a generation (P, F1, G2, 3), got {generation!r}",
        )

    transfer_depth: int | None = None
    if "td" in registered:
        if _DIGITS.fullmatch(registered["td"]):
            transfer_depth = int(registered["td"])
        else:
            warnings.warn(
                f"Compact URL parameter 'td' is not plain decimal digits "
                f"({registered['td']!r}); it is ignored.",
                WolsWarning,
                stacklevel=2,
            )

    strain: Strain | None = None
    if "sn" in registered or generation is not None or transfer_depth is not None:
        strain = Strain(
            name=registered.get("sn"),
            generation=generation,
            transfer_depth=transfer_depth,
        )

    return SpecimenRef(
        id=specimen_id,
        species_code=species_code,
        stage=stage,
        params=params,
        species=species,
        type=specimen_type,
        created=created,
        batch=registered.get("b"),
        strain=strain,
        unrecognized_params=unrecognized,
        signature=raw_sig,
    )


_REGISTERED = frozenset(REGISTERED_PARAMETERS)
_DIGITS = re.compile(r"[0-9]+")
_VERSION_RE = re.compile(r"v[0-9]+")
_CUSTOM_SCHEMES = ("wemush://", "web+wemush://")


def _compact_id_segment(path: str, refuse: Callable[[str, str], Exception]) -> str:
    """The raw ID segment of a compact URL (everything before ``?``)."""
    lowered = path[:16].lower()
    scheme = next((s for s in _CUSTOM_SCHEMES if lowered.startswith(s)), None)
    if scheme is not None:
        segments = path[len(scheme) :].split("/")
        if len(segments) < 2 or not _VERSION_RE.fullmatch(segments[0]):
            raise refuse(
                "INVALID_URL",
                f"Compact URL must be {scheme}v1/{{id}}, got {path!r}",
            )
    elif lowered.startswith("https://"):
        # https://{host}/{path}/v1/{id}: the version is the second-to-last
        # segment. The host and any base path before it are not checked.
        segments = path[len("https://") :].split("/")[1:]
        if (
            len(segments) >= 3
            and _VERSION_RE.fullmatch(segments[-3])
            and segments[-2] == "encrypted"
        ):
            segments = segments[-3:]
        elif len(segments) >= 2 and _VERSION_RE.fullmatch(segments[-2]):
            segments = segments[-2:]
        else:
            raise refuse(
                "INVALID_URL",
                f"HTTPS compact URL must end in /v1/{{id}}, got {path!r}",
            )
    else:
        raise refuse(
            "INVALID_URL",
            "Invalid URL scheme: expected wemush://, web+wemush:// or https://",
        )

    if segments[0] != "v1":
        raise refuse(
            "UNSUPPORTED_VERSION",
            f"Unsupported compact URL version {segments[0]!r}; only v1 is defined",
        )
    if segments[1] == "encrypted" and len(segments) > 2:
        raise refuse(
            "ENCRYPTED_URL",
            "This is an encrypted WOLS URL; decrypt it with "
            "wols.crypto.decrypt_specimen()",
        )
    if len(segments) != 2 or segments[1] == "":
        raise refuse(
            "INVALID_URL",
            f"Compact URL needs exactly one ID segment after v1/, got {path!r}",
        )
    return segments[1]


def _unix_time(value: str, refuse: Callable[[str, str], Exception]) -> datetime:
    """``t``: Unix seconds as plain decimal digits, in UTC."""
    if not _DIGITS.fullmatch(value):
        raise refuse(
            "INVALID_PARAMETER",
            f"Compact URL 't' must be Unix seconds as decimal digits, got {value!r}",
        )
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (OverflowError, OSError, ValueError):
        raise refuse(
            "INVALID_PARAMETER", f"Compact URL 't' is out of range: {value!r}"
        ) from None


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
