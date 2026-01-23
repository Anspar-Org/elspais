"""Tree builder for constructing traceability trees.

This module provides the TraceTreeBuilder class for building TraceTree
instances from various data sources (requirements, tests, code references).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.core.models import Requirement
    from elspais.core.tree import TraceNode, TraceTree
    from elspais.core.tree_schema import TreeSchema


@dataclass
class ValidationResult:
    """Result of tree validation.

    Attributes:
        is_valid: True if no errors were found.
        errors: List of error messages.
        warnings: List of warning messages.
    """

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class TraceTreeBuilder:
    """Builds a TraceTree from various data sources.

    The builder pattern allows incremental construction of the tree
    from multiple data sources, with final linking and validation
    performed when build() is called.

    Example:
        builder = TraceTreeBuilder(repo_root=Path.cwd())
        builder.add_requirements(requirements)
        builder.add_test_coverage(test_data)
        tree = builder.build()
    """

    def __init__(
        self,
        repo_root: Path,
        schema: TreeSchema | None = None,
    ) -> None:
        """Initialize the builder.

        Args:
            repo_root: Path to the repository root.
            schema: Tree schema (uses default if not provided).
        """
        from elspais.core.tree_schema import TreeSchema

        self.repo_root = repo_root
        self.schema = schema or TreeSchema.default()
        self._nodes: dict[str, TraceNode] = {}
        self._requirements: dict[str, Requirement] = {}
        self._pending_links: list[tuple[str, str, str]] = []  # (from_id, to_id, rel_name)

    def add_requirements(self, requirements: dict[str, Requirement]) -> TraceTreeBuilder:
        """Add requirements and their assertions as nodes.

        Args:
            requirements: Dictionary of requirement ID to Requirement.

        Returns:
            Self for method chaining.
        """
        from elspais.core.tree import NodeKind, SourceLocation, TraceNode

        self._requirements = requirements

        for req_id, req in requirements.items():
            # Skip conflict entries for tree building
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

            # Queue addresses links if present
            addresses = getattr(req, "addresses", [])
            for addr_id in addresses:
                self._pending_links.append((req_id, addr_id, "addresses"))

        return self

    def add_user_journeys(self, journeys: dict[str, TraceNode]) -> TraceTreeBuilder:
        """Add user journey nodes.

        Args:
            journeys: Dictionary of journey ID to TraceNode.

        Returns:
            Self for method chaining.
        """
        for jny_id, jny_node in journeys.items():
            self._nodes[jny_id] = jny_node
        return self

    def add_nodes(self, nodes: list[TraceNode]) -> TraceTreeBuilder:
        """Add pre-built nodes to the tree.

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

    def add_test_coverage(self, test_nodes: list[TraceNode]) -> TraceTreeBuilder:
        """Add test reference nodes.

        Args:
            test_nodes: List of test TraceNode instances.

        Returns:
            Self for method chaining.
        """
        return self.add_nodes(test_nodes)

    def add_code_references(self, code_nodes: list[TraceNode]) -> TraceTreeBuilder:
        """Add code reference nodes.

        Args:
            code_nodes: List of code TraceNode instances.

        Returns:
            Self for method chaining.
        """
        return self.add_nodes(code_nodes)

    def add_test_results(self, result_nodes: list[TraceNode]) -> TraceTreeBuilder:
        """Add test result nodes.

        Args:
            result_nodes: List of test result TraceNode instances.

        Returns:
            Self for method chaining.
        """
        return self.add_nodes(result_nodes)

    def build(self) -> TraceTree:
        """Build the final tree, linking parent-child relationships.

        Returns:
            The constructed TraceTree.
        """
        from elspais.core.tree import TraceTree

        # Link all pending relationships
        self._link_relationships()

        # Find roots
        roots = self._find_roots()

        # Create tree
        tree = TraceTree(
            roots=sorted(roots, key=lambda n: n.id),
            repo_root=self.repo_root,
            _index=dict(self._nodes),
        )

        return tree

    def build_and_validate(self) -> tuple[TraceTree, ValidationResult]:
        """Build the tree and run validation.

        Returns:
            Tuple of (TraceTree, ValidationResult).
        """
        tree = self.build()
        result = self.validate(tree)
        return tree, result

    def validate(self, tree: TraceTree) -> ValidationResult:
        """Validate the tree according to schema rules.

        Args:
            tree: The tree to validate.

        Returns:
            ValidationResult with errors and warnings.
        """
        result = ValidationResult()

        if self.schema.validation.cycle_check:
            cycles = self._detect_cycles(tree)
            for cycle in cycles:
                result.errors.append(f"Cycle detected: {' -> '.join(cycle)}")
                result.is_valid = False

        if self.schema.validation.orphan_check:
            orphans = self._find_orphans(tree)
            for orphan_id in orphans:
                result.warnings.append(f"Orphaned node: {orphan_id}")

        if self.schema.validation.broken_link_check:
            broken = self._find_broken_links()
            for from_id, to_id in broken:
                result.warnings.append(f"Broken link: {from_id} -> {to_id}")

        if self.schema.validation.duplicate_id_check:
            # Already handled during add_requirements (conflicts)
            pass

        return result

    def _link_relationships(self) -> None:
        """Link all pending relationships."""
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

        Tries: exact match, with REQ- prefix, suffix match.

        Args:
            node_id: The ID to search for.

        Returns:
            Matching TraceNode or None.
        """
        # Exact match
        if node_id in self._nodes:
            return self._nodes[node_id]

        # Try with REQ- prefix
        prefixed = f"REQ-{node_id}"
        if prefixed in self._nodes:
            return self._nodes[prefixed]

        # Suffix match (e.g., "p00001" matches "REQ-p00001")
        for nid, node in self._nodes.items():
            if nid.endswith(node_id) or nid.endswith(f"-{node_id}"):
                return node

        return None

    def _find_roots(self) -> list[TraceNode]:
        """Find root nodes (nodes with no parents).

        Returns:
            List of root TraceNode instances.
        """
        from elspais.core.tree import NodeKind

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

    def _detect_cycles(self, tree: TraceTree) -> list[list[str]]:
        """Detect cycles in the tree.

        Args:
            tree: The tree to check.

        Returns:
            List of cycle paths (each path is a list of node IDs).
        """
        from elspais.core.tree import NodeKind

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

            node = tree.find_by_id(node_id)
            if node:
                for child in node.children:
                    # Only follow requirement children for cycle detection
                    if child.kind == NodeKind.REQUIREMENT:
                        dfs(child.id, path[:])

            rec_stack.remove(node_id)

        # Start from roots
        for root in tree.roots:
            dfs(root.id, [])

        # Also check all requirement nodes using the index directly
        # (in case there are isolated cycles where no node is a root)
        for node_id, node in tree._index.items():
            if node.kind == NodeKind.REQUIREMENT and node_id not in visited:
                dfs(node_id, [])

        return cycles

    def _find_orphans(self, tree: TraceTree) -> list[str]:
        """Find orphaned nodes (non-root nodes with no parents).

        Args:
            tree: The tree to check.

        Returns:
            List of orphaned node IDs.
        """
        from elspais.core.tree import NodeKind

        orphans: list[str] = []

        for node in tree.all_nodes():
            # Skip roots and assertions (assertions have req parent)
            if node in tree.roots:
                continue
            if node.kind == NodeKind.ASSERTION:
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


def build_tree_from_requirements(
    requirements: dict[str, Requirement],
    repo_root: Path,
    schema: TreeSchema | None = None,
) -> TraceTree:
    """Convenience function to build a tree from requirements.

    Args:
        requirements: Dictionary of requirement ID to Requirement.
        repo_root: Path to the repository root.
        schema: Optional tree schema.

    Returns:
        Constructed TraceTree.
    """
    builder = TraceTreeBuilder(repo_root=repo_root, schema=schema)
    builder.add_requirements(requirements)
    return builder.build()


def build_tree_from_repo(
    repo_root: Path,
    config: dict[str, Any] | None = None,
    schema: TreeSchema | None = None,
) -> TraceTree:
    """Build a tree by loading requirements from a repository.

    Args:
        repo_root: Path to the repository root.
        config: Optional configuration dictionary.
        schema: Optional tree schema.

    Returns:
        Constructed TraceTree.
    """
    from elspais.core.loader import load_requirements_from_repo

    requirements = load_requirements_from_repo(repo_root, config or {})
    return build_tree_from_requirements(requirements, repo_root, schema)
