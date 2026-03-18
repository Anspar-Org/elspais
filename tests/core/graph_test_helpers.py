"""Test helpers for black-box graph testing.

This module provides factories and string conversion helpers for testing
the graph through observable output rather than internal state.
"""

from __future__ import annotations

from pathlib import Path

from elspais.graph import GraphNode
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.GraphNode import FileType, NodeKind
from elspais.graph.parsers import ParsedContent
from elspais.graph.relations import EdgeKind

# === Constants ===


def make_node_with_file(
    node_id: str,
    kind: NodeKind,
    label: str = "",
    path: str = "spec/test.md",
    line: int = 1,
    end_line: int | None = None,
    repo: str | None = None,
    file_node: GraphNode | None = None,
) -> GraphNode:
    """Create a GraphNode with a FILE parent and parse_line fields.

    This replaces the old pattern of ``GraphNode(..., source=SourceLocation(...))``.
    Creates a FILE node and wires a CONTAINS edge from FILE to the content node.
    If ``file_node`` is provided, reuses it instead of creating a new one.

    Returns the content node (not the FILE node).
    """
    node = GraphNode(id=node_id, kind=kind, label=label)
    node.set_field("parse_line", line)
    node.set_field("parse_end_line", end_line)

    # Create or reuse FILE node for this path
    if file_node is None:
        file_id = f"file:{path}"
        file_node = GraphNode(id=file_id, kind=NodeKind.FILE, label=Path(path).name)
        file_node.set_field("file_type", FileType.SPEC)
        file_node.set_field("relative_path", path)
        file_node.set_field("absolute_path", f"/repo/{path}")
        file_node.set_field("repo", repo)

    file_node.link(node, EdgeKind.CONTAINS)
    return node


def wire_file_parent(
    node: GraphNode,
    path: str = "spec/test.md",
    line: int = 1,
    end_line: int | None = None,
    repo: str | None = None,
    graph: TraceGraph | None = None,
) -> GraphNode:
    """Wire an existing node to a FILE parent (for test migration).

    Creates a FILE node, sets parse_line/parse_end_line on the content node,
    and wires a CONTAINS edge. Optionally registers the FILE node in a graph index.

    Returns the FILE node (not the content node).
    """
    node.set_field("parse_line", line)
    node.set_field("parse_end_line", end_line)

    file_id = f"file:{path}"
    # Check if FILE already exists in graph index
    existing = graph._index.get(file_id) if graph else None
    if existing and existing.kind == NodeKind.FILE:
        file_node = existing
    else:
        file_node = GraphNode(id=file_id, kind=NodeKind.FILE, label=Path(path).name)
        file_node.set_field("file_type", FileType.SPEC)
        file_node.set_field("relative_path", path)
        file_node.set_field("absolute_path", f"/repo/{path}")
        file_node.set_field("repo", repo)
        if graph is not None:
            graph._index[file_id] = file_node

    file_node.link(node, EdgeKind.CONTAINS)
    return file_node


VALID_LEVELS = {"PRD", "OPS", "DEV"}


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
    satisfies: list[str] | None = None,
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
        satisfies: List of IDs this requirement satisfies (cross-cutting)
        assertions: List of assertion dicts with "label" and "text"
        source_path: Source file path
        start_line: Start line in source
        end_line: End line in source
        hash_value: Optional content hash

    Returns:
        ParsedContent ready for GraphBuilder.add_parsed_content()

    Raises:
        ValueError: If level is not one of PRD, OPS, DEV.
    """
    if level not in VALID_LEVELS:
        raise ValueError(f"Invalid level '{level}'. Must be one of: {VALID_LEVELS}")

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
            "satisfies": satisfies or [],
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
    validates: list[str] | None = None,
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
        validates: List of requirement IDs this journey validates
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
            "validates": validates or [],
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
    verifies: list[str],
    source_path: str = "tests/test_module.py",
    start_line: int = 1,
    end_line: int = 10,
    function_name: str | None = None,
    class_name: str | None = None,
    function_line: int | None = None,
) -> ParsedContent:
    """Factory for creating test references.

    Args:
        verifies: List of requirement IDs this test verifies
        source_path: Source file path
        start_line: Start line in source
        end_line: End line in source
        function_name: Optional test function name for canonical IDs
        class_name: Optional test class name for canonical IDs
        function_line: Optional line of the function def

    Returns:
        ParsedContent ready for GraphBuilder.add_parsed_content()
    """
    parsed_data: dict = {
        "verifies": verifies,
    }
    if function_name is not None:
        parsed_data["function_name"] = function_name
    if class_name is not None:
        parsed_data["class_name"] = class_name
    if function_line is not None:
        parsed_data["function_line"] = function_line

    content = ParsedContent(
        content_type="test_ref",
        start_line=start_line,
        end_line=end_line,
        raw_text="",
        parsed_data=parsed_data,
    )
    content.source_context = MockSourceContext(source_id=source_path)
    return content


def make_test_result(
    result_id: str,
    status: str = "passed",
    test_id: str | None = None,
    duration: float = 0.0,
    source_path: str = "results/test_results.xml",
    start_line: int = 1,
    end_line: int = 1,
    verifies: list[str] | None = None,
    name: str = "",
    classname: str = "",
) -> ParsedContent:
    """Factory for creating test result content.

    Args:
        result_id: Unique result ID
        status: Test status ("passed", "failed", "skipped", "error")
        test_id: Optional ID of the test that produced this result
        duration: Test duration in seconds
        source_path: Path to results file
        start_line: Start line in results file
        end_line: End line in results file
        verifies: List of REQ IDs this test verifies (extracted from name)
        name: Test function name
        classname: Test class/module name

    Returns:
        ParsedContent ready for GraphBuilder.add_parsed_content()
    """
    content = ParsedContent(
        content_type="test_result",
        start_line=start_line,
        end_line=end_line,
        raw_text="",
        parsed_data={
            "id": result_id,
            "status": status,
            "test_id": test_id,
            "duration": duration,
            "verifies": verifies or [],
            "name": name,
            "classname": classname,
        },
    )
    content.source_context = MockSourceContext(source_id=source_path)
    return content


def make_remainder(
    remainder_id: str,
    text: str = "",
    source_path: str = "spec/file.md",
    start_line: int = 1,
    end_line: int = 1,
) -> ParsedContent:
    """Factory for creating remainder content.

    Remainder nodes represent unclaimed content - lines not matched by
    any other parser (requirements, journeys, code refs, etc).

    Args:
        remainder_id: Unique node ID
        text: The unclaimed text content
        source_path: Path to source file
        start_line: Start line in source
        end_line: End line in source

    Returns:
        ParsedContent ready for GraphBuilder.add_parsed_content()
    """
    content = ParsedContent(
        content_type="remainder",
        start_line=start_line,
        end_line=end_line,
        raw_text=text,
        parsed_data={
            "id": remainder_id,
            "text": text,
        },
    )
    content.source_context = MockSourceContext(source_id=source_path)
    return content


# === Graph Builder Convenience ===


def build_graph(
    *contents: ParsedContent,
    repo_root: Path | None = None,
) -> TraceGraph:
    """Build a TraceGraph from multiple ParsedContent items.

    Convenience wrapper around GraphBuilder that eliminates boilerplate.
    Automatically creates FILE nodes from source_context paths.

    Args:
        *contents: ParsedContent items to add to the graph
        repo_root: Optional repository root path

    Returns:
        Constructed TraceGraph
    """
    builder = GraphBuilder(repo_root=repo_root)

    # Create FILE nodes from source contexts (like factory.py does)
    file_nodes: dict[str, GraphNode] = {}
    for content in contents:
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else None
        file_node = None
        if source_path and source_path not in file_nodes:
            file_id = f"file:{source_path}"
            file_node = GraphNode(id=file_id, kind=NodeKind.FILE, label=Path(source_path).name)
            file_node.set_field("file_type", FileType.SPEC)
            file_node.set_field("relative_path", source_path)
            file_node.set_field("absolute_path", str(Path(repo_root or ".") / source_path))
            file_node.set_field("repo", None)
            file_nodes[source_path] = file_node
            builder.register_file_node(file_node)
        elif source_path:
            file_node = file_nodes[source_path]
        builder.add_parsed_content(content, file_node=file_node)

    return builder.build()


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


def descendants_string(node: GraphNode) -> str:
    """Return sorted comma-separated descendant IDs, excluding self.

    Args:
        node: GraphNode to inspect

    Returns:
        Comma-separated string of descendant IDs, sorted alphabetically
    """
    return ",".join(sorted(d.id for d in node.walk("pre") if d.id != node.id))


def edges_by_kind_string(node: GraphNode, kind: EdgeKind) -> str:
    """Return sorted semicolon-separated edges of a specific kind.

    Format: "source_id->target_id"

    Args:
        node: GraphNode to inspect
        kind: EdgeKind to filter by

    Returns:
        Semicolon-separated string of edge descriptions
    """
    parts = []
    for e in node.iter_edges_by_kind(kind):
        parts.append(f"{e.source.id}->{e.target.id}")
    return ";".join(sorted(parts))


def metrics_string(node: GraphNode, *keys: str) -> str:
    """Return comma-separated key=value pairs for specified metrics.

    Args:
        node: GraphNode to inspect
        *keys: Metric keys to include

    Returns:
        Comma-separated string of key=value pairs
    """
    parts = []
    for key in keys:
        value = node.get_metric(key)
        if value is not None:
            parts.append(f"{key}={value}")
    return ",".join(parts)
