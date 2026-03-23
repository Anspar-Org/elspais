# Daemon-First Engine Refactor

## Problem

Seven CLI commands independently implement a daemon-first pattern with duplicated
decision logic, param building, graph construction, and result deserialization.
This caused three bugs:

1. `analysis_cmd` weight validation only runs on the local path (daemon bypasses it)
2. `daemon.json` is written before uvicorn binds — first CLI call races and falls back to local
3. `analysis_cmd` missing the `spec_dir` skip guard all other commands have

## Design

### Engine abstraction (`commands/_engine.py`)

Single function encapsulating the daemon-vs-local decision:

```python
def call(
    endpoint: str,
    params: dict[str, str],
    compute_fn: Callable[[FederatedGraph, dict, dict[str, str]], dict],
    skip_daemon: bool = False,
) -> dict:
```

Decision tree:
- `skip_daemon` true --> local path
- Try viewer (port 5001), then daemon (from daemon.json, version-checked)
- If not found and `cli_ttl != 0`: auto-start daemon, poll HTTP (not just daemon.json) for readiness
- Fallback: build graph locally, call `compute_fn(graph, config, params)`

Both paths return the same `dict`.

### Command pattern

Each command's `run()` becomes:

```python
def run(args):
    error = validate(args)          # step 1: always
    if error: return error
    params = build_params(args)     # step 2: args -> dict
    skip = bool(getattr(args, "spec_dir", None))
    data = engine.call(             # step 3: transparent
        "/api/run/X", params, compute_X, skip_daemon=skip
    )
    render(data, args)              # step 4: format + output
    return exit_code(data)
```

### Compute functions

Uniform signature: `compute_fn(graph, config, params) -> dict`.
Most already exist: `_collect_coverage`, `collect_gaps`, `collect_unlinked`, `_search`.
Extract from duplicated code: `compute_checks`, `compute_analysis`, `compute_trace`.

### Server routes

`routes_api.py` endpoints shrink to: extract query params, call compute function, JSONResponse.
They import the same compute functions the CLI uses.

### daemon.json race fix

After finding daemon.json, poll the actual HTTP endpoint before returning the port:

```python
while time.time() < deadline:
    if _try_port(port, "/api/check-freshness"):
        return port
    time.sleep(0.2)
```

### `_daemon_client.py`

Loses decision logic (moves to `_engine.py`). Keeps HTTP plumbing only.

## Migration order

1. `summary.py` (simplest, `_collect_coverage` already matches)
2. `gaps.py`
3. `unlinked.py`
4. `search_cmd.py`
5. `analysis_cmd.py`
6. `trace.py`
7. `health.py` (most complex, last)

Each command migrates independently. Tests pass throughout.
