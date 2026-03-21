# Implements: REQ-p00006-A, REQ-p00006-B, REQ-p00006-C
# Implements: REQ-p00050-B
# Implements: REQ-d00052-A, REQ-d00052-D, REQ-d00052-E, REQ-d00052-F
# Implements: REQ-d00070-A, REQ-d00070-B
"""HTML Generator for traceability reports.

This module generates interactive HTML traceability views from TraceGraph.
Uses Jinja2 templates for rich interactive output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais import __version__
from elspais.html.theme import get_catalog
from elspais.utilities.patterns import INSTANCE_SEPARATOR

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph
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
    is_test_result: bool  # RESULT node (test execution result)
    has_children: bool
    has_failures: bool
    is_associated: bool  # From sponsor/associated repository
    coverage_indirect: str = "none"  # "none", "partial", "full" (including indirect)
    validation_color: str = ""  # val-green/val-yellow-green/val-yellow/val-red/val-orange or ""
    validation_tip: str = ""  # Hover tooltip explaining the validation color
    source_file: str = ""  # Relative path to source file
    source_line: int = 0  # Line number in source file
    result_status: str = ""  # For RESULT: passed/failed/error/skipped


@dataclass
class JourneyItem:
    """Represents a user journey for display."""

    id: str
    title: str
    description: str
    actor: str | None = None
    goal: str | None = None
    descriptor: str = ""  # Extracted from ID: JNY-{descriptor}-{number}
    file: str = ""  # Source file path
    referenced_reqs: list[str] = field(default_factory=list)  # REQs via VALIDATES edges


@dataclass
class ViewStats:
    """Statistics for the header display."""

    prd_count: int = 0
    ops_count: int = 0
    dev_count: int = 0
    total_count: int = 0
    code_count: int = 0  # Number of unique CODE nodes in the graph
    test_count: int = 0  # Number of unique TEST nodes in the graph
    test_result_count: int = 0  # Number of RESULT nodes
    test_passed_count: int = 0  # Number of passed RESULT nodes
    test_failed_count: int = 0  # Number of failed RESULT nodes
    associated_count: int = 0
    journey_count: int = 0
    # Assertion-level metrics
    assertion_count: int = 0  # Total unique assertions
    assertions_implemented: int = 0  # Assertions with CODE coverage
    assertions_tested: int = 0  # Assertions with TEST coverage
    assertions_validated: int = 0  # Assertions with passing RESULTs


def _val_tier(key: str) -> tuple[str, str]:
    """Look up a validation tier from the catalog, returning (color_key, description)."""
    from elspais.html.theme import get_catalog

    entry = get_catalog().by_key(key)
    return (entry.color_key, entry.description)


# ── Severity-driven coverage tiers ──

SEVERITY_PRIORITY: dict[str, int] = {"error": 0, "warning": 1, "info": 2, "ok": 3}
SEVERITY_TO_COLOR: dict[str, str] = {
    "error": "red",
    "warning": "yellow",
    "info": "yellow-green",
    "ok": "green",
}

# Human-readable descriptions for each dimension
_DIMENSION_LABELS: dict[str, str] = {
    "implemented": "Implemented",
    "tested": "Tested",
    "verified": "Verified",
    "uat_coverage": "Validated",
    "uat_verified": "Accepted",
}

# Tooltip definitions for card-view badges
DIMENSION_TIPS: dict[str, str] = {
    "implemented": "Assertions with Implements references in CODE",
    "tested": "Assertions referenced by TEST nodes",
    "verified": "Assertions with passing test results",
    "uat_coverage": "Assertions referenced by Journey Validates",
    "uat_verified": "Assertions with passing Journey results",
}

# Tier descriptions for tooltip text
_TIER_DESCRIPTIONS: dict[str, str] = {
    "failing": "test failures detected",
    "full-direct": "all assertions directly covered",
    "full-indirect": "all assertions covered (including indirect)",
    "partial": "some assertions covered",
    "none": "no coverage",
}

# Ordered list of dimension keys (matches CoverageDimension attrs on RollupMetrics)
DIMENSION_KEYS = ("implemented", "tested", "verified", "uat_coverage", "uat_verified")


def _tier_to_severity(tier: str, severity_config: Any) -> str:
    """Map a CoverageDimension tier to a severity string using config."""
    # tier keys use hyphens; config field names use underscores
    field_name = tier.replace("-", "_")
    return getattr(severity_config, field_name, "error")


def compute_coverage_tiers(node: GraphNode, config: dict[str, Any] | None = None) -> dict[str, str]:
    """Compute per-dimension severity colors and combined worst-of-all.

    Uses each CoverageDimension's tier property, maps through config
    severity to determine badge color.

    Args:
        node: A GraphNode with pre-computed rollup_metrics.
        config: Project config dict (from load_config()). If None, uses defaults.

    Returns:
        Dict with keys: impl_color, impl_tip, tested_color, tested_tip,
        verified_color, verified_tip, uat_cov_color, uat_cov_tip,
        uat_ver_color, uat_ver_tip, combined_color, combined_tip.
        All empty strings if node is not ACTIVE or has no assertions.
    """
    from elspais.config.schema import CoverageConfig, CoverageSeverityConfig

    empty: dict[str, str] = {
        "impl_color": "",
        "impl_tip": "",
        "tested_color": "",
        "tested_tip": "",
        "verified_color": "",
        "verified_tip": "",
        "uat_cov_color": "",
        "uat_cov_tip": "",
        "uat_ver_color": "",
        "uat_ver_tip": "",
        "combined_color": "",
        "combined_tip": "",
    }

    status = (node.status or "").upper()
    if status != "ACTIVE":
        return empty

    from elspais.graph.metrics import RollupMetrics

    rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
    if not rollup or rollup.total_assertions == 0:
        return empty

    # Get coverage severity config
    cov_config = CoverageConfig()
    if config:
        rules = config.get("rules", {})
        if isinstance(rules, dict):
            cov_raw = rules.get("coverage", {})
            if isinstance(cov_raw, dict):
                cov_config = CoverageConfig(
                    **{
                        k: CoverageSeverityConfig(**v) if isinstance(v, dict) else v
                        for k, v in cov_raw.items()
                    }
                )
            elif hasattr(cov_raw, "implemented"):
                cov_config = cov_raw
        elif hasattr(rules, "coverage"):
            cov_config = rules.coverage

    # Map dimension key → (CoverageDimension, CoverageSeverityConfig, output_prefix)
    dim_map = [
        ("implemented", rollup.implemented, cov_config.implemented, "impl"),
        ("tested", rollup.tested, cov_config.tested, "tested"),
        ("verified", rollup.verified, cov_config.verified, "verified"),
        ("uat_coverage", rollup.uat_coverage, cov_config.uat_coverage, "uat_cov"),
        ("uat_verified", rollup.uat_verified, cov_config.uat_verified, "uat_ver"),
    ]

    result: dict[str, str] = {}
    worst_severity_priority = 999
    worst_color = ""
    tip_parts: list[str] = []

    for dim_key, dim, sev_cfg, prefix in dim_map:
        tier = dim.tier
        severity = _tier_to_severity(tier, sev_cfg)
        color = SEVERITY_TO_COLOR.get(severity, "")
        label = _DIMENSION_LABELS[dim_key]
        desc = _TIER_DESCRIPTIONS.get(tier, tier)
        tip = f"{label}: {desc}"

        result[f"{prefix}_color"] = color
        result[f"{prefix}_tip"] = tip

        # Track worst severity for combined
        sev_pri = SEVERITY_PRIORITY.get(severity, 999)
        if sev_pri < worst_severity_priority:
            worst_severity_priority = sev_pri
            worst_color = color

        tip_parts.append(tip)

    result["combined_color"] = worst_color
    result["combined_tip"] = " | ".join(tip_parts)

    return result


# Implements: REQ-p00006-A
def compute_validation_color(
    node: GraphNode, config: dict[str, Any] | None = None
) -> tuple[str, str]:
    """Compute a validation quality color for a requirement's Active status badge.

    Backward-compatible wrapper around compute_coverage_tiers().
    Returns the combined (worst-of-all) color and tooltip.

    Args:
        node: A GraphNode with pre-computed rollup_metrics.
        config: Optional project config dict.

    Returns:
        Tuple of (css_class_suffix, reason_text). Both empty if no color applies.
    """
    tiers = compute_coverage_tiers(node, config)
    return (tiers["combined_color"], tiers["combined_tip"])


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
        graph: FederatedGraph,
        base_path: str = "",
        version: str | None = None,
        repo_name: str | None = None,
        namespace: str = "REQ",
    ) -> None:
        self.graph = graph
        self.base_path = base_path
        self.version = version if version is not None else __version__
        self.repo_name = repo_name
        self.namespace = namespace

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
            template = env.get_template("trace_unified.html.j2")
        except ImportError as err:
            raise ImportError(
                "HTMLGenerator requires the trace-view extra. "
                "Install with: pip install elspais[trace-view]"
            ) from err

        # Annotation must happen AFTER graph construction, BEFORE output generation.
        # Generators may add additional annotations specific to their output format.
        self._annotate_git_state()

        # Build data structures
        stats = self._compute_stats()
        rows = self._build_tree_rows()
        journeys = self._collect_journeys()
        statuses = self._collect_unique_values("status")
        topics = self._collect_unique_values("topic")
        tree_data = self._build_tree_data() if embed_content else {}

        # Collect source files with syntax highlighting for inline viewer
        source_files = self._collect_source_files() if embed_content else {}
        pygments_css = self._get_pygments_css() if source_files else ""
        pygments_css_dark = self._get_pygments_css_dark() if source_files else ""

        # Build embedded data indexes for view-mode apiFetch adapter
        node_index = self._build_node_index() if embed_content else {}
        coverage_index = self._build_coverage_index() if embed_content else {}
        status_data = self._build_status_data() if embed_content else {}

        # Update journey count in stats
        stats.journey_count = len(journeys)

        # Render template
        html_content = template.render(
            mode="view",
            stats=stats,
            rows=rows,
            journeys=journeys,
            statuses=sorted(statuses),
            topics=sorted(topics),
            tree_data=tree_data,
            source_files=source_files,
            pygments_css=pygments_css,
            pygments_css_dark=pygments_css_dark,
            node_index=node_index,
            coverage_index=coverage_index,
            status_data=status_data,
            version=self.version,
            base_path=self.base_path,
            repo_name=(
                self.repo_name or (Path(self.base_path).name if self.base_path else "elspais")
            ),
            catalog=get_catalog(),
            default_hidden_statuses=[],
        )

        return html_content

    def _annotate_git_state(self) -> None:
        """Apply git state and display annotations to all requirement nodes.

        Uses the shared annotate_graph_git_state() for git detection,
        then applies display info annotations separately.
        """
        from elspais.graph import NodeKind
        from elspais.graph.annotators import annotate_display_info, annotate_graph_git_state

        # Standard annotation sequence: git_state -> display_info.
        # This order matters: display_info may depend on git state.
        annotate_graph_git_state(self.graph)

        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            annotate_display_info(node)

    def _is_associated(self, node: GraphNode) -> bool:
        """Check if a node is from an associated/sponsor repository.

        Associated requirements come from sponsor repos, identified by:
        - ID containing associated prefix (e.g., REQ-CAL-p00001)
        - Path containing 'sponsor' or 'associated'
        - Path outside the base_path (different repo)
        - Or marked with an associated field
        """
        # Check if ID has a different namespace than the core project.
        # Associated IDs have a different prefix (e.g., REQ-CAL-p00001 when
        # core namespace is "REQ"). Detect by checking if the ID starts with
        # "{namespace}-" followed by an uppercase segment (the associate prefix).
        import re

        core_prefix = f"{self.namespace}-"
        if node.id.startswith(core_prefix):
            after_prefix = node.id[len(core_prefix) :]
            # Associated: namespace-ASSOC-type (ASSOC is 2+ uppercase letters)
            if re.match(r"^[A-Z]{2,}-[a-z]", after_prefix):
                return True

        # Implements: REQ-d00129-D
        _fn = node.file_node()
        if not _fn:
            return False

        _rp = _fn.get_field("relative_path") or ""
        path = _rp.lower()
        # Check for common associated repo patterns
        if "sponsor" in path or "associated" in path:
            return True

        # Check if path is outside base_path (different repo)
        if self.base_path:
            try:
                # If the source path doesn't start with base_path, it's from a different repo
                source_path = Path(_rp).resolve()
                base = Path(self.base_path).resolve()
                if not str(source_path).startswith(str(base)):
                    return True
            except (ValueError, OSError):
                pass

        # Check if node has associated field set
        if node.get_field("associated", False):
            return True

        return False

    def _compute_stats(self) -> ViewStats:
        """Compute statistics for the header.

        Uses pre-computed RollupMetrics from annotate_coverage() for all
        assertion-level coverage stats. No ad-hoc calculation.
        """
        from elspais.graph import NodeKind
        from elspais.graph.metrics import RollupMetrics

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

            # Aggregate all assertion metrics from pre-computed RollupMetrics
            rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
            if rollup:
                stats.assertion_count += rollup.total_assertions
                stats.assertions_implemented += rollup.implemented.indirect
                stats.assertions_tested += rollup.tested.direct
                stats.assertions_validated += rollup.verified.direct

        # Count CODE nodes
        for _ in self.graph.nodes_by_kind(NodeKind.CODE):
            stats.code_count += 1

        # Count TEST nodes
        for _ in self.graph.nodes_by_kind(NodeKind.TEST):
            stats.test_count += 1

        # Count RESULT nodes
        for node in self.graph.nodes_by_kind(NodeKind.RESULT):
            stats.test_result_count += 1
            status = (node.get_field("status", "") or "").lower()
            if status in ("passed", "pass", "success"):
                stats.test_passed_count += 1
            elif status in ("failed", "fail", "failure", "error"):
                stats.test_failed_count += 1

        return stats

    def _build_tree_rows(self) -> list[TreeRow]:
        """Build flat list of rows representing the hierarchical tree.

        Nodes can appear multiple times if they have multiple parents.
        Uses DFS traversal to maintain parent-child ordering.
        """
        from elspais.graph import NodeKind

        rows: list[TreeRow] = []
        visited_at_depth: dict[tuple[str, int, str | None], bool] = {}
        visited_node_ids: set[str] = set()  # Track all rendered node IDs

        def get_topic(node: GraphNode) -> str:
            """Extract topic from file path."""
            _fn = node.file_node()
            if not _fn:
                return ""
            path = _fn.get_field("relative_path") or ""
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
            _fn = node.file_node()
            if not _fn:
                return False
            return "roadmap" in (_fn.get_field("relative_path") or "").lower()

        def compute_coverage(node: GraphNode) -> tuple[str, str, bool]:
            """Get coverage status and failure flag from pre-computed metrics.

            Uses RollupMetrics computed by annotate_coverage().

            Returns:
                Tuple of (coverage_status, coverage_indirect, has_failures)
                coverage_status: "none", "partial", or "full" (strict)
                coverage_indirect: "none", "partial", or "full" (includes indirect)
            """
            from elspais.graph.metrics import RollupMetrics

            rollup: RollupMetrics | None = node.get_metric("rollup_metrics")

            if not rollup or rollup.total_assertions == 0:
                # No assertions - check if any code references the req directly
                has_code = False
                for child in node.iter_children():
                    if child.kind == NodeKind.CODE:
                        has_code = True
                        break
                cov = "full" if has_code else "none"
                return (cov, cov, False)

            # Strict coverage (excludes INDIRECT)
            if rollup.implemented.direct_pct == 0:
                strict = "none"
            elif rollup.implemented.direct_pct < 100:
                strict = "partial"
            else:
                strict = "full"

            # Indirect coverage (includes INDIRECT)
            if rollup.implemented.indirect_pct == 0:
                indirect = "none"
            elif rollup.implemented.indirect_pct < 100:
                indirect = "partial"
            else:
                indirect = "full"

            return (strict, indirect, rollup.verified.has_failures)

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

        def has_test_result_children(node: GraphNode) -> bool:
            """Check if node has test result children."""
            for child in node.iter_children():
                if child.kind == NodeKind.RESULT:
                    return True
            return False

        def traverse(
            node: GraphNode,
            depth: int,
            parent_id: str | None,
            parent_assertions: list[str] | None = None,
            ancestor_ids: frozenset[str] | None = None,
        ) -> None:
            """DFS traversal to build rows."""
            # Detect cycles - if this node is already an ancestor, skip
            if ancestor_ids and node.id in ancestor_ids:
                return

            # Avoid duplicate (id, depth, parent) entries
            key = (node.id, depth, parent_id)
            if key in visited_at_depth:
                return
            visited_at_depth[key] = True

            # Process requirements, code, test, and test_result nodes
            if node.kind not in (
                NodeKind.REQUIREMENT,
                NodeKind.CODE,
                NodeKind.TEST,
                NodeKind.RESULT,
            ):
                return

            is_code = node.kind == NodeKind.CODE
            is_test = node.kind == NodeKind.TEST
            is_test_result = node.kind == NodeKind.RESULT
            is_impl_node = is_code or is_test or is_test_result  # Implementation/evidence nodes
            coverage, coverage_indirect, has_failures = (
                ("none", "none", False) if is_impl_node else compute_coverage(node)
            )
            val_color, val_tip = ("", "") if is_impl_node else compute_validation_color(node)
            assertion_letters = (
                get_assertion_letters(node, parent_id)
                if parent_assertions is None
                else parent_assertions
            )

            # Get source location
            source_file = node.file_node().get_field("relative_path") if node.file_node() else ""
            source_line = node.get_field("parse_line") or 0

            # Get result status for RESULT nodes
            result_status = ""
            if is_test_result:
                result_status = (node.get_field("status", "") or "").lower()

            # Determine has_children based on node kind
            if is_test:
                # TEST nodes can have RESULT children
                node_has_children = has_test_result_children(node)
            elif is_test_result:
                # RESULT nodes don't have children
                node_has_children = False
            else:
                # REQ and CODE nodes
                node_has_children = (
                    has_req_children(node) or has_code_children(node) or has_test_children(node)
                )

            # Create row
            row = TreeRow(
                id=f"{node.id}_{depth}_{parent_id or 'root'}",  # Unique key for multi-parent
                display_id=node.id,
                title=node.get_label() or "",
                level=(node.level or "").upper() if not is_impl_node else "",
                status=(node.status or "").upper() if not is_impl_node else "",
                coverage=coverage,
                coverage_indirect=coverage_indirect,
                validation_color=val_color,
                validation_tip=val_tip,
                topic=get_topic(node) if not is_impl_node else "",
                depth=depth,
                parent_id=(
                    f"{parent_id}_{depth - 1}_"
                    f"{rows[-1].parent_id if rows and depth > 0 else 'root'}"
                    if parent_id and depth > 0
                    else None
                ),
                assertions=assertion_letters,
                is_leaf=not has_req_children(node) and not is_impl_node,
                is_changed=node.get_metric("is_branch_changed", False),
                is_uncommitted=node.get_metric("is_uncommitted", False)
                or node.get_metric("is_untracked", False),
                is_roadmap=is_roadmap(node),
                is_code=is_code,
                is_test=is_test,
                is_test_result=is_test_result,
                has_children=node_has_children,
                has_failures=has_failures,
                is_associated=self._is_associated(node) if not is_impl_node else False,
                source_file=source_file,
                source_line=source_line,
                result_status=result_status,
            )

            # Fix parent_id to reference actual row id
            if parent_id and depth > 0:
                # Find the parent row we just added
                for prev_row in reversed(rows):
                    if prev_row.display_id == parent_id and prev_row.depth == depth - 1:
                        row.parent_id = prev_row.id
                        break

            rows.append(row)
            visited_node_ids.add(node.id)

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
            for _child_id, (child, assertions) in child_assertions.items():
                # Convert set to sorted list
                children_to_visit.append((child, sorted(assertions)))

            # Add children without assertion targets
            # (only if they don't have assertion-specific edges)
            for child in children_without_assertions:
                if child.id not in child_assertions:
                    children_to_visit.append((child, None))

            # Add code, test, and test_result children
            for child in node.iter_children():
                if child.kind == NodeKind.CODE:
                    children_to_visit.append((child, None))
                elif child.kind == NodeKind.TEST:
                    children_to_visit.append((child, None))
                elif child.kind == NodeKind.RESULT:
                    # RESULT children of TEST nodes
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

            current_ancestors = (ancestor_ids or frozenset()) | {node.id}
            for child, assertions in children_to_visit:
                traverse(child, depth + 1, node.id, assertions, current_ancestors)

        # Start traversal from roots
        for root in self.graph.iter_roots():
            if root.kind == NodeKind.REQUIREMENT:
                traverse(root, 0, None)

        # Add unvisited TEST nodes (orphan or not reached from root traversal)
        # These appear as root-level items with their RESULT children
        for node in self.graph.nodes_by_kind(NodeKind.TEST):
            if node.id in visited_node_ids:
                continue

            source_file = node.file_node().get_field("relative_path") if node.file_node() else ""
            source_line = node.get_field("parse_line") or 0

            row = TreeRow(
                id=f"{node.id}_0_root",
                display_id=node.id,
                title=node.get_label() or "",
                level="",
                status="",
                coverage="none",
                topic="",
                depth=0,
                parent_id=None,
                assertions=[],
                is_leaf=False,
                is_changed=False,
                is_uncommitted=False,
                is_roadmap=False,
                is_code=False,
                is_test=True,
                is_test_result=False,
                has_children=has_test_result_children(node),
                has_failures=False,
                is_associated=False,
                source_file=source_file,
                source_line=source_line,
                result_status="",
            )
            rows.append(row)
            visited_node_ids.add(node.id)

            # Render RESULT children under this TEST node
            for child in node.iter_children():
                if child.kind == NodeKind.RESULT:
                    child_source_file = (
                        child.file_node().get_field("relative_path") if child.file_node() else ""
                    )
                    child_source_line = child.get_field("parse_line") or 0
                    child_result_status = (child.get_field("status", "") or "").lower()

                    child_row = TreeRow(
                        id=f"{child.id}_1_{node.id}",
                        display_id=child.id,
                        title=child.get_label() or "",
                        level="",
                        status="",
                        coverage="none",
                        topic="",
                        depth=1,
                        parent_id=row.id,
                        assertions=[],
                        is_leaf=True,
                        is_changed=False,
                        is_uncommitted=False,
                        is_roadmap=False,
                        is_code=False,
                        is_test=False,
                        is_test_result=True,
                        has_children=False,
                        has_failures=child_result_status in ("failed", "fail", "failure", "error"),
                        is_associated=False,
                        source_file=child_source_file,
                        source_line=child_source_line,
                        result_status=child_result_status,
                    )
                    rows.append(child_row)
                    visited_node_ids.add(child.id)

        # Add orphan RESULT nodes (not visited via any TEST parent)
        for node in self.graph.nodes_by_kind(NodeKind.RESULT):
            if node.id in visited_node_ids:
                continue

            source_file = node.file_node().get_field("relative_path") if node.file_node() else ""
            source_line = node.get_field("parse_line") or 0
            result_status = (node.get_field("status", "") or "").lower()

            # Create a short display ID from test name
            test_name = node.get_field("name", "") or ""
            classname = node.get_field("classname", "") or ""
            if test_name:
                display_id = test_name
            elif classname:
                display_id = classname.split(".")[-1]
            else:
                display_id = (
                    node.id.split(INSTANCE_SEPARATOR)[-1]
                    if INSTANCE_SEPARATOR in node.id
                    else node.id[-30:]
                )

            row = TreeRow(
                id=f"{node.id}_0_root",
                display_id=display_id,
                title=node.get_label() or "",
                level="",
                status="",
                coverage="none",
                topic="",
                depth=0,
                parent_id=None,
                assertions=[],
                is_leaf=True,
                is_changed=False,
                is_uncommitted=False,
                is_roadmap=False,
                is_code=False,
                is_test=False,
                is_test_result=True,
                has_children=False,
                has_failures=result_status in ("failed", "fail", "failure", "error"),
                is_associated=False,
                source_file=source_file,
                source_line=source_line,
                result_status=result_status,
            )
            rows.append(row)

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
        _fn = node.file_node()
        if not _fn:
            return ""
        path = _fn.get_field("relative_path") or ""
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
            vc, vt = compute_validation_color(node)
            data[node.id] = {
                "id": node.id,
                "label": node.get_label(),
                "uuid": node.uuid,
                "level": (node.level or "").upper(),
                "status": node.status,
                "hash": node.hash,
                "validation_color": vc,
                "validation_tip": vt,
                "source": {
                    "path": (
                        node.file_node().get_field("relative_path") if node.file_node() else None
                    ),
                    "line": node.get_field("parse_line"),
                },
            }
        return data

    def _build_node_index(self) -> dict[str, Any]:
        """Build node index for embedded JSON — matches /api/node/<id> response shape.

        Delegates to the MCP server's _serialize_node_generic() to produce
        identical JSON as the live API, ensuring view mode and edit mode
        see the same data structure.
        """
        from elspais.mcp.server import _serialize_node_generic

        index: dict[str, Any] = {}
        for node in self.graph.all_nodes():
            index[node.id] = _serialize_node_generic(node, self.graph)
        return index

    def _build_coverage_index(self) -> dict[str, Any]:
        """Build per-requirement coverage index for embedded JSON.

        Each entry is keyed by requirement ID and contains both test coverage
        (matching /api/test-coverage/<id>) and code coverage
        (matching /api/code-coverage/<id>) response shapes.
        """
        from elspais.graph import NodeKind
        from elspais.mcp.server import _get_assertion_code_map, _get_assertion_test_map

        index: dict[str, Any] = {}
        for node in self.graph.nodes_by_kind(NodeKind.REQUIREMENT):
            index[node.id] = {
                "test": _get_assertion_test_map(self.graph, node.id),
                "code": _get_assertion_code_map(self.graph, node.id),
            }
        return index

    def _build_status_data(self) -> dict[str, Any]:
        """Build graph status data for embedded JSON — matches /api/status response shape."""
        from elspais.mcp.server import _get_graph_status

        return _get_graph_status(self.graph)

    def _collect_source_files(self) -> dict[str, Any]:
        """Collect source file contents with syntax highlighting for inline viewer.

        Walks all graph nodes, reads unique source files, and applies Pygments
        syntax highlighting at generation time. The pre-highlighted HTML is
        embedded in the output so the browser needs no JS highlighting library.

        Returns:
            Dict mapping file paths to their content data:
            {path: {lines: [highlighted_html_per_line], language: str, raw: str}}
        """
        from elspais.html.highlighting import MAX_FILE_SIZE, highlight_file_content

        # Collect unique source paths from all nodes
        paths: set[str] = set()
        for node in self.graph.all_nodes():
            _fn = node.file_node()
            _rp = _fn.get_field("relative_path") if _fn else None
            if _rp:
                paths.add(_rp)

        result: dict[str, Any] = {}
        for path in sorted(paths):
            try:
                file_path = Path(path)
                if not file_path.is_absolute() and self.graph.repo_root:
                    file_path = self.graph.repo_root / file_path
                if not file_path.is_file():
                    continue

                # Skip files that are too large
                if file_path.stat().st_size > MAX_FILE_SIZE:
                    continue

                # Skip binary files (check first 8KB for null bytes)
                with open(file_path, "rb") as f:
                    chunk = f.read(8192)
                    if b"\x00" in chunk:
                        continue

                raw_content = file_path.read_text(encoding="utf-8", errors="replace")
                result[path] = highlight_file_content(path, raw_content)
            except (OSError, UnicodeDecodeError):
                continue

        return result

    def _get_pygments_css(self) -> str:
        """Generate Pygments CSS theme for syntax highlighting.

        Returns CSS rules scoped under .highlight for the file viewer panel.
        Returns empty string if Pygments is not installed.
        """
        from elspais.html.highlighting import get_pygments_css

        return get_pygments_css()

    def _get_pygments_css_dark(self) -> str:
        """Generate dark-theme Pygments CSS for syntax highlighting.

        Returns CSS rules scoped under .theme-dark .highlight for the
        file viewer panel when dark theme is active.
        Returns empty string if Pygments is not installed.
        """
        from elspais.html.highlighting import get_pygments_css

        return get_pygments_css(style="monokai", scope=".theme-dark .highlight")

    def _collect_journeys(self) -> list[JourneyItem]:
        """Collect all user journey nodes for the journeys tab."""
        import re

        from elspais.graph import NodeKind
        from elspais.graph.relations import EdgeKind

        journeys: list[JourneyItem] = []

        for node in self.graph.nodes_by_kind(NodeKind.USER_JOURNEY):
            # Extract description from body or other fields
            description = node.get_field("body", "") or node.get_field("description", "")
            if not description and node.get_label():
                # Use label as title, look for body content
                description = ""

            # Extract actor and goal fields from parsed journey data
            actor = node.get_field("actor")
            goal = node.get_field("goal")

            # Extract descriptor from journey ID: JNY-{descriptor}-{number}
            descriptor = ""
            match = re.match(r"JNY-(.+)-\d+$", node.id)
            if match:
                descriptor = match.group(1)

            # Extract file from FILE parent node
            file = ""
            _fn = node.file_node()
            if _fn:
                _rp = _fn.get_field("relative_path") or ""
                file = Path(_rp).name if _rp else ""

            # Extract referenced requirements from incoming VALIDATES edges
            referenced_reqs = sorted(
                e.source.id for e in node.iter_incoming_edges() if e.kind == EdgeKind.VALIDATES
            )

            journeys.append(
                JourneyItem(
                    id=node.id,
                    title=node.get_label() or node.id,
                    description=description,
                    actor=actor,
                    goal=goal,
                    descriptor=descriptor,
                    file=file,
                    referenced_reqs=referenced_reqs,
                )
            )

        # Sort by ID for consistent ordering
        journeys.sort(key=lambda j: j.id)
        return journeys


__all__ = ["HTMLGenerator", "compute_validation_color"]
