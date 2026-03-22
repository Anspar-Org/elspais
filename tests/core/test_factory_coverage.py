# Validates REQ-d00054-A
"""Tests for coverage file scanning and FILE node annotation in build_graph().

Verifies that when [scanning.coverage] is configured with file_patterns,
build_graph() parses coverage files and annotates matching FILE nodes
with line_coverage and executable_lines fields.
"""

from pathlib import Path

from elspais.graph import NodeKind
from elspais.graph.factory import build_graph


def _write_spec(spec_dir: Path, req_id: str = "REQ-p00001", title: str = "Test Req") -> None:
    """Write a minimal valid spec file with a single requirement."""
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "reqs.md").write_text(
        f"""\
### {req_id}: {title}

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *{title}* | **Hash**: ________
""",
        encoding="utf-8",
    )


def _write_code_file(file_path: Path, req_id: str = "REQ-p00001") -> None:
    """Write a Python file with an Implements comment."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        f"# Implements: {req_id}\ndef work(): pass\n",
        encoding="utf-8",
    )


def _write_lcov(lcov_path: Path, source_file: str) -> None:
    """Write a minimal lcov.info file covering the given source file."""
    lcov_path.parent.mkdir(parents=True, exist_ok=True)
    lcov_path.write_text(
        f"""\
SF:{source_file}
DA:1,1
DA:2,1
LF:2
LH:2
end_of_record
""",
        encoding="utf-8",
    )


class TestCoverageFileScanning:
    """Tests for [scanning.coverage] in build_graph()."""

    def test_lcov_annotates_file_node(self, tmp_path: Path) -> None:
        """Coverage data from lcov.info annotates FILE nodes with
        line_coverage and executable_lines fields."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-coverage"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[scanning.coverage]
file_patterns = ["coverage/lcov.info"]
directories = ["."]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "main.py")
        _write_lcov(tmp_path / "coverage" / "lcov.info", "src/main.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        # Find the FILE node for src/main.py
        file_node = None
        for node in graph.iter_by_kind(NodeKind.FILE):
            if node.id == "file:src/main.py":
                file_node = node
                break

        assert file_node is not None, "FILE node for src/main.py should exist"
        line_cov = file_node.get_field("line_coverage")
        assert line_cov is not None, "line_coverage should be set on FILE node"
        assert line_cov == {1: 1, 2: 1}

        exec_lines = file_node.get_field("executable_lines")
        assert exec_lines == 2

    def test_coverage_skipped_when_no_patterns(self, tmp_path: Path) -> None:
        """When no file_patterns are configured for coverage, no error occurs."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-no-coverage"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "main.py")

        # Should not raise
        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )
        # FILE node should exist but without coverage fields
        file_node = None
        for node in graph.iter_by_kind(NodeKind.FILE):
            if node.id == "file:src/main.py":
                file_node = node
                break

        assert file_node is not None
        assert file_node.get_field("line_coverage") is None

    def test_coverage_unmatched_file_skipped(self, tmp_path: Path) -> None:
        """Coverage data for files not in the graph is silently skipped."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-unmatched"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[scanning.coverage]
file_patterns = ["lcov.info"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "main.py")
        # Coverage for a file NOT in the scanned dirs
        _write_lcov(tmp_path / "lcov.info", "other/missing.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        # FILE node for src/main.py should NOT have coverage fields
        file_node = None
        for node in graph.iter_by_kind(NodeKind.FILE):
            if node.id == "file:src/main.py":
                file_node = node
                break

        assert file_node is not None
        assert file_node.get_field("line_coverage") is None

    def test_coverage_json_annotates_file_node(self, tmp_path: Path) -> None:
        """Coverage data from coverage.json annotates FILE nodes."""
        import json

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-cov-json"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[scanning.coverage]
file_patterns = ["coverage.json"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "main.py")

        cov_data = {
            "files": {
                "src/main.py": {
                    "executed_lines": [1, 2],
                    "missing_lines": [3],
                    "summary": {
                        "num_statements": 3,
                        "covered_lines": 2,
                    },
                }
            }
        }
        (tmp_path / "coverage.json").write_text(
            json.dumps(cov_data), encoding="utf-8"
        )

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        file_node = None
        for node in graph.iter_by_kind(NodeKind.FILE):
            if node.id == "file:src/main.py":
                file_node = node
                break

        assert file_node is not None
        line_cov = file_node.get_field("line_coverage")
        assert line_cov == {1: 1, 2: 1, 3: 0}
        assert file_node.get_field("executable_lines") == 3
