# Verifies: REQ-d00010
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
