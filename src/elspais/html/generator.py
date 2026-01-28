"""HTML Generator for traceability reports.

This module generates interactive HTML traceability views from TraceGraph.
Uses Jinja2 templates for rich interactive output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais import __version__

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
    is_test: bool  # TEST node for traceability
    has_children: bool
    has_failures: bool
    is_associated: bool  # From sponsor/associated repository


@dataclass
class JourneyItem:
    """Represents a user journey for display."""

    id: str
    title: str
    description: str
    actor: str | None = None
    goal: str | None = None


@dataclass
class ViewStats:
    """Statistics for the header display."""

    prd_count: int = 0
    ops_count: int = 0
    dev_count: int = 0
    total_count: int = 0
    test_count: int = 0  # Number of TEST nodes in the graph
    associated_count: int = 0
    journey_count: int = 0


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
        version: Version string for display (defaults to elspais package version).
    """

    def __init__(
        self,
        graph: TraceGraph,
        base_path: str = "",
        version: str | None = None,
    ) -> None:
        self.graph = graph
        self.base_path = base_path
        self.version = version if version is not None else __version__

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
        journeys = self._collect_journeys()
        statuses = self._collect_unique_values("status")
        topics = self._collect_unique_values("topic")
        tree_data = self._build_tree_data() if embed_content else {}

        # Update journey count in stats
        stats.journey_count = len(journeys)

        # Render template
        html_content = template.render(
            stats=stats,
            rows=rows,
            journeys=journeys,
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

    def _is_associated(self, node: GraphNode) -> bool:
        """Check if a node is from an associated/sponsor repository.

        Associated requirements come from sponsor repos, identified by:
        - Path containing 'sponsor' or 'associated'
        - Path outside the main spec/ directory structure
        - Or marked with an associated field
        """
        if not node.source:
            return False

        path = node.source.path.lower()
        # Check for common associated repo patterns
        if "sponsor" in path or "associated" in path:
            return True

        # Check if node has associated field set
        if node.get_field("associated", False):
            return True

        return False

    def _compute_stats(self) -> ViewStats:
        """Compute statistics for the header."""
        from elspais.graph import NodeKind

        stats = ViewStats()

        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            stats.total_count += 1

            level = (node.level or "").upper()
            if level == "PRD":
                stats.prd_count += 1
            elif level == "OPS":
                stats.ops_count += 1
            elif level == "DEV":
                stats.dev_count += 1

            # Count associated requirements
            if self._is_associated(node):
                stats.associated_count += 1

        # Count TEST nodes (more meaningful than file count)
        for _ in self.graph.nodes_by_kind(NodeKind.TEST):
            stats.test_count += 1

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

        def has_test_children(node: GraphNode) -> bool:
            """Check if node has test children."""
            for child in node.iter_children():
                if child.kind == NodeKind.TEST:
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

            # Process requirements, code, and test nodes
            if node.kind not in (NodeKind.REQUIREMENT, NodeKind.CODE, NodeKind.TEST):
                return

            is_code = node.kind == NodeKind.CODE
            is_test = node.kind == NodeKind.TEST
            is_impl_node = is_code or is_test  # Implementation nodes (code or test)
            coverage, has_failures = ("none", False) if is_impl_node else compute_coverage(node)
            assertion_letters = get_assertion_letters(node, parent_id) if parent_assertions is None else parent_assertions

            # Create row
            row = TreeRow(
                id=f"{node.id}_{depth}_{parent_id or 'root'}",  # Unique key for multi-parent
                display_id=node.id,
                title=node.label or "",
                level=(node.level or "").upper() if not is_impl_node else "",
                status=(node.status or "").upper() if not is_impl_node else "",
                coverage=coverage,
                topic=get_topic(node) if not is_impl_node else "",
                depth=depth,
                parent_id=f"{parent_id}_{depth - 1}_{rows[-1].parent_id if rows and depth > 0 else 'root'}" if parent_id and depth > 0 else None,
                assertions=assertion_letters,
                is_leaf=not has_req_children(node) and not is_impl_node,
                is_changed=node.get_metric("is_branch_changed", False),
                is_uncommitted=node.get_metric("is_uncommitted", False) or node.get_metric("is_untracked", False),
                is_roadmap=is_roadmap(node),
                is_code=is_code,
                is_test=is_test,
                has_children=has_req_children(node) or has_code_children(node) or has_test_children(node),
                has_failures=has_failures,
                is_associated=self._is_associated(node) if not is_impl_node else False,
            )

            # Fix parent_id to reference actual row id
            if parent_id and depth > 0:
                # Find the parent row we just added
                for prev_row in reversed(rows):
                    if prev_row.display_id == parent_id and prev_row.depth == depth - 1:
                        row.parent_id = prev_row.id
                        break

            rows.append(row)

            # Traverse children - requirements first, then code/tests
            # First, aggregate all assertion targets per child to avoid duplicates
            child_assertions: dict[str, tuple[GraphNode, set[str]]] = {}
            children_without_assertions: list[GraphNode] = []

            for edge in node.iter_outgoing_edges():
                child = edge.target
                if child.kind == NodeKind.REQUIREMENT:
                    if edge.assertion_targets:
                        # Aggregate assertion targets for this child
                        if child.id not in child_assertions:
                            child_assertions[child.id] = (child, set())
                        child_assertions[child.id][1].update(edge.assertion_targets)
                    else:
                        # Track children without assertion-specific edges
                        if child.id not in child_assertions:
                            children_without_assertions.append(child)

            # Build children_to_visit list: assertion-specific children first
            children_to_visit: list[tuple[GraphNode, list[str] | None]] = []
            for child_id, (child, assertions) in child_assertions.items():
                # Convert set to sorted list
                children_to_visit.append((child, sorted(assertions)))

            # Add children without assertion targets (only if they don't have assertion-specific edges)
            for child in children_without_assertions:
                if child.id not in child_assertions:
                    children_to_visit.append((child, None))

            # Add code and test children
            for child in node.iter_children():
                if child.kind == NodeKind.CODE:
                    children_to_visit.append((child, None))
                elif child.kind == NodeKind.TEST:
                    children_to_visit.append((child, None))

            # Sort children: assertion-specific first (by letter), then general (by ID)
            # Key: (has_assertions=False sorts before True, assertion_letters, node_id)
            def sort_key(item: tuple[GraphNode, list[str] | None]) -> tuple:
                child, assertions = item
                if assertions:
                    # Has assertion targets: sort by letters first (A, B, C...)
                    return (0, sorted(assertions), child.id)
                else:
                    # No assertion targets: sort after assertion-specific children
                    return (1, [], child.id)

            children_to_visit.sort(key=sort_key)

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

    def _collect_journeys(self) -> list[JourneyItem]:
        """Collect all user journey nodes for the journeys tab."""
        from elspais.graph import NodeKind

        journeys: list[JourneyItem] = []

        for node in self.graph.nodes_by_kind(NodeKind.USER_JOURNEY):
            # Extract description from body or other fields
            description = node.get_field("body", "") or node.get_field("description", "")
            if not description and node.label:
                # Use label as title, look for body content
                description = ""

            # Extract actor and goal fields from parsed journey data
            actor = node.get_field("actor")
            goal = node.get_field("goal")

            journeys.append(
                JourneyItem(
                    id=node.id,
                    title=node.label or node.id,
                    description=description,
                    actor=actor,
                    goal=goal,
                )
            )

        # Sort by ID for consistent ordering
        journeys.sort(key=lambda j: j.id)
        return journeys


__all__ = ["HTMLGenerator"]
