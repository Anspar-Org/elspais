# Git & Daemon Test Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate git env leakage and daemon misrouting so tests safely use real daemons, and the daemon routing is correct by construction for all users.

**Architecture:** Viewer writes `daemon.json` like the daemon does, removing the hardcoded port 5001 probe. `_try_daemon()` becomes a single path: read `daemon.json` → use or auto-start. Git env isolation uses `pytest_configure` + `GIT_CEILING_DIRECTORIES`. E2e tests restore `cli_ttl=2` and get cleanup fixtures.

**Tech Stack:** Python stdlib, pytest fixtures, existing `daemon.py` infrastructure

**Spec:** `docs/superpowers/specs/2026-03-24-git-daemon-test-isolation-design.md`

---

### Task 1: `start_daemon()` stops existing server before overwriting

**Files:**
- Modify: `src/elspais/mcp/daemon.py:120-134`
- Test: `tests/core/test_git.py` (or new `tests/mcp/test_daemon_lifecycle.py`)

- [ ] **Step 1: Write failing test**

Create `tests/mcp/test_daemon_lifecycle.py`:

```python
# Verifies: REQ-d00010
"""Tests for daemon lifecycle — no orphan servers."""

from pathlib import Path
from unittest.mock import patch


def test_start_daemon_stops_existing_first(tmp_path):
    """start_daemon() must call stop_daemon() before overwriting daemon.json."""
    from elspais.mcp.daemon import start_daemon

    calls = []

    with (
        patch("elspais.mcp.daemon.stop_daemon", side_effect=lambda r: calls.append(("stop", r))),
        patch("elspais.mcp.daemon.get_daemon_info", return_value={"pid": 999, "port": 8888}),
        patch("elspais.mcp.daemon.subprocess.Popen"),
        patch("elspais.mcp.daemon.time.time", side_effect=[0, 0, 0, 20]),  # force timeout
    ):
        try:
            start_daemon(tmp_path, ttl_minutes=1)
        except RuntimeError:
            pass  # Expected: daemon won't actually start

    assert len(calls) == 1
    assert calls[0] == ("stop", tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/mcp/test_daemon_lifecycle.py::test_start_daemon_stops_existing_first -v`
Expected: FAIL — `stop_daemon` is not called.

- [ ] **Step 3: Implement — add `stop_daemon()` call to `start_daemon()`**

In `src/elspais/mcp/daemon.py`, replace lines 132-134:

```python
    daemon_json = _daemon_json_path(repo_root)
    daemon_json.parent.mkdir(parents=True, exist_ok=True)
    daemon_json.unlink(missing_ok=True)
```

with:

```python
    # Stop any existing server before overwriting daemon.json.
    # Without this, the old server becomes an undiscoverable orphan.
    stop_daemon(repo_root)

    daemon_json = _daemon_json_path(repo_root)
    daemon_json.parent.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/mcp/test_daemon_lifecycle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/mcp/daemon.py tests/mcp/test_daemon_lifecycle.py
git commit -m "fix: start_daemon stops existing server before overwriting daemon.json"
```

---

### Task 2: Add `type` field to `daemon.json` + `write_daemon_json` helper

**Files:**
- Modify: `src/elspais/mcp/daemon.py`
- Modify: `src/elspais/mcp/server.py:5687-5699`
- Test: `tests/mcp/test_daemon_lifecycle.py`

- [ ] **Step 1: Write failing test**

Add to `tests/mcp/test_daemon_lifecycle.py`:

```python
def test_write_daemon_json_includes_type(tmp_path):
    """write_daemon_json() must include a 'type' field."""
    from elspais.mcp.daemon import write_daemon_json

    path = tmp_path / ".elspais" / "daemon.json"
    write_daemon_json(
        repo_root=tmp_path,
        pid=12345,
        port=9999,
        server_type="daemon",
    )

    import json

    data = json.loads(path.read_text())
    assert data["type"] == "daemon"
    assert data["pid"] == 12345
    assert data["port"] == 9999
    assert data["repo_root"] == str(tmp_path)
    assert "version" in data
    assert "started_at" in data


def test_write_daemon_json_viewer_type(tmp_path):
    """write_daemon_json() accepts type='viewer'."""
    from elspais.mcp.daemon import write_daemon_json

    write_daemon_json(
        repo_root=tmp_path,
        pid=12345,
        port=5001,
        server_type="viewer",
    )

    import json

    data = json.loads((tmp_path / ".elspais" / "daemon.json").read_text())
    assert data["type"] == "viewer"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp/test_daemon_lifecycle.py -v -k "write_daemon_json"`
Expected: FAIL — `write_daemon_json` does not exist.

- [ ] **Step 3: Implement `write_daemon_json` in `daemon.py`**

Add to `src/elspais/mcp/daemon.py` after the existing imports:

```python
def write_daemon_json(
    repo_root: Path,
    pid: int,
    port: int,
    server_type: str = "daemon",
) -> Path:
    """Write daemon.json state file for a running server.

    Both the headless daemon and the viewer use this to register
    themselves as the active server for a project.

    Args:
        repo_root: Project root directory.
        pid: Process ID of the server.
        port: Port the server is listening on.
        server_type: "daemon" or "viewer".

    Returns:
        Path to the written daemon.json file.
    """
    import time

    from elspais import __version__

    daemon_json = _daemon_json_path(repo_root)
    daemon_json.parent.mkdir(parents=True, exist_ok=True)

    config_path = repo_root / ".elspais.toml"
    config_hash = compute_config_hash(config_path) if config_path.is_file() else ""

    daemon_json.write_text(
        json.dumps(
            {
                "pid": pid,
                "port": port,
                "repo_root": str(repo_root),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "version": __version__,
                "config_hash": config_hash,
                "type": server_type,
            }
        )
    )
    return daemon_json
```

Then update `server.py` to use it. In `src/elspais/mcp/server.py`, replace the inline daemon.json write block (lines 5687-5700) with:

```python
        if daemon_json:
            from elspais.mcp.daemon import write_daemon_json

            write_daemon_json(
                repo_root=working_dir,
                pid=_os.getpid(),
                port=port,
                server_type="daemon",
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mcp/test_daemon_lifecycle.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/mcp/daemon.py src/elspais/mcp/server.py tests/mcp/test_daemon_lifecycle.py
git commit -m "refactor: extract write_daemon_json with type field"
```

---

### Task 3: Viewer writes `daemon.json` on start, removes on stop

**Files:**
- Modify: `src/elspais/commands/viewer.py:210-226`
- Test: `tests/commands/test_engine_graph_source.py` (updated later)

- [ ] **Step 1: Write failing test for viewer daemon.json lifecycle**

Add to `tests/mcp/test_daemon_lifecycle.py`:

```python
def test_viewer_cleanup_removes_daemon_json(tmp_path):
    """Viewer must remove daemon.json in its finally block."""
    from elspais.mcp.daemon import _daemon_json_path, write_daemon_json

    # Simulate viewer writing daemon.json
    write_daemon_json(repo_root=tmp_path, pid=99999, port=5001, server_type="viewer")
    path = _daemon_json_path(tmp_path)
    assert path.exists()

    # Simulate viewer cleanup (the finally block)
    path.unlink(missing_ok=True)
    assert not path.exists()


def test_viewer_atexit_removes_daemon_json(tmp_path):
    """atexit handler must remove daemon.json as safety net."""
    from elspais.mcp.daemon import _daemon_json_path, write_daemon_json

    path = _daemon_json_path(tmp_path)
    write_daemon_json(repo_root=tmp_path, pid=99999, port=5001, server_type="viewer")
    assert path.exists()

    # The atexit handler is a closure over daemon_json path
    # Simulate it running
    path.unlink(missing_ok=True)
    assert not path.exists()
```

- [ ] **Step 2: Run tests to verify they pass** (these test the behavior pattern, not viewer.py itself)

Run: `pytest tests/mcp/test_daemon_lifecycle.py -v -k "viewer"`
Expected: PASS

- [ ] **Step 3: Implement — viewer writes and cleans up `daemon.json`**

In `src/elspais/commands/viewer.py`, add the `daemon.json` write before the server loop, and cleanup in `finally`. Replace lines 210-226:

```python
    # Register this viewer in daemon.json so CLI commands find it
    from elspais.mcp.daemon import (
        _daemon_json_path,
        stop_daemon,
        write_daemon_json,
    )

    stop_daemon(repo_root)  # Kill any existing server for this project
    write_daemon_json(
        repo_root=repo_root,
        pid=os.getpid(),
        port=port,
        server_type="viewer",
    )
    daemon_json = _daemon_json_path(repo_root)

    # Safety net: remove daemon.json even on unhandled exits
    import atexit

    atexit.register(lambda: daemon_json.unlink(missing_ok=True))

    try:
        import anyio
        import uvicorn

        uvi_config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning" if quiet else "info",
        )
        server = uvicorn.Server(uvi_config)
        anyio.run(server.serve)
    except KeyboardInterrupt:
        if not quiet:
            print("\nServer stopped.", file=sys.stderr)
    finally:
        daemon_json.unlink(missing_ok=True)

    return 0
```

Add `import atexit, os` at the top of the function if not already present (check existing imports).

- [ ] **Step 3: Run all viewer-related tests**

Run: `pytest tests/mcp/test_daemon_lifecycle.py tests/commands/test_engine_graph_source.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/elspais/commands/viewer.py tests/mcp/test_daemon_lifecycle.py
git commit -m "feat: viewer writes daemon.json on start, removes on stop"
```

---

### Task 4: Remove hardcoded 5001 probe from `_engine.py`

**Files:**
- Modify: `src/elspais/commands/_engine.py:63-141`
- Modify: `src/elspais/commands/_daemon_client.py:14`
- Modify: `src/elspais/mcp/daemon.py:21`
- Modify: `tests/commands/test_engine_graph_source.py`

- [ ] **Step 1: Update engine tests for new routing**

Replace `tests/commands/test_engine_graph_source.py`:

```python
# Verifies: REQ-d00010

"""Tests that _engine.call injects graph_source metadata."""

from unittest.mock import patch


def test_engine_call_local_includes_graph_source():
    """Local fallback should tag result with graph_source='local'."""
    from elspais.commands._engine import call

    def fake_compute(graph, config, params):
        return {"healthy": True, "checks": []}

    with patch(
        "elspais.commands._engine._ensure_local_graph",
        return_value=(object(), {}),
    ):
        result = call("/api/run/checks", {}, fake_compute, skip_daemon=True)

    assert "graph_source" in result
    assert result["graph_source"]["type"] == "local"


def test_engine_call_daemon_includes_graph_source():
    """Daemon path should tag result with graph_source including port."""
    from elspais.commands._engine import call

    daemon_result = {"healthy": True, "checks": []}

    with patch(
        "elspais.commands._engine._try_daemon",
        return_value=(daemon_result, {"type": "daemon", "port": 35121}),
    ):
        result = call(
            "/api/run/checks", {}, lambda g, c, p: {}, skip_daemon=False
        )

    assert "graph_source" in result
    assert result["graph_source"]["type"] == "daemon"
    assert result["graph_source"]["port"] == 35121


def test_engine_call_viewer_includes_graph_source():
    """Viewer path should tag result with graph_source type='viewer'."""
    from elspais.commands._engine import call

    viewer_result = {"healthy": True, "checks": []}

    # Viewer now goes through daemon.json like everything else —
    # the type comes from daemon.json "type" field
    with patch(
        "elspais.commands._engine._try_daemon",
        return_value=(viewer_result, {"type": "viewer", "port": 5001}),
    ):
        result = call(
            "/api/run/checks", {}, lambda g, c, p: {}, skip_daemon=False
        )

    assert result["graph_source"]["type"] == "viewer"
```

- [ ] **Step 2: Rewrite `_try_daemon()` and `_build_daemon_source()`**

**Key change in `_build_daemon_source`:** The current version hardcodes `"type": "daemon"`. The new version reads `type` from `daemon.json` via `info.get("type", "daemon")`. This is what makes the viewer/daemon distinction work in `graph_source` metadata.

Replace `src/elspais/commands/_engine.py` lines 63-141 with:

```python
def _build_daemon_source(port: int) -> dict[str, Any]:
    """Build graph_source dict for a server result."""
    source: dict[str, Any] = {"port": port}
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import get_daemon_info

        repo_root = find_git_root()
        if repo_root:
            info = get_daemon_info(repo_root)
            if info:
                source["type"] = info.get("type", "daemon")
                source["started_at"] = info.get("started_at", "")
            else:
                source["type"] = "daemon"
        else:
            source["type"] = "daemon"
    except Exception:
        source["type"] = "daemon"
    return source


def _try_daemon(
    endpoint: str,
    params: dict[str, str],
) -> tuple[dict, dict[str, Any]] | None:
    """Try to serve a request via a running server (viewer or daemon).

    Routing is entirely through daemon.json — no hardcoded ports.
    Both the viewer and headless daemon write daemon.json on startup.

    Decision tree:
      1. find_git_root() — if None, can't route
      2. Read daemon.json for this project — get port
      3. If found, try HTTP call
      4. If not found, auto-start daemon via ensure_daemon()
      5. If auto-start disabled (cli_ttl=0), return None → local fallback

    Returns (result_dict, source_info) or None.
    """
    from elspais.commands._daemon_client import _get_daemon_port, _try_port
    from elspais.config import find_git_root

    repo_root = find_git_root()
    if repo_root is None:
        return None

    # 1. Try existing server (viewer or daemon — both use daemon.json)
    port = _get_daemon_port()
    if port:
        result = _try_port(port, endpoint, params, "GET")
        if result is not None:
            source = _build_daemon_source(port)
            return result, source

    # 2. Auto-start daemon if allowed
    try:
        from elspais.mcp.daemon import ensure_daemon

        port = ensure_daemon(repo_root)
        result = _try_port(port, endpoint, params, "GET")
        if result is not None:
            source = _build_daemon_source(port)
            return result, source
    except Exception:
        pass

    return None
```

Also delete `_server_version_ok()` (lines 80-95) — no longer needed. Version checking is already in `ensure_daemon()`.

Update the module docstring (lines 4-9) to reflect the new decision tree.

- [ ] **Step 3: Remove `_VIEWER_PORT` from `_daemon_client.py` and `daemon.py`**

In `src/elspais/commands/_daemon_client.py` line 14, delete:
```python
_VIEWER_PORT = 5001
```

In `src/elspais/mcp/daemon.py` line 21, delete:
```python
_VIEWER_PORT = 5001
```

And remove the empty "Viewer detection" comment block at lines 87-88 of `daemon.py`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/commands/test_engine_graph_source.py tests/mcp/test_daemon_lifecycle.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspais/commands/_engine.py src/elspais/commands/_daemon_client.py src/elspais/mcp/daemon.py tests/commands/test_engine_graph_source.py
git commit -m "fix: remove hardcoded 5001 probe, route all servers through daemon.json"
```

---

### Task 5: `pytest_configure` git env isolation

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Replace module-level env pops with `pytest_configure`**

In `tests/conftest.py`, replace the current git isolation block (lines 16-23):

```python
# ── Git isolation ────────────────────────────────────────────────────────
# Git sets GIT_DIR when running hooks (e.g., pre-push).  If pytest is
# invoked from a hook, every subprocess.run(["git", ...], cwd=tmp_path)
# will silently operate on the HOOK's repo instead of the temp directory,
# because GIT_DIR overrides cwd.  Strip it once at session start so all
# tests get a clean environment.
os.environ.pop("GIT_DIR", None)
os.environ.pop("GIT_WORK_TREE", None)
```

with:

```python
def pytest_configure(config):
    """Strip git env vars before any test collection or coverage forking.

    Git sets GIT_DIR when running hooks (pre-commit, pre-push).  This
    overrides cwd in subprocess calls, causing test git operations to
    target the hook's repo instead of temp directories.

    GIT_CEILING_DIRECTORIES=/ prevents git from discovering a parent
    .git above a test's working directory — defense-in-depth against
    accidental upward repo discovery.

    Using pytest_configure (not module-level code) ensures this runs
    before pytest-cov forks coverage subprocesses.
    """
    os.environ.pop("GIT_DIR", None)
    os.environ.pop("GIT_WORK_TREE", None)
    os.environ["GIT_CEILING_DIRECTORIES"] = "/"
```

- [ ] **Step 2: Run unit tests with simulated hook env**

Run: `GIT_DIR=/tmp/fake pytest tests/core/test_git.py -q --cov=src/elspais --cov-report=`
Expected: All 83 pass, no contamination.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "fix: use pytest_configure for git env isolation with GIT_CEILING_DIRECTORIES"
```

---

### Task 6: Restore daemon usage in e2e tests

**Files:**
- Modify: `tests/e2e/helpers.py:341`
- Modify: `tests/e2e/conftest.py`

- [ ] **Step 1: Change `cli_ttl` from 0 to 2**

In `tests/e2e/helpers.py` line 341, change:
```python
        "cli_ttl": 0,
```
to:
```python
        "cli_ttl": 2,
```

- [ ] **Step 2: Add `_cleanup_daemon` autouse fixture**

Add to `tests/e2e/conftest.py` after the existing fixtures:

```python
@pytest.fixture(autouse=True)
def _cleanup_daemon(tmp_path):
    """Stop any daemon started during the test.

    E2e tests may auto-start per-project daemons in temp directories.
    This fixture ensures they are cleaned up to prevent zombie processes.
    """
    yield
    try:
        from elspais.mcp.daemon import stop_daemon

        for daemon_json in tmp_path.rglob(".elspais/daemon.json"):
            try:
                stop_daemon(daemon_json.parent.parent)
            except Exception:
                pass
    except Exception:
        pass
```

- [ ] **Step 3: Run e2e tests**

Run: `pytest tests/e2e/test_cli_commands.py -v -x -m e2e`
Expected: Tests pass, using real daemons.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/helpers.py tests/e2e/conftest.py
git commit -m "feat: restore daemon usage in e2e tests (cli_ttl=2)"
```

---

### Task 7: Full test suite verification and cleanup

**Files:**
- Modify: `KNOWN_ISSUES.md:28`
- Modify: `pyproject.toml:7`

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -m "" -q --tb=short`
Expected: All tests pass.

- [ ] **Step 2: Check for daemon leaks**

Run: `ps aux | grep "elspais.*mcp.*serve" | grep -v grep`
Expected: No leftover daemon processes.

- [ ] **Step 3: Run unit tests with simulated hook env + coverage**

Run: `GIT_DIR=/tmp/fake pytest tests/ -m "not e2e and not browser" -q --cov=src/elspais --cov-report=`
Expected: All pass — validates the `pytest_configure` fix works with `--cov`.

- [ ] **Step 4: Mark KNOWN_ISSUES as done, bump version**

In `KNOWN_ISSUES.md` line 28, change `[ ]` to `[x]`.

Bump patch version in `pyproject.toml`.

- [ ] **Step 5: Commit**

```bash
git add KNOWN_ISSUES.md pyproject.toml
git commit -m "docs: mark daemon e2e isolation as resolved, bump version"
```
