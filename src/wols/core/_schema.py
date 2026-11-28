"""A small checker for the parts of the WOLS 1.5 JSON Schema this library
validates structurally: the 1.5 label members and the Records Bundle.

The definitions below follow ``schema/1.5/label.schema.json`` and
``schema/1.5/bundle.schema.json`` in wemush/open-standard (1.5.0-rc.2). The
schema is normative, so a change there must be copied here; the conformance
tests check the result against the vectors (and against the schema itself
when ``jsonschema`` is installed).

A spec is a dict with any of these keys:

``type``: a JSON type name or a tuple of them; ``const``; ``enum``;
``open_enum`` (an enum, or a string matching ``^x-[a-z0-9-]+$``);
``pattern`` (a compiled regex, searched); ``format`` (``date-time`` or
``date``); ``min_length``; ``min_items``; ``minimum``; ``maximum``;
``required``; ``properties``; ``additional`` (False to reject other
members); ``items``.

``format: uri`` (``publisher.contact`` and ``media[].url``) is not checked:
JSON Schema treats ``format`` as an annotation unless a checker for it is
installed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from wols.models.enums import (
    Condition,
    ContainerFormat,
    GrowthStage,
    ParentRelation,
    SpecimenForm,
)
from wols.models.validation import ValidationError

type Spec = Mapping[str, Any]

EXTENSION_RE = re.compile(r"^x-[a-z0-9-]+$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")
SPECIMEN_ID_RE = re.compile(r"^wemush:.+$")


def join(path: str, key: str | int) -> str:
    """Dot path of a member or array position."""
    return f"{path}.{key}" if path else str(key)


def is_rfc3339(value: str) -> bool:
    """An RFC 3339 date-time with a time zone (``Z`` or ``+hh:mm``)."""
    if "T" not in value.upper() or not (
        value.endswith(("Z", "z")) or (len(value) > 6 and value[-6] in "+-")
    ):
        return False
    try:
        datetime.fromisoformat(value.replace("z", "Z").replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10


def _type_ok(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if isinstance(value, bool):
        return False
    if name == "number":
        return isinstance(value, int | float)
    if name == "integer":
        return isinstance(value, int) or (
            isinstance(value, float) and value.is_integer()
        )
    raise ValueError(f"unknown schema type {name!r}")  # pragma: no cover


def _error(errors: list[ValidationError], path: str, code: str, message: str) -> None:
    errors.append(ValidationError(path=path, code=code, message=message))


def check(value: Any, spec: Spec, path: str, errors: list[ValidationError]) -> None:
    """Check ``value`` against ``spec``, appending one error per problem."""
    kind = spec.get("type")
    if kind is not None:
        kinds = (kind,) if isinstance(kind, str) else kind
        if not any(_type_ok(value, k) for k in kinds):
            _error(
                errors,
                path,
                "INVALID_TYPE",
                f"Expected {' or '.join(kinds)}, got {type(value).__name__}",
            )
            return
    if "const" in spec and value != spec["const"]:
        _error(errors, path, "INVALID_VALUE", f"Expected {spec['const']!r}")
        return
    if "enum" in spec and value not in spec["enum"]:
        _error(
            errors,
            path,
            "INVALID_VALUE",
            f"Invalid value {value!r}. Valid values: {', '.join(spec['enum'])}",
        )
        return
    if "open_enum" in spec and not (
        value in spec["open_enum"]
        or (isinstance(value, str) and EXTENSION_RE.match(value))
    ):
        _error(
            errors,
            path,
            "INVALID_VALUE",
            f"Invalid value {value!r}: use a registered value or an 'x-' "
            "extension (lowercase letters, digits and hyphens)",
        )
        return
    if isinstance(value, str):
        _check_string(value, spec, path, errors)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            _error(errors, path, "INVALID_VALUE", f"Must be at least {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            _error(errors, path, "INVALID_VALUE", f"Must be at most {spec['maximum']}")
    elif isinstance(value, list):
        if "min_items" in spec and len(value) < spec["min_items"]:
            _error(
                errors,
                path,
                "INVALID_VALUE",
                f"Needs at least {spec['min_items']} item(s)",
            )
        if "items" in spec:
            for index, item in enumerate(value):
                check(item, spec["items"], join(path, index), errors)
    elif isinstance(value, dict):
        _check_object(value, spec, path, errors)


def _check_string(
    value: str, spec: Spec, path: str, errors: list[ValidationError]
) -> None:
    if "min_length" in spec and len(value) < spec["min_length"]:
        _error(errors, path, "INVALID_VALUE", "Must not be empty")
    pattern = spec.get("pattern")
    if pattern is not None and not pattern.search(value):
        _error(errors, path, "INVALID_VALUE", f"Invalid value {value!r}")
    fmt = spec.get("format")
    if fmt == "date-time" and not is_rfc3339(value):
        _error(
            errors,
            path,
            "INVALID_VALUE",
            f"Expected an RFC 3339 date-time with a time zone, got {value!r}",
        )
    elif fmt == "date" and not _is_date(value):
        _error(errors, path, "INVALID_VALUE", f"Expected a date, got {value!r}")


def _check_object(
    value: dict[str, Any], spec: Spec, path: str, errors: list[ValidationError]
) -> None:
    properties: Mapping[str, Spec] = spec.get("properties", {})
    for name in spec.get("required", ()):
        if name not in value:
            _error(
                errors,
                join(path, name),
                "REQUIRED_FIELD",
                f"Field '{join(path, name)}' is required",
            )
    for name, member in value.items():
        if name in properties:
            check(member, properties[name], join(path, name), errors)
        elif spec.get("additional", True) is False:
            _error(
                errors,
                join(path, name),
                "UNKNOWN_FIELD",
                f"Field '{name}' is not allowed here",
            )


def _values(enum: type) -> tuple[str, ...]:
    return tuple(member.value for member in enum)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# label.schema.json $defs
# ---------------------------------------------------------------------------

NON_EMPTY: Spec = {"type": "string", "min_length": 1}
SPECIMEN_ID: Spec = {"type": "string", "pattern": SPECIMEN_ID_RE}
DATE_TIME: Spec = {"type": "string", "format": "date-time"}
STRING: Spec = {"type": "string"}
NUMBER: Spec = {"type": "number"}

QUANTITY: Spec = {
    "type": "object",
    "required": ("value", "unit"),
    "properties": {"value": NUMBER, "unit": NON_EMPTY},
    "additional": False,
}

TAXON_IDENTIFIER: Spec = {
    "type": "object",
    "required": ("scheme", "value"),
    "properties": {
        "scheme": {
            "enum": ("mycobank", "indexfungorum", "gbif", "col", "inaturalist", "ncbi")
        },
        "value": NON_EMPTY,
    },
    "additional": False,
}

TAXON: Spec = {
    "type": "object",
    "required": ("scientificName",),
    "properties": {
        "scientificName": NON_EMPTY,
        "authorship": STRING,
        "rank": {
            "enum": ("species", "subspecies", "variety", "form", "genus", "hybrid")
        },
        "identifiers": {"type": "array", "items": TAXON_IDENTIFIER},
        "hybridOf": {
            "type": "array",
            "min_items": 2,
            "items": {
                "type": "object",
                "required": ("scientificName",),
                "properties": {
                    "scientificName": NON_EMPTY,
                    "role": {"enum": ("PARENT_A", "PARENT_B", "UNKNOWN")},
                    "identifiers": {"type": "array", "items": TAXON_IDENTIFIER},
                },
                "additional": False,
            },
        },
    },
    "additional": False,
}

PARENT_LINK: Spec = {
    "type": "object",
    "required": ("id",),
    "properties": {
        "id": SPECIMEN_ID,
        "relation": {"enum": _values(ParentRelation)},
        "quantity": QUANTITY,
    },
    "additional": False,
}

CONTAINER: Spec = {
    "type": "object",
    "required": ("format",),
    "properties": {
        "format": {"open_enum": _values(ContainerFormat)},
        "capacity": QUANTITY,
    },
    "additional": False,
}

GROWTH_STAGE: Spec = {"enum": _values(GrowthStage)}
CONDITION: Spec = {"enum": _values(Condition)}

# The members WOLS 1.5 added to the label, checked exactly as the schema says.
LABEL_V15_MEMBERS: Mapping[str, Spec] = {
    "taxon": TAXON,
    "form": {"open_enum": _values(SpecimenForm)},
    "derivedFrom": {"type": "array", "min_items": 1, "items": PARENT_LINK},
    "condition": CONDITION,
    "container": CONTAINER,
    "lot": NON_EMPTY,
}

# ---------------------------------------------------------------------------
# bundle.schema.json $defs
# ---------------------------------------------------------------------------

RANGE: Spec = {
    "type": "object",
    "properties": {"min": NUMBER, "max": NUMBER},
    "additional": False,
}

QUANTITY_RANGE: Spec = {
    "type": "object",
    "required": ("unit",),
    "properties": {"min": NUMBER, "max": NUMBER, "optimal": NUMBER, "unit": STRING},
    "additional": False,
}

ENVIRONMENT_RANGE: Spec = {
    "type": "object",
    "properties": {
        "temperature": QUANTITY_RANGE,
        "relativeHumidity": QUANTITY_RANGE,
        "co2": QUANTITY_RANGE,
    },
    "additional": False,
}

LOCATION: Spec = {
    "type": "object",
    "properties": {
        "name": STRING,
        "latitude": {"type": "number", "minimum": -90, "maximum": 90},
        "longitude": {"type": "number", "minimum": -180, "maximum": 180},
        "gln": {"type": "string", "pattern": re.compile(r"^[0-9]{13}$")},
    },
    "additional": False,
}

CIRCULAR_ECONOMY: Spec = {
    "type": "object",
    "properties": {
        "wasteSource": {
            "type": "object",
            "properties": {
                "type": {
                    "enum": ("BREWERY", "RESTAURANT", "FARM", "COFFEE_SHOP", "OTHER")
                },
                "partnerId": STRING,
                "collectionDate": {"type": "string", "format": "date"},
                "composition": {"type": "array", "items": STRING},
            },
            "additional": False,
        },
        "sustainability": {
            "type": "object",
            "properties": {
                "carbonOffset": QUANTITY,
                "wasteUtilized": QUANTITY,
                "localSourcing": {"type": "boolean"},
            },
            "additional": False,
        },
    },
    "additional": False,
}

# Members a SpecimenRecord adds to a label (the label itself is checked by
# validate_specimen).
SPECIMEN_RECORD_MEMBERS: Mapping[str, Spec] = {
    "strainRef": STRING,
    "recipeRef": STRING,
    "inoculatedAt": DATE_TIME,
    "inoculum": QUANTITY,
    "substrateWetWeight": QUANTITY,
    "substrateDryWeight": QUANTITY,
    "location": LOCATION,
    "circularEconomy": CIRCULAR_ECONOMY,
}

STRAIN_RECORD: Spec = {
    "type": "object",
    "required": ("id", "name", "taxon"),
    "properties": {
        "id": NON_EMPTY,
        "name": NON_EMPTY,
        "aliases": {"type": "array", "items": STRING},
        "taxon": TAXON,
        "accession": STRING,
        "origin": STRING,
        "isolatedAt": {"type": "string", "format": "date"},
        "isolationSource": STRING,
        "growthParameters": {
            "type": "object",
            "properties": {
                "colonization": ENVIRONMENT_RANGE,
                "fruiting": ENVIRONMENT_RANGE,
                "incubationDays": RANGE,
                "fruitingDays": RANGE,
            },
            "additional": False,
        },
    },
    "additional": False,
}

RECIPE: Spec = {
    "type": "object",
    "required": ("id", "name", "kind", "ingredients"),
    "properties": {
        "id": NON_EMPTY,
        "name": NON_EMPTY,
        "kind": {
            "enum": ("AGAR", "LIQUID_CULTURE", "GRAIN", "SUBSTRATE", "CASING", "OTHER")
        },
        "ingredients": {
            "type": "array",
            "min_items": 1,
            "items": {
                "type": "object",
                "required": ("name", "amount"),
                "properties": {
                    "name": NON_EMPTY,
                    "amount": QUANTITY,
                    "role": {
                        "enum": (
                            "BASE",
                            "SUPPLEMENT",
                            "WATER",
                            "ADDITIVE",
                            "GELLING_AGENT",
                            "NUTRIENT",
                        )
                    },
                    "supplier": STRING,
                    "foodonId": STRING,
                },
                "additional": False,
            },
        },
        "yields": QUANTITY,
        "hydration": QUANTITY,
        "treatment": {
            "type": "object",
            "required": ("method",),
            "properties": {
                "method": {
                    "enum": (
                        "AUTOCLAVE",
                        "PRESSURE_COOKER",
                        "PASTEURIZATION",
                        "LIME",
                        "COLD_WATER",
                        "NONE",
                        "OTHER",
                    )
                },
                "temperature": QUANTITY,
                "duration": QUANTITY,
                "pressure": QUANTITY,
            },
            "additional": False,
        },
        "instructions": STRING,
    },
    "additional": False,
}

ENVIRONMENT: Spec = {
    "type": "object",
    "properties": {
        "temperature": QUANTITY,
        "relativeHumidity": QUANTITY,
        "co2": QUANTITY,
        "light": {
            "type": "object",
            "properties": {
                "intensity": QUANTITY,
                "photoperiod": QUANTITY,
                "spectrum": {"type": "array", "items": STRING},
            },
            "additional": False,
        },
        "freshAirExchangesPerHour": {"type": "number", "minimum": 0},
    },
    "additional": False,
}

OBSERVATION: Spec = {
    "type": "object",
    "required": ("id", "specimen", "observedAt", "kind"),
    "properties": {
        "id": NON_EMPTY,
        "specimen": SPECIMEN_ID,
        "observedAt": DATE_TIME,
        "recordedAt": DATE_TIME,
        "kind": {
            "enum": (
                "NOTE",
                "MEASUREMENT",
                "ENVIRONMENT",
                "STAGE_CHANGE",
                "CONDITION_CHANGE",
                "CONTAMINATION",
                "INSPECTION",
                "PHOTO",
            )
        },
        "stage": GROWTH_STAGE,
        "condition": CONDITION,
        "measurements": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ("name", "value"),
                "properties": {
                    "name": {
                        "type": "string",
                        "pattern": re.compile(
                            r"^([a-z][A-Za-z0-9]*|[a-z0-9_]+:[A-Za-z0-9_]+)$"
                        ),
                    },
                    "value": {"type": ("number", "string", "boolean")},
                    "unit": STRING,
                    "method": STRING,
                },
                "additional": False,
            },
        },
        "environment": ENVIRONMENT,
        "contamination": {
            "type": "object",
            "properties": {
                "agent": {
                    "enum": (
                        "TRICHODERMA",
                        "BACTERIA",
                        "COBWEB",
                        "PENICILLIUM",
                        "ASPERGILLUS",
                        "RHIZOPUS",
                        "LIPSTICK",
                        "YEAST",
                        "UNKNOWN",
                        "OTHER",
                    )
                },
                "suspectedTaxon": TAXON,
                "severity": {"enum": ("SUSPECTED", "LOCALIZED", "SPREADING", "TOTAL")},
                "action": {"enum": ("MONITOR", "ISOLATE", "DISCARD", "TREAT")},
            },
            "additional": False,
        },
        "outcome": {
            "enum": (
                "SUCCESS",
                "PARTIAL_SUCCESS",
                "CONTAMINATION",
                "FAILURE",
                "INCONCLUSIVE",
            )
        },
        "note": STRING,
        "media": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ("url",),
                "properties": {"url": STRING, "mediaType": STRING, "license": STRING},
                "additional": False,
            },
        },
        "location": LOCATION,
        "source": {
            "type": "object",
            "properties": {
                "kind": {"enum": ("MANUAL", "SENSOR", "IMPORT", "AI_ASSISTED")},
                "device": STRING,
                "software": STRING,
            },
            "additional": False,
        },
    },
    "additional": False,
}

HARVEST: Spec = {
    "type": "object",
    "required": ("id", "specimen", "harvestedAt", "freshWeight"),
    "properties": {
        "id": NON_EMPTY,
        "specimen": SPECIMEN_ID,
        "harvestedAt": DATE_TIME,
        "flush": {"type": "integer", "minimum": 1},
        "freshWeight": QUANTITY,
        "dryWeight": QUANTITY,
        "grade": {"enum": ("A", "B", "C", "REJECT", "UNGRADED")},
        "lot": STRING,
        "output": SPECIMEN_ID,
        "note": STRING,
    },
    "additional": False,
}

# The bundle header. ``specimens`` is checked record by record.
BUNDLE_HEADER: Spec = {
    "type": "object",
    "required": ("@context", "@type", "version", "specimens"),
    "properties": {
        "@context": {"const": "https://wemush.com/wols/v1"},
        "@type": {"const": "Bundle"},
        "version": {"type": "string", "pattern": VERSION_RE},
        "generated": DATE_TIME,
        "publisher": {
            "type": "object",
            "required": ("name",),
            "properties": {"name": STRING, "organization": STRING, "contact": STRING},
            "additional": False,
        },
        "license": STRING,
        "specimens": {"type": "array"},
        "strains": {"type": "array", "items": STRAIN_RECORD},
        "recipes": {"type": "array", "items": RECIPE},
        "observations": {"type": "array", "items": OBSERVATION},
        "harvests": {"type": "array", "items": HARVEST},
    },
    "additional": False,
}
