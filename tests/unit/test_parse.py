"""Tests for wols.core.parse."""

import pytest

from wols import (
    GrowthStage,
    Specimen,
    SpecimenRef,
    SpecimenType,
    WolsParseError,
    WolsWarning,
    parse_compact_url,
    parse_specimen,
    resolve_species,
)


class TestParseSpecimen:
    """Tests for parse_specimen function."""

    def test_parse_valid_json(self) -> None:
        """Test parsing valid JSON-LD."""
        json_str = """{
            "@context": "https://wemush.com/wols/v1",
            "@type": "Specimen",
            "id": "wemush:clx1abc123def456ghijklmn",
            "version": "1.1.0",
            "type": "SUBSTRATE",
            "species": "Pleurotus ostreatus"
        }"""
        specimen = parse_specimen(json_str)
        assert isinstance(specimen, Specimen)
        assert specimen.id == "wemush:clx1abc123def456ghijklmn"
        assert specimen.type == SpecimenType.SUBSTRATE

    def test_parse_with_strain(self) -> None:
        """Test parsing JSON with strain object."""
        json_str = """{
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Pleurotus ostreatus",
            "strain": {"name": "Blue Oyster", "generation": "3"}
        }"""
        specimen = parse_specimen(json_str)
        assert specimen.strain is not None
        assert specimen.strain.name == "Blue Oyster"
        assert specimen.strain.generation == "3"

    def test_parse_numeric_generation(self) -> None:
        """WOLS 1.4.0: a JSON integer generation parses as its decimal string."""
        json_str = """{
            "id": "wemush:abc123def456ghijklmnopqr",
            "type": "CULTURE",
            "species": "Pleurotus ostreatus",
            "strain": {"name": "Blue Oyster", "generation": 1}
        }"""
        with pytest.warns(WolsWarning, match="strain.generation"):
            specimen = parse_specimen(json_str)
        assert specimen.strain is not None
        assert specimen.strain.generation == "1"

    def test_invalid_json_raises(self) -> None:
        """Test that invalid JSON raises parse error."""
        with pytest.raises(WolsParseError) as exc_info:
            parse_specimen("{invalid json}")
        assert "INVALID_JSON" in str(exc_info.value)

    def test_missing_required_field_raises(self) -> None:
        """Test that missing required field raises parse error."""
        with pytest.raises(WolsParseError) as exc_info:
            parse_specimen('{"id": "wemush:abc123"}')
        assert "REQUIRED_FIELD" in str(exc_info.value)


class TestParseCompactUrl:
    """Tests for parse_compact_url function."""

    def test_parse_wemush_url(self) -> None:
        """Test parsing native wemush:// URL."""
        ref = parse_compact_url("wemush://v1/abc123?s=POSTR&st=COL")
        assert isinstance(ref, SpecimenRef)
        assert ref.id == "abc123"
        assert ref.species_code == "POSTR"
        assert ref.stage == GrowthStage.COLONIZATION

    def test_parse_web_wemush_url(self) -> None:
        """Test parsing PWA-compatible web+wemush:// URL."""
        ref = parse_compact_url("web+wemush://v1/abc123?s=POSTR&st=COL")
        assert isinstance(ref, SpecimenRef)
        assert ref.id == "abc123"
        assert ref.species_code == "POSTR"
        assert ref.stage == GrowthStage.COLONIZATION

    def test_parse_https_url(self) -> None:
        """Test parsing HTTPS URL."""
        ref = parse_compact_url("https://wemush.com/s/v1/abc123?s=POSTR&st=COL")
        assert isinstance(ref, SpecimenRef)
        assert ref.id == "abc123"
        assert ref.species_code == "POSTR"
        assert ref.stage == GrowthStage.COLONIZATION

    def test_parse_https_url_custom_base(self) -> None:
        """Test parsing HTTPS URL with custom base path."""
        ref = parse_compact_url("https://example.com/specimens/v1/abc123?s=HERIN")
        assert ref.id == "abc123"
        assert ref.species_code == "HERIN"

    def test_parse_url_without_query(self) -> None:
        """Test parsing URL without query parameters."""
        ref = parse_compact_url("wemush://v1/abc123def456")
        assert ref.id == "abc123def456"
        assert ref.species_code is None

    def test_parse_web_wemush_url_without_query(self) -> None:
        """Test parsing web+wemush URL without query parameters."""
        ref = parse_compact_url("web+wemush://v1/abc123def456")
        assert ref.id == "abc123def456"
        assert ref.species_code is None

    def test_invalid_scheme_raises(self) -> None:
        """Test that invalid scheme raises parse error."""
        with pytest.raises(WolsParseError) as exc_info:
            parse_compact_url("http://v1/abc123")
        assert "INVALID_SCHEME" in str(exc_info.value)

    def test_missing_version_raises(self) -> None:
        """Test that missing v1 marker raises parse error."""
        with pytest.raises(WolsParseError) as exc_info:
            parse_compact_url("wemush://abc123")
        assert "INVALID_PATH" in str(exc_info.value)


class TestSpeciesCodeRegistry:
    """Compact URL species codes follow the WOLS 1.5 Species Code Registry."""

    def test_registered_code_resolves(self) -> None:
        ref = parse_compact_url("wemush://v1/abc123?s=POSTR")
        assert ref.species_code == "POSTR"
        assert ref.species == "Pleurotus ostreatus"

    def test_legacy_code_still_reads_with_warning(self) -> None:
        """Labels printed by wols before 1.5 still scan."""
        with pytest.warns(WolsWarning, match="legacy code"):
            ref = parse_compact_url("wemush://v1/abc123?s=PO&st=COL")
        assert ref.species_code == "PO"
        assert ref.species == "Pleurotus ostreatus"
        assert ref.stage == GrowthStage.COLONIZATION

    def test_unregistered_value_is_species_name(self) -> None:
        ref = parse_compact_url("wemush://v1/abc123?s=Morchella%20importuna")
        assert ref.species_code == "Morchella importuna"
        assert ref.species == "Morchella importuna"

    def test_no_species(self) -> None:
        ref = parse_compact_url("wemush://v1/abc123")
        assert ref.species is None

    def test_resolve_species(self) -> None:
        assert resolve_species("LLENC") == "Lentinula edodes"
        assert resolve_species("Morchella importuna") == "Morchella importuna"
        with pytest.warns(WolsWarning):
            assert resolve_species("LE") == "Lentinula edodes"

    def test_codes_are_case_sensitive(self) -> None:
        """Codes are upper case; anything else is a name as written."""
        assert resolve_species("postr") == "postr"

    def test_full_stage_name_parses(self) -> None:
        ref = parse_compact_url("wemush://v1/abc123?st=COLONIZATION")
        assert ref.stage == GrowthStage.COLONIZATION

    def test_unknown_stage_is_none(self) -> None:
        ref = parse_compact_url("wemush://v1/abc123?st=NOPE")
        assert ref.stage is None
        assert ref.params["st"] == "NOPE"
