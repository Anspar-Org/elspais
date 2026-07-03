# Implements: REQ-d00054-A
# Implements: REQ-d00128-A, REQ-d00128-B, REQ-d00128-C, REQ-d00128-G, REQ-d00128-H
"""Graph Factory - Shared utility for building TraceGraph from spec files.

This module provides a single entry point for all commands to build a TraceGraph
from configuration and spec directories. Commands should use this instead of
implementing their own file reading logic.
"""

from __future__ import annotations

import logging
import os
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
from elspais.graph.GraphNode import FileType, GraphNode, NodeKind, make_file_id
from elspais.graph.parsers import ParserRegistry
from elspais.graph.parsers.journey import JourneyParser
from elspais.graph.parsers.lark import FileDispatcher
from elspais.graph.parsers.remainder import RemainderParser
from elspais.utilities.patterns import build_resolver

_log = logging.getLogger(__name__)

# Known schema fields (by alias and Python name) for filtering non-schema keys
_SCHEMA_FIELDS = {f.alias or name for name, f in ElspaisConfig.model_fields.items()} | set(
    ElspaisConfig.model_fields.keys()
)


def _resolve_coverage_file_node(graph, source_file, lcov_path, repo_root):
    """Resolve an lcov SF path to a repo-relative FILE node.

    Tries the SF verbatim, then resolves it relative to the package root
    (the directory containing the lcov file, minus a trailing 'coverage').
    """
    node = graph.find_by_id(make_file_id(source_file))
    if node is not None:
        return node
    pkg_root = lcov_path.parent
    if pkg_root.name == "coverage":
        pkg_root = pkg_root.parent
    try:
        rel = (pkg_root / source_file).resolve().relative_to(Path(repo_root).resolve())
    except ValueError:
        return None
    return graph.find_by_id(make_file_id(str(rel)))


# Implements: REQ-d00254-F, REQ-d00254-I
def _ingest_target_results(
    builder,
    target,
    results_text: str,
    repo_root: Path,
    source_path: str = "",
    *,
    carried: bool = False,
) -> int:
    """Parse a target's reporter output and add RESULT ParsedContent.

    Each ParsedContent carries real source_file (repo-relative) + match.
    Returns the count of RESULT records added.

    Only "results"-kind reporters are handled; coverage-kind reporters are
    skipped (returns 0 immediately).
    """
    from elspais.graph.parsers import ParsedContent
    from elspais.graph.parsers.results.registry import get_reporter

    try:
        spec = get_reporter(target.reporter)
    except KeyError:
        _log.debug("_ingest_target_results: unknown reporter %r, skipping", target.reporter)
        return 0

    if spec.kind != "results":
        _log.debug(
            "_ingest_target_results: reporter %r is kind=%r, not 'results', skipping",
            target.reporter,
            spec.kind,
        )
        return 0

    parser = spec.parser_factory()
    records = parser.parse(results_text, source_path)
    repo_root_resolved = Path(repo_root).resolve()
    count = 0
    for rec in records:
        raw_src = rec.get("source_path", "")
        # Normalize absolute source_path to repo-relative for source_file.
        # If already relative or outside the repo, keep as-is.
        if raw_src and os.path.isabs(raw_src):
            try:
                source_file = str(Path(raw_src).resolve().relative_to(repo_root_resolved))
            except ValueError:
                source_file = raw_src  # outside repo root -- keep absolute
        else:
            source_file = raw_src

        # Normalize root_path (from root_url after stripping file://) the same
        # way. root_path is set only by flutter-machine for testWidgets() calls
        # whose test.line is a framework wrapper rather than the user call site.
        raw_root = rec.get("root_path") or None
        if raw_root and os.path.isabs(raw_root):
            try:
                root_file: str | None = str(
                    Path(raw_root).resolve().relative_to(repo_root_resolved)
                )
            except ValueError:
                root_file = raw_root  # outside repo root -- keep absolute
        else:
            root_file = raw_root

        parsed_data = {
            "id": rec["id"],
            "status": rec.get("status"),
            "name": rec.get("name", ""),
            "classname": rec.get("classname", ""),
            "duration": rec.get("duration", 0.0),
            "message": rec.get("message"),
            "verifies": rec.get("verifies", []),
            "test_id": rec.get("test_id"),
            "source_path": raw_src,
            "source_file": source_file,
            "match": target.match,
            "carried": carried,
            "target": target.name,
            "line": rec.get("line"),
            "root_line": rec.get("root_line"),
            "root_file": root_file,
        }
        content = ParsedContent(
            content_type="test_result",
            start_line=1,
            end_line=1,
            raw_text="",
            parsed_data=parsed_data,
        )
        builder.add_parsed_content(content)
        count += 1
    return count


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
def create_file_node(
    file_path: Path,
    repo_root: Path,
    file_type: FileType,
    repo: str | None = None,
    git_branch: str | None = None,
    git_commit: str | None = None,
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

    file_id = make_file_id(rel_path)
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


# Implements: REQ-d00254-A+B+F
def _derive_credit_config(targets):
    """Collapse per-target credit settings into the annotator's global CoverageCreditConfig.

    Phase 1: homogeneous targets. assertion_credit = strongest credit_coverage;
    unmatched_credit = "verified" iff any aggregate target; dirs = target cwds;
    min_coverage_fraction = max.

    Returns:
        CoverageCreditConfig instance.
    """
    from elspais.graph.annotators import CoverageCreditConfig

    _tgt_dirs = tuple(t.cwd for t in targets if t.cwd and t.cwd != ".")
    _order = {"off": 0, "tested": 1, "verified": 2}
    _assertion_credit = "off"
    for _t in targets:
        if _order.get(_t.credit_coverage, 0) > _order.get(_assertion_credit, 0):
            _assertion_credit = _t.credit_coverage
    _unmatched = "verified" if any(_t.match == "aggregate" for _t in targets) else "off"
    _min_frac = max((_t.min_coverage_fraction for _t in targets), default=0.0)
    return CoverageCreditConfig(
        app_dirs=_tgt_dirs,
        unmatched_credit=_unmatched,
        coverage_dirs=_tgt_dirs,
        assertion_credit=_assertion_credit,
        min_coverage_fraction=_min_frac,
    )


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
    # RequirementParser removed — Lark dispatcher handles spec files
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
    captured_results: dict[str, str] | None = None,
    fresh_targets: set[str] | None = None,
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
        captured_results: Optional mapping of target name -> captured stdout/results
            text, bypassing the on-disk results glob for that target.
        fresh_targets: Optional set of [[scanning.test.targets]] names considered
            "freshly run" (e.g. via ``--targets``). When set, every RESULT node
            ingested for a target NOT in this set is tagged ``carried=True``.
            When None (the default), no target is considered carried. Stashed
            on the returned FederatedGraph as ``render_fresh_targets``.

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
    # YIELDS (RESULT->TEST) links are always enabled: flutter-machine emits
    # test_id=None (never queues YIELDS), while junit/pytest emit real test_ids
    # (YIELDS desired).  So the per-test link is unconditionally safe.
    builder = GraphBuilder(
        repo_root=repo_root,
        hash_mode=hash_mode,
        satellite_kinds=satellite_kinds,
        multi_assertion_separator=str(mas),
        resolver=default_resolver,
        namespace=typed_config.project.namespace,
        project_name=typed_config.project.name,
        link_results_to_tests=True,
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
            fn = create_file_node(
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

            # 6b-target. Ingest results from [[scanning.test.targets]] via reporter registry.
            # Implements: REQ-d00128-A+H
            # RemainderParser is NOT registered for RESULT file types.
            # When targets is empty (the default) this loop is a no-op.
            _captured = captured_results or {}
            resolved_root = repo_root.resolve()
            for target in typed_config.scanning.test.targets:
                if not target.reporter:
                    continue
                # Implements: REQ-d00254-I
                carried = fresh_targets is not None and target.name not in fresh_targets
                # cwd-escape guard: skip targets whose cwd resolves outside the repo root
                cwd_path = (repo_root / target.cwd) if target.cwd else repo_root
                try:
                    cwd_path.resolve().relative_to(resolved_root)
                except ValueError:
                    _log.warning(
                        "target %r: cwd %r escapes repo root -- skipping",
                        target.name,
                        target.cwd,
                    )
                    continue
                if target.name in _captured:
                    _ingest_target_results(
                        builder, target, _captured[target.name], repo_root, "", carried=carried
                    )
                elif target.results:
                    matched = glob(str(cwd_path / target.results), recursive=True)
                    if matched:
                        for f in matched:
                            if Path(f).is_file():
                                # Implements: REQ-d00128-A
                                _get_or_create_file_node(Path(f), FileType.RESULT)
                                _ingest_target_results(
                                    builder,
                                    target,
                                    Path(f).read_text(encoding="utf-8", errors="replace"),
                                    repo_root,
                                    str(Path(f)),
                                    carried=carried,
                                )
                    else:
                        _log.debug("target %r: no files matched %r", target.name, target.results)
                else:
                    _log.debug(
                        "target %r: stdout reporter with no captured output and no results"
                        " glob -- skipping",
                        target.name,
                    )

    graph = builder.build()

    # 6c-target. Per-target coverage ingestion: scan coverage files and annotate FILE nodes.
    # When targets is empty (the default), this loop is a no-op.
    if typed_config.scanning.test.targets:
        from elspais.graph.parsers.results.coverage_json import CoverageJsonParser
        from elspais.graph.parsers.results.coverage_sqlite import CoverageSqliteParser
        from elspais.graph.parsers.results.lcov import LcovParser

        lcov_parser = LcovParser()
        cov_json_parser = CoverageJsonParser()
        cov_sqlite_parser = CoverageSqliteParser()
        _resolved_root = repo_root.resolve()
        for target in typed_config.scanning.test.targets:
            if not target.coverage:
                continue
            # cwd-escape guard: skip targets whose cwd resolves outside the repo root
            cwd_path = (repo_root / target.cwd) if target.cwd else repo_root
            try:
                cwd_path.resolve().relative_to(_resolved_root)
            except ValueError:
                _log.warning(
                    "target %r: cwd %r escapes repo root -- skipping",
                    target.name,
                    target.cwd,
                )
                continue
            cov_path = (cwd_path / target.coverage).resolve()
            if not cov_path.is_file():
                _log.debug("target %r: coverage file not found: %s", target.name, cov_path)
                continue
            if lcov_parser.can_parse(cov_path):
                cov_parser = lcov_parser
            elif cov_json_parser.can_parse(cov_path):
                cov_parser = cov_json_parser
            elif cov_sqlite_parser.can_parse(cov_path):
                cov_parser = cov_sqlite_parser
            else:
                _log.debug("target %r: unrecognised coverage format: %s", target.name, cov_path)
                continue
            # Binary formats (e.g. the .coverage SQLite DB) can't be
            # text-decoded -- their parser ignores `content` and reopens
            # `source_path` directly (see CoverageSqliteParser.binary).
            if getattr(cov_parser, "binary", False):
                cov_content = ""
            else:
                cov_content = cov_path.read_text(encoding="utf-8")
            parsed_cov = cov_parser.parse(cov_content, str(cov_path))
            for source_file, data in parsed_cov.items():
                cov_node = _resolve_coverage_file_node(graph, source_file, cov_path, repo_root)
                if cov_node is None:
                    continue
                cov_node.set_field("line_coverage", data["line_coverage"])
                cov_node.set_field("executable_lines", data["executable_lines"])
                if data.get("contexts"):
                    cov_node.set_field("line_contexts", data["contexts"])

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
    from elspais.graph.annotators import (
        annotate_coverage,
        annotate_journey_verification,
        annotate_keywords,
    )

    annotate_keywords(graph)
    # Derive the global coverage-credit config from [[scanning.test.targets]].
    # Per-target settings are collapsed into one global config (acceptable for
    # Phase 1 homogeneous targets). Logic lives in _derive_credit_config (pure,
    # unit-tested independently).
    credit = _derive_credit_config(typed_config.scanning.test.targets)
    # Roll each journey's verifying tests into a journey_verification metric
    # BEFORE coverage, so the per-REQ UAT consumer can read each validating
    # journey's verdict when populating the uat_verified dimension.
    annotate_journey_verification(graph)
    annotate_coverage(graph, credit)

    # Implements: REQ-d00203-A+B+C+D+E
    # Build associate repos if [associates] config is present
    if _build_associates:
        from elspais.config import get_associates_config, validate_no_transitive_associates
        from elspais.graph.federated import FederationError, RepoEntry

        associates_config = get_associates_config(config, repo_root=repo_root)
        if associates_config:
            entries: list[RepoEntry] = []
            host_name = config["project"]["name"]
            # Root repo entry
            entries.append(
                RepoEntry(
                    name=host_name,
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

            federated = FederatedGraph(entries, root_repo=host_name)
            # Implements: REQ-d00254-I
            federated.render_fresh_targets = fresh_targets
            return federated

    federated = FederatedGraph.from_single(graph, config, repo_root)
    # Implements: REQ-d00254-I
    federated.render_fresh_targets = fresh_targets
    return federated


__all__ = ["build_graph"]
