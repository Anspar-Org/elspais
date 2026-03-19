# Validates REQ-p00001-A: CLI shell completion install/uninstall commands
"""Tests for shell completion command at commands/completion.py.

Validates REQ-p00001-A: CLI entry point shell completion generation, installation,
and uninstallation with idempotent RC file management.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elspais.commands.completion import (
    _SHELL_CONFIG,
    _append_rc_block,
    _detect_shell,
    _rc_has_block,
    _remove_argcomplete_lines,
    _remove_rc_block,
    cmd_install,
    cmd_uninstall,
)


class TestDetectShell:
    """Validates REQ-p00001-A: shell auto-detection from $SHELL."""

    def test_REQ_p00001_A_detect_bash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHELL", "/bin/bash")
        assert _detect_shell() == "bash"

    def test_REQ_p00001_A_detect_zsh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHELL", "/usr/bin/zsh")
        assert _detect_shell() == "zsh"

    def test_REQ_p00001_A_detect_tcsh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHELL", "/usr/local/bin/tcsh")
        assert _detect_shell() == "tcsh"

    def test_REQ_p00001_A_detect_unknown_shell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHELL", "/usr/bin/fish")
        assert _detect_shell() is None

    def test_REQ_p00001_A_detect_empty_shell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SHELL", raising=False)
        assert _detect_shell() is None

    def test_REQ_p00001_A_detect_shell_with_deep_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SHELL", "/nix/store/abc123/bin/zsh")
        assert _detect_shell() == "zsh"


class TestRemoveArgcompleteLines:
    """Validates REQ-p00001-A: removal of stale argcomplete entries."""

    def test_REQ_p00001_A_removes_eval_line(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text(
            'export PATH="/usr/bin"\n'
            'eval "$(register-python-argcomplete elspais)"\n'
            "alias ll='ls -la'\n"
        )
        removed = _remove_argcomplete_lines(rc)
        assert removed == 1
        content = rc.read_text()
        assert "argcomplete" not in content
        assert 'export PATH="/usr/bin"' in content
        assert "alias ll='ls -la'" in content

    def test_REQ_p00001_A_removes_comment_and_eval(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text(
            "# some stuff\n"
            "# Autocompletion for elspais\n"
            'eval "$(register-python-argcomplete elspais)"\n'
            "# other stuff\n"
        )
        removed = _remove_argcomplete_lines(rc)
        assert removed == 2
        content = rc.read_text()
        assert "argcomplete" not in content
        assert "Autocompletion for elspais" not in content
        assert "# some stuff" in content
        assert "# other stuff" in content

    def test_REQ_p00001_A_preserves_unrelated_lines(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        original = "export FOO=bar\nalias g=git\n"
        rc.write_text(original)
        removed = _remove_argcomplete_lines(rc)
        assert removed == 0
        assert rc.read_text() == original

    def test_REQ_p00001_A_handles_missing_file(self, tmp_path: Path) -> None:
        rc = tmp_path / ".nonexistent"
        removed = _remove_argcomplete_lines(rc)
        assert removed == 0

    def test_REQ_p00001_A_removes_tab_completion_comment(self, tmp_path: Path) -> None:
        rc = tmp_path / ".bashrc"
        rc.write_text(
            "# elspais shell tab-completion setup\n"
            'eval "$(register-python-argcomplete elspais)"\n'
        )
        removed = _remove_argcomplete_lines(rc)
        assert removed == 2
        # Only whitespace or empty should remain
        assert "argcomplete" not in rc.read_text()


class TestRcHasBlock:
    """Validates REQ-p00001-A: detection of existing completion blocks in RC files."""

    def test_REQ_p00001_A_detects_marker(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text(
            "# some config\n"
            "# elspais shell completion\n"
            "fpath=(~/.zfunc $fpath)\n"
            "autoload -Uz compinit && compinit\n"
        )
        assert _rc_has_block(rc, "# elspais shell completion") is True

    def test_REQ_p00001_A_detects_orphaned_fpath(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text("fpath=(~/.zfunc $fpath)\nautoload -Uz compinit && compinit\n")
        assert _rc_has_block(rc, "# elspais shell completion") is True

    def test_REQ_p00001_A_returns_false_when_absent(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text("export PATH=/usr/bin\n")
        assert _rc_has_block(rc, "# elspais shell completion") is False

    def test_REQ_p00001_A_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        assert _rc_has_block(rc, "# elspais shell completion") is False


class TestAppendRcBlock:
    """Validates REQ-p00001-A: appending completion blocks to RC files."""

    def test_REQ_p00001_A_appends_to_existing_file(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text("export FOO=bar\n")
        _append_rc_block(rc, "# elspais shell completion\nfpath=(~/.zfunc $fpath)")
        content = rc.read_text()
        assert "export FOO=bar" in content
        assert "# elspais shell completion" in content
        assert content.endswith("\n")

    def test_REQ_p00001_A_appends_to_empty_file(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text("")
        _append_rc_block(rc, "# elspais shell completion")
        content = rc.read_text()
        assert content == "# elspais shell completion\n"

    def test_REQ_p00001_A_appends_to_nonexistent_file(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        _append_rc_block(rc, "# elspais shell completion")
        assert rc.read_text() == "# elspais shell completion\n"

    def test_REQ_p00001_A_adds_blank_line_separator(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text("export FOO=bar\n")
        _append_rc_block(rc, "# block")
        content = rc.read_text()
        # Should have a blank line between existing content and block
        assert "export FOO=bar\n\n# block\n" == content

    def test_REQ_p00001_A_handles_no_trailing_newline(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text("export FOO=bar")
        _append_rc_block(rc, "# block")
        content = rc.read_text()
        assert "export FOO=bar\n\n# block\n" == content


class TestRemoveRcBlock:
    """Validates REQ-p00001-A: removal of completion blocks from RC files."""

    def test_REQ_p00001_A_removes_zsh_block(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text(
            "export FOO=bar\n"
            "\n"
            "# elspais shell completion\n"
            "fpath=(~/.zfunc $fpath)\n"
            "autoload -Uz compinit && compinit\n"
            "\n"
            "alias g=git\n"
        )
        result = _remove_rc_block(rc)
        assert result is True
        content = rc.read_text()
        assert "elspais" not in content
        assert "export FOO=bar" in content
        assert "alias g=git" in content

    def test_REQ_p00001_A_removes_tcsh_block(self, tmp_path: Path) -> None:
        rc = tmp_path / ".tcshrc"
        rc.write_text(
            "set path = (/usr/bin)\n"
            "\n"
            "# elspais shell completion\n"
            "source /home/user/.config/elspais/completion.tcsh\n"
            "\n"
            "alias ls ls -la\n"
        )
        result = _remove_rc_block(rc)
        assert result is True
        content = rc.read_text()
        assert "elspais" not in content
        assert "set path" in content

    def test_REQ_p00001_A_returns_false_when_no_block(self, tmp_path: Path) -> None:
        rc = tmp_path / ".zshrc"
        rc.write_text("export FOO=bar\n")
        result = _remove_rc_block(rc)
        assert result is False

    def test_REQ_p00001_A_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        rc = tmp_path / ".nonexistent"
        result = _remove_rc_block(rc)
        assert result is False


def _make_shell_config(tmp_path: Path, shell: str) -> dict[str, Path | str | None]:
    """Build a _SHELL_CONFIG entry pointing at tmp_path locations."""
    if shell == "bash":
        return {
            "script_path": tmp_path / "completions" / "elspais",
            "rc_file": tmp_path / ".bashrc",
            "rc_block": None,
        }
    elif shell == "zsh":
        return {
            "script_path": tmp_path / ".zfunc" / "_elspais",
            "rc_file": tmp_path / ".zshrc",
            "rc_block": (
                "# elspais shell completion\n"
                "fpath=(~/.zfunc $fpath)\n"
                "autoload -Uz compinit && compinit"
            ),
        }
    else:  # tcsh
        script_path = tmp_path / ".config" / "elspais" / "completion.tcsh"
        return {
            "script_path": script_path,
            "rc_file": tmp_path / ".tcshrc",
            "rc_block": "# elspais shell completion\nsource {script_path}",
        }


class TestCmdInstall:
    """Validates REQ-p00001-A: completion install command."""

    def _patch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        shell: str,
    ) -> dict[str, Path | str | None]:
        """Monkeypatch _SHELL_CONFIG and _generate_completion for a given shell."""
        cfg = _make_shell_config(tmp_path, shell)
        patched_config = {**_SHELL_CONFIG, shell: cfg}
        monkeypatch.setattr("elspais.commands.completion._SHELL_CONFIG", patched_config)
        monkeypatch.setattr(
            "elspais.commands.completion._generate_completion",
            lambda s: f"# fake {s} completion script\n",
        )
        # Prevent _clear_zsh_compdump from touching real files
        monkeypatch.setattr("elspais.commands.completion._clear_zsh_compdump", lambda: 0)
        return cfg

    def test_REQ_p00001_A_install_zsh_writes_script(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = self._patch(monkeypatch, tmp_path, "zsh")
        # Create RC file so append works
        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text("")

        result = cmd_install("zsh")
        assert result == 0

        script_path = Path(cfg["script_path"])  # type: ignore[arg-type]
        assert script_path.exists()
        assert "fake zsh completion script" in script_path.read_text()

    def test_REQ_p00001_A_install_zsh_updates_rc(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = self._patch(monkeypatch, tmp_path, "zsh")
        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text("# existing config\n")

        result = cmd_install("zsh")
        assert result == 0

        content = rc_file.read_text()
        assert "# elspais shell completion" in content
        assert "fpath=(~/.zfunc $fpath)" in content
        assert "autoload -Uz compinit && compinit" in content

    def test_REQ_p00001_A_install_bash_no_rc_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = self._patch(monkeypatch, tmp_path, "bash")
        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text("# existing config\n")

        result = cmd_install("bash")
        assert result == 0

        # bash has rc_block=None, so RC file should be untouched
        assert rc_file.read_text() == "# existing config\n"

    def test_REQ_p00001_A_install_unsupported_shell(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = cmd_install("fish")
        assert result == 1

    def test_REQ_p00001_A_install_no_shell_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SHELL", raising=False)
        result = cmd_install(None)
        assert result == 1

    def test_REQ_p00001_A_install_removes_stale_argcomplete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = self._patch(monkeypatch, tmp_path, "zsh")
        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text("# existing\n" 'eval "$(register-python-argcomplete elspais)"\n')

        result = cmd_install("zsh")
        assert result == 0
        assert "argcomplete" not in rc_file.read_text()


class TestCmdUninstall:
    """Validates REQ-p00001-A: completion uninstall command."""

    def _patch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        shell: str,
    ) -> dict[str, Path | str | None]:
        cfg = _make_shell_config(tmp_path, shell)
        patched_config = {**_SHELL_CONFIG, shell: cfg}
        monkeypatch.setattr("elspais.commands.completion._SHELL_CONFIG", patched_config)
        monkeypatch.setattr("elspais.commands.completion._clear_zsh_compdump", lambda: 0)
        return cfg

    def test_REQ_p00001_A_uninstall_removes_script(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = self._patch(monkeypatch, tmp_path, "zsh")
        script_path = Path(cfg["script_path"])  # type: ignore[arg-type]
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text("# completion script\n")

        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text(
            "# elspais shell completion\n"
            "fpath=(~/.zfunc $fpath)\n"
            "autoload -Uz compinit && compinit\n"
        )

        result = cmd_uninstall("zsh")
        assert result == 0
        assert not script_path.exists()

    def test_REQ_p00001_A_uninstall_removes_rc_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = self._patch(monkeypatch, tmp_path, "zsh")
        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text(
            "export FOO=bar\n"
            "\n"
            "# elspais shell completion\n"
            "fpath=(~/.zfunc $fpath)\n"
            "autoload -Uz compinit && compinit\n"
        )

        result = cmd_uninstall("zsh")
        assert result == 0
        content = rc_file.read_text()
        assert "elspais" not in content
        assert "export FOO=bar" in content

    def test_REQ_p00001_A_uninstall_no_script_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = self._patch(monkeypatch, tmp_path, "bash")
        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text("")

        result = cmd_uninstall("bash")
        assert result == 0  # should succeed even with nothing to remove

    def test_REQ_p00001_A_uninstall_unsupported_shell(self) -> None:
        result = cmd_uninstall("fish")
        assert result == 1

    def test_REQ_p00001_A_uninstall_no_shell_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SHELL", raising=False)
        result = cmd_uninstall(None)
        assert result == 1

    def test_REQ_p00001_A_uninstall_removes_stale_argcomplete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = self._patch(monkeypatch, tmp_path, "zsh")
        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text(
            "# Autocompletion for elspais\n" 'eval "$(register-python-argcomplete elspais)"\n'
        )

        result = cmd_uninstall("zsh")
        assert result == 0
        assert "argcomplete" not in rc_file.read_text()


class TestIdempotency:
    """Validates REQ-p00001-A: install is idempotent -- running twice does not duplicate."""

    def test_REQ_p00001_A_install_twice_no_duplicate_rc(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _make_shell_config(tmp_path, "zsh")
        patched_config = {**_SHELL_CONFIG, "zsh": cfg}
        monkeypatch.setattr("elspais.commands.completion._SHELL_CONFIG", patched_config)
        monkeypatch.setattr(
            "elspais.commands.completion._generate_completion",
            lambda s: f"# fake {s} completion\n",
        )
        monkeypatch.setattr("elspais.commands.completion._clear_zsh_compdump", lambda: 0)

        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text("")

        # Install twice
        assert cmd_install("zsh") == 0
        first_content = rc_file.read_text()

        assert cmd_install("zsh") == 0
        second_content = rc_file.read_text()

        assert first_content == second_content
        # Marker should appear exactly once
        assert second_content.count("# elspais shell completion") == 1

    def test_REQ_p00001_A_install_twice_script_updated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second install overwrites script (idempotent update)."""
        cfg = _make_shell_config(tmp_path, "bash")
        patched_config = {**_SHELL_CONFIG, "bash": cfg}
        monkeypatch.setattr("elspais.commands.completion._SHELL_CONFIG", patched_config)

        call_count = 0

        def fake_generate(s: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"# version {call_count}\n"

        monkeypatch.setattr("elspais.commands.completion._generate_completion", fake_generate)
        monkeypatch.setattr("elspais.commands.completion._clear_zsh_compdump", lambda: 0)

        rc_file = Path(cfg["rc_file"])  # type: ignore[arg-type]
        rc_file.write_text("")

        assert cmd_install("bash") == 0
        assert cmd_install("bash") == 0

        script_path = Path(cfg["script_path"])  # type: ignore[arg-type]
        assert "version 2" in script_path.read_text()
