"""Deleting a requirement whose status is in the active role.

An active requirement is retired in place: it keeps its identifier, its
assertions and every reference to it, and takes the one status the
configuration declares in the retired role (REQ-p00017-D). Where the
configuration declares several retired-role statuses, or none, the tool
cannot tell which status the author means, so the deletion is refused and
the declared statuses are reported (REQ-p00017-N). A provisional requirement
is still removed. The viewer route and the MCP tool answer alike
(REQ-o00062-O).

Each test writes a small repository into ``tmp_path`` because the status
roles come from the repository's configuration and the retirement is
observable through a save and rebuild.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from elspais.graph import render
from elspais.graph.builder import RetiredRequirementError
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.graph.render import render_save
from tests.core.graph_test_helpers import build_graph as build_bare_graph
from tests.core.graph_test_helpers import comparable_mutation_result, make_requirement

_CONFIG = """version = 5

[project]
name = "retire"
namespace = "REQ"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "prd"]

[scanning.spec]
directories = ["spec"]

[scanning.code]
directories = ["src"]
"""

PARENT = "REQ-p00001"
CHILD = "REQ-d00001"

# The status roles each project declares. Every role is written out, so the
# set of retired-role statuses is exactly the one under test.
ONE_RETIRED = ["Deprecated"]
SEVERAL_RETIRED = ["Deprecated", "Superseded", "Rejected"]
NONE_RETIRED: list[str] = []


def _roles(retired: list[str]) -> str:
    quoted = ", ".join(f'"{status}"' for status in retired)
    return (
        "\n[rules.format.status_roles]\n"
        'active = ["Active"]\n'
        'provisional = ["Draft"]\n'
        'aspirational = ["Roadmap"]\n'
        f"retired = [{quoted}]\n"
    )


def _prd(status: str) -> str:
    return (
        f"# {PARENT}: Parent\n\n"
        f"**Level**: prd | **Status**: {status} | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. The tool SHALL do alpha.\n\n"
        "B. The tool SHALL do beta.\n\n"
        "*End* *Parent* | **Hash**: 00000000\n---\n"
    )


_DEV = (
    f"# {CHILD}: Child\n\n"
    f"**Level**: dev | **Status**: Active | **Implements**: {PARENT}-A\n\n"
    "## Assertions\n\n"
    "A. The tool SHALL do child.\n\n"
    "*End* *Child* | **Hash**: 00000000\n---\n"
)


def _write_project(tmp_path: Path, *, retired: list[str] | None, status: str = "Active") -> Path:
    """Write a repository whose REQ-p00001 is cited by a requirement and by code.

    ``retired=None`` leaves the status roles to the schema's defaults.
    """
    root = tmp_path / "repo"
    for directory in ("spec", "src"):
        (root / directory).mkdir(parents=True)
    config = _CONFIG + ("" if retired is None else _roles(retired))
    (root / ".elspais.toml").write_text(config, encoding="utf-8")
    (root / "spec" / "prd.md").write_text(_prd(status), encoding="utf-8")
    (root / "spec" / "dev.md").write_text(_DEV, encoding="utf-8")
    (root / "src" / "m.py").write_text(
        f"# Implements: {PARENT}-B\ndef f():\n    pass\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def _cited_labels(graph, citing_id: str) -> list[str]:
    """The labels of REQ-p00001 that *citing_id* cites."""
    citing = graph.find_by_id(citing_id)
    return sorted(
        label
        for edge in citing.iter_incoming_edges()
        if edge.source.id == PARENT
        for label in edge.assertion_targets
    )


def _code_cites(graph) -> list[str]:
    """The labels of REQ-p00001 the one code node cites."""
    (code,) = list(graph.iter_by_kind(NodeKind.CODE))
    return _cited_labels(graph, code.id)


def _snapshot(graph) -> tuple:
    """A witness that a refused deletion changed nothing."""
    parent = graph.find_by_id(PARENT)
    return (
        parent.get_field("status"),
        len(graph.mutation_log),
        sorted(node.id for node in graph.all_nodes()),
        _cited_labels(graph, CHILD),
    )


# ─────────────────────────────────────────────────────────────────────────────
# An active requirement is retired in place (REQ-p00017-D)
# ─────────────────────────────────────────────────────────────────────────────


class TestActiveRequirementIsRetiredInPlace:
    """Validates REQ-p00017-D."""

    # Verifies: REQ-p00017-D
    def test_REQ_p00017_D_node_identifier_assertions_and_citations_are_kept(self, tmp_path: Path):
        graph = build_graph(repo_root=_write_project(tmp_path, retired=ONE_RETIRED))
        assertions = sorted(
            child.id
            for child in graph.find_by_id(PARENT).iter_children()
            if child.kind == NodeKind.ASSERTION
        )
        assert assertions == [f"{PARENT}-A", f"{PARENT}-B"]

        entry = graph.delete_requirement(PARENT)

        parent = graph.find_by_id(PARENT)
        assert parent is not None
        assert parent.id == PARENT
        assert parent.get_field("status") == "Deprecated"
        for assertion_id in assertions:
            assert graph.find_by_id(assertion_id) is not None
        assert _cited_labels(graph, CHILD) == ["A"]
        assert _code_cites(graph) == ["B"]
        assert graph.repo_for(PARENT) is not None
        assert not graph.has_deletions()

        assert entry.operation == "delete_requirement"
        assert entry.target_id == PARENT
        assert entry.before_state == {
            "id": PARENT,
            "status": "Active",
            "disposition": "retired",
            "source_file_id": "file:REQ:spec/prd.md",
        }
        assert entry.after_state == {"status": "Deprecated"}

    # Verifies: REQ-p00017-D
    def test_REQ_p00017_D_saved_file_holds_the_retired_requirement(self, tmp_path: Path):
        root = _write_project(tmp_path, retired=ONE_RETIRED)
        graph = build_graph(repo_root=root)

        graph.delete_requirement(PARENT)
        result = render_save(graph, repo_root=root)

        assert result["success"] is True, result.get("errors")
        text = (root / "spec" / "prd.md").read_text(encoding="utf-8")
        assert f"# {PARENT}: Parent" in text
        assert "**Status**: Deprecated" in text
        assert "**Status**: Active" not in text
        assert "A. The tool SHALL do alpha." in text

        rebuilt = build_graph(repo_root=root)
        parent = rebuilt.find_by_id(PARENT)
        assert parent is not None
        assert parent.get_field("status") == "Deprecated"
        assert _cited_labels(rebuilt, CHILD) == ["A"]
        assert _code_cites(rebuilt) == ["B"]
        assert not any(f.target_id.startswith(PARENT) for f in rebuilt.unresolved_references())

    # Verifies: REQ-p00017-D
    def test_REQ_p00017_D_undo_restores_the_active_status(self, tmp_path: Path):
        graph = build_graph(repo_root=_write_project(tmp_path, retired=ONE_RETIRED))
        version_before = render.node_version(graph.find_by_id(PARENT))

        graph.delete_requirement(PARENT)
        graph.undo_last()

        parent = graph.find_by_id(PARENT)
        assert parent.get_field("status") == "Active"
        assert render.node_version(parent) == version_before
        assert _cited_labels(graph, CHILD) == ["A"]
        assert len(graph.mutation_log) == 0

    # Verifies: REQ-p00017-D, REQ-p00017-E
    def test_REQ_p00017_D_a_retired_requirement_is_not_deleted_again(self, tmp_path: Path):
        """Once retired, the requirement is in the retired role and is read-only."""
        graph = build_graph(repo_root=_write_project(tmp_path, retired=ONE_RETIRED))
        graph.delete_requirement(PARENT)

        with pytest.raises(RetiredRequirementError):
            graph.delete_requirement(PARENT)

        assert graph.find_by_id(PARENT).get_field("status") == "Deprecated"
        assert len(graph.mutation_log) == 1

    # Verifies: REQ-p00017-D
    def test_REQ_p00017_D_mcp_reports_the_retirement(self, tmp_path: Path):
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_requirement

        graph = build_graph(repo_root=_write_project(tmp_path, retired=ONE_RETIRED))

        result = _mutate_delete_requirement(graph, PARENT, confirm=True)

        assert result["success"] is True
        assert result["message"] == (
            f"Retired requirement {PARENT} in place with status 'Deprecated'; "
            "its identifier is kept"
        )
        assert result["mutation"]["before_state"]["disposition"] == "retired"
        assert graph.find_by_id(PARENT).get_field("status") == "Deprecated"


# ─────────────────────────────────────────────────────────────────────────────
# No single retired status, so the deletion is refused (REQ-p00017-N)
# ─────────────────────────────────────────────────────────────────────────────


REFUSED_ROLES = [
    pytest.param(SEVERAL_RETIRED, "Deprecated, Superseded, Rejected", id="several"),
    pytest.param(NONE_RETIRED, "none", id="none"),
    pytest.param(None, "Deprecated, Superseded, Rejected", id="schema-defaults"),
]


def _assert_refusal_message(message: str, declared: str) -> None:
    assert message.startswith(f"Cannot delete {PARENT}: its status 'Active' "), message
    assert "is in the active role" in message
    assert f"({declared})" in message
    assert "Nothing was changed." in message
    assert "Change its status to the retired status you mean" in message
    if declared == "none":
        assert "[rules.format.status_roles] retired" in message
    else:
        assert "[rules.format.status_roles]" not in message


class TestDeletionWithoutOneRetiredStatusIsRefused:
    """Validates REQ-p00017-N."""

    @pytest.mark.parametrize("retired,declared", REFUSED_ROLES)
    # Verifies: REQ-p00017-N
    def test_REQ_p00017_N_refusal_reports_the_declared_retired_statuses(
        self, tmp_path: Path, retired: list[str] | None, declared: str
    ):
        graph = build_graph(repo_root=_write_project(tmp_path, retired=retired))
        before = _snapshot(graph)

        with pytest.raises(ValueError) as refused:
            graph.delete_requirement(PARENT)

        _assert_refusal_message(str(refused.value), declared)
        assert _snapshot(graph) == before
        assert not graph.has_deletions()

    # Verifies: REQ-p00017-N
    def test_REQ_p00017_N_a_graph_holding_no_configuration_reads_the_default_roles(self):
        """No configuration document: the schema's default roles declare three
        retired statuses, so the deletion is refused."""
        graph = build_bare_graph(make_requirement(PARENT, title="Parent", level="PRD"))
        logged = len(graph.mutation_log)

        with pytest.raises(ValueError) as refused:
            graph.delete_requirement(PARENT)

        _assert_refusal_message(str(refused.value), "Deprecated, Superseded, Rejected")
        assert graph.find_by_id(PARENT).get_field("status") == "Active"
        assert len(graph.mutation_log) == logged
        assert not graph.has_deletions()

    @pytest.mark.parametrize("retired,declared", REFUSED_ROLES)
    # Verifies: REQ-p00017-N
    def test_REQ_p00017_N_mcp_reports_the_refusal(
        self, tmp_path: Path, retired: list[str] | None, declared: str
    ):
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_requirement

        graph = build_graph(repo_root=_write_project(tmp_path, retired=retired))
        before = _snapshot(graph)

        result = _mutate_delete_requirement(graph, PARENT, confirm=True)

        assert result["success"] is False
        _assert_refusal_message(result["error"], declared)
        assert _snapshot(graph) == before


# ─────────────────────────────────────────────────────────────────────────────
# Control: a provisional requirement is removed
# ─────────────────────────────────────────────────────────────────────────────


class TestProvisionalRequirementIsRemoved:
    """Control for REQ-p00017-D: retirement in place applies to the active role."""

    @pytest.mark.parametrize(
        "retired",
        [
            pytest.param(ONE_RETIRED, id="one-retired"),
            pytest.param(SEVERAL_RETIRED, id="several-retired"),
        ],
    )
    # Verifies: REQ-p00017-D, REQ-o00062-A
    def test_REQ_p00017_D_draft_requirement_is_removed(self, tmp_path: Path, retired: list[str]):
        """The number of retired statuses does not matter to a removal."""
        graph = build_graph(repo_root=_write_project(tmp_path, retired=retired, status="Draft"))

        entry = graph.delete_requirement(PARENT)

        assert graph.find_by_id(PARENT) is None
        assert graph.find_by_id(f"{PARENT}-A") is None
        assert entry.before_state.get("disposition") != "retired"
        assert PARENT in {node.id for node in graph.deleted_nodes()}


# ─────────────────────────────────────────────────────────────────────────────
# The viewer route and the MCP tool answer alike (REQ-o00062-O)
# ─────────────────────────────────────────────────────────────────────────────


def _surfaces(root: Path):
    """One served graph, reached over HTTP and through the MCP tool."""
    pytest.importorskip("mcp")
    from starlette.testclient import TestClient

    from elspais.mcp.server import create_server
    from elspais.server.app import create_app
    from elspais.server.state import AppState

    state = AppState.from_config(repo_root=root)
    client = TestClient(create_app(state=state, mount_mcp=False))
    server = create_server(state.graph, working_dir=root)
    tool = server._tool_manager._tools["mutate_delete_requirement"].fn
    return state, client, tool


class TestDeletionParity:
    """Validates REQ-o00062-O for a requirement deletion."""

    # Verifies: REQ-o00062-O, REQ-p00017-D
    def test_REQ_o00062_O_retirement_answers_alike(self, tmp_path: Path):
        state, client, tool = _surfaces(_write_project(tmp_path, retired=ONE_RETIRED))
        version = render.node_version(state.graph.find_by_id(PARENT))

        response = client.post(
            "/api/mutate/requirement/delete",
            json={"node_id": PARENT, "confirm": True, "if_version": version},
        )
        assert response.status_code == 200, response.text
        http_body = response.json()
        state.graph.undo_last()
        assert render.node_version(state.graph.find_by_id(PARENT)) == version

        mcp_body = tool(node_id=PARENT, if_version=version, confirm=True)

        assert http_body["success"] is True
        assert http_body["message"].startswith(f"Retired requirement {PARENT} in place")
        # Both surfaces report the retired requirement's resulting version.
        assert http_body["version"] == render.node_version(state.graph.find_by_id(PARENT))
        assert comparable_mutation_result(mcp_body) == comparable_mutation_result(http_body)
        assert state.graph.find_by_id(PARENT).get_field("status") == "Deprecated"

    # Verifies: REQ-o00062-K, REQ-o00062-O
    def test_REQ_o00062_O_removal_answers_alike(self, tmp_path: Path):
        """A removal through the route reports the containing file's version."""
        state, client, tool = _surfaces(
            _write_project(tmp_path, retired=ONE_RETIRED, status="Draft")
        )
        version = render.node_version(state.graph.find_by_id(PARENT))
        file_node = state.graph.find_by_id(PARENT).file_node()
        file_version_before = render.node_version(file_node)

        response = client.post(
            "/api/mutate/requirement/delete",
            json={"node_id": PARENT, "confirm": True, "if_version": version},
        )
        assert response.status_code == 200, response.text
        http_body = response.json()
        assert state.graph.find_by_id(PARENT) is None
        assert http_body["version"] == render.node_version(file_node)
        assert http_body["version"] != file_version_before
        state.graph.undo_last()
        assert render.node_version(state.graph.find_by_id(PARENT)) == version

        mcp_body = tool(node_id=PARENT, if_version=version, confirm=True)

        assert http_body["success"] is True
        assert http_body["message"] == f"Deleted requirement {PARENT}"
        assert comparable_mutation_result(mcp_body) == comparable_mutation_result(http_body)

    @pytest.mark.parametrize(
        "retired",
        [
            pytest.param(SEVERAL_RETIRED, id="several"),
            pytest.param(NONE_RETIRED, id="none"),
        ],
    )
    # Verifies: REQ-o00062-O, REQ-p00017-N
    def test_REQ_o00062_O_refusal_answers_alike(self, tmp_path: Path, retired: list[str]):
        state, client, tool = _surfaces(_write_project(tmp_path, retired=retired))
        version = render.node_version(state.graph.find_by_id(PARENT))
        before = _snapshot(state.graph)

        response = client.post(
            "/api/mutate/requirement/delete",
            json={"node_id": PARENT, "confirm": True, "if_version": version},
        )
        mcp_body = tool(node_id=PARENT, if_version=version, confirm=True)

        assert response.status_code == 400
        assert response.json() == mcp_body
        assert mcp_body["success"] is False
        assert "Nothing was changed." in mcp_body["error"]
        assert _snapshot(state.graph) == before


# ─────────────────────────────────────────────────────────────────────────────
# The version a deletion reports (REQ-o00062-K)
# ─────────────────────────────────────────────────────────────────────────────


class TestDeletionReportsTheSurvivingVersion:
    """Validates REQ-o00062-K for a requirement deletion.

    A retirement modifies the requirement, which survives, so the tool reports
    the requirement's own resulting version. A removal leaves no requirement,
    so it reports the version of the file that absorbed the change.
    """

    # Verifies: REQ-o00062-K, REQ-p00017-D
    def test_REQ_o00062_K_retirement_reports_the_requirements_version(self, tmp_path: Path):
        state, _client, tool = _surfaces(_write_project(tmp_path, retired=ONE_RETIRED))
        version = render.node_version(state.graph.find_by_id(PARENT))
        file_node = state.graph.find_by_id(PARENT).file_node()

        result = tool(node_id=PARENT, if_version=version, confirm=True)

        assert result["success"] is True, result
        retired = state.graph.find_by_id(PARENT)
        assert result["version"] == render.node_version(retired)
        assert result["version"] != version
        assert result["version"] != render.node_version(file_node)

    # Verifies: REQ-o00062-K
    def test_REQ_o00062_K_removal_reports_the_containing_files_version(self, tmp_path: Path):
        state, _client, tool = _surfaces(
            _write_project(tmp_path, retired=ONE_RETIRED, status="Draft")
        )
        version = render.node_version(state.graph.find_by_id(PARENT))
        file_node = state.graph.find_by_id(PARENT).file_node()
        file_version_before = render.node_version(file_node)

        result = tool(node_id=PARENT, if_version=version, confirm=True)

        assert result["success"] is True, result
        assert state.graph.find_by_id(PARENT) is None
        assert result["version"] == render.node_version(file_node)
        assert result["version"] != file_version_before
