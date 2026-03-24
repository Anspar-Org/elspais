"""Tests for TermDictionary data model.

Validates REQ-d00220-A+B+C+D: TermDictionary add, lookup, iteration,
and merge operations for defined terms support.
"""

from __future__ import annotations

from elspais.graph.terms import TermDictionary, TermEntry, TermRef


def _make_entry(
    term: str = "electronic record",
    definition: str = "Any combination of text stored in digital form.",
    *,
    collection: bool = False,
    indexed: bool = True,
    defined_in: str = "REQ-p00001",
    defined_at_line: int = 10,
    namespace: str = "main",
    references: list[TermRef] | None = None,
) -> TermEntry:
    """Create a TermEntry with sensible defaults to reduce test boilerplate."""
    return TermEntry(
        term=term,
        definition=definition,
        collection=collection,
        indexed=indexed,
        defined_in=defined_in,
        defined_at_line=defined_at_line,
        namespace=namespace,
        references=references if references is not None else [],
    )


class TestTermDictionary:
    """Validates REQ-d00220-A+B+C+D: TermDictionary CRUD and iteration."""

    def test_REQ_d00220_A_add_stores_entry(self) -> None:
        """add() stores an entry that lookup() can retrieve."""
        td = TermDictionary()
        entry = _make_entry(term="Electronic Record")
        td.add(entry)

        result = td.lookup("electronic record")
        assert result is not None
        assert result.term == "Electronic Record"
        assert result.definition == entry.definition

    def test_REQ_d00220_A_add_returns_none_first_time(self) -> None:
        """add() returns None when the term is new (no duplicate)."""
        td = TermDictionary()
        entry = _make_entry(term="Audit Trail")
        result = td.add(entry)
        assert result is None

    def test_REQ_d00220_A_add_duplicate_returns_existing(self) -> None:
        """Adding a term that already exists returns the existing entry."""
        td = TermDictionary()
        first = _make_entry(term="Electronic Record", definition="First definition.")
        second = _make_entry(term="electronic record", definition="Second definition.")

        td.add(first)
        existing = td.add(second)

        assert existing is first
        # The original entry should not be overwritten.
        found = td.lookup("electronic record")
        assert found is not None
        assert found.definition == "First definition."

    def test_REQ_d00220_B_lookup_case_insensitive(self) -> None:
        """lookup() performs case-insensitive matching."""
        td = TermDictionary()
        entry = _make_entry(term="electronic record")
        td.add(entry)

        assert td.lookup("Electronic Record") is entry
        assert td.lookup("ELECTRONIC RECORD") is entry
        assert td.lookup("Electronic record") is entry

    def test_REQ_d00220_B_lookup_missing_returns_none(self) -> None:
        """lookup() returns None for a term not in the dictionary."""
        td = TermDictionary()
        assert td.lookup("nonexistent term") is None

    def test_REQ_d00220_C_iter_indexed(self) -> None:
        """iter_indexed() yields only entries where indexed is True."""
        td = TermDictionary()
        indexed_entry = _make_entry(term="Audit Trail", indexed=True)
        non_indexed_entry = _make_entry(term="Level", indexed=False)
        td.add(indexed_entry)
        td.add(non_indexed_entry)

        indexed_terms = list(td.iter_indexed())
        assert len(indexed_terms) == 1
        assert indexed_terms[0].term == "Audit Trail"

    def test_REQ_d00220_C_iter_collections(self) -> None:
        """iter_collections() yields only entries where collection is True."""
        td = TermDictionary()
        collection_entry = _make_entry(term="Questionnaire", collection=True)
        regular_entry = _make_entry(term="Electronic Record", collection=False)
        td.add(collection_entry)
        td.add(regular_entry)

        collections = list(td.iter_collections())
        assert len(collections) == 1
        assert collections[0].term == "Questionnaire"

    def test_REQ_d00220_D_merge_combines(self) -> None:
        """merge() combines entries from two dictionaries."""
        td1 = TermDictionary()
        td2 = TermDictionary()

        entry_a = _make_entry(term="Audit Trail", namespace="main")
        entry_b = _make_entry(term="Questionnaire", namespace="sponsor-a")
        td1.add(entry_a)
        td2.add(entry_b)

        td1.merge(td2)

        assert td1.lookup("audit trail") is entry_a
        assert td1.lookup("questionnaire") is entry_b

    def test_REQ_d00220_D_merge_detects_duplicates(self) -> None:
        """merge() returns duplicate pairs for same term across namespaces."""
        td1 = TermDictionary()
        td2 = TermDictionary()

        entry_main = _make_entry(
            term="Electronic Record",
            namespace="main",
            definition="Main definition.",
        )
        entry_sponsor = _make_entry(
            term="electronic record",
            namespace="sponsor-a",
            definition="Sponsor definition.",
        )
        td1.add(entry_main)
        td2.add(entry_sponsor)

        duplicates = td1.merge(td2)

        assert len(duplicates) == 1
        pair = duplicates[0]
        assert pair[0] is entry_main
        assert pair[1] is entry_sponsor
