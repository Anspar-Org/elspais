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
_VIEWER_PORT = 5001


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


# ── Viewer detection (fast path) ─────────────────────────────────────────


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


def start_daemon(repo_root: Path, ttl_minutes: int = _DEFAULT_TTL) -> int:
    """Start a background MCP server and return its port.

    Spawns ``elspais mcp serve --transport streamable-http --port 0
    --ttl <ttl>`` as a detached process.  The server writes daemon.json
    after binding; this function polls for it.

    Args:
        ttl_minutes: >0 = exit after N minutes idle.
                     <0 = run forever (no timeout).
                      0 = should not be called (caller should check).
    """
    daemon_json = _daemon_json_path(repo_root)
    daemon_json.parent.mkdir(parents=True, exist_ok=True)
    daemon_json.unlink(missing_ok=True)

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

    with open(log_path, "w") as log_file:
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(repo_root),
            env={**os.environ, "_ELSPAIS_DAEMON_JSON": str(daemon_json)},
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

    return start_daemon(repo_root, ttl_minutes=ttl_minutes)
