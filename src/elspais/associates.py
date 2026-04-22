# Implements: REQ-p00005-A
"""
elspais.associates - Associate repository configuration and discovery.

Provides functions for discovering associate repositories from their
.elspais.toml config and resolving associate spec directories.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from elspais.config.schema import ElspaisConfig

_SCHEMA_FIELDS = {f.alias or name for name, f in ElspaisConfig.model_fields.items()} | set(
    ElspaisConfig.model_fields.keys()
)


def _validate_config(config: dict[str, Any]) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig, stripping non-schema keys."""
    filtered = {k: v for k, v in config.items() if k in _SCHEMA_FIELDS}
    assoc = filtered.get("associates")
    if isinstance(assoc, dict) and "paths" in assoc:
        filtered.pop("associates", None)
    return ElspaisConfig.model_validate(filtered)


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
        local_path: Override path for local development
    """

    name: str
    code: str
    enabled: bool = True
    path: str = ""
    spec_path: str = "spec"
    local_path: str | None = None


def get_associate_spec_directories(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> tuple[list[Path], list[str]]:
    """
    Get all associate spec directories from configuration.

    Loads named associates from [associates.<name>] config sections.

    Args:
        config: Main elspais configuration dictionary
        base_path: Base path to resolve relative paths (defaults to cwd)

    Returns:
        Tuple of (spec_dirs, errors). errors contains messages for any
        configured associate paths that could not be resolved.
    """
    # Implements: REQ-p00005-F
    if base_path is None:
        base_path = Path.cwd()

    spec_dirs = []
    errors: list[str] = []

    # 0. Resolve associates from typed config
    typed_config = _validate_config(config)

    # 1. Path-based loading from [associates] config (new format: named entries)
    for _assoc_name, assoc_entry in typed_config.associates.items():
        repo_path = Path(assoc_entry.path)
        if not repo_path.is_absolute():
            repo_path = base_path / repo_path
        result = discover_associate_from_path(repo_path)
        if isinstance(result, str):
            errors.append(result)
            continue
        spec_dir = repo_path / result.spec_path
        if spec_dir.exists() and spec_dir.is_dir():
            spec_dirs.append(spec_dir)
        else:
            errors.append(f"Spec directory not found: {spec_dir}")

    return spec_dirs, errors


def discover_associate_from_path(
    repo_path: Path,
) -> Associate | str:
    """Discover associate identity by reading a repo's .elspais.toml.

    Reads {repo_path}/.elspais.toml and extracts associate configuration.
    Returns an error message string if the path is invalid or has no config.

    Args:
        repo_path: Path to the associate repository root.

    Returns:
        Associate object if valid, error message string otherwise.
    """
    # Implements: REQ-p00005-D
    repo_path = Path(repo_path)

    if not repo_path.exists():
        return f"Associate path does not exist: {repo_path}"

    config_file = repo_path / ".elspais.toml"
    if not config_file.exists():
        return f"No .elspais.toml found in associate path: {repo_path}"

    from elspais.config import load_config

    # Route through the single canonical loader so migrations and field
    # strips (e.g. legacy rules.format.allowed_statuses) apply consistently.
    config = load_config(config_file)

    project = config.get("project", {})
    scanning_spec = config.get("scanning", {}).get("spec", {})
    spec_dirs = scanning_spec.get("directories", [])
    name = project.get("name") or repo_path.name
    namespace = project.get("namespace", "")
    spec_path = spec_dirs[0] if spec_dirs else "spec"

    return Associate(
        name=name,
        code=namespace,
        enabled=True,
        path=str(repo_path),
        spec_path=spec_path,
    )


__all__ = [
    "Associate",
    "get_associate_spec_directories",
    "discover_associate_from_path",
]
