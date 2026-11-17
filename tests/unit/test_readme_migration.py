"""Run the README "Migrating from 1.2" examples against real wols 1.2.0 output.

The legacy fixtures below were produced by ``wols[crypto]==1.2.0`` from PyPI
with the key ``bytes(range(32))`` (passed as its base64 string, the 1.2
convention).
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import pytest

from wols import WolsEncryptionError, WolsWarning, create_specimen
from wols.crypto import RawKey, decrypt_specimen, decrypt_specimen_fields

README = Path(__file__).resolve().parents[2] / "README.md"

KEY_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="

# encrypt_specimen(specimen, KEY_B64) from wols 1.2.0.
V12_PAYLOAD = (
    "tK2l92iurAdtt7UyITt7/IR/phSDQ+DJsQdjA3CPDurI7XIvIXvkYuYBjwFZOD7AP6seEaBu5Z"
    "jy1znnAx6GRs/yMKgWCTnRyj6bozBaqK4MeQ+XmSbuvmuoiszpDOXP091UoklMl2ivYhT1IRAZ"
    "9694fX9jLUjcJAn8k0BqYSuXUU8Ubcl+XtZLMNJKfAtgAMOcaz1kHddxJvRP7JUV5W/qV2D+wV"
    "hfC05DyF2Vt4BKPa2xsQz+Lscg0A0h+tQ4GAcbl49eTTHrsXZIZ36CAbD+YWAdfOfvDbbPpMec"
    "bV8sahBBmQ8cjDRTM3r6FugJ1qeYFfIiuIlp5/cxxgkW5Z+9jdZZxGXbNfVCPbzfK/zyHE/ucc"
    "PuqpP/v2lfzzFeHy8n0ARQNAXSkRAJBHQ9"
)
V12_SPECIMEN: dict[str, Any] = {
    "@context": "https://wemush.com/wols/v1",
    "@type": "Specimen",
    "id": "wemush:u9v42l9b7tgxz1rpx0pucux0",
    "version": "1.2.0",
    "type": "CULTURE",
    "species": "Pleurotus ostreatus",
    "strain": {"name": "Blue Oyster"},
    "created": "2026-11-16T05:35:14.097642+00:00",
    "batch": "B-1",
}
# to_json(encrypt_specimen_fields(specimen, KEY_B64, ["batch", "strain"]))
# from wols 1.2.0, which dropped the encrypted strain.
V12_FIELDS: dict[str, Any] = {
    **{k: v for k, v in V12_SPECIMEN.items() if k not in ("strain", "batch")},
    "batch": "encrypted:V32jTPTlMQxI0U6dhK2T4fC/a19ozMuSQodfc+VsMxjK",
}


def _migration_blocks() -> list[str]:
    text = README.read_text(encoding="utf-8")
    match = re.search(r"^## Migrating from 1\.2\n(.*?)^## ", text, re.M | re.S)
    assert match, "README has no 'Migrating from 1.2' section"
    blocks = re.findall(r"^```python\n(.*?)^```", match.group(1), re.M | re.S)
    assert len(blocks) == 3
    return blocks


@pytest.fixture(scope="module")
def ns() -> dict[str, Any]:
    """Execute every README migration example in one namespace."""
    namespace: dict[str, Any] = {
        "specimen": create_specimen(type="CULTURE", species="Pleurotus ostreatus")
    }
    for block in _migration_blocks():
        exec(compile(block, str(README), "exec"), namespace)
    return namespace


def test_readme_key_is_the_fixture_key(ns: dict[str, Any]) -> None:
    assert ns["key_b64"] == KEY_B64
    assert base64.b64decode(KEY_B64) == bytes(range(32))
    assert "kdf=raw" in ns["url"]


def test_legacy_needs_allow_legacy() -> None:
    with pytest.raises(WolsEncryptionError) as exc_info:
        decrypt_specimen(V12_PAYLOAD, RawKey(KEY_B64))
    assert exc_info.value.code == "LEGACY_FORMAT"


def test_legacy_str_key_is_base64_on_legacy_path() -> None:
    old = decrypt_specimen(V12_PAYLOAD, KEY_B64, allow_legacy=True)
    assert old.to_dict()["batch"] == "B-1"


def test_is_legacy_label(ns: dict[str, Any]) -> None:
    assert ns["is_legacy_label"](V12_PAYLOAD)
    assert not ns["is_legacy_label"](ns["url"])


def test_upgrade_label(ns: dict[str, Any]) -> None:
    url = ns["upgrade_label"](V12_PAYLOAD, KEY_B64)
    assert url.startswith(f"wemush://v1/encrypted/{V12_SPECIMEN['id'][7:]}?")
    assert "kdf=raw" in url
    assert not ns["is_legacy_label"](url)
    restored = decrypt_specimen(url, base64.b64decode(KEY_B64))
    assert restored == decrypt_specimen(V12_PAYLOAD, KEY_B64, allow_legacy=True)
    assert restored.to_dict()["strain"] == {"name": "Blue Oyster"}


def test_upgrade_fields(ns: dict[str, Any]) -> None:
    upgraded = ns["upgrade_fields"](json.loads(json.dumps(V12_FIELDS)), KEY_B64)
    assert upgraded["batch"]["encrypted"] is True
    assert upgraded["batch"]["kdf"] == "raw"
    restored = decrypt_specimen_fields(upgraded, RawKey(KEY_B64))
    assert restored["batch"] == "B-1"
    assert restored["id"] == V12_SPECIMEN["id"]


def test_upgraded_fields_are_bound(ns: dict[str, Any]) -> None:
    """After re-encryption a field copied to another label no longer decrypts."""
    upgraded = ns["upgrade_fields"](dict(V12_FIELDS), KEY_B64)
    moved = {**upgraded, "id": "wemush:other"}
    with pytest.raises(WolsEncryptionError) as exc_info:
        decrypt_specimen_fields(moved, RawKey(KEY_B64))
    assert exc_info.value.code == "AUTHENTICATION_FAILED"
    # The legacy field had no such binding.
    legacy_moved = {**V12_FIELDS, "id": "wemush:other"}
    assert (
        decrypt_specimen_fields(legacy_moved, KEY_B64, allow_legacy=True)["batch"]
        == "B-1"
    )


def test_old_key_string_is_a_passphrase(ns: dict[str, Any]) -> None:
    """The README's warning: the bare 1.2 key string now means kdf=pbkdf2."""
    from wols.crypto import encrypt_specimen

    with pytest.warns(WolsWarning):
        url = encrypt_specimen(ns["specimen"], KEY_B64, iterations=100_000)
    assert "kdf=pbkdf2" in url


def test_typescript_legacy_url_rejected_even_with_allow_legacy() -> None:
    """A URL without kdf (the @wemush/wols 1.2 shape) is not this library's."""
    url = "wemush://v1/encrypted/abc?e=AAAAAAAAAAAAAAAAAAAAAA&iv=AAAAAAAAAAAAAAAA"
    with pytest.raises(WolsEncryptionError) as exc_info:
        decrypt_specimen(url, RawKey(KEY_B64), allow_legacy=True)
    assert exc_info.value.code == "LEGACY_FORMAT"
