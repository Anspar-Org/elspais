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
from elspais.graph.GraphNode import make_file_id


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


def _unit_folder(root: Path) -> Path:
    """Create and return the output area of the `unit` target."""
    folder = root / ".results" / "unit"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


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
coverage = "lcov.info"
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "main.py")
        _write_lcov(tmp_path / ".results" / "unit" / "lcov.info", "src/main.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        # Find the FILE node for src/main.py
        file_node = None
        for node in graph.iter_by_kind(NodeKind.FILE):
            if node.id == make_file_id("REQ", "src/main.py"):
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
            if node.id == make_file_id("REQ", "src/main.py"):
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
        _write_lcov(tmp_path / ".results" / "unit" / "lcov.info", "other/missing.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        # FILE node for src/main.py should NOT have coverage fields
        file_node = None
        for node in graph.iter_by_kind(NodeKind.FILE):
            if node.id == make_file_id("REQ", "src/main.py"):
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
        _unit_folder(tmp_path).joinpath("coverage.json").write_text(
            json.dumps(cov_data), encoding="utf-8"
        )

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        file_node = None
        for node in graph.iter_by_kind(NodeKind.FILE):
            if node.id == make_file_id("REQ", "src/main.py"):
                file_node = node
                break

        assert file_node is not None
        line_cov = file_node.get_field("line_coverage")
        assert line_cov == {1: 1, 2: 1, 3: 0}
        assert file_node.get_field("executable_lines") == 3

    # Verifies: REQ-d00254-G, REQ-d00258-W
    def test_coverage_json_contexts_annotate_line_contexts(self, tmp_path: Path) -> None:
        """A coverage.json with a per-line `contexts` map (coverage.py
        dynamic contexts, e.g. from `--cov-context=test` + `show_contexts`)
        annotates the FILE node with a `line_contexts` field."""
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
        _unit_folder(tmp_path).joinpath("coverage.json").write_text(
            json.dumps(cov_data), encoding="utf-8"
        )

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        file_node = None
        for node in graph.iter_by_kind(NodeKind.FILE):
            if node.id == make_file_id("REQ", "src/main.py"):
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
        _unit_folder(tmp_path).joinpath("coverage.json").write_text(
            json.dumps(cov_data), encoding="utf-8"
        )

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        file_node = None
        for node in graph.iter_by_kind(NodeKind.FILE):
            if node.id == make_file_id("REQ", "src/main.py"):
                file_node = node
                break

        assert file_node is not None
        assert file_node.get_field("line_contexts") is None

    # Verifies: REQ-d00254-G, REQ-d00258-W
    def test_coverage_sqlite_annotates_file_node_and_contexts(self, tmp_path: Path) -> None:
        """A `.coverage` SQLite target (coverage.py's native data file)
        annotates FILE nodes with line_coverage AND line_contexts, restoring
        per-test attribution without the JSON `show_contexts` blowup."""
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

        cov_path = _unit_folder(tmp_path) / ".coverage"
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
            if node.id == make_file_id("REQ", "src/main.py"):
                file_node = node
                break

        assert file_node is not None, "FILE node for src/main.py should exist"
        line_cov = file_node.get_field("line_coverage")
        assert line_cov is not None
        assert line_cov.get(2) == 1  # `def work(): pass` body line

        line_contexts = file_node.get_field("line_contexts")
        assert line_contexts is not None
        assert any("test_work" in c for c in line_contexts.get(2, [])), (
            f"expected test_work context on line 2, got {line_contexts}"
        )

    # Verifies: REQ-d00254-G, REQ-d00258-W
    def test_coverage_sqlite_unresolvable_file_contexts_not_materialized(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Measured files that don't resolve to a FILE node (e.g. sources
        outside the scanned dirs) must never have their per-line context
        lists materialized -- the factory passes a FILE-node-resolution
        predicate to the sqlite parser so contexts_by_lineno() is only
        called for resolvable files."""
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

        cov_path = _unit_folder(tmp_path) / ".coverage"
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
        assert str(outside_path) not in queried, (
            "unresolvable measured file's contexts must never be materialized"
        )

        # And the resolvable file's annotation still works end-to-end.
        file_node = graph.find_by_id(make_file_id("REQ", "src/main.py"))
        assert file_node is not None
        assert file_node.get_field("line_contexts") is not None


def _write_cwd_project(
    root: Path,
    code_files: list[str],
    *,
    cwd: str | None,
    coverage: str = "lcov.info",
    code_dirs: list[str] | None = None,
    extra: str = "",
) -> Path:
    """Write a project whose `unit` target may run in a working directory.

    Returns the config path. Every entry of *code_files* is a repo-relative
    path written as a scanned code file. *extra* is appended to the target.
    """
    import json

    dirs = code_dirs or sorted({Path(p).parent.as_posix() for p in code_files})
    cwd_line = f'cwd = "{cwd}"\n' if cwd is not None else ""
    config_file = root / ".elspais.toml"
    config_file.write_text(
        f"""\
[project]
name = "test-coverage-cwd"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = {json.dumps(dirs)}

[[scanning.test.targets]]
name = "unit"
coverage = "{coverage}"
{cwd_line}{extra}""",
        encoding="utf-8",
    )
    _write_spec(root / "spec")
    for rel in code_files:
        _write_code_file(root / rel)
    return config_file


def _credited(graph, namespace: str = "REQ") -> dict[str, object]:
    """Map each FILE node carrying line_coverage to that coverage, by repo path."""
    prefix = f"file:{namespace}:"
    return {
        node.id[len(prefix) :]: node.get_field("line_coverage")
        for node in graph.iter_by_kind(NodeKind.FILE)
        if node.get_field("line_coverage") is not None and node.id.startswith(prefix)
    }


class TestCoveragePathsResolveAgainstTargetWorkingDirectory:
    """A coverage artifact's relative source paths are read from the
    directory its target ran in, not from where the artifact is stored."""

    # Verifies: REQ-d00254-Y
    @pytest.mark.parametrize(
        "cwd,code_file,recorded",
        [
            # The target ran in app/: the tool recorded lib/x.py.
            ("app", "app/lib/x.py", "lib/x.py"),
            # No cwd: the target ran at the repository root.
            (None, "lib/x.py", "lib/x.py"),
        ],
        ids=["cwd-target", "repo-root-target"],
    )
    def test_relative_lcov_path_credits_file_under_working_dir(
        self, tmp_path: Path, cwd: str | None, code_file: str, recorded: str
    ) -> None:
        config_file = _write_cwd_project(tmp_path, [code_file], cwd=cwd)
        _write_lcov(_unit_folder(tmp_path) / "lcov.info", recorded)

        graph = build_graph(config_path=config_file, repo_root=tmp_path, scan_tests=False)

        assert _credited(graph) == {code_file: {1: 1, 2: 1}}
        node = graph.find_by_id(make_file_id("REQ", code_file))
        assert node is not None
        assert node.get_field("executable_lines") == 2

    # Verifies: REQ-d00254-Y
    def test_relative_coverage_json_path_credits_file_under_working_dir(
        self, tmp_path: Path
    ) -> None:
        import json

        config_file = _write_cwd_project(
            tmp_path, ["app/lib/x.py"], cwd="app", coverage="coverage.json"
        )
        cov_data = {
            "files": {
                "lib/x.py": {
                    "executed_lines": [1, 2],
                    "missing_lines": [3],
                    "summary": {"num_statements": 3, "covered_lines": 2},
                }
            }
        }
        _unit_folder(tmp_path).joinpath("coverage.json").write_text(
            json.dumps(cov_data), encoding="utf-8"
        )

        graph = build_graph(config_path=config_file, repo_root=tmp_path, scan_tests=False)

        assert _credited(graph) == {"app/lib/x.py": {1: 1, 2: 1, 3: 0}}

    # Verifies: REQ-d00254-Y
    def test_absolute_path_is_read_as_it_stands(self, tmp_path: Path) -> None:
        config_file = _write_cwd_project(tmp_path, ["app/lib/x.py"], cwd="app")
        _write_lcov(_unit_folder(tmp_path) / "lcov.info", str(tmp_path / "app" / "lib" / "x.py"))

        graph = build_graph(config_path=config_file, repo_root=tmp_path, scan_tests=False)

        assert _credited(graph) == {"app/lib/x.py": {1: 1, 2: 1}}

    # Verifies: REQ-d00254-Y
    @pytest.mark.parametrize(
        "recorded",
        [
            "lib/missing.py",  # names no scanned file under app/
            "../../outside.py",  # escapes the repository
            "app/lib/x.py",  # repo-relative spelling: reads as app/app/lib/x.py
        ],
        ids=["missing", "escapes-repo", "repo-relative-spelling"],
    )
    def test_path_naming_no_file_under_working_dir_credits_nothing(
        self, tmp_path: Path, recorded: str
    ) -> None:
        config_file = _write_cwd_project(tmp_path, ["app/lib/x.py"], cwd="app")
        # A file the escaping path would reach if it were not confined.
        (tmp_path.parent / "outside.py").write_text("x = 1\n", encoding="utf-8")
        _write_lcov(_unit_folder(tmp_path) / "lcov.info", recorded)

        graph = build_graph(config_path=config_file, repo_root=tmp_path, scan_tests=False)

        assert _credited(graph) == {}

    # Verifies: REQ-d00254-Y
    def test_relative_path_is_not_also_read_from_repo_root(self, tmp_path: Path) -> None:
        """With a scanned file at the same path from the root, the working
        directory alone decides which file is credited."""
        config_file = _write_cwd_project(
            tmp_path,
            ["app/lib/x.py", "lib/x.py"],
            cwd="app",
            code_dirs=["app/lib", "lib"],
        )
        _write_lcov(_unit_folder(tmp_path) / "lcov.info", "lib/x.py")

        graph = build_graph(config_path=config_file, repo_root=tmp_path, scan_tests=False)

        assert graph.find_by_id(make_file_id("REQ", "lib/x.py")) is not None
        assert _credited(graph) == {"app/lib/x.py": {1: 1, 2: 1}}

    # Verifies: REQ-d00254-Y
    def test_federation_member_reads_from_its_own_target_working_dir(self, tmp_path: Path) -> None:
        from tests.federation_repos import _git, make_repo

        lib_toml = """version = 5

[project]
name = "lib"
namespace = "LIB"

[levels.prd]
rank = 1
implements = []

[levels.dev]
rank = 2
implements = ["prd", "dev"]

[scanning.code]
directories = ["pkg/lib"]

[[scanning.test.targets]]
name = "unit"
coverage = "lcov.info"
cwd = "pkg"
"""
        root_toml = """version = 5

[project]
name = "root"
namespace = "ROOT"

[levels.prd]
rank = 1
implements = []

[levels.dev]
rank = 2
implements = ["prd", "dev"]

[associates.lib]
path = "../lib"
namespace = "LIB"
"""
        lib = make_repo(tmp_path, "lib", namespace="LIB", config_text=lib_toml)
        _write_code_file(lib / "pkg" / "lib" / "x.py", req_id="LIB-d00001")
        _write_lcov(lib / ".results" / "unit" / "lcov.info", "lib/x.py")
        _git(lib, "add", "-A")
        _git(lib, "commit", "-m", "code")
        root = make_repo(tmp_path, "root", namespace="ROOT", config_text=root_toml)

        graph = build_graph(repo_root=root)

        node = graph.find_by_id(make_file_id("LIB", "pkg/lib/x.py"))
        assert node is not None
        assert node.get_field("line_coverage") == {1: 1, 2: 1}


def _write_coverage(root: Path, fmt: str, recorded: str) -> str:
    """Write the `unit` target's coverage in *fmt*, recording *recorded*; return its name."""
    import json

    if fmt == "lcov":
        _write_lcov(_unit_folder(root) / "lcov.info", recorded)
        return "lcov.info"
    cov_data = {
        "files": {
            recorded: {
                "executed_lines": [1, 2],
                "missing_lines": [],
                "summary": {"num_statements": 2, "covered_lines": 2},
            }
        }
    }
    _unit_folder(root).joinpath("coverage.json").write_text(json.dumps(cov_data), encoding="utf-8")
    return "coverage.json"


class TestCoveragePathsFollowTheDeclaredOrigin:
    """A coverage artifact's relative paths are read from the origin its
    reporter declares, or from the one its target declares in its place."""

    # Verifies: REQ-d00327-B, REQ-d00254-Y
    @pytest.mark.parametrize("fmt", ["lcov", "coverage-json"])
    def test_a_target_declaring_the_root_reads_repo_relative_coverage(
        self, tmp_path: Path, fmt: str
    ) -> None:
        """The spelling that credits nothing under the reporter's own origin
        credits its file once the target declares the repository root."""
        coverage = _write_coverage(tmp_path, fmt, "app/lib/x.py")
        config_file = _write_cwd_project(
            tmp_path,
            ["app/lib/x.py"],
            cwd="app",
            coverage=coverage,
            extra='coverage_origin = "repository-root"\n',
        )

        graph = build_graph(config_path=config_file, repo_root=tmp_path, scan_tests=False)

        assert _credited(graph) == {"app/lib/x.py": {1: 1, 2: 1}}

    # Verifies: REQ-d00327-B, REQ-d00254-Y
    @pytest.mark.parametrize(
        "declared,credited",
        [
            ("", "app/lib/x.py"),
            ("working-directory", "app/lib/x.py"),
            ("repository-root", "lib/x.py"),
        ],
        ids=["reporter-default", "working-directory", "repository-root"],
    )
    def test_the_declared_origin_alone_decides_which_file_is_credited(
        self, tmp_path: Path, declared: str, credited: str
    ) -> None:
        """With a scanned file at the recorded path from either origin, the
        origin that applies decides, and the other is never also tried."""
        extra = f'coverage_origin = "{declared}"\n' if declared else ""
        config_file = _write_cwd_project(
            tmp_path,
            ["app/lib/x.py", "lib/x.py"],
            cwd="app",
            code_dirs=["app/lib", "lib"],
            extra=extra,
        )
        _write_lcov(_unit_folder(tmp_path) / "lcov.info", "lib/x.py")

        graph = build_graph(config_path=config_file, repo_root=tmp_path, scan_tests=False)

        assert _credited(graph) == {credited: {1: 1, 2: 1}}

    # Verifies: REQ-d00327-B, REQ-d00327-E
    def test_the_targets_results_origin_does_not_move_its_coverage(self, tmp_path: Path) -> None:
        """Coverage and results are declared apart: a results origin says
        nothing about where the target's coverage starts."""
        config_file = _write_cwd_project(
            tmp_path,
            ["app/lib/x.py"],
            cwd="app",
            extra='results_origin = "repository-root"\n',
        )
        _write_lcov(_unit_folder(tmp_path) / "lcov.info", "lib/x.py")

        graph = build_graph(config_path=config_file, repo_root=tmp_path, scan_tests=False)

        assert _credited(graph) == {"app/lib/x.py": {1: 1, 2: 1}}
