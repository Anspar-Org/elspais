# Verifies: REQ-p00005-C, REQ-d00202-I, REQ-d00289-A+B+C+D+E+F+G+H+I, REQ-d00290-A+B
"""Tests for elspais associate command.

Validates REQ-p00005-C: CLI-based management of associate repository links.
Validates REQ-p00005-E: Clear error reporting for invalid paths/configs.
Validates REQ-d00202-I: Candidate dirs with unloadable configs are skipped
with a reported reason; the scan completes.
Validates REQ-d00289-A..I: what a registration run reports, what it does when
the entry already names another path or another entry already records the
namespace declared, and which conditions it refuses at -- on the single-link
surface and on --all discovery alike.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import tomlkit


def _make_core_repo(tmp_path: Path) -> Path:
    """Create a minimal core repo with .elspais.toml."""
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / ".elspais.toml").write_text(
        'version = 5\n[project]\nname = "core"\nnamespace = "REQ"\n\n'
        '[scanning.spec]\ndirectories = ["spec"]\n'
    )
    (tmp_path / "spec").mkdir(exist_ok=True)
    return tmp_path


def _make_associate_repo(base: Path, name: str, prefix: str) -> Path:
    """Create a minimal associate repo with .elspais.toml."""
    repo = base / name
    repo.mkdir(exist_ok=True)
    (repo / ".elspais.toml").write_text(
        f'version = 5\n[project]\nname = "{name}"\nnamespace = "{prefix}"\n\n'
        f'[scanning.spec]\ndirectories = ["spec"]\n'
    )
    (repo / "spec").mkdir(exist_ok=True)
    return repo


class TestAssociateLinkByPath:
    """Validates REQ-p00005-C: linking an associate by directory path."""

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_link_valid_associate_by_path(self, tmp_path, monkeypatch, capsys):
        """Link a valid associate repo by absolute path."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=str(assoc),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "callisto" in output
        assert "CAL" in output

        # Verify .elspais.local.toml was created with v3 named format
        local_config = core / ".elspais.local.toml"
        assert local_config.exists()
        doc = tomlkit.parse(local_config.read_text())
        assert "callisto" in doc["associates"]
        assert doc["associates"]["callisto"]["path"] == str(assoc)

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_link_creates_local_toml_if_missing(self, tmp_path, monkeypatch):
        """Creates .elspais.local.toml if it doesn't exist."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        local_config = core / ".elspais.local.toml"
        assert not local_config.exists()

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=str(assoc),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        run(args)
        assert local_config.exists()

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_link_appends_to_existing_paths(self, tmp_path, monkeypatch):
        """Adding second associate doesn't replace the first."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc1 = _make_associate_repo(tmp_path, "callisto", "CAL")
        assoc2 = _make_associate_repo(tmp_path, "europa", "EUR")

        monkeypatch.chdir(core)

        # Link first associate
        args = argparse.Namespace(
            associate_path=str(assoc1),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        run(args)

        # Link second associate
        args.associate_path = str(assoc2)
        run(args)

        # Both should be in the config as named entries
        local_config = core / ".elspais.local.toml"
        doc = tomlkit.parse(local_config.read_text())
        assert "callisto" in doc["associates"]
        assert "europa" in doc["associates"]
        assert doc["associates"]["callisto"]["path"] == str(assoc1)
        assert doc["associates"]["europa"]["path"] == str(assoc2)

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_link_duplicate_path_is_noop(self, tmp_path, monkeypatch, capsys):
        """Linking the same path twice doesn't duplicate."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=str(assoc),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        run(args)
        first = capsys.readouterr().out
        run(args)
        second = capsys.readouterr().out

        local_config = core / ".elspais.local.toml"
        doc = tomlkit.parse(local_config.read_text())
        # Should have exactly one entry, not duplicated
        assoc_entries = [k for k in doc["associates"] if isinstance(doc["associates"][k], dict)]
        assert len(assoc_entries) == 1

        # REQ-d00289-B: the run that recorded nothing reads differently from
        # the run that recorded the entry.
        assert "linked" in first.lower()
        assert "no change" not in first.lower()
        assert "no change" in second.lower()
        assert "linked" not in second.lower()
        # REQ-d00289-A: the report names the path the configuration holds.
        assert str(assoc) in second


class TestAssociateLinkByName:
    """Validates REQ-p00005-C: linking by name scans sibling directories."""

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_link_by_name_finds_sibling(self, tmp_path, monkeypatch, capsys):
        """Search for associate by directory name in parent directory."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")
        _make_associate_repo(workspace, "callisto", "CAL")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path="callisto",
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "callisto" in output


class TestAssociateErrors:
    """Validates REQ-p00005-E: clear errors for invalid paths/configs."""

    # Verifies: REQ-p00005-E
    def test_REQ_p00005_E_link_nonexistent_path_errors(self, tmp_path, monkeypatch, capsys):
        """Non-existent path produces a clear error."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        monkeypatch.chdir(core)

        args = argparse.Namespace(
            associate_path="/nonexistent/repo",
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 1

        output = capsys.readouterr().err
        assert "does not exist" in output or "not found" in output.lower()

    # Verifies: REQ-p00005-E
    def test_REQ_p00005_E_link_directory_without_config_errors(self, tmp_path, monkeypatch, capsys):
        """Directory without .elspais.toml produces a clear error."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        no_config = tmp_path / "no-config-repo"
        no_config.mkdir()

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=str(no_config),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 1

        output = capsys.readouterr().err
        assert ".elspais.toml" in output

    # Verifies: REQ-p00005-E
    def test_REQ_p00005_E_link_any_valid_repo_succeeds(self, tmp_path, monkeypatch, capsys):
        """In v3, any repo with a valid .elspais.toml can be linked as an associate."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        other = tmp_path / "other"
        other.mkdir()
        # Its own namespace: a repo colliding with the core repo's is refused
        # by the federation rules (REQ-d00202-K), which is a different
        # question from the one this test asks.
        (other / ".elspais.toml").write_text(
            'version = 5\n[project]\nname = "other"\nnamespace = "OTH"\n'
        )

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=str(other),
            all=False,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
            force=False,
        )
        rc = run(args)
        assert rc == 0

        doc = tomlkit.parse((core / ".elspais.local.toml").read_text())
        assert doc["associates"]["other"]["path"] == str(other)

    # Verifies: REQ-p00005-E
    def test_REQ_p00005_E_unlink_unknown_name_errors(self, tmp_path, monkeypatch, capsys):
        """Unlinking a name that doesn't exist produces a clear error."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        monkeypatch.chdir(core)

        args = argparse.Namespace(
            associate_path=None,
            all=False,
            list=False,
            unlink="nonexistent",
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 1

        output = capsys.readouterr().err
        assert "nonexistent" in output or "not found" in output.lower()


class TestAssociateAll:
    """Validates REQ-p00005-C: auto-discovery of associates."""

    # Verifies: REQ-p00005-C
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
            associate_path=None,
            all=True,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "callisto" in output or "CAL" in output
        assert "europa" in output or "EUR" in output

        # Verify both are in .elspais.local.toml as named entries
        local_config = core / ".elspais.local.toml"
        assert local_config.exists()
        doc = tomlkit.parse(local_config.read_text())
        assoc_entries = {k for k in doc["associates"] if isinstance(doc["associates"][k], dict)}
        assert len(assoc_entries) == 2
        assert "callisto" in assoc_entries
        assert "europa" in assoc_entries

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_all_no_associates_found(self, tmp_path, monkeypatch, capsys):
        """--all with no associates reports none found."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=None,
            all=True,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "0" in output or "no" in output.lower() or "none" in output.lower()

    # Verifies: REQ-p00005-F
    def test_REQ_p00005_F_all_deduplicates_relative_and_absolute(
        self, tmp_path, monkeypatch, capsys
    ):
        """--all does not add absolute duplicate when relative path exists in worktree."""
        from elspais.commands.associate_cmd import run

        # Simulate worktree layout: canonical_root != cwd
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")
        _make_associate_repo(workspace, "callisto", "CAL")

        # Simulate a worktree cwd that differs from canonical_root
        worktree_cwd = tmp_path / "worktrees" / "my-branch"
        worktree_cwd.mkdir(parents=True)

        # Pre-create local config with v3 named entry using relative path
        local_config = core / ".elspais.local.toml"
        local_config.write_text('[associates.callisto]\npath = "../callisto"\nnamespace = "CAL"\n')

        # cwd is the worktree, NOT the canonical root
        monkeypatch.chdir(worktree_cwd)
        args = argparse.Namespace(
            associate_path=None,
            all=True,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        # Should not have duplicated — ../callisto resolves from canonical_root
        doc = tomlkit.parse(local_config.read_text())
        assoc_entries = {k for k in doc["associates"] if isinstance(doc["associates"][k], dict)}
        assert len(assoc_entries) == 1

        output = capsys.readouterr().out
        # REQ-d00289-B on the scanning surface, and REQ-d00289-A with it: the
        # report is the recorded relative path, not the absolute candidate.
        assert "no change" in output.lower()
        assert "../callisto" in output
        assert str(workspace / "callisto") not in output
        assert "1 unchanged" in output


# Broken .elspais.toml contents that make load_config() raise, paired with
# fragments (any-of, case-insensitive) that the skip reason must mention.
# Empirically verified against load_config():
#   toml-syntax-error  -> tomlkit UnexpectedCharError
#   schema-unknown-key -> pydantic ValidationError (extra="forbid" on project.type)
#   missing-namespace  -> ValueError ([project].namespace is required)
_BROKEN_CONFIG_CASES = [
    pytest.param(
        'version = 5\n[project\nname = "stale"\n',
        ("unexpected", "parse", "invalid", "toml", "char"),
        id="toml-syntax-error",
    ),
    pytest.param(
        'version = 5\n[project]\nname = "stale"\nnamespace = "STL"\ntype = "associated"\n',
        ("type",),
        id="schema-unknown-key",
    ),
    pytest.param(
        'version = 5\n[project]\nname = "stale"\n',
        ("namespace",),
        id="missing-namespace",
    ),
]


def _make_broken_repo(base: Path, name: str, config_text: str) -> Path:
    """Create a sibling dir that claims to be an elspais repo but fails to load."""
    repo = base / name
    repo.mkdir(exist_ok=True)
    (repo / ".elspais.toml").write_text(config_text)
    return repo


class TestAssociateBrokenSiblingConfig:
    """Validates REQ-d00202-I: a candidate directory whose elspais config fails
    to parse or validate is skipped with the path and reason reported, without
    aborting the scan; dirs without a config stay silently ignored."""

    # Verifies: REQ-d00202-I
    @pytest.mark.parametrize("config_text, reason_fragments", _BROKEN_CONFIG_CASES)
    def test_REQ_d00202_I_discover_returns_error_string_for_unloadable_config(
        self, tmp_path, config_text, reason_fragments
    ):
        """discover_associate_from_path must not raise on an unloadable config;
        it returns an error string naming the path and the reason."""
        from elspais.associates import discover_associate_from_path

        broken = _make_broken_repo(tmp_path, "stale-sibling", config_text)

        result = discover_associate_from_path(broken)

        assert isinstance(result, str), (
            f"Expected an error message string for an unloadable config, got {result!r}"
        )
        assert str(broken) in result, f"Skip reason must name the path: {result!r}"
        # The message must carry the underlying reason, not just the path.
        lowered = result.lower()
        assert any(frag in lowered for frag in reason_fragments), (
            f"Skip reason must explain why the config failed to load "
            f"(expected one of {reason_fragments}): {result!r}"
        )

    # Verifies: REQ-d00202-I
    @pytest.mark.parametrize("config_text, reason_fragments", _BROKEN_CONFIG_CASES)
    def test_REQ_d00202_I_broken_sibling_config_is_skipped_with_reason(
        self, tmp_path, monkeypatch, capsys, config_text, reason_fragments
    ):
        """--all completes past a broken-config sibling: exits 0, links the
        valid sibling, reports the broken path with a reason, and stays silent
        about a plain dir that has no .elspais.toml at all.

        Negative test (red phase): the unguarded load_config() call in
        discover_associate_from_path currently propagates the exception and
        kills the whole scan — this test fails with that raised exception
        until the guard exists.
        """
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")
        _make_associate_repo(workspace, "callisto", "CAL")
        # Sorted before "callisto" so the scan must survive the broken repo
        # to reach and link the valid one.
        broken = _make_broken_repo(workspace, "a-stale-repo", config_text)
        plain = workspace / "b-plain-dir"
        plain.mkdir()
        (plain / "README.md").write_text("not an elspais repo\n")

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=None,
            all=True,
            list=False,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0, "scan must complete and exit 0 despite the broken sibling"

        captured = capsys.readouterr()
        combined = captured.out + captured.err

        # The valid sibling is still discovered and linked.
        local_config = core / ".elspais.local.toml"
        assert local_config.exists()
        doc = tomlkit.parse(local_config.read_text())
        assert "callisto" in doc["associates"], "valid sibling must still be linked"
        assert "a-stale-repo" not in doc.get("associates", {})

        # The broken candidate is reported with its path and a reason.
        assert str(broken) in combined, (
            f"skip report must name the broken sibling's path; output was:\n{combined}"
        )
        lowered = combined.lower()
        assert any(frag in lowered for frag in reason_fragments), (
            f"skip report must include the reason (one of {reason_fragments}); "
            f"output was:\n{combined}"
        )

        # A dir without .elspais.toml is not a candidate: no report at all.
        assert "b-plain-dir" not in combined, (
            f"plain dirs without .elspais.toml must stay silent; output was:\n{combined}"
        )


class TestAssociateList:
    """Validates REQ-p00005-C: listing associate links and status."""

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_list_shows_linked_associates(self, tmp_path, monkeypatch, capsys):
        """--list shows linked associates with status."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        # Pre-create local config with associate path
        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates.callisto]\npath = "{assoc}"\nnamespace = "CAL"\n')

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=None,
            all=False,
            list=True,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "callisto" in output
        assert "CAL" in output

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_list_no_associates(self, tmp_path, monkeypatch, capsys):
        """--list with no associates shows informational message."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        monkeypatch.chdir(core)

        args = argparse.Namespace(
            associate_path=None,
            all=False,
            list=True,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "no" in output.lower() or "none" in output.lower() or "0" in output

    # Verifies: REQ-p00005-E
    def test_REQ_p00005_E_list_shows_broken_path(self, tmp_path, monkeypatch, capsys):
        """--list shows broken status for non-existent paths."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        local_config = core / ".elspais.local.toml"
        local_config.write_text(
            '[associates.callisto]\npath = "/nonexistent/callisto"\nnamespace = "CAL"\n'
        )

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=None,
            all=False,
            list=True,
            unlink=None,
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
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

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_unlink_by_name(self, tmp_path, monkeypatch, capsys):
        """Unlink an associate by name."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        # Pre-create local config with associate path
        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates.callisto]\npath = "{assoc}"\nnamespace = "CAL"\n')

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=None,
            all=False,
            list=False,
            unlink="callisto",
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        output = capsys.readouterr().out
        assert "unlinked" in output.lower() or "callisto" in output.lower()

        # Verify removed from local config
        doc = tomlkit.parse(local_config.read_text())
        assert "callisto" not in doc.get("associates", {})

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_unlink_preserves_other_paths(self, tmp_path, monkeypatch):
        """Unlinking one associate preserves others."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc1 = _make_associate_repo(tmp_path, "callisto", "CAL")
        assoc2 = _make_associate_repo(tmp_path, "europa", "EUR")

        local_config = core / ".elspais.local.toml"
        local_config.write_text(
            f'[associates.callisto]\npath = "{assoc1}"\nnamespace = "CAL"\n\n'
            f'[associates.europa]\npath = "{assoc2}"\nnamespace = "EUR"\n'
        )

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=None,
            all=False,
            list=False,
            unlink="callisto",
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        run(args)

        doc = tomlkit.parse(local_config.read_text())
        assert "callisto" not in doc.get("associates", {})
        assert "europa" in doc["associates"]
        assert doc["associates"]["europa"]["path"] == str(assoc2)

    # Verifies: REQ-p00005-F
    def test_REQ_p00005_F_unlink_by_path_component_substring(self, tmp_path, monkeypatch, capsys):
        """Unlink matches when name is a substring of a path component."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")

        # Simulate worktree path: callisto-worktrees/linking-code
        wt = tmp_path / "callisto-worktrees" / "linking-code"
        wt.mkdir(parents=True)
        (wt / ".elspais.toml").write_text(
            'version = 5\n[project]\nname = "callisto"\nnamespace = "CAL"\n\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )
        (wt / "spec").mkdir()

        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates.callisto]\npath = "{wt}"\nnamespace = "CAL"\n')

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=None,
            all=False,
            list=False,
            unlink="callisto",
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        doc = tomlkit.parse(local_config.read_text())
        assert "callisto" not in doc.get("associates", {})

    # Verifies: REQ-p00005-C
    def test_REQ_p00005_C_unlink_by_prefix_code(self, tmp_path, monkeypatch, capsys):
        """Unlink an associate by its prefix code (e.g., CAL)."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates.callisto]\npath = "{assoc}"\nnamespace = "CAL"\n')

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=None,
            all=False,
            list=False,
            unlink="CAL",
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        doc = tomlkit.parse(local_config.read_text())
        assert "callisto" not in doc.get("associates", {})

    # Verifies: REQ-p00005-F
    def test_REQ_p00005_F_unlink_by_project_name_worktree_path(self, tmp_path, monkeypatch, capsys):
        """Unlink works when stored path is a worktree (basename != project name)."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")

        # Simulate worktree path: workspace/callisto-worktrees/some-feature
        worktree_dir = workspace / "callisto-worktrees" / "some-feature"
        worktree_dir.mkdir(parents=True)
        # But it has callisto's config
        (worktree_dir / ".elspais.toml").write_text(
            'version = 5\n[project]\nname = "callisto"\nnamespace = "CAL"\n\n'
            '[scanning.spec]\ndirectories = ["spec"]\n'
        )
        (worktree_dir / "spec").mkdir()

        local_config = core / ".elspais.local.toml"
        local_config.write_text(
            f'[associates.callisto]\npath = "{worktree_dir}"\nnamespace = "CAL"\n'
        )

        monkeypatch.chdir(core)
        args = argparse.Namespace(
            associate_path=None,
            all=False,
            list=False,
            unlink="callisto",
            config=core / ".elspais.toml",
            verbose=False,
            quiet=False,
        )
        rc = run(args)
        assert rc == 0

        doc = tomlkit.parse(local_config.read_text())
        assert "callisto" not in doc.get("associates", {})


def _link_args(core: Path, path: str | None, **overrides) -> argparse.Namespace:
    """The argument namespace an `elspais associate` invocation is given."""
    kwargs = {
        "associate_path": path,
        "all": False,
        "list": False,
        "unlink": None,
        "config": core / ".elspais.toml",
        "verbose": False,
        "quiet": False,
        "force": False,
    }
    kwargs.update(overrides)
    return argparse.Namespace(**kwargs)


class TestAssociateRegistrationOutcome:
    """Validates REQ-d00289: what a registration run records and reports."""

    # Verifies: REQ-d00289-A
    def test_REQ_d00289_A_report_names_recorded_path_not_argument(
        self, tmp_path, monkeypatch, capsys
    ):
        """A run reports the path the configuration holds, not the target given."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        assoc = _make_associate_repo(tmp_path, "callisto", "CAL")

        local_config = core / ".elspais.local.toml"
        local_config.write_text('[associates.callisto]\npath = "../callisto"\nnamespace = "CAL"\n')

        monkeypatch.chdir(core)
        rc = run(_link_args(core, str(assoc)))
        assert rc == 0

        output = capsys.readouterr().out
        assert "../callisto" in output
        assert str(assoc) not in output, (
            "the report must state what the configuration holds, not the argument"
        )

    # Verifies: REQ-d00289-B
    def test_REQ_d00289_B_all_summarises_unchanged_apart_from_recorded(
        self, tmp_path, monkeypatch, capsys
    ):
        """--all counts a candidate that changed nothing apart from one it recorded."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")
        already = _make_associate_repo(workspace, "callisto", "CAL")
        _make_associate_repo(workspace, "europa", "EUR")

        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates.callisto]\npath = "{already}"\nnamespace = "CAL"\n')

        monkeypatch.chdir(core)
        rc = run(_link_args(core, None, all=True))
        assert rc == 0

        output = capsys.readouterr().out
        assert "Linked 1 associate(s), 1 unchanged, 0 refused" in output

    # Verifies: REQ-d00289-C
    def test_REQ_d00289_C_moved_copy_is_refused_leaving_file_byte_identical(
        self, tmp_path, monkeypatch, capsys
    ):
        """A copy of a recorded associate at a new path is refused, and the
        configuration file is left exactly as it was."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        original = _make_associate_repo(tmp_path, "callisto", "CAL")
        moved_base = tmp_path / "moved"
        moved_base.mkdir()
        # Same declared name and namespace, different location.
        copy = _make_associate_repo(moved_base, "callisto", "CAL")

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(original))) == 0
        capsys.readouterr()

        local_config = core / ".elspais.local.toml"
        before = local_config.read_bytes()

        rc = run(_link_args(core, str(copy)))
        assert rc != 0, "a registration the tool refuses must not exit 0"
        assert local_config.read_bytes() == before

        err = capsys.readouterr().err
        assert "callisto" in err
        assert str(original) in err, "the refusal must name the recorded path"
        assert str(copy) in err, "the refusal must name the target it would record"
        assert "-f" in err, "the refusal must say how to replace the recorded path"
        assert "--list" in err, "the refusal must say how to see the registrations"

    # Verifies: REQ-d00289-D
    def test_REQ_d00289_D_force_repoints_and_reports_both_paths(
        self, tmp_path, monkeypatch, capsys
    ):
        """With force, the entry is repointed and both paths are reported;
        a later --list reads the new one."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        original = _make_associate_repo(tmp_path, "callisto", "CAL")
        moved_base = tmp_path / "moved"
        moved_base.mkdir()
        copy = _make_associate_repo(moved_base, "callisto", "CAL")

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(original))) == 0
        capsys.readouterr()

        rc = run(_link_args(core, str(copy), force=True))
        assert rc == 0

        output = capsys.readouterr().out
        assert str(original) in output, "the report must name the path replaced"
        assert str(copy) in output, "the report must name the path recorded"

        doc = tomlkit.parse((core / ".elspais.local.toml").read_text())
        assert doc["associates"]["callisto"]["path"] == str(copy)

        assert run(_link_args(core, None, list=True)) == 0
        listing = capsys.readouterr().out
        assert str(copy) in listing
        assert str(original) not in listing

    # Verifies: REQ-d00289-E
    @pytest.mark.parametrize("collides_with", ["core", "existing-associate"])
    def test_REQ_d00289_E_federation_refusal_stops_registration(
        self, tmp_path, monkeypatch, capsys, collides_with
    ):
        """A namespace collision the federation planner would refuse
        (REQ-d00202-K) is refused at registration, writing nothing."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        local_config = core / ".elspais.local.toml"
        monkeypatch.chdir(core)

        if collides_with == "core":
            namespace = "REQ"
        else:
            namespace = "CAL"
            existing = _make_associate_repo(tmp_path, "callisto", "CAL")
            assert run(_link_args(core, str(existing))) == 0
            capsys.readouterr()

        clash = _make_associate_repo(tmp_path, "ganymede", namespace)
        before = local_config.read_bytes() if local_config.exists() else None

        rc = run(_link_args(core, str(clash)))
        assert rc != 0

        after = local_config.read_bytes() if local_config.exists() else None
        assert after == before, "a refused registration must write nothing"

        err = capsys.readouterr().err
        assert "namespace" in err.lower(), "the refusal must carry the federation's reason"
        assert namespace in err
        assert "ganymede" in err

    # Verifies: REQ-d00289-F
    def test_REQ_d00289_F_all_reports_refusal_and_keeps_scanning(
        self, tmp_path, monkeypatch, capsys
    ):
        """One refused candidate neither ends the --all scan nor suppresses
        the candidates around it; the run still exits non-zero."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")
        # Sorts before "callisto", so the scan must survive it to reach the
        # candidate that does register.
        _make_associate_repo(workspace, "aclone", "REQ")
        _make_associate_repo(workspace, "callisto", "CAL")

        monkeypatch.chdir(core)
        rc = run(_link_args(core, None, all=True))
        assert rc != 0, "a scan that refused a candidate must not exit 0"

        captured = capsys.readouterr()
        # A refusal reads the same from either surface: on stderr, where a
        # single registration puts it.
        assert "aclone" in captured.err
        assert "namespace" in captured.err.lower()
        assert "callisto" in captured.out
        assert "Linked 1 associate(s), 0 unchanged, 1 refused" in captured.out

        doc = tomlkit.parse((core / ".elspais.local.toml").read_text())
        assert "callisto" in doc["associates"]
        assert "aclone" not in doc["associates"]


def _write_associate_config(repo: Path, name: str, prefix: str) -> Path:
    """Give a directory an associate config declaring a name of its own.

    A repository's declared name need not be its directory name, which is
    what lets two candidates of one scan claim the same entry.
    """
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".elspais.toml").write_text(
        f'version = 5\n[project]\nname = "{name}"\nnamespace = "{prefix}"\n\n'
        f'[scanning.spec]\ndirectories = ["spec"]\n'
    )
    (repo / "spec").mkdir(exist_ok=True)
    return repo


class TestAssociateRivalCandidates:
    """Validates REQ-d00289: candidates of one scan sharing a declared name,
    and an entry matched by name against an entry matched by path."""

    # Verifies: REQ-d00289-G, REQ-d00289-C
    def test_REQ_d00289_G_shared_name_with_distinct_namespaces_is_not_contested(
        self, tmp_path, monkeypatch, capsys
    ):
        """G is the namespace rule read at scan time, and a shared declared
        name is not its business: two candidates declaring different
        namespaces own disjoint identifiers, so nothing about them is
        ambiguous. They contend only for the entry key, which is what C
        already decides -- the first is recorded and the second is refused
        against the path recorded under that name, rather than both being
        withheld as a contested pair."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")
        first = _write_associate_config(workspace / "a-callisto", "callisto", "CAL")
        second = _write_associate_config(workspace / "b-callisto", "callisto", "CA2")

        monkeypatch.chdir(core)
        rc = run(_link_args(core, None, all=True))

        captured = capsys.readouterr()
        assert rc != 0, "the second candidate contends for an entry already recorded"
        assert "Linked 1 associate(s), 0 unchanged, 1 refused" in captured.out, captured.out
        assert "none of them was recorded" not in captured.err, (
            "a shared name is not the contested-namespace case, so neither "
            "candidate may be withheld for it"
        )
        assert str(first) in captured.err and str(second) in captured.err, (
            "the entry-exists refusal names the recorded path and the target"
        )

        doc = tomlkit.parse((core / ".elspais.local.toml").read_text())
        entries = {k for k in doc["associates"] if isinstance(doc["associates"][k], dict)}
        assert entries == {"callisto"}
        assert doc["associates"]["callisto"]["path"] == str(first), (
            "the candidate reached first holds the entry; the other is refused, not swapped in"
        )

    # Verifies: REQ-d00289-C
    @pytest.mark.parametrize("name_entry_first", [True, False])
    def test_REQ_d00289_C_name_match_decides_regardless_of_file_order(
        self, tmp_path, monkeypatch, capsys, name_entry_first
    ):
        """An entry under the target's own name decides the outcome even when
        an unrelated entry records the very path being registered, whichever
        of the two is written into the file first. One obstacle is met -- the
        entry named records another path -- so C governs, and the refusal
        says how to replace the path it names."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        target = _make_associate_repo(tmp_path, "callisto", "CAL")
        # The entry under the target's name records a repository declaring a
        # namespace of its own, so the starting configuration federates and
        # the entry recording the target's path is the only thing this run
        # meets besides the entry named. Two entries reaching ONE directory
        # converge on one member, so recording the target twice is not a
        # namespace collision.
        recorded_elsewhere = _write_associate_config(
            tmp_path / "moved" / "callisto", "callisto", "OTH"
        )

        by_name = f'[associates.callisto]\npath = "{recorded_elsewhere}"\nnamespace = "OTH"\n'
        by_path = f'[associates.mirror]\npath = "{target}"\nnamespace = "CAL"\n'
        local_config = core / ".elspais.local.toml"
        local_config.write_text(
            f"{by_name}\n{by_path}" if name_entry_first else f"{by_path}\n{by_name}"
        )
        before = local_config.read_bytes()

        monkeypatch.chdir(core)
        rc = run(_link_args(core, str(target)))

        assert rc != 0, "the name-matching entry records another path, so this is a refusal"
        assert local_config.read_bytes() == before

        err = capsys.readouterr().err
        assert str(recorded_elsewhere) in err, (
            "the refusal must name the path recorded under this entry, "
            "not the one recorded under another name"
        )
        assert str(target) in err
        assert "-f" in err


class TestAssociateSameNamespaceTwice:
    """Validates REQ-d00289-H: one namespace names one member, so an entry
    already recording a namespace at another directory is an obstacle to a
    registration that would record it again."""

    # Verifies: REQ-d00289-H
    def test_REQ_d00289_H_other_name_same_namespace_is_refused(self, tmp_path, monkeypatch, capsys):
        """A second directory declaring an already-recorded namespace is
        refused under a name of its own. The refusal names both directories
        -- which is what tells the operator which of the two they are about
        to stop reading -- and identifies the entry already holding the
        namespace. Nothing is written."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        # The declared names share nothing with the directory names, so the
        # entry can only be identified from what the refusal says about it.
        first = _write_associate_config(tmp_path / "one", "alpha", "LIB")
        # A second directory claiming the same identifiers under another name.
        second = _write_associate_config(tmp_path / "two", "beta", "LIB")

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(first))) == 0
        capsys.readouterr()

        local_config = core / ".elspais.local.toml"
        before = local_config.read_bytes()

        assert run(_link_args(core, str(second))) != 0
        assert local_config.read_bytes() == before, "a refused registration must write nothing"

        err = capsys.readouterr().err
        assert "LIB" in err, "the refusal must name the namespace in contention"
        assert str(first) in err and str(second) in err, (
            "the refusal must name both directories claiming the namespace"
        )
        assert "alpha" in err, "the entry already recording the namespace must be identifiable"

        doc = tomlkit.parse(local_config.read_text())
        entries = {k for k in doc["associates"] if isinstance(doc["associates"][k], dict)}
        assert entries == {"alpha"}

    # Verifies: REQ-d00289-E, REQ-d00289-H
    def test_REQ_d00289_H_namespace_collision_is_refused_with_or_without_force(
        self, tmp_path, monkeypatch, capsys
    ):
        """One namespace names one member, so a second directory claiming a
        recorded namespace is a membership the federation would refuse --
        and an instruction to replace a recorded path says nothing about
        that. The answer is the same either way round, and the
        configuration is untouched both times."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        first = _write_associate_config(tmp_path / "lib", "lib", "LIB")
        second = _write_associate_config(tmp_path / "lib-copy", "lib2", "LIB")

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(first))) == 0
        capsys.readouterr()

        local_config = core / ".elspais.local.toml"
        before = local_config.read_bytes()

        assert run(_link_args(core, str(second))) != 0
        plain = capsys.readouterr().err
        assert local_config.read_bytes() == before

        assert run(_link_args(core, str(second), force=True)) != 0, (
            "-f replaces a recorded path; it does not make one namespace name two members"
        )
        forced = capsys.readouterr().err
        assert local_config.read_bytes() == before, "a refused registration must write nothing"

        assert forced == plain, "the answer must not depend on whether -f was given"

        doc = tomlkit.parse(local_config.read_text())
        entries = {k for k in doc["associates"] if isinstance(doc["associates"][k], dict)}
        assert entries == {"lib"}, "the entry already holding the namespace stands"

    # Verifies: REQ-d00289-C, REQ-d00289-H
    def test_REQ_d00289_C_same_name_other_directory_is_the_entry_exists_refusal(
        self, tmp_path, monkeypatch, capsys
    ):
        """Two directories declaring one name is the entry-exists refusal,
        naming the recorded path and the target. What the two directories are
        to each other is not part of it: the refusal reports the declarations
        it read, and nothing is consulted beyond them. This is also H read
        where the registration would be recorded under the entry's own name:
        the namespace declared is the one that entry already records at
        another directory, and the refusal names the entry and both
        directories."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        first = _write_associate_config(tmp_path / "lib", "lib", "LIB")
        second = _write_associate_config(tmp_path / "lib-copy" / "lib", "lib", "LIB")

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(first))) == 0
        capsys.readouterr()

        local_config = core / ".elspais.local.toml"
        before = local_config.read_bytes()

        assert run(_link_args(core, str(second))) != 0
        assert local_config.read_bytes() == before

        err = capsys.readouterr().err
        assert f"lib is already registered at {first}" in err
        assert str(second) in err
        assert "repository" not in err.lower(), (
            "registration reads declarations, so it must not claim anything "
            "about the repositories the directories hold"
        )

    # Verifies: REQ-d00289-H
    def test_REQ_d00289_H_different_namespaces_are_two_entries(self, tmp_path, monkeypatch, capsys):
        """Two directories declaring different namespaces both register, however
        closely related they are. This is a deliberate allowance, not an
        oversight: a derived copy that renames its namespace owns identifiers
        disjoint from its ancestor's, so it is a member in its own right."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        original = _write_associate_config(tmp_path / "lib", "lib", "LIB")
        # The same project, copied and renamed: new namespace, new identifiers.
        derived = _write_associate_config(tmp_path / "lib-fork", "libfork", "FRK")

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(original))) == 0
        assert run(_link_args(core, str(derived))) == 0
        capsys.readouterr()

        doc = tomlkit.parse((core / ".elspais.local.toml").read_text())
        entries = {k for k in doc["associates"] if isinstance(doc["associates"][k], dict)}
        assert entries == {"lib", "libfork"}
        assert doc["associates"]["lib"]["path"] == str(original)
        assert doc["associates"]["libfork"]["path"] == str(derived)

    # Verifies: REQ-d00289-G, REQ-d00289-H
    @pytest.mark.parametrize(
        "clean_dir,rival_dirs",
        [
            ("a-callisto", ("b-lib", "c-lib")),
            ("b-callisto", ("a-lib", "c-lib")),
            ("c-callisto", ("a-lib", "b-lib")),
        ],
    )
    def test_REQ_d00289_G_all_records_neither_candidate_for_one_namespace(
        self, tmp_path, monkeypatch, capsys, clean_dir, rival_dirs
    ):
        """Two candidates of one scan declaring one namespace stand for one
        entry: neither is recorded and both directories are named, while an
        uncontested candidate of the same scan still links. The scan reaches
        candidates in directory-name order, so the directories are named to
        place the uncontested one before, between and after the contested
        pair -- the outcome is the same each way round."""
        from elspais.commands.associate_cmd import run

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        core = _make_core_repo(workspace / "core")
        first = _write_associate_config(workspace / rival_dirs[0], "lib", "LIB")
        second = _write_associate_config(workspace / rival_dirs[1], "lib2", "LIB")
        _write_associate_config(workspace / clean_dir, "callisto", "CAL")

        monkeypatch.chdir(core)
        assert run(_link_args(core, None, all=True, force=True)) != 0, (
            "a scan that refused a candidate must not exit 0"
        )

        captured = capsys.readouterr()
        assert "Linked 1 associate(s), 0 unchanged, 2 refused" in captured.out
        assert str(first) in captured.err, "both contested directories must be named"
        assert str(second) in captured.err, "both contested directories must be named"
        assert "LIB" in captured.err, "the refusal must name the namespace in contention"
        assert "by path" in captured.err.lower(), (
            "the refusal must say how to register the one meant"
        )

        doc = tomlkit.parse((core / ".elspais.local.toml").read_text())
        entries = {k for k in doc["associates"] if isinstance(doc["associates"][k], dict)}
        assert entries == {"callisto"}, (
            "the uncontested candidate links; neither contested candidate is recorded"
        )


class TestAssociatePreExistingFederationFault:
    """Validates REQ-d00289-I: a configuration that already will not federate
    refuses every candidate put to it, and says so."""

    # Verifies: REQ-d00289-I
    def test_REQ_d00289_I_pre_existing_fault_is_not_blamed_on_the_candidate(
        self, tmp_path, monkeypatch, capsys
    ):
        """A declaration pointing at a repository that declares another
        namespace (REQ-d00202-L) is a fault the planner reaches and the
        registration checks do not: an unrelated candidate put to it is
        refused as a fault the configuration already held, and that reads
        differently from the fault a candidate introduces."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        # The entry expects LIB; the repository there says it owns OTH.
        mismatched = _write_associate_config(tmp_path / "lib", "lib", "OTH")
        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates.lib]\npath = "{mismatched}"\nnamespace = "LIB"\n')
        before = local_config.read_bytes()

        gamma = _write_associate_config(tmp_path / "gamma", "gamma", "GAM")

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(gamma))) != 0
        assert local_config.read_bytes() == before, "a refused registration must write nothing"

        standing = capsys.readouterr().err
        assert "does not federate as it stands" in standing
        assert "before gamma" in standing, "the refusal must say the fault predates the candidate"
        assert str(mismatched) in standing, (
            "the refusal must name the entry at fault, not only the candidate"
        )
        assert "would not federate" not in standing, (
            "a standing fault must not read as one the candidate introduces"
        )

        # The other half of the contrast: a collision this candidate brings.
        # The core repository's own namespace is not an entry, so no
        # registration check stands between the candidate and the planner.
        other_core = _make_core_repo(tmp_path / "other-core")
        clash = _write_associate_config(tmp_path / "ganymede", "ganymede", "REQ")

        monkeypatch.chdir(other_core)
        assert run(_link_args(other_core, str(clash))) != 0
        introduced = capsys.readouterr().err

        assert "would not federate" in introduced
        assert "ganymede" in introduced
        assert "does not federate as it stands" not in introduced
        assert introduced.splitlines()[0] != standing.splitlines()[0], (
            "a standing fault and one the candidate introduces must read differently"
        )

    # Verifies: REQ-d00289-E, REQ-d00289-I
    def test_REQ_d00289_I_a_standing_unreadable_declaration_refuses_the_candidate(
        self, tmp_path, monkeypatch, capsys
    ):
        """A declaration pointing at nothing is a fault the build refuses
        (REQ-d00202-M), so a registration put to that configuration is
        refused too -- reported as a fault the configuration already held,
        naming the entry that points nowhere rather than the candidate."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        nowhere = tmp_path / "nowhere"
        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates.ghost]\npath = "{nowhere}"\nnamespace = "GHO"\n')
        before = local_config.read_bytes()

        gamma = _write_associate_config(tmp_path / "gamma", "gamma", "GAM")

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(gamma))) != 0
        assert local_config.read_bytes() == before, "a refused registration must write nothing"

        err = capsys.readouterr().err
        assert "does not federate as it stands" in err
        assert "before gamma" in err
        assert "ghost" in err, "the refusal must name the entry that points nowhere"
        assert str(nowhere) in err

    # Verifies: REQ-d00289-E, REQ-d00289-I
    def test_REQ_d00289_E_an_unreadable_declaration_the_candidate_brings_is_refused(
        self, tmp_path, monkeypatch, capsys
    ):
        """A candidate whose own declarations reach nothing would make the
        federation unbuildable, so it is refused before anything is written
        -- as a fault the registration introduces, not a standing one."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        nowhere = tmp_path / "nowhere"
        lib = _write_associate_config(tmp_path / "lib", "lib", "LIB")
        (lib / ".elspais.toml").write_text(
            (lib / ".elspais.toml").read_text()
            + f'\n[associates.phantom]\npath = "{nowhere}"\nnamespace = "PHA"\n'
        )
        local_config = core / ".elspais.local.toml"

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(lib))) != 0
        assert not local_config.exists(), "a refused registration must write nothing"

        err = capsys.readouterr().err
        assert "would not federate" in err
        assert "does not federate as it stands" not in err
        assert "phantom" in err
        assert str(nowhere) in err


def _core_declaring(tmp_path: Path, entries: str) -> Path:
    """A core repo whose MAIN config declares associate entries of its own.

    `elspais associate` writes only `.elspais.local.toml`, so an entry the
    main config declares is one the command reads but cannot rewrite.
    """
    core = _make_core_repo(tmp_path / "core")
    config = core / ".elspais.toml"
    config.write_text(config.read_text() + entries)
    return core


class TestAssociateNamesTheDirectoryTheFederationReached:
    """Validates REQ-d00289-H with REQ-d00290-A: the two directories a
    namespace collision names are the ones the federation actually reached,
    which is what the assembled configuration says and not what any single
    file writes."""

    # Verifies: REQ-d00289-H, REQ-d00290-A
    def test_REQ_d00289_H_refusal_names_the_directory_the_federation_reached(
        self, tmp_path, monkeypatch, capsys
    ):
        """A machine-local override redirects an entry the committed file
        declares, so the directory colliding with the candidate is the one
        the override names. The path written in the committed file is not in
        the federation at all, and naming it would send the operator to a
        directory that collides with nothing."""
        from elspais.commands.associate_cmd import run

        core = _core_declaring(
            tmp_path, '\n[associates.libA]\npath = "../libA"\nnamespace = "LIB"\n'
        )
        # The path the committed file writes, which the override takes out of
        # the federation. Its name is not a substring of the override's.
        abandoned = _write_associate_config(tmp_path / "libA", "libA", "LIB")
        moved = _write_associate_config(tmp_path / "moved" / "libA", "libA", "LIB")
        second = _write_associate_config(tmp_path / "libB", "libB", "LIB")

        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates.libA]\npath = "{moved}"\nnamespace = "LIB"\n')
        before = local_config.read_bytes()

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(second))) != 0
        assert local_config.read_bytes() == before, "a refused registration must write nothing"

        err = capsys.readouterr().err
        assert "LIB" in err, "the refusal must name the namespace in contention"
        assert str(moved) in err and str(second) in err, (
            "the refusal must name both directories the federation reached"
        )
        assert "libA" in err, "the entry already recording the namespace must be identifiable"
        assert str(abandoned) not in err, (
            "the committed file's path is not the directory the federation reached"
        )
        assert "../libA" not in err, (
            "the refusal must not quote the relative path the committed file writes"
        )
        assert "Use -f" not in err, (
            "offering -f for a collision -f cannot clear sends the operator into a retry "
            "that refuses identically"
        )


class TestAssociateForcedPastAnUnretireableRival:
    """Validates REQ-d00289-C: what a refusal says once -f has been given."""

    # Verifies: REQ-d00289-C, REQ-d00289-E
    def test_REQ_d00289_C_forced_refusal_carries_the_collision_not_another_force_hint(
        self, tmp_path, monkeypatch, capsys
    ):
        """The namespace is claimed by a repository another member declares,
        so no entry of this configuration can be retired to make room. Under
        -f the refusal reports that collision; repeating an instruction the
        operator has already followed names no fault at all."""
        from elspais.commands.associate_cmd import run

        core = _core_declaring(tmp_path, '\n[associates.mid]\npath = "../mid"\nnamespace = "MID"\n')
        mid = _write_associate_config(tmp_path / "mid", "mid", "MID")
        (mid / ".elspais.toml").write_text(
            (mid / ".elspais.toml").read_text()
            + '\n[associates.beta]\npath = "../beta"\nnamespace = "LIB"\n'
        )
        beta = _write_associate_config(tmp_path / "beta", "beta", "LIB")
        # The entry under the name the candidate declares points elsewhere,
        # so the registration would move it -- the one obstacle -f is for.
        old = _write_associate_config(tmp_path / "libx-old", "libx", "OLD")
        candidate = _write_associate_config(tmp_path / "libx-copy", "libx", "LIB")

        local_config = core / ".elspais.local.toml"
        local_config.write_text(f'[associates.libx]\npath = "{old}"\nnamespace = "OLD"\n')
        before = local_config.read_bytes()

        monkeypatch.chdir(core)
        assert run(_link_args(core, str(candidate), force=True)) != 0
        assert local_config.read_bytes() == before, "a refused registration must write nothing"

        err = capsys.readouterr().err
        assert "Use -f" not in err, (
            "-f was given; repeating it reports an obstacle that is not the one met"
        )
        assert "would not federate" in err, err
        assert "LIB" in err and str(beta) in err and str(candidate) in err, (
            "the refusal must name the namespace and both directories claiming it"
        )


# One entry, one spelling: the same declaration content routed into either
# configuration file, so the only thing a test varies is which file holds it.
_MISPOINTED_ENTRY = '\n[associates.oldname]\npath = "../libX"\nnamespace = "WRONG"\n'


def _core_holding(tmp_path: Path, holder: str) -> Path:
    """A core repo whose configuration holds `_MISPOINTED_ENTRY` in `holder`."""
    if holder == ".elspais.toml":
        return _core_declaring(tmp_path, _MISPOINTED_ENTRY)
    core = _make_core_repo(tmp_path / "core")
    (core / holder).write_text(_MISPOINTED_ENTRY.lstrip("\n"))
    return core


class TestAssociateReadsTheAssembledConfiguration:
    """Validates REQ-d00290-A: a configuration assembled with a machine-local
    overlay answers as one holding the assembled result in its committed file
    alone, so which file a declaration was written into settles nothing."""

    # Verifies: REQ-d00290-A, REQ-d00289-I
    @pytest.mark.parametrize("holder", [".elspais.toml", ".elspais.local.toml"])
    def test_REQ_d00290_A_registration_answers_the_same_from_either_file(
        self, tmp_path, monkeypatch, capsys, holder
    ):
        """An entry pointing at a repository that declares another namespace
        (REQ-d00202-L) is a configuration that does not federate. Registering
        the repository it points at is refused for that standing fault -- and
        is refused identically whether the entry was committed or written by
        the machine-local overlay, since a registration reads the assembled
        configuration and not the file it happens to write."""
        from elspais.commands.associate_cmd import run

        core = _core_holding(tmp_path, holder)
        # The entry expects WRONG; the repository there declares LIB.
        target = _write_associate_config(tmp_path / "libX", "libX", "LIB")

        local_config = core / ".elspais.local.toml"
        before = local_config.read_bytes() if local_config.exists() else None

        monkeypatch.chdir(core)
        rc = run(_link_args(core, str(target)))

        captured = capsys.readouterr()
        after = local_config.read_bytes() if local_config.exists() else None
        assert after == before, "a refused registration must write nothing"

        assert rc == 1, "a configuration that will not federate is refused however it was assembled"
        assert "No change" not in captured.out, (
            "reporting success over a configuration that will not federate is "
            "the failure this invariant exists to catch"
        )
        assert "does not federate as it stands" in captured.err
        assert str(target) in captured.err
        assert "WRONG" in captured.err and "LIB" in captured.err, (
            "the refusal must carry the mismatch the planner reached"
        )


class TestAssociateListReportsLocalOverride:
    """Validates REQ-d00290-B: a member assembled with a machine-local overlay
    is reported as locally overridden."""

    # Verifies: REQ-d00290-B
    def test_REQ_d00290_B_list_marks_only_the_overridden_member(
        self, tmp_path, monkeypatch, capsys
    ):
        """The listing marks the member holding a machine-local overlay and
        leaves the one assembled from its committed file alone unmarked."""
        from elspais.commands.associate_cmd import run

        core = _make_core_repo(tmp_path / "core")
        overridden = _make_associate_repo(tmp_path, "callisto", "CAL")
        plain = _make_associate_repo(tmp_path, "europa", "EUR")
        # An overlay that changes no value: what is reported is that a
        # machine-local file took part, not what it contributed.
        (overridden / ".elspais.local.toml").write_text("# machine-local overlay\n")

        (core / ".elspais.local.toml").write_text(
            f'[associates.callisto]\npath = "{overridden}"\nnamespace = "CAL"\n\n'
            f'[associates.europa]\npath = "{plain}"\nnamespace = "EUR"\n'
        )

        monkeypatch.chdir(core)
        assert run(_link_args(core, None, list=True)) == 0

        rows = {
            line.split()[0]: line.split()
            for line in capsys.readouterr().out.splitlines()
            if line.split() and line.split()[0] in ("callisto", "europa")
        }
        assert set(rows) == {"callisto", "europa"}, rows
        # Name, prefix, status, local, path.
        assert rows["callisto"][3] == "yes", rows["callisto"]
        assert rows["europa"][3] == "-", rows["europa"]


class TestAssociateRelativePathResolution:
    """Validates REQ-d00289-A: a recorded relative path is read against the
    repository root it was written against."""

    # Verifies: REQ-d00289-A, REQ-d00290-A
    def test_REQ_d00289_A_recorded_relative_path_resolves_against_the_repo_root(self, tmp_path):
        """Under a worktree the repository root is not the directory holding
        the configuration. A recorded relative path resolves against the root
        given, so the entry already recording the repository being registered
        is recognised as that entry rather than as an unrelated one."""
        from elspais.commands.associate_cmd import Outcome, register_associate

        (tmp_path / "held").mkdir()
        config_dir = _make_core_repo(tmp_path / "held" / "core")
        repo_root = tmp_path / "tree" / "worktree"
        repo_root.mkdir(parents=True)
        target = _write_associate_config(tmp_path / "tree" / "lib", "lib", "LIB")
        # The same relative path read against config_dir names a directory
        # that is not there at all, so the two bases cannot agree by accident.
        assert not (config_dir.parent / "lib").exists()

        (config_dir / ".elspais.local.toml").write_text(
            '[associates.lib]\npath = "../lib"\nnamespace = "LIB"\n'
        )
        before = (config_dir / ".elspais.local.toml").read_bytes()

        outcome = register_associate(
            config_dir,
            str(target),
            "lib",
            "LIB",
            repo_root=repo_root,
            config_path=config_dir / ".elspais.toml",
        )

        assert outcome.kind is Outcome.UNCHANGED, (
            "the recorded relative path names this very repository once it is "
            "read against the repository root"
        )
        assert outcome.path == "../lib", "the report states what the configuration holds"
        assert (config_dir / ".elspais.local.toml").read_bytes() == before
