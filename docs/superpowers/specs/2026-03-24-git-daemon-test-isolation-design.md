# Git & Daemon Test Isolation

**Date:** 2026-03-24
**Status:** Draft
**Supersedes:** `2026-03-24-daemon-e2e-isolation-design.md`

## Problem

Tests that involve git subprocess calls are unsafe when run inside git hooks (pre-commit, pre-push) or alongside coverage instrumentation (`--cov`). Git sets `GIT_DIR` in hook contexts, which overrides `cwd` in subprocess calls, causing test git operations to silently target the host worktree instead of temp directories. This has caused: stray commits, branch switches, local config contamination, and orphaned files.

Separately, the CLI engine's `_try_daemon()` hardcodes a probe to port 5001 (viewer) with only a version check — no project identity. A viewer running for the main repo intercepts CLI commands from any project, including e2e test temp directories. The workaround (`cli_ttl=0`) disables daemon usage in tests entirely, losing coverage of daemon startup, HTTP transport, and version checks.

These are the same problem: the system lacks a single, reliable mechanism for "which project am I in, and which server should I talk to?"

## Design

### 1. Viewer writes `daemon.json`

When `elspais view` starts, it writes `<repo_root>/.elspais/daemon.json` with the same schema the headless daemon uses:

```json
{
  "pid": 12345,
  "port": 5001,
  "repo_root": "/home/user/project",
  "version": "0.111.97",
  "config_hash": "abc123...",
  "started_at": "2026-03-24T12:00:00",
  "type": "viewer"
}
```

The `type` field ("viewer" or "daemon") allows `graph_source` metadata to distinguish them.

**Viewer cleanup:** The viewer wraps its server loop in `try/finally` to remove `daemon.json` on exit. An `atexit.register` handler provides a safety net for unhandled exits. If the viewer crashes without cleanup, `get_daemon_info()` already detects stale files via `os.kill(pid, 0)` and unlinks them.

**Viewer `config_hash`:** The viewer computes and writes `config_hash` using the existing `compute_config_hash()` from `daemon.py`. This ensures `ensure_daemon()` correctly detects config staleness whether the active server is a viewer or daemon.

**Viewer port is not always 5001:** The viewer has port conflict resolution logic — it may end up on a different port. Writing `daemon.json` with the actual port solves this existing port-discovery problem.

**No orphan servers:** Before any server writes `daemon.json`, it must stop the process pointed to by the existing `daemon.json` (if any). Currently `start_daemon()` unlinks `daemon.json` without killing the old process — this creates ghost daemons. Fix: `start_daemon()` calls `stop_daemon()` before unlinking. The viewer startup does the same. This guarantees: if `daemon.json` exists, it points to the only server for this project; if it doesn't exist, no server is running.

**Last writer wins:** If both a viewer and daemon could run for the same project, the "no orphan servers" rule prevents it — writing `daemon.json` kills whatever was there before. The viewer naturally takes precedence because it starts after the daemon (user launches it manually). When the viewer stops, it removes `daemon.json`, and the next CLI command auto-starts a fresh daemon.

### 2. Remove hardcoded viewer probe from `_engine.py`

`_try_daemon()` currently has three steps: (1) probe port 5001, (2) read `daemon.json`, (3) auto-start. Step 1 is the bug — it bypasses per-project routing.

Replace with a single path:

```
1. repo_root = find_git_root()  -- if None, return None
2. port = _get_daemon_port()    -- reads daemon.json for THIS project
3. If port found and server alive, use it
4. If no port, auto-start via ensure_daemon(repo_root)
5. Fallback to local build
```

No hardcoded ports. No special viewer path. The `daemon.json` file is the single source of truth for "what server is running for this project." Both viewer and daemon go through the same routing.

Remove `_VIEWER_PORT = 5001` from `_engine.py`, `_daemon_client.py`, and `daemon.py` (the latter two are dead declarations — only `_engine.py` uses it functionally).

### 3. Git env isolation

Two layers, applied at the earliest possible point:

**Layer 1 — Shell hooks:** `unset GIT_DIR GIT_WORK_TREE` at the top of `.githooks/pre-commit` and `.githooks/pre-push`, before any commands run. Already committed.

**Layer 2 — `pytest_configure`:** In `tests/conftest.py`, implement a `pytest_configure` hook (runs before coverage subprocess forking) that:
- Strips `GIT_DIR` and `GIT_WORK_TREE` from `os.environ`
- Sets `GIT_CEILING_DIRECTORIES=/`

`GIT_CEILING_DIRECTORIES=/` prevents git from discovering a parent `.git` above a test's working directory. Combined with `GIT_DIR` stripping, this covers both explicit env override and accidental upward discovery.

Replace the current module-level `os.environ.pop()` calls with the `pytest_configure` hook to ensure the cleanup happens before any coverage or collection machinery.

### 4. E2e daemon usage

In `tests/e2e/helpers.py` `base_config()`, change `"cli_ttl": 0` to `"cli_ttl": 2` (2-minute idle timeout). E2e subprocesses auto-start per-project daemons naturally. The per-project `daemon.json` routing means they can never connect to the wrong project's server.

Add a `_cleanup_daemon` autouse fixture in `tests/e2e/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _cleanup_daemon(tmp_path):
    """Stop any daemon started during the test."""
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

## Files Changed

| File | Change |
|------|--------|
| `src/elspais/commands/viewer.py` | Write `daemon.json` on start, remove on stop |
| `src/elspais/commands/_engine.py` | Remove hardcoded 5001 probe; single `daemon.json` routing path |
| `src/elspais/commands/_daemon_client.py` | Remove `_VIEWER_PORT` |
| `src/elspais/mcp/daemon.py` | Remove `_VIEWER_PORT`; add `type` field to `daemon.json` schema; `start_daemon()` calls `stop_daemon()` before overwriting |
| `src/elspais/commands/args.py` | No change needed (5001 stays as default CLI arg) |
| `tests/conftest.py` | `pytest_configure` hook: strip `GIT_DIR`, `GIT_WORK_TREE`, set `GIT_CEILING_DIRECTORIES=/` |
| `tests/e2e/helpers.py` | `cli_ttl: 0` → `cli_ttl: 2` |
| `tests/e2e/conftest.py` | Add `_cleanup_daemon` autouse fixture |
| `.githooks/pre-commit` | `unset GIT_DIR GIT_WORK_TREE` (already committed) |
| `.githooks/pre-push` | `unset GIT_DIR GIT_WORK_TREE` (already committed) |
| `tests/commands/test_engine_graph_source.py` | Update tests — remove viewer-on-5001 mock, test `daemon.json` routing |
| `KNOWN_ISSUES.md` | Mark "restore daemon usage in e2e tests" as done |

## Risks

- **Viewer crash without cleanup.** If the viewer crashes without removing `daemon.json`, the stale file will point to a dead process. `get_daemon_info()` already handles this — it checks `os.kill(pid, 0)` and unlinks stale files. The `atexit` handler provides an additional safety net. No new risk.
- **Last-writer-wins race.** If a user starts both viewer and daemon simultaneously, `daemon.json` could thrash. In practice this doesn't happen — the viewer is interactive and the daemon is auto-started by CLI commands. The viewer's write on startup is deterministic.
- **E2e test latency.** Daemon startup adds ~1-2s per test that runs CLI commands. Subsequent commands in the same test reuse the daemon. Net: slower per-test, but exercises real code paths.
- **`GIT_CEILING_DIRECTORIES=/`** could break a test that legitimately needs to discover a parent repo. No current tests do this — they all create self-contained repos in `tmp_path`.

## Non-Goals

- Changing the `daemon.json` schema beyond adding `type`
- Supporting multiple simultaneous servers per project
- Parallelizing e2e tests (orthogonal)
