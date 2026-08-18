# Verifies: REQ-o00077-A+B+C+D+E+F
"""What a serving process owes its clients when the program beneath it moves.

A process loads its program once and answers from it until it ends. When
the tool is reinstalled beneath a running process -- which, for a tree
the tool is installed from, is what editing a source file amounts to --
every answer it goes on giving was computed by the program it started
with, and nothing in the ordinary request path notices.

These tests drive the rule directly rather than through a real thread:
``poll()`` is the whole decision, and a stub reader lets a change be
staged, held, reverted or repeated exactly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.mcp import executable
from elspais.mcp import server as server_mod
from elspais.mcp.executable import ExecutableWatcher, compute_executable_hash
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


class _FakeState(dict):
    def __init__(self, pending: int) -> None:
        super().__init__()
        self["graph"] = type("G", (), {"mutation_log": _FakeLog(pending)})()


def _renewable(pending: int) -> _FakeState:
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
        readings follow it."""
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

    def test_REQ_o00077_C_held_work_under_a_moved_program_is_refused(self):
        """Validates REQ-o00077-C: answers would come from the program as it
        was, and the two remedies that would avoid saying so are both closed."""
        self._drifted()
        rejection = _guard_executable_drift(_FakeState(pending=3), "search")

        assert rejection is not None
        assert rejection["code"] == "executable_changed"
        assert rejection["success"] is False

    def test_REQ_o00077_A_refusal_states_how_much_is_held(self):
        """Validates REQ-o00077-A: the refusal is the disclosure, and one that
        understates what is at stake is a warning that reads as reassurance."""
        self._drifted()
        rejection = _guard_executable_drift(_FakeState(pending=7), "search")

        assert rejection["held_mutations"] == 7
        assert "7" in rejection["error"]

    def test_REQ_o00077_B_the_request_that_resolves_it_stays_available(self):
        """Validates REQ-o00077-B: a process that will not accept the request
        to write what it holds has trapped it, which is the loss the refusal
        exists to prevent."""
        self._drifted()

        assert _guard_executable_drift(_FakeState(pending=3), "save_mutations") is None

    def test_REQ_o00077_D_a_clean_renewable_process_says_nothing(self):
        """Validates REQ-o00077-D: where the process can be replaced without
        ending anyone's session and holds nothing that would be lost by it,
        there is no refusal to deliver -- the tree is simply re-served, and the
        client never learns there was anything to refuse. This is also where C
        stops: nothing held is not that assertion's case."""
        self._drifted()

        assert _guard_executable_drift(_renewable(pending=0), "search") is None

    def test_REQ_o00077_F_a_clean_unrenewable_process_still_refuses(self):
        """Validates REQ-o00077-F: standing down here would take the tool out of
        the client's session altogether, and a client whose connection vanished
        mid-task can only discover that it has. Refusing is what is left, and it
        is refused with nothing held."""
        self._drifted()
        rejection = _guard_executable_drift(_FakeState(pending=0), "search")

        assert rejection is not None
        assert rejection["success"] is False
        assert rejection["code"] == "executable_changed"
        assert rejection["held_mutations"] == 0

    def test_REQ_o00077_F_the_refusal_names_the_action_that_renews_it(self):
        """Validates REQ-o00077-F: naming the renewing action is the whole of
        the assertion's value. A client left holding a working connection and an
        instruction can act on it; one told only that it was refused is stuck
        against a process that will refuse it again."""
        self._drifted()
        rejection = _guard_executable_drift(_FakeState(pending=0), "search")

        assert "reconnect" in rejection["hint"].lower()

    def test_REQ_o00077_B_persisting_stays_available_with_nothing_held(self):
        """Validates REQ-o00077-B: the exemption is written against the request,
        not against the reason for refusing, so it survives F as it does C. A
        client meeting F still has to be able to reach the one request that
        empties the process."""
        self._drifted()

        assert _guard_executable_drift(_FakeState(pending=0), "save_mutations") is None

    def test_REQ_o00077_F_the_answer_is_the_same_whether_work_is_held(self):
        """Validates REQ-o00077-F: F and C reach the same behaviour from
        opposite conditions on purpose, so a client of an unrenewable process
        meets one rule rather than two and never has to work out which of them
        it is under."""
        self._drifted()
        clean = _guard_executable_drift(_FakeState(pending=0), "search")
        holding = _guard_executable_drift(_FakeState(pending=4), "search")

        assert clean is not None and holding is not None
        assert clean["code"] == holding["code"]

    def test_REQ_o00077_C_held_work_refuses_even_where_renewal_is_open(self):
        """Validates REQ-o00077-C: being replaceable is no help while the
        process holds the only copy of a change, because the replacement would
        end it along with the process. C is read first, and D's condition only
        ever decides the case C has already let go."""
        self._drifted()
        rejection = _guard_executable_drift(_renewable(pending=3), "search")

        assert rejection is not None
        assert rejection["code"] == "executable_changed"
        assert rejection["held_mutations"] == 3

    def test_REQ_o00077_C_unmoved_program_refuses_nothing(self):
        """Validates REQ-o00077-C: pending work under the program this process
        started with is not a problem at all."""
        w = ExecutableWatcher(read_hash=_reader("base"), baseline="base")
        w.poll()
        executable.install_watcher(w)

        assert _guard_executable_drift(_FakeState(pending=5), "search") is None

    def test_REQ_o00077_C_unreadable_pending_count_refuses_nothing(self):
        """Validates REQ-o00077-C: this guard protects held work, so a count
        it could not take is not evidence that any is held."""
        self._drifted()
        broken = {"graph": type("G", (), {"mutation_log": None})()}

        assert _guard_executable_drift(broken, "search") is None


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


class _ExitRecorder:
    """Stands in for ending the process, so the decision can be observed."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


class _BrokenLog:
    """A mutation log whose count cannot be taken."""

    def tail(self, _n: int) -> list[object]:
        raise RuntimeError("log unreadable")


def _shared(pending: int | None = 0) -> SharedServerState:
    """A process holder carrying a graph that holds ``pending`` changes.

    ``pending=None`` gives a graph whose count raises. No working
    directory is set, so committing to stop writes nothing to disk.
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


class TestNothingHeldIsRenewedWithoutBeingAsked:
    def test_REQ_o00077_D_held_work_keeps_the_process_serving(self, monkeypatch):
        """Validates REQ-o00077-D: renewal is for the case where nothing is at
        risk. A process holding changes nothing else can see would end them by
        standing down, so it stays and leaves the client to be told."""
        calls: list[str] = []
        monkeypatch.setattr(
            server_mod, "finalize_shutdown", lambda *a, **k: calls.append("stop") or {}
        )
        exit_fn = _ExitRecorder()
        shared = _shared(pending=3)

        assert renew_for_installed_program(shared, lambda: shared["graph"], exit_fn) == "held"
        assert exit_fn.calls == 0
        assert calls == []
        assert shared.is_shutting_down is False

    def test_REQ_o00077_D_uncountable_work_keeps_the_process_serving(self, monkeypatch):
        """Validates REQ-o00077-D: 'holds no changes' has to be established, not
        assumed. A count that could not be taken is no evidence the process is
        empty, and standing down on it would end the only copy of somebody's
        work."""
        calls: list[str] = []
        monkeypatch.setattr(
            server_mod, "finalize_shutdown", lambda *a, **k: calls.append("stop") or {}
        )
        exit_fn = _ExitRecorder()
        shared = _shared(pending=None)

        assert renew_for_installed_program(shared, lambda: shared["graph"], exit_fn) == "unknown"
        assert exit_fn.calls == 0
        assert calls == []
        assert shared.is_shutting_down is False

    def test_REQ_o00077_D_a_graph_that_cannot_be_reached_is_also_unknown(self, monkeypatch):
        """Validates REQ-o00077-D: the same caution covers not reaching the
        graph at all. Whichever step failed, what the process holds is unknown,
        and an unknown is never read as nothing."""
        calls: list[str] = []
        monkeypatch.setattr(
            server_mod, "finalize_shutdown", lambda *a, **k: calls.append("stop") or {}
        )
        exit_fn = _ExitRecorder()
        shared = _shared(pending=0)

        def no_graph():
            raise RuntimeError("holder empty")

        assert renew_for_installed_program(shared, no_graph, exit_fn) == "unknown"
        assert exit_fn.calls == 0
        assert calls == []

    def test_REQ_o00077_D_nothing_held_stands_the_process_down(self):
        """Validates REQ-o00077-D: this is the whole point of the assertion --
        the client that most needs the tree re-served is the one that will
        never ask, so the process commits to stopping on its own account and
        its record says so, leaving the successor to whoever comes next."""
        exit_fn = _ExitRecorder()
        shared = _shared(pending=0)

        result = renew_for_installed_program(shared, lambda: shared["graph"], exit_fn)

        assert result == "standing_down"
        assert exit_fn.calls == 1
        assert shared.is_shutting_down is True
        assert shared.shutdown_finalized is True

    def test_REQ_o00077_D_a_failed_save_leaves_the_process_usable(self, monkeypatch):
        """Validates REQ-o00077-D: renewal must never cost work. When the
        accounting could not be written the changes are still only here, so the
        process keeps serving and a client can still save through it -- exactly
        the case D was confined to avoiding, met on the way out."""
        monkeypatch.setattr(
            server_mod,
            "finalize_shutdown",
            lambda *a, **k: {"success": False, "error": "disk full", "pending": 1},
        )
        exit_fn = _ExitRecorder()
        shared = _shared(pending=0)

        result = renew_for_installed_program(shared, lambda: shared["graph"], exit_fn)

        assert result == "save_failed"
        assert exit_fn.calls == 0

    def test_REQ_o00077_D_a_failed_save_is_disclosed(self, monkeypatch, capsys):
        """Validates REQ-o00077-D: a renewal that quietly did not happen leaves
        the operator believing the tree is served by the installed program when
        it is not, so the failure is stated where a watcher will see it."""
        monkeypatch.setattr(
            server_mod,
            "finalize_shutdown",
            lambda *a, **k: {"success": False, "error": "disk full", "pending": 1},
        )
        shared = _shared(pending=0)

        renew_for_installed_program(shared, lambda: shared["graph"], _ExitRecorder())

        err = capsys.readouterr().err
        assert "disk full" in err
        assert "still serving" in err

    def test_REQ_o00077_D_the_count_is_taken_under_the_write_lock(self):
        """Validates REQ-o00077-D: a mutation landing while the count is being
        taken would otherwise be lost -- counted as absent, then ended with the
        process. Holding the lock across the reading is what puts every change
        either inside the count or after the decision."""
        shared = _shared(pending=0)
        observed: list[bool] = []

        def graph_fn():
            observed.append(_lock_is_held(shared))
            return shared["graph"]

        renew_for_installed_program(shared, graph_fn, _ExitRecorder())

        assert observed == [True]

    def test_REQ_o00077_D_the_decision_is_taken_under_the_same_lock(self, monkeypatch):
        """Validates REQ-o00077-D: counting under the lock and then releasing it
        before committing to stop would reopen the gap it was taken to close, so
        the reading and the decision are one critical section."""
        shared = _shared(pending=0)
        observed: list[bool] = []

        def fake_finalize(*_a, **_k):
            observed.append(_lock_is_held(shared))
            return {"success": True, "pending": 0, "saved": False}

        monkeypatch.setattr(server_mod, "finalize_shutdown", fake_finalize)

        renew_for_installed_program(shared, lambda: shared["graph"], _ExitRecorder())

        assert observed == [True]

    def test_REQ_o00077_D_the_lock_is_released_when_the_decision_is_made(self):
        """Validates REQ-o00077-D: the routine runs on a watcher thread beside
        everything else the process is doing. A lock it never gave back would
        stall every writer on a process that had decided nothing was held."""
        shared = _shared(pending=0)

        renew_for_installed_program(shared, lambda: shared["graph"], _ExitRecorder())

        assert _lock_is_held(shared) is False
