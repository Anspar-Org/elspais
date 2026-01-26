"""Graph Builder - Constructs TraceGraph from parsed content.

This module provides the builder pattern for constructing a complete
traceability graph from parsed content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from elspais.arch3.Graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.arch3.Graph.relations import Edge, EdgeKind
from elspais.arch3.Graph.MDparser import ParsedContent


@dataclass
class TraceGraph:
    """Container for the complete traceability graph.

    Provides indexed access to all nodes and methods for graph-wide
    operations.

    Attributes:
        roots: Top-level nodes (requirements with no implements).
        repo_root: Path to the repository root.
    """

    roots: list[GraphNode] = field(default_factory=list)
    repo_root: Path = field(default_factory=Path.cwd)
    _index: dict[str, GraphNode] = field(default_factory=dict, repr=False)

    def find_by_id(self, node_id: str) -> GraphNode | None:
        """Find node by ID.

        Args:
            node_id: The node ID to find.

        Returns:
            The matching GraphNode, or None if not found.
        """
        return self._index.get(node_id)

    def all_nodes(self, order: str = "pre") -> Iterator[GraphNode]:
        """Iterate all nodes in graph.

        Args:
            order: Traversal order ("pre", "post", "level").

        Yields:
            All GraphNode instances in the graph.
        """
        for root in self.roots:
            yield from root.walk(order)

    def nodes_by_kind(self, kind: NodeKind) -> Iterator[GraphNode]:
        """Get all nodes of a specific kind.

        Args:
            kind: The NodeKind to filter by.

        Yields:
            GraphNode instances of the specified kind.
        """
        for node in self._index.values():
            if node.kind == kind:
                yield node

    def node_count(self) -> int:
        """Return total number of nodes in the graph."""
        return len(self._index)


class GraphBuilder:
    """Builder for constructing TraceGraph from parsed content.

    Usage:
        builder = GraphBuilder()
        for content in parsed_contents:
            builder.add_parsed_content(content)
        graph = builder.build()
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        """Initialize the graph builder.

        Args:
            repo_root: Repository root path.
        """
        self.repo_root = repo_root or Path.cwd()
        self._nodes: dict[str, GraphNode] = {}
        self._pending_links: list[tuple[str, str, EdgeKind]] = []

    def add_parsed_content(self, content: ParsedContent) -> None:
        """Add parsed content to the graph.

        Args:
            content: Parsed content from a parser.
        """
        if content.content_type == "requirement":
            self._add_requirement(content)
        elif content.content_type == "journey":
            self._add_journey(content)
        elif content.content_type == "code_ref":
            self._add_code_ref(content)
        elif content.content_type == "test_ref":
            self._add_test_ref(content)

    def _add_requirement(self, content: ParsedContent) -> None:
        """Add a requirement node and its assertions."""
        data = content.parsed_data
        req_id = data["id"]

        # Create requirement node
        source = SourceLocation(
            path=getattr(content, "source_context", {}).get("source_id", ""),
            line=content.start_line,
            end_line=content.end_line,
        ) if hasattr(content, "source_context") else SourceLocation(
            path="",
            line=content.start_line,
            end_line=content.end_line,
        )

        node = GraphNode(
            id=req_id,
            kind=NodeKind.REQUIREMENT,
            label=data.get("title", ""),
            source=source,
            content={
                "level": data.get("level"),
                "status": data.get("status"),
                "hash": data.get("hash"),
            },
        )
        self._nodes[req_id] = node

        # Create assertion nodes
        for assertion in data.get("assertions", []):
            assertion_id = f"{req_id}-{assertion['label']}"
            assertion_node = GraphNode(
                id=assertion_id,
                kind=NodeKind.ASSERTION,
                label=assertion["text"],
                content={"label": assertion["label"]},
            )
            self._nodes[assertion_id] = assertion_node

            # Link assertion to parent requirement
            node.add_child(assertion_node)

        # Queue implements/refines links for later resolution
        for impl_ref in data.get("implements", []):
            self._pending_links.append((req_id, impl_ref, EdgeKind.IMPLEMENTS))

        for refine_ref in data.get("refines", []):
            self._pending_links.append((req_id, refine_ref, EdgeKind.REFINES))

    def _add_journey(self, content: ParsedContent) -> None:
        """Add a user journey node."""
        data = content.parsed_data
        journey_id = data["id"]

        node = GraphNode(
            id=journey_id,
            kind=NodeKind.USER_JOURNEY,
            label=data.get("title", ""),
            content={
                "actor": data.get("actor"),
                "goal": data.get("goal"),
            },
        )
        self._nodes[journey_id] = node

    def _add_code_ref(self, content: ParsedContent) -> None:
        """Add code reference nodes."""
        data = content.parsed_data
        source_id = getattr(content, "source_context", {}).get("source_id", "code")

        for impl_ref in data.get("implements", []):
            code_id = f"code:{source_id}:{content.start_line}"
            if code_id not in self._nodes:
                node = GraphNode(
                    id=code_id,
                    kind=NodeKind.CODE,
                    label=f"Code at {source_id}:{content.start_line}",
                )
                self._nodes[code_id] = node

            self._pending_links.append((code_id, impl_ref, EdgeKind.IMPLEMENTS))

    def _add_test_ref(self, content: ParsedContent) -> None:
        """Add test reference nodes."""
        data = content.parsed_data
        source_id = getattr(content, "source_context", {}).get("source_id", "test")

        for val_ref in data.get("validates", []):
            test_id = f"test:{source_id}:{content.start_line}"
            if test_id not in self._nodes:
                node = GraphNode(
                    id=test_id,
                    kind=NodeKind.TEST,
                    label=f"Test at {source_id}:{content.start_line}",
                )
                self._nodes[test_id] = node

            self._pending_links.append((test_id, val_ref, EdgeKind.VALIDATES))

    def build(self) -> TraceGraph:
        """Build the final TraceGraph.

        Resolves all pending links and identifies root nodes.

        Returns:
            Complete TraceGraph.
        """
        # Resolve pending links
        for source_id, target_id, edge_kind in self._pending_links:
            source = self._nodes.get(source_id)
            target = self._nodes.get(target_id)

            if source and target:
                # Link target as parent of source (implements relationship)
                target.link(source, edge_kind)

        # Identify roots (nodes with no parents)
        roots = [
            node for node in self._nodes.values()
            if not node.parents and node.kind == NodeKind.REQUIREMENT
        ]

        # Also include journeys as roots
        roots.extend(
            node for node in self._nodes.values()
            if node.kind == NodeKind.USER_JOURNEY
        )

        return TraceGraph(
            roots=roots,
            repo_root=self.repo_root,
            _index=dict(self._nodes),
        )
