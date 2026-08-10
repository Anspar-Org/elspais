"""Daemon management for persistent MCP server.

Provides lifecycle management (start/stop/ensure) for a background MCP
server process, and lightweight clients for querying a running server
(viewer or MCP daemon) from the CLI.
"""

from __future__ import annotations

import enum
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

_DEFAULT_TTL = 30  # minutes

# Env var carrying the client's PID into the detached daemon process
# (start_new_session=True reparents the daemon to PID 1, so the parent
# chain cannot identify the client after the fact).
_CLIENT_ENV = "_ELSPAIS_CLIENT_PID"

# Public override: a session/IDE can declare itself the client so that
# implicitly started daemons are reaped when it exits.
CLIENT_OVERRIDE_ENV = "ELSPAIS_CLIENT_PID"

# Former name of the public override, still honoured so existing callers
# keep working.
_LEGACY_OVERRIDE_ENV = "ELSPAIS_SPAWNER_PID"

# Sentinel returned by ``_declared_client_pid`` for a declaration that is
# present but not a usable handle (unparsable, non-positive, or already
# dead).
_UNUSABLE = "unusable"


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


def _declared_client_pid() -> int | str | None:
    """Read the caller's declared client handle.

    Three distinct answers: the pid; ``_UNUSABLE`` when a declaration is
    present but is not a handle whose disappearance can be observed; and
    None when nothing is declared. A declaration that could not be used is
    a fact its author needs told (REQ-o00074-N), and an absent one is not,
    so the two cannot share an answer.

    A declared pid that is already dead is unusable rather than usable.
    Recording it would bind the daemon to a process that has gone, so the
    daemon would reap itself at its next check — an outcome the caller
    would read as the daemon failing rather than as its declaration being
    stale.

    The former variable name is read so callers that set it keep working.
    """
    for name in (CLIENT_OVERRIDE_ENV, _LEGACY_OVERRIDE_ENV):
        raw = os.environ.get(name)
        if not raw:
            continue
        try:
            pid = int(raw)
        except ValueError:
            return _UNUSABLE
        if pid <= 1:
            return _UNUSABLE
        try:
            os.kill(pid, 0)
        except OSError:
            return _UNUSABLE
        return pid
    return None


# Implements: REQ-o00074-A, REQ-o00074-D
def resolve_client_pid() -> int | None:
    """Identify the session on whose behalf a daemon is being auto-started.

    Resolution order:
      1. ``ELSPAIS_CLIENT_PID`` env var (or its former name, still
         honoured) — explicit declaration by the session/IDE (also the
         deterministic hook for tests).
      2. Inside a Claude Code session (``CLAUDECODE`` env set): the
         nearest ancestor process named ``claude`` (the session process;
         intermediate tool shells are ephemeral).
      3. The controlling-terminal session leader (``os.getsid(0)``), if
         it is a real interactive session (has a tty). An interactive
         shell qualifies; batch/CI/tool shells do not.

    Steps 2 and 3 read ``/proc`` and a POSIX session id, so on platforms
    without them only the explicit declaration in step 1 resolves.

    Returns None when no session identity can be established — the
    daemon then keeps its TTL-only lifetime (current behavior).
    """
    declared = _declared_client_pid()
    if declared is not None:
        return declared if isinstance(declared, int) else None

    if os.environ.get("CLAUDECODE"):
        for pid, comm in _iter_proc_ancestors():
            if comm == "claude":
                return pid

    try:
        sid = os.getsid(0)
    except (OSError, AttributeError):
        # No session concept on this platform: no identity to record.
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
    client_pid: int | None = None,
) -> Path:
    """Write daemon.json state file for a running server.

    Both the headless daemon and the viewer use this to register
    themselves as the active server for a project.

    Args:
        repo_root: Project root directory.
        pid: Process ID of the server.
        port: Port the server is listening on.
        server_type: "daemon" or "viewer".
        client_pid: PID of the session the daemon was implicitly
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
    if client_pid is not None:
        info["client_pid"] = client_pid
        # A list of process ids cannot answer "who is this daemon watching"
        # once a handle may be a held stream instead. Each entry says what
        # kind of handle it is.
        info["clients"] = [{"kind": "pid", "id": client_pid}]
    _write_json_atomic(daemon_json, info)
    return daemon_json


# Implements: REQ-o00074-B
def record_daemon_clients(repo_root: Path, client_pids: list[int], held: int = 0) -> None:
    """Publish the daemon's current client set in its state record.

    A lifetime rule nobody can inspect cannot be diagnosed, and the set
    grows as clients pick the daemon up, so publishing only the first one
    would answer a question nobody is asking by the time it matters.

    Each entry names the kind of handle it is, because a client can be
    present as a held stream rather than as a process id, and a record
    that can only hold process ids leaves such a client watched and
    invisible.
    """
    path = _daemon_json_path(repo_root)
    if not path.exists():
        return
    try:
        info = json.loads(path.read_text())
        info["clients"] = [{"kind": "pid", "id": p} for p in sorted(client_pids)] + (
            [{"kind": "session", "count": held}] if held else []
        )
        _write_json_atomic(path, info)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"warning: could not publish the daemon's client set: {exc}", file=sys.stderr)


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
        _write_json_atomic(path, info)
    except OSError:
        pass  # Best effort — a failed refresh only risks an extra restart


# ── Daemon lifecycle ─────────────────────────────────────────────────────


def _daemon_dir(repo_root: Path) -> Path:
    return repo_root / ".elspais"


def _write_json_atomic(path: Path, payload: dict) -> None:
    """Replace a state record without a reader ever seeing it half-written.

    Truncate-then-write leaves a window in which the file is short. A reader
    landing there gets invalid JSON and concludes the record is corrupt --
    and the reader for this record *deletes* it on that conclusion, so a
    daemon that is running and healthy becomes undiscoverable while it is
    still serving, and the next command starts a second one for the same
    working tree.

    Writing a sibling and renaming over the target is atomic on POSIX: a
    reader sees either the whole old record or the whole new one. The
    temporary file is a sibling so the rename stays within one filesystem,
    and carries the writer's pid so two writers cannot collide on it.
    """
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _daemon_json_path(repo_root: Path) -> Path:
    return _daemon_dir(repo_root) / "daemon.json"


def _client_notice_path(repo_root: Path) -> Path:
    """Marker that the unbound-lifetime notice has been given.

    Scoped to the daemon it describes: removed when a daemon starts, so a
    client meeting a different daemon is told about that one. Named under
    the daemon.* prefix so the existing ignore rule covers it.
    """
    return _daemon_dir(repo_root) / "daemon.client-notice"


# Implements: REQ-o00074-N
def notify_unbound_lifetime(repo_root: Path, reason: str) -> bool:
    """Say once that this daemon's lifetime is not bound to this client.

    The condition is not an error and the command is not refused: a tool
    whose operations require a background process fails whenever that
    process cannot be bound (REQ-o00075-G). What the client is owed is the
    fact and the remedy, which is also the only route by which a harness
    author discovers the declaration exists.

    Returns True when it printed.
    """
    marker = _client_notice_path(repo_root)
    if marker.exists():
        return False
    print(
        f"note: {reason}, so this daemon's lifetime is not bound to this "
        "session — it will stop when its recorded clients do, or when its "
        "idle timeout expires. To bind it, export ELSPAIS_CLIENT_PID with "
        "the process id of the session or job this work belongs to.",
        file=sys.stderr,
    )
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        pass  # printing once more beats failing the command
    return True


def _automatic_save_path(repo_root: Path) -> Path:
    """Record of a save the daemon performed itself.

    A sibling of daemon.json rather than a key inside it: daemon.json
    describes the process that is running now and is removed when that
    process stops, while this record has to outlive the daemon that
    wrote it — its whole purpose is to reach the *next* client.
    """
    return _daemon_dir(repo_root) / "automatic-save.json"


def _unsaved_changes_path(repo_root: Path) -> Path:
    """Sentinel meaning "a server is holding changes it has not written".

    Presence is the whole signal. It says nothing about how many changes
    there are or what they touch, because nothing it could say would be
    true by the time it mattered: the file is written once, when the
    holding starts, and the holding goes on changing afterwards.

    A sibling of daemon.json rather than a key inside it, for the same
    reason the automatic-save record is: daemon.json is unlinked when the
    process stops, and this has to reach the process that comes next.
    """
    return _daemon_dir(repo_root) / "unsaved-changes"


def _lost_changes_path(repo_root: Path) -> Path:
    """Sentinel meaning "a process that is gone ended holding changes".

    Separate from the sentinel above because the two answer different
    questions — what is held now, and what was held by something that no
    longer exists — and one file cannot answer both without the answer to
    each being read as the answer to the other.
    """
    return _daemon_dir(repo_root) / "lost-changes"


def _touch_sentinel(path: Path, what: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError as exc:
        # Best effort, and said out loud. The alternative — refusing the
        # mutation because its sentinel could not be written — would turn
        # an honesty measure into an outage.
        print(f"warning: could not record that {what}: {exc}", file=sys.stderr)


def _remove_sentinel(path: Path, what: str) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"warning: could not clear the record that {what}: {exc}", file=sys.stderr)


# Implements: REQ-p00083-E
def mark_unsaved_changes(repo_root: Path) -> None:
    """Record that changes are being held unwritten, before they are acknowledged."""
    _touch_sentinel(_unsaved_changes_path(repo_root), "changes are being held unwritten")


# Implements: REQ-o00074-L
def clear_unsaved_changes(repo_root: Path) -> None:
    """Record that nothing is being held any more."""
    _remove_sentinel(_unsaved_changes_path(repo_root), "changes were being held unwritten")


# Implements: REQ-o00074-L
def has_unsaved_changes_sentinel(repo_root: Path) -> bool:
    return _unsaved_changes_path(repo_root).exists()


# Implements: REQ-o00074-L
def has_lost_changes(repo_root: Path) -> bool:
    """True while an earlier process is known to have died holding changes."""
    return _lost_changes_path(repo_root).exists()


# Implements: REQ-o00074-J
def clear_lost_changes(repo_root: Path) -> None:
    """Retire the finding once a client has written the tree at its own request."""
    _remove_sentinel(_lost_changes_path(repo_root), "an earlier process died holding changes")


# Implements: REQ-o00074-L
def adopt_inherited_sentinel(repo_root: Path) -> bool:
    """Turn a sentinel left by a dead process into a finding about it.

    Called once, as a server starts. A sentinel that is still present
    then was written by a process that is gone, and it was still present
    because that process never reached the point of clearing it — it
    ended holding changes it never wrote.

    The sentinel is not simply left in place: from this moment it would
    read as a statement about the starting process, which holds nothing.
    It is not simply deleted either, because deleting it is the only way
    the finding can be lost a second time. It becomes the other record,
    which says what is actually known.

    Returns True if such a sentinel was found.
    """
    if not has_unsaved_changes_sentinel(repo_root):
        return False
    _touch_sentinel(_lost_changes_path(repo_root), "an earlier process died holding changes")
    clear_unsaved_changes(repo_root)
    print(
        "warning: a previous elspais server ended while holding changes it never "
        "wrote to disk. What they were cannot be recovered — the files on disk do "
        "not include them.",
        file=sys.stderr,
    )
    return True


# Implements: REQ-p00083-C
def record_automatic_save(
    repo_root: Path,
    mutation_count: int | None,
    files_written: int = 0,
    trigger: str = "",
) -> None:
    """Record a save the daemon performed rather than a client requesting it.

    The record carries facts only — who saved, when, how much, and what
    condition triggered it. It says nothing about whether the work is
    finished, wanted, or trustworthy: a client can disappear because it
    completed, crashed, or lost its connection, and those are
    indistinguishable from here. The reader draws the conclusion.

    Best effort: a daemon that cannot write this record has already
    written the files, and failing the save afterwards would be worse
    than an unrecorded one. The failure is printed instead.
    """
    from elspais import __version__

    record = {
        "saved_by": "daemon",
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mutation_count": mutation_count,
        "files_written": files_written,
        "trigger": trigger,
        "version": __version__,
    }
    path = _automatic_save_path(repo_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path, record)
    except OSError as exc:
        print(f"warning: could not record the automatic save: {exc}", file=sys.stderr)


# Implements: REQ-p00083-C
def read_automatic_save(repo_root: Path) -> dict | None:
    """Return the outstanding automatic-save record, or None."""
    path = _automatic_save_path(repo_root)
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return record if isinstance(record, dict) else None


# Implements: REQ-p00083-H
def clear_automatic_save(repo_root: Path) -> None:
    """Retire the record once a client saves at its own request.

    From that point the record describes a state that no longer stands,
    and a notice that never retires is one nobody reads.
    """
    try:
        _automatic_save_path(repo_root).unlink(missing_ok=True)
    except OSError as exc:
        print(f"warning: could not retire the automatic-save record: {exc}", file=sys.stderr)


# Implements: REQ-o00075-B, REQ-o00075-E
def mark_daemon_stopping(repo_root: Path, pid: int | None = None) -> bool:
    """Record that the daemon described by the state record is stopping.

    A process that has committed to stopping goes on answering until it
    actually goes, so being alive no longer distinguishes it from one that
    will serve. Everything it is handed is refused, and the refusal tells
    the caller to reconnect to a server that will be started on demand —
    which is not what happens while this one is still the server a client
    locates.

    The record is marked rather than removed. Removing it while the
    process still serves is what lets a successor boot alongside it, and
    one working tree is served by one process (REQ-o00075-B). It is
    unlinked once the process is gone, which is stopping's job.

    Only a record describing *this* process is marked. A server holding a
    private graph — a stdio session, or any process that did not write the
    record — would otherwise report a daemon as stopping that is serving
    perfectly well.

    Returns True if the record was marked. Best effort: a stop that could
    not write this is still a stop, so failure is warned about and never
    raised into a shutdown already underway.
    """
    if pid is None:
        pid = os.getpid()
    path = _daemon_json_path(repo_root)
    try:
        if not path.is_file():
            return False
        info = json.loads(path.read_text())
        if info.get("pid") != pid:
            return False
        info["stopping"] = True
        _write_json_atomic(path, info)
        return True
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        print(
            f"warning: could not record that this daemon is stopping: {exc}. "
            "A client may reuse it and have its writes refused.",
            file=sys.stderr,
        )
        return False


# Implements: REQ-o00075-E
def daemon_is_stopping(info: dict | None) -> bool:
    """True when the record says its daemon has committed to stopping."""
    return bool(info and info.get("stopping"))


# Implements: REQ-o00075-B
def replace_stopping_daemon(repo_root: Path, info: dict, timeout: float = 20.0) -> bool:
    """Wait for a stopping daemon to go, so a fresh one can take its place.

    The wait is the same one stopping performs, and for the same reason:
    starting a replacement while the outgoing process still serves would
    put two processes on one working tree, each holding a graph the other
    cannot see.

    The record is unlinked only if it still describes the process waited
    on. A successor that has already registered owns the record by then,
    and clearing it would hide a daemon that is serving.

    Returns False when the daemon did not go, in which case the caller has
    neither a daemon to reuse nor leave to start one.
    """
    if not wait_for_daemon_exit(info, timeout=timeout):
        print(
            f"warning: the daemon (pid {info.get('pid')}) is stopping but had not "
            f"gone after {timeout:.0f}s. It refuses writes, and starting a second "
            "one for this working tree would split the graph between two processes.",
            file=sys.stderr,
        )
        return False
    current = get_daemon_info(repo_root)
    if current and current.get("pid") == info.get("pid"):
        _daemon_json_path(repo_root).unlink(missing_ok=True)
    return True


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
    client_pid: int | None = None,
) -> int:
    """Start a background MCP server and return its port.

    Spawns ``elspais mcp serve --transport streamable-http --port 0
    --ttl <ttl>`` as a detached process.  The server writes daemon.json
    after binding; this function polls for it.

    Args:
        ttl_minutes: >0 = exit after N minutes idle.
                     <0 = run forever (no timeout).
                      0 = should not be called (caller should check).
        client_pid: PID of the session this daemon serves. When set,
            the daemon watches it and shuts down after the session
            exits. None (explicit starts) keeps TTL-only lifetime.
    """
    # Stop any existing server before overwriting daemon.json. Without
    # this, the old server becomes an undiscoverable orphan.
    #
    # Implements: REQ-o00075-B
    # And refuse if it would not go. Every caller today checks this for
    # itself and reaches here with the tree already clear, so this guard
    # is unreachable in practice -- which is exactly why it belongs here.
    # "At most one process per working tree" cannot rest on every future
    # caller of a function named start_daemon remembering to stop one
    # first; the function that would break the invariant is the one that
    # has to hold it.
    if stop_daemon(repo_root) is StopOutcome.STILL_RUNNING:
        raise RuntimeError(
            "Refusing to start a daemon for this working tree: the one already "
            "serving it did not stop. Two daemons would split the graph between "
            "two processes, and neither would see the other's unsaved work."
        )

    # Implements: REQ-o00074-N
    # A fresh daemon is a fresh account of its own client set, so it
    # discloses on its own account rather than being silenced by what a
    # predecessor already told this repo root.
    _client_notice_path(repo_root).unlink(missing_ok=True)

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
    if client_pid is not None:
        child_env[_CLIENT_ENV] = str(client_pid)
    else:
        child_env.pop(_CLIENT_ENV, None)

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


# Implements: REQ-o00075-B, REQ-o00075-E
class StopOutcome(str, enum.Enum):
    """What a stop attempt actually found, as three distinct facts.

    A boolean cannot carry these. "Nothing was running" and "it would not
    stop" are both not-stopped, and a caller that refuses on the second
    must not refuse on the first: a daemon that exited between the
    caller's look and this one is gone, which is what the caller wanted.
    Conflating them produced confident, wrong refusals.
    """

    STOPPED = "stopped"
    NOT_RUNNING = "not-running"
    STILL_RUNNING = "still-running"

    @property
    def is_gone(self) -> bool:
        """True when nothing is serving this working tree any more."""
        return self is not StopOutcome.STILL_RUNNING


def stop_daemon(repo_root: Path, wait: bool = True, timeout: float = 20.0) -> StopOutcome:
    """Stop a running daemon. Reports which of three things happened.

    The record is unlinked last, and only once the process it describes
    has exited. Removing it first left a window in which a daemon was
    serving and undiscoverable: a concurrent command found nothing and
    started a second process for the same working tree, and a successor
    booting into that window read the predecessor's dirty sentinel as
    evidence of a process that died holding work, which is a loss that is
    not happening.

    A daemon persists what it holds on the way out, so the wait covers a
    save rather than a signal handler.

    NOT_RUNNING means there was nothing to stop -- including the case
    where the daemon exited between the caller's own look and this one.
    STILL_RUNNING leaves the record in place, because it still describes
    something a client would reach.
    """
    info = get_daemon_info(repo_root)
    if info is None:
        return StopOutcome.NOT_RUNNING
    try:
        os.kill(info["pid"], signal.SIGTERM)
    except OSError:
        pass  # already gone; fall through and clear the record
    if wait and not wait_for_daemon_exit(info, timeout=timeout):
        print(
            f"warning: the daemon (pid {info['pid']}) did not stop within "
            f"{timeout:.0f}s. Its state record is left in place because it is "
            "still serving.",
            file=sys.stderr,
        )
        return StopOutcome.STILL_RUNNING
    _daemon_json_path(repo_root).unlink(missing_ok=True)
    return StopOutcome.STOPPED


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


# Implements: REQ-o00074-E
def attach_client(info: dict, pid: int | None) -> bool:
    """Tell a running daemon that this session is now one of its clients.

    Best effort by design: a daemon too old to know the call, or a
    session whose identity could not be established, leaves the daemon's
    lifetime exactly as it was rather than failing the command the
    caller actually asked for.
    """
    import json as _json
    from urllib.request import Request as _Request

    port = info.get("port")
    if not port or not pid:
        return False
    req = _Request(
        f"http://127.0.0.1:{port}/api/session/attach",
        data=_json.dumps({"pid": pid}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=3) as resp:
            return bool(_json.loads(resp.read().decode()).get("attached"))
    except (URLError, OSError, ValueError):
        return False


# Implements: REQ-o00074-E, REQ-o00074-N
def ensure_client_registered(repo_root: Path, info: dict | None) -> bool:
    """Register this session as a client of a daemon it did not start.

    Called on every path that reuses a running daemon, not only the one
    that considers starting a fresh one: a session that only ever picks
    up somebody else's daemon is the case the rule exists for, and it is
    also the one that never reaches the start path.

    Skips the call when the daemon's published client set already names
    this session, so the cost is one round-trip per session rather than
    one per command.

    ``repo_root`` keys the unbound-lifetime notice: both call sites already
    hold it, and a notice keyed on a path read back out of the record would
    be keyed on whatever the record happened to say rather than on the
    daemon this session is actually reusing.
    """
    if not info:
        return False
    pid = resolve_client_pid()
    if not pid:
        reason = (
            "the declared client handle could not be used"
            if _declared_client_pid() == _UNUSABLE
            else "no client handle could be derived from this session"
        )
        notify_unbound_lifetime(repo_root, reason)
        return False
    # Read tolerantly: an absent key means "not recorded", so a record
    # written by a differently-versioned process costs one wasted attach
    # round-trip rather than a missed registration.
    recorded = {c.get("id") for c in (info.get("clients") or []) if c.get("kind") == "pid"}
    if pid in recorded:
        return True
    return attach_client(info, pid)


def save_daemon_mutations(info: dict, message: str | None = None) -> dict:
    """Ask the daemon to persist pending mutations to disk.

    ``message`` is the changelog reason for changes to Active
    requirements; the save is refused without one when changelog
    enforcement is on and such a change is pending.

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
    payload: dict = {"if_tip_mutation_id": tip}
    if message:
        payload["message"] = message
    body = _json.dumps(payload).encode()
    req = _Request(
        f"http://127.0.0.1:{port}/api/save",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return _json.loads(resp.read().decode())
    except HTTPError as e:
        # A refused save answers with a body saying why — a stale tip, a
        # missing changelog reason, a write that failed. Report that,
        # rather than the status code the caller cannot act on.
        return _rejection_body(e)
    except URLError as e:
        return {"success": False, "error": f"daemon unreachable: {e}"}
    except (OSError, ValueError) as e:
        return {"success": False, "error": str(e)}


def _rejection_body(exc: HTTPError) -> dict:
    """Parse a refusing server's JSON body, falling back to its status."""
    import json as _json

    try:
        body = _json.loads(exc.read().decode())
    except (OSError, ValueError):
        return {"success": False, "error": f"server refused the request: HTTP {exc.code}"}
    if not isinstance(body, dict):
        return {"success": False, "error": f"server refused the request: HTTP {exc.code}"}
    body.setdefault("success", False)
    return body


# Implements: REQ-o00074-I
def request_daemon_stop(info: dict, discard_changes: bool = False) -> dict:
    """Ask a running daemon to stop, saying what to do with what it holds.

    Without ``discard_changes`` this is an ordinary stop and the daemon
    writes its pending changes on the way out. With it, the caller has
    said those changes are not wanted, and the daemon drops them.

    A discard names the mutation-log tip the caller last saw, so the
    instruction covers the changes that existed when it was given: if
    another writer has applied one since, the daemon refuses the whole
    request and reports the conflict rather than sweeping that change
    into a discard nobody asked for it to cover.
    """
    import json as _json
    from urllib.request import Request as _Request

    port = info.get("port")
    if not port:
        return {"success": False, "error": "daemon has no port"}

    body: dict = {}
    if discard_changes:
        tip = ""
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/dirty", timeout=5) as resp:
                tip = _json.loads(resp.read().decode()).get("tip") or ""
        except (URLError, OSError, ValueError):
            pass  # "" means "nothing pending"; the guard rejects it if not true
        body = {"discard_changes": True, "if_tip_mutation_id": tip}

    req = _Request(
        f"http://127.0.0.1:{port}/api/shutdown",
        data=_json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return _json.loads(resp.read().decode())
    except HTTPError as e:
        return _rejection_body(e)
    except URLError as e:
        return {"success": False, "error": f"daemon unreachable: {e}"}
    except (OSError, ValueError) as e:
        return {"success": False, "error": str(e)}


def _reap_if_our_child(pid: int) -> bool:
    """Collect ``pid`` if it is our own child that has already exited.

    ``waitpid(pid, WNOHANG)`` only succeeds for a direct child; for any
    other pid it raises, which is exactly the "not ours to reap" case and
    is swallowed. True means the child was collected (or was already
    gone); the caller still needs its own liveness check to know which.
    """
    try:
        collected_pid, _status = os.waitpid(pid, os.WNOHANG)
        return collected_pid == pid
    except (ChildProcessError, OSError):
        return False


def _proc_is_zombie(pid: int) -> bool:
    """True if ``/proc/<pid>`` reports process state ``Z`` (zombie).

    Best effort, matching ``_session_leader_has_tty``'s read-and-tolerate
    style: unreadable or malformed /proc content (missing, permission
    denied, non-Linux) reports False rather than raising, leaving the
    caller to fall back to its own liveness check.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        # comm may contain spaces/parens; fields after the last ')' are
        # position-stable. State is the first field after that.
        state = stat.rsplit(")", 1)[1].split()[0]
        return state == "Z"
    except (OSError, ValueError, IndexError):
        return False


def wait_for_daemon_exit(info: dict, timeout: float = 20.0) -> bool:
    """Block until the daemon process is gone. True if it went.

    ``kill(pid, 0)`` alone is not enough: it asks the kernel only whether
    the pid could be signalled, and a process that has exited but not yet
    been reaped by its parent -- a zombie -- still answers yes. Every test
    that spawns a daemon directly is that daemon's parent, and so is any
    other caller that does the same, so this is not a corner case: without
    accounting for it, a daemon that died immediately is reported as still
    serving for the full timeout. Each poll therefore also reaps the pid
    if it is our own child (harmless if it is not, or if nothing is
    waiting to be collected) and checks /proc for zombie state, so a
    reaped-or-reapable exit is seen at once rather than at the deadline.
    """
    pid = info.get("pid")
    if not pid:
        return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        _reap_if_our_child(pid)
        if _proc_is_zombie(pid):
            return True
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.2)
    return False


def restart_daemon(
    repo_root: Path,
    discard_changes: bool = False,
    persist: bool = False,
    message: str | None = None,
    ttl_minutes: int | None = None,
) -> dict:
    """Stop and restart the daemon, picking up any config file changes.

    Hard restart only — kills the existing process and spawns a fresh one,
    which re-reads ``.elspais.toml`` during startup.

    In-memory mutation safety:
        - If the daemon reports 0 unsaved mutations: restart proceeds.
        - Otherwise, the default is to refuse with an error listing the
          count. The caller says what to do with the work: ``persist``
          saves it here, with a changelog reason, before stopping;
          ``discard_changes`` instructs the daemon to drop it. The two
          are mutually exclusive.

    A daemon stopped by any other route writes what it holds as it goes,
    because nobody has said otherwise. ``discard_changes`` is that
    statement: the work is dropped and nothing reaches disk. It is sent
    to the daemon naming the changes it covers, so a change another
    writer applied in the meantime is reported rather than dropped with
    the rest.

    Returns:
        Dict with ``success`` (bool) and ``message`` (str). On successful
        restart, also includes ``port``. On refusal due to unsaved
        mutations, includes ``mutation_count`` and an ``error`` key.
    """
    if discard_changes and persist:
        return {
            "success": False,
            "error": "--discard-changes and --persist are mutually exclusive",
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

    # An instruction to discard goes to the daemon whatever the pending
    # count reads, because that count is a read that can go stale: a
    # mutation applied just after it would otherwise be stopped over with
    # an ordinary signal and saved, which is the opposite of what was
    # asked for. The daemon decides against the log it holds.
    stopped = False
    if discard_changes:
        stop_result = request_daemon_stop(info, discard_changes=True)
        if not stop_result.get("success"):
            return {
                "success": False,
                "error": (
                    f"Cannot restart — the daemon did not discard: "
                    f"{stop_result.get('error', stop_result)}"
                ),
                "code": stop_result.get("code"),
                "mutation_count": get_daemon_mutation_count(info),
            }
        if not wait_for_daemon_exit(info):
            return {
                "success": False,
                "error": (
                    "Cannot restart — the daemon accepted the discard but did "
                    "not exit. It is still serving, and starting a second one "
                    "for this working tree would split the graph between two "
                    "processes."
                ),
            }
        # The daemon is confirmed gone here, so the record is unlinked now
        # rather than by the stop_daemon() call below. That call reads
        # through get_daemon_info(), which would see the pid already dead
        # and quietly clear the record as stale -- indistinguishable, from
        # stop_daemon()'s own view, from nothing having been running.
        _daemon_json_path(repo_root).unlink(missing_ok=True)
        stopped = True
    else:
        # Daemon is running — check for unsaved work.
        count = get_daemon_mutation_count(info)
        if count and count > 0:
            if persist:
                save_result = save_daemon_mutations(info, message=message)
                if not save_result.get("success"):
                    return {
                        "success": False,
                        "error": (
                            f"Cannot restart — persist requested but save failed: "
                            f"{save_result.get('error', save_result)}"
                        ),
                        "mutation_count": count,
                    }
            else:
                return {
                    "success": False,
                    "error": (
                        f"Cannot restart — daemon has {count} unsaved in-memory mutation(s). "
                        "Use --persist (with --message when Active requirements "
                        "changed) to save them here, or --discard-changes to throw "
                        "them away."
                    ),
                    "mutation_count": count,
                }

    # At this point we're committed to restart.
    if not stopped and not stop_daemon(repo_root).is_gone:
        return {
            "success": False,
            "error": (
                "Cannot restart — the running daemon did not stop. It is still "
                "serving, and starting a second one for this working tree would "
                "split the graph between two processes."
            ),
        }

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
    # Implements: REQ-o00075-B, REQ-o00075-E
    # A daemon that has committed to stopping passes every liveness check
    # and refuses everything it is handed. Wait for it and start a fresh
    # one; do not hand it out, and do not start alongside it. The wait
    # happens here rather than inside the start path because that path
    # discards the answer, and a daemon that will not go has to stop the
    # start rather than be spawned past.
    if daemon_is_stopping(info):
        if not replace_stopping_daemon(repo_root, info):
            raise RuntimeError(
                "The daemon serving this working tree is stopping and has not gone. "
                "Starting a second one would split the graph between two processes."
            )
        info = None
    if info:
        # Version check: restart if daemon is from a different elspais version
        from elspais import __version__

        daemon_version = info.get("version")
        if daemon_version and daemon_version != __version__:
            if not stop_daemon(repo_root).is_gone:
                # It is still serving. An out-of-date daemon answering is
                # better than two daemons answering differently. This
                # session is about to use it in place of the fresh one it
                # could not start, so it registers as a client the same
                # way the reuse path below does.
                ensure_client_registered(repo_root, info)
                return info["port"]
            # Fall through to start a fresh daemon
        elif _config_hash_stale(info, repo_root):
            if not stop_daemon(repo_root).is_gone:
                # It is still serving. An out-of-date daemon answering is
                # better than two daemons answering differently. This
                # session is about to use it in place of the fresh one it
                # could not start, so it registers as a client the same
                # way the reuse path below does.
                ensure_client_registered(repo_root, info)
                return info["port"]
            # Fall through to start a fresh daemon
        else:
            # Implements: REQ-o00074-E
            # Reusing a daemon somebody else started makes this session
            # one of its clients. Say so, or the daemon goes on watching
            # only the client that started it and stops underneath this
            # one when that client exits.
            ensure_client_registered(repo_root, info)
            return info["port"]

    if ttl_minutes is None:
        ttl_minutes = get_cli_ttl(repo_root)

    # cli_ttl=0 means never auto-launch
    if ttl_minutes == 0:
        raise RuntimeError("Daemon auto-launch disabled (cli_ttl=0)")

    # Implicit spawn on behalf of a CLI/session: tie the daemon's
    # lifetime to that session so it cannot outlive it. Explicit starts
    # (elspais daemon, manual mcp serve, viewer) do not pass a
    # client and keep TTL-only behavior.
    client_pid = resolve_client_pid()
    if client_pid is None:
        # Implements: REQ-o00074-N
        notify_unbound_lifetime(repo_root, "no client handle could be derived from this session")
    return start_daemon(
        repo_root,
        ttl_minutes=ttl_minutes,
        client_pid=client_pid,
    )
