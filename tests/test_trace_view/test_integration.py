# Implements: REQ-int-d00006 (Test Migration)
"""
Tests for trace_view integration.

REQ-int-d00006-A: All trace_view tests SHALL be migrated to tests/test_trace_view/.
REQ-int-d00006-B: Tests requiring optional deps SHALL use pytest.importorskip().
"""

from pathlib import Path

import pytest


class TestTraceViewImports:
    """Test that trace_view package imports correctly."""

    def test_import_models(self):
        """Test TraceViewRequirement model can be imported."""
        from elspais.trace_view.models import GitChangeInfo, TestInfo, TraceViewRequirement

        assert TraceViewRequirement is not None
        assert TestInfo is not None
        assert GitChangeInfo is not None

    def test_import_generator(self):
        """Test TraceViewGenerator can be imported."""
        from elspais.trace_view.generators.base import TraceViewGenerator

        assert TraceViewGenerator is not None

    def test_import_annotators(self):
        """Test annotators module can be imported (replaces coverage module)."""
        from elspais.core.annotators import (
            count_by_level,
            count_by_repo,
            get_implementation_status,
        )

        assert count_by_level is not None
        assert count_by_repo is not None
        assert get_implementation_status is not None

    def test_import_scanning(self):
        """Test scanning module can be imported."""
        from elspais.trace_view.scanning import scan_implementation_files

        assert scan_implementation_files is not None


class TestTraceViewHTMLImports:
    """Test HTML generator imports (requires jinja2)."""

    def test_import_html_generator(self):
        """Test HTMLGenerator can be imported when jinja2 is available."""
        pytest.importorskip("jinja2")
        from elspais.trace_view.html import HTMLGenerator

        assert HTMLGenerator is not None

    def test_import_html_availability_flag(self):
        """Test JINJA2_AVAILABLE flag is exported."""
        from elspais.trace_view.html import JINJA2_AVAILABLE

        # Should be True since we successfully imported jinja2 above
        assert isinstance(JINJA2_AVAILABLE, bool)


class TestTraceViewReviewImports:
    """Test review system imports (requires flask)."""

    def test_import_review_models(self):
        """Test review models can be imported without flask."""
        from elspais.trace_view.review import (
            Comment,
            Thread,
        )

        assert Comment is not None
        assert Thread is not None

    def test_import_review_server(self):
        """Test create_app can be imported when flask is available."""
        pytest.importorskip("flask")
        from elspais.trace_view.review import create_app

        assert create_app is not None

    def test_flask_availability_flag(self):
        """Test FLASK_AVAILABLE flag is exported."""
        from elspais.trace_view.review import FLASK_AVAILABLE

        assert isinstance(FLASK_AVAILABLE, bool)


class TestReformatImports:
    """Test reformat module imports."""

    def test_import_detector(self):
        """Test format detection can be imported."""
        from elspais.reformat import detect_format, needs_reformatting

        assert detect_format is not None
        assert needs_reformatting is not None

    def test_import_line_breaks(self):
        """Test line break functions can be imported."""
        from elspais.reformat import normalize_line_breaks

        assert normalize_line_breaks is not None

    def test_import_hierarchy(self):
        """Test hierarchy functions can be imported."""
        from elspais.reformat import RequirementNode

        assert RequirementNode is not None


class TestTraceViewModels:
    """Test TraceViewRequirement model functionality."""

    def test_create_from_core_requirement(self):
        """Test creating TraceViewRequirement from core Requirement."""
        from elspais.core.models import Requirement
        from elspais.trace_view.models import TraceViewRequirement

        core_req = Requirement(
            id="REQ-d00001",
            title="Test Requirement",
            level="Dev",
            status="Active",
            implements=["REQ-p00001"],
            body="Test body",
            rationale="Test rationale",
            hash="abc12345",
            file_path=Path("/test/spec/test.md"),
            line_number=10,
        )

        tv_req = TraceViewRequirement.from_core(core_req)

        assert tv_req.id == "d00001"
        assert tv_req.title == "Test Requirement"
        assert tv_req.level.upper() == "DEV"  # Level may be normalized
        assert tv_req.status == "Active"
        # Implements may keep REQ- prefix or strip it
        assert any("p00001" in impl for impl in tv_req.implements)

    def test_requirement_properties(self):
        """Test TraceViewRequirement property accessors."""
        from elspais.core.models import Requirement
        from elspais.trace_view.models import TraceViewRequirement

        core_req = Requirement(
            id="REQ-p00001",
            title="PRD Requirement",
            level="PRD",
            status="Active",
            implements=[],
            body="",
            rationale="",
            hash="12345678",
            file_path=Path("/test/spec/prd.md"),
            line_number=1,
        )

        tv_req = TraceViewRequirement.from_core(core_req)

        # Test is_roadmap (should be False for regular spec file)
        assert tv_req.is_roadmap is False

        # Test display_filename
        assert "prd.md" in tv_req.display_filename


class TestFormatDetection:
    """Test requirement format detection."""

    def test_detect_old_format(self):
        """Test detection of old Acceptance Criteria format."""
        from elspais.reformat import detect_format

        old_body = """
**Acceptance Criteria**:
- The system does X
- The system provides Y
        """

        analysis = detect_format(old_body)
        assert analysis.has_acceptance_criteria is True
        assert analysis.is_new_format is False

    def test_detect_new_format(self):
        """Test detection of new Assertions format."""
        from elspais.reformat import detect_format

        new_body = """
## Assertions

A. The system SHALL do X.
B. The system SHALL provide Y.
        """

        analysis = detect_format(new_body)
        assert analysis.has_assertions_section is True
        assert analysis.has_labeled_assertions is True
        assert analysis.is_new_format is True


class TestLineBreakNormalization:
    """Test line break normalization."""

    def test_collapse_blank_lines(self):
        """Test collapsing multiple blank lines."""
        from elspais.reformat import normalize_line_breaks

        content = "Line 1\n\n\n\nLine 2"
        result = normalize_line_breaks(content, reflow=False)

        # Should have at most one blank line
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_preserve_structural_lines(self):
        """Test that structural lines are preserved."""
        from elspais.reformat import normalize_line_breaks

        content = """## Assertions

A. The system SHALL do X.
B. The system SHALL do Y.
        """

        result = normalize_line_breaks(content)

        assert "## Assertions" in result
        assert "A. The system SHALL" in result
        assert "B. The system SHALL" in result


class TestScanningPatterns:
    """Test scanning pattern handles assertion-level references.

    Validates: REQ-p00003-C
    """

    def test_scanning_pattern_matches_base_req(self):
        """Test pattern matches base requirement IDs."""
        import re

        # Pattern from scanning.py
        pattern = re.compile(r"REQ-(?:([A-Z]+)-)?([pod]\d{5})(?:-[A-Z])?")

        match = pattern.search("# Implements: REQ-d00001")
        assert match is not None
        assert match.group(1) is None  # No sponsor prefix
        assert match.group(2) == "d00001"

    def test_scanning_pattern_matches_assertion_ref(self):
        """Test pattern matches assertion-level references."""
        import re

        pattern = re.compile(r"REQ-(?:([A-Z]+)-)?([pod]\d{5})(?:-[A-Z])?")

        match = pattern.search("# Implements: REQ-d00001-A")
        assert match is not None
        assert match.group(1) is None  # No sponsor prefix
        assert match.group(2) == "d00001"  # Core ID without assertion

    def test_scanning_pattern_matches_sponsor_assertion_ref(self):
        """Test pattern matches sponsor + assertion-level references."""
        import re

        pattern = re.compile(r"REQ-(?:([A-Z]+)-)?([pod]\d{5})(?:-[A-Z])?")

        match = pattern.search("# Implements: REQ-CAL-d00001-B")
        assert match is not None
        assert match.group(1) == "CAL"  # Sponsor prefix
        assert match.group(2) == "d00001"  # Core ID without assertion

    def test_scanning_pattern_all_assertion_labels(self):
        """Test pattern matches all assertion labels A-Z."""
        import re

        pattern = re.compile(r"REQ-(?:([A-Z]+)-)?([pod]\d{5})(?:-[A-Z])?")

        for label in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            ref = f"REQ-p00001-{label}"
            match = pattern.search(ref)
            assert match is not None, f"Failed to match {ref}"
            assert match.group(2) == "p00001"


class TestAssertionIndicatorInView:
    """Test assertion indicator feature in trace view.

    When a child requirement implements specific assertions (e.g., REQ-p00001-A),
    the trace view should show an assertion indicator like "(A)" before the
    expand/collapse icon.

    These tests use TraceGraph, the single source of truth for requirement
    hierarchy and relationships.
    """

    def _build_test_graph(self, requirements):
        """Build a TraceGraph from a list of core requirements."""
        from elspais.core.graph_builder import TraceGraphBuilder

        builder = TraceGraphBuilder(repo_root=Path("."))

        # Add all requirements to the builder (as a dict by ID)
        reqs_dict = {req.id: req for req in requirements}
        builder.add_requirements(reqs_dict)

        return builder.build()

    def test_find_children_with_assertion_info_direct_impl(self):
        """Test finding children that implement parent directly."""
        pytest.importorskip("jinja2")
        from elspais.core.models import Requirement
        from elspais.trace_view.html import HTMLGenerator

        parent = Requirement(
            id="REQ-p00001",
            title="Parent",
            level="PRD",
            status="Active",
            body="",
            implements=[],
        )
        child = Requirement(
            id="REQ-d00001",
            title="Child",
            level="DEV",
            status="Active",
            body="",
            implements=["REQ-p00001"],  # Direct implementation
        )

        graph = self._build_test_graph([parent, child])
        generator = HTMLGenerator(graph)

        parent_node = graph.find_by_id("REQ-p00001")
        children = generator._get_children_with_assertion_info(parent_node)

        assert len(children) == 1
        assert children[0][0].id == "REQ-d00001"
        assert children[0][1] == []  # No assertion labels for direct impl

    def test_find_children_with_assertion_info_single_assertion(self):
        """Test finding children that implement a single assertion."""
        pytest.importorskip("jinja2")
        from elspais.core.models import Assertion, Requirement
        from elspais.trace_view.html import HTMLGenerator

        parent = Requirement(
            id="REQ-p00001",
            title="Parent",
            level="PRD",
            status="Active",
            body="",
            implements=[],
            assertions=[
                Assertion(label="A", text="The system SHALL do something."),
                Assertion(label="B", text="The system SHALL do another thing."),
            ],
        )
        child = Requirement(
            id="REQ-d00001",
            title="Child implementing assertion A",
            level="DEV",
            status="Active",
            body="",
            implements=["REQ-p00001-A"],  # Implements assertion A
        )

        graph = self._build_test_graph([parent, child])
        generator = HTMLGenerator(graph)

        parent_node = graph.find_by_id("REQ-p00001")
        children = generator._get_children_with_assertion_info(parent_node)

        assert len(children) == 1
        assert children[0][0].id == "REQ-d00001"
        assert children[0][1] == ["A"]  # Single assertion label

    def test_find_children_with_assertion_info_multiple_assertions(self):
        """Test finding children that implement multiple assertions."""
        pytest.importorskip("jinja2")
        from elspais.core.models import Assertion, Requirement
        from elspais.trace_view.html import HTMLGenerator

        parent = Requirement(
            id="REQ-p00001",
            title="Parent",
            level="PRD",
            status="Active",
            body="",
            implements=[],
            assertions=[
                Assertion(label="A", text="The system SHALL do something."),
                Assertion(label="B", text="The system SHALL do another thing."),
            ],
        )
        child = Requirement(
            id="REQ-d00001",
            title="Child implementing assertions A and B",
            level="DEV",
            status="Active",
            body="",
            # Multi-assertion syntax (REQ-p00001-A-B) gets expanded by parser
            implements=["REQ-p00001-A", "REQ-p00001-B"],
        )

        graph = self._build_test_graph([parent, child])
        generator = HTMLGenerator(graph)

        parent_node = graph.find_by_id("REQ-p00001")
        children = generator._get_children_with_assertion_info(parent_node)

        assert len(children) == 1
        assert children[0][0].id == "REQ-d00001"
        assert sorted(children[0][1]) == ["A", "B"]  # Both assertion labels

    def test_assertion_indicator_html_generation(self):
        """Test that assertion indicator HTML is generated correctly."""
        pytest.importorskip("jinja2")
        from elspais.core.models import Assertion, Requirement
        from elspais.trace_view.html import HTMLGenerator

        parent = Requirement(
            id="REQ-p00001",
            title="Parent",
            level="PRD",
            status="Active",
            body="",
            implements=[],
            file_path=Path("spec/test.md"),
            assertions=[
                Assertion(label="A", text="The system SHALL do something."),
                Assertion(label="B", text="The system SHALL do another thing."),
            ],
        )
        child = Requirement(
            id="REQ-d00001",
            title="Child",
            level="DEV",
            status="Active",
            body="",
            # Multi-assertion syntax (REQ-p00001-A-B) gets expanded by parser
            implements=["REQ-p00001-A", "REQ-p00001-B"],
            file_path=Path("spec/test.md"),
        )

        graph = self._build_test_graph([parent, child])
        generator = HTMLGenerator(graph)

        # Build flat list which triggers assertion detection
        flat_list = generator._build_flat_requirement_list()

        # Find child entry in flat list
        child_entry = next(
            (e for e in flat_list if e.get("node") and e["node"].id == "REQ-d00001"),
            None,
        )

        assert child_entry is not None
        assert sorted(child_entry["assertion_labels"]) == ["A", "B"]

        # Generate HTML and check for assertion indicator
        html = generator._format_req_html(child_entry)
        assert 'class="assertion-indicator"' in html
        assert "(A,B)" in html or "(B,A)" in html  # Order may vary
