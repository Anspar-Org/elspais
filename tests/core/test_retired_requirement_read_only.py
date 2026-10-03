"""A requirement whose status is in the retired role is read-only.

REQ-p00017-E: a retired requirement is a historical record, so no mutation
may change its content or identifier. Changing its status is how it is
reopened, so that change and the changelog that records it stay allowed.
REQ-o00062-O: the MCP tools and the viewer's HTTP routes refuse alike.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from elspais.graph.builder import RetiredRequirementError
from elspais.graph.factory import build_graph
from elspais.graph.relations import EdgeKind
from elspais.graph.render import node_version

_CONFIG = """version = 5

[project]
name = "retired"
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
"""

_PRD = """# REQ-p00001: Parent

**Level**: prd | **Status**: Active | **Implements**: -

## Assertions

A. The tool SHALL do alpha.

B. The tool SHALL do beta.

*End* *Parent* | **Hash**: 00000000
---
"""

_DEV = """# REQ-d00001: Withdrawn child

**Level**: dev | **Status**: {status} | **Implements**: REQ-p00001-A, REQ-p00001-Z

## Assertions

A. The tool SHALL do delta.

B. The tool SHALL do epsilon.

## Rationale

Kept for the record.

*End* *Withdrawn child* | **Hash**: 00000000
---
"""

RETIRED = "REQ-d00001"
SECTION = f"{RETIRED}:section:0"

# The schema's default roles place each of these in the retired role.
RETIRED_STATUSES = ["Deprecated", "Superseded", "Rejected"]


def _write_project(tmp_path: Path, status: str = "Deprecated") -> Path:
    root = tmp_path / "repo"
    (root / "spec").mkdir(parents=True)
    (root / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    (root / "spec" / "prd.md").write_text(_PRD, encoding="utf-8")
    (root / "spec" / "dev.md").write_text(_DEV.format(status=status), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


# Every mutation of the retired requirement's content or identifier, and of
# the references it holds (an edge whose citing node is the requirement).
REFUSED_MUTATIONS = [
    pytest.param(lambda g: g.rename_node(RETIRED, "REQ-d00009"), id="rename_node"),
    pytest.param(lambda g: g.update_title(RETIRED, "Another title"), id="update_title"),
    pytest.param(lambda g: g.set_stereotype(RETIRED, True), id="set_stereotype"),
    pytest.param(lambda g: g.delete_requirement(RETIRED), id="delete_requirement"),
    pytest.param(lambda g: g.rename_assertion(f"{RETIRED}-A", "C"), id="rename_assertion"),
    pytest.param(
        lambda g: g.update_assertion(f"{RETIRED}-A", "The tool SHALL do zeta."),
        id="update_assertion",
    ),
    pytest.param(lambda g: g.add_assertion(RETIRED, "The tool SHALL do eta."), id="add_assertion"),
    pytest.param(lambda g: g.delete_assertion(f"{RETIRED}-B"), id="delete_assertion"),
    pytest.param(lambda g: g.add_remainder(RETIRED, "Notes", "More."), id="add_remainder"),
    pytest.param(lambda g: g.update_remainder(SECTION, text="Rewritten."), id="update_remainder"),
    pytest.param(lambda g: g.delete_remainder(SECTION), id="delete_remainder"),
    pytest.param(
        lambda g: g.add_edge(RETIRED, "REQ-p00001", EdgeKind.IMPLEMENTS, ["B"]),
        id="add_edge",
    ),
    pytest.param(
        lambda g: g.change_edge_kind(RETIRED, "REQ-p00001", EdgeKind.REFINES),
        id="change_edge_kind",
    ),
    pytest.param(
        lambda g: g.change_edge_targets(RETIRED, "REQ-p00001", ["B"]),
        id="change_edge_targets",
    ),
    pytest.param(lambda g: g.delete_edge(RETIRED, "REQ-p00001"), id="delete_edge"),
    pytest.param(
        lambda g: g.fix_broken_reference(RETIRED, "REQ-p00001-Z", "REQ-p00001-B"),
        id="fix_broken_reference",
    ),
]


def _snapshot(graph) -> tuple:
    node = graph.find_by_id(RETIRED)
    return (node_version(node), node.get_field("hash"), len(graph.mutation_log))


class TestRetiredRequirementIsReadOnly:
    """Validates REQ-p00017-E."""

    @pytest.mark.parametrize("mutate", REFUSED_MUTATIONS)
    # Verifies: REQ-p00017-E
    def test_REQ_p00017_E_mutation_of_a_retired_requirement_is_refused(
        self, tmp_path: Path, mutate
    ):
        graph = build_graph(repo_root=_write_project(tmp_path))
        before = _snapshot(graph)

        with pytest.raises(RetiredRequirementError) as refused:
            mutate(graph)

        message = str(refused.value)
        assert message.startswith(f"{RETIRED} has status 'Deprecated'")
        assert "retired role" in message
        assert "first change its status" in message
        assert _snapshot(graph) == before

    @pytest.mark.parametrize("status", RETIRED_STATUSES)
    # Verifies: REQ-p00017-E
    def test_REQ_p00017_E_every_retired_status_is_read_only(self, tmp_path: Path, status: str):
        graph = build_graph(repo_root=_write_project(tmp_path, status=status))

        with pytest.raises(RetiredRequirementError, match=f"status '{status}'"):
            graph.update_title(RETIRED, "Another title")

    @pytest.mark.parametrize("mutate", REFUSED_MUTATIONS)
    # Verifies: REQ-p00017-E
    def test_REQ_p00017_E_changing_the_status_reopens_the_requirement(self, tmp_path: Path, mutate):
        """The status change itself is accepted, and afterwards the mutation
        that was refused applies."""
        graph = build_graph(repo_root=_write_project(tmp_path))

        graph.change_status(RETIRED, "Draft")
        mutate(graph)

        assert len(graph.mutation_log) == 2

    # Verifies: REQ-p00017-E
    def test_REQ_p00017_E_changelog_entry_is_accepted_while_retired(self, tmp_path: Path):
        graph = build_graph(repo_root=_write_project(tmp_path))
        entry = {
            "date": "2026-10-02",
            "hash": "00000000",
            "change_order": "-",
            "author_name": "Reviewer",
            "author_id": "reviewer@example.com",
            "reason": "Withdrawn",
        }

        graph.add_changelog_entry(RETIRED, entry)

        assert graph.find_by_id(RETIRED).get_field("changelog")[0] == entry

    # Verifies: REQ-p00017-E
    def test_REQ_p00017_E_a_requirement_outside_the_retired_role_is_not_refused(
        self, tmp_path: Path
    ):
        """Control: the same mutation of an active requirement applies."""
        graph = build_graph(repo_root=_write_project(tmp_path, status="Active"))

        graph.update_title(RETIRED, "Another title")

        assert graph.find_by_id(RETIRED).get_label() == "Another title"


# Each case: the HTTP route, the MCP tool, the node whose version guards it,
# and the arguments both surfaces take.
SURFACE_CASES = [
    pytest.param(
        "/api/mutate/title",
        "mutate_update_title",
        RETIRED,
        {"node_id": RETIRED, "new_title": "Another title"},
        id="title",
    ),
    pytest.param(
        "/api/mutate/assertion/add",
        "mutate_add_assertion",
        RETIRED,
        {"req_id": RETIRED, "text": "The tool SHALL do eta."},
        id="assertion-add",
    ),
    pytest.param(
        "/api/mutate/assertion/delete",
        "mutate_delete_assertion",
        f"{RETIRED}-B",
        {"assertion_id": f"{RETIRED}-B", "confirm": True},
        id="assertion-delete",
    ),
]


class TestBothSurfacesRefuseAlike:
    """Validates REQ-o00062-O for the retired-role refusal."""

    @pytest.mark.parametrize("route,tool,guarded,arguments", SURFACE_CASES)
    # Verifies: REQ-o00062-O, REQ-p00017-E
    def test_REQ_o00062_O_mcp_and_http_return_the_same_refusal(
        self, tmp_path: Path, route: str, tool: str, guarded: str, arguments: dict
    ):
        pytest.importorskip("mcp")
        from starlette.testclient import TestClient

        from elspais.mcp.server import create_server
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        root = _write_project(tmp_path)
        state = AppState.from_config(repo_root=root)
        graph = state.graph
        version = node_version(graph.find_by_id(guarded))
        client = TestClient(create_app(state=state, mount_mcp=False))
        server = create_server(graph, working_dir=root)
        tools = {name: t.fn for name, t in server._tool_manager._tools.items()}

        http = client.post(route, json={**arguments, "if_version": version})
        mcp = tools[tool](**arguments, if_version=version)

        assert http.status_code == 400, http.text
        assert mcp["success"] is False
        assert f"{RETIRED} has status 'Deprecated'" in mcp["error"]
        assert http.json() == mcp
        assert len(graph.mutation_log) == 0
