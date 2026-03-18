"""Config module - Configuration loading and management.

Exports:
- ConfigLoader: Configuration container with dot-notation access
- load_config: Load config from TOML file
- find_config_file: Find .elspais.toml in directory hierarchy
"""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit

# Default configuration values
DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "namespace": "REQ",
    },
    "id-patterns": {
        "canonical": "{namespace}-{type.letter}{component}",
        "aliases": {"short": "{type.letter}{component}"},
        "types": {
            "prd": {"level": 1, "aliases": {"letter": "p"}},
            "ops": {"level": 2, "aliases": {"letter": "o"}},
            "dev": {"level": 3, "aliases": {"letter": "d"}},
        },
        "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
        "assertions": {
            "label_style": "uppercase",
            "max_count": 26,
        },
    },
    "spec": {
        "directories": ["spec"],
        "patterns": ["*.md"],
        "skip_files": [],
        "skip_dirs": [],
    },
    "rules": {
        "hierarchy": {
            "dev": ["ops", "prd"],
            "ops": ["prd"],
            "prd": [],
        },
    },
    "testing": {
        "enabled": False,
        "test_dirs": ["tests"],
        "skip_dirs": [],
        "patterns": ["test_*.py", "*_test.py"],
        "result_files": [],
        "run_meta_file": "",
        "reference_patterns": [],
        "reference_keyword": "Verifies",
        "prescan_command": "",
    },
    "ignore": {
        "global": ["node_modules", ".git", "__pycache__", "*.pyc", ".venv", ".env"],
        "spec": ["README.md", "INDEX.md"],
        "code": ["*_test.py", "conftest.py", "test_*.py"],
        "test": ["fixtures/**", "__snapshots__"],
    },
    "references": {
        "defaults": {
            "separators": ["-", "_"],
            "case_sensitive": False,
            "prefix_optional": False,
            "comment_styles": ["#", "//", "--"],
            "keywords": {
                "implements": ["Implements", "IMPLEMENTS"],
                "verifies": ["Verifies", "VERIFIES"],
                "refines": ["Refines", "REFINES"],
                # Implements: REQ-d00069-H
                "satisfies": ["Satisfies", "SATISFIES"],
            },
        },
        "overrides": [],
    },
    "keywords": {
        "min_length": 3,
    },
    "validation": {
        "hash_mode": "normalized-text",
        "allow_unresolved_cross_repo": False,
    },
    "graph": {
        "satellite_kinds": ["assertion", "result"],
    },
    "changelog": {
        "enforce": True,
        "require_present": False,
        "id_source": "gh",
        "date_format": "iso",
        "require_change_order": False,
        "require_reason": True,
        "require_author_name": True,
        "require_author_id": True,
        "author_id_format": "email",
        "allowed_author_ids": "all",
    },
}


class ConfigLoader:
    """Configuration container with dot-notation access."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize with configuration data.

        Args:
            data: Configuration dictionary.
        """
        self._data = data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfigLoader:
        """Create ConfigLoader from dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            ConfigLoader instance.
        """
        merged = _merge_configs(DEFAULT_CONFIG, data)
        return cls(merged)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key.

        Args:
            key: Dot-separated key path (e.g., "patterns.prefix").
            default: Default value if key not found.

        Returns:
            Configuration value or default.
        """
        parts = key.split(".")
        value = self._data

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value

    def get_raw(self) -> dict[str, Any]:
        """Get raw configuration dictionary.

        Returns:
            Complete configuration dictionary.
        """
        return self._data


def _migrate_legacy_patterns(config: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy [patterns] config to [id-patterns] format.

    Configs without an explicit ``version`` field (pre-v2) may define ID
    patterns in the old ``[patterns]`` section.  This function synthesizes
    the equivalent ``[id-patterns]`` so that ``IdResolver`` works correctly.

    Once all repos have migrated to ``[id-patterns]`` and set ``version = 2``,
    this migration path can be removed.
    """
    # v2+ configs must use [id-patterns] directly — skip migration
    config_version = config.get("version")
    if config_version is not None and isinstance(config_version, int) and config_version >= 2:
        return config

    patterns = config.get("patterns", {})
    if not patterns or not patterns.get("types"):
        return config

    # Only migrate if [id-patterns] is still at defaults (user didn't define it)
    id_patterns = config.get("id-patterns", {})
    canonical = id_patterns.get("canonical")
    default_canonical = DEFAULT_CONFIG["id-patterns"]["canonical"]
    if canonical is not None and canonical != default_canonical:
        return config  # user has explicit [id-patterns], don't override

    # Build type definitions: old types.*.id -> new types.*.aliases.letter
    old_types = patterns.get("types", {})
    new_types: dict[str, Any] = {}
    for code, tdef in old_types.items():
        if isinstance(tdef, dict):
            new_types[code] = {
                "level": tdef.get("level", 1),
                "aliases": {"letter": tdef.get("id", code[0])},
            }

    # Build component format from old id_format
    old_id_format = patterns.get("id_format", {})
    new_component = {
        "style": old_id_format.get("style", "numeric"),
        "digits": old_id_format.get("digits", 5),
        "leading_zeros": old_id_format.get("leading_zeros", True),
    }
    if old_id_format.get("pattern"):
        new_component["pattern"] = old_id_format["pattern"]

    # Build canonical template by translating tokens
    old_template = patterns.get("id_template", "{prefix}-{type}{id}")
    canonical = old_template
    canonical = canonical.replace("{prefix}", "{namespace}")
    canonical = canonical.replace("{id}", "{component}")
    canonical = canonical.replace("{type}", "{type.letter}")

    # Handle {associated} token: replace with literal prefix if configured
    associated_config = patterns.get("associated", {})
    if associated_config.get("enabled") and "{associated}" in canonical:
        assoc_prefix = config.get("associated", {}).get("prefix", "")
        sep = associated_config.get("separator", "-")
        if assoc_prefix:
            canonical = canonical.replace("{associated}", f"{assoc_prefix}{sep}")
        else:
            # Associated enabled but no prefix — drop the token
            canonical = canonical.replace("{associated}", "")
    else:
        canonical = canonical.replace("{associated}", "")

    # Build assertions config
    old_assertions = patterns.get("assertions", {})
    new_assertions: dict[str, Any] = {}
    if old_assertions:
        new_assertions["label_style"] = old_assertions.get("label_style", "uppercase")
        new_assertions["max_count"] = old_assertions.get("max_count", 26)
        if "zero_pad" in old_assertions:
            new_assertions["zero_pad"] = old_assertions["zero_pad"]
        if "multi_separator" in old_assertions:
            new_assertions["multi_separator"] = old_assertions["multi_separator"]

    # Also set namespace from patterns.prefix if not already in [project]
    namespace = patterns.get("prefix", "REQ")
    if config.get("project", {}).get("namespace") == DEFAULT_CONFIG["project"]["namespace"]:
        config.setdefault("project", {})["namespace"] = namespace

    # Write synthesized [id-patterns]
    config["id-patterns"] = {
        "canonical": canonical,
        "aliases": {"short": canonical.split("-", 1)[1] if "-" in canonical else canonical},
        "types": new_types,
        "component": new_component,
        "assertions": new_assertions or id_patterns.get("assertions", {}),
    }

    return config


CURRENT_CONFIG_VERSION = 2

MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    1: _migrate_legacy_patterns,  # [patterns] -> [id-patterns]
}


def load_config(config_path: Path) -> ConfigLoader:
    """Load configuration from a TOML file.

    Loads config_path, then deep-merges .elspais.local.toml (if present
    alongside it) on top — following the docker-compose.override.yml / .env.local
    convention for developer-local overrides.

    Args:
        config_path: Path to the .elspais.toml file.

    Returns:
        ConfigLoader with merged configuration.
    """
    content = config_path.read_text(encoding="utf-8")
    user_config = _parse_toml(content)
    merged = _merge_configs(DEFAULT_CONFIG, user_config)

    # Deep-merge developer-local overrides if present
    local_path = config_path.parent / ".elspais.local.toml"
    if local_path.is_file():
        local_config = _parse_toml(local_path.read_text(encoding="utf-8"))
        merged = _merge_configs(merged, local_config)

    merged = _apply_env_overrides(merged)

    # Version-gated sequential migration
    version = merged.get("version", 1)
    for v in range(version, CURRENT_CONFIG_VERSION):
        if v in MIGRATIONS:
            merged = MIGRATIONS[v](merged)

    return ConfigLoader(merged)


def find_git_root(start_path: Path | None = None) -> Path | None:
    """Find the root directory of a git repository.

    Searches upward from start_path for a .git directory or file (worktree).

    Args:
        start_path: Directory to start searching from (defaults to cwd).

    Returns:
        Path to git repository root, or None if not in a git repo.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    if current.is_file():
        current = current.parent

    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.exists():
            # Could be a directory (normal repo) or file (worktree)
            return current

        current = current.parent

    return None


def find_canonical_root(start_path: Path | None = None) -> Path | None:
    """Find the canonical (non-worktree) git repository root.

    For normal repos: returns same as find_git_root().
    For worktrees: returns the MAIN repo root via git-common-dir.
    Use this for resolving cross-repo sibling paths.

    Args:
        start_path: Directory to start searching from (defaults to cwd).

    Returns:
        Path to canonical git repository root, or None if not in a git repo.
    """
    # Implements: REQ-p00005-F
    import subprocess

    git_root = find_git_root(start_path)
    if git_root is None:
        return None

    git_marker = git_root / ".git"
    if git_marker.is_file():
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                capture_output=True,
                text=True,
                cwd=git_root,
            )
            if result.returncode == 0:
                common_dir = Path(result.stdout.strip())
                if not common_dir.is_absolute():
                    common_dir = (git_root / common_dir).resolve()
                return common_dir.parent
        except (OSError, subprocess.SubprocessError):
            pass

    return git_root


def get_project_name(config: dict[str, Any] | None = None) -> str:
    """Get the project name from config.

    Returns config["project"]["name"] if set, otherwise "unknown".
    """
    if config:
        name = config.get("project", {}).get("name")
        if name:
            return name
    return "unknown"


def find_config_file(start_path: Path) -> Path | None:
    """Find .elspais.toml configuration file.

    Searches from start_path up to git root or filesystem root.

    Args:
        start_path: Directory to start searching from.

    Returns:
        Path to config file if found, None otherwise.
    """
    current = start_path.resolve()

    if current.is_file():
        current = current.parent

    while current != current.parent:
        config_path = current / ".elspais.toml"
        if config_path.exists():
            return config_path

        # Stop at git root
        if (current / ".git").exists():
            break

        current = current.parent

    return None


def _merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge configuration dictionaries.

    Args:
        base: Base configuration.
        override: Override configuration.

    Returns:
        Merged configuration.
    """
    result = dict(base)

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value

    return result


def _try_parse_env_value(value: str) -> Any:
    """Parse an environment variable value with type inference.

    Attempts to interpret the string as a richer Python type:
    - JSON arrays/objects (starts with ``[`` or ``{``)
    - Booleans (``true``/``false``, case-insensitive)
    - Falls back to plain string

    Args:
        value: Raw environment variable string.

    Returns:
        Parsed Python value (list, dict, bool, or str).
    """
    import json

    # JSON array or object
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    # Boolean
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    return value


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides.

    Looks for ELSPAIS_* environment variables.  Values are parsed via
    ``_try_parse_env_value`` so that JSON lists, booleans, and plain
    strings are all handled correctly.

    Args:
        config: Configuration dictionary.

    Returns:
        Configuration with environment overrides applied.
    """
    # Example: ELSPAIS_PATTERNS_PREFIX=MYREQ
    # Example: ELSPAIS_ASSOCIATES_PATHS='["/path/to/repo"]'
    for key, value in os.environ.items():
        if key.startswith("ELSPAIS_"):
            # Convert ELSPAIS_PATTERNS_PREFIX to patterns.prefix
            # Single _ = section separator, __ = literal underscore in key
            # e.g., ELSPAIS_VALIDATION_STRICT__HIERARCHY -> validation.strict_hierarchy
            config_key = (
                key[8:].lower().replace("__", "\x00").replace("_", ".").replace("\x00", "_")
            )
            _set_nested(config, config_key, _try_parse_env_value(value))

    return config


def _set_nested(data: dict[str, Any], key: str, value: Any) -> None:
    """Set a value at a nested key path."""
    parts = key.split(".")
    current = data

    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]

    current[parts[-1]] = value


def apply_cli_overrides(config: dict[str, Any], overrides: list[str] | None) -> dict[str, Any]:
    """Apply ``--set key=value`` CLI overrides to a config dict.

    Each override must be in ``key=value`` format where *key* is a
    dot-separated path (e.g. ``spec.directories``) and *value* is parsed
    via :func:`_try_parse_env_value` (supports JSON, booleans, strings).

    Args:
        config: Configuration dictionary to modify in place.
        overrides: List of ``key=value`` strings, or *None*.

    Returns:
        The mutated *config* dict (for convenience).

    Raises:
        ValueError: If an override string does not contain ``=``.
    """
    if not overrides:
        return config
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"Invalid override format: {item!r}  (expected key=value)")
        key, value = item.split("=", 1)
        _set_nested(config, key.strip(), _try_parse_env_value(value.strip()))
    return config


def _parse_toml(content: str) -> dict[str, Any]:
    """Parse TOML content into a plain dictionary.

    Uses tomlkit for full TOML 1.0 compliance. Returns a plain dict
    (unwrapped from TOMLDocument) to avoid downstream type surprises.

    Args:
        content: TOML file content.

    Returns:
        Parsed dictionary.
    """
    # Implements: REQ-p00002-A
    doc = tomlkit.parse(content)
    return doc.unwrap()


def parse_toml_document(content: str) -> tomlkit.TOMLDocument:
    """Parse TOML content into a TOMLDocument for round-trip editing.

    Unlike parse_toml(), this preserves comments, whitespace, and
    formatting. Use this when modifying and writing back TOML content.

    Args:
        content: TOML file content.

    Returns:
        TOMLDocument that preserves formatting on dumps().
    """
    # Implements: REQ-p00002-A
    return tomlkit.parse(content)


_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


def _try_parse_numeric(value: str) -> int | float | None:
    """Try to parse a string as an integer or float.

    Args:
        value: String to parse.

    Returns:
        Parsed int or float, or None if not numeric.
    """
    if _INT_RE.match(value):
        return int(value)
    if _FLOAT_RE.match(value):
        return float(value)
    return None


def get_config(
    config_path: Path | None = None,
    start_path: Path | None = None,
    quiet: bool = False,
    overrides: list[str] | None = None,
) -> dict[str, Any]:
    """Get configuration with auto-discovery and fallback.

    This is the standard helper for command modules to load configuration.
    It handles:
    - Explicit config file path (if provided)
    - Config file discovery from start_path
    - Fallback to defaults if no config found
    - Error reporting (unless quiet=True)
    - CLI ``--set`` overrides (applied last, highest precedence)

    Override precedence (highest first):
        ``--set`` > env vars > ``.elspais.local.toml`` > ``.elspais.toml`` > defaults

    Args:
        config_path: Explicit config file path (optional)
        start_path: Directory to search for config (defaults to cwd)
        quiet: Suppress error messages
        overrides: List of ``key=value`` strings from ``--set`` CLI flag.

    Returns:
        Configuration dictionary (defaults if not found)
    """
    if start_path is None:
        start_path = Path.cwd()

    # Use explicit config path or discover
    resolved_path = config_path if config_path else find_config_file(start_path)

    if resolved_path and resolved_path.exists():
        try:
            config = load_config(resolved_path).get_raw()
        except Exception as e:
            # A config file that exists but can't be parsed is always an error.
            # Silently falling back to defaults would hide the problem and cause
            # hard-to-diagnose issues (e.g. skip_dirs not working).
            raise ValueError(
                f"Failed to parse config file {resolved_path}: {e}\n"
                "Fix the syntax error in your .elspais.toml file."
            ) from e
    else:
        # Return defaults (no config file found)
        config = dict(DEFAULT_CONFIG)

    # Apply CLI overrides (highest precedence)
    apply_cli_overrides(config, overrides)
    return config


def get_spec_directories(
    spec_dir_override: Path | None,
    config: dict[str, Any],
    base_path: Path | None = None,
) -> list[Path]:
    """Get the spec directories from override or config.

    Args:
        spec_dir_override: Explicit spec directory (e.g., from CLI --spec-dir)
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing spec directory paths
    """
    if spec_dir_override:
        return [spec_dir_override]

    if base_path is None:
        base_path = Path.cwd()

    # Get directories from config - check both "directories" and "spec" sections
    dir_config = config.get("directories", {}).get("spec")
    if dir_config is None:
        dir_config = config.get("spec", {}).get("directories", ["spec"])

    # Handle both string and list
    if isinstance(dir_config, str):
        dir_list = [dir_config]
    else:
        dir_list = list(dir_config)

    # Resolve paths and filter to existing
    result = []
    for d in dir_list:
        path = Path(d)
        if not path.is_absolute():
            path = base_path / path
        if path.exists() and path.is_dir():
            result.append(path)

    return result


def get_code_directories(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> list[Path]:
    """Get code directories from configuration.

    Args:
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing code directory paths
    """
    if base_path is None:
        base_path = Path.cwd()

    dir_config = config.get("directories", {}).get("code", ["src"])

    # Handle both string and list
    if isinstance(dir_config, str):
        dir_list = [dir_config]
    else:
        dir_list = list(dir_config)

    # Resolve paths and filter to existing
    result = []
    for d in dir_list:
        path = Path(d)
        if not path.is_absolute():
            path = base_path / path
        if path.exists() and path.is_dir():
            result.append(path)

    return result


def get_docs_directories(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> list[Path]:
    """Get documentation directories from configuration.

    Uses [directories].docs config for scanning documentation files
    for requirement references and traceability.

    Args:
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing docs directory paths
    """
    if base_path is None:
        base_path = Path.cwd()

    dir_config = config.get("directories", {}).get("docs", ["docs"])

    # Handle both string and list
    if isinstance(dir_config, str):
        dir_list = [dir_config]
    else:
        dir_list = list(dir_config)

    # Resolve paths and filter to existing
    result = []
    for d in dir_list:
        path = Path(d)
        if not path.is_absolute():
            path = base_path / path
        if path.exists() and path.is_dir():
            result.append(path)

    return result


# Re-export parse_toml for use by config_cmd
parse_toml = _parse_toml


@dataclass
class IgnoreConfig:
    """Unified configuration for ignoring files and directories.

    Supports glob patterns (fnmatch) for flexible matching.
    Patterns can be scoped to specific contexts (spec, code, test).

    Attributes:
        global_patterns: Patterns applied everywhere
        spec_patterns: Additional patterns for spec file scanning
        code_patterns: Additional patterns for code scanning
        test_patterns: Additional patterns for test scanning
    """

    global_patterns: list[str]
    spec_patterns: list[str]
    code_patterns: list[str]
    test_patterns: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IgnoreConfig:
        """Create IgnoreConfig from configuration dictionary.

        Args:
            data: Dictionary from [ignore] config section

        Returns:
            IgnoreConfig instance
        """
        return cls(
            global_patterns=data.get("global", []),
            spec_patterns=data.get("spec", []),
            code_patterns=data.get("code", []),
            test_patterns=data.get("test", []),
        )

    def should_ignore(self, path: str | Path, scope: str = "global") -> bool:
        """Check if a path should be ignored based on patterns.

        Matches against:
        1. Global patterns (always checked)
        2. Scope-specific patterns (if scope is provided)

        Supports glob patterns via fnmatch:
        - "*" matches any characters within a path component
        - "**" matches across directory separators (when using pathlib)
        - "?" matches a single character

        Args:
            path: Path to check (can be file or directory)
            scope: Context scope ("global", "spec", "code", "test")

        Returns:
            True if path should be ignored
        """
        if isinstance(path, Path):
            path_str = str(path)
            path_name = path.name
            path_parts = path.parts
        else:
            path_str = path
            path_obj = Path(path)
            path_name = path_obj.name
            path_parts = path_obj.parts

        # Collect all applicable patterns
        patterns = list(self.global_patterns)
        if scope == "spec":
            patterns.extend(self.spec_patterns)
        elif scope == "code":
            patterns.extend(self.code_patterns)
        elif scope == "test":
            patterns.extend(self.test_patterns)

        for pattern in patterns:
            # Check if pattern matches the file/dir name directly
            if fnmatch.fnmatch(path_name, pattern):
                return True

            # Check if pattern matches any path component
            for part in path_parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

            # Check if pattern matches the full relative path
            if fnmatch.fnmatch(path_str, pattern):
                return True

        return False

    def get_patterns_for_scope(self, scope: str) -> list[str]:
        """Get all patterns applicable to a scope (global + scope-specific).

        Args:
            scope: Context scope ("global", "spec", "code", "test")

        Returns:
            Combined list of patterns
        """
        patterns = list(self.global_patterns)
        if scope == "spec":
            patterns.extend(self.spec_patterns)
        elif scope == "code":
            patterns.extend(self.code_patterns)
        elif scope == "test":
            patterns.extend(self.test_patterns)
        return patterns


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    pass


def validate_project_config(config: dict[str, Any]) -> list[str]:
    """Validate project type configuration consistency.

    Checks that project.type matches the presence of [core] and [associated] sections:
    - project.type = "core" → [associated] MAY exist (defines associated repos)
    - project.type = "associated" → [core] MUST exist (specifies core repo path)
    - project.type not set → [core] and [associated] sections are ERRORS

    Args:
        config: Configuration dictionary

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    project_type = config.get("project", {}).get("type")
    has_core_section = "core" in config and isinstance(config["core"], dict)
    has_associated_section = "associated" in config and isinstance(config["associated"], dict)

    if project_type == "associated":
        # Associated repos MUST have a [core] section
        if not has_core_section:
            errors.append(
                "project.type='associated' requires a [core] section with 'path' "
                "to the core repository"
            )
        elif not config["core"].get("path"):
            errors.append(
                "[core] section must specify 'path' to core repository " "for associated projects"
            )
    elif project_type == "core":
        # Core repos MAY have [associated] section - no validation needed
        pass
    elif project_type is None:
        # No project type set - [core] and [associated] sections are errors
        if has_core_section:
            errors.append(
                "[core] section found but project.type is not set. "
                "Set project.type='associated' to use this section"
            )
        if has_associated_section:
            errors.append(
                "[associated] section found but project.type is not set. "
                "Set project.type='core' or 'associated' to use this section"
            )
    else:
        # Unknown project type
        errors.append(
            f"Unknown project.type='{project_type}'. " "Valid values: 'core', 'associated'"
        )

    return errors


def get_test_directories(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> list[Path]:
    """Get test directories from configuration.

    Uses [testing].test_dirs config, falling back to common defaults.

    Args:
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing test directory paths
    """
    if base_path is None:
        base_path = Path.cwd()

    # Get from [testing] section first, then fall back to defaults
    testing_config = config.get("testing", {})
    dir_config = testing_config.get("test_dirs", ["tests"])

    # Handle both string and list
    if isinstance(dir_config, str):
        dir_list = [dir_config]
    else:
        dir_list = list(dir_config)

    # Resolve paths and filter to existing
    result = []
    for d in dir_list:
        path = Path(d)
        if not path.is_absolute():
            path = base_path / path
        if path.exists() and path.is_dir():
            result.append(path)

    return result


def get_ignore_config(config: dict[str, Any]) -> IgnoreConfig:
    """Get IgnoreConfig from configuration dictionary.

    The IgnoreConfig provides a unified way to check if paths should be ignored
    during file scanning. It supports glob patterns and scope-specific rules.

    Args:
        config: Configuration dictionary from get_config() or load_config().get_raw()

    Returns:
        IgnoreConfig instance with patterns from [ignore] section or defaults.
    """
    ignore_data = config.get("ignore", {})

    # Also check legacy spec.skip_files and spec.skip_dirs and merge them
    spec_config = config.get("spec", {})
    legacy_skip_files = spec_config.get("skip_files", [])
    legacy_skip_dirs = spec_config.get("skip_dirs", [])

    # Merge legacy patterns into spec scope
    merged_spec = list(ignore_data.get("spec", []))
    merged_spec.extend(legacy_skip_files)
    merged_spec.extend(legacy_skip_dirs)

    # Create config with merged patterns
    return IgnoreConfig(
        global_patterns=ignore_data.get("global", []),
        spec_patterns=list(set(merged_spec)),  # Deduplicate
        code_patterns=ignore_data.get("code", []),
        test_patterns=ignore_data.get("test", []),
    )


__all__ = [
    "ConfigLoader",
    "ConfigValidationError",
    "IgnoreConfig",
    "load_config",
    "find_config_file",
    "find_canonical_root",
    "find_git_root",
    "get_config",
    "get_spec_directories",
    "get_code_directories",
    "get_docs_directories",
    "get_test_directories",
    "get_ignore_config",
    "validate_project_config",
    "DEFAULT_CONFIG",
    "parse_toml",
    "parse_toml_document",
    "get_status_roles",
    "_try_parse_numeric",
    "_try_parse_env_value",
    "apply_cli_overrides",
    "get_associates_config",
    "validate_no_transitive_associates",
]


# Implements: REQ-d00202-A+B+C
def get_associates_config(config: dict[str, Any]) -> dict[str, dict]:
    """Read [associates] sections from config.

    Each associate entry has:
    - path (str, required): relative path to the associate repo
    - git (str | None, optional): remote URL for clone assistance

    Args:
        config: The project configuration dictionary.

    Returns:
        Dict mapping associate name to {"path": str, "git": str | None}.
        Empty dict if no [associates] section exists.
    """
    associates = config.get("associates", {})
    if not associates:
        return {}
    result: dict[str, dict] = {}
    for name, entry in associates.items():
        if isinstance(entry, dict):
            result[name] = {
                "path": entry["path"],
                "git": entry.get("git"),
            }
    return result


# Implements: REQ-d00202-D
def validate_no_transitive_associates(
    associate_name: str, associate_config: dict[str, Any]
) -> None:
    """Check that an associate does not declare its own associates.

    Only the root repo may declare [associates]. If an associate's config
    contains an [associates] section, raise FederationError.

    Args:
        associate_name: Name of the associate being validated.
        associate_config: The associate's loaded config dict.

    Raises:
        FederationError: If the associate declares its own associates.
    """
    from elspais.graph.federated import FederationError

    # Use get_associates_config to check for NEW-format [associates.<name>] entries
    # (not the legacy associates.paths list from the old sponsor system)
    new_format_associates = get_associates_config(associate_config)
    if new_format_associates:
        raise FederationError(
            f"Associate '{associate_name}' declares its own associates "
            f"-- only the root repo may declare associates."
        )


def get_status_roles(config: dict[str, Any]):
    """Get StatusRolesConfig from configuration dictionary."""
    from elspais.config.status_roles import StatusRolesConfig

    roles_data = config.get("rules", {}).get("format", {}).get("status_roles", {})
    if roles_data:
        return StatusRolesConfig.from_dict(roles_data)
    return StatusRolesConfig.default()
