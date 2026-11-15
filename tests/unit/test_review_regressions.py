"""Regression tests for defects found in the WOLS 1.3.0 review."""

from __future__ import annotations

import base64
import json
import os
import warnings

import pytest

from wols import (
    IdValidationMode,
    Strain,
    WolsEncryptionError,
    WolsParseError,
    WolsWarning,
    create_specimen,
    parse_specimen,
    validate_specimen_id,
)
from wols.crypto import (
    b64url_decode,
    b64url_encode,
    decrypt_specimen,
    decrypt_specimen_fields,
    encrypt_specimen,
    encrypt_specimen_fields,
    parse_encrypted_url,
)
from wols.crypto.wire import MAX_DECODE_ITERATIONS

BASE = {"id": "wemush:a", "type": "CULTURE", "species": "x"}


class TestParseNeverLeaksBuiltinErrors:
    """Untrusted JSON surfaces only as WolsParseError."""

    @pytest.mark.parametrize(
        "extra",
        [
            {"strain": 5},
            {"strain": []},
            {"strain": {"generation": "F1"}},
            {"strain": {"name": 5}},
            {"strain": {"name": "a", "clonalGeneration": "3"}},
            {"strain": {"name": "a", "generation": -1}},
            {"created": 5},
            {"created": "not a date"},
            {"stage": "PINNING"},
        ],
    )
    def test_bad_field_types(self, extra: dict[str, object]) -> None:
        with pytest.raises(WolsParseError):
            parse_specimen(json.dumps({**BASE, **extra}))


class TestStrainCounters:
    @pytest.mark.parametrize("value", [-1, True, "3", 1.5])
    def test_clonal_generation_validated(self, value: object) -> None:
        with pytest.raises(ValueError, match="clonalGeneration"):
            Strain(name="a", clonal_generation=value)  # type: ignore[arg-type]

    @pytest.mark.parametrize("value", [-1, True, 1.5, ["F1"]])
    def test_generation_validated(self, value: object) -> None:
        with pytest.raises(ValueError, match="generation"):
            Strain(name="a", generation=value)  # type: ignore[arg-type]

    def test_valid_counters_accepted(self) -> None:
        Strain(name="a", generation="F1", clonal_generation=0, transfer_depth=0)
        Strain(name="a", generation=2)


class TestAnchoredPatterns:
    """'$' must not let a trailing newline through."""

    @pytest.mark.parametrize(
        ("specimen_id", "mode"),
        [
            ("wemush:abcdefghijklmnopqrstuvwx\n", IdValidationMode.CUID),
            ("wemush:abc123\n", IdValidationMode.STRICT),
            ("wemush:01ARZ3NDEKTSV4RRFFQ69G5FAV\n", IdValidationMode.ULID),
            ("wemush:550e8400-e29b-41d4-a716-446655440000\n", IdValidationMode.UUID),
        ],
    )
    def test_trailing_newline_rejected(
        self, specimen_id: str, mode: IdValidationMode
    ) -> None:
        assert validate_specimen_id(specimen_id, mode) is False
        assert validate_specimen_id(specimen_id.rstrip("\n"), mode) is True

    def test_b64url_trailing_newline_rejected(self) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            b64url_decode("AAAA\n")
        assert exc_info.value.code == "INVALID_PARAMETER"


class TestIterationBounds:
    @pytest.fixture
    def url(self) -> str:
        return encrypt_specimen(
            create_specimen(type="CULTURE", species="x"), "pw", iterations=100_000
        )

    @pytest.mark.parametrize("digits", [9, 4301, 10_000])
    def test_huge_iteration_string(self, url: str, digits: int) -> None:
        bad = url.split("&i=")[0] + "&i=" + "9" * digits
        with pytest.raises(WolsEncryptionError) as exc_info:
            parse_encrypted_url(bad)
        assert exc_info.value.code == "EXCESSIVE_ITERATIONS"

    def test_leading_zeros_allowed(self, url: str) -> None:
        padded = url.replace("&i=100000", "&i=000100000")
        assert parse_encrypted_url(padded).payload.iterations == 100_000

    def test_max_accepted(self, url: str) -> None:
        at_max = url.replace("&i=100000", f"&i={MAX_DECODE_ITERATIONS}")
        assert parse_encrypted_url(at_max).payload.iterations == MAX_DECODE_ITERATIONS


class TestFieldDecryptBounds:
    """An untrusted label cannot force unbounded PBKDF2 work."""

    @staticmethod
    def _field(salt: bytes, iterations: int) -> dict[str, object]:
        return {
            "encrypted": True,
            "algorithm": "AES-256-GCM",
            "payload": b64url_encode(b"\x00" * 32),
            "iv": b64url_encode(b"\x00" * 12),
            "kdf": "pbkdf2",
            "salt": b64url_encode(salt),
            "iterations": iterations,
        }

    def test_total_iteration_budget(self) -> None:
        data = {
            **BASE,
            "batch": self._field(os.urandom(16), MAX_DECODE_ITERATIONS),
            "creator": self._field(os.urandom(16), 10_000),
        }
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(data, "pw")
        assert exc_info.value.code == "EXCESSIVE_ITERATIONS"

    def test_many_salts_rejected_before_any_derivation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import wols.crypto._aead as aead

        calls: list[int] = []
        monkeypatch.setattr(
            aead, "derive_key", lambda *a: calls.append(1) or b"\x00" * 32
        )
        fields = {f"f{i}": self._field(os.urandom(16), 2_000_000) for i in range(50)}
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields({**BASE, **fields}, "pw")
        assert exc_info.value.code == "EXCESSIVE_ITERATIONS"
        assert calls == []

    def test_shared_salt_counts_once(self) -> None:
        salt = os.urandom(16)
        fields = {f"f{i}": self._field(salt, MAX_DECODE_ITERATIONS) for i in range(6)}
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields({**BASE, **fields}, "pw")
        # One derivation within budget; the dummy ciphertext then fails auth.
        assert exc_info.value.code == "AUTHENTICATION_FAILED"

    def test_legitimate_label_within_budget(self) -> None:
        spec = create_specimen(
            type="CULTURE", species="x", batch="B", creator="c", organization="o"
        )
        data = encrypt_specimen_fields(spec, "pw", ["batch", "creator", "organization"])
        assert decrypt_specimen_fields(data, "pw")["batch"] == "B"

    @pytest.mark.parametrize("field", ["id", "type", "species", "@context"])
    def test_identifying_field_rejected(self, field: str) -> None:
        data = {**BASE, field: self._field(os.urandom(16), 100_000)}
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(data, "pw")
        assert exc_info.value.code == "IDENTIFYING_FIELD"


class TestBase64KeyStringWarning:
    """A 1.2-style base64 key passed as str warns (it is now a passphrase)."""

    @pytest.mark.parametrize(
        "encode", [base64.b64encode, base64.urlsafe_b64encode, b64url_encode]
    )
    def test_warns(self, encode: object) -> None:
        key = os.urandom(32)
        encoded = encode(key)  # type: ignore[operator]
        key_str = encoded if isinstance(encoded, str) else encoded.decode()
        spec = create_specimen(type="CULTURE", species="x")
        with pytest.warns(WolsWarning, match=r"base64\.b64decode"):
            encrypt_specimen(spec, key_str)

    def test_recommended_migration_round_trips(self) -> None:
        key_str = base64.b64encode(os.urandom(32)).decode()
        spec = create_specimen(type="CULTURE", species="x")
        url = encrypt_specimen(spec, base64.b64decode(key_str))
        assert "kdf=raw" in url
        assert decrypt_specimen(url, base64.b64decode(key_str)) == spec

    @pytest.mark.parametrize(
        "passphrase", ["correct horse battery staple", "x" * 44, "short"]
    )
    def test_ordinary_passphrase_no_warning(self, passphrase: str) -> None:
        spec = create_specimen(type="CULTURE", species="x")
        with warnings.catch_warnings():
            warnings.simplefilter("error", WolsWarning)
            encrypt_specimen(spec, passphrase)


class TestLegacyRouting:
    def test_url_typo_reported_as_url_error(self) -> None:
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen("wemush:v1/encrypted", b"0" * 32, allow_legacy=True)
        assert exc_info.value.code == "INVALID_URL"
