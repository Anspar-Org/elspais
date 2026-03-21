# Implements: REQ-d00010
"""Tests for server state management and auto-refresh."""
import time
from pathlib import Path

_MINIMAL_CONFIG = """\
version = 3

[project]
name = "test"

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

    def test_link_mcp_state(self, tmp_path):
        """link_mcp_state() syncs graph and config into MCP state dict."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        mcp_state: dict = {}
        state.link_mcp_state(mcp_state)

        assert mcp_state["graph"] is state.graph
        assert mcp_state["config"] is state.config

    def test_rebuild_propagates_to_mcp_state(self, tmp_path):
        """After rebuild, linked MCP state dict receives new graph."""
        from elspais.server.state import AppState

        _make_repo(tmp_path)
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_file = spec_dir / "test.md"
        spec_file.write_text("# REQ-001\nTitle\n")

        state = AppState.from_config(repo_root=tmp_path)
        mcp_state: dict = {}
        state.link_mcp_state(mcp_state)

        original_graph = state.graph

        time.sleep(0.05)
        spec_file.write_text("# REQ-001\nNew title\n")

        state._last_stale_check = 0.0
        state.ensure_fresh()

        assert mcp_state["graph"] is state.graph
        assert mcp_state["graph"] is not original_graph

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


class TestAppStateDetached:
    """REQ-d00010: Detached HEAD tracking in AppState."""

    def test_initially_not_detached(self, tmp_path):
        """New AppState starts with detached state cleared."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        assert state.is_detached is False
        assert state.originating_branch is None
        assert state.originating_head is None

    def test_enter_detached_sets_fields(self, tmp_path):
        """enter_detached() records branch and commit, sets is_detached."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        state.enter_detached("main", "abc1234")
        assert state.is_detached is True
        assert state.originating_branch == "main"
        assert state.originating_head == "abc1234"

    def test_leave_detached_clears_fields(self, tmp_path):
        """leave_detached() resets all three detached-state fields."""
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=tmp_path)
        state.enter_detached("feature/foo", "deadbeef")
        state.leave_detached()
        assert state.is_detached is False
        assert state.originating_branch is None
        assert state.originating_head is None
