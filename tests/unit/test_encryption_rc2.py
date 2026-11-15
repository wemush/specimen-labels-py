"""WOLS 1.3.0-rc.2 encryption rules not fully covered by the vectors.

The vectors check decoding. These tests check that generated labels follow
the same rules: NFC passphrases, field AAD, iteration limits, ID
percent-encoding, and byte-order-mark handling.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import unicodedata

import pytest

pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from wols import Strain, create_specimen
from wols.crypto import (
    b64url_decode,
    b64url_encode,
    decrypt_specimen,
    decrypt_specimen_bytes,
    decrypt_specimen_fields,
    derive_key,
    encrypt_specimen,
    encrypt_specimen_fields,
    parse_encrypted_url,
)
from wols.crypto.wire import MAX_DECODE_ITERATIONS
from wols.exceptions import WolsEncryptionError

FAST = 100_000
PASSPHRASE = "Pilzzüchter Ångström"


@pytest.fixture
def specimen():  # type: ignore[no-untyped-def]
    return create_specimen(
        type="SUBSTRATE",
        species="Pleurotus ostreatus",
        strain=Strain(name="MO-Blue-001", generation="F1"),
        batch="batch_2025_12_001",
        creator="lab",
    )


class TestNfcPassphrase:
    def test_nfc_and_nfd_derive_the_same_key(self) -> None:
        salt = os.urandom(16)
        nfc = unicodedata.normalize("NFC", PASSPHRASE)
        nfd = unicodedata.normalize("NFD", PASSPHRASE)
        assert nfc != nfd
        assert derive_key(nfc, salt, 10_000) == derive_key(nfd, salt, 10_000)

    def test_url_encrypted_with_nfd_decrypts_with_nfc(self, specimen) -> None:  # type: ignore[no-untyped-def]
        url = encrypt_specimen(
            specimen, unicodedata.normalize("NFD", PASSPHRASE), iterations=FAST
        )
        nfc = unicodedata.normalize("NFC", PASSPHRASE)
        assert decrypt_specimen(url, nfc) == specimen

    def test_fields_encrypted_with_nfc_decrypt_with_nfd(self, specimen) -> None:  # type: ignore[no-untyped-def]
        data = encrypt_specimen_fields(
            specimen,
            unicodedata.normalize("NFC", PASSPHRASE),
            ["batch"],
            iterations=FAST,
        )
        nfd = unicodedata.normalize("NFD", PASSPHRASE)
        assert decrypt_specimen_fields(data, nfd)["batch"] == "batch_2025_12_001"


class TestFieldAad:
    def test_aad_is_label_id_and_field_name(self, specimen) -> None:  # type: ignore[no-untyped-def]
        key = os.urandom(32)
        obj = encrypt_specimen_fields(specimen, key, ["batch"])["batch"]
        aad = f"{specimen.id}\nbatch".encode()
        plaintext = AESGCM(key).decrypt(
            b64url_decode(obj["iv"]), b64url_decode(obj["payload"]), aad
        )
        assert json.loads(plaintext) == "batch_2025_12_001"

    def test_swapped_fields_fail(self, specimen) -> None:  # type: ignore[no-untyped-def]
        data = encrypt_specimen_fields(
            specimen, "pw-swap", ["batch", "creator"], iterations=FAST
        )
        data["batch"], data["creator"] = data["creator"], data["batch"]
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(data, "pw-swap")
        assert exc_info.value.code == "AUTHENTICATION_FAILED"

    def test_field_from_other_label_fails(self, specimen) -> None:  # type: ignore[no-untyped-def]
        key = os.urandom(32)
        other = dataclasses.replace(specimen, id="wemush:other")
        donor = encrypt_specimen_fields(other, key, ["batch"])
        data = encrypt_specimen_fields(specimen, key, ["creator"])
        data["batch"] = donor["batch"]
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(data, key)
        assert exc_info.value.code == "AUTHENTICATION_FAILED"

    def test_changed_label_id_fails(self, specimen) -> None:  # type: ignore[no-untyped-def]
        key = os.urandom(32)
        data = encrypt_specimen_fields(specimen, key, ["batch"])
        data["id"] = "wemush:relabelled"
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(data, key)
        assert exc_info.value.code == "AUTHENTICATION_FAILED"

    def test_each_field_gets_its_own_iv(self, specimen) -> None:  # type: ignore[no-untyped-def]
        data = encrypt_specimen_fields(specimen, os.urandom(32), ["batch", "creator"])
        assert data["batch"]["iv"] != data["creator"]["iv"]

    @pytest.mark.parametrize("label_id", [None, 42, "", "nope"])
    def test_encrypt_requires_label_id(self, specimen, label_id: object) -> None:  # type: ignore[no-untyped-def]
        data = specimen.to_dict()
        if label_id is None:
            del data["id"]
        else:
            data["id"] = label_id
        with pytest.raises(WolsEncryptionError) as exc_info:
            encrypt_specimen_fields(data, os.urandom(32), ["batch"])
        assert exc_info.value.code == "INVALID_ID"

    def test_decrypt_requires_string_id(self, specimen) -> None:  # type: ignore[no-untyped-def]
        key = os.urandom(32)
        data = encrypt_specimen_fields(specimen, key, ["batch"])
        del data["id"]
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(data, key)
        assert exc_info.value.code == "INVALID_ID"

    def test_field_plaintext_bom_rejected(self, specimen) -> None:  # type: ignore[no-untyped-def]
        key = os.urandom(32)
        iv = os.urandom(12)
        aad = f"{specimen.id}\nbatch".encode()
        ct = AESGCM(key).encrypt(iv, b'\xef\xbb\xbf"x"', aad)
        data = specimen.to_dict()
        data["batch"] = {
            "encrypted": True,
            "algorithm": "AES-256-GCM",
            "payload": b64url_encode(ct),
            "iv": b64url_encode(iv),
            "kdf": "raw",
        }
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(data, key)
        assert exc_info.value.code == "INVALID_PLAINTEXT"


class TestGeneratorIterations:
    def test_above_decoder_maximum_rejected(self, specimen) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(WolsEncryptionError) as exc_info:
            encrypt_specimen(specimen, "pw", iterations=MAX_DECODE_ITERATIONS + 1)
        assert exc_info.value.code == "INVALID_PARAMETER"


class TestIdPercentEncoding:
    @pytest.mark.parametrize(
        "suffix",
        ["Lab A/plate+3%", "Pilz-ü", "a?b#c", "tab\there", "plus+sign"],
    )
    def test_round_trip(self, specimen, suffix: str) -> None:  # type: ignore[no-untyped-def]
        spec = dataclasses.replace(specimen, id=f"wemush:{suffix}")
        key = os.urandom(32)
        url = encrypt_specimen(spec, key)
        path_segment = url.split("?", 1)[0].rsplit("/", 1)[1]
        # Only RFC 3986 unreserved characters and escapes remain.
        assert re.fullmatch(r"(?:[A-Za-z0-9._~-]|%[0-9A-F]{2})+", path_segment)
        assert parse_encrypted_url(url).id == suffix
        assert decrypt_specimen(url, key) == spec

    def test_literal_plus_is_not_a_space(self) -> None:
        key = os.urandom(32)
        spec = create_specimen(type="CULTURE", species="x")
        spec = dataclasses.replace(spec, id="wemush:a+b")
        url = encrypt_specimen(spec, key).replace("a%2Bb", "a+b")
        assert parse_encrypted_url(url).id == "a+b"
        assert decrypt_specimen(url, key) == spec

    @pytest.mark.parametrize("segment", ["abc%", "abc%2", "abc%zz", "%C3%28", "%FF"])
    def test_malformed_id_rejected_before_derivation(self, segment: str) -> None:
        url = (
            f"wemush://v1/encrypted/{segment}?e={b64url_encode(b'x' * 32)}"
            f"&iv={b64url_encode(b'i' * 12)}&kdf=pbkdf2"
            f"&salt={b64url_encode(b's' * 16)}&i=100000"
        )
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_bytes(url, "pw")
        assert exc_info.value.code == "INVALID_ENCODING"

    def test_invalid_utf8_in_query_rejected(self) -> None:
        url = (
            f"wemush://v1/encrypted/abc?e={b64url_encode(b'x' * 32)}"
            f"&iv={b64url_encode(b'i' * 12)}&kdf=raw&sig=%FF"
        )
        with pytest.raises(WolsEncryptionError) as exc_info:
            parse_encrypted_url(url)
        assert exc_info.value.code == "INVALID_ENCODING"
