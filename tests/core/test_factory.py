# Verifies: REQ-d00212-Q, REQ-d00212-W
# Verifies: REQ-d00128-A, REQ-d00128-D, REQ-p00003-B
# Validates REQ-d00055-D, REQ-o00061-B
"""Tests for graph factory build_graph() — file selection and coverage annotation.

One mechanism decides whether a file is scanned: a scanning kind walks the
directories it declares, the ignore configuration excludes, and the kind's
declared patterns select among what is left. These tests pin that meaning for
the code and test kinds alike, and pin that a kind reaches nothing outside the
directories it declared. Also verifies that build_graph() annotates coverage
metrics on requirement nodes.
"""

import builtins
import fnmatch
import os
from pathlib import Path

import pytest

from elspais.graph import NodeKind
from elspais.graph.deserializer import SourceReadError
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import make_file_id
from elspais.graph.relations import EdgeKind


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


class TestCodeDirectoryScanning:
    """Tests for [directories].code scanning in build_graph()."""

    # Verifies: REQ-d00212-Q
    def test_REQ_d00212_Q_a_declared_code_directory_is_scanned(self, tmp_path: Path) -> None:
        """A code directory with no pattern declared beside it is still scanned.

        Declaring a directory is the whole of asking for it to be scanned; the
        patterns say which files inside it count, and their absence means the
        kind's defaults rather than nothing.
        """
        # Config with code dirs but NO scan_patterns
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-code-dirs"
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

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        assert len(code_nodes) > 0, (
            "[directories].code should produce CODE nodes even without scan_patterns"
        )
        # Verify the code node references our requirement
        code_ids = [n.id for n in code_nodes]
        has_ref = any("main.py" in cid for cid in code_ids)
        assert has_ref, f"Expected a CODE node from src/main.py, got: {code_ids}"

    # Verifies: REQ-d00212-W, REQ-d00241-F
    def test_REQ_d00212_W_code_patterns_reach_nothing_outside_declared_directories(
        self, tmp_path: Path
    ) -> None:
        """A path-shaped pattern selects within the declared directories only.

        A pattern naming a path outside them used to be resolved against the
        repository root, so `[scanning.code]` could reach a file no declared
        directory contained. It now selects among what the declared
        directories hold and nothing else -- and because it selects nothing
        here, the annotated file inside `src` is one the scan passed over,
        which is recorded rather than left to be inferred.
        """
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-patterns-stay-inside"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
file_patterns = ["tests/conftest.py"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "app.py")
        _write_code_file(tmp_path / "tests" / "conftest.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        code_ids = [n.id for n in graph.nodes_by_kind(NodeKind.CODE)]
        assert not any("conftest.py" in cid for cid in code_ids), (
            f"A code pattern must not reach outside [scanning.code].directories: {code_ids}"
        )
        assert graph.find_by_id(make_file_id("REQ", "tests/conftest.py")) is None
        assert not any("app.py" in cid for cid in code_ids), (
            f"The pattern selects no file in src/, so nothing there is scanned: {code_ids}"
        )

        declined = {(u.path, u.kind) for u in graph.unscanned_keyword_files()}
        assert ("src/app.py", "code") in declined, (
            f"The annotated file the patterns declined must be recorded: {declined}"
        )
        assert not any(path.endswith("conftest.py") for path, _ in declined), (
            "A file no declared directory contains was never reached, so it is "
            f"not something the code kind declined: {declined}"
        )

    # Verifies: REQ-d00212-Q
    def test_REQ_d00212_Q_a_file_two_declared_directories_hold_is_scanned_once(
        self, tmp_path: Path
    ) -> None:
        """Nested declared directories reach the same file; it is scanned once.

        `src` and `src/sub` are both declared, so the walk for each reaches
        `src/sub/overlap.py`. One file scanned twice would be one requirement
        credited twice, so the second walk must recognise what the first
        already read.
        """
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-dedup"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src", "src/sub"]
file_patterns = ["*.py"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "sub" / "overlap.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        # Filter to nodes from overlap.py specifically
        overlap_nodes = [n for n in code_nodes if "overlap.py" in n.id]

        assert len(overlap_nodes) == 1, (
            f"Expected exactly 1 CODE node from overlap.py (de-duplication), "
            f"got {len(overlap_nodes)}: {[n.id for n in overlap_nodes]}"
        )

    # Verifies: REQ-d00241-G
    def test_REQ_d00241_G_skip_dirs_excludes_a_subdirectory_of_a_code_directory(
        self, tmp_path: Path
    ) -> None:
        """A subdirectory the kind excludes is not descended into.

        The exclusion half of selection is settled inside the walk, so the
        excluded directory's contents are never reached at all."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-ignore"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
skip_dirs = ["src/vendor"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        # This file is inside src/vendor/ which should be ignored
        _write_code_file(tmp_path / "src" / "vendor" / "foo.py")
        # This file is in src/ top-level which should be scanned
        _write_code_file(tmp_path / "src" / "app.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        code_ids = [n.id for n in code_nodes]

        vendor_nodes = [cid for cid in code_ids if "vendor" in cid]
        app_nodes = [cid for cid in code_ids if "app.py" in cid]

        assert len(vendor_nodes) == 0, (
            f"Files in ignored 'vendor' dir should NOT produce CODE nodes, but got: {vendor_nodes}"
        )
        assert len(app_nodes) > 0, (
            f"Non-ignored src/app.py should produce CODE node, got: {code_ids}"
        )

    # Verifies: REQ-d00054-A
    def test_REQ_d00054_A_code_directories_explicit_src_scanned(self, tmp_path: Path) -> None:
        """When scanning.code.directories is explicitly set to ["src"],
        the src directory is scanned."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-explicit-src"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")
        _write_code_file(tmp_path / "src" / "default.py")

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        code_ids = [n.id for n in code_nodes]

        has_default = any("default.py" in cid for cid in code_ids)
        assert has_default, f"Explicit src/ directory should be scanned, got: {code_ids}"

    # Verifies: REQ-d00054-A
    def test_REQ_d00054_A_nonexistent_code_directory_is_skipped(self, tmp_path: Path) -> None:
        """When [directories].code lists a non-existent directory, build_graph
        does not crash — the directory is silently skipped."""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-missing-dir"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["does_not_exist"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")

        # Should not raise
        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        assert len(code_nodes) == 0, "Non-existent code directory should produce zero CODE nodes"


def _build_graph_for_annotated_file(tmp_path: Path, filename: str):
    """Build a graph over a src/ dir holding one annotated file with the given name.

    Config sets no `file_patterns`, so DEFAULT_CODE_PATTERNS decides whether the
    file is scanned at all.
    """
    config_file = tmp_path / ".elspais.toml"
    config_file.write_text(
        """\
[project]
name = "test-default-code-patterns"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
""",
        encoding="utf-8",
    )
    _write_spec(tmp_path / "spec")
    _write_code_file(tmp_path / "src" / filename)

    return build_graph(
        config_path=config_file,
        repo_root=tmp_path,
        scan_tests=False,
    )


class TestDefaultCodePatternFileTypes:
    """Every extension in DEFAULT_CODE_PATTERNS produces the same graph shape.

    Terraform/HCL sources carry `# Implements:` annotations exactly as shell
    scripts do, so an annotated `.tf` must land in the graph with the same
    FILE / CODE / IMPLEMENTS structure a `.sh` file gets. `.sh` is the control:
    it was scanned before Terraform support existed, so any divergence between
    the parametrized cases is a Terraform-specific regression.
    """

    # Verifies: REQ-d00128-A
    @pytest.mark.parametrize("ext", ["sh", "tf", "tfvars", "hcl"])
    def test_REQ_d00128_A_annotated_hash_comment_file_yields_same_shape(
        self, tmp_path: Path, ext: str
    ) -> None:
        """A hash-comment source file in a code directory produces a FILE node, a
        CODE node it CONTAINS, and an IMPLEMENTS edge to the requirement."""
        graph = _build_graph_for_annotated_file(tmp_path, f"infra.{ext}")

        # REQ-d00128-A: FILE node with file:<repo-relative-path> ID
        file_node = graph.find_by_id(make_file_id("REQ", f"src/infra.{ext}"))
        assert file_node is not None, f".{ext} file should produce a FILE node"
        assert file_node.get_field("relative_path") == f"src/infra.{ext}"

        # REQ-d00128-D: FILE CONTAINS exactly one CODE node
        contained_code = [
            c
            for c in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
            if c.kind == NodeKind.CODE
        ]
        assert len(contained_code) == 1, (
            f"Expected exactly one CODE node contained by src/infra.{ext}, "
            f"got: {[c.id for c in contained_code]}"
        )
        code_node = contained_code[0]

        # The CODE node is reachable from the graph's CODE index, not just the FILE.
        assert code_node.id in {n.id for n in graph.nodes_by_kind(NodeKind.CODE)}

        # REQ-p00003-B: the `Implements:` annotation becomes an IMPLEMENTS edge
        implements_edges = [
            e for e in code_node.iter_incoming_edges() if e.kind == EdgeKind.IMPLEMENTS
        ]
        assert len(implements_edges) == 1, (
            f".{ext} annotation should produce one IMPLEMENTS edge, got {len(implements_edges)}"
        )
        implementing_parents = {
            p.id for p in code_node.iter_parents(edge_kinds={EdgeKind.IMPLEMENTS})
        }
        assert implementing_parents == {"REQ-p00001"}

    # Verifies: REQ-d00236-H, REQ-d00212-Q
    @pytest.mark.parametrize("filename", ["Dockerfile", "Containerfile", "service.Dockerfile"])
    def test_REQ_d00236_H_a_container_image_file_is_scanned_and_read_as_shell(
        self, tmp_path: Path, filename: str
    ) -> None:
        """A container image file is selected by default and its `#` line is read.

        An image file is where a deployment's configuration values are bound,
        so it is a normal place to cite a requirement from -- and it names its
        language in the file name rather than in an extension, which is why
        both halves have to hold: the default patterns must select it, and the
        comment pattern associated with it must read the citation. Only the
        annotation line matters to either half, so the body the shared writer
        produces is beside the point.
        """
        graph = _build_graph_for_annotated_file(tmp_path, filename)

        file_node = graph.find_by_id(make_file_id("REQ", f"src/{filename}"))
        assert file_node is not None, f"{filename} should be selected by the code defaults"

        contained_code = [
            c
            for c in file_node.iter_children(edge_kinds={EdgeKind.CONTAINS})
            if c.kind == NodeKind.CODE
        ]
        assert len(contained_code) == 1, (
            f"Expected one CODE node in src/{filename}, got {[c.id for c in contained_code]}"
        )
        implementing_parents = {
            p.id for p in contained_code[0].iter_parents(edge_kinds={EdgeKind.IMPLEMENTS})
        }
        assert implementing_parents == {"REQ-p00001"}

    # Verifies: REQ-d00128-A
    def test_REQ_d00128_A_extension_outside_default_patterns_is_not_scanned(
        self, tmp_path: Path
    ) -> None:
        """An identically annotated file whose extension is not in
        DEFAULT_CODE_PATTERNS produces no FILE or CODE node — so the parametrized
        cases above are evidence about the pattern list, not about any file being
        picked up regardless of name."""
        graph = _build_graph_for_annotated_file(tmp_path, "infra.tfstate")

        assert graph.find_by_id("file:src/infra.tfstate") is None
        assert list(graph.nodes_by_kind(NodeKind.CODE)) == []


class TestBuildGraphCoverageAnnotation:
    """Validates REQ-d00055-D: build_graph() annotates referenced_pct on requirement nodes.

    Validates REQ-o00061-B: get_project_summary() returns non-zero coverage when
    requirements have implementing code, because build_graph() now runs annotate_coverage().
    """

    # Verifies: REQ-d00055-D
    def test_REQ_d00055_D_build_graph_sets_referenced_pct_metric(self, tmp_path: Path) -> None:
        """After build_graph(), requirement nodes have referenced_pct metric set.

        When a code file implements a requirement's assertion, the referenced_pct
        metric should reflect that coverage (not remain at 0).
        """
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
""",
            encoding="utf-8",
        )

        # Write a spec with one requirement and one assertion
        # Uses ## heading level and ## Assertions section (matching parser expectations)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "reqs.md").write_text(
            """\
# Test Requirements

## REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

The system SHALL do something testable.

## Assertions

A. The system SHALL perform action X.

*End* *Test Requirement* | **Hash**: abcd1234

---
""",
            encoding="utf-8",
        )

        # Write a code file that implements the assertion
        code_dir = tmp_path / "src"
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / "impl.py").write_text(
            "# Implements: REQ-p00001-A\ndef do_action_x(): pass\n",
            encoding="utf-8",
        )

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        req_node = graph.find_by_id("REQ-p00001")
        assert req_node is not None, "REQ-p00001 should exist in the graph"

        rollup = req_node.get_metric("rollup_metrics")
        assert rollup is not None, "rollup_metrics should be set after build_graph()"
        referenced_pct = rollup.implemented.covered_pct
        assert referenced_pct == 100.0, (
            f"Expected 100% coverage (1/1 assertion covered), got {referenced_pct}"
        )

    # Verifies: REQ-d00055-D
    def test_REQ_d00055_D_build_graph_sets_rollup_metrics(self, tmp_path: Path) -> None:
        """After build_graph(), requirement nodes have rollup_metrics metric set.

        The rollup_metrics object tracks detailed coverage breakdown (direct,
        explicit, inferred sources).
        """
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-rollup"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
""",
            encoding="utf-8",
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "reqs.md").write_text(
            """\
# Test Requirements

## REQ-p00001: Rollup Test

**Level**: PRD | **Status**: Active | **Implements**: -

The system SHALL do something.

## Assertions

A. The system SHALL do A.
B. The system SHALL do B.

*End* *Rollup Test* | **Hash**: abcd1234

---
""",
            encoding="utf-8",
        )

        # Code covers only assertion A
        code_dir = tmp_path / "src"
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / "impl.py").write_text(
            "# Implements: REQ-p00001-A\ndef do_a(): pass\n",
            encoding="utf-8",
        )

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        req_node = graph.find_by_id("REQ-p00001")
        assert req_node is not None

        from elspais.graph.metrics import RollupMetrics

        rollup = req_node.get_metric("rollup_metrics")
        assert rollup is not None, "rollup_metrics should be set after build_graph()"
        assert isinstance(rollup, RollupMetrics), f"Expected RollupMetrics, got {type(rollup)}"
        assert rollup.total_assertions == 2
        assert rollup.implemented.covered == 1
        assert rollup.implemented.covered_pct == 50.0

    # Verifies: REQ-o00061-B
    def test_REQ_o00061_B_project_summary_nonzero_coverage_after_build_graph(
        self, tmp_path: Path
    ) -> None:
        """get_project_summary() reports non-zero coverage when build_graph()
        has annotated coverage metrics.

        This is the integration test for the bug fix: previously build_graph()
        did not call annotate_coverage(), so MCP's get_project_summary() always
        reported 0% coverage.
        """
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-summary"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
""",
            encoding="utf-8",
        )

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "reqs.md").write_text(
            """\
# Test Requirements

## REQ-p00001: Summary Test

**Level**: PRD | **Status**: Active | **Implements**: -

The system SHALL do something.

## Assertions

A. The system SHALL do A.

*End* *Summary Test* | **Hash**: abcd1234

---
""",
            encoding="utf-8",
        )

        # Code covers the assertion
        code_dir = tmp_path / "src"
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / "impl.py").write_text(
            "# Implements: REQ-p00001-A\ndef do_a(): pass\n",
            encoding="utf-8",
        )

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
        )

        # Simulate what the MCP server does: call count_by_coverage on the graph
        from elspais.graph.annotators import count_by_coverage

        coverage_stats = count_by_coverage(graph)

        assert coverage_stats["total"] == 1
        assert coverage_stats["full_coverage"] == 1, (
            "After build_graph() with annotate_coverage(), the requirement with "
            "100% coverage should appear in full_coverage count"
        )
        assert coverage_stats["no_coverage"] == 0, (
            "The requirement should NOT be in no_coverage since it has code implementing it"
        )


class TestMultiRoleFileScanning:
    """Tests for files scanned as both CODE and TEST (dual-type)."""

    # Verifies: REQ-d00212-W
    def test_REQ_d00212_W_a_file_both_kinds_select_has_both_content_types(
        self, tmp_path: Path
    ) -> None:
        """A file both the code and the test kind select produces one FILE node
        with both CODE and TEST content children and file_types set.

        Both kinds declare `tests` and both kinds' patterns select the file
        there, which is the only way one file now holds two roles: a pattern
        selects within its own kind's declared directories.
        """
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """\
[project]
name = "test-multi-role"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src", "tests"]
file_patterns = ["*.py"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["test_*.py"]
""",
            encoding="utf-8",
        )

        _write_spec(tmp_path / "spec")

        # Write a test file that also has # Implements: (code role)
        test_file = tmp_path / "tests" / "test_dual.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            "# Implements: REQ-p00001\ndef test_REQ_p00001_something():\n    assert True\n",
            encoding="utf-8",
        )

        graph = build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=True,
        )

        # Find the FILE node for test_dual.py
        file_nodes = [n for n in graph.iter_roots(NodeKind.FILE) if "test_dual.py" in n.id]
        assert len(file_nodes) == 1, (
            f"Expected exactly 1 FILE node for test_dual.py, got {len(file_nodes)}"
        )
        file_node = file_nodes[0]

        # Check file_types list includes both CODE and TEST (stored as string values)
        file_types = file_node.get_field("file_types")
        assert file_types is not None, "file_types field should be set for multi-role files"
        assert "code" in file_types, f"Expected 'code' in file_types, got {file_types}"
        assert "test" in file_types, f"Expected 'test' in file_types, got {file_types}"

        # Check both CODE and TEST content children exist
        child_kinds = {child.kind for child in file_node.iter_children()}
        assert NodeKind.CODE in child_kinds, (
            f"Expected CODE child from # Implements:, got kinds: {child_kinds}"
        )
        assert NodeKind.TEST in child_kinds, (
            f"Expected TEST child from test function, got kinds: {child_kinds}"
        )


# --- One selection mechanism, one meaning for every kind ------------------- #


def _toml_list(values) -> str:
    """A TOML array literal for a list of strings."""
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"


def _write_selection_config(
    tmp_path: Path,
    *,
    global_skip=(),
    spec_skip_files=(),
    spec_skip_dirs=(),
    code_dirs=("src",),
    code_patterns=("*.py",),
    code_skip_files=(),
    code_skip_dirs=(),
    test_dirs=("tests",),
    test_patterns=("test_*.py",),
    test_skip_files=(),
    test_skip_dirs=(),
) -> Path:
    """Write a project whose scanning kinds are configured the same way.

    The spec, code and test kinds are given the same shape of configuration so
    a test can vary one setting and compare the kinds' answers.
    """
    config_file = tmp_path / ".elspais.toml"
    config_file.write_text(
        f"""\
[project]
name = "test-selection"
namespace = "REQ"

[scanning]
skip = {_toml_list(global_skip)}

[scanning.spec]
directories = ["spec"]
skip_files = {_toml_list(spec_skip_files)}
skip_dirs = {_toml_list(spec_skip_dirs)}

[scanning.code]
directories = {_toml_list(code_dirs)}
file_patterns = {_toml_list(code_patterns)}
skip_files = {_toml_list(code_skip_files)}
skip_dirs = {_toml_list(code_skip_dirs)}

[scanning.test]
enabled = true
directories = {_toml_list(test_dirs)}
file_patterns = {_toml_list(test_patterns)}
skip_files = {_toml_list(test_skip_files)}
skip_dirs = {_toml_list(test_skip_dirs)}
""",
        encoding="utf-8",
    )
    _write_spec(tmp_path / "spec")
    return config_file


def _write_annotated(tmp_path: Path, relative: str, keyword: str) -> None:
    """Write a Python file citing REQ-p00001 with *keyword*, holding one function."""
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"# {keyword}: REQ-p00001\ndef test_thing():\n    assert True\n",
        encoding="utf-8",
    )


def _scanned(graph, relative: str) -> bool:
    """Whether the file at *relative* was read by the build."""
    return graph.find_by_id(make_file_id("REQ", relative)) is not None


class TestOneSelectionMechanism:
    """File selection means one thing, and it means it for every kind.

    A kind walks the directories it declares, the ignore configuration
    excludes, and the kind's declared patterns select what is left
    (REQ-d00212-Q). The patterns select WITHIN those directories, with the
    same meaning wherever they are written (REQ-d00212-W) -- so the code kind
    and the test kind are compared against each other rather than each
    against its own former behaviour.
    """

    _KINDS = [
        pytest.param("code", "src", "tests", "Implements", id="code"),
        pytest.param("test", "tests", "src", "Verifies", id="test"),
    ]

    @staticmethod
    def _one_kind_config(tmp_path: Path, kind: str, own_dir: str, patterns) -> Path:
        """Configure exactly one kind to scan *own_dir*, silencing the other."""
        if kind == "code":
            return _write_selection_config(
                tmp_path,
                code_dirs=[own_dir],
                code_patterns=patterns,
                test_dirs=[],
            )
        return _write_selection_config(
            tmp_path,
            code_dirs=[],
            test_dirs=[own_dir],
            test_patterns=patterns,
        )

    # Verifies: REQ-d00212-W
    @pytest.mark.parametrize(("kind", "own_dir", "other_dir", "keyword"), _KINDS)
    def test_REQ_d00212_W_a_pattern_narrows_each_kind_identically(
        self, tmp_path: Path, kind: str, own_dir: str, other_dir: str, keyword: str
    ) -> None:
        """The same pattern, written for either kind, selects the same files.

        Both trees are laid out identically and both hold an annotated file the
        pattern does not select and one it does. Whichever kind is configured,
        the same file is read and the same one is passed over -- and neither
        kind reaches the tree it did not declare.
        """
        for directory in ("src", "tests"):
            _write_annotated(tmp_path, f"{directory}/api/handler.py", keyword)
            _write_annotated(tmp_path, f"{directory}/app.py", keyword)

        config_file = self._one_kind_config(tmp_path, kind, own_dir, ["api/*.py"])
        graph = build_graph(config_path=config_file, repo_root=tmp_path)

        assert _scanned(graph, f"{own_dir}/api/handler.py"), (
            f"The {kind} kind's pattern selects {own_dir}/api/handler.py"
        )
        assert not _scanned(graph, f"{own_dir}/app.py"), (
            f"The {kind} kind's pattern does not select {own_dir}/app.py"
        )
        assert not _scanned(graph, f"{other_dir}/api/handler.py"), (
            f"The {kind} kind declared only {own_dir}, so {other_dir} is out of reach"
        )
        assert not _scanned(graph, f"{other_dir}/app.py")

    # Verifies: REQ-d00212-Q
    @pytest.mark.parametrize(("kind", "own_dir", "other_dir", "keyword"), _KINDS)
    def test_REQ_d00212_Q_declaring_no_pattern_scans_the_kinds_defaults(
        self, tmp_path: Path, kind: str, own_dir: str, other_dir: str, keyword: str
    ) -> None:
        """An empty `file_patterns` means the kind's defaults, not nothing.

        The defaults are what this one setting holds until a project writes
        its own, so a configuration that declares none still scans what it
        always scanned.
        """
        _write_annotated(tmp_path, f"{own_dir}/test_main.py", keyword)

        config_file = self._one_kind_config(tmp_path, kind, own_dir, [])
        graph = build_graph(config_path=config_file, repo_root=tmp_path)

        assert _scanned(graph, f"{own_dir}/test_main.py"), (
            f"With no {kind} pattern declared, the {kind} defaults select the file"
        )
        assert graph.unscanned_keyword_files() == [], (
            "A file the defaults select was scanned, so nothing was passed over"
        )

    # Verifies: REQ-d00241-G
    @pytest.mark.parametrize(
        ("kind", "keyword", "excluded", "kept", "settings"),
        [
            pytest.param(
                "test",
                "Verifies",
                "tests/test_legacy.py",
                "tests/test_kept.py",
                {"global_skip": ["test_legacy.py"]},
                id="test-global-skip",
            ),
            pytest.param(
                "test",
                "Verifies",
                "tests/test_legacy.py",
                "tests/test_kept.py",
                {"test_skip_files": ["test_legacy.py"]},
                id="test-skip-files",
            ),
            pytest.param(
                "test",
                "Verifies",
                "tests/legacy/test_legacy.py",
                "tests/test_kept.py",
                {"test_skip_dirs": ["tests/legacy"]},
                id="test-skip-dirs",
            ),
            pytest.param(
                "code",
                "Implements",
                "src/legacy.py",
                "src/kept.py",
                {"global_skip": ["legacy.py"]},
                id="code-global-skip",
            ),
            pytest.param(
                "code",
                "Implements",
                "src/legacy.py",
                "src/kept.py",
                {"code_skip_files": ["legacy.py"]},
                id="code-skip-files",
            ),
            pytest.param(
                "code",
                "Implements",
                "src/legacy/thing.py",
                "src/kept.py",
                {"code_skip_dirs": ["src/legacy"]},
                id="code-skip-dirs",
            ),
        ],
    )
    def test_REQ_d00241_G_an_excluded_file_is_neither_scanned_nor_reported(
        self, tmp_path: Path, kind: str, keyword: str, excluded: str, kept: str, settings: dict
    ) -> None:
        """Every route to exclusion removes a file from the scan and from the report.

        The test kind never consulted the ignore configuration at all, so its
        own exclusions decided nothing. Excluding a file is also a decision
        about reporting: the project said not to look there, so a citation
        found in such a file is not something to be told about.
        """
        _write_annotated(tmp_path, excluded, keyword)
        _write_annotated(tmp_path, kept, keyword)

        config_file = _write_selection_config(tmp_path, **settings)
        graph = build_graph(config_path=config_file, repo_root=tmp_path)

        assert _scanned(graph, kept), f"The {kind} kind still scans {kept}"
        assert not _scanned(graph, excluded), f"An excluded file must not be scanned: {excluded}"
        reported = {record.path for record in graph.unscanned_keyword_files()}
        assert excluded not in reported, (
            f"An excluded file must not be reported as passed over: {reported}"
        )

    # Verifies: REQ-d00241-F
    def test_REQ_d00241_F_a_declined_file_carrying_a_keyword_is_recorded(
        self, tmp_path: Path
    ) -> None:
        """A file reached, not excluded, not selected, and citing anyway is recorded.

        The record names where the citation is and how it was spelled, because
        a citation nothing read and a requirement genuinely uncovered produce
        the same coverage figure otherwise.
        """
        notes = tmp_path / "src" / "notes.txt"
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text(
            "Release notes\n\n# Implements: REQ-p00001\n",
            encoding="utf-8",
        )
        _write_annotated(tmp_path, "src/app.py", "Implements")

        config_file = _write_selection_config(tmp_path, test_dirs=[])
        graph = build_graph(config_path=config_file, repo_root=tmp_path)

        assert _scanned(graph, "src/app.py")
        assert not _scanned(graph, "src/notes.txt")

        records = graph.unscanned_keyword_files()
        assert len(records) == 1, f"Expected one declined citing file, got {records}"
        record = records[0]
        assert (record.path, record.kind, record.keyword, record.line) == (
            "src/notes.txt",
            "code",
            "Implements",
            3,
        )

    # Verifies: REQ-d00241-F
    def test_REQ_d00241_F_a_declined_file_without_a_keyword_is_not_recorded(
        self, tmp_path: Path
    ) -> None:
        """Passing over an ordinary file is not a finding.

        Only a declined file that cites is worth reporting; every scanned tree
        holds files no kind selects, and reporting each of them would bury the
        one that matters.
        """
        quiet = tmp_path / "src" / "notes.txt"
        quiet.parent.mkdir(parents=True, exist_ok=True)
        quiet.write_text("Release notes, mentioning no requirement.\n", encoding="utf-8")
        _write_annotated(tmp_path, "src/app.py", "Implements")

        config_file = _write_selection_config(tmp_path, test_dirs=[])
        graph = build_graph(config_path=config_file, repo_root=tmp_path)

        assert graph.unscanned_keyword_files() == []


# --- Excluded content is not read at all ----------------------------------- #


def _write_excludable_spec(tmp_path: Path, relative: str, req_id: str) -> None:
    """Write a valid spec file holding one requirement at *relative*."""
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"""\
### {req_id}: Excludable Req

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *Excludable Req* | **Hash**: ________
""",
        encoding="utf-8",
    )


def _write_for_kind(tmp_path: Path, kind: str, relative: str, req_id: str) -> None:
    """Write a file the *kind* being configured would read if it reached it."""
    if kind == "spec":
        _write_excludable_spec(tmp_path, relative, req_id)
    else:
        _write_annotated(tmp_path, relative, "Implements" if kind == "code" else "Verifies")


# Every route by which a project excludes content, for every scanning kind:
# the global list, the kind's own file list, and the kind's own directory list.
_EXCLUSION_ROUTES = [
    pytest.param("spec", "spec/secret.md", "spec/reqs.md", {"global_skip": ["secret.md"]}),
    pytest.param("spec", "spec/secret.md", "spec/reqs.md", {"spec_skip_files": ["secret.md"]}),
    pytest.param(
        "spec", "spec/drafts/draft.md", "spec/reqs.md", {"spec_skip_dirs": ["spec/drafts"]}
    ),
    pytest.param("code", "src/legacy.py", "src/kept.py", {"global_skip": ["legacy.py"]}),
    pytest.param("code", "src/legacy.py", "src/kept.py", {"code_skip_files": ["legacy.py"]}),
    pytest.param("code", "src/legacy/thing.py", "src/kept.py", {"code_skip_dirs": ["src/legacy"]}),
    pytest.param(
        "test",
        "tests/test_legacy.py",
        "tests/test_kept.py",
        {"global_skip": ["test_legacy.py"]},
    ),
    pytest.param(
        "test",
        "tests/test_legacy.py",
        "tests/test_kept.py",
        {"test_skip_files": ["test_legacy.py"]},
    ),
    pytest.param(
        "test",
        "tests/legacy/test_legacy.py",
        "tests/test_kept.py",
        {"test_skip_dirs": ["tests/legacy"]},
    ),
]

_ROUTE_IDS = [
    "spec-global-skip",
    "spec-skip-files",
    "spec-skip-dirs",
    "code-global-skip",
    "code-skip-files",
    "code-skip-dirs",
    "test-global-skip",
    "test-skip-files",
    "test-skip-dirs",
]


class TestExcludedContentIsNotRead:
    """A reader who excludes content is promised the content is not opened.

    The weaker promise -- that excluded content contributes to no answer --
    is satisfiable by a tool that reads a file and then throws the content
    away, and that is not what a reader excluding a file of secrets is owed.
    These tests therefore watch the read itself rather than the answer: an
    excluded path is never opened, and an excluded directory is never
    descended into.
    """

    @staticmethod
    def _project(tmp_path: Path, kind: str, excluded: str, kept: str, settings: dict) -> Path:
        """Lay out a project holding *kept* and *excluded*, excluding the latter."""
        # The config helper writes the project's own spec file, which for the
        # spec kind IS this case's kept file -- so the kept file is written
        # through the helper and the excluded one beside it afterwards, leaving
        # the two differing only in which is excluded.
        config_file = _write_selection_config(tmp_path, **settings)
        _write_for_kind(tmp_path, kind, kept, "REQ-p00001")
        _write_for_kind(tmp_path, kind, excluded, "REQ-p00009")
        return config_file

    # Verifies: REQ-p00015-H
    @pytest.mark.parametrize(
        ("kind", "excluded", "kept", "settings"),
        _EXCLUSION_ROUTES,
        ids=_ROUTE_IDS,
    )
    def test_an_excluded_path_is_never_opened(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        kind: str,
        excluded: str,
        kept: str,
        settings: dict,
    ) -> None:
        """No route to exclusion leaves the excluded file's content ever opened.

        Watching the open is what separates the obligation from its weaker
        cousin: a build that read the file and discarded what it found would
        report nothing about it either, and would be caught only here.
        """
        config_file = self._project(tmp_path, kind, excluded, kept, settings)
        excluded_path = str((tmp_path / excluded).resolve())
        kept_path = str((tmp_path / kept).resolve())

        opened: set[str] = set()
        real_path_open = Path.open
        real_builtin_open = builtins.open

        def record_path_open(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            opened.add(str(Path(self).resolve()))
            return real_path_open(self, *args, **kwargs)

        def record_builtin_open(file, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            if isinstance(file, (str, Path)):
                opened.add(str(Path(file).resolve()))
            return real_builtin_open(file, *args, **kwargs)

        monkeypatch.setattr(Path, "open", record_path_open)
        monkeypatch.setattr(builtins, "open", record_builtin_open)
        try:
            build_graph(config_path=config_file, repo_root=tmp_path)
        finally:
            monkeypatch.undo()

        assert kept_path in opened, (
            f"The {kind} kind reads {kept}, so the recorder is watching the reads "
            f"this build actually makes"
        )
        assert excluded_path not in opened, (
            f"An excluded path must never be opened: {excluded} was read by the build"
        )

    # Verifies: REQ-p00015-H
    @pytest.mark.parametrize(
        ("kind", "root_dir", "excluded_dir", "decoy", "kept", "settings"),
        [
            pytest.param(
                "spec",
                "spec",
                "spec/drafts",
                "spec/drafts/draft.md",
                "spec/reqs.md",
                {"spec_skip_dirs": ["spec/drafts"]},
            ),
            pytest.param(
                "code",
                "src",
                "src/legacy",
                "src/legacy/thing.py",
                "src/kept.py",
                {"code_skip_dirs": ["src/legacy"]},
            ),
            pytest.param(
                "test",
                "tests",
                "tests/legacy",
                "tests/legacy/test_thing.py",
                "tests/test_kept.py",
                {"test_skip_dirs": ["tests/legacy"]},
            ),
            pytest.param(
                "spec",
                "spec",
                "spec/drafts",
                "spec/drafts/draft.md",
                "spec/reqs.md",
                {"global_skip": ["spec/drafts"]},
            ),
            pytest.param(
                "code",
                "src",
                "src/legacy",
                "src/legacy/thing.py",
                "src/kept.py",
                {"global_skip": ["src/legacy"]},
            ),
            pytest.param(
                "test",
                "tests",
                "tests/legacy",
                "tests/legacy/test_thing.py",
                "tests/test_kept.py",
                {"global_skip": ["tests/legacy"]},
            ),
        ],
        ids=[
            "spec-skip-dirs",
            "code-skip-dirs",
            "test-skip-dirs",
            "spec-global-skip",
            "code-global-skip",
            "test-global-skip",
        ],
    )
    def test_an_excluded_directory_is_never_descended_into(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        kind: str,
        root_dir: str,
        excluded_dir: str,
        decoy: str,
        kept: str,
        settings: dict,
    ) -> None:
        """The directory itself is not listed, so its contents are never known.

        A walk that descended and then dropped what it found would leave no
        trace in any answer, so the directory listing is where the promise is
        observable. The excluded directory holds a decoy the kind would
        otherwise read, which is what makes not descending the only way to
        stay silent about it.
        """
        config_file = self._project(tmp_path, kind, decoy, kept, settings)
        excluded_abs = str((tmp_path / excluded_dir).resolve())
        root_abs = str((tmp_path / root_dir).resolve())

        listed: set[str] = set()
        real_scandir = os.scandir

        def record_scandir(path=".", *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            try:
                listed.add(str(Path(path).resolve()))
            except (TypeError, ValueError):
                pass
            return real_scandir(path, *args, **kwargs)

        monkeypatch.setattr(os, "scandir", record_scandir)
        try:
            build_graph(config_path=config_file, repo_root=tmp_path)
        finally:
            monkeypatch.undo()

        assert root_abs in listed, (
            f"The {kind} kind walks {root_dir}, so the recorder is watching this walk"
        )
        assert excluded_abs not in listed, (
            f"An excluded directory must not be descended into: {excluded_dir} was listed"
        )

    # Verifies: REQ-p00015-H
    @pytest.mark.parametrize(
        ("kind", "excluded", "kept", "settings"),
        _EXCLUSION_ROUTES,
        ids=_ROUTE_IDS,
    )
    def test_undecodable_bytes_in_an_excluded_file_never_reach_the_decoder(
        self,
        tmp_path: Path,
        kind: str,
        excluded: str,
        kept: str,
        settings: dict,
    ) -> None:
        """Content that cannot be decoded is harmless while it is excluded.

        Reading this file raises, so the same tree built without the exclusion
        fails -- which is what establishes that the excluded build's success
        comes from never having read the file rather than from the file being
        uninteresting. No instrumentation is involved: the file itself is the
        detector.
        """
        config_file = self._project(tmp_path, kind, excluded, kept, settings)
        (tmp_path / excluded).write_bytes(b"\xff\xfe# Implements: REQ-p00001\n\x80\x81")

        graph = build_graph(config_path=config_file, repo_root=tmp_path)
        assert graph.find_by_id("REQ-p00001") is not None, (
            "The rest of the project still built while the excluded file sat there"
        )

        # Control: the same undecodable file, no longer excluded, is read.
        unexcluded = _write_selection_config(tmp_path)
        if kind == "spec":
            _write_for_kind(tmp_path, kind, kept, "REQ-p00001")
        with pytest.raises(SourceReadError):
            build_graph(config_path=unexcluded, repo_root=tmp_path)


# The skip list `elspais init` writes into a new project's configuration, spelled
# exactly as it writes it. Every entry names something a repository may sit
# *under* as easily as hold, and the `**/` entries are the dangerous ones: they
# name a directory at any depth INSIDE the repository, so nothing but reading the
# path from the repository root keeps them off an ancestor of the checkout.
_INIT_TEMPLATE_SKIP = [
    "**/node_modules",
    "**/.git",
    "**/__pycache__",
    "*.pyc",
    "**/.venv",
    ".env",
]


def _repo_under(parent: Path) -> Path:
    """Lay a one-requirement project out at *parent*/myrepo, skipping as `init` does."""
    repo = parent / "myrepo"
    (repo / "spec").mkdir(parents=True)
    (repo / ".elspais.toml").write_text(
        f"""\
[project]
name = "located-somewhere"
namespace = "REQ"

[scanning]
skip = {_toml_list(_INIT_TEMPLATE_SKIP)}

[scanning.spec]
directories = ["spec"]
""",
        encoding="utf-8",
    )
    _write_spec(repo / "spec")
    return repo


def _requirements_found(repo: Path) -> list[str]:
    """Every requirement id a build of the project at *repo* admits."""
    graph = build_graph(config_path=repo / ".elspais.toml", repo_root=repo)
    return sorted(node.id for node in graph.iter_by_kind(NodeKind.REQUIREMENT))


class TestWhereARepositorySitsDecidesNothing:
    """The same repository answers the same wherever it is checked out.

    An exclusion pattern names content inside the repository. Matched against
    the absolute path instead, a pattern also matched a directory the checkout
    merely sits under, so a repository cloned beneath `node_modules` scanned
    to nothing -- and said so as a blameless-looking configuration warning.
    """

    @pytest.mark.parametrize("parent_name", ["node_modules", ".venv", "__pycache__"])
    def test_a_checkout_under_a_skipped_directory_name_finds_the_same_requirements(
        self, tmp_path: Path, parent_name: str
    ) -> None:
        """Two identical checkouts, differing only in the name above them."""
        assert not any(
            fnmatch.fnmatch(part, pattern.rsplit("/", 1)[-1])
            for part in tmp_path.parts
            for pattern in _INIT_TEMPLATE_SKIP
        ), (
            f"The temporary directory {tmp_path} itself matches a skip pattern, so the "
            f"control arm would be excluded too and the comparison would prove nothing"
        )

        control = _requirements_found(_repo_under(tmp_path / "plainbox"))
        assert control, "The control checkout holds a requirement, so a build of it finds one"

        located = _requirements_found(_repo_under(tmp_path / parent_name))

        assert located == control, (
            f"A checkout under a directory named {parent_name!r} found {located} where the "
            f"same project under an ordinary directory found {control}"
        )
