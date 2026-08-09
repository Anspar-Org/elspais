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

from elspais.mcp.daemon import _daemon_json_path, stop_daemon, wait_for_daemon_exit


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

        assert stop_daemon(tmp_path) is True
        assert proc.poll() is not None, "stop_daemon returned while the process was alive"
        assert not record.exists()

    def test_REQ_o00075_B_ignored_stop_keeps_its_record(self, tmp_path):
        """Validates REQ-o00075-B: a daemon that ignores the stop keeps its
        record, so a caller cannot start a second process for the same
        working tree while the first is still serving."""
        # SIGTERM ignored: the process outlives the stop request. It
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
            assert stop_daemon(tmp_path, timeout=1.0) is False
            assert record.exists(), "the record was removed while the process was still serving"
        finally:
            proc.kill()
            proc.wait()

    def test_REQ_o00075_E_no_record_is_not_an_error(self, tmp_path):
        """Validates REQ-o00075-E: stopping when nothing is serving reports
        that nothing was stopped rather than failing."""
        assert stop_daemon(tmp_path) is False

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

        assert stop_daemon(tmp_path) is True
        assert not record.exists()
