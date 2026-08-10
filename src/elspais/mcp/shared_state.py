"""elspais.mcp.shared_state - single source of truth for the live graph.

The unified daemon serves two mutation surfaces over one graph: the MCP
tools (sync functions FastMCP runs on worker threads) and the viewer's
HTTP routes (async handlers on the event loop). Both must always
dereference the same graph, including across rebuilds — two references
kept "in sync" is how accepted writes get silently dropped (CUR-1829
stress finding: one save_mutations split the surfaces and a guarded,
accepted HTTP write never reached disk).

SharedServerState is that single point of dereference. It is a dict
(the MCP tools' historical ``_state`` shape: "graph", "config",
"working_dir") so every existing ``_state["graph"]`` read and write is
already a read/write of the shared cell. AppState exposes ``.graph`` /
``.config`` as properties over the same object.

``write_lock`` serializes every mutation critical section
(guard + mutate + log append) and every rebuild-and-swap, across both
surfaces. It is a ``threading.RLock`` — an asyncio lock cannot exclude
the MCP worker threads. Mutations are short synchronous CPU work, so
async handlers may hold it briefly without starving the event loop.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from typing import Any


class SharedServerState(dict):
    """Dict-shaped holder for graph/config plus the write lock.

    There is exactly one of these per server process; MCP tool closures
    and AppState both hold a reference to the same instance, so a swap
    (``state["graph"] = new_graph``) is visible to every surface at once
    with nothing to propagate.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.write_lock = threading.RLock()
        # Every rebuild-and-swap stamps this, on either surface. The viewer's
        # staleness check reads it, so a holder that never carried one would
        # report every spec file as changed.
        self.setdefault("build_time", time.time())
        # Callbacks run inside rebuild_shared_graph()'s critical section, after
        # the new config and graph are published. This is how change-detection
        # state that lives outside the holder is brought forward by a rebuild
        # reached through any surface: the process serving the graph registers
        # its mtime re-snapshot and its daemon-fingerprint sync here, rather
        # than each reload path remembering to call them (REQ-p00004-O).
        #
        # Registration is also what scopes those effects to the process that
        # owns them. A stdio MCP server holds a private graph of its own and
        # registers nothing, so it never writes freshness records belonging to
        # a daemon running in the same repo — a fingerprint stamped by a
        # process that did not rebuild the daemon's graph would suppress a
        # restart that is genuinely needed.
        self.post_rebuild_hooks: list[Callable[[], None]] = []
        # Raised the instant this process decides to stop, before the
        # signal that starts the drain. Every write critical section
        # checks it under the same lock, so a write arriving after the
        # decision is refused rather than accepted and then lost with
        # the process (REQ-o00062-O, REQ-p00083-G).
        self._shutting_down = threading.Event()
        # Raised once the process has finished accounting for the work it
        # holds. Distinct from the refusal flag above: refusals begin the
        # moment a stop is decided, while this says the final persist has
        # already run, so a later stop path does not repeat it.
        self._shutdown_finalized = False
        # Raised when a client stopping this process has said what is to
        # become of the work it holds. Preserving that work is what
        # happens when nobody has said; an instruction to drop it is the
        # statement that was otherwise missing (REQ-p00083-B).
        self._discard_requested = False
        # The one bound on a drain that will not finish, and the lock that
        # keeps it one. A stop can be reached through two paths at once —
        # a client's stop request arms it, and the signal that request
        # sends lands in the handler, which arms it again — and a second
        # timer nobody holds a handle to would force an exit after a drain
        # that finished perfectly well.
        self._drain_backstop: threading.Timer | None = None
        # Reentrant, because a stop signal can land on this thread while
        # it is inside this lock's critical section, and the handler arms
        # the bound as its first act. A plain lock would deadlock there —
        # in the handler whose whole job is to stop the process hanging.
        self._drain_backstop_lock = threading.RLock()

    # Implements: REQ-o00075-B, REQ-o00075-E
    def begin_shutdown(self) -> None:
        """Mark this process as shutting down. Irreversible by design.

        The state record clients read to find this process is marked too,
        because from here on it describes a server that answers and
        refuses: every write is turned away with a message telling the
        caller to reconnect to a server started on demand, which is untrue
        while this one is the server a client locates. Marked rather than
        removed — a record removed while its process still serves is what
        lets a second daemon boot alongside it.

        Marking is best effort and never raises: a stop that cannot write
        this is still a stop, and failing here would leave the process
        neither stopping nor serving.
        """
        already = self._shutting_down.is_set()
        self._shutting_down.set()
        if already:
            # Reached from every stop path, and more than one can run. The
            # record already says what this would write.
            return
        working_dir = self.get("working_dir")
        if working_dir is None:
            return
        try:
            from elspais.mcp.daemon import mark_daemon_stopping

            mark_daemon_stopping(working_dir)
        except Exception as exc:  # never let a stop fail on its own bookkeeping
            print(
                f"warning: could not record that this daemon is stopping ({exc!r}); "
                "a client may reuse it and have its writes refused.",
                file=sys.stderr,
                flush=True,
            )

    def request_discard(self) -> None:
        """Record an instruction to drop the work this process holds.

        Set under ``write_lock`` in the same critical section that decides
        the stop, so the set of changes the instruction covers is the set
        that existed when it was given: a writer already past the refusal
        check has finished before this runs, and one arriving afterwards
        meets a process that has committed to stopping and is refused.
        """
        self._discard_requested = True

    @property
    def discard_requested(self) -> bool:
        """True when a client has instructed this process to drop its work."""
        return self._discard_requested

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down.is_set()

    @property
    def shutdown_finalized(self) -> bool:
        """True once the work this process held has been accounted for."""
        return self._shutdown_finalized


# Implements: REQ-o00074-G, REQ-p00083-A, REQ-p00083-D
def finalize_shutdown(state: SharedServerState, trigger: str) -> dict[str, Any]:
    """Account for the work this process holds, then commit it to stopping.

    Every way the process can stop runs this and nothing else: the
    client-liveness deadline, the idle timeout, a client asking it to
    stop, and the fall-through after the server stops serving, which is
    where an external stop signal arrives. A process holding unsaved
    changes therefore persists them whatever prompted it to stop, rather
    than only on the one path somebody thought to write a save into.

    Unless it was told not to. A client that stopped this process may
    have said what is to become of the work; when it has, that answer
    stands and nothing is written. Preservation is what happens when
    nobody has said, not a rule that outranks whoever did.

    Ordering. The whole routine runs under ``write_lock``, so a writer
    that had already passed the refusal check is finished before the
    count is taken and its change is inside the save, while a writer
    arriving later blocks here and then meets the refusal flag this
    routine raises before it releases the lock. That is why the flag is
    raised last rather than first: the check is taken under the same
    lock, so raising it early buys nothing, and raising it late leaves a
    failed save recoverable.

    Failure. If the changes cannot be written they are kept, the flag is
    not raised, and nothing is marked finalized — the process stays
    usable, a client can still save through it, and the next stop path
    tries again. Reported, never raised: a caller holding the only copy
    of somebody's work has to be able to keep it.

    Args:
        state: The process-wide holder.
        trigger: The condition that prompted the stop, stated as an
            observation. It is recorded verbatim for the next client.

    Returns:
        ``{"success", "finalized", "pending", "saved", "discarded",
        "files_written"}``, plus ``"error"`` when the save failed.
        ``finalized`` is False on a repeat call, which is how a caller
        tells "already accounted for" from "just accounted for".
    """
    with state.write_lock:
        if state._shutdown_finalized:
            # What the first call found is not this call's to report, and
            # a zero here would be a number nobody measured.
            return {
                "success": True,
                "finalized": False,
                "pending": None,
                "saved": False,
                "discarded": False,
                "files_written": 0,
            }

        graph = state.get("graph")
        pending: int | None
        try:
            pending = len(graph.mutation_log.tail(0)) if graph is not None else 0
        except Exception:
            # Never assume work we cannot count is absent; attempt the
            # save and let it report what it did.
            pending = None

        result: dict[str, Any] = {}
        saved = False
        discarded = state.discard_requested
        if not discarded and (pending is None or pending > 0):
            result = persist_pending(state, automatic=True, trigger=trigger)
            if not result.get("success"):
                return {
                    "success": False,
                    "finalized": False,
                    "pending": pending,
                    "saved": False,
                    "discarded": False,
                    "files_written": 0,
                    "error": result.get("error", "save failed"),
                }
            saved = True

        if discarded:
            # The work is going, at the instruction of somebody who said
            # so. Nothing was lost that anyone needs telling about, so the
            # sentinel goes with it rather than reporting a loss the next
            # process would have to explain (REQ-o00074-L).
            from elspais.mcp.daemon import clear_unsaved_changes

            working_dir = state.get("working_dir")
            if working_dir is not None:
                clear_unsaved_changes(working_dir)

        state._shutdown_finalized = True
        state.begin_shutdown()
        return {
            "success": True,
            "finalized": True,
            "pending": pending,
            "saved": saved,
            "discarded": discarded,
            "files_written": result.get("saved_count") or 0,
        }


# Implements: REQ-p00083-E
def attach_dirty_sentinel(state: SharedServerState) -> bool:
    """Make this process's unwritten changes visible from outside it.

    Two things happen here, once, as a server starts. A sentinel left
    behind by a process that is gone is turned into a finding about that
    process, so that presence from here on means only what this process
    is holding. Then this process's mutation log is watched, so the
    sentinel appears the moment it starts holding changes — before the
    change is acknowledged — and goes when it stops.

    Re-attached after every rebuild, because a rebuild publishes a new
    graph with a new log and an observer left on the old one would be
    watching a log nobody writes to.

    Returns True if an earlier process was found to have died holding
    changes.
    """
    from elspais.mcp.daemon import (
        adopt_inherited_sentinel,
        clear_unsaved_changes,
        mark_unsaved_changes,
    )

    working_dir = state.get("working_dir")
    if working_dir is None:
        return False

    inherited = adopt_inherited_sentinel(working_dir)

    def _observe(holding: bool) -> None:
        if holding:
            mark_unsaved_changes(working_dir)
        else:
            clear_unsaved_changes(working_dir)

    def _attach() -> None:
        graph = state.get("graph")
        log = getattr(graph, "mutation_log", None)
        if log is not None:
            log.set_dirty_observer(_observe)
            # A rebuilt graph holds nothing; say so rather than leaving
            # the previous graph's sentinel standing for it.
            if not len(log):
                clear_unsaved_changes(working_dir)

    _attach()
    state.post_rebuild_hooks.append(_attach)
    return inherited


def report_shutdown_outcome(outcome: dict[str, Any], trigger: str) -> None:
    """Print what the shutdown routine did, for whoever is watching stderr."""
    pending = outcome.get("pending")
    if not outcome.get("success"):
        print(
            f"Stopping because {trigger}: saving "
            f"{pending if pending is not None else 'an unknown number of'} "
            f"pending mutation(s) FAILED: {outcome.get('error')}. The mutations "
            "are retained in memory and the process is still serving.",
            file=sys.stderr,
            flush=True,
        )
    elif outcome.get("discarded"):
        if pending:
            print(
                f"Stopping because {trigger}: dropped {pending} pending "
                "mutation(s) as instructed. Nothing was written to disk.",
                file=sys.stderr,
                flush=True,
            )
    elif outcome.get("saved"):
        print(
            f"Stopping because {trigger}: saved {pending} pending "
            f"mutation(s) to {outcome.get('files_written')} file(s). The save was "
            "performed by the daemon, not requested by a client; that is recorded "
            "for the next client to read.",
            file=sys.stderr,
            flush=True,
        )


# The status this process ends with when it gave up on a drain that would
# not finish. 75 is the conventional "temporary failure" of sysexits.h: the
# stop was not completed as asked, and whoever is supervising the process
# can tell that from a stop that drained cleanly (0). Nothing else in this
# tree ends with 75.
DRAIN_ABANDONED_EXIT_STATUS = 75


def cancel_drain_backstop(state: SharedServerState) -> None:
    """Drop the bound on the drain, because the drain finished.

    Called where a stop completes on its own — the point serving ends —
    so a healthy shutdown never trips the forced exit. Safe to call when
    nothing is armed, and safe to call twice.
    """
    with state._drain_backstop_lock:
        timer = state._drain_backstop
        state._drain_backstop = None
    if timer is not None:
        timer.cancel()


# Implements: REQ-p00083-A, REQ-p00083-D
def arm_drain_backstop(
    state: SharedServerState,
    seconds: float = 10.0,
    trigger: str = "the drain did not finish",
    finalize_fn: Callable[[], dict[str, Any]] | None = None,
    exit_fn: Callable[[int], None] | None = None,
) -> Callable[[], None]:
    """Bound a drain that cannot finish, without losing what is held.

    A client connected over streamable HTTP holds a GET open for the life
    of its session. That is an in-flight request, so the server's graceful
    drain waits for it and never completes: the process neither stops nor
    serves, and the changes it holds stay in it.

    This is the bound on that wait. It accounts for the work FIRST — the
    shutdown routine is idempotent, so a path that already ran it pays
    nothing — and only then ends the process. The order is the whole
    point: a bound that simply exited would turn a stalled drain into
    exactly the loss this rule exists to prevent. It ends non-zero,
    because a stop that was abandoned is not the stop that was asked for
    and a supervisor has to be able to tell.

    Arming is idempotent per process. Every path that can decide to stop
    arms it, and two of them can run for a single stop, so a second call
    returns a handle to the bound already armed rather than adding one no
    caller can cancel.

    Returns:
        A callable that cancels the bound. A drain that finishes normally
        calls it, so a healthy shutdown never trips this.
    """
    import os

    if finalize_fn is None:

        def finalize_fn() -> dict[str, Any]:  # noqa: D401 - default binding
            return finalize_shutdown(state, trigger)

    if exit_fn is None:
        # os._exit, not sys.exit: this runs on a timer thread, where
        # SystemExit is raised into that thread and unwinds nothing else.
        # Everything the process owes has already been written by the
        # call above, so there is nothing left for an orderly teardown.
        exit_fn = os._exit

    def _cancel() -> None:
        cancel_drain_backstop(state)

    def _fire() -> None:
        with state._drain_backstop_lock:
            state._drain_backstop = None
        try:
            outcome = finalize_fn()
        except Exception as exc:  # pragma: no cover - defensive
            outcome = {"success": False, "error": repr(exc), "pending": None}
        pending = outcome.get("pending")
        held = f"{pending} pending mutation(s)" if pending else "no pending mutations"
        if outcome.get("success"):
            print(
                f"Gave up on the shutdown after {seconds:g}s: {trigger}, and a "
                "client is still holding a request open. The work this process "
                f"held ({held}) is accounted for; exiting "
                f"{DRAIN_ABANDONED_EXIT_STATUS}.",
                file=sys.stderr,
                flush=True,
            )
        else:
            # The process has already committed to stopping and is
            # refusing writes, so staying up would be a hang no client
            # could rescue. It ends, and says what it is ending with: the
            # sentinel recording that a process died holding changes is
            # still on disk for the next one to find (REQ-p00083-F).
            print(
                f"Gave up on the shutdown after {seconds:g}s: {trigger}, and the "
                f"work this process held ({held}) could NOT be written "
                f"({outcome.get('error')}). It is lost with this process; the "
                "record of that is left on disk. Exiting "
                f"{DRAIN_ABANDONED_EXIT_STATUS}.",
                file=sys.stderr,
                flush=True,
            )
        exit_fn(DRAIN_ABANDONED_EXIT_STATUS)

    with state._drain_backstop_lock:
        if state._drain_backstop is not None:
            return _cancel
        timer = threading.Timer(seconds, _fire)
        # Daemon threads only: a pending timer the interpreter joins on its
        # way out would hold the process open for exactly as long as the
        # bound was meant to bound it.
        timer.daemon = True
        state._drain_backstop = timer
        timer.start()

    return _cancel


# Implements: REQ-d00132-A, REQ-d00132-B, REQ-p00083-A, REQ-p00083-C, REQ-p00083-H
def persist_pending(
    state: SharedServerState,
    message: str | None = None,
    save_branch: bool = False,
    automatic: bool = False,
    trigger: str = "",
) -> dict[str, Any]:
    """Write pending in-memory mutations to the spec files. Never raises.

    Callers reach this either because a client asked for a save or
    because the daemon is stopping with no client left to ask. The two
    differ in exactly two places: a save the daemon performs itself
    supplies its own changelog reason (there is no client to prompt),
    and it leaves a record of who saved, when, how much and why, so a
    later client can see how the files reached their current form. A
    client-requested save retires that record instead.

    Failure is reported, never raised: the caller with pending work in
    hand has to be able to keep it rather than lose it to an exception.
    """
    from elspais.graph.render import render_save
    from elspais.mcp.daemon import (
        clear_automatic_save,
        clear_lost_changes,
        record_automatic_save,
    )
    from elspais.mcp.server import (
        _add_changelog_for_active_mutations,
        _get_active_mutated_reqs,
        _validate_config,
    )
    from elspais.utilities.patterns import build_resolver

    graph = state.get("graph")
    if graph is None:
        return {"success": False, "code": "save_failed", "error": "graph not available"}
    working_dir = state["working_dir"]
    config = state.get("config", {})

    pending = len(graph.mutation_log.tail(0))

    typed_config = _validate_config(config) if isinstance(config, dict) else config
    changelog_enforce = typed_config.changelog.hash_current
    if changelog_enforce and not message:
        active_mutated = _get_active_mutated_reqs(graph)
        if active_mutated:
            if not automatic:
                ids = ", ".join(sorted(active_mutated))
                return {
                    "success": False,
                    # Not a conflict and not an infrastructure failure: the
                    # caller has to supply something before this can succeed.
                    "code": "changelog_message_required",
                    "error": (
                        f"Active requirement(s) modified: {ids}. "
                        "Provide a 'message' parameter with the changelog reason."
                    ),
                }
            # A save the daemon performs has no client to prompt, and
            # leaving an Active requirement changed on disk with no
            # changelog row would leave the tree failing its own checks.
            message = f"Saved automatically by the daemon ({trigger or 'no client present'})"

    if save_branch:
        from elspais.utilities.git import create_safety_branch

        create_safety_branch(working_dir, "save-mutations")

    try:
        result = render_save(
            graph,
            working_dir,
            resolver=build_resolver(config),
            write_associates=(
                config.get("federation", {}).get("write_associates", False)
                if isinstance(config, dict)
                else False
            ),
        )
    except Exception as exc:
        return {"success": False, "code": "save_failed", "error": f"save failed: {exc!r}"}

    if result.get("success") and changelog_enforce and message:
        cl_result = _add_changelog_for_active_mutations(graph, working_dir, config, message)
        if not cl_result.get("success", True):
            return {
                "success": False,
                "code": "save_failed",
                "error": cl_result.get("error", "Changelog author resolution failed"),
            }

    if result.get("success"):
        files = result.get("saved_count") or 0
        if automatic:
            record_automatic_save(
                working_dir,
                pending,
                files if isinstance(files, int) else 0,
                trigger=trigger,
            )
        else:
            clear_automatic_save(working_dir)
            # The tree on disk is now one a client wrote deliberately, so
            # an older finding about a process that died holding changes
            # has been overtaken: it described the tree the client has
            # just replaced (REQ-o00074-J).
            clear_lost_changes(working_dir)
    return result


# Implements: REQ-p00004-J, REQ-p00004-O, REQ-p00015-F, REQ-d00205-B
def rebuild_shared_graph(state: SharedServerState, full: bool = False) -> dict[str, Any]:
    """Rebuild the live graph from disk and publish it. The only rebuild path.

    Every surface that reloads the graph reaches this function: the viewer's
    automatic freshness check, its ``/api/reload`` and ``/api/revert`` routes,
    the MCP ``refresh_graph`` tool, and the MCP tools that rebuild after
    writing spec files. A rebuild is not just a graph swap — it must also
    re-read configuration from disk (REQ-p00004-J) and leave the tool's
    change-detection state agreeing with what it just loaded (REQ-p00004-O).
    Those two steps are exactly what nine hand-rolled copies of this logic
    kept forgetting, which is why there is now one copy.

    Publication order inside the lock is config, then graph, then
    ``build_time``, then the post-rebuild hooks — hooks read config through
    the holder, so they must see the new one.

    Nothing is published unless the new graph exists. A configuration that
    cannot be parsed is reported as a failure with the previously served
    graph left in place: replacing a working graph with an empty one because
    a config file was mistyped would be a silent, destructive substitution
    (REQ-p00015-F).

    Args:
        state: The process-wide holder. ``working_dir`` names the repo root.
        full: Accepted for caller compatibility; no cache is retained between
            builds, so a full rebuild is what every call already performs.

    Returns:
        ``{"success", "message", "node_count", "config"}``. ``config`` is the
        rebuilt federation's root repo config, already published into the
        holder (REQ-d00205-B); callers need not sync it themselves.
    """
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    working_dir = state["working_dir"]

    try:
        new_config = get_config(start_path=working_dir, quiet=True)
        new_graph = build_graph(config=new_config, repo_root=working_dir)
    except Exception as exc:
        message = str(exc)
        if ".elspais.toml" in message:
            # Config parse error — a descriptive report, not a stack trace,
            # and the previous graph stays live.
            return {
                "success": False,
                "message": f"CONFIG ERROR: {message}",
                "node_count": 0,
                "config": None,
            }
        raise

    if hasattr(new_graph, "load_comments"):
        new_graph.load_comments()

    # REQ-d00205-B: the published config is the rebuilt federation's root repo
    # config, which is the one every global operation reads.
    root_config = None
    iter_repos = getattr(new_graph, "iter_repos", None)
    if iter_repos is not None:
        for entry in iter_repos():
            if entry.config is not None:
                root_config = entry.config
                break

    with state.write_lock:
        state["config"] = root_config if root_config is not None else new_config
        state["graph"] = new_graph
        state["build_time"] = time.time()
        for hook in state.post_rebuild_hooks:
            try:
                hook()
            except Exception as exc:
                # The new graph is already published and is what every reader
                # now sees, so this rebuild did happen and must be reported as
                # having happened (REQ-p00015-F). A hook that could not bring
                # its own state forward is a visible warning, not a retraction
                # of a swap that is already visible.
                name = getattr(hook, "__qualname__", repr(hook))
                print(
                    f"warning: post-rebuild hook {name} failed after the graph "
                    f"was published: {exc}",
                    file=sys.stderr,
                )

    return {
        "success": True,
        "message": "Graph refreshed successfully",
        "node_count": new_graph.node_count(),
        "config": root_config,
    }
