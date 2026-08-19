# Verifies: REQ-d00253-F
"""elspais fix must not claim to fix associate-owned content it will not write.

Validates REQ-d00253-F: with federation.write_associates=false, every
fix-report line for an associate-owned node is prefixed [skipping] (both
"Fixing" and dry-run "Would fix" reports); primary-repo lines stay plain.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

_PRIMARY_CONFIG = """\
version = 3

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
version = 3

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
        [(False, "Fixing"), (True, "Would fix")],
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
            mode="combined",
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
