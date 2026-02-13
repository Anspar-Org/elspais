# Implements: REQ-p00005-A
"""
elspais.associates - Associate repository configuration loading.

Provides functions for loading associate configurations from YAML files
and resolving associate spec directories.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Associate:
    """
    Represents an associate repository configuration.

    Attributes:
        name: Associate name (e.g., "callisto")
        code: Short code used in requirement IDs (e.g., "CAL")
        enabled: Whether this associate is enabled for scanning
        path: Default path relative to project root
        spec_path: Spec directory within associate path (e.g., "spec")
        local_path: Override path for local development (from .local.yml)
    """

    name: str
    code: str
    enabled: bool = True
    path: str = ""
    spec_path: str = "spec"
    local_path: str | None = None


# Alias for backwards compatibility
Sponsor = Associate


@dataclass
class AssociatesConfig:
    """
    Container for associate configuration.

    Attributes:
        associates: List of Associate objects
        config_file: Path to the associates config file
        local_dir: Default base directory for associate repos
    """

    associates: list[Associate] = field(default_factory=list)
    config_file: str = ""
    local_dir: str = "sponsor"

    # Alias property for backwards compatibility
    @property
    def sponsors(self) -> list[Associate]:
        return self.associates


# Alias for backwards compatibility
SponsorsConfig = AssociatesConfig


def parse_yaml(content: str) -> dict[str, Any]:
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
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[dict] | None = None
    current_dict: dict[str, Any] | None = None

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
    from elspais.config import _try_parse_numeric

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

    # Numeric
    numeric = _try_parse_numeric(value)
    if numeric is not None:
        return numeric

    return value


def load_associates_yaml(yaml_path: Path) -> dict[str, Any]:
    """
    Load associates configuration from a YAML file.

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
        yaml_path: Path to the associates YAML file

    Returns:
        Dictionary with associate configuration
    """
    if not yaml_path.exists():
        return {}

    content = yaml_path.read_text(encoding="utf-8")
    return _parse_associates_yaml(content)


# Alias for backwards compatibility
load_sponsors_yaml = load_associates_yaml


def _parse_associates_yaml(content: str) -> dict[str, Any]:
    """
    Parse associates YAML content with proper handling of nested lists.

    Args:
        content: YAML file content

    Returns:
        Parsed dictionary with associates configuration
    """
    result: dict[str, Any] = {"sponsors": {}}
    current_section = None
    current_list_key = None
    current_list: list[dict] = []
    current_item: dict | None = None
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


def load_associates_config(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> AssociatesConfig:
    """
    Load associate configurations from config files.

    Reads the main associates config file and applies local overrides.

    Args:
        config: Main elspais configuration dictionary
        base_path: Base path to resolve relative paths (defaults to cwd)

    Returns:
        AssociatesConfig with loaded associates
    """
    if base_path is None:
        base_path = Path.cwd()

    associates_config = AssociatesConfig()

    # Get sponsors section from config (keeping "sponsors" key for compatibility)
    sponsors_section = config.get("sponsors", {})
    config_file = sponsors_section.get("config_file", "")
    associates_config.config_file = config_file
    associates_config.local_dir = sponsors_section.get("local_dir", "sponsor")

    if not config_file:
        return associates_config

    # Load main sponsors config
    config_path = base_path / config_file
    main_config = load_associates_yaml(config_path)

    # Load local overrides if present
    local_config_path = config_path.with_suffix(".local.yml")
    local_overrides = load_associates_yaml(local_config_path)

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

        associate = Associate(
            name=name,
            code=sponsor_data.get("code", ""),
            enabled=sponsor_data.get("enabled", True),
            path=sponsor_data.get("path", ""),
            spec_path=sponsor_data.get("spec_path", "spec"),
            local_path=local_path,
        )
        associates_config.associates.append(associate)

    return associates_config


# Alias for backwards compatibility
load_sponsors_config = load_associates_config


def resolve_associate_spec_dir(
    associate: Associate,
    config: AssociatesConfig,
    base_path: Path | None = None,
) -> Path | None:
    """
    Resolve the spec directory path for an associate.

    Checks local_path override first, then default path.

    Args:
        associate: Associate configuration
        config: Overall associates configuration
        base_path: Base path to resolve relative paths (defaults to cwd)

    Returns:
        Path to associate spec directory, or None if not found
    """
    if base_path is None:
        base_path = Path.cwd()

    if not associate.enabled:
        return None

    # Check local_path override first
    if associate.local_path:
        spec_dir = Path(associate.local_path) / associate.spec_path
        if not spec_dir.is_absolute():
            spec_dir = base_path / spec_dir
        if spec_dir.exists() and spec_dir.is_dir():
            return spec_dir

    # Fall back to default path
    if associate.path:
        spec_dir = base_path / associate.path / associate.spec_path
        if spec_dir.exists() and spec_dir.is_dir():
            return spec_dir

    # Try local_dir / name / spec_path
    spec_dir = base_path / config.local_dir / associate.name / associate.spec_path
    if spec_dir.exists() and spec_dir.is_dir():
        return spec_dir

    return None


# Alias for backwards compatibility
resolve_sponsor_spec_dir = resolve_associate_spec_dir


def get_associate_spec_directories(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> list[Path]:
    """
    Get all associate spec directories from configuration.

    Args:
        config: Main elspais configuration dictionary
        base_path: Base path to resolve relative paths (defaults to cwd)

    Returns:
        List of existing associate spec directory paths
    """
    if base_path is None:
        base_path = Path.cwd()

    associates_config = load_associates_config(config, base_path)
    spec_dirs = []

    for associate in associates_config.associates:
        spec_dir = resolve_associate_spec_dir(associate, associates_config, base_path)
        if spec_dir:
            spec_dirs.append(spec_dir)

    return spec_dirs


# Alias for backwards compatibility
get_sponsor_spec_directories = get_associate_spec_directories


def discover_associate_from_path(
    repo_path: Path,
) -> Associate | None:
    """Discover associate identity by reading a repo's .elspais.toml.

    Reads {repo_path}/.elspais.toml and extracts associate configuration.
    Returns None (with warning) if the path is invalid, has no config,
    or isn't configured as an associated repository.

    Args:
        repo_path: Path to the associate repository root.

    Returns:
        Associate object if valid, None otherwise.
    """
    # Implements: REQ-p00005-D
    import sys

    repo_path = Path(repo_path)

    if not repo_path.exists():
        print(
            f"Associate path does not exist: {repo_path}",
            file=sys.stderr,
        )
        return None

    config_file = repo_path / ".elspais.toml"
    if not config_file.exists():
        print(
            f"No .elspais.toml found in associate path: {repo_path}",
            file=sys.stderr,
        )
        return None

    from elspais.config import parse_toml_document

    config = parse_toml_document(config_file.read_text(encoding="utf-8"))

    project_type = config.get("project", {}).get("type")
    if project_type != "associated":
        print(
            f"Repository at {repo_path} has project.type='{project_type}', "
            f"expected 'associated'",
            file=sys.stderr,
        )
        return None

    prefix = config.get("associated", {}).get("prefix")
    if not prefix:
        print(
            f"Associated repository at {repo_path} is missing " f"[associated] prefix",
            file=sys.stderr,
        )
        return None

    name = config.get("project", {}).get("name", repo_path.name)
    spec_path = config.get("directories", {}).get("spec", "spec")

    return Associate(
        name=name,
        code=prefix,
        enabled=True,
        path=str(repo_path),
        spec_path=spec_path,
    )


__all__ = [
    "Associate",
    "Sponsor",  # alias
    "AssociatesConfig",
    "SponsorsConfig",  # alias
    "parse_yaml",
    "load_associates_yaml",
    "load_sponsors_yaml",  # alias
    "load_associates_config",
    "load_sponsors_config",  # alias
    "resolve_associate_spec_dir",
    "resolve_sponsor_spec_dir",  # alias
    "get_associate_spec_directories",
    "get_sponsor_spec_directories",  # alias
    "discover_associate_from_path",
]
