# Verifies: REQ-d00253-F
"""elspais fix must not claim to fix associate-owned content it will not write.

Validates REQ-d00253-F: with federation.write_associates=false, every
fix-report line for an associate-owned node is prefixed [skipping] (both
"Fixed" and dry-run "Would fix" reports); primary-repo lines stay plain.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest.mock import patch

import pytest

_PRIMARY_CONFIG = """\
version = 5

[project]
name = "primary"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false

[associates.callisto]
path = "../callisto"
namespace = "CAL"
"""

_ASSOCIATE_CONFIG = """\
version = 5

[project]
name = "callisto"
namespace = "CAL"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false
"""

# Both requirements carry a deliberately stale **Hash** so `elspais fix`
# detects exactly one fixable issue (update hash) in each repo.
_PRIMARY_SPEC = """\
# Primary Requirements

## REQ-p00001: Primary Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

Primary intro text.

### Assertions

A. The system SHALL validate input.

*End* *Primary Requirement* | **Hash**: deadbeef
"""

_ASSOCIATE_SPEC = """\
# Callisto Requirements

## CAL-p00001: Library Requirement

**Level**: PRD | **Status**: Active | **Implements**: -

Library intro text.

### Assertions

A. The system SHALL process data.

*End* *Library Requirement* | **Hash**: 00000000
"""

_STALE_ASSOCIATE_HASH = "00000000"
_STALE_PRIMARY_HASH = "deadbeef"


@pytest.fixture()
def federated_fixable_workspace(tmp_path: Path) -> dict[str, Path]:
    """Primary repo + associate repo, each with one stale-hash requirement.

    federation.write_associates defaults to false, so render_save will only
    ever write the primary file — the associate's fixable issue is detected
    but must never be claimed as applied.
    """
    primary = tmp_path / "primary"
    associate = tmp_path / "callisto"
    (primary / "spec").mkdir(parents=True)
    (associate / "spec").mkdir(parents=True)

    (primary / ".elspais.toml").write_text(_PRIMARY_CONFIG)
    (primary / "spec" / "core.md").write_text(_PRIMARY_SPEC)
    (associate / ".elspais.toml").write_text(_ASSOCIATE_CONFIG)
    (associate / "spec" / "lib.md").write_text(_ASSOCIATE_SPEC)

    return {"primary": primary, "associate": associate}


class TestFixAssociateSkipReporting:
    """Validates REQ-d00253-F: fix-report lines for associate-owned nodes are
    prefixed [skipping] and the output never claims an associate-owned fix was
    applied; primary-repo lines remain plain."""

    @pytest.mark.parametrize(
        "dry_run, verb",
        [(False, "Fixed"), (True, "Would fix")],
        ids=["apply", "dry-run"],
    )
    def test_REQ_d00253_F_associate_lines_prefixed_skipping(
        self, federated_fixable_workspace, monkeypatch, capsys, dry_run, verb
    ):
        """Associate-owned fixable nodes are reported [skipping]; the plain
        '<verb> CAL-...' claim never appears; primary lines stay plain."""
        from elspais.commands.fix_cmd import run

        primary = federated_fixable_workspace["primary"]
        associate = federated_fixable_workspace["associate"]

        monkeypatch.chdir(primary)
        args = argparse.Namespace(
            req_id=None,
            dry_run=dry_run,
            spec_dir=None,
            config=primary / ".elspais.toml",
            quiet=False,
            verbose=False,
            git_root=primary,
        )
        rc = run(args)
        assert rc == 0

        lines = capsys.readouterr().out.splitlines()

        # Primary-repo fixable node is still reported plainly.
        assert any(line.startswith(f"{verb} REQ-p00001") for line in lines), (
            f"primary-repo node must keep its plain '{verb}' line; got:\n" + "\n".join(lines)
        )

        # The report must never claim work on associate-owned content that
        # will not be written (write_associates defaults to false).
        offending = [line for line in lines if line.startswith(f"{verb} CAL-p00001")]
        assert not offending, (
            f"associate-owned node must not get an unprefixed '{verb}' claim; "
            f"offending lines: {offending}"
        )

        # Instead each associate-owned line is prefixed [skipping] and still
        # names the node so the operator can see what was left untouched.
        skip_lines = [line for line in lines if line.startswith("[skipping]")]
        assert any("CAL-p00001" in line for line in skip_lines), (
            "associate-owned fixable node must appear on a line starting with "
            "'[skipping]'; got:\n" + "\n".join(lines)
        )

        # Ground truth on disk: the associate file is never written, so the
        # report above is the only honest description of what happened.
        associate_content = (associate / "spec" / "lib.md").read_text()
        assert _STALE_ASSOCIATE_HASH in associate_content, (
            "associate file must remain untouched (write_associates=false)"
        )
        primary_content = (primary / "spec" / "core.md").read_text()
        if dry_run:
            assert _STALE_PRIMARY_HASH in primary_content, "dry-run must not write files"
        else:
            assert _STALE_PRIMARY_HASH not in primary_content, (
                "primary repo fix must actually be applied"
            )


_MOCK_AUTHOR = {"name": "Test Author", "id": "test@example.com"}


def _args(primary: Path, dry_run: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        req_id=None,
        dry_run=dry_run,
        spec_dir=None,
        config=primary / ".elspais.toml",
        quiet=False,
        verbose=False,
        git_root=primary,
    )


@pytest.fixture()
def changelog_enforced_workspace(federated_fixable_workspace) -> dict[str, Path]:
    """The federated workspace with changelog enforcement on in both repos.

    Each Active requirement then needs a changelog entry, so a fix that
    queued one for the associate's requirement would leave the save work it
    must hold back.
    """
    for repo in federated_fixable_workspace.values():
        cfg = repo / ".elspais.toml"
        cfg.write_text(cfg.read_text().replace("hash_current = false", "hash_current = true"))
    return federated_fixable_workspace


class TestFixLeavesAssociateAlone:
    """A fix whose write scope excludes an associate queues nothing for it,
    so the primary repository is written as it would be without the associate."""

    # Verifies: REQ-d00253-B, REQ-d00330-A, REQ-d00330-B
    @patch(
        "elspais.utilities.changelog_author.resolve_changelog_author",
        return_value=_MOCK_AUTHOR,
    )
    def test_primary_written_when_associate_needs_changelog(
        self, _mock_author, changelog_enforced_workspace, monkeypatch, capsys
    ):
        from elspais.commands.fix_cmd import run

        primary = changelog_enforced_workspace["primary"]
        associate = changelog_enforced_workspace["associate"]
        associate_before = (associate / "spec" / "lib.md").read_text()

        monkeypatch.chdir(primary)
        rc = run(_args(primary))
        captured = capsys.readouterr()

        assert rc == 0, captured.err
        primary_content = (primary / "spec" / "core.md").read_text()
        assert _STALE_PRIMARY_HASH not in primary_content
        assert "## Changelog" in primary_content
        assert (associate / "spec" / "lib.md").read_text() == associate_before
        lines = captured.out.splitlines()
        assert any(line.startswith("Fixed REQ-p00001") for line in lines)
        assert not any(line.startswith("Not fixed") for line in lines)
        assert any(line.startswith("[skipping] CAL-p00001") for line in lines)

    # Verifies: REQ-d00253-B
    @patch(
        "elspais.utilities.changelog_author.resolve_changelog_author",
        return_value=_MOCK_AUTHOR,
    )
    def test_primary_output_identical_without_associate(
        self, _mock_author, changelog_enforced_workspace, tmp_path, monkeypatch
    ):
        """The primary file a fix writes does not depend on the associate."""
        import shutil

        from elspais.commands.fix_cmd import run

        primary = changelog_enforced_workspace["primary"]
        solo = tmp_path / "solo"
        shutil.copytree(primary, solo)
        cfg = solo / ".elspais.toml"
        cfg.write_text(cfg.read_text().split("[associates.callisto]")[0])

        monkeypatch.chdir(primary)
        assert run(_args(primary)) == 0
        monkeypatch.chdir(solo)
        assert run(_args(solo)) == 0

        assert (primary / "spec" / "core.md").read_text() == (solo / "spec" / "core.md").read_text()


class TestFixReportsUnwrittenChanges:
    """A fix whose save writes nothing says so and fails."""

    # Verifies: REQ-d00330-D, REQ-p00015-B
    def test_declined_save_exits_nonzero_and_claims_no_fix(
        self, federated_fixable_workspace, monkeypatch, capsys
    ):
        import elspais.graph.render as render
        from elspais.commands.fix_cmd import run

        declined = {
            "success": False,
            "saved_count": 0,
            "files_modified": [],
            "conflicts": [],
            "errors": ["file:REQ:spec/core.md: held back"],
            "skipped": [],
            "changed_beyond_edits": [],
            "code": "write_scope_declined",
            "error": "This save did not write file:REQ:spec/core.md",
        }
        monkeypatch.setattr(render, "render_save", lambda *a, **k: declined)

        primary = federated_fixable_workspace["primary"]
        monkeypatch.chdir(primary)
        rc = run(_args(primary))
        captured = capsys.readouterr()

        assert rc != 0
        lines = captured.out.splitlines()
        assert any(line.startswith("Not fixed REQ-p00001") for line in lines)
        assert not any(line.startswith(("Fixed", "Rewrote")) for line in lines)
        assert "held back" in captured.err
        assert _STALE_PRIMARY_HASH in (primary / "spec" / "core.md").read_text()


# ---------------------------------------------------------------------------
# A full fix over a federation whose write scope excludes the associate.
# ---------------------------------------------------------------------------

_ENFORCED_PRIMARY_CONFIG = _PRIMARY_CONFIG.replace("hash_current = false", "hash_current = true")
_ENFORCED_ASSOCIATE_CONFIG = _ASSOCIATE_CONFIG.replace(
    "hash_current = false", "hash_current = true"
)


def _block(req_id: str, title: str, assertion: str, status: str, *, stale: bool) -> str:
    """One requirement whose recorded hash is stale, or current but out of canonical form.

    A current-hash block is written with its assertions heading one level too
    shallow and no blank line beneath it, so it needs a canonical-form rewrite
    and nothing else.
    """
    # The graph package is loaded first: importing the hasher before it is a
    # circular import.
    import elspais.graph  # noqa: F401
    from elspais.utilities.hasher import compute_normalized_hash

    meta = f"**Level**: PRD | **Status**: {status} | **Implements**: -"
    if stale:
        return (
            f"## {req_id}: {title}\n\n{meta}\n\n### Assertions\n\nA. {assertion}\n\n"
            f"*End* *{title}* | **Hash**: deadbeef\n"
        )
    digest = compute_normalized_hash([("A", assertion)])
    return (
        f"## {req_id}: {title}\n\n{meta}\n\n## Assertions\nA. {assertion}\n\n"
        f"*End* *{title}* | **Hash**: {digest}\n"
    )


def _fed_core() -> str:
    return (
        "# Core\n\n"
        + _block("REQ-p00001", "Stale One", "The system SHALL validate input.", "Draft", stale=True)
        + "\n---\n\n"
        + _block("REQ-p00002", "Untidy One", "The system SHALL log output.", "Draft", stale=False)
    )


def _fed_more() -> str:
    return (
        "# More\n\n"
        + _block("REQ-p00003", "Untidy Two", "The system SHALL keep records.", "Draft", stale=False)
        + "\n---\n\n"
        + _block("REQ-p00004", "Stale Two", "The system SHALL archive data.", "Draft", stale=True)
    )


def _fed_lib() -> str:
    return "# Callisto\n\n" + _block(
        "CAL-p00001", "Library Requirement", "The system SHALL process data.", "Active", stale=True
    )


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under *root*'s spec directory, by repository-relative path."""
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted((root / "spec").rglob("*"))
        if p.is_file()
    }


@pytest.fixture()
def federation_needing_fixes(tmp_path: Path) -> dict[str, Path]:
    """A primary whose Draft requirements carry stale hashes beside untidy parts,
    linked to an associate whose Active requirement a fix would changelog.

    Changelog enforcement is on in both repositories, so fixing the
    associate's stale hash would queue a changelog entry for its file.
    federation.write_associates is left at its default, false.
    """
    primary = tmp_path / "primary"
    associate = tmp_path / "callisto"
    (primary / "spec").mkdir(parents=True)
    (associate / "spec").mkdir(parents=True)
    (primary / ".elspais.toml").write_text(_ENFORCED_PRIMARY_CONFIG)
    (primary / "spec" / "core.md").write_text(_fed_core())
    (primary / "spec" / "more.md").write_text(_fed_more())
    (associate / ".elspais.toml").write_text(_ENFORCED_ASSOCIATE_CONFIG)
    (associate / "spec" / "lib.md").write_text(_fed_lib())
    return {"primary": primary, "associate": associate}


def _flagged(primary: Path) -> dict[str, set[str]]:
    """The requirements spec.hash_integrity and spec.needs_rewrite fault, by check."""
    from elspais.commands.health import run_spec_checks
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    config = get_config(primary / ".elspais.toml", primary)
    graph = build_graph(config_path=primary / ".elspais.toml", repo_root=primary)
    flagged: dict[str, set[str]] = {"spec.hash_integrity": set(), "spec.needs_rewrite": set()}
    for check in run_spec_checks(graph, config):
        if check.name not in flagged or check.passed:
            continue
        if check.name == "spec.hash_integrity":
            flagged[check.name] |= {m["id"] for m in check.details["mismatches"]}
        else:
            flagged[check.name] |= {f.node_id for f in check.findings}
    return flagged


class TestFullFixOverFederation:
    """A full fix writes every primary change it reports and nothing in the associate."""

    # Verifies: REQ-d00330-A, REQ-d00330-B, REQ-d00253-B, REQ-d00253-F
    def test_fix_writes_primary_changes_and_leaves_associate(
        self, federation_needing_fixes, monkeypatch, capsys
    ):
        from elspais.commands.fix_cmd import run

        primary = federation_needing_fixes["primary"]
        associate = federation_needing_fixes["associate"]
        associate_before = _tree(associate)
        # The precondition the fix must resolve: both checks fault the primary.
        assert _flagged(primary) == {
            "spec.hash_integrity": {"REQ-p00001", "REQ-p00004", "CAL-p00001"},
            "spec.needs_rewrite": {"REQ-p00001", "REQ-p00002", "REQ-p00003", "REQ-p00004"}
            | {"CAL-p00001"},
        }

        monkeypatch.chdir(primary)
        assert run(_args(primary, dry_run=True)) == 0
        planned = capsys.readouterr().out.splitlines()
        would = {line.split(":")[0].removeprefix("Would fix ") for line in planned}
        assert {"REQ-p00001", "REQ-p00002", "REQ-p00003", "REQ-p00004"} <= would
        assert not any(line.startswith("Would fix CAL-") for line in planned)

        rc = run(_args(primary))
        captured = capsys.readouterr()

        assert rc == 0, captured.err
        lines = captured.out.splitlines()
        # Each change the dry run reported is now reported as written.
        assert [
            ln.replace("Would fix", "Fixed", 1) for ln in planned if ln.startswith("Would fix ")
        ] == [ln for ln in lines if ln.startswith(("Fixed", "Not fixed"))]
        assert any(line.startswith("[skipping] CAL-p00001") for line in lines)
        assert _tree(associate) == associate_before

        core = (primary / "spec" / "core.md").read_text()
        more = (primary / "spec" / "more.md").read_text()
        assert "deadbeef" not in core and "deadbeef" not in more
        assert "## Assertions" not in core.replace("### Assertions", "")
        assert "## Assertions" not in more.replace("### Assertions", "")
        # Draft requirements need no changelog, so none was written.
        assert "Changelog" not in core + more

        # Nothing left for the same fix to resolve in the primary.
        # The associate's are still there, as the fix left them.
        assert _flagged(primary) == {
            "spec.hash_integrity": {"CAL-p00001"},
            "spec.needs_rewrite": {"CAL-p00001"},
        }

    # Verifies: REQ-d00253-B
    def test_primary_output_identical_without_associate(
        self, federation_needing_fixes, tmp_path, monkeypatch
    ):
        import shutil

        from elspais.commands.fix_cmd import run

        primary = federation_needing_fixes["primary"]
        solo = tmp_path / "solo"
        shutil.copytree(primary, solo)
        cfg = solo / ".elspais.toml"
        cfg.write_text(cfg.read_text().split("[associates.callisto]")[0])

        monkeypatch.chdir(primary)
        assert run(_args(primary)) == 0
        monkeypatch.chdir(solo)
        assert run(_args(solo)) == 0

        assert _tree(primary) == _tree(solo)

    # Verifies: REQ-d00248-A
    def test_second_fix_changes_nothing(self, federation_needing_fixes, monkeypatch, capsys):
        from elspais.commands.fix_cmd import run

        primary = federation_needing_fixes["primary"]
        associate = federation_needing_fixes["associate"]
        monkeypatch.chdir(primary)
        assert run(_args(primary)) == 0
        settled = (_tree(primary), _tree(associate))
        capsys.readouterr()

        assert run(_args(primary)) == 0
        out = capsys.readouterr().out.splitlines()

        assert (_tree(primary), _tree(associate)) == settled
        assert not any(line.startswith(("Fixed", "Not fixed", "Rewrote")) for line in out)


class TestFixRefusedWrite:
    """A save the filesystem refuses makes the fix fail and say why."""

    # Verifies: REQ-d00330-D, REQ-p00015-B
    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="the superuser writes a file whatever its mode",
    )
    def test_unwritable_file_fails_the_fix_and_names_it(
        self, federation_needing_fixes, monkeypatch, capsys
    ):
        from elspais.commands.fix_cmd import run

        primary = federation_needing_fixes["primary"]
        locked = primary / "spec" / "more.md"
        locked_before = locked.read_bytes()
        locked.chmod(0o444)
        try:
            monkeypatch.chdir(primary)
            rc = run(_args(primary))
            captured = capsys.readouterr()
        finally:
            locked.chmod(0o644)

        assert rc != 0
        lines = captured.out.splitlines()
        # The change in the writable file landed; those in the locked one did not.
        assert any(line.startswith("Fixed REQ-p00001") for line in lines)
        assert any(line.startswith("Not fixed REQ-p00004") for line in lines)
        assert not any(line.startswith("Fixed REQ-p00004") for line in lines)
        assert "deadbeef" not in (primary / "spec" / "core.md").read_text()
        assert locked.read_bytes() == locked_before
        assert "Error:" in captured.err and "more.md" in captured.err
