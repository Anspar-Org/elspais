"""Defined terms data model for glossary, index, and collection support.

Implements: REQ-d00220
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
# Implements: REQ-d00220-E
class TermRef:
    """A reference to a defined term found in prose text."""

    node_id: str  # enclosing element (REQ, ASSERTION, REMAINDER, FILE)
    namespace: str  # repo where the reference occurs
    marked: bool  # True = *term*/**term**, False = plain text
    line: int  # for error reporting
    wrong_marking: str = ""  # e.g. "__" when markup_styles are ["*", "**"]
    surface_form: str = ""  # the actual text matched (e.g. "traceability")
    delimiter: str = ""  # the emphasis delimiter used (e.g. "*", "**", "")

    def is_canonical(self, canonical_term: str) -> bool:
        """Check if this ref uses canonical form (correct markup + casing)."""
        return self.marked and self.surface_form == canonical_term


@dataclass
class TermEntry:
    """A single defined term with its definition and metadata."""

    term: str  # display form (original casing)
    definition: str  # full definition text (metadata lines stripped)
    collection: bool = False  # generates its own manifest
    indexed: bool = True  # True by default; False suppresses index + health check
    defined_in: str = ""  # node ID of nearest REQUIREMENT or FILE ancestor
    defined_at_line: int = 0  # for error reporting
    namespace: str = ""  # repo namespace
    references: list[TermRef] = field(default_factory=list)


# Implements: REQ-d00220
class TermDictionary:
    """Term index, keyed by normalized (lowercased) term name."""

    def __init__(self) -> None:
        self._entries: dict[str, TermEntry] = {}

    # Implements: REQ-d00220-A
    def add(self, entry: TermEntry) -> TermEntry | None:
        """Add a term entry. Returns existing entry on duplicate, None otherwise."""
        key = entry.term.lower()
        existing = self._entries.get(key)
        if existing is not None:
            return existing
        self._entries[key] = entry
        return None

    # Implements: REQ-d00220-B
    def lookup(self, term: str) -> TermEntry | None:
        """Case-insensitive lookup. Returns the entry or None."""
        return self._entries.get(term.lower())

    def iter_all(self) -> Iterator[TermEntry]:
        """Yield all term entries."""
        yield from self._entries.values()

    # Implements: REQ-d00220-C
    def iter_indexed(self) -> Iterator[TermEntry]:
        """Yield only entries where indexed is True."""
        for entry in self._entries.values():
            if entry.indexed:
                yield entry

    # Implements: REQ-d00220-C
    def iter_collections(self) -> Iterator[TermEntry]:
        """Yield only entries where collection is True."""
        for entry in self._entries.values():
            if entry.collection:
                yield entry

    # Implements: REQ-d00220-D
    def merge(self, other: TermDictionary) -> list[tuple[TermEntry, TermEntry]]:
        """Merge another dictionary into this one.

        Returns a list of (existing, incoming) pairs for duplicate terms.
        """
        duplicates: list[tuple[TermEntry, TermEntry]] = []
        for key, entry in other._entries.items():
            existing = self._entries.get(key)
            if existing is not None:
                duplicates.append((existing, entry))
            else:
                self._entries[key] = entry
        return duplicates

    def __len__(self) -> int:
        return len(self._entries)
