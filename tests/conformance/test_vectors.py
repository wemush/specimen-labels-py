"""WOLS conformance vectors, run through the public API.

The vectors in ``vectors/`` are vendored from wemush/open-standard; see
``README.md`` in this directory for their source and how to refresh them.

``MUST`` cases must pass. A ``SHOULD`` case that fails is reported as
``xfail`` rather than failing the run.
"""

from __future__ import annotations

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
    b64url_decode,
    decrypt_specimen,
    decrypt_specimen_bytes,
    derive_key,
)
from wols.exceptions import WolsEncryptionError

VECTORS_DIR = Path(__file__).parent / "vectors"
VECTOR_FILES = ("embedded", "primordia", "generation", "encrypted")


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
        assert json.loads(plaintext) == expected["specimen"]
        assert decrypt_specimen(url, secret) == Specimen.from_dict(expected["specimen"])
    else:
        # The vector's reason is a suggested category; this library uses the
        # same names as error codes.
        expected_code = expected["reason"].upper().replace("-", "_")
        with pytest.raises(WolsEncryptionError) as exc_info:
            decrypt_specimen_bytes(url, secret)
        assert exc_info.value.code == expected_code
        with pytest.raises(WolsEncryptionError):
            decrypt_specimen(url, secret)


CHECKS: dict[str, Callable[[dict[str, Any]], None]] = {
    "validate": check_validate,
    "create": check_create,
    "derive": check_derive,
    "decrypt": check_decrypt,
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
        assert doc["wolsVersion"] == "1.3.0"
        assert doc["cases"]
