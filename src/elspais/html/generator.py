"""HTML Generator for traceability reports.

This module generates interactive HTML traceability views from TraceGraph.
Uses Jinja2 templates for rich interactive output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph
    from elspais.graph.GraphNode import GraphNode


@dataclass
class TreeRow:
    """Represents a single row in the tree view."""

    id: str
    display_id: str
    title: str
    level: str
    status: str
    coverage: str  # "none", "partial", "full"
    topic: str
    depth: int
    parent_id: str | None
    assertions: list[str]  # Assertion letters like ["A", "B"]
    is_leaf: bool
    is_changed: bool
    is_uncommitted: bool
    is_roadmap: bool
    is_code: bool
    has_children: bool
    has_failures: bool


@dataclass
class ViewStats:
    """Statistics for the header display."""

    prd_count: int = 0
    ops_count: int = 0
    dev_count: int = 0
    total_count: int = 0
    file_count: int = 0


class HTMLGenerator:
    """Generates interactive HTML traceability view from TraceGraph.

    Uses Jinja2 templates to render a rich, interactive tree view with:
    - Hierarchical expand/collapse
    - Multiple view modes (flat/hierarchical)
    - Git change detection
    - Coverage indicators
    - Filtering and search

    Args:
        graph: The TraceGraph containing all requirement data.
        version: Version string for display (elspais version).
    """

    def __init__(
        self,
        graph: TraceGraph,
        base_path: str = "",
        version: int | str = 1,
    ) -> None:
        self.graph = graph
        self.base_path = base_path
        self.version = version

    def generate(self, embed_content: bool = False) -> str:
        """Generate the complete HTML report.

        Args:
            embed_content: If True, embed full requirement content as JSON.

        Returns:
            Complete HTML document as string.
        """
        try:
            from jinja2 import Environment, PackageLoader, select_autoescape

            env = Environment(
                loader=PackageLoader("elspais.html", "templates"),
                autoescape=select_autoescape(["html", "xml"]),
            )
            template = env.get_template("trace_view.html.j2")
        except ImportError:
            raise ImportError(
                "HTMLGenerator requires the trace-view extra. "
                "Install with: pip install elspais[trace-view]"
            )

        # Apply git annotations to all nodes
        self._annotate_git_state()

        # Build data structures
        stats = self._compute_stats()
        rows = self._build_tree_rows()
        statuses = self._collect_unique_values("status")
        topics = self._collect_unique_values("topic")
        tree_data = self._build_tree_data() if embed_content else {}

        # Render template
        html_content = template.render(
            stats=stats,
            rows=rows,
            statuses=sorted(statuses),
            topics=sorted(topics),
            tree_data=tree_data,
            version=self.version,
        )

        return html_content

    def _annotate_git_state(self) -> None:
        """Apply git state annotations to all requirement nodes.

        Detects uncommitted changes and changes vs main branch for filtering.
        """
        from elspais.graph import NodeKind
        from elspais.graph.annotators import annotate_git_state, annotate_display_info

        # Try to get git info
        git_info = None
        try:
            from elspais.utilities.git import (
                get_repo_root,
                get_modified_files,
                get_changed_vs_branch,
                get_committed_req_locations,
                GitChangeInfo,
            )

            repo_root = self.graph.repo_root
            if repo_root:
                modified, untracked = get_modified_files(repo_root)
                branch_changed = get_changed_vs_branch(repo_root)
                committed_locs = get_committed_req_locations(repo_root, "spec")

                git_info = GitChangeInfo(
                    modified_files=set(modified),
                    untracked_files=set(untracked),
                    branch_changed_files=set(branch_changed),
                    committed_req_locations=committed_locs,
                )
        except Exception:
            # Git not available or error - continue without git info
            pass

        # Annotate all requirement nodes
        for node in self.graph.all_nodes():
            if node.kind == NodeKind.REQUIREMENT:
                annotate_git_state(node, git_info)
                annotate_display_info(node)

    def _compute_stats(self) -> ViewStats:
        """Compute statistics for the header."""
        from elspais.graph import NodeKind

        stats = ViewStats()
        files: set[str] = set()

        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            stats.total_count += 1

            level = (node.level or "").upper()
            if level == "PRD":
                stats.prd_count += 1
            elif level == "OPS":
                stats.ops_count += 1
            elif level == "DEV":
                stats.dev_count += 1

            if node.source:
                files.add(node.source.path)

        # Count all traced files (code, tests, specs)
        for node in self.graph.all_nodes():
            if node.source:
                files.add(node.source.path)

        stats.file_count = len(files)
        return stats

    def _build_tree_rows(self) -> list[TreeRow]:
        """Build flat list of rows representing the hierarchical tree.

        Nodes can appear multiple times if they have multiple parents.
        Uses DFS traversal to maintain parent-child ordering.
        """
        from elspais.graph import NodeKind
        from elspais.graph.relations import EdgeKind

        rows: list[TreeRow] = []
        visited_at_depth: dict[tuple[str, int, str | None], bool] = {}

        def get_topic(node: GraphNode) -> str:
            """Extract topic from file path."""
            if not node.source:
                return ""
            path = node.source.path
            # Extract filename without extension
            # e.g., "spec/prd-system.md" -> "prd-system" -> "system"
            filename = Path(path).stem
            # Remove level prefix if present
            for prefix in ("prd-", "ops-", "dev-"):
                if filename.lower().startswith(prefix):
                    return filename[len(prefix) :]
            return filename

        def is_roadmap(node: GraphNode) -> bool:
            """Check if node is from a roadmap file."""
            if not node.source:
                return False
            return "roadmap" in node.source.path.lower()

        def compute_coverage(node: GraphNode) -> tuple[str, bool]:
            """Compute coverage status and failure flag for a requirement.

            Returns:
                Tuple of (coverage_status, has_failures)
                coverage_status: "none", "partial", or "full"
            """
            # Get assertions for this requirement
            assertions: list[GraphNode] = []
            for child in node.iter_children():
                if child.kind == NodeKind.ASSERTION:
                    assertions.append(child)

            if not assertions:
                # No assertions - check if any code references the req directly
                has_code = False
                for child in node.iter_children():
                    if child.kind == NodeKind.CODE:
                        has_code = True
                        break
                return ("full" if has_code else "none", False)

            # Count assertions with code implementations
            covered_count = 0
            has_failures = False

            for assertion in assertions:
                has_impl = False
                for impl in assertion.iter_children():
                    if impl.kind == NodeKind.CODE:
                        has_impl = True
                    elif impl.kind == NodeKind.TEST_RESULT:
                        # Check for failures
                        result_status = impl.get_field("status", "")
                        if result_status.lower() in ("failed", "error", "failure"):
                            has_failures = True
                if has_impl:
                    covered_count += 1

            # Also check tests for failures
            for child in node.iter_children():
                if child.kind == NodeKind.TEST:
                    for result in child.iter_children():
                        if result.kind == NodeKind.TEST_RESULT:
                            result_status = result.get_field("status", "")
                            if result_status.lower() in ("failed", "error", "failure"):
                                has_failures = True

            if covered_count == 0:
                return ("none", has_failures)
            elif covered_count < len(assertions):
                return ("partial", has_failures)
            else:
                return ("full", has_failures)

        def get_assertion_letters(node: GraphNode, parent_id: str | None) -> list[str]:
            """Get assertion letters that this node implements from a specific parent."""
            if not parent_id:
                return []

            letters: list[str] = []
            for edge in node.iter_incoming_edges():
                if edge.source.id == parent_id and edge.assertion_targets:
                    letters.extend(edge.assertion_targets)
            return sorted(set(letters))

        def has_req_children(node: GraphNode) -> bool:
            """Check if node has requirement children (for tree expand/collapse)."""
            for child in node.iter_children():
                if child.kind == NodeKind.REQUIREMENT:
                    return True
            return False

        def has_code_children(node: GraphNode) -> bool:
            """Check if node has code children."""
            for child in node.iter_children():
                if child.kind == NodeKind.CODE:
                    return True
            return False

        def traverse(
            node: GraphNode,
            depth: int,
            parent_id: str | None,
            parent_assertions: list[str] | None = None,
        ) -> None:
            """DFS traversal to build rows."""
            # Avoid infinite loops - track by (id, depth, parent)
            key = (node.id, depth, parent_id)
            if key in visited_at_depth:
                return
            visited_at_depth[key] = True

            # Only process requirements and code nodes
            if node.kind not in (NodeKind.REQUIREMENT, NodeKind.CODE):
                return

            is_code = node.kind == NodeKind.CODE
            coverage, has_failures = ("none", False) if is_code else compute_coverage(node)
            assertion_letters = get_assertion_letters(node, parent_id) if parent_assertions is None else parent_assertions

            # Create row
            row = TreeRow(
                id=f"{node.id}_{depth}_{parent_id or 'root'}",  # Unique key for multi-parent
                display_id=node.id,
                title=node.label or "",
                level=(node.level or "").upper() if not is_code else "",
                status=(node.status or "").upper() if not is_code else "",
                coverage=coverage,
                topic=get_topic(node) if not is_code else "",
                depth=depth,
                parent_id=f"{parent_id}_{depth - 1}_{rows[-1].parent_id if rows and depth > 0 else 'root'}" if parent_id and depth > 0 else None,
                assertions=assertion_letters,
                is_leaf=not has_req_children(node) and not is_code,
                is_changed=node.get_metric("is_branch_changed", False),
                is_uncommitted=node.get_metric("is_uncommitted", False) or node.get_metric("is_untracked", False),
                is_roadmap=is_roadmap(node),
                is_code=is_code,
                has_children=has_req_children(node) or has_code_children(node),
                has_failures=has_failures,
            )

            # Fix parent_id to reference actual row id
            if parent_id and depth > 0:
                # Find the parent row we just added
                for prev_row in reversed(rows):
                    if prev_row.display_id == parent_id and prev_row.depth == depth - 1:
                        row.parent_id = prev_row.id
                        break

            rows.append(row)

            # Traverse children - requirements first, then code
            children_to_visit: list[tuple[GraphNode, list[str] | None]] = []

            for edge in node.iter_outgoing_edges():
                child = edge.target
                if child.kind == NodeKind.REQUIREMENT:
                    # Check specificity: if child implements both REQ-XXX and REQ-XXX-A,
                    # only show under the assertion-specific link
                    if edge.assertion_targets:
                        # This is an assertion-specific implementation
                        children_to_visit.append((child, edge.assertion_targets))
                    else:
                        # Check if there's also an assertion-specific edge
                        has_specific = False
                        for other_edge in node.iter_outgoing_edges():
                            if other_edge.target.id == child.id and other_edge.assertion_targets:
                                has_specific = True
                                break
                        if not has_specific:
                            children_to_visit.append((child, None))

            # Add code children
            for child in node.iter_children():
                if child.kind == NodeKind.CODE:
                    children_to_visit.append((child, None))

            # Sort children for consistent ordering
            children_to_visit.sort(key=lambda x: x[0].id)

            for child, assertions in children_to_visit:
                traverse(child, depth + 1, node.id, assertions)

        # Start traversal from roots
        for root in self.graph.iter_roots():
            if root.kind == NodeKind.REQUIREMENT:
                traverse(root, 0, None)

        return rows

    def _collect_unique_values(self, field_name: str) -> set[str]:
        """Collect unique values for a field across all requirements."""
        from elspais.graph import NodeKind

        values: set[str] = set()
        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            if field_name == "status":
                val = (node.status or "").upper()
            elif field_name == "topic":
                val = self._get_topic_for_node(node)
            else:
                val = node.get_field(field_name, "")
            if val:
                values.add(val)
        return values

    def _get_topic_for_node(self, node: GraphNode) -> str:
        """Extract topic from file path."""
        if not node.source:
            return ""
        path = node.source.path
        filename = Path(path).stem
        for prefix in ("prd-", "ops-", "dev-"):
            if filename.lower().startswith(prefix):
                return filename[len(prefix) :]
        return filename

    def _build_tree_data(self) -> dict[str, Any]:
        """Build tree data structure for embedded JSON."""
        from elspais.graph import NodeKind

        data: dict[str, Any] = {}
        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            data[node.id] = {
                "id": node.id,
                "label": node.label,
                "uuid": node.uuid,
                "level": node.level,
                "status": node.status,
                "hash": node.hash,
                "source": {
                    "path": node.source.path if node.source else None,
                    "line": node.source.line if node.source else None,
                },
            }
        return data


__all__ = ["HTMLGenerator"]
