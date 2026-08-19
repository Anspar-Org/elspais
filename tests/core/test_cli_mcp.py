# Verifies: REQ-d00214-A+B+C+D+E+F+G, REQ-o00076-K
"""Tests for elspais mcp install/uninstall/env subcommands."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from elspais.cli import (
    _claude_desktop_config_path,
    _http_registration_url,
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

_STANDIN_PORT = 49999


@pytest.fixture(autouse=True)
def address_seam(monkeypatch):
    """Stand in for everything that settles a tree's address.

    Working out where a tree is reached touches the machine the tests run
    on: it reads and writes that tree's reservation record, and the
    launcher it used to go through would leave a serving process behind.
    None of that belongs to a test of what gets registered, and a test
    that reserved an address in the developer's own tree would move the
    address that tree is really reached at. So every part of the seam is
    replaced here for the whole module -- including the launcher, which
    the registration path must never reach at all -- and the tests that
    care about an address drive it through the returned handle.
    """
    seam = SimpleNamespace(
        reserved=MagicMock(return_value=_STANDIN_PORT),
        free=MagicMock(return_value=_STANDIN_PORT),
        reserve=MagicMock(),
        ensure=MagicMock(side_effect=AssertionError("registering must not start a daemon")),
    )
    monkeypatch.setattr("elspais.mcp.daemon.reserved_port", seam.reserved)
    monkeypatch.setattr("elspais.mcp.daemon.free_port", seam.free)
    monkeypatch.setattr("elspais.mcp.daemon.reserve_port", seam.reserve)
    monkeypatch.setattr("elspais.mcp.daemon.ensure_daemon", seam.ensure)
    return seam


class TestHttpRegistrationUrl:
    """What an http registration names, and when it can name an address.

    A registration is written once and read at every launch, so what it
    names decides whether a client that never re-reads its configuration
    can still reach the tree it is working in.
    """

    # Verifies: REQ-o00076-K
    def test_REQ_o00076_K_project_scope_names_the_trees_own_address(
        self, address_seam, monkeypatch, tmp_path
    ):
        """Validates REQ-o00076-K: a registration bound to one project
        names one working tree, and the address of a tree outlives the
        process serving it -- a replacement is reached where its
        predecessor was. An address that stable can be written down,
        which is what spares the client arranging anything before it is
        launched. The address written is this tree's, so the reservation
        consulted is the one belonging to the root that was found.
        """
        monkeypatch.setattr("elspais.config.find_git_root", lambda *args: tmp_path)
        address_seam.reserved.return_value = 52101

        url = _http_registration_url(global_scope=False)

        assert url == "http://127.0.0.1:52101/mcp"
        address_seam.reserved.assert_called_once_with(tmp_path)

    # Verifies: REQ-o00076-K
    def test_REQ_o00076_K_an_existing_reservation_is_reused_not_replaced(
        self, address_seam, monkeypatch, tmp_path
    ):
        """Validates REQ-o00076-K: the whole worth of a written-down
        address is that it does not move. A tree that already has one
        must be registered at that one, so nothing goes looking for a
        fresh port and nothing overwrites what is on record -- either
        would hand a second client a different address for the same tree
        and strand the first client's configuration.
        """
        monkeypatch.setattr("elspais.config.find_git_root", lambda *args: tmp_path)
        address_seam.reserved.return_value = 52101

        url = _http_registration_url(global_scope=False)

        assert url == "http://127.0.0.1:52101/mcp"
        address_seam.free.assert_not_called()
        address_seam.reserve.assert_not_called()

    # Verifies: REQ-o00076-K
    def test_REQ_o00076_K_a_first_registration_settles_an_address_and_keeps_it(
        self, address_seam, monkeypatch, tmp_path
    ):
        """Validates REQ-o00076-K: a tree being registered for the first
        time has no address yet, so one is chosen from what is free. It
        is of no use unless it is kept: an address recomputed on each
        reading would differ every time it was asked for, which is
        precisely the moving address the assertion forbids. Recording it
        is what makes the second answer the same as the first.
        """
        monkeypatch.setattr("elspais.config.find_git_root", lambda *args: tmp_path)
        recorded: dict = {}
        address_seam.reserve.side_effect = lambda root, port: recorded.__setitem__(root, port)
        address_seam.reserved.side_effect = recorded.get
        address_seam.free.return_value = 53311

        first = _http_registration_url(global_scope=False)
        second = _http_registration_url(global_scope=False)

        assert first == "http://127.0.0.1:53311/mcp"
        assert second == first
        address_seam.free.assert_called_once()
        address_seam.reserve.assert_called_once_with(tmp_path, 53311)

    # Verifies: REQ-o00076-K
    def test_REQ_o00076_K_global_scope_names_the_variable_and_settles_nothing(
        self, address_seam, monkeypatch, tmp_path
    ):
        """Validates REQ-o00076-K: one registration shared by every
        project cannot name an address, because the address a client
        needs is decided by the tree it was started in and that is not
        known when the registration is written. The variable defers the
        answer to the shell that launches the client. The tree the
        install happened to run in must not be consulted either --
        reserving its address would settle a tree nobody asked about on
        behalf of a registration that will never name it.
        """
        monkeypatch.setattr("elspais.config.find_git_root", lambda *args: tmp_path)

        url = _http_registration_url(global_scope=True)

        assert url == "${ELSPAIS_MCP_URL}"
        address_seam.reserved.assert_not_called()
        address_seam.reserve.assert_not_called()

    # Verifies: REQ-o00076-K
    def test_REQ_o00076_K_falls_back_to_the_variable_outside_a_repository(
        self, address_seam, monkeypatch
    ):
        """Validates REQ-o00076-K: with no repository around the install
        there is no working tree whose address could be written down, so
        there is nothing to write. The variable is the honest answer --
        an invented literal would send the client to a port nothing
        serves, which is worse than a variable the shell has to fill in.
        """
        monkeypatch.setattr("elspais.config.find_git_root", lambda *args: None)

        url = _http_registration_url(global_scope=False)

        assert url == "${ELSPAIS_MCP_URL}"
        address_seam.reserved.assert_not_called()
        address_seam.free.assert_not_called()

    # Verifies: REQ-o00076-K
    def test_REQ_o00076_K_registering_never_starts_a_serving_process(
        self, address_seam, monkeypatch, tmp_path
    ):
        """Validates REQ-o00076-K: settling an address says where a tree
        will be served, not that it is being served now. A machine being
        set up would otherwise be left running a daemon nobody asked for,
        for a tree whose graph nobody has read. The address is reserved
        rather than obtained from a running process precisely so the two
        can be separated, and the launcher here fails the test if the
        registration path reaches it.
        """
        monkeypatch.setattr("elspais.config.find_git_root", lambda *args: tmp_path)

        assert _http_registration_url(global_scope=False).startswith("http://127.0.0.1:")
        assert _http_registration_url(global_scope=True) == "${ELSPAIS_MCP_URL}"
        address_seam.ensure.assert_not_called()


class TestMcpInstallLocal:
    """test_mcp_install_local — verifies correct claude mcp add command."""

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A, REQ-o00076-K
    def test_REQ_o00076_K_install_registers_this_trees_address_by_default(
        self, mock_which, mock_run, address_seam, monkeypatch, tmp_path
    ):
        """Validates REQ-o00076-K: a registration made for one project
        names that project's tree, and the address of a tree survives the
        process serving it -- a replacement is reached where its
        predecessor was. So the address can be written into the
        registration outright, and a client that expands its
        configuration only once still reaches whatever serves the tree
        later. Registering it is what spares the reader arranging
        anything in the shell before launching the client. The transport
        is deliberately not passed here: http being the default is part
        of the behaviour under test, since a stdio default would put
        every client back on a private process that nothing renews.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        monkeypatch.setattr("elspais.config.find_git_root", lambda *args: tmp_path)
        address_seam.reserved.return_value = 53007

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
            "http://127.0.0.1:53007/mcp",
        ]

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A, REQ-o00076-K
    def test_mcp_install_local_stdio(self, mock_which, mock_run, address_seam):
        """A client that cannot speak http is still registered as a server
        command it owns, so asking for stdio produces the `--` separated
        invocation rather than an address. It owns the process outright,
        so no tree's address is settled on its behalf -- reserving one
        for a client that will never dial it would claim a port nothing
        is going to serve.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = _mcp_install(global_scope=False, transport="stdio")

        assert result == 0
        address_seam.reserved.assert_not_called()
        address_seam.reserve.assert_not_called()
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
    # Verifies: REQ-d00214-A, REQ-o00076-K
    def test_REQ_o00076_K_global_install_registers_the_address_variable(
        self, mock_which, mock_run, address_seam, monkeypatch, tmp_path
    ):
        """Validates REQ-o00076-K: a registration installed for every
        project is read by clients started in trees this install knows
        nothing about, each reached at its own address. The one thing it
        can name is the variable those clients' shells fill in, and the
        tree the install ran in gets no say -- writing its address here
        would point every other project at it.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        monkeypatch.setattr("elspais.config.find_git_root", lambda *args: tmp_path)

        result = _mcp_install(global_scope=True)

        assert result == 0
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "/usr/bin/claude",
            "mcp",
            "add",
            "elspais",
            "--transport",
            "http",
            "--scope",
            "user",
            "${ELSPAIS_MCP_URL}",
        ]
        address_seam.reserve.assert_not_called()

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


class TestMcpInstallReplacesExisting:
    """test_mcp_install_replaces_existing — verifies a name the client
    already holds is re-registered rather than reported as a conflict.
    """

    @staticmethod
    def _result(returncode: int, stderr: str = "") -> MagicMock:
        return MagicMock(returncode=returncode, stdout="", stderr=stderr)

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A
    def test_mcp_install_does_not_remove_when_add_succeeds(self, mock_which, mock_run):
        """A registration that lands first time is the ordinary case, and
        nothing is removed on the way -- removal happens only after the
        client has said the name is taken.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = self._result(0)

        result = _mcp_install(global_scope=False)

        assert result == 0
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "add" in cmd
        assert "remove" not in cmd

    @pytest.mark.parametrize(
        "stderr_text",
        [
            "MCP server elspais already exists",
            "MCP server elspais Already Exists",
            "MCP SERVER ELSPAIS ALREADY EXISTS in local config",
        ],
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A
    def test_mcp_install_replaces_existing_registration(
        self, mock_which, mock_run, stderr_text, capsys
    ):
        """Re-running install is how transport is changed, and the client
        refuses a name it already holds. The taken name is removed and the
        add retried, so the caller gets the registration it asked for
        instead of a conflict it would resolve by hand. The client's
        wording is not fixed, so the match reads the message case-blind.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.side_effect = [
            self._result(1, stderr_text),
            self._result(0),
            self._result(0),
        ]

        result = _mcp_install(global_scope=False)

        assert result == 0
        assert mock_run.call_count == 3
        first_add = mock_run.call_args_list[0][0][0]
        removal = mock_run.call_args_list[1][0][0]
        retry_add = mock_run.call_args_list[2][0][0]
        assert removal == ["/usr/bin/claude", "mcp", "remove", "elspais", "-s", "local"]
        assert first_add[:4] == ["/usr/bin/claude", "mcp", "add", "elspais"]
        assert retry_add == first_add
        captured = capsys.readouterr()
        assert "Replaced the existing elspais MCP registration." in captured.out

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-A
    def test_mcp_install_replacement_uses_the_requested_scope(self, mock_which, mock_run):
        """The registration being replaced is the one in the scope being
        installed into, so a user-scope install must remove the user-scope
        entry -- removing the local one would leave the conflict in place.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.side_effect = [
            self._result(1, "already exists"),
            self._result(0),
            self._result(0),
        ]

        result = _mcp_install(global_scope=True)

        assert result == 0
        removal = mock_run.call_args_list[1][0][0]
        assert removal == ["/usr/bin/claude", "mcp", "remove", "elspais", "-s", "user"]
        for index in (0, 2):
            add_cmd = mock_run.call_args_list[index][0][0]
            assert add_cmd[add_cmd.index("--scope") + 1] == "user"

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-G
    def test_mcp_install_leaves_registration_alone_on_other_errors(
        self, mock_which, mock_run, capsys
    ):
        """Removal is conditional on the name being taken, never
        speculative: a failure for any other reason must leave whatever
        was registered exactly as it was.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.side_effect = [self._result(1, "connection refused")]

        result = _mcp_install(global_scope=False)

        assert result == 1
        assert mock_run.call_count == 1
        assert "remove" not in mock_run.call_args_list[0][0][0]
        captured = capsys.readouterr()
        assert "connection refused" in captured.err

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-G
    def test_mcp_install_reports_a_removal_that_failed(self, mock_which, mock_run, capsys):
        """When the taken name cannot be removed there is nothing to retry
        against, so the add is not reattempted and both failures are
        reported -- the conflict and the reason it could not be cleared.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.side_effect = [
            self._result(1, "server elspais already exists"),
            self._result(1, "no write access to the config"),
        ]

        result = _mcp_install(global_scope=False)

        assert result == 1
        assert mock_run.call_count == 2
        captured = capsys.readouterr()
        assert "server elspais already exists" in captured.err
        assert "no write access to the config" in captured.err

    @patch("subprocess.run")
    @patch("shutil.which")
    # Verifies: REQ-d00214-G
    def test_mcp_install_says_nothing_is_registered_when_the_retry_fails(
        self, mock_which, mock_run, capsys
    ):
        """The old registration is already gone by the time the retry
        runs, so a failed retry leaves nothing registered at all. A caller
        who read only "failed" would assume the old one survived and never
        think to register again, so the state is stated outright.
        """
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.side_effect = [
            self._result(1, "already exists"),
            self._result(0),
            self._result(1, "transport not supported"),
        ]

        result = _mcp_install(global_scope=False)

        assert result == 1
        assert mock_run.call_count == 3
        captured = capsys.readouterr()
        assert "transport not supported" in captured.err
        assert "nothing is registered" in captured.err
        assert "Re-run" in captured.err


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

    A registration shared by every project names `${ELSPAIS_MCP_URL}`
    rather than any one tree's address, and only reaches a daemon if
    something fills the variable in at launch. That something is this
    command, evaluated by the shell that starts the client, which is why
    its output has to be exactly what a shell will accept and why nothing
    else may reach stdout.
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
