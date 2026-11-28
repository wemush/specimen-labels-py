"""WOLS enumeration types.

Contains SpecimenType and GrowthStage enums per WOLS v1.2.0.
"""

from __future__ import annotations

from enum import Enum


class SpecimenType(str, Enum):
    """Valid specimen types per WOLS v1.2.0.

    Represents the physical form of the specimen in the cultivation lifecycle.
    """

    CULTURE = "CULTURE"
    """Pure culture (agar, liquid)."""

    SPAWN = "SPAWN"
    """Colonized grain/substrate for inoculation."""

    SUBSTRATE = "SUBSTRATE"
    """Bulk substrate (straw, sawdust, etc.)."""

    FRUITING = "FRUITING"
    """Fruiting container/block."""

    HARVEST = "HARVEST"
    """Harvested mushrooms."""


class GrowthStage(str, Enum):
    """Valid growth stages per WOLS v1.2.0.

    Represents the current stage in the growth lifecycle.

    WOLS v1.2.0 introduces 7 research-grade stages for scientific precision:
    - INCUBATION: Post-inoculation, pre-visible growth monitoring
    - PRIMORDIA: Pin initiation / hyphal knot formation
    - SENESCENCE: End-of-life monitoring for research specimens
    """

    INOCULATION = "INOCULATION"
    """Initial spore/culture introduction."""

    INCUBATION = "INCUBATION"
    """Post-inoculation, pre-visible growth monitoring (v1.2.0)."""

    COLONIZATION = "COLONIZATION"
    """Active mycelial growth."""

    PRIMORDIA = "PRIMORDIA"
    """Pin initiation / hyphal knot formation (v1.2.0)."""

    FRUITING = "FRUITING"
    """Fruiting body development."""

    SENESCENCE = "SENESCENCE"
    """End-of-life monitoring for research specimens (v1.2.0)."""

    HARVEST = "HARVEST"
    """Final harvest stage."""


# Ordered tuple for lifecycle progression (v1.2.0)
GROWTH_STAGES: tuple[GrowthStage, ...] = (
    GrowthStage.INOCULATION,
    GrowthStage.INCUBATION,
    GrowthStage.COLONIZATION,
    GrowthStage.PRIMORDIA,
    GrowthStage.FRUITING,
    GrowthStage.SENESCENCE,
    GrowthStage.HARVEST,
)


def get_growth_stage_order(stage: GrowthStage) -> int:
    """Get the numeric order of a growth stage (0-6).

    Args:
        stage: The growth stage to get the order for.

    Returns:
        Integer index in the lifecycle (0 = INOCULATION, 6 = HARVEST).
    """
    return GROWTH_STAGES.index(stage)


def get_next_growth_stage(stage: GrowthStage) -> GrowthStage | None:
    """Get the next growth stage in the lifecycle.

    Args:
        stage: Current growth stage.

    Returns:
        Next stage, or None if already at HARVEST.
    """
    idx = GROWTH_STAGES.index(stage)
    return GROWTH_STAGES[idx + 1] if idx < len(GROWTH_STAGES) - 1 else None


def get_previous_growth_stage(stage: GrowthStage) -> GrowthStage | None:
    """Get the previous growth stage in the lifecycle.

    Args:
        stage: Current growth stage.

    Returns:
        Previous stage, or None if already at INOCULATION.
    """
    idx = GROWTH_STAGES.index(stage)
    return GROWTH_STAGES[idx - 1] if idx > 0 else None


# ---------------------------------------------------------------------------
# WOLS 1.5 data model (1.5.0-rc.1)
# ---------------------------------------------------------------------------


class Condition(str, Enum):
    """Health or terminal state of a specimen, separate from its stage (v1.5.0).

    Absent means ``ACTIVE``. Contamination and disposal are conditions, never
    growth stages.
    """

    ACTIVE = "ACTIVE"
    CONTAMINATED = "CONTAMINATED"
    EXHAUSTED = "EXHAUSTED"
    DISPOSED = "DISPOSED"
    ARCHIVED = "ARCHIVED"


class SpecimenForm(str, Enum):
    """Registered values of ``form``: the specific form within ``type`` (v1.5.0).

    ``form`` is an open vocabulary: any other value must start with ``x-``
    and use only lowercase letters, digits and hyphens (``x-koji-rice``).
    """

    AGAR_PLATE = "AGAR_PLATE"
    SLANT = "SLANT"
    TISSUE_CULTURE = "TISSUE_CULTURE"
    LIQUID_CULTURE = "LIQUID_CULTURE"
    SPORE_SYRINGE = "SPORE_SYRINGE"
    SPORE_PRINT = "SPORE_PRINT"
    SPORE_SWAB = "SPORE_SWAB"
    GRAIN_SPAWN = "GRAIN_SPAWN"
    SAWDUST_SPAWN = "SAWDUST_SPAWN"
    PLUG_SPAWN = "PLUG_SPAWN"
    SUBSTRATE_BLOCK = "SUBSTRATE_BLOCK"
    BULK_SUBSTRATE = "BULK_SUBSTRATE"
    FRUITING_BLOCK = "FRUITING_BLOCK"
    FRUITING_BAG = "FRUITING_BAG"
    LOG = "LOG"
    BED = "BED"
    FRESH = "FRESH"
    DRIED = "DRIED"
    PROCESSED = "PROCESSED"
    EXTRACT = "EXTRACT"
    LIVE_SAMPLE = "LIVE_SAMPLE"


class ContainerFormat(str, Enum):
    """Registered values of ``container.format`` (v1.5.0).

    Any other value must start with ``x-``, as for :class:`SpecimenForm`.
    """

    PETRI_DISH = "PETRI_DISH"
    SLANT_TUBE = "SLANT_TUBE"
    JAR = "JAR"
    BOTTLE = "BOTTLE"
    CARBOY = "CARBOY"
    SYRINGE = "SYRINGE"
    BAG = "BAG"
    MONOTUB = "MONOTUB"
    BUCKET = "BUCKET"
    COMPRESSED_BLOCK = "COMPRESSED_BLOCK"
    TRAY = "TRAY"
    OTHER = "OTHER"


class ParentRelation(str, Enum):
    """How a parent in ``derivedFrom`` was used (v1.5.0).

    ``SUBCULTURE`` increments ``clonalGeneration`` and ``transferDepth``;
    ``EXPANSION`` and ``SPAWN_TO_BULK`` increment ``transferDepth`` only;
    ``CROSS`` starts a new filial generation.
    """

    SUBCULTURE = "SUBCULTURE"
    EXPANSION = "EXPANSION"
    SPAWN_TO_BULK = "SPAWN_TO_BULK"
    COMBINED = "COMBINED"
    CLONE = "CLONE"
    SPORE_ISOLATE = "SPORE_ISOLATE"
    CROSS = "CROSS"
    REPACK = "REPACK"
