# Verifies: REQ-d00221-A+B
"""Tests for definition block grammar and transformer support.

Validates REQ-d00221-A+B:

These tests verify that the Lark grammar recognizes definition blocks
(Markdown definition list syntax) and the transformer extracts structured
data (term, definition text, Collection/Indexed flags).

Tests are expected to FAIL until grammar and transformer support is added.
"""

from __future__ import annotations

import pytest

from elspais.graph.parsers.lark import GrammarFactory
from elspais.graph.parsers.lark.transformers.requirement import RequirementTransformer
from elspais.utilities.patterns import IdPatternConfig, IdResolver


@pytest.fixture
def resolver():
    """IdResolver for standard HHT-like pattern."""
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase", "max_count": 26},
            },
        }
    )
    return IdResolver(config)


def _parse(content: str, resolver: IdResolver) -> list:
    """Parse spec content with Lark pipeline, return all ParsedContent."""
    factory = GrammarFactory(resolver)
    lark_parser = factory.get_requirement_parser()
    transformer = RequirementTransformer(resolver)
    if not content.endswith("\n"):
        content += "\n"
    tree = lark_parser.parse(content)
    return transformer.transform(tree, source=content)


class TestDefinitionGrammar:
    """Validates REQ-d00221-A+B: definition block grammar and transformer."""

    def test_REQ_d00221_A_definition_between_requirements(self, resolver):
        """Definition block between two requirements produces definition_block content."""
        content = """\
# REQ-p00001: First Requirement
**Level**: prd | **Status**: Active

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234

Electronic Record
: Any combination of text, graphics, data, audio, or pictorial
  information stored in digital form.

# REQ-p00002: Second Requirement
**Level**: prd | **Status**: Active

A. Second assertion

*End* *REQ-p00002* **Hash**: efgh5678
"""
        results = _parse(content, resolver)
        def_blocks = [r for r in results if r.content_type == "definition_block"]
        assert len(def_blocks) >= 1, (
            f"Expected at least one definition_block, got content_types: "
            f"{[r.content_type for r in results]}"
        )

    def test_REQ_d00221_A_definition_in_requirement_preamble(self, resolver):
        """Definition block in requirement body (preamble) is recognized."""
        content = """\
# REQ-p00001: Requirement With Definitions
**Level**: prd | **Status**: Active

The following terms apply:

Questionnaire
: A structured set of questions administered to a participant.

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        # The requirement should have a definition_block in its parsed_data
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        req_data = reqs[0].parsed_data

        # Check for definition data in sections or a dedicated field
        has_definition = False
        # Option 1: definitions as a top-level field
        if "definitions" in req_data:
            has_definition = len(req_data["definitions"]) > 0
        # Option 2: definition_block content type at file level
        def_blocks = [r for r in results if r.content_type == "definition_block"]
        if def_blocks:
            has_definition = True
        # Option 3: definition in sections
        for section in req_data.get("sections", []):
            if "definition" in section.get("heading", "").lower():
                has_definition = True

        assert has_definition, (
            f"Expected definition block in preamble, got sections: "
            f"{[s.get('heading') for s in req_data.get('sections', [])]}, "
            f"content_types: {[r.content_type for r in results]}"
        )

    def test_REQ_d00221_A_definition_in_named_block(self, resolver):
        """Definition block inside a ## Rationale section is recognized."""
        content = """\
# REQ-p00001: Requirement With Section Definitions
**Level**: prd | **Status**: Active

## Rationale

Key terms:

Level
: The classification tier of a requirement (PRD, OPS, DEV).

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        req_data = reqs[0].parsed_data

        # The Rationale section should contain definition block data
        has_definition = False
        if "definitions" in req_data:
            has_definition = len(req_data["definitions"]) > 0
        def_blocks = [r for r in results if r.content_type == "definition_block"]
        if def_blocks:
            has_definition = True
        for section in req_data.get("sections", []):
            if section.get("heading") == "Rationale":
                content_text = section.get("content", "")
                # If definitions were extracted, content should reference them
                if "definition" in str(section).lower():
                    has_definition = True

        assert has_definition, (
            f"Expected definition block in Rationale section, "
            f"content_types: {[r.content_type for r in results]}"
        )

    def test_REQ_d00221_A_definition_not_in_assertions(self, resolver):
        """Colon-prefixed text inside assertions must NOT produce definition_block."""
        content = """\
# REQ-p00001: Requirement With Colon In Assertions
**Level**: prd | **Status**: Active

## Assertions

A. The system shall support these levels:
   PRD, OPS, DEV.

B. Each level has a rank value.

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_blocks = [r for r in results if r.content_type == "definition_block"]
        assert len(def_blocks) == 0, (
            f"definition_block should NOT appear inside assertion blocks, "
            f"but found {len(def_blocks)}"
        )

        # Verify assertions parsed correctly
        reqs = [r for r in results if r.content_type == "requirement"]
        assert len(reqs) == 1
        assertions = reqs[0].parsed_data.get("assertions", [])
        assert len(assertions) == 2, f"Expected 2 assertions, got {len(assertions)}"

    def test_REQ_d00221_B_extracts_term_and_definition(self, resolver):
        """Transformer extracts term name and definition text from definition_block."""
        content = """\
# REQ-p00001: Requirement With Definition
**Level**: prd | **Status**: Active

Electronic Record
: Any combination of text, graphics, data, audio, or pictorial
  information stored in digital form.

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        # Find definition block data
        def_data = None
        for r in results:
            if r.content_type == "definition_block":
                def_data = r.parsed_data
                break
        # Also check inside requirement parsed_data
        for r in results:
            if r.content_type == "requirement" and "definitions" in r.parsed_data:
                defs = r.parsed_data["definitions"]
                if defs:
                    def_data = defs[0]
                    break

        assert def_data is not None, (
            f"No definition_block data found. content_types: "
            f"{[r.content_type for r in results]}"
        )
        assert def_data.get("term") == "Electronic Record", (
            f"Expected term='Electronic Record', got {def_data.get('term')!r}"
        )
        assert "combination" in def_data.get("definition", ""), (
            f"Expected definition containing 'combination', got {def_data.get('definition')!r}"
        )

    def test_REQ_d00221_B_collection_flag(self, resolver):
        """Definition with ': Collection: true' has collection=True in parsed_data."""
        content = """\
# REQ-p00001: Requirement With Collection Definition
**Level**: prd | **Status**: Active

Questionnaire
: A structured set of questions administered to a participant.
: Collection: true

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_data = None
        for r in results:
            if r.content_type == "definition_block":
                def_data = r.parsed_data
                break
        for r in results:
            if r.content_type == "requirement" and "definitions" in r.parsed_data:
                defs = r.parsed_data["definitions"]
                if defs:
                    def_data = defs[0]
                    break

        assert def_data is not None, (
            f"No definition_block data found. content_types: "
            f"{[r.content_type for r in results]}"
        )
        assert def_data.get("collection") is True, (
            f"Expected collection=True, got {def_data.get('collection')!r}"
        )

    def test_REQ_d00221_B_indexed_flag(self, resolver):
        """Definition with ': Indexed: false' has indexed=False in parsed_data."""
        content = """\
# REQ-p00001: Requirement With Indexed Definition
**Level**: prd | **Status**: Active

Level
: The classification tier of a requirement (PRD, OPS, DEV).
: Indexed: false

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_data = None
        for r in results:
            if r.content_type == "definition_block":
                def_data = r.parsed_data
                break
        for r in results:
            if r.content_type == "requirement" and "definitions" in r.parsed_data:
                defs = r.parsed_data["definitions"]
                if defs:
                    def_data = defs[0]
                    break

        assert def_data is not None, (
            f"No definition_block data found. content_types: "
            f"{[r.content_type for r in results]}"
        )
        assert def_data.get("indexed") is False, (
            f"Expected indexed=False, got {def_data.get('indexed')!r}"
        )

    def test_REQ_d00221_B_multiline_definition(self, resolver):
        """Definition with multiple ': ' lines has joined definition text."""
        content = """\
# REQ-p00001: Requirement With Multiline Definition
**Level**: prd | **Status**: Active

Electronic Record
: Any combination of text, graphics, data, audio,
: or pictorial information stored in digital form.
: Used for regulatory compliance tracking.

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_data = None
        for r in results:
            if r.content_type == "definition_block":
                def_data = r.parsed_data
                break
        for r in results:
            if r.content_type == "requirement" and "definitions" in r.parsed_data:
                defs = r.parsed_data["definitions"]
                if defs:
                    def_data = defs[0]
                    break

        assert def_data is not None, (
            f"No definition_block data found. content_types: "
            f"{[r.content_type for r in results]}"
        )
        definition_text = def_data.get("definition", "")
        assert "combination" in definition_text, (
            f"Expected 'combination' in definition, got {definition_text!r}"
        )
        assert "regulatory" in definition_text, (
            f"Expected 'regulatory' in definition (multiline join), got {definition_text!r}"
        )
