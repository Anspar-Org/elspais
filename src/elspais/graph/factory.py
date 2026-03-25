# Implements: REQ-d00054-A
# Implements: REQ-d00128-A, REQ-d00128-B, REQ-d00128-C, REQ-d00128-G, REQ-d00128-H
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

from elspais.config import (
    IgnoreConfig,
    get_code_directories,
    get_config,
    get_ignore_config,
    get_spec_directories,
)
from elspais.config.schema import ElspaisConfig
from elspais.graph.builder import GraphBuilder
from elspais.graph.deserializer import DomainFile
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import FileType, GraphNode, NodeKind
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.journey import JourneyParser
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.parsers.remainder import RemainderParser
from elspais.graph.parsers.requirement import RequirementParser
from elspais.graph.parsers.results import JUnitXMLParser, PytestJSONParser
from elspais.utilities.patterns import build_resolver

# Known schema fields (by alias and Python name) for filtering non-schema keys
_SCHEMA_FIELDS = {f.alias or name for name, f in ElspaisConfig.model_fields.items()} | set(
    ElspaisConfig.model_fields.keys()
)


def _validate_config(config: dict[str, Any]) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig, stripping non-schema keys.

    The config dict from get_config() may contain legacy keys (e.g. 'patterns')
    that were consumed by migration but not removed. We filter those out before
    validation since ElspaisConfig uses extra='forbid'.

    The 'associates' key may use legacy format (``{paths: [...]}`` instead of
    ``{name: {path: ...}}``), which is incompatible with the schema. We strip
    it when it has the legacy shape since factory.py accesses associates via
    ``get_associates_config(config)`` on the raw dict.
    """
    filtered = {k: v for k, v in config.items() if k in _SCHEMA_FIELDS}
    # Strip legacy-format associates (contains 'paths' list instead of named entries)
    assoc = filtered.get("associates")
    if isinstance(assoc, dict) and "paths" in assoc:
        filtered.pop("associates", None)
    return ElspaisConfig.model_validate(filtered)


# Implements: REQ-d00128-C
def _capture_git_info(repo_root: Path) -> tuple[str | None, str | None]:
    """Capture git branch and commit once per repo.

    Args:
        repo_root: Path to repository root.

    Returns:
        Tuple of (git_branch, git_commit), both may be None.
    """
    try:
        from elspais.utilities.git import get_current_branch, get_current_commit

        return get_current_branch(repo_root), get_current_commit(repo_root)
    except Exception:
        return None, None


# Implements: REQ-d00128-A, REQ-d00128-B
def _create_file_node(
    file_path: Path,
    repo_root: Path,
    file_type: FileType,
    repo: str | None,
    git_branch: str | None,
    git_commit: str | None,
) -> GraphNode:
    """Create a FILE node for a scanned file.

    Args:
        file_path: Absolute path to the file.
        repo_root: Repository root for computing relative path.
        file_type: The FileType classification.
        repo: Repository identifier (None for main project).
        git_branch: Current git branch (captured once per repo).
        git_commit: Current git commit (captured once per repo).

    Returns:
        A GraphNode with kind == NodeKind.FILE.
    """
    try:
        rel_path = str(file_path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        rel_path = str(file_path)

    file_id = f"file:{rel_path}"
    node = GraphNode(
        id=file_id,
        kind=NodeKind.FILE,
        label=file_path.name,
    )
    node._content = {
        "file_type": file_type,
        "absolute_path": str(file_path.resolve()),
        "relative_path": rel_path,
        "repo": repo,
        "git_branch": git_branch,
        "git_commit": git_commit,
    }
    return node


def _run_prescan_command(
    command: str,
    test_dirs: list[str],
    test_patterns: list[str],
    skip_dirs: list[str],
    repo_root: Path,
) -> dict[str, list[dict]] | None:
    """Run an external prescan command to discover test structure.

    The command receives test file paths on stdin (one per line) and
    outputs a JSON array on stdout with the standardized schema:
    [{"file": "...", "function": "...", "class": "...|null", "line": N}, ...]

    Args:
        command: Shell command to run.
        test_dirs: Test directory patterns from config.
        test_patterns: File patterns to match.
        skip_dirs: Directories to skip.
        repo_root: Repository root for resolving paths.

    Returns:
        Dict mapping file path -> list of function entries, or None on failure.
    """
    import json
    import subprocess
    import sys

    # Collect all test file paths
    test_files: list[str] = []
    for dir_pattern in test_dirs:
        matched_dirs = glob(str(repo_root / dir_pattern), recursive=True)
        for dir_path in matched_dirs:
            p = Path(dir_path)
            if p.is_dir():
                domain_file = DomainFile(
                    p, patterns=test_patterns, recursive=True, skip_dirs=skip_dirs
                )
                for ctx, _content in domain_file.iterate_sources():
                    source_path = ctx.metadata.get("path", ctx.source_id)
                    try:
                        rel = str(Path(source_path).resolve().relative_to(repo_root.resolve()))
                    except ValueError:
                        rel = source_path
                    test_files.append(rel)

    if not test_files:
        return None

    stdin_data = "\n".join(test_files)
    try:
        result = subprocess.run(
            command,
            shell=True,
            input=stdin_data,
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=60,
        )
        if result.returncode != 0:
            print(
                f"Warning: prescan_command failed (exit {result.returncode}): "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
            return None

        entries = json.loads(result.stdout)
        if not isinstance(entries, list):
            print("Warning: prescan_command output is not a JSON array", file=sys.stderr)
            return None

        # Group by file path
        by_file: dict[str, list[dict]] = {}
        for entry in entries:
            file_path = entry.get("file", "")
            if file_path:
                by_file.setdefault(file_path, []).append(entry)
        return by_file

    except subprocess.TimeoutExpired:
        print("Warning: prescan_command timed out after 60s", file=sys.stderr)
        return None
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: prescan_command error: {e}", file=sys.stderr)
        return None


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

    Bundles the parser registry and FileDispatcher with scan settings that
    may differ between the main project and associated projects.
    """

    registry: ParserRegistry
    dispatcher: FileDispatcher | None = None
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

    # Typed config conversion at function boundary
    if isinstance(repo_config, dict):
        typed_repo_config = _validate_config(repo_config)
    else:
        typed_repo_config = repo_config

    resolver = build_resolver(repo_config)

    # Build Lark-based FileDispatcher for spec files
    dispatcher = FileDispatcher(resolver)

    # Legacy registry kept for backwards compatibility during transition
    registry = ParserRegistry()
    registry.register(RequirementParser(resolver))
    registry.register(JourneyParser())
    # Implements: REQ-d00128-G
    registry.register(RemainderParser())

    patterns = typed_repo_config.scanning.spec.file_patterns
    # patterns can be list[str] or dict — extract list if needed
    # Fall back to ["*.md"] if patterns is empty or not a list
    file_patterns = patterns if isinstance(patterns, list) and patterns else ["*.md"]
    return SpecDirConfig(
        registry=registry,
        dispatcher=dispatcher,
        file_patterns=file_patterns,
        skip_dirs=list(typed_repo_config.scanning.spec.skip_dirs),
        skip_files=list(typed_repo_config.scanning.spec.skip_files),
        ignore_config=get_ignore_config(repo_config),
    )


# Implements: REQ-p00005-B, REQ-d00203-A+B+C+D+E
def build_graph(
    config: dict[str, Any] | None = None,
    spec_dirs: list[Path] | None = None,
    config_path: Path | None = None,
    repo_root: Path | None = None,
    scan_code: bool = True,
    scan_tests: bool = True,
    strict: bool = False,
    _build_associates: bool = True,
) -> FederatedGraph:
    """Build a FederatedGraph from spec directories.

    This is the standard way for commands to obtain a graph.
    It handles:
    - Configuration loading (auto-discovery or explicit)
    - Spec directory resolution
    - Parser registration
    - Graph construction
    - Code and test directory scanning (configurable)
    - Multi-repo federation via [associates] config

    Args:
        config: Pre-loaded config dict (optional).
        spec_dirs: Explicit spec directories (optional).
        config_path: Path to config file (optional).
        repo_root: Repository root for relative paths (defaults to cwd).
        scan_code: Whether to scan code directories from traceability.scan_patterns.
        scan_tests: Whether to scan test directories from testing.test_dirs.
        strict: If True, raise on missing associate paths instead of soft-failing.
        _build_associates: Internal flag to prevent recursive associate building.

    Returns:
        FederatedGraph wrapping one or more TraceGraph instances.

    Priority:
        spec_dirs > config > config_path > defaults
    """
    # Default repo_root
    if repo_root is None:
        repo_root = Path.cwd()

    # 1. Resolve configuration
    if config is None:
        config = get_config(config_path, repo_root)

    # Typed config conversion at function boundary
    if isinstance(config, dict):
        typed_config = _validate_config(config)
    else:
        typed_config = config

    # 2. Resolve spec directories
    if spec_dirs is None:
        spec_dirs = get_spec_directories(None, config, repo_root)

    # 3. Create default resolver
    default_resolver = build_resolver(config)

    # Implements: REQ-d00128-G
    # Lark FileDispatcher for code and test files
    default_dispatcher = FileDispatcher(default_resolver)

    # 4. Build graph from all spec directories
    hash_mode = typed_config.validation.hash_mode
    satellite_kinds = ["assertion", "result"]
    mas = default_resolver.config.assertions.multi_separator
    if mas is False or mas is None:
        mas = ""
    builder = GraphBuilder(
        repo_root=repo_root,
        hash_mode=hash_mode,
        satellite_kinds=satellite_kinds,
        multi_assertion_separator=str(mas),
        resolver=default_resolver,
    )

    # Get ignore configuration for code/test scanning (main project only)
    default_ignore_config = get_ignore_config(config)

    # Implements: REQ-d00128-C
    # Capture git info once per repo
    git_branch, git_commit = _capture_git_info(repo_root)

    # Track FILE nodes created to avoid duplicates
    file_nodes: dict[str, GraphNode] = {}  # resolved_path -> FILE node

    def _get_or_create_file_node(
        source_path: Path,
        file_type: FileType,
        file_repo: str | None = None,
    ) -> GraphNode:
        """Get or create a FILE node for the given source path."""
        resolved = str(source_path.resolve())
        if resolved not in file_nodes:
            fn = _create_file_node(
                source_path, repo_root, file_type, file_repo, git_branch, git_commit
            )
            file_nodes[resolved] = fn
            builder.register_file_node(fn)
        else:
            # Multi-role: track additional file types on existing node (stored as
            # string values for JSON serializability)
            fn = file_nodes[resolved]
            existing_types = fn.get_field("file_types")
            if existing_types is None:
                first = fn.get_field("file_type")
                existing_types = [first.value if isinstance(first, FileType) else first]
            type_val = file_type.value if isinstance(file_type, FileType) else file_type
            if type_val not in existing_types:
                existing_types.append(type_val)
            fn.set_field("file_types", existing_types)
        return file_nodes[resolved]

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

        # Use Lark FileDispatcher for spec file parsing
        for parsed_content in domain_file.dispatch(dir_config.dispatcher.dispatch_spec):
            # Check if source should be ignored using [ignore].spec patterns
            source_path = parsed_content.source_context.metadata.get("path")
            if source_path and dir_config.ignore_config.should_ignore(source_path, scope="spec"):
                continue
            # Implements: REQ-d00128-A
            # Create FILE node for this spec file
            file_node = None
            if source_path:
                file_node = _get_or_create_file_node(Path(source_path), FileType.SPEC)
            builder.add_parsed_content(parsed_content, file_node=file_node)

    # 5. Scan code files from [traceability].scan_patterns AND [directories].code
    if scan_code:
        scanned_code_files: set[str] = set()

        # 5a. Explicit scan_patterns (existing behavior)
        scan_patterns = list(typed_config.scanning.code.file_patterns)

        for pattern in scan_patterns:
            # Resolve glob pattern relative to repo_root
            matched_files = glob(str(repo_root / pattern), recursive=True)
            for file_path in matched_files:
                path = Path(file_path)
                if path.is_file():
                    resolved = str(path.resolve())
                    scanned_code_files.add(resolved)
                    # Implements: REQ-d00128-A
                    fn = _get_or_create_file_node(path, FileType.CODE)
                    domain_file = DomainFile(path)
                    for parsed_content in domain_file.dispatch(default_dispatcher.dispatch_code):
                        builder.add_parsed_content(parsed_content, file_node=fn)

        # 5b. [directories].code with default file patterns
        code_dirs = get_code_directories(config, repo_root)
        ignore_dirs = list(typed_config.scanning.skip)

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
            for parsed_content in domain_file.dispatch(default_dispatcher.dispatch_code):
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
                # Implements: REQ-d00128-A
                fn = None
                if source_path:
                    fn = _get_or_create_file_node(Path(source_path), FileType.CODE)
                builder.add_parsed_content(parsed_content, file_node=fn)

    # 6. Scan test directories from testing config
    if scan_tests:
        testing_cfg = typed_config.scanning.test
        if testing_cfg.enabled:
            test_dirs = list(testing_cfg.directories)
            test_patterns = list(testing_cfg.file_patterns)
            test_skip_dirs = list(testing_cfg.skip_dirs)

            # Run external prescan command if configured
            prescan_command = testing_cfg.prescan_command
            prescan_data: dict[str, list[dict]] | None = None
            if prescan_command:
                prescan_data = _run_prescan_command(
                    prescan_command, test_dirs, test_patterns, test_skip_dirs, repo_root
                )

            # Build dispatch function with prescan data
            def _dispatch_test(content: str, file_path: str) -> list:
                return default_dispatcher.dispatch_test(
                    content, file_path, prescan_data=prescan_data
                )

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
                            skip_dirs=test_skip_dirs,
                        )
                        for parsed_content in domain_file.dispatch(_dispatch_test):
                            # Implements: REQ-d00128-A
                            source_path = parsed_content.source_context.metadata.get("path")
                            fn = None
                            if source_path:
                                fn = _get_or_create_file_node(Path(source_path), FileType.TEST)
                            builder.add_parsed_content(parsed_content, file_node=fn)

            # 6b. Scan test result files (JUnit XML, pytest JSON)
            # Implements: REQ-d00128-H
            # RemainderParser is NOT registered for RESULT file types
            result_files = list(typed_config.scanning.result.file_patterns)
            if result_files:
                xml_registry = ParserRegistry()
                xml_registry.register(
                    JUnitXMLParser(
                        resolver=default_resolver,
                        base_path=repo_root,
                    )
                )
                json_registry = ParserRegistry()
                json_registry.register(
                    PytestJSONParser(
                        resolver=default_resolver,
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
                        # Implements: REQ-d00128-A
                        fn = _get_or_create_file_node(path, FileType.RESULT)
                        domain_file = DomainFile(path)
                        for parsed_content in domain_file.deserialize(registry):
                            builder.add_parsed_content(parsed_content, file_node=fn)

    graph = builder.build()

    # 6c. Scan coverage files and annotate FILE nodes
    coverage_patterns = list(typed_config.scanning.coverage.file_patterns)
    if coverage_patterns:
        from elspais.graph.parsers.results.coverage_json import CoverageJsonParser
        from elspais.graph.parsers.results.lcov import LcovParser

        lcov_parser = LcovParser()
        cov_json_parser = CoverageJsonParser()

        for file_pattern in coverage_patterns:
            coverage_dirs = list(typed_config.scanning.coverage.directories)
            if not coverage_dirs:
                coverage_dirs = ["."]
            for cov_dir in coverage_dirs:
                matched_files = glob(str(repo_root / cov_dir / file_pattern), recursive=True)
                for file_path in matched_files:
                    path = Path(file_path)
                    if not path.is_file():
                        continue

                    # Detect format
                    if lcov_parser.can_parse(path):
                        parser = lcov_parser
                    elif cov_json_parser.can_parse(path):
                        parser = cov_json_parser
                    else:
                        continue

                    content = path.read_text(encoding="utf-8")
                    parsed = parser.parse(content, str(path))

                    # Annotate existing FILE nodes
                    for source_file, data in parsed.items():
                        file_id = f"file:{source_file}"
                        node = graph.find_by_id(file_id)
                        if node is None:
                            continue
                        node.set_field("line_coverage", data["line_coverage"])
                        node.set_field("executable_lines", data["executable_lines"])

    # Link TEST nodes to CODE nodes via import analysis.
    # This creates TEST→CODE edges that enable transitive coverage:
    # REQUIREMENT ← CODE ← TEST ← RESULT
    if scan_code and scan_tests:
        from elspais.graph.test_code_linker import link_tests_to_code

        # Get source roots from config (default: ["src", ""])
        source_roots = typed_config.scanning.code.source_roots
        link_tests_to_code(graph, repo_root, source_roots)

    # Annotate keywords on all nodes so keyword search tools work
    # Annotate coverage metrics so all consumers (MCP, HTML, Flask) get coverage data
    from elspais.graph.annotators import annotate_coverage, annotate_keywords

    annotate_keywords(graph)
    annotate_coverage(graph)

    # Implements: REQ-d00203-A+B+C+D+E
    # Build associate repos if [associates] config is present
    if _build_associates:
        from elspais.config import get_associates_config, validate_no_transitive_associates
        from elspais.graph.federated import FederationError, RepoEntry

        associates_config = get_associates_config(config, repo_root=repo_root)
        if associates_config:
            entries: list[RepoEntry] = []
            # Root repo entry
            entries.append(
                RepoEntry(
                    name="root",
                    graph=graph,
                    config=config,
                    repo_root=repo_root,
                )
            )
            for assoc_name, assoc_info in associates_config.items():
                assoc_path = (repo_root / assoc_info["path"]).resolve()
                git_origin = assoc_info.get("git")

                if not assoc_path.exists():
                    # Implements: REQ-d00203-C, REQ-d00203-D
                    if strict:
                        raise FederationError(
                            f"Associate '{assoc_name}' path does not exist: {assoc_path}"
                        )
                    entries.append(
                        RepoEntry(
                            name=assoc_name,
                            graph=None,
                            config=None,
                            repo_root=assoc_path,
                            git_origin=git_origin,
                            error=f"Path does not exist: {assoc_path}",
                        )
                    )
                    continue

                # Load associate's config
                assoc_config = get_config(None, assoc_path)

                # Implements: REQ-d00203-B
                validate_no_transitive_associates(assoc_name, assoc_config)

                # Build associate's graph (no recursive associate building)
                assoc_fg = build_graph(
                    config=assoc_config,
                    repo_root=assoc_path,
                    scan_code=scan_code,
                    scan_tests=scan_tests,
                    _build_associates=False,
                )
                # Extract the TraceGraph from the federation-of-one
                assoc_graph = list(assoc_fg.iter_repos())[0].graph
                entries.append(
                    RepoEntry(
                        name=assoc_name,
                        graph=assoc_graph,
                        config=assoc_config,
                        repo_root=assoc_path,
                        git_origin=git_origin,
                    )
                )

            return FederatedGraph(entries, root_repo="root")

    return FederatedGraph.from_single(graph, config, repo_root)


__all__ = ["build_graph"]
