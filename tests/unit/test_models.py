"""Tests for wols models."""

from __future__ import annotations

import pytest

from wols import (
    GrowthStage,
    Specimen,
    SpecimenRef,
    SpecimenType,
    Strain,
    ValidationError,
    ValidationResult,
)


class TestSpecimenType:
    """Tests for SpecimenType enum."""

    def test_all_types_exist(self) -> None:
        """Verify all specimen types are defined."""
        assert SpecimenType.CULTURE == "CULTURE"
        assert SpecimenType.SPAWN == "SPAWN"
        assert SpecimenType.SUBSTRATE == "SUBSTRATE"
        assert SpecimenType.FRUITING == "FRUITING"
        assert SpecimenType.HARVEST == "HARVEST"

    def test_type_count(self) -> None:
        """Verify correct number of types."""
        assert len(SpecimenType) == 5

    def test_from_string(self) -> None:
        """Test creating type from string value."""
        assert SpecimenType("CULTURE") == SpecimenType.CULTURE

    def test_invalid_type_raises(self) -> None:
        """Test that invalid types raise ValueError."""
        with pytest.raises(ValueError):
            SpecimenType("INVALID")


class TestGrowthStage:
    """Tests for GrowthStage enum."""

    def test_all_stages_exist(self) -> None:
        """Verify all growth stages are defined (v1.2.0: 7 stages)."""
        assert GrowthStage.INOCULATION == "INOCULATION"
        assert GrowthStage.INCUBATION == "INCUBATION"  # v1.2.0
        assert GrowthStage.COLONIZATION == "COLONIZATION"
        assert GrowthStage.PRIMORDIA == "PRIMORDIA"  # v1.2.0
        assert GrowthStage.FRUITING == "FRUITING"
        assert GrowthStage.SENESCENCE == "SENESCENCE"  # v1.2.0
        assert GrowthStage.HARVEST == "HARVEST"

    def test_stage_count(self) -> None:
        """Verify correct number of stages (v1.2.0: 7 stages)."""
        assert len(GrowthStage) == 7

    def test_invalid_stage_raises(self) -> None:
        """Test that invalid stages raise ValueError."""
        with pytest.raises(ValueError):
            GrowthStage("INVALID")


class TestStrain:
    """Tests for Strain dataclass."""

    def test_minimal_strain(self) -> None:
        """Test creating strain with only required fields."""
        strain = Strain(name="Blue Oyster")
        assert strain.name == "Blue Oyster"
        assert strain.generation is None

    def test_full_strain(self) -> None:
        """Test creating strain with all fields."""
        strain = Strain(
            name="Blue Oyster",
            generation=3,
            clonal_generation=1,
            source="Wild clone",
        )
        assert strain.generation == 3
        assert strain.clonal_generation == 1

    def test_to_dict(self) -> None:
        """Test to_dict conversion."""
        strain = Strain(name="Blue Oyster", generation=3)
        result = strain.to_dict()
        assert result["name"] == "Blue Oyster"
        assert result["generation"] == 3

    def test_from_dict(self) -> None:
        """Test creating strain from dict."""
        data = {"name": "Blue Oyster", "generation": 3}
        strain = Strain.from_dict(data)
        assert strain.name == "Blue Oyster"
        assert strain.generation == 3

    def test_to_dict_with_clonal_generation(self) -> None:
        """Test to_dict includes clonalGeneration when set."""
        strain = Strain(name="Blue Oyster", clonal_generation=2)
        result = strain.to_dict()
        assert result["name"] == "Blue Oyster"
        assert result["clonalGeneration"] == 2

    def test_to_dict_with_lineage(self) -> None:
        """Test to_dict includes lineage when set."""
        strain = Strain(name="Blue Oyster", lineage="Parent Strain A")
        result = strain.to_dict()
        assert result["lineage"] == "Parent Strain A"

    def test_to_dict_with_source(self) -> None:
        """Test to_dict includes source when set."""
        strain = Strain(name="Blue Oyster", source="Wild clone")
        result = strain.to_dict()
        assert result["source"] == "Wild clone"

    def test_to_dict_full_strain(self) -> None:
        """Test to_dict with all fields set."""
        strain = Strain(
            name="Blue Oyster",
            generation=3,
            clonal_generation=2,
            lineage="Parent A",
            source="Lab culture",
        )
        result = strain.to_dict()
        assert result["name"] == "Blue Oyster"
        assert result["generation"] == 3
        assert result["clonalGeneration"] == 2
        assert result["lineage"] == "Parent A"
        assert result["source"] == "Lab culture"

    def test_from_dict_with_all_fields(self) -> None:
        """Test from_dict with all fields."""
        data = {
            "name": "Blue Oyster",
            "generation": 3,
            "clonalGeneration": 2,
            "lineage": "Parent A",
            "source": "Lab culture",
        }
        strain = Strain.from_dict(data)
        assert strain.name == "Blue Oyster"
        assert strain.generation == 3
        assert strain.clonal_generation == 2
        assert strain.lineage == "Parent A"
        assert strain.source == "Lab culture"


class TestSpecimen:
    """Tests for Specimen dataclass."""

    def test_minimal_specimen(self) -> None:
        """Test creating specimen with only required fields."""
        specimen = Specimen(
            id="wemush:abc123def456ghijklmnopqr",
            version="1.1.0",
            type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )
        assert specimen.id == "wemush:abc123def456ghijklmnopqr"
        assert specimen.version == "1.1.0"
        assert specimen.type == SpecimenType.CULTURE
        assert specimen.species == "Pleurotus ostreatus"

    def test_to_dict_includes_context(self) -> None:
        """Test that to_dict includes JSON-LD context."""
        specimen = Specimen(
            id="wemush:abc123def456ghijklmnopqr",
            version="1.1.0",
            type=SpecimenType.CULTURE,
            species="Test",
        )
        result = specimen.to_dict()
        assert result["@context"] == "https://wemush.com/wols/v1"
        assert result["@type"] == "Specimen"

    def test_from_dict(self) -> None:
        """Test creating specimen from dict."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "SUBSTRATE",
            "species": "Pleurotus ostreatus",
            "strain": {"name": "Blue Oyster"},
        }
        specimen = Specimen.from_dict(data)
        assert specimen.type == SpecimenType.SUBSTRATE
        assert specimen.strain is not None
        assert specimen.strain.name == "Blue Oyster"

    def test_from_dict_with_string_strain(self) -> None:
        """Test creating specimen from dict with string strain."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Pleurotus ostreatus",
            "strain": "Blue Oyster",
        }
        specimen = Specimen.from_dict(data)
        assert specimen.strain is not None
        assert specimen.strain.name == "Blue Oyster"

    def test_from_dict_with_datetime_created(self) -> None:
        """Test creating specimen from dict with datetime object."""
        from datetime import UTC, datetime

        created_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Pleurotus ostreatus",
            "created": created_time,
        }
        specimen = Specimen.from_dict(data)
        assert specimen.created is not None
        assert specimen.created == created_time

    def test_from_dict_with_iso_string_created(self) -> None:
        """Test creating specimen from dict with ISO string created."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Pleurotus ostreatus",
            "created": "2024-01-15T10:30:00Z",
        }
        specimen = Specimen.from_dict(data)
        assert specimen.created is not None
        assert specimen.created.year == 2024
        assert specimen.created.month == 1
        assert specimen.created.day == 15

    def test_from_dict_with_stage(self) -> None:
        """Test creating specimen from dict with stage."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "SUBSTRATE",
            "species": "Pleurotus ostreatus",
            "stage": "COLONIZATION",
        }
        specimen = Specimen.from_dict(data)
        assert specimen.stage == GrowthStage.COLONIZATION

    def test_to_dict_with_stage(self) -> None:
        """Test to_dict includes stage when set."""
        specimen = Specimen(
            id="wemush:abc123def456ghijklmnopqr",
            version="1.2.0",
            type=SpecimenType.SUBSTRATE,
            species="Pleurotus ostreatus",
            stage=GrowthStage.PRIMORDIA,
        )
        result = specimen.to_dict()
        assert result["stage"] == "PRIMORDIA"

    def test_to_dict_with_all_optional_fields(self) -> None:
        """Test to_dict includes all optional fields when set."""
        from datetime import UTC, datetime

        specimen = Specimen(
            id="wemush:abc123def456ghijklmnopqr",
            version="1.2.0",
            type=SpecimenType.SUBSTRATE,
            species="Pleurotus ostreatus",
            strain=Strain(name="Blue Oyster"),
            stage=GrowthStage.COLONIZATION,
            created=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            batch="BATCH-001",
            organization="WeMush Labs",
            creator="test-user",
            custom={"temp": 72},
            signature="sig123",
        )
        result = specimen.to_dict()
        assert result["batch"] == "BATCH-001"
        assert result["organization"] == "WeMush Labs"
        assert result["creator"] == "test-user"
        assert result["custom"] == {"temp": 72}
        assert result["signature"] == "sig123"
        assert "created" in result


class TestSpecimenRef:
    """Tests for SpecimenRef dataclass."""

    def test_minimal_ref(self) -> None:
        """Test creating minimal SpecimenRef."""
        ref = SpecimenRef(id="abc123")
        assert ref.id == "abc123"
        assert ref.species_code is None

    def test_full_ref(self) -> None:
        """Test creating full SpecimenRef."""
        ref = SpecimenRef(
            id="abc123",
            species_code="PO",
            stage=GrowthStage.COLONIZATION,
            params={"s": "PO"},
        )
        assert ref.species_code == "PO"
        assert ref.stage == GrowthStage.COLONIZATION


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self) -> None:
        """Test creating a valid result."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert bool(result) is True

    def test_invalid_result(self) -> None:
        """Test creating an invalid result."""
        errors = [ValidationError(path="type", code="REQUIRED", message="Required")]
        result = ValidationResult(valid=False, errors=errors)
        assert result.valid is False
        assert len(result.errors) == 1
