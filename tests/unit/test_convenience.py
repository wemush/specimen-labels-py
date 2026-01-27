"""Tests for convenience parsing functions (v1.2.0)."""

from __future__ import annotations

import pytest

from wols import (
    GrowthStage,
    SpecimenRef,
    WolsParseError,
    parse_compact_url,
    parse_compact_url_or_none,
    parse_compact_url_or_throw,
)


class TestParseCompactUrlOrThrow:
    """Tests for parse_compact_url_or_throw function."""

    def test_valid_url_returns_specimen_ref(self) -> None:
        """Verify valid URL returns SpecimenRef."""
        ref = parse_compact_url_or_throw("web+wemush://v1/abc123?s=PO")
        assert isinstance(ref, SpecimenRef)
        assert ref.id == "abc123"
        assert ref.species_code == "PO"

    def test_raises_on_invalid_scheme(self) -> None:
        """Verify raises WolsParseError on invalid scheme."""
        with pytest.raises(WolsParseError) as exc_info:
            parse_compact_url_or_throw("invalid://v1/abc123")
        assert exc_info.value.code == "INVALID_SCHEME"

    def test_raises_on_missing_version(self) -> None:
        """Verify raises WolsParseError on missing version."""
        with pytest.raises(WolsParseError) as exc_info:
            parse_compact_url_or_throw("wemush://abc123")
        assert exc_info.value.code == "INVALID_PATH"

    def test_raises_on_missing_id(self) -> None:
        """Verify raises WolsParseError on missing ID."""
        with pytest.raises(WolsParseError) as exc_info:
            parse_compact_url_or_throw("wemush://v1/")
        assert exc_info.value.code == "INVALID_PATH"

    def test_same_behavior_as_parse_compact_url(self) -> None:
        """Verify same behavior as parse_compact_url."""
        url = "web+wemush://v1/test123?s=HE&st=FRU"

        ref1 = parse_compact_url(url)
        ref2 = parse_compact_url_or_throw(url)

        assert ref1.id == ref2.id
        assert ref1.species_code == ref2.species_code
        assert ref1.stage == ref2.stage


class TestParseCompactUrlOrNone:
    """Tests for parse_compact_url_or_none function."""

    def test_valid_url_returns_specimen_ref(self) -> None:
        """Verify valid URL returns SpecimenRef."""
        ref = parse_compact_url_or_none("web+wemush://v1/abc123?s=PO")
        assert ref is not None
        assert isinstance(ref, SpecimenRef)
        assert ref.id == "abc123"
        assert ref.species_code == "PO"

    def test_invalid_scheme_returns_none(self) -> None:
        """Verify invalid scheme returns None instead of raising."""
        ref = parse_compact_url_or_none("invalid://v1/abc123")
        assert ref is None

    def test_missing_version_returns_none(self) -> None:
        """Verify missing version returns None."""
        ref = parse_compact_url_or_none("wemush://abc123")
        assert ref is None

    def test_empty_string_returns_none(self) -> None:
        """Verify empty string returns None."""
        ref = parse_compact_url_or_none("")
        assert ref is None

    def test_malformed_url_returns_none(self) -> None:
        """Verify malformed URL returns None."""
        ref = parse_compact_url_or_none("not a url at all")
        assert ref is None


class TestConvenienceFunctionsWithSchemes:
    """Tests for convenience functions with different URL schemes."""

    def test_wemush_scheme(self) -> None:
        """Verify wemush:// scheme works."""
        ref = parse_compact_url_or_none("wemush://v1/native123?s=PO")
        assert ref is not None
        assert ref.id == "native123"

    def test_web_plus_wemush_scheme(self) -> None:
        """Verify web+wemush:// scheme works."""
        ref = parse_compact_url_or_none("web+wemush://v1/pwa123?s=LE")
        assert ref is not None
        assert ref.id == "pwa123"

    def test_https_scheme(self) -> None:
        """Verify https:// scheme works."""
        ref = parse_compact_url_or_none("https://wemush.com/s/v1/web123?s=GL")
        assert ref is not None
        assert ref.id == "web123"


class TestConvenienceFunctionsWithStage:
    """Tests for convenience functions with stage parsing."""

    def test_stage_code_parsed(self) -> None:
        """Verify stage code is parsed correctly."""
        ref = parse_compact_url_or_throw("web+wemush://v1/abc123?s=PO&st=COL")
        assert ref.stage == GrowthStage.COLONIZATION

    def test_fruiting_stage(self) -> None:
        """Verify FRUITING stage is parsed."""
        ref = parse_compact_url_or_throw("web+wemush://v1/abc123?st=FRU")
        assert ref.stage == GrowthStage.FRUITING

    def test_harvest_stage(self) -> None:
        """Verify HARVEST stage is parsed."""
        ref = parse_compact_url_or_throw("web+wemush://v1/abc123?st=HAR")
        assert ref.stage == GrowthStage.HARVEST

    def test_new_incubation_stage(self) -> None:
        """Verify new INCUBATION stage (v1.2.0) is parsed."""
        ref = parse_compact_url_or_throw("web+wemush://v1/abc123?st=INC")
        assert ref.stage == GrowthStage.INCUBATION

    def test_new_primordia_stage(self) -> None:
        """Verify new PRIMORDIA stage (v1.2.0) is parsed."""
        ref = parse_compact_url_or_throw("web+wemush://v1/abc123?st=PRI")
        assert ref.stage == GrowthStage.PRIMORDIA

    def test_new_senescence_stage(self) -> None:
        """Verify new SENESCENCE stage (v1.2.0) is parsed."""
        ref = parse_compact_url_or_throw("web+wemush://v1/abc123?st=SEN")
        assert ref.stage == GrowthStage.SENESCENCE


class TestConvenienceFunctionsParams:
    """Tests for convenience functions parameter handling."""

    def test_all_params_captured(self) -> None:
        """Verify all query params are captured."""
        ref = parse_compact_url_or_throw(
            "web+wemush://v1/abc123?s=PO&st=COL&custom=value"
        )
        assert ref.params["s"] == "PO"
        assert ref.params["st"] == "COL"
        assert ref.params["custom"] == "value"

    def test_missing_optional_params(self) -> None:
        """Verify missing optional params don't cause issues."""
        ref = parse_compact_url_or_throw("web+wemush://v1/abc123")
        assert ref.id == "abc123"
        assert ref.species_code is None
        assert ref.stage is None


class TestOrNoneVsOrThrowBehavior:
    """Tests comparing or_none vs or_throw behavior."""

    def test_both_succeed_on_valid(self) -> None:
        """Verify both functions succeed on valid input."""
        url = "web+wemush://v1/valid123?s=PO"

        ref_throw = parse_compact_url_or_throw(url)
        ref_none = parse_compact_url_or_none(url)

        assert ref_throw is not None
        assert ref_none is not None
        assert ref_throw.id == ref_none.id

    def test_different_behavior_on_invalid(self) -> None:
        """Verify different behavior on invalid input."""
        url = "invalid://bad"

        # or_throw raises
        with pytest.raises(WolsParseError):
            parse_compact_url_or_throw(url)

        # or_none returns None
        result = parse_compact_url_or_none(url)
        assert result is None
