"""Graph Factory - Shared utility for building TraceGraph from spec files.

This module provides a single entry point for all commands to build a TraceGraph
from configuration and spec directories. Commands should use this instead of
implementing their own file reading logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from elspais.config import get_config, get_spec_directories
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.deserializer import DomainFile
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.code import CodeParser
from elspais.graph.parsers.journey import JourneyParser
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.parsers.test import TestParser
from elspais.utilities.patterns import PatternConfig


def build_graph(
    config: dict[str, Any] | None = None,
    spec_dirs: list[Path] | None = None,
    config_path: Path | None = None,
    repo_root: Path | None = None,
) -> TraceGraph:
    """Build a TraceGraph from spec directories.

    This is the standard way for commands to obtain a TraceGraph.
    It handles:
    - Configuration loading (auto-discovery or explicit)
    - Spec directory resolution
    - Parser registration
    - Graph construction

    Args:
        config: Pre-loaded config dict (optional).
        spec_dirs: Explicit spec directories (optional).
        config_path: Path to config file (optional).
        repo_root: Repository root for relative paths (defaults to cwd).

    Returns:
        Complete TraceGraph with all requirements linked.

    Priority:
        spec_dirs > config > config_path > defaults
    """
    # Default repo_root
    if repo_root is None:
        repo_root = Path.cwd()

    # 1. Resolve configuration
    if config is None:
        config = get_config(config_path, repo_root)

    # 2. Resolve spec directories
    if spec_dirs is None:
        spec_dirs = get_spec_directories(None, config, repo_root)

    # 3. Create parser registry with ALL parsers
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    registry = ParserRegistry()
    registry.register(RequirementParser(pattern_config))
    registry.register(JourneyParser())
    registry.register(CodeParser())
    registry.register(TestParser())

    # 4. Build graph from all spec directories
    builder = GraphBuilder(repo_root=repo_root)

    # Get skip configuration
    spec_config = config.get("spec", {})
    skip_dirs = spec_config.get("skip_dirs", [])
    skip_files = spec_config.get("skip_files", [])

    for spec_dir in spec_dirs:
        # Get file patterns from config
        file_patterns = spec_config.get("patterns", ["*.md"])
        domain_file = DomainFile(
            spec_dir,
            patterns=file_patterns,
            recursive=True,
            skip_dirs=skip_dirs,
            skip_files=skip_files,
        )

        for parsed_content in domain_file.deserialize(registry):
            builder.add_parsed_content(parsed_content)

    return builder.build()


__all__ = ["build_graph"]
