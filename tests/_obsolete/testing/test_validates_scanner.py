# elspais: expected-broken-links 6
"""Tests for Validates: reference pattern scanning."""

from pathlib import Path

import pytest

from elspais.core.graph import NodeKind, TraceNode
from elspais.core.patterns import PatternConfig
from elspais.testing.config import TestingConfig
from elspais.testing.scanner import TestScanner, build_validates_patterns


class TestValidatesPattern:
    """Tests for Validates: reference pattern matching."""

    @pytest.fixture
    def fixtures_dir(self):
        """Return path to test fixtures directory."""
        return Path(__file__).parent / "fixtures"

    @pytest.fixture
    def validates_file(self, fixtures_dir):
        """Return path to validates_test.py fixture."""
        return fixtures_dir / "validates_test.py"

    @pytest.fixture
    def pattern_config(self):
        """Create a PatternConfig for HHT-style IDs."""
        return PatternConfig.from_dict({
            "prefix": "REQ",
            "id_template": "{prefix}-{type}{id}",
            "types": {
                "product": {"id": "p", "level": 1},
                "operations": {"id": "o", "level": 2},
                "development": {"id": "d", "level": 3},
            },
            "id_format": {"style": "numeric", "digits": 5},
            "assertions": {"label_style": "uppercase"},
        })

    def test_validates_in_docstring(self, fixtures_dir):
        """Validates: pattern found in docstring."""
        scanner = TestScanner(reference_keyword="Validates")
        refs = scanner.scan_file(fixtures_dir / "validates_test.py")

        # Should find REQ-d00001-A from docstring
        d00001_refs = [r for r in refs if r.requirement_id == "REQ-d00001"]
        assert len(d00001_refs) >= 1
        # Should find assertion label A
        assert any(r.assertion_label == "A" for r in d00001_refs)

    def test_validates_in_comment(self, fixtures_dir):
        """Validates: pattern found in comment above function."""
        scanner = TestScanner(reference_keyword="Validates")
        refs = scanner.scan_file(fixtures_dir / "validates_test.py")

        # Should find REQ-d00001, REQ-d00001-B from comment
        d00001_refs = [r for r in refs if r.requirement_id == "REQ-d00001"]
        assert any(r.assertion_label == "B" for r in d00001_refs)

    def test_validates_multiple_refs(self, fixtures_dir):
        """Multiple comma-separated requirements."""
        scanner = TestScanner(reference_keyword="Validates")
        refs = scanner.scan_file(fixtures_dir / "validates_test.py")

        # Should find REQ-p00001-A, REQ-p00001-B, REQ-o00001 from docstring
        req_ids = {r.requirement_id for r in refs}
        assert "REQ-p00001" in req_ids
        assert "REQ-o00001" in req_ids

    def test_validates_with_assertion(self, fixtures_dir):
        """Assertion suffix like REQ-d00001-A."""
        scanner = TestScanner(reference_keyword="Validates")
        refs = scanner.scan_file(fixtures_dir / "validates_test.py")

        # Find refs with assertion labels
        refs_with_assertions = [r for r in refs if r.assertion_label]
        assert len(refs_with_assertions) >= 4  # A, B, A, B from various tests

    def test_validates_case_insensitive(self, fixtures_dir):
        """validates:, VALIDATES:, Validates: all work."""
        scanner = TestScanner(reference_keyword="Validates")
        refs = scanner.scan_file(fixtures_dir / "validates_test.py")

        req_ids = {r.requirement_id for r in refs}
        # These use different case variants
        assert "REQ-d00002" in req_ids  # VALIDATES:
        assert "REQ-d00003" in req_ids  # validates:

    def test_validates_uses_pattern_config(self, pattern_config):
        """Scanner uses PatternValidator from config."""
        patterns = build_validates_patterns(pattern_config, keyword="Validates")

        # Patterns should match HHT-style IDs
        assert len(patterns) >= 1
        # Each pattern should be a valid regex string
        for pattern in patterns:
            assert isinstance(pattern, str)
            assert "Validates" in pattern or "validates" in pattern.lower()

    def test_scanner_with_custom_keyword(self, fixtures_dir):
        """Scanner respects custom reference_keyword."""
        # Create scanner that looks for IMPLEMENTS instead
        scanner = TestScanner(reference_keyword="IMPLEMENTS")
        refs = scanner.scan_file(fixtures_dir / "sample_test.py")

        # Should find IMPLEMENTS: references from sample_test.py
        assert len(refs) >= 1


class TestBuildValidatesPatterns:
    """Tests for build_validates_patterns helper."""

    @pytest.fixture
    def hht_config(self):
        """HHT-style pattern config."""
        return PatternConfig.from_dict({
            "prefix": "REQ",
            "id_template": "{prefix}-{type}{id}",
            "types": {
                "product": {"id": "p", "level": 1},
                "operations": {"id": "o", "level": 2},
                "development": {"id": "d", "level": 3},
            },
            "id_format": {"style": "numeric", "digits": 5},
        })

    @pytest.fixture
    def jira_config(self):
        """Jira-style pattern config."""
        return PatternConfig.from_dict({
            "prefix": "PROJ",
            "id_template": "{prefix}-{id}",
            "types": {},
            "id_format": {"style": "numeric", "digits": 0, "leading_zeros": False},
        })

    def test_builds_patterns_from_hht_config(self, hht_config):
        """Builds patterns matching HHT-style IDs."""
        patterns = build_validates_patterns(hht_config, keyword="Validates")

        # Should have at least one pattern
        assert len(patterns) >= 1

        # Test that pattern matches expected format
        import re
        combined = "|".join(patterns)
        regex = re.compile(combined, re.IGNORECASE)

        # Should match: Validates: REQ-p00001
        assert regex.search("Validates: REQ-p00001")
        # Should match: Validates: REQ-d00001-A
        assert regex.search("Validates: REQ-d00001-A")

    def test_builds_patterns_from_jira_config(self, jira_config):
        """Builds patterns matching Jira-style IDs."""
        patterns = build_validates_patterns(jira_config, keyword="Validates")

        import re
        combined = "|".join(patterns)
        regex = re.compile(combined, re.IGNORECASE)

        # Should match: Validates: PROJ-123
        assert regex.search("Validates: PROJ-123")


class TestScannerIntegration:
    """Tests for scanner integration with graph builder."""

    @pytest.fixture
    def fixtures_dir(self):
        """Return path to test fixtures directory."""
        return Path(__file__).parent / "fixtures"

    def test_scanner_creates_test_nodes(self, fixtures_dir, tmp_path):
        """Scanner creates TraceNode with _validates_targets."""
        from elspais.testing.scanner import create_test_nodes

        scanner = TestScanner(reference_keyword="Validates")
        result = scanner.scan_directories(
            base_path=fixtures_dir,
            test_dirs=["."],
            file_patterns=["validates_test.py"],
        )

        # Convert to TraceNodes
        test_nodes = create_test_nodes(result, repo_root=fixtures_dir.parent.parent)

        assert len(test_nodes) > 0

        # Each node should have the right kind
        for node in test_nodes:
            assert node.kind == NodeKind.TEST
            # Should have _validates_targets in metrics
            assert "_validates_targets" in node.metrics

    def test_graph_links_tests_to_assertions(self, fixtures_dir, tmp_path):
        """Tests are linked as children of assertions."""
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.core.models import Assertion, Requirement
        from elspais.testing.scanner import create_test_nodes

        # Create a simple requirement with assertions
        requirements = {
            "REQ-d00001": Requirement(
                id="REQ-d00001",
                title="Test Requirement",
                level="Dev",
                status="Active",
                body="Test requirement body",
                implements=[],
                file_path=tmp_path / "spec" / "test.md",
                assertions=[
                    Assertion(label="A", text="First assertion"),
                    Assertion(label="B", text="Second assertion"),
                ],
            )
        }

        # Scan for test references
        scanner = TestScanner(reference_keyword="Validates")
        result = scanner.scan_directories(
            base_path=fixtures_dir,
            test_dirs=["."],
            file_patterns=["validates_test.py"],
        )

        # Build graph with requirements and tests
        builder = TraceGraphBuilder(repo_root=tmp_path)
        builder.add_requirements(requirements)

        # Convert scan results to nodes and add to graph
        test_nodes = create_test_nodes(result, repo_root=fixtures_dir.parent.parent)
        builder.add_test_coverage(test_nodes)

        graph, _ = builder.build_and_validate()

        # Find the assertion node
        assertion_a = graph.find_by_id("REQ-d00001-A")
        assert assertion_a is not None

        # Should have test children linked
        test_children = [c for c in assertion_a.children if c.kind == NodeKind.TEST]
        assert len(test_children) >= 1

    def test_coverage_calculated_from_tests(self, fixtures_dir, tmp_path):
        """compute_metrics() counts linked tests."""
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.core.models import Assertion, Requirement
        from elspais.testing.scanner import create_test_nodes

        # Create requirement with 2 assertions
        requirements = {
            "REQ-d00001": Requirement(
                id="REQ-d00001",
                title="Test Requirement",
                level="Dev",
                status="Active",
                body="Test requirement body",
                implements=[],
                file_path=tmp_path / "spec" / "test.md",
                assertions=[
                    Assertion(label="A", text="Covered assertion"),
                    Assertion(label="B", text="Also covered assertion"),
                ],
            )
        }

        # Scan for test references
        scanner = TestScanner(reference_keyword="Validates")
        result = scanner.scan_directories(
            base_path=fixtures_dir,
            test_dirs=["."],
            file_patterns=["validates_test.py"],
        )

        # Build graph
        builder = TraceGraphBuilder(repo_root=tmp_path)
        builder.add_requirements(requirements)
        test_nodes = create_test_nodes(result, repo_root=fixtures_dir.parent.parent)
        builder.add_test_coverage(test_nodes)
        graph, _ = builder.build_and_validate()

        # Compute metrics
        builder.compute_metrics(graph)

        # Check coverage on requirement
        req_node = graph.find_by_id("REQ-d00001")
        assert req_node is not None
        assert req_node.metrics.get("total_assertions", 0) == 2
        assert req_node.metrics.get("covered_assertions", 0) >= 1
        assert req_node.metrics.get("coverage_pct", 0) > 0


class TestTestingConfigKeyword:
    """Tests for reference_keyword in TestingConfig."""

    def test_default_keyword(self):
        """Default keyword is 'Validates'."""
        config = TestingConfig()
        assert config.reference_keyword == "Validates"

    def test_from_dict_with_keyword(self):
        """Keyword can be set via from_dict."""
        config = TestingConfig.from_dict({
            "enabled": True,
            "reference_keyword": "Implements",
        })
        assert config.reference_keyword == "Implements"

    def test_from_dict_without_keyword(self):
        """Missing keyword defaults to 'Validates'."""
        config = TestingConfig.from_dict({"enabled": True})
        assert config.reference_keyword == "Validates"


class TestExpectedBrokenLinksMarker:
    """Tests for expected-broken-links marker detection and sequential suppression."""

    @pytest.fixture
    def fixtures_dir(self):
        """Return path to test fixtures directory."""
        return Path(__file__).parent / "fixtures"

    def test_first_n_refs_marked_expected_broken(self, fixtures_dir):
        """Marker N=3 marks first 3 refs as expected_broken."""
        scanner = TestScanner(reference_keyword="Validates")
        refs = scanner.scan_file(fixtures_dir / "expected_broken_fixture.py")

        # Should have at least 3 refs found
        assert len(refs) >= 3
        # First 3 should be marked (marker=3)
        marked_count = sum(1 for ref in refs if ref.expected_broken)
        assert marked_count == 3

    def test_refs_after_n_not_marked(self, fixtures_dir):
        """4th+ refs are NOT marked even with marker N=2."""
        scanner = TestScanner(reference_keyword="Validates")
        refs = scanner.scan_file(fixtures_dir / "expected_broken_sequential.py")

        # File has 4 unique requirement IDs with marker=2
        assert len(refs) >= 4
        # Only first 2 should be marked
        marked_count = sum(1 for ref in refs if ref.expected_broken)
        assert marked_count == 2
        # Non-marked refs should exist
        unmarked_count = sum(1 for ref in refs if not ref.expected_broken)
        assert unmarked_count >= 2

    def test_suppressed_count_tracked(self, fixtures_dir):
        """suppressed_count reflects number of marked refs."""
        scanner = TestScanner(reference_keyword="Validates")
        result = scanner.scan_directories(
            base_path=fixtures_dir,
            test_dirs=["."],
            file_patterns=["expected_broken_fixture.py"],
        )

        # File has marker=3, so suppressed_count should be 3
        assert result.suppressed_count == 3

    def test_marker_case_insensitive(self, fixtures_dir):
        """expected-broken-links, EXPECTED-BROKEN-LINKS work."""
        scanner = TestScanner(reference_keyword="Validates")
        refs = scanner.scan_file(fixtures_dir / "expected_broken_case_variants.py")

        # File has marker=2
        marked_count = sum(1 for ref in refs if ref.expected_broken)
        assert marked_count == 2

    def test_marker_outside_header_ignored(self, fixtures_dir):
        """Marker after line 20 is ignored."""
        scanner = TestScanner(reference_keyword="Validates")
        result = scanner.scan_directories(
            base_path=fixtures_dir,
            test_dirs=["."],
            file_patterns=["marker_outside_header.py"],
        )

        # No refs should be marked as expected_broken
        all_refs = [ref for refs in result.references.values() for ref in refs]
        assert all(not ref.expected_broken for ref in all_refs)

    def test_direct_marker_detection_method(self, fixtures_dir):
        """_detect_expected_broken_links_marker works correctly."""
        scanner = TestScanner(reference_keyword="Validates")

        # File with marker
        count = scanner._detect_expected_broken_links_marker(
            fixtures_dir / "expected_broken_fixture.py"
        )
        assert count == 3

        # File without marker
        count = scanner._detect_expected_broken_links_marker(
            fixtures_dir / "validates_test.py"
        )
        assert count is None

        # File with marker outside header
        count = scanner._detect_expected_broken_links_marker(
            fixtures_dir / "marker_outside_header.py"
        )
        assert count is None

    # Multi-language comment support tests

    def test_python_hash_comment(self, fixtures_dir):
        """# elspais: expected-broken-links N works."""
        scanner = TestScanner(reference_keyword="Validates")
        count = scanner._detect_expected_broken_links_marker(
            fixtures_dir / "expected_broken_fixture.py"
        )
        assert count == 3

    def test_js_double_slash_comment(self, fixtures_dir):
        """// elspais: expected-broken-links N works."""
        scanner = TestScanner(reference_keyword="Validates")
        count = scanner._detect_expected_broken_links_marker(
            fixtures_dir / "expected_broken_js.js"
        )
        assert count == 2

    def test_sql_double_dash_comment(self, fixtures_dir):
        """-- elspais: expected-broken-links N works."""
        scanner = TestScanner(reference_keyword="Validates")
        count = scanner._detect_expected_broken_links_marker(
            fixtures_dir / "expected_broken_sql.sql"
        )
        assert count == 2

    def test_html_comment(self, fixtures_dir):
        """<!-- elspais: expected-broken-links N --> works."""
        scanner = TestScanner(reference_keyword="Validates")
        count = scanner._detect_expected_broken_links_marker(
            fixtures_dir / "expected_broken_html.html"
        )
        assert count == 1

    def test_css_block_comment(self, fixtures_dir):
        """/* elspais: expected-broken-links N */ works."""
        scanner = TestScanner(reference_keyword="Validates")
        count = scanner._detect_expected_broken_links_marker(
            fixtures_dir / "expected_broken_css.css"
        )
        assert count == 1


class TestExpectedBrokenLinksFiltering:
    """Tests for broken link warning suppression based on sequential marking."""

    @pytest.fixture
    def fixtures_dir(self):
        """Return path to test fixtures directory."""
        return Path(__file__).parent / "fixtures"

    def test_suppressed_refs_emit_info_not_warning(self, fixtures_dir, tmp_path):
        """Broken links with expected_broken=True emit info, not warning."""
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.testing.scanner import create_test_nodes

        # Create empty requirements (all references will be broken)
        requirements = {}

        # Scan fixture with marker (3 expected broken refs)
        # Note: Due to overlapping patterns, each ref may be matched multiple times.
        # With marker=3, the first 3 pattern matches are suppressed.
        scanner = TestScanner(reference_keyword="Validates")
        result = scanner.scan_directories(
            base_path=fixtures_dir,
            test_dirs=["."],
            file_patterns=["expected_broken_fixture.py"],
        )

        # Build graph
        builder = TraceGraphBuilder(repo_root=tmp_path)
        builder.add_requirements(requirements)
        test_nodes = create_test_nodes(result, repo_root=fixtures_dir.parent.parent)
        builder.add_test_coverage(test_nodes)

        graph, validation = builder.build_and_validate()

        # Should have info messages for suppressed links
        info_messages = [
            i for i in validation.info if "Expected broken link" in i
        ]
        assert len(info_messages) >= 1  # At least some are suppressed

        # Should have mix of info (suppressed) and warnings (not suppressed)
        # depending on how pattern matches consume the budget

    def test_excess_refs_still_warn(self, fixtures_dir, tmp_path):
        """Refs beyond N produce normal warnings."""
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.testing.scanner import create_test_nodes

        # Create empty requirements
        requirements = {}

        # Scan fixture with marker=2 but 4 unique requirement IDs
        # Due to overlapping patterns, the 2-ref budget may be consumed
        # by the first 2 pattern matches (which may be duplicates).
        scanner = TestScanner(reference_keyword="Validates")
        result = scanner.scan_directories(
            base_path=fixtures_dir,
            test_dirs=["."],
            file_patterns=["expected_broken_sequential.py"],
        )

        # Build graph
        builder = TraceGraphBuilder(repo_root=tmp_path)
        builder.add_requirements(requirements)
        test_nodes = create_test_nodes(result, repo_root=fixtures_dir.parent.parent)
        builder.add_test_coverage(test_nodes)

        graph, validation = builder.build_and_validate()

        # Should have at least 1 info message for suppressed links
        info_messages = [
            i for i in validation.info if "Expected broken link" in i
        ]
        assert len(info_messages) >= 1

        # Should have warnings for the refs beyond the budget
        broken_link_warnings = [
            w for w in validation.warnings if "Broken link" in w
        ]
        assert len(broken_link_warnings) >= 1
        # At least one unsuppressed ref should produce a warning
        warning_text = " ".join(broken_link_warnings)
        assert any(
            f"d920{i:02d}" in warning_text for i in range(1, 5)
        )  # Any of d92001-d92004

    def test_no_marker_reports_all_warnings(self, fixtures_dir, tmp_path):
        """File without marker reports all broken link warnings."""
        from elspais.core.graph_builder import TraceGraphBuilder
        from elspais.testing.scanner import create_test_nodes

        # Create empty requirements
        requirements = {}

        # Scan fixture without marker
        scanner = TestScanner(reference_keyword="Validates")
        result = scanner.scan_directories(
            base_path=fixtures_dir,
            test_dirs=["."],
            file_patterns=["validates_test.py"],
        )

        # Build graph
        builder = TraceGraphBuilder(repo_root=tmp_path)
        builder.add_requirements(requirements)
        test_nodes = create_test_nodes(result, repo_root=fixtures_dir.parent.parent)
        builder.add_test_coverage(test_nodes)

        graph, validation = builder.build_and_validate()

        # Should have broken link warnings (no marker to suppress them)
        broken_link_warnings = [
            w for w in validation.warnings if "Broken link" in w
        ]
        assert len(broken_link_warnings) > 0

        # Should have no info messages (nothing suppressed)
        info_messages = [
            i for i in validation.info if "Expected broken link" in i
        ]
        assert len(info_messages) == 0
