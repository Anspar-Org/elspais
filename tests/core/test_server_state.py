# Verifies: REQ-d00010, REQ-p00004-O, REQ-p00015-B, REQ-p00015-F, REQ-p00015-G
"""Tests for server state management and auto-refresh."""
import time
from pathlib import Path

_MINIMAL_CONFIG = """\
version = 3

[project]
name = "test"
namespace = "REQ"

[levels.prd]
rank = 1
letter = "p"
implements = ["prd"]

[levels.ops]
rank = 2
letter = "o"
implements = ["ops", "prd"]

[levels.dev]
rank = 3
letter = "d"
implements = ["dev", "ops", "prd"]
"""


# tomlkit rejects the bare newline inside the unterminated string, and the
# config loader wraps the parse error with the offending file's path.
_BROKEN_CONFIG = '[project]\nname = "unterminated\n'


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal repo layout with .elspais.toml."""
    (tmp_path / ".elspais.toml").write_text(_MINIMAL_CONFIG)
    return tmp_path


class TestAppState:
    """REQ-d00010: Server state management."""

    def test_initial_state(self, tmp_path):
        """AppState initializes with graph and tracks build time."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        assert state.graph is not None
        assert state.repo_root == tmp_path
        assert state.build_time > 0

    def test_is_stale_detects_file_change(self, tmp_path):
        """is_stale() returns True when a scanned file's mtime changes."""
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "test.md"
        spec_file.write_text("# REQ-001\nTitle\n")

        state = AppState.from_config(repo_root=tmp_path)
        state.snapshot_mtimes()

        assert not state.is_stale()

        # Touch the file
        time.sleep(0.05)
        spec_file.write_text("# REQ-001\nTitle changed\n")

        assert state.is_stale()

    def test_ensure_fresh_rebuilds_when_stale(self, tmp_path):
        """ensure_fresh() rebuilds graph when files changed."""
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "test.md"
        spec_file.write_text("# REQ-001\nTitle\n")

        state = AppState.from_config(repo_root=tmp_path)
        old_build_time = state.build_time

        time.sleep(0.05)
        spec_file.write_text("# REQ-001\nNew title\n")

        # Reset throttle so ensure_fresh() actually checks
        state._last_stale_check = 0.0
        state.ensure_fresh()
        assert state.build_time > old_build_time

    def test_ensure_fresh_noop_when_clean(self, tmp_path):
        """ensure_fresh() does not rebuild when no files changed."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        old_build_time = state.build_time

        # Reset throttle so ensure_fresh() actually checks
        state._last_stale_check = 0.0
        state.ensure_fresh()
        assert state.build_time == old_build_time

    def test_ensure_fresh_throttled(self, tmp_path):
        """ensure_fresh() skips check within throttle window."""
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "test.md"
        spec_file.write_text("# REQ-001\nTitle\n")

        state = AppState.from_config(repo_root=tmp_path)

        # Simulate a file change
        time.sleep(0.05)
        spec_file.write_text("# REQ-001\nChanged\n")

        # First call triggers check (throttle window not yet set)
        state._last_stale_check = 0.0
        state.ensure_fresh()
        build_after_first = state.build_time

        # Immediately call again — should be throttled, no rebuild
        spec_file.write_text("# REQ-001\nChanged again\n")
        result = state.ensure_fresh()
        assert result is False
        assert state.build_time == build_after_first

    def test_shared_holder_is_the_single_source(self, tmp_path):
        """Validates REQ-o00062-Q: AppState.graph/.config ARE the shared holder.

        There is no propagation step to forget: .graph and .config are
        properties over one SharedServerState cell, so any surface holding
        the same object dereferences the same graph by construction.
        """
        from elspais.mcp.shared_state import SharedServerState
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)

        assert isinstance(state.shared, SharedServerState)
        assert state.shared["graph"] is state.graph
        assert state.shared["config"] is state.config
        assert state.shared["working_dir"] == tmp_path
        # The lock every mutation critical section serializes under.
        assert hasattr(state.shared, "write_lock")

    def test_rebuild_swaps_graph_inside_the_same_holder(self, tmp_path):
        """Validates REQ-o00062-Q: a rebuild swaps the graph IN the holder.

        The SharedServerState instance itself must survive the rebuild --
        replacing it would orphan every other surface holding a reference,
        which is exactly the split-brain being prevented.
        """
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "test.md"
        spec_file.write_text("# REQ-001\nTitle\n")

        state = AppState.from_config(repo_root=tmp_path)
        holder = state.shared
        original_graph = state.graph

        time.sleep(0.05)
        spec_file.write_text("# REQ-001\nNew title\n")

        state._last_stale_check = 0.0
        state.ensure_fresh()

        assert state.shared is holder, "rebuild must not replace the shared holder"
        assert holder["graph"] is state.graph
        assert holder["graph"] is not original_graph

    def test_is_stale_detects_new_file(self, tmp_path):
        """is_stale() returns True when a new file appears in a scanned dir."""
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        state = AppState.from_config(repo_root=tmp_path)
        state.snapshot_mtimes()

        assert not state.is_stale()

        # Add a new file
        new_file = spec_dir / "new.md"
        new_file.write_text("# REQ-002\nNew req\n")

        assert state.is_stale()

    def test_allowed_roots_defaults_to_repo_root(self, tmp_path):
        """AppState.allowed_roots defaults to [repo_root]."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        assert tmp_path in state.allowed_roots


class TestEnsureFreshHonestRebuildReport:
    """Validates REQ-p00015-F: ensure_fresh() records a rebuild as applied only
    when the rebuilt graph is what the state actually serves afterwards.

    Validates REQ-p00015-B: when the rebuild does not happen, the state reports
    the unapplied rebuild and its cause on stderr.

    A rebuild that raises leaves the previous graph in place. Reporting that
    rebuild to the caller as done is phantom success: the caller is told the
    served graph came from disk when it did not. The same defect one level
    down is a partially-applied rebuild -- the freshly read on-disk config
    recorded in the holder while the graph beside it was built from the old
    one.
    """

    REBUILD_CAUSE = "probe-cause-disk-vanished"

    @staticmethod
    def _stale_state(tmp_path):
        """An AppState whose spec file changed on disk since the last build."""
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "test.md"
        spec_file.write_text("# REQ-001\nTitle\n")

        state = AppState.from_config(repo_root=tmp_path)
        time.sleep(0.05)
        spec_file.write_text("# REQ-001\nNew title\n")
        # Reset throttle so ensure_fresh() actually checks.
        state._last_stale_check = 0.0
        assert state.is_stale(), "fixture must present a genuinely stale state"
        return state

    def _break_rebuild(self, state, monkeypatch):
        """Make _rebuild() raise with a distinctive, greppable cause."""

        def _raise() -> None:
            raise RuntimeError(self.REBUILD_CAUSE)

        monkeypatch.setattr(state, "_rebuild", _raise)

    def test_REQ_p00015_F_failed_rebuild_is_not_reported_as_rebuilt(self, tmp_path, monkeypatch):
        """A rebuild that raised must not be returned as a rebuild that happened."""
        state = self._stale_state(tmp_path)
        self._break_rebuild(state, monkeypatch)

        assert state.ensure_fresh() is False, "ensure_fresh() reported a rebuild it did not perform"

    def test_REQ_p00015_F_failed_rebuild_keeps_serving_the_previous_graph(
        self, tmp_path, monkeypatch
    ):
        """The record's destination -- the served graph -- must be untouched."""
        state = self._stale_state(tmp_path)
        graph_before = state.graph
        build_time_before = state.build_time
        self._break_rebuild(state, monkeypatch)

        state.ensure_fresh()

        assert state.graph is graph_before, "failed rebuild swapped the served graph"
        assert state.build_time == build_time_before, "failed rebuild advanced the build clock"

    def test_REQ_p00015_B_failed_rebuild_reports_the_cause(self, tmp_path, monkeypatch, capsys):
        """The unapplied rebuild and its cause reach stderr."""
        state = self._stale_state(tmp_path)
        self._break_rebuild(state, monkeypatch)

        state.ensure_fresh()

        err = capsys.readouterr().err
        assert "rebuild" in err, f"failure report does not name the operation: {err!r}"
        assert self.REBUILD_CAUSE in err, f"failure report does not carry the cause: {err!r}"

    def test_REQ_p00015_F_failed_rebuild_does_not_record_the_new_config(
        self, tmp_path, monkeypatch
    ):
        """A rebuild that dies mid-way must not record its config half.

        The config in the shared holder names the configuration the served
        graph was built from. Swapping in the newly read on-disk config while
        the old graph is still served records a change that is not present at
        the destination the record names.
        """
        state = self._stale_state(tmp_path)
        assert state.config["project"]["name"] == "test"

        # New config on disk, and a build that cannot complete against it.
        (tmp_path / ".elspais.toml").write_text(
            _MINIMAL_CONFIG.replace('name = "test"', 'name = "renamed-on-disk"')
        )
        state._last_stale_check = 0.0

        def _raise(*args, **kwargs):
            raise RuntimeError(self.REBUILD_CAUSE)

        monkeypatch.setattr("elspais.graph.factory.build_graph", _raise)

        state.ensure_fresh()

        assert state.config["project"]["name"] == "test", (
            "failed rebuild recorded the new on-disk config while still "
            "serving the graph built from the old one"
        )

    def test_REQ_p00015_F_successful_rebuild_is_reported_as_rebuilt(self, tmp_path):
        """A rebuild that completed is still reported -- honesty cuts both ways."""
        state = self._stale_state(tmp_path)
        graph_before = state.graph
        build_time_before = state.build_time

        assert state.ensure_fresh() is True
        assert state.graph is not graph_before
        assert state.build_time > build_time_before


class TestSharedStateWithMcpServer:
    """REQ-o00062-Q: the MCP tools and AppState dereference one holder."""

    SPEC_REQ = """\
### REQ-p00001: Shared Holder Probe

**Level**: PRD | **Status**: Active

The system SHALL expose one graph to every mutation surface.

## Assertions

A. The system SHALL swap the graph inside the shared holder on rebuild.

*End* *Shared Holder Probe* | **Hash**: 00000000
"""

    @staticmethod
    def _holder_of(server):
        """Extract the SharedServerState a server's tool closures capture."""
        from elspais.mcp.shared_state import SharedServerState

        fn = server._tool_manager._tools["get_mutation_log"].fn
        for cell in fn.__closure__ or ():
            if isinstance(cell.cell_contents, SharedServerState):
                return cell.cell_contents
        raise AssertionError("no SharedServerState found in tool closure")

    def _make_project(self, tmp_path):
        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "core.md").write_text(self.SPEC_REQ)
        return spec_dir / "core.md"

    def test_mcp_tools_write_through_appstate_holder_across_rebuild(self, tmp_path):
        """Validates REQ-o00062-Q: an MCP write after a rebuild lands in the
        graph AppState now serves, not in a stale pre-rebuild reference.

        This is the CUR-1829 split-brain regression at unit scope: before
        SharedServerState, the rebuild reassigned only one side's graph and
        the other side's accepted writes went to a discarded object.
        """
        import pytest as _pytest

        _pytest.importorskip("mcp")
        from elspais.graph.render import node_version
        from elspais.mcp.server import create_server
        from elspais.server.state import AppState

        spec_file = self._make_project(tmp_path)
        state = AppState.from_config(repo_root=tmp_path)
        server = create_server(graph=state.graph, working_dir=tmp_path, shared_state=state.shared)
        assert self._holder_of(server) is state.shared
        tools = {name: tool.fn for name, tool in server._tool_manager._tools.items()}

        # Rebuild: the graph object is replaced inside the shared holder.
        original_graph = state.graph
        time.sleep(0.05)
        spec_file.write_text(self.SPEC_REQ.replace("SHALL expose", "SHALL always expose"))
        state._last_stale_check = 0.0
        state.ensure_fresh()
        assert state.graph is not original_graph

        # The MCP tool must mutate the CURRENT graph -- no propagation step.
        node = state.graph.find_by_id("REQ-p00001")
        assert node is not None
        result = tools["mutate_update_title"](
            node_id="REQ-p00001",
            new_title="Shared Holder Probe (written over MCP)",
            if_version=node_version(node),
        )

        assert result["success"] is True, result
        assert len(state.graph.mutation_log) == 1
        assert (
            state.graph.find_by_id("REQ-p00001").get_label()
            == "Shared Holder Probe (written over MCP)"
        )
        assert len(original_graph.mutation_log) == 0

    def test_build_time_lives_in_the_holder_not_on_appstate(self, tmp_path):
        """Validates REQ-o00062-Q: build_time is a cell of the shared holder.

        A standalone holder self-initializes it (an MCP-only server has no
        AppState to seed it), and AppState reads it back through the holder --
        so the MCP tools' ``_state["build_time"] = ...`` stamp after a
        graph swap is immediately what the viewer's staleness check compares
        spec-file mtimes against.
        """
        from elspais.mcp.shared_state import SharedServerState
        from elspais.server.state import AppState

        bare = SharedServerState()
        assert bare["build_time"] > 0

        state = AppState.from_config(repo_root=tmp_path)
        assert state.build_time == state.shared["build_time"]

        # An MCP-side stamp (holder write) is what AppState now serves...
        state.shared["build_time"] = 1234.5
        assert state.build_time == 1234.5
        # ...and a viewer-side rebuild (property write) lands in the same cell,
        # rather than shadowing it with a per-object attribute.
        state.build_time = 6789.0
        assert state.shared["build_time"] == 6789.0
        assert "build_time" not in vars(state)

    def test_mcp_save_advances_build_time_so_the_viewer_stays_calm(self, tmp_path):
        """Validates REQ-o00062-Q: an MCP save must not leave the viewer's
        freshness clock behind its own writes.

        ``save_mutations`` renders spec files to disk and rebuilds the graph.
        The files it just wrote are now newer than the build_time the viewer
        compares against -- so unless the save stamps the shared holder, the
        very next ``/api/check-freshness`` poll reports "spec files have
        changed on disk" for a graph that already matches disk exactly.
        """
        import pytest as _pytest

        _pytest.importorskip("mcp")
        from starlette.testclient import TestClient

        from elspais.graph.render import node_version
        from elspais.mcp.server import create_server
        from elspais.server.app import create_app
        from elspais.server.state import AppState

        spec_file = self._make_project(tmp_path)
        state = AppState.from_config(repo_root=tmp_path)
        server = create_server(graph=state.graph, working_dir=tmp_path, shared_state=state.shared)
        tools = {name: tool.fn for name, tool in server._tool_manager._tools.items()}
        client = TestClient(create_app(state=state, mount_mcp=False))

        assert client.get("/api/check-freshness").json()["stale"] is False
        build_time_before_save = state.build_time

        mutated = tools["mutate_update_title"](
            node_id="REQ-p00001",
            new_title="Shared Holder Probe (saved over MCP)",
            if_version=node_version(state.graph.find_by_id("REQ-p00001")),
        )
        assert mutated["success"] is True, mutated

        entries = list(state.graph.mutation_log.iter_entries())
        time.sleep(0.05)
        saved = tools["save_mutations"](
            if_tip_mutation_id=entries[-1].id,
            message="build_time stamping regression",
        )
        assert saved.get("success") is True, saved

        # The write really did land after the pre-save clock, which is what
        # would have tripped the false alarm.
        assert spec_file.stat().st_mtime > build_time_before_save
        assert state.build_time > build_time_before_save

        freshness = client.get("/api/check-freshness").json()
        assert freshness["stale"] is False, freshness
        assert freshness["stale_files"] == []
        assert freshness["has_pending_mutations"] is False
        assert freshness["mutation_tip"] == ""

    def test_create_server_without_holder_creates_a_private_one(self, tmp_path):
        """Validates REQ-o00062-Q: a standalone server (stdio, tests) gets its
        own SharedServerState populated with its graph and working dir."""
        import pytest as _pytest

        _pytest.importorskip("mcp")
        from elspais.graph.factory import build_graph
        from elspais.mcp.server import create_server
        from elspais.mcp.shared_state import SharedServerState

        self._make_project(tmp_path)
        graph = build_graph(repo_root=tmp_path)
        server = create_server(graph=graph, working_dir=tmp_path)

        holder = self._holder_of(server)
        assert isinstance(holder, SharedServerState)
        assert holder["graph"] is graph
        assert holder["working_dir"] == tmp_path
        assert hasattr(holder, "write_lock")


class TestAppStateDetached:
    """REQ-d00010: Detached HEAD tracking in AppState."""

    def test_initially_not_detached(self, tmp_path):
        """New AppState starts with detached state cleared."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        assert state.is_detached is False

    def test_enter_detached_sets_fields(self, tmp_path):
        """enter_detached() records branch and commit, sets is_detached."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        state.enter_detached("root", "main", "abc1234")
        assert state.is_detached is True

    def test_leave_detached_clears_fields(self, tmp_path):
        """leave_detached() resets detached state for the given repo."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        state.enter_detached("root", "feature/foo", "deadbeef")
        state.leave_detached("root")
        assert state.is_detached is False


class TestPerRepoDetachedState:
    """REQ-p00004-I: Per-repo detached HEAD tracking."""

    def test_enter_detached_for_repo(self, tmp_path):
        """enter_detached stores state keyed by repo name."""
        state = self._make_state(tmp_path)
        state.enter_detached("root", "feat-branch", "abc123")
        assert state.is_repo_detached("root")
        ds = state.get_detached_state("root")
        assert ds.originating_branch == "feat-branch"
        assert ds.originating_head == "abc123"

    def test_leave_detached_for_repo(self, tmp_path):
        """leave_detached clears state for specific repo."""
        state = self._make_state(tmp_path)
        state.enter_detached("root", "feat-branch", "abc123")
        state.enter_detached("core", "feat-branch", "def456")
        state.leave_detached("root")
        assert not state.is_repo_detached("root")
        assert state.is_repo_detached("core")

    def test_is_any_detached(self, tmp_path):
        """is_detached returns True if any repo is detached."""
        state = self._make_state(tmp_path)
        assert not state.is_detached
        state.enter_detached("core", "feat-branch", "abc123")
        assert state.is_detached

    def test_get_detached_state_returns_none(self, tmp_path):
        """get_detached_state returns None for non-detached repo."""
        state = self._make_state(tmp_path)
        assert state.get_detached_state("root") is None

    @staticmethod
    def _make_state(tmp_path):
        """Create a minimal AppState for testing."""
        from elspais.server.state import AppState

        state = AppState.__new__(AppState)
        state.repo_root = tmp_path
        state._repo_detached = {}
        return state


class TestMcpRefreshAbsorbsChangeDetectionState:
    """Validates REQ-p00004-O: MCP ``refresh_graph`` is a reload from disk and
    must bring the change-detection state held for the reloaded content into
    agreement with it.

    The MCP tools and the viewer share one holder, so an MCP refresh that
    leaves the viewer's mtime snapshot and daemon.json's config hash behind
    makes the viewer rebuild the same files a second time and makes the CLI
    restart a daemon that is already current.
    """

    SPEC_REQ = """\
### REQ-p00001: Refresh Freshness Probe

**Level**: PRD | **Status**: Active

The system SHALL absorb its own reloads.

## Assertions

A. The system SHALL leave no staleness a completed reload already absorbed.

*End* *Refresh Freshness Probe* | **Hash**: 00000000
"""

    def _project(self, tmp_path):
        """A real repo plus an AppState and the MCP tools over its holder."""
        import pytest as _pytest

        _pytest.importorskip("mcp")
        from elspais.mcp.server import create_server
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "core.md"
        spec_file.write_text(self.SPEC_REQ)

        state = AppState.from_config(repo_root=tmp_path)
        server = create_server(graph=state.graph, working_dir=tmp_path, shared_state=state.shared)
        tools = {name: tool.fn for name, tool in server._tool_manager._tools.items()}
        return state, tools, spec_file

    def test_REQ_p00004_O_mcp_refresh_leaves_no_redundant_rebuild(self, tmp_path):
        """After MCP refresh_graph absorbs a disk change, the viewer's next
        freshness check must not find that same change still outstanding."""
        state, tools, spec_file = self._project(tmp_path)

        time.sleep(0.05)
        spec_file.write_text(self.SPEC_REQ.replace("SHALL absorb", "SHALL always absorb"))

        result = tools["refresh_graph"]()
        assert result.get("success") is True, result
        build_time_after_refresh = state.build_time

        state._last_stale_check = 0.0
        rebuilt = state.ensure_fresh()

        assert rebuilt is False, (
            "the freshness check after a completed MCP refresh reported the "
            "change the refresh already absorbed, and rebuilt a second time"
        )
        assert (
            state.build_time == build_time_after_refresh
        ), "build_time moved after the refresh with nothing changed on disk"

    def test_REQ_p00004_O_mcp_refresh_syncs_daemon_config_hash(self, tmp_path):
        """A refresh that re-read an edited config must leave daemon.json's
        config_hash agreeing with that config, with no later request needed."""
        import json

        from elspais.mcp.daemon import compute_config_hash

        state, tools, _spec_file = self._project(tmp_path)
        config_path = tmp_path / ".elspais.toml"

        daemon_json = tmp_path / ".elspais" / "daemon.json"
        daemon_json.parent.mkdir(parents=True, exist_ok=True)
        daemon_json.write_text(
            json.dumps(
                {
                    "pid": 1,
                    "port": 5000,
                    "repo_root": str(tmp_path),
                    "started_at": "2026-01-01T00:00:00",
                    "version": "0.0.0",
                    "config_hash": compute_config_hash(config_path),
                    "type": "daemon",
                }
            )
        )

        time.sleep(0.05)
        config_path.write_text(_MINIMAL_CONFIG.replace('name = "test"', 'name = "renamed-on-disk"'))
        assert json.loads(daemon_json.read_text())["config_hash"] != compute_config_hash(
            config_path
        ), "fixture must present a genuinely stale recorded config hash"

        result = tools["refresh_graph"]()
        assert result.get("success") is True, result

        assert json.loads(daemon_json.read_text())["config_hash"] == compute_config_hash(
            config_path
        ), "daemon.json still records the config the refresh replaced"


class TestPostRebuildHookFailureDoesNotRetractTheRebuild:
    """Validates REQ-p00015-F: a rebuild is recorded as applied whenever the
    rebuilt graph is what the state serves afterwards -- including when a
    post-rebuild hook then fails.

    The hooks run after config, graph and build_time are published, so by the
    time one of them raises, the new graph IS what every reader dereferences.
    Reporting that rebuild as not-done is the mirror image of phantom success:
    a phantom failure, telling the caller the served graph came from the
    previous build when it did not. The state that a failing hook could not
    bring forward is a separate, lesser problem.

    Validates REQ-p00015-B: the hook failure is reported with its cause on
    stderr rather than being swallowed.
    """

    HOOK_CAUSE = "probe-cause-hook-refused"

    @staticmethod
    def _stale_state(tmp_path):
        """An AppState whose spec file changed on disk since the last build."""
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "test.md"
        spec_file.write_text("# REQ-001\nTitle\n")

        state = AppState.from_config(repo_root=tmp_path)
        time.sleep(0.05)
        spec_file.write_text("# REQ-001\nNew title\n")
        state._last_stale_check = 0.0
        assert state.is_stale(), "fixture must present a genuinely stale state"
        return state

    def _break_a_hook(self, state):
        """Register a failing post-rebuild hook after the real ones."""

        def _raise() -> None:
            raise RuntimeError(self.HOOK_CAUSE)

        state.shared.post_rebuild_hooks.append(_raise)

    # Verifies: REQ-p00015-F
    def test_REQ_p00015_F_failing_hook_does_not_retract_the_rebuild(self, tmp_path, capsys):
        """The swap the readers can already see must be reported as having
        happened, and the served graph must be the newly built one."""
        state = self._stale_state(tmp_path)
        graph_before = state.graph
        build_time_before = state.build_time
        self._break_a_hook(state)

        rebuilt = state.ensure_fresh()

        assert rebuilt is True, (
            "a hook failure after publication retracted a rebuild that is "
            "already visible to every reader"
        )
        assert state.graph is not graph_before, "the served graph was not swapped"
        assert state.shared["graph"] is state.graph
        assert state.build_time > build_time_before, "the build clock did not move"

    # Verifies: REQ-p00015-B
    def test_REQ_p00015_B_failing_hook_reports_its_cause(self, tmp_path, capsys):
        """The hook that could not bring its state forward is named on stderr."""
        state = self._stale_state(tmp_path)
        self._break_a_hook(state)

        state.ensure_fresh()

        err = capsys.readouterr().err
        assert "post-rebuild hook" in err, f"report does not name the operation: {err!r}"
        assert self.HOOK_CAUSE in err, f"report does not carry the cause: {err!r}"

    # Verifies: REQ-p00015-F
    def test_REQ_p00015_F_hooks_before_the_failing_one_still_ran(self, tmp_path, capsys):
        """A hook that raises must not cost the hooks already brought forward.

        ``snapshot_mtimes`` runs before the failing hook. If the exception
        escaped the loop, the freshness check would still see the absorbed
        change outstanding and rebuild the same content a second time.
        """
        state = self._stale_state(tmp_path)
        self._break_a_hook(state)

        assert state.ensure_fresh() is True

        state._last_stale_check = 0.0
        assert state.ensure_fresh() is False, (
            "the change the completed rebuild absorbed is still reported as "
            "outstanding, so its mtime re-snapshot was lost"
        )


class TestDaemonFingerprintIsStampedOnlyByItsOwner:
    """Validates REQ-p00004-O: the recorded config fingerprint is brought
    forward by the process that serves the graph the daemon record describes,
    and by no other.

    The sync is a hook the owning ``AppState`` registers, not a step of the
    shared rebuild routine, so a process holding a private graph of its own --
    a stdio MCP server built by ``create_server()`` -- rebuilds in the same
    repository without touching another server's record.

    Validates REQ-p00015-G: a fingerprint stamped by a process that did not
    rebuild the daemon's graph reads as current when it is not, suppressing
    the disclosure that the running server serves a superseded configuration.
    """

    @staticmethod
    def _project_with_daemon_record(tmp_path):
        """A repo plus a daemon.json whose config_hash matches disk."""
        import json

        from elspais.mcp.daemon import compute_config_hash

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "core.md").write_text("# REQ-001\nTitle\n")

        config_path = tmp_path / ".elspais.toml"
        daemon_json = tmp_path / ".elspais" / "daemon.json"
        daemon_json.parent.mkdir(parents=True, exist_ok=True)
        daemon_json.write_text(
            json.dumps(
                {
                    "pid": 1,
                    "port": 5000,
                    "repo_root": str(tmp_path),
                    "started_at": "2026-01-01T00:00:00",
                    "version": "0.0.0",
                    "config_hash": compute_config_hash(config_path),
                    "type": "daemon",
                }
            )
        )
        return config_path, daemon_json

    @staticmethod
    def _edit_config(config_path, daemon_json):
        """Move the config on disk past the recorded fingerprint."""
        import json

        from elspais.mcp.daemon import compute_config_hash

        recorded = json.loads(daemon_json.read_text())["config_hash"]
        time.sleep(0.05)
        config_path.write_text(_MINIMAL_CONFIG.replace('name = "test"', 'name = "renamed-on-disk"'))
        assert recorded != compute_config_hash(
            config_path
        ), "fixture must present a genuinely stale recorded config hash"
        return recorded

    # Verifies: REQ-p00004-O, REQ-p00015-G
    def test_REQ_p00004_O_a_holder_without_hooks_leaves_the_record_alone(self, tmp_path):
        """A bare holder -- what a stdio MCP server carries -- must not stamp
        a daemon record it does not own."""
        import json

        from elspais.mcp.shared_state import SharedServerState, rebuild_shared_graph

        config_path, daemon_json = self._project_with_daemon_record(tmp_path)
        recorded = self._edit_config(config_path, daemon_json)

        holder = SharedServerState({"working_dir": tmp_path})
        assert holder.post_rebuild_hooks == []
        result = rebuild_shared_graph(holder)

        # Without this the test cannot tell "no hook" from "no rebuild":
        # a rebuild that failed would also leave the record untouched.
        assert result["success"] is True, result
        assert holder["graph"] is not None

        assert json.loads(daemon_json.read_text())["config_hash"] == recorded, (
            "a process that rebuilt only its own private graph stamped another "
            "server's freshness record as current"
        )

    # Verifies: REQ-p00004-O
    def test_REQ_p00004_O_the_owning_appstate_does_stamp_the_record(self, tmp_path):
        """The positive counterpart: the process that owns the record brings
        it forward through the very same rebuild routine."""
        import json

        from elspais.mcp.daemon import compute_config_hash
        from elspais.mcp.shared_state import rebuild_shared_graph
        from elspais.server.state import AppState

        config_path, daemon_json = self._project_with_daemon_record(tmp_path)
        state = AppState.from_config(repo_root=tmp_path)
        self._edit_config(config_path, daemon_json)

        result = rebuild_shared_graph(state.shared)
        assert result["success"] is True, result

        assert json.loads(daemon_json.read_text())["config_hash"] == compute_config_hash(
            config_path
        ), "the server that owns the record left it describing the config it replaced"


class TestEnsureFreshReportsTheRoutinesFailureMessage:
    """Validates REQ-p00015-B: when the rebuild routine declines to publish,
    the message it gives for declining is what reaches the operator.

    A rebuild can fail without raising: an unparseable configuration is
    reported as an ordinary unsuccessful result carrying ``CONFIG ERROR:`` and
    the offending file. That result must be converted into the same visible,
    caused report as an exception, or the one failure mode an operator can
    actually fix is the one that surfaces without a reason.
    """

    # Verifies: REQ-p00015-B, REQ-p00015-F
    def test_REQ_p00015_B_unparseable_on_disk_config_reports_its_cause(self, tmp_path, capsys):
        """The routine's own CONFIG ERROR message reaches stderr intact."""
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "core.md").write_text("# REQ-001\nTitle\n")

        state = AppState.from_config(repo_root=tmp_path)
        graph_before = state.graph

        time.sleep(0.05)
        (tmp_path / ".elspais.toml").write_text(_BROKEN_CONFIG)
        state._last_stale_check = 0.0
        assert state.is_stale(), "fixture must present a genuinely stale state"

        rebuilt = state.ensure_fresh()

        assert rebuilt is False, "a rebuild that published nothing was reported as done"
        assert state.graph is graph_before, "the previous graph stopped being served"

        err = capsys.readouterr().err
        assert "CONFIG ERROR:" in err, f"report does not carry the routine's reason: {err!r}"
        assert ".elspais.toml" in err, f"report does not name the offending file: {err!r}"
