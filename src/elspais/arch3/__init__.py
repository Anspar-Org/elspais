"""Architecture 3.0 - Clean graph-based traceability system.

This package provides the Architecture 3.0 implementation:
- GraphNode: Unified node representation with typed content
- Relations: Edge types (implements, refines, validates)
- MDparser: Line-claiming parser system
- DomainDeserializer: Abstract deserialization controller
- Models: Core dataclasses (Requirement, Assertion, etc.)
- Rules: Validation rule engine
- Loader: Requirement loading utilities
"""

__version__ = "0.1.0"

# Re-export main components for easy access
from elspais.arch3.models import (
    Assertion,
    ContentRule,
    ParseResult,
    ParseWarning,
    Requirement,
    RequirementType,
    StructuredParseResult,
)
from elspais.arch3.config import (
    ConfigLoader,
    DEFAULT_CONFIG,
    find_config_file,
    get_code_directories,
    get_config,
    get_spec_directories,
    load_config,
)
from elspais.arch3.rules import (
    FormatConfig,
    HierarchyConfig,
    RuleEngine,
    RulesConfig,
    RuleViolation,
    Severity,
)
from elspais.arch3.loader import (
    create_parser,
    get_skip_dirs,
    get_skip_files,
    get_spec_directories,
    load_requirements_from_directories,
    load_requirements_from_directory,
    load_requirements_from_repo,
    parse_requirements_from_directories,
)
from elspais.arch3.parser import RequirementParser
from elspais.arch3.content_rules import (
    load_content_rule,
    load_content_rules,
    parse_frontmatter,
)
from elspais.arch3.associates import (
    Associate,
    AssociatesConfig,
    get_associate_spec_directories,
    get_sponsor_spec_directories,  # alias for backwards compatibility
    load_associates_config,
    Sponsor,  # alias for backwards compatibility
    SponsorsConfig,  # alias for backwards compatibility
)
from elspais.arch3.utilities.hasher import (
    calculate_hash,
    clean_requirement_body,
    verify_hash,
)
from elspais.arch3.utilities.patterns import (
    PatternConfig,
    PatternValidator,
)
from elspais.arch3.Graph import (
    Edge,
    EdgeKind,
    GraphNode,
    NodeKind,
    SourceLocation,
)

__all__ = [
    # Version
    "__version__",
    # Models
    "Assertion",
    "ContentRule",
    "ParseResult",
    "ParseWarning",
    "Requirement",
    "RequirementType",
    "StructuredParseResult",
    # Config
    "ConfigLoader",
    "DEFAULT_CONFIG",
    "find_config_file",
    "get_code_directories",
    "get_config",
    "get_spec_directories",
    "load_config",
    # Rules
    "FormatConfig",
    "HierarchyConfig",
    "RuleEngine",
    "RulesConfig",
    "RuleViolation",
    "Severity",
    # Loader
    "create_parser",
    "get_skip_dirs",
    "get_skip_files",
    "get_spec_directories",
    "load_requirements_from_directories",
    "load_requirements_from_directory",
    "load_requirements_from_repo",
    "parse_requirements_from_directories",
    # Parser
    "RequirementParser",
    # Content Rules
    "load_content_rule",
    "load_content_rules",
    "parse_frontmatter",
    # Associates
    "Associate",
    "AssociatesConfig",
    "get_associate_spec_directories",
    "get_sponsor_spec_directories",
    "load_associates_config",
    "Sponsor",
    "SponsorsConfig",
    # Hasher
    "calculate_hash",
    "clean_requirement_body",
    "verify_hash",
    # Patterns
    "PatternConfig",
    "PatternValidator",
    # Graph
    "Edge",
    "EdgeKind",
    "GraphNode",
    "NodeKind",
    "SourceLocation",
]
