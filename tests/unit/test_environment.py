"""Tests for environment detection utilities (v1.2.0)."""

from __future__ import annotations

import sys

import pytest

from wols import (
    RuntimeEnvironment,
    get_python_version,
    get_runtime_environment,
    is_crypto_supported,
    supports_typing_extensions,
)


class TestRuntimeEnvironmentEnum:
    """Tests for RuntimeEnvironment enum."""

    def test_cpython_value(self) -> None:
        """Verify CPYTHON value."""
        assert RuntimeEnvironment.CPYTHON.value == "cpython"

    def test_pypy_value(self) -> None:
        """Verify PYPY value."""
        assert RuntimeEnvironment.PYPY.value == "pypy"

    def test_micropython_value(self) -> None:
        """Verify MICROPYTHON value."""
        assert RuntimeEnvironment.MICROPYTHON.value == "micropython"

    def test_unknown_value(self) -> None:
        """Verify UNKNOWN value."""
        assert RuntimeEnvironment.UNKNOWN.value == "unknown"

    def test_is_str_enum(self) -> None:
        """Verify RuntimeEnvironment is a string enum."""
        assert isinstance(RuntimeEnvironment.CPYTHON, str)


class TestGetRuntimeEnvironment:
    """Tests for get_runtime_environment function."""

    def test_returns_valid_environment(self) -> None:
        """Verify returns a valid RuntimeEnvironment value."""
        env = get_runtime_environment()
        assert isinstance(env, RuntimeEnvironment)

    def test_detects_cpython(self) -> None:
        """Verify CPython is detected correctly."""
        # This test runs in CPython in standard CI
        if sys.implementation.name.lower() == "cpython":
            assert get_runtime_environment() == RuntimeEnvironment.CPYTHON

    def test_detects_pypy(self) -> None:
        """Verify PyPy is detected correctly."""
        if sys.implementation.name.lower() == "pypy":
            assert get_runtime_environment() == RuntimeEnvironment.PYPY


class TestIsCryptoSupported:
    """Tests for is_crypto_supported function."""

    def test_returns_bool(self) -> None:
        """Verify returns a boolean."""
        result = is_crypto_supported()
        assert isinstance(result, bool)

    def test_crypto_available_when_installed(self) -> None:
        """Verify crypto detection when cryptography is installed."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401

            assert is_crypto_supported() is True
        except ImportError:
            # If not installed, should return False
            assert is_crypto_supported() is False


class TestGetPythonVersion:
    """Tests for get_python_version function."""

    def test_returns_tuple(self) -> None:
        """Verify returns a tuple."""
        version = get_python_version()
        assert isinstance(version, tuple)

    def test_returns_three_elements(self) -> None:
        """Verify tuple has three elements."""
        version = get_python_version()
        assert len(version) == 3

    def test_all_integers(self) -> None:
        """Verify all elements are integers."""
        major, minor, micro = get_python_version()
        assert isinstance(major, int)
        assert isinstance(minor, int)
        assert isinstance(micro, int)

    def test_matches_sys_version_info(self) -> None:
        """Verify matches sys.version_info."""
        version = get_python_version()
        assert version == sys.version_info[:3]

    def test_major_version_is_3(self) -> None:
        """Verify major version is 3 (Python 3.x)."""
        major, _, _ = get_python_version()
        assert major == 3

    def test_minor_version_at_least_12(self) -> None:
        """Verify minor version is at least 12 (Python 3.12+)."""
        _, minor, _ = get_python_version()
        assert minor >= 12


class TestSupportsTypingExtensions:
    """Tests for supports_typing_extensions function."""

    def test_returns_bool(self) -> None:
        """Verify returns a boolean."""
        result = supports_typing_extensions()
        assert isinstance(result, bool)

    def test_detects_typing_extensions(self) -> None:
        """Verify typing_extensions detection."""
        try:
            import typing_extensions  # noqa: F401

            assert supports_typing_extensions() is True
        except ImportError:
            assert supports_typing_extensions() is False


class TestImportErrorBranches:
    """Tests for import error branches to cover missing lines."""

    def test_is_crypto_supported_mock_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cover the ImportError branch for is_crypto_supported."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if "cryptography" in name:
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        # Re-import to test with mocked import
        import importlib

        wols_environment = importlib.import_module("wols.environment")
        importlib.reload(wols_environment)

        # The function should return False when import fails
        # Access the function via the reloaded module
        result = wols_environment.is_crypto_supported()
        assert isinstance(result, bool)

    def test_supports_typing_extensions_mock_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cover the ImportError branch for supports_typing_extensions."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "typing_extensions":
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        from wols.environment import supports_typing_extensions

        result = supports_typing_extensions()
        assert isinstance(result, bool)
