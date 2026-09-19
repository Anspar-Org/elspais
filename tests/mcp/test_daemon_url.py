# Verifies: REQ-o00076-C, REQ-o00076-E
"""A server mounted under a prefix is reached under it by every reader of
its record.

A server started with a base path answers nothing at the root of its port.
Its record therefore names the prefix, and every command that turns the
record into an address builds it under that prefix -- the unsaved-work
probe, the client registration, the save and stop requests, the doctor's
pending count, the CLI's graph queries, the announced MCP address and the
viewer's own port-conflict probe. The fake server here answers only under
the prefix it is given, so a reader that addressed the root would get a
404 and the reader's fallback (None, 0, False) instead of the answer.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from elspais.mcp import daemon as dm

_PREFIXES = ["", "/w/abc"]


class _RecordingServer:
    """An HTTP server answering JSON only under ``prefix``, recording paths."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.paths: list[str] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                server.paths.append(self.path)
                route = self.path.split("?", 1)[0]
                if not route.startswith(server.prefix + "/"):
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error": "not found"}')
                    return
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                body = {
                    "mutation_count": 2,
                    "tip": "tip-1",
                    "attached": True,
                    "success": True,
                    "node_counts": {"requirement": 1},
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            do_GET = _answer
            do_POST = _answer

            def log_message(self, *_args) -> None:  # quiet
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> _RecordingServer:
        self.thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture(params=_PREFIXES, ids=["root", "prefixed"])
def prefixed_server(request):
    with _RecordingServer(request.param) as server:
        yield server


def _info(server: _RecordingServer) -> dict:
    return {"pid": os.getpid(), "port": server.port, "base_path": server.prefix}


# Verifies: REQ-o00076-E
@pytest.mark.parametrize("base_path", _PREFIXES, ids=["root", "prefixed"])
def test_REQ_o00076_E_the_record_names_the_prefix_the_server_answers_under(tmp_path, base_path):
    dm.write_daemon_json(
        tmp_path, pid=os.getpid(), port=4321, server_type="viewer", base_path=base_path
    )
    info = dm.get_daemon_info(tmp_path)
    assert info is not None
    assert info["base_path"] == base_path
    assert dm.daemon_url(info, "/api/dirty") == f"http://127.0.0.1:4321{base_path}/api/dirty"


# Verifies: REQ-o00076-E
def test_REQ_o00076_E_the_prefix_survives_the_records_later_rewrites(tmp_path):
    """The client set and the config hash are republished over the record
    while the server runs; neither rewrite drops where the server answers."""
    dm.write_daemon_json(
        tmp_path, pid=os.getpid(), port=4321, server_type="viewer", base_path="/w/abc"
    )
    dm.record_daemon_clients(tmp_path, [os.getpid()])
    (tmp_path / ".elspais.toml").write_text('[project]\nname = "t"\n')
    dm.refresh_daemon_config_hash(tmp_path)
    assert dm.mark_daemon_stopping(tmp_path, os.getpid())
    info = dm.get_daemon_info(tmp_path)
    assert info is not None
    assert info["base_path"] == "/w/abc"


def _reach_mutation_count(info):
    return dm.get_daemon_mutation_count(info) == 2


def _reach_attach(info):
    return dm.attach_client(info, os.getpid()) is True


def _reach_save(info):
    return dm.save_daemon_mutations(info, message="m").get("success") is True


def _reach_stop(info):
    return dm.request_daemon_stop(info, discard_changes=True).get("success") is True


def _reach_doctor(info):
    from elspais.commands import doctor

    return doctor._daemon_pending_count(info) == 2


def _reach_client(info):
    from elspais.commands._daemon_client import _try_server

    return _try_server(info, "/api/status", {"q": "1"}, "GET") is not None


def _reach_viewer_probe(info):
    from elspais.commands import viewer

    return viewer._is_elspais_server(info["port"], info["base_path"]) is True


_READERS = {
    "mutation_count": _reach_mutation_count,
    "attach_client": _reach_attach,
    "save": _reach_save,
    "stop": _reach_stop,
    "doctor_pending": _reach_doctor,
    "cli_client": _reach_client,
    "viewer_probe": _reach_viewer_probe,
}


# Verifies: REQ-o00076-C, REQ-o00076-E
@pytest.mark.parametrize("reader", list(_READERS), ids=list(_READERS))
def test_REQ_o00076_E_every_reader_reaches_the_server_under_its_prefix(prefixed_server, reader):
    server = prefixed_server
    assert _READERS[reader](_info(server)), f"{reader} did not reach the server: {server.paths}"
    assert server.paths, f"{reader} made no request"
    outside = [p for p in server.paths if not p.startswith(server.prefix + "/")]
    assert outside == [], f"{reader} addressed the server outside its prefix: {outside}"


# Verifies: REQ-o00076-E
def test_REQ_o00076_E_a_probe_at_the_root_misses_a_prefixed_viewer():
    """Why the prefix is part of the address: the same server, asked at the
    root of its port, reads as not being an elspais server at all."""
    from elspais.commands import viewer

    with _RecordingServer("/w/abc") as server:
        assert viewer._is_elspais_server(server.port) is False
        assert viewer._is_elspais_server(server.port, "/w/abc") is True


# Verifies: REQ-o00076-E, REQ-o00076-M
@pytest.mark.parametrize("base_path", _PREFIXES, ids=["root", "prefixed"])
def test_REQ_o00076_E_the_announced_mcp_address_carries_the_prefix(
    tmp_path, base_path, capsys, monkeypatch
):
    from elspais.commands import daemon_cmd

    dm.write_daemon_json(
        tmp_path, pid=os.getpid(), port=4321, server_type="viewer", base_path=base_path
    )
    monkeypatch.setattr(daemon_cmd, "find_git_root", lambda: tmp_path)
    rc = daemon_cmd.run_env(argparse.Namespace(no_start=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert f"export ELSPAIS_MCP_URL=http://127.0.0.1:4321{base_path}/mcp" in out
    assert "export ELSPAIS_MCP_PORT=4321" in out


# Verifies: REQ-o00076-E
def test_REQ_o00076_E_the_graph_source_names_where_the_server_answered():
    from elspais.commands._engine import _build_daemon_source

    prefixed = _build_daemon_source(
        {"port": 4321, "base_path": "/w/abc", "type": "viewer", "started_at": "t"}
    )
    assert prefixed["base_path"] == "/w/abc"
    assert prefixed["type"] == "viewer"
    assert "base_path" not in _build_daemon_source({"port": 4321, "base_path": ""})
