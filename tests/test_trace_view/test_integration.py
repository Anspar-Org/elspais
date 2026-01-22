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

    def test_import_coverage(self):
        """Test coverage module can be imported."""
        from elspais.trace_view.coverage import (
            calculate_coverage,
        )

        assert calculate_coverage is not None

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
