"""Tests for migration utilities (v1.2.0)."""

from __future__ import annotations

from typing import Any

import pytest

from wols import (
    WOLS_VERSION,
    Specimen,
    SpecimenType,
    can_migrate,
    clear_migrations,
    compare_versions,
    get_current_version,
    get_migrations,
    is_newer,
    is_outdated,
    migrate,
    register_migration,
)


class TestCompareVersions:
    """Tests for compare_versions function."""

    def test_equal_versions(self) -> None:
        """Verify equal versions return 0."""
        assert compare_versions("1.0.0", "1.0.0") == 0
        assert compare_versions("1.2.0", "1.2.0") == 0
        assert compare_versions("0.0.1", "0.0.1") == 0

    def test_first_version_greater(self) -> None:
        """Verify first > second returns 1."""
        assert compare_versions("2.0.0", "1.0.0") == 1
        assert compare_versions("1.1.0", "1.0.0") == 1
        assert compare_versions("1.0.1", "1.0.0") == 1
        assert compare_versions("1.2.0", "1.1.9") == 1

    def test_first_version_lesser(self) -> None:
        """Verify first < second returns -1."""
        assert compare_versions("1.0.0", "2.0.0") == -1
        assert compare_versions("1.0.0", "1.1.0") == -1
        assert compare_versions("1.0.0", "1.0.1") == -1
        assert compare_versions("1.1.9", "1.2.0") == -1


class TestIsOutdated:
    """Tests for is_outdated function."""

    def test_old_version_is_outdated(self) -> None:
        """Verify older versions are outdated."""
        assert is_outdated("1.0.0") is True
        assert is_outdated("1.1.0") is True

    def test_current_version_not_outdated(self) -> None:
        """Verify current version is not outdated."""
        assert is_outdated(WOLS_VERSION) is False

    def test_future_version_not_outdated(self) -> None:
        """Verify future versions are not outdated."""
        assert is_outdated("99.0.0") is False


class TestIsNewer:
    """Tests for is_newer function."""

    def test_old_version_not_newer(self) -> None:
        """Verify older versions are not newer."""
        assert is_newer("1.0.0") is False
        assert is_newer("1.1.0") is False

    def test_current_version_not_newer(self) -> None:
        """Verify current version is not newer."""
        assert is_newer(WOLS_VERSION) is False

    def test_future_version_is_newer(self) -> None:
        """Verify future versions are newer."""
        assert is_newer("99.0.0") is True
        assert is_newer("1.3.0") is True


class TestGetCurrentVersion:
    """Tests for get_current_version function."""

    def test_returns_wols_version(self) -> None:
        """Verify returns current WOLS_VERSION."""
        assert get_current_version() == WOLS_VERSION

    def test_returns_1_2_0(self) -> None:
        """Verify returns 1.2.0."""
        assert get_current_version() == "1.2.0"


class TestMigrationRegistry:
    """Tests for migration registration and retrieval."""

    def setup_method(self) -> None:
        """Clear migrations before each test."""
        clear_migrations()

    def teardown_method(self) -> None:
        """Clear migrations after each test."""
        clear_migrations()

    def test_no_migrations_initially(self) -> None:
        """Verify no migrations registered initially."""
        assert len(get_migrations()) == 0

    def test_register_migration(self) -> None:
        """Verify migration can be registered."""

        def dummy_handler(data: dict[str, Any]) -> dict[str, Any]:
            return data

        register_migration("1.1.0", "1.2.0", dummy_handler)
        migrations = get_migrations()
        assert len(migrations) == 1
        # get_migrations returns (from_version, to_version) tuples, not handlers
        assert migrations[0] == ("1.1.0", "1.2.0")

    def test_register_multiple_migrations(self) -> None:
        """Verify multiple migrations can be registered."""

        def handler1(data: dict[str, Any]) -> dict[str, Any]:
            return data

        def handler2(data: dict[str, Any]) -> dict[str, Any]:
            return data

        register_migration("1.0.0", "1.1.0", handler1)
        register_migration("1.1.0", "1.2.0", handler2)

        migrations = get_migrations()
        assert len(migrations) == 2

    def test_clear_migrations(self) -> None:
        """Verify migrations can be cleared."""

        def handler(data: dict[str, Any]) -> dict[str, Any]:
            return data

        register_migration("1.1.0", "1.2.0", handler)
        assert len(get_migrations()) == 1

        clear_migrations()
        assert len(get_migrations()) == 0


class TestCanMigrate:
    """Tests for can_migrate function."""

    def setup_method(self) -> None:
        """Clear migrations before each test."""
        clear_migrations()

    def teardown_method(self) -> None:
        """Clear migrations after each test."""
        clear_migrations()

    def test_no_migrations_available(self) -> None:
        """Verify can_migrate returns False when no migrations registered."""
        specimen = Specimen(
            id="wemush:test123",
            version="1.1.0",
            type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )
        assert can_migrate(specimen) is False

    def test_migration_available(self) -> None:
        """Verify can_migrate returns True when migration exists."""

        def handler(data: dict[str, Any]) -> dict[str, Any]:
            return data

        register_migration("1.1.0", "1.2.0", handler)

        specimen = Specimen(
            id="wemush:test123",
            version="1.1.0",
            type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )
        assert can_migrate(specimen) is True

    def test_no_migration_for_version(self) -> None:
        """Verify can_migrate returns False for unregistered version."""

        def handler(data: dict[str, Any]) -> dict[str, Any]:
            return data

        register_migration("1.1.0", "1.2.0", handler)

        specimen = Specimen(
            id="wemush:test123",
            version="0.9.0",  # No migration from this version
            type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )
        assert can_migrate(specimen) is False


class TestMigrate:
    """Tests for migrate function."""

    def setup_method(self) -> None:
        """Clear migrations before each test."""
        clear_migrations()

    def teardown_method(self) -> None:
        """Clear migrations after each test."""
        clear_migrations()

    def test_migrate_updates_version(self) -> None:
        """Verify migrate applies handler and updates version."""

        def handler(data: dict[str, Any]) -> dict[str, Any]:
            # Update version in the dict
            data["version"] = "1.2.0"
            return data

        register_migration("1.1.0", "1.2.0", handler)

        old_specimen = Specimen(
            id="wemush:migrate001",
            version="1.1.0",
            type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )

        result = migrate(old_specimen)
        # migrate returns a dict, not a Specimen
        assert isinstance(result, dict)
        assert result["version"] == "1.2.0"

    def test_migrate_preserves_data(self) -> None:
        """Verify migrate preserves specimen data."""

        def handler(data: dict[str, Any]) -> dict[str, Any]:
            data["version"] = "1.2.0"
            return data

        register_migration("1.1.0", "1.2.0", handler)

        old_specimen = Specimen(
            id="wemush:migrate002",
            version="1.1.0",
            type=SpecimenType.SPAWN,
            species="Lentinula edodes",
            batch="BATCH-2024-001",
            organization="WeMush Labs",
        )

        result = migrate(old_specimen)
        assert result["id"] == old_specimen.id
        assert result["type"] == old_specimen.type.value
        assert result["species"] == old_specimen.species
        assert result["batch"] == old_specimen.batch
        assert result["organization"] == old_specimen.organization

    def test_migrate_multi_step(self) -> None:
        """Verify multi-step migration works."""

        def handler_1_0_to_1_1(data: dict[str, Any]) -> dict[str, Any]:
            data["version"] = "1.1.0"
            return data

        def handler_1_1_to_1_2(data: dict[str, Any]) -> dict[str, Any]:
            data["version"] = "1.2.0"
            return data

        register_migration("1.0.0", "1.1.0", handler_1_0_to_1_1)
        register_migration("1.1.0", "1.2.0", handler_1_1_to_1_2)

        old_specimen = Specimen(
            id="wemush:multistep",
            version="1.0.0",
            type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )

        result = migrate(old_specimen)
        assert result["version"] == "1.2.0"

    def test_migrate_no_migration_returns_dict(self) -> None:
        """Verify migrate returns dict representation when no migration needed."""
        specimen = Specimen(
            id="wemush:nomigrate",
            version="1.2.0",
            type=SpecimenType.CULTURE,
            species="Ganoderma lucidum",
        )

        result = migrate(specimen)
        # Result is always a dict
        assert isinstance(result, dict)
        assert result["id"] == specimen.id
        assert result["version"] == specimen.version

    def test_migrate_no_path_raises(self) -> None:
        """Verify migrate raises when no migration path exists."""
        specimen = Specimen(
            id="wemush:nopath",
            version="0.5.0",  # No migration from this version
            type=SpecimenType.CULTURE,
            species="Test species",
        )

        with pytest.raises(ValueError) as exc_info:
            migrate(specimen)
        assert "No migration path" in str(exc_info.value)

    def test_migrate_from_dict_input(self) -> None:
        """Verify migrate works with dict input."""

        def handler(data: dict[str, Any]) -> dict[str, Any]:
            data["version"] = "1.2.0"
            return data

        register_migration("1.1.0", "1.2.0", handler)

        input_dict: dict[str, Any] = {
            "id": "wemush:dictinput",
            "version": "1.1.0",
            "type": "CULTURE",
            "species": "Test species",
        }

        result = migrate(input_dict)
        assert result["version"] == "1.2.0"

    def test_migrate_dict_without_version_uses_default(self) -> None:
        """Verify migrate uses 1.0.0 default when version missing."""

        def handler_1_0_to_1_1(data: dict[str, Any]) -> dict[str, Any]:
            data["version"] = "1.1.0"
            return data

        def handler_1_1_to_1_2(data: dict[str, Any]) -> dict[str, Any]:
            data["version"] = "1.2.0"
            return data

        register_migration("1.0.0", "1.1.0", handler_1_0_to_1_1)
        register_migration("1.1.0", "1.2.0", handler_1_1_to_1_2)

        input_dict: dict[str, Any] = {
            "id": "wemush:noversion",
            # No version field - should default to 1.0.0
            "type": "CULTURE",
            "species": "Test species",
        }

        result = migrate(input_dict)
        assert result["version"] == "1.2.0"


class TestCanMigrateEdgeCases:
    """Edge case tests for can_migrate function."""

    def setup_method(self) -> None:
        """Clear migrations before each test."""
        clear_migrations()

    def teardown_method(self) -> None:
        """Clear migrations after each test."""
        clear_migrations()

    def test_can_migrate_dict_input(self) -> None:
        """Verify can_migrate works with dict input."""

        def handler(data: dict[str, Any]) -> dict[str, Any]:
            return data

        register_migration("1.1.0", "1.2.0", handler)

        input_dict: dict[str, Any] = {
            "version": "1.1.0",
            "type": "CULTURE",
            "species": "Test",
        }

        assert can_migrate(input_dict) is True

    def test_can_migrate_dict_without_version(self) -> None:
        """Verify can_migrate with dict missing version field."""

        def handler_1_0_to_1_1(data: dict[str, Any]) -> dict[str, Any]:
            return data

        def handler_1_1_to_1_2(data: dict[str, Any]) -> dict[str, Any]:
            return data

        register_migration("1.0.0", "1.1.0", handler_1_0_to_1_1)
        register_migration("1.1.0", "1.2.0", handler_1_1_to_1_2)

        input_dict: dict[str, Any] = {
            # No version - defaults to 1.0.0
            "type": "CULTURE",
            "species": "Test",
        }

        assert can_migrate(input_dict) is True

    def test_can_migrate_newer_version(self) -> None:
        """Verify can_migrate returns True for newer versions."""
        specimen = Specimen(
            id="wemush:newer",
            version="99.0.0",  # Newer than current
            type=SpecimenType.CULTURE,
            species="Test",
        )

        assert can_migrate(specimen) is True

    def test_can_migrate_current_version(self) -> None:
        """Verify can_migrate returns True for current version."""
        specimen = Specimen(
            id="wemush:current",
            version="1.2.0",  # Current version
            type=SpecimenType.CULTURE,
            species="Test",
        )

        assert can_migrate(specimen) is True
