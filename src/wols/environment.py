"""Environment Detection Utilities for WOLS v1.2.0.

Detects runtime environment and crypto capabilities.
"""

from __future__ import annotations

import sys
from enum import Enum


class RuntimeEnvironment(str, Enum):
    """Runtime environment type."""

    CPYTHON = "cpython"
    """Standard CPython interpreter."""

    PYPY = "pypy"
    """PyPy interpreter."""

    MICROPYTHON = "micropython"
    """MicroPython interpreter."""

    UNKNOWN = "unknown"
    """Unknown interpreter."""


_RUNTIME_ENV_MAP: dict[str, RuntimeEnvironment] = {
    "cpython": RuntimeEnvironment.CPYTHON,
    "pypy": RuntimeEnvironment.PYPY,
    "micropython": RuntimeEnvironment.MICROPYTHON,
}


def get_runtime_environment() -> RuntimeEnvironment:
    """Get the current Python runtime environment.

    Returns:
        The detected runtime environment.

    Example:
        >>> get_runtime_environment()
        <RuntimeEnvironment.CPYTHON: 'cpython'>
    """
    impl = sys.implementation.name.lower()
    return _RUNTIME_ENV_MAP.get(impl, RuntimeEnvironment.UNKNOWN)


def is_crypto_supported() -> bool:
    """Check if cryptographic operations are supported.

    Returns:
        True if the cryptography package is available, False otherwise.

    Example:
        >>> is_crypto_supported()
        True  # If cryptography is installed
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401

        return True
    except ImportError:
        return False


def get_python_version() -> tuple[int, int, int]:
    """Get Python version as tuple.

    Returns:
        A tuple of (major, minor, micro) version numbers.

    Example:
        >>> get_python_version()
        (3, 12, 0)
    """
    return sys.version_info[:3]


def supports_typing_extensions() -> bool:
    """Check if typing_extensions is available.

    Returns:
        True if typing_extensions is available, False otherwise.

    Example:
        >>> supports_typing_extensions()
        True
    """
    try:
        import typing_extensions  # noqa: F401

        return True
    except ImportError:
        return False
