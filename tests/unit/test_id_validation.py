"""Tests for ID validation modes (v1.2.0)."""

from __future__ import annotations

from wols import IdValidationMode, validate_specimen_id


class TestIdValidationModeEnum:
    """Tests for IdValidationMode enum."""

    def test_strict_value(self) -> None:
        """Verify STRICT value."""
        assert IdValidationMode.STRICT.value == "strict"

    def test_ulid_value(self) -> None:
        """Verify ULID value."""
        assert IdValidationMode.ULID.value == "ulid"

    def test_uuid_value(self) -> None:
        """Verify UUID value."""
        assert IdValidationMode.UUID.value == "uuid"

    def test_any_value(self) -> None:
        """Verify ANY value."""
        assert IdValidationMode.ANY.value == "any"

    def test_is_str_enum(self) -> None:
        """Verify IdValidationMode is a string enum."""
        assert isinstance(IdValidationMode.STRICT, str)


class TestValidateSpecimenIdStrict:
    """Tests for validate_specimen_id with STRICT mode."""

    def test_valid_cuid_format(self) -> None:
        """Verify valid CUID format passes."""
        assert validate_specimen_id("wemush:abc123def456ghi789jkl012") is True
        assert validate_specimen_id("wemush:abcdefghijklmnopqrstuvwx") is True

    def test_lowercase_alphanumeric_only(self) -> None:
        """Verify only lowercase alphanumeric is valid."""
        assert validate_specimen_id("wemush:abc123") is True
        assert validate_specimen_id("wemush:12345") is True

    def test_uppercase_fails(self) -> None:
        """Verify uppercase characters fail in strict mode."""
        assert validate_specimen_id("wemush:ABC123") is False

    def test_missing_prefix_fails(self) -> None:
        """Verify missing wemush: prefix fails."""
        assert validate_specimen_id("abc123def456ghi789jkl012") is False

    def test_wrong_prefix_fails(self) -> None:
        """Verify wrong prefix fails."""
        assert validate_specimen_id("other:abc123") is False

    def test_empty_suffix_fails(self) -> None:
        """Verify empty suffix fails."""
        assert validate_specimen_id("wemush:") is False

    def test_default_mode_is_strict(self) -> None:
        """Verify default mode is STRICT."""
        assert validate_specimen_id("wemush:abc123") is True


class TestValidateSpecimenIdUlid:
    """Tests for validate_specimen_id with ULID mode."""

    def test_valid_ulid_format(self) -> None:
        """Verify valid ULID format passes."""
        # Valid ULID: 26 characters, Crockford's base32
        assert (
            validate_specimen_id(
                "wemush:01ARZ3NDEKTSV4RRFFQ69G5FAV",
                IdValidationMode.ULID,
            )
            is True
        )

    def test_ulid_case_insensitive(self) -> None:
        """Verify ULID validation is case-insensitive."""
        assert (
            validate_specimen_id(
                "wemush:01arz3ndektsv4rrffq69g5fav",
                IdValidationMode.ULID,
            )
            is True
        )

    def test_short_ulid_fails(self) -> None:
        """Verify short ULID fails."""
        assert (
            validate_specimen_id(
                "wemush:01ARZ3NDEKTSV4RRFFQ69G5FA",  # 25 chars
                IdValidationMode.ULID,
            )
            is False
        )

    def test_long_ulid_fails(self) -> None:
        """Verify long ULID fails."""
        assert (
            validate_specimen_id(
                "wemush:01ARZ3NDEKTSV4RRFFQ69G5FAVX",  # 27 chars
                IdValidationMode.ULID,
            )
            is False
        )

    def test_invalid_ulid_chars_fail(self) -> None:
        """Verify invalid ULID characters fail (I, L, O, U)."""
        # ULID excludes I, L, O, U
        assert (
            validate_specimen_id(
                "wemush:01ARZ3NDEKTSV4RRFFQ69GIFAV",  # I is invalid
                IdValidationMode.ULID,
            )
            is False
        )


class TestValidateSpecimenIdUuid:
    """Tests for validate_specimen_id with UUID mode."""

    def test_valid_uuid_v4_format(self) -> None:
        """Verify valid UUID v4 format passes."""
        assert (
            validate_specimen_id(
                "wemush:550e8400-e29b-41d4-a716-446655440000",
                IdValidationMode.UUID,
            )
            is True
        )

    def test_uuid_case_insensitive(self) -> None:
        """Verify UUID validation is case-insensitive."""
        assert (
            validate_specimen_id(
                "wemush:550E8400-E29B-41D4-A716-446655440000",
                IdValidationMode.UUID,
            )
            is True
        )

    def test_uuid_v4_version_required(self) -> None:
        """Verify UUID v4 version marker (4) is required."""
        # UUID with version 1 instead of 4
        assert (
            validate_specimen_id(
                "wemush:550e8400-e29b-11d4-a716-446655440000",
                IdValidationMode.UUID,
            )
            is False
        )

    def test_uuid_variant_required(self) -> None:
        """Verify UUID variant (8, 9, a, b) is required."""
        # UUID with invalid variant (0 instead of 8, 9, a, b)
        assert (
            validate_specimen_id(
                "wemush:550e8400-e29b-41d4-0716-446655440000",
                IdValidationMode.UUID,
            )
            is False
        )

    def test_invalid_uuid_format_fails(self) -> None:
        """Verify invalid UUID format fails."""
        assert (
            validate_specimen_id(
                "wemush:not-a-uuid",
                IdValidationMode.UUID,
            )
            is False
        )


class TestValidateSpecimenIdAny:
    """Tests for validate_specimen_id with ANY mode."""

    def test_any_non_empty_suffix_passes(self) -> None:
        """Verify any non-empty suffix passes."""
        assert validate_specimen_id("wemush:anything", IdValidationMode.ANY) is True
        assert validate_specimen_id("wemush:123", IdValidationMode.ANY) is True
        assert validate_specimen_id("wemush:a", IdValidationMode.ANY) is True
        assert validate_specimen_id("wemush:ABC-123-xyz", IdValidationMode.ANY) is True

    def test_empty_suffix_still_fails(self) -> None:
        """Verify empty suffix still fails in ANY mode."""
        assert validate_specimen_id("wemush:", IdValidationMode.ANY) is False

    def test_missing_prefix_still_fails(self) -> None:
        """Verify missing prefix still fails in ANY mode."""
        assert validate_specimen_id("anything", IdValidationMode.ANY) is False


class TestValidateSpecimenIdCustomValidator:
    """Tests for validate_specimen_id with custom validator."""

    def test_custom_validator_takes_precedence(self) -> None:
        """Verify custom validator takes precedence over mode."""

        # Custom validator that accepts anything starting with "test"
        def custom(id: str) -> bool:
            return id.startswith("test")

        assert validate_specimen_id("test123", custom_validator=custom) is True
        assert validate_specimen_id("wemush:abc", custom_validator=custom) is False

    def test_custom_validator_receives_full_id(self) -> None:
        """Verify custom validator receives the full ID."""
        received_id = None

        def capture(id: str) -> bool:
            nonlocal received_id
            received_id = id
            return True

        validate_specimen_id("wemush:test123", custom_validator=capture)
        assert received_id == "wemush:test123"
