# Verifies: REQ-o00077-A+D+E+F
"""What a serving process owes its clients when the program beneath it moves.

A process loads its program once and answers from it until it ends. When
the tool is reinstalled beneath a running process -- which, for a tree
the tool is installed from, is what editing a source file amounts to --
every answer it goes on giving was computed by the program it started
with, and nothing in the ordinary request path notices.

These tests drive the rule directly rather than through a real thread:
``poll()`` is the whole decision, and a stub reader lets a change be
staged, held, reverted or repeated exactly. Replacing the process image
is injected everywhere it is reached, because the real one would replace
the process running the suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elspais.mcp import executable
from elspais.mcp import server as server_mod
from elspais.mcp.executable import (
    ExecutableWatcher,
    compute_executable_hash,
    installation_can_change,
)
from elspais.mcp.server import _guard_executable_drift, renew_for_installed_program
from elspais.mcp.shared_state import SharedServerState


def _reader(*values: str):
    """A hash reader yielding each value in turn, then repeating the last."""
    seq = list(values)

    def read() -> str:
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return read


class _FakeLog:
    def __init__(self, count: int) -> None:
        self._count = count

    def tail(self, _n: int) -> list[object]:
        return [object()] * self._count


class _BrokenLog:
    """A mutation log whose count cannot be taken."""

    def tail(self, _n: int) -> list[object]:
        raise RuntimeError("log unreadable")


class _FakeState(dict):
    """A holder whose process cannot be replaced without ending a session."""

    def __init__(self, pending: int = 0) -> None:
        super().__init__()
        self["graph"] = type("G", (), {"mutation_log": _FakeLog(pending)})()


def _renewable(pending: int = 0) -> _FakeState:
    """A state whose process can be replaced without ending a session.

    The HTTP daemon raises this flag on its holder; a stdio server, whose
    client reaches it over a connection that client owns, never does.
    """
    state = _FakeState(pending)
    state["renewable_unasked"] = True
    return state


@pytest.fixture(autouse=True)
def _isolate_process_watcher():
    """Keep each test's watcher out of the process-wide slot."""
    executable.install_watcher(None)
    yield
    executable.install_watcher(None)


class TestExecutableHashIdentifiesTheInstalledProgram:
    def test_REQ_o00077_A_hash_moves_when_a_shipped_file_changes(self, tmp_path):
        """Validates REQ-o00077-A: the identity has to move when the program
        does, or nothing downstream can tell that it did."""
        root = tmp_path / "pkg"
        (root / "sub").mkdir(parents=True)
        (root / "a.py").write_text("x = 1")
        (root / "sub" / "topic.md").write_text("docs")
        before = compute_executable_hash(root)

        (root / "a.py").write_text("x = 2")
        assert compute_executable_hash(root) != before

    def test_REQ_o00077_A_package_data_counts_as_the_program(self, tmp_path):
        """Validates REQ-o00077-A: shipped documentation and templates decide
        what the tool answers just as its modules do, so a change to one is a
        change to the program."""
        root = tmp_path / "pkg"
        root.mkdir()
        (root / "a.py").write_text("x = 1")
        (root / "topic.md").write_text("original")
        before = compute_executable_hash(root)

        (root / "topic.md").write_text("rewritten")
        assert compute_executable_hash(root) != before

    def test_REQ_o00077_A_bytecode_is_not_the_program(self, tmp_path):
        """Validates REQ-o00077-A: __pycache__ is written by running the
        program, so counting it would make every process report itself as
        superseded moments after starting."""
        root = tmp_path / "pkg"
        root.mkdir()
        (root / "a.py").write_text("x = 1")
        before = compute_executable_hash(root)

        cache = root / "__pycache__"
        cache.mkdir()
        (cache / "a.cpython-311.pyc").write_bytes(b"\x00\x01")
        assert compute_executable_hash(root) == before

    def test_REQ_o00077_A_rename_alone_moves_the_hash(self, tmp_path):
        """Validates REQ-o00077-A: the same bytes under a different name are a
        different program, so path and content are both bound into the digest."""
        root = tmp_path / "pkg"
        root.mkdir()
        (root / "a.py").write_text("shared")
        before = compute_executable_hash(root)

        (root / "a.py").rename(root / "b.py")
        assert compute_executable_hash(root) != before

    def test_REQ_o00077_A_unreadable_root_reports_nothing(self, tmp_path):
        """Validates REQ-o00077-A: a reading that could not be taken is not
        evidence that the program changed."""
        assert compute_executable_hash(tmp_path / "absent") == ""


class TestOnlyAMovableInstallationIsWatched:
    """Everything here is confined to an installation that resolves to a
    working tree. One whose files are fixed until it is replaced wholesale
    cannot move beneath a running process, so no such process pays to watch
    for it -- and reading that from the packaging metadata is what keeps a
    tree that merely sits beside the package from being mistaken for the
    program the tool is running."""

    def _distribution(self, monkeypatch, recorded: str | None) -> None:
        """Answer ``direct_url.json`` with ``recorded`` for any distribution."""

        class _Dist:
            def read_text(self, _name: str) -> str | None:
                return recorded

        monkeypatch.setattr("importlib.metadata.distribution", lambda _n: _Dist())

    def test_REQ_o00077_D_an_editable_installation_can_move(self, monkeypatch):
        """Validates REQ-o00077-D: this is the case the whole requirement
        exists for -- editing a source file installs a new program by the same
        act, so a process serving that tree has to be renewable out of it."""
        self._distribution(monkeypatch, json.dumps({"dir_info": {"editable": True}}))

        assert installation_can_change() is True

    def test_REQ_o00077_D_a_fixed_installation_cannot(self, monkeypatch):
        """Validates REQ-o00077-D: an installation recorded as a copy rather
        than as a tree stays put until it is replaced wholesale, so watching it
        would spend a process's time on a change that cannot happen."""
        self._distribution(monkeypatch, json.dumps({"dir_info": {"editable": False}}))

        assert installation_can_change() is False

    def test_REQ_o00077_D_an_installation_from_elsewhere_cannot(self, monkeypatch):
        """Validates REQ-o00077-D: a record naming a source that is not a
        directory at all says nothing about editability, and an absent answer
        is never read as a yes."""
        self._distribution(monkeypatch, json.dumps({"vcs_info": {"vcs": "git"}}))

        assert installation_can_change() is False

    def test_REQ_o00077_D_no_installation_record_cannot(self, monkeypatch):
        """Validates REQ-o00077-D: a wheel carries no ``direct_url.json`` at
        all, and the reader has to treat its absence as the ordinary case
        rather than as something to fail on."""
        self._distribution(monkeypatch, None)

        assert installation_can_change() is False

    def test_REQ_o00077_D_an_unfindable_distribution_cannot(self, monkeypatch):
        """Validates REQ-o00077-D: the tool can be run from a tree that was
        never installed as a distribution, and a process there must go on
        serving rather than raising out of a question it only asked to decide
        whether to watch."""
        from importlib.metadata import PackageNotFoundError

        def missing(_name):
            raise PackageNotFoundError(_name)

        monkeypatch.setattr("importlib.metadata.distribution", missing)

        assert installation_can_change() is False

    def test_REQ_o00077_D_an_unreadable_record_cannot(self, monkeypatch):
        """Validates REQ-o00077-D: a record that will not parse is not evidence
        of an editable install, and guessing from one would start a watcher
        that replaces a process on a reading nobody can account for."""
        self._distribution(monkeypatch, "{not json at all")

        assert installation_can_change() is False


class TestOneRunOfChangesCausesOneResponse:
    def test_REQ_o00077_E_change_is_not_reported_until_it_settles(self):
        """Validates REQ-o00077-E: an editor writing a directory is one act
        arriving as many writes, so a reading taken mid-write must not count."""
        w = ExecutableWatcher(read_hash=_reader("base", "mid", "final", "final"), baseline="base")

        assert w.poll() is None  # unchanged
        assert w.poll() is None  # first sighting of a change
        assert w.poll() is None  # a different value again: still moving
        assert w.poll() == "final"  # held across two readings

    def test_REQ_o00077_E_settled_change_is_announced_once(self):
        """Validates REQ-o00077-E: at most one response per run, however many
        readings follow it. Each response renews the process, so a second one
        for the same run would replace a process that had already answered."""
        w = ExecutableWatcher(read_hash=_reader("new"), baseline="base", settle_polls=1)

        assert w.poll() == "new"
        assert [w.poll() for _ in range(4)] == [None, None, None, None]

    def test_REQ_o00077_E_a_later_run_is_announced_again(self):
        """Validates REQ-o00077-E: 'once per run' is not 'once per process' --
        a second reinstall is a second run and is answered on its own."""
        w = ExecutableWatcher(
            read_hash=_reader("first", "first", "second", "second"),
            baseline="base",
            settle_polls=1,
        )

        assert w.poll() == "first"
        assert w.poll() is None
        assert w.poll() == "second"

    def test_REQ_o00077_E_change_reverted_before_settling_is_never_reported(self):
        """Validates REQ-o00077-E: a branch switched and switched back leaves
        the process running exactly what it started with."""
        w = ExecutableWatcher(read_hash=_reader("other", "base"), baseline="base")

        assert w.poll() is None
        assert w.poll() is None
        assert w.settled_difference is None

    def test_REQ_o00077_A_unreadable_reading_does_not_report_a_change(self):
        """Validates REQ-o00077-A: an empty reading is a failure to look, not
        a program that vanished."""
        w = ExecutableWatcher(read_hash=_reader(""), baseline="base", settle_polls=1)

        assert w.poll() is None
        assert w.settled_difference is None

    def test_REQ_o00077_A_difference_stays_once_settled(self):
        """Validates REQ-o00077-A: no amount of further polling makes this
        process the one that was installed."""
        w = ExecutableWatcher(read_hash=_reader("new"), baseline="base", settle_polls=1)
        w.poll()

        for _ in range(3):
            w.poll()
        assert w.settled_difference == "new"
        assert executable.difference() is None  # process slot untouched by this watcher


class TestDriftGuardRefusesOnlyWhatItMust:
    def _drifted(self) -> ExecutableWatcher:
        w = ExecutableWatcher(read_hash=_reader("new"), baseline="base", settle_polls=1)
        w.poll()
        executable.install_watcher(w)
        return w

    def test_REQ_o00077_D_a_renewable_process_says_nothing(self):
        """Validates REQ-o00077-D: where the process renews itself out of the
        difference, the tree simply goes on being served and the client never
        learns there was anything to refuse. A refusal here would take the tool
        away from a client that was about to be handed a working one."""
        self._drifted()

        assert _guard_executable_drift(_renewable(), "search") is None

    def test_REQ_o00077_D_held_work_does_not_turn_renewal_into_a_refusal(self):
        """Validates REQ-o00077-D: changes held here are carried across a
        renewal, not trapped by one, so holding them is a reason to take care
        over the replacement rather than to stop answering. A client of a
        renewable process gets the same answer whether or not it has been
        writing."""
        self._drifted()

        assert _guard_executable_drift(_renewable(pending=7), "search") is None

    def test_REQ_o00077_D_what_the_process_holds_is_not_this_guard_s_question(self):
        """Validates REQ-o00077-D: the guard decides on how the client reaches
        the process and nothing else. Asked of a holder it cannot count at all,
        it still answers -- a count it could not take must never be what
        silences a renewable process or excuses an unrenewable one."""
        self._drifted()
        uncountable = {"renewable_unasked": True}
        stdio = {}

        assert _guard_executable_drift(uncountable, "search") is None
        assert _guard_executable_drift(stdio, "search") is not None

    def test_REQ_o00077_F_an_unrenewable_process_refuses(self):
        """Validates REQ-o00077-F: renewing a process whose client reaches it
        over a connection that client owns would end the session mid-task,
        which costs more than the difference it would remove. Refusing is what
        is left, and the refusal is also the disclosure REQ-o00077-A asks for."""
        self._drifted()
        rejection = _guard_executable_drift(_FakeState(), "search")

        assert rejection is not None
        assert rejection["success"] is False
        assert rejection["code"] == "executable_changed"

    def test_REQ_o00077_F_the_refusal_names_the_action_that_renews_it(self):
        """Validates REQ-o00077-F: naming the renewing action is the whole of
        the assertion's value. A client left holding a working connection and an
        instruction can act on it; one told only that it was refused is stuck
        against a process that will refuse it again."""
        self._drifted()
        rejection = _guard_executable_drift(_FakeState(), "search")

        assert "reconnect" in rejection["hint"].lower()

    def test_REQ_o00077_F_every_request_is_refused_alike(self):
        """Validates REQ-o00077-F: the refusal covers the other requests the
        process would otherwise answer, with no request carved out of it. A
        client of an unrenewable process meets one rule rather than having to
        work out which of its calls this process will still take."""
        self._drifted()

        refused = [
            _guard_executable_drift(_FakeState(pending=2), name)
            for name in ("search", "save_mutations")
        ]

        assert [r["code"] for r in refused] == ["executable_changed", "executable_changed"]

    def test_REQ_o00077_F_unmoved_program_refuses_nothing(self):
        """Validates REQ-o00077-F: a process answering from the program it was
        installed from owes its client nothing here, however it is reached, so
        an unrenewable process is not a permanently refusing one."""
        w = ExecutableWatcher(read_hash=_reader("base"), baseline="base")
        w.poll()
        executable.install_watcher(w)

        assert _guard_executable_drift(_FakeState(pending=5), "search") is None


class TestTheProcessRunsOneProgram:
    def test_REQ_o00077_A_difference_reports_both_identities(self):
        """Validates REQ-o00077-A: facts, not a verdict -- what is running and
        what is installed, leaving what it is worth to the reader."""
        w = ExecutableWatcher(read_hash=_reader("installed"), baseline="running", settle_polls=1)
        w.poll()
        executable.install_watcher(w)

        assert executable.difference() == {"running": "running", "installed": "installed"}

    def test_REQ_o00077_A_agreement_is_reported_as_no_difference(self):
        """Validates REQ-o00077-A: a surface says nothing when there is
        nothing to say, rather than publishing an empty difference."""
        w = ExecutableWatcher(read_hash=_reader("same"), baseline="same")
        w.poll()
        executable.install_watcher(w)

        assert executable.difference() is None

    def test_REQ_o00077_A_the_installed_root_is_the_package_not_a_tree(self):
        """Validates REQ-o00077-A: resolved through the imported package, so
        that serving some other working tree cannot be mistaken for the
        program this process is running."""
        import elspais

        assert executable.installed_root() == Path(elspais.__file__).resolve().parent


class _ExecRecorder:
    """Stands in for replacing the process image, so the decision can be
    observed. The real one never returns, and inside the suite it would
    replace the process running the tests."""

    def __init__(self, on_call=None) -> None:
        self.calls = 0
        self._on_call = on_call

    def __call__(self) -> None:
        self.calls += 1
        if self._on_call is not None:
            self._on_call()


class _PersistRecorder:
    """Stands in for writing what the process holds."""

    def __init__(self, outcome: dict[str, object], on_call=None) -> None:
        self.calls: list[dict[str, object]] = []
        self._outcome = outcome
        self._on_call = on_call

    def __call__(self, _shared, **kwargs) -> dict[str, object]:
        self.calls.append(kwargs)
        if self._on_call is not None:
            self._on_call()
        return self._outcome


def _shared(pending: int | None = 0) -> SharedServerState:
    """A process holder carrying a graph that holds ``pending`` changes.

    ``pending=None`` gives a graph whose count raises.
    """
    log = _BrokenLog() if pending is None else _FakeLog(pending)
    shared = SharedServerState()
    shared["graph"] = type("G", (), {"mutation_log": log})()
    return shared


def _lock_is_held(shared: SharedServerState) -> bool:
    """Whether another thread is currently locked out of ``write_lock``.

    Asked from a second thread on purpose: ``write_lock`` is re-entrant,
    so the thread running the routine could re-acquire it and learn
    nothing about whether anybody else can.
    """
    import threading

    seen: list[bool] = []

    def probe() -> None:
        acquired = shared.write_lock.acquire(timeout=0.2)
        seen.append(acquired)
        if acquired:
            shared.write_lock.release()

    t = threading.Thread(target=probe)
    t.start()
    t.join()
    return not seen[0]


class TestTheTreeGoesOnBeingServedFromTheInstalledProgram:
    def test_REQ_o00077_D_an_empty_process_is_replaced_without_writing(self, monkeypatch):
        """Validates REQ-o00077-D: the client that most needs the tree re-served
        is the one that will never ask, so the process renews itself unasked.
        With nothing held there is nothing to preserve first, and writing anyway
        would put a changelog entry and a saved-by record against a tree nobody
        had changed."""
        persist = _PersistRecorder({"success": True})
        monkeypatch.setattr(server_mod, "persist_pending", persist)
        exec_fn = _ExecRecorder()
        shared = _shared(pending=0)

        result = renew_for_installed_program(shared, lambda: shared["graph"], exec_fn)

        assert result == "renewing"
        assert exec_fn.calls == 1
        assert persist.calls == []

    def test_REQ_o00077_D_held_work_is_carried_across_the_renewal(self, monkeypatch):
        """Validates REQ-o00077-D: changes held here exist nowhere else, so the
        renewal writes them first and then goes ahead. Stopping short of the
        replacement would leave the tree served by the superseded program, and
        replacing without writing would take the work with it -- carrying it is
        what lets the assertion ask for both."""
        persist = _PersistRecorder({"success": True})
        monkeypatch.setattr(server_mod, "persist_pending", persist)
        exec_fn = _ExecRecorder()
        shared = _shared(pending=3)

        result = renew_for_installed_program(shared, lambda: shared["graph"], exec_fn)

        assert result == "renewing"
        assert exec_fn.calls == 1
        assert len(persist.calls) == 1
        assert persist.calls[0]["automatic"] is True
        assert persist.calls[0]["trigger"]

    def test_REQ_o00077_D_work_that_could_not_be_written_stays_where_it_is(self, monkeypatch):
        """Validates REQ-o00077-D: a renewal must never cost work. When the
        write failed the changes are still only in this process, so it keeps
        serving from the program it started with and a client can still save
        through it -- the superseded program is the lesser of the two harms."""
        persist = _PersistRecorder({"success": False, "error": "disk full"})
        monkeypatch.setattr(server_mod, "persist_pending", persist)
        exec_fn = _ExecRecorder()
        shared = _shared(pending=1)

        result = renew_for_installed_program(shared, lambda: shared["graph"], exec_fn)

        assert result == "save_failed"
        assert exec_fn.calls == 0

    def test_REQ_o00077_D_a_failed_write_is_disclosed(self, monkeypatch, capsys):
        """Validates REQ-o00077-D: a renewal that quietly did not happen leaves
        the operator believing the tree is served by the installed program when
        it is not, and leaves unsaved work sitting in a process nobody knows to
        empty. Both are stated where a watcher will see them."""
        monkeypatch.setattr(
            server_mod,
            "persist_pending",
            _PersistRecorder({"success": False, "error": "disk full"}),
        )
        shared = _shared(pending=1)

        renew_for_installed_program(shared, lambda: shared["graph"], _ExecRecorder())

        err = capsys.readouterr().err
        assert "disk full" in err
        assert "NOT renewing" in err

    def test_REQ_o00077_D_an_uncountable_process_is_left_alone(self, monkeypatch):
        """Validates REQ-o00077-D: 'holds nothing' has to be established, not
        assumed. Renewing on a count that could not be taken risks replacing a
        process holding the only copy of somebody's work before it has been
        written, so an unknown is never read as nothing."""
        persist = _PersistRecorder({"success": True})
        monkeypatch.setattr(server_mod, "persist_pending", persist)
        exec_fn = _ExecRecorder()
        shared = _shared(pending=None)

        result = renew_for_installed_program(shared, lambda: shared["graph"], exec_fn)

        assert result == "unknown"
        assert exec_fn.calls == 0
        assert persist.calls == []

    def test_REQ_o00077_D_a_graph_that_cannot_be_reached_is_also_unknown(self, monkeypatch):
        """Validates REQ-o00077-D: the same caution covers not reaching the
        graph at all. Whichever step failed, what the process holds is unknown,
        and the process stays as it is."""
        monkeypatch.setattr(server_mod, "persist_pending", _PersistRecorder({"success": True}))
        exec_fn = _ExecRecorder()
        shared = _shared(pending=0)

        def no_graph():
            raise RuntimeError("holder empty")

        assert renew_for_installed_program(shared, no_graph, exec_fn) == "unknown"
        assert exec_fn.calls == 0

    def test_REQ_o00077_D_the_count_is_taken_under_the_write_lock(self, monkeypatch):
        """Validates REQ-o00077-D: a mutation landing while the count is being
        taken would otherwise be lost -- counted as absent, then carried off by
        a replacement that wrote nothing. Holding the lock across the reading is
        what puts every change either inside the count or after the decision."""
        monkeypatch.setattr(server_mod, "persist_pending", _PersistRecorder({"success": True}))
        shared = _shared(pending=0)
        observed: list[bool] = []

        def graph_fn():
            observed.append(_lock_is_held(shared))
            return shared["graph"]

        renew_for_installed_program(shared, graph_fn, _ExecRecorder())

        assert observed == [True]

    def test_REQ_o00077_D_the_replacement_is_reached_under_the_same_lock(self, monkeypatch):
        """Validates REQ-o00077-D: counting and writing under the lock and then
        releasing it before the replacement would reopen the gap it was taken to
        close, admitting a change between the last write and the process image
        going away. The reading, the write and the replacement are one critical
        section."""
        shared = _shared(pending=2)
        persisted: list[bool] = []
        replaced: list[bool] = []
        monkeypatch.setattr(
            server_mod,
            "persist_pending",
            _PersistRecorder(
                {"success": True}, on_call=lambda: persisted.append(_lock_is_held(shared))
            ),
        )

        renew_for_installed_program(
            shared,
            lambda: shared["graph"],
            _ExecRecorder(on_call=lambda: replaced.append(_lock_is_held(shared))),
        )

        assert persisted == [True]
        assert replaced == [True]

    def test_REQ_o00077_D_the_lock_is_released_once_the_decision_is_made(self, monkeypatch):
        """Validates REQ-o00077-D: the routine runs on a watcher thread beside
        everything else the process is doing, and a decision not to replace
        leaves that process serving. A lock it never gave back would stall every
        writer on a process that had decided to carry on."""
        monkeypatch.setattr(server_mod, "persist_pending", _PersistRecorder({"success": True}))
        shared = _shared(pending=None)

        renew_for_installed_program(shared, lambda: shared["graph"], _ExecRecorder())

        assert _lock_is_held(shared) is False
