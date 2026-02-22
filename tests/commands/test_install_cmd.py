# Implements: REQ-p00001-A
"""Tests for elspais.commands.install_cmd — install/uninstall management."""
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from elspais.commands import install_cmd

# ---------------------------------------------------------------------------
# detect_tool
# ---------------------------------------------------------------------------


class TestDetectTool:
    """Validates REQ-p00001-A: Tool detection for install management."""

    @patch("shutil.which")
    def test_REQ_p00001_A_finds_pipx_first(self, mock_which):
        mock_which.side_effect = lambda x: "/usr/bin/pipx" if x == "pipx" else "/usr/bin/uv"
        assert install_cmd.detect_tool() == "pipx"

    @patch("shutil.which")
    def test_REQ_p00001_A_falls_back_to_uv(self, mock_which):
        mock_which.side_effect = lambda x: "/usr/bin/uv" if x == "uv" else None
        assert install_cmd.detect_tool() == "uv"

    @patch("shutil.which", return_value=None)
    def test_REQ_p00001_A_returns_none_when_neither(self, mock_which):
        assert install_cmd.detect_tool() is None

    @patch("shutil.which")
    def test_REQ_p00001_A_preferred_overrides(self, mock_which):
        mock_which.side_effect = lambda x: f"/usr/bin/{x}"
        assert install_cmd.detect_tool(preferred="uv") == "uv"
        mock_which.assert_called_once_with("uv")

    @patch("shutil.which", return_value=None)
    def test_REQ_p00001_A_preferred_not_found(self, mock_which):
        assert install_cmd.detect_tool(preferred="pipx") is None


# ---------------------------------------------------------------------------
# find_source_root
# ---------------------------------------------------------------------------


class TestFindSourceRoot:
    """Validates REQ-p00001-A: Source root detection."""

    def test_REQ_p00001_A_finds_real_source_root(self):
        """Walking up from the real install_cmd.__file__ should find elspais."""
        result = install_cmd.find_source_root()
        assert result is not None
        assert (result / "pyproject.toml").exists()

    def test_REQ_p00001_A_override_valid_project(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "elspais"\n')
        result = install_cmd.find_source_root(override_path=tmp_path)
        assert result == tmp_path.resolve()

    def test_REQ_p00001_A_override_non_elspais_returns_none(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "other-project"\n')
        result = install_cmd.find_source_root(override_path=tmp_path)
        assert result is None

    def test_REQ_p00001_A_override_nonexistent_returns_none(self, tmp_path):
        result = install_cmd.find_source_root(override_path=tmp_path / "nope")
        assert result is None


# ---------------------------------------------------------------------------
# _is_elspais_project
# ---------------------------------------------------------------------------


class TestIsElspaisProject:
    """Validates REQ-p00001-A: pyproject.toml identification."""

    def test_REQ_p00001_A_valid_elspais(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "elspais"\nversion = "1.0"\n')
        assert install_cmd._is_elspais_project(pyproject) is True

    def test_REQ_p00001_A_wrong_name(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "some-other-thing"\n')
        assert install_cmd._is_elspais_project(pyproject) is False

    def test_REQ_p00001_A_missing_file(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        assert install_cmd._is_elspais_project(pyproject) is False

    def test_REQ_p00001_A_invalid_toml(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("{{invalid toml content!!")
        assert install_cmd._is_elspais_project(pyproject) is False


# ---------------------------------------------------------------------------
# detect_installed_extras
# ---------------------------------------------------------------------------


class TestDetectInstalledExtras:
    """Validates REQ-p00001-A: Extras auto-detection."""

    @patch("importlib.util.find_spec", return_value=MagicMock())
    def test_REQ_p00001_A_all_extras_available(self, mock_find):
        result = install_cmd.detect_installed_extras()
        # trace-review is superset of trace-view, so trace-view is deduped
        assert "mcp" in result
        assert "trace-review" in result
        assert "trace-view" not in result
        assert "completion" in result

    @patch("importlib.util.find_spec")
    def test_REQ_p00001_A_only_mcp_available(self, mock_find):
        def side_effect(dep):
            return MagicMock() if dep == "mcp" else None

        mock_find.side_effect = side_effect
        result = install_cmd.detect_installed_extras()
        assert result == ["mcp"]

    @patch("importlib.util.find_spec", return_value=None)
    def test_REQ_p00001_A_nothing_available(self, mock_find):
        result = install_cmd.detect_installed_extras()
        assert result == []

    @patch("importlib.util.find_spec")
    def test_REQ_p00001_A_trace_review_dedupes_trace_view(self, mock_find):
        """When all jinja2/pygments/flask/flask_cors are present,
        trace-review should suppress trace-view."""
        available = {"jinja2", "pygments", "flask", "flask_cors"}
        mock_find.side_effect = lambda dep: MagicMock() if dep in available else None
        result = install_cmd.detect_installed_extras()
        assert "trace-review" in result
        assert "trace-view" not in result


# ---------------------------------------------------------------------------
# _build_install_spec
# ---------------------------------------------------------------------------


class TestBuildInstallSpec:
    """Validates REQ-p00001-A: Install spec string building."""

    def test_REQ_p00001_A_without_extras(self):
        assert install_cmd._build_install_spec("/src/elspais", None) == "/src/elspais"

    def test_REQ_p00001_A_with_empty_extras(self):
        assert install_cmd._build_install_spec("/src/elspais", []) == "/src/elspais"

    def test_REQ_p00001_A_with_extras(self):
        result = install_cmd._build_install_spec("/src/elspais", ["mcp", "trace-view"])
        assert result == "/src/elspais[mcp,trace-view]"


# ---------------------------------------------------------------------------
# install_local
# ---------------------------------------------------------------------------


class TestInstallLocal:
    """Validates REQ-p00001-A: Local editable installation."""

    @patch("elspais.commands.install_cmd._print_shell_hint")
    @patch("elspais.commands.install_cmd._show_active_version")
    @patch("elspais.commands.install_cmd._patch_argcomplete_marker")
    @patch("subprocess.run")
    def test_REQ_p00001_A_pipx_two_step(self, mock_run, *_):
        """pipx uses two-step: install --force, then runpip -e."""
        mock_run.return_value = MagicMock(returncode=0)
        source = Path("/home/dev/elspais")
        result = install_cmd.install_local(source, "pipx")
        assert result == 0
        assert mock_run.call_count == 2
        # Step 1: pipx install <path> --force
        step1 = mock_run.call_args_list[0][0][0]
        assert step1 == ["pipx", "install", str(source), "--force"]
        # Step 2: pipx runpip elspais install -e <path>
        step2 = mock_run.call_args_list[1][0][0]
        assert step2 == ["pipx", "runpip", "elspais", "install", "-e", str(source)]

    @patch("elspais.commands.install_cmd._print_shell_hint")
    @patch("elspais.commands.install_cmd._show_active_version")
    @patch("elspais.commands.install_cmd._patch_argcomplete_marker")
    @patch("subprocess.run")
    def test_REQ_p00001_A_pipx_with_extras(self, mock_run, *_):
        mock_run.return_value = MagicMock(returncode=0)
        source = Path("/home/dev/elspais")
        result = install_cmd.install_local(source, "pipx", extras=["mcp", "all"])
        assert result == 0
        # Step 2 should include extras in the spec
        step2 = mock_run.call_args_list[1][0][0]
        assert step2[-1] == f"{source}[mcp,all]"

    @patch("elspais.commands.install_cmd._print_shell_hint")
    @patch("elspais.commands.install_cmd._show_active_version")
    @patch("elspais.commands.install_cmd._patch_argcomplete_marker")
    @patch("subprocess.run")
    def test_REQ_p00001_A_uv_command(self, mock_run, *_):
        mock_run.return_value = MagicMock(returncode=0)
        source = Path("/home/dev/elspais")
        result = install_cmd.install_local(source, "uv")
        assert result == 0
        cmd = mock_run.call_args[0][0]
        assert cmd == ["uv", "tool", "install", "--editable", str(source), "--force"]

    @patch("subprocess.run")
    def test_REQ_p00001_A_pipx_step1_failure_returns_1(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="boom")
        source = Path("/home/dev/elspais")
        result = install_cmd.install_local(source, "pipx")
        assert result == 1
        # Only step 1 should have been called
        assert mock_run.call_count == 1

    @patch("subprocess.run")
    def test_REQ_p00001_A_pipx_step2_failure_returns_1(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),  # step 1 succeeds
            MagicMock(returncode=1, stderr="editable failed"),  # step 2 fails
        ]
        source = Path("/home/dev/elspais")
        result = install_cmd.install_local(source, "pipx")
        assert result == 1

    def test_REQ_p00001_A_unsupported_tool_returns_1(self):
        source = Path("/home/dev/elspais")
        result = install_cmd.install_local(source, "conda")
        assert result == 1


# ---------------------------------------------------------------------------
# uninstall_local
# ---------------------------------------------------------------------------


class TestUninstallLocal:
    """Validates REQ-p00001-A: Reverting to PyPI version (two-step)."""

    @patch("elspais.commands.install_cmd._show_active_version")
    @patch("subprocess.run")
    def test_REQ_p00001_A_pipx_uninstalls_then_installs(self, mock_run, mock_version):
        mock_run.return_value = MagicMock(returncode=0)
        result = install_cmd.uninstall_local("pipx")
        assert result == 0
        assert mock_run.call_count == 2
        step1 = mock_run.call_args_list[0][0][0]
        step2 = mock_run.call_args_list[1][0][0]
        assert step1 == ["pipx", "uninstall", "elspais"]
        assert step2 == ["pipx", "install", "elspais"]

    @patch("elspais.commands.install_cmd._show_active_version")
    @patch("subprocess.run")
    def test_REQ_p00001_A_uv_uninstalls_then_installs(self, mock_run, mock_version):
        mock_run.return_value = MagicMock(returncode=0)
        result = install_cmd.uninstall_local("uv")
        assert result == 0
        assert mock_run.call_count == 2
        step1 = mock_run.call_args_list[0][0][0]
        step2 = mock_run.call_args_list[1][0][0]
        assert step1 == ["uv", "tool", "uninstall", "elspais"]
        assert step2 == ["uv", "tool", "install", "elspais"]

    @patch("elspais.commands.install_cmd._show_active_version")
    @patch("subprocess.run")
    def test_REQ_p00001_A_with_version(self, mock_run, mock_version):
        mock_run.return_value = MagicMock(returncode=0)
        result = install_cmd.uninstall_local("pipx", version="0.50.0")
        assert result == 0
        step2 = mock_run.call_args_list[1][0][0]
        assert "elspais==0.50.0" in step2[2]

    @patch("elspais.commands.install_cmd._show_active_version")
    @patch("subprocess.run")
    def test_REQ_p00001_A_with_extras(self, mock_run, mock_version):
        mock_run.return_value = MagicMock(returncode=0)
        result = install_cmd.uninstall_local("pipx", extras=["mcp", "trace-view"])
        assert result == 0
        step2 = mock_run.call_args_list[1][0][0]
        assert step2[2] == "elspais[mcp,trace-view]"

    @patch("subprocess.run")
    def test_REQ_p00001_A_uninstall_failure_returns_1(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="fail")
        result = install_cmd.uninstall_local("pipx")
        assert result == 1
        # Should fail on step 1 (uninstall), never reaching step 2
        assert mock_run.call_count == 1

    @patch("subprocess.run")
    def test_REQ_p00001_A_install_failure_returns_1(self, mock_run):
        """Uninstall succeeds but fresh install fails."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # uninstall OK
            MagicMock(returncode=1, stderr="install fail"),  # install fails
        ]
        result = install_cmd.uninstall_local("pipx")
        assert result == 1
        assert mock_run.call_count == 2

    def test_REQ_p00001_A_unsupported_tool_returns_1(self):
        result = install_cmd.uninstall_local("conda")
        assert result == 1


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    """Validates REQ-p00001-A: Install dispatcher."""

    @patch("elspais.commands.install_cmd._run_install_local", return_value=0)
    def test_REQ_p00001_A_dispatches_install_local(self, mock_install):
        args = argparse.Namespace(install_action="local")
        assert install_cmd.run(args) == 0
        mock_install.assert_called_once_with(args)

    def test_REQ_p00001_A_missing_subcommand_returns_1(self, capsys):
        args = argparse.Namespace()
        assert install_cmd.run(args) == 1
        captured = capsys.readouterr()
        assert "Usage:" in captured.err


# ---------------------------------------------------------------------------
# run_uninstall
# ---------------------------------------------------------------------------


class TestRunUninstall:
    """Validates REQ-p00001-A: Uninstall dispatcher."""

    @patch("elspais.commands.install_cmd._run_uninstall_local", return_value=0)
    def test_REQ_p00001_A_dispatches_uninstall_local(self, mock_uninstall):
        args = argparse.Namespace(uninstall_action="local")
        assert install_cmd.run_uninstall(args) == 0
        mock_uninstall.assert_called_once_with(args)

    def test_REQ_p00001_A_missing_subcommand_returns_1(self, capsys):
        args = argparse.Namespace()
        assert install_cmd.run_uninstall(args) == 1
        captured = capsys.readouterr()
        assert "Usage:" in captured.err


# ---------------------------------------------------------------------------
# _run_install_local
# ---------------------------------------------------------------------------


class TestRunInstallLocal:
    """Validates REQ-p00001-A: Full install-local flow."""

    @patch("elspais.commands.install_cmd.detect_tool", return_value=None)
    def test_REQ_p00001_A_no_tool_returns_1(self, mock_detect, capsys):
        args = argparse.Namespace(verbose=False, tool=None, path=None, extras=None)
        assert install_cmd._run_install_local(args) == 1
        captured = capsys.readouterr()
        assert "Neither pipx nor uv" in captured.err

    @patch("elspais.commands.install_cmd.detect_tool", return_value=None)
    def test_REQ_p00001_A_preferred_tool_not_found(self, mock_detect, capsys):
        args = argparse.Namespace(verbose=False, tool="pipx", path=None, extras=None)
        assert install_cmd._run_install_local(args) == 1
        captured = capsys.readouterr()
        assert "'pipx' not found" in captured.err

    @patch("elspais.commands.install_cmd.find_source_root", return_value=None)
    @patch("elspais.commands.install_cmd.detect_tool", return_value="pipx")
    def test_REQ_p00001_A_no_source_root_returns_1(self, mock_detect, mock_find, capsys):
        args = argparse.Namespace(verbose=False, tool=None, path=None, extras=None)
        assert install_cmd._run_install_local(args) == 1
        captured = capsys.readouterr()
        assert "Cannot find elspais source" in captured.err

    @patch("elspais.commands.install_cmd.install_local", return_value=0)
    @patch(
        "elspais.commands.install_cmd.find_source_root",
        return_value=Path("/dev/elspais"),
    )
    @patch("elspais.commands.install_cmd.detect_tool", return_value="pipx")
    @patch("elspais.commands.install_cmd._parse_extras", return_value=["mcp"])
    def test_REQ_p00001_A_successful_flow(self, mock_extras, mock_detect, mock_find, mock_install):
        args = argparse.Namespace(verbose=False, tool=None, path=None, extras="mcp")
        assert install_cmd._run_install_local(args) == 0
        mock_install.assert_called_once_with(Path("/dev/elspais"), "pipx", ["mcp"], False)


# ---------------------------------------------------------------------------
# _run_uninstall_local
# ---------------------------------------------------------------------------


class TestRunUninstallLocal:
    """Validates REQ-p00001-A: Full uninstall-local flow."""

    @patch("elspais.commands.install_cmd.detect_tool", return_value=None)
    def test_REQ_p00001_A_no_tool_returns_1(self, mock_detect, capsys):
        args = argparse.Namespace(verbose=False, tool=None, extras=None, version=None)
        assert install_cmd._run_uninstall_local(args) == 1
        captured = capsys.readouterr()
        assert "Neither pipx nor uv" in captured.err

    @patch("elspais.commands.install_cmd.uninstall_local", return_value=0)
    @patch("elspais.commands.install_cmd.detect_tool", return_value="uv")
    @patch("elspais.commands.install_cmd._parse_extras", return_value=None)
    def test_REQ_p00001_A_successful_flow(self, mock_extras, mock_detect, mock_uninstall):
        args = argparse.Namespace(verbose=False, tool=None, extras=None, version=None)
        assert install_cmd._run_uninstall_local(args) == 0
        mock_uninstall.assert_called_once_with("uv", None, None, False)


# ---------------------------------------------------------------------------
# _parse_extras
# ---------------------------------------------------------------------------


class TestParseExtras:
    """Validates REQ-p00001-A: Extras argument parsing."""

    def test_REQ_p00001_A_parses_comma_separated(self):
        args = argparse.Namespace(extras="mcp, trace-view, all")
        result = install_cmd._parse_extras(args)
        assert result == ["mcp", "trace-view", "all"]

    @patch(
        "elspais.commands.install_cmd.detect_installed_extras",
        return_value=["mcp", "trace-review"],
    )
    def test_REQ_p00001_A_auto_detects(self, mock_detect):
        args = argparse.Namespace(extras=None)
        result = install_cmd._parse_extras(args)
        assert result == ["mcp", "trace-review"]

    @patch("elspais.commands.install_cmd.detect_installed_extras", return_value=[])
    def test_REQ_p00001_A_returns_none_when_nothing(self, mock_detect):
        args = argparse.Namespace(extras=None)
        result = install_cmd._parse_extras(args)
        assert result is None


# ---------------------------------------------------------------------------
# _patch_argcomplete_marker
# ---------------------------------------------------------------------------


class TestPatchArgcompleteMarker:
    """Validates REQ-p00001-A: Argcomplete marker injection in entry point."""

    def test_REQ_p00001_A_patches_shebang_script(self, tmp_path):
        script = tmp_path / "elspais"
        script.write_text("#!/usr/bin/python\nimport sys\nsys.exit(0)\n")
        with patch("shutil.which", return_value=str(script)):
            install_cmd._patch_argcomplete_marker()
        content = script.read_text()
        assert "# PYTHON_ARGCOMPLETE_OK" in content
        # Marker should be on line 2 (after shebang)
        lines = content.splitlines()
        assert lines[0].startswith("#!")
        assert lines[1] == "# PYTHON_ARGCOMPLETE_OK"

    def test_REQ_p00001_A_idempotent(self, tmp_path):
        script = tmp_path / "elspais"
        script.write_text("#!/usr/bin/python\n# PYTHON_ARGCOMPLETE_OK\nimport sys\n")
        with patch("shutil.which", return_value=str(script)):
            install_cmd._patch_argcomplete_marker()
        content = script.read_text()
        assert content.count("PYTHON_ARGCOMPLETE_OK") == 1

    def test_REQ_p00001_A_skips_when_not_found(self):
        with patch("shutil.which", return_value=None):
            # Should not raise
            install_cmd._patch_argcomplete_marker()

    def test_REQ_p00001_A_handles_permission_error(self, tmp_path):
        script = tmp_path / "elspais"
        script.write_text("#!/usr/bin/python\nimport sys\n")
        with (
            patch("shutil.which", return_value=str(script)),
            patch.object(Path, "write_text", side_effect=PermissionError("denied")),
        ):
            # Should not raise, just warn
            install_cmd._patch_argcomplete_marker()


# ---------------------------------------------------------------------------
# _print_shell_hint
# ---------------------------------------------------------------------------


class TestPrintShellHint:
    """Validates REQ-p00001-A: Post-install shell refresh hints."""

    @patch.dict("os.environ", {"SHELL": "/bin/zsh"})
    def test_REQ_p00001_A_zsh_hint(self, capsys):
        install_cmd._print_shell_hint()
        out = capsys.readouterr().out
        assert "rehash" in out
        assert "completion --install" in out

    @patch.dict("os.environ", {"SHELL": "/bin/bash"})
    def test_REQ_p00001_A_bash_hint(self, capsys):
        install_cmd._print_shell_hint()
        out = capsys.readouterr().out
        assert "hash -r" in out
        assert "completion --install" in out

    @patch.dict("os.environ", {"SHELL": "/usr/bin/fish"})
    def test_REQ_p00001_A_fish_hint(self, capsys):
        install_cmd._print_shell_hint()
        out = capsys.readouterr().out
        assert "completion --install" in out

    @patch.dict("os.environ", {"SHELL": ""})
    def test_REQ_p00001_A_unknown_shell_hint(self, capsys):
        install_cmd._print_shell_hint()
        out = capsys.readouterr().out
        assert "hash -r" in out
        assert "completion --install" in out
