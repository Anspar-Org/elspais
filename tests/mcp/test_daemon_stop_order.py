# Verifies: REQ-o00075-B+E
"""The order in which a daemon is stopped, verifying REQ-o00075.

A daemon's state record is what clients use to find it (REQ-o00075-E),
so the record must describe a process a client would reach and must be
present for as long as one is serving. Removing it before the process it
describes has exited breaks both halves at once: for that window the
record is absent while the daemon serves, so a second command starts a
second process in one working tree (REQ-o00075-B), and a successor that
boots first reads the predecessor's still-standing dirty sentinel as
evidence of a process that died holding work.

The daemon is faked with a sleeping subprocess: what is under test is the
ordering, not the daemon.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from elspais.mcp.daemon import StopOutcome, _daemon_json_path, stop_daemon, wait_for_daemon_exit


def _write_record(repo_root: Path, pid: int, port: int = 65000) -> Path:
    path = _daemon_json_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "port": port, "version": "test"}))
    return path


class TestStopWaitsForTheProcess:
    def test_REQ_o00075_E_record_outlives_the_process_it_describes(self, tmp_path):
        """Validates REQ-o00075-E: the record is removed only once the
        process it describes is gone, so it never names a process a client
        cannot reach and never goes missing while one is serving."""
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        # This test process is the child's real parent. wait_for_daemon_exit
        # reaps a pid it owns as part of its liveness check (see its
        # docstring), which is what lets this assertion hold without a
        # background reaper of its own.
        record = _write_record(tmp_path, proc.pid)

        assert stop_daemon(tmp_path) is StopOutcome.STOPPED
        assert proc.poll() is not None, "stop_daemon returned while the process was alive"
        assert not record.exists()

    def test_REQ_o00075_B_ignored_stop_is_escalated_until_the_process_goes(self, tmp_path):
        """Validates REQ-o00075-B: the deadline on a stop belongs to whoever
        asked for it. A daemon that will not go on being asked -- a drain a
        held-open client keeps from ever finishing -- is escalated to a kill
        it cannot decline, so one working tree is not left with a process
        that neither stops nor can be replaced."""
        # SIGTERM ignored: the process outlives the request to stop. It
        # prints once the handler is actually installed, and the test
        # blocks on that line before sending SIGTERM -- without it, the
        # signal can arrive during interpreter startup, before
        # signal.signal() has run, and the process dies of the *default*
        # disposition instead of proving anything about the ignore.
        ignore_sigterm = (
            "import signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('ready', flush=True); "
            "time.sleep(30)"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", ignore_sigterm],
            stdout=subprocess.PIPE,
            text=True,
        )
        proc.stdout.readline()
        record = _write_record(tmp_path, proc.pid)
        try:
            assert stop_daemon(tmp_path, timeout=1.0) is StopOutcome.STOPPED
            assert proc.poll() is not None, "stop_daemon returned while the process was alive"
            assert not record.exists(), "the record outlived the process it describes"
        finally:
            proc.kill()
            proc.wait()

    def test_REQ_o00075_E_no_record_is_not_an_error(self, tmp_path):
        """Validates REQ-o00075-E: stopping when nothing is serving reports
        that nothing was stopped rather than failing."""
        assert stop_daemon(tmp_path) is StopOutcome.NOT_RUNNING

    def test_REQ_o00075_E_unreaped_zombie_is_seen_as_gone_promptly(self):
        """Validates REQ-o00075-E: a process that exited but was never
        reaped -- a zombie -- still answers kill(pid, 0), which is not
        enough on its own to tell "gone" from "still serving". The wait
        must see it as gone at once, not only once its own timeout has run
        out, or a description of "still serving" would outlive the process
        it names."""
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        # Deliberately left unreaped: no proc.wait()/poll() here. Give it a
        # moment to actually exit before polling, so the assertion below is
        # about detection speed, not about whether it had exited yet.
        time.sleep(0.3)
        start = time.monotonic()
        assert wait_for_daemon_exit({"pid": proc.pid}, timeout=4.0) is True
        elapsed = time.monotonic() - start
        assert elapsed < 3.0, (
            "wait_for_daemon_exit ran to (near) the full timeout instead of "
            "seeing the unreaped exit promptly"
        )

    def test_REQ_o00075_B_unreaped_child_counts_as_stopped(self, tmp_path):
        """Validates REQ-o00075-B: stop_daemon must not mistake a zombie
        for a still-serving process -- that would refuse a restart, or a
        viewer takeover, over a daemon that has actually already gone."""
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        time.sleep(0.3)  # let it exit and sit unreaped
        record = _write_record(tmp_path, proc.pid)

        assert stop_daemon(tmp_path) is StopOutcome.STOPPED
        assert not record.exists()


class TestTheStopperOwnsTheDeadline:
    """Validates REQ-o00075-B and REQ-o00075-E: the deadline on a stop, and
    the escalation when it passes, belong to whoever asked for the stop --
    the pattern every process supervisor uses. The daemon holds no deadline
    of its own, so a drain a held-open client keeps from finishing ends here
    or not at all.
    """

    def test_REQ_o00075_B_cooperative_daemon_is_never_killed(self, tmp_path, monkeypatch):
        """Validates REQ-o00075-B: escalation is what happens when the ask
        was not enough. A daemon that stops on the ask writes what it holds
        on the way out, and a kill it never earned would cut that short."""
        import signal as signal_module

        from elspais.mcp import daemon as daemon_module

        sent: list[int] = []
        real_kill = daemon_module.os.kill

        def _record(pid: int, sig: int) -> None:
            sent.append(sig)
            real_kill(pid, sig)

        monkeypatch.setattr(daemon_module.os, "kill", _record)
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        _write_record(tmp_path, proc.pid)

        assert stop_daemon(tmp_path) is StopOutcome.STOPPED
        assert signal_module.SIGKILL not in sent, f"a cooperative daemon was killed: {sent}"

    def test_REQ_o00075_B_the_kill_comes_only_after_the_wait(self, tmp_path, monkeypatch):
        """Validates REQ-o00075-B: the wait before the kill is the margin a
        save runs in. Writing a spec file is not atomic, so a kill that
        arrived first would truncate one -- the loss the whole stop routine
        is arranged to prevent."""
        import signal as signal_module
        import time as time_module

        from elspais.mcp import daemon as daemon_module

        # Slow enough to be measurable, far shorter than any real save.
        wait_seconds = 1.0
        marks: list[tuple[int, float]] = []
        start = time_module.monotonic()

        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                "print('ready',flush=True);time.sleep(30)",
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert proc.stdout.readline().strip() == "ready"
        _write_record(tmp_path, proc.pid)

        real_kill = daemon_module.os.kill

        def _record(pid: int, sig: int) -> None:
            if sig in (signal_module.SIGTERM, signal_module.SIGKILL):
                marks.append((sig, time_module.monotonic() - start))
            real_kill(pid, sig)

        monkeypatch.setattr(daemon_module.os, "kill", _record)
        try:
            assert stop_daemon(tmp_path, timeout=wait_seconds) is StopOutcome.STOPPED
        finally:
            proc.kill()
            proc.wait()

        assert [sig for sig, _ in marks] == [
            signal_module.SIGTERM,
            signal_module.SIGKILL,
        ], f"the stop did not ask before it escalated: {marks}"
        assert (
            marks[1][1] - marks[0][1] >= wait_seconds
        ), f"the kill arrived before the wait was over: {marks}"


class TestRecordIsNeverSeenHalfWritten:
    def test_REQ_o00075_E_concurrent_reader_never_sees_a_torn_record(self, tmp_path):
        """Validates REQ-o00075-E: what a client locates describes the process
        it would reach. A reader landing mid-write on a truncate-then-write
        sees invalid JSON, and this record's reader deletes it on that
        conclusion -- so a healthy daemon becomes undiscoverable while it is
        still serving, and the next command starts a second one for the same
        working tree."""
        import json
        import threading
        import time

        from elspais.mcp.daemon import _write_json_atomic

        record = tmp_path / "daemon.json"
        payload = {
            "pid": 4242,
            "port": 40000,
            "clients": [{"kind": "pid", "id": i} for i in range(40)],
        }
        record.write_text(json.dumps(payload))

        stop = threading.Event()

        def writer() -> None:
            while not stop.is_set():
                _write_json_atomic(record, payload)

        t = threading.Thread(target=writer, daemon=True)
        t.start()
        try:
            torn = 0
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                try:
                    json.loads(record.read_text())
                except (json.JSONDecodeError, FileNotFoundError):
                    torn += 1
            assert torn == 0, f"{torn} torn reads: the record was seen half-written"
        finally:
            stop.set()
            t.join(timeout=2)


class TestStopDistinguishesGoneFromRefusing:
    def test_REQ_o00075_B_daemon_that_exits_first_is_not_a_refusal(self, tmp_path):
        """Validates REQ-o00075-B: a caller refuses to start a second process
        only when one is still serving. A daemon that exits between the
        caller's own look and the stop is gone -- reporting that as "it would
        not stop" fails a command that had in fact succeeded, which is the
        race a single boolean could not express."""
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        _write_record(tmp_path, proc.pid)

        outcome = stop_daemon(tmp_path)

        assert outcome is StopOutcome.NOT_RUNNING
        assert outcome.is_gone, "an already-exited daemon must not read as a refusal"

    def test_REQ_o00075_B_only_a_daemon_that_survived_the_kill_reads_as_still_running(
        self, tmp_path, monkeypatch
    ):
        """Validates REQ-o00075-B: the one outcome that must stop a caller is
        a process that is there after everything the stopper can do. A refusal
        to stop is no longer enough on its own -- that is escalated -- so this
        is a process still present after the kill, which is what a caller
        cannot start a second daemon alongside.

        Nothing in a test can hold a process against SIGKILL (an
        uninterruptible wait in the kernel can, which is why the outcome
        exists), so the wait reports what such a process would."""
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                "print('ready',flush=True);time.sleep(30)",
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert proc.stdout.readline().strip() == "ready"
        record = _write_record(tmp_path, proc.pid)
        monkeypatch.setattr("elspais.mcp.daemon.wait_for_daemon_exit", lambda *a, **k: False)
        try:
            outcome = stop_daemon(tmp_path, timeout=1.0)
            assert outcome is StopOutcome.STILL_RUNNING
            assert not outcome.is_gone
            assert record.exists(), "the record was removed while the process was still there"
        finally:
            proc.kill()
            proc.wait()


class TestStartRefusesToJoinALiveDaemon:
    def test_REQ_o00075_B_start_refuses_when_the_predecessor_will_not_go(
        self, tmp_path, monkeypatch
    ):
        """Validates REQ-o00075-B: at most one process serves a working tree.
        Callers stop the old daemon before starting a new one, so this guard
        is unreachable through them -- which is the point. The invariant
        cannot rest on every future caller of a function named start_daemon
        remembering to check first."""
        import pytest as _pytest

        from elspais.mcp.daemon import start_daemon

        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                "print('ready',flush=True);time.sleep(30)",
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert proc.stdout.readline().strip() == "ready"
        record = _write_record(tmp_path, proc.pid)
        # A process nothing can remove: the stop escalates to a kill, and
        # the predecessor is still there afterwards.
        monkeypatch.setattr("elspais.mcp.daemon.wait_for_daemon_exit", lambda *a, **k: False)
        try:
            with _pytest.raises(RuntimeError, match="did not stop"):
                start_daemon(tmp_path, ttl_minutes=30)
            assert record.exists(), "the live daemon's record must survive the refusal"
        finally:
            proc.kill()
            proc.wait()
