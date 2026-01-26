"""
Requirement loading utilities.

Centralized functions for loading requirements from repository paths.
This is the single source of truth for spec file loading - used by
context.py, validate.py, and other modules that need to parse requirements.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from elspais.config.loader import load_config
from elspais.core.models import ParseResult, Requirement
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


def create_parser(config: Dict[str, Any]) -> RequirementParser:
    """Create a RequirementParser from configuration.

    This is the standard way to create a parser with the correct
    pattern config and options from a configuration dict.

    Args:
        config: Configuration dict with 'patterns' and 'spec' sections

    Returns:
        Configured RequirementParser instance
    """
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    spec_config = config.get("spec", {})
    no_reference_values = spec_config.get("no_reference_values")
    return RequirementParser(pattern_config, no_reference_values=no_reference_values)


def get_skip_files(config: Dict[str, Any]) -> List[str]:
    """Get the skip_files list from configuration.

    Args:
        config: Configuration dict

    Returns:
        List of file patterns to skip
    """
    return config.get("spec", {}).get("skip_files", [])


def get_skip_dirs(config: Dict[str, Any]) -> List[str]:
    """Get the skip_dirs list from configuration.

    Args:
        config: Configuration dict

    Returns:
        List of directory names to skip (e.g., ["roadmap", "archive"])
    """
    return config.get("spec", {}).get("skip_dirs", [])


def parse_requirements_from_directories(
    spec_dirs: List[Path],
    config: Dict[str, Any],
    skip_files: Optional[List[str]] = None,
    skip_dirs: Optional[List[str]] = None,
    recursive: bool = True,
) -> ParseResult:
    """Parse requirements from multiple directories, returning ParseResult.

    Use this when you need access to parse warnings (e.g., for validation).
    For simpler use cases where you only need requirements, use
    load_requirements_from_directories().

    Args:
        spec_dirs: List of spec directories to parse
        config: Configuration dict
        skip_files: Optional list of files to skip (overrides config if provided)
        skip_dirs: Optional list of directories to skip (overrides config if provided)
        recursive: If True, search subdirectories recursively (default: True)

    Returns:
        ParseResult containing requirements dict and any warnings
    """
    parser = create_parser(config)
    if skip_files is None:
        skip_files = get_skip_files(config)
    if skip_dirs is None:
        skip_dirs = get_skip_dirs(config)

    return parser.parse_directories(
        spec_dirs, skip_files=skip_files, skip_dirs=skip_dirs, recursive=recursive
    )


def load_requirements_from_directories(
    spec_dirs: List[Path],
    config: Dict[str, Any],
    skip_files: Optional[List[str]] = None,
    skip_dirs: Optional[List[str]] = None,
    recursive: bool = True,
) -> Dict[str, Requirement]:
    """Load requirements from multiple directories.

    This is the high-level function for loading requirements when you
    don't need parse warnings.

    Args:
        spec_dirs: List of spec directories to parse
        config: Configuration dict
        skip_files: Optional list of files to skip (overrides config if provided)
        skip_dirs: Optional list of directories to skip (overrides config if provided)
        recursive: If True, search subdirectories recursively (default: True)

    Returns:
        Dict mapping requirement ID to Requirement object
    """
    result = parse_requirements_from_directories(
        spec_dirs, config, skip_files=skip_files, skip_dirs=skip_dirs, recursive=recursive
    )
    return result.requirements


def load_requirements_from_directory(
    spec_dir: Path,
    config: Dict[str, Any],
    skip_files: Optional[List[str]] = None,
    skip_dirs: Optional[List[str]] = None,
    recursive: bool = True,
) -> Dict[str, Requirement]:
    """Load requirements from a single directory.

    Convenience function for single-directory loading.

    Args:
        spec_dir: Spec directory to parse
        config: Configuration dict
        skip_files: Optional list of files to skip (overrides config if provided)
        skip_dirs: Optional list of directories to skip (overrides config if provided)
        recursive: If True, search subdirectories recursively (default: True)

    Returns:
        Dict mapping requirement ID to Requirement object
    """
    return load_requirements_from_directories(
        [spec_dir], config, skip_files=skip_files, skip_dirs=skip_dirs, recursive=recursive
    )


def load_requirements_from_repo(repo_path: Path, config: Dict[str, Any]) -> Dict[str, Requirement]:
    """Load requirements from any repository path.

    Args:
        repo_path: Path to the repository root
        config: Configuration dict (used as fallback if repo has no config)

    Returns:
        Dict mapping requirement ID to Requirement object
    """
    if not repo_path.exists():
        return {}

    # Find repo config
    repo_config_path = repo_path / ".elspais.toml"
    if repo_config_path.exists():
        repo_config = load_config(repo_config_path)
    else:
        repo_config = config  # Use same config

    spec_dir = repo_path / repo_config.get("directories", {}).get("spec", "spec")
    if not spec_dir.exists():
        return {}

    return load_requirements_from_directory(spec_dir, repo_config, recursive=True)
