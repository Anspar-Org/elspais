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
    # Phase 4: reference-type definitions, synonyms, change tracking
    is_reference: bool = False  # True for external standard/document definitions
    reference_fields: dict[str, str] = field(
        default_factory=dict
    )  # title, version, effective_date, url
    reference_term: str = ""  # synonym: official name in a reference document
    reference_source: str = ""  # which reference document defines the official name
    definition_hash: str = ""  # SHA-256 hash of definition text for change tracking


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

    def iter_references(self) -> Iterator[TermEntry]:
        """Yield only reference-type entries (external standards/documents)."""
        for entry in self._entries.values():
            if entry.is_reference:
                yield entry

    def lookup_by_synonym(self, synonym: str) -> TermEntry | None:
        """Find a term that declares the given synonym via reference_term."""
        key = synonym.lower()
        for entry in self._entries.values():
            if entry.reference_term and entry.reference_term.lower() == key:
                return entry
        return None

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


def _canonicalize_definition_text(text: str) -> str:
    """Canonicalize whitespace in definition text before hashing.

    - Strip trailing whitespace from each line
    - Collapse runs of blank lines to a single blank line
    - Strip leading/trailing blank lines from the block
    """
    lines = [line.rstrip() for line in text.split("\n")]
    collapsed: list[str] = []
    prev_blank = False
    for line in lines:
        if not line:
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        collapsed.append(line)
    return "\n".join(collapsed).strip()


def compute_definition_hash(
    definition: str,
    reference_fields: dict[str, str] | None = None,
) -> str:
    """Compute 8-char SHA-256 hash of a term definition for change tracking.

    Definition text is canonicalized (trailing whitespace stripped, blank
    runs collapsed, outer whitespace trimmed) before hashing so cosmetic
    whitespace changes do not flip hashes on round-trip.

    For reference-type entries, includes reference_fields values so that
    URL/version/title changes are detected.
    """
    from elspais.utilities.hasher import calculate_hash

    text = _canonicalize_definition_text(definition)
    if reference_fields:
        text += "\n" + "\n".join(f"{k}={v}" for k, v in sorted(reference_fields.items()))
    return calculate_hash(text)


def diff_terms(old: TermDictionary, new: TermDictionary) -> dict[str, list[dict[str, str]]]:
    """Compare two TermDictionaries and return changes.

    Returns dict with 'added', 'removed', 'changed' lists.
    Each entry is {'term': str, 'old_hash': str, 'new_hash': str}.
    """
    old_keys = {e.term.lower(): e for e in old.iter_all()}
    new_keys = {e.term.lower(): e for e in new.iter_all()}

    added = [
        {"term": new_keys[k].term, "old_hash": "", "new_hash": new_keys[k].definition_hash}
        for k in new_keys
        if k not in old_keys
    ]
    removed = [
        {"term": old_keys[k].term, "old_hash": old_keys[k].definition_hash, "new_hash": ""}
        for k in old_keys
        if k not in new_keys
    ]
    changed = [
        {
            "term": new_keys[k].term,
            "old_hash": old_keys[k].definition_hash,
            "new_hash": new_keys[k].definition_hash,
        }
        for k in new_keys
        if k in old_keys and new_keys[k].definition_hash != old_keys[k].definition_hash
    ]

    return {"added": added, "removed": removed, "changed": changed}
