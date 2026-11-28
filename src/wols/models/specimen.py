"""WOLS specimen data models.

Contains Specimen, Strain, SpecimenRef dataclasses and SpecimenMeta TypedDict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypedDict

from wols.constants import WOLS_CONTEXT, WOLS_VERSION
from wols.generation import is_integer_generation, warn_numeric_generation
from wols.models.enums import GrowthStage, SpecimenType


class SpecimenMeta(TypedDict, total=False):
    """Metadata for specimen round-trip preservation (v1.2.0).

    The _meta namespace is reserved for implementation-specific metadata
    that should be preserved through import/export operations.

    Attributes:
        source_id: Original ID from source system.
        imported_at: ISO 8601 timestamp of import.
        source_system: Name of the source system.
        schema_version: Schema version of source data.
    """

    source_id: str
    imported_at: str
    source_system: str
    schema_version: str


# Top-level members of a WOLS specimen this library knows. Anything else is an
# unknown member: valid (with a warning) and kept on re-serialization.
SPECIMEN_FIELDS: frozenset[str] = frozenset(
    {
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
)

# WOLS 1.5 draft: _meta keys are camelCase on the wire. SpecimenMeta keeps its
# snake_case keys in Python; to_dict() writes camelCase and from_dict() reads
# either form. Keys not listed here pass through unchanged.
_META_WIRE_KEYS: dict[str, str] = {
    "source_id": "sourceId",
    "imported_at": "importedAt",
    "source_system": "sourceSystem",
    "schema_version": "schemaVersion",
}
_META_PYTHON_KEYS: dict[str, str] = {v: k for k, v in _META_WIRE_KEYS.items()}


def meta_to_wire(meta: SpecimenMeta | dict[str, Any]) -> dict[str, Any]:
    """Return ``_meta`` with its standard keys in camelCase (WOLS 1.5 draft).

    When a mapping holds both forms of a key, the camelCase value wins.
    """
    source: dict[str, Any] = dict(meta)
    result: dict[str, Any] = {}
    for key, value in source.items():
        wire_key = _META_WIRE_KEYS.get(key)
        if wire_key is None:
            result[key] = value
        elif wire_key not in source:
            result[wire_key] = value
    return result


def meta_from_wire(meta: dict[str, Any]) -> SpecimenMeta:
    """Return ``_meta`` with its standard keys in snake_case.

    Accepts camelCase (the 1.5 wire form) and snake_case (what 1.4.0 and
    earlier releases of this library wrote). When both forms of a key are
    present, the camelCase value wins.
    """
    result: dict[str, Any] = {}
    for key, value in meta.items():
        python_key = _META_PYTHON_KEYS.get(key)
        if python_key is not None:
            result[python_key] = value
        elif key in _META_WIRE_KEYS:
            if _META_WIRE_KEYS[key] not in meta:
                result[key] = value
        else:
            result[key] = value
    return result  # type: ignore[return-value]


def is_non_negative_int(value: object) -> bool:
    """Return True if value is a non-negative int (bool is rejected)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_encrypted_field(value: object) -> bool:
    """Return True for a field-level encryption object (WOLS v1.3.0).

    The single predicate shared by validation and decryption, so the two
    cannot disagree about which fields are encrypted.
    """
    return isinstance(value, dict) and value.get("encrypted") is True


def transfer_depth_below_clonal(
    clonal_generation: object, transfer_depth: object
) -> bool:
    """Return True when both counters are valid and transferDepth < clonal.

    WOLS v1.3.0 says transferDepth SHOULD be at least clonalGeneration, since
    every subculture is also a transfer. A violation is a warning, not an
    error.
    """
    return (
        is_non_negative_int(clonal_generation)
        and is_non_negative_int(transfer_depth)
        and transfer_depth < clonal_generation  # type: ignore[operator]
    )


@dataclass(frozen=True)
class Strain:
    """Strain/lineage information.

    The three counters are independent (WOLS v1.3.0) and must not stand in
    for one another.

    Attributes:
        name: Strain name (e.g., "Blue Oyster").
        generation: Filial (sexual) generation, e.g. "F1", "P", "G2", or
            "3". It does not change when the same genetics is transferred.
            Always a string once constructed: a non-negative ``int`` (which
            wols 1.3.0 accepted and wrote) is converted to its decimal string
            with a :class:`~wols.exceptions.WolsWarning` (WOLS 1.4.0).
        clonal_generation: Culture-to-culture subculture count. The original
            culture is 0. Expansion to grain or substrate does not increment it.
        transfer_depth: Total transfers of any kind from the original culture
            (v1.3.0). The original culture is 0. Serialized as
            ``transferDepth``.
        lineage: Parent specimen ID reference.
        source: Origin (spore, tissue, agar, liquid).

    Raises:
        ValueError: If ``clonal_generation`` or ``transfer_depth`` is not a
            non-negative integer, or ``generation`` is not a string or a
            non-negative integer.
    """

    name: str
    generation: str | int | None = None
    clonal_generation: int | None = None
    lineage: str | None = None
    source: str | None = None
    transfer_depth: int | None = None

    def __post_init__(self) -> None:
        for wire_name, value in (
            ("clonalGeneration", self.clonal_generation),
            ("transferDepth", self.transfer_depth),
        ):
            if value is not None and not is_non_negative_int(value):
                raise ValueError(
                    f"strain.{wire_name} must be a non-negative integer, got {value!r}"
                )
        if self.generation is not None and not (
            isinstance(self.generation, str) or is_non_negative_int(self.generation)
        ):
            raise ValueError(
                "strain.generation must be a string or a non-negative integer, "
                f"got {self.generation!r}"
            )
        if is_integer_generation(self.generation):
            # WOLS 1.4.0: generators MUST write a string; read an int as its
            # decimal string. Frozen dataclass, so set it directly.
            warn_numeric_generation(self.generation, stacklevel=3)
            object.__setattr__(self, "generation", str(self.generation))

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        result: dict[str, Any] = {"name": self.name}
        if self.generation is not None:
            result["generation"] = self.generation
        if self.clonal_generation is not None:
            result["clonalGeneration"] = self.clonal_generation
        if self.transfer_depth is not None:
            result["transferDepth"] = self.transfer_depth
        if self.lineage is not None:
            result["lineage"] = self.lineage
        if self.source is not None:
            result["source"] = self.source
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Strain:
        """Create from dictionary.

        Raises:
            ValueError: If the data is not an object or a field is invalid.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"strain must be a string or an object, got {type(data).__name__}"
            )
        if not isinstance(data.get("name"), str):
            raise ValueError("strain.name must be a string")
        return cls(
            name=data["name"],
            generation=data.get("generation"),
            clonal_generation=data.get("clonalGeneration"),
            lineage=data.get("lineage"),
            source=data.get("source"),
            transfer_depth=data.get("transferDepth"),
        )


@dataclass(frozen=True)
class Specimen:
    """WOLS specimen entity.

    Attributes:
        id: Unique identifier: ``wemush:`` followed by any non-empty suffix.
        version: WOLS spec version (currently "1.4.0").
        type: Specimen type.
        species: Scientific species name.
        strain: Optional genetic info.
        stage: Optional growth stage.
        created: ISO 8601 timestamp.
        batch: Batch identifier.
        organization: Organization name.
        creator: Creator identifier.
        custom: Namespace for custom fields.
        signature: Digital signature.
        _meta: Reserved namespace for round-trip metadata (v1.2.0).
        unknown_members: Top-level members this library doesn't know, kept as
            received so a parse and re-serialize round trip doesn't drop them
            (WOLS 1.5 draft). ``to_dict()`` writes them back at the top level
            after the known fields, and never over a known field. Put your own
            vendor data in ``custom`` instead.
    """

    id: str
    version: str
    type: SpecimenType
    species: str
    strain: Strain | None = None
    stage: GrowthStage | None = None
    created: datetime | None = None
    batch: str | None = None
    organization: str | None = None
    creator: str | None = None
    custom: dict[str, Any] | None = None
    signature: str | None = None
    _meta: SpecimenMeta | None = None  # v1.2.0
    unknown_members: dict[str, Any] | None = None  # WOLS 1.5 draft

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary with JSON-LD context."""
        result: dict[str, Any] = {
            "@context": WOLS_CONTEXT,
            "@type": "Specimen",
            "id": self.id,
            "version": self.version,
            "type": self.type.value,
            "species": self.species,
        }

        if self.strain is not None and not isinstance(self.strain, dict):
            result["strain"] = self.strain.to_dict()
        if self.stage is not None:
            result["stage"] = self.stage.value
        if self.created is not None:
            result["created"] = self.created.isoformat()
        if self.batch is not None:
            result["batch"] = self.batch
        if self.organization is not None:
            result["organization"] = self.organization
        if self.creator is not None:
            result["creator"] = self.creator
        if self.custom is not None:
            result["custom"] = self.custom
        if self.signature is not None:
            result["signature"] = self.signature
        if self._meta is not None:
            result["_meta"] = meta_to_wire(self._meta)
        if self.unknown_members is not None:
            for key, value in self.unknown_members.items():
                if key not in SPECIMEN_FIELDS:
                    result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Specimen:
        """Create from dictionary."""
        strain_data = data.get("strain")
        strain: Strain | None = None
        if strain_data is not None:
            if isinstance(strain_data, str):
                strain = Strain(name=strain_data)
            else:
                strain = Strain.from_dict(strain_data)

        stage_value = data.get("stage")
        stage: GrowthStage | None = None
        if stage_value is not None:
            stage = GrowthStage(stage_value)

        created_value = data.get("created")
        created: datetime | None = None
        if created_value is not None:
            if isinstance(created_value, datetime):
                created = created_value
            elif isinstance(created_value, str):
                created = datetime.fromisoformat(created_value.replace("Z", "+00:00"))
            else:
                raise ValueError(
                    "created must be an ISO 8601 string, "
                    f"got {type(created_value).__name__}"
                )

        # Parse _meta field (v1.2.0). Arbitrary keys are kept; the standard
        # keys are read in camelCase or snake_case (WOLS 1.5 draft).
        meta_value = data.get("_meta")
        meta: SpecimenMeta | None = None
        if meta_value is not None and isinstance(meta_value, dict):
            meta = meta_from_wire(meta_value)

        # WOLS 1.5 draft: keep unknown top-level members for re-serialization.
        unknown = {k: v for k, v in data.items() if k not in SPECIMEN_FIELDS}

        return cls(
            id=data["id"],
            version=data.get("version", WOLS_VERSION),
            type=SpecimenType(data["type"]),
            species=data["species"],
            strain=strain,
            stage=stage,
            created=created,
            batch=data.get("batch"),
            organization=data.get("organization"),
            creator=data.get("creator"),
            custom=data.get("custom"),
            signature=data.get("signature"),
            _meta=meta,
            unknown_members=unknown or None,
        )


@dataclass(frozen=True)
class SpecimenRef:
    """Lightweight reference from compact URL.

    Attributes:
        id: Specimen ID (without wemush: prefix).
        species_code: The ``s`` value as written in the URL (e.g., "POSTR").
        stage: Stage from URL.
        params: All URL query parameters.
        species: Scientific name that ``s`` resolves to under the WOLS 1.5
            Species Code Registry (registered code, legacy code, or the
            name as written).
    """

    id: str
    species_code: str | None = None
    stage: GrowthStage | None = None
    params: dict[str, str] = field(default_factory=dict)
    species: str | None = None
