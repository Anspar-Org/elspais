# Validates: REQ-d00128-A, REQ-d00128-B, REQ-d00128-C, REQ-d00128-D,
# Validates: REQ-d00128-E, REQ-d00128-F, REQ-d00128-G, REQ-d00128-H, REQ-d00128-I
"""Tests for FILE node creation in the build pipeline.

Verifies that factory.py creates FILE nodes for scanned files, builder.py
wires CONTAINS edges from FILE to top-level content nodes, and RemainderParser
is mandatory for text-based file types but not RESULT types.
"""

from pathlib import Path

from elspais.graph import NodeKind
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import FileType
from elspais.graph.relations import EdgeKind


def _write_config(tmp_path: Path, extra: str = "") -> Path:
    """Write a minimal .elspais.toml and return its path."""
    config_file = tmp_path / ".elspais.toml"
    config_file.write_text(
        f"""\
[project]
name = "test-file-nodes"

[directories]
spec = "spec"
code = ["src"]
{extra}
""",
        encoding="utf-8",
    )
    return config_file


def _write_spec(tmp_path: Path, filename: str = "reqs.md", content: str | None = None) -> Path:
    """Write a spec file and return its path."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    if content is None:
        content = """\
# Test Requirements

## REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

The system SHALL do something testable.

## Assertions

A. The system SHALL perform action X.

*End* *Test Requirement* | **Hash**: abcd1234

---
"""
    (spec_dir / filename).write_text(content, encoding="utf-8")
    return spec_dir / filename


def _write_code_file(tmp_path: Path, filename: str = "main.py", req_id: str = "REQ-p00001") -> Path:
    """Write a Python code file with an Implements comment."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    file_path = src_dir / filename
    file_path.write_text(
        f"# Implements: {req_id}\ndef work(): pass\n",
        encoding="utf-8",
    )
    return file_path


class TestFileNodeCreation:
    """Validates REQ-d00128-A: factory.py creates FILE nodes for scanned files."""

    def test_REQ_d00128_A_spec_file_gets_file_node(self, tmp_path: Path) -> None:
        """A scanned spec file produces a FILE node with file:<relative-path> ID."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_nodes = list(graph.nodes_by_kind(NodeKind.FILE))
        assert len(file_nodes) >= 1, f"Expected at least 1 FILE node, got {len(file_nodes)}"

        file_ids = [n.id for n in file_nodes]
        expected_id = "file:spec/reqs.md"
        assert (
            expected_id in file_ids
        ), f"Expected FILE node with ID '{expected_id}', got: {file_ids}"

    def test_REQ_d00128_A_code_file_gets_file_node(self, tmp_path: Path) -> None:
        """A scanned code file produces a FILE node with file:<relative-path> ID."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)
        _write_code_file(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_nodes = list(graph.nodes_by_kind(NodeKind.FILE))
        file_ids = [n.id for n in file_nodes]
        expected_id = "file:src/main.py"
        assert (
            expected_id in file_ids
        ), f"Expected FILE node with ID '{expected_id}', got: {file_ids}"

    def test_REQ_d00128_A_file_node_kind_is_file(self, tmp_path: Path) -> None:
        """FILE nodes have kind == NodeKind.FILE."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None
        assert file_node.kind == NodeKind.FILE


class TestFileNodeContentFields:
    """Validates REQ-d00128-B: FILE node content fields."""

    def test_REQ_d00128_B_spec_file_has_file_type(self, tmp_path: Path) -> None:
        """FILE node for spec file has file_type == FileType.SPEC."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None
        assert file_node.get_field("file_type") == FileType.SPEC

    def test_REQ_d00128_B_code_file_has_file_type(self, tmp_path: Path) -> None:
        """FILE node for code file has file_type == FileType.CODE."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)
        _write_code_file(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:src/main.py")
        assert file_node is not None
        assert file_node.get_field("file_type") == FileType.CODE

    def test_REQ_d00128_B_paths_are_set(self, tmp_path: Path) -> None:
        """FILE node has absolute_path and relative_path fields."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None
        assert file_node.get_field("relative_path") == "spec/reqs.md"
        abs_path = file_node.get_field("absolute_path")
        assert abs_path is not None
        assert str(tmp_path / "spec" / "reqs.md") == abs_path

    def test_REQ_d00128_B_repo_field_none_for_main_project(self, tmp_path: Path) -> None:
        """FILE node for main project has repo == None."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None
        assert file_node.get_field("repo") is None


class TestGitInfoCapture:
    """Validates REQ-d00128-C: git info captured once per repo."""

    def test_REQ_d00128_C_git_fields_present(self, tmp_path: Path) -> None:
        """FILE node has git_branch and git_commit fields (may be None outside git repo)."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None
        # Fields should be present (even if None when not in a git repo)
        content = file_node.get_all_content()
        assert "git_branch" in content
        assert "git_commit" in content

    def test_REQ_d00128_C_git_info_same_across_files(self, tmp_path: Path) -> None:
        """All FILE nodes from the same repo share the same git_branch and git_commit."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path, "reqs.md")
        _write_spec(
            tmp_path,
            "reqs2.md",
            content="""\
# More Requirements

## REQ-p00002: Another Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

The system SHALL do something else.

*End* *Another Requirement* | **Hash**: abcd1234

---
""",
        )

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file1 = graph.find_by_id("file:spec/reqs.md")
        file2 = graph.find_by_id("file:spec/reqs2.md")
        assert file1 is not None and file2 is not None
        assert file1.get_field("git_branch") == file2.get_field("git_branch")
        assert file1.get_field("git_commit") == file2.get_field("git_commit")


class TestContainsEdges:
    """Validates REQ-d00128-D: CONTAINS edges from FILE to top-level content nodes."""

    def test_REQ_d00128_D_file_contains_requirement(self, tmp_path: Path) -> None:
        """FILE node has CONTAINS edge to REQUIREMENT node."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None

        contains_children = list(file_node.iter_children(edge_kinds={EdgeKind.CONTAINS}))
        child_kinds = [c.kind for c in contains_children]
        assert (
            NodeKind.REQUIREMENT in child_kinds
        ), f"FILE should CONTAINS a REQUIREMENT, got kinds: {child_kinds}"

    def test_REQ_d00128_D_file_contains_code(self, tmp_path: Path) -> None:
        """FILE node has CONTAINS edge to CODE node."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)
        _write_code_file(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:src/main.py")
        assert file_node is not None

        contains_children = list(file_node.iter_children(edge_kinds={EdgeKind.CONTAINS}))
        child_kinds = [c.kind for c in contains_children]
        assert NodeKind.CODE in child_kinds, f"FILE should CONTAINS CODE, got kinds: {child_kinds}"

    def test_REQ_d00128_D_requirement_reachable_via_file_node_method(self, tmp_path: Path) -> None:
        """REQUIREMENT's file_node() returns its parent FILE node."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        req_node = graph.find_by_id("REQ-p00001")
        assert req_node is not None
        fn = req_node.file_node()
        assert fn is not None
        assert fn.kind == NodeKind.FILE
        assert fn.id == "file:spec/reqs.md"


class TestContainsEdgeMetadata:
    """Validates REQ-d00128-E: CONTAINS edge metadata."""

    def test_REQ_d00128_E_contains_edge_has_start_line(self, tmp_path: Path) -> None:
        """CONTAINS edge metadata includes start_line."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None

        for edge in file_node.iter_outgoing_edges():
            if edge.kind == EdgeKind.CONTAINS:
                assert (
                    "start_line" in edge.metadata
                ), f"CONTAINS edge to {edge.target.id} missing start_line metadata"
                assert isinstance(edge.metadata["start_line"], int)
                break
        else:
            raise AssertionError("No CONTAINS edge found from FILE node")

    def test_REQ_d00128_E_contains_edge_has_render_order(self, tmp_path: Path) -> None:
        """CONTAINS edge metadata includes render_order as float."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None

        for edge in file_node.iter_outgoing_edges():
            if edge.kind == EdgeKind.CONTAINS:
                assert (
                    "render_order" in edge.metadata
                ), f"CONTAINS edge to {edge.target.id} missing render_order"
                assert isinstance(edge.metadata["render_order"], float)
                break
        else:
            raise AssertionError("No CONTAINS edge found from FILE node")

    def test_REQ_d00128_E_render_order_sequential(self, tmp_path: Path) -> None:
        """CONTAINS edge render_order values are sequential from 0.0."""
        config = _write_config(tmp_path)
        # Write a spec with two requirements so we get multiple CONTAINS edges
        _write_spec(
            tmp_path,
            content="""\
# Test Requirements

## REQ-p00001: First Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

The system SHALL do thing one.

*End* *First Requirement* | **Hash**: abcd1234

---

## REQ-p00002: Second Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

The system SHALL do thing two.

*End* *Second Requirement* | **Hash**: abcd5678

---
""",
        )

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None

        contains_edges = [e for e in file_node.iter_outgoing_edges() if e.kind == EdgeKind.CONTAINS]
        assert (
            len(contains_edges) >= 2
        ), f"Expected at least 2 CONTAINS edges, got {len(contains_edges)}"

        orders = sorted(e.metadata["render_order"] for e in contains_edges)
        # Should be sequential 0.0, 1.0, 2.0, ...
        for i, order in enumerate(orders):
            assert order == float(
                i
            ), f"Expected render_order {float(i)} at position {i}, got {order}"


class TestAssertionsNotContained:
    """Validates REQ-d00128-F: ASSERTIONs don't get CONTAINS edges from FILE."""

    def test_REQ_d00128_F_assertions_not_direct_children_of_file(self, tmp_path: Path) -> None:
        """ASSERTION nodes are NOT direct CONTAINS children of FILE nodes."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None

        contains_children = list(file_node.iter_children(edge_kinds={EdgeKind.CONTAINS}))
        assertion_children = [c for c in contains_children if c.kind == NodeKind.ASSERTION]
        assert len(assertion_children) == 0, (
            f"ASSERTIONs should NOT be CONTAINS children of FILE, found: "
            f"{[c.id for c in assertion_children]}"
        )

    def test_REQ_d00128_F_assertions_reachable_via_structures(self, tmp_path: Path) -> None:
        """ASSERTION nodes are reachable from REQUIREMENT via STRUCTURES edges."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        req_node = graph.find_by_id("REQ-p00001")
        assert req_node is not None

        structures_children = list(req_node.iter_children(edge_kinds={EdgeKind.STRUCTURES}))
        assertion_children = [c for c in structures_children if c.kind == NodeKind.ASSERTION]
        assert (
            len(assertion_children) > 0
        ), "ASSERTIONs should be STRUCTURES children of REQUIREMENT"

    def test_REQ_d00128_F_section_remainder_not_contained_by_file(self, tmp_path: Path) -> None:
        """Requirement-level REMAINDER sections are NOT CONTAINS children of FILE."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None

        # Check that requirement-level REMAINDER sections (section:N IDs) are not
        # direct CONTAINS children of FILE
        contains_children = list(file_node.iter_children(edge_kinds={EdgeKind.CONTAINS}))
        section_remainders = [
            c for c in contains_children if c.kind == NodeKind.REMAINDER and ":section:" in c.id
        ]
        assert len(section_remainders) == 0, (
            f"Requirement-level REMAINDER sections should NOT be CONTAINS children of FILE, "
            f"found: {[c.id for c in section_remainders]}"
        )


class TestRemainderParserRegistration:
    """Validates REQ-d00128-G, REQ-d00128-H: RemainderParser registration."""

    def test_REQ_d00128_G_spec_files_have_remainder_nodes(self, tmp_path: Path) -> None:
        """Spec files produce file-level REMAINDER nodes for unclaimed lines."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None

        contains_children = list(file_node.iter_children(edge_kinds={EdgeKind.CONTAINS}))
        remainder_children = [c for c in contains_children if c.kind == NodeKind.REMAINDER]
        # The spec file has a "# Test Requirements" heading and "---" separator
        # which are not claimed by RequirementParser, so RemainderParser should claim them
        assert (
            len(remainder_children) > 0
        ), "RemainderParser should produce REMAINDER nodes for unclaimed lines in spec files"

    def test_REQ_d00128_G_code_files_have_remainder_nodes(self, tmp_path: Path) -> None:
        """Code files produce file-level REMAINDER nodes for non-Implements lines."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)
        _write_code_file(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        file_node = graph.find_by_id("file:src/main.py")
        assert file_node is not None

        contains_children = list(file_node.iter_children(edge_kinds={EdgeKind.CONTAINS}))
        remainder_children = [c for c in contains_children if c.kind == NodeKind.REMAINDER]
        # The code file has "def work(): pass\n" which is unclaimed
        assert (
            len(remainder_children) > 0
        ), "RemainderParser should produce REMAINDER nodes for unclaimed lines in code files"


class TestExistingBehaviorUnaffected:
    """Validates REQ-d00128-I: FILE nodes are additive, existing behavior unaffected."""

    def test_REQ_d00128_I_traceability_still_works(self, tmp_path: Path) -> None:
        """Requirements still have implementing code and coverage works."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)
        _write_code_file(tmp_path, req_id="REQ-p00001-A")

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        req_node = graph.find_by_id("REQ-p00001")
        assert req_node is not None

        # Coverage should still work
        coverage_pct = req_node.get_metric("coverage_pct")
        assert coverage_pct is not None, "coverage_pct should still be set"
        assert coverage_pct == 100.0

    def test_REQ_d00128_I_roots_unchanged(self, tmp_path: Path) -> None:
        """Graph roots are still REQUIREMENT nodes, not FILE nodes."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        roots = list(graph.iter_roots())
        root_kinds = {r.kind for r in roots}
        # FILE nodes should NOT appear in roots (they're filtered out or excluded)
        assert NodeKind.FILE not in root_kinds, "FILE nodes should NOT appear in graph roots"
        # REQUIREMENT should still be a root
        assert NodeKind.REQUIREMENT in root_kinds, "REQUIREMENT should still be a root"

    def test_REQ_d00128_I_orphan_detection_unaffected(self, tmp_path: Path) -> None:
        """Orphan detection is not affected by FILE nodes."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        # The requirement should not be an orphan
        orphan_ids = graph._orphaned_ids
        assert "REQ-p00001" not in orphan_ids

    def test_REQ_d00128_I_node_count_includes_file_nodes(self, tmp_path: Path) -> None:
        """FILE nodes are included in the graph index (findable by ID)."""
        config = _write_config(tmp_path)
        _write_spec(tmp_path)

        graph = build_graph(
            config_path=config,
            repo_root=tmp_path,
            scan_code=False,
            scan_tests=False,
            scan_sponsors=False,
        )

        # FILE node should be findable
        file_node = graph.find_by_id("file:spec/reqs.md")
        assert file_node is not None

        # Total node count should include FILE nodes
        all_nodes = list(graph.all_nodes())
        file_nodes_in_all = [n for n in all_nodes if n.kind == NodeKind.FILE]
        assert len(file_nodes_in_all) >= 1
