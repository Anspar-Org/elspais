# Implements: REQ-o00065-A, REQ-o00065-B, REQ-o00065-C, REQ-o00065-E
# Implements: REQ-d00072-A, REQ-d00072-B, REQ-d00072-C, REQ-d00072-D
# Implements: REQ-d00072-E, REQ-d00072-F
"""Link suggestion engine — proposes requirement associations for unlinked nodes.

Analyzes unlinked TEST nodes and proposes requirement associations using
scoring heuristics: import chain analysis, function name matching, file
path proximity, and keyword overlap. All operations are read-only on the
graph; suggestions are returned as data, not applied.

Reuses existing building blocks:
- utilities/import_analyzer.py: extract_python_imports, module_to_source_path
- graph/test_code_linker.py: _build_code_index, _extract_candidate_functions
- graph/annotators.py: extract_keywords
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from elspais.graph.annotators import extract_keywords
from elspais.graph.GraphNode import NodeKind
from elspais.graph.test_code_linker import (
    _build_code_index,
    _extract_candidate_functions,
    _normalize_path,
)
from elspais.utilities.import_analyzer import (
    extract_python_imports,
    module_to_source_path,
)

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph
    from elspais.graph.GraphNode import GraphNode

# Confidence band thresholds
CONFIDENCE_HIGH = 0.8
CONFIDENCE_MEDIUM = 0.5

# Heuristic base scores
_SCORE_IMPORT_CHAIN = 0.9
_SCORE_FUNC_NAME_EXACT = 0.85
_SCORE_FILE_PROXIMITY = 0.6
_SCORE_KEYWORD_CAP = 0.5


@dataclass
class LinkSuggestion:
    """A proposed link between a test node and a requirement."""

    test_id: str
    test_label: str
    test_file: str
    requirement_id: str
    requirement_title: str
    confidence: float
    reasons: list[str] = field(default_factory=list)

    @property
    def confidence_band(self) -> str:
        if self.confidence >= CONFIDENCE_HIGH:
            return "high"
        if self.confidence >= CONFIDENCE_MEDIUM:
            return "medium"
        return "low"

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "test_label": self.test_label,
            "test_file": self.test_file,
            "requirement_id": self.requirement_id,
            "requirement_title": self.requirement_title,
            "confidence": round(self.confidence, 3),
            "confidence_band": self.confidence_band,
            "reasons": self.reasons,
        }


def suggest_links(
    graph: TraceGraph,
    repo_root: Path,
    file_path: str | None = None,
    limit: int = 50,
    source_roots: list[str] | None = None,
) -> list[LinkSuggestion]:
    """Orchestrate all heuristics and return deduplicated suggestions.

    Args:
        graph: The TraceGraph to analyze (read-only).
        repo_root: Repository root path for resolving imports.
        file_path: Optional file path to restrict analysis to.
        limit: Maximum suggestions to return.
        source_roots: Source root directories (defaults to ["src", ""]).

    Returns:
        List of LinkSuggestion sorted by confidence descending.
    """
    unlinked = _find_unlinked_tests(graph, file_path)
    if not unlinked:
        return []

    # Build indices once for all heuristics
    code_index = _build_code_index(graph, repo_root)
    code_to_reqs = _build_code_to_req_index(graph)

    # Collect all suggestions from all heuristics
    all_suggestions: list[LinkSuggestion] = []

    for test_node in unlinked:
        all_suggestions.extend(
            _heuristic_import_chain(
                test_node, graph, repo_root, code_index, code_to_reqs, source_roots
            )
        )
        all_suggestions.extend(_heuristic_function_name(test_node, code_index, code_to_reqs))
        all_suggestions.extend(_heuristic_file_proximity(test_node, graph, repo_root, code_to_reqs))
        all_suggestions.extend(_heuristic_keyword_overlap(test_node, graph))

    # Deduplicate and sort
    deduped = _deduplicate_suggestions(all_suggestions)
    deduped.sort(key=lambda s: s.confidence, reverse=True)

    return deduped[:limit]


def _find_unlinked_tests(
    graph: TraceGraph,
    file_path: str | None = None,
) -> list[GraphNode]:
    """Find TEST nodes without REQUIREMENT parents (directly or via assertion).

    Args:
        graph: The TraceGraph to scan.
        file_path: Optional file path to filter by.

    Returns:
        List of unlinked TEST nodes.
    """
    unlinked: list[GraphNode] = []

    for node in graph.nodes_by_kind(NodeKind.TEST):
        # Filter by file path if specified
        if file_path:
            if not node.source:
                continue
            node_path = _normalize_path(node.source.path)
            filter_path = _normalize_path(file_path)
            if filter_path not in node_path and node_path not in filter_path:
                continue

        # Check if test has any REQUIREMENT or ASSERTION parent
        has_req_link = False
        for parent in node.iter_parents():
            if parent.kind in (NodeKind.REQUIREMENT, NodeKind.ASSERTION):
                has_req_link = True
                break
            # Also check if parent is CODE that links to a REQUIREMENT
            if parent.kind == NodeKind.CODE:
                for grandparent in parent.iter_parents():
                    if grandparent.kind in (NodeKind.REQUIREMENT, NodeKind.ASSERTION):
                        has_req_link = True
                        break
                if has_req_link:
                    break

        if not has_req_link:
            unlinked.append(node)

    return unlinked


def _build_code_to_req_index(
    graph: TraceGraph,
) -> dict[str, list[tuple[str, str]]]:
    """Build index mapping CODE node IDs to their parent REQUIREMENTs.

    Returns:
        Dict mapping code_node_id to list of (req_id, req_title) tuples.
    """
    index: dict[str, list[tuple[str, str]]] = {}

    for node in graph.nodes_by_kind(NodeKind.CODE):
        reqs: list[tuple[str, str]] = []
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT:
                reqs.append((parent.id, parent.get_label()))
            elif parent.kind == NodeKind.ASSERTION:
                # Assertion's parent is the requirement
                for grandparent in parent.iter_parents():
                    if grandparent.kind == NodeKind.REQUIREMENT:
                        reqs.append((grandparent.id, grandparent.get_label()))
        if reqs:
            index[node.id] = reqs

    return index


def _heuristic_import_chain(
    test_node: GraphNode,
    graph: TraceGraph,
    repo_root: Path,
    code_index: dict[tuple[str, str], list[GraphNode]],
    code_to_reqs: dict[str, list[tuple[str, str]]],
    source_roots: list[str] | None = None,
) -> list[LinkSuggestion]:
    """H1: Trace TEST → import → CODE → REQ relationships.

    Score: 0.9 (high confidence — explicit import chain).
    """
    if not test_node.source:
        return []

    test_path = _normalize_path(test_node.source.path)
    abs_path = repo_root / test_path
    if not abs_path.is_file():
        return []

    try:
        content = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    modules = extract_python_imports(content)
    if not modules:
        return []

    # Resolve imports to source file paths
    resolved_paths: list[str] = []
    for mod in modules:
        src_path = module_to_source_path(mod, repo_root, source_roots)
        if src_path:
            resolved_paths.append(_normalize_path(str(src_path)))

    if not resolved_paths:
        return []

    # Find CODE nodes in imported files → their REQUIREMENTs
    suggestions: list[LinkSuggestion] = []
    seen_reqs: set[str] = set()

    for (path, _func), code_nodes in code_index.items():
        if path not in resolved_paths:
            continue
        for code_node in code_nodes:
            reqs = code_to_reqs.get(code_node.id, [])
            for req_id, req_title in reqs:
                if req_id in seen_reqs:
                    continue
                seen_reqs.add(req_id)
                suggestions.append(
                    LinkSuggestion(
                        test_id=test_node.id,
                        test_label=test_node.get_label() or test_node.id,
                        test_file=test_path,
                        requirement_id=req_id,
                        requirement_title=req_title,
                        confidence=_SCORE_IMPORT_CHAIN,
                        reasons=[f"imports module containing code that implements {req_id}"],
                    )
                )

    return suggestions


def _heuristic_function_name(
    test_node: GraphNode,
    code_index: dict[tuple[str, str], list[GraphNode]],
    code_to_reqs: dict[str, list[tuple[str, str]]],
) -> list[LinkSuggestion]:
    """H2: Match test function names to CODE node function names.

    Score: 0.85 for exact match, decreasing by 0.05 per shorter prefix.
    """
    candidates = _extract_candidate_functions(test_node)
    if not candidates:
        return []

    test_path = _normalize_path(test_node.source.path) if test_node.source else ""

    suggestions: list[LinkSuggestion] = []
    seen_reqs: set[str] = set()

    for i, candidate in enumerate(candidates):
        # Score decreases for shorter/less specific matches
        score = max(_SCORE_FUNC_NAME_EXACT - (i * 0.05), 0.4)

        for (_path, func_name), code_nodes in code_index.items():
            if func_name != candidate:
                continue
            for code_node in code_nodes:
                reqs = code_to_reqs.get(code_node.id, [])
                for req_id, req_title in reqs:
                    if req_id in seen_reqs:
                        continue
                    seen_reqs.add(req_id)
                    match_type = "exact" if i == 0 else "partial"
                    suggestions.append(
                        LinkSuggestion(
                            test_id=test_node.id,
                            test_label=test_node.get_label() or test_node.id,
                            test_file=test_path,
                            requirement_id=req_id,
                            requirement_title=req_title,
                            confidence=score,
                            reasons=[
                                f"function name {match_type} match: "
                                f"test '{candidate}' -> {func_name}() implements {req_id}"
                            ],
                        )
                    )

    return suggestions


def _heuristic_file_proximity(
    test_node: GraphNode,
    graph: TraceGraph,
    repo_root: Path,
    code_to_reqs: dict[str, list[tuple[str, str]]],
) -> list[LinkSuggestion]:
    """H3: Map test file paths to source directories and find linked REQs.

    Score: 0.6 (weaker signal — same directory doesn't guarantee relationship).
    """
    if not test_node.source:
        return []

    test_path = _normalize_path(test_node.source.path)

    # Map test path to likely source directory
    # Common patterns: tests/test_foo.py -> src/elspais/foo.py
    #                  tests/core/test_bar.py -> src/elspais/core/bar.py
    source_dirs = _infer_source_dirs(test_path)
    if not source_dirs:
        return []

    suggestions: list[LinkSuggestion] = []
    seen_reqs: set[str] = set()

    for code_node in graph.nodes_by_kind(NodeKind.CODE):
        if not code_node.source:
            continue
        code_path = _normalize_path(code_node.source.path)

        # Check if code file is in one of the inferred source directories
        matches = any(code_path.startswith(sd) for sd in source_dirs)
        if not matches:
            continue

        reqs = code_to_reqs.get(code_node.id, [])
        for req_id, req_title in reqs:
            if req_id in seen_reqs:
                continue
            seen_reqs.add(req_id)
            suggestions.append(
                LinkSuggestion(
                    test_id=test_node.id,
                    test_label=test_node.get_label() or test_node.id,
                    test_file=test_path,
                    requirement_id=req_id,
                    requirement_title=req_title,
                    confidence=_SCORE_FILE_PROXIMITY,
                    reasons=[
                        f"file proximity: test in {test_path} near code implementing {req_id}"
                    ],
                )
            )

    return suggestions


def _infer_source_dirs(test_path: str) -> list[str]:
    """Infer likely source directories from a test file path.

    Maps common test path patterns to source paths:
    - tests/test_foo.py -> src/*/foo.py area
    - tests/core/test_bar.py -> src/*/core/ area

    Returns:
        List of source directory prefixes to match against.
    """
    parts = test_path.replace("\\", "/").split("/")

    # Find the "tests" directory in the path
    try:
        tests_idx = parts.index("tests")
    except ValueError:
        # Try "test" as well
        try:
            tests_idx = parts.index("test")
        except ValueError:
            return []

    # Get subdirectory path after "tests/"
    sub_parts = parts[tests_idx + 1 :]
    if not sub_parts:
        return []

    # Strip "test_" prefix from filename
    filename = sub_parts[-1]
    if filename.startswith("test_"):
        filename = filename[5:]  # len("test_") == 5
    # Remove .py extension
    if filename.endswith(".py"):
        filename = filename[:-3]

    # Build candidate source dirs
    dirs: list[str] = []

    # Pattern: tests/core/test_foo.py -> src/*/core/
    if len(sub_parts) > 1:
        subdir = "/".join(sub_parts[:-1])
        dirs.append(f"src/{subdir}/")
        # Also try with package prefix
        for prefix_part in parts[:tests_idx]:
            if prefix_part != "src":
                dirs.append(f"src/{prefix_part}/{subdir}/")

    # Pattern: tests/test_foo.py -> src/*/
    # Match any source file named like the test subject
    dirs.append("src/")

    return dirs


def _heuristic_keyword_overlap(
    test_node: GraphNode,
    graph: TraceGraph,
) -> list[LinkSuggestion]:
    """H4: Compare test name/docstring keywords against requirement titles.

    Score: overlap ratio capped at 0.5.
    """
    # Build keyword set from test node
    test_text_parts: list[str] = []

    # Use test label/name
    label = test_node.get_label()
    if label:
        # Convert snake_case to spaces for keyword extraction
        test_text_parts.append(label.replace("_", " "))

    # Use function_name if available
    func_name = test_node.get_field("function_name")
    if func_name:
        test_text_parts.append(func_name.replace("_", " "))

    # Use docstring if available
    docstring = test_node.get_field("docstring")
    if docstring:
        test_text_parts.append(docstring)

    test_text = " ".join(test_text_parts)
    test_keywords = set(extract_keywords(test_text))

    if not test_keywords:
        return []

    test_path = _normalize_path(test_node.source.path) if test_node.source else ""

    suggestions: list[LinkSuggestion] = []

    for req_node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        # Build keyword set from requirement title + assertion text
        req_text_parts = [req_node.get_label() or ""]
        for child in req_node.iter_children():
            if child.kind == NodeKind.ASSERTION:
                req_text_parts.append(child.get_label() or "")

        req_text = " ".join(req_text_parts)
        req_keywords = set(extract_keywords(req_text))

        if not req_keywords:
            continue

        # Calculate overlap ratio
        overlap = test_keywords & req_keywords
        if not overlap:
            continue

        # Ratio based on smaller set to avoid bias toward large requirements
        ratio = len(overlap) / min(len(test_keywords), len(req_keywords))
        score = min(ratio * _SCORE_KEYWORD_CAP, _SCORE_KEYWORD_CAP)

        # Only suggest if meaningful overlap (at least 2 keywords or high ratio)
        if len(overlap) < 2 and ratio < 0.5:
            continue

        suggestions.append(
            LinkSuggestion(
                test_id=test_node.id,
                test_label=test_node.get_label() or test_node.id,
                test_file=test_path,
                requirement_id=req_node.id,
                requirement_title=req_node.get_label() or "",
                confidence=score,
                reasons=[
                    f"keyword overlap ({len(overlap)} shared): " f"{', '.join(sorted(overlap)[:5])}"
                ],
            )
        )

    return suggestions


def _deduplicate_suggestions(
    suggestions: list[LinkSuggestion],
) -> list[LinkSuggestion]:
    """Merge suggestions for the same (test, requirement) pair.

    Keeps the highest confidence and combines reasons.
    """
    key_map: dict[tuple[str, str], LinkSuggestion] = {}

    for s in suggestions:
        key = (s.test_id, s.requirement_id)
        if key in key_map:
            existing = key_map[key]
            if s.confidence > existing.confidence:
                existing.confidence = s.confidence
            # Combine reasons, avoiding duplicates
            for reason in s.reasons:
                if reason not in existing.reasons:
                    existing.reasons.append(reason)
        else:
            # Copy to avoid mutating the original
            key_map[key] = LinkSuggestion(
                test_id=s.test_id,
                test_label=s.test_label,
                test_file=s.test_file,
                requirement_id=s.requirement_id,
                requirement_title=s.requirement_title,
                confidence=s.confidence,
                reasons=list(s.reasons),
            )

    return list(key_map.values())


def apply_link_to_file(
    file_path: Path,
    line: int,
    req_id: str,
    dry_run: bool = False,
) -> str | None:
    """Insert a # Implements: comment into a source file.

    Inserts the comment at the specified line number. If the line is 0,
    inserts at the top of the file (after any shebang/encoding lines).

    Args:
        file_path: Absolute path to the source file.
        line: Line number to insert at (1-based). 0 means top of file.
        req_id: Requirement ID to reference.
        dry_run: If True, return the comment that would be inserted
                 without modifying the file.

    Returns:
        The comment line that was (or would be) inserted, or None on error.
    """
    comment = f"# Implements: {req_id}"

    if dry_run:
        return comment

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return None

    # Determine insertion point
    if line <= 0:
        # Insert at top, after shebang and encoding lines
        insert_at = 0
        for i, existing_line in enumerate(lines):
            stripped = existing_line.strip()
            if stripped.startswith("#!") or stripped.startswith("# -*-"):
                insert_at = i + 1
            else:
                break
    else:
        insert_at = min(line - 1, len(lines))

    lines.insert(insert_at, comment + "\n")

    try:
        file_path.write_text("".join(lines), encoding="utf-8")
    except OSError:
        return None

    return comment
