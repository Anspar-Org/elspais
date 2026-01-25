"""
elspais.sponsors - Sponsor/associated repository configuration loading.

Provides functions for loading sponsor configurations from YAML files
and resolving sponsor spec directories.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Sponsor:
    """
    Represents a sponsor/associated repository configuration.

    Attributes:
        name: Sponsor name (e.g., "callisto")
        code: Short code used in requirement IDs (e.g., "CAL")
        enabled: Whether this sponsor is enabled for scanning
        path: Default path relative to project root
        spec_path: Spec directory within sponsor path (e.g., "spec")
        local_path: Override path for local development (from .local.yml)
    """

    name: str
    code: str
    enabled: bool = True
    path: str = ""
    spec_path: str = "spec"
    local_path: Optional[str] = None


@dataclass
class SponsorsConfig:
    """
    Container for sponsor configuration.

    Attributes:
        sponsors: List of Sponsor objects
        config_file: Path to the sponsors config file
        local_dir: Default base directory for sponsor repos
    """

    sponsors: List[Sponsor] = field(default_factory=list)
    config_file: str = ""
    local_dir: str = "sponsor"


def parse_yaml(content: str) -> Dict[str, Any]:
    """
    Parse simple YAML content into a dictionary.

    This is a zero-dependency YAML parser that handles basic structures:
    - Key-value pairs
    - Nested dictionaries
    - Lists of dictionaries
    - Strings, booleans, numbers

    Args:
        content: YAML file content

    Returns:
        Parsed dictionary
    """
    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_list: Optional[List[Dict]] = None
    current_dict: Optional[Dict[str, Any]] = None

    lines = content.split("\n")

    for line in lines:
        # Skip empty lines and comments
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Calculate indent level
        indent = len(line) - len(line.lstrip())

        # Handle list item (starts with -)
        if stripped.startswith("- "):
            item_content = stripped[2:].strip()

            # List item with inline key-value (e.g., "- name: value")
            if ":" in item_content:
                if current_list is None:
                    current_list = []
                    if current_key:
                        result[current_key] = current_list
                current_dict = {}
                current_list.append(current_dict)

                # Parse the key-value on the same line
                key, value = item_content.split(":", 1)
                key = key.strip()
                value = value.strip()
                if value:
                    current_dict[key] = _parse_yaml_value(value)
            continue

        # Handle key-value pair
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()

            if value:
                # Inline value
                parsed_value = _parse_yaml_value(value)
                if current_dict is not None and indent > 0:
                    current_dict[key] = parsed_value
                else:
                    result[key] = parsed_value
            else:
                # Nested structure starts
                current_key = key
                if current_dict is not None and indent > 0:
                    # Nested dict within list item
                    pass
                else:
                    # Top-level or second-level key
                    current_list = None
                    current_dict = None

    return result


def _parse_yaml_value(value: str) -> Any:
    """Parse a YAML value string."""
    value = value.strip()

    # Remove quotes if present
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
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

    return value


def load_sponsors_yaml(yaml_path: Path) -> Dict[str, Any]:
    """
    Load sponsors configuration from a YAML file.

    Handles the nested structure:
    ```yaml
    sponsors:
      local:
        - name: callisto
          code: CAL
          enabled: true
          path: sponsor/callisto
          spec_path: spec
    ```

    Args:
        yaml_path: Path to the sponsors YAML file

    Returns:
        Dictionary with sponsor configuration
    """
    if not yaml_path.exists():
        return {}

    content = yaml_path.read_text(encoding="utf-8")
    return _parse_sponsors_yaml(content)


def _parse_sponsors_yaml(content: str) -> Dict[str, Any]:
    """
    Parse sponsors YAML content with proper handling of nested lists.

    Args:
        content: YAML file content

    Returns:
        Parsed dictionary with sponsors configuration
    """
    result: Dict[str, Any] = {"sponsors": {}}
    current_section = None
    current_list_key = None
    current_list: List[Dict] = []
    current_item: Optional[Dict] = None
    current_dict_key = None  # For override files: sponsors: callisto: ...

    lines = content.split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        # Top-level key (sponsors:)
        if indent == 0 and stripped.endswith(":"):
            current_section = stripped[:-1]
            if current_section not in result:
                result[current_section] = {}
            current_list_key = None
            current_dict_key = None
            current_item = None
            continue

        # Second-level key (local:, or sponsor name for overrides)
        if indent == 2 and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()

            if not value:
                # Could be list (local:) or dict (callisto:) - depends on following content
                current_list_key = key
                current_list = []
                current_dict_key = key
                # Initialize as empty dict for now, will be replaced with list if needed
                if current_section:
                    result[current_section][key] = {}
            else:
                # Simple key-value at second level
                if current_section:
                    if current_section not in result:
                        result[current_section] = {}
                    result[current_section][key] = _parse_yaml_value(value)
            current_item = None
            continue

        # List item start (- name: value)
        if stripped.startswith("- "):
            item_content = stripped[2:].strip()
            current_item = {}

            # Convert dict to list if this is our first list item
            if current_list_key and current_section:
                if not isinstance(result[current_section].get(current_list_key), list):
                    result[current_section][current_list_key] = current_list

            current_list.append(current_item)

            if ":" in item_content:
                key, value = item_content.split(":", 1)
                current_item[key.strip()] = _parse_yaml_value(value.strip())
            continue

        # Item property (within a list item)
        if indent >= 6 and ":" in stripped and current_item is not None:
            key, value = stripped.split(":", 1)
            current_item[key.strip()] = _parse_yaml_value(value.strip())
            continue

        # Third-level key-value for override files (sponsors: callisto: local_path: ...)
        if indent == 4 and ":" in stripped and current_section and current_dict_key:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()

            if value:
                # This is a property of the dict entry
                if isinstance(result[current_section].get(current_dict_key), dict):
                    result[current_section][current_dict_key][key] = _parse_yaml_value(value)

    return result


def load_sponsors_config(
    config: Dict[str, Any],
    base_path: Optional[Path] = None,
) -> SponsorsConfig:
    """
    Load sponsor configurations from config files.

    Reads the main sponsors config file and applies local overrides.

    Args:
        config: Main elspais configuration dictionary
        base_path: Base path to resolve relative paths (defaults to cwd)

    Returns:
        SponsorsConfig with loaded sponsors
    """
    if base_path is None:
        base_path = Path.cwd()

    sponsors_config = SponsorsConfig()

    # Get sponsors section from config
    sponsors_section = config.get("sponsors", {})
    config_file = sponsors_section.get("config_file", "")
    sponsors_config.config_file = config_file
    sponsors_config.local_dir = sponsors_section.get("local_dir", "sponsor")

    if not config_file:
        return sponsors_config

    # Load main sponsors config
    config_path = base_path / config_file
    main_config = load_sponsors_yaml(config_path)

    # Load local overrides if present
    local_config_path = config_path.with_suffix(".local.yml")
    local_overrides = load_sponsors_yaml(local_config_path)

    # Parse sponsors from config
    sponsors_data = main_config.get("sponsors", {})

    # Handle "local" list format (the standard structure)
    sponsor_list = []
    if isinstance(sponsors_data, dict):
        # Check for "local" key containing list
        if "local" in sponsors_data and isinstance(sponsors_data["local"], list):
            sponsor_list = sponsors_data["local"]

    # Apply local overrides
    local_sponsors = local_overrides.get("sponsors", {})

    for sponsor_data in sponsor_list:
        name = sponsor_data.get("name", "")
        if not name:
            continue

        # Check for local override
        local_path = None
        if name in local_sponsors:
            local_override = local_sponsors[name]
            if isinstance(local_override, dict):
                local_path = local_override.get("local_path")

        sponsor = Sponsor(
            name=name,
            code=sponsor_data.get("code", ""),
            enabled=sponsor_data.get("enabled", True),
            path=sponsor_data.get("path", ""),
            spec_path=sponsor_data.get("spec_path", "spec"),
            local_path=local_path,
        )
        sponsors_config.sponsors.append(sponsor)

    return sponsors_config


def resolve_sponsor_spec_dir(
    sponsor: Sponsor,
    config: SponsorsConfig,
    base_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    Resolve the spec directory path for a sponsor.

    Checks local_path override first, then default path.

    Args:
        sponsor: Sponsor configuration
        config: Overall sponsors configuration
        base_path: Base path to resolve relative paths (defaults to cwd)

    Returns:
        Path to sponsor spec directory, or None if not found
    """
    if base_path is None:
        base_path = Path.cwd()

    if not sponsor.enabled:
        return None

    # Check local_path override first
    if sponsor.local_path:
        spec_dir = Path(sponsor.local_path) / sponsor.spec_path
        if not spec_dir.is_absolute():
            spec_dir = base_path / spec_dir
        if spec_dir.exists() and spec_dir.is_dir():
            return spec_dir

    # Fall back to default path
    if sponsor.path:
        spec_dir = base_path / sponsor.path / sponsor.spec_path
        if spec_dir.exists() and spec_dir.is_dir():
            return spec_dir

    # Try local_dir / name / spec_path
    spec_dir = base_path / config.local_dir / sponsor.name / sponsor.spec_path
    if spec_dir.exists() and spec_dir.is_dir():
        return spec_dir

    return None


def get_sponsor_spec_directories(
    config: Dict[str, Any],
    base_path: Optional[Path] = None,
) -> List[Path]:
    """
    Get all sponsor spec directories from configuration.

    Args:
        config: Main elspais configuration dictionary
        base_path: Base path to resolve relative paths (defaults to cwd)

    Returns:
        List of existing sponsor spec directory paths
    """
    if base_path is None:
        base_path = Path.cwd()

    sponsors_config = load_sponsors_config(config, base_path)
    spec_dirs = []

    for sponsor in sponsors_config.sponsors:
        spec_dir = resolve_sponsor_spec_dir(sponsor, sponsors_config, base_path)
        if spec_dir:
            spec_dirs.append(spec_dir)

    return spec_dirs
