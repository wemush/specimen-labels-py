"""WOLS 1.5 release candidates: data model, Records Bundle and compact URLs.

The conformance vectors in ``tests/conformance`` cover the specification's
cases; these tests cover the library's own edges.
"""

from __future__ import annotations

import json
import warnings
from datetime import UTC, datetime
from typing import Any

import pytest

from wols import (
    REGISTERED_PARAMETERS,
    Condition,
    ContainerFormat,
    ParentRelation,
    SpecimenForm,
    SpecimenType,
    Strain,
    WolsParseError,
    WolsValidationError,
    WolsWarning,
    create_specimen,
    parse_compact_url,
    parse_specimen,
    to_compact_url,
    to_json,
    unwrap_wols_url,
    validate_bundle,
    validate_specimen,
)
from wols.core._schema import check, is_rfc3339
from wols.core.compact import InvalidEncoding, is_compact_shape, percent_decode
from wols.crypto import (
    SignatureStatus,
    TrustedKey,
    sign_compact_url,
    verify_compact_url,
    verify_encrypted_url,
    verify_specimen,
)
from wols.exceptions import WolsSignatureError
from wols.models.validation import ValidationError

SEED = bytes(range(32))


def _public_key(seed: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    key = Ed25519PrivateKey.from_private_bytes(seed)
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


STORE = {"w1": TrustedKey(public_key=_public_key(SEED), alg="Ed25519")}

LABEL: dict[str, Any] = {
    "@context": "https://wemush.com/wols/v1",
    "@type": "Specimen",
    "id": "wemush:child",
    "version": "1.5.0-rc.2",
    "type": "SUBSTRATE",
    "species": "Pleurotus ostreatus",
}


def _codes(errors: list[ValidationError]) -> dict[str, str]:
    return {e.path: e.code for e in errors}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_values_match_the_schema(self) -> None:
        assert [c.value for c in Condition] == [
            "ACTIVE",
            "CONTAMINATED",
            "EXHAUSTED",
            "DISPOSED",
            "ARCHIVED",
        ]
        assert ParentRelation.SPAWN_TO_BULK.value == "SPAWN_TO_BULK"
        assert SpecimenForm.GRAIN_SPAWN.value == "GRAIN_SPAWN"
        assert ContainerFormat.BAG.value == "BAG"

    def test_registered_parameters(self) -> None:
        assert REGISTERED_PARAMETERS == (
            "s",
            "ty",
            "st",
            "t",
            "b",
            "sn",
            "sg",
            "td",
            "sig",
        )


# ---------------------------------------------------------------------------
# Label validation
# ---------------------------------------------------------------------------


class TestValidateLabel:
    def test_full_1_5_label_is_valid(self) -> None:
        label = {
            **LABEL,
            "taxon": {"scientificName": "Pleurotus ostreatus", "rank": "species"},
            "form": "x-acme-tube",
            "strain": {"generation": "F2", "lineage": "wemush:parent"},
            "derivedFrom": [
                {
                    "id": "wemush:parent",
                    "relation": "SPAWN_TO_BULK",
                    "quantity": {"value": 1, "unit": "kg"},
                }
            ],
            "condition": "ACTIVE",
            "container": {"format": "x-acme-jar"},
            "lot": "L-1",
            "created": "2026-11-10T09:00:00+01:00",
        }
        result = validate_specimen(label)
        assert result.valid, result.errors
        assert result.warnings == []

    def test_lineage_must_equal_first_parent(self) -> None:
        label = {
            **LABEL,
            "strain": {"lineage": "wemush:a"},
            "derivedFrom": [{"id": "wemush:b"}, {"id": "wemush:a"}],
        }
        result = validate_specimen(label)
        assert _codes(result.errors) == {"strain.lineage": "INCONSISTENT_VALUE"}

    def test_lineage_without_derived_from_is_free(self) -> None:
        result = validate_specimen({**LABEL, "strain": {"lineage": "wemush:a"}})
        assert result.valid
        assert result.warnings == []

    @pytest.mark.parametrize("lineage", ["parent-1", 7])
    def test_lineage_not_a_specimen_id_is_a_warning(self, lineage: Any) -> None:
        result = validate_specimen({**LABEL, "strain": {"lineage": lineage}})
        assert result.valid
        assert _codes(result.warnings) == {"strain.lineage": "INVALID_VALUE"}

    def test_strain_accession_and_source_types(self) -> None:
        result = validate_specimen(
            {**LABEL, "strain": {"name": "A", "accession": 5, "source": 5}}
        )
        assert _codes(result.errors) == {"strain.accession": "INVALID_TYPE"}
        assert _codes(result.warnings) == {"strain.source": "INVALID_TYPE"}

    def test_empty_strain_name_is_still_an_error(self) -> None:
        result = validate_specimen({**LABEL, "strain": {"name": " "}})
        assert _codes(result.errors) == {"strain.name": "INVALID_VALUE"}

    def test_missing_version_is_a_warning(self) -> None:
        label = {k: v for k, v in LABEL.items() if k != "version"}
        result = validate_specimen(label)
        assert result.valid
        assert _codes(result.warnings) == {"version": "MISSING_FIELD"}

    @pytest.mark.parametrize("version", ["1.5", "v1.5.0", "1.5.0-", "1.5.0+build"])
    def test_malformed_version_is_an_error(self, version: str) -> None:
        result = validate_specimen({**LABEL, "version": version})
        assert _codes(result.errors) == {"version": "INVALID_VERSION"}

    @pytest.mark.parametrize("created", ["2026-11-10T09:00:00", "2026-11-10", "x"])
    def test_created_without_a_time_zone_is_a_warning(self, created: str) -> None:
        result = validate_specimen({**LABEL, "created": created})
        assert result.valid
        assert _codes(result.warnings) == {"created": "INVALID_VALUE"}

    @pytest.mark.parametrize("field", ["batch", "organization", "creator"])
    def test_empty_string_member_is_a_warning(self, field: str) -> None:
        result = validate_specimen({**LABEL, field: ""})
        assert result.valid
        assert _codes(result.warnings) == {field: "INVALID_VALUE"}

    def test_extra_member_in_a_closed_object(self) -> None:
        result = validate_specimen(
            {**LABEL, "taxon": {"scientificName": "P. ostreatus", "note": "x"}}
        )
        assert _codes(result.errors) == {"taxon.note": "UNKNOWN_FIELD"}

    def test_encrypted_1_5_member_is_not_inspected(self) -> None:
        encrypted = {"encrypted": True, "value": "AAAA", "iv": "AAAA"}
        result = validate_specimen({**LABEL, "lot": encrypted})
        assert result.valid

    def test_specimen_object_validates(self) -> None:
        specimen = parse_specimen(json.dumps({**LABEL, "lot": "L-1"}))
        assert validate_specimen(specimen).valid


class TestSchemaChecker:
    @pytest.mark.parametrize(
        ("value", "valid"),
        [
            ("2026-11-10T09:00:00Z", True),
            ("2026-11-10t09:00:00z", True),
            ("2026-11-10T09:00:00-05:00", True),
            ("2026-11-10T09:00:00", False),
            ("2026-11-10 09:00:00Z", False),
            ("2026-13-10T09:00:00Z", False),
        ],
    )
    def test_rfc3339(self, value: str, valid: bool) -> None:
        assert is_rfc3339(value) is valid

    def test_numbers_and_types(self) -> None:
        errors: list[ValidationError] = []
        spec = {"type": "integer", "minimum": 1, "maximum": 3}
        for value in (2, 2.0):
            check(value, spec, "n", errors)
        assert errors == []
        check(0, spec, "low", errors)
        check(4, spec, "high", errors)
        check(True, spec, "bool", errors)
        check(2.5, spec, "frac", errors)
        assert _codes(errors) == {
            "low": "INVALID_VALUE",
            "high": "INVALID_VALUE",
            "bool": "INVALID_TYPE",
            "frac": "INVALID_TYPE",
        }

    def test_boolean_date_and_union(self) -> None:
        errors: list[ValidationError] = []
        check(True, {"type": "boolean"}, "ok", errors)
        check("2026-11-10", {"type": "string", "format": "date"}, "date", errors)
        check(1, {"type": ("number", "string")}, "union", errors)
        assert errors == []
        check(1, {"type": "boolean"}, "b", errors)
        check("2026-11-10T00:00:00Z", {"format": "date"}, "d1", errors)
        check("2026-02-30", {"format": "date"}, "d2", errors)
        check("x", {"const": "y"}, "c", errors)
        assert _codes(errors) == {
            "b": "INVALID_TYPE",
            "d1": "INVALID_VALUE",
            "d2": "INVALID_VALUE",
            "c": "INVALID_VALUE",
        }


# ---------------------------------------------------------------------------
# Records Bundle
# ---------------------------------------------------------------------------

BUNDLE: dict[str, Any] = {
    "@context": "https://wemush.com/wols/v1",
    "@type": "Bundle",
    "version": "1.5.0-rc.2",
    "specimens": [{**LABEL, "strainRef": "s1", "recipeRef": "r1"}],
    "strains": [
        {"id": "s1", "name": "Blue", "taxon": {"scientificName": "P. ostreatus"}}
    ],
    "recipes": [
        {
            "id": "r1",
            "name": "Masters mix",
            "kind": "SUBSTRATE",
            "ingredients": [{"name": "oak", "amount": {"value": 1, "unit": "kg"}}],
        }
    ],
    "observations": [
        {
            "id": "o1",
            "specimen": "wemush:child",
            "observedAt": "2026-11-10T09:00:00Z",
            "kind": "MEASUREMENT",
            "measurements": [{"name": "pinCount", "value": 3}],
        }
    ],
    "harvests": [
        {
            "id": "h1",
            "specimen": "wemush:child",
            "harvestedAt": "2026-11-20T09:00:00Z",
            "freshWeight": {"value": 1.2, "unit": "kg"},
            "flush": 1,
        }
    ],
}


class TestValidateBundle:
    def test_valid(self) -> None:
        result = validate_bundle(BUNDLE)
        assert result.valid, result.errors
        assert result.warnings == []

    def test_not_an_object(self) -> None:
        result = validate_bundle([])  # type: ignore[arg-type]
        assert not result.valid
        assert _codes(result.errors) == {"": "INVALID_TYPE"}

    def test_unknown_header_member(self) -> None:
        result = validate_bundle({**BUNDLE, "extra": 1})
        assert _codes(result.errors) == {"extra": "UNKNOWN_FIELD"}

    def test_specimen_entry_not_an_object(self) -> None:
        result = validate_bundle({**BUNDLE, "specimens": [5], "observations": []})
        assert "specimens.0" in _codes(result.errors)

    def test_specimen_record_members_are_checked(self) -> None:
        specimen = {**LABEL, "inoculatedAt": "yesterday", "inoculum": {"value": 1}}
        result = validate_bundle({"specimens": [specimen], **_header()})
        assert _codes(result.errors) == {
            "specimens.0.inoculatedAt": "INVALID_VALUE",
            "specimens.0.inoculum.unit": "REQUIRED_FIELD",
        }

    def test_label_warnings_are_prefixed(self) -> None:
        specimen = {**LABEL, "zz": 1}
        result = validate_bundle({"specimens": [specimen], **_header()})
        assert result.valid
        assert _codes(result.warnings) == {"specimens.0.zz": "UNKNOWN_FIELD"}

    def test_strict_makes_unknown_label_members_errors(self) -> None:
        specimen = {**LABEL, "zz": 1}
        result = validate_bundle({"specimens": [specimen], **_header()}, strict=True)
        assert _codes(result.errors) == {"specimens.0.zz": "UNKNOWN_FIELD"}

    def test_unresolved_recipe(self) -> None:
        result = validate_bundle({**BUNDLE, "recipes": []})
        assert _codes(result.errors) == {
            "specimens.0.recipeRef": "UNRESOLVED_REFERENCE"
        }

    def test_unresolved_harvest(self) -> None:
        harvest = {**BUNDLE["harvests"][0], "specimen": "wemush:other"}
        result = validate_bundle({**BUNDLE, "harvests": [harvest]})
        assert _codes(result.errors) == {"harvests.0.specimen": "UNRESOLVED_REFERENCE"}

    def test_derived_from_may_point_outside_the_bundle(self) -> None:
        specimen = {**LABEL, "derivedFrom": [{"id": "wemush:elsewhere"}]}
        assert validate_bundle({"specimens": [specimen], **_header()}).valid

    def test_malformed_records_do_not_crash_reference_checks(self) -> None:
        bundle = {**BUNDLE, "strains": "x", "observations": [5], "harvests": {}}
        result = validate_bundle(bundle)
        assert not result.valid
        assert "specimens.0.strainRef" in _codes(result.errors)


def _header() -> dict[str, Any]:
    return {k: BUNDLE[k] for k in ("@context", "@type", "version")}


# ---------------------------------------------------------------------------
# Model round trip and create_specimen
# ---------------------------------------------------------------------------


class TestModel:
    def test_parse_reads_1_5_members(self) -> None:
        label = {
            **LABEL,
            "condition": "ARCHIVED",
            "form": "GRAIN_SPAWN",
            "container": {"format": "JAR"},
            "strain": {"generation": "F1", "accession": "CC-1", "x-grade": "A"},
        }
        specimen = parse_specimen(json.dumps(label))
        assert specimen.condition is Condition.ARCHIVED
        assert specimen.form == "GRAIN_SPAWN"
        assert specimen.container == {"format": "JAR"}
        assert specimen.strain is not None
        assert specimen.strain.name is None
        assert specimen.strain.accession == "CC-1"
        assert specimen.strain.unknown_members == {"x-grade": "A"}
        assert json.loads(to_json(specimen)) == label

    @pytest.mark.parametrize(
        "extra",
        [
            {"condition": "WILTING"},
            {"taxon": "Pleurotus"},
            {"derivedFrom": {"id": "wemush:a"}},
            {"container": []},
            {"form": 5},
            {"strain": {"name": 5}},
        ],
    )
    def test_parse_rejects_wrong_json_types(self, extra: dict[str, Any]) -> None:
        with pytest.raises(WolsParseError):
            parse_specimen(json.dumps({**LABEL, **extra}))

    def test_created_text_is_kept(self) -> None:
        text = json.dumps({**LABEL, "created": "2026-11-10T09:00:00Z"})
        assert json.loads(to_json(parse_specimen(text)))["created"] == (
            "2026-11-10T09:00:00Z"
        )


class TestCreate:
    def test_1_5_members(self) -> None:
        specimen = create_specimen(
            type=SpecimenType.SPAWN,
            species="Pleurotus ostreatus",
            strain=Strain(generation="F2", lineage="wemush:parent"),
            form=SpecimenForm.GRAIN_SPAWN,
            derived_from=[{"id": "wemush:parent", "relation": "EXPANSION"}],
            condition="active",
            container={"format": "BAG", "capacity": {"value": 2, "unit": "kg"}},
            taxon={"scientificName": "Pleurotus ostreatus"},
            lot="L-1",
        )
        assert specimen.form == "GRAIN_SPAWN"
        assert specimen.condition is Condition.ACTIVE
        data = json.loads(to_json(specimen))
        assert data["derivedFrom"][0]["relation"] == "EXPANSION"
        assert data["lot"] == "L-1"
        assert validate_specimen(data).valid

    def test_condition_enum_is_kept(self) -> None:
        specimen = create_specimen(
            type="SUBSTRATE", species="P. ostreatus", condition=Condition.EXHAUSTED
        )
        assert specimen.condition is Condition.EXHAUSTED

    def test_invalid_members_are_collected(self) -> None:
        with pytest.raises(WolsValidationError) as exc_info:
            create_specimen(
                type="SUBSTRATE",
                species="P. ostreatus",
                condition="WILTING",
                form="Tube",
                derived_from=[],
                lot="",
            )
        assert {e.path for e in exc_info.value.errors} == {
            "condition",
            "form",
            "derivedFrom",
            "lot",
        }

    def test_lineage_mismatch(self) -> None:
        with pytest.raises(WolsValidationError) as exc_info:
            create_specimen(
                type="SUBSTRATE",
                species="P. ostreatus",
                strain=Strain(name="A", lineage="wemush:a"),
                derived_from=[{"id": "wemush:b"}],
            )
        assert [e.path for e in exc_info.value.errors] == ["strain.lineage"]


# ---------------------------------------------------------------------------
# Compact URLs
# ---------------------------------------------------------------------------


class TestPercentDecode:
    def test_plus(self) -> None:
        assert percent_decode("a+b") == "a+b"
        assert percent_decode("a+b", plus_as_space=True) == "a b"
        assert percent_decode("a%2Bb", plus_as_space=True) == "a+b"

    @pytest.mark.parametrize("text", ["%", "%2", "%zz", "%C3%28", "\ud800%41"])
    def test_invalid(self, text: str) -> None:
        with pytest.raises(InvalidEncoding):
            percent_decode(text)


class TestParseCompact:
    def test_result_fields(self) -> None:
        url = "wemush://v1/abc?s=POSTR&ty=SPAWN&t=0&b=B+1&x-room=2&x-room=3"
        ref = parse_compact_url(url)
        assert ref.specimen_id == "wemush:abc"
        assert ref.type is SpecimenType.SPAWN
        assert ref.created == datetime(1970, 1, 1, tzinfo=UTC)
        assert ref.batch == "B 1"
        assert ref.unrecognized_params == {"x-room": "2"}
        assert ref.signature is None

    def test_scheme_is_case_insensitive(self) -> None:
        assert parse_compact_url("WEMUSH://v1/abc?s=POSTR").id == "abc"

    @pytest.mark.parametrize(
        ("url", "ident"),
        [
            ("https://example.com/v1/abc?s=POSTR", "abc"),
            ("https://example.com/labels/s/v1/a%20b?s=POSTR", "a b"),
        ],
    )
    def test_https(self, url: str, ident: str) -> None:
        assert parse_compact_url(url).id == ident

    @pytest.mark.parametrize(
        ("url", "code"),
        [
            ("https://example.com/v1/encrypted/abc?e=AA", "ENCRYPTED_URL"),
            ("https://example.com/v2/abc?s=POSTR", "UNSUPPORTED_VERSION"),
            ("https://example.com/abc?s=POSTR", "INVALID_URL"),
            ("https://example.com/v1/abc/more?s=POSTR", "INVALID_URL"),
            ("wemush://v1/a/b?s=POSTR", "INVALID_URL"),
            ("wemush://v1/abc?s=POSTR#frag", "INVALID_URL"),
            ("wemush://v1/abc?s=", "MISSING_PARAMETER"),
            ("wemush://v1/abc?s=POSTR&t=99999999999999999999", "INVALID_PARAMETER"),
            ("wemush://v1/abc?s=POSTR&sg=+F2", "INVALID_PARAMETER"),
        ],
    )
    def test_refused(self, url: str, code: str) -> None:
        with pytest.raises(WolsParseError) as exc_info:
            parse_compact_url(url)
        assert exc_info.value.code == code

    def test_not_a_string(self) -> None:
        with pytest.raises(WolsParseError) as exc_info:
            parse_compact_url(5)  # type: ignore[arg-type]
        assert exc_info.value.code == "INVALID_URL"

    def test_empty_parameters_are_skipped(self) -> None:
        ref = parse_compact_url("wemush://v1/abc?&s=POSTR&&b=")
        assert ref.species_code == "POSTR"
        assert ref.params["b"] == ""

    def test_legacy_species_warns(self) -> None:
        with pytest.warns(WolsWarning, match="legacy"):
            ref = parse_compact_url("wemush://v1/abc?s=PO")
        assert ref.species == "Pleurotus ostreatus"

    def test_malformed_transfer_depth_warns(self) -> None:
        with pytest.warns(WolsWarning, match="'td'"):
            ref = parse_compact_url("wemush://v1/abc?s=POSTR&sg=F1&td=x")
        assert ref.strain is not None
        assert ref.strain.generation == "F1"
        assert ref.strain.transfer_depth is None

    def test_well_formed_url_does_not_warn(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            parse_compact_url("wemush://v1/abc?s=POSTR&sn=A&td=3")

    def test_generator_output_parses(self) -> None:
        specimen = create_specimen(
            type="SUBSTRATE", species="Pleurotus ostreatus", strain="Blue"
        )
        object.__setattr__(specimen, "id", "wemush:Lab A/1")
        url = to_compact_url(specimen)
        assert "Lab%20A%2F1" in url
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", WolsWarning)
            assert parse_compact_url(url).id == "Lab A/1"


class TestCompactShapeAndUnwrap:
    @pytest.mark.parametrize(
        ("url", "shape"),
        [
            ("wemush://v1/abc?s=POSTR", True),
            ("wemush://v1/encrypted?s=POSTR", True),
            ("wemush://v1/encrypted/abc?e=AA", False),
            ("wemush://v1/?s=POSTR", False),
            ("wemush://v1/a/b", False),
            ("web+wemush://v1/abc", False),
        ],
    )
    def test_is_compact_shape(self, url: str, shape: bool) -> None:
        assert is_compact_shape(url) is shape

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (5, None),
            ("https://example.com/wols/%zz", None),
            ("https://example.com/wols/wemush%3A%2F%2Fv1%2Fabc", "wemush://v1/abc"),
            ("WEB+wemush://v1/abc", None),
        ],
    )
    def test_unwrap(self, text: Any, expected: str | None) -> None:
        assert unwrap_wols_url(text) == expected


class TestCompactSignatures:
    URL = "wemush://v1/abc?s=POSTR&sn=Blue+Oyster&x-room=B2"

    def test_round_trip_result(self) -> None:
        signed = sign_compact_url(self.URL, SEED, "w1")
        result = verify_compact_url(signed, STORE)
        assert result.status is SignatureStatus.VALID
        assert result.form == "compact-url"
        assert result.params == {"s": "POSTR", "sn": "Blue Oyster", "x-room": "B2"}
        assert result.unrecognized_params == ("x-room",)
        assert verify_specimen(signed, STORE) == result

    def test_tampered(self) -> None:
        signed = sign_compact_url(self.URL, SEED, "w1").replace("B2", "B3")
        result = verify_compact_url(signed, STORE)
        assert result.status is SignatureStatus.INVALID
        assert result.params is None

    def test_unsigned(self) -> None:
        assert verify_compact_url(self.URL, STORE).status is SignatureStatus.UNSIGNED

    @pytest.mark.parametrize(
        "url",
        [
            "web+wemush://v1/abc?s=POSTR",
            "wemush://v1/encrypted/abc?e=AA",
            "wemush://v1/abc?s=POSTR&sig=w1.AAAA",
            "wemush://v1/abc?s=POSTR#x",
        ],
    )
    def test_signer_refuses(self, url: str) -> None:
        with pytest.raises(WolsSignatureError):
            sign_compact_url(url, SEED, "w1")

    def test_non_string_inputs(self) -> None:
        with pytest.raises(WolsSignatureError):
            sign_compact_url(5, SEED, "w1")  # type: ignore[arg-type]
        for verify in (verify_compact_url, verify_encrypted_url):
            result = verify(5, STORE)  # type: ignore[arg-type]
            assert result.status is SignatureStatus.MALFORMED
