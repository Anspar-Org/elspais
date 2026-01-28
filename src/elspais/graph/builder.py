"""Graph Builder - Constructs TraceGraph from parsed content.

This module provides the builder pattern for constructing a complete
traceability graph from parsed content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.graph.relations import Edge, EdgeKind
from elspais.graph.parsers import ParsedContent


@dataclass
class TraceGraph:
    """Container for the complete traceability graph.

    Provides indexed access to all nodes and methods for graph-wide
    operations. Uses iterator-only API for traversal.

    Attributes:
        repo_root: Path to the repository root.
    """

    repo_root: Path = field(default_factory=Path.cwd)

    # Internal storage (prefixed) - excluded from constructor
    _roots: list[GraphNode] = field(default_factory=list, init=False)
    _index: dict[str, GraphNode] = field(default_factory=dict, init=False, repr=False)

    def iter_roots(self) -> Iterator[GraphNode]:
        """Iterate root nodes."""
        yield from self._roots

    def root_count(self) -> int:
        """Return number of root nodes."""
        return len(self._roots)

    def has_root(self, node_id: str) -> bool:
        """Check if a node ID is a root."""
        return any(r.id == node_id for r in self._roots)

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
        for root in self._roots:
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
        elif content.content_type == "test_result":
            self._add_test_result(content)
        elif content.content_type == "remainder":
            self._add_remainder(content)

    def _add_requirement(self, content: ParsedContent) -> None:
        """Add a requirement node and its assertions."""
        data = content.parsed_data
        req_id = data["id"]

        # Get source path from context if available
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else ""

        # Create requirement node
        source = SourceLocation(
            path=source_path,
            line=content.start_line,
            end_line=content.end_line,
        )

        node = GraphNode(
            id=req_id,
            kind=NodeKind.REQUIREMENT,
            label=data.get("title", ""),
            source=source,
        )
        node._content = {
            "level": data.get("level"),
            "status": data.get("status"),
            "hash": data.get("hash"),
        }
        self._nodes[req_id] = node

        # Create assertion nodes
        for assertion in data.get("assertions", []):
            assertion_id = f"{req_id}-{assertion['label']}"
            assertion_node = GraphNode(
                id=assertion_id,
                kind=NodeKind.ASSERTION,
                label=assertion["text"],
            )
            assertion_node._content = {"label": assertion["label"]}
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
        )
        node._content = {
            "actor": data.get("actor"),
            "goal": data.get("goal"),
        }
        self._nodes[journey_id] = node

    def _add_code_ref(self, content: ParsedContent) -> None:
        """Add code reference nodes."""
        data = content.parsed_data
        source_ctx = getattr(content, "source_context", None)
        source_id = source_ctx.source_id if source_ctx else "code"

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
        source_ctx = getattr(content, "source_context", None)
        source_id = source_ctx.source_id if source_ctx else "test"

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

    def _add_test_result(self, content: ParsedContent) -> None:
        """Add a test result node."""
        data = content.parsed_data
        result_id = data["id"]
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else ""

        node = GraphNode(
            id=result_id,
            kind=NodeKind.TEST_RESULT,
            label=f"{data.get('status', 'unknown')}: {result_id}",
            source=SourceLocation(
                path=source_path,
                line=content.start_line,
                end_line=content.end_line,
            ),
        )
        node._content = {
            "status": data.get("status"),
            "test_id": data.get("test_id"),
            "duration": data.get("duration"),
        }
        self._nodes[result_id] = node

    def _add_remainder(self, content: ParsedContent) -> None:
        """Add a remainder/unclaimed content node."""
        data = content.parsed_data
        source_ctx = getattr(content, "source_context", None)
        source_path = source_ctx.source_id if source_ctx else ""

        # Use provided ID or generate from source location
        remainder_id = data.get("id") or f"rem:{source_path}:{content.start_line}"
        text = data.get("text", content.raw_text or "")

        node = GraphNode(
            id=remainder_id,
            kind=NodeKind.REMAINDER,
            label=text[:50] + "..." if len(text) > 50 else text,
            source=SourceLocation(
                path=source_path,
                line=content.start_line,
                end_line=content.end_line,
            ),
        )
        node._content = {"text": text}
        self._nodes[remainder_id] = node

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
                # If target is an assertion, link from its parent requirement
                # with assertion_targets set, so the child appears under the
                # parent REQ (not the assertion node) with assertion badges
                if target.kind == NodeKind.ASSERTION:
                    # Find the parent requirement of this assertion
                    parent_reqs = [
                        p for p in target.iter_parents()
                        if p.kind == NodeKind.REQUIREMENT
                    ]
                    if parent_reqs:
                        parent_req = parent_reqs[0]
                        assertion_label = target.get_field("label", "")
                        parent_req.link(
                            source,
                            edge_kind,
                            assertion_targets=[assertion_label] if assertion_label else None,
                        )
                    else:
                        # Fallback: link directly if no parent found
                        target.link(source, edge_kind)
                else:
                    # Link target as parent of source (implements relationship)
                    target.link(source, edge_kind)

        # Identify roots (nodes with no parents)
        roots = [
            node for node in self._nodes.values()
            if not node._parents and node.kind == NodeKind.REQUIREMENT
        ]

        # Also include journeys as roots
        roots.extend(
            node for node in self._nodes.values()
            if node.kind == NodeKind.USER_JOURNEY
        )

        graph = TraceGraph(repo_root=self.repo_root)
        graph._roots = roots
        graph._index = dict(self._nodes)
        return graph
