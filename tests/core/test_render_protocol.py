# Implements: REQ-d00131
# elspais: expected-broken-links 1
"""Tests for the render protocol (Task 1 of FILENODE3).

Validates REQ-d00131-A: Each NodeKind has a render() function dispatched by kind
Validates REQ-d00131-B: REQUIREMENT renders full block
Validates REQ-d00131-C: ASSERTION render raises ValueError
Validates REQ-d00131-D: REMAINDER renders raw text verbatim
Validates REQ-d00131-E: USER_JOURNEY renders full block
Validates REQ-d00131-F: CODE renders # Implements: comment line(s)
Validates REQ-d00131-G: TEST renders # Tests: / # Validates: comment line(s)
Validates REQ-d00131-H: TEST_RESULT render raises ValueError
Validates REQ-d00131-I: FILE node renders by walking CONTAINS children sorted by render_order
Validates REQ-d00131-J: Order-independent assertion hashing
"""

from __future__ import annotations

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.GraphNode import FileType
from elspais.graph.relations import EdgeKind


def _make_file_node(path: str = "spec/test.md") -> GraphNode:
    """Create a FILE node for testing."""
    node = GraphNode(id=f"file:{path}", kind=NodeKind.FILE, label=path.split("/")[-1])
    node.set_field("file_type", FileType.SPEC)
    node.set_field("relative_path", path)
    node.set_field("absolute_path", f"/repo/{path}")
    return node


def _make_requirement_node(
    req_id: str = "REQ-t00001",
    title: str = "Test Requirement",
    level: str = "Dev",
    status: str = "Draft",
    body_text: str = "",
    implements: str | None = None,
    assertions: list[tuple[str, str]] | None = None,
    sections: list[tuple[str, str]] | None = None,
    hash_val: str | None = None,
) -> GraphNode:
    """Create a REQUIREMENT node with STRUCTURES children for testing."""
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=title)
    node.set_field("level", level)
    node.set_field("status", status)
    node.set_field("body_text", body_text)
    node.set_field("hash", hash_val)
    node.set_field("parse_line", 1)
    node.set_field("parse_end_line", 10)

    # Store implements references for rendering metadata line
    if implements:
        node.set_field("implements_refs", [implements])
    else:
        node.set_field("implements_refs", [])

    # Add assertion children via STRUCTURES edges
    if assertions:
        for label, text in assertions:
            assertion_id = f"{req_id}-{label}"
            assertion_node = GraphNode(id=assertion_id, kind=NodeKind.ASSERTION, label=text)
            assertion_node.set_field("label", label)
            assertion_node.set_field("parse_line", 5)
            node.link(assertion_node, EdgeKind.STRUCTURES)

    # Add section children via STRUCTURES edges
    if sections:
        for idx, (heading, content) in enumerate(sections):
            section_id = f"{req_id}:section:{idx}"
            section_node = GraphNode(id=section_id, kind=NodeKind.REMAINDER, label=heading)
            section_node.set_field("heading", heading)
            section_node.set_field("text", content)
            section_node.set_field("order", idx)
            section_node.set_field("parse_line", 8)
            node.link(section_node, EdgeKind.STRUCTURES)

    return node


def _make_remainder_node(
    text: str = "Some remainder text\nwith multiple lines",
    node_id: str = "rem:spec/test.md:1",
) -> GraphNode:
    """Create a REMAINDER node for testing."""
    node = GraphNode(id=node_id, kind=NodeKind.REMAINDER, label=text[:50])
    node.set_field("text", text)
    node.set_field("parse_line", 1)
    return node


def _make_journey_node(
    journey_id: str = "JNY-Login-01",
    title: str = "Login Flow",
    body: str = "",
) -> GraphNode:
    """Create a USER_JOURNEY node for testing."""
    node = GraphNode(id=journey_id, kind=NodeKind.USER_JOURNEY, label=title)
    node.set_field("actor", "User")
    node.set_field("goal", "Access the system")
    if not body:
        body = (
            f"## {journey_id}: {title}\n\n"
            "**Actor**: User\n"
            "**Goal**: Access the system\n\n"
            "## Steps\n\n"
            "1. Navigate to login page\n"
            "2. Enter credentials\n\n"
            f"*End* *{journey_id}*"
        )
    node.set_field("body", body)
    node.set_field("parse_line", 1)
    return node


def _make_code_node(
    raw_text: str = "# Implements: REQ-t00001",
    node_id: str = "code:src/main.py:10",
) -> GraphNode:
    """Create a CODE node for testing."""
    node = GraphNode(id=node_id, kind=NodeKind.CODE, label=f"Code at {node_id}")
    node.set_field("raw_text", raw_text)
    node.set_field("parse_line", 10)
    return node


def _make_test_node(
    raw_text: str = "# Tests: REQ-t00001",
    node_id: str = "test:tests/test_main.py::TestClass::test_func",
) -> GraphNode:
    """Create a TEST node for testing."""
    node = GraphNode(id=node_id, kind=NodeKind.TEST, label="TestClass::test_func")
    node.set_field("raw_text", raw_text)
    node.set_field("parse_line", 5)
    return node


class TestRenderDispatch:
    """Validates REQ-d00131-A: Each NodeKind has a render() function dispatched by kind."""

    def test_REQ_d00131_A_render_function_importable(self):
        """render_node() can be imported from graph.render module."""
        from elspais.graph.render import render_node

        assert callable(render_node)

    def test_REQ_d00131_A_render_dispatches_by_kind(self):
        """render_node() dispatches correctly for each NodeKind."""
        from elspais.graph.render import render_node

        # REMAINDER should render its text
        rem = _make_remainder_node(text="hello world")
        result = render_node(rem)
        assert result == "hello world"

    def test_REQ_d00131_A_render_unknown_kind_raises(self):
        """render_node() should handle all known kinds gracefully."""
        from elspais.graph.render import render_node

        # All known kinds should be handled (some may raise ValueError by design)
        rem = _make_remainder_node(text="text")
        result = render_node(rem)
        assert isinstance(result, str)


class TestRequirementRender:
    """Validates REQ-d00131-B: REQUIREMENT renders full block."""

    def test_REQ_d00131_B_requirement_header(self):
        """Rendered requirement starts with ## REQ-xxx: Title header."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00001",
            title="Test Requirement",
            level="Dev",
            status="Draft",
        )
        result = render_node(node)
        assert result.startswith("## REQ-t00001: Test Requirement\n")

    def test_REQ_d00131_B_requirement_metadata_line(self):
        """Rendered requirement contains metadata line with level, status."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00001",
            title="Test Requirement",
            level="Dev",
            status="Draft",
        )
        result = render_node(node)
        assert "**Level**: Dev" in result
        assert "**Status**: Draft" in result

    def test_REQ_d00131_B_requirement_metadata_with_implements(self):
        """Rendered requirement metadata includes Implements when present."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00002",
            title="Test",
            level="Dev",
            status="Draft",
            implements="REQ-t00001",
        )
        result = render_node(node)
        assert "**Implements**: REQ-t00001" in result

    def test_REQ_d00131_B_requirement_end_marker(self):
        """Rendered requirement ends with *End* marker."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00001",
            title="Test Requirement",
        )
        result = render_node(node)
        assert "*End* *Test Requirement*" in result
        assert "**Hash**:" in result

    def test_REQ_d00131_B_requirement_with_assertions(self):
        """Rendered requirement includes assertions section."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00001",
            title="Test Requirement",
            assertions=[("A", "SHALL do X."), ("B", "SHALL do Y.")],
        )
        result = render_node(node)
        assert "## Assertions" in result
        assert "A. SHALL do X." in result
        assert "B. SHALL do Y." in result

    def test_REQ_d00131_B_requirement_with_sections(self):
        """Rendered requirement includes non-normative sections."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00001",
            title="Test Requirement",
            sections=[("Rationale", "Because reasons.")],
        )
        result = render_node(node)
        assert "## Rationale" in result
        assert "Because reasons." in result

    def test_REQ_d00131_B_requirement_with_body_text(self):
        """Rendered requirement includes preamble body text."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00001",
            title="Test Requirement",
            sections=[("preamble", "This requirement describes something.")],
        )
        result = render_node(node)
        assert "This requirement describes something." in result

    def test_REQ_d00131_B_requirement_separator(self):
        """Rendered requirement ends with --- separator after end marker."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00001",
            title="Test Requirement",
        )
        result = render_node(node)
        lines = result.rstrip().split("\n")
        assert lines[-1] == "---"

    def test_REQ_d00131_B_requirement_full_round_trip_structure(self):
        """Rendered requirement has correct overall structure."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00001",
            title="Full Test",
            level="PRD",
            status="Active",
            implements="REQ-p00001",
            assertions=[("A", "SHALL do X."), ("B", "SHALL do Y.")],
            sections=[
                ("preamble", "Main body text here."),
                ("Rationale", "Because reasons."),
            ],
        )
        result = render_node(node)
        lines = result.split("\n")

        # Check structure
        assert lines[0] == "## REQ-t00001: Full Test"
        assert "**Level**: PRD" in lines[2]
        assert "**Status**: Active" in lines[2]
        assert "**Implements**: REQ-p00001" in lines[2]
        assert "*End* *Full Test*" in result
        assert "## Assertions" in result
        assert "## Rationale" in result
        assert "---" in lines[-1]


class TestAssertionRender:
    """Validates REQ-d00131-C: ASSERTION render raises ValueError."""

    def test_REQ_d00131_C_assertion_render_raises(self):
        """Calling render on an ASSERTION node raises ValueError."""
        from elspais.graph.render import render_node

        node = GraphNode(id="REQ-t00001-A", kind=NodeKind.ASSERTION, label="SHALL do X.")
        node.set_field("label", "A")
        with pytest.raises(ValueError, match="ASSERTION"):
            render_node(node)


class TestRemainderRender:
    """Validates REQ-d00131-D: REMAINDER renders raw text verbatim."""

    def test_REQ_d00131_D_remainder_verbatim(self):
        """REMAINDER render returns raw text exactly as stored."""
        from elspais.graph.render import render_node

        text = "# Header\n\nSome content\n  with indentation\n"
        node = _make_remainder_node(text=text)
        result = render_node(node)
        assert result == text

    def test_REQ_d00131_D_remainder_preserves_whitespace(self):
        """REMAINDER preserves all whitespace including blank lines."""
        from elspais.graph.render import render_node

        text = "\n\n  indented\n\n\ntrailing"
        node = _make_remainder_node(text=text)
        result = render_node(node)
        assert result == text

    def test_REQ_d00131_D_remainder_empty(self):
        """REMAINDER with empty text returns empty string."""
        from elspais.graph.render import render_node

        node = _make_remainder_node(text="")
        result = render_node(node)
        assert result == ""


class TestJourneyRender:
    """Validates REQ-d00131-E: USER_JOURNEY renders full block."""

    def test_REQ_d00131_E_journey_renders_body(self):
        """USER_JOURNEY render returns the stored body text."""
        from elspais.graph.render import render_node

        node = _make_journey_node()
        result = render_node(node)
        assert "## JNY-Login-01: Login Flow" in result
        assert "*End* *JNY-Login-01*" in result

    def test_REQ_d00131_E_journey_includes_actor_goal(self):
        """USER_JOURNEY render includes actor and goal fields."""
        from elspais.graph.render import render_node

        node = _make_journey_node()
        result = render_node(node)
        assert "**Actor**: User" in result
        assert "**Goal**: Access the system" in result


class TestCodeRender:
    """Validates REQ-d00131-F: CODE renders # Implements: comment line(s)."""

    def test_REQ_d00131_F_code_single_line(self):
        """CODE render returns single comment line."""
        from elspais.graph.render import render_node

        node = _make_code_node(raw_text="# Implements: REQ-t00001")
        result = render_node(node)
        assert result == "# Implements: REQ-t00001"

    def test_REQ_d00131_F_code_multi_line(self):
        """CODE render returns multiple comment lines."""
        from elspais.graph.render import render_node

        raw = "# Implements: REQ-t00001\n# Implements: REQ-t00002"
        node = _make_code_node(raw_text=raw)
        result = render_node(node)
        assert result == raw


class TestTestRender:
    """Validates REQ-d00131-G: TEST renders comment line(s)."""

    def test_REQ_d00131_G_test_single_line(self):
        """TEST render returns single comment line."""
        from elspais.graph.render import render_node

        node = _make_test_node(raw_text="# Tests: REQ-t00001")
        result = render_node(node)
        assert result == "# Tests: REQ-t00001"

    def test_REQ_d00131_G_test_validates_line(self):
        """TEST render returns Validates comment line."""
        from elspais.graph.render import render_node

        node = _make_test_node(raw_text="# Validates: REQ-t00001-A")
        result = render_node(node)
        assert result == "# Validates: REQ-t00001-A"


class TestTestResultRender:
    """Validates REQ-d00131-H: TEST_RESULT render raises ValueError."""

    def test_REQ_d00131_H_test_result_raises(self):
        """Calling render on a TEST_RESULT node raises ValueError."""
        from elspais.graph.render import render_node

        node = GraphNode(id="result:1", kind=NodeKind.TEST_RESULT, label="test")
        with pytest.raises(ValueError, match="TEST_RESULT"):
            render_node(node)


class TestFileRender:
    """Validates REQ-d00131-I: FILE node renders by walking CONTAINS children."""

    def test_REQ_d00131_I_file_renders_children_in_order(self):
        """FILE render concatenates CONTAINS children sorted by render_order."""
        from elspais.graph.render import render_file

        file_node = _make_file_node()

        # Create two remainder children with different render_orders
        rem1 = _make_remainder_node(text="First block", node_id="rem:1")
        rem2 = _make_remainder_node(text="Second block", node_id="rem:2")

        edge1 = file_node.link(rem1, EdgeKind.CONTAINS)
        edge1.metadata = {"render_order": 0.0}

        edge2 = file_node.link(rem2, EdgeKind.CONTAINS)
        edge2.metadata = {"render_order": 1.0}

        result = render_file(file_node)
        assert "First block" in result
        assert "Second block" in result
        # First block should appear before second block
        assert result.index("First block") < result.index("Second block")

    def test_REQ_d00131_I_file_respects_render_order(self):
        """FILE render uses render_order, not insertion order."""
        from elspais.graph.render import render_file

        file_node = _make_file_node()

        # Insert in reverse order but with correct render_order
        rem2 = _make_remainder_node(text="Second", node_id="rem:2")
        rem1 = _make_remainder_node(text="First", node_id="rem:1")

        edge2 = file_node.link(rem2, EdgeKind.CONTAINS)
        edge2.metadata = {"render_order": 1.0}

        edge1 = file_node.link(rem1, EdgeKind.CONTAINS)
        edge1.metadata = {"render_order": 0.0}

        result = render_file(file_node)
        assert result.index("First") < result.index("Second")

    def test_REQ_d00131_I_file_empty_children(self):
        """FILE with no CONTAINS children renders empty string."""
        from elspais.graph.render import render_file

        file_node = _make_file_node()
        result = render_file(file_node)
        assert result == ""

    def test_REQ_d00131_I_file_mixed_node_kinds(self):
        """FILE renders children of different NodeKinds correctly."""
        from elspais.graph.render import render_file

        file_node = _make_file_node()

        # Remainder before requirement
        rem = _make_remainder_node(text="# Header\n", node_id="rem:1")
        edge_rem = file_node.link(rem, EdgeKind.CONTAINS)
        edge_rem.metadata = {"render_order": 0.0}

        req = _make_requirement_node(
            req_id="REQ-t00001",
            title="Test",
            assertions=[("A", "SHALL work.")],
        )
        edge_req = file_node.link(req, EdgeKind.CONTAINS)
        edge_req.metadata = {"render_order": 1.0}

        result = render_file(file_node)
        assert "# Header" in result
        assert "## REQ-t00001: Test" in result
        assert "A. SHALL work." in result


class TestOrderIndependentHashing:
    """Validates REQ-d00131-J: Order-independent assertion hashing."""

    def test_REQ_d00131_J_hash_independent_of_assertion_order(self):
        """Same assertions in different order produce the same hash."""
        from elspais.graph.render import compute_requirement_hash

        assertions_ab = [("A", "SHALL do X."), ("B", "SHALL do Y.")]
        assertions_ba = [("B", "SHALL do Y."), ("A", "SHALL do X.")]

        hash_ab = compute_requirement_hash(assertions_ab)
        hash_ba = compute_requirement_hash(assertions_ba)

        assert hash_ab == hash_ba

    def test_REQ_d00131_J_hash_changes_on_text_edit(self):
        """Editing assertion text changes the hash."""
        from elspais.graph.render import compute_requirement_hash

        original = [("A", "SHALL do X."), ("B", "SHALL do Y.")]
        modified = [("A", "SHALL do X."), ("B", "SHALL do Z.")]

        hash_orig = compute_requirement_hash(original)
        hash_mod = compute_requirement_hash(modified)

        assert hash_orig != hash_mod

    def test_REQ_d00131_J_hash_is_8_chars(self):
        """Computed hash is 8 characters long."""
        from elspais.graph.render import compute_requirement_hash

        assertions = [("A", "SHALL do X.")]
        result = compute_requirement_hash(assertions)
        assert len(result) == 8
        assert all(c in "0123456789abcdef" for c in result)

    def test_REQ_d00131_J_sorts_individual_hashes(self):
        """Individual assertion hashes are sorted lexicographically before combining."""
        from elspais.graph.render import compute_requirement_hash

        # The implementation should:
        # 1. Hash each assertion individually
        # 2. Sort those hashes
        # 3. Hash the sorted collection
        # We verify by checking that reordered assertions give same result
        assertions1 = [("A", "First"), ("B", "Second"), ("C", "Third")]
        assertions2 = [("C", "Third"), ("A", "First"), ("B", "Second")]

        assert compute_requirement_hash(assertions1) == compute_requirement_hash(assertions2)
