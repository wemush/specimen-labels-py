"""WOLS - WeMush Open Labeling Standard.

Python implementation of the WOLS v1.2.0 specification for specimen tracking.

Example:
    >>> from wols import create_specimen, SpecimenType, to_json
    >>> specimen = create_specimen(
    ...     type=SpecimenType.SUBSTRATE,
    ...     species="Pleurotus ostreatus",
    ... )
    >>> print(to_json(specimen, indent=2))
"""

# Core constants
from wols.constants import (
    DEFAULT_HTTPS_BASE_URL,
    DEFAULT_URL_SCHEME,
    WOLS_CONTEXT,
    WOLS_VERSION,
    UrlScheme,
)

# Core functions
from wols.core.create import create_specimen
from wols.core.parse import (
    parse_compact_url,
    parse_compact_url_or_none,
    parse_compact_url_or_throw,
    parse_specimen,
)
from wols.core.serialize import to_compact_url, to_json
from wols.core.validate import (
    IdValidationMode,
    validate_specimen,
    validate_specimen_id,
)

# Environment detection (v1.2.0)
from wols.environment import (
    RuntimeEnvironment,
    get_python_version,
    get_runtime_environment,
    is_crypto_supported,
    supports_typing_extensions,
)

# Exceptions
from wols.exceptions import (
    WolsEncryptionError,
    WolsError,
    WolsParseError,
    WolsValidationError,
)

# Generation format (v1.2.0)
from wols.generation import (
    GenerationFormat,
    is_valid_generation,
    normalize_generation,
)

# Migration utilities (v1.2.0)
from wols.migration import (
    can_migrate,
    clear_migrations,
    compare_versions,
    get_current_version,
    get_migrations,
    is_newer,
    is_outdated,
    migrate,
    register_migration,
)

# Models
from wols.models.enums import (
    GROWTH_STAGES,
    GrowthStage,
    SpecimenType,
    get_growth_stage_order,
    get_next_growth_stage,
    get_previous_growth_stage,
)
from wols.models.specimen import Specimen, SpecimenMeta, SpecimenRef, Strain
from wols.models.validation import ValidationError, ValidationResult

# Type aliases (v1.2.0)
from wols.type_aliases import (
    WOLS_TO_PLATFORM_MAP,
    get_type_aliases,
    map_from_wols_type,
    map_to_wols_type,
    register_type_alias,
    resolve_type_alias,
)

__version__ = "1.2.0"

__all__ = [
    "DEFAULT_HTTPS_BASE_URL",
    "DEFAULT_URL_SCHEME",
    "GROWTH_STAGES",
    "WOLS_CONTEXT",
    "WOLS_TO_PLATFORM_MAP",
    "WOLS_VERSION",
    "GenerationFormat",
    "GrowthStage",
    "IdValidationMode",
    "RuntimeEnvironment",
    "Specimen",
    "SpecimenMeta",
    "SpecimenRef",
    "SpecimenType",
    "Strain",
    "UrlScheme",
    "ValidationError",
    "ValidationResult",
    "WolsEncryptionError",
    "WolsError",
    "WolsParseError",
    "WolsValidationError",
    "__version__",
    "can_migrate",
    "clear_migrations",
    "compare_versions",
    "create_specimen",
    "get_current_version",
    "get_growth_stage_order",
    "get_migrations",
    "get_next_growth_stage",
    "get_previous_growth_stage",
    "get_python_version",
    "get_runtime_environment",
    "get_type_aliases",
    "is_crypto_supported",
    "is_newer",
    "is_outdated",
    "is_valid_generation",
    "map_from_wols_type",
    "map_to_wols_type",
    "migrate",
    "normalize_generation",
    "parse_compact_url",
    "parse_compact_url_or_none",
    "parse_compact_url_or_throw",
    "parse_specimen",
    "register_migration",
    "register_type_alias",
    "resolve_type_alias",
    "supports_typing_extensions",
    "to_compact_url",
    "to_json",
    "validate_specimen",
    "validate_specimen_id",
]
