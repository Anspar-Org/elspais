"""Test helpers for black-box graph testing.

This module provides factories and string conversion helpers for testing
the graph through observable output rather than internal state.
"""

from __future__ import annotations

from elspais.graph import GraphNode
from elspais.graph.builder import TraceGraph
from elspais.graph.parsers import ParsedContent


# === Mock Source Context ===


class MockSourceContext:
    """Mock source context for parsed content."""

    def __init__(self, source_id: str):
        self.source_id = source_id


# === ParsedContent Factory ===


def make_requirement(
    req_id: str,
    title: str = "",
    level: str = "PRD",
    status: str = "Active",
    implements: list[str] | None = None,
    refines: list[str] | None = None,
    assertions: list[dict] | None = None,
    source_path: str = "spec/test.md",
    start_line: int = 1,
    end_line: int = 10,
    hash_value: str | None = None,
) -> ParsedContent:
    """Factory for creating test requirements.

    Args:
        req_id: Requirement ID (e.g., "REQ-p00001")
        title: Requirement title (defaults to req_id if empty)
        level: Requirement level (PRD, OPS, DEV)
        status: Requirement status (Active, Deprecated, etc.)
        implements: List of IDs this requirement implements
        refines: List of IDs this requirement refines
        assertions: List of assertion dicts with "label" and "text"
        source_path: Source file path
        start_line: Start line in source
        end_line: End line in source
        hash_value: Optional content hash

    Returns:
        ParsedContent ready for GraphBuilder.add_parsed_content()
    """
    content = ParsedContent(
        content_type="requirement",
        start_line=start_line,
        end_line=end_line,
        raw_text="",
        parsed_data={
            "id": req_id,
            "title": title or req_id,
            "level": level,
            "status": status,
            "implements": implements or [],
            "refines": refines or [],
            "assertions": assertions or [],
            "hash": hash_value,
        },
    )
    content.source_context = MockSourceContext(source_id=source_path)
    return content


def make_journey(
    journey_id: str,
    title: str = "",
    actor: str = "User",
    goal: str = "",
    source_path: str = "spec/journeys.md",
    start_line: int = 1,
    end_line: int = 10,
) -> ParsedContent:
    """Factory for creating test user journeys.

    Args:
        journey_id: Journey ID (e.g., "UJ-001")
        title: Journey title
        actor: Actor performing the journey
        goal: Journey goal
        source_path: Source file path
        start_line: Start line in source
        end_line: End line in source

    Returns:
        ParsedContent ready for GraphBuilder.add_parsed_content()
    """
    content = ParsedContent(
        content_type="journey",
        start_line=start_line,
        end_line=end_line,
        raw_text="",
        parsed_data={
            "id": journey_id,
            "title": title or journey_id,
            "actor": actor,
            "goal": goal,
        },
    )
    content.source_context = MockSourceContext(source_id=source_path)
    return content


def make_code_ref(
    implements: list[str],
    source_path: str = "src/module.py",
    start_line: int = 1,
    end_line: int = 10,
) -> ParsedContent:
    """Factory for creating test code references.

    Args:
        implements: List of requirement IDs this code implements
        source_path: Source file path
        start_line: Start line in source
        end_line: End line in source

    Returns:
        ParsedContent ready for GraphBuilder.add_parsed_content()
    """
    content = ParsedContent(
        content_type="code_ref",
        start_line=start_line,
        end_line=end_line,
        raw_text="",
        parsed_data={
            "implements": implements,
        },
    )
    content.source_context = MockSourceContext(source_id=source_path)
    return content


def make_test_ref(
    validates: list[str],
    source_path: str = "tests/test_module.py",
    start_line: int = 1,
    end_line: int = 10,
) -> ParsedContent:
    """Factory for creating test references.

    Args:
        validates: List of requirement IDs this test validates
        source_path: Source file path
        start_line: Start line in source
        end_line: End line in source

    Returns:
        ParsedContent ready for GraphBuilder.add_parsed_content()
    """
    content = ParsedContent(
        content_type="test_ref",
        start_line=start_line,
        end_line=end_line,
        raw_text="",
        parsed_data={
            "validates": validates,
        },
    )
    content.source_context = MockSourceContext(source_id=source_path)
    return content


# === String Conversion Helpers (use public methods only) ===


def children_string(node: GraphNode) -> str:
    """Return sorted comma-separated child IDs.

    Args:
        node: GraphNode to inspect

    Returns:
        Comma-separated string of child IDs, sorted alphabetically
    """
    return ",".join(sorted(c.id for c in node.iter_children()))


def parents_string(node: GraphNode) -> str:
    """Return sorted comma-separated parent IDs.

    Args:
        node: GraphNode to inspect

    Returns:
        Comma-separated string of parent IDs, sorted alphabetically
    """
    return ",".join(sorted(p.id for p in node.iter_parents()))


def walk_string(node: GraphNode, order: str = "pre") -> str:
    """Return comma-separated node IDs in traversal order.

    Traversal order is preserved (not sorted).

    Args:
        node: GraphNode to start traversal from
        order: Traversal order ("pre", "post", "level")

    Returns:
        Comma-separated string of node IDs in traversal order
    """
    return ",".join(n.id for n in node.walk(order))


def ancestors_string(node: GraphNode) -> str:
    """Return sorted comma-separated ancestor IDs.

    Args:
        node: GraphNode to inspect

    Returns:
        Comma-separated string of ancestor IDs, sorted alphabetically
    """
    return ",".join(sorted(a.id for a in node.ancestors()))


def outgoing_edges_string(node: GraphNode) -> str:
    """Return sorted semicolon-separated edge descriptions.

    Format: "source_id->target_id:edge_kind"

    Args:
        node: GraphNode to inspect

    Returns:
        Semicolon-separated string of edge descriptions
    """
    parts = []
    for e in node.iter_outgoing_edges():
        parts.append(f"{e.source.id}->{e.target.id}:{e.kind.value}")
    return ";".join(sorted(parts))


def incoming_edges_string(node: GraphNode) -> str:
    """Return sorted semicolon-separated incoming edge descriptions.

    Format: "source_id->target_id:edge_kind"

    Args:
        node: GraphNode to inspect

    Returns:
        Semicolon-separated string of edge descriptions
    """
    parts = []
    for e in node.iter_incoming_edges():
        parts.append(f"{e.source.id}->{e.target.id}:{e.kind.value}")
    return ";".join(sorted(parts))


def graph_roots_string(graph: TraceGraph) -> str:
    """Return sorted comma-separated root node IDs.

    Args:
        graph: TraceGraph to inspect

    Returns:
        Comma-separated string of root node IDs, sorted alphabetically
    """
    return ",".join(sorted(r.id for r in graph.iter_roots()))


def graph_node_ids_string(graph: TraceGraph) -> str:
    """Return sorted comma-separated all node IDs.

    Args:
        graph: TraceGraph to inspect

    Returns:
        Comma-separated string of all node IDs, sorted alphabetically
    """
    return ",".join(sorted(n.id for n in graph.all_nodes()))
