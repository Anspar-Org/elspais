# Verifies: REQ-o00074-L, REQ-p00083-E+F
"""The record, outside a server's memory, that it is holding unwritten changes.

Unsaved in-memory mutations exist in no file. A process killed outright
describes nothing on its way out, so the only account of the loss that can
survive is one written *before* the change it records is acknowledged. That is
what ``.elspais/unsaved-changes`` is: a presence-only sentinel, written on the
clean->dirty transition and removed on dirty->clean, carrying no count and no
detail because nothing it could say would still be true by the time anyone read
it.

Presence has to mean one thing. A sentinel a server finds standing as it starts
was left by a process that is gone, and reading it as a statement about the
starting process would be false -- so it is converted, once, into
``.elspais/lost-changes``, which says what is actually known: an earlier process
ended holding changes it never wrote. The finding is disclosed to clients and
retired only by a save a client asked for.

Unit-level: the transition contract is exercised on the logs directly with a
counting observer, and the file-level behaviour through a real ``AppState`` over
a throwaway project copy. The one ending this cannot reach -- a process killed
outright, and the next server start finding what it left -- is covered by the
subprocess companion in tests/e2e/test_e2e_special.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
HHT_LIKE = FIXTURES_DIR / "hht-like"

REQ = "REQ-p00001"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A throwaway copy of the hht-like fixture the save paths may write to."""
    dest = tmp_path / "project"
    shutil.copytree(HHT_LIKE, dest)
    return dest


def _sentinel(project: Path) -> Path:
    return project / ".elspais" / "unsaved-changes"


def _finding(project: Path) -> Path:
    return project / ".elspais" / "lost-changes"


class _Observer:
    """Records every announcement the log makes, in order."""

    def __init__(self) -> None:
        self.calls: list[bool] = []

    def __call__(self, holding: bool) -> None:
        self.calls.append(holding)


def _entry(n: int):
    from elspais.graph.mutations import MutationEntry

    return MutationEntry(
        operation="update_title",
        target_id=f"REQ-p0000{n}",
        before_state={},
        after_state={},
    )


class _PlainLog:
    """Drives a single-repo ``MutationLog`` through the shared vocabulary."""

    def __init__(self) -> None:
        from elspais.graph.mutations import MutationLog

        self.log = MutationLog()

    def add(self, n: int) -> None:
        self.log.append(_entry(n))

    def remove_one(self) -> None:
        self.log.pop()

    def remove_all(self) -> None:
        self.log.clear()


class _FederatedLog:
    """Drives a ``FederatedMutationLog``, which is the log a server holds."""

    def __init__(self) -> None:
        from elspais.graph.federated import FederatedMutationLog

        self.log = FederatedMutationLog()

    def add(self, n: int) -> None:
        self.log.record("primary", f"mutation-{n}")

    def remove_one(self) -> None:
        self.log.pop()

    def remove_all(self) -> None:
        self.log.clear()


@pytest.fixture(params=[_PlainLog, _FederatedLog], ids=["single-repo", "federated"])
def driver(request):
    """One log, plus the operations that make it hold work and let it go.

    Both kinds are covered because a server holds the federated one and a
    single-repo graph holds the plain one, and a transition that fired on only
    one of them would leave whole deployments silent.
    """
    return request.param()


class TestTheLogAnnouncesOnlyTheTransitions:
    """Validates REQ-p00083-E: what is recorded outside the process is the
    *fact* of holding unwritten work, which starts once and ends once. The log
    therefore announces the clean->dirty and dirty->clean crossings and nothing
    in between -- a per-mutation announcement would rewrite the record on every
    keystroke to say what it already said.
    """

    def test_REQ_o00074_L_first_entry_announces_that_work_is_held(self, driver):
        observer = _Observer()
        driver.log.set_dirty_observer(observer)

        driver.add(1)

        assert observer.calls == [True]

    def test_REQ_o00074_L_further_entries_announce_nothing_new(self, driver):
        observer = _Observer()
        driver.log.set_dirty_observer(observer)

        driver.add(1)
        driver.add(2)
        driver.add(3)

        assert observer.calls == [True], (
            "the log announced work being held once per mutation rather than once "
            f"per crossing: {observer.calls}"
        )

    def test_REQ_o00074_L_removing_the_last_entry_announces_the_release(self, driver):
        observer = _Observer()
        driver.log.set_dirty_observer(observer)
        driver.add(1)
        driver.add(2)

        driver.remove_one()
        assert observer.calls == [True], "released while work was still held"

        driver.remove_one()
        assert observer.calls == [True, False]

    def test_REQ_o00074_L_clearing_a_holding_log_announces_the_release_once(self, driver):
        observer = _Observer()
        driver.log.set_dirty_observer(observer)
        driver.add(1)
        driver.add(2)

        driver.remove_all()

        assert observer.calls == [True, False]

    def test_REQ_o00074_L_clearing_an_empty_log_announces_nothing(self, driver):
        observer = _Observer()
        driver.log.set_dirty_observer(observer)

        driver.remove_all()
        driver.remove_one()

        assert (
            observer.calls == []
        ), f"an empty log announced a crossing it never made: {observer.calls}"


class TestTheSentinelTracksWhatTheServerHolds:
    """Validates REQ-o00074-L, REQ-p00083-E, REQ-p00083-B: while a server holds
    unwritten changes the sentinel is present, and it is present at no other
    time -- so a reader outside the process learns exactly whether work is at
    stake.
    """

    @pytest.fixture
    def state(self, project: Path):
        from elspais.mcp.shared_state import attach_dirty_sentinel
        from elspais.server.state import AppState

        app_state = AppState.from_config(repo_root=project)
        attach_dirty_sentinel(app_state.shared)
        return app_state

    def test_REQ_o00074_L_nothing_is_recorded_before_the_first_change(self, state, project):
        assert not _sentinel(project).exists(), "a server holding nothing claimed to hold work"

    def test_REQ_o00074_L_the_first_change_puts_the_record_on_disk(self, state, project):
        state.graph.update_title(REQ, "User Authentication (held in memory)")

        assert _sentinel(project).exists(), (
            "a server holding an unwritten change left nothing outside itself to "
            "say so; killed here, the loss would be silent"
        )

    def test_REQ_o00074_L_further_changes_do_not_rewrite_the_record(self, state, project):
        state.graph.update_title(REQ, "User Authentication (one)")
        stamp = _sentinel(project).stat().st_mtime_ns

        state.graph.update_title(REQ, "User Authentication (two)")
        state.graph.update_title(REQ, "User Authentication (three)")

        entries = sorted(p.name for p in (project / ".elspais").iterdir())
        assert entries.count("unsaved-changes") == 1, entries
        assert _sentinel(project).stat().st_mtime_ns == stamp, (
            "the record was rewritten per mutation; it says the same thing each "
            "time and the writing is on the path a mutation waits for"
        )

    def test_REQ_o00074_L_client_requested_save_takes_the_record_away(self, state, project):
        from elspais.mcp.shared_state import persist_pending

        state.graph.update_title(REQ, "User Authentication (client-saved)")
        assert _sentinel(project).exists()

        assert persist_pending(state.shared, message="the client asked for this").get("success")

        assert not _sentinel(
            project
        ).exists(), "the work is on disk and the record still says it is held only in memory"

    def test_REQ_o00074_L_undoing_back_to_nothing_takes_the_record_away(self, state, project):
        state.graph.update_title(REQ, "User Authentication (held in memory)")
        assert _sentinel(project).exists()

        state.graph.undo_last()

        assert len(state.graph.mutation_log) == 0
        assert not _sentinel(
            project
        ).exists(), "nothing is held any more and the record still says something is"

    def test_REQ_o00074_L_reverting_takes_the_record_away_and_keeps_watching(self, project):
        """A revert does not empty the log, it replaces the graph. The record
        has to go with the work it described, and the watch has to follow the
        new log -- an observer left on the discarded one would leave the next
        change held with nothing outside the process saying so, which is the
        silent loss the whole arrangement exists to prevent."""
        from starlette.testclient import TestClient

        from elspais.graph import render
        from elspais.mcp.shared_state import attach_dirty_sentinel
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=project)
        attach_dirty_sentinel(state.shared)
        client = TestClient(create_app(state=state, mount_mcp=False))

        def _mutate(title: str) -> None:
            node = state.graph.find_by_id(REQ)
            resp = client.post(
                "/api/mutate/title",
                json={
                    "node_id": REQ,
                    "new_title": title,
                    "if_version": render.node_version(node),
                },
            )
            assert resp.status_code == 200, resp.text

        _mutate("User Authentication (about to be reverted)")
        assert _sentinel(project).exists()

        tip = client.get("/api/dirty").json()["tip"] or ""
        assert client.post("/api/revert", json={"if_tip_mutation_id": tip}).status_code == 200
        assert len(state.graph.mutation_log) == 0

        assert not _sentinel(
            project
        ).exists(), "nothing is held any more and the record still says something is"

        _mutate("User Authentication (held after the revert)")

        assert _sentinel(project).exists(), (
            "the watch stayed on the log the revert threw away, so a change held "
            "afterwards is recorded nowhere outside this process"
        )

    def test_REQ_o00074_L_an_instructed_discard_takes_the_record_away(self, state, project):
        """A discard is not a loss: somebody said the work was not wanted, so
        the record of work at risk goes with it rather than becoming a finding
        the next process has to explain."""
        from elspais.mcp.shared_state import finalize_shutdown

        state.graph.update_title(REQ, "User Authentication (thrown away)")
        assert _sentinel(project).exists()

        state.shared.request_discard()
        outcome = finalize_shutdown(state.shared, "a client asked the server to stop")

        assert outcome["discarded"] is True, outcome
        assert not _sentinel(project).exists()
        assert not _finding(
            project
        ).exists(), "a discard the operator asked for was reported as work lost"


class TestASentinelLeftBehindBecomesAFindingAboutItsWriter:
    """Validates REQ-o00074-L, REQ-o00074-J, REQ-p00083-F: a sentinel still
    standing when a server starts was written by a process that no longer
    exists, and it must not be readable as a statement about the starting one.
    It is converted to the record that says what is actually known, so
    presence keeps meaning "held now", is disclosed to later clients, and is
    retired once a client persists at its own request.
    """

    def test_REQ_o00074_L_adoption_converts_the_inherited_record(self, tmp_path):
        from elspais.mcp.daemon import (
            adopt_inherited_sentinel,
            has_lost_changes,
            has_unsaved_changes_sentinel,
            mark_unsaved_changes,
        )

        mark_unsaved_changes(tmp_path)

        assert adopt_inherited_sentinel(tmp_path) is True

        assert has_lost_changes(tmp_path), "the finding was discarded rather than recorded"
        assert not has_unsaved_changes_sentinel(tmp_path), (
            "the inherited record still stands, and now reads as a claim about a "
            "process that holds nothing"
        )

    def test_REQ_o00074_L_nothing_inherited_reports_nothing(self, tmp_path):
        from elspais.mcp.daemon import adopt_inherited_sentinel, has_lost_changes

        assert adopt_inherited_sentinel(tmp_path) is False
        assert not has_lost_changes(tmp_path), "a clean start invented a loss"

    def test_REQ_o00074_L_presence_never_answers_both_questions_at_once(self, project):
        """The invariant the whole arrangement rests on: after a start that
        inherited a sentinel, the live sentinel is absent. A reader that finds
        it present can only be reading about this process."""
        from elspais.mcp.daemon import mark_unsaved_changes
        from elspais.mcp.shared_state import attach_dirty_sentinel
        from elspais.server.state import AppState

        mark_unsaved_changes(project)  # the dead process's record

        state = AppState.from_config(repo_root=project)
        assert attach_dirty_sentinel(state.shared) is True

        assert _finding(project).exists(), "the inherited record was not turned into a finding"
        assert not _sentinel(project).exists(), (
            "the same file now answers 'what died holding work' and 'what is held "
            "now', and a reader cannot tell which question it answered"
        )

    def test_REQ_o00074_L_the_finding_is_disclosed_to_clients(self, project):
        from starlette.testclient import TestClient

        from elspais.mcp.daemon import mark_unsaved_changes
        from elspais.mcp.shared_state import attach_dirty_sentinel
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        mark_unsaved_changes(project)
        state = AppState.from_config(repo_root=project)
        attach_dirty_sentinel(state.shared)
        client = TestClient(create_app(state=state, mount_mcp=False))

        for route in ("/api/dirty", "/api/check-freshness"):
            notice = client.get(route).json().get("lost_changes")
            assert notice, f"{route} disclosed nothing about a process that died holding work"
            assert notice["note"].strip(), f"{route} disclosed an empty notice"

    def test_REQ_o00074_L_clean_start_discloses_no_finding(self, project):
        from starlette.testclient import TestClient

        from elspais.mcp.shared_state import attach_dirty_sentinel
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=project)
        assert attach_dirty_sentinel(state.shared) is False
        client = TestClient(create_app(state=state, mount_mcp=False))

        assert "lost_changes" not in client.get("/api/dirty").json()
        assert client.get("/api/check-freshness").json().get("lost_changes") is None

    def test_REQ_o00074_L_the_mcp_surface_discloses_the_finding_too(self, project):
        from elspais.mcp.daemon import mark_unsaved_changes
        from elspais.mcp.server import _build_base_workspace_info, _get_graph_status
        from elspais.mcp.shared_state import attach_dirty_sentinel
        from elspais.server.state import AppState

        mark_unsaved_changes(project)
        state = AppState.from_config(repo_root=project)
        attach_dirty_sentinel(state.shared)

        info = _build_base_workspace_info(project, state.config)
        assert info.get("lost_changes"), "get_workspace_info hid the finding from an agent"

        status = _get_graph_status(state.graph, project)
        assert status.get("lost_changes"), "get_graph_status hid the finding from an agent"

    def test_REQ_o00074_L_client_requested_save_retires_the_finding(self, project):
        """The finding describes the tree as the dead process left it. A client
        that writes the tree at its own request has replaced that tree, so the
        notice no longer describes anything and stops being shown."""
        from elspais.mcp.daemon import mark_unsaved_changes
        from elspais.mcp.shared_state import attach_dirty_sentinel, persist_pending
        from elspais.server.state import AppState

        mark_unsaved_changes(project)
        state = AppState.from_config(repo_root=project)
        attach_dirty_sentinel(state.shared)
        assert _finding(project).exists()

        state.graph.update_title(REQ, "User Authentication (client-saved)")
        assert persist_pending(state.shared, message="the client asked for this").get("success")

        assert not _finding(project).exists(), (
            "a notice about a superseded tree is still being shown, and a notice "
            "that never retires is one nobody reads"
        )
