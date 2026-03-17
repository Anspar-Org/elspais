# Validates: REQ-p00003-A, REQ-p00003-B
"""Tests for test_refs_grouped in _get_node_data()."""

import json
from pathlib import Path

import pytest

from elspais.graph import NodeKind


class TestTraceGroupedRefs:
    """Integration tests for test_refs_grouped field in _get_node_data()."""

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        """Create a project with spec, tests, and config."""
        # Spec directory with a requirement that has assertions
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: Grouped Refs Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A requirement to test grouped refs.

## Assertions

A. The system SHALL validate input.
B. The system SHALL produce output.
C. The system SHALL log events.

*End* *Grouped Refs Requirement* | **Hash**: abcd1234
"""
        )

        # Test directory with test files
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Test file targeting specific assertions via Validates comments
        test_assertion_a = test_dir / "test_input_validation.py"
        test_assertion_a.write_text(
            """# Validates: REQ-p00001-A
def test_REQ_p00001_A_validates_input():
    pass
"""
        )

        # Test file targeting assertion B
        test_assertion_b = test_dir / "test_output.py"
        test_assertion_b.write_text(
            """# Validates: REQ-p00001-B
def test_REQ_p00001_B_produces_output():
    pass
"""
        )

        # Test file targeting whole requirement (no assertion)
        test_whole_req = test_dir / "test_whole_req.py"
        test_whole_req.write_text(
            """# Validates: REQ-p00001
def test_REQ_p00001_general():
    pass
"""
        )

        # Test file targeting multiple assertions (A and C)
        test_multi = test_dir / "test_multi_target.py"
        test_multi.write_text(
            """# Validates: REQ-p00001-A, REQ-p00001-C
def test_REQ_p00001_A_and_C():
    pass
"""
        )

        # Config file
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """[project]
name = "test-grouped-refs"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"

[references]
enabled = true

[references.defaults]
multi_assertion_separator = "+"

[testing]
enabled = true
test_dirs = ["tests"]
patterns = ["test_*.py"]
"""
        )

        return tmp_path

    def _build_and_get_node_data(self, project_dir: Path) -> dict:
        """Build graph and return _get_node_data for REQ-p00001."""
        from elspais.commands.trace import _get_node_data
        from elspais.graph.factory import build_graph

        config_path = project_dir / ".elspais.toml"
        spec_dir = project_dir / "spec"

        graph = build_graph(
            spec_dirs=[spec_dir],
            config_path=config_path,
            repo_root=project_dir,
            scan_code=False,
            scan_tests=True,
        )

        # Find REQ-p00001
        req_node = None
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            if node.id == "REQ-p00001":
                req_node = node
                break

        assert req_node is not None, "REQ-p00001 not found in graph"
        return _get_node_data(req_node, graph)

    def test_whole_requirement_tests_under_star_key(self, project_dir: Path):
        """Whole-requirement tests (no assertion target) appear under '*' key."""
        data = self._build_and_get_node_data(project_dir)
        grouped = data["test_refs_grouped"]
        assert "*" in grouped, f"Expected '*' key in grouped refs, got: {grouped}"
        # The whole-req test should be under "*"
        star_ids = grouped["*"]
        assert any(
            "test_whole_req" in tid for tid in star_ids
        ), f"Expected test_whole_req under '*', got: {star_ids}"

    def test_assertion_targeted_tests_under_label_keys(self, project_dir: Path):
        """Assertion-targeted tests appear under their label keys."""
        data = self._build_and_get_node_data(project_dir)
        grouped = data["test_refs_grouped"]
        assert "A" in grouped, f"Expected 'A' key in grouped refs, got: {grouped}"
        assert "B" in grouped, f"Expected 'B' key in grouped refs, got: {grouped}"

    def test_multi_target_tests_appear_under_each_assertion(self, project_dir: Path):
        """Multi-target tests appear under each targeted assertion."""
        data = self._build_and_get_node_data(project_dir)
        grouped = data["test_refs_grouped"]
        # The multi-target test (A+C) should appear under both A and C
        assert "A" in grouped
        assert "C" in grouped
        a_ids = grouped["A"]
        c_ids = grouped["C"]
        # test_multi_target should be in both
        assert any(
            "test_multi_target" in tid for tid in a_ids
        ), f"Expected test_multi_target under 'A', got: {a_ids}"
        assert any(
            "test_multi_target" in tid for tid in c_ids
        ), f"Expected test_multi_target under 'C', got: {c_ids}"

    def test_flat_test_refs_still_populated(self, project_dir: Path):
        """The flat test_refs list is still populated with all test IDs."""
        data = self._build_and_get_node_data(project_dir)
        test_refs = data["test_refs"]
        assert len(test_refs) > 0, "Expected non-empty test_refs"
        # Should contain IDs from all test files
        assert any("test_input_validation" in tid for tid in test_refs)
        assert any("test_whole_req" in tid for tid in test_refs)

    def test_no_tests_gives_empty_grouped(self, tmp_path: Path):
        """A requirement with no tests has empty test_refs_grouped."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: Lonely Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A requirement with no tests.

## Assertions

A. The system SHALL be alone.

*End* *Lonely Requirement* | **Hash**: abcd1234
"""
        )

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """[project]
name = "test-no-tests"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"

[references]
enabled = true

[references.defaults]
multi_assertion_separator = "+"

[testing]
enabled = false
"""
        )

        from elspais.commands.trace import _get_node_data
        from elspais.graph.factory import build_graph

        graph = build_graph(
            spec_dirs=[spec_dir],
            config_path=config_file,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
        )

        req_node = None
        for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            if node.id == "REQ-p00001":
                req_node = node
                break

        assert req_node is not None
        data = _get_node_data(req_node, graph)
        assert data["test_refs_grouped"] == {}
        assert data["test_refs"] == []


class TestMarkdownGroupedRefs:
    """Integration tests for grouped test refs in format_markdown() output."""

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        """Create a project with spec, tests, and config."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: Grouped Refs Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A requirement to test grouped refs.

## Assertions

A. The system SHALL validate input.
B. The system SHALL produce output.
C. The system SHALL log events.

*End* *Grouped Refs Requirement* | **Hash**: abcd1234
"""
        )

        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Test targeting assertion A
        (test_dir / "test_input_validation.py").write_text(
            """# Validates: REQ-p00001-A
def test_REQ_p00001_A_validates_input():
    pass
"""
        )

        # Test targeting assertion B
        (test_dir / "test_output.py").write_text(
            """# Validates: REQ-p00001-B
def test_REQ_p00001_B_produces_output():
    pass
"""
        )

        # Whole-requirement test (no assertion)
        (test_dir / "test_whole_req.py").write_text(
            """# Validates: REQ-p00001
def test_REQ_p00001_general():
    pass
"""
        )

        # Multi-target test (A and C)
        (test_dir / "test_multi_target.py").write_text(
            """# Validates: REQ-p00001-A, REQ-p00001-C
def test_REQ_p00001_A_and_C():
    pass
"""
        )

        # Another test targeting assertion A for count checks
        (test_dir / "test_input_extra.py").write_text(
            """# Validates: REQ-p00001-A
def test_REQ_p00001_A_extra_check():
    pass
"""
        )

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """[project]
name = "test-md-grouped-refs"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"

[references]
enabled = true

[references.defaults]
multi_assertion_separator = "+"

[testing]
enabled = true
test_dirs = ["tests"]
patterns = ["test_*.py"]
"""
        )

        return tmp_path

    def _build_and_format(self, project_dir: Path) -> str:
        """Build graph and return markdown output as a single string."""
        from elspais.commands.trace import ReportPreset, format_markdown
        from elspais.graph.factory import build_graph

        config_path = project_dir / ".elspais.toml"
        spec_dir = project_dir / "spec"

        graph = build_graph(
            spec_dirs=[spec_dir],
            config_path=config_path,
            repo_root=project_dir,
            scan_code=False,
            scan_tests=True,
        )

        preset = ReportPreset(
            name="test",
            columns=["id", "title", "level", "status"],
            include_test_refs=True,
        )
        return "\n".join(format_markdown(graph, preset))

    def test_markdown_groups_by_assertion(self, project_dir: Path):
        """Output contains Whole-requirement, A, and B assertion group labels."""
        output = self._build_and_format(project_dir)
        assert "**Whole-requirement**" in output
        assert "**A**" in output
        assert "**B**" in output

    def test_markdown_whole_req_listed_first(self, project_dir: Path):
        """Whole-requirement group appears before assertion-specific labels."""
        output = self._build_and_format(project_dir)
        whole_pos = output.index("**Whole-requirement**")
        a_pos = output.index("**A**")
        b_pos = output.index("**B**")
        assert whole_pos < a_pos, "Whole-requirement should appear before A"
        assert whole_pos < b_pos, "Whole-requirement should appear before B"

    def test_markdown_counts_in_headers(self, project_dir: Path):
        """Group headers include correct counts."""
        output = self._build_and_format(project_dir)
        # Each test file produces both file-level and function-level refs
        # A has: test_input_validation (2), test_multi_target (2), test_input_extra (2) = 6
        assert "**A** (6):" in output
        # B has: test_output (2) = 2
        assert "**B** (2):" in output
        # C has: test_multi_target file-level ref only = 1
        # (multi-target file ref counts once for C)
        assert "**C** (" in output


class TestHtmlGroupedRefs:
    """Integration tests for grouped test refs in format_html() output."""

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        """Create a project with spec, tests, and config."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: Grouped Refs Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A requirement to test grouped refs.

## Assertions

A. The system SHALL validate input.
B. The system SHALL produce output.
C. The system SHALL log events.

*End* *Grouped Refs Requirement* | **Hash**: abcd1234
"""
        )

        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Test targeting assertion A
        (test_dir / "test_input_validation.py").write_text(
            """# Validates: REQ-p00001-A
def test_REQ_p00001_A_validates_input():
    pass
"""
        )

        # Test targeting assertion B
        (test_dir / "test_output.py").write_text(
            """# Validates: REQ-p00001-B
def test_REQ_p00001_B_produces_output():
    pass
"""
        )

        # Whole-requirement test (no assertion)
        (test_dir / "test_whole_req.py").write_text(
            """# Validates: REQ-p00001
def test_REQ_p00001_general():
    pass
"""
        )

        # Multi-target test (A and C)
        (test_dir / "test_multi_target.py").write_text(
            """# Validates: REQ-p00001-A, REQ-p00001-C
def test_REQ_p00001_A_and_C():
    pass
"""
        )

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """[project]
name = "test-html-grouped-refs"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"

[references]
enabled = true

[references.defaults]
multi_assertion_separator = "+"

[testing]
enabled = true
test_dirs = ["tests"]
patterns = ["test_*.py"]
"""
        )

        return tmp_path

    def _build_and_format(self, project_dir: Path) -> str:
        """Build graph and return HTML output as a single string."""
        from elspais.commands.trace import ReportPreset, format_html
        from elspais.graph.factory import build_graph

        config_path = project_dir / ".elspais.toml"
        spec_dir = project_dir / "spec"

        graph = build_graph(
            spec_dirs=[spec_dir],
            config_path=config_path,
            repo_root=project_dir,
            scan_code=False,
            scan_tests=True,
        )

        preset = ReportPreset(
            name="test",
            columns=["id", "title", "level", "status"],
            include_test_refs=True,
        )
        return "\n".join(format_html(graph, preset))

    def test_html_groups_by_assertion(self, project_dir: Path):
        """Output contains Whole-requirement, A, and B assertion group labels."""
        output = self._build_and_format(project_dir)
        assert "<strong>Whole-requirement</strong>" in output
        assert "<strong>A</strong>" in output
        assert "<strong>B</strong>" in output

    def test_html_test_refs_in_code_tags(self, project_dir: Path):
        """Each test ref is wrapped in <code> tags."""
        output = self._build_and_format(project_dir)
        assert "<code>" in output
        assert "</code>" in output
        # Verify specific test refs are in code tags
        assert "<code>test" in output or "<code>tests/" in output


class TestJsonGroupedRefs:
    """Integration tests for grouped test refs in format_json() output."""

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        """Create a project with spec, tests, and config."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: Grouped Refs Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A requirement to test grouped refs.

## Assertions

A. The system SHALL validate input.
B. The system SHALL produce output.
C. The system SHALL log events.

*End* *Grouped Refs Requirement* | **Hash**: abcd1234
"""
        )

        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Test targeting assertion A
        (test_dir / "test_input_validation.py").write_text(
            """# Validates: REQ-p00001-A
def test_REQ_p00001_A_validates_input():
    pass
"""
        )

        # Test targeting assertion B
        (test_dir / "test_output.py").write_text(
            """# Validates: REQ-p00001-B
def test_REQ_p00001_B_produces_output():
    pass
"""
        )

        # Whole-requirement test (no assertion)
        (test_dir / "test_whole_req.py").write_text(
            """# Validates: REQ-p00001
def test_REQ_p00001_general():
    pass
"""
        )

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """[project]
name = "test-json-grouped-refs"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"

[references]
enabled = true

[references.defaults]
multi_assertion_separator = "+"

[testing]
enabled = true
test_dirs = ["tests"]
patterns = ["test_*.py"]
"""
        )

        return tmp_path

    def _build_and_format_json(self, project_dir: Path) -> list[dict]:
        """Build graph and return parsed JSON output."""
        from elspais.commands.trace import ReportPreset, format_json
        from elspais.graph.factory import build_graph

        config_path = project_dir / ".elspais.toml"
        spec_dir = project_dir / "spec"

        graph = build_graph(
            spec_dirs=[spec_dir],
            config_path=config_path,
            repo_root=project_dir,
            scan_code=False,
            scan_tests=True,
        )

        preset = ReportPreset(
            name="test",
            columns=["id", "title", "level", "status"],
            include_test_refs=True,
        )
        raw = "\n".join(format_json(graph, preset))
        return json.loads(raw)

    def test_json_test_refs_is_dict(self, project_dir: Path):
        """test_refs in JSON output is a dict with '*', 'A', 'B' keys."""
        nodes = self._build_and_format_json(project_dir)
        req = next(n for n in nodes if n["id"] == "REQ-p00001")
        test_refs = req["test_refs"]
        assert isinstance(test_refs, dict), f"Expected dict, got {type(test_refs)}"
        assert "*" in test_refs, f"Expected '*' key, got keys: {list(test_refs.keys())}"
        assert "A" in test_refs, f"Expected 'A' key, got keys: {list(test_refs.keys())}"
        assert "B" in test_refs, f"Expected 'B' key, got keys: {list(test_refs.keys())}"

    def test_json_grouped_refs_content(self, project_dir: Path):
        """Grouped refs contain correct test ID counts per key."""
        nodes = self._build_and_format_json(project_dir)
        req = next(n for n in nodes if n["id"] == "REQ-p00001")
        test_refs = req["test_refs"]
        # '*' should have whole-req tests
        assert len(test_refs["*"]) >= 1, f"Expected at least 1 test under '*', got {test_refs['*']}"
        assert any("test_whole_req" in tid for tid in test_refs["*"])
        # 'A' should have test_input_validation refs
        assert len(test_refs["A"]) >= 1, f"Expected at least 1 test under 'A', got {test_refs['A']}"
        assert any("test_input_validation" in tid for tid in test_refs["A"])
        # 'B' should have test_output refs
        assert len(test_refs["B"]) >= 1, f"Expected at least 1 test under 'B', got {test_refs['B']}"
        assert any("test_output" in tid for tid in test_refs["B"])


class TestCsvGroupedRefs:
    """Integration tests for grouped test refs in format_csv() output."""

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        """Create a project with spec, tests, and config."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: Grouped Refs Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A requirement to test grouped refs.

## Assertions

A. The system SHALL validate input.
B. The system SHALL produce output.
C. The system SHALL log events.

*End* *Grouped Refs Requirement* | **Hash**: abcd1234
"""
        )

        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Test targeting assertion A
        (test_dir / "test_input_validation.py").write_text(
            """# Validates: REQ-p00001-A
def test_REQ_p00001_A_validates_input():
    pass
"""
        )

        # Test targeting assertion B
        (test_dir / "test_output.py").write_text(
            """# Validates: REQ-p00001-B
def test_REQ_p00001_B_produces_output():
    pass
"""
        )

        # Whole-requirement test (no assertion)
        (test_dir / "test_whole_req.py").write_text(
            """# Validates: REQ-p00001
def test_REQ_p00001_general():
    pass
"""
        )

        # Multi-target test (A and C)
        (test_dir / "test_multi_target.py").write_text(
            """# Validates: REQ-p00001-A, REQ-p00001-C
def test_REQ_p00001_A_and_C():
    pass
"""
        )

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """[project]
name = "test-csv-grouped-refs"

[requirements]
spec_dirs = ["spec"]

[requirements.id_pattern]
prefix = "REQ"
separator = "-"
pattern = "REQ-[a-z]\\\\d{5}"

[references]
enabled = true

[references.defaults]
multi_assertion_separator = "+"

[testing]
enabled = true
test_dirs = ["tests"]
patterns = ["test_*.py"]
"""
        )

        return tmp_path

    def _build_and_format_csv(self, project_dir: Path, include_test_refs: bool = True) -> list[str]:
        """Build graph and return CSV output as a list of lines."""
        from elspais.commands.trace import ReportPreset, format_csv
        from elspais.graph.factory import build_graph

        config_path = project_dir / ".elspais.toml"
        spec_dir = project_dir / "spec"

        graph = build_graph(
            spec_dirs=[spec_dir],
            config_path=config_path,
            repo_root=project_dir,
            scan_code=False,
            scan_tests=True,
        )

        preset = ReportPreset(
            name="test",
            columns=["id", "title", "level", "status"],
            include_test_refs=include_test_refs,
        )
        return list(format_csv(graph, preset))

    def test_csv_has_kind_column(self, project_dir: Path):
        """CSV header starts with 'Kind,' when test refs enabled."""
        lines = self._build_and_format_csv(project_dir, include_test_refs=True)
        header = lines[0]
        assert header.startswith("Kind,"), f"Expected header to start with 'Kind,', got: {header}"

    def test_csv_req_row_kind(self, project_dir: Path):
        """Requirement rows have Kind=REQ."""
        lines = self._build_and_format_csv(project_dir, include_test_refs=True)
        req_rows = [line for line in lines[1:] if line.startswith("REQ,")]
        assert len(req_rows) >= 1, f"Expected at least one REQ row, got lines: {lines}"

    def test_csv_test_rows_follow_req(self, project_dir: Path):
        """TEST rows follow their parent REQ row."""
        lines = self._build_and_format_csv(project_dir, include_test_refs=True)
        req_idx = None
        for i, line in enumerate(lines):
            if line.startswith("REQ,"):
                req_idx = i
                break
        assert req_idx is not None, "No REQ row found"
        test_rows = [i for i, line in enumerate(lines) if line.startswith("TEST,")]
        assert len(test_rows) >= 1, f"Expected TEST rows, got lines: {lines}"
        for tidx in test_rows:
            assert tidx > req_idx, f"TEST row at {tidx} should come after REQ row at {req_idx}"

    def test_csv_test_row_has_assertion_label(self, project_dir: Path):
        """TEST rows include assertion label (*, A, B, etc.)."""
        lines = self._build_and_format_csv(project_dir, include_test_refs=True)
        test_rows = [line for line in lines if line.startswith("TEST,")]
        assert len(test_rows) >= 1, "Expected TEST rows"
        labels_found = set()
        for row in test_rows:
            parts = row.split(",")
            # Assertion label is second-to-last column
            label = parts[-2]
            labels_found.add(label)
        assert "*" in labels_found, f"Expected '*' label in TEST rows, got labels: {labels_found}"
        assert "A" in labels_found, f"Expected 'A' label in TEST rows, got labels: {labels_found}"

    def test_csv_no_kind_column_without_test_refs(self, project_dir: Path):
        """Kind column NOT added when test refs not included."""
        lines = self._build_and_format_csv(project_dir, include_test_refs=False)
        header = lines[0]
        assert not header.startswith(
            "Kind,"
        ), f"Header should not start with 'Kind,' when test refs disabled, got: {header}"
        for line in lines[1:]:
            assert not line.startswith("REQ,"), f"No REQ kind expected without test refs: {line}"
            assert not line.startswith("TEST,"), f"No TEST kind expected without test refs: {line}"
