"""Tests for wols.core.validate."""

from wols import Specimen, SpecimenType, validate_specimen


class TestValidateSpecimen:
    """Tests for validate_specimen function."""

    def test_valid_specimen_dict(self) -> None:
        """Test validating a specimen as dict."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Pleurotus ostreatus",
        }
        result = validate_specimen(data)
        assert result.valid is True

    def test_missing_id(self) -> None:
        """Test that missing ID is an error."""
        data = {"type": "CULTURE", "species": "Test"}
        result = validate_specimen(data)
        assert result.valid is False
        assert any(e.code == "REQUIRED_FIELD" and e.path == "id" for e in result.errors)

    def test_missing_type(self) -> None:
        """Test that missing type is an error."""
        data = {"id": "wemush:abc123def456ghijklmnopqr", "species": "Test"}
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "REQUIRED_FIELD" and e.path == "type" for e in result.errors
        )

    def test_invalid_type_value(self) -> None:
        """Test that invalid type value is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "INVALID",
            "species": "Test",
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_VALUE" and e.path == "type" for e in result.errors
        )

    def test_unknown_field_warning(self) -> None:
        """Test that unknown fields produce warnings."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "unknownField": "value",
        }
        result = validate_specimen(data)
        assert result.valid is True
        assert any(w.code == "UNKNOWN_FIELD" for w in result.warnings)

    def test_strict_mode_unknown_field_error(self) -> None:
        """Test that unknown fields are errors in strict mode."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "unknownField": "value",
        }
        result = validate_specimen(data, strict=True)
        assert result.valid is False
        assert any(e.code == "UNKNOWN_FIELD" for e in result.errors)

    def test_specimen_object_input(self) -> None:
        """Test validating a Specimen object instead of dict."""
        specimen = Specimen(
            id="wemush:abc123def456ghijklmnopqr",
            version="1.2.0",
            type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )
        result = validate_specimen(specimen)
        assert result.valid is True

    def test_invalid_id_type(self) -> None:
        """Test that non-string ID is an error."""
        data = {
            "id": 12345,
            "type": "CULTURE",
            "species": "Test",
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(e.code == "INVALID_TYPE" and e.path == "id" for e in result.errors)

    def test_invalid_id_format(self) -> None:
        """Test that invalid ID format is an error."""
        data = {
            "id": "invalid-id-format",
            "type": "CULTURE",
            "species": "Test",
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(e.code == "INVALID_ID" and e.path == "id" for e in result.errors)

    def test_invalid_type_type(self) -> None:
        """Test that non-string type is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": 123,
            "species": "Test",
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(e.code == "INVALID_TYPE" and e.path == "type" for e in result.errors)

    def test_missing_species(self) -> None:
        """Test that missing species is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "REQUIRED_FIELD" and e.path == "species" for e in result.errors
        )

    def test_invalid_species_type(self) -> None:
        """Test that non-string species is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": 123,
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "species" for e in result.errors
        )

    def test_empty_species(self) -> None:
        """Test that empty species string is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "   ",
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_VALUE" and e.path == "species" for e in result.errors
        )

    def test_invalid_version_type(self) -> None:
        """Test that non-string version is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "version": 1.2,
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "version" for e in result.errors
        )

    def test_version_mismatch_warning(self) -> None:
        """Test that version mismatch produces a warning."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "version": "1.0.0",
        }
        result = validate_specimen(data)
        assert result.valid is True
        assert any(
            w.code == "INVALID_VERSION" and w.path == "version" for w in result.warnings
        )

    def test_invalid_stage_type(self) -> None:
        """Test that non-string stage is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "stage": 123,
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "stage" for e in result.errors
        )

    def test_invalid_stage_value(self) -> None:
        """Test that invalid stage value is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "stage": "INVALID_STAGE",
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_VALUE" and e.path == "stage" for e in result.errors
        )

    def test_strain_dict_missing_name(self) -> None:
        """Test that strain dict without name is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "strain": {"generation": 2},
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "REQUIRED_FIELD" and e.path == "strain.name"
            for e in result.errors
        )

    def test_strain_dict_empty_name(self) -> None:
        """Test that strain dict with empty name is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "strain": {"name": "   "},
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_VALUE" and e.path == "strain.name" for e in result.errors
        )

    def test_strain_invalid_generation_type(self) -> None:
        """Test that non-integer generation is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "strain": {"name": "Blue Oyster", "generation": "two"},
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and "generation" in e.path for e in result.errors
        )

    def test_strain_negative_generation(self) -> None:
        """Test that negative generation is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "strain": {"name": "Blue Oyster", "generation": -1},
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_VALUE" and "generation" in e.path for e in result.errors
        )

    def test_strain_clonal_generation_invalid_type(self) -> None:
        """Test that non-integer clonalGeneration is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "strain": {"name": "Blue Oyster", "clonalGeneration": "three"},
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and "clonalGeneration" in e.path
            for e in result.errors
        )

    def test_strain_clonal_generation_negative(self) -> None:
        """Test that negative clonalGeneration is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "strain": {"name": "Blue Oyster", "clonalGeneration": -5},
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_VALUE" and "clonalGeneration" in e.path
            for e in result.errors
        )

    def test_strain_invalid_type(self) -> None:
        """Test that non-string/non-dict strain is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "strain": 123,
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "strain" for e in result.errors
        )

    def test_invalid_created_type(self) -> None:
        """Test that non-string created is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "created": 12345,
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "created" for e in result.errors
        )

    def test_invalid_batch_type(self) -> None:
        """Test that non-string batch is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "batch": 123,
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "batch" for e in result.errors
        )

    def test_invalid_organization_type(self) -> None:
        """Test that non-string organization is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "organization": 123,
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "organization" for e in result.errors
        )

    def test_invalid_creator_type(self) -> None:
        """Test that non-string creator is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "creator": 123,
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "creator" for e in result.errors
        )

    def test_invalid_signature_type(self) -> None:
        """Test that non-string signature is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "signature": 123,
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "signature" for e in result.errors
        )

    def test_invalid_custom_type(self) -> None:
        """Test that non-dict custom is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "custom": "not a dict",
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_TYPE" and e.path == "custom" for e in result.errors
        )

    def test_null_optional_fields_valid(self) -> None:
        """Test that null optional fields are valid."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "created": None,
            "batch": None,
            "organization": None,
            "creator": None,
            "signature": None,
            "custom": None,
        }
        result = validate_specimen(data)
        assert result.valid is True

    def test_valid_stage(self) -> None:
        """Test that valid stage is accepted."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "stage": "COLONIZATION",
        }
        result = validate_specimen(data)
        assert result.valid is True

    def test_strain_string_valid(self) -> None:
        """Test that string strain is valid."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "strain": "Blue Oyster",
        }
        result = validate_specimen(data)
        assert result.valid is True

    def test_strain_name_non_string(self) -> None:
        """Test that non-string strain name in dict is an error."""
        data = {
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Test",
            "strain": {"name": 123},
        }
        result = validate_specimen(data)
        assert result.valid is False
        assert any(
            e.code == "INVALID_VALUE" and e.path == "strain.name" for e in result.errors
        )
