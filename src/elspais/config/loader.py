"""
elspais.config.loader - Configuration loading and merging.

Handles loading .elspais.toml files and merging with defaults.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from elspais.config.defaults import DEFAULT_CONFIG


def load_config(config_path: Path) -> Dict[str, Any]:
    """
    Load configuration from a TOML file.

    Args:
        config_path: Path to the .elspais.toml file

    Returns:
        Merged configuration dictionary
    """
    user_config = parse_toml(config_path.read_text(encoding="utf-8"))
    merged = merge_configs(DEFAULT_CONFIG, user_config)
    merged = apply_env_overrides(merged)
    return merged


def find_config_file(start_path: Path) -> Optional[Path]:
    """
    Find .elspais.toml configuration file.

    Searches from start_path up to git root or filesystem root.

    Args:
        start_path: Directory to start searching from

    Returns:
        Path to config file if found, None otherwise
    """
    current = start_path.resolve()

    # If start_path is a file, use its parent
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


def parse_toml(content: str) -> Dict[str, Any]:
    """
    Parse TOML content into a dictionary.

    Uses a simple parser for zero dependencies.

    Args:
        content: TOML file content

    Returns:
        Parsed dictionary
    """
    result: Dict[str, Any] = {}
    current_section: List[str] = []
    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            i += 1
            continue

        # Section header
        if line.startswith("[") and not line.startswith("[["):
            section = line.strip("[]").strip()
            # Handle nested sections like [patterns.types]
            current_section = section.split(".")
            # Create nested structure
            _ensure_nested(result, current_section)
            i += 1
            continue

        # Key-value pair
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            # Handle multi-line arrays
            if value.startswith("[") and not value.endswith("]"):
                # Collect all lines until closing bracket
                value_lines = [value]
                i += 1
                while i < len(lines):
                    next_line = lines[i].strip()
                    value_lines.append(next_line)
                    if "]" in next_line:
                        break
                    i += 1
                value = " ".join(value_lines)

            # Strip inline comments (but not from quoted strings)
            if not (value.startswith('"') or value.startswith("'")):
                # Find comment marker that's not inside brackets/braces
                comment_idx = _find_comment_start(value)
                if comment_idx >= 0:
                    value = value[:comment_idx].strip()

            # Parse value
            parsed_value = _parse_value(value)

            # Set in current section
            target = _get_nested(result, current_section)
            target[key] = parsed_value

        i += 1

    return result


def _parse_value(value: str) -> Any:
    """Parse a TOML value string."""
    value = value.strip()

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

    # String (quoted)
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    # Array
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        # Simple array parsing
        items = []
        for item in _split_array(inner):
            item = item.strip()
            if item:
                items.append(_parse_value(item))
        return items

    # Inline table
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        if not inner:
            return {}
        result = {}
        for pair in _split_array(inner):
            if "=" in pair:
                k, v = pair.split("=", 1)
                result[k.strip()] = _parse_value(v.strip())
        return result

    # Unquoted string
    return value


def _find_comment_start(value: str) -> int:
    """Find the start of an inline comment, respecting brackets."""
    depth = 0
    for i, char in enumerate(value):
        if char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "#" and depth == 0:
            return i
    return -1


def _split_array(s: str) -> List[str]:
    """Split array/table content, respecting nested structures and quoted strings."""
    items = []
    current = ""
    depth = 0
    in_string = False
    string_char = None

    for char in s:
        if in_string:
            current += char
            if char == string_char:
                in_string = False
                string_char = None
        elif char in "\"'":
            in_string = True
            string_char = char
            current += char
        elif char in "[{":
            depth += 1
            current += char
        elif char in "]}":
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            items.append(current.strip())
            current = ""
        else:
            current += char

    if current.strip():
        items.append(current.strip())

    return items


def _ensure_nested(d: Dict, keys: List[str]) -> None:
    """Ensure nested dictionary structure exists."""
    current = d
    for key in keys:
        if key not in current:
            current[key] = {}
        current = current[key]


def _get_nested(d: Dict, keys: List[str]) -> Dict:
    """Get nested dictionary by key path."""
    current = d
    for key in keys:
        current = current[key]
    return current


def merge_configs(defaults: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge user configuration over defaults.

    Args:
        defaults: Default configuration dictionary
        user: User configuration dictionary

    Returns:
        Merged configuration dictionary
    """
    result = {}

    # Start with all keys from defaults
    all_keys = set(defaults.keys()) | set(user.keys())

    for key in all_keys:
        default_val = defaults.get(key)
        user_val = user.get(key)

        if user_val is None:
            result[key] = default_val
        elif default_val is None:
            result[key] = user_val
        elif isinstance(default_val, dict) and isinstance(user_val, dict):
            result[key] = merge_configs(default_val, user_val)
        else:
            result[key] = user_val

    return result


def apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply environment variable overrides to configuration.

    Pattern: ELSPAIS_<SECTION>_<KEY> (e.g., ELSPAIS_DIRECTORIES_SPEC)

    Args:
        config: Configuration dictionary

    Returns:
        Configuration with environment overrides applied
    """
    prefix = "ELSPAIS_"

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue

        # Parse key: ELSPAIS_DIRECTORIES_SPEC -> directories.spec
        parts = key[len(prefix) :].lower().split("_")

        if len(parts) >= 2:
            section = parts[0]
            subkey = "_".join(parts[1:])

            if section in config and isinstance(config[section], dict):
                # Parse value (handle booleans, numbers)
                parsed: Any = value
                if value.lower() == "true":
                    parsed = True
                elif value.lower() == "false":
                    parsed = False
                elif value.isdigit():
                    parsed = int(value)

                config[section][subkey] = parsed

    return config


def validate_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate configuration for required fields and valid values.

    Args:
        config: Configuration dictionary

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Check required sections
    if "project" not in config:
        errors.append("Missing required section: [project]")
    elif "type" in config["project"]:
        project_type = config["project"]["type"]
        if project_type not in ["core", "associated"]:
            errors.append(f"Invalid project type: {project_type}. Must be 'core' or 'associated'")

    # Validate associated config when type is associated
    if config.get("project", {}).get("type") == "associated":
        associated = config.get("associated", {})
        if not associated.get("prefix"):
            errors.append("Associated repository requires associated.prefix to be set")

    return errors


def get_directories(
    config: Dict[str, Any],
    key: str,
    override: Optional[Path] = None,
    base_path: Optional[Path] = None,
    default: Optional[str] = None,
    require_exist: bool = True,
    recursive: bool = False,
    ignore: Optional[List[str]] = None,
) -> List[Path]:
    """Get directory paths from config, handling both strings and lists.

    Config can specify either a single directory or a list:
    - spec = "spec"
    - spec = ["spec", "spec/roadmap"]
    - code = ["apps", "packages", "server"]

    Args:
        config: Configuration dictionary
        key: Config key to look up under 'directories' section (e.g., "spec", "code")
        override: Explicit directory path override (e.g., from CLI --spec-dir)
        base_path: Base path to resolve relative directories (defaults to cwd)
        default: Default value if key not in config (defaults to key name)
        require_exist: If True, filter to only existing directories
        recursive: If True, include all subdirectories recursively
        ignore: List of directory names to ignore when recursing (e.g., ["node_modules", ".git"])

    Returns:
        List of directory paths (optionally filtered to existing ones)
    """
    if override:
        return [override]

    if base_path is None:
        base_path = Path.cwd()

    if default is None:
        default = key

    if ignore is None:
        ignore = config.get("directories", {}).get("ignore", [])

    dir_config = config.get("directories", {}).get(key, default)

    # Handle both string and list
    if isinstance(dir_config, str):
        dir_list = [dir_config]
    else:
        dir_list = list(dir_config)

    # Resolve paths
    result = []
    for dir_entry in dir_list:
        dir_path = base_path / dir_entry
        if require_exist and not (dir_path.exists() and dir_path.is_dir()):
            continue

        result.append(dir_path)

        # Recursively add subdirectories if requested
        if recursive and dir_path.exists() and dir_path.is_dir():
            for subdir in dir_path.rglob("*"):
                if subdir.is_dir():
                    # Check if any part of the path is in ignore list
                    if not any(ignored in subdir.parts for ignored in ignore):
                        result.append(subdir)

    return result


def get_code_directories(
    config: Dict[str, Any],
    base_path: Optional[Path] = None,
) -> List[Path]:
    """Get all code directories recursively, respecting ignore patterns.

    Convenience wrapper for get_directories with key="code" and recursive=True.

    Args:
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing code directory paths (including all subdirectories)
    """
    return get_directories(
        config=config,
        key="code",
        base_path=base_path,
        recursive=True,
    )


def get_spec_directories(
    spec_dir_override: Optional[Path],
    config: Dict[str, Any],
    base_path: Optional[Path] = None,
) -> List[Path]:
    """Get the spec directories from override or config.

    Convenience wrapper for get_directories with key="spec".

    Args:
        spec_dir_override: Explicit spec directory (e.g., from CLI --spec-dir)
        config: Configuration dictionary
        base_path: Base path to resolve relative directories (defaults to cwd)

    Returns:
        List of existing spec directory paths
    """
    return get_directories(
        config=config,
        key="spec",
        override=spec_dir_override,
        base_path=base_path,
        default="spec",
    )


def get_content_rules(
    config: Dict[str, Any],
    base_path: Optional[Path] = None,
) -> List[Path]:
    """Get content rule file paths from configuration.

    Args:
        config: Configuration dictionary
        base_path: Base path to resolve relative paths (defaults to cwd)

    Returns:
        List of content rule file paths (may not exist)
    """
    if base_path is None:
        base_path = Path.cwd()

    rules_config = config.get("rules", {})
    rule_paths = rules_config.get("content_rules", [])

    return [base_path / rel_path for rel_path in rule_paths]
