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
                section.get("content", "")  # verify field exists
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
        assert (
            def_data.get("term") == "Electronic Record"
        ), f"Expected term='Electronic Record', got {def_data.get('term')!r}"
        assert "combination" in def_data.get(
            "definition", ""
        ), f"Expected definition containing 'combination', got {def_data.get('definition')!r}"

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
        assert (
            def_data.get("collection") is True
        ), f"Expected collection=True, got {def_data.get('collection')!r}"

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
        assert (
            def_data.get("indexed") is False
        ), f"Expected indexed=False, got {def_data.get('indexed')!r}"

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
        assert (
            "combination" in definition_text
        ), f"Expected 'combination' in definition, got {definition_text!r}"
        assert (
            "regulatory" in definition_text
        ), f"Expected 'regulatory' in definition (multiline join), got {definition_text!r}"

    # -- REQ-d00221-A: hanging-indent continuation line support ----------------

    def test_REQ_d00221_A_indented_continuation(self, resolver):
        """Def block with 2-space continuation lines joins all 3 lines with \\n."""
        content = """\
# REQ-p00001: Requirement With Continuation
**Level**: prd | **Status**: Active

Electronic Record
: Any combination of text, graphics, data, audio, or pictorial
  information stored in digital form. Used for regulatory
  compliance tracking and audit support.

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
        definition = def_data.get("definition", "")
        # All three lines must appear in the joined definition text.
        assert "combination" in definition
        assert "information stored" in definition
        assert "compliance tracking" in definition
        # Continuation indent must have been stripped (no leading double-space).
        lines = definition.split("\n")
        assert len(lines) >= 3, f"Expected >=3 lines in definition, got {lines!r}"
        for ln in lines[1:]:
            assert not ln.startswith("  "), f"Continuation line still has hanging indent: {ln!r}"

    def test_REQ_d00221_A_mixed_colon_and_continuation(self, resolver):
        """Continuation line attaches only to the preceding DEF_LINE, not the next."""
        content = """\
# REQ-p00001: Requirement With Mixed
**Level**: prd | **Status**: Active

Email Address
: A unique technical identifier used as a destination for system notifications
  and as a primary User ID for authentication.
: Reference Term: __Registered Notification Address__

## Assertions

A. First assertion

*End* *REQ-p00001* **Hash**: abcd1234
"""
        results = _parse(content, resolver)
        def_blocks = [r for r in results if r.content_type == "definition_block"]
        # Also check inside requirement parsed_data
        req_defs: list = []
        for r in results:
            if r.content_type == "requirement":
                req_defs = r.parsed_data.get("definitions", [])

        all_def_data = [r.parsed_data for r in def_blocks] + list(req_defs)
        assert (
            len(all_def_data) == 1
        ), f"Expected exactly one definition_block, got {len(all_def_data)}"

        def_data = all_def_data[0]
        assert (
            def_data.get("term") == "Email Address"
        ), f"Expected term='Email Address', got {def_data.get('term')!r}"
        definition = def_data.get("definition", "")
        assert "unique technical identifier" in definition
        assert "primary User ID for authentication" in definition
        # Reference Term must be parsed cleanly, not polluted with continuation text.
        ref_term = def_data.get("reference_term", "")
        assert ref_term == "Registered Notification Address", (
            f"Expected reference_term='Registered Notification Address', " f"got {ref_term!r}"
        )

    def test_REQ_d00221_A_reference_type_with_structured_fields(self, resolver):
        """Reference entry with Title/Version/URL metadata lines and no prose."""
        content = """\
# REQ-p00001: Requirement With Reference
**Level**: prd | **Status**: Active

ISO/IEC 24760-1
: Reference
: Title: IT Security and Privacy
: Version: ISO/IEC 24760-1:2019
: URL: <https://www.iso.org>

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
        assert (
            def_data.get("is_reference") is True
        ), f"Expected is_reference=True, got {def_data.get('is_reference')!r}"
        ref_fields = def_data.get("reference_fields") or {}
        assert (
            ref_fields.get("title") == "IT Security and Privacy"
        ), f"Expected title='IT Security and Privacy', got {ref_fields.get('title')!r}"
        assert (
            ref_fields.get("version") == "ISO/IEC 24760-1:2019"
        ), f"Expected version='ISO/IEC 24760-1:2019', got {ref_fields.get('version')!r}"
        assert (
            ref_fields.get("url") == "https://www.iso.org"
        ), f"Expected url='https://www.iso.org', got {ref_fields.get('url')!r}"
        # No prose definition -- only metadata.
        assert (
            def_data.get("definition", "") == ""
        ), f"Expected empty definition, got {def_data.get('definition')!r}"

    def test_REQ_d00221_A_continuation_on_metadata_line(self, resolver):
        """Continuation line after a '<key>: <val>' metadata line joins into the value."""
        content = """\
# REQ-p00001: Requirement With Metadata Continuation
**Level**: prd | **Status**: Active

Some Term
: Title: A long title
  that continues on the next line

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
        title = (def_data.get("reference_fields") or {}).get("title", "")
        assert "A long title" in title, f"Expected 'A long title' in title, got {title!r}"
        assert (
            "continues on the next line" in title
        ), f"Expected continuation text in title, got {title!r}"

    # -- format_definition_block renderer --------------------------------------

    def test_format_definition_block_multiline_prose(self):
        """Multi-line prose renders with ': ' on first line, 2-space hanging indent."""
        from elspais.graph.render import format_definition_block

        data = {
            "term": "Electronic Record",
            "definition": "first\nsecond\nthird",
        }
        out = format_definition_block(data)
        # Canonical shape: term line, then ': first', then '  second', '  third'.
        assert (
            "\n: first\n  second\n  third" in out
        ), f"Expected hanging-indent shape in output, got {out!r}"
        # Term must appear as its own (first) line.
        assert out.startswith(
            "Electronic Record\n"
        ), f"Expected output to start with term line, got {out!r}"

    def test_format_definition_block_reference_fields(self):
        """Reference entry renders ': Reference' + ': Title: ...' + ': URL: <...>' lines."""
        from elspais.graph.render import format_definition_block

        data = {
            "term": "ISO/IEC 24760-1",
            "definition": "",
            "is_reference": True,
            "reference_fields": {
                "title": "IT Security and Privacy",
                "version": "ISO/IEC 24760-1:2019",
                "url": "https://www.iso.org",
            },
        }
        out = format_definition_block(data)
        lines = out.split("\n")
        assert ": Reference" in lines, f"Expected ': Reference' line in output, got {out!r}"
        assert (
            ": Title: IT Security and Privacy" in lines
        ), f"Expected title line in output, got {out!r}"
        assert (
            ": Version: ISO/IEC 24760-1:2019" in lines
        ), f"Expected version line in output, got {out!r}"
        assert (
            ": URL: <https://www.iso.org>" in lines
        ), f"Expected URL line with angle brackets in output, got {out!r}"
