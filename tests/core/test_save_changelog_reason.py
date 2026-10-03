"""The reason a save records in the changelog of each Active requirement it changes.

A save of pending changes is the one moment a requirement's text moves on disk,
so it is where the changelog of an Active requirement gains the row saying why.
These tests drive the viewer's ``/api/save`` route and the agent interface's
``save_mutations`` tool against a throwaway copy of the ``hht-like`` fixture,
one pending change at a time, across every kind of change that reaches an
Active requirement -- including the ones that move it off Active (a status
change, a retirement) and the one that changes its identifier (a rename).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from elspais.graph import render
from tests.core.test_server_version_guard import (
    _DRAFT_REQ_METADATA,
    ASSERTION,
    DRAFT_REQ,
    HHT_LIKE,
    HISTORY_TIP_FIELD,
    JOURNEY,
    REQ,
    ROUTE_CASES,
    SECTION,
    VERSION_FIELD,
    RouteCase,
    _log_tip,
    _spec_snapshot,
)

REASON = "the auditors asked for it"
RENAMED = "REQ-d00030"
REFUSAL_CODE = "changelog_message_required"

# Every role written out: the table replaces the default whole, and the default
# declares three retired statuses, which leaves the retirement of an Active
# requirement with no status to take.
_ONE_RETIRED_STATUS = """
[rules.format.status_roles]
active = ["Active"]
provisional = ["Draft", "Proposed"]
aspirational = ["Roadmap", "Future", "Idea"]
retired = ["Deprecated"]
"""

_CHANGELOG_OFF = """
[changelog]
hash_current = false
"""

# The mutation routes whose change reaches the Active requirement REQ.
_ACTIVE_PATHS = {
    "/api/mutate/status",
    "/api/mutate/template",
    "/api/mutate/title",
    "/api/mutate/assertion",
    "/api/mutate/assertion/add",
    "/api/mutate/assertion/delete",
    "/api/mutate/remainder",
    "/api/mutate/remainder/add",
    "/api/mutate/remainder/delete",
    "/api/mutate/edge",
    "/api/mutate/move-to-file",
}
_ACTIVE_CASES = [case for case in ROUTE_CASES if case.path in _ACTIVE_PATHS]
assert {case.path for case in _ACTIVE_CASES} == _ACTIVE_PATHS, "route table moved"
for _case in _ACTIVE_CASES:
    assert _case.guarded_id in (REQ, ASSERTION, SECTION), _case

# Deleting an Active requirement retires it in place under its identifier.
_RETIRE = RouteCase("/api/mutate/requirement/delete", REQ, {"node_id": REQ, "confirm": True})

# Each entry: a name, and either a route case or the rename (made through the
# agent interface, which is the only surface that renames a requirement).
CHANGES = [(case.path, case) for case in _ACTIVE_CASES] + [
    ("retire-in-place", _RETIRE),
    ("mcp:mutate_rename_node", "rename"),
]
CHANGE_IDS = [name for name, _ in CHANGES]


def _id_after(change) -> str:
    return RENAMED if change == "rename" else REQ


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _copy_project(tmp_path: Path, extra_config: str = "") -> Path:
    """The hht-like fixture with REQ-d00002 Draft and one retired status."""
    project = tmp_path / "project"
    shutil.copytree(HHT_LIKE, project)
    spec = project / "spec" / "dev-impl.md"
    text = spec.read_text(encoding="utf-8")
    active = _DRAFT_REQ_METADATA.format(status="Active")
    assert text.count(active) == 1, f"fixture premise: {DRAFT_REQ} metadata line moved"
    spec.write_text(text.replace(active, _DRAFT_REQ_METADATA.format(status="Draft")), "utf-8")
    config = project / ".elspais.toml"
    config.write_text(
        config.read_text(encoding="utf-8") + _ONE_RETIRED_STATUS + extra_config, "utf-8"
    )
    return project


@pytest.fixture(autouse=True)
def _author(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Reason Tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "reason@test.org")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return _copy_project(tmp_path)


@pytest.fixture
def app_state(project: Path):
    from elspais.server.state import AppState

    return AppState.from_config(repo_root=project)


@pytest.fixture
def client(app_state) -> TestClient:
    from elspais.server.app import create_app

    return TestClient(create_app(state=app_state, mount_mcp=False))


@pytest.fixture
def mcp_tools(app_state, project: Path):
    """MCP tool closures over the same graph the HTTP app serves."""
    pytest.importorskip("mcp")
    from elspais.mcp.server import create_server

    server = create_server(app_state.graph, working_dir=project)
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}


def _version(app_state, node_id: str) -> str:
    node = app_state.graph.find_by_id(node_id)
    assert node is not None, f"fixture node {node_id!r} missing"
    return render.node_version(node)


def _apply(client, app_state, mcp_tools, change) -> None:
    """Leave one pending change in the served graph."""
    if change == "rename":
        result = mcp_tools["mutate_rename_node"](REQ, RENAMED, _version(app_state, REQ))
        assert result.get("success"), result
        return
    body = change.with_tokens(lambda node_id: _version(app_state, node_id))
    resp = client.post(change.path, json=body)
    assert resp.status_code == 200, f"{change.path} -> {resp.status_code}: {resp.text}"


def _changelog(app_state, req_id: str) -> list[dict]:
    node = app_state.graph.find_by_id(req_id)
    assert node is not None, f"{req_id} missing from the graph"
    return list(node.get_field("changelog") or [])


def _save(client, app_state, message=None):
    body = {HISTORY_TIP_FIELD: _log_tip(app_state)}
    if message is not None:
        body["message"] = message
    return client.post("/api/save", json=body)


# ─────────────────────────────────────────────────────────────────────────────
# B, C, F: a save with no reason is refused, writes nothing, keeps everything
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("message", [None, "", "   "], ids=["absent", "empty", "blank"])
@pytest.mark.parametrize("change", [c for _, c in CHANGES], ids=CHANGE_IDS)
class TestSaveWithoutAReasonIsRefused:
    """Validates REQ-d00325-B, REQ-d00325-C:

    Every kind of change that reaches an Active requirement, including those
    that leave it no longer Active, needs the reason before anything is written.
    """

    # Verifies: REQ-d00325-B
    def test_REQ_d00325_B_refused_save_writes_nothing_and_keeps_the_change(
        self, client, app_state, mcp_tools, project, change, message
    ):
        _apply(client, app_state, mcp_tools, change)
        before_disk = _spec_snapshot(project)
        pending = len(app_state.graph.mutation_log)

        resp = _save(client, app_state, message)

        assert resp.status_code == 400, resp.text
        payload = resp.json()
        assert payload["success"] is False
        assert payload["code"] == REFUSAL_CODE
        assert _id_after(change) in payload["requirement_ids"]
        assert _spec_snapshot(project) == before_disk
        assert len(app_state.graph.mutation_log) == pending

    # Verifies: REQ-d00325-C
    def test_REQ_d00325_C_refusal_names_each_requirement_and_how_to_answer(
        self, client, app_state, mcp_tools, change, message
    ):
        _apply(client, app_state, mcp_tools, change)

        payload = _save(client, app_state, message).json()

        assert payload["requirement_ids"] == sorted(payload["requirement_ids"])
        for req_id in payload["requirement_ids"]:
            assert req_id in payload["error"], payload
        assert "message" in payload["error"], payload


class TestRefusalNamesEveryRequirement:
    """Validates REQ-d00325-C: with two Active requirements changed, both are named."""

    # Verifies: REQ-d00325-C
    def test_REQ_d00325_C_two_changed_requirements_are_both_named(self, client, app_state):
        for req_id in (REQ, "REQ-d00001"):
            resp = client.post(
                "/api/mutate/title",
                json={
                    "node_id": req_id,
                    "new_title": f"Retitled {req_id}",
                    VERSION_FIELD: _version(app_state, req_id),
                },
            )
            assert resp.status_code == 200, resp.text

        payload = _save(client, app_state).json()

        assert payload["requirement_ids"] == ["REQ-d00001", REQ]
        assert "REQ-d00001" in payload["error"] and REQ in payload["error"]


@pytest.mark.parametrize("message", [None, "   "], ids=["absent", "blank"])
@pytest.mark.parametrize("change", [c for _, c in CHANGES], ids=CHANGE_IDS)
class TestBothSurfacesRefuseAlike:
    """Validates REQ-d00325-F: the viewer's save and the agent's save need a
    reason under the same conditions and report the same refusal."""

    # Verifies: REQ-d00325-B+F
    def test_REQ_d00325_F_http_and_mcp_refusals_are_identical(
        self, client, app_state, mcp_tools, project, change, message
    ):
        _apply(client, app_state, mcp_tools, change)
        before_disk = _spec_snapshot(project)
        pending = len(app_state.graph.mutation_log)

        http_body = _save(client, app_state, message).json()
        mcp_body = mcp_tools["save_mutations"](_log_tip(app_state), message=message)

        assert http_body["code"] == REFUSAL_CODE
        assert mcp_body == http_body
        assert _spec_snapshot(project) == before_disk
        assert len(app_state.graph.mutation_log) == pending


# ─────────────────────────────────────────────────────────────────────────────
# A: a save with the reason writes one row carrying it and the new hash
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("change", [c for _, c in CHANGES], ids=CHANGE_IDS)
class TestSaveWithAReasonWritesOneRow:
    """Validates REQ-d00325-A:

    The row lands on the requirement as it is after the save -- under its new
    identifier after a rename, and on it although it is no longer Active after
    a status change or a retirement -- and records the hash it has then.
    """

    # Verifies: REQ-d00325-A
    def test_REQ_d00325_A_one_row_with_the_reason_and_the_hash_after_the_save(
        self, client, app_state, mcp_tools, project, change
    ):
        before_rows = _changelog(app_state, REQ)
        _apply(client, app_state, mcp_tools, change)
        req_id = _id_after(change)

        resp = _save(client, app_state, REASON)

        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True
        rows = _changelog(app_state, req_id)
        assert len(rows) == len(before_rows) + 1, rows
        added = [row for row in rows if row not in before_rows]
        assert len(added) == 1, rows
        assert added[0]["reason"] == REASON
        node = app_state.graph.find_by_id(req_id)
        rel = node.file_node().get_field("relative_path")
        text = (project / rel).read_text(encoding="utf-8")
        assert f"| {REASON}" in text
        # The hash written on the requirement's End marker after the save.
        assert node.hash, f"{req_id} has no stored hash"
        assert added[0]["hash"] == node.hash
        assert added[0]["hash"] == render.compute_hash_for_node(node, app_state.graph.hash_mode)

    # Verifies: REQ-d00325-A+F
    def test_REQ_d00325_A_the_agent_save_writes_the_same_row(
        self, client, app_state, mcp_tools, project, change
    ):
        before_rows = _changelog(app_state, REQ)
        _apply(client, app_state, mcp_tools, change)
        req_id = _id_after(change)

        result = mcp_tools["save_mutations"](_log_tip(app_state), message=REASON)

        assert result.get("success") is True, result
        from elspais.server.state import AppState

        rebuilt = AppState.from_config(repo_root=project)
        rows = _changelog(rebuilt, req_id)
        assert len(rows) == len(before_rows) + 1, rows
        added = [row for row in rows if row not in before_rows]
        assert [row["reason"] for row in added] == [REASON]
        assert added[0]["hash"] == rebuilt.graph.find_by_id(req_id).hash


class TestNoRowWhereNoActiveRequirementChanged:
    """Validates REQ-d00325-A, REQ-d00325-B: the rule reaches Active requirements
    only, so other changes save without a reason and gain no row."""

    @pytest.mark.parametrize(
        "path, payload",
        [
            (
                "/api/mutate/title",
                {"node_id": DRAFT_REQ, "new_title": "Retitled Draft"},
            ),
            (
                "/api/mutate/journey/field",
                {"node_id": JOURNEY, "field": "goal", "value": "A changed goal"},
            ),
        ],
        ids=["draft-requirement", "journey"],
    )
    # Verifies: REQ-d00325-A+B
    def test_REQ_d00325_A_no_reason_needed_and_no_row_written(
        self, client, app_state, project, path, payload
    ):
        guarded = payload["node_id"]
        before = {
            req_id: _changelog(app_state, req_id) for req_id in (REQ, DRAFT_REQ, "REQ-d00001")
        }
        resp = client.post(path, json={**payload, VERSION_FIELD: _version(app_state, guarded)})
        assert resp.status_code == 200, resp.text

        saved = _save(client, app_state)

        assert saved.status_code == 200, saved.text
        assert saved.json()["success"] is True
        assert len(app_state.graph.mutation_log) == 0
        for req_id, rows in before.items():
            assert _changelog(app_state, req_id) == rows, req_id


class TestChangelogTrackingDisabled:
    """Validates REQ-d00325-A, REQ-d00325-B: without changelog tracking a save
    needs no reason and writes no row."""

    # Verifies: REQ-d00325-A+B
    def test_REQ_d00325_B_no_reason_needed_and_no_row_written(self, tmp_path: Path):
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        project = _copy_project(tmp_path, extra_config=_CHANGELOG_OFF)
        state = AppState.from_config(repo_root=project)
        client = TestClient(create_app(state=state, mount_mcp=False))
        before = _changelog(state, REQ)
        resp = client.post(
            "/api/mutate/title",
            json={"node_id": REQ, "new_title": "Untracked", VERSION_FIELD: _version(state, REQ)},
        )
        assert resp.status_code == 200, resp.text

        saved = _save(client, state)

        assert saved.status_code == 200, saved.text
        assert saved.json()["success"] is True
        assert "Untracked" in (project / "spec" / "dev-impl.md").read_text(encoding="utf-8")
        assert _changelog(state, REQ) == before


# ─────────────────────────────────────────────────────────────────────────────
# E: a save no client requested records that, and why it happened
# ─────────────────────────────────────────────────────────────────────────────


class TestAutomaticSaveRecordsItsCause:
    """Validates REQ-d00325-E."""

    # Verifies: REQ-d00325-E
    def test_REQ_d00325_E_row_says_no_client_requested_it_and_names_the_trigger(
        self, client, app_state, project
    ):
        from elspais.mcp.shared_state import persist_pending, rebuild_shared_graph

        trigger = "every client was gone past the grace period"
        before = _changelog(app_state, REQ)
        resp = client.post(
            "/api/mutate/title",
            json={
                "node_id": REQ,
                "new_title": "Saved Alone",
                VERSION_FIELD: _version(app_state, REQ),
            },
        )
        assert resp.status_code == 200, resp.text

        result = persist_pending(app_state.shared, automatic=True, trigger=trigger)

        assert result.get("success") is True, result
        assert rebuild_shared_graph(app_state.shared).get("success")
        added = [row for row in _changelog(app_state, REQ) if row not in before]
        assert len(added) == 1, added
        reason = added[0]["reason"]
        assert "no client requested" in reason.lower(), reason
        assert trigger in reason, reason
