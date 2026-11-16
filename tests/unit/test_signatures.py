"""WOLS 1.4.0 signatures: behavior the conformance vectors don't pin down.

The vectors in ``tests/conformance`` check signing output and every
verification status. These tests cover the Python-specific parts: how
:mod:`json` parsing is made to match I-JSON, the check order around
duplicate names, input types, trust store handling, signing refusals, and
round trips through encryption.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

import pytest

pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from wols import (
    Specimen,
    SpecimenType,
    WolsSignatureError,
    create_specimen,
    to_json,
    validate_specimen,
)
from wols.crypto import (
    SignatureStatus,
    TrustedKey,
    TrustStore,
    VerificationResult,
    b64url_encode,
    decrypt_specimen,
    decrypt_specimen_bytes,
    encrypt_specimen,
    parse_encrypted_url,
    sign_encrypted_url,
    sign_specimen,
    trust_store_from_key_set,
    verify_embedded,
    verify_encrypted_url,
    verify_specimen,
)
from wols.crypto.jcs import CanonicalizationError, canonicalize, parse_json
from wols.crypto.signature import _ED25519_L

SEED = hashlib.sha256(b"wols unit test key").digest()
OTHER_SEED = hashlib.sha256(b"wols unit test other key").digest()
KID = "unit-2026"


def _public(seed: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()


STORE: TrustStore = {KID: TrustedKey(_public(SEED))}

LABEL = {
    "@context": "https://wemush.com/wols/v1",
    "@type": "Specimen",
    "id": "wemush:clx1a2b3c4",
    "version": "1.4.0",
    "type": "SUBSTRATE",
    "species": "Pleurotus ostreatus",
}
LABEL_TEXT = json.dumps(LABEL)
DUMMY_TOKEN = f"{KID}.{'A' * 86}"


def _status(label: object, store: TrustStore = STORE) -> SignatureStatus:
    return verify_specimen(label, store).status  # type: ignore[arg-type]


class TestJcs:
    def test_numbers_follow_ecmascript(self) -> None:
        values = [1.0, -0.0, 1e21, 1e20, 1e-7, 1e-6, 5e-324, 123456789012345680000.0]
        assert canonicalize(values) == (
            "[1,0,1e+21,100000000000000000000,1e-7,0.000001,5e-324,"
            "123456789012345680000]"
        )

    def test_integers_become_doubles(self) -> None:
        assert canonicalize(9007199254740993) == "9007199254740992"
        assert canonicalize(-(2**60)) == "-1152921504606847000"  # as in JS

    @pytest.mark.parametrize(
        "value", [float("nan"), float("inf"), -float("inf"), 10**400]
    )
    def test_non_finite_numbers_rejected(self, value: object) -> None:
        with pytest.raises(CanonicalizationError):
            canonicalize(value)

    def test_member_names_sorted_by_utf16(self) -> None:
        assert canonicalize({"ﬁ": 1, "\U0001f344": 2}) == '{"\U0001f344":2,"ﬁ":1}'

    def test_lone_surrogate_in_name_or_value(self) -> None:
        with pytest.raises(CanonicalizationError):
            canonicalize({"\ud800": 1})
        with pytest.raises(CanonicalizationError):
            canonicalize(["\udfff"])

    @pytest.mark.parametrize("value", [(1, 2), {1: "a"}, b"x", object()])
    def test_non_json_values_rejected(self, value: object) -> None:
        with pytest.raises(CanonicalizationError):
            canonicalize(value)

    def test_string_escapes(self) -> None:
        assert canonicalize('"\\/\b\f\n\r\t\x01\x7f\u2028') == (
            '"\\"\\\\/\\b\\f\\n\\r\\t\\u0001\x7f\u2028"'
        )

    def test_parse_reports_duplicates_and_huge_integers(self) -> None:
        assert parse_json('{"a":1,"b":{"c":1,"c":2}}').duplicate_names is True
        assert parse_json('{"a":1,"b":{"a":2}}').duplicate_names is False
        huge = parse_json("1" + "0" * 5000).value
        assert huge == float("inf")


class TestVerifyEmbedded:
    def test_round_trip(self) -> None:
        signed = sign_specimen(LABEL_TEXT, SEED, KID)
        result = verify_specimen(signed, STORE)
        assert result == VerificationResult(SignatureStatus.VALID, kid=KID)
        assert result.valid

    def test_bytes_and_parsed_object(self) -> None:
        signed = sign_specimen(LABEL_TEXT, SEED, KID)
        assert _status(signed.encode("utf-8")) is SignatureStatus.VALID
        assert _status(json.loads(signed)) is SignatureStatus.VALID
        assert verify_embedded(json.loads(signed), STORE).valid

    def test_whitespace_and_member_order_ignored(self) -> None:
        signed = json.loads(sign_specimen(LABEL_TEXT, SEED, KID))
        reordered = json.dumps(dict(reversed(list(signed.items()))), indent=4)
        assert _status(reordered) is SignatureStatus.VALID

    def test_unknown_members_are_covered(self) -> None:
        label = {**LABEL, "x-vendor": {"a": [1, 2.5]}}
        signed = json.loads(sign_specimen(label, SEED, KID))
        assert _status(signed) is SignatureStatus.VALID
        signed["x-vendor"]["a"][1] = 2.75
        assert _status(signed) is SignatureStatus.INVALID

    def test_nested_signature_members_are_covered(self) -> None:
        label = {**LABEL, "custom": {"signature": "nested"}}
        signed = json.loads(sign_specimen(label, SEED, KID))
        signed["custom"]["signature"] = "changed"
        assert _status(signed) is SignatureStatus.INVALID

    def test_invalid_utf8_is_malformed(self) -> None:
        assert _status(b'{"signature":"\xff"}') is SignatureStatus.MALFORMED

    @pytest.mark.parametrize(
        "text", ["", "not json", '{"a":', "[" * 100_000 + "]" * 100_000]
    )
    def test_unparseable_text_is_malformed(self, text: str) -> None:
        assert _status(text) is SignatureStatus.MALFORMED

    @pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e400"])
    def test_non_finite_number_is_malformed(self, value: str) -> None:
        text = f'{{"n":{value},"signature":"{DUMMY_TOKEN}"}}'
        assert _status(text) is SignatureStatus.MALFORMED

    def test_duplicate_names_are_malformed_when_signed(self) -> None:
        signed = sign_specimen(LABEL_TEXT, SEED, KID)
        duplicated = signed[:-1] + ',"type":"CULTURE"}'
        result = verify_specimen(duplicated, STORE)
        assert result.status is SignatureStatus.MALFORMED
        assert result.reason == "label repeats a member name"

    def test_unsigned_is_checked_before_malformed_rules(self) -> None:
        # The check order is unsigned first, so an unsigned label with a
        # duplicate name, a lone surrogate, or NaN is unsigned.
        for text in ('{"a":1,"a":2}', '{"a":"\\ud800"}', '{"a":NaN}'):
            assert _status(text) is SignatureStatus.UNSIGNED

    def test_non_object_is_malformed(self) -> None:
        assert _status("[]") is SignatureStatus.MALFORMED
        assert _status("null") is SignatureStatus.MALFORMED
        assert _status([]) is SignatureStatus.MALFORMED

    def test_specimen_model_is_rejected(self) -> None:
        specimen = create_specimen(type=SpecimenType.CULTURE, species="P. ostreatus")
        with pytest.raises(TypeError):
            verify_specimen(specimen, STORE)  # type: ignore[arg-type]

    def test_never_raises_for_odd_trust_stores(self) -> None:
        signed = sign_specimen(LABEL_TEXT, SEED, KID)
        bad_stores: list[object] = [
            {},
            {KID: _public(SEED)},  # bare bytes, not a TrustedKey
            {KID: TrustedKey(_public(SEED), alg="EdDSA")},
            {KID: TrustedKey(b"short")},
            None,
        ]
        for store in bad_stores:
            result = verify_specimen(signed, store)  # type: ignore[arg-type]
            assert result.status is SignatureStatus.UNKNOWN_KID
            assert result.kid == KID

    def test_kid_maps_to_a_different_key(self) -> None:
        store = {KID: TrustedKey(_public(OTHER_SEED))}
        signed = sign_specimen(LABEL_TEXT, SEED, KID)
        result = verify_specimen(signed, store)
        assert result.status is SignatureStatus.INVALID
        assert result.kid == KID

    def test_s_at_or_above_l_is_invalid(self) -> None:
        signed = json.loads(sign_specimen(LABEL_TEXT, SEED, KID))
        kid, sig = signed["signature"].split(".")
        raw = bytearray(base64.urlsafe_b64decode(sig + "=="))
        s = int.from_bytes(raw[32:], "little") + _ED25519_L
        raw[32:] = s.to_bytes(32, "little")
        signed["signature"] = f"{kid}.{b64url_encode(bytes(raw))}"
        result = verify_specimen(signed, STORE)
        assert result.status is SignatureStatus.INVALID
        assert result.reason is not None and "group order" in result.reason


class TestSignEmbedded:
    def test_preserves_member_order_and_values(self) -> None:
        text = '{"z":1,"a":[1.5,true,null],"signature":"old","m":"ü"}'
        signed = sign_specimen(text, SEED, KID)
        assert list(json.loads(signed)) == ["z", "a", "m", "signature"]
        assert signed.startswith('{"z":1,"a":[1.5,true,null],"m":"ü",')

    def test_re_signing_replaces_signature(self) -> None:
        once = sign_specimen(LABEL_TEXT, SEED, KID)
        twice = sign_specimen(once, SEED, KID)
        assert once == twice

    def test_specimen_model_is_signed_as_serialized(self) -> None:
        specimen = create_specimen(type=SpecimenType.CULTURE, species="P. ostreatus")
        signed = sign_specimen(specimen, SEED, KID)
        assert _status(signed) is SignatureStatus.VALID
        unsigned = json.loads(signed)
        del unsigned["signature"]
        assert unsigned == json.loads(to_json(specimen))

    def test_accepts_private_key_object(self) -> None:
        key = Ed25519PrivateKey.from_private_bytes(SEED)
        assert sign_specimen(LABEL_TEXT, key, KID) == sign_specimen(
            LABEL_TEXT, SEED, KID
        )

    @pytest.mark.parametrize(
        "label",
        [
            "[]",
            "not json",
            '{"a":1,"a":2}',
            '{"a":"\\ud800"}',
            '{"a":NaN}',
            {"a": (1, 2)},
            {"a": float("inf")},
            b"\xff",
        ],
    )
    def test_refuses_labels_it_cannot_sign(self, label: object) -> None:
        with pytest.raises(WolsSignatureError) as exc_info:
            sign_specimen(label, SEED, KID)  # type: ignore[arg-type]
        assert exc_info.value.code == "INVALID_LABEL"

    @pytest.mark.parametrize("kid", ["", "a.b", "a b", "k" * 65, "é", "kid\n"])
    def test_refuses_bad_kids(self, kid: str) -> None:
        with pytest.raises(WolsSignatureError) as exc_info:
            sign_specimen(LABEL_TEXT, SEED, kid)
        assert exc_info.value.code == "INVALID_KID"

    @pytest.mark.parametrize("key", [b"", SEED[:31], SEED + b"\0", "seed"])
    def test_refuses_bad_keys(self, key: object) -> None:
        with pytest.raises(WolsSignatureError) as exc_info:
            sign_specimen(LABEL_TEXT, key, KID)  # type: ignore[arg-type]
        assert exc_info.value.code == "INVALID_KEY"


class TestEncryptedUrl:
    def test_encrypt_sign_verify_decrypt(self) -> None:
        specimen = create_specimen(type=SpecimenType.CULTURE, species="P. ostreatus")
        key = os.urandom(32)
        url = encrypt_specimen(specimen, key)
        signed = sign_encrypted_url(url, SEED, KID)
        assert signed.startswith(url + "&sig=")
        assert verify_encrypted_url(signed, STORE).valid
        assert verify_specimen(signed, STORE).valid
        # Decoding ignores the signature and keeps it unchanged.
        assert decrypt_specimen(signed, key) == specimen
        label = parse_encrypted_url(signed)
        assert label.signature == signed.rsplit("&sig=", 1)[1]
        assert label.to_url() == signed

    def test_sign_then_encrypt_carries_both_signatures(self) -> None:
        specimen = create_specimen(type=SpecimenType.CULTURE, species="P. ostreatus")
        signed_label = sign_specimen(specimen, SEED, KID)
        key = os.urandom(32)
        inner = Specimen.from_dict(json.loads(signed_label))
        url = sign_encrypted_url(encrypt_specimen(inner, key), SEED, KID)
        assert verify_specimen(url, STORE).valid
        plaintext = decrypt_specimen_bytes(url, key)
        assert verify_specimen(plaintext, STORE).valid

    def test_web_scheme_is_malformed(self) -> None:
        signed = sign_encrypted_url("wemush://v1/encrypted/x?e=a", SEED, KID)
        web = "web+" + signed
        assert _status(web) is SignatureStatus.MALFORMED

    def test_sig_without_value_is_malformed(self) -> None:
        assert _status("wemush://v1/encrypted/x?e=a&sig") is SignatureStatus.MALFORMED

    def test_sig_as_only_parameter_is_malformed(self) -> None:
        url = f"wemush://v1/encrypted/x?sig={DUMMY_TOKEN}"
        assert _status(url) is SignatureStatus.MALFORMED

    def test_url_without_query_is_unsigned(self) -> None:
        assert _status("wemush://v1/encrypted/x") is SignatureStatus.UNSIGNED

    @pytest.mark.parametrize(
        ("url", "code"),
        [
            (f"wemush://v1/encrypted/x?e=a&sig={DUMMY_TOKEN}", "ALREADY_SIGNED"),
            ("wemush://v1/encrypted/x?e=a#frag", "INVALID_URL"),
            ("wemush://v1/encrypted/x y?e=a", "INVALID_URL"),
            ("wemush://v1/encrypted/ü?e=a", "INVALID_URL"),
            ("web+wemush://v1/encrypted/x?e=a", "INVALID_URL"),
            ("wemush://v1/encrypted/x", "INVALID_URL"),
        ],
    )
    def test_refuses_urls_it_cannot_sign(self, url: str, code: str) -> None:
        with pytest.raises(WolsSignatureError) as exc_info:
            sign_encrypted_url(url, SEED, KID)
        assert exc_info.value.code == code


class TestKeySet:
    def test_builds_trust_store(self) -> None:
        public = b64url_encode(_public(SEED))
        doc = {
            "keys": [
                {"kid": KID, "alg": "Ed25519", "publicKey": public},
                {"kid": "future", "alg": "ML-DSA-44", "publicKey": "AAAA"},
            ]
        }
        store = trust_store_from_key_set(json.dumps(doc))
        assert store[KID] == TrustedKey(_public(SEED))
        signed = sign_specimen(LABEL_TEXT, SEED, KID)
        assert _status(signed, store) is SignatureStatus.VALID
        future = sign_specimen(LABEL_TEXT, SEED, "future")
        assert _status(future, store) is SignatureStatus.UNKNOWN_KID

    @pytest.mark.parametrize(
        "doc",
        [
            {},
            {"keys": {}},
            {"keys": ["x"]},
            {"keys": [{"kid": "a b", "alg": "Ed25519", "publicKey": "A" * 43}]},
            {"keys": [{"kid": "a", "alg": "Ed25519"}]},
            {"keys": [{"kid": "a", "alg": "Ed25519", "publicKey": "A" * 42}]},
            {"keys": [{"kid": "a", "alg": "Ed25519", "publicKey": "A" * 42 + "B"}]},
            {
                "keys": [
                    {"kid": "a", "alg": "Ed25519", "publicKey": "A" * 43},
                    {"kid": "a", "alg": "Ed25519", "publicKey": "A" * 43},
                ]
            },
        ],
    )
    def test_rejects_malformed_documents(self, doc: object) -> None:
        with pytest.raises(ValueError):
            trust_store_from_key_set(doc)  # type: ignore[arg-type]


class TestVersion:
    @pytest.mark.parametrize("version", ["1.3.0", "1.3.1", "1.4.0"])
    def test_supported_versions_validate_without_warning(self, version: str) -> None:
        result = validate_specimen({**LABEL, "version": version})
        assert result.valid
        assert not any(w.code == "INVALID_VERSION" for w in result.warnings)

    @pytest.mark.parametrize("version", ["1.2.0", "1.5.0", "2.0.0"])
    def test_other_versions_still_warn(self, version: str) -> None:
        result = validate_specimen({**LABEL, "version": version})
        assert result.valid
        assert any(w.code == "INVALID_VERSION" for w in result.warnings)
