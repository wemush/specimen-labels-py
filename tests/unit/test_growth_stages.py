"""Tests for extended growth stages (v1.2.0)."""

from __future__ import annotations

from wols import (
    GROWTH_STAGES,
    GrowthStage,
    get_growth_stage_order,
    get_next_growth_stage,
    get_previous_growth_stage,
)


class TestGrowthStageEnum:
    """Tests for GrowthStage enum values."""

    def test_has_seven_stages(self) -> None:
        """Verify there are exactly 7 growth stages in v1.2.0."""
        assert len(GrowthStage) == 7

    def test_inoculation_exists(self) -> None:
        """Verify INOCULATION stage exists."""
        assert GrowthStage.INOCULATION.value == "INOCULATION"

    def test_incubation_exists(self) -> None:
        """Verify INCUBATION stage exists (new in v1.2.0)."""
        assert GrowthStage.INCUBATION.value == "INCUBATION"

    def test_colonization_exists(self) -> None:
        """Verify COLONIZATION stage exists."""
        assert GrowthStage.COLONIZATION.value == "COLONIZATION"

    def test_primordia_exists(self) -> None:
        """Verify PRIMORDIA stage exists (new in v1.2.0)."""
        assert GrowthStage.PRIMORDIA.value == "PRIMORDIA"

    def test_fruiting_exists(self) -> None:
        """Verify FRUITING stage exists."""
        assert GrowthStage.FRUITING.value == "FRUITING"

    def test_senescence_exists(self) -> None:
        """Verify SENESCENCE stage exists (new in v1.2.0)."""
        assert GrowthStage.SENESCENCE.value == "SENESCENCE"

    def test_harvest_exists(self) -> None:
        """Verify HARVEST stage exists."""
        assert GrowthStage.HARVEST.value == "HARVEST"

    def test_is_str_enum(self) -> None:
        """Verify GrowthStage is a string enum."""
        assert isinstance(GrowthStage.INOCULATION, str)
        assert GrowthStage.INOCULATION == "INOCULATION"


class TestGrowthStagesTuple:
    """Tests for GROWTH_STAGES ordered tuple."""

    def test_is_tuple(self) -> None:
        """Verify GROWTH_STAGES is a tuple."""
        assert isinstance(GROWTH_STAGES, tuple)

    def test_has_seven_elements(self) -> None:
        """Verify GROWTH_STAGES has 7 elements."""
        assert len(GROWTH_STAGES) == 7

    def test_correct_order(self) -> None:
        """Verify GROWTH_STAGES is in lifecycle order."""
        expected = (
            GrowthStage.INOCULATION,
            GrowthStage.INCUBATION,
            GrowthStage.COLONIZATION,
            GrowthStage.PRIMORDIA,
            GrowthStage.FRUITING,
            GrowthStage.SENESCENCE,
            GrowthStage.HARVEST,
        )
        assert expected == GROWTH_STAGES

    def test_first_stage_is_inoculation(self) -> None:
        """Verify first stage is INOCULATION."""
        assert GROWTH_STAGES[0] == GrowthStage.INOCULATION

    def test_last_stage_is_harvest(self) -> None:
        """Verify last stage is HARVEST."""
        assert GROWTH_STAGES[-1] == GrowthStage.HARVEST


class TestGetGrowthStageOrder:
    """Tests for get_growth_stage_order function."""

    def test_inoculation_is_zero(self) -> None:
        """Verify INOCULATION has order 0."""
        assert get_growth_stage_order(GrowthStage.INOCULATION) == 0

    def test_incubation_is_one(self) -> None:
        """Verify INCUBATION has order 1."""
        assert get_growth_stage_order(GrowthStage.INCUBATION) == 1

    def test_colonization_is_two(self) -> None:
        """Verify COLONIZATION has order 2."""
        assert get_growth_stage_order(GrowthStage.COLONIZATION) == 2

    def test_primordia_is_three(self) -> None:
        """Verify PRIMORDIA has order 3."""
        assert get_growth_stage_order(GrowthStage.PRIMORDIA) == 3

    def test_fruiting_is_four(self) -> None:
        """Verify FRUITING has order 4."""
        assert get_growth_stage_order(GrowthStage.FRUITING) == 4

    def test_senescence_is_five(self) -> None:
        """Verify SENESCENCE has order 5."""
        assert get_growth_stage_order(GrowthStage.SENESCENCE) == 5

    def test_harvest_is_six(self) -> None:
        """Verify HARVEST has order 6."""
        assert get_growth_stage_order(GrowthStage.HARVEST) == 6


class TestGetNextGrowthStage:
    """Tests for get_next_growth_stage function."""

    def test_inoculation_to_incubation(self) -> None:
        """Verify INOCULATION -> INCUBATION."""
        assert get_next_growth_stage(GrowthStage.INOCULATION) == GrowthStage.INCUBATION

    def test_incubation_to_colonization(self) -> None:
        """Verify INCUBATION -> COLONIZATION."""
        assert get_next_growth_stage(GrowthStage.INCUBATION) == GrowthStage.COLONIZATION

    def test_colonization_to_primordia(self) -> None:
        """Verify COLONIZATION -> PRIMORDIA."""
        assert get_next_growth_stage(GrowthStage.COLONIZATION) == GrowthStage.PRIMORDIA

    def test_primordia_to_fruiting(self) -> None:
        """Verify PRIMORDIA -> FRUITING."""
        assert get_next_growth_stage(GrowthStage.PRIMORDIA) == GrowthStage.FRUITING

    def test_fruiting_to_senescence(self) -> None:
        """Verify FRUITING -> SENESCENCE."""
        assert get_next_growth_stage(GrowthStage.FRUITING) == GrowthStage.SENESCENCE

    def test_senescence_to_harvest(self) -> None:
        """Verify SENESCENCE -> HARVEST."""
        assert get_next_growth_stage(GrowthStage.SENESCENCE) == GrowthStage.HARVEST

    def test_harvest_returns_none(self) -> None:
        """Verify HARVEST returns None (no next stage)."""
        assert get_next_growth_stage(GrowthStage.HARVEST) is None


class TestGetPreviousGrowthStage:
    """Tests for get_previous_growth_stage function."""

    def test_inoculation_returns_none(self) -> None:
        """Verify INOCULATION returns None (no previous stage)."""
        assert get_previous_growth_stage(GrowthStage.INOCULATION) is None

    def test_incubation_to_inoculation(self) -> None:
        """Verify INCUBATION -> INOCULATION."""
        result = get_previous_growth_stage(GrowthStage.INCUBATION)
        assert result == GrowthStage.INOCULATION

    def test_colonization_to_incubation(self) -> None:
        """Verify COLONIZATION -> INCUBATION."""
        result = get_previous_growth_stage(GrowthStage.COLONIZATION)
        assert result == GrowthStage.INCUBATION

    def test_primordia_to_colonization(self) -> None:
        """Verify PRIMORDIA -> COLONIZATION."""
        result = get_previous_growth_stage(GrowthStage.PRIMORDIA)
        assert result == GrowthStage.COLONIZATION

    def test_fruiting_to_primordia(self) -> None:
        """Verify FRUITING -> PRIMORDIA."""
        assert get_previous_growth_stage(GrowthStage.FRUITING) == GrowthStage.PRIMORDIA

    def test_senescence_to_fruiting(self) -> None:
        """Verify SENESCENCE -> FRUITING."""
        assert get_previous_growth_stage(GrowthStage.SENESCENCE) == GrowthStage.FRUITING

    def test_harvest_to_senescence(self) -> None:
        """Verify HARVEST -> SENESCENCE."""
        assert get_previous_growth_stage(GrowthStage.HARVEST) == GrowthStage.SENESCENCE
