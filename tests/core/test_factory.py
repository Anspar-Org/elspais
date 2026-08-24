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

from pathlib import Path

import pytest

from elspais.graph import NodeKind
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
skip_dirs = ["vendor"]
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
    code_dirs=("src",),
    code_patterns=("*.py",),
    code_skip_files=(),
    code_skip_dirs=(),
    test_dirs=("tests",),
    test_patterns=("test_*.py",),
    test_skip_files=(),
    test_skip_dirs=(),
) -> Path:
    """Write a project whose two scanning kinds are configured the same way.

    The code and test kinds are given the same shape of configuration so a
    test can vary one setting and compare the two kinds' answers.
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
                {"test_skip_dirs": ["legacy"]},
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
                {"code_skip_dirs": ["legacy"]},
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
