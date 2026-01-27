"""Tests for type alias system (v1.2.0)."""

from __future__ import annotations

from wols import (
    WOLS_TO_PLATFORM_MAP,
    SpecimenType,
    get_type_aliases,
    map_from_wols_type,
    map_to_wols_type,
    register_type_alias,
    resolve_type_alias,
)


class TestResolveTypeAlias:
    """Tests for resolve_type_alias function."""

    def test_canonical_type_unchanged(self) -> None:
        """Verify canonical types are returned unchanged."""
        assert resolve_type_alias("CULTURE") == "CULTURE"
        assert resolve_type_alias("SPAWN") == "SPAWN"
        assert resolve_type_alias("SUBSTRATE") == "SUBSTRATE"
        assert resolve_type_alias("FRUITING") == "FRUITING"
        assert resolve_type_alias("HARVEST") == "HARVEST"

    def test_case_insensitive(self) -> None:
        """Verify resolution is case-insensitive."""
        assert resolve_type_alias("culture") == "CULTURE"
        assert resolve_type_alias("Culture") == "CULTURE"
        assert resolve_type_alias("CULTURE") == "CULTURE"

    def test_lc_alias_to_culture(self) -> None:
        """Verify LC alias resolves to CULTURE."""
        assert resolve_type_alias("LC") == "CULTURE"
        assert resolve_type_alias("lc") == "CULTURE"

    def test_liquid_culture_alias(self) -> None:
        """Verify LIQUID_CULTURE alias resolves to CULTURE."""
        assert resolve_type_alias("LIQUID_CULTURE") == "CULTURE"

    def test_agar_alias(self) -> None:
        """Verify AGAR alias resolves to CULTURE."""
        assert resolve_type_alias("AGAR") == "CULTURE"

    def test_grain_spawn_alias(self) -> None:
        """Verify GRAIN_SPAWN alias resolves to SPAWN."""
        assert resolve_type_alias("GRAIN_SPAWN") == "SPAWN"

    def test_block_alias(self) -> None:
        """Verify BLOCK alias resolves to SUBSTRATE."""
        assert resolve_type_alias("BLOCK") == "SUBSTRATE"

    def test_flush_alias(self) -> None:
        """Verify FLUSH alias resolves to FRUITING."""
        assert resolve_type_alias("FLUSH") == "FRUITING"

    def test_dried_alias(self) -> None:
        """Verify DRIED alias resolves to HARVEST."""
        assert resolve_type_alias("DRIED") == "HARVEST"

    def test_unknown_alias_returns_original(self) -> None:
        """Verify unknown aliases return original string."""
        assert resolve_type_alias("UNKNOWN") == "UNKNOWN"
        assert resolve_type_alias("random") == "random"


class TestRegisterTypeAlias:
    """Tests for register_type_alias function."""

    def test_register_custom_alias(self) -> None:
        """Verify custom aliases can be registered."""
        register_type_alias("MY_CUSTOM_TYPE", SpecimenType.SUBSTRATE)
        assert resolve_type_alias("MY_CUSTOM_TYPE") == "SUBSTRATE"

    def test_register_lowercase_alias(self) -> None:
        """Verify lowercase aliases are normalized to uppercase."""
        register_type_alias("lowercase_alias", SpecimenType.CULTURE)
        assert resolve_type_alias("LOWERCASE_ALIAS") == "CULTURE"
        assert resolve_type_alias("lowercase_alias") == "CULTURE"


class TestGetTypeAliases:
    """Tests for get_type_aliases function."""

    def test_returns_dict(self) -> None:
        """Verify get_type_aliases returns a dict."""
        aliases = get_type_aliases()
        assert isinstance(aliases, dict)

    def test_contains_builtin_aliases(self) -> None:
        """Verify built-in aliases are present."""
        aliases = get_type_aliases()
        assert "LC" in aliases
        assert "AGAR" in aliases
        assert "GRAIN_SPAWN" in aliases

    def test_returns_copy(self) -> None:
        """Verify returned dict is a copy (not the internal registry)."""
        aliases1 = get_type_aliases()
        aliases2 = get_type_aliases()
        assert aliases1 is not aliases2


class TestMapToWolsType:
    """Tests for map_to_wols_type function."""

    def test_canonical_type(self) -> None:
        """Verify canonical types are mapped correctly."""
        assert map_to_wols_type("CULTURE") == SpecimenType.CULTURE
        assert map_to_wols_type("SPAWN") == SpecimenType.SPAWN

    def test_alias_mapping(self) -> None:
        """Verify aliases are mapped correctly."""
        assert map_to_wols_type("LC") == SpecimenType.CULTURE
        assert map_to_wols_type("GRAIN_SPAWN") == SpecimenType.SPAWN

    def test_platform_name_mapping(self) -> None:
        """Verify platform names are mapped correctly."""
        assert map_to_wols_type("Liquid Culture") == SpecimenType.CULTURE
        assert map_to_wols_type("Grain Spawn") == SpecimenType.SPAWN

    def test_unknown_returns_none(self) -> None:
        """Verify unknown types return None."""
        assert map_to_wols_type("UNKNOWN_TYPE") is None
        assert map_to_wols_type("random") is None


class TestMapFromWolsType:
    """Tests for map_from_wols_type function."""

    def test_culture_platform_names(self) -> None:
        """Verify CULTURE maps to expected platform names."""
        names = map_from_wols_type(SpecimenType.CULTURE)
        assert isinstance(names, tuple)
        assert "Liquid Culture" in names
        assert "LC" in names
        assert "Agar" in names

    def test_spawn_platform_names(self) -> None:
        """Verify SPAWN maps to expected platform names."""
        names = map_from_wols_type(SpecimenType.SPAWN)
        assert "Grain Spawn" in names
        assert "Sawdust Spawn" in names

    def test_substrate_platform_names(self) -> None:
        """Verify SUBSTRATE maps to expected platform names."""
        names = map_from_wols_type(SpecimenType.SUBSTRATE)
        assert "Block" in names
        assert "Bag" in names

    def test_fruiting_platform_names(self) -> None:
        """Verify FRUITING maps to expected platform names."""
        names = map_from_wols_type(SpecimenType.FRUITING)
        assert "Flush" in names
        assert "Pinning" in names

    def test_harvest_platform_names(self) -> None:
        """Verify HARVEST maps to expected platform names."""
        names = map_from_wols_type(SpecimenType.HARVEST)
        assert "Fresh" in names
        assert "Dried" in names


class TestWolsToPlatformMap:
    """Tests for WOLS_TO_PLATFORM_MAP constant."""

    def test_is_dict(self) -> None:
        """Verify WOLS_TO_PLATFORM_MAP is a dict."""
        assert isinstance(WOLS_TO_PLATFORM_MAP, dict)

    def test_has_all_specimen_types(self) -> None:
        """Verify all specimen types are present."""
        assert SpecimenType.CULTURE in WOLS_TO_PLATFORM_MAP
        assert SpecimenType.SPAWN in WOLS_TO_PLATFORM_MAP
        assert SpecimenType.SUBSTRATE in WOLS_TO_PLATFORM_MAP
        assert SpecimenType.FRUITING in WOLS_TO_PLATFORM_MAP
        assert SpecimenType.HARVEST in WOLS_TO_PLATFORM_MAP

    def test_values_are_tuples(self) -> None:
        """Verify all values are tuples of strings."""
        for value in WOLS_TO_PLATFORM_MAP.values():
            assert isinstance(value, tuple)
            for name in value:
                assert isinstance(name, str)
