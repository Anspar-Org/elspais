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
import threading
from pathlib import Path

from elspais.mcp.daemon import _daemon_json_path, stop_daemon


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
        # This test process is the child's real parent, so an exited child
        # sits as a zombie -- which still answers kill(pid, 0) -- until
        # something waits on it. A detached daemon has no such parent; init
        # reaps it, which is what lets kill(pid, 0) report it gone for
        # real. Reap in the background so the liveness check under test
        # sees the same thing it would see in production.
        threading.Thread(target=proc.wait, daemon=True).start()
        record = _write_record(tmp_path, proc.pid)

        assert stop_daemon(tmp_path) is True
        assert proc.poll() is not None, "stop_daemon returned while the process was alive"
        assert not record.exists()

    def test_REQ_o00075_B_ignored_stop_keeps_its_record(self, tmp_path):
        """Validates REQ-o00075-B: a daemon that ignores the stop keeps its
        record, so a caller cannot start a second process for the same
        working tree while the first is still serving."""
        # SIGTERM ignored: the process outlives the stop request.
        ignore_sigterm = (
            "import signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "time.sleep(30)"
        )
        proc = subprocess.Popen([sys.executable, "-c", ignore_sigterm])
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
