# Implements: REQ-o00062-E
"""Mutation types for TraceGraph operations.

This module provides dataclasses for tracking graph mutations and other
graph state changes. Reference faults live in
``elspais.graph.reference_faults``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


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
        self._revision = 0
        self._dirty_observer: Callable[[bool], None] | None = None

    # Implements: REQ-p00083-E
    def set_dirty_observer(self, observer: Callable[[bool], None] | None) -> None:
        """Watch the transitions between holding changes and holding none.

        The observer is called with True when the log goes from empty to
        holding an entry, and with False when it goes back to empty. Only
        on those transitions, never per entry: what it exists to record is
        the fact of holding unrecorded work, which does not change while
        the count merely grows.

        It runs inside the append, before the mutation is acknowledged to
        whoever made it. A process that dies between the acknowledgement
        and the observer is the case the whole arrangement exists for.
        """
        self._dirty_observer = observer

    def _notify_dirty(self, holding: bool) -> None:
        observer = self._dirty_observer
        if observer is not None:
            observer(holding)

    @property
    def revision(self) -> int:
        """Monotonic count of changes to this log.

        Advances on every append, undo and clear, and never repeats. The
        tip id cannot serve this purpose: an append followed by an undo
        restores the previous tip exactly, so two logs with the same tip
        may have had activity between them.
        """
        return self._revision

    def append(self, entry: MutationEntry) -> None:
        """Append a mutation entry to the log.

        Args:
            entry: The mutation record to append.
        """
        was_holding = bool(self._entries)
        self._entries.append(entry)
        self._revision += 1
        if not was_holding:
            self._notify_dirty(True)

    def iter_entries(self) -> Iterator[MutationEntry]:
        """Iterate over all entries in chronological order.

        Yields:
            MutationEntry instances in order of occurrence.
        """
        yield from self._entries

    def tail(self, limit: int) -> list[MutationEntry]:
        """Return the most recent ``limit`` entries, oldest-to-newest.

        Returns a snapshot list, never a live iterator: concurrent writers
        append (and undo removes) entries, and handing out a live view over
        ``_entries`` invites skipped or double-yielded elements. The
        snapshot is internally consistent; freshness is the tip guard's job.
        """
        entries = list(self._entries)
        return entries[-limit:] if limit > 0 else entries

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
        if not self._entries:
            return None
        self._revision += 1
        entry = self._entries.pop()
        if not self._entries:
            self._notify_dirty(False)
        return entry

    def clear(self) -> None:
        """Clear all entries from the log."""
        was_holding = bool(self._entries)
        if was_holding:
            self._revision += 1
        self._entries.clear()
        if was_holding:
            self._notify_dirty(False)


__all__ = ["MutationEntry", "MutationLog"]
