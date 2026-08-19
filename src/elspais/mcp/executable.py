"""Identity of the program this process is running, and noticing it change.

A process that serves a working tree loads its program once and then
answers from it for as long as it lives. Nothing it does afterwards
re-reads that program, so when the tool is installed afresh beneath a
running process -- which, for a tree the tool is itself installed from,
is what editing a source file amounts to -- the process goes on giving
answers computed by the program it started with.

This is not the same condition as the traced content going stale, and it
is deliberately kept apart from it. Content the tool traces changes
constantly and is answered by rebuilding the graph; the installed
program cannot be answered that way at all. The word "code" is avoided
throughout for the same reason: in this estate it already means the
source files being traced.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from pathlib import Path

#: Seconds between checks. Cheap enough to be frequent: the walk costs
#: single-digit milliseconds over a package of this size, against a graph
#: rebuild measured in seconds.
DEFAULT_INTERVAL_SECONDS = 2.0

#: Consecutive polls a new identity must persist for before it counts as
#: settled (REQ-o00077-E). One act -- an editor writing a directory, a
#: branch switch, a build emitting sources -- arrives as many separate
#: file writes, and answering each in turn would disturb a serving
#: process repeatedly while the program beneath it was still moving.
DEFAULT_SETTLE_POLLS = 2

_SKIP_DIR_NAMES = frozenset({"__pycache__"})
_SKIP_SUFFIXES = frozenset({".pyc", ".pyo"})


def installed_root() -> Path:
    """Directory the tool is installed from.

    Resolved through the imported package rather than from any working
    tree, because the two coincide only in an editable install -- which
    is the case this module exists for, and therefore exactly the case
    where confusing them would go unnoticed.
    """
    import elspais

    return Path(elspais.__file__).resolve().parent


def installation_can_change() -> bool:
    """True where the installed program can move while a process runs.

    An installation whose files are fixed until it is replaced wholesale
    cannot go stale beneath a running process, so nothing here applies to
    one and no process running from one pays to watch for it. What
    remains is an installation that resolves to a working tree, where
    editing a source file installs a new program by the same act.

    Read from the packaging metadata rather than guessed at: a tree that
    merely happens to sit beside the package is not what the tool is
    running.
    """
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        recorded = distribution("elspais").read_text("direct_url.json")
    except (PackageNotFoundError, OSError):
        return False
    if not recorded:
        return False
    try:
        import json

        return bool(json.loads(recorded).get("dir_info", {}).get("editable"))
    except (ValueError, AttributeError):
        return False


# Implements: REQ-o00077-A
def compute_executable_hash(root: Path | None = None) -> str:
    """Digest every file the tool is installed from.

    Package data counts, not only modules: the documentation topics and
    templates shipped inside the package decide what the tool answers
    just as its modules do.

    Note that ``pyproject.toml`` lies outside this root, so bumping the
    version does not on its own move this digest -- the recorded version
    and this digest answer different questions and are compared
    separately.

    Returns:
        16-char hex digest (first 8 bytes of SHA-256), or "" if the root
        cannot be read at all.
    """
    root = root if root is not None else installed_root()
    h = hashlib.sha256()
    try:
        paths = sorted(
            p
            for p in root.rglob("*")
            if p.is_file()
            and p.suffix not in _SKIP_SUFFIXES
            and not _SKIP_DIR_NAMES.intersection(p.relative_to(root).parts)
        )
    except OSError:
        return ""
    seen = False
    for p in paths:
        try:
            blob = p.read_bytes()
        except OSError:
            continue
        # Length-delimit both fields: concatenated variable-length blobs
        # are ambiguous, and one file's tail could otherwise stand in for
        # the next file's head.
        rel = str(p.relative_to(root)).encode("utf-8", "surrogateescape")
        h.update(len(rel).to_bytes(4, "big"))
        h.update(rel)
        h.update(len(blob).to_bytes(8, "big"))
        h.update(blob)
        seen = True
    if not seen:
        return ""
    return h.hexdigest()[:16]


class ExecutableWatcher:
    """Watches for the installed program moving out from under this process.

    Polls rather than subscribing to filesystem events: a poll costs
    milliseconds over a package of this size, needs no third-party
    dependency and no per-directory watch descriptor, and the settling
    rule REQ-o00077-E asks for falls out of it rather than having to be
    built on top.

    The decision is separated from the thread so it can be exercised
    directly: ``poll()`` is the whole rule, and ``start()`` only arranges
    to call it.
    """

    def __init__(
        self,
        read_hash: Callable[[], str] = compute_executable_hash,
        baseline: str | None = None,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        settle_polls: int = DEFAULT_SETTLE_POLLS,
        on_settled: Callable[[str], None] | None = None,
    ) -> None:
        self._read_hash = read_hash
        # Established on first use rather than here: constructing a
        # server must stay free, and the baseline is only meaningful
        # from the moment this process starts answering.
        self._baseline_value = baseline
        self._interval = interval_seconds
        self._settle_polls = max(1, settle_polls)
        #: Called with the new identity when a run of changes settles.
        #: Public because the response differs by how the process is
        #: serving, and only the caller that started it knows which.
        self.on_settled = on_settled
        self._candidate: str | None = None
        self._stable = 0
        self._settled: str | None = None
        self._announced: str | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def baseline(self) -> str:
        """Identity of the program this process is actually running."""
        if self._baseline_value is None:
            self._baseline_value = self._read_hash()
        return self._baseline_value

    @property
    def settled_difference(self) -> str | None:
        """The differing identity once it has stopped moving, else None.

        Sticky: a program that has been replaced beneath this process
        stays replaced, and no amount of further polling makes this
        process the one that was installed.
        """
        with self._lock:
            return self._settled

    # Implements: REQ-o00077-E
    def poll(self) -> str | None:
        """Take one reading. Returns the new identity when a run settles.

        Returns None on every other call, including further readings of
        an already-settled difference -- one run of changes causes one
        response however many files it touched (REQ-o00077-E).
        """
        baseline = self.baseline
        current = self._read_hash()
        if not current:
            return None  # unreadable; report nothing rather than a false change
        with self._lock:
            if current == baseline:
                # Reverted before settling, or never moved.
                self._candidate, self._stable, self._settled = None, 0, None
                return None
            if current == self._candidate:
                self._stable += 1
            else:
                self._candidate, self._stable = current, 1
            if self._stable < self._settle_polls:
                return None
            self._settled = current
            if self._announced == current:
                return None
            self._announced = current
        if self.on_settled is not None:
            self.on_settled(current)
        return current

    def start(self) -> None:
        if self._thread is not None:
            return
        _ = self.baseline  # establish before the first reading can be taken
        self._thread = threading.Thread(
            target=self._run, name="elspais-executable-watch", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.poll()
            except Exception:  # noqa: BLE001
                # A watcher that dies takes the protection with it and
                # says nothing. Keep polling; a reading that failed once
                # is not evidence about the next one.
                continue


_WATCHER: ExecutableWatcher | None = None
_WATCHER_LOCK = threading.Lock()


def watcher() -> ExecutableWatcher:
    """The watcher for this process.

    Process-scoped rather than per-server or per-working-tree, because
    what it watches is process-scoped: one process runs one program, and
    it runs the same one whichever tree it is serving or however many
    servers it hosts.
    """
    global _WATCHER
    with _WATCHER_LOCK:
        if _WATCHER is None:
            _WATCHER = ExecutableWatcher()
        return _WATCHER


def install_watcher(replacement: ExecutableWatcher | None) -> None:
    """Replace the process watcher. For tests driving ``poll()`` directly."""
    global _WATCHER
    with _WATCHER_LOCK:
        _WATCHER = replacement


# Implements: REQ-o00077-A
def difference() -> dict[str, str] | None:
    """What this process runs versus what is installed, or None if they agree.

    Facts only: the two identities, and no verdict about what the
    difference is worth. What it is worth depends on what the reader was
    about to do with the answer, which this cannot know.
    """
    w = watcher()
    settled = w.settled_difference
    if settled is None:
        return None
    return {"running": w.baseline, "installed": settled}
