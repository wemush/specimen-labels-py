"""Tests for WOLS v1.3.0 behavior beyond the conformance vectors."""

from __future__ import annotations

import json
import warnings

import pytest
from typer.testing import CliRunner

from wols import (
    GrowthStage,
    IdValidationMode,
    Specimen,
    SpecimenType,
    Strain,
    WolsParseError,
    WolsValidationError,
    WolsWarning,
    create_specimen,
    parse_compact_url,
    parse_specimen,
    register_type_alias,
    to_json,
    validate_specimen,
)
from wols.cli.app import app

BASE = {
    "@context": "https://wemush.com/wols/v1",
    "@type": "Specimen",
    "id": "wemush:clx1a2b3c4",
    "version": "1.3.0",
    "type": "SUBSTRATE",
    "species": "Pleurotus ostreatus",
}


def _create_quietly(**kwargs: object) -> tuple[Specimen, list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        specimen = create_specimen(**kwargs)  # type: ignore[arg-type]
    messages = [str(w.message) for w in caught if issubclass(w.category, WolsWarning)]
    return specimen, messages


class TestTypeAliases:
    """create_specimen resolves the spec alias table case-insensitively."""

    @pytest.mark.parametrize(
        ("alias", "expected"),
        [
            *[
                (a, SpecimenType.CULTURE)
                for a in (
                    "LIQUID_CULTURE",
                    "LC",
                    "AGAR",
                    "PETRI",
                    "SLANT",
                    "CULTURE_PLATE",
                )
            ],
            *[
                (a, SpecimenType.SPAWN)
                for a in ("GRAIN_SPAWN", "SAWDUST_SPAWN", "PLUG_SPAWN", "DOWEL")
            ],
            *[
                (a, SpecimenType.SUBSTRATE)
                for a in ("BLOCK", "BAG", "BED", "LOG", "BUCKET")
            ],
            *[
                (a, SpecimenType.FRUITING)
                for a in ("FLUSH", "PINNING", "FRUIT", "FIRST_FLUSH")
            ],
            *[
                (a, SpecimenType.HARVEST)
                for a in ("FRESH", "DRIED", "PROCESSED", "EXTRACT")
            ],
        ],
    )
    def test_alias_table(self, alias: str, expected: SpecimenType) -> None:
        for spelling in (alias, alias.lower(), f"  {alias.title()} "):
            specimen, messages = _create_quietly(type=spelling, species="Test")
            assert specimen.type == expected
            assert specimen.stage is None
            assert messages == []

    def test_canonical_lowercase(self) -> None:
        specimen, _ = _create_quietly(type="culture", species="Test")
        assert specimen.type == SpecimenType.CULTURE

    def test_unknown_type_rejected(self) -> None:
        with pytest.raises(WolsValidationError):
            create_specimen(type="NOT_A_TYPE", species="Test")

    def test_input_type_still_accepted(self) -> None:
        specimen = create_specimen(input_type="LC", species="Test")
        assert specimen.type == SpecimenType.CULTURE

    def test_type_and_input_type_conflict(self) -> None:
        with pytest.raises(TypeError, match="not both"):
            create_specimen(
                type=SpecimenType.CULTURE, input_type=SpecimenType.SPAWN, species="T"
            )

    def test_type_required(self) -> None:
        with pytest.raises(TypeError, match="type"):
            create_specimen(species="Test")

    @pytest.mark.parametrize("alias", ["PRIMORDIA", "primordia", " Primordia "])
    def test_primordia_alias_is_reserved(self, alias: str) -> None:
        with pytest.raises(ValueError, match="reserved"):
            register_type_alias(alias, SpecimenType.SUBSTRATE)

    def test_canonical_type_cannot_be_alias(self) -> None:
        with pytest.raises(ValueError, match="canonical"):
            register_type_alias("spawn", SpecimenType.CULTURE)


class TestPrimordiaAsType:
    """PRIMORDIA supplied as a type (spec note, v1.3.0)."""

    def test_sets_stage_and_warns(self) -> None:
        specimen, messages = _create_quietly(type="PRIMORDIA", species="Test")
        assert specimen.type == SpecimenType.FRUITING
        assert specimen.stage == GrowthStage.PRIMORDIA
        assert len(messages) == 1
        assert 'type="FRUITING", stage="PRIMORDIA"' in messages[0]

    @pytest.mark.parametrize("stage", [GrowthStage.FRUITING, "senescence"])
    def test_supplied_stage_not_overridden(self, stage: GrowthStage | str) -> None:
        specimen, messages = _create_quietly(
            type="Primordia", species="Test", stage=stage
        )
        assert specimen.type == SpecimenType.FRUITING
        assert specimen.stage != GrowthStage.PRIMORDIA
        assert len(messages) == 1

    def test_never_serialized_as_type(self) -> None:
        specimen, _ = _create_quietly(type="PRIMORDIA", species="Test")
        data = json.loads(to_json(specimen))
        assert data["type"] == "FRUITING"
        assert data["stage"] == "PRIMORDIA"

    def test_warning_can_be_made_an_error(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", WolsWarning)
            with pytest.raises(WolsWarning):
                create_specimen(type="PRIMORDIA", species="Test")

    def test_parse_rejects_primordia_type(self) -> None:
        with pytest.raises(WolsParseError):
            parse_specimen(json.dumps({**BASE, "type": "PRIMORDIA"}))


class TestTransferDepth:
    """strain.transferDepth (v1.3.0)."""

    def test_serialized_as_transfer_depth(self) -> None:
        strain = Strain(
            name="Blue", generation="F1", clonal_generation=3, transfer_depth=5
        )
        assert strain.to_dict() == {
            "name": "Blue",
            "generation": "F1",
            "clonalGeneration": 3,
            "transferDepth": 5,
        }

    def test_roundtrip_through_json(self) -> None:
        specimen = create_specimen(
            type="SPAWN",
            species="Pleurotus ostreatus",
            strain=Strain(
                name="Blue", generation="F1", clonal_generation=3, transfer_depth=5
            ),
        )
        parsed = parse_specimen(to_json(specimen))
        assert parsed == specimen
        assert parsed.strain is not None
        assert parsed.strain.transfer_depth == 5
        assert json.loads(to_json(parsed))["strain"]["transferDepth"] == 5

    def test_zero_roundtrips(self) -> None:
        data = {**BASE, "strain": {"name": "Blue", "transferDepth": 0}}
        parsed = parse_specimen(json.dumps(data))
        assert parsed.strain is not None
        assert parsed.strain.transfer_depth == 0
        assert json.loads(to_json(parsed))["strain"]["transferDepth"] == 0

    def test_omitted_when_none(self) -> None:
        assert "transferDepth" not in Strain(name="Blue").to_dict()

    @pytest.mark.parametrize("value", [-1, 1.5, "3", True])
    def test_strain_rejects_invalid(self, value: object) -> None:
        with pytest.raises(ValueError, match="transferDepth"):
            Strain(name="Blue", transfer_depth=value)  # type: ignore[arg-type]

    @pytest.mark.parametrize("value", [-1, 1.5, "3", True])
    def test_parse_rejects_invalid(self, value: object) -> None:
        data = {**BASE, "strain": {"name": "Blue", "transferDepth": value}}
        with pytest.raises(WolsParseError):
            parse_specimen(json.dumps(data))

    def test_validate_rejects_bool(self) -> None:
        data = {**BASE, "strain": {"name": "Blue", "transferDepth": True}}
        result = validate_specimen(data)
        assert not result.valid
        assert [e.path for e in result.errors] == ["strain.transferDepth"]

    def test_validate_warns_below_clonal_generation(self) -> None:
        data = {
            **BASE,
            "strain": {"name": "Blue", "clonalGeneration": 3, "transferDepth": 1},
        }
        result = validate_specimen(data)
        assert result.valid
        assert any(
            w.path == "strain.transferDepth" and w.code == "INCONSISTENT_VALUE"
            for w in result.warnings
        )

    def test_validate_no_warning_when_consistent(self) -> None:
        data = {
            **BASE,
            "strain": {"name": "Blue", "clonalGeneration": 3, "transferDepth": 3},
        }
        assert validate_specimen(data).warnings == []

    def test_create_warns_below_clonal_generation(self) -> None:
        _, messages = _create_quietly(
            type="SPAWN",
            species="Test",
            strain=Strain(name="Blue", clonal_generation=3, transfer_depth=1),
        )
        assert len(messages) == 1
        assert "transferDepth" in messages[0]


class TestValidateSpecimen130:
    """validate_specimen changes in v1.3.0."""

    def test_spec_example_short_id_valid(self) -> None:
        assert validate_specimen(BASE).valid

    def test_id_mode_opt_in(self) -> None:
        result = validate_specimen(BASE, id_mode=IdValidationMode.CUID)
        assert not result.valid
        assert [e.path for e in result.errors] == ["id"]

    @pytest.mark.parametrize("field", ["@context", "@type"])
    def test_wrong_json_ld_value_is_error(self, field: str) -> None:
        result = validate_specimen({**BASE, field: "https://example.com"})
        assert not result.valid
        assert [e.path for e in result.errors] == [field]

    @pytest.mark.parametrize("field", ["@context", "@type"])
    def test_missing_json_ld_value_is_warning(self, field: str) -> None:
        data = {k: v for k, v in BASE.items() if k != field}
        result = validate_specimen(data)
        assert result.valid
        assert [w.path for w in result.warnings] == [field]

    def test_unknown_field_warning_recommends_custom(self) -> None:
        result = validate_specimen({**BASE, "metadata": {}})
        assert result.valid
        assert "custom" in result.warnings[0].message

    @pytest.mark.parametrize("generation", ["P", "P1", "F1", "f2", "G2", "3", 0, 2])
    def test_generation_notations(self, generation: object) -> None:
        data = {**BASE, "strain": {"name": "Blue", "generation": generation}}
        assert validate_specimen(data).valid

    @pytest.mark.parametrize("generation", [-1, True, [1]])
    def test_generation_invalid(self, generation: object) -> None:
        data = {**BASE, "strain": {"name": "Blue", "generation": generation}}
        result = validate_specimen(data)
        assert [e.path for e in result.errors] == ["strain.generation"]

    def test_clonal_generation_bool_rejected(self) -> None:
        data = {**BASE, "strain": {"name": "Blue", "clonalGeneration": False}}
        assert not validate_specimen(data).valid

    def test_encrypted_field_objects_accepted(self) -> None:
        enc = {
            "encrypted": True,
            "algorithm": "AES-256-GCM",
            "payload": "x",
            "iv": "y",
            "kdf": "raw",
        }
        data = {**BASE, "strain": enc, "stage": enc, "batch": enc, "custom": enc}
        assert validate_specimen(data).valid

    def test_signature_cannot_be_encrypted_object(self) -> None:
        data = {**BASE, "signature": {"encrypted": True}}
        assert not validate_specimen(data).valid


class TestCompactUrlDecoding:
    """Decoders accept both custom schemes (output is unchanged)."""

    @pytest.mark.parametrize("scheme", ["wemush", "web+wemush", "WEMUSH", "Web+Wemush"])
    def test_schemes_accepted(self, scheme: str) -> None:
        ref = parse_compact_url(f"{scheme}://v1/clx1a2b3c4?s=POSTR&st=COL")
        assert ref.id == "clx1a2b3c4"
        assert ref.species_code == "POSTR"
        assert ref.stage == GrowthStage.COLONIZATION

    def test_spec_example(self) -> None:
        ref = parse_compact_url(
            "wemush://v1/clx1a2b3c4?s=POSTR&st=COLONIZATION&t=1734307200"
        )
        assert ref.id == "clx1a2b3c4"
        assert ref.params["t"] == "1734307200"

    def test_encrypted_url_rejected(self) -> None:
        with pytest.raises(WolsParseError) as exc_info:
            parse_compact_url("wemush://v1/encrypted/clx1a2b3c4?e=x&iv=y&kdf=raw")
        assert exc_info.value.code == "ENCRYPTED_URL"


class TestCliCreate130:
    """The CLI accepts aliases and reports the PRIMORDIA warning."""

    runner = CliRunner()

    def test_alias(self) -> None:
        result = self.runner.invoke(
            app, ["create", "--species", "Test", "--type", "lc", "--json"]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["type"] == "CULTURE"

    def test_primordia_warns(self) -> None:
        result = self.runner.invoke(
            app, ["create", "--species", "Test", "--type", "PRIMORDIA", "--json"]
        )
        assert result.exit_code == 0, result.output
        assert "Warning" in result.stderr
        data = json.loads(result.stdout)
        assert data["type"] == "FRUITING"
        assert data["stage"] == "PRIMORDIA"
