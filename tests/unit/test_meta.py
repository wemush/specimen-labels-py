"""Tests for SpecimenMeta and _meta field (v1.2.0)."""

from __future__ import annotations

import json

from wols import (
    Specimen,
    SpecimenMeta,
    SpecimenType,
    create_specimen,
    parse_specimen,
    to_json,
)


class TestSpecimenMetaTypeDict:
    """Tests for SpecimenMeta TypedDict."""

    def test_create_empty_meta(self) -> None:
        """Verify empty SpecimenMeta can be created."""
        meta: SpecimenMeta = {}
        assert meta == {}

    def test_create_with_source_id(self) -> None:
        """Verify SpecimenMeta with source_id."""
        meta: SpecimenMeta = {"source_id": "ext-123"}
        assert meta["source_id"] == "ext-123"

    def test_create_with_all_fields(self) -> None:
        """Verify SpecimenMeta with all fields."""
        meta: SpecimenMeta = {
            "source_id": "ext-123",
            "imported_at": "2024-01-15T10:30:00Z",
            "source_system": "legacy-db",
            "schema_version": "2.0",
        }
        assert meta["source_id"] == "ext-123"
        assert meta["imported_at"] == "2024-01-15T10:30:00Z"
        assert meta["source_system"] == "legacy-db"
        assert meta["schema_version"] == "2.0"


class TestSpecimenWithMeta:
    """Tests for Specimen with _meta field."""

    def test_specimen_default_meta_is_none(self) -> None:
        """Verify Specimen._meta defaults to None."""
        specimen = create_specimen(
            input_type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )
        assert specimen._meta is None

    def test_specimen_with_meta(self) -> None:
        """Verify Specimen can have _meta field."""
        meta: SpecimenMeta = {
            "source_id": "legacy-001",
            "source_system": "old-tracker",
        }
        specimen = Specimen(
            id="wemush:test123",
            version="1.2.0",
            type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
            _meta=meta,
        )
        assert specimen._meta is not None
        assert specimen._meta["source_id"] == "legacy-001"
        assert specimen._meta["source_system"] == "old-tracker"


class TestSpecimenMetaSerialization:
    """Tests for _meta field serialization."""

    def test_to_dict_without_meta(self) -> None:
        """Verify to_dict excludes _meta when None."""
        specimen = create_specimen(
            input_type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )
        data = specimen.to_dict()
        assert "_meta" not in data

    def test_to_dict_with_meta(self) -> None:
        """Verify to_dict includes _meta when present."""
        meta: SpecimenMeta = {
            "source_id": "ext-456",
            "imported_at": "2024-06-01T12:00:00Z",
        }
        specimen = Specimen(
            id="wemush:test456",
            version="1.2.0",
            type=SpecimenType.SUBSTRATE,
            species="Lentinula edodes",
            _meta=meta,
        )
        data = specimen.to_dict()
        assert "_meta" in data
        assert data["_meta"]["source_id"] == "ext-456"
        assert data["_meta"]["imported_at"] == "2024-06-01T12:00:00Z"

    def test_to_json_with_meta(self) -> None:
        """Verify to_json includes _meta field."""
        meta: SpecimenMeta = {"source_system": "import-tool"}
        specimen = Specimen(
            id="wemush:json789",
            version="1.2.0",
            type=SpecimenType.CULTURE,
            species="Ganoderma lucidum",
            _meta=meta,
        )
        json_str = to_json(specimen)
        data = json.loads(json_str)
        assert "_meta" in data
        assert data["_meta"]["source_system"] == "import-tool"


class TestSpecimenMetaParsing:
    """Tests for _meta field parsing."""

    def test_parse_without_meta(self) -> None:
        """Verify parsing specimen without _meta works."""
        json_str = json.dumps(
            {
                "@context": "https://wemush.com/wols/v1",
                "id": "wemush:parse001",
                "type": "CULTURE",
                "species": "Hericium erinaceus",
            }
        )
        specimen = parse_specimen(json_str)
        assert specimen._meta is None

    def test_parse_with_meta(self) -> None:
        """Verify parsing specimen with _meta works."""
        json_str = json.dumps(
            {
                "@context": "https://wemush.com/wols/v1",
                "id": "wemush:parse002",
                "type": "CULTURE",
                "species": "Hericium erinaceus",
                "_meta": {
                    "source_id": "imported-123",
                    "source_system": "external-db",
                },
            }
        )
        specimen = parse_specimen(json_str)
        assert specimen._meta is not None
        assert specimen._meta["source_id"] == "imported-123"
        assert specimen._meta["source_system"] == "external-db"

    def test_round_trip_preserves_meta(self) -> None:
        """Verify _meta is preserved through serialization round-trip."""
        original_meta: SpecimenMeta = {
            "source_id": "round-trip-001",
            "imported_at": "2024-03-15T08:45:00Z",
            "source_system": "partner-api",
            "schema_version": "1.5",
        }
        original = Specimen(
            id="wemush:roundtrip",
            version="1.2.0",
            type=SpecimenType.SPAWN,
            species="Pleurotus eryngii",
            _meta=original_meta,
        )

        # Serialize and parse back
        json_str = to_json(original)
        parsed = parse_specimen(json_str)

        # Verify all meta fields preserved
        assert parsed._meta is not None
        assert parsed._meta["source_id"] == "round-trip-001"
        assert parsed._meta["imported_at"] == "2024-03-15T08:45:00Z"
        assert parsed._meta["source_system"] == "partner-api"
        assert parsed._meta["schema_version"] == "1.5"


class TestSpecimenMetaValidation:
    """Tests for _meta field validation behavior."""

    def test_unknown_meta_fields_preserved(self) -> None:
        """Verify unknown fields in _meta are preserved."""
        json_str = json.dumps(
            {
                "@context": "https://wemush.com/wols/v1",
                "id": "wemush:custom001",
                "type": "CULTURE",
                "species": "Trametes versicolor",
                "_meta": {
                    "source_id": "abc",
                    "custom_field": "preserved",
                    "another_field": 123,
                },
            }
        )
        specimen = parse_specimen(json_str)
        assert specimen._meta is not None
        # Standard fields
        assert specimen._meta.get("source_id") == "abc"
        # Custom fields should be accessible
        meta_dict = dict(specimen._meta)
        assert "custom_field" in meta_dict

    def test_empty_meta_object(self) -> None:
        """Verify empty _meta object is handled."""
        json_str = json.dumps(
            {
                "@context": "https://wemush.com/wols/v1",
                "id": "wemush:empty001",
                "type": "CULTURE",
                "species": "Cordyceps militaris",
                "_meta": {},
            }
        )
        specimen = parse_specimen(json_str)
        # Empty dict is truthy but has no keys
        assert specimen._meta is not None
        assert len(specimen._meta) == 0
