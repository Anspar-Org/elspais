# Implements: REQ-o00065-A, REQ-o00065-B, REQ-o00065-C, REQ-o00065-E
# Implements: REQ-d00072-A+B+C
"""Link suggestion engine — proposes requirement associations for unlinked nodes.

Analyzes unlinked TEST nodes and proposes requirement/assertion associations
using the discover_assertions search engine. Extracts search terms from test
metadata (function name, class name, file name, docstring) and searches
requirement titles, bodies, and assertion text for matches.

All operations are read-only on the graph; suggestions are returned as data,
not applied.

The ``discover_fn`` parameter allows the caller (typically the MCP server)
to inject the ``_discover_assertions`` function, avoiding circular imports
between ``graph/`` and ``mcp/``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.graph.GraphNode import NodeKind

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph
    from elspais.graph.GraphNode import GraphNode

# Confidence band thresholds
CONFIDENCE_HIGH = 0.8
CONFIDENCE_MEDIUM = 0.5

# Max raw search score used for normalization (title match = 50)
_MAX_EXPECTED_SCORE = 100.0

# Type alias for the discover function injected by the MCP server
DiscoverFn = Callable[..., dict[str, Any]]

# Common words to filter from search queries (too generic to be useful)
_STOPWORDS = frozenset(
    {
        "test",
        "tests",
        "assert",
        "check",
        "verify",
        "should",
        "must",
        "when",
        "then",
        "given",
        "with",
        "from",
        "that",
        "this",
        "does",
        "not",
        "and",
        "the",
        "for",
        "are",
        "can",
        "has",
        "have",
        "will",
        "all",
        "each",
        "every",
        "none",
        "some",
        "any",
    }
)


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
    graph: FederatedGraph,
    repo_root: Path,
    file_path: str | None = None,
    limit: int = 50,
    *,
    discover_fn: DiscoverFn | None = None,
) -> list[LinkSuggestion]:
    """Suggest requirement/assertion links for unlinked test nodes.

    Extracts search terms from each test node's metadata and uses
    discover_assertions to find matching assertions/requirements.

    Args:
        graph: The TraceGraph to analyze (read-only).
        repo_root: Repository root path.
        file_path: Optional file path to restrict analysis to.
        limit: Maximum suggestions to return.
        discover_fn: Callable matching _discover_assertions signature.
            Injected by the MCP server to avoid circular imports.

    Returns:
        List of LinkSuggestion sorted by confidence descending.
    """
    if discover_fn is None:
        return []

    unlinked = _find_unlinked_tests(graph, file_path)
    if not unlinked:
        return []

    all_suggestions: list[LinkSuggestion] = []

    for test_node in unlinked:
        query = _extract_search_terms(test_node)
        if not query:
            continue

        result = discover_fn(graph, query, scope_id="", limit=10)
        assertions = result.get("assertions", [])

        _tfn = test_node.file_node()
        test_file = (_tfn.get_field("relative_path") or "") if _tfn else ""

        for assertion in assertions:
            confidence = _normalize_score(assertion.get("score", 0.0))
            if confidence <= 0:
                continue

            direct = assertion.get("direct_match", False)
            match_type = "direct assertion match" if direct else "requirement context match"

            all_suggestions.append(
                LinkSuggestion(
                    test_id=test_node.id,
                    test_label=test_node.get_label() or test_node.id,
                    test_file=test_file,
                    requirement_id=assertion["id"],
                    requirement_title=assertion.get("text", ""),
                    confidence=confidence,
                    reasons=[f"{match_type}: '{query}' -> {assertion['id']}"],
                )
            )

    deduped = _deduplicate_suggestions(all_suggestions)
    deduped.sort(key=lambda s: s.confidence, reverse=True)
    return deduped[:limit]


def _extract_search_terms(test_node: GraphNode) -> str:
    """Build a search query string from a test node's metadata.

    Extracts meaningful words from:
    - function_name (strip test_ prefix, split on _)
    - class_name (strip Test prefix, split camelCase)
    - file name (strip test_ prefix and .py, split on _)
    - docstring (if available)

    Returns an OR-joined query string for broad matching, or empty string
    if nothing meaningful can be extracted.
    """
    words: list[str] = []

    # Function name: test_validate_config -> ["validate", "config"]
    func_name = test_node.get_field("function_name") or ""
    if func_name.startswith("test_"):
        func_name = func_name[5:]
    if func_name:
        words.extend(func_name.split("_"))

    # Class name: TestConfigValidation -> ["Config", "Validation"]
    class_name = test_node.get_field("class_name") or ""
    if class_name.startswith("Test"):
        class_name = class_name[4:]
    if class_name:
        # Split camelCase: "ConfigValidation" -> ["Config", "Validation"]
        parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", class_name).split()
        words.extend(parts)

    # File name: test_link_suggest.py -> ["link", "suggest"]
    _tfn = test_node.file_node()
    if _tfn:
        rel_path = _tfn.get_field("relative_path") or ""
        filename = Path(rel_path).stem  # strip .py
        if filename.startswith("test_"):
            filename = filename[5:]
        if filename:
            words.extend(filename.split("_"))

    # Docstring
    docstring = test_node.get_field("docstring") or ""
    if docstring:
        # Take first sentence, split into words
        first_sentence = docstring.split(".")[0]
        words.extend(first_sentence.lower().split())

    # Filter: lowercase, remove stopwords, remove very short words, deduplicate
    seen: set[str] = set()
    filtered: list[str] = []
    for w in words:
        w_lower = w.lower().strip()
        if len(w_lower) < 3:
            continue
        if w_lower in _STOPWORDS:
            continue
        if w_lower in seen:
            continue
        seen.add(w_lower)
        filtered.append(w_lower)

    if not filtered:
        return ""

    # Use OR to get broad matching (AND would be too restrictive)
    return " OR ".join(filtered)


def _normalize_score(raw_score: float) -> float:
    """Normalize a raw search score to 0-1 confidence range."""
    return min(raw_score / _MAX_EXPECTED_SCORE, 1.0)


def _find_unlinked_tests(
    graph: FederatedGraph,
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
            _fn = node.file_node()
            if not _fn:
                continue
            node_path = (_fn.get_field("relative_path") or "").replace("\\", "/")
            filter_path = file_path.replace("\\", "/")
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
