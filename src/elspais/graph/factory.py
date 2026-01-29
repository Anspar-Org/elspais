"""Graph Factory - Shared utility for building TraceGraph from spec files.

This module provides a single entry point for all commands to build a TraceGraph
from configuration and spec directories. Commands should use this instead of
implementing their own file reading logic.
"""

from __future__ import annotations

from glob import glob
from pathlib import Path
from typing import Any

from elspais.associates import get_associate_spec_directories
from elspais.config import get_config, get_spec_directories
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.deserializer import DomainFile
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.code import CodeParser
from elspais.graph.parsers.journey import JourneyParser
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.parsers.results import JUnitXMLParser, PytestJSONParser
from elspais.graph.parsers.test import TestParser
from elspais.utilities.patterns import PatternConfig
from elspais.utilities.reference_config import ReferenceResolver


def _find_repo_root(spec_dir: Path) -> Path | None:
    """Find the repository root containing .elspais.toml for a spec directory.

    Walks up the directory tree looking for .elspais.toml.

    Args:
        spec_dir: The spec directory path

    Returns:
        Path to repo root, or None if not found
    """
    current = spec_dir.resolve()
    while current != current.parent:
        if (current / ".elspais.toml").exists():
            return current
        current = current.parent
    return None


def _create_registry_for_spec_dir(
    spec_dir: Path,
    default_pattern_config: PatternConfig,
    default_reference_resolver: ReferenceResolver,
) -> ParserRegistry:
    """Create a parser registry for a spec directory.

    If the spec directory is in a different repo (has its own .elspais.toml),
    loads that repo's config and creates a registry with its pattern config
    and reference resolver. Otherwise uses the defaults.

    Args:
        spec_dir: The spec directory path
        default_pattern_config: The default pattern config from main repo
        default_reference_resolver: The default reference resolver from main repo

    Returns:
        ParserRegistry configured for this spec directory
    """
    registry = ParserRegistry()

    # Check if this spec dir is in a different repo with its own config
    repo_root = _find_repo_root(spec_dir)
    if repo_root:
        config_path = repo_root / ".elspais.toml"
        if config_path.exists():
            repo_config = get_config(config_path, repo_root)
            patterns_dict = repo_config.get("patterns", {})
            pattern_config = PatternConfig.from_dict(patterns_dict)
            # Build reference resolver from this repo's config
            reference_resolver = ReferenceResolver.from_config(repo_config.get("references", {}))
            registry.register(RequirementParser(pattern_config))
            registry.register(JourneyParser())
            registry.register(CodeParser(pattern_config, reference_resolver))
            registry.register(TestParser(pattern_config, reference_resolver))
            return registry

    # Fall back to defaults
    registry.register(RequirementParser(default_pattern_config))
    registry.register(JourneyParser())
    registry.register(CodeParser(default_pattern_config, default_reference_resolver))
    registry.register(TestParser(default_pattern_config, default_reference_resolver))
    return registry


def build_graph(
    config: dict[str, Any] | None = None,
    spec_dirs: list[Path] | None = None,
    config_path: Path | None = None,
    repo_root: Path | None = None,
    scan_code: bool = True,
    scan_tests: bool = True,
    scan_sponsors: bool = True,
) -> TraceGraph:
    """Build a TraceGraph from spec directories.

    This is the standard way for commands to obtain a TraceGraph.
    It handles:
    - Configuration loading (auto-discovery or explicit)
    - Spec directory resolution
    - Sponsor/associate spec directory resolution
    - Parser registration
    - Graph construction
    - Code and test directory scanning (configurable)

    Args:
        config: Pre-loaded config dict (optional).
        spec_dirs: Explicit spec directories (optional).
        config_path: Path to config file (optional).
        repo_root: Repository root for relative paths (defaults to cwd).
        scan_code: Whether to scan code directories from traceability.scan_patterns.
        scan_tests: Whether to scan test directories from testing.test_dirs.
        scan_sponsors: Whether to scan sponsor/associate spec directories.

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

    # 2b. Add sponsor/associate spec directories if enabled
    if scan_sponsors:
        sponsor_dirs = get_associate_spec_directories(config, repo_root)
        spec_dirs = list(spec_dirs) + sponsor_dirs

    # 3. Create default pattern config and reference resolver
    default_pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    default_reference_resolver = ReferenceResolver.from_config(config.get("references", {}))

    # Registry for code files (code parser only)
    code_registry = ParserRegistry()
    code_registry.register(CodeParser(default_pattern_config, default_reference_resolver))

    # Registry for test files (test parser only)
    test_registry = ParserRegistry()
    test_registry.register(TestParser(default_pattern_config, default_reference_resolver))

    # 4. Build graph from all spec directories
    builder = GraphBuilder(repo_root=repo_root)

    # Get skip configuration
    spec_config = config.get("spec", {})
    skip_dirs = spec_config.get("skip_dirs", [])
    skip_files = spec_config.get("skip_files", [])

    for spec_dir in spec_dirs:
        # Create registry with appropriate pattern config for this spec dir
        # (uses sponsor repo's config if applicable)
        spec_registry = _create_registry_for_spec_dir(
            spec_dir, default_pattern_config, default_reference_resolver
        )

        # Get file patterns from config
        file_patterns = spec_config.get("patterns", ["*.md"])
        domain_file = DomainFile(
            spec_dir,
            patterns=file_patterns,
            recursive=True,
            skip_dirs=skip_dirs,
            skip_files=skip_files,
        )

        for parsed_content in domain_file.deserialize(spec_registry):
            builder.add_parsed_content(parsed_content)

    # 5. Scan code directories from traceability.scan_patterns
    if scan_code:
        traceability_config = config.get("traceability", {})
        scan_patterns = traceability_config.get("scan_patterns", [])

        for pattern in scan_patterns:
            # Resolve glob pattern relative to repo_root
            matched_files = glob(str(repo_root / pattern), recursive=True)
            for file_path in matched_files:
                path = Path(file_path)
                if path.is_file():
                    domain_file = DomainFile(path)
                    for parsed_content in domain_file.deserialize(code_registry):
                        builder.add_parsed_content(parsed_content)

    # 6. Scan test directories from testing config
    if scan_tests:
        testing_config = config.get("testing", {})
        if testing_config.get("enabled", False):
            test_dirs = testing_config.get("test_dirs", [])
            test_patterns = testing_config.get("patterns", ["*_test.*", "test_*.*"])

            for dir_pattern in test_dirs:
                # Resolve glob pattern to get directories
                matched_dirs = glob(str(repo_root / dir_pattern), recursive=True)
                for dir_path in matched_dirs:
                    path = Path(dir_path)
                    if path.is_dir():
                        domain_file = DomainFile(
                            path,
                            patterns=test_patterns,
                            recursive=True,
                        )
                        for parsed_content in domain_file.deserialize(test_registry):
                            builder.add_parsed_content(parsed_content)

            # 6b. Scan test result files (JUnit XML, pytest JSON)
            result_files = testing_config.get("result_files", [])
            if result_files:
                # Create parsers for result files (these have a different interface)
                junit_parser = JUnitXMLParser(
                    pattern_config=default_pattern_config,
                    reference_resolver=default_reference_resolver,
                    base_path=repo_root,
                )
                pytest_parser = PytestJSONParser(
                    pattern_config=default_pattern_config,
                    reference_resolver=default_reference_resolver,
                    base_path=repo_root,
                )

                for file_pattern in result_files:
                    # Resolve glob pattern relative to repo_root
                    matched_files = glob(str(repo_root / file_pattern), recursive=True)
                    for file_path in matched_files:
                        path = Path(file_path)
                        if path.is_file():
                            content = path.read_text(encoding="utf-8")
                            source_path = str(path)

                            # Choose parser based on file extension
                            results = []
                            if path.suffix.lower() == ".xml":
                                results = junit_parser.parse(content, source_path)
                            elif path.suffix.lower() == ".json":
                                results = pytest_parser.parse(content, source_path)

                            # Convert results to ParsedContent for the builder
                            for result in results:
                                from elspais.graph.deserializer import (
                                    DomainContext,
                                    ParsedContentWithContext,
                                )

                                ctx = DomainContext(
                                    source_type="file",
                                    source_id=source_path,
                                    metadata={"path": path},
                                )

                                parsed_content = ParsedContentWithContext(
                                    content_type="test_result",
                                    start_line=1,
                                    end_line=1,
                                    raw_text="",
                                    parsed_data=result,
                                    source_context=ctx,
                                )
                                builder.add_parsed_content(parsed_content)

    return builder.build()


__all__ = ["build_graph"]
