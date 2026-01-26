"""Graph builder for constructing traceability graphs.

This module provides the TraceGraphBuilder class for building TraceGraph
instances from various data sources (requirements, tests, code references).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.core.models import Requirement, StructuredParseResult
    from elspais.core.graph import TraceNode, TraceGraph
    from elspais.core.graph_schema import GraphSchema


@dataclass
class ValidationResult:
    """Result of graph validation.

    Attributes:
        is_valid: True if no errors were found.
        errors: List of error messages.
        warnings: List of warning messages.
        info: List of informational messages (e.g., suppressed warnings).
    """

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


class TraceGraphBuilder:
    """Builds a TraceGraph from various data sources.

    The builder pattern allows incremental construction of the graph
    from multiple data sources, with final linking and validation
    performed when build() is called.

    Example:
        builder = TraceGraphBuilder(repo_root=Path.cwd())
        builder.add_requirements(requirements)
        builder.add_test_coverage(test_data)
        graph = builder.build()
    """

    def __init__(
        self,
        repo_root: Path,
        schema: GraphSchema | None = None,
        include_file_nodes: bool = False,
    ) -> None:
        """Initialize the builder.

        Args:
            repo_root: Path to the repository root.
            schema: Graph schema (uses default if not provided).
            include_file_nodes: If True, create FILE and FILE_REGION nodes for
                lossless file reconstruction. Default False.
        """
        from elspais.core.graph_schema import GraphSchema

        self.repo_root = repo_root
        self.schema = schema or GraphSchema.default()
        self.include_file_nodes = include_file_nodes
        self._nodes: dict[str, TraceNode] = {}
        self._requirements: dict[str, Requirement] = {}
        self._pending_links: list[tuple[str, str, str]] = []  # (from_id, to_id, rel_name)
        self._validation_warnings: list[str] = []  # Type constraint warnings
        self._file_structures: dict[str, StructuredParseResult] = {}  # file_path -> StructuredParseResult

    def add_requirements(self, requirements: dict[str, Requirement]) -> TraceGraphBuilder:
        """Add requirements and their assertions as nodes.

        Args:
            requirements: Dictionary of requirement ID to Requirement.

        Returns:
            Self for method chaining.
        """
        from elspais.core.graph import NodeKind, SourceLocation, TraceNode

        self._requirements = requirements

        for req_id, req in requirements.items():
            # Skip conflict entries for graph building
            if req.is_conflict:
                continue

            # Create requirement node
            req_node = TraceNode(
                id=req_id,
                kind=NodeKind.REQUIREMENT,
                label=f"{req_id}: {req.title}",
                source=SourceLocation(
                    path=self._relative_path(req.file_path),
                    line=req.line_number or 0,
                ),
                requirement=req,
            )
            self._nodes[req_id] = req_node

            # Add assertion children
            for assertion in req.assertions:
                assertion_id = f"{req_id}-{assertion.label}"
                assertion_node = TraceNode(
                    id=assertion_id,
                    kind=NodeKind.ASSERTION,
                    label=f"{assertion.label}. {assertion.text[:50]}...",
                    source=req_node.source,
                    assertion=assertion,
                )
                req_node.children.append(assertion_node)
                assertion_node.parents.append(req_node)
                self._nodes[assertion_id] = assertion_node

            # Queue implements links for later resolution
            for impl_id in req.implements:
                self._pending_links.append((req_id, impl_id, "implements"))

            # Queue refines links for later resolution
            refines = getattr(req, "refines", [])
            for ref_id in refines:
                self._pending_links.append((req_id, ref_id, "refines"))

            # Queue addresses links if present
            addresses = getattr(req, "addresses", [])
            for addr_id in addresses:
                self._pending_links.append((req_id, addr_id, "addresses"))

        return self

    def add_file_structures(
        self, file_results: list[StructuredParseResult]
    ) -> TraceGraphBuilder:
        """Add file structure data for lossless reconstruction.

        This stores StructuredParseResult objects so that FILE and FILE_REGION
        nodes can be created during build() when include_file_nodes=True.

        Args:
            file_results: List of StructuredParseResult from parse_file_with_structure()

        Returns:
            Self for method chaining.
        """
        for result in file_results:
            self._file_structures[result.file_node.file_path] = result
        return self

    def add_user_journeys(self, journeys: dict[str, TraceNode]) -> TraceGraphBuilder:
        """Add user journey nodes.

        Args:
            journeys: Dictionary of journey ID to TraceNode.

        Returns:
            Self for method chaining.
        """
        for jny_id, jny_node in journeys.items():
            self._nodes[jny_id] = jny_node
        return self

    def add_nodes(self, nodes: list[TraceNode]) -> TraceGraphBuilder:
        """Add pre-built nodes to the graph.

        Args:
            nodes: List of TraceNode instances.

        Returns:
            Self for method chaining.
        """
        for node in nodes:
            self._nodes[node.id] = node

            # Extract validates targets and queue for linking
            targets = node.metrics.get("_validates_targets", [])
            for target_id in targets:
                self._pending_links.append((node.id, target_id, "validates"))

        return self

    def add_test_coverage(
        self,
        test_nodes: list[TraceNode],
        expected_broken_links: dict[str, int] | None = None,  # Deprecated, ignored
    ) -> TraceGraphBuilder:
        """Add test reference nodes.

        Args:
            test_nodes: List of test TraceNode instances.
            expected_broken_links: Deprecated - expected broken links are now
                tracked per-reference via the _expected_broken_targets metric.

        Returns:
            Self for method chaining.
        """
        return self.add_nodes(test_nodes)

    def add_code_references(self, code_nodes: list[TraceNode]) -> TraceGraphBuilder:
        """Add code reference nodes.

        Args:
            code_nodes: List of code TraceNode instances.

        Returns:
            Self for method chaining.
        """
        return self.add_nodes(code_nodes)

    def add_test_results(self, result_nodes: list[TraceNode]) -> TraceGraphBuilder:
        """Add test result nodes.

        Args:
            result_nodes: List of test result TraceNode instances.

        Returns:
            Self for method chaining.
        """
        return self.add_nodes(result_nodes)

    def build(self) -> TraceGraph:
        """Build the final graph, linking parent-child relationships.

        Returns:
            The constructed TraceGraph.
        """
        from elspais.core.graph import TraceGraph

        # Link all pending relationships
        self._link_relationships()

        # Create FILE and FILE_REGION nodes if enabled
        # FILE nodes are added to _nodes index, and _find_roots() picks them up
        # via is_root=True in their schema
        if self.include_file_nodes and self._file_structures:
            self._build_file_nodes()

        # Find roots (includes FILE nodes via is_root=True schema)
        roots = self._find_roots()

        # Create graph
        graph = TraceGraph(
            roots=sorted(roots, key=lambda n: n.id),
            repo_root=self.repo_root,
            _index=dict(self._nodes),
        )

        return graph

    def build_and_validate(self) -> tuple[TraceGraph, ValidationResult]:
        """Build the graph and run validation.

        Returns:
            Tuple of (TraceGraph, ValidationResult).
        """
        graph = self.build()
        result = self.validate(graph)
        return graph, result

    def validate(self, graph: TraceGraph) -> ValidationResult:
        """Validate the graph according to schema rules.

        Broken link warnings are filtered based on `elspais: expected-broken-links N`
        markers in test files. References marked as expected_broken emit info
        messages instead of warnings.

        Args:
            graph: The graph to validate.

        Returns:
            ValidationResult with errors, warnings, and info.
        """
        result = ValidationResult()

        # Add type constraint warnings collected during linking
        result.warnings.extend(self._validation_warnings)

        if self.schema.validation.cycle_check:
            cycles = self._detect_cycles(graph)
            for cycle in cycles:
                result.errors.append(f"Cycle detected: {' -> '.join(cycle)}")
                result.is_valid = False

        if self.schema.validation.orphan_check:
            orphans = self._find_orphans(graph)
            for orphan_id in orphans:
                result.warnings.append(f"Orphaned node: {orphan_id}")

        if self.schema.validation.broken_link_check:
            # Get broken links with source information
            broken_with_sources = self._find_broken_links_with_sources()

            # Check each broken link against expected_broken_targets
            for from_id, to_id, source_path in broken_with_sources:
                node = self._nodes.get(from_id)
                if node:
                    expected_targets = node.metrics.get("_expected_broken_targets", [])
                    if to_id in expected_targets:
                        # Emit info instead of warning for expected broken links
                        result.info.append(
                            f"Expected broken link (suppressed): {from_id} -> {to_id}"
                        )
                    else:
                        result.warnings.append(f"Broken link: {from_id} -> {to_id}")
                else:
                    result.warnings.append(f"Broken link: {from_id} -> {to_id}")

        if self.schema.validation.duplicate_id_check:
            # Already handled during add_requirements (conflicts)
            pass

        return result

    def _link_relationships(self) -> None:
        """Link all pending relationships."""
        from elspais.core.graph import NodeKind

        for from_id, to_id, rel_name in self._pending_links:
            from_node = self._nodes.get(from_id)
            if not from_node:
                continue

            # Find the target node with flexible matching
            to_node = self._find_node(to_id)
            if not to_node:
                continue

            # Get relationship schema
            rel_schema = self.schema.get_relationship(rel_name)
            if rel_schema:
                # Validate from_kind constraint
                if from_node.kind.value not in rel_schema.from_kind:
                    self._validation_warnings.append(
                        f"Invalid relationship: {from_node.kind.value} cannot '{rel_name}'"
                    )
                # Validate to_kind constraint
                if to_node.kind.value not in rel_schema.to_kind:
                    self._validation_warnings.append(
                        f"Invalid target: '{rel_name}' cannot target {to_node.kind.value}"
                    )

            # Track relationship type for coverage rollup decisions
            if "_relationship_to_parent" not in from_node.metrics:
                from_node.metrics["_relationship_to_parent"] = {}
            from_node.metrics["_relationship_to_parent"][to_node.id] = rel_name

            # Track if this is an assertion-level implements (explicit coverage)
            if rel_name == "implements" and to_node.kind == NodeKind.ASSERTION:
                from_node.metrics["_implements_assertion"] = True

            if not rel_schema:
                # Default to "up" direction (child declares parent)
                if to_node not in from_node.parents:
                    from_node.parents.append(to_node)
                if from_node not in to_node.children:
                    to_node.children.append(from_node)
            elif rel_schema.direction == "up":
                # Child declares parent
                if to_node not in from_node.parents:
                    from_node.parents.append(to_node)
                if from_node not in to_node.children:
                    to_node.children.append(from_node)
            else:
                # Parent declares child
                if from_node not in to_node.parents:
                    to_node.parents.append(from_node)
                if to_node not in from_node.children:
                    from_node.children.append(to_node)

    def _find_node(self, node_id: str) -> TraceNode | None:
        """Find a node by ID with flexible matching.

        Tries: exact match, with REQ- prefix, suffix match (requirements only).

        Args:
            node_id: The ID to search for.

        Returns:
            Matching TraceNode or None.
        """
        from elspais.core.graph import NodeKind

        # Exact match
        if node_id in self._nodes:
            return self._nodes[node_id]

        # Try with REQ- prefix
        prefixed = f"REQ-{node_id}"
        if prefixed in self._nodes:
            return self._nodes[prefixed]

        # Suffix match - only match REQUIREMENT or ASSERTION nodes to avoid
        # false matches with test node IDs that contain requirement references
        for nid, node in self._nodes.items():
            if node.kind not in (NodeKind.REQUIREMENT, NodeKind.ASSERTION):
                continue
            if nid.endswith(node_id) or nid.endswith(f"-{node_id}"):
                return node

        return None

    def _find_roots(self) -> list[TraceNode]:
        """Find root nodes (nodes with no parents).

        Returns:
            List of root TraceNode instances.
        """
        from elspais.core.graph import NodeKind

        roots: list[TraceNode] = []

        for node in self._nodes.values():
            # Check if explicitly marked as root in schema
            node_schema = self.schema.get_node_type(node.kind.value)
            if node_schema and node_schema.is_root:
                roots.append(node)
                continue

            # Check if has no parents and is the default root kind
            if not node.parents:
                if node.kind == NodeKind.REQUIREMENT:
                    roots.append(node)
                elif node.kind.value == self.schema.default_root_kind:
                    roots.append(node)

        return roots

    def _detect_cycles(self, graph: TraceGraph) -> list[list[str]]:
        """Detect cycles in the graph.

        Args:
            graph: The graph to check.

        Returns:
            List of cycle paths (each path is a list of node IDs).
        """
        from elspais.core.graph import NodeKind

        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_id: str, path: list[str]) -> None:
            if node_id in rec_stack:
                # Found cycle - extract the cycle portion
                if node_id in path:
                    cycle_start = path.index(node_id)
                    cycle = path[cycle_start:] + [node_id]
                    cycles.append(cycle)
                return

            if node_id in visited:
                return

            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            node = graph.find_by_id(node_id)
            if node:
                for child in node.children:
                    # Only follow requirement children for cycle detection
                    if child.kind == NodeKind.REQUIREMENT:
                        dfs(child.id, path[:])

            rec_stack.remove(node_id)

        # Start from roots
        for root in graph.roots:
            dfs(root.id, [])

        # Also check all requirement nodes using the index directly
        # (in case there are isolated cycles where no node is a root)
        for node_id, node in graph._index.items():
            if node.kind == NodeKind.REQUIREMENT and node_id not in visited:
                dfs(node_id, [])

        return cycles

    def _find_orphans(self, graph: TraceGraph) -> list[str]:
        """Find orphaned nodes (non-root nodes with no parents).

        Args:
            graph: The graph to check.

        Returns:
            List of orphaned node IDs.
        """
        from elspais.core.graph import NodeKind

        orphans: list[str] = []

        for node in graph.all_nodes():
            # Skip roots and assertions (assertions have req parent)
            if node in graph.roots:
                continue
            if node.kind == NodeKind.ASSERTION:
                continue
            # Skip FILE_REGION nodes (they have FILE parent via edge)
            if node.kind == NodeKind.FILE_REGION:
                continue
            # Skip FILE nodes (they're roots for reconstruction, not requirement hierarchy)
            if node.kind == NodeKind.FILE:
                continue

            # Check if marked as root type
            node_schema = self.schema.get_node_type(node.kind.value)
            if node_schema and node_schema.is_root:
                continue

            # Check for implements relationship requirement
            rel_schema = self.schema.get_relationship("implements")
            if rel_schema and rel_schema.required_for_non_root:
                if node.kind == NodeKind.REQUIREMENT and not node.parents:
                    orphans.append(node.id)

        return orphans

    def _find_broken_links(self) -> list[tuple[str, str]]:
        """Find broken links (references to non-existent nodes).

        Returns:
            List of (from_id, to_id) tuples for broken links.
        """
        broken: list[tuple[str, str]] = []

        for from_id, to_id, _ in self._pending_links:
            if from_id in self._nodes and self._find_node(to_id) is None:
                broken.append((from_id, to_id))

        return broken

    def _find_broken_links_with_sources(
        self,
    ) -> list[tuple[str, str, str | None]]:
        """Find broken links with their source file paths.

        Returns:
            List of (from_id, to_id, source_path) tuples for broken links.
            source_path is the file path if available, None otherwise.
        """
        broken: list[tuple[str, str, str | None]] = []

        for from_id, to_id, _ in self._pending_links:
            if from_id in self._nodes and self._find_node(to_id) is None:
                node = self._nodes[from_id]
                source_path = node.source.path if node.source else None
                broken.append((from_id, to_id, source_path))

        return broken

    def compute_metrics(
        self,
        graph: TraceGraph,
        exclude_status: list[str] | None = None,
        strict_mode: bool | None = None,
    ) -> None:
        """Compute roll-up metrics for all nodes.

        Coverage is tracked at the assertion level using contribution lists.
        Each assertion accumulates a list of CoverageContribution objects
        from tests and child requirements. The consumer decides how to
        interpret/aggregate multiple contributions.

        Coverage contribution rules:
        - Tests → Assertion: Direct contribution (coverage_value=1.0)
        - Child REQ → Assertion (explicit): Explicit contribution (child's coverage)
        - Child REQ → Parent REQ: Inferred contribution to ALL parent assertions
          (child's coverage distributed to all parent assertions)
        - Explicit overrides inferred: If child targets specific assertion(s),
          those get explicit, others get inferred (same child won't appear twice)

        Args:
            graph: The graph to compute metrics for.
            exclude_status: Statuses to exclude from roll-up (default from config).
            strict_mode: Deprecated - coverage now always tracked via contributions.
                        Kept for backward compatibility.
        """
        from elspais.core.graph import NodeKind
        from elspais.core.graph_schema import CoverageContribution, CoverageSource, RollupMetrics

        # Get exclusions from config if not provided
        if exclude_status is None:
            exclude_status = self.schema.metrics_config.exclude_status
        if strict_mode is None:
            strict_mode = self.schema.metrics_config.strict_mode

        # Initialize metrics for all nodes
        for node in graph.all_nodes():
            node.metrics["_rollup"] = RollupMetrics()
            node.metrics["_coverage_contributions"] = []  # List[CoverageContribution]

        # First pass: compute each node's own coverage (for REQs)
        for node in graph.all_nodes():
            if node.kind == NodeKind.REQUIREMENT:
                own_assertions = [c for c in node.children if c.kind == NodeKind.ASSERTION]
                own_covered = sum(
                    1 for a in own_assertions
                    if any(c.kind == NodeKind.TEST for c in a.children)
                )
                total = len(own_assertions)
                node.metrics["_own_coverage"] = own_covered / total if total > 0 else 0.0

        # Second pass: populate assertion coverage contributions
        for node in graph.all_nodes():
            if node.kind != NodeKind.ASSERTION:
                continue

            contributions: list[CoverageContribution] = []

            # Direct coverage from tests
            for child in node.children:
                if child.kind == NodeKind.TEST:
                    contributions.append(CoverageContribution(
                        source_id=child.id,
                        source_type=CoverageSource.DIRECT,
                        coverage_value=1.0,
                        relationship="validates",
                    ))

            # Explicit coverage from child REQs that target this assertion specifically
            for child in node.children:
                if child.kind == NodeKind.REQUIREMENT:
                    rel_to_this = child.metrics.get("_relationship_to_parent", {}).get(node.id)
                    if rel_to_this in ("implements", "refines"):
                        child_coverage = child.metrics.get("_own_coverage", 0.0)
                        contributions.append(CoverageContribution(
                            source_id=child.id,
                            source_type=CoverageSource.EXPLICIT,
                            coverage_value=child_coverage,
                            relationship=rel_to_this,
                        ))

            node.metrics["_coverage_contributions"] = contributions

        # Third pass: inferred coverage from child REQs that target parent REQ
        # Find children that target a REQ (not assertion) and add inferred to all assertions
        for node in graph.all_nodes():
            if node.kind != NodeKind.REQUIREMENT:
                continue

            # Get this REQ's assertions
            own_assertions = [c for c in node.children if c.kind == NodeKind.ASSERTION]

            # Find children that target this REQ directly (not specific assertions)
            for child in node.children:
                if child.kind != NodeKind.REQUIREMENT:
                    continue
                if self._should_exclude_child(child, exclude_status):
                    continue

                rel_to_this = child.metrics.get("_relationship_to_parent", {}).get(node.id)
                if rel_to_this not in ("implements", "refines"):
                    continue

                child_coverage = child.metrics.get("_own_coverage", 0.0)

                # Find which assertions this child explicitly targets
                explicit_assertion_ids = set()
                for target_id, rel in child.metrics.get("_relationship_to_parent", {}).items():
                    target_node = graph.find_by_id(target_id)
                    if target_node and target_node.kind == NodeKind.ASSERTION:
                        # Check if this assertion belongs to this REQ
                        if target_node in own_assertions:
                            explicit_assertion_ids.add(target_id)

                # Add inferred contribution to assertions NOT explicitly targeted
                for assertion in own_assertions:
                    if assertion.id in explicit_assertion_ids:
                        continue  # Already has explicit from this child

                    # Check if this child already contributed (avoid duplicates)
                    existing = assertion.metrics.get("_coverage_contributions", [])
                    if any(c.source_id == child.id for c in existing):
                        continue

                    existing.append(CoverageContribution(
                        source_id=child.id,
                        source_type=CoverageSource.INFERRED,
                        coverage_value=child_coverage,
                        relationship=rel_to_this,
                    ))
                    assertion.metrics["_coverage_contributions"] = existing

        # Fourth pass: compute RollupMetrics from contributions (post-order)
        for node in graph.all_nodes(order="post"):
            metrics: RollupMetrics = node.metrics["_rollup"]

            if node.kind == NodeKind.ASSERTION:
                metrics.total_assertions = 1
                contributions = node.metrics.get("_coverage_contributions", [])

                # Count coverage by source type
                has_direct = any(c.source_type == CoverageSource.DIRECT for c in contributions)
                has_explicit = any(c.source_type == CoverageSource.EXPLICIT for c in contributions)
                has_inferred = any(c.source_type == CoverageSource.INFERRED for c in contributions)

                if has_direct:
                    metrics.covered_assertions = 1
                    metrics.direct_covered = 1
                elif has_explicit:
                    metrics.covered_assertions = 1
                    metrics.explicit_covered = 1
                elif has_inferred:
                    metrics.covered_assertions = 1
                    metrics.inferred_covered = 1

                # Accumulate test metrics from children
                for child in node.children:
                    child_metrics: RollupMetrics = child.metrics.get("_rollup", RollupMetrics())
                    metrics.total_tests += child_metrics.total_tests
                    metrics.passed_tests += child_metrics.passed_tests
                    metrics.failed_tests += child_metrics.failed_tests
                    metrics.skipped_tests += child_metrics.skipped_tests
                    metrics.total_code_refs += child_metrics.total_code_refs

            elif node.kind == NodeKind.TEST:
                metrics.total_tests = 1
                status = node.metrics.get("_test_status", "unknown")
                if status == "passed":
                    metrics.passed_tests = 1
                elif status == "failed":
                    metrics.failed_tests = 1
                elif status == "skipped":
                    metrics.skipped_tests = 1

            elif node.kind == NodeKind.CODE:
                metrics.total_code_refs = 1

            elif node.kind == NodeKind.REQUIREMENT:
                # Roll up from assertion children
                for child in node.children:
                    if self._should_exclude_child(child, exclude_status):
                        continue

                    child_metrics: RollupMetrics = child.metrics.get("_rollup", RollupMetrics())

                    if child.kind == NodeKind.ASSERTION:
                        metrics.total_assertions += child_metrics.total_assertions
                        metrics.covered_assertions += child_metrics.covered_assertions
                        metrics.direct_covered += child_metrics.direct_covered
                        metrics.explicit_covered += child_metrics.explicit_covered
                        metrics.inferred_covered += child_metrics.inferred_covered
                        metrics.total_tests += child_metrics.total_tests
                        metrics.passed_tests += child_metrics.passed_tests
                        metrics.failed_tests += child_metrics.failed_tests
                        metrics.skipped_tests += child_metrics.skipped_tests
                        metrics.total_code_refs += child_metrics.total_code_refs

                    elif child.kind == NodeKind.REQUIREMENT:
                        # Roll up test/code metrics from child REQs
                        metrics.total_tests += child_metrics.total_tests
                        metrics.passed_tests += child_metrics.passed_tests
                        metrics.failed_tests += child_metrics.failed_tests
                        metrics.skipped_tests += child_metrics.skipped_tests
                        metrics.total_code_refs += child_metrics.total_code_refs

                        # In strict mode, also roll up assertion counts
                        if strict_mode:
                            metrics.total_assertions += child_metrics.total_assertions
                            metrics.covered_assertions += child_metrics.covered_assertions
                            metrics.direct_covered += child_metrics.direct_covered
                            metrics.explicit_covered += child_metrics.explicit_covered
                            metrics.inferred_covered += child_metrics.inferred_covered

                # Calculate percentages
                if metrics.total_assertions > 0:
                    metrics.coverage_pct = (
                        metrics.covered_assertions / metrics.total_assertions
                    ) * 100

                if metrics.total_tests > 0:
                    metrics.pass_rate_pct = (
                        metrics.passed_tests / metrics.total_tests
                    ) * 100

            node.metrics["_rollup"] = metrics

        # Copy rollup metrics to public metrics for convenience
        for node in graph.all_nodes():
            rollup = node.metrics.get("_rollup")
            if rollup:
                node.metrics["total_assertions"] = rollup.total_assertions
                node.metrics["covered_assertions"] = rollup.covered_assertions
                node.metrics["direct_covered"] = rollup.direct_covered
                node.metrics["explicit_covered"] = rollup.explicit_covered
                node.metrics["inferred_covered"] = rollup.inferred_covered
                node.metrics["total_tests"] = rollup.total_tests
                node.metrics["passed_tests"] = rollup.passed_tests
                node.metrics["failed_tests"] = rollup.failed_tests
                node.metrics["skipped_tests"] = rollup.skipped_tests
                node.metrics["total_code_refs"] = rollup.total_code_refs
                node.metrics["coverage_pct"] = rollup.coverage_pct
                node.metrics["pass_rate_pct"] = rollup.pass_rate_pct

            # Serialize coverage contributions for JSON output
            contributions = node.metrics.get("_coverage_contributions", [])
            if contributions:
                node.metrics["coverage_contributions"] = [
                    c.to_dict() for c in contributions
                ]

    def _should_exclude_child(
        self, child: TraceNode, exclude_status: list[str]
    ) -> bool:
        """Check if a child node should be excluded from parent roll-up.

        Args:
            child: The child node to check.
            exclude_status: List of statuses to exclude.

        Returns:
            True if the child should be excluded.
        """
        from elspais.core.graph import NodeKind

        if child.kind != NodeKind.REQUIREMENT:
            return False

        if child.requirement and child.requirement.status in exclude_status:
            return True

        return False

    def _build_file_nodes(self) -> list[TraceNode]:
        """Build FILE and FILE_REGION nodes from stored file structures.

        Creates FILE nodes with FILE_REGION children, and establishes
        bidirectional node-data references between FILE and REQUIREMENT nodes.

        Returns:
            List of FILE TraceNode instances (to be added as roots).
        """
        from elspais.core.graph import (
            FileInfo,
            NodeKind,
            SourceLocation,
            TraceNode,
        )

        file_nodes: list[TraceNode] = []

        for file_path, result in self._file_structures.items():
            file_node_data = result.file_node

            # Look up requirement nodes for this file
            req_nodes: list[TraceNode] = []
            for req_id in file_node_data.requirements:
                req_node = self._nodes.get(req_id)
                if req_node:
                    req_nodes.append(req_node)

            # Create FileInfo with direct node references
            file_info = FileInfo(
                file_path=file_path,
                requirements=req_nodes,
            )

            # Create FILE node
            file_node = TraceNode(
                id=f"file:{file_path}",
                kind=NodeKind.FILE,
                label=file_path,
                source=SourceLocation(path=file_path, line=1),
                file_info=file_info,
            )

            # Create FILE_REGION nodes as children
            for region in file_node_data.regions:
                region_id = f"file:{file_path}:{region.region_type}:{region.start_line}"
                region_node = TraceNode(
                    id=region_id,
                    kind=NodeKind.FILE_REGION,
                    label=f"{region.region_type} ({region.start_line}-{region.end_line})",
                    source=SourceLocation(path=file_path, line=region.start_line),
                    file_region=region,
                )
                # Add as child of FILE node (edge data - for reconstruction traversal)
                file_node.children.append(region_node)
                region_node.parents.append(file_node)
                # Add to index
                self._nodes[region_id] = region_node

            # Set bidirectional node-data references (NOT edges)
            for req_node in req_nodes:
                req_node.source_file = file_node

            # Add FILE node to index
            self._nodes[file_node.id] = file_node
            file_nodes.append(file_node)

        return file_nodes

    def _relative_path(self, path: Path | None) -> str:
        """Convert to repo-relative path string.

        Args:
            path: Absolute or relative path.

        Returns:
            Relative path string.
        """
        if not path:
            return ""
        try:
            return str(path.relative_to(self.repo_root))
        except ValueError:
            return str(path)


def build_graph_from_requirements(
    requirements: dict[str, Requirement],
    repo_root: Path,
    schema: GraphSchema | None = None,
) -> TraceGraph:
    """Convenience function to build a graph from requirements.

    Args:
        requirements: Dictionary of requirement ID to Requirement.
        repo_root: Path to the repository root.
        schema: Optional graph schema.

    Returns:
        Constructed TraceGraph.
    """
    builder = TraceGraphBuilder(repo_root=repo_root, schema=schema)
    builder.add_requirements(requirements)
    return builder.build()


def build_graph_from_repo(
    repo_root: Path,
    config: dict[str, Any] | None = None,
    schema: GraphSchema | None = None,
) -> TraceGraph:
    """Build a graph by loading requirements from a repository.

    Args:
        repo_root: Path to the repository root.
        config: Optional configuration dictionary.
        schema: Optional graph schema.

    Returns:
        Constructed TraceGraph.
    """
    from elspais.core.loader import load_requirements_from_repo

    requirements = load_requirements_from_repo(repo_root, config or {})
    return build_graph_from_requirements(requirements, repo_root, schema)


# Backwards compatibility aliases (deprecated)
# Use TraceGraphBuilder, build_graph_from_requirements, build_graph_from_repo instead
TraceTreeBuilder = TraceGraphBuilder
build_tree_from_requirements = build_graph_from_requirements
build_tree_from_repo = build_graph_from_repo
