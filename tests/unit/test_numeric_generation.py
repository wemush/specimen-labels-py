"""Numeric strain.generation (WOLS 1.4.0).

wols 1.3.0 accepted and wrote ``strain.generation`` as a JSON integer.
Decoders read one as its decimal string with a ``WolsWarning``; generators
always write a string.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import pytest

from wols import Specimen, SpecimenType, Strain, WolsWarning, create_specimen, to_json
from wols.crypto import (
    decrypt_specimen,
    decrypt_specimen_bytes,
    decrypt_specimen_fields,
    encrypt_specimen,
    encrypt_specimen_fields,
)

VECTORS = Path(__file__).parent.parent / "conformance" / "vectors"
KEY = bytes(range(32))


def _case(file: str, case_id: str) -> dict[str, Any]:
    doc = json.loads((VECTORS / file).read_text(encoding="utf-8"))
    return next(c for c in doc["cases"] if c["id"] == case_id)


def _label(generation: object) -> dict[str, Any]:
    return {
        "@context": "https://wemush.com/wols/v1",
        "@type": "Specimen",
        "id": "wemush:numeric-gen",
        "version": "1.3.0",
        "type": "CULTURE",
        "species": "Pleurotus ostreatus",
        "strain": {"name": "Blue Oyster", "generation": generation},
    }


class TestDecoding:
    def test_decrypt_specimen_reads_decimal_string(self) -> None:
        case = _case("encrypted.json", "decrypt-numeric-generation")
        url, passphrase = case["input"]["url"], case["input"]["secret"]["passphrase"]
        # The exact plaintext keeps the integer...
        assert decrypt_specimen_bytes(url, passphrase) == case["expected"][
            "plaintext"
        ].encode("utf-8")
        # ...and the decoded specimen has the decimal string.
        with pytest.warns(WolsWarning, match="strain.generation"):
            specimen = decrypt_specimen(url, passphrase)
        assert specimen.strain is not None
        assert specimen.strain.generation == "1"
        with warnings.catch_warnings():
            warnings.simplefilter("error", WolsWarning)  # expected has a string
            assert specimen == Specimen.from_dict(case["expected"]["specimen"])

    def test_decrypt_specimen_fields_reads_decimal_string(self) -> None:
        case = _case("field-encryption.json", "decrypt-fields-numeric-generation")
        secret = case["input"]["secret"]["passphrase"]
        with pytest.warns(WolsWarning, match="strain.generation"):
            restored = decrypt_specimen_fields(case["input"]["specimen"], secret)
        assert restored == case["expected"]["specimen"]

    def test_decrypt_specimen_fields_cleartext_strain(self) -> None:
        with pytest.warns(WolsWarning, match="strain.generation"):
            restored = decrypt_specimen_fields(_label(2), KEY)
        assert restored["strain"]["generation"] == "2"

    def test_decrypt_specimen_fields_does_not_mutate_input(self) -> None:
        label = _label(2)
        with pytest.warns(WolsWarning):
            decrypt_specimen_fields(label, KEY)
        assert label["strain"]["generation"] == 2

    def test_string_generation_does_not_warn(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", WolsWarning)
            restored = decrypt_specimen_fields(_label("F1"), KEY)
        assert restored["strain"]["generation"] == "F1"

    def test_non_object_strain_is_left_alone(self) -> None:
        label = {**_label("F1"), "strain": "Blue Oyster"}
        with warnings.catch_warnings():
            warnings.simplefilter("error", WolsWarning)
            restored = decrypt_specimen_fields(label, KEY)
        assert restored["strain"] == "Blue Oyster"


class TestGenerators:
    def test_create_and_serialize_write_a_string(self) -> None:
        with pytest.warns(WolsWarning, match="strain.generation"):
            strain = Strain(name="Blue Oyster", generation=1)
        specimen = create_specimen(
            input_type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
            strain=strain,
        )
        assert json.loads(to_json(specimen))["strain"]["generation"] == "1"

    def test_encrypt_specimen_writes_a_string(self) -> None:
        with pytest.warns(WolsWarning):
            specimen = Specimen.from_dict(_label(1))
        url = encrypt_specimen(specimen, KEY)
        plaintext = json.loads(decrypt_specimen_bytes(url, KEY))
        assert plaintext["strain"]["generation"] == "1"

    def test_encrypt_specimen_fields_writes_a_string(self) -> None:
        label = _label(1)
        with pytest.warns(WolsWarning, match="strain.generation"):
            encrypted = encrypt_specimen_fields(label, KEY, ["strain"])
        # The caller's dict is unchanged; the encrypted value holds a string.
        assert label["strain"]["generation"] == 1
        with warnings.catch_warnings():
            warnings.simplefilter("error", WolsWarning)
            restored = decrypt_specimen_fields(encrypted, KEY)
        assert restored["strain"]["generation"] == "1"

    def test_encrypt_specimen_fields_cleartext_strain_is_a_string(self) -> None:
        with pytest.warns(WolsWarning):
            encrypted = encrypt_specimen_fields(_label(1), KEY, ["stage"])
        assert encrypted["strain"]["generation"] == "1"
