"""Tests for elspais mcp install/uninstall subcommands."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from elspais.cli import _claude_env, _mcp_install, _mcp_uninstall

_has_claude = shutil.which("claude") is not None
_has_elspais = shutil.which("elspais") is not None
_skip_e2e = pytest.mark.skipif(
    not (_has_claude and _has_elspais),
    reason="requires claude and elspais on PATH",
)


class TestMcpInstallLocal:
    """test_mcp_install_local — verifies correct claude mcp add command."""

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_mcp_install_local(self, mock_which, mock_run):
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
            "stdio",
            "--",
            "elspais",
            "mcp",
            "serve",
        ]

    @patch("subprocess.run")
    @patch("shutil.which")
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
    def test_mcp_uninstall(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = _mcp_uninstall()

        assert result == 0
        cmd = mock_run.call_args[0][0]
        assert cmd == ["/usr/bin/claude", "mcp", "remove", "elspais"]

    @patch("subprocess.run")
    @patch("shutil.which")
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
    def test_mcp_uninstall_prints_message(self, mock_which, mock_run, capsys):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        _mcp_uninstall()

        captured = capsys.readouterr()
        assert "elspais MCP server removed." in captured.out


class TestMcpInstallErrors:
    """test_mcp_install_claude_not_found / elspais_not_found."""

    @patch("shutil.which")
    def test_mcp_install_claude_not_found(self, mock_which, capsys):
        mock_which.return_value = None

        result = _mcp_install()

        assert result == 1
        captured = capsys.readouterr()
        assert "'claude' not found" in captured.err

    @patch("shutil.which")
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
    def test_mcp_install_claude_command_fails(self, mock_which, mock_run, capsys):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="some error")

        result = _mcp_install()

        assert result == 1
        captured = capsys.readouterr()
        assert "some error" in captured.err

    @patch("shutil.which")
    def test_mcp_uninstall_claude_not_found(self, mock_which, capsys):
        mock_which.return_value = None

        result = _mcp_uninstall()

        assert result == 1
        captured = capsys.readouterr()
        assert "'claude' not found" in captured.err


@pytest.mark.e2e
@_skip_e2e
class TestMcpInstallE2E:
    """End-to-end: install registers with claude, uninstall removes it."""

    def _claude_mcp_list(self) -> str:
        """Run ``claude mcp list`` and return stdout."""
        result = subprocess.run(
            [shutil.which("claude"), "mcp", "list"],
            capture_output=True,
            text=True,
            env=_claude_env(),
        )
        return result.stdout

    def test_e2e_install_and_uninstall(self, capsys):
        # Install at user scope so it doesn't collide with .mcp.json
        rc = _mcp_install(global_scope=True)
        assert rc == 0, capsys.readouterr().err

        listing = self._claude_mcp_list()
        # claude mcp list shows "<name>: <command> - <status>"
        assert "elspais" in listing
        assert "elspais mcp serve" in listing

        # Uninstall
        rc = _mcp_uninstall(global_scope=True)
        assert rc == 0, capsys.readouterr().err
