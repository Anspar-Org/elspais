# Implements: REQ-p00001-A
"""Tests for shell tab-completion setup."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from elspais.commands.completion import (
    _COMPLETION_MARKER,
    _detect_shell,
    _get_rc_file,
    _install,
    _snippet_for,
    _uninstall,
)


class TestDetectShell:
    """Tests for _detect_shell()."""

    def test_REQ_p00001_A_detects_bash(self):
        with patch.dict(os.environ, {"SHELL": "/bin/bash"}):
            assert _detect_shell() == "bash"

    def test_REQ_p00001_A_detects_zsh(self):
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}):
            assert _detect_shell() == "zsh"

    def test_REQ_p00001_A_detects_fish(self):
        with patch.dict(os.environ, {"SHELL": "/usr/bin/fish"}):
            assert _detect_shell() == "fish"

    def test_REQ_p00001_A_detects_tcsh(self):
        with patch.dict(os.environ, {"SHELL": "/bin/tcsh"}):
            assert _detect_shell() == "tcsh"

    def test_REQ_p00001_A_defaults_to_bash_for_unknown(self):
        with patch.dict(os.environ, {"SHELL": "/bin/unknown"}):
            assert _detect_shell() == "bash"

    def test_REQ_p00001_A_defaults_to_bash_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _detect_shell() == "bash"


class TestGetRcFile:
    """Tests for _get_rc_file()."""

    def test_REQ_p00001_A_bash_rc_file(self):
        assert _get_rc_file("bash") == Path.home() / ".bashrc"

    def test_REQ_p00001_A_zsh_rc_file(self):
        assert _get_rc_file("zsh") == Path.home() / ".zshrc"

    def test_REQ_p00001_A_fish_rc_file(self):
        assert _get_rc_file("fish") == Path.home() / ".config" / "fish" / "config.fish"

    def test_REQ_p00001_A_tcsh_rc_file(self):
        assert _get_rc_file("tcsh") == Path.home() / ".tcshrc"

    def test_REQ_p00001_A_unknown_defaults_to_bashrc(self):
        assert _get_rc_file("nushell") == Path.home() / ".bashrc"


class TestSnippetFor:
    """Tests for _snippet_for()."""

    def test_REQ_p00001_A_bash_snippet_contains_marker(self):
        assert _COMPLETION_MARKER in _snippet_for("bash")

    def test_REQ_p00001_A_fish_snippet_uses_source(self):
        assert "source" in _snippet_for("fish")

    def test_REQ_p00001_A_tcsh_snippet_uses_eval(self):
        assert "eval" in _snippet_for("tcsh")


class TestInstall:
    """Tests for _install() writing to rc files."""

    def test_REQ_p00001_A_install_appends_snippet(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bashrc", delete=False) as f:
            f.write("# existing content\n")
            f.flush()
            rc_path = Path(f.name)

        with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
            result = _install("bash")

        assert result == 0
        content = rc_path.read_text()
        assert _COMPLETION_MARKER in content
        assert "existing content" in content
        rc_path.unlink()

    def test_REQ_p00001_A_install_idempotent(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bashrc", delete=False) as f:
            f.write(f"# existing\n{_snippet_for('bash')}")
            f.flush()
            rc_path = Path(f.name)

        with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
            result = _install("bash")

        assert result == 0
        content = rc_path.read_text()
        assert content.count(_COMPLETION_MARKER) == 1
        rc_path.unlink()

    def test_REQ_p00001_A_install_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rc_path = Path(tmpdir) / ".bashrc"
            with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
                result = _install("bash")

            assert result == 0
            assert rc_path.exists()
            assert _COMPLETION_MARKER in rc_path.read_text()


class TestUninstall:
    """Tests for _uninstall() removing from rc files."""

    def test_REQ_p00001_A_uninstall_removes_snippet(self):
        snippet = _snippet_for("bash")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bashrc", delete=False) as f:
            f.write(f"# before\n\n{snippet}# after\n")
            f.flush()
            rc_path = Path(f.name)

        with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
            result = _uninstall("bash")

        assert result == 0
        content = rc_path.read_text()
        assert _COMPLETION_MARKER not in content
        assert "# before" in content
        assert "# after" in content
        rc_path.unlink()

    def test_REQ_p00001_A_uninstall_noop_when_not_installed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bashrc", delete=False) as f:
            f.write("# no completion here\n")
            f.flush()
            rc_path = Path(f.name)

        with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
            result = _uninstall("bash")

        assert result == 0
        rc_path.unlink()

    def test_REQ_p00001_A_uninstall_noop_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rc_path = Path(tmpdir) / ".bashrc"
            with patch("elspais.commands.completion._get_rc_file", return_value=rc_path):
                result = _uninstall("bash")

            assert result == 0
