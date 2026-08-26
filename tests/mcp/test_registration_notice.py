# Verifies: REQ-o00076-M
"""The disclosure owed when a client here would not reach this tree.

A client that cannot connect reports a refused connection or a missing
variable, and neither names what to do about it. REQ-o00076-M obliges the
tool to report the condition; saying it only where somebody runs a check
first means saying it after they have lost an afternoon. So it is said
where every command reaches, once per tree, with the remedy for the
condition the reader actually has.
"""

from __future__ import annotations

import json

from elspais.mcp.daemon import _daemon_dir, notify_registration


def _register(root, entry):
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"elspais": entry}}))


class TestARegistrationThatWouldNotReachThisTree:
    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_a_fixed_address_names_the_install_command(
        self, tmp_path, capsys, monkeypatch
    ):
        """A registration naming a port is read by every working tree that
        shares it, so it reaches one tree's daemon or nothing. The remedy is
        to register the variable, and the notice says so."""
        monkeypatch.delenv("ELSPAIS_MCP_URL", raising=False)
        _register(tmp_path, {"type": "http", "url": "http://127.0.0.1:40689/mcp"})

        assert notify_registration(tmp_path) is True
        out = capsys.readouterr().err
        assert "40689" in out
        assert "elspais mcp install" in out

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_an_unset_variable_names_the_command_that_sets_it(
        self, tmp_path, capsys, monkeypatch
    ):
        """The client reports a missing variable by name and stops there. What
        the reader needs is the command that supplies it, which nothing else
        tells them at the moment it matters."""
        monkeypatch.delenv("ELSPAIS_MCP_URL", raising=False)
        _register(tmp_path, {"type": "http", "url": "${ELSPAIS_MCP_URL}"})

        assert notify_registration(tmp_path) is True
        out = capsys.readouterr().err
        assert "ELSPAIS_MCP_URL" in out
        assert "elspais mcp env" in out

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_a_working_arrangement_is_not_reported(
        self, tmp_path, capsys, monkeypatch
    ):
        """Reporting the arrangement the tool asks for would train the reader
        to ignore the notice."""
        monkeypatch.setenv("ELSPAIS_MCP_URL", "http://127.0.0.1:39709/mcp")
        _register(tmp_path, {"type": "http", "url": "${ELSPAIS_MCP_URL}"})

        assert notify_registration(tmp_path) is False
        assert capsys.readouterr().err == ""

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_a_registration_naming_no_address_is_not_reported(
        self, tmp_path, capsys, monkeypatch
    ):
        """A registration that launches a process names nowhere to connect, so
        there is no address that could reach the wrong tree."""
        monkeypatch.delenv("ELSPAIS_MCP_URL", raising=False)
        _register(tmp_path, {"command": "elspais", "args": ["mcp", "serve"]})

        assert notify_registration(tmp_path) is False
        assert capsys.readouterr().err == ""

    # Verifies: REQ-o00076-M
    def test_REQ_o00076_M_the_notice_does_not_repeat(self, tmp_path, capsys, monkeypatch):
        """A disclosure repeated on every command is noise, and noise is what
        a reader learns to skip past."""
        monkeypatch.delenv("ELSPAIS_MCP_URL", raising=False)
        _register(tmp_path, {"type": "http", "url": "http://127.0.0.1:40689/mcp"})

        assert notify_registration(tmp_path) is True
        capsys.readouterr()

        assert notify_registration(tmp_path) is False
        assert capsys.readouterr().err == ""
        assert (_daemon_dir(tmp_path) / "daemon.registration-notice").exists()
