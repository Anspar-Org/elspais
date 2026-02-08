"""Relations - Edge types and relationship semantics.

This module defines the typed edges between graph nodes:
- EdgeKind: Enum of relationship types with semantic properties
- Edge: A typed edge between two nodes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.GraphNode import GraphNode


class EdgeKind(Enum):
    """Types of edges in the traceability graph.

    Each edge type has semantic meaning for coverage calculation:
    - IMPLEMENTS: Child claims to satisfy parent (coverage rollup)
    - REFINES: Child adds detail to parent (NO coverage rollup)
    - VALIDATES: Test validates requirement/assertion (coverage rollup)
    - ADDRESSES: Links to user journey (informational, no coverage)
    - CONTAINS: File structure containment (no coverage)
    """

    IMPLEMENTS = "implements"
    REFINES = "refines"
    VALIDATES = "validates"
    ADDRESSES = "addresses"
    CONTAINS = "contains"

    def contributes_to_coverage(self) -> bool:
        """Check if this edge type contributes to coverage rollup.

        Returns:
            True if edges of this type should be included in coverage
            calculations, False otherwise.
        """
        return self in (EdgeKind.IMPLEMENTS, EdgeKind.VALIDATES)


@dataclass
class Edge:
    """A typed edge between two graph nodes.

    Edges represent relationships with semantic meaning. The edge kind
    determines how the relationship affects metrics like coverage.

    Attributes:
        source: The parent/source node.
        target: The child/target node.
        kind: The type of relationship.
        assertion_targets: For multi-assertion syntax, the specific
            assertion labels targeted (e.g., ["A", "B", "C"]).
    """

    source: GraphNode
    target: GraphNode
    kind: EdgeKind
    assertion_targets: list[str] = field(default_factory=list)

    def __eq__(self, other: object) -> bool:
        """Check equality based on source, target, and kind."""
        if not isinstance(other, Edge):
            return NotImplemented
        return (
            self.source.id == other.source.id
            and self.target.id == other.target.id
            and self.kind == other.kind
            and self.assertion_targets == other.assertion_targets
        )

    def __hash__(self) -> int:
        """Hash based on source, target, and kind."""
        return hash((self.source.id, self.target.id, self.kind.value))
