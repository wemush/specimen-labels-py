"""Tests for wols.crypto (WOLS v1.3.0 encrypted format)."""

from __future__ import annotations

import base64
import json
import os
from urllib.parse import parse_qs, urlsplit

import pytest

from wols import (
    GrowthStage,
    Specimen,
    SpecimenType,
    Strain,
    WolsEncryptionError,
    validate_specimen,
)
from wols.crypto import (
    b64url_decode,
    b64url_encode,
    decrypt_specimen,
    decrypt_specimen_bytes,
    decrypt_specimen_fields,
    encrypt_specimen,
    encrypt_specimen_fields,
    is_encrypted_url,
    parse_encrypted_url,
)

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def crypto_specimen() -> Specimen:
    """Specimen for crypto tests."""
    return Specimen(
        id="wemush:abc123def456ghijklmnopqr",
        version="1.3.0",
        type=SpecimenType.SUBSTRATE,
        species="Pleurotus ostreatus",
    )


@pytest.fixture
def full_specimen() -> Specimen:
    """Full specimen with all fields for testing partial encryption."""
    return Specimen(
        id="wemush:abc123def456ghijklmnopqr",
        version="1.3.0",
        type=SpecimenType.SUBSTRATE,
        species="Pleurotus ostreatus",
        strain=Strain(
            name="Blue Oyster", generation="F1", clonal_generation=3, transfer_depth=5
        ),
        stage=GrowthStage.COLONIZATION,
        batch="BATCH-001",
        organization="WeMush",
        creator="test@example.com",
        custom={"temp": 72},
    )


@pytest.fixture
def raw_key() -> bytes:
    """32-byte encryption key for testing."""
    return b"0123456789abcdef0123456789abcdef"


def _params(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def _replace_param(url: str, name: str, value: str | None) -> str:
    base, query = url.split("?", 1)
    pairs = [p.split("=", 1) for p in query.split("&")]
    out = [f"{k}={v}" for k, v in pairs if k != name]
    if value is not None:
        out.append(f"{name}={value}")
    return f"{base}?{'&'.join(out)}"


def _raw_url(id_suffix: str, plaintext: bytes, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, plaintext, None)
    return (
        f"wemush://v1/encrypted/{id_suffix}?e={b64url_encode(ct)}"
        f"&iv={b64url_encode(iv)}&kdf=raw"
    )


def _legacy_blob(plaintext: bytes, key: bytes) -> str:
    """The wols 1.x format: base64(nonce || ciphertext || tag)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    return base64.b64encode(
        nonce + AESGCM(key).encrypt(nonce, plaintext, None)
    ).decode()


class TestEncryptedUrlFormat:
    """encrypt_specimen produces the v1.3.0 wire format."""

    def test_passphrase_url_shape(self, crypto_specimen: Specimen) -> None:
        url = encrypt_specimen(crypto_specimen, PASSPHRASE)
        assert url.startswith("wemush://v1/encrypted/abc123def456ghijklmnopqr?")
        params = _params(url)
        assert params["kdf"] == "pbkdf2"
        assert int(params["i"]) >= 100_000
        assert len(b64url_decode(params["salt"])) >= 16
        assert len(b64url_decode(params["iv"])) == 12
        assert all("=" not in value for value in params.values())  # unpadded

    def test_raw_url_shape(self, crypto_specimen: Specimen, raw_key: bytes) -> None:
        url = encrypt_specimen(crypto_specimen, raw_key)
        params = _params(url)
        assert params["kdf"] == "raw"
        assert "salt" not in params
        assert "i" not in params
        # Ciphertext carries the 16-byte tag; the IV is not prefixed.
        plaintext_len = len(
            json.dumps(crypto_specimen.to_dict(), separators=(",", ":")).encode()
        )
        assert len(b64url_decode(params["e"])) == plaintext_len + 16

    def test_fresh_iv_and_salt_every_call(self, crypto_specimen: Specimen) -> None:
        a = _params(encrypt_specimen(crypto_specimen, PASSPHRASE))
        b = _params(encrypt_specimen(crypto_specimen, PASSPHRASE))
        assert a["iv"] != b["iv"]
        assert a["salt"] != b["salt"]
        assert a["e"] != b["e"]

    def test_custom_iterations(self, crypto_specimen: Specimen) -> None:
        url = encrypt_specimen(crypto_specimen, PASSPHRASE, iterations=150_000)
        assert _params(url)["i"] == "150000"
        assert decrypt_specimen(url, PASSPHRASE) == crypto_specimen

    @pytest.mark.parametrize("iterations", [99_999, 10_000, 0])
    def test_low_iterations_rejected_when_generating(
        self, crypto_specimen: Specimen, iterations: int
    ) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            encrypt_specimen(crypto_specimen, PASSPHRASE, iterations=iterations)
        assert exc_info.value.code == "INVALID_PARAMETER"

    def test_never_generates_legacy(
        self, crypto_specimen: Specimen, raw_key: bytes
    ) -> None:
        for secret in (PASSPHRASE, raw_key):
            url = encrypt_specimen(crypto_specimen, secret)
            assert is_encrypted_url(url)
            assert "kdf" in _params(url)

    def test_id_is_percent_encoded(self, raw_key: bytes) -> None:
        specimen = Specimen(
            id="wemush:WM LC/01",
            version="1.3.0",
            type=SpecimenType.CULTURE,
            species="Pleurotus ostreatus",
        )
        url = encrypt_specimen(specimen, raw_key)
        assert url.startswith("wemush://v1/encrypted/WM%20LC%2F01?")
        assert parse_encrypted_url(url).specimen_id == "wemush:WM LC/01"
        assert decrypt_specimen(url, raw_key) == specimen

    @pytest.mark.parametrize("bad_id", ["abc123", "wemush:"])
    def test_invalid_id_rejected(self, raw_key: bytes, bad_id: str) -> None:
        specimen = Specimen(
            id=bad_id, version="1.3.0", type=SpecimenType.CULTURE, species="Test"
        )
        with pytest.raises(WolsEncryptionError) as exc_info:
            encrypt_specimen(specimen, raw_key)
        assert exc_info.value.code == "INVALID_ID"


class TestSecrets:
    """The secret type selects the KDF."""

    def test_short_raw_key_rejected(self, crypto_specimen: Specimen) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            encrypt_specimen(crypto_specimen, b"too_short")
        assert exc_info.value.code == "INVALID_KEY"
        assert "32 bytes" in str(exc_info.value)

    def test_empty_passphrase_rejected(self, crypto_specimen: Specimen) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            encrypt_specimen(crypto_specimen, "")
        assert exc_info.value.code == "INVALID_KEY"

    def test_non_secret_type_rejected(self, crypto_specimen: Specimen) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            encrypt_specimen(crypto_specimen, 12345)  # type: ignore[arg-type]
        assert exc_info.value.code == "INVALID_KEY"

    def test_passphrase_for_raw_label_rejected(
        self, crypto_specimen: Specimen, raw_key: bytes
    ) -> None:
        url = encrypt_specimen(crypto_specimen, raw_key)
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(url, PASSPHRASE)
        assert exc_info.value.code == "INVALID_KEY"

    def test_key_for_pbkdf2_label_rejected(
        self, crypto_specimen: Specimen, raw_key: bytes
    ) -> None:
        url = encrypt_specimen(crypto_specimen, PASSPHRASE)
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(url, raw_key)
        assert exc_info.value.code == "INVALID_KEY"


class TestEncryptDecrypt:
    """Round trips and decode-side checks."""

    def test_passphrase_roundtrip(self, full_specimen: Specimen) -> None:
        url = encrypt_specimen(full_specimen, PASSPHRASE)
        assert decrypt_specimen(url, PASSPHRASE) == full_specimen

    def test_raw_key_roundtrip(self, full_specimen: Specimen, raw_key: bytes) -> None:
        url = encrypt_specimen(full_specimen, raw_key)
        decrypted = decrypt_specimen(url, bytearray(raw_key))
        assert decrypted == full_specimen
        assert decrypted.strain is not None
        assert decrypted.strain.transfer_depth == 5

    def test_decrypt_bytes_is_compact_json(
        self, crypto_specimen: Specimen, raw_key: bytes
    ) -> None:
        url = encrypt_specimen(crypto_specimen, raw_key)
        plaintext = decrypt_specimen_bytes(url, raw_key)
        assert json.loads(plaintext) == crypto_specimen.to_dict()
        assert b", " not in plaintext

    def test_web_wemush_scheme_accepted(
        self, crypto_specimen: Specimen, raw_key: bytes
    ) -> None:
        url = "web+" + encrypt_specimen(crypto_specimen, raw_key)
        assert decrypt_specimen(url, raw_key) == crypto_specimen

    def test_wrong_passphrase_fails(self, crypto_specimen: Specimen) -> None:
        url = encrypt_specimen(crypto_specimen, PASSPHRASE)
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(url, "wrong passphrase")
        assert exc_info.value.code == "AUTHENTICATION_FAILED"

    def test_wrong_key_fails(self, crypto_specimen: Specimen, raw_key: bytes) -> None:
        url = encrypt_specimen(crypto_specimen, raw_key)
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(url, b"zyxwvutsrqponmlkzyxwvutsrqponmlk")
        assert exc_info.value.code == "AUTHENTICATION_FAILED"

    def test_id_mismatch_rejected(self, raw_key: bytes) -> None:
        plaintext = json.dumps(
            {"id": "wemush:other", "type": "CULTURE", "species": "Test"}
        ).encode()
        url = _raw_url("abc", plaintext, raw_key)
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(url, raw_key)
        assert exc_info.value.code == "ID_MISMATCH"

    @pytest.mark.parametrize("plaintext", [b"not json", b"[1, 2]", b"\xff\xfe"])
    def test_non_object_plaintext_rejected(
        self, raw_key: bytes, plaintext: bytes
    ) -> None:
        url = _raw_url("abc", plaintext, raw_key)
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_bytes(url, raw_key)
        assert exc_info.value.code == "INVALID_PAYLOAD"


class TestDecodeValidation:
    """parse_encrypted_url rejects malformed labels before decrypting."""

    @pytest.fixture
    def raw_url(self, crypto_specimen: Specimen, raw_key: bytes) -> str:
        return encrypt_specimen(crypto_specimen, raw_key)

    @pytest.fixture
    def pbkdf2_url(self, crypto_specimen: Specimen) -> str:
        return encrypt_specimen(crypto_specimen, PASSPHRASE)

    def test_parse_fields(self, pbkdf2_url: str) -> None:
        label = parse_encrypted_url(pbkdf2_url)
        assert label.id == "abc123def456ghijklmnopqr"
        assert label.payload.kdf == "pbkdf2"
        assert label.payload.iterations == 100_000
        assert len(label.payload.iv) == 12
        assert label.signature is None

    def test_signature_preserved_but_ignored(
        self, raw_url: str, raw_key: bytes, crypto_specimen: Specimen
    ) -> None:
        url = raw_url + "&sig=abc123"
        assert parse_encrypted_url(url).signature == "abc123"
        assert decrypt_specimen(url, raw_key) == crypto_specimen

    def test_padded_values_accepted(
        self, raw_url: str, raw_key: bytes, crypto_specimen: Specimen
    ) -> None:
        iv = _params(raw_url)["iv"]
        padded = iv + "=" * (-len(iv) % 4)
        assert (
            decrypt_specimen(_replace_param(raw_url, "iv", padded), raw_key)
            == crypto_specimen
        )

    @pytest.mark.parametrize(
        ("name", "value", "code"),
        [
            ("iv", "not+base64", "INVALID_PARAMETER"),
            ("iv", b64url_encode(b"short"), "INVALID_PARAMETER"),
            ("e", b64url_encode(b"x" * 8), "INVALID_PARAMETER"),
            ("e", None, "MISSING_PARAMETER"),
            ("iv", None, "MISSING_PARAMETER"),
            ("kdf", None, "LEGACY_FORMAT"),
            ("kdf", "scrypt", "UNSUPPORTED_KDF"),
            ("i", "100000", "UNEXPECTED_PARAMETER"),
        ],
    )
    def test_raw_url_errors(
        self, raw_url: str, name: str, value: str | None, code: str
    ) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            parse_encrypted_url(_replace_param(raw_url, name, value))
        assert exc_info.value.code == code

    @pytest.mark.parametrize(
        ("name", "value", "code"),
        [
            ("i", None, "MISSING_PARAMETER"),
            ("i", "9999", "INSUFFICIENT_ITERATIONS"),
            ("i", "1e5", "INVALID_PARAMETER"),
            ("i", "-100000", "INVALID_PARAMETER"),
            ("i", "99999999999", "INVALID_PARAMETER"),
            ("salt", None, "MISSING_PARAMETER"),
            ("salt", "", "INVALID_PARAMETER"),
        ],
    )
    def test_pbkdf2_url_errors(
        self, pbkdf2_url: str, name: str, value: str | None, code: str
    ) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            parse_encrypted_url(_replace_param(pbkdf2_url, name, value))
        assert exc_info.value.code == code

    def test_duplicate_parameter_rejected(self, raw_url: str) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            parse_encrypted_url(raw_url + "&kdf=raw")
        assert exc_info.value.code == "INVALID_PARAMETER"

    @pytest.mark.parametrize(
        "url",
        [
            "https://wemush.com/v1/encrypted/abc?e=x&iv=y&kdf=raw",
            "wemush://v1/abc?e=x&iv=y&kdf=raw",
            "wemush://v1/encrypted/?e=x&iv=y&kdf=raw",
            "wemush://v1/encrypted/a/b?e=x&iv=y&kdf=raw",
        ],
    )
    def test_invalid_url_rejected(self, url: str) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            parse_encrypted_url(url)
        assert exc_info.value.code == "INVALID_URL"

    def test_is_encrypted_url(self, raw_url: str) -> None:
        assert is_encrypted_url(raw_url)
        assert is_encrypted_url("web+" + raw_url)
        assert not is_encrypted_url("wemush://v1/abc?s=PO")
        assert not is_encrypted_url("not a url")


class TestLegacyFormat:
    """The wols 1.x payload is readable only with allow_legacy=True."""

    def test_legacy_rejected_by_default(
        self, crypto_specimen: Specimen, raw_key: bytes
    ) -> None:
        blob = _legacy_blob(json.dumps(crypto_specimen.to_dict()).encode(), raw_key)
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(blob, raw_key)
        assert exc_info.value.code == "LEGACY_FORMAT"

    def test_legacy_with_bytes_key(
        self, crypto_specimen: Specimen, raw_key: bytes
    ) -> None:
        blob = _legacy_blob(json.dumps(crypto_specimen.to_dict()).encode(), raw_key)
        assert decrypt_specimen(blob, raw_key, allow_legacy=True) == crypto_specimen

    def test_legacy_with_base64_key(
        self, crypto_specimen: Specimen, raw_key: bytes
    ) -> None:
        blob = _legacy_blob(json.dumps(crypto_specimen.to_dict()).encode(), raw_key)
        b64_key = base64.b64encode(raw_key).decode()
        assert decrypt_specimen(blob, b64_key, allow_legacy=True) == crypto_specimen

    def test_legacy_wrong_key(self, crypto_specimen: Specimen, raw_key: bytes) -> None:
        blob = _legacy_blob(json.dumps(crypto_specimen.to_dict()).encode(), raw_key)
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(blob, b"z" * 32, allow_legacy=True)
        assert exc_info.value.code == "AUTHENTICATION_FAILED"

    @pytest.mark.parametrize(
        ("payload", "key", "code"),
        [
            ("not-valid-base64!!!", b"0" * 32, "INVALID_PAYLOAD"),
            (base64.b64encode(b"short").decode(), b"0" * 32, "INVALID_PAYLOAD"),
            ("AAAA", "not-valid-base64!!!", "INVALID_KEY"),
            ("AAAA", base64.b64encode(b"0" * 16).decode(), "INVALID_KEY"),
        ],
    )
    def test_legacy_errors(self, payload: str, key: str | bytes, code: str) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen(payload, key, allow_legacy=True)
        assert exc_info.value.code == code


class TestFieldEncryption:
    """Field-level encryption objects."""

    def test_field_object_shape_pbkdf2(self, full_specimen: Specimen) -> None:
        data = encrypt_specimen_fields(full_specimen, PASSPHRASE, ["strain", "batch"])
        for field in ("strain", "batch"):
            obj = data[field]
            assert obj["encrypted"] is True
            assert obj["algorithm"] == "AES-256-GCM"
            assert obj["kdf"] == "pbkdf2"
            assert obj["iterations"] >= 100_000
            assert len(b64url_decode(obj["salt"])) >= 16
            assert len(b64url_decode(obj["iv"])) == 12
            assert "=" not in obj["payload"] + obj["iv"] + obj["salt"]
        # One salt per label, a fresh IV per field.
        assert data["strain"]["salt"] == data["batch"]["salt"]
        assert data["strain"]["iv"] != data["batch"]["iv"]
        # Unlisted fields are untouched.
        assert data["organization"] == "WeMush"
        assert data["id"] == full_specimen.id

    def test_field_object_shape_raw(
        self, full_specimen: Specimen, raw_key: bytes
    ) -> None:
        obj = encrypt_specimen_fields(full_specimen, raw_key, ["custom"])["custom"]
        assert obj["kdf"] == "raw"
        assert "salt" not in obj
        assert "iterations" not in obj

    @pytest.mark.parametrize("use_passphrase", [True, False])
    def test_roundtrip(
        self, full_specimen: Specimen, raw_key: bytes, use_passphrase: bool
    ) -> None:
        secret: str | bytes = PASSPHRASE if use_passphrase else raw_key
        fields = ["strain", "stage", "batch", "organization", "creator", "custom"]
        data = encrypt_specimen_fields(full_specimen, secret, fields)
        assert validate_specimen(data).valid
        restored = decrypt_specimen_fields(data, secret)
        assert Specimen.from_dict(restored) == full_specimen

    def test_field_plaintext_is_json(
        self, full_specimen: Specimen, raw_key: bytes
    ) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        obj = encrypt_specimen_fields(full_specimen, raw_key, ["custom"])["custom"]
        plaintext = AESGCM(raw_key).decrypt(
            b64url_decode(obj["iv"]), b64url_decode(obj["payload"]), None
        )
        assert json.loads(plaintext) == {"temp": 72}

    def test_dict_input_not_mutated(
        self, full_specimen: Specimen, raw_key: bytes
    ) -> None:
        original = full_specimen.to_dict()
        snapshot = json.loads(json.dumps(original))
        encrypt_specimen_fields(original, raw_key, ["strain", "custom"])
        assert original == snapshot

    def test_invalid_field_name(self, full_specimen: Specimen, raw_key: bytes) -> None:
        with pytest.raises(ValueError, match="Invalid field"):
            encrypt_specimen_fields(full_specimen, raw_key, ["species"])

    def test_none_field_left_alone(
        self, crypto_specimen: Specimen, raw_key: bytes
    ) -> None:
        data = encrypt_specimen_fields(crypto_specimen, raw_key, ["batch"])
        assert "batch" not in data
        assert data == crypto_specimen.to_dict()

    def test_wrong_secret_fails(self, full_specimen: Specimen) -> None:
        data = encrypt_specimen_fields(full_specimen, PASSPHRASE, ["batch"])
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(data, "wrong")
        assert exc_info.value.code == "AUTHENTICATION_FAILED"

    @pytest.mark.parametrize(
        ("change", "code"),
        [
            ({"algorithm": "AES-128-CBC"}, "UNSUPPORTED_ALGORITHM"),
            ({"kdf": None}, "MISSING_PARAMETER"),
            ({"iterations": 5000}, "INSUFFICIENT_ITERATIONS"),
            ({"iterations": True}, "INVALID_PARAMETER"),
            ({"salt": None}, "MISSING_PARAMETER"),
        ],
    )
    def test_invalid_field_object(
        self, full_specimen: Specimen, change: dict[str, object], code: str
    ) -> None:
        data = encrypt_specimen_fields(full_specimen, PASSPHRASE, ["batch"])
        obj = dict(data["batch"])
        for key, value in change.items():
            if value is None:
                obj.pop(key)
            else:
                obj[key] = value
        data["batch"] = obj
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(data, PASSPHRASE)
        assert exc_info.value.code == code

    def test_legacy_field_strings(
        self, full_specimen: Specimen, raw_key: bytes
    ) -> None:
        data = full_specimen.to_dict()
        data["batch"] = "encrypted:" + _legacy_blob(b'"BATCH-001"', raw_key)
        # Without the option the legacy string is left as-is.
        assert decrypt_specimen_fields(data, raw_key)["batch"] == data["batch"]
        restored = decrypt_specimen_fields(data, raw_key, allow_legacy=True)
        assert restored["batch"] == "BATCH-001"
