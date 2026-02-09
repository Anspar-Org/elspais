# Implements: REQ-o00062-E
"""Mutation types for TraceGraph operations.

This module provides dataclasses for tracking graph mutations,
broken references, and other graph state changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


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


@dataclass
class MutationEntry:
    """Single mutation operation record.

    Records a mutation for auditing and undo support. The before_state
    contains enough information to reverse the operation.

    Attributes:
        id: Unique mutation ID (UUID4).
        timestamp: When the mutation occurred.
        operation: Operation type (e.g., "rename_node", "add_edge").
        target_id: Primary target of the mutation.
        before_state: State before mutation (for undo).
        after_state: State after mutation.
        affects_hash: Whether this mutation affects content hash.
    """

    operation: str
    target_id: str
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    affects_hash: bool = False
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        """Human-readable representation."""
        return f"[{self.id[:8]}] {self.operation}({self.target_id})"


class MutationLog:
    """Append-only mutation history.

    Provides auditing and undo capabilities for graph mutations.
    Entries are stored in chronological order.

    Example:
        >>> log = MutationLog()
        >>> entry = MutationEntry(
        ...     operation="rename_node",
        ...     target_id="REQ-p00001",
        ...     before_state={"id": "REQ-p00001"},
        ...     after_state={"id": "REQ-p00002"},
        ... )
        >>> log.append(entry)
        >>> list(log.iter_entries())
        [MutationEntry(...)]
    """

    def __init__(self) -> None:
        """Initialize an empty mutation log."""
        self._entries: list[MutationEntry] = []

    def append(self, entry: MutationEntry) -> None:
        """Append a mutation entry to the log.

        Args:
            entry: The mutation record to append.
        """
        self._entries.append(entry)

    def iter_entries(self) -> Iterator[MutationEntry]:
        """Iterate over all entries in chronological order.

        Yields:
            MutationEntry instances in order of occurrence.
        """
        yield from self._entries

    def __len__(self) -> int:
        """Return the number of entries in the log."""
        return len(self._entries)

    def last(self) -> MutationEntry | None:
        """Return the most recent entry, or None if empty."""
        return self._entries[-1] if self._entries else None

    def find_by_id(self, mutation_id: str) -> MutationEntry | None:
        """Find an entry by its mutation ID.

        Args:
            mutation_id: The UUID of the mutation to find.

        Returns:
            The matching MutationEntry, or None if not found.
        """
        for entry in self._entries:
            if entry.id == mutation_id:
                return entry
        return None

    def entries_since(self, mutation_id: str) -> list[MutationEntry]:
        """Get all entries since (and including) a specific mutation.

        Useful for batch undo operations.

        Args:
            mutation_id: The UUID to start from.

        Returns:
            List of entries from the specified mutation to the most recent.

        Raises:
            ValueError: If the mutation_id is not found.
        """
        for i, entry in enumerate(self._entries):
            if entry.id == mutation_id:
                return list(self._entries[i:])
        raise ValueError(f"Mutation {mutation_id} not found in log")

    def pop(self) -> MutationEntry | None:
        """Remove and return the most recent entry.

        Used internally for undo operations. Does not log the removal.

        Returns:
            The removed entry, or None if log is empty.
        """
        return self._entries.pop() if self._entries else None

    def clear(self) -> None:
        """Clear all entries from the log."""
        self._entries.clear()


__all__ = ["BrokenReference", "MutationEntry", "MutationLog"]
