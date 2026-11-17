"""RawKey wrapper and the opt-in strict_passphrase flag."""

from __future__ import annotations

import base64
import os
import warnings

import pytest

from wols import Specimen, WolsEncryptionError, WolsWarning, create_specimen
from wols.crypto import (
    RawKey,
    b64url_encode,
    decrypt_specimen,
    decrypt_specimen_bytes,
    decrypt_specimen_fields,
    encrypt_specimen,
    encrypt_specimen_fields,
)

KEY = bytes(range(32))


@pytest.fixture
def specimen() -> Specimen:
    return create_specimen(type="CULTURE", species="x", strain="s", batch="B")


class TestConstruction:
    @pytest.mark.parametrize(
        "value",
        [
            KEY,
            bytearray(KEY),
            memoryview(KEY),
            base64.b64encode(KEY).decode(),
            base64.b64encode(KEY).decode().rstrip("="),
            base64.urlsafe_b64encode(KEY).decode(),
            b64url_encode(KEY),
            f"  {base64.b64encode(KEY).decode()}\n",
        ],
    )
    def test_accepted_forms(self, value: bytes | bytearray | memoryview | str) -> None:
        assert RawKey(value).key == KEY
        assert bytes(RawKey(value)) == KEY

    def test_both_alphabets(self) -> None:
        # 0xfb 0xff encodes to "+/" in standard and "-_" in base64url.
        key = b"\xfb\xff" * 16
        assert RawKey(base64.b64encode(key).decode()).key == key
        assert RawKey(base64.urlsafe_b64encode(key).decode()).key == key

    @pytest.mark.parametrize(
        "value",
        [
            b"\x00" * 31,
            b"\x00" * 33,
            b"",
            base64.b64encode(b"\x00" * 16).decode(),
            base64.b64encode(b"\x00" * 33).decode(),
            "not base64 at all!",
            "",
            "+" + b64url_encode(KEY)[1:-1] + "_",  # mixed alphabets
            "A",  # impossible length
            "correct horse battery staple",
        ],
    )
    def test_rejected_values(self, value: bytes | str) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            RawKey(value)
        assert exc_info.value.code == "INVALID_KEY"

    @pytest.mark.parametrize("value", [None, 5, [1, 2], RawKey(KEY)])
    def test_rejected_types(self, value: object) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            RawKey(value)  # type: ignore[arg-type]
        assert exc_info.value.code == "INVALID_KEY"

    def test_copies_mutable_input(self) -> None:
        buf = bytearray(KEY)
        key = RawKey(buf)
        buf[0] ^= 0xFF
        assert key.key == KEY


class TestValueSemantics:
    def test_equality_and_hash(self) -> None:
        a = RawKey(KEY)
        b = RawKey(base64.b64encode(KEY).decode())
        assert a == b
        assert hash(a) == hash(b)
        assert a != RawKey(os.urandom(32))
        assert a != KEY  # a RawKey is not bytes

    def test_repr_hides_key(self) -> None:
        key = RawKey(KEY)
        text = repr(key)
        assert text == "RawKey(<32 bytes>)"
        assert base64.b64encode(KEY).decode() not in text
        assert KEY.hex() not in text
        assert str(key) == text

    def test_key_is_read_only(self) -> None:
        key = RawKey(KEY)
        with pytest.raises(AttributeError):
            key.key = b"\x00" * 32  # type: ignore[misc]
        with pytest.raises(AttributeError):
            key.other = 1  # type: ignore[attr-defined]


class TestAcceptedAsSecret:
    def test_url_round_trip(self, specimen: Specimen) -> None:
        url = encrypt_specimen(specimen, RawKey(KEY))
        assert "kdf=raw" in url
        assert decrypt_specimen(url, RawKey(KEY)) == specimen
        assert decrypt_specimen(url, KEY) == specimen
        assert decrypt_specimen_bytes(url, RawKey(KEY))

    def test_interchangeable_with_bytes(self, specimen: Specimen) -> None:
        url = encrypt_specimen(specimen, KEY)
        assert decrypt_specimen(url, RawKey(b64url_encode(KEY))) == specimen

    def test_fields_round_trip(self, specimen: Specimen) -> None:
        data = encrypt_specimen_fields(specimen, RawKey(KEY), ["strain", "batch"])
        assert data["batch"]["kdf"] == "raw"
        restored = decrypt_specimen_fields(data, RawKey(KEY))
        assert restored == specimen.to_dict()

    def test_wrong_key_fails_auth(self, specimen: Specimen) -> None:
        url = encrypt_specimen(specimen, RawKey(KEY))
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(url, RawKey(os.urandom(32)))
        assert exc_info.value.code == "AUTHENTICATION_FAILED"

    def test_not_a_passphrase(self, specimen: Specimen) -> None:
        url = encrypt_specimen(specimen, "pw", iterations=100_000)
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(url, RawKey(KEY))
        assert exc_info.value.code == "INVALID_KEY"

    def test_no_warning(self, specimen: Specimen) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", WolsWarning)
            encrypt_specimen(specimen, RawKey(base64.b64encode(KEY).decode()))


class TestStrictPassphrase:
    def test_default_still_warns(self, specimen: Specimen) -> None:
        key_str = base64.b64encode(KEY).decode()
        with pytest.warns(WolsWarning, match=r"RawKey\(key\)"):
            url = encrypt_specimen(specimen, key_str, iterations=100_000)
        assert "kdf=pbkdf2" in url

    @pytest.mark.parametrize("encode", [base64.b64encode, b64url_encode])
    def test_strict_raises(self, specimen: Specimen, encode: object) -> None:
        encoded = encode(KEY)  # type: ignore[operator]
        key_str = encoded if isinstance(encoded, str) else encoded.decode()
        with pytest.raises(WolsEncryptionError) as exc_info:
            encrypt_specimen(specimen, key_str, strict_passphrase=True)
        assert exc_info.value.code == "INVALID_KEY"
        with pytest.raises(WolsEncryptionError) as exc_info:
            encrypt_specimen_fields(
                specimen, key_str, ["batch"], strict_passphrase=True
            )
        assert exc_info.value.code == "INVALID_KEY"

    def test_strict_allows_ordinary_passphrase(self, specimen: Specimen) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", WolsWarning)
            url = encrypt_specimen(
                specimen,
                "correct horse battery staple",
                iterations=100_000,
                strict_passphrase=True,
            )
        assert decrypt_specimen(url, "correct horse battery staple") == specimen

    def test_strict_ignores_raw_keys(self, specimen: Specimen) -> None:
        assert "kdf=raw" in encrypt_specimen(specimen, KEY, strict_passphrase=True)
        assert "kdf=raw" in encrypt_specimen(
            specimen, RawKey(KEY), strict_passphrase=True
        )
