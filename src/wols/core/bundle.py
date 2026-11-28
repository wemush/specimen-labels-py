"""Records Bundle validation (WOLS 1.5).

A Records Bundle is an optional exchange format: specimen labels plus the
records that are too large or too private to print (strains, recipes,
observations and harvests). Its shape is ``schema/1.5/bundle.schema.json``.
"""

from __future__ import annotations

from typing import Any

from wols.core._schema import (
    BUNDLE_HEADER,
    SPECIMEN_RECORD_MEMBERS,
    check,
    join,
)
from wols.core.validate import IdValidationMode, check_label
from wols.models.validation import ValidationError, ValidationResult

__all__ = ["validate_bundle"]

_RECORD_FIELDS = frozenset(SPECIMEN_RECORD_MEMBERS)


def validate_bundle(
    bundle: dict[str, Any],
    *,
    strict: bool = False,
    id_mode: IdValidationMode = IdValidationMode.ANY,
) -> ValidationResult:
    """Validate a WOLS 1.5 Records Bundle.

    Checks the bundle header, every record against its schema, each entry in
    ``specimens`` as a label (with :func:`validate_specimen`'s rules) plus
    the specimen record members, and that references resolve inside the
    bundle: every ``observations[].specimen`` and ``harvests[].specimen``
    names a specimen in ``specimens``, every ``strainRef`` a strain in
    ``strains`` and every ``recipeRef`` a recipe in ``recipes``.

    Error paths are dot paths from the bundle root, such as
    ``specimens.0.stage`` or ``harvests.0.freshWeight``.

    Args:
        bundle: The bundle, as parsed JSON.
        strict: Passed to the label checks: unknown label members become
            errors instead of warnings.
        id_mode: Passed to the label checks for specimen IDs.

    Returns:
        ValidationResult with errors and warnings.

    Example:
        >>> result = validate_bundle(json.loads(text))
        >>> for error in result.errors:
        ...     print(error)
    """
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    check(bundle, BUNDLE_HEADER, "", errors)
    if not isinstance(bundle, dict):
        return ValidationResult(valid=False, errors=errors)

    specimens = bundle.get("specimens")
    if isinstance(specimens, list):
        for index, record in enumerate(specimens):
            _check_specimen(
                record, f"specimens.{index}", strict, id_mode, errors, warnings
            )

    _check_references(bundle, errors)
    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def _check_specimen(
    record: Any,
    path: str,
    strict: bool,
    id_mode: IdValidationMode,
    errors: list[ValidationError],
    warnings: list[ValidationError],
) -> None:
    if not isinstance(record, dict):
        errors.append(
            ValidationError(
                path=path,
                code="INVALID_TYPE",
                message=f"Expected object, got {type(record).__name__}",
            )
        )
        return
    label_errors, label_warnings = check_label(
        record,
        strict=strict,
        id_mode=id_mode,
        extra_fields=_RECORD_FIELDS,
        prefix=f"{path}.",
    )
    errors.extend(label_errors)
    warnings.extend(label_warnings)
    for name, spec in SPECIMEN_RECORD_MEMBERS.items():
        if name in record:
            check(record[name], spec, join(path, name), errors)


def _ids(records: Any) -> set[str]:
    if not isinstance(records, list):
        return set()
    return {
        r["id"] for r in records if isinstance(r, dict) and isinstance(r.get("id"), str)
    }


def _unresolved(path: str, member: str, value: str, target: str) -> ValidationError:
    return ValidationError(
        path=path,
        code="UNRESOLVED_REFERENCE",
        message=f"{member} {value!r} is not the id of an entry in '{target}'",
    )


def _check_references(bundle: dict[str, Any], errors: list[ValidationError]) -> None:
    specimen_ids = _ids(bundle.get("specimens"))
    targets = {
        "strainRef": ("strains", _ids(bundle.get("strains"))),
        "recipeRef": ("recipes", _ids(bundle.get("recipes"))),
    }

    specimens = bundle.get("specimens")
    if isinstance(specimens, list):
        for index, record in enumerate(specimens):
            if not isinstance(record, dict):
                continue
            for member, (target, ids) in targets.items():
                value = record.get(member)
                if isinstance(value, str) and value not in ids:
                    errors.append(
                        _unresolved(
                            f"specimens.{index}.{member}", member, value, target
                        )
                    )

    for kind in ("observations", "harvests"):
        records = bundle.get(kind)
        if not isinstance(records, list):
            continue
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            value = record.get("specimen")
            if isinstance(value, str) and value not in specimen_ids:
                errors.append(
                    _unresolved(
                        f"{kind}.{index}.specimen", "specimen", value, "specimens"
                    )
                )
