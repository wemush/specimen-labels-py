"""Specimen serialization functionality."""

from __future__ import annotations

import json
from urllib.parse import quote

from wols.constants import (
    DEFAULT_HTTPS_BASE_URL,
    DEFAULT_URL_SCHEME,
    ID_PREFIX,
    SPECIES_NAMES,
    STAGE_NAMES,
    UrlScheme,
)
from wols.models.specimen import Specimen


def to_json(
    specimen: Specimen,
    *,
    indent: int | None = None,
    ensure_ascii: bool = False,
) -> str:
    """Serialize a specimen to JSON-LD string.

    Args:
        specimen: Specimen to serialize.
        indent: JSON indentation (None for compact).
        ensure_ascii: Escape non-ASCII characters.

    Returns:
        JSON-LD formatted string.

    Example:
        >>> json_str = to_json(specimen, indent=2)
        >>> print(json_str)
        {
            "@context": "https://wemush.com/wols/v1",
            "@type": "Specimen",
            ...
        }
    """
    data = specimen.to_dict()
    return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)


def to_compact_url(
    specimen: Specimen,
    *,
    include_stage: bool = True,
    scheme: UrlScheme | str = DEFAULT_URL_SCHEME,
    base_url: str | None = None,
) -> str:
    """Generate a compact URL from a specimen.

    Args:
        specimen: Specimen to encode.
        include_stage: Include stage parameter if available.
        scheme: URL scheme to use. Options:
            - UrlScheme.WEB_WEMUSH (default): "web+wemush://" - PWA compatible
            - UrlScheme.WEMUSH: "wemush://" - Native app deep links
            - UrlScheme.HTTPS: "https://" - Universal web URLs
        base_url: Base URL for HTTPS scheme (default: https://wemush.com/s).
            Only used when scheme is HTTPS.

    Returns:
        Compact URL string.

    ``s`` is the species' code from the WOLS 1.5 Species Code Registry
    (:data:`~wols.constants.SPECIES_CODES`). A species without a registered
    code is written by its full scientific name, percent-encoded. The ID
    suffix is percent-encoded as a single path segment.

    To sign the URL, generate it with ``scheme="wemush"`` and pass it to
    :func:`wols.crypto.sign_compact_url`: signed compact URLs always use
    ``wemush://``.

    Example:
        >>> url = to_compact_url(specimen)
        >>> print(url)
        'web+wemush://v1/clx1abc123?s=POSTR&st=COL'

        >>> url = to_compact_url(specimen, scheme=UrlScheme.HTTPS)
        >>> print(url)
        'https://wemush.com/s/v1/clx1abc123?s=POSTR&st=COL'

        >>> url = to_compact_url(specimen, scheme="wemush")
        >>> print(url)
        'wemush://v1/clx1abc123?s=POSTR&st=COL'
    """
    # Normalize scheme to UrlScheme enum
    if isinstance(scheme, str):
        scheme = UrlScheme(scheme)

    # The ID suffix without the prefix, percent-encoded as one path segment
    # (WOLS 1.5: the same rule as the encrypted format, so "/", "?", "#",
    # "%", "+" and spaces can't change how the URL reads).
    specimen_id = specimen.id
    if specimen_id.startswith(f"{ID_PREFIX}:"):
        specimen_id = specimen_id[len(ID_PREFIX) + 1 :]
    specimen_id = quote(specimen_id, safe="")

    # Build query parameters
    params: list[str] = []

    # The registered code, or the full species name when it has none (WOLS 1.5)
    species_code = SPECIES_NAMES.get(specimen.species)
    params.append(f"s={species_code or quote(specimen.species, safe='')}")

    # Get stage code
    if include_stage and specimen.stage is not None:
        stage_code = STAGE_NAMES.get(specimen.stage.value)
        if stage_code:
            params.append(f"st={stage_code}")

    # Build URL based on scheme
    query = "&".join(params)

    if scheme == UrlScheme.HTTPS:
        # HTTPS scheme: https://base/v1/{id}?params
        effective_base = base_url or DEFAULT_HTTPS_BASE_URL
        # Remove trailing slash if present
        effective_base = effective_base.rstrip("/")
        url = f"{effective_base}/v1/{specimen_id}"
    else:
        # Custom scheme: scheme://v1/{id}?params
        url = f"{scheme.value}://v1/{specimen_id}"

    if query:
        url += f"?{query}"

    return url
