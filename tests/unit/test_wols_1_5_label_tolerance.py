"""WOLS 1.5 label tolerance.

- ``version`` allows a pre-release suffix (``1.5.0-rc.1``)
- the 1.5 members are read into their own fields and written back
- unknown top-level members are valid (a warning) and survive a re-save
- ``_meta`` keys are camelCase on the wire; snake_case is still read
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from wols import Specimen, SpecimenType, parse_specimen, to_json, validate_specimen
from wols.crypto import decrypt_specimen_fields, encrypt_specimen_fields

BASE: dict[str, Any] = {
    "@context": "https://wemush.com/wols/v1",
    "@type": "Specimen",
    "id": "wemush:clx1a2b3c4",
    "version": "1.4.0",
    "type": "SUBSTRATE",
    "species": "Pleurotus ostreatus",
}

LABEL_1_5: dict[str, Any] = {
    **BASE,
    "version": "1.5.0-rc.1",
    "taxon": {"scientificName": "Pleurotus ostreatus", "rank": "species"},
    "lot": "TLC-2026-0042",
    "derivedFrom": [{"id": "wemush:parent1", "relation": "SPAWN_TO_BULK"}],
    "x-acme-room": "B2",
}


class TestPreReleaseVersion:
    def test_pre_release_label_parses(self) -> None:
        specimen = parse_specimen(json.dumps({**BASE, "version": "1.5.0-rc.1"}))
        assert specimen.version == "1.5.0-rc.1"

    def test_pre_release_version_is_valid(self) -> None:
        result = validate_specimen({**BASE, "version": "1.5.0-rc.1"})
        assert result.valid
        assert result.warnings == []

    def test_unknown_pre_release_version_is_a_warning(self) -> None:
        result = validate_specimen({**BASE, "version": "1.6.0-beta.1"})
        assert result.valid
        assert [w.code for w in result.warnings] == ["INVALID_VERSION"]


class TestUnknownMembers:
    def test_each_unknown_member_is_a_warning(self) -> None:
        result = validate_specimen(LABEL_1_5)
        assert result.valid
        unknown = sorted(w.path for w in result.warnings if w.code == "UNKNOWN_FIELD")
        assert unknown == ["x-acme-room"]

    def test_parse_keeps_unknown_members(self) -> None:
        specimen = parse_specimen(json.dumps(LABEL_1_5))
        assert specimen.unknown_members == {"x-acme-room": "B2"}
        assert specimen.taxon == LABEL_1_5["taxon"]
        assert specimen.lot == LABEL_1_5["lot"]
        assert specimen.derived_from == LABEL_1_5["derivedFrom"]

    def test_re_save_writes_them_back(self) -> None:
        specimen = parse_specimen(json.dumps(LABEL_1_5))
        assert json.loads(to_json(specimen)) == LABEL_1_5

    def test_round_trip_is_stable(self) -> None:
        once = to_json(parse_specimen(json.dumps(LABEL_1_5)))
        assert to_json(parse_specimen(once)) == once

    def test_label_without_unknown_members(self) -> None:
        specimen = parse_specimen(json.dumps(BASE))
        assert specimen.unknown_members is None
        assert json.loads(to_json(specimen)) == BASE

    def test_kept_member_never_overrides_a_known_field(self) -> None:
        specimen = Specimen(
            id="wemush:clx1a2b3c4",
            version="1.4.0",
            type=SpecimenType.SUBSTRATE,
            species="Pleurotus ostreatus",
            unknown_members={"id": "wemush:other", "species": "Other", "lot": "x"},
        )
        data = specimen.to_dict()
        assert data["id"] == "wemush:clx1a2b3c4"
        assert data["species"] == "Pleurotus ostreatus"
        assert data["lot"] == "x"

    def test_field_encryption_keeps_unknown_members(self) -> None:
        label = {**BASE, "strain": {"name": "Blue Oyster"}, "lot": "TLC-2026-0042"}
        specimen = parse_specimen(json.dumps(label))
        secret = "correct horse battery staple, long enough"
        encrypted = encrypt_specimen_fields(
            specimen, secret, ["strain"], iterations=100_000
        )
        assert encrypted["lot"] == "TLC-2026-0042"
        restored = decrypt_specimen_fields(encrypted, secret)
        assert restored["strain"] == {"name": "Blue Oyster"}
        assert restored["lot"] == "TLC-2026-0042"


class TestMetaWireCase:
    @pytest.mark.parametrize(
        "wire",
        [
            {"sourceId": "ext-1", "sourceSystem": "legacy", "note": "kept"},
            {"source_id": "ext-1", "source_system": "legacy", "note": "kept"},
        ],
        ids=["camelCase", "snake_case"],
    )
    def test_reads_either_case_and_writes_camel_case(
        self, wire: dict[str, Any]
    ) -> None:
        specimen = parse_specimen(json.dumps({**BASE, "_meta": wire}))
        assert specimen._meta is not None
        assert specimen._meta["source_id"] == "ext-1"
        assert specimen._meta["source_system"] == "legacy"
        out = json.loads(to_json(specimen))
        assert out["_meta"] == {
            "sourceId": "ext-1",
            "sourceSystem": "legacy",
            "note": "kept",
        }

    def test_camel_case_wins_when_both_are_present(self) -> None:
        wire = {"source_id": "old", "sourceId": "new"}
        specimen = parse_specimen(json.dumps({**BASE, "_meta": wire}))
        assert specimen._meta == {"source_id": "new"}
        assert json.loads(to_json(specimen))["_meta"] == {"sourceId": "new"}

    def test_every_standard_key_is_renamed(self) -> None:
        specimen = Specimen(
            id="wemush:clx1a2b3c4",
            version="1.4.0",
            type=SpecimenType.SUBSTRATE,
            species="Pleurotus ostreatus",
            _meta={
                "source_id": "a",
                "imported_at": "2026-01-25T10:00:00Z",
                "source_system": "b",
                "schema_version": "1.3.0",
            },
        )
        assert specimen.to_dict()["_meta"] == {
            "sourceId": "a",
            "importedAt": "2026-01-25T10:00:00Z",
            "sourceSystem": "b",
            "schemaVersion": "1.3.0",
        }

    def test_camel_case_wins_on_write_when_both_are_present(self) -> None:
        mixed: Any = {"source_id": "old", "sourceId": "new"}
        specimen = Specimen(
            id="wemush:clx1a2b3c4",
            version="1.4.0",
            type=SpecimenType.SUBSTRATE,
            species="Pleurotus ostreatus",
            _meta=mixed,
        )
        assert specimen.to_dict()["_meta"] == {"sourceId": "new"}
