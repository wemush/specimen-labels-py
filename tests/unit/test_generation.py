"""Tests for generation format system (v1.2.0)."""

from __future__ import annotations

from wols import GenerationFormat, is_valid_generation, normalize_generation


class TestIsValidGeneration:
    """Tests for is_valid_generation function."""

    def test_filial_format_valid(self) -> None:
        """Verify F{n} format is valid."""
        assert is_valid_generation("F1") is True
        assert is_valid_generation("F2") is True
        assert is_valid_generation("F10") is True
        assert is_valid_generation("F100") is True

    def test_generation_format_valid(self) -> None:
        """Verify G{n} format is valid."""
        assert is_valid_generation("G1") is True
        assert is_valid_generation("G2") is True
        assert is_valid_generation("G10") is True

    def test_parental_format_valid(self) -> None:
        """Verify P and P1 formats are valid."""
        assert is_valid_generation("P") is True
        assert is_valid_generation("P1") is True

    def test_numeric_format_valid(self) -> None:
        """Verify plain numeric format is valid."""
        assert is_valid_generation("1") is True
        assert is_valid_generation("2") is True
        assert is_valid_generation("10") is True
        assert is_valid_generation("100") is True

    def test_case_insensitive(self) -> None:
        """Verify validation is case-insensitive."""
        assert is_valid_generation("f1") is True
        assert is_valid_generation("g2") is True
        assert is_valid_generation("p") is True

    def test_whitespace_handled(self) -> None:
        """Verify whitespace is trimmed."""
        assert is_valid_generation(" F1 ") is True
        assert is_valid_generation("  P  ") is True

    def test_invalid_formats(self) -> None:
        """Verify invalid formats return False."""
        assert is_valid_generation("invalid") is False
        assert is_valid_generation("F") is False
        assert is_valid_generation("G") is False
        assert is_valid_generation("X1") is False
        assert is_valid_generation("1F") is False
        assert is_valid_generation("") is False
        assert is_valid_generation("F-1") is False


class TestNormalizeGeneration:
    """Tests for normalize_generation function."""

    def test_preserve_format_unchanged(self) -> None:
        """Verify PRESERVE format returns original."""
        assert normalize_generation("F1", GenerationFormat.PRESERVE) == "F1"
        assert normalize_generation("G2", GenerationFormat.PRESERVE) == "G2"
        assert normalize_generation("P", GenerationFormat.PRESERVE) == "P"
        assert normalize_generation("5", GenerationFormat.PRESERVE) == "5"

    def test_filial_format_from_f(self) -> None:
        """Verify FILIAL format normalizes F{n}."""
        assert normalize_generation("F1", GenerationFormat.FILIAL) == "F1"
        assert normalize_generation("F10", GenerationFormat.FILIAL) == "F10"

    def test_filial_format_from_g(self) -> None:
        """Verify FILIAL format converts G{n} to F{n}."""
        assert normalize_generation("G1", GenerationFormat.FILIAL) == "F1"
        assert normalize_generation("G5", GenerationFormat.FILIAL) == "F5"

    def test_filial_format_from_numeric(self) -> None:
        """Verify FILIAL format converts numeric to F{n}."""
        assert normalize_generation("1", GenerationFormat.FILIAL) == "F1"
        assert normalize_generation("10", GenerationFormat.FILIAL) == "F10"

    def test_filial_format_from_parental(self) -> None:
        """Verify FILIAL format converts P to P."""
        assert normalize_generation("P", GenerationFormat.FILIAL) == "P"
        assert normalize_generation("P1", GenerationFormat.FILIAL) == "P"

    def test_numeric_format_from_f(self) -> None:
        """Verify NUMERIC format converts F{n} to n."""
        assert normalize_generation("F1", GenerationFormat.NUMERIC) == "1"
        assert normalize_generation("F10", GenerationFormat.NUMERIC) == "10"

    def test_numeric_format_from_g(self) -> None:
        """Verify NUMERIC format converts G{n} to n."""
        assert normalize_generation("G1", GenerationFormat.NUMERIC) == "1"
        assert normalize_generation("G5", GenerationFormat.NUMERIC) == "5"

    def test_numeric_format_from_numeric(self) -> None:
        """Verify NUMERIC format keeps numeric unchanged."""
        assert normalize_generation("1", GenerationFormat.NUMERIC) == "1"
        assert normalize_generation("10", GenerationFormat.NUMERIC) == "10"

    def test_numeric_format_from_parental(self) -> None:
        """Verify NUMERIC format converts P to 0."""
        assert normalize_generation("P", GenerationFormat.NUMERIC) == "0"
        assert normalize_generation("P1", GenerationFormat.NUMERIC) == "0"

    def test_case_insensitive(self) -> None:
        """Verify normalization is case-insensitive."""
        assert normalize_generation("f1", GenerationFormat.FILIAL) == "F1"
        assert normalize_generation("g2", GenerationFormat.FILIAL) == "F2"
        assert normalize_generation("p", GenerationFormat.NUMERIC) == "0"

    def test_invalid_returns_original(self) -> None:
        """Verify invalid formats return original string."""
        assert normalize_generation("invalid", GenerationFormat.FILIAL) == "invalid"
        assert normalize_generation("X1", GenerationFormat.NUMERIC) == "X1"

    def test_default_format_is_preserve(self) -> None:
        """Verify default format is PRESERVE."""
        assert normalize_generation("F1") == "F1"
        assert normalize_generation("G2") == "G2"


class TestGenerationFormatEnum:
    """Tests for GenerationFormat enum."""

    def test_preserve_value(self) -> None:
        """Verify PRESERVE value."""
        assert GenerationFormat.PRESERVE.value == "preserve"

    def test_filial_value(self) -> None:
        """Verify FILIAL value."""
        assert GenerationFormat.FILIAL.value == "filial"

    def test_numeric_value(self) -> None:
        """Verify NUMERIC value."""
        assert GenerationFormat.NUMERIC.value == "numeric"

    def test_is_str_enum(self) -> None:
        """Verify GenerationFormat is a string enum."""
        assert isinstance(GenerationFormat.PRESERVE, str)
        assert GenerationFormat.PRESERVE == "preserve"
