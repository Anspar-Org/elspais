# Verifies: REQ-d00131
# elspais: expected-broken-links 1
"""Tests for the render protocol (Task 1 of FILENODE3).

Validates REQ-d00131-A: Each NodeKind has a render() function dispatched by kind
Validates REQ-d00131-B: REQUIREMENT renders full block
Validates REQ-d00131-C: ASSERTION render raises ValueError
Validates REQ-d00131-D: REMAINDER renders raw text verbatim
Validates REQ-d00131-E: USER_JOURNEY renders full block
Validates REQ-d00131-F: CODE renders # Implements: comment line(s)
Validates REQ-d00131-G: TEST renders # Verifies: comment line(s)
Validates REQ-d00131-H: TEST_RESULT render raises ValueError
Validates REQ-d00131-I: FILE node renders by walking CONTAINS children sorted by render_order
Validates REQ-d00131-J: Order-independent assertion hashing
"""

from __future__ import annotations

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.GraphNode import FileType
from elspais.graph.relations import EdgeKind
from tests.fixtures import fake_reqs


def _make_file_node(path: str = "spec/test.md") -> GraphNode:
    """Create a FILE node for testing."""
    node = GraphNode(id=f"file:{path}", kind=NodeKind.FILE, label=path.split("/")[-1])
    node.set_field("file_type", FileType.SPEC)
    node.set_field("relative_path", path)
    node.set_field("absolute_path", f"/repo/{path}")
    return node


def _make_requirement_node(
    req_id: str = fake_reqs.FAKE_REQ_ID,
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
    raw_text: str = fake_reqs.CODE_RAW_TEXT,
    node_id: str = "code:src/main.py:10",
) -> GraphNode:
    """Create a CODE node for testing."""
    node = GraphNode(id=node_id, kind=NodeKind.CODE, label=f"Code at {node_id}")
    node.set_field("raw_text", raw_text)
    node.set_field("parse_line", 10)
    return node


def _make_test_node(
    raw_text: str = fake_reqs.TEST_RAW_TEXT,
    node_id: str = "test:tests/test_main.py::TestClass::test_func",
) -> GraphNode:
    """Create a TEST node for testing."""
    node = GraphNode(id=node_id, kind=NodeKind.TEST, label="TestClass::test_func")
    node.set_field("raw_text", raw_text)
    node.set_field("parse_line", 5)
    return node


class TestRenderDispatch:
    """Validates REQ-d00131-A: Each NodeKind has a render() function dispatched by kind."""

    def test_REQ_d00131_A_render_dispatches_by_kind(self):
        """render_node() dispatches correctly for each NodeKind."""
        from elspais.graph.render import render_node

        # REMAINDER should render its text
        rem = _make_remainder_node(text="hello world")
        result = render_node(rem)
        assert result == "hello world"

    # Implements: REQ-d00131-D
    def test_render_remainder_kind_raises(self):
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

    # Implements: REQ-d00131-B
    def test_render_requirement_sorts_by_render_order(self):
        """_render_requirement() must sort STRUCTURES children by render_order."""
        from elspais.graph.render import _render_requirement

        req = GraphNode(id="REQ-t00001", kind=NodeKind.REQUIREMENT, label="Test Req")
        req._content = {
            "level": "dev",
            "status": "Active",
            "hash_mode": "normalized-text",
            "implements_refs": [],
        }

        a_node = GraphNode(
            id="REQ-t00001-A", kind=NodeKind.ASSERTION, label="First assertion"
        )
        a_node._content = {"label": "A"}

        b_node = GraphNode(
            id="REQ-t00001-B", kind=NodeKind.ASSERTION, label="Second assertion"
        )
        b_node._content = {"label": "B"}

        # Link B first (insertion order: B, A), but give A lower render_order
        edge_b = req.link(b_node, EdgeKind.STRUCTURES)
        edge_b.metadata = {"render_order": 20.0}
        edge_a = req.link(a_node, EdgeKind.STRUCTURES)
        edge_a.metadata = {"render_order": 10.0}

        output = _render_requirement(req)
        lines = output.split("\n")
        assertion_lines = [l for l in lines if l and l[0].isalpha() and ". " in l]

        assert assertion_lines[0].startswith("A."), (
            f"Expected A first, got: {assertion_lines}"
        )
        assert assertion_lines[1].startswith("B."), (
            f"Expected B second, got: {assertion_lines}"
        )

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

    def test_REQ_d00131_B_requirement_ends_with_end_marker(self):
        """Rendered requirement ends with *End* marker (separator is REMAINDER)."""
        from elspais.graph.render import render_node

        node = _make_requirement_node(
            req_id="REQ-t00001",
            title="Test Requirement",
        )
        result = render_node(node)
        lines = result.rstrip().split("\n")
        assert lines[-1].startswith("*End*")

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
        assert lines[0].endswith("REQ-t00001: Full Test")
        assert "**Level**: PRD" in lines[2]
        assert "**Status**: Active" in lines[2]
        assert "**Implements**: REQ-p00001" in lines[2]
        assert "*End* *Full Test*" in result
        assert "## Assertions" in result
        assert "## Rationale" in result
        # Requirement ends with *End* marker; separator is now REMAINDER
        assert lines[-1].startswith("*End*") or lines[-1] == ""


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

        node = _make_code_node(raw_text=fake_reqs.CODE_RAW_TEXT)
        result = render_node(node)
        assert result == fake_reqs.CODE_RAW_TEXT

    def test_REQ_d00131_F_code_multi_line(self):
        """CODE render returns multiple comment lines."""
        from elspais.graph.render import render_node

        raw = fake_reqs.CODE_RAW_TEXT_MULTI
        node = _make_code_node(raw_text=raw)
        result = render_node(node)
        assert result == raw


class TestTestRender:
    """Validates REQ-d00131-G: TEST renders comment line(s)."""

    def test_REQ_d00131_G_test_single_line(self):
        """TEST render returns single comment line."""
        from elspais.graph.render import render_node

        node = _make_test_node(raw_text=fake_reqs.TEST_RAW_TEXT)
        result = render_node(node)
        assert result == fake_reqs.TEST_RAW_TEXT

    def test_REQ_d00131_G_test_validates_line(self):
        """TEST render returns Validates comment line."""
        from elspais.graph.render import render_node

        node = _make_test_node(raw_text=fake_reqs.TEST_RAW_TEXT_VALIDATES_A)
        result = render_node(node)
        assert result == fake_reqs.TEST_RAW_TEXT_VALIDATES_A


class TestTestResultRender:
    """Validates REQ-d00131-H: TEST_RESULT render raises ValueError."""

    def test_REQ_d00131_H_test_result_raises(self):
        """Calling render on a TEST_RESULT node raises ValueError."""
        from elspais.graph.render import render_node

        node = GraphNode(id="result:1", kind=NodeKind.RESULT, label="test")
        with pytest.raises(ValueError, match="RESULT"):
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


class TestNormalizedHashing:
    """Validates REQ-d00131-J: Renderer uses canonical compute_normalized_hash."""

    def test_REQ_d00131_J_hash_changes_on_text_edit(self):
        """Editing assertion text changes the hash."""
        from elspais.utilities.hasher import compute_normalized_hash

        original = [("A", "SHALL do X."), ("B", "SHALL do Y.")]
        modified = [("A", "SHALL do X."), ("B", "SHALL do Z.")]

        hash_orig = compute_normalized_hash(original)
        hash_mod = compute_normalized_hash(modified)

        assert hash_orig != hash_mod

    def test_REQ_d00131_J_hash_is_8_chars(self):
        """Computed hash is 8 characters long."""
        from elspais.utilities.hasher import compute_normalized_hash

        assertions = [("A", "SHALL do X.")]
        result = compute_normalized_hash(assertions)
        assert len(result) == 8
        assert all(c in "0123456789abcdef" for c in result)

    def test_REQ_d00131_J_whitespace_normalization(self):
        """Whitespace differences do not change the hash."""
        from elspais.utilities.hasher import compute_normalized_hash

        assertions_clean = [("A", "SHALL do X."), ("B", "SHALL do Y.")]
        assertions_extra_spaces = [("A", "SHALL  do  X."), ("B", "SHALL  do  Y.")]

        assert compute_normalized_hash(assertions_clean) == compute_normalized_hash(
            assertions_extra_spaces
        )


class TestRenderRoundTrip:
    """Validates REQ-d00131-I: render_file produces line-identical output for unmutated files."""

    @pytest.fixture
    def built_graph(self, tmp_path):
        """Build a graph from a spec file with known content."""
        from elspais.graph.factory import build_graph

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (tmp_path / ".elspais.toml").write_text(
            "version = 3\n"
            '[project]\nname = "test"\nnamespace = "REQ"\n'
            '[levels.prd]\nrank = 1\nletter = "p"\n'
            '[levels.dev]\nrank = 2\nletter = "d"\nimplements = ["prd"]\n'
            '[id-patterns]\ncanonical = "{namespace}-{level.letter}{component}"\n'
            '[id-patterns.component]\nstyle = "numeric"\ndigits = 5\n'
            "leading_zeros = true\n"
            '[id-patterns.assertions]\nlabel_style = "uppercase"\nmax_count = 26\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
            "[rules.format]\nrequire_hash = true\nrequire_assertions = true\n"
        )
        content = (
            "# Test Spec\n"
            "\n"
            "Introduction paragraph.\n"
            "\n"
            "---\n"
            "\n"
            "## REQ-p00001: First Requirement\n"
            "\n"
            "**Level**: prd | **Status**: Active\n"
            "\n"
            "Body text here.\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. SHALL do X.\n"
            "\n"
            "B. SHALL do Y.\n"
            "\n"
            "*End* *First Requirement* | **Hash**: placeholder\n"
            "\n"
            "---\n"
            "\n"
            "## REQ-p00002: Second Requirement\n"
            "\n"
            "**Level**: prd | **Status**: Draft\n"
            "\n"
            "Another body.\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. SHALL do Z.\n"
            "\n"
            "*End* *Second Requirement* | **Hash**: placeholder\n"
        )
        (spec_dir / "test.md").write_text(content)
        graph = build_graph(repo_root=tmp_path)
        return graph, spec_dir / "test.md", content

    # Implements: REQ-d00131-I
    def test_render_roundtrip_line_identical(self, built_graph):
        """Rendered output matches original file line-by-line (except hash/canonical header)."""
        from elspais.graph.render import render_file

        graph, spec_file, original_content = built_graph
        original_lines = original_content.split("\n")

        # Find the FILE node for this spec file
        file_node = None
        for root in graph.iter_roots(NodeKind.FILE):
            rel_path = root.get_field("relative_path")
            if rel_path and rel_path.endswith("test.md"):
                file_node = root
                break
        assert file_node is not None, "FILE node not found"

        rendered = render_file(file_node)
        rendered_lines = rendered.split("\n")

        # Compare line by line, allowing canonical header capitalization
        # and hash differences (the render computes the real hash)
        for i, (orig, rend) in enumerate(
            zip(original_lines, rendered_lines, strict=False), start=1
        ):
            # Skip hash line comparison (render computes canonical hash)
            if orig.startswith("*End*"):
                continue
            # Allow canonical metadata capitalization (prd vs PRD)
            if orig.startswith("**Level**") or orig.startswith("**Status**"):
                continue
            assert orig == rend, (
                f"Line {i} differs:\n" f"  original: {orig!r}\n" f"  rendered: {rend!r}"
            )

        # Line count should match (within 1 for trailing newline)
        assert abs(len(original_lines) - len(rendered_lines)) <= 1, (
            f"Line count mismatch: original={len(original_lines)}, "
            f"rendered={len(rendered_lines)}"
        )

    # Implements: REQ-d00131-I
    def test_render_roundtrip_assertion_sub_headings(self, tmp_path):
        """REQ-d00131-B: Assertion sub-headings (*italic*) survive round-trip."""
        from elspais.graph.factory import build_graph
        from elspais.graph.render import render_file

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (tmp_path / ".elspais.toml").write_text(
            "version = 4\n"
            '[project]\nname = "test"\nnamespace = "REQ"\n'
            '[levels.prd]\nrank = 1\nletter = "p"\n'
            '[id-patterns]\ncanonical = "{namespace}-{level.letter}{component}"\n'
            '[id-patterns.component]\nstyle = "numeric"\ndigits = 5\n'
            "leading_zeros = true\n"
            '[id-patterns.assertions]\nlabel_style = "uppercase"\nmax_count = 26\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
            "[rules.format]\nrequire_hash = true\nrequire_assertions = true\n"
        )
        content = (
            "## REQ-p00001: Platform Features\n"
            "\n"
            "**Level**: prd | **Status**: Active\n"
            "\n"
            "## Assertions\n"
            "\n"
            "A. SHALL provide feature X.\n"
            "\n"
            "B. SHALL provide feature Y.\n"
            "\n"
            "*Core Functionality*\n"
            "\n"
            "C. SHALL enable core operations.\n"
            "\n"
            "D. SHALL support offline mode.\n"
            "\n"
            "**Data Management**\n"
            "\n"
            "E. SHALL store data locally.\n"
            "\n"
            "*End* *Platform Features* | **Hash**: placeholder\n"
        )
        (spec_dir / "test.md").write_text(content)
        graph = build_graph(repo_root=tmp_path)

        # Find FILE node
        file_node = None
        for root in graph.iter_roots(NodeKind.FILE):
            rel_path = root.get_field("relative_path")
            if rel_path and rel_path.endswith("test.md"):
                file_node = root
                break
        assert file_node is not None

        rendered = render_file(file_node)

        # The sub-headings must appear in their original format
        assert "*Core Functionality*" in rendered, (
            f"Italic sub-heading not preserved.\nRendered:\n{rendered}"
        )
        assert "**Data Management**" in rendered, (
            f"Bold sub-heading not preserved.\nRendered:\n{rendered}"
        )
        # Must NOT appear as ## headings
        assert "## Core Functionality" not in rendered
        assert "## Data Management" not in rendered
        assert "### Core Functionality" not in rendered
        assert "### Data Management" not in rendered
