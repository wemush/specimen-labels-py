"""Migration Utilities for WOLS v1.2.0.

Handles version comparison and specimen migration.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from wols.constants import WOLS_VERSION

if TYPE_CHECKING:
    from wols.models.specimen import Specimen

# Type alias for migration handler functions
MigrationHandler = Callable[[dict[str, Any]], dict[str, Any]]

# Migration registry: (from_version, to_version) -> handler
_MIGRATION_REGISTRY: dict[tuple[str, str], MigrationHandler] = {}


def compare_versions(a: str, b: str) -> int:
    """Compare two semantic version strings.

    Args:
        a: First version string (e.g., "1.0.0").
        b: Second version string (e.g., "1.2.0").

    Returns:
        -1 if a < b, 0 if a == b, 1 if a > b.

    Example:
        >>> compare_versions("1.0.0", "1.2.0")
        -1
        >>> compare_versions("1.2.0", "1.2.0")
        0
        >>> compare_versions("2.0.0", "1.2.0")
        1
    """

    def parse(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split("."))

    va, vb = parse(a), parse(b)

    if va < vb:
        return -1
    elif va > vb:
        return 1
    return 0


def is_outdated(version: str) -> bool:
    """Check if a version is older than the current library version.

    Args:
        version: The version string to check.

    Returns:
        True if the version is older than WOLS_VERSION.

    Example:
        >>> is_outdated("1.0.0")
        True
        >>> is_outdated("1.2.0")
        False
    """
    return compare_versions(version, WOLS_VERSION) < 0


def is_newer(version: str) -> bool:
    """Check if a version is newer than the current library version.

    Args:
        version: The version string to check.

    Returns:
        True if the version is newer than WOLS_VERSION.

    Example:
        >>> is_newer("2.0.0")
        True
        >>> is_newer("1.2.0")
        False
    """
    return compare_versions(version, WOLS_VERSION) > 0


def get_current_version() -> str:
    """Get the current WOLS library version.

    Returns:
        The current WOLS_VERSION string.

    Example:
        >>> get_current_version()
        '1.2.0'
    """
    return WOLS_VERSION


def register_migration(
    from_version: str,
    to_version: str,
    handler: MigrationHandler,
) -> None:
    """Register a migration handler.

    Args:
        from_version: Source version.
        to_version: Target version.
        handler: Function that transforms specimen data.

    Example:
        >>> def migrate_1_0_to_1_1(data):
        ...     data["version"] = "1.1.0"
        ...     return data
        >>> register_migration("1.0.0", "1.1.0", migrate_1_0_to_1_1)
    """
    _MIGRATION_REGISTRY[(from_version, to_version)] = handler


def can_migrate(specimen: Specimen | dict[str, Any]) -> bool:
    """Check if a specimen can be migrated to the current version.

    Args:
        specimen: The specimen object or dict to check.

    Returns:
        True if migration is possible (already current or path exists).

    Example:
        >>> can_migrate({"version": "1.0.0", ...})
        True  # If migration path exists
    """
    if isinstance(specimen, dict):
        version = specimen.get("version", "1.0.0")
    else:
        version = specimen.version if hasattr(specimen, "version") else "0.0.0"

    if compare_versions(version, WOLS_VERSION) >= 0:
        return True  # Already current or newer

    # Check if migration path exists
    current = version
    while compare_versions(current, WOLS_VERSION) < 0:
        found_next = False
        for from_v, to_v in _MIGRATION_REGISTRY:
            if from_v == current:
                current = to_v
                found_next = True
                break
        if not found_next:
            return False

    return True


def migrate(specimen: Specimen | dict[str, Any]) -> dict[str, Any]:
    """Migrate a specimen to the current version.

    Args:
        specimen: The specimen object or dict to migrate.

    Returns:
        Migrated specimen data as a dictionary.

    Raises:
        ValueError: If no migration path exists.

    Example:
        >>> migrated = migrate(old_specimen)
        >>> migrated["version"]
        '1.2.0'
    """
    data = dict(specimen) if isinstance(specimen, dict) else specimen.to_dict()
    version = data.get("version", "1.0.0")

    if compare_versions(version, WOLS_VERSION) >= 0:
        return data  # Already current or newer

    current = version
    while compare_versions(current, WOLS_VERSION) < 0:
        found_next = False
        for (from_v, to_v), handler in sorted(_MIGRATION_REGISTRY.items()):
            if from_v == current:
                data = handler(data)
                current = to_v
                found_next = True
                break

        if not found_next:
            raise ValueError(f"No migration path from {current} to {WOLS_VERSION}")

    return data


def get_migrations() -> list[tuple[str, str]]:
    """Get all registered migration paths.

    Returns:
        A sorted list of (from_version, to_version) tuples.

    Example:
        >>> get_migrations()
        [('1.0.0', '1.1.0'), ('1.1.0', '1.2.0')]
    """
    return sorted(_MIGRATION_REGISTRY.keys())


def clear_migrations() -> None:
    """Clear all registered migrations (for testing).

    Example:
        >>> clear_migrations()
        >>> get_migrations()
        []
    """
    _MIGRATION_REGISTRY.clear()
