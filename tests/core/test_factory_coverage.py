# Validates REQ-d00054-A
"""Tests for coverage file scanning and FILE node annotation in build_graph().

Verifies that when a [[scanning.test.targets]] entry declares a coverage file,
build_graph() parses it and annotates matching FILE nodes with line_coverage
and executable_lines fields.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

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
    """Tests for target-driven coverage ingestion in build_graph()."""

    def test_lcov_annotates_file_node(self, tmp_path: Path) -> None:
        """Coverage data from lcov.info annotates FILE nodes with
        line_coverage and executable_lines fields."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-coverage"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[[scanning.test.targets]]
name = "unit"
coverage = "coverage/lcov.info"
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
namespace = "REQ"

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
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[[scanning.test.targets]]
name = "unit"
coverage = "lcov.info"
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
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[[scanning.test.targets]]
name = "unit"
coverage = "coverage.json"
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
        (tmp_path / "coverage.json").write_text(json.dumps(cov_data), encoding="utf-8")

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

    # Verifies: REQ-d00254-G, REQ-d00258-E
    def test_coverage_json_contexts_annotate_line_contexts(self, tmp_path: Path) -> None:
        """A coverage.json with a per-line `contexts` map (coverage.py
        dynamic contexts, e.g. from `--cov-context=test` + `show_contexts`)
        annotates the FILE node with a `line_contexts` field (CUR-1568)."""
        import json

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-cov-json-contexts"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[[scanning.test.targets]]
name = "unit"
coverage = "coverage.json"
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
                    "contexts": {
                        "1": ["tests/test_main.py::test_work|run"],
                        "2": ["tests/test_main.py::test_work|run"],
                    },
                }
            }
        }
        (tmp_path / "coverage.json").write_text(json.dumps(cov_data), encoding="utf-8")

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
        line_contexts = file_node.get_field("line_contexts")
        assert line_contexts == {
            1: ["tests/test_main.py::test_work|run"],
            2: ["tests/test_main.py::test_work|run"],
        }

    def test_coverage_json_no_contexts_leaves_line_contexts_unset(self, tmp_path: Path) -> None:
        """A coverage.json without a `contexts` key leaves line_contexts
        unset (backward compatible with existing aggregate reports)."""
        import json

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-cov-json-no-contexts"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[[scanning.test.targets]]
name = "unit"
coverage = "coverage.json"
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
                    "summary": {"num_statements": 3, "covered_lines": 2},
                }
            }
        }
        (tmp_path / "coverage.json").write_text(json.dumps(cov_data), encoding="utf-8")

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
        assert file_node.get_field("line_contexts") is None

    # Verifies: REQ-d00254-G, REQ-d00258-E
    def test_coverage_sqlite_annotates_file_node_and_contexts(self, tmp_path: Path) -> None:
        """A `.coverage` SQLite target (coverage.py's native data file)
        annotates FILE nodes with line_coverage AND line_contexts, restoring
        per-test attribution without the JSON `show_contexts` blowup
        (CUR-1568)."""
        coverage = pytest.importorskip("coverage")

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-cov-sqlite"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[[scanning.test.targets]]
name = "unit"
coverage = ".coverage"
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        code_path = tmp_path / "src" / "main.py"
        _write_code_file(code_path)

        cov_path = tmp_path / ".coverage"
        cov = coverage.Coverage(data_file=str(cov_path), source=[str(tmp_path / "src")])
        cov.start()
        try:
            spec_obj = importlib.util.spec_from_file_location(
                "factory_coverage_sqlite_fixture", str(code_path)
            )
            mod = importlib.util.module_from_spec(spec_obj)
            cov.switch_context("tests/test_main.py::test_work|run")
            spec_obj.loader.exec_module(mod)
            mod.work()
        finally:
            cov.stop()
        cov.save()

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

        assert file_node is not None, "FILE node for src/main.py should exist"
        line_cov = file_node.get_field("line_coverage")
        assert line_cov is not None
        assert line_cov.get(2) == 1  # `def work(): pass` body line

        line_contexts = file_node.get_field("line_contexts")
        assert line_contexts is not None
        assert any(
            "test_work" in c for c in line_contexts.get(2, [])
        ), f"expected test_work context on line 2, got {line_contexts}"

    # Verifies: REQ-d00254-G, REQ-d00258-E
    def test_coverage_sqlite_unresolvable_file_contexts_not_materialized(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Measured files that don't resolve to a FILE node (e.g. sources
        outside the scanned dirs) must never have their per-line context
        lists materialized -- the factory passes a FILE-node-resolution
        predicate to the sqlite parser so contexts_by_lineno() is only
        called for resolvable files (CUR-1568 hardening)."""
        coverage = pytest.importorskip("coverage")

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-cov-sqlite-lazy"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]

[[scanning.test.targets]]
name = "unit"
coverage = ".coverage"
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        code_path = tmp_path / "src" / "main.py"
        _write_code_file(code_path)
        # A second measured module OUTSIDE the scanned dirs -- no FILE node.
        outside_path = tmp_path / "other" / "helper.py"
        outside_path.parent.mkdir(parents=True, exist_ok=True)
        outside_path.write_text("def helper():\n    return 42\n", encoding="utf-8")

        cov_path = tmp_path / ".coverage"
        cov = coverage.Coverage(data_file=str(cov_path), source=[str(tmp_path)])
        cov.start()
        try:
            cov.switch_context("tests/test_main.py::test_work|run")
            for name, path in (
                ("factory_lazy_main", code_path),
                ("factory_lazy_helper", outside_path),
            ):
                spec_obj = importlib.util.spec_from_file_location(name, str(path))
                mod = importlib.util.module_from_spec(spec_obj)
                spec_obj.loader.exec_module(mod)
        finally:
            cov.stop()
        cov.save()

        queried: list[str] = []
        orig = coverage.CoverageData.contexts_by_lineno

        def _spy(self, filename):
            queried.append(filename)
            return orig(self, filename)

        monkeypatch.setattr(coverage.CoverageData, "contexts_by_lineno", _spy)

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        assert str(code_path) in queried, "resolvable file's contexts should be read"
        assert (
            str(outside_path) not in queried
        ), "unresolvable measured file's contexts must never be materialized"

        # And the resolvable file's annotation still works end-to-end.
        file_node = graph.find_by_id("file:src/main.py")
        assert file_node is not None
        assert file_node.get_field("line_contexts") is not None
