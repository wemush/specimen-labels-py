"""Specimen validation functionality."""

from __future__ import annotations

import re
from collections.abc import Callable
from enum import Enum
from typing import Any

from wols.constants import ID_PREFIX, SUPPORTED_VERSIONS, WOLS_CONTEXT, WOLS_VERSION
from wols.generation import (
    NUMERIC_GENERATION,
    is_valid_generation,
    numeric_generation_message,
)
from wols.models.enums import GrowthStage, SpecimenType
from wols.models.specimen import (
    Specimen,
    is_encrypted_field,
    is_non_negative_int,
    transfer_depth_below_clonal,
)
from wols.models.validation import ValidationError, ValidationResult

# CUID pattern: wemush: followed by a 24-character lowercase CUID2.
# Only enforced with IdValidationMode.CUID (opt-in).
ID_PATTERN = re.compile(rf"^{ID_PREFIX}:[a-z0-9]{{24}}$")

# ULID pattern: 26 characters, Crockford's base32
ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$", re.IGNORECASE)

# UUID v4 pattern
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Strict pattern: wemush: followed by any non-empty lowercase alphanumeric string.
# Note: This is less restrictive than ID_PATTERN which requires exactly 24 chars.
# The 24-char constraint is enforced separately in validate_specimen.
STRICT_PATTERN = re.compile(rf"^{ID_PREFIX}:[a-z0-9]+$")


class IdValidationMode(str, Enum):
    """ID validation mode for flexible ID format support.

    WOLS requires implementations to accept any non-empty suffix after
    ``wemush:``, so :attr:`ANY` is the default everywhere. The other modes
    are opt-in checks for systems that issue IDs in a specific format.
    """

    STRICT = "strict"
    """wemush: followed by lowercase alphanumeric characters (validates prefix and charset)."""

    ULID = "ulid"
    """wemush: followed by valid ULID."""

    UUID = "uuid"
    """wemush: followed by valid UUID v4."""

    ANY = "any"
    """wemush: followed by any non-empty string (default, per spec)."""

    CUID = "cuid"
    """wemush: followed by a 24-character lowercase CUID2 (the 1.x default)."""


# Type alias for custom validator functions
IdValidator = Callable[[str], bool]


def validate_specimen_id(
    id: str,
    mode: IdValidationMode = IdValidationMode.ANY,
    custom_validator: IdValidator | None = None,
) -> bool:
    """Validate a specimen ID according to the specified mode.

    Args:
        id: The specimen ID to validate.
        mode: Validation mode (any, strict, cuid, ulid, uuid). Defaults to
            ``ANY``: any non-empty suffix after ``wemush:``.
        custom_validator: Optional custom validator function.

    Returns:
        True if valid, False otherwise.

    Example:
        >>> validate_specimen_id("wemush:WM-LC-250114-000001")
        True
        >>> validate_specimen_id("wemush:WM-LC-1", IdValidationMode.STRICT)
        False
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
        return bool(STRICT_PATTERN.fullmatch(id))
    elif mode == IdValidationMode.CUID:
        return bool(ID_PATTERN.fullmatch(id))
    elif mode == IdValidationMode.ULID:
        return bool(ULID_PATTERN.fullmatch(suffix))
    elif mode == IdValidationMode.UUID:
        return bool(UUID_PATTERN.fullmatch(suffix))
    elif mode == IdValidationMode.ANY:
        return True

    return False


_is_encrypted_field = is_encrypted_field


def validate_specimen(
    specimen: Specimen | dict[str, Any],
    *,
    strict: bool = False,
    id_mode: IdValidationMode = IdValidationMode.ANY,
) -> ValidationResult:
    """Validate a specimen against the WOLS v1.4.0 schema.

    Fields replaced by field-level encryption objects
    (``{"encrypted": true, ...}``) are accepted without inspecting their
    plaintext.

    Args:
        specimen: Specimen object or dictionary to validate.
        strict: If True, unknown fields are errors (default: warnings).
        id_mode: ID suffix check. Defaults to ``ANY`` (any non-empty suffix
            after ``wemush:``), as the specification requires. Pass another
            mode to opt in to a stricter format.

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
                message=f"Field '{field}' is not in WOLS schema; "
                "put vendor-specific data under 'custom'",
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
    elif not validate_specimen_id(data["id"], id_mode):
        expected = (
            f"'{ID_PREFIX}:' followed by a non-empty suffix"
            if id_mode == IdValidationMode.ANY
            else f"'{ID_PREFIX}:' followed by a {id_mode.value} suffix"
        )
        errors.append(
            ValidationError(
                path="id",
                code="INVALID_ID",
                message=f"Invalid ID format. Expected {expected}, got '{data['id']}'",
            )
        )

    # JSON-LD fields: a wrong value is an error. A missing value is a
    # warning so that partial dictionaries can still be checked.
    for field, expected_value in (("@context", WOLS_CONTEXT), ("@type", "Specimen")):
        if field not in data:
            warnings.append(
                ValidationError(
                    path=field,
                    code="MISSING_FIELD",
                    message=f"Field '{field}' should be '{expected_value}'",
                )
            )
        elif data[field] != expected_value:
            errors.append(
                ValidationError(
                    path=field,
                    code="INVALID_VALUE",
                    message=f"Expected '{expected_value}', got {data[field]!r}",
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
        elif data["version"] not in SUPPORTED_VERSIONS:
            warnings.append(
                ValidationError(
                    path="version",
                    code="INVALID_VERSION",
                    message=f"Unrecognized version '{data['version']}'. This "
                    f"library reads {', '.join(sorted(SUPPORTED_VERSIONS))} "
                    f"and writes {WOLS_VERSION}",
                )
            )

    # Optional field: stage
    if "stage" in data and not _is_encrypted_field(data["stage"]):
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
    if "strain" in data and not _is_encrypted_field(data["strain"]):
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

            _validate_strain_counters(strain, errors, warnings)
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
            and not (field != "signature" and _is_encrypted_field(data[field]))
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


def _validate_strain_counters(
    strain: dict[str, Any],
    errors: list[ValidationError],
    warnings: list[ValidationError],
) -> None:
    """Validate generation, clonalGeneration, and transferDepth (v1.3.0)."""
    # generation: filial notation string (P, F1, G2, 3) or a non-negative int
    if "generation" in strain and strain["generation"] is not None:
        generation = strain["generation"]
        if isinstance(generation, str):
            if not is_valid_generation(generation):
                errors.append(
                    ValidationError(
                        path="strain.generation",
                        code="INVALID_VALUE",
                        message=f"Unrecognized generation '{generation}'. "
                        "Expected P, P1, F{n}, G{n}, or a number",
                    )
                )
        elif isinstance(generation, bool) or not isinstance(generation, int):
            errors.append(
                ValidationError(
                    path="strain.generation",
                    code="INVALID_TYPE",
                    message="Expected string or integer, got "
                    f"{type(generation).__name__}",
                )
            )
        elif generation < 0:
            errors.append(
                ValidationError(
                    path="strain.generation",
                    code="INVALID_VALUE",
                    message="generation must be non-negative",
                )
            )
        else:
            # WOLS 1.4.0: a JSON integer is read as its decimal string.
            warnings.append(
                ValidationError(
                    path="strain.generation",
                    code=NUMERIC_GENERATION,
                    message=numeric_generation_message(generation),
                )
            )

    # clonalGeneration and transferDepth: non-negative integers
    valid_counters: dict[str, int] = {}
    for counter in ("clonalGeneration", "transferDepth"):
        if counter not in strain or strain[counter] is None:
            continue
        value = strain[counter]
        if is_non_negative_int(value):
            valid_counters[counter] = value
        elif isinstance(value, bool) or not isinstance(value, int):
            errors.append(
                ValidationError(
                    path=f"strain.{counter}",
                    code="INVALID_TYPE",
                    message=f"Expected integer, got {type(value).__name__}",
                )
            )
        else:
            errors.append(
                ValidationError(
                    path=f"strain.{counter}",
                    code="INVALID_VALUE",
                    message=f"{counter} must be non-negative",
                )
            )

    if transfer_depth_below_clonal(
        valid_counters.get("clonalGeneration"), valid_counters.get("transferDepth")
    ):
        warnings.append(
            ValidationError(
                path="strain.transferDepth",
                code="INCONSISTENT_VALUE",
                message=f"transferDepth ({valid_counters['transferDepth']}) "
                "should be at least clonalGeneration "
                f"({valid_counters['clonalGeneration']}); every subculture is "
                "also a transfer",
            )
        )
