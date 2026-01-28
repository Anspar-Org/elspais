"""Mutation types for TraceGraph operations.

This module provides dataclasses for tracking graph mutations,
broken references, and other graph state changes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokenReference:
    """A reference to a non-existent target node.

    Captured during graph build when a link cannot be resolved.

    Attributes:
        source_id: ID of the node containing the reference.
        target_id: ID that was referenced but doesn't exist.
        edge_kind: Type of relationship ("implements", "refines", "validates").
    """

    source_id: str
    target_id: str
    edge_kind: str

    def __str__(self) -> str:
        """Human-readable representation."""
        return f"{self.source_id} --[{self.edge_kind}]--> {self.target_id} (missing)"


__all__ = ["BrokenReference"]
