"""Tests for the term-index reference filter.

Verifies: REQ-d00253-C (Generated INDEX.md and term-index.md SHALL contain
only primary-repo requirements and terms unless federation.index_associates
is true). A term index groups each term's references by namespace
(``**<NS>:**`` blocks); the federated term scan records references from
associate repos, so a primary-defined term referenced by an associate
requirement would otherwise produce a ``**<ASSOCIATE_NS>:**`` section in the
primary term index. The ``ref_filter`` predicate drops those references.
"""

from __future__ import annotations

import json

from elspais.commands.glossary_cmd import generate_term_index, write_term_outputs
from elspais.graph.terms import TermDictionary, TermEntry, TermRef


def _build_dictionary() -> TermDictionary:
    """One indexed term referenced from two namespaces (primary + associate)."""
    td = TermDictionary()
    td.add(
        TermEntry(
            term="Diary Entry",
            definition="A dated participant-authored record.",
            indexed=True,
            defined_in="REQ-p00001",
            namespace="DIARY",
            references=[
                # Primary-repo references.
                TermRef(node_id="REQ-p00003", namespace="DIARY", marked=True, line=10),
                TermRef(node_id="REQ-d00045", namespace="DIARY", marked=False, line=22),
                # Associate-repo reference (recorded by the federated term scan).
                TermRef(node_id="REQ-c00009", namespace="CAL", marked=False, line=4),
            ],
        )
    )
    return td


def test_unfiltered_index_contains_both_namespaces() -> None:
    """Without a filter, both primary and associate namespace blocks appear."""
    td = _build_dictionary()
    out = generate_term_index(td)
    assert "**DIARY:**" in out
    assert "**CAL:**" in out
    assert "## Diary Entry" in out


def test_filter_drops_associate_namespace_keeps_term() -> None:
    """A ref_filter excluding CAL removes its block but keeps DIARY and the term."""
    td = _build_dictionary()
    out = generate_term_index(td, ref_filter=lambda r: r.namespace != "CAL")
    assert "**DIARY:**" in out
    assert "**CAL:**" not in out
    # The term itself is still listed even though one namespace was dropped.
    assert "## Diary Entry" in out
    # The associate node id must not leak in either.
    assert "REQ-c00009" not in out


def test_json_format_honors_filter() -> None:
    """JSON output drops the excluded namespace from the references dict."""
    td = _build_dictionary()
    raw = generate_term_index(td, format="json", ref_filter=lambda r: r.namespace != "CAL")
    data = json.loads(raw)
    assert len(data) == 1
    refs = data[0]["references"]
    assert "DIARY" in refs
    assert "CAL" not in refs
    assert "REQ-c00009" not in refs["DIARY"]


def test_write_term_outputs_filters_index_not_glossary(tmp_path) -> None:
    """write_term_outputs applies the filter to term-index.md but not glossary.md."""
    td = _build_dictionary()
    generate = write_term_outputs(td, tmp_path, ref_filter=lambda r: r.namespace != "CAL")
    assert any(p.endswith("term-index.md") for p in generate)

    index_text = (tmp_path / "term-index.md").read_text(encoding="utf-8")
    assert "**DIARY:**" in index_text
    assert "**CAL:**" not in index_text
    assert "## Diary Entry" in index_text

    # The glossary lists definitions only (no per-namespace reference blocks);
    # the filter must not disturb it. The defining term is still present.
    glossary_text = (tmp_path / "glossary.md").read_text(encoding="utf-8")
    assert "Diary Entry" in glossary_text
    # Glossary records the defining namespace, which is unaffected by the filter.
    assert "DIARY" in glossary_text
