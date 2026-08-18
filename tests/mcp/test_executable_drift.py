# Verifies: REQ-o00077-A+B+C+E
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
from elspais.mcp.executable import ExecutableWatcher, compute_executable_hash
from elspais.mcp.server import _guard_executable_drift


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

    def test_REQ_o00077_C_nothing_held_is_not_this_guards_business(self):
        """Validates REQ-o00077-C: the refusal is confined to held work.
        A moved program with nothing pending is answered by replacing the
        process, not by refusing its clients."""
        self._drifted()

        assert _guard_executable_drift(_FakeState(pending=0), "search") is None

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
