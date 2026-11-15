"""Specimen creation functionality."""

from __future__ import annotations

import warnings
from datetime import UTC, datetime
from typing import Any, overload

from cuid2 import cuid_wrapper

from wols.constants import ID_PREFIX, WOLS_VERSION
from wols.exceptions import WolsValidationError, WolsWarning
from wols.models.enums import GrowthStage, SpecimenType
from wols.models.specimen import Specimen, Strain, transfer_depth_below_clonal
from wols.models.validation import ValidationError
from wols.type_aliases import PRIMORDIA_TYPE_ALIAS, resolve_type_alias

# Configure CUID generator
_cuid = cuid_wrapper()


@overload
def create_specimen(
    *,
    type: SpecimenType | str,
    species: str,
    strain: Strain | str | None = None,
    stage: GrowthStage | str | None = None,
    batch: str | None = None,
    organization: str | None = None,
    creator: str | None = None,
    custom: dict[str, Any] | None = None,
    created: datetime | None = None,
    input_type: None = None,
) -> Specimen: ...


@overload
def create_specimen(
    *,
    type: None = None,
    species: str,
    strain: Strain | str | None = None,
    stage: GrowthStage | str | None = None,
    batch: str | None = None,
    organization: str | None = None,
    creator: str | None = None,
    custom: dict[str, Any] | None = None,
    created: datetime | None = None,
    input_type: SpecimenType | str,
) -> Specimen: ...


def create_specimen(
    *,
    type: SpecimenType | str | None = None,
    species: str,
    strain: Strain | str | None = None,
    stage: GrowthStage | str | None = None,
    batch: str | None = None,
    organization: str | None = None,
    creator: str | None = None,
    custom: dict[str, Any] | None = None,
    created: datetime | None = None,
    input_type: SpecimenType | str | None = None,
) -> Specimen:
    """Create a new specimen with auto-generated CUID.

    String types are matched case-insensitively against the canonical types
    and the alias table (e.g. ``"lc"`` resolves to ``CULTURE``).

    ``PRIMORDIA`` is a growth stage, not a type. When it is supplied as the
    type (WOLS v1.3.0), the type resolves to ``FRUITING``, ``stage`` defaults
    to ``PRIMORDIA`` if no stage was supplied (a supplied stage is never
    overridden), and a :class:`~wols.exceptions.WolsWarning` is emitted.

    Args:
        type: Specimen type (CULTURE, SPAWN, SUBSTRATE, FRUITING, HARVEST)
            or a type alias.
        species: Scientific species name.
        strain: Strain information (string shorthand or Strain object).
        stage: Current growth stage.
        batch: Batch identifier.
        organization: Organization name.
        creator: Creator identifier.
        custom: Custom namespace fields.
        created: Creation timestamp (defaults to current time).
        input_type: Deprecated spelling of ``type``, kept for compatibility
            with 1.x callers. Pass one or the other, not both.

    Returns:
        A new Specimen instance with generated ID.

    Raises:
        WolsValidationError: If required fields are invalid.
        TypeError: If neither ``type`` nor ``input_type`` is given, or both
            are (a calling-convention error, not a data error).

    Example:
        >>> specimen = create_specimen(
        ...     type=SpecimenType.SUBSTRATE,
        ...     species="Pleurotus ostreatus",
        ...     strain="Blue Oyster",
        ...     stage=GrowthStage.COLONIZATION,
        ... )
        >>> print(specimen.id)
        'wemush:clx1abc123def456'
    """
    errors: list[ValidationError] = []

    if type is not None and input_type is not None:
        raise TypeError("Pass either 'type' or 'input_type', not both")
    requested_type = type if type is not None else input_type
    if requested_type is None:
        raise TypeError("create_specimen() missing required argument: 'type'")

    # Validate and convert type
    specimen_type: SpecimenType
    primordia_as_type = False
    if isinstance(requested_type, SpecimenType):
        specimen_type = requested_type
    else:
        if requested_type.strip().upper() == PRIMORDIA_TYPE_ALIAS:
            primordia_as_type = True
        try:
            specimen_type = SpecimenType(resolve_type_alias(requested_type))
        except ValueError:
            valid_types = ", ".join(t.value for t in SpecimenType)
            errors.append(
                ValidationError(
                    path="type",
                    code="INVALID_VALUE",
                    message=f"Invalid specimen type '{requested_type}'."
                    f" Valid types: {valid_types}",
                )
            )
            # Placeholder for type checking
            specimen_type = SpecimenType.CULTURE

    # Validate species
    if not species or not species.strip():
        errors.append(
            ValidationError(
                path="species",
                code="REQUIRED_FIELD",
                message="Species is required and cannot be empty",
            )
        )

    # Convert strain if string
    strain_obj: Strain | None = None
    if strain is not None:
        if isinstance(strain, str):
            if strain.strip():
                strain_obj = Strain(name=strain)
            else:
                errors.append(
                    ValidationError(
                        path="strain",
                        code="INVALID_VALUE",
                        message="Strain name cannot be empty",
                    )
                )
        else:
            strain_obj = strain

    # Validate and convert stage
    growth_stage: GrowthStage | None = None
    if stage is not None:
        if isinstance(stage, str):
            try:
                growth_stage = GrowthStage(stage.strip().upper())
            except ValueError:
                valid_stages = ", ".join(s.value for s in GrowthStage)
                errors.append(
                    ValidationError(
                        path="stage",
                        code="INVALID_VALUE",
                        message=f"Invalid growth stage '{stage}'."
                        f" Valid stages: {valid_stages}",
                    )
                )
        else:
            growth_stage = stage

    # Validate optional string fields
    if batch is not None and not batch.strip():
        errors.append(
            ValidationError(
                path="batch",
                code="INVALID_VALUE",
                message="Batch cannot be empty if provided",
            )
        )

    if organization is not None and not organization.strip():
        errors.append(
            ValidationError(
                path="organization",
                code="INVALID_VALUE",
                message="Organization cannot be empty if provided",
            )
        )

    if creator is not None and not creator.strip():
        errors.append(
            ValidationError(
                path="creator",
                code="INVALID_VALUE",
                message="Creator cannot be empty if provided",
            )
        )

    # Raise if validation errors
    if errors:
        raise WolsValidationError(
            message=f"Failed to create specimen: {len(errors)} validation error(s)",
            errors=errors,
        )

    if primordia_as_type:
        warnings.warn(
            "PRIMORDIA is a growth stage, not a specimen type. Resolved to "
            "type FRUITING"
            + ("" if growth_stage is not None else " with stage PRIMORDIA")
            + '; use type="FRUITING", stage="PRIMORDIA" instead.',
            WolsWarning,
            stacklevel=2,
        )
        if growth_stage is None:
            growth_stage = GrowthStage.PRIMORDIA

    if strain_obj is not None and transfer_depth_below_clonal(
        strain_obj.clonal_generation, strain_obj.transfer_depth
    ):
        warnings.warn(
            f"strain.transferDepth ({strain_obj.transfer_depth}) is less than "
            f"strain.clonalGeneration ({strain_obj.clonal_generation}); every "
            "subculture is also a transfer.",
            WolsWarning,
            stacklevel=2,
        )

    # Generate ID and timestamp
    specimen_id = f"{ID_PREFIX}:{_cuid()}"
    creation_time = created if created is not None else datetime.now(UTC)

    return Specimen(
        id=specimen_id,
        version=WOLS_VERSION,
        type=specimen_type,
        species=species,
        strain=strain_obj,
        stage=growth_stage,
        created=creation_time,
        batch=batch,
        organization=organization,
        creator=creator,
        custom=custom,
    )
