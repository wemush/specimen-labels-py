"""Specimen validation functionality."""

from __future__ import annotations

import re
from collections.abc import Callable
from enum import Enum
from typing import Any

from wols.constants import ID_PREFIX, WOLS_VERSION
from wols.models.enums import GrowthStage, SpecimenType
from wols.models.specimen import Specimen
from wols.models.validation import ValidationError, ValidationResult

# Valid ID pattern: wemush:{cuid}
ID_PATTERN = re.compile(rf"^{ID_PREFIX}:[a-z0-9]{{24}}$")

# ULID pattern: 26 characters, Crockford's base32
ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$", re.IGNORECASE)

# UUID v4 pattern
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Strict pattern (original CUID format)
STRICT_PATTERN = re.compile(rf"^{ID_PREFIX}:[a-z0-9]+$")


class IdValidationMode(str, Enum):
    """ID validation mode for flexible ID format support (v1.2.0)."""

    STRICT = "strict"
    """wemush:[a-z0-9]+ (original CUID format)."""

    ULID = "ulid"
    """wemush: followed by valid ULID."""

    UUID = "uuid"
    """wemush: followed by valid UUID v4."""

    ANY = "any"
    """wemush: followed by any non-empty string."""


# Type alias for custom validator functions
IdValidator = Callable[[str], bool]


def validate_specimen_id(
    id: str,
    mode: IdValidationMode = IdValidationMode.STRICT,
    custom_validator: IdValidator | None = None,
) -> bool:
    """Validate a specimen ID according to the specified mode.

    Args:
        id: The specimen ID to validate.
        mode: Validation mode (strict, ulid, uuid, any).
        custom_validator: Optional custom validator function.

    Returns:
        True if valid, False otherwise.

    Example:
        >>> validate_specimen_id("wemush:abc123def456ghi789jkl012")
        True
        >>> validate_specimen_id(
        ...     "wemush:01ARZ3NDEKTSV4RRFFQ69G5FAV", IdValidationMode.ULID
        ... )
        True
    """
    # Custom validator takes precedence
    if custom_validator is not None:
        return custom_validator(id)

    # Must have wemush: prefix
    prefix = f"{ID_PREFIX}:"
    if not id.startswith(prefix):
        return False

    suffix = id[len(prefix) :]  # Everything after "wemush:"

    if not suffix:
        return False

    if mode == IdValidationMode.STRICT:
        return bool(STRICT_PATTERN.match(id))
    elif mode == IdValidationMode.ULID:
        return bool(ULID_PATTERN.match(suffix))
    elif mode == IdValidationMode.UUID:
        return bool(UUID_PATTERN.match(suffix))
    elif mode == IdValidationMode.ANY:
        return True

    return False


def validate_specimen(
    specimen: Specimen | dict[str, Any],
    *,
    strict: bool = False,
) -> ValidationResult:
    """Validate a specimen against the WOLS v1.1.0 schema.

    Args:
        specimen: Specimen object or dictionary to validate.
        strict: If True, unknown fields are errors (default: warnings).

    Returns:
        ValidationResult with errors and warnings.

    Example:
        >>> result = validate_specimen(specimen)
        >>> if not result.valid:
        ...     for error in result.errors:
        ...         print(f"{error.path}: {error.message}")
    """
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    # Convert dict to check fields
    data = specimen.to_dict() if isinstance(specimen, Specimen) else specimen

    # Known fields in WOLS schema (v1.2.0 adds _meta)
    known_fields = {
        "@context",
        "@type",
        "id",
        "version",
        "type",
        "species",
        "strain",
        "stage",
        "created",
        "batch",
        "organization",
        "creator",
        "custom",
        "signature",
        "_meta",  # v1.2.0
    }

    # Check for unknown fields
    for field in data:
        if field not in known_fields:
            error = ValidationError(
                path=field,
                code="UNKNOWN_FIELD",
                message=f"Field '{field}' is not in WOLS schema",
            )
            if strict:
                errors.append(error)
            else:
                warnings.append(error)

    # Required field: id
    if "id" not in data:
        errors.append(
            ValidationError(
                path="id",
                code="REQUIRED_FIELD",
                message="Field 'id' is required",
            )
        )
    elif not isinstance(data["id"], str):
        errors.append(
            ValidationError(
                path="id",
                code="INVALID_TYPE",
                message=f"Expected string, got {type(data['id']).__name__}",
            )
        )
    elif not ID_PATTERN.match(data["id"]):
        errors.append(
            ValidationError(
                path="id",
                code="INVALID_ID",
                message="Invalid ID format. Expected "
                f"'{ID_PREFIX}:{{cuid}}', got '{data['id']}'",
            )
        )

    # Required field: type
    if "type" not in data:
        errors.append(
            ValidationError(
                path="type",
                code="REQUIRED_FIELD",
                message="Field 'type' is required",
            )
        )
    elif not isinstance(data["type"], str):
        errors.append(
            ValidationError(
                path="type",
                code="INVALID_TYPE",
                message=f"Expected string, got {type(data['type']).__name__}",
            )
        )
    else:
        valid_types = [t.value for t in SpecimenType]
        if data["type"] not in valid_types:
            errors.append(
                ValidationError(
                    path="type",
                    code="INVALID_VALUE",
                    message=f"Invalid type '{data['type']}'."
                    f" Valid types: {', '.join(valid_types)}",
                )
            )

    # Required field: species
    if "species" not in data:
        errors.append(
            ValidationError(
                path="species",
                code="REQUIRED_FIELD",
                message="Field 'species' is required",
            )
        )
    elif not isinstance(data["species"], str):
        errors.append(
            ValidationError(
                path="species",
                code="INVALID_TYPE",
                message=f"Expected string, got {type(data['species']).__name__}",
            )
        )
    elif not data["species"].strip():
        errors.append(
            ValidationError(
                path="species",
                code="INVALID_VALUE",
                message="Species cannot be empty",
            )
        )

    # Optional field: version
    if "version" in data:
        if not isinstance(data["version"], str):
            errors.append(
                ValidationError(
                    path="version",
                    code="INVALID_TYPE",
                    message=f"Expected string, got {type(data['version']).__name__}",
                )
            )
        elif data["version"] != WOLS_VERSION:
            warnings.append(
                ValidationError(
                    path="version",
                    code="INVALID_VERSION",
                    message=f"Expected version '{WOLS_VERSION}',"
                    f" got '{data['version']}'",
                )
            )

    # Optional field: stage
    if "stage" in data:
        if not isinstance(data["stage"], str):
            errors.append(
                ValidationError(
                    path="stage",
                    code="INVALID_TYPE",
                    message=f"Expected string, got {type(data['stage']).__name__}",
                )
            )
        else:
            valid_stages = [s.value for s in GrowthStage]
            if data["stage"] not in valid_stages:
                errors.append(
                    ValidationError(
                        path="stage",
                        code="INVALID_VALUE",
                        message=f"Invalid stage '{data['stage']}'."
                        f" Valid stages: {', '.join(valid_stages)}",
                    )
                )

    # Optional field: strain
    if "strain" in data:
        strain = data["strain"]
        if isinstance(strain, dict):
            if "name" not in strain:
                errors.append(
                    ValidationError(
                        path="strain.name",
                        code="REQUIRED_FIELD",
                        message="Strain name is required",
                    )
                )
            elif not isinstance(strain["name"], str) or not strain["name"].strip():
                errors.append(
                    ValidationError(
                        path="strain.name",
                        code="INVALID_VALUE",
                        message="Strain name must be a non-empty string",
                    )
                )

            # Validate generation fields
            for gen_field in ["generation", "clonalGeneration"]:
                if gen_field in strain:
                    if not isinstance(strain[gen_field], int):
                        errors.append(
                            ValidationError(
                                path=f"strain.{gen_field}",
                                code="INVALID_TYPE",
                                message=f"Expected integer, got"
                                f" {type(strain[gen_field]).__name__}",
                            )
                        )
                    elif strain[gen_field] < 0:
                        errors.append(
                            ValidationError(
                                path=f"strain.{gen_field}",
                                code="INVALID_VALUE",
                                message=f"{gen_field} must be non-negative",
                            )
                        )
        elif not isinstance(strain, str):
            errors.append(
                ValidationError(
                    path="strain",
                    code="INVALID_TYPE",
                    message=f"Expected string or object, got {type(strain).__name__}",
                )
            )

    # Optional field: created
    if (
        "created" in data
        and data["created"] is not None
        and not isinstance(data["created"], str)
    ):
        errors.append(
            ValidationError(
                path="created",
                code="INVALID_TYPE",
                message=f"Expected ISO 8601 string,"
                f" got {type(data['created']).__name__}",
            )
        )

    # Optional string fields
    for field in ["batch", "organization", "creator", "signature"]:
        if (
            field in data
            and data[field] is not None
            and not isinstance(data[field], str)
        ):
            errors.append(
                ValidationError(
                    path=field,
                    code="INVALID_TYPE",
                    message=f"Expected string, got {type(data[field]).__name__}",
                )
            )

    # Optional field: custom
    if (
        "custom" in data
        and data["custom"] is not None
        and not isinstance(data["custom"], dict)
    ):
        errors.append(
            ValidationError(
                path="custom",
                code="INVALID_TYPE",
                message=f"Expected object, got {type(data['custom']).__name__}",
            )
        )

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
