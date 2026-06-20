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
    - VALIDATES: JNY validates REQ/assertion (coverage rollup, UAT)
    - CONTAINS: File structure containment (no coverage)
    - SATISFIES: Requirement satisfies a cross-cutting template (structural, no coverage)
    """

    IMPLEMENTS = "implements"
    REFINES = "refines"
    VERIFIES = "verifies"
    VALIDATES = "validates"
    CONTAINS = "contains"
    # Implements: REQ-d00069-G
    SATISFIES = "satisfies"
    # Implements: REQ-p00014-C
    INSTANCE = "instance"
    # Implements: REQ-d00126-C
    STRUCTURES = "structures"
    DEFINES = "defines"
    YIELDS = "yields"
    # Implements: REQ-d00252
    # Top-down external reference: consumer REQ is implemented by an associate
    # library node. Distinct from IMPLEMENTS so the library's Implements:
    # derivation (filtered on EdgeKind.IMPLEMENTS) never renders a consumer ID
    # into the library file.
    INTEGRATES = "integrates"

    # Implements: REQ-p00050-D
    def contributes_to_coverage(self) -> bool:
        """Check if this edge type contributes to coverage rollup.

        Returns:
            True if edges of this type should be included in coverage
            calculations, False otherwise.
        """
        return self in (
            EdgeKind.IMPLEMENTS,
            EdgeKind.VERIFIES,
            EdgeKind.VALIDATES,
            EdgeKind.INTEGRATES,
        )

    # Implements: REQ-d00069-J
    def conducts_coverage(self) -> bool:
        """Check if this edge type conducts child coverage up to a parent assertion.

        Conduction paths add no coverage by themselves -- they propagate the
        *actual* per-dimension coverage of the refining/implementing child up to
        the targeted parent *Assertion* (REQ-d00069-J). This is distinct from
        :meth:`contributes_to_coverage`, which classifies leaf-evidence edges
        (TEST/CODE/JNY) and is relied on by reachability checks.

        Currently only ``REFINES`` conducts; req->req ``IMPLEMENTS`` keeps its
        binary EXPLICIT/INFERRED contribution (see CUR-1329 scope note).

        Returns:
            True if edges of this type conduct child coverage upward.
        """
        return self is EdgeKind.REFINES


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
