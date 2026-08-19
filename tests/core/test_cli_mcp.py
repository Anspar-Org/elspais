# Verifies: REQ-d00214-A+B+C+D+E+F+G, REQ-o00076-K
"""Tests for elspais mcp install/uninstall/env subcommands."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from elspais.cli import (
    _claude_desktop_config_path,
    _mcp_install,
    _mcp_install_desktop,
    _mcp_uninstall,
    _mcp_uninstall_desktop,
)
from elspais.commands.daemon_cmd import run_env

_has_claude = shutil.which("claude") is not None
_has_elspais = shutil.which("elspais") is not None
_inside_claude_code = os.environ.get("CLAUDECODE") == "1"
_skip_e2e = pytest.mark.skipif(
    not (_has_claude and _has_elspais) or _inside_claude_code,
    reason="requires claude and elspais on PATH, cannot run inside Claude Code session",
)


class TestMcpInstallLocal:
    """test_mcp_install_local — verifies correct claude mcp add command."""

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A, REQ-o00076-K
    def test_REQ_o00076_K_install_registers_the_address_variable_by_default(
        self, mock_which, mock_run
    ):
        """Validates REQ-o00076-K: a client registered once must go on
        reaching this working tree after the process serving it has been
        replaced. A literal port baked into the registration cannot do
        that -- a client that expands its configuration only at launch
        would keep dialling an address nothing answers at. Registering
        the variable instead defers the answer to the shell that starts
        the client, so each launch picks up whatever address the tree is
        being served at now. The transport is deliberately not passed
        here: http being the default is the behaviour under test, since a
        stdio default would put every client back on a private process
        that nothing renews.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = _mcp_install(global_scope=False)

        assert result == 0
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "/usr/bin/claude",
            "mcp",
            "add",
            "elspais",
            "--transport",
            "http",
            "${ELSPAIS_MCP_URL}",
        ]

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A
    def test_mcp_install_local_stdio(self, mock_which, mock_run):
        """A client that cannot speak http is still registered as a server
        command it owns, so asking for stdio produces the `--` separated
        invocation rather than an address.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = _mcp_install(global_scope=False, transport="stdio")

        assert result == 0
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "/usr/bin/claude",
            "mcp",
            "add",
            "elspais",
            "--transport",
            "stdio",
            "--",
            "elspais",
            "mcp",
            "serve",
        ]

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A
    def test_mcp_install_local_prints_tip(self, mock_which, mock_run, capsys):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        _mcp_install(global_scope=False)

        captured = capsys.readouterr()
        assert "Tip: Use --global" in captured.out


class TestMcpInstallGlobal:
    """test_mcp_install_global — verifies --scope user is passed."""

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A
    def test_mcp_install_global(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = _mcp_install(global_scope=True)

        assert result == 0
        cmd = mock_run.call_args[0][0]
        assert "--scope" in cmd
        assert "user" in cmd

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A
    def test_mcp_install_global_no_tip(self, mock_which, mock_run, capsys):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        _mcp_install(global_scope=True)

        captured = capsys.readouterr()
        assert "Tip:" not in captured.out
        assert "all projects (user scope)" in captured.out


class TestMcpUninstall:
    """test_mcp_uninstall — verifies claude mcp remove is called."""

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-B
    def test_mcp_uninstall(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = _mcp_uninstall()

        assert result == 0
        cmd = mock_run.call_args[0][0]
        assert cmd == ["/usr/bin/claude", "mcp", "remove", "elspais"]

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-B
    def test_mcp_uninstall_global(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = _mcp_uninstall(global_scope=True)

        assert result == 0
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "/usr/bin/claude",
            "mcp",
            "remove",
            "elspais",
            "--scope",
            "user",
        ]

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-B
    def test_mcp_uninstall_prints_message(self, mock_which, mock_run, capsys):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        _mcp_uninstall()

        captured = capsys.readouterr()
        assert "elspais MCP server removed." in captured.out


class TestMcpInstallErrors:
    """test_mcp_install_claude_not_found / elspais_not_found."""

    @patch("shutil.which")
    # Verifies: REQ-d00214-C
    def test_mcp_install_claude_not_found(self, mock_which, capsys):
        mock_which.return_value = None

        result = _mcp_install()

        assert result == 1
        captured = capsys.readouterr()
        assert "'claude' not found" in captured.err

    @patch("shutil.which")
    # Verifies: REQ-d00214-D
    def test_mcp_install_elspais_not_found(self, mock_which, capsys):
        def which_side_effect(name):
            if name == "claude":
                return "/usr/bin/claude"
            return None

        mock_which.side_effect = which_side_effect

        result = _mcp_install()

        assert result == 1
        captured = capsys.readouterr()
        assert "'elspais' not found" in captured.err

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-G
    def test_mcp_install_claude_command_fails(self, mock_which, mock_run, capsys):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="some error")

        result = _mcp_install()

        assert result == 1
        captured = capsys.readouterr()
        assert "some error" in captured.err

    @patch("shutil.which")
    # Verifies: REQ-d00214-C
    def test_mcp_uninstall_claude_not_found(self, mock_which, capsys):
        mock_which.return_value = None

        result = _mcp_uninstall()

        assert result == 1
        captured = capsys.readouterr()
        assert "'claude' not found" in captured.err


class TestDesktopConfigPath:
    """test_desktop_config_path — verifies platform detection."""

    @patch("platform.system", return_value="Linux")
    # Verifies: REQ-d00214-E
    def test_linux_path(self, _mock):
        path = _claude_desktop_config_path()
        assert path is not None
        assert ".config/Claude/claude_desktop_config.json" in str(path)

    @patch("platform.system", return_value="Darwin")
    # Verifies: REQ-d00214-E
    def test_macos_path(self, _mock):
        path = _claude_desktop_config_path()
        assert path is not None
        assert "Application Support/Claude/claude_desktop_config.json" in str(path)

    @patch("platform.system", return_value="FreeBSD")
    # Verifies: REQ-d00214-E
    def test_unsupported_returns_none(self, _mock):
        assert _claude_desktop_config_path() is None


class TestMcpInstallDesktop:
    """test_mcp_install_desktop — verifies config file creation/update."""

    # Verifies: REQ-d00214-F
    def test_creates_config_from_scratch(self, tmp_path, capsys):
        config_file = tmp_path / "claude_desktop_config.json"
        with patch("elspais.cli._claude_desktop_config_path", return_value=config_file):
            result = _mcp_install_desktop()

        assert result == 0
        data = json.loads(config_file.read_text())
        assert data["mcpServers"]["elspais"]["command"] == "elspais"
        assert data["mcpServers"]["elspais"]["args"] == ["mcp", "serve"]
        captured = capsys.readouterr()
        assert "registered" in captured.out

    # Verifies: REQ-d00214-F
    def test_updates_existing_config(self, tmp_path):
        config_file = tmp_path / "claude_desktop_config.json"
        existing = {"mcpServers": {"other-server": {"command": "other"}}, "extra": True}
        config_file.write_text(json.dumps(existing))

        with patch("elspais.cli._claude_desktop_config_path", return_value=config_file):
            result = _mcp_install_desktop()

        assert result == 0
        data = json.loads(config_file.read_text())
        # Preserves existing servers and extra keys
        assert "other-server" in data["mcpServers"]
        assert data["extra"] is True
        # Adds elspais
        assert data["mcpServers"]["elspais"]["command"] == "elspais"

    # Verifies: REQ-d00214-F
    def test_creates_parent_dirs(self, tmp_path):
        config_file = tmp_path / "deep" / "nested" / "claude_desktop_config.json"
        with patch("elspais.cli._claude_desktop_config_path", return_value=config_file):
            result = _mcp_install_desktop()

        assert result == 0
        assert config_file.exists()

    # Verifies: REQ-d00214-E
    def test_unsupported_platform(self, capsys):
        with patch("elspais.cli._claude_desktop_config_path", return_value=None):
            result = _mcp_install_desktop()

        assert result == 1
        assert "Unsupported platform" in capsys.readouterr().err


class TestMcpEnv:
    """`elspais mcp env` — the shell's half of the address variable.

    Installation registers `${ELSPAIS_MCP_URL}` rather than a literal
    port, which only reaches a daemon if something fills the variable in
    at launch. That something is this command, evaluated by the shell
    that starts the client, which is why its output has to be exactly
    what a shell will accept and why nothing else may reach stdout.
    """

    # Verifies: REQ-o00076-K
    def test_REQ_o00076_K_env_prints_shell_assignments_for_the_serving_address(
        self, tmp_path, capsys
    ):
        """Validates REQ-o00076-K: a client that only expands environment
        variables learns the address of the process serving this tree from
        a shell that read it for them. The output is consumed by `eval`,
        so it must carry the address the daemon is actually reachable at
        and nothing a shell would choke on -- a diagnostic on stdout would
        be executed as a command.
        """
        args = argparse.Namespace(no_start=False)

        with (
            patch("elspais.commands.daemon_cmd.find_git_root", return_value=tmp_path),
            patch("elspais.mcp.daemon.ensure_daemon", return_value=54321) as ensure,
        ):
            rc = run_env(args)

        assert rc == 0
        ensure.assert_called_once_with(tmp_path)
        out = capsys.readouterr().out
        assert "export ELSPAIS_MCP_URL=http://127.0.0.1:54321/mcp" in out
        assert "export ELSPAIS_MCP_PORT=54321" in out

    # Verifies: REQ-o00076-K
    def test_REQ_o00076_K_env_reports_no_address_rather_than_inventing_one(self, tmp_path, capsys):
        """Validates REQ-o00076-K: asked not to start anything, the command
        can only report an address if one is already being served. When no
        process serves this tree there is no address to hand out, and the
        honest answer is a non-zero status with an empty stdout -- anything
        printed there would be evaluated by the caller's shell and would
        point a client at a port nothing answers on.
        """
        args = argparse.Namespace(no_start=True)

        with (
            patch("elspais.commands.daemon_cmd.find_git_root", return_value=tmp_path),
            patch("elspais.mcp.daemon.get_daemon_info", return_value=None),
            patch("elspais.mcp.daemon.ensure_daemon", side_effect=AssertionError("must not start")),
        ):
            rc = run_env(args)

        assert rc != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "No daemon" in captured.err


class TestMcpUninstallDesktop:
    """test_mcp_uninstall_desktop — verifies config entry removal."""

    # Verifies: REQ-d00214-F
    def test_removes_entry(self, tmp_path, capsys):
        config_file = tmp_path / "claude_desktop_config.json"
        data = {"mcpServers": {"elspais": {"command": "elspais"}, "other": {"command": "x"}}}
        config_file.write_text(json.dumps(data))

        with patch("elspais.cli._claude_desktop_config_path", return_value=config_file):
            result = _mcp_uninstall_desktop()

        assert result == 0
        updated = json.loads(config_file.read_text())
        assert "elspais" not in updated["mcpServers"]
        assert "other" in updated["mcpServers"]
        assert "removed" in capsys.readouterr().out

    # Verifies: REQ-d00214-F
    def test_missing_config_file(self, tmp_path, capsys):
        config_file = tmp_path / "nonexistent.json"
        with patch("elspais.cli._claude_desktop_config_path", return_value=config_file):
            result = _mcp_uninstall_desktop()

        assert result == 0
        assert "not found" in capsys.readouterr().out

    # Verifies: REQ-d00214-F
    def test_not_registered(self, tmp_path, capsys):
        config_file = tmp_path / "claude_desktop_config.json"
        config_file.write_text(json.dumps({"mcpServers": {}}))

        with patch("elspais.cli._claude_desktop_config_path", return_value=config_file):
            result = _mcp_uninstall_desktop()

        assert result == 0
        assert "not registered" in capsys.readouterr().out


@pytest.mark.e2e
@_skip_e2e
class TestMcpInstallE2E:
    """End-to-end: install registers with claude, uninstall removes it.

    Runs the test logic in a subprocess to prevent the claude CLI from
    corrupting the parent pytest process's file descriptors (the claude
    binary writes directly to /dev/tty, which disrupts pytest's output
    capture and causes all subsequent test output to vanish).
    """

    # Verifies: REQ-d00214-A
    def test_e2e_install_and_uninstall(self):
        result = subprocess.run(
            [
                shutil.which("python") or "python",
                "-c",
                _E2E_MCP_SCRIPT,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            start_new_session=True,
        )
        assert (
            result.returncode == 0
        ), f"MCP install/uninstall e2e failed:\n{result.stdout}\n{result.stderr}"


_E2E_MCP_SCRIPT = """\
from elspais.cli import _mcp_install, _mcp_uninstall, _claude_env
import shutil, subprocess

def claude_mcp_list():
    r = subprocess.run(
        [shutil.which("claude"), "mcp", "list"],
        capture_output=True, text=True, env=_claude_env(),
    )
    return r.stdout

# Clean slate
_mcp_uninstall(global_scope=True)

try:
    # Default (http): registered against the address variable, not a command.
    rc = _mcp_install(global_scope=True)
    assert rc == 0, f"install failed with rc={rc}"
    listing = claude_mcp_list()
    assert "elspais" in listing, f"elspais not in listing: {listing}"
    _mcp_uninstall(global_scope=True)

    # stdio: still registered as a server command the client owns.
    rc = _mcp_install(global_scope=True, transport="stdio")
    assert rc == 0, f"stdio install failed with rc={rc}"
    listing = claude_mcp_list()
    assert "elspais mcp serve" in listing, f"serve not in listing: {listing}"
finally:
    _mcp_uninstall(global_scope=True)

print("OK")
"""
