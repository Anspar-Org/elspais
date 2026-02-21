# Implements: REQ-p00005-C
"""Tests for elspais associate command.

Validates REQ-p00005-C: CLI-based management of associate repository links.
Validates REQ-p00005-E: Clear error reporting for invalid paths/configs.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import tomlkit


def _make_core_repo(tmp_path: Path) -> Path:
    """Create a minimal core repo with .elspais.toml."""
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / ".elspais.toml").write_text(
        '[project]\nname = "core"\ntype = "core"\n\n' '[directories]\nspec = "spec"\n'
    )
    (tmp_path / "spec").mkdir(exist_ok=True)
    return tmp_path


def _make_associate_repo(base: Path, name: str, prefix: str) -> Path:
    """Create a minimal associate repo with .elspais.toml."""
    repo = base / name
    repo.mkdir(exist_ok=True)
    (repo / ".elspais.toml").write_text(
        f'[project]\nname = "{name}"\ntype = "associated"\n\n'
        f'[associated]\nprefix = "{prefix}"\n\n'
        f'[directories]\nspec = "spec"\n'
    )
    (repo / "spec").mkdir(exist_ok=True)
    return repo


class TestAssociateLinkByPath:
    """Validates REQ-p00005-C: linking an associate by directory path."""

    def test_REQ_p00005_C_link_valid_associate_by_path(self, tmp_path, monkeypatch, capsys):
        """Link a valid associate repo by absolute path."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=str(assoc),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "callisto" in output
        assert "CAL" in output

        # Verify .elspais.local.toml was created
        local_config = core / ".elspais.local.toml"
        assert local_config.exists()
        doc = tomlkit.parse(local_config.read_text())
        assert str(assoc) in doc["associates"]["paths"]

    def test_REQ_p00005_C_link_creates_local_toml_if_missing(self, tmp_path, monkeypatch):
        """Creates .elspais.local.toml if it doesn't exist."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        local_config = core / ".elspais.local.toml"
        assert not local_config.exists()

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=str(assoc),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        run(args)
        assert local_config.exists()

    def test_REQ_p00005_C_link_appends_to_existing_paths(self, tmp_path, monkeypatch):
        """Appending to existing [associates].paths doesn't replace."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc1 = _make_associate_repo(tmp_path, "callisto", "CAL")
        assoc2 = _make_associate_repo(tmp_path, "europa", "EUR")

        monkeypatch.chdir(core)

        # Link first associate
        args = argparse.Namespace(
            path=str(assoc1),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        run(args)

        # Link second associate
        args.path = str(assoc2)
        run(args)

        # Both should be in the config
        local_config = core / ".elspais.local.toml"
        doc = tomlkit.parse(local_config.read_text())
        paths = list(doc["associates"]["paths"])
        assert str(assoc1) in paths
        assert str(assoc2) in paths

    def test_REQ_p00005_C_link_duplicate_path_is_noop(self, tmp_path, monkeypatch, capsys):
        """Linking the same path twice doesn't duplicate."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=str(assoc),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        run(args)
        run(args)

        local_config = core / ".elspais.local.toml"
        doc = tomlkit.parse(local_config.read_text())
        paths = list(doc["associates"]["paths"])
        assert paths.count(str(assoc)) == 1

        output = capsys.readouterr().out
        assert "already linked" in output.lower()


class TestAssociateLinkByName:
    """Validates REQ-p00005-C: linking by name scans sibling directories."""

    def test_REQ_p00005_C_link_by_name_finds_sibling(self, tmp_path, monkeypatch, capsys):
        """Search for associate by directory name in parent directory."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")
        _make_associate_repo(workspace, "callisto", "CAL")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path="callisto",
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=core,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "callisto" in output


class TestAssociateErrors:
    """Validates REQ-p00005-E: clear errors for invalid paths/configs."""

    def test_REQ_p00005_E_link_nonexistent_path_errors(self, tmp_path, monkeypatch, capsys):
        """Non-existent path produces a clear error."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        monkeypatch.chdir(core)

        args = argparse.Namespace(
            path="/nonexistent/repo",
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        rc = run(args)
        assert rc == 1

        output = capsys.readouterr().err
        assert "does not exist" in output or "not found" in output.lower()

    def test_REQ_p00005_E_link_directory_without_config_errors(self, tmp_path, monkeypatch, capsys):
        """Directory without .elspais.toml produces a clear error."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        no_config = tmp_path / "no-config-repo"
        no_config.mkdir()

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=str(no_config),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        rc = run(args)
        assert rc == 1

        output = capsys.readouterr().err
        assert ".elspais.toml" in output

    def test_REQ_p00005_E_link_non_associated_type_errors(self, tmp_path, monkeypatch, capsys):
        """Repo with wrong project.type produces a clear error."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        wrong_type = tmp_path / "wrong-type"
        wrong_type.mkdir()
        (wrong_type / ".elspais.toml").write_text('[project]\nname = "wrong"\ntype = "core"\n')

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=str(wrong_type),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        rc = run(args)
        assert rc == 1

        output = capsys.readouterr().err
        assert "associated" in output.lower()

    def test_REQ_p00005_E_unlink_unknown_name_errors(self, tmp_path, monkeypatch, capsys):
        """Unlinking a name that doesn't exist produces a clear error."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        monkeypatch.chdir(core)

        args = argparse.Namespace(
            path=None,
            all=False,
            list=False,
            unlink="nonexistent",
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        rc = run(args)
        assert rc == 1

        output = capsys.readouterr().err
        assert "nonexistent" in output or "not found" in output.lower()


class TestAssociateAll:
    """Validates REQ-p00005-C: auto-discovery of associates."""

    def test_REQ_p00005_C_all_discovers_siblings(self, tmp_path, monkeypatch, capsys):
        """--all scans parent directory for associate repos."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")
        _make_associate_repo(workspace, "callisto", "CAL")
        _make_associate_repo(workspace, "europa", "EUR")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=None,
            all=True,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=core,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "callisto" in output or "CAL" in output
        assert "europa" in output or "EUR" in output

        # Verify both are in .elspais.local.toml
        local_config = core / ".elspais.local.toml"
        assert local_config.exists()
        doc = tomlkit.parse(local_config.read_text())
        paths = list(doc["associates"]["paths"])
        assert len(paths) == 2

    def test_REQ_p00005_C_all_no_associates_found(self, tmp_path, monkeypatch, capsys):
        """--all with no associates reports none found."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=None,
            all=True,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=core,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "0" in output or "no" in output.lower() or "none" in output.lower()


class TestAssociateList:
    """Validates REQ-p00005-C: listing associate links and status."""

    def test_REQ_p00005_C_list_shows_linked_associates(self, tmp_path, monkeypatch, capsys):
        """--list shows linked associates with status."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        # Pre-create local config with associate path
        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates]\npaths = ["{assoc}"]\n')

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=None,
            all=False,
            list=True,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "callisto" in output
        assert "CAL" in output

    def test_REQ_p00005_C_list_no_associates(self, tmp_path, monkeypatch, capsys):
        """--list with no associates shows informational message."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        monkeypatch.chdir(core)

        args = argparse.Namespace(
            path=None,
            all=False,
            list=True,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "no" in output.lower() or "none" in output.lower() or "0" in output

    def test_REQ_p00005_E_list_shows_broken_path(self, tmp_path, monkeypatch, capsys):
        """--list shows broken status for non-existent paths."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        local_config = core / ".elspais.local.toml"
        local_config.write_text('[associates]\npaths = ["/nonexistent/callisto"]\n')

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=None,
            all=False,
            list=True,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        # Should indicate broken/missing status
        assert (
            "not found" in output.lower()
            or "missing" in output.lower()
            or "broken" in output.lower()
        )


class TestAssociateUnlink:
    """Validates REQ-p00005-C: unlinking associates."""

    def test_REQ_p00005_C_unlink_by_name(self, tmp_path, monkeypatch, capsys):
        """Unlink an associate by name."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        # Pre-create local config with associate path
        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates]\npaths = ["{assoc}"]\n')

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=None,
            all=False,
            list=False,
            unlink="callisto",
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "unlinked" in output.lower() or "callisto" in output.lower()

        # Verify removed from local config
        doc = tomlkit.parse(local_config.read_text())
        paths = list(doc["associates"]["paths"])
        assert str(assoc) not in paths

    def test_REQ_p00005_C_unlink_preserves_other_paths(self, tmp_path, monkeypatch):
        """Unlinking one associate preserves others."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc1 = _make_associate_repo(tmp_path, "callisto", "CAL")
        assoc2 = _make_associate_repo(tmp_path, "europa", "EUR")

        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates]\npaths = ["{assoc1}", "{assoc2}"]\n')

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            path=None,
            all=False,
            list=False,
            unlink="callisto",
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            canonical_root=None,
        )
        run(args)

        doc = tomlkit.parse(local_config.read_text())
        paths = list(doc["associates"]["paths"])
        assert str(assoc1) not in paths
        assert str(assoc2) in paths
