"""Daemon management for persistent MCP server.

Provides lifecycle management (start/stop/ensure) for a background MCP
server process, and lightweight clients for querying a running server
(viewer or MCP daemon) from the CLI.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

_DEFAULT_TTL = 30  # minutes

# Env var carrying the spawner's PID into the detached daemon process
# (start_new_session=True reparents the daemon to PID 1, so the parent
# chain cannot identify the spawner after the fact).
_SPAWNER_ENV = "_ELSPAIS_SPAWNER_PID"

# Public override: a session/IDE can declare itself the spawner so that
# implicitly started daemons are reaped when it exits.
SPAWNER_OVERRIDE_ENV = "ELSPAIS_SPAWNER_PID"


def _iter_proc_ancestors(pid: int | None = None):
    """Yield (pid, comm) for each ancestor of ``pid`` (exclusive), via /proc.

    Best effort: stops silently on any read error or at PID 1.
    """
    if pid is None:
        pid = os.getpid()
    for _ in range(64):  # depth bound against /proc anomalies
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            # comm may contain spaces/parens; fields after the last ')'
            # are position-stable.
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return
        if ppid <= 1:
            return
        yield ppid, _read_comm(ppid) or ""
        pid = ppid


def _read_comm(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except OSError:
        return None


def _session_leader_has_tty(sid: int) -> bool:
    """True if the session leader has a controlling terminal (tty_nr != 0)."""
    try:
        stat = Path(f"/proc/{sid}/stat").read_text()
        tty_nr = int(stat.rsplit(")", 1)[1].split()[4])
        return tty_nr != 0
    except (OSError, ValueError, IndexError):
        return False


# Implements: REQ-o00074-A, REQ-o00074-D
def resolve_spawner_pid() -> int | None:
    """Identify the session on whose behalf a daemon is being auto-started.

    Resolution order:
      1. ``ELSPAIS_SPAWNER_PID`` env var — explicit declaration by the
         session/IDE (also the deterministic hook for tests).
      2. Inside a Claude Code session (``CLAUDECODE`` env set): the
         nearest ancestor process named ``claude`` (the session process;
         intermediate tool shells are ephemeral).
      3. The controlling-terminal session leader (``os.getsid(0)``), if
         it is a real interactive session (has a tty). An interactive
         shell qualifies; batch/CI/tool shells do not.

    Returns None when no session identity can be established — the
    daemon then keeps its TTL-only lifetime (current behavior).
    """
    override = os.environ.get(SPAWNER_OVERRIDE_ENV)
    if override:
        try:
            pid = int(override)
        except ValueError:
            pid = 0
        return pid if pid > 1 else None

    if os.environ.get("CLAUDECODE"):
        for pid, comm in _iter_proc_ancestors():
            if comm == "claude":
                return pid

    try:
        sid = os.getsid(0)
    except OSError:
        return None
    if sid > 1 and sid != os.getpid() and _session_leader_has_tty(sid):
        return sid
    return None


def compute_config_hash(config_path: Path) -> str:
    """Compute a hash of all config files that affect the graph.

    Hashes the main .elspais.toml, .elspais.local.toml (if present),
    and any associate repo .elspais.toml files referenced in [associates].

    Returns:
        16-char hex digest (first 8 bytes of SHA-256).
    """
    import hashlib

    h = hashlib.sha256()

    # Main config
    if config_path.is_file():
        h.update(config_path.read_bytes())

    # Local overrides
    local_path = config_path.parent / ".elspais.local.toml"
    if local_path.is_file():
        h.update(local_path.read_bytes())

    # Associate configs: parse merged config to find associate paths
    try:
        from elspais.config import get_associates_config, get_config

        merged = get_config(config_path=config_path)
        repo_root = config_path.parent
        associates = get_associates_config(merged, repo_root=repo_root)
        for _name, info in sorted(associates.items()):
            assoc_path = (repo_root / info["path"]).resolve()
            assoc_toml = assoc_path / ".elspais.toml"
            if assoc_toml.is_file():
                h.update(assoc_toml.read_bytes())
            assoc_local = assoc_path / ".elspais.local.toml"
            if assoc_local.is_file():
                h.update(assoc_local.read_bytes())
    except Exception:
        pass  # Best effort - don't fail daemon start on parse errors

    return h.hexdigest()[:16]


def get_cli_ttl(repo_root: Path | None = None) -> int:
    """Read cli_ttl from .elspais.toml config.

    Returns:
        >0: auto-start daemon with this TTL in minutes
         0: never auto-launch daemon (manual only)
        <0: auto-start daemon that never times out
    Default: 30 (minutes).
    """
    if repo_root is None:
        return _DEFAULT_TTL
    try:
        from elspais.config import get_config

        config = get_config(start_path=repo_root, quiet=True)
        return int(config.get("cli_ttl", _DEFAULT_TTL))
    except Exception:
        return _DEFAULT_TTL


def write_daemon_json(
    repo_root: Path,
    pid: int,
    port: int,
    server_type: str = "daemon",
    spawner_pid: int | None = None,
) -> Path:
    """Write daemon.json state file for a running server.

    Both the headless daemon and the viewer use this to register
    themselves as the active server for a project.

    Args:
        repo_root: Project root directory.
        pid: Process ID of the server.
        port: Port the server is listening on.
        server_type: "daemon" or "viewer".
        spawner_pid: PID of the session the daemon was implicitly
            spawned for, or None for explicitly started servers
            (TTL-only lifetime).

    Returns:
        Path to the written daemon.json file.
    """
    from elspais import __version__

    daemon_json = _daemon_json_path(repo_root)
    daemon_json.parent.mkdir(parents=True, exist_ok=True)

    config_path = repo_root / ".elspais.toml"
    config_hash = compute_config_hash(config_path) if config_path.is_file() else ""

    info: dict = {
        "pid": pid,
        "port": port,
        "repo_root": str(repo_root),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "version": __version__,
        "config_hash": config_hash,
        "type": server_type,
    }
    # Implements: REQ-o00074-B, REQ-o00074-C
    if spawner_pid is not None:
        info["spawner_pid"] = spawner_pid
    daemon_json.write_text(json.dumps(info))
    return daemon_json


# Implements: REQ-p00004-J
def refresh_daemon_config_hash(repo_root: Path) -> None:
    """Rewrite daemon.json's config_hash from the current config on disk.

    Called by a running server after it rebuilds its graph with freshly
    re-read config, so CLI staleness checks (_config_hash_stale) don't
    restart a server that is already up to date.
    """
    path = _daemon_json_path(repo_root)
    if not path.exists():
        return
    try:
        info = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return
    config_path = repo_root / ".elspais.toml"
    info["config_hash"] = compute_config_hash(config_path) if config_path.is_file() else ""
    try:
        path.write_text(json.dumps(info))
    except OSError:
        pass  # Best effort — a failed refresh only risks an extra restart


# ── Daemon lifecycle ─────────────────────────────────────────────────────


def _daemon_dir(repo_root: Path) -> Path:
    return repo_root / ".elspais"


def _daemon_json_path(repo_root: Path) -> Path:
    return _daemon_dir(repo_root) / "daemon.json"


def get_daemon_info(repo_root: Path) -> dict | None:
    """Read daemon.json and verify the process is alive.

    Returns dict with pid/port/repo_root/started_at, or None if
    the daemon is not running or the state file is stale.
    """
    path = _daemon_json_path(repo_root)
    if not path.exists():
        return None
    try:
        info = json.loads(path.read_text())
        pid = info["pid"]
        os.kill(pid, 0)  # check alive
        return info
    except (json.JSONDecodeError, KeyError, OSError):
        path.unlink(missing_ok=True)
        return None


def start_daemon(
    repo_root: Path,
    ttl_minutes: int = _DEFAULT_TTL,
    spawner_pid: int | None = None,
) -> int:
    """Start a background MCP server and return its port.

    Spawns ``elspais mcp serve --transport streamable-http --port 0
    --ttl <ttl>`` as a detached process.  The server writes daemon.json
    after binding; this function polls for it.

    Args:
        ttl_minutes: >0 = exit after N minutes idle.
                     <0 = run forever (no timeout).
                      0 = should not be called (caller should check).
        spawner_pid: PID of the session this daemon serves. When set,
            the daemon watches it and shuts down after the session
            exits. None (explicit starts) keeps TTL-only lifetime.
    """
    # Stop any existing server before overwriting daemon.json.
    # Without this, the old server becomes an undiscoverable orphan.
    stop_daemon(repo_root)

    daemon_json = _daemon_json_path(repo_root)
    daemon_json.parent.mkdir(parents=True, exist_ok=True)

    log_path = _daemon_dir(repo_root) / "daemon.log"

    # Negative TTL → run forever (pass 0 to mcp serve, which means no timeout)
    serve_ttl = max(ttl_minutes, 0)

    cmd = [
        sys.executable,
        "-m",
        "elspais",
        "mcp",
        "serve",
        "--transport",
        "streamable-http",
        "--port",
        "0",
        "--ttl",
        str(serve_ttl),
    ]

    # Implements: REQ-o00074-A, REQ-o00074-C
    child_env = {**os.environ, "_ELSPAIS_DAEMON_JSON": str(daemon_json)}
    if spawner_pid is not None:
        child_env[_SPAWNER_ENV] = str(spawner_pid)
    else:
        child_env.pop(_SPAWNER_ENV, None)

    with open(log_path, "w") as log_file:
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(repo_root),
            env=child_env,
        )

    # Poll for daemon.json, then verify HTTP readiness.
    # daemon.json is written before uvicorn binds, so we must also check
    # that the server actually responds to HTTP requests.
    deadline = time.time() + 15
    port = None
    while time.time() < deadline:
        info = get_daemon_info(repo_root)
        if info and "port" in info:
            port = info["port"]
            break
        time.sleep(0.2)

    if port is None:
        raise RuntimeError("Daemon failed to start (timed out waiting for daemon.json)")

    # Now poll until the server is actually responding
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/check-freshness", timeout=2):
                return port
        except (URLError, OSError):
            time.sleep(0.2)

    raise RuntimeError("Daemon started but not responding to HTTP")


def stop_daemon(repo_root: Path) -> bool:
    """Stop a running daemon. Returns True if stopped."""
    info = get_daemon_info(repo_root)
    if info is None:
        return False
    try:
        os.kill(info["pid"], signal.SIGTERM)
    except OSError:
        pass
    _daemon_json_path(repo_root).unlink(missing_ok=True)
    return True


def _config_hash_stale(info: dict, repo_root: Path) -> bool:
    """Check if the daemon's config hash is stale.

    Returns True if the config has changed since the daemon started.
    Returns False (keep daemon) if there is no hash to compare.
    """
    daemon_hash = info.get("config_hash")
    if not daemon_hash:
        return False  # Old daemon without hash, or hash computation failed
    config_path = repo_root / ".elspais.toml"
    if not config_path.is_file():
        return False
    return compute_config_hash(config_path) != daemon_hash


def get_daemon_mutation_count(info: dict) -> int | None:
    """Query the daemon's unsaved-mutation count.

    Returns int on success, or None if the daemon can't be reached / the
    endpoint is missing (treated as "unknown", not zero).
    """
    import json as _json

    port = info.get("port")
    if not port:
        return None
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/dirty", timeout=3) as resp:
            data = _json.loads(resp.read().decode())
            count = data.get("mutation_count")
            if isinstance(count, int):
                return count
    except (URLError, OSError, ValueError):
        return None
    return None


def save_daemon_mutations(info: dict) -> dict:
    """Ask the daemon to persist pending mutations to disk.

    Returns the daemon's JSON response, or ``{"success": False, "error": "..."}``
    if the call fails.
    """
    import json as _json
    from urllib.request import Request as _Request

    port = info.get("port")
    if not port:
        return {"success": False, "error": "daemon has no port"}
    # REQ-o00062-N: a save must name the history it persists. Read the
    # current tip first; the guard rejects if it moves in between.
    tip = ""
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/dirty", timeout=5) as resp:
            tip = _json.loads(resp.read().decode()).get("tip") or ""
    except (URLError, OSError, ValueError):
        pass  # "" means "nothing pending"; the guard rejects it if not true
    body = _json.dumps({"if_tip_mutation_id": tip}).encode()
    req = _Request(
        f"http://127.0.0.1:{port}/api/save",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return _json.loads(resp.read().decode())
    except URLError as e:
        return {"success": False, "error": f"daemon unreachable: {e}"}
    except (OSError, ValueError) as e:
        return {"success": False, "error": str(e)}


def restart_daemon(
    repo_root: Path,
    force: bool = False,
    persist: bool = False,
    ttl_minutes: int | None = None,
) -> dict:
    """Stop and restart the daemon, picking up any config file changes.

    Hard restart only — kills the existing process and spawns a fresh one,
    which re-reads ``.elspais.toml`` during startup.

    In-memory mutation safety:
        - If the daemon reports 0 unsaved mutations: restart proceeds.
        - Otherwise, default behavior is to refuse with an error listing
          the count. Caller must opt in via ``force`` (discard) or
          ``persist`` (save first). These flags are mutually exclusive.

    Returns:
        Dict with ``success`` (bool) and ``message`` (str). On successful
        restart, also includes ``port``. On refusal due to unsaved
        mutations, includes ``mutation_count`` and an ``error`` key.
    """
    if force and persist:
        return {
            "success": False,
            "error": "--force and --persist are mutually exclusive",
        }

    info = get_daemon_info(repo_root)
    if info is None:
        # No daemon running — just start one.
        if ttl_minutes is None:
            ttl_minutes = get_cli_ttl(repo_root)
        if ttl_minutes == 0:
            return {
                "success": False,
                "error": "Daemon auto-launch disabled (cli_ttl=0)",
            }
        port = start_daemon(repo_root, ttl_minutes=ttl_minutes)
        return {
            "success": True,
            "message": "No daemon was running; started a fresh one.",
            "port": port,
        }

    # Daemon is running — check for unsaved work.
    count = get_daemon_mutation_count(info)
    if count and count > 0:
        if persist:
            save_result = save_daemon_mutations(info)
            if not save_result.get("success"):
                return {
                    "success": False,
                    "error": (
                        f"Cannot restart — persist requested but save failed: "
                        f"{save_result.get('error', save_result)}"
                    ),
                    "mutation_count": count,
                }
        elif not force:
            return {
                "success": False,
                "error": (
                    f"Cannot restart — daemon has {count} unsaved in-memory mutation(s). "
                    "Use --force to discard them, or --persist to save first."
                ),
                "mutation_count": count,
            }
        # force: fall through and kill anyway

    # At this point we're committed to restart.
    stop_daemon(repo_root)

    if ttl_minutes is None:
        ttl_minutes = get_cli_ttl(repo_root)
    if ttl_minutes == 0:
        return {
            "success": True,
            "message": "Daemon stopped (cli_ttl=0, not restarting).",
        }
    port = start_daemon(repo_root, ttl_minutes=ttl_minutes)
    return {
        "success": True,
        "message": f"Daemon restarted on port {port}.",
        "port": port,
    }


def ensure_daemon(repo_root: Path, ttl_minutes: int | None = None) -> int:
    """Return port of a running daemon, starting one if needed.

    Reads ``cli_ttl`` from config if ttl_minutes is not provided.
    Raises RuntimeError if cli_ttl=0 (daemon disabled) and no daemon running.
    Restarts the daemon if its version or config hash doesn't match.
    """
    info = get_daemon_info(repo_root)
    if info:
        # Version check: restart if daemon is from a different elspais version
        from elspais import __version__

        daemon_version = info.get("version")
        if daemon_version and daemon_version != __version__:
            stop_daemon(repo_root)
            # Fall through to start a fresh daemon
        elif _config_hash_stale(info, repo_root):
            stop_daemon(repo_root)
            # Fall through to start a fresh daemon
        else:
            return info["port"]

    if ttl_minutes is None:
        ttl_minutes = get_cli_ttl(repo_root)

    # cli_ttl=0 means never auto-launch
    if ttl_minutes == 0:
        raise RuntimeError("Daemon auto-launch disabled (cli_ttl=0)")

    # Implicit spawn on behalf of a CLI/session: tie the daemon's
    # lifetime to that session so it cannot outlive it. Explicit starts
    # (elspais daemon restart, manual mcp serve, viewer) do not pass a
    # spawner and keep TTL-only behavior.
    return start_daemon(
        repo_root,
        ttl_minutes=ttl_minutes,
        spawner_pid=resolve_spawner_pid(),
    )
