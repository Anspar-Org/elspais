"""
elspais.commands.config_cmd - Configuration management command.

View and modify .elspais.toml configuration.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from elspais.config.loader import (
    find_config_file,
    load_config,
    merge_configs,
    parse_toml,
)
from elspais.config.defaults import DEFAULT_CONFIG


def run(args: argparse.Namespace) -> int:
    """
    Run the config command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success)
    """
    action = getattr(args, "config_action", None)

    if action == "show":
        return cmd_show(args)
    elif action == "get":
        return cmd_get(args)
    elif action == "set":
        return cmd_set(args)
    elif action == "unset":
        return cmd_unset(args)
    elif action == "add":
        return cmd_add(args)
    elif action == "remove":
        return cmd_remove(args)
    elif action == "path":
        return cmd_path(args)
    else:
        # Default to show
        return cmd_show(args)


def cmd_show(args: argparse.Namespace) -> int:
    """Show current configuration."""
    config_path = _get_config_path(args)

    if not config_path:
        print("No configuration file found. Run 'elspais init' to create one.")
        return 1

    config = load_config(config_path)
    section = getattr(args, "section", None)

    if section:
        value = _get_by_path(config, section)
        if value is None:
            print(f"Section not found: {section}", file=sys.stderr)
            return 1
        _print_value(value, section)
    else:
        if getattr(args, "json", False):
            print(json.dumps(config, indent=2))
        else:
            _print_config(config)

    return 0


def cmd_get(args: argparse.Namespace) -> int:
    """Get a specific configuration value."""
    config_path = _get_config_path(args)

    if not config_path:
        print("No configuration file found.", file=sys.stderr)
        return 1

    config = load_config(config_path)
    key = args.key

    value = _get_by_path(config, key)
    if value is None:
        # Check if it's truly None vs not found
        parts = key.split(".")
        current = config
        for part in parts[:-1]:
            if part not in current:
                print(f"Key not found: {key}", file=sys.stderr)
                return 1
            current = current[part]
        if parts[-1] not in current:
            print(f"Key not found: {key}", file=sys.stderr)
            return 1

    if getattr(args, "json", False):
        print(json.dumps(value))
    else:
        _print_value(value)

    return 0


def cmd_set(args: argparse.Namespace) -> int:
    """Set a configuration value."""
    config_path = _get_config_path(args)

    if not config_path:
        config_path = Path.cwd() / ".elspais.toml"
        print(f"Creating new configuration file: {config_path}")

    key = args.key
    value = args.value

    # Parse value with type inference
    parsed_value = _parse_cli_value(value)

    # Load existing user config (not merged with defaults)
    user_config = _load_user_config(config_path)

    # Set the value
    _set_by_path(user_config, key, parsed_value)

    # Write back
    _write_config(config_path, user_config)

    if not args.quiet:
        print(f"Set {key} = {_format_value(parsed_value)}")

    return 0


def cmd_unset(args: argparse.Namespace) -> int:
    """Remove a configuration key."""
    config_path = _get_config_path(args)

    if not config_path:
        print("No configuration file found.", file=sys.stderr)
        return 1

    key = args.key
    user_config = _load_user_config(config_path)

    if not _unset_by_path(user_config, key):
        print(f"Key not found: {key}", file=sys.stderr)
        return 1

    _write_config(config_path, user_config)

    if not args.quiet:
        print(f"Unset {key}")

    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """Add a value to an array configuration."""
    config_path = _get_config_path(args)

    if not config_path:
        config_path = Path.cwd() / ".elspais.toml"

    key = args.key
    value = _parse_cli_value(args.value)

    user_config = _load_user_config(config_path)

    # Get or create the array
    current = _get_by_path(user_config, key)

    if current is None:
        # Check defaults for existing array
        default_val = _get_by_path(DEFAULT_CONFIG, key)
        if isinstance(default_val, list):
            current = list(default_val)  # Copy default
        else:
            current = []
    elif not isinstance(current, list):
        print(f"Error: {key} is not an array", file=sys.stderr)
        return 1

    if value in current:
        print(f"Value already exists in {key}: {_format_value(value)}")
        return 0

    current.append(value)
    _set_by_path(user_config, key, current)
    _write_config(config_path, user_config)

    if not args.quiet:
        print(f"Added {_format_value(value)} to {key}")

    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    """Remove a value from an array configuration."""
    config_path = _get_config_path(args)

    if not config_path:
        print("No configuration file found.", file=sys.stderr)
        return 1

    key = args.key
    value = _parse_cli_value(args.value)

    user_config = _load_user_config(config_path)
    merged_config = load_config(config_path)

    # Get current merged value to see what's there
    current = _get_by_path(merged_config, key)

    if current is None or not isinstance(current, list):
        print(f"Error: {key} is not an array or doesn't exist", file=sys.stderr)
        return 1

    if value not in current:
        print(f"Value not in {key}: {_format_value(value)}", file=sys.stderr)
        return 1

    # Get user config array or copy from defaults
    user_array = _get_by_path(user_config, key)
    if user_array is None:
        user_array = list(current)  # Copy merged

    user_array = [v for v in user_array if v != value]
    _set_by_path(user_config, key, user_array)
    _write_config(config_path, user_config)

    if not args.quiet:
        print(f"Removed {_format_value(value)} from {key}")

    return 0


def cmd_path(args: argparse.Namespace) -> int:
    """Show the path to the configuration file."""
    config_path = _get_config_path(args)

    if config_path:
        print(config_path)
        return 0
    else:
        print("No configuration file found.", file=sys.stderr)
        return 1


# Helper functions

def _get_config_path(args: argparse.Namespace) -> Optional[Path]:
    """Get configuration file path from args or by discovery."""
    if hasattr(args, "config") and args.config:
        return args.config
    return find_config_file(Path.cwd())


def _load_user_config(config_path: Path) -> Dict[str, Any]:
    """Load user configuration without merging with defaults."""
    if config_path.exists():
        return parse_toml(config_path.read_text(encoding="utf-8"))
    return {}


def _get_by_path(config: Dict[str, Any], path: str) -> Any:
    """Get a value from config using dot-notation path."""
    parts = path.split(".")
    current = config
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_by_path(config: Dict[str, Any], path: str, value: Any) -> None:
    """Set a value in config using dot-notation path."""
    parts = path.split(".")
    current = config
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _unset_by_path(config: Dict[str, Any], path: str) -> bool:
    """Remove a key from config. Returns True if found and removed."""
    parts = path.split(".")
    current = config
    for part in parts[:-1]:
        if part not in current:
            return False
        current = current[part]
    if parts[-1] in current:
        del current[parts[-1]]
        return True
    return False


def _parse_cli_value(value: str) -> Any:
    """Parse a CLI value string with type inference."""
    # Boolean
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # Integer
    try:
        return int(value)
    except ValueError:
        pass

    # Float
    try:
        return float(value)
    except ValueError:
        pass

    # JSON array or object
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

    # String
    return value


def _format_value(value: Any) -> str:
    """Format a value for display."""
    if isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (list, dict)):
        return json.dumps(value)
    else:
        return str(value)


def _print_value(value: Any, prefix: str = "") -> None:
    """Print a configuration value."""
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else k
            _print_value(v, key)
    elif isinstance(value, list):
        if prefix:
            print(f"{prefix} = {json.dumps(value)}")
        else:
            print(json.dumps(value))
    elif isinstance(value, bool):
        if prefix:
            print(f"{prefix} = {'true' if value else 'false'}")
        else:
            print('true' if value else 'false')
    elif isinstance(value, str):
        if prefix:
            print(f'{prefix} = "{value}"')
        else:
            print(value)
    else:
        if prefix:
            print(f"{prefix} = {value}")
        else:
            print(value)


def _print_config(config: Dict[str, Any], indent: int = 0) -> None:
    """Pretty print configuration in TOML-like format."""
    for key, value in config.items():
        if isinstance(value, dict):
            print(f"\n[{key}]")
            _print_section(value, key)
        else:
            print(f"{key} = {_format_value(value)}")


def _print_section(section: Dict[str, Any], path: str, indent: int = 0) -> None:
    """Print a configuration section."""
    simple_items = []
    nested_items = []

    for key, value in section.items():
        if isinstance(value, dict):
            nested_items.append((key, value))
        else:
            simple_items.append((key, value))

    # Print simple items first
    for key, value in simple_items:
        print(f"{key} = {_format_value(value)}")

    # Then nested sections
    for key, value in nested_items:
        new_path = f"{path}.{key}"
        print(f"\n[{new_path}]")
        _print_section(value, new_path)


def _write_config(config_path: Path, config: Dict[str, Any]) -> None:
    """Write configuration to TOML file."""
    content = serialize_toml(config)
    config_path.write_text(content, encoding="utf-8")


def serialize_toml(config: Dict[str, Any], prefix: str = "") -> str:
    """
    Serialize a dictionary to TOML format.

    Args:
        config: Configuration dictionary
        prefix: Section prefix for nested tables

    Returns:
        TOML formatted string
    """
    lines: List[str] = []

    # Separate simple values and nested tables
    simple_items: List[Tuple[str, Any]] = []
    nested_items: List[Tuple[str, Dict]] = []

    for key, value in config.items():
        if isinstance(value, dict) and not _is_inline_table(value):
            nested_items.append((key, value))
        else:
            simple_items.append((key, value))

    # Write simple items
    for key, value in simple_items:
        lines.append(f"{key} = {_serialize_value(value)}")

    # Write nested tables
    for key, value in nested_items:
        section_name = f"{prefix}.{key}" if prefix else key
        lines.append("")
        lines.append(f"[{section_name}]")
        nested_content = serialize_toml(value, section_name)
        # Remove leading newline from nested content
        nested_content = nested_content.lstrip("\n")
        if nested_content:
            lines.append(nested_content)

    result = "\n".join(lines)
    # Clean up multiple consecutive empty lines
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    return result


def _is_inline_table(value: Dict) -> bool:
    """Check if a dict should be serialized as inline table."""
    # Use inline for simple, small tables without nested dicts
    if len(value) > 4:
        return False
    for v in value.values():
        if isinstance(v, dict):
            return False
        if isinstance(v, list) and len(v) > 3:
            return False
    return True


def _serialize_value(value: Any) -> str:
    """Serialize a single value to TOML format."""
    if value is None:
        return '""'  # TOML doesn't have null, use empty string
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        return str(value)
    elif isinstance(value, str):
        # Escape quotes and backslashes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    elif isinstance(value, list):
        items = [_serialize_value(v) for v in value]
        # Check if it fits on one line
        single_line = f"[{', '.join(items)}]"
        if len(single_line) < 80:
            return single_line
        # Multi-line format
        return "[\n    " + ",\n    ".join(items) + ",\n]"
    elif isinstance(value, dict):
        items = [f"{k} = {_serialize_value(v)}" for k, v in value.items()]
        return "{ " + ", ".join(items) + " }"
    else:
        return str(value)
