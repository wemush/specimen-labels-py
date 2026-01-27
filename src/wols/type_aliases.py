"""Type Alias System for WOLS v1.2.0.

Maps platform-specific type names to canonical WOLS SpecimenTypes.
"""

from __future__ import annotations

from wols.models.enums import SpecimenType

# Module-level set of canonical type values for efficient lookup
_CANONICAL_TYPE_VALUES: frozenset[str] = frozenset(t.value for t in SpecimenType)

# Built-in alias registry mapping platform names to WOLS types
_TYPE_ALIAS_REGISTRY: dict[str, SpecimenType] = {
    # Culture aliases
    "LIQUID_CULTURE": SpecimenType.CULTURE,
    "LC": SpecimenType.CULTURE,
    "AGAR": SpecimenType.CULTURE,
    "PETRI": SpecimenType.CULTURE,
    "SLANT": SpecimenType.CULTURE,
    "CULTURE_PLATE": SpecimenType.CULTURE,
    # Spawn aliases
    "GRAIN_SPAWN": SpecimenType.SPAWN,
    "SAWDUST_SPAWN": SpecimenType.SPAWN,
    "PLUG_SPAWN": SpecimenType.SPAWN,
    "DOWEL": SpecimenType.SPAWN,
    # Substrate aliases
    "BLOCK": SpecimenType.SUBSTRATE,
    "BAG": SpecimenType.SUBSTRATE,
    "BED": SpecimenType.SUBSTRATE,
    "LOG": SpecimenType.SUBSTRATE,
    "BUCKET": SpecimenType.SUBSTRATE,
    # Fruiting aliases
    "FLUSH": SpecimenType.FRUITING,
    "PINNING": SpecimenType.FRUITING,
    "PRIMORDIA": SpecimenType.FRUITING,
    "FRUIT": SpecimenType.FRUITING,
    "FIRST_FLUSH": SpecimenType.FRUITING,
    # Harvest aliases
    "FRESH": SpecimenType.HARVEST,
    "DRIED": SpecimenType.HARVEST,
    "PROCESSED": SpecimenType.HARVEST,
    "EXTRACT": SpecimenType.HARVEST,
}

# Mapping from WOLS types to common platform type names
WOLS_TO_PLATFORM_MAP: dict[SpecimenType, tuple[str, ...]] = {
    SpecimenType.CULTURE: (
        "Liquid Culture",
        "LC",
        "Agar",
        "Petri",
        "Slant",
        "Culture Plate",
    ),
    SpecimenType.SPAWN: ("Grain Spawn", "Sawdust Spawn", "Plug Spawn", "Dowel"),
    SpecimenType.SUBSTRATE: ("Block", "Bag", "Bed", "Log", "Bucket"),
    SpecimenType.FRUITING: ("Pinning", "Primordia", "Fruiting", "Flush", "First Flush"),
    SpecimenType.HARVEST: ("Fresh", "Dried", "Processed", "Extract"),
}


def register_type_alias(alias: str, wols_type: SpecimenType) -> None:
    """Register a custom type alias.

    Args:
        alias: The alias name to register (case-insensitive).
        wols_type: The WOLS SpecimenType to map the alias to.

    Example:
        >>> register_type_alias("MYCELIUM_BLOCK", SpecimenType.SUBSTRATE)
    """
    _TYPE_ALIAS_REGISTRY[alias.upper()] = wols_type


def resolve_type_alias(type_or_alias: str) -> str:
    """Resolve a type alias to its canonical WOLS type.

    Args:
        type_or_alias: A type name or alias to resolve.

    Returns:
        The canonical WOLS type value if resolved, otherwise the original input.

    Example:
        >>> resolve_type_alias("LC")
        'CULTURE'
        >>> resolve_type_alias("CULTURE")
        'CULTURE'
        >>> resolve_type_alias("unknown")
        'unknown'
    """
    upper = type_or_alias.upper()

    # Already a valid type? Use module-level set for O(1) lookup
    if upper in _CANONICAL_TYPE_VALUES:
        return upper

    # Check alias registry
    resolved = _TYPE_ALIAS_REGISTRY.get(upper)
    return resolved.value if resolved else type_or_alias


def get_type_aliases() -> dict[str, SpecimenType]:
    """Get all registered type aliases.

    Returns:
        A copy of the type alias registry.
    """
    return dict(_TYPE_ALIAS_REGISTRY)


def map_to_wols_type(platform_type: str) -> SpecimenType | None:
    """Map a platform-specific type to a WOLS SpecimenType.

    Args:
        platform_type: A platform-specific type name.

    Returns:
        The corresponding WOLS SpecimenType, or None if not found.

    Example:
        >>> map_to_wols_type("Liquid Culture")
        <SpecimenType.CULTURE: 'CULTURE'>
        >>> map_to_wols_type("unknown")
        None
    """
    # First try the alias registry
    resolved = resolve_type_alias(platform_type)
    try:
        return SpecimenType(resolved)
    except ValueError:
        pass

    # Fall back to searching WOLS_TO_PLATFORM_MAP
    normalized = platform_type.upper().replace(" ", "_")
    for wols_type, platform_types in WOLS_TO_PLATFORM_MAP.items():
        for pt in platform_types:
            if pt.upper().replace(" ", "_") == normalized:
                return wols_type

    return None


def map_from_wols_type(wols_type: SpecimenType) -> tuple[str, ...]:
    """Get all platform type names for a WOLS SpecimenType.

    Args:
        wols_type: The WOLS SpecimenType to get platform names for.

    Returns:
        A tuple of platform type names, or empty tuple if none found.

    Example:
        >>> map_from_wols_type(SpecimenType.CULTURE)
        ('Liquid Culture', 'LC', 'Agar', 'Petri', 'Slant', 'Culture Plate')
    """
    return WOLS_TO_PLATFORM_MAP.get(wols_type, ())
