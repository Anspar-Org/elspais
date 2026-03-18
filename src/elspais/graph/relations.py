"""Relations - Edge types and relationship semantics.

This module defines the typed edges between graph nodes:
- EdgeKind: Enum of relationship types with semantic properties
- Edge: A typed edge between two nodes
- Stereotype: Node classification for template-instance pattern
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.GraphNode import GraphNode


# Implements: REQ-p00014-C
class Stereotype(Enum):
    """Classification of nodes in the template-instance pattern.

    - CONCRETE: Default — normal requirement node
    - TEMPLATE: Original node targeted by a Satisfies declaration
    - INSTANCE: Cloned copy of a template node
    """

    CONCRETE = "concrete"
    TEMPLATE = "template"
    INSTANCE = "instance"


# Implements: REQ-p00050-A
class EdgeKind(Enum):
    """Types of edges in the traceability graph.

    Each edge type has semantic meaning for coverage calculation:
    - IMPLEMENTS: Child claims to satisfy parent (coverage rollup)
    - REFINES: Child adds detail to parent (NO coverage rollup)
    - VERIFIES: TEST/CODE verifies/implements assertion (coverage rollup)
    - ADDRESSES: Links to user journey (informational, no coverage)
    - CONTAINS: File structure containment (no coverage)
    - SATISFIES: Requirement satisfies a cross-cutting template (structural, no coverage)
    """

    IMPLEMENTS = "implements"
    REFINES = "refines"
    VERIFIES = "verifies"
    ADDRESSES = "addresses"
    CONTAINS = "contains"
    # Implements: REQ-d00069-G
    SATISFIES = "satisfies"
    # Implements: REQ-p00014-C
    INSTANCE = "instance"
    # Implements: REQ-d00126-C
    STRUCTURES = "structures"
    DEFINES = "defines"
    YIELDS = "yields"

    # Implements: REQ-p00050-D
    def contributes_to_coverage(self) -> bool:
        """Check if this edge type contributes to coverage rollup.

        Returns:
            True if edges of this type should be included in coverage
            calculations, False otherwise.
        """
        return self in (EdgeKind.IMPLEMENTS, EdgeKind.VERIFIES)


# Implements: REQ-p00050-A
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
    # Implements: REQ-d00126-E
    metadata: dict[str, Any] = field(default_factory=dict)

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
        """Hash based on source, target, kind, and assertion_targets."""
        return hash(
            (self.source.id, self.target.id, self.kind.value, tuple(self.assertion_targets))
        )
