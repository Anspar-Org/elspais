# Implements: REQ-d00054-A, REQ-d00054-B, REQ-d00054-C
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
from elspais.config import get_code_directories, get_config, get_ignore_config, get_spec_directories
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

# Default file patterns for [directories].code scanning.
# Covers all languages listed in the multi-language comment support table.
DEFAULT_CODE_PATTERNS = [
    "*.py",
    "*.js",
    "*.ts",
    "*.jsx",
    "*.tsx",
    "*.java",
    "*.c",
    "*.cpp",
    "*.h",
    "*.hpp",
    "*.go",
    "*.rs",
    "*.rb",
    "*.sh",
    "*.bash",
    "*.sql",
    "*.lua",
    "*.yml",
    "*.yaml",
    "*.dart",
    "*.swift",
    "*.kt",
    "*.css",
    "*.scss",
]


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


# Implements: REQ-p00005-B
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
    hash_mode = config.get("validation", {}).get("hash_mode", "normalized-text")
    graph_config = config.get("graph", {})
    satellite_kinds = graph_config.get("satellite_kinds", None)
    builder = GraphBuilder(
        repo_root=repo_root, hash_mode=hash_mode, satellite_kinds=satellite_kinds
    )

    # Get ignore configuration for filtering spec files
    ignore_config = get_ignore_config(config)

    # Get skip configuration (legacy, for backward compatibility)
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
            # Check if source should be ignored using [ignore].spec patterns
            source_path = parsed_content.source_context.metadata.get("path")
            if source_path and ignore_config.should_ignore(source_path, scope="spec"):
                continue
            builder.add_parsed_content(parsed_content)

    # 5. Scan code files from [traceability].scan_patterns AND [directories].code
    if scan_code:
        scanned_code_files: set[str] = set()

        # 5a. Explicit scan_patterns (existing behavior)
        traceability_config = config.get("traceability", {})
        scan_patterns = traceability_config.get("scan_patterns", [])

        for pattern in scan_patterns:
            # Resolve glob pattern relative to repo_root
            matched_files = glob(str(repo_root / pattern), recursive=True)
            for file_path in matched_files:
                path = Path(file_path)
                if path.is_file():
                    resolved = str(path.resolve())
                    scanned_code_files.add(resolved)
                    domain_file = DomainFile(path)
                    for parsed_content in domain_file.deserialize(code_registry):
                        builder.add_parsed_content(parsed_content)

        # 5b. [directories].code with default file patterns
        code_dirs = get_code_directories(config, repo_root)
        ignore_dirs = config.get("directories", {}).get("ignore", [])

        for code_dir in code_dirs:
            domain_file = DomainFile(
                code_dir,
                patterns=DEFAULT_CODE_PATTERNS,
                recursive=True,
                skip_dirs=ignore_dirs,
            )
            for parsed_content in domain_file.deserialize(code_registry):
                source_path = parsed_content.source_context.metadata.get("path")
                if source_path:
                    resolved = str(Path(source_path).resolve())
                    if resolved in scanned_code_files:
                        continue
                    scanned_code_files.add(resolved)
                    if ignore_config.should_ignore(source_path, scope="code"):
                        continue
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
            # Uses standard pipeline: result parsers implement claim_and_parse()
            # Each file type gets its own registry since result parsers consume
            # the entire file content (not individual lines).
            result_files = testing_config.get("result_files", [])
            if result_files:
                xml_registry = ParserRegistry()
                xml_registry.register(
                    JUnitXMLParser(
                        pattern_config=default_pattern_config,
                        reference_resolver=default_reference_resolver,
                        base_path=repo_root,
                    )
                )
                json_registry = ParserRegistry()
                json_registry.register(
                    PytestJSONParser(
                        pattern_config=default_pattern_config,
                        reference_resolver=default_reference_resolver,
                        base_path=repo_root,
                    )
                )

                for file_pattern in result_files:
                    matched_files = glob(str(repo_root / file_pattern), recursive=True)
                    for file_path in matched_files:
                        path = Path(file_path)
                        if not path.is_file():
                            continue
                        ext = path.suffix.lower()
                        if ext == ".xml":
                            registry = xml_registry
                        elif ext == ".json":
                            registry = json_registry
                        else:
                            continue
                        domain_file = DomainFile(path)
                        for parsed_content in domain_file.deserialize(registry):
                            builder.add_parsed_content(parsed_content)

    graph = builder.build()

    # Link TEST nodes to CODE nodes via import analysis.
    # This creates TEST→CODE edges that enable transitive coverage:
    # REQUIREMENT ← CODE ← TEST ← TEST_RESULT
    if scan_code and scan_tests:
        from elspais.graph.test_code_linker import link_tests_to_code

        # Get source roots from config (default: ["src", ""])
        traceability_config = config.get("traceability", {})
        source_roots = traceability_config.get("source_roots", None)
        link_tests_to_code(graph, repo_root, source_roots)

    # Annotate keywords on all nodes so keyword search tools work
    from elspais.graph.annotators import annotate_keywords

    annotate_keywords(graph)

    return graph


__all__ = ["build_graph"]
