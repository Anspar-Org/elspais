"""Config module - Configuration loading and management.

Exports:
- ConfigLoader: Configuration container with dot-notation access
- load_config: Load config from TOML file
- find_config_file: Find .elspais.toml in directory hierarchy
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


# Default configuration values
DEFAULT_CONFIG: dict[str, Any] = {
    "patterns": {
        "id_template": "{prefix}-{type}{id}",
        "prefix": "REQ",
        "types": {
            "prd": {"id": "p", "name": "PRD", "level": 1},
            "ops": {"id": "o", "name": "OPS", "level": 2},
            "dev": {"id": "d", "name": "DEV", "level": 3},
        },
        "id_format": {"style": "numeric", "digits": 5, "leading_zeros": True},
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


def load_config(config_path: Path) -> ConfigLoader:
    """Load configuration from a TOML file.

    Args:
        config_path: Path to the .elspais.toml file.

    Returns:
        ConfigLoader with merged configuration.
    """
    content = config_path.read_text(encoding="utf-8")
    user_config = _parse_toml(content)
    merged = _merge_configs(DEFAULT_CONFIG, user_config)
    merged = _apply_env_overrides(merged)
    return ConfigLoader(merged)


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


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides.

    Looks for ELSPAIS_* environment variables.

    Args:
        config: Configuration dictionary.

    Returns:
        Configuration with environment overrides applied.
    """
    # Example: ELSPAIS_PATTERNS_PREFIX=MYREQ
    for key, value in os.environ.items():
        if key.startswith("ELSPAIS_"):
            # Convert ELSPAIS_PATTERNS_PREFIX to patterns.prefix
            config_key = key[8:].lower().replace("_", ".")
            _set_nested(config, config_key, value)

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


def _parse_toml(content: str) -> dict[str, Any]:
    """Parse TOML content into a dictionary.

    Simple zero-dependency TOML parser.

    Args:
        content: TOML file content.

    Returns:
        Parsed dictionary.
    """
    result: dict[str, Any] = {}
    current_section: list[str] = []
    lines = content.split("\n")

    for line in lines:
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Section header
        if line.startswith("[") and not line.startswith("[["):
            section = line.strip("[]").strip()
            current_section = section.split(".")
            _ensure_nested(result, current_section)
            continue

        # Key-value pair
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = _parse_value(value.strip())

            if current_section:
                target = result
                for part in current_section:
                    target = target[part]
                target[key] = value
            else:
                result[key] = value

    return result


def _ensure_nested(data: dict[str, Any], keys: list[str]) -> None:
    """Ensure nested dictionary structure exists."""
    current = data
    for key in keys:
        if key not in current:
            current[key] = {}
        current = current[key]


def _parse_value(value: str) -> Any:
    """Parse a TOML value string."""
    # String (quoted)
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    # Boolean
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # Integer
    if re.match(r"^-?\d+$", value):
        return int(value)

    # Float
    if re.match(r"^-?\d+\.\d+$", value):
        return float(value)

    # Array (simple single-line)
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items = [_parse_value(item.strip()) for item in inner.split(",")]
        return items

    # Inline table: { key = value, key2 = value2 }
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        if not inner:
            return {}
        result = {}
        # Split on commas, but handle nested structures
        pairs = inner.split(",")
        for pair in pairs:
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                result[k.strip()] = _parse_value(v.strip())
        return result

    return value


def get_config(
    config_path: Path | None = None,
    start_path: Path | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Get configuration with auto-discovery and fallback.

    This is the standard helper for command modules to load configuration.
    It handles:
    - Explicit config file path (if provided)
    - Config file discovery from start_path
    - Fallback to defaults if no config found
    - Error reporting (unless quiet=True)

    Args:
        config_path: Explicit config file path (optional)
        start_path: Directory to search for config (defaults to cwd)
        quiet: Suppress error messages

    Returns:
        Configuration dictionary (defaults if not found)
    """
    import sys

    if start_path is None:
        start_path = Path.cwd()

    # Use explicit config path or discover
    resolved_path = config_path if config_path else find_config_file(start_path)

    if resolved_path and resolved_path.exists():
        try:
            return load_config(resolved_path).get_raw()
        except Exception as e:
            if not quiet:
                print(f"Warning: Error loading config from {resolved_path}: {e}", file=sys.stderr)

    # Return defaults
    return dict(DEFAULT_CONFIG)


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


# Re-export parse_toml for use by config_cmd
parse_toml = _parse_toml


__all__ = [
    "ConfigLoader",
    "load_config",
    "find_config_file",
    "get_config",
    "get_spec_directories",
    "get_code_directories",
    "DEFAULT_CONFIG",
    "parse_toml",
]
