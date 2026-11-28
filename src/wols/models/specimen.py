"""WOLS specimen data models.

Contains Specimen, Strain, SpecimenRef dataclasses and SpecimenMeta TypedDict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypedDict

from wols.constants import ID_PREFIX, WOLS_CONTEXT, WOLS_VERSION
from wols.generation import is_integer_generation, warn_numeric_generation
from wols.models.enums import Condition, GrowthStage, SpecimenType


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
        # WOLS 1.5.0-rc.1
        "taxon",
        "form",
        "derivedFrom",
        "condition",
        "container",
        "lot",
    }
)

# The members WOLS 1.5 added. Earlier releases of this library kept them in
# ``Specimen.unknown_members``; to_dict() still writes them from there when
# the typed field is unset.
V15_FIELDS: frozenset[str] = frozenset(
    {"taxon", "form", "derivedFrom", "condition", "container", "lot"}
)

# Members of ``strain`` this library knows. Others are kept as received.
STRAIN_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "generation",
        "clonalGeneration",
        "transferDepth",
        "lineage",
        "source",
        "accession",  # WOLS 1.5.0-rc.1
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


def shadowed_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Return the snake_case ``_meta`` members that have a camelCase twin.

    When a label has both spellings of a key, the camelCase value is used and
    the snake_case member is kept unchanged (WOLS 1.5.0-rc.2), so neither
    value is lost.
    """
    return {
        key: value
        for key, value in meta.items()
        if key in _META_WIRE_KEYS and _META_WIRE_KEYS[key] in meta
    }


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
        name: Strain name (e.g., "Blue Oyster"). Optional from WOLS 1.5, so
            a generation can be recorded for a strain that has no name.
        generation: Filial (sexual) generation, e.g. "F1", "P", "G2", or
            "3". It does not change when the same genetics is transferred.
            Always a string once constructed: a non-negative ``int`` (which
            wols 1.3.0 accepted and wrote) is converted to its decimal string
            with a :class:`~wols.exceptions.WolsWarning` (WOLS 1.4.0).
        clonal_generation: Culture-to-culture subculture count. The original
            culture is 0. Expansion to grain or substrate does not increment it.
        lineage: Parent specimen ID reference. When the label also has
            ``derived_from``, it must equal the first parent's ``id``.
        source: Origin (spore, tissue, agar, liquid).
        transfer_depth: Total transfers of any kind from the original culture
            (v1.3.0). The original culture is 0. Serialized as
            ``transferDepth``.
        accession: Culture-collection or vendor accession (WOLS 1.5).
        unknown_members: Members of ``strain`` this library doesn't know,
            kept as received and written back by ``to_dict()`` (WOLS 1.5).

    Raises:
        ValueError: If ``clonal_generation`` or ``transfer_depth`` is not a
            non-negative integer, or ``generation`` is not a string or a
            non-negative integer.
    """

    name: str | None = None
    generation: str | int | None = None
    clonal_generation: int | None = None
    lineage: str | None = None
    source: str | None = None
    transfer_depth: int | None = None
    accession: str | None = None
    unknown_members: dict[str, Any] | None = None

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
        result: dict[str, Any] = {}
        if self.name is not None:
            result["name"] = self.name
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
        if self.accession is not None:
            result["accession"] = self.accession
        if self.unknown_members is not None:
            for key, value in self.unknown_members.items():
                if key not in STRAIN_FIELDS:
                    result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Strain:
        """Create from dictionary.

        Members this library doesn't know are kept in ``unknown_members``.

        Raises:
            ValueError: If the data is not an object or a field is invalid.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"strain must be a string or an object, got {type(data).__name__}"
            )
        if "name" in data and not isinstance(data["name"], str):
            raise ValueError("strain.name must be a string")
        unknown = {k: v for k, v in data.items() if k not in STRAIN_FIELDS}
        return cls(
            name=data.get("name"),
            generation=data.get("generation"),
            clonal_generation=data.get("clonalGeneration"),
            lineage=data.get("lineage"),
            source=data.get("source"),
            transfer_depth=data.get("transferDepth"),
            accession=_optional(data, "accession", str, "a string"),
            unknown_members=unknown or None,
        )


def _wire_value(value: Any) -> Any:
    """An enum member as its value; anything else unchanged."""
    return value.value if isinstance(value, Enum) else value


def _optional(data: dict[str, Any], key: str, kind: type, label: str) -> Any:
    """``data[key]`` if it has the JSON type ``kind``, else ValueError."""
    value = data.get(key)
    if value is not None and not isinstance(value, kind):
        raise ValueError(f"{key} must be {label}, got {type(value).__name__}")
    return value


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
            (WOLS 1.5). ``to_dict()`` writes them back at the top level
            after the known fields, and never over a known field. Put your own
            vendor data in ``custom`` instead.
        taxon: Name plus identifiers and hybrid parents (WOLS 1.5), as the
            JSON object ``{scientificName, authorship?, rank?, identifiers?,
            hybridOf?}``. Keep ``species`` equal to its ``scientificName``.
        form: The specific form within ``type``, such as ``GRAIN_SPAWN``
            (a :class:`~wols.SpecimenForm` value) or an ``x-`` extension
            (WOLS 1.5).
        derived_from: Every parent specimen, as a list of
            ``{id, relation?, quantity?}`` objects (WOLS 1.5). Serialized as
            ``derivedFrom``. When ``strain.lineage`` is set too, it must
            equal the first parent's ``id``.
        condition: Health or terminal state, separate from ``stage``
            (WOLS 1.5). Absent means ``ACTIVE``.
        container: The vessel, as ``{format, capacity?}`` (WOLS 1.5).
        lot: Traceability lot code for sellable product, distinct from
            ``batch`` (WOLS 1.5).
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
    unknown_members: dict[str, Any] | None = None  # WOLS 1.5
    taxon: dict[str, Any] | None = None  # WOLS 1.5
    form: str | None = None  # WOLS 1.5
    derived_from: list[dict[str, Any]] | None = None  # WOLS 1.5
    condition: Condition | None = None  # WOLS 1.5
    container: dict[str, Any] | None = None  # WOLS 1.5
    lot: str | None = None  # WOLS 1.5
    # The ``created`` text as parsed, written back unchanged so that a round
    # trip keeps its spelling (``Z`` or ``+00:00``). Not copied by replace().
    _created_text: str | None = field(
        default=None, init=False, repr=False, compare=False
    )
    # snake_case ``_meta`` members that a camelCase member of the same key
    # overrode on parse, written back unchanged (WOLS 1.5.0-rc.2). Not copied
    # by replace().
    _meta_shadowed: dict[str, Any] | None = field(
        default=None, init=False, repr=False, compare=False
    )

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

        if self.taxon is not None:
            result["taxon"] = self.taxon
        if self.form is not None:
            result["form"] = _wire_value(self.form)
        if self.strain is not None and not isinstance(self.strain, dict):
            result["strain"] = self.strain.to_dict()
        if self.derived_from is not None:
            result["derivedFrom"] = self.derived_from
        if self.stage is not None:
            result["stage"] = self.stage.value
        if self.condition is not None:
            result["condition"] = _wire_value(self.condition)
        if self.container is not None:
            result["container"] = self.container
        if self.created is not None:
            result["created"] = (
                self._created_text
                if self._created_text is not None
                else self.created.isoformat()
            )
        if self.batch is not None:
            result["batch"] = self.batch
        if self.lot is not None:
            result["lot"] = self.lot
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
            if self._meta_shadowed:
                result["_meta"].update(self._meta_shadowed)
        if self.unknown_members is not None:
            for key, value in self.unknown_members.items():
                if key in result:
                    continue
                if key not in SPECIMEN_FIELDS or key in V15_FIELDS:
                    result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Specimen:
        """Create from dictionary.

        Raises:
            ValueError: If a member has the wrong JSON type or an invalid
                ``type``, ``stage`` or ``condition``.
        """
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

        condition_value = data.get("condition")
        condition = Condition(condition_value) if condition_value is not None else None

        created_value = data.get("created")
        created: datetime | None = None
        created_text: str | None = None
        if created_value is not None:
            if isinstance(created_value, datetime):
                created = created_value
            elif isinstance(created_value, str):
                created = datetime.fromisoformat(created_value.replace("Z", "+00:00"))
                created_text = created_value
            else:
                raise ValueError(
                    "created must be an ISO 8601 string, "
                    f"got {type(created_value).__name__}"
                )

        # Parse _meta field (v1.2.0). Arbitrary keys are kept; the standard
        # keys are read in camelCase or snake_case (WOLS 1.5).
        meta_value = data.get("_meta")
        meta: SpecimenMeta | None = None
        meta_shadowed: dict[str, Any] = {}
        if meta_value is not None and isinstance(meta_value, dict):
            meta = meta_from_wire(meta_value)
            meta_shadowed = shadowed_meta(meta_value)

        # WOLS 1.5: keep unknown top-level members for re-serialization.
        unknown = {k: v for k, v in data.items() if k not in SPECIMEN_FIELDS}

        specimen = cls(
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
            taxon=_optional(data, "taxon", dict, "an object"),
            form=_optional(data, "form", str, "a string"),
            derived_from=_optional(data, "derivedFrom", list, "an array"),
            condition=condition,
            container=_optional(data, "container", dict, "an object"),
            lot=_optional(data, "lot", str, "a string"),
        )
        if created_text is not None:
            object.__setattr__(specimen, "_created_text", created_text)
        if meta_shadowed:
            object.__setattr__(specimen, "_meta_shadowed", meta_shadowed)
        return specimen


@dataclass(frozen=True)
class SpecimenRef:
    """Lightweight reference from a compact URL.

    A compact URL is a reference: its signature, if any, covers only the
    printed parameters, and :func:`~wols.parse_compact_url` never verifies
    it. Use :func:`wols.crypto.verify_specimen` on the URL as scanned.

    Attributes:
        id: Specimen ID suffix, percent-decoded (without the ``wemush:``
            prefix; see :attr:`specimen_id`).
        species_code: The ``s`` value as written in the URL (e.g., "POSTR").
        stage: Stage from ``st`` (a full stage name or a 3-letter code).
        params: Every query parameter, percent-decoded (``+`` as a space).
        species: Scientific name that ``s`` resolves to under the WOLS 1.5
            Species Code Registry (registered code, legacy code, or the
            name as written).
        type: Specimen type from ``ty`` (WOLS 1.5).
        created: Creation time from ``t`` (Unix seconds), in UTC (WOLS 1.5).
        batch: Batch identifier from ``b`` (WOLS 1.5).
        strain: Strain from ``sn`` (name), ``sg`` (generation) and ``td``
            (transfer depth), or None if none of them is present (WOLS 1.5).
        unrecognized_params: Parameters outside the registry, such as
            ``x-acme-room``, percent-decoded. They are kept, never a reason
            to reject the URL (WOLS 1.5).
        signature: The ``sig`` value exactly as it appeared in the URL. Kept
            so a re-emitted URL stays signed; it is never verified here.
    """

    id: str
    species_code: str | None = None
    stage: GrowthStage | None = None
    params: dict[str, str] = field(default_factory=dict)
    species: str | None = None
    type: SpecimenType | None = None
    created: datetime | None = None
    batch: str | None = None
    strain: Strain | None = None
    unrecognized_params: dict[str, str] = field(default_factory=dict)
    signature: str | None = None

    @property
    def specimen_id(self) -> str:
        """The full specimen ID, ``wemush:`` followed by :attr:`id`."""
        return f"{ID_PREFIX}:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        """The label members this reference carries, as JSON.

        ``id`` has the ``wemush:`` prefix, ``species`` is the scientific name
        and ``created`` is an RFC 3339 UTC date-time with no fractional
        seconds (``2024-12-16T00:00:00Z``). Unrecognized parameters and
        ``sig`` aren't label members and aren't included.
        """
        result: dict[str, Any] = {"id": self.specimen_id}
        if self.species is not None:
            result["species"] = self.species
        if self.type is not None:
            result["type"] = self.type.value
        if self.stage is not None:
            result["stage"] = self.stage.value
        if self.created is not None:
            result["created"] = self.created.astimezone(UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        if self.batch is not None:
            result["batch"] = self.batch
        if self.strain is not None:
            result["strain"] = self.strain.to_dict()
        return result
