"""Tests for glossary and term index generators.

Validates REQ-d00224-A+B+C+D: glossary output, term index, collection manifests,
and format support.
"""

from __future__ import annotations

import json

import pytest

from elspais.graph.terms import TermDictionary, TermEntry, TermRef


def _build_test_dictionary() -> TermDictionary:
    """Build a TermDictionary with representative test data."""
    td = TermDictionary()

    td.add(TermEntry(
        term="Electronic Record",
        definition="Any combination of text, graphics, data, audio, or pictorial "
                   "information stored in digital form.",
        collection=False,
        indexed=True,
        defined_in="REQ-p00001",
        namespace="main",
        references=[
            TermRef(node_id="REQ-p00003", namespace="main", marked=True, line=10),
            TermRef(node_id="REQ-p00003-B", namespace="main", marked=True, line=15),
            TermRef(node_id="REQ-d00045", namespace="main", marked=False, line=22),
            TermRef(node_id="file:src/records/model.dart", namespace="sponsor-a", marked=False, line=5),
        ],
    ))

    td.add(TermEntry(
        term="Questionnaire",
        definition="A structured set of questions administered to a participant.",
        collection=True,
        indexed=True,
        defined_in="REQ-p00012",
        namespace="main",
        references=[
            TermRef(node_id="REQ-p00012", namespace="main", marked=True, line=1),
            TermRef(node_id="REQ-p00012-A", namespace="main", marked=True, line=5),
            TermRef(node_id="REQ-d00067-C", namespace="sponsor-a", marked=False, line=30),
            TermRef(node_id="file:src/questionnaire/hhc_qol.dart", namespace="sponsor-a", marked=False, line=12),
        ],
    ))

    td.add(TermEntry(
        term="Level",
        definition="The classification tier of a requirement (PRD, OPS, DEV).",
        collection=False,
        indexed=False,
        defined_in="REQ-p00001",
        namespace="main",
        references=[],
    ))

    return td


# Lazy import helper — the module under test does not exist yet.
def _import_generators():
    from elspais.commands.glossary_cmd import (
        generate_collection_manifest,
        generate_glossary,
        generate_term_index,
    )
    return generate_glossary, generate_term_index, generate_collection_manifest


class TestGlossaryCmd:
    """Validates REQ-d00224-A+B+C+D: glossary generators."""

    # -- REQ-d00224-A: glossary -----------------------------------------------

    def test_REQ_d00224_A_glossary_alphabetical_headings(self) -> None:
        """Glossary has letter headings in alphabetical order."""
        generate_glossary, _, _ = _import_generators()
        td = _build_test_dictionary()
        output = generate_glossary(td)
        e_pos = output.index("## E")
        l_pos = output.index("## L")
        q_pos = output.index("## Q")
        assert e_pos < l_pos < q_pos

    def test_REQ_d00224_A_glossary_has_definitions(self) -> None:
        """Glossary contains definition text for each term."""
        generate_glossary, _, _ = _import_generators()
        td = _build_test_dictionary()
        output = generate_glossary(td)
        assert "stored in digital form" in output
        assert "classification tier" in output
        assert "structured set of questions" in output

    def test_REQ_d00224_A_glossary_non_indexed_annotation(self) -> None:
        """Non-indexed terms are annotated with (not indexed)."""
        generate_glossary, _, _ = _import_generators()
        td = _build_test_dictionary()
        output = generate_glossary(td)
        # Level should have (not indexed) nearby
        level_section = output[output.index("**Level**"):]
        assert "(not indexed)" in level_section.split("\n## ")[0]

    def test_REQ_d00224_A_glossary_collection_annotation(self) -> None:
        """Collection terms are annotated with (collection)."""
        generate_glossary, _, _ = _import_generators()
        td = _build_test_dictionary()
        output = generate_glossary(td)
        q_section = output[output.index("**Questionnaire**"):]
        assert "(collection)" in q_section.split("\n## ")[0]

    # -- REQ-d00224-B: term index ---------------------------------------------

    def test_REQ_d00224_B_term_index_only_indexed(self) -> None:
        """Term index includes only indexed terms (not Level)."""
        _, generate_term_index, _ = _import_generators()
        td = _build_test_dictionary()
        output = generate_term_index(td)
        assert "Electronic Record" in output
        assert "Questionnaire" in output
        assert "Level" not in output

    def test_REQ_d00224_B_term_index_namespace_grouping(self) -> None:
        """Term index groups references by namespace."""
        _, generate_term_index, _ = _import_generators()
        td = _build_test_dictionary()
        output = generate_term_index(td)
        assert "**main:**" in output
        assert "**sponsor-a:**" in output

    # -- REQ-d00224-C: collection manifests ------------------------------------

    def test_REQ_d00224_C_collection_manifest(self) -> None:
        """Collection manifest produces standalone listing for a collection term."""
        _, _, generate_collection_manifest = _import_generators()
        td = _build_test_dictionary()
        entry = td.lookup("Questionnaire")
        assert entry is not None
        output = generate_collection_manifest(entry)
        assert "Questionnaire" in output
        assert "REQ-p00012" in output

    # -- REQ-d00224-D: header and format support --------------------------------

    def test_REQ_d00224_D_auto_generated_header(self) -> None:
        """Glossary output starts with an auto-generated comment."""
        generate_glossary, _, _ = _import_generators()
        td = _build_test_dictionary()
        output = generate_glossary(td)
        first_line = output.lstrip().split("\n")[0]
        assert "auto" in first_line.lower() or "generated" in first_line.lower()

    def test_REQ_d00224_D_json_format(self) -> None:
        """generate_glossary with format='json' produces valid JSON."""
        generate_glossary, _, _ = _import_generators()
        td = _build_test_dictionary()
        output = generate_glossary(td, format="json")
        data = json.loads(output)  # raises if invalid
        assert isinstance(data, (dict, list))
