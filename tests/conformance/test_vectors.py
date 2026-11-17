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
from pathlib import Path
from typing import Any

import pytest

from wols import (
    Specimen,
    SpecimenType,
    WolsWarning,
    create_specimen,
    to_json,
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
    sign_encrypted_url,
    sign_specimen,
    trust_store_from_key_set,
    verify_embedded,
    verify_encrypted_url,
    verify_specimen,
)
from wols.crypto.jcs import canonicalize, parse_json
from wols.exceptions import (
    WolsEncryptionError,
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
)
# The signature scheme is WOLS 1.4.0; the other files target the 1.3.0 wire
# format, which 1.3.1 and 1.4.0 leave unchanged.
VECTOR_VERSIONS = {"signatures": "1.4.0"}

_SIGNATURES = json.loads((VECTORS_DIR / "signatures.json").read_text(encoding="utf-8"))


def _trust_store(entries: dict[str, dict[str, str]]) -> TrustStore:
    return {
        kid: TrustedKey(
            public_key=b64url_decode(entry["publicKeyBase64url"]), alg=entry["alg"]
        )
        for kid, entry in entries.items()
    }


TRUST_STORE = _trust_store(_SIGNATURES["trustStore"])
TEST_SEEDS = {
    name: b64url_decode(key["seedBase64url"])
    for name, key in _SIGNATURES["testKeys"].items()
}


def _load_cases() -> list[Any]:
    params = []
    for name in VECTOR_FILES:
        doc = json.loads((VECTORS_DIR / f"{name}.json").read_text(encoding="utf-8"))
        for case in doc["cases"]:
            params.append(
                pytest.param(
                    case,
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


def _signing_prefix(form: str, kid: str) -> str:
    return f"{_SIGNATURES['signingDomain']}\n{form}\n{kid}\n"


def _embedded_body(label_text: str) -> str:
    obj = parse_json(label_text).value
    return canonicalize({k: v for k, v in obj.items() if k != "signature"})


def check_sign(case: dict[str, Any]) -> None:
    inp = case["input"]
    expected = case["expected"]
    kid = inp["kid"]
    seed = TEST_SEEDS[inp["key"]]
    prefix = _signing_prefix(inp["form"], kid)

    if expected.get("refused"):
        with pytest.raises(WolsSignatureError):
            if inp["form"] == "embedded":
                sign_specimen(inp["label"], seed, kid)
            else:
                sign_encrypted_url(inp["url"], seed, kid)
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
        result = verify_specimen(signed, TRUST_STORE)
    else:
        assert prefix + inp["url"] == expected["signingInput"]
        signed = sign_encrypted_url(inp["url"], seed, kid)
        assert signed == expected["url"]
        assert signed == f"{inp['url']}&sig={expected['signature']}"
        result = verify_specimen(signed, TRUST_STORE)
    assert result.status is SignatureStatus.VALID
    assert result.kid == kid


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
    store = TRUST_STORE
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
        direct = verify_encrypted_url(label, store)
    result = verify_specimen(label, store)

    assert result.status == expected["status"], result
    assert direct == result
    if result.status is SignatureStatus.VALID:
        assert result.kid == expected["kid"]
        prefix = _signing_prefix(inp["form"], expected["kid"])
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
        doc = json.loads((VECTORS_DIR / f"{name}.json").read_text(encoding="utf-8"))
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
