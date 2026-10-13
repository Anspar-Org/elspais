# Verifies: REQ-o00076-M, REQ-o00076-P
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
import os
import shlex
import shutil
import subprocess
import sys

import pytest

from elspais.mcp.daemon import _daemon_dir, env_instruction, notify_registration


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

    # Verifies: REQ-o00076-M, REQ-o00076-P
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
        assert env_instruction() in out

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


def _console_script(directory, name="elspais"):
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / name
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    return script


def _program_of(line):
    """The words the line runs, read the way a shell would read them."""
    prefix, suffix = 'eval "$(', ' mcp env)"'
    assert line.startswith(prefix) and line.endswith(suffix), line
    return shlex.split(line[len(prefix) : -len(suffix)])


class TestTheLineThatSetsTheAddress:
    """A bare `elspais` runs whichever installation the reader's PATH finds
    first, which need not be the program that printed the line, and that
    program would then replace this tree's daemon with itself."""

    # Verifies: REQ-o00076-P
    def test_REQ_o00076_P_a_console_script_is_named_by_its_absolute_path(
        self, tmp_path, monkeypatch
    ):
        script = _console_script(tmp_path / "venv" / "bin")
        monkeypatch.setattr(sys, "argv", [str(script), "mcp", "install"])

        assert _program_of(env_instruction()) == [str(script)]

    # Verifies: REQ-o00076-P
    def test_REQ_o00076_P_a_relative_console_script_is_made_absolute(self, tmp_path, monkeypatch):
        """The reader runs the line from wherever they are, so a path
        relative to where the program was started would name nothing."""
        script = _console_script(tmp_path / "bin")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", [os.path.join("bin", "elspais")])

        assert _program_of(env_instruction()) == [str(script)]

    # Verifies: REQ-o00076-P
    @pytest.mark.parametrize(
        "argv0",
        ["main_module", "-c", "not_executable", "other_program"],
    )
    def test_REQ_o00076_P_without_a_console_script_the_interpreter_runs_the_package(
        self, tmp_path, monkeypatch, argv0
    ):
        """`python -m elspais` and an embedding program leave no console
        script to name, and a file merely called `elspais` that cannot run,
        or a runnable file called something else, is not this program."""
        if argv0 == "main_module":
            argv0 = str(tmp_path / "elspais" / "__main__.py")
        elif argv0 == "not_executable":
            argv0 = str(tmp_path / "elspais")
            (tmp_path / "elspais").write_text("")
        elif argv0 == "other_program":
            argv0 = str(_console_script(tmp_path, name="pytest"))
        monkeypatch.setattr(sys, "argv", [argv0])
        monkeypatch.setattr(sys, "executable", "/opt/python3.12/bin/python3")

        assert _program_of(env_instruction()) == [
            "/opt/python3.12/bin/python3",
            "-m",
            "elspais",
        ]

    # Verifies: REQ-o00076-P
    def test_REQ_o00076_P_a_path_holding_a_space_stays_one_word(self, tmp_path, monkeypatch):
        script = _console_script(tmp_path / "my tools" / "bin")
        monkeypatch.setattr(sys, "argv", [str(script)])

        assert _program_of(env_instruction()) == [str(script)]

    # Verifies: REQ-o00076-P
    @pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash to evaluate the line")
    def test_REQ_o00076_P_a_shell_evaluating_the_line_runs_the_named_program(
        self, tmp_path, monkeypatch
    ):
        """The line is pasted into a shell, so the proof is a shell running
        it: the program it reaches is the one named, with `mcp env`."""
        script = tmp_path / "my tools" / "elspais"
        script.parent.mkdir()
        script.write_text('#!/bin/sh\necho "echo reached:$*"\n')
        script.chmod(0o755)
        monkeypatch.setattr(sys, "argv", [str(script)])

        ran = subprocess.run(
            ["bash", "-c", env_instruction()],
            capture_output=True,
            text=True,
            check=True,
        )

        assert ran.stdout.strip() == "reached:mcp env"
