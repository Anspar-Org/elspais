"""
Requirement loading utilities.

Centralized functions for loading requirements from repository paths.
"""

from pathlib import Path
from typing import Dict

from elspais.config.loader import load_config
from elspais.core.models import Requirement
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


def load_requirements_from_repo(repo_path: Path, config: Dict) -> Dict[str, Requirement]:
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

    pattern_config = PatternConfig.from_dict(repo_config.get("patterns", {}))
    spec_config = repo_config.get("spec", {})
    no_reference_values = spec_config.get("no_reference_values")
    parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)
    skip_files = spec_config.get("skip_files", [])

    try:
        return parser.parse_directory(spec_dir, skip_files=skip_files)
    except Exception:
        return {}
