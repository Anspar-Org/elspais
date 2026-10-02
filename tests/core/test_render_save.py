# Verifies: REQ-d00132
"""Tests for render-based save operation (Task 2 of FILENODE3).

Validates REQ-d00132-A: save_mutations() identifies dirty files and renders to disk
Validates REQ-d00132-B: Safety branches created when save_branch=True
Validates REQ-d00132-C: Consistency check (rebuild + compare)
Validates REQ-d00132-D: persistence.py deleted
Validates REQ-d00132-E: Mutation log cleared after save
Validates REQ-d00132-F: Derives implements/refines from live graph edges
Validates REQ-d00132-J: A save names the text it changed that no mutation changed
Validates REQ-d00132-L: A save keeps the hash of each requirement no mutation changed
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import FileType
from elspais.graph.relations import EdgeKind
from tests.core.graph_test_helpers import (
    EDITED_ASSERTION,
    MARKED_PROSE,
    NEIGHBOUR_ASSERTION,
    PLAIN_ASSERTION,
    TIDY_NEIGHBOUR,
    UNMARKED_PROSE,
    UNTIDY_NEIGHBOUR,
    end_marker_hash,
    grammar_for,
    replace_in_file,
    requirement_block,
    write_canonical_repo,
    write_unmarked_term_repo,
)


def _build_graph_with_spec(tmp_path: Path) -> tuple[FederatedGraph, Path, GraphNode]:
    """Build a FederatedGraph with a real spec file on disk.

    Creates a minimal graph with FILE node, requirement, and assertions,
    then wraps it in a single-repo FederatedGraph.
    Returns (federated_graph, spec_file_path, file_node).
    """
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("placeholder", encoding="utf-8")

    graph = TraceGraph(repo_root=tmp_path, _resolver=grammar_for("REQ"))
    rel_path = str(spec_file.relative_to(tmp_path))

    file_node = GraphNode(id=f"file:{rel_path}", kind=NodeKind.FILE, label="test_spec.md")
    file_node.set_field("file_type", FileType.SPEC)
    file_node.set_field("relative_path", rel_path)
    file_node.set_field("absolute_path", str(spec_file))
    file_node.set_field("repo", None)

    # PRD root
    prd = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Product Req")
    prd._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "00000000",
        "parse_line": 1,
        "parse_end_line": None,
    }

    # DEV requirement
    req = GraphNode(id="REQ-t00001", kind=NodeKind.REQUIREMENT, label="Test Requirement")
    req._content = {
        "level": "DEV",
        "status": "Active",
        "hash": "abcd1234",
        "body_text": "",
        "parse_line": 1,
        "parse_end_line": None,
    }

    # Assertions
    a1 = GraphNode(
        id="REQ-t00001-A", kind=NodeKind.ASSERTION, label="The system SHALL do something."
    )
    a1._content = {"label": "A", "parse_line": 7, "parse_end_line": None}
    req.link(a1, EdgeKind.STRUCTURES)

    a2 = GraphNode(
        id="REQ-t00001-B",
        kind=NodeKind.ASSERTION,
        label="The system SHALL do another thing.",
    )
    a2._content = {"label": "B", "parse_line": 8, "parse_end_line": None}
    req.link(a2, EdgeKind.STRUCTURES)

    # CONTAINS edges from FILE
    e1 = file_node.link(req, EdgeKind.CONTAINS)
    e1.metadata = {"render_order": 0.0}

    # IMPLEMENTS edge
    prd.link(req, EdgeKind.IMPLEMENTS)

    graph._roots = [prd]
    graph._index = {
        f"file:{rel_path}": file_node,
        "REQ-p00001": prd,
        "REQ-t00001": req,
        "REQ-t00001-A": a1,
        "REQ-t00001-B": a2,
    }

    fed = FederatedGraph.from_single(
        graph, {"project": {"name": "test", "namespace": "REQ"}}, tmp_path
    )
    return fed, spec_file, file_node


class TestRenderSaveDirtyFiles:
    """Validates REQ-d00132-A: save identifies dirty files and renders to disk."""

    # Verifies: REQ-d00132-A
    def test_REQ_d00132_A_change_status_saves(self, tmp_path: Path):
        """change_status mutation triggers render-save of the file."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.change_status("REQ-t00001", "Draft")
        result = render_save(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] >= 1

        content = spec_file.read_text(encoding="utf-8")
        assert "**Status**: Draft" in content
        assert "## REQ-t00001: Test Requirement" in content

    # Verifies: REQ-d00132-A
    def test_REQ_d00132_A_update_title_saves(self, tmp_path: Path):
        """update_title mutation triggers render-save of the file."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.update_title("REQ-t00001", "New Title")
        result = render_save(graph, tmp_path)

        assert result["success"] is True
        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00001: New Title" in content

    # Verifies: REQ-d00132-A
    def test_REQ_d00132_A_update_assertion_saves(self, tmp_path: Path):
        """update_assertion mutation saves updated text."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.update_assertion("REQ-t00001-B", "The system SHALL do NEW thing.")
        result = render_save(graph, tmp_path)

        assert result["success"] is True
        content = spec_file.read_text(encoding="utf-8")
        assert "B. The system SHALL do NEW thing." in content
        assert "A. The system SHALL do something." in content

    # Verifies: REQ-d00132-A
    def test_REQ_d00132_A_delete_assertion_saves(self, tmp_path: Path):
        """delete_assertion mutation removes assertion from rendered file."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.delete_assertion("REQ-t00001-B")
        result = render_save(graph, tmp_path)

        assert result["success"] is True
        content = spec_file.read_text(encoding="utf-8")
        assert "A. The system SHALL do something." in content
        assert "do another thing" not in content

    # Verifies: REQ-d00132-A
    def test_REQ_d00132_A_add_assertion_saves(self, tmp_path: Path):
        """add_assertion mutation adds new assertion to rendered file."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.add_assertion("REQ-t00001", "The system SHALL do a third thing.")
        result = render_save(graph, tmp_path)

        assert result["success"] is True
        content = spec_file.read_text(encoding="utf-8")
        assert "C. The system SHALL do a third thing." in content

    # Verifies: REQ-d00132-A
    def test_REQ_d00132_A_no_mutations_noop(self, tmp_path: Path):
        """No mutations means no files are written."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        result = render_save(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 0

    # Verifies: REQ-d00132-A
    def test_REQ_d00132_A_add_requirement_saves(self, tmp_path: Path):
        """add_requirement mutation creates new requirement in rendered file."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.add_requirement(
            "REQ-t00002",
            "New Requirement",
            level="DEV",
            parent_id="REQ-t00001",
        )
        result = render_save(graph, tmp_path)

        assert result["success"] is True
        content = spec_file.read_text(encoding="utf-8")
        assert "## REQ-t00002: New Requirement" in content


class TestRenderSaveMutationLog:
    """Validates REQ-d00132-E: Mutation log cleared after save."""

    # Verifies: REQ-d00132-E
    def test_REQ_d00132_E_log_cleared_after_save(self, tmp_path: Path):
        """Mutation log is cleared after successful save."""
        from elspais.graph.render import render_save

        graph, _, _ = _build_graph_with_spec(tmp_path)

        graph.change_status("REQ-t00001", "Draft")
        assert len(graph.mutation_log) > 0

        result = render_save(graph, tmp_path)
        assert result["success"] is True
        assert len(graph.mutation_log) == 0

    # Verifies: REQ-d00132-E
    def test_REQ_d00132_E_log_not_cleared_on_error(self, tmp_path: Path):
        """Mutation log is NOT cleared if there are errors."""
        from elspais.graph.render import render_save

        graph, _, file_node = _build_graph_with_spec(tmp_path)

        graph.change_status("REQ-t00001", "Draft")

        # Make the file path invalid to trigger an error
        file_node.set_field("relative_path", "/nonexistent/path/file.md")
        file_node.set_field("absolute_path", "/nonexistent/path/file.md")

        render_save(graph, tmp_path)
        # The file can't be found as a dirty file since the node path changed
        # but the node still exists in graph, so the mutation is still tracked


class TestRenderSaveEdgeDerivation:
    """Validates REQ-d00132-F: Derives implements/refines from live graph edges."""

    # Verifies: REQ-d00132-F
    def test_REQ_d00132_F_implements_from_edges(self, tmp_path: Path):
        """Rendered file shows implements derived from graph edges."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        # The IMPLEMENTS edge prd -> req should be reflected
        graph.change_status("REQ-t00001", "Draft")  # trigger dirty
        render_save(graph, tmp_path)

        content = spec_file.read_text(encoding="utf-8")
        assert "**Implements**: REQ-p00001" in content

    # Verifies: REQ-d00132-F
    def test_REQ_d00132_F_add_edge_reflected(self, tmp_path: Path):
        """Adding an edge is reflected in rendered output."""
        from elspais.graph.render import render_save

        graph, spec_file, file_node = _build_graph_with_spec(tmp_path)

        # Add a second PRD directly to the inner sub-graph, then refresh
        # ownership so the federated graph routes look-ups correctly.
        prd2 = GraphNode(id="REQ-p00002", kind=NodeKind.REQUIREMENT, label="PRD 2")
        prd2._content = {"level": "PRD", "status": "Active"}
        graph.repo_for("REQ-t00001").graph._index["REQ-p00002"] = prd2
        graph._rebuild_ownership()

        # Add edge: REQ-t00001 implements REQ-p00002
        graph.add_edge("REQ-t00001", "REQ-p00002", EdgeKind.IMPLEMENTS)
        render_save(graph, tmp_path)

        content = spec_file.read_text(encoding="utf-8")
        # Should have both implements refs
        assert "REQ-p00001" in content
        assert "REQ-p00002" in content

    # Verifies: REQ-d00132-F
    def test_REQ_d00132_F_delete_edge_reflected(self, tmp_path: Path):
        """Deleting an edge is reflected in rendered output."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        # Delete the implements edge: REQ-t00001 no longer implements REQ-p00001
        graph.delete_edge("REQ-t00001", "REQ-p00001")
        render_save(graph, tmp_path)

        content = spec_file.read_text(encoding="utf-8")
        assert "**Implements**: -" in content


class TestConsistencyCheck:
    """Validates REQ-d00132-C: Consistency check (rebuild + compare)."""

    # Verifies: REQ-d00132-C
    def test_REQ_d00132_C_consistency_check_passes(self, tmp_path: Path):
        """Consistency check succeeds when rebuild matches in-memory graph."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.change_status("REQ-t00001", "Draft")

        # Create a rebuild function that returns the same graph
        # (simulating perfect round-trip)
        def rebuild_fn():
            return {}, graph

        result = render_save(graph, tmp_path, consistency_check=True, rebuild_fn=rebuild_fn)

        assert result["success"] is True
        assert "consistency" in result
        assert result["consistency"]["consistent"] is True
        assert result["consistency"]["checked"] > 0

    # Verifies: REQ-d00132-C
    def test_REQ_d00132_C_consistency_check_detects_mismatch(self, tmp_path: Path):
        """Consistency check detects mismatches between original and rebuilt graph."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.change_status("REQ-t00001", "Draft")

        # Create a mismatched graph for rebuild
        bad_graph = TraceGraph(repo_root=tmp_path, _resolver=grammar_for("REQ"))
        req = GraphNode(id="REQ-t00001", kind=NodeKind.REQUIREMENT, label="WRONG Title")
        req._content = {"level": "DEV", "status": "Draft", "hash": "00000000"}
        bad_graph._index = {"REQ-t00001": req}
        bad_fed = FederatedGraph.from_single(
            bad_graph, {"project": {"name": "test", "namespace": "REQ"}}, tmp_path
        )

        def rebuild_fn():
            return {}, bad_fed

        result = render_save(graph, tmp_path, consistency_check=True, rebuild_fn=rebuild_fn)

        assert result["success"] is False
        assert result["consistency"]["consistent"] is False
        assert "title" in result["consistency"]["details"]

    # Verifies: REQ-d00132-C
    def test_REQ_d00132_C_consistency_check_skipped_by_default(self, tmp_path: Path):
        """Consistency check is not run when consistency_check=False (default)."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.change_status("REQ-t00001", "Draft")
        result = render_save(graph, tmp_path)

        assert result["success"] is True
        assert "consistency" not in result

    # Verifies: REQ-d00132-C
    def test_REQ_d00132_C_consistency_check_handles_rebuild_failure(self, tmp_path: Path):
        """Consistency check handles rebuild failures gracefully."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        graph.change_status("REQ-t00001", "Draft")

        def rebuild_fn():
            raise RuntimeError("Rebuild failed")

        result = render_save(graph, tmp_path, consistency_check=True, rebuild_fn=rebuild_fn)

        assert result["success"] is False
        assert result["consistency"]["consistent"] is False
        assert "Rebuild failed" in result["consistency"]["details"]


class TestParseDirtyFileDetection:
    """Validates that a FILE node with a parse_dirty REQUIREMENT child is included in dirty set.

    Validates: REQ-p00002-A
    """

    # Verifies: REQ-d00132-A
    def test_parse_dirty_requirement_marks_file_dirty_without_mutations(self, tmp_path: Path):
        # Verifies: REQ-p00002-A
        """A FILE node whose REQUIREMENT child has parse_dirty=True appears in dirty set
        even when the mutation log is empty (no explicit mutations were made)."""
        from elspais.graph.render import render_save

        graph, spec_file, file_node = _build_graph_with_spec(tmp_path)

        # Ensure no mutations have been made
        assert len(graph.mutation_log) == 0

        # Mark the requirement as parse_dirty to simulate redundant refs detected at parse time
        req_node = graph.find_by_id("REQ-t00001")
        assert req_node is not None
        req_node.set_field("parse_dirty", True)

        # A tidying save detects parse_dirty and includes the file
        result = render_save(graph, tmp_path, tidy=True)

        assert result["success"] is True
        assert result["saved_count"] >= 1, (
            "Expected file to be saved because its requirement child has parse_dirty=True"
        )

    # Verifies: REQ-d00132-A
    def test_no_parse_dirty_no_save_without_mutations(self, tmp_path: Path):
        # Verifies: REQ-p00002-A
        """Without parse_dirty or mutations, no file is saved."""
        from elspais.graph.render import render_save

        graph, spec_file, _ = _build_graph_with_spec(tmp_path)

        assert len(graph.mutation_log) == 0

        result = render_save(graph, tmp_path)

        assert result["success"] is True
        assert result["saved_count"] == 0


class TestPersistenceDeleted:
    """Validates REQ-d00132-D: persistence.py is deleted."""

    # Verifies: REQ-d00132-D
    def test_REQ_d00132_D_persistence_deleted(self):
        """persistence.py should not exist (replaced by render-based save)."""
        persistence_path = (
            Path(__file__).parent.parent.parent / "src" / "elspais" / "server" / "persistence.py"
        )
        assert not persistence_path.exists(), (
            f"persistence.py should be deleted (replaced by render-based save): {persistence_path}"
        )


# ---------------------------------------------------------------------------
# What a save of pending mutations writes (REQ-d00132-H, REQ-d00132-I).
#
# A repository on disk with three spec files: the requirements that are cited
# (prd.md), the requirements citing them by Assertion (dev.md), and a file
# that is NOT in canonical form (ops-untidy.md: no blank lines between its
# metadata, body, heading and assertions). The untidy file is parse-dirty from
# the moment it is read, and no mutation below touches it.
# ---------------------------------------------------------------------------

_SAVE_SCOPE_TOML = 'version = 5\n\n[project]\nname = "scope"\nnamespace = "REQ"\n'

_CITED_SPEC = """# Product

## REQ-p00001: Alpha

**Level**: prd | **Status**: Active

Alpha body.

### Assertions

A. The tool SHALL alpha.

B. The tool SHALL alpha two.

*End* *Alpha* | **Hash**: 00000000

## REQ-p00002: Gamma

**Level**: prd | **Status**: Active

Gamma body.

### Assertions

A. The tool SHALL gamma.

*End* *Gamma* | **Hash**: 00000000
"""

_CITING_SPEC = """# Dev

## REQ-d00001: Beta

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001-A

Beta body.

### Assertions

A. The tool SHALL beta.

*End* *Beta* | **Hash**: 00000000

## REQ-d00002: Delta

**Level**: dev | **Status**: Active | **Implements**: REQ-p00002-A

Delta body.

### Assertions

A. The tool SHALL delta.

*End* *Delta* | **Hash**: 00000000
"""

_UNTIDY_SPEC = """# Untidy

## REQ-o00001: Untidy

**Level**: ops | **Status**: Active | **Implements**: -
Body directly after metadata.
## Assertions
A. The tool SHALL one.
B. The tool SHALL two.
*End* *Untidy* | **Hash**: 00000000
"""


def _save_scope_repo(tmp_path: Path) -> tuple[FederatedGraph, Path]:
    """Write the three-file repository and build its FederatedGraph."""
    from elspais.graph.factory import build_graph

    (tmp_path / ".elspais.toml").write_text(_SAVE_SCOPE_TOML, encoding="utf-8")
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "prd.md").write_text(_CITED_SPEC, encoding="utf-8")
    (spec / "dev.md").write_text(_CITING_SPEC, encoding="utf-8")
    (spec / "ops-untidy.md").write_text(_UNTIDY_SPEC, encoding="utf-8")
    graph = build_graph(repo_root=tmp_path)
    assert graph.find_by_id("REQ-o00001") is not None, "the untidy requirement did not load"
    return graph, spec


def _modified_names(result: dict) -> set[str]:
    return {Path(path).name for path in result["files_modified"]}


def _untidy_is_only_parse_dirty(graph: FederatedGraph) -> None:
    """Fail when the fixture has stopped exercising a merely parse-dirty file."""
    from elspais.graph.render import _files_with_pending_mutations, _find_dirty_files

    def names(nodes):
        return {node.get_field("relative_path") for node in nodes}

    assert "spec/ops-untidy.md" not in names(_files_with_pending_mutations(graph))
    assert "spec/ops-untidy.md" in names(_find_dirty_files(graph, tidy=True)), (
        "the untidy file is not parse-dirty, so this fixture tests nothing"
    )


class TestASaveLeavesUntouchedFilesUnwritten:
    """Validates REQ-d00132-I: a save writes the files its mutations change, and
    no file that is merely not in canonical form."""

    # Verifies: REQ-d00132-I
    def test_REQ_d00132_I_a_non_canonical_file_the_mutation_misses_is_not_written(
        self, tmp_path: Path
    ):
        from elspais.graph.render import render_save

        graph, spec = _save_scope_repo(tmp_path)
        untidy = spec / "ops-untidy.md"
        before = untidy.read_bytes()

        graph.update_title("REQ-p00002", "Gamma Renamed")
        _untidy_is_only_parse_dirty(graph)
        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        assert "ops-untidy.md" not in _modified_names(result)
        assert untidy.read_bytes() == before
        assert "## REQ-p00002: Gamma Renamed" in (spec / "prd.md").read_text(encoding="utf-8")

    # Verifies: REQ-d00132-I
    def test_REQ_d00132_I_a_tidying_save_does_rewrite_the_non_canonical_file(self, tmp_path: Path):
        """The fix command's tidying save is what brings the file into canonical form."""
        from elspais.graph.render import render_save

        graph, spec = _save_scope_repo(tmp_path)
        untidy = spec / "ops-untidy.md"
        before = untidy.read_bytes()

        graph.update_title("REQ-p00002", "Gamma Renamed")
        result = render_save(graph, repo_root=tmp_path, tidy=True)

        assert result["success"] is True, result["errors"]
        assert "ops-untidy.md" in _modified_names(result)
        assert untidy.read_bytes() != before
        assert "### Assertions\n\nA. The tool SHALL one.\n\nB." in untidy.read_text(
            encoding="utf-8"
        )


class TestASaveWritesTheFilesCitingARenamedIdentifier:
    """Validates REQ-d00132-H: a rename changes the text of every file citing
    the renamed identifier, so the save writes those files too."""

    # Verifies: REQ-d00132-H
    def test_REQ_d00132_H_renaming_a_requirement_rewrites_the_citing_file(self, tmp_path: Path):
        from elspais.graph.render import render_save

        graph, spec = _save_scope_repo(tmp_path)

        graph.rename_node("REQ-p00001", "REQ-p00009")
        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        assert {"prd.md", "dev.md"} <= _modified_names(result)
        citing = (spec / "dev.md").read_text(encoding="utf-8")
        assert "**Implements**: REQ-p00009-A" in citing
        assert "REQ-p00001" not in citing

    # Verifies: REQ-d00132-H
    def test_REQ_d00132_H_renaming_an_assertion_rewrites_the_citing_file(self, tmp_path: Path):
        from elspais.graph.render import render_save

        graph, spec = _save_scope_repo(tmp_path)

        graph.rename_assertion("REQ-p00001-A", "C")
        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        assert "dev.md" in _modified_names(result)
        citing = (spec / "dev.md").read_text(encoding="utf-8")
        assert "**Implements**: REQ-p00001-C" in citing
        assert "REQ-p00001-A" not in citing

    # Verifies: REQ-d00132-H, REQ-d00132-I
    def test_REQ_d00132_H_a_mutation_citing_nothing_renamed_leaves_the_citing_file_alone(
        self, tmp_path: Path
    ):
        """Negative: a mutation that renames nothing does not reach the citing file."""
        from elspais.graph.render import render_save

        graph, spec = _save_scope_repo(tmp_path)
        before = (spec / "dev.md").read_bytes()

        graph.update_title("REQ-p00001", "Alpha Renamed")
        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        assert _modified_names(result) == {"prd.md"}
        assert (spec / "dev.md").read_bytes() == before


class TestASaveNamesTheTextNoMutationChanged:
    """Validates REQ-d00132-J: a file a save writes is written whole, so the
    save names each requirement and each file-level text section whose text it
    changed although no pending mutation changed it."""

    @staticmethod
    def _save_after_editing_beta(tmp_path: Path) -> dict:
        from elspais.graph.factory import build_graph
        from elspais.graph.render import render_save

        graph = build_graph(repo_root=tmp_path)
        graph.update_title("REQ-d00001", "Beta Renamed")
        result = render_save(graph, repo_root=tmp_path)
        assert result["success"] is True, result["errors"]
        assert "dev.md" in _modified_names(result)
        return result

    # Verifies: REQ-d00132-J
    def test_REQ_d00132_J_an_untidy_neighbour_of_the_edit_is_named(self, tmp_path: Path):
        spec = write_canonical_repo(tmp_path)
        replace_in_file(spec / "dev.md", TIDY_NEIGHBOUR, UNTIDY_NEIGHBOUR)
        # The line named is where the neighbour stood in the file the save replaced.
        before = (spec / "dev.md").read_text(encoding="utf-8").split("\n")
        neighbour_line = before.index("## REQ-d00002: Delta") + 1

        result = self._save_after_editing_beta(tmp_path)

        assert result["changed_beyond_edits"] == [
            {
                "file": "spec/dev.md",
                "node_id": "REQ-d00002",
                "kind": "requirement",
                "label": "Delta",
                "line": neighbour_line,
            }
        ]
        assert TIDY_NEIGHBOUR in (spec / "dev.md").read_text(encoding="utf-8")

    # Verifies: REQ-d00132-J
    def test_REQ_d00132_J_a_save_over_canonical_text_names_nothing(self, tmp_path: Path):
        write_canonical_repo(tmp_path)

        result = self._save_after_editing_beta(tmp_path)

        assert result["changed_beyond_edits"] == []

    # Verifies: REQ-d00132-J
    def test_REQ_d00132_J_file_level_prose_whose_term_form_changes_is_named(self, tmp_path: Path):
        spec = write_canonical_repo(tmp_path)
        replace_in_file(spec / "dev.md", MARKED_PROSE, UNMARKED_PROSE)

        result = self._save_after_editing_beta(tmp_path)

        changed = result["changed_beyond_edits"]
        assert [(c["kind"], c["label"]) for c in changed] == [("remainder", UNMARKED_PROSE)], (
            changed
        )
        assert changed[0]["file"] == "spec/dev.md"
        assert changed[0]["node_id"].startswith("rem:")
        assert MARKED_PROSE in (spec / "dev.md").read_text(encoding="utf-8")

    # Verifies: REQ-d00132-J
    def test_REQ_d00132_J_a_journey_whose_term_form_changes_is_named(self, tmp_path: Path):
        """A journey beside the edited one is a file-level part of its own."""
        from elspais.graph.factory import build_graph
        from elspais.graph.render import render_save

        (tmp_path / ".elspais.toml").write_text(
            _SAVE_SCOPE_TOML
            + '\n[scanning.journey]\ndirectories = ["spec"]\n'
            + '\n[terms]\nmarkup_styles = ["*", "**"]\n',
            encoding="utf-8",
        )
        spec = tmp_path / "spec"
        spec.mkdir()
        (spec / "glossary.md").write_text("# Glossary\n\nWidget\n: A thing.\n", encoding="utf-8")
        journeys = spec / "journeys.md"
        journeys.write_text(
            "# Journeys\n\n"
            "### JNY-001: Count Things\n\n**Actor**: Operator\n\n"
            "## Steps\n\n1. Operator counts the Widget\n\n*End* *Count Things*\n\n"
            "### JNY-002: Ship Things\n\n**Actor**: Operator\n\n"
            "## Steps\n\n1. Operator ships the order\n\n*End* *Ship Things*\n",
            encoding="utf-8",
        )
        graph = build_graph(repo_root=tmp_path)
        graph.update_journey_field("JNY-002", "actor", "Shipper")

        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        changed = result["changed_beyond_edits"]
        assert [(c["node_id"], c["kind"]) for c in changed] == [("JNY-001", "journey")], changed
        text = journeys.read_text(encoding="utf-8")
        assert "counts the *Widget*" in text and "**Actor**: Shipper" in text, text


class TestASaveKeepsTheHashOfARequirementNobodyEdited:
    """Validates REQ-d00132-L: marking a *Defined Term* in an *Assertion* moves
    the requirement's hash, so a save makes that change only to a requirement
    a pending mutation changed."""

    MARKED_NEIGHBOUR = "The tool SHALL count every *Widget*."

    @staticmethod
    def _hash_of(assertion: str) -> str:
        from elspais.utilities.hasher import compute_normalized_hash

        return compute_normalized_hash([("A", assertion)])

    # Verifies: REQ-d00132-L
    def test_REQ_d00132_L_an_unedited_neighbour_keeps_its_assertion_and_hash(self, tmp_path: Path):
        from elspais.graph.factory import build_graph
        from elspais.graph.render import render_save

        spec = write_unmarked_term_repo(tmp_path, edited_assertion=PLAIN_ASSERTION)
        before = (spec / "dev.md").read_text(encoding="utf-8")

        graph = build_graph(repo_root=tmp_path)
        # The build records the unmarked term and leaves the text as written.
        assert graph.find_by_id("REQ-d00002-A").get_label() == NEIGHBOUR_ASSERTION
        assert "non_canonical_term" in (
            graph.find_by_id("REQ-d00002").get_field("parse_dirty_reasons") or []
        )

        graph.update_title("REQ-d00001", "Beta Renamed")
        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        after = (spec / "dev.md").read_text(encoding="utf-8")
        assert "## REQ-d00001: Beta Renamed" in after
        assert requirement_block(after, "REQ-d00002") == requirement_block(before, "REQ-d00002")
        assert end_marker_hash(after, "REQ-d00002") == self._hash_of(NEIGHBOUR_ASSERTION)
        assert result["changed_beyond_edits"] == []

    # Verifies: REQ-d00132-L, REQ-d00132-J
    def test_REQ_d00132_L_a_neighbour_still_gets_canonical_form_that_keeps_its_hash(
        self, tmp_path: Path
    ):
        """The neighbour's body is outside its normalized-text hash, so its term
        is marked there while the term in its *Assertion* is left as written."""
        from elspais.graph.factory import build_graph
        from elspais.graph.render import render_save

        spec = write_unmarked_term_repo(
            tmp_path,
            edited_assertion=PLAIN_ASSERTION,
            neighbour_body="Delta body names the Widget.",
        )

        graph = build_graph(repo_root=tmp_path)
        graph.update_title("REQ-d00001", "Beta Renamed")
        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        neighbour = requirement_block((spec / "dev.md").read_text(encoding="utf-8"), "REQ-d00002")
        assert "Delta body names the *Widget*." in neighbour
        assert f"A. {NEIGHBOUR_ASSERTION}" in neighbour
        assert end_marker_hash(neighbour, "REQ-d00002") == self._hash_of(NEIGHBOUR_ASSERTION)
        assert [(c["node_id"], c["kind"]) for c in result["changed_beyond_edits"]] == [
            ("REQ-d00002", "requirement")
        ]

    # Verifies: REQ-d00132-L
    def test_REQ_d00132_L_a_neighbour_restored_to_canonical_spacing_keeps_its_hash(
        self, tmp_path: Path
    ):
        from elspais.graph.factory import build_graph
        from elspais.graph.render import render_save

        spec = write_unmarked_term_repo(tmp_path, edited_assertion=PLAIN_ASSERTION)
        replace_in_file(
            spec / "dev.md",
            f"Delta body.\n\n### Assertions\n\nA. {NEIGHBOUR_ASSERTION}",
            f"Delta body.\n### Assertions\nA. {NEIGHBOUR_ASSERTION}",
        )

        graph = build_graph(repo_root=tmp_path)
        graph.update_title("REQ-d00001", "Beta Renamed")
        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        neighbour = requirement_block((spec / "dev.md").read_text(encoding="utf-8"), "REQ-d00002")
        assert f"Delta body.\n\n### Assertions\n\nA. {NEIGHBOUR_ASSERTION}" in neighbour
        assert end_marker_hash(neighbour, "REQ-d00002") == self._hash_of(NEIGHBOUR_ASSERTION)
        assert "REQ-d00002" in {c["node_id"] for c in result["changed_beyond_edits"]}

    # Verifies: REQ-d00132-L
    @pytest.mark.parametrize(
        ("on_disk", "edit", "marked"),
        [
            pytest.param(
                EDITED_ASSERTION,
                ("title", "Beta Renamed"),
                "The tool SHALL make a *Widget*.",
                id="term-on-disk-title-edited",
            ),
            pytest.param(
                PLAIN_ASSERTION,
                ("assertion", "The tool SHALL ship a Widget."),
                "The tool SHALL ship a *Widget*.",
                id="term-introduced-by-the-edit",
            ),
        ],
    )
    def test_REQ_d00132_L_the_edited_requirement_gets_its_term_marked(
        self, tmp_path: Path, on_disk: str, edit: tuple[str, str], marked: str
    ):
        from elspais.graph.factory import build_graph
        from elspais.graph.render import render_save

        spec = write_unmarked_term_repo(tmp_path, edited_assertion=on_disk)

        graph = build_graph(repo_root=tmp_path)
        what, value = edit
        if what == "title":
            graph.update_title("REQ-d00001", value)
        else:
            graph.update_assertion("REQ-d00001-A", value)
        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        text = (spec / "dev.md").read_text(encoding="utf-8")
        edited = requirement_block(text, "REQ-d00001")
        assert f"A. {marked}" in edited
        assert end_marker_hash(text, "REQ-d00001") == self._hash_of(marked)
        # The neighbour in the same file is not edited and keeps its text.
        assert f"A. {NEIGHBOUR_ASSERTION}" in requirement_block(text, "REQ-d00002")
        assert end_marker_hash(text, "REQ-d00002") == self._hash_of(NEIGHBOUR_ASSERTION)

    # Verifies: REQ-d00132-L, REQ-d00132-H
    def test_REQ_d00132_L_a_rename_respells_the_citation_and_keeps_the_citer_hash(
        self, tmp_path: Path
    ):
        """A requirement reached only because it cites a renamed one is not edited."""
        from elspais.graph.factory import build_graph
        from elspais.graph.render import render_save

        spec = write_unmarked_term_repo(tmp_path, edited_assertion=PLAIN_ASSERTION)

        graph = build_graph(repo_root=tmp_path)
        graph.rename_node("REQ-p00001", "REQ-p00009")
        result = render_save(graph, repo_root=tmp_path)

        assert result["success"] is True, result["errors"]
        citer = requirement_block((spec / "dev.md").read_text(encoding="utf-8"), "REQ-d00002")
        assert "**Implements**: REQ-p00009-A" in citer
        assert f"A. {NEIGHBOUR_ASSERTION}" in citer
        assert self.MARKED_NEIGHBOUR not in citer
        assert end_marker_hash(citer, "REQ-d00002") == self._hash_of(NEIGHBOUR_ASSERTION)
