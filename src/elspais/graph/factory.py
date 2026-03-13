# Implements: REQ-d00054-A
"""Graph Factory - Shared utility for building TraceGraph from spec files.

This module provides a single entry point for all commands to build a TraceGraph
from configuration and spec directories. Commands should use this instead of
implementing their own file reading logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from glob import glob
from pathlib import Path
from typing import Any

from elspais.associates import get_associate_spec_directories
from elspais.config import (
    IgnoreConfig,
    get_code_directories,
    get_config,
    get_ignore_config,
    get_spec_directories,
)
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.deserializer import DomainFile
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.code import CodeParser
from elspais.graph.parsers.journey import JourneyParser
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.parsers.results import JUnitXMLParser, PytestJSONParser
from elspais.graph.parsers.test import TestParser
from elspais.utilities.patterns import IdPatternConfig, IdResolver, PatternConfig
from elspais.utilities.reference_config import ReferenceResolver


def _bridge_pattern_config(resolver: IdResolver) -> PatternConfig:
    """Create a backward-compatible PatternConfig from an IdResolver.

    Temporary bridge until all parsers migrate to IdResolver.
    """
    config = resolver.config
    # Build old-style types dict
    old_types = {}
    for code, tdef in config.types.items():
        letter = tdef.aliases.get("letter", code[0] if code else "")
        old_types[code] = {"id": letter, "name": code.upper(), "level": tdef.level}

    # Build old-style id_format
    old_format = {
        "style": config.component.style,
        "digits": config.component.digits,
        "leading_zeros": config.component.leading_zeros,
    }
    if config.component.pattern:
        old_format["pattern"] = config.component.pattern

    # Build old-style assertions
    old_assertions = {
        "label_style": config.assertions.label_style,
        "max_count": config.assertions.max_count,
        "zero_pad": config.assertions.zero_pad,
    }

    return PatternConfig(
        id_template="{prefix}-{type}{id}",
        prefix=config.namespace,
        types=old_types,
        id_format=old_format,
        assertions=old_assertions,
    )


def _build_resolver(config: dict[str, Any]) -> IdResolver:
    """Create IdResolver from a full config dict (reads project.namespace + id-patterns)."""
    id_config = IdPatternConfig.from_dict(config)
    return IdResolver(id_config)


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


@dataclass
class SpecDirConfig:
    """Per-spec-directory scan configuration.

    Bundles the parser registry with scan settings that may differ between
    the main project and associated projects.
    """

    registry: ParserRegistry
    file_patterns: list[str] = field(default_factory=lambda: ["*.md"])
    skip_dirs: list[str] = field(default_factory=list)
    skip_files: list[str] = field(default_factory=list)
    ignore_config: IgnoreConfig | None = None


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


def _resolve_spec_dir_config(
    spec_dir: Path,
) -> SpecDirConfig:
    """Resolve the full scan configuration for a spec directory.

    Loads the .elspais.toml from the repo containing spec_dir and returns
    a SpecDirConfig with the registry, file patterns, skip settings, and
    ignore config from that project's configuration.

    Args:
        spec_dir: The spec directory path

    Returns:
        SpecDirConfig with registry and scan settings for this spec directory

    Raises:
        FileNotFoundError: If no .elspais.toml is found above spec_dir.
            Associated projects must have their own configuration.
    """
    repo_root = _find_repo_root(spec_dir)
    if not repo_root:
        raise FileNotFoundError(
            f"No .elspais.toml found for spec directory: {spec_dir}. "
            "Associated projects must have their own .elspais.toml configuration."
        )

    config_path = repo_root / ".elspais.toml"
    repo_config = get_config(config_path, repo_root)
    resolver = _build_resolver(repo_config)
    reference_resolver = ReferenceResolver.from_config(repo_config.get("references", {}))

    registry = ParserRegistry()
    registry.register(RequirementParser(resolver))
    registry.register(JourneyParser())
    registry.register(CodeParser(resolver, reference_resolver))
    registry.register(TestParser(resolver, reference_resolver))

    spec_config = repo_config.get("spec", {})
    return SpecDirConfig(
        registry=registry,
        file_patterns=spec_config.get("patterns", ["*.md"]),
        skip_dirs=spec_config.get("skip_dirs", []),
        skip_files=spec_config.get("skip_files", []),
        ignore_config=get_ignore_config(repo_config),
    )


# Implements: REQ-p00005-B
def build_graph(
    config: dict[str, Any] | None = None,
    spec_dirs: list[Path] | None = None,
    config_path: Path | None = None,
    repo_root: Path | None = None,
    scan_code: bool = True,
    scan_tests: bool = True,
    scan_sponsors: bool = True,
    canonical_root: Path | None = None,
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
        canonical_root: Canonical (non-worktree) repo root for cross-repo paths.

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
        sponsor_dirs, associate_errors = get_associate_spec_directories(
            config, repo_root, canonical_root=canonical_root
        )
        spec_dirs = list(spec_dirs) + sponsor_dirs
        if associate_errors:
            import sys

            for err in associate_errors:
                print(f"Warning: {err}", file=sys.stderr)

    # 3. Create default resolver and reference resolver
    default_resolver = _build_resolver(config)
    default_reference_resolver = ReferenceResolver.from_config(config.get("references", {}))

    # Registry for code files (code parser only)
    code_registry = ParserRegistry()
    code_registry.register(CodeParser(default_resolver, default_reference_resolver))

    # Registry for test files (test parser only)
    test_registry = ParserRegistry()
    test_registry.register(TestParser(default_resolver, default_reference_resolver))

    # 4. Build graph from all spec directories
    hash_mode = config.get("validation", {}).get("hash_mode", "normalized-text")
    graph_config = config.get("graph", {})
    satellite_kinds = graph_config.get("satellite_kinds", None)
    mas = default_resolver.config.assertions.multi_separator
    if mas is False or mas is None:
        mas = ""
    builder = GraphBuilder(
        repo_root=repo_root,
        hash_mode=hash_mode,
        satellite_kinds=satellite_kinds,
        multi_assertion_separator=str(mas),
    )

    # Get ignore configuration for code/test scanning (main project only)
    default_ignore_config = get_ignore_config(config)

    for spec_dir in spec_dirs:
        # Resolve full scan config for this spec dir from its own .elspais.toml
        dir_config = _resolve_spec_dir_config(spec_dir)

        domain_file = DomainFile(
            spec_dir,
            patterns=dir_config.file_patterns,
            recursive=True,
            skip_dirs=dir_config.skip_dirs,
            skip_files=dir_config.skip_files,
        )

        for parsed_content in domain_file.deserialize(dir_config.registry):
            # Check if source should be ignored using [ignore].spec patterns
            source_path = parsed_content.source_context.metadata.get("path")
            if source_path and dir_config.ignore_config.should_ignore(source_path, scope="spec"):
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
            # Track files already checked for ignore/dedup in this loop
            checked_files: set[str] = set()
            skip_files: set[str] = set()
            for parsed_content in domain_file.deserialize(code_registry):
                source_path = parsed_content.source_context.metadata.get("path")
                if source_path:
                    resolved = str(Path(source_path).resolve())
                    # Skip files already processed by scan_patterns (step 5a)
                    if resolved in scanned_code_files:
                        continue
                    # Check ignore only once per file
                    if resolved not in checked_files:
                        checked_files.add(resolved)
                        if default_ignore_config.should_ignore(source_path, scope="code"):
                            skip_files.add(resolved)
                    if resolved in skip_files:
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
                        resolver=default_resolver,
                        reference_resolver=default_reference_resolver,
                        base_path=repo_root,
                    )
                )
                json_registry = ParserRegistry()
                json_registry.register(
                    PytestJSONParser(
                        resolver=default_resolver,
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
    # Annotate coverage metrics so all consumers (MCP, HTML, Flask) get coverage data
    from elspais.graph.annotators import annotate_coverage, annotate_keywords

    annotate_keywords(graph)
    annotate_coverage(graph)

    return graph


__all__ = ["build_graph"]
