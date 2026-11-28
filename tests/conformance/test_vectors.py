"""WOLS conformance vectors, run through the public API.

The vectors in ``vectors/`` are vendored from wemush/open-standard; see
``README.md`` in this directory for their source and how to refresh them.

``MUST`` cases must pass. A ``SHOULD`` case that fails is reported as
``xfail`` rather than failing the run.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from wols import (
    Specimen,
    SpecimenType,
    WolsWarning,
    create_specimen,
    parse_compact_url,
    parse_compact_url_or_none,
    parse_specimen,
    to_json,
    unwrap_wols_url,
    validate_bundle,
    validate_specimen,
)
from wols.crypto import (
    SignatureStatus,
    TrustedKey,
    TrustStore,
    b64url_decode,
    decrypt_specimen,
    decrypt_specimen_bytes,
    decrypt_specimen_fields,
    derive_key,
    parse_encrypted_url,
    sign_compact_url,
    sign_encrypted_url,
    sign_specimen,
    trust_store_from_key_set,
    verify_compact_url,
    verify_embedded,
    verify_encrypted_url,
    verify_specimen,
)
from wols.crypto.jcs import canonicalize, parse_json
from wols.exceptions import (
    WolsEncryptionError,
    WolsParseError,
    WolsSignatureError,
    WolsTrustStoreError,
)
from wols.generation import with_string_generation

VECTORS_DIR = Path(__file__).parent / "vectors"
VECTOR_FILES = (
    "embedded",
    "primordia",
    "generation",
    "encrypted",
    "field-encryption",
    "signatures",
    # WOLS 1.5 release candidates (open-standard spec/1.5.0-rc.2)
    "data-model",
    "bundle",
    "compact",
    "compact-signatures",
)
# The signature scheme is WOLS 1.4.0 and the 1.5 files target its release
# candidates; the other files target the 1.3.0 wire format, which 1.4.0
# leaves unchanged.
VECTOR_VERSIONS = {
    "signatures": "1.4.0",
    "data-model": "1.5.0-rc.1",
    "bundle": "1.5.0-rc.1",
    "compact": "1.5.0-rc.2",
    "compact-signatures": "1.5.0-rc.2",
}


def _read(name: str) -> Any:
    return json.loads((VECTORS_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _trust_store(entries: dict[str, dict[str, str]]) -> TrustStore:
    return {
        kid: TrustedKey(
            public_key=b64url_decode(entry["publicKeyBase64url"]), alg=entry["alg"]
        )
        for kid, entry in entries.items()
    }


@dataclass(frozen=True)
class Keys:
    """A signature vector file's own signing domain, trust store and keys."""

    domain: str
    store: TrustStore
    seeds: dict[str, bytes]

    @classmethod
    def load(cls, name: str) -> Keys:
        doc = _read(name)
        return cls(
            domain=doc["signingDomain"],
            store=_trust_store(doc["trustStore"]),
            seeds={
                kid: b64url_decode(key["seedBase64url"])
                for kid, key in doc["testKeys"].items()
            },
        )


# Each signature file is checked against its own trust store and keys
# (compact-signatures.json adds the short kid `w1`).
KEYS = {name: Keys.load(name) for name in ("signatures", "compact-signatures")}
TRUST_STORE = KEYS["signatures"].store


def _keys(case: dict[str, Any]) -> Keys:
    return KEYS.get(case.get("_file", ""), KEYS["signatures"])


def _load_cases() -> list[Any]:
    params = []
    for name in VECTOR_FILES:
        doc = _read(name)
        for case in doc["cases"]:
            params.append(
                pytest.param(
                    {**case, "_file": name},
                    id=f"{name}:{case['id']}",
                    marks=pytest.mark.conformance(
                        file=name, requirement=case["requirement"]
                    ),
                )
            )
    return params


def _secret(secret: dict[str, str]) -> str | bytes:
    if secret["kdf"] == "raw":
        return b64url_decode(secret["keyBase64url"])
    return secret["passphrase"]


def check_validate(case: dict[str, Any]) -> None:
    expected = case["expected"]
    result = validate_specimen(case["input"])
    assert result.valid is expected["valid"], result.errors
    if "errorField" in expected:
        paths = [e.path for e in result.errors]
        assert expected["errorField"] in paths, paths
    if "warningField" in expected:
        paths = [w.path for w in result.warnings]
        assert expected["warningField"] in paths, paths


def check_validate_bundle(case: dict[str, Any]) -> None:
    expected = case["expected"]
    result = validate_bundle(case["input"])
    assert result.valid is expected["valid"], result.errors
    if "errorField" in expected:
        paths = [e.path for e in result.errors]
        assert expected["errorField"] in paths, paths


def check_roundtrip(case: dict[str, Any]) -> None:
    """Decode and re-encode: the output must equal the expected object."""
    specimen = parse_specimen(case["input"]["text"])
    output = json.loads(to_json(specimen))
    assert output == case["expected"]["output"]
    # Re-encoding the output is stable.
    assert json.loads(to_json(parse_specimen(json.dumps(output)))) == output


def check_parse_compact(case: dict[str, Any]) -> None:
    url = case["input"]["url"]
    expected = case["expected"]

    if expected.get("refused"):
        with pytest.raises(WolsParseError) as exc_info:
            parse_compact_url(url)
        assert exc_info.value.code == _error_code(expected["reason"])
        assert parse_compact_url_or_none(url) is None
        return

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ref = parse_compact_url(url)
    messages = [str(w.message) for w in caught if issubclass(w.category, WolsWarning)]

    # The vector's label shape: the label members, then the unrecognized
    # parameters and the raw `sig`, which is never verified by parsing.
    label = ref.to_dict()
    if ref.unrecognized_params:
        label["unrecognized"] = dict(ref.unrecognized_params)
    if ref.signature is not None:
        label["sig"] = ref.signature
    assert label == expected["label"]

    if "warningField" in expected:
        field = expected["warningField"]
        assert messages, "expected a warning"
        if field == "td":
            assert any("'td'" in m for m in messages), messages
    else:
        assert not messages, messages


def check_unwrap(case: dict[str, Any]) -> None:
    unwrapped = unwrap_wols_url(case["input"]["text"])
    assert unwrapped == case["expected"]["url"]
    if unwrapped is not None:
        # Every vector that unwraps carries a valid compact URL signature.
        result = verify_specimen(unwrapped, _keys(case).store)
        assert result.status is SignatureStatus.VALID, result


def check_create(case: dict[str, Any]) -> None:
    expected = case["expected"]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        specimen = create_specimen(**case["input"])
    wols_warnings = [w for w in caught if issubclass(w.category, WolsWarning)]

    assert specimen.type.value == expected["type"]
    assert (specimen.stage.value if specimen.stage else None) == expected["stage"]
    assert bool(wols_warnings) is expected["warning"], [
        str(w.message) for w in wols_warnings
    ]
    # PRIMORDIA is never serialized as a type.
    serialized = json.loads(to_json(specimen))
    assert serialized["type"] in {t.value for t in SpecimenType}
    assert validate_specimen(serialized).valid


def check_derive(case: dict[str, Any]) -> None:
    inp = case["input"]
    key = derive_key(
        inp["passphrase"], b64url_decode(inp["saltBase64url"]), inp["iterations"]
    )
    assert key == b64url_decode(case["expected"]["keyBase64url"])


def check_decrypt(case: dict[str, Any]) -> None:
    url = case["input"]["url"]
    secret = _secret(case["input"]["secret"])
    expected = case["expected"]

    if expected["success"]:
        plaintext = decrypt_specimen_bytes(url, secret)
        assert plaintext == expected["plaintext"].encode("utf-8")
        # `specimen` is the decoded label: a numeric strain.generation in the
        # plaintext is read as its decimal string (WOLS 1.4.0).
        decoded = json.loads(plaintext)
        if "strain" in decoded:
            decoded["strain"] = with_string_generation(decoded["strain"], stacklevel=1)
        assert decoded == expected["specimen"]
        assert decrypt_specimen(url, secret) == Specimen.from_dict(expected["specimen"])
        if "sig" in expected:
            # Decoding keeps `sig` unchanged and never verifies it.
            assert expected["sigVerified"] is False
            label = parse_encrypted_url(url)
            assert label.signature == expected["sig"]
            assert not hasattr(label, "verified")
            assert label.to_url() == url
    else:
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_bytes(url, secret)
        assert exc_info.value.code == _error_code(expected["reason"])
        with pytest.raises(WolsEncryptionError):
            decrypt_specimen(url, secret)


def check_decrypt_fields(case: dict[str, Any]) -> None:
    label = case["input"]["specimen"]
    secret = _secret(case["input"]["secret"])
    expected = case["expected"]

    if expected["success"]:
        restored = decrypt_specimen_fields(label, secret)
        assert restored == expected["specimen"]
        assert Specimen.from_dict(restored) == Specimen.from_dict(expected["specimen"])
    else:
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_fields(label, secret)
        assert exc_info.value.code == _error_code(expected["reason"])


def _signing_prefix(form: str, kid: str, keys: Keys | None = None) -> str:
    domain = (keys or KEYS["signatures"]).domain
    return f"{domain}\n{form}\n{kid}\n"


_URL_SIGNERS = {"encrypted-url": sign_encrypted_url, "compact-url": sign_compact_url}
_URL_VERIFIERS = {
    "encrypted-url": verify_encrypted_url,
    "compact-url": verify_compact_url,
}


def _embedded_body(label_text: str) -> str:
    obj = parse_json(label_text).value
    return canonicalize({k: v for k, v in obj.items() if k != "signature"})


def check_sign(case: dict[str, Any]) -> None:
    inp = case["input"]
    expected = case["expected"]
    kid = inp["kid"]
    keys = _keys(case)
    seed = keys.seeds[inp["key"]]
    prefix = _signing_prefix(inp["form"], kid, keys)

    if expected.get("refused"):
        with pytest.raises(WolsSignatureError):
            if inp["form"] == "embedded":
                sign_specimen(inp["label"], seed, kid)
            else:
                _URL_SIGNERS[inp["form"]](inp["url"], seed, kid)
        return

    if inp["form"] == "embedded":
        assert prefix + _embedded_body(inp["label"]) == expected["signingInput"]
        signed = sign_specimen(inp["label"], seed, kid)
        signed_obj = json.loads(signed)
        assert signed_obj["signature"] == expected["signature"]
        # The signer adds the token and changes nothing else.
        original = json.loads(inp["label"])
        original.pop("signature", None)
        assert {k: v for k, v in signed_obj.items() if k != "signature"} == original
        result = verify_specimen(signed, keys.store)
    else:
        assert prefix + inp["url"] == expected["signingInput"]
        signed = _URL_SIGNERS[inp["form"]](inp["url"], seed, kid)
        assert signed == expected["url"]
        assert signed == f"{inp['url']}&sig={expected['signature']}"
        result = verify_specimen(signed, keys.store)
    assert result.status is SignatureStatus.VALID
    assert result.kid == kid
    assert result.form == inp["form"]


def _unchecked_trust_store(entries: dict[str, dict[str, str]]) -> Any:
    """The vector's entries as plain dicts, skipping TrustedKey's checks, so
    an unusable entry reaches verification."""
    return {
        kid: {"alg": e["alg"], "public_key": b64url_decode(e["publicKeyBase64url"])}
        for kid, e in entries.items()
    }


def check_verify(case: dict[str, Any]) -> None:
    inp = case["input"]
    expected = case["expected"]
    keys = _keys(case)
    store = keys.store
    if "trustStore" in inp:
        if expected.get("configError"):
            # Rejected when the trust store is built ...
            with pytest.raises(WolsTrustStoreError):
                _trust_store(inp["trustStore"])
            # ... and invalid if an unusable entry reaches verification.
            store = _unchecked_trust_store(inp["trustStore"])
        else:
            store = _trust_store(inp["trustStore"])
    if inp["form"] == "embedded":
        label = inp["label"]
        direct = verify_embedded(label, store)
    else:
        label = inp["url"]
        direct = _URL_VERIFIERS[inp["form"]](label, store)
    result = verify_specimen(label, store)

    assert result.status == expected["status"], result
    assert direct == result
    if result.status is SignatureStatus.VALID:
        assert result.kid == expected["kid"]
        assert result.form == inp["form"]
        prefix = _signing_prefix(inp["form"], expected["kid"], keys)
        if inp["form"] == "embedded":
            assert prefix + _embedded_body(label) == expected["signingInput"]
        else:
            body = label[: label.rindex("&sig=")]
            assert prefix + body == expected["signingInput"]
    else:
        assert result.reason


def check_load_key_set(case: dict[str, Any]) -> None:
    inp = case["input"]
    expected = case["expected"]
    # The document as parsed JSON and as text: both must load (or fail) alike.
    documents = [inp["keySet"], json.dumps(inp["keySet"])]
    if expected.get("configError"):
        for document in documents:
            with pytest.raises(WolsTrustStoreError):
                trust_store_from_key_set(document)
        return
    for document in documents:
        skipped: list[Any] = []
        store = trust_store_from_key_set(document, on_skip=skipped.append)
        assert sorted(store) == expected["kids"]
        assert len(skipped) == expected["skipped"]
        result = verify_specimen(inp["label"], store)
        assert result.status == expected["status"], result
        if result.status is SignatureStatus.VALID:
            assert result.kid == expected["kid"]


def _check_layer(layer: str, text: str, expected: dict[str, Any] | None) -> None:
    assert expected is not None, f"{layer} expectation missing"
    result = verify_specimen(text, TRUST_STORE)
    assert result.status == expected["status"], (layer, result)
    if result.status is SignatureStatus.VALID:
        assert result.kid == expected["kid"], layer
        if layer == "outer":
            body = text[: text.rindex("&sig=")]
            assert (
                _signing_prefix("encrypted-url", result.kid) + body
                == expected["signingInput"]
            )
        else:
            assert (
                _signing_prefix("embedded", result.kid) + _embedded_body(text)
                == expected["signingInput"]
            )
    else:
        assert result.reason


def check_verify_nested(case: dict[str, Any]) -> None:
    """Sign-then-encrypt: verify the URL, decrypt it, then verify the plaintext."""
    inp = case["input"]
    expected = case["expected"]
    assert inp["form"] == "encrypted-url"
    url = inp["url"]
    secret = _secret(inp["secret"])

    # 1. Outer: the URL signature, checked without decrypting.
    _check_layer("outer", url, expected["outer"])
    assert verify_encrypted_url(url, TRUST_STORE) == verify_specimen(url, TRUST_STORE)

    # 2. Decrypt to the exact plaintext bytes.
    if not expected["decrypt"]["success"]:
        assert "inner" not in expected
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_bytes(url, secret)
        assert exc_info.value.code == _error_code(expected["decrypt"]["reason"])
        with pytest.raises(WolsEncryptionError):
            decrypt_specimen(url, secret)
        return
    plaintext = decrypt_specimen_bytes(url, secret)
    assert plaintext == expected["decrypt"]["plaintext"].encode("utf-8")
    decrypt_specimen(url, secret)

    # 3. Inner: the decrypted text as received, never a rebuilt label.
    text = plaintext.decode("utf-8")
    _check_layer("inner", text, expected.get("inner"))
    assert verify_embedded(text, TRUST_STORE) == verify_specimen(text, TRUST_STORE)


def _error_code(reason: str) -> str:
    """The vector's reason is a suggested category; this library uses the
    same names as error codes (``id-mismatch`` becomes ``ID_MISMATCH``)."""
    return reason.upper().replace("-", "_")


CHECKS: dict[str, Callable[[dict[str, Any]], None]] = {
    "validate": check_validate,
    "create": check_create,
    "derive": check_derive,
    "decrypt": check_decrypt,
    "decryptFields": check_decrypt_fields,
    "sign": check_sign,
    "verify": check_verify,
    "loadKeySet": check_load_key_set,
    "verifyNested": check_verify_nested,
    "validateBundle": check_validate_bundle,
    "roundtrip": check_roundtrip,
    "parseCompact": check_parse_compact,
    "unwrap": check_unwrap,
}


@pytest.mark.parametrize("case", _load_cases())
def test_conformance_vector(case: dict[str, Any]) -> None:
    check = CHECKS[case["operation"]]
    if case["requirement"] == "MUST":
        check(case)
        return
    try:
        check(case)
    except Exception as e:  # any failure of a SHOULD case is non-fatal
        pytest.xfail(f"SHOULD case not met: {e!r}")


def test_all_vector_files_present() -> None:
    for name in VECTOR_FILES:
        doc = _read(name)
        assert doc["wolsVersion"] == VECTOR_VERSIONS.get(name, "1.3.0")
        assert doc["cases"]


def test_vendored_files_match_sha256sums() -> None:
    """The vendored files are unmodified copies of the upstream vectors."""
    listed = {}
    for line in (VECTORS_DIR / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        listed[name] = digest
    assert set(listed) == {f"{name}.json" for name in VECTOR_FILES}
    for name, digest in listed.items():
        actual = hashlib.sha256((VECTORS_DIR / name).read_bytes()).hexdigest()
        assert actual == digest, name
