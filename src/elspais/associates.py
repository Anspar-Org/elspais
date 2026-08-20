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


def spec_directory_name(config: dict) -> str:
    """The directory a repository keeps its spec files in.

    One reading of `[scanning.spec].directories` for everything that asks
    where a federated repository's specs are: the scan that collects them
    and the health check that reports on them answered this separately
    before, and a repository that configured something other than the
    default was described differently by each.
    """
    directories = (config or {}).get("scanning", {}).get("spec", {}).get("directories", [])
    return directories[0] if directories else "spec"


def get_associate_spec_directories(
    config: dict[str, Any],
    base_path: Path | None = None,
) -> tuple[list[Path], list[str]]:
    """
    Get the spec directory of every federation member other than the caller.

    Membership comes from ``plan_federation()``, the single authority on
    which repositories a federation contains, so a repository reached only
    through an associate's own declarations is covered here exactly like one
    the invoking config names directly.

    Args:
        config: Main elspais configuration dictionary
        base_path: Base path to resolve relative paths (defaults to cwd)

    Returns:
        Tuple of (spec_dirs, errors). errors carries a message for every
        federation member that could not be loaded or whose spec directory
        is missing, and for a declaration set that cannot be resolved at all
        (a cycle, or two repositories federated under one name).
    """
    # Implements: REQ-p00005-F, REQ-d00202-D
    if base_path is None:
        base_path = Path.cwd()

    from elspais.graph.federation_plan import plan_federation_or_error

    spec_dirs: list[Path] = []
    errors: list[str] = []

    # This is a scan with an error channel, so a declaration set that cannot be
    # walked at all is reported through it rather than raised at every caller.
    plan, plan_error = plan_federation_or_error(config, base_path)
    if plan_error is not None:
        return [], [plan_error]

    # Element 0 is the invoking repository, which is not an associate of itself.
    for member in plan[1:]:
        if member.config is None:
            errors.append(member.error or f"Associate could not be loaded: {member.repo_root}")
            continue
        spec_dir = member.repo_root / spec_directory_name(member.config)
        if spec_dir.is_dir():
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

    from tomlkit.exceptions import TOMLKitError

    from elspais.config import load_config

    # Route through the single canonical loader so migrations apply
    # consistently.
    # Implements: REQ-d00202-I
    # Tolerated failure, scoped to config parse/validation errors: a sibling
    # with a stale or incompatible .elspais.toml is reported as unloadable
    # (path + reason), never raised — discovery scans must survive it.
    # ValueError covers pydantic ValidationError and the loader's own
    # missing-name/namespace checks; TOMLKitError covers syntax errors.
    try:
        config = load_config(config_file)
    except (ValueError, TOMLKitError) as exc:
        return f"Cannot load associate config in {repo_path}: {exc}"

    project = config.get("project", {})
    name = project.get("name") or repo_path.name
    # load_config refuses a config without a non-empty namespace, so this
    # is present by the time the candidate has loaded at all.
    namespace = project["namespace"]
    spec_path = spec_directory_name(config)

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
