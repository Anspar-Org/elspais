"""Tests for JourneyParser - Priority 60 user journey parser.

Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
linking including validates.
"""

from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.journey import JourneyParser
from elspais.utilities.patterns import FederatedIdReader
from tests.core.graph_test_helpers import grammar_for


def _parser() -> JourneyParser:
    """A parser reading the shipped default identifier grammar.

    Dividing a ``Validates:`` line into its references is the identifier
    reader's job, so the parser cannot be built without one.
    """
    return JourneyParser(FederatedIdReader(grammar_for()))


class TestJourneyParserPriority:
    """Tests for JourneyParser priority."""

    # Verifies: REQ-d00128-G
    def test_priority_is_60(self):
        parser = _parser()
        assert parser.priority == 60


class TestJourneyParserBasic:
    """Tests for basic journey parsing."""

    # Verifies: REQ-o00050-C
    def test_claims_simple_journey(self):
        parser = _parser()
        lines = [
            (1, "## JNY-Spec-Author-01: Creating Requirements"),
            (2, ""),
            (3, "**Actor**: Spec Author"),
            (4, "**Goal**: Create new requirements"),
            (5, ""),
            (6, "### Steps"),
            (7, "1. Open spec file"),
            (8, "2. Add requirement header"),
            (9, "3. Save file"),
            (10, ""),
            (11, "*End* *JNY-Spec-Author-01*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "journey"
        assert results[0].parsed_data["id"] == "JNY-Spec-Author-01"
        assert results[0].parsed_data["actor"] == "Spec Author"

    # Verifies: REQ-o00050-C
    def test_no_journeys_returns_empty(self):
        parser = _parser()
        lines = [
            (1, "# Regular Header"),
            (2, "Regular text."),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0


class TestJourneyParserValidates:
    """Tests for JourneyParser Validates: field parsing.

    Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
    linking including validates.
    """

    # Verifies: REQ-o00050-C
    def test_REQ_o00050_C_validates_multiple_refs(self):
        """Journey with Validates: REQ-p00012, REQ-d00042 parses both refs."""
        parser = _parser()
        lines = [
            (1, "## JNY-Dev-01: Development Workflow"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Implement a feature"),
            (5, "Validates: REQ-p00012, REQ-d00042"),
            (6, ""),
            (7, "### Steps"),
            (8, "1. Read requirements"),
            (9, "2. Write code"),
            (10, ""),
            (11, "*End* *JNY-Dev-01*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        validates = results[0].parsed_data["validates"]
        assert len(validates) == 2
        assert "REQ-p00012" in validates
        assert "REQ-d00042" in validates

    # Verifies: REQ-o00050-C
    def test_REQ_o00050_C_no_validates_line_empty_list(self):
        """Journey without Validates: line has empty validates list."""
        parser = _parser()
        lines = [
            (1, "## JNY-Dev-02: Simple Journey"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Do something"),
            (5, ""),
            (6, "### Steps"),
            (7, "1. Step one"),
            (8, ""),
            (9, "*End* *JNY-Dev-02*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        validates = results[0].parsed_data["validates"]
        assert validates == []

    # Verifies: REQ-o00050-C
    def test_REQ_o00050_C_single_validates(self):
        """Journey with single Validates: REQ-p00012 parses one ref."""
        parser = _parser()
        lines = [
            (1, "## JNY-Dev-03: Single Validates Journey"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Implement feature"),
            (5, "Validates: REQ-p00012"),
            (6, ""),
            (7, "### Steps"),
            (8, "1. Do work"),
            (9, ""),
            (10, "*End* *JNY-Dev-03*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        validates = results[0].parsed_data["validates"]
        assert len(validates) == 1
        assert validates[0] == "REQ-p00012"

    # Verifies: REQ-o00050-C
    def test_REQ_o00050_C_validates_whitespace_padded(self):
        """Journey with whitespace-padded refs in Validates: line."""
        parser = _parser()
        lines = [
            (1, "## JNY-Dev-04: Whitespace Journey"),
            (2, ""),
            (3, "**Actor**: Developer"),
            (4, "**Goal**: Test whitespace"),
            (5, "Validates:   REQ-p00012 ,  REQ-d00042  , REQ-o00005  "),
            (6, ""),
            (7, "### Steps"),
            (8, "1. Verify parsing"),
            (9, ""),
            (10, "*End* *JNY-Dev-04*"),
        ]
        ctx = ParseContext(file_path="spec/journeys.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        validates = results[0].parsed_data["validates"]
        assert len(validates) == 3
        assert "REQ-p00012" in validates
        assert "REQ-d00042" in validates
        assert "REQ-o00005" in validates
        # Verify no leading/trailing whitespace on parsed refs
        for val in validates:
            assert val == val.strip()


# Verifies: REQ-o00050-C
def test_journey_parser_REQ_validates_field():
    """JourneyParser extracts Validates: field into parsed_data['validates'].

    Validates REQ-d00069-A: journey parser supports validates field.
    """
    parser = _parser()
    lines_text = """\
## JNY-TST-001: Test Journey
**Actor**: Tester
**Goal**: Verify something
Validates: REQ-p00001, REQ-p00002
*End* *JNY-TST-001*
"""
    lines = [(i + 1, line) for i, line in enumerate(lines_text.splitlines())]
    results = list(parser.claim_and_parse(lines, context=None))
    assert len(results) == 1
    data = results[0].parsed_data
    assert "validates" in data
    assert "addresses" not in data
    assert data["validates"] == ["REQ-p00001", "REQ-p00002"]


# ---------------------------------------------------------------------------
# What the author wrote where the validation targets go.
#
# A journey that declared nothing and one whose declaration named nothing
# this estate holds both end with an empty ``validates`` list, and only
# ``validates_declared`` says which happened (REQ-d00288-C). A target
# declared as not yet chosen is a third state again, and it is carried
# verbatim so a reader learns the journey is waiting rather than broken
# (REQ-d00288-D).
# ---------------------------------------------------------------------------

_JOURNEY_LINES = """\
## JNY-TST-100: Waiting Journey
**Actor**: Tester
**Goal**: Verify something
{validates}*End* *JNY-TST-100*
"""


def _journey_data(validates_line: str | None):
    """The parsed data for a journey carrying *validates_line*, or none."""
    text = _JOURNEY_LINES.format(
        validates=f"{validates_line}\n" if validates_line is not None else ""
    )
    lines = [(i + 1, line) for i, line in enumerate(text.splitlines())]
    results = list(_parser().claim_and_parse(lines, context=None))
    assert len(results) == 1
    return results[0].parsed_data


# Verifies: REQ-d00288-C
def test_a_journey_with_no_validates_line_records_that_none_was_written():
    data = _journey_data(None)

    assert data["validates"] == []
    assert data["validates_declared"] is False, (
        "an absent line and a line naming nothing produce the same empty "
        "reference list; only this distinguishes them"
    )
    assert data["validates_placeholders"] == []


# Verifies: REQ-d00288-C
def test_a_journey_whose_declaration_names_nothing_records_that_one_was_written():
    """``REQ-p09999`` reads as an identifier and names no requirement, so the
    journey validates nothing -- but its author did write the line, which is
    a different authoring defect from having written none."""
    data = _journey_data("Validates: REQ-p09999")

    assert data["validates_declared"] is True
    assert data["validates_placeholders"] == []


# Verifies: REQ-d00288-D, REQ-d00287-I
def test_a_journey_declaring_a_placeholder_carries_it_verbatim():
    """The placeholder contributes no reference -- there is nothing to
    validate yet -- and survives as written, which is what lets the report
    say the journey is awaiting its requirement rather than missing one."""
    data = _journey_data("Validates: <TBD>")

    assert data["validates"] == []
    assert data["validates_declared"] is True
    assert data["validates_placeholders"] == ["<TBD>"]


# Verifies: REQ-d00288-D
def test_a_placeholder_beside_a_real_target_leaves_the_target_validating():
    data = _journey_data("Validates: REQ-p00001, <the second one>")

    assert data["validates"] == ["REQ-p00001"]
    assert data["validates_placeholders"] == ["<the second one>"]


# Verifies: REQ-d00288-C
def test_a_journey_whose_targets_resolve_declares_no_placeholder():
    data = _journey_data("Validates: REQ-p00001, REQ-p00002")

    assert data["validates"] == ["REQ-p00001", "REQ-p00002"]
    assert data["validates_declared"] is True
    assert data["validates_placeholders"] == []
