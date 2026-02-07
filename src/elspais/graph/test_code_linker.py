"""Test-to-code linker — creates TEST→CODE edges via import analysis.

Links TEST nodes to CODE nodes by analyzing test file imports and
matching test function names to source function names. This enables
indirect traceability: TEST → CODE → REQUIREMENT.

The linker runs after the graph is built but before coverage annotation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind
from elspais.utilities.import_analyzer import (
    extract_python_imports,
    module_to_source_path,
)

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph
    from elspais.graph.GraphNode import GraphNode


def _normalize_path(path: str) -> str:
    """Normalize path separators for consistent comparison.

    Args:
        path: File path string.

    Returns:
        Path with forward slashes and no leading ./ prefix.
    """
    p = path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return p


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case.

    Args:
        name: CamelCase string (e.g., "AnnotateCoverage").

    Returns:
        snake_case string (e.g., "annotate_coverage").
    """
    # Insert underscore before uppercase letters preceded by lowercase
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Insert underscore between consecutive uppercase + lowercase
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    return s2.lower()


def _build_code_index(
    graph: TraceGraph,
    repo_root: Path | None = None,
) -> dict[tuple[str, str], list[GraphNode]]:
    """Build index of CODE nodes by (normalized_path, function_name).

    Paths are normalized to be relative to repo_root when possible.
    This ensures they match the relative paths from module_to_source_path().

    Args:
        graph: The TraceGraph to index.
        repo_root: Repository root for making paths relative.

    Returns:
        Dict mapping (normalized_path, function_name) to CODE nodes.
    """
    index: dict[tuple[str, str], list[GraphNode]] = {}
    repo_root_str = _normalize_path(str(repo_root)) + "/" if repo_root else None

    for node in graph.nodes_by_kind(NodeKind.CODE):
        func_name = node.get_field("function_name")
        if not func_name or not node.source:
            continue

        path = _normalize_path(node.source.path)
        # Make path relative to repo_root if it's absolute
        if repo_root_str and path.startswith(repo_root_str):
            path = path[len(repo_root_str) :]

        key = (path, func_name)
        if key not in index:
            index[key] = []
        index[key].append(node)

    return index


def _extract_candidate_functions(test_node: GraphNode) -> list[str]:
    """Extract candidate source function names from a test node.

    Uses heuristics to map test names to source function names:
    - Strip "test_" prefix from function name
    - Strip "Test" prefix from class name, convert to snake_case
    - Generate progressively shorter prefix matches

    Args:
        test_node: A TEST node from the graph.

    Returns:
        List of candidate source function names, most specific first.
    """
    candidates: list[str] = []

    # Get test function name from the node's content or ID
    func_name = test_node.get_field("function_name")
    class_name = test_node.get_field("class_name")

    # If no function_name stored, try parsing from the test ID
    # Format: test:path::ClassName::function_name or test:path::function_name
    if not func_name:
        parts = test_node.id.split("::")
        if len(parts) >= 2:
            func_name = parts[-1]
        if len(parts) >= 3:
            class_name = class_name or parts[-2]

    if func_name and func_name.startswith("test_"):
        # Strip test_ prefix: "test_annotate_coverage_basic" → "annotate_coverage_basic"
        stripped = func_name[5:]  # len("test_") == 5
        if stripped:
            candidates.append(stripped)

            # Generate progressively shorter matches by removing trailing parts
            # "annotate_coverage_basic" → "annotate_coverage" → "annotate"
            parts = stripped.split("_")
            for i in range(len(parts) - 1, 0, -1):
                candidates.append("_".join(parts[:i]))

    if class_name and class_name.startswith("Test"):
        # Strip Test prefix and convert: "TestAnnotateCoverage" → "annotate_coverage"
        stripped_class = class_name[4:]  # len("Test") == 4
        if stripped_class:
            snake = _camel_to_snake(stripped_class)
            if snake not in candidates:
                candidates.append(snake)

    return candidates


def link_tests_to_code(
    graph: TraceGraph,
    repo_root: Path,
    source_roots: list[str] | None = None,
) -> int:
    """Link TEST nodes to CODE nodes via import analysis.

    For each TEST node, analyzes the test file's imports to find
    which source files it references. Then matches the test function
    name to source function names using heuristics.

    Creates VALIDATES edges from CODE nodes to TEST nodes when matches
    are found. Only creates edges for TEST nodes that don't already
    have a CODE parent.

    Args:
        graph: The TraceGraph to modify (in-place).
        repo_root: Repository root path for resolving imports.
        source_roots: Source root directories (defaults to ["src", ""]).

    Returns:
        Number of TEST→CODE edges created.
    """
    # 1. Build CODE index: (normalized_path, function_name) → [CODE nodes]
    code_index = _build_code_index(graph, repo_root)
    if not code_index:
        return 0

    repo_root_str = _normalize_path(str(repo_root)) + "/"

    # 2. Cache test file imports: file_path → list of resolved source paths
    import_cache: dict[str, list[str]] = {}

    edges_created = 0

    # 3. For each TEST node, try to link to CODE nodes
    test_nodes = list(graph.nodes_by_kind(NodeKind.TEST))
    for test_node in test_nodes:
        # Skip tests that already have CODE parents (via VALIDATES edges)
        has_code_parent = False
        for parent in test_node.iter_parents():
            if parent.kind == NodeKind.CODE:
                has_code_parent = True
                break
        if has_code_parent:
            continue

        # Get test file path (make relative to repo_root)
        if not test_node.source:
            continue
        test_path = _normalize_path(test_node.source.path)
        if test_path.startswith(repo_root_str):
            test_path = test_path[len(repo_root_str) :]

        # Cache imports for this test file
        if test_path not in import_cache:
            abs_path = repo_root / test_path
            if abs_path.is_file():
                try:
                    content = abs_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    import_cache[test_path] = []
                    continue

                modules = extract_python_imports(content)
                resolved_paths: list[str] = []
                for mod in modules:
                    src_path = module_to_source_path(mod, repo_root, source_roots)
                    if src_path:
                        resolved_paths.append(_normalize_path(str(src_path)))
                import_cache[test_path] = resolved_paths
            else:
                import_cache[test_path] = []

        imported_paths = import_cache[test_path]
        if not imported_paths:
            continue

        # Get candidate function names from the test
        candidates = _extract_candidate_functions(test_node)
        if not candidates:
            continue

        # Try to match: find CODE nodes in imported files with matching function names
        matched = False
        for candidate in candidates:
            if matched:
                break
            for src_path in imported_paths:
                key = (src_path, candidate)
                code_nodes = code_index.get(key)
                if code_nodes:
                    # Create VALIDATES edge: CODE → TEST
                    for code_node in code_nodes:
                        code_node.link(test_node, EdgeKind.VALIDATES)
                        edges_created += 1
                    matched = True
                    break

    return edges_created
